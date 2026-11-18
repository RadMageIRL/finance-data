// DATA_CONVENTIONS v0.5 regression coverage (owner brief 2026-11-18, P2.4 acceptance): locks
// that keep a rejected historical change out after it leaves the fetch window, rollback locks
// that only an authorized review clears, lock state rebuilt from the published state after a
// restart, kept through retention and restore, delayed source revisions, Fiscal Data's missing
// values against a numeric zero, and the request identification.
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/bin/fixture-scenario.mjs';
const { debtDay, effrDay, loadInputs } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/lib/fixture-fetch.mjs';
const { makeFixtureFetch, makeWait } = m2 as unknown as Loose;
import * as m3 from '../../../pipeline/lib/run.mjs';
const { carriesLock, lockedChanges, restore, reviewHold, rollback, runCollector } = m3 as unknown as Loose;
import * as m9 from '../../../pipeline/lib/retention.mjs';
const { isSignificant } = m9 as unknown as Loose;
import * as m10 from '../../../pipeline/bin/collect.mjs';
const { collect } = m10 as unknown as Loose;
import * as m4 from '../../../pipeline/lib/normalize.mjs';
const { normalizeDebt, validateSeries } = m4 as unknown as Loose;
import * as m5 from '../../../pipeline/collectors/adapters.mjs';
const { adapterFetch } = m5 as unknown as Loose;
import * as m6 from '../../../pipeline/lib/fixture-transport.mjs';
const { loadRawFixtures, makeFixtureTransport } = m6 as unknown as Loose;
import * as m7 from '../../../pipeline/lib/json-schema.mjs';
const { validate } = m7 as unknown as Loose;
import * as m8 from '../../../pipeline/lib/calendar.mjs';
const { makeCalendar } = m8 as unknown as Loose;

const inputs = loadInputs({ slice: true });
const full = loadInputs();
const roots: string[] = [];
const newRoot = () => {
  const dir = mkdtempSync(join(tmpdir(), 'rmf-v05-'));
  roots.push(dir);
  return dir;
};
afterAll(() => {
  for (const r of roots) rmSync(r, { recursive: true, force: true });
});
const base = (root: string) => ({ root, mode: 'fixture', registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays });
const data = (effr: Loose[], debt: Loose[]): Loose => ({ effr: { records: effr }, debt: { rows: debt }, h6: { body: inputs.h6 } });
let counter = 0;
const go = (root: string, now: string, d: Loose, more: Loose = {}) => {
  counter += 1;
  return runCollector({ ...base(root), now, run: { id: `v05-${counter}`, attempt: 1, trigger: 'schedule', collector_commit: '0'.repeat(40) }, fetch: makeFixtureFetch(d), wait: makeWait(), ...more });
};
const review = (root: string, now: string, series: string, candidate_sha256: string, decision: string, more: Loose = {}) => reviewHold({ ...base(root), now, run: { id: `review-${now.replace(/[-:]/g, '')}`, attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, series, candidate_sha256, decision, reviewer: 'example-maintainer', reviewer_permission: 'maintain', permission_checked_at: now, reason: 'test decision', ...more });
const json = (root: string, rel: string) => JSON.parse(readFileSync(join(root, rel), 'utf8'));
const manifest = (root: string) => json(root, 'live/manifest.json');
const queue = (root: string) => json(root, 'archive/state/review-queue.json');
const FIRST = '2026-11-13T14:17:00Z';
const lastOf = (rows: Loose[]): Loose => rows[rows.length - 1] as Loose;
const plusCents = (text: string, cents: number) => {
  const [i = '0', f = '0'] = text.split('.');
  const total = BigInt(i) * 100n + BigInt(f) + BigInt(cents);
  return `${total / 100n}.${String(total % 100n).padStart(2, '0')}`;
};
const calendar = makeCalendar(full.holidays);

// Debt history with the total of 2026-09-15 changed by `cents`, and synthetic days to `until`.
const debtWith = (cents: number, until: string) => {
  let rows = inputs.debt.map((r: Loose) => (r.record_date === '2026-09-15' ? { ...r, tot_pub_debt_out_amt: plusCents(r.tot_pub_debt_out_amt, cents) } : r));
  for (let d = calendar.nextBusinessDay(lastOf(rows).record_date); d <= until; d = calendar.nextBusinessDay(d)) rows = [...rows, debtDay(lastOf(rows), d, 1_000_000)];
  return rows;
};
const effrTo = (until: string) => {
  const out = [...inputs.effr];
  for (let d = calendar.nextBusinessDay('2026-11-12'); d <= until; d = calendar.nextBusinessDay(d)) out.push(effrDay(d));
  return out;
};

/** A published root whose debt-total has a rejected change of 2026-09-15 (a historical period). */
const rejectedRoot = async () => {
  const root = newRoot();
  await go(root, FIRST, data(inputs.effr, inputs.debt));
  const held = await go(root, '2026-11-15T15:17:00Z', data(inputs.effr, debtWith(1, '2026-11-12')));
  const hash = held.snapshot.holds.find((h: Loose) => h.series === 'debt-total').candidate.sha256;
  const r = await review(root, '2026-11-16T13:00:00Z', 'debt-total', hash, 'reject');
  expect(r.outcome).toBe('published');
  return { root, hash };
};

describe('a rejected historical change stays locked outside the fetch window', () => {
  it('publishes nothing of the series on weekday windows and Sundays while the source keeps the change', async () => {
    const { root, hash } = await rejectedRoot();
    const lock = queue(root).frozen.find((f: Loose) => f.series === 'debt-total');
    expect(lock).toMatchObject({ origin: 'rejected', candidate_sha256: hash, locked_changes: [{ period: '2026-09-15', field: 'value' }] });
    // Monday evening: 2026-09-15 is before the 60-day window; a new day arrives.
    await go(root, '2026-11-16T22:17:00Z', data(effrTo('2026-11-13'), debtWith(1, '2026-11-13')));
    let m = manifest(root);
    expect(m.series['debt-total']).toMatchObject({ status: 'frozen', last_period: '2026-11-12' });
    expect(m.series['debt-held-public'].last_period).toBe('2026-11-13');
    // Sunday full fetch: the change is still there.
    await go(root, '2026-11-22T15:17:00Z', data(effrTo('2026-11-20'), debtWith(1, '2026-11-20')));
    m = manifest(root);
    expect(m.series['debt-total']).toMatchObject({ status: 'frozen', last_period: '2026-11-12' });
    expect(json(root, `live/${m.snapshot.path}`).frozen).toEqual([expect.objectContaining({ series: 'debt-total', origin: 'rejected' })]);
  });

  it('keeps the lock when the source reverts outside the window, and lifts it at the next full fetch', async () => {
    const { root } = await rejectedRoot();
    await go(root, '2026-11-16T22:17:00Z', data(effrTo('2026-11-13'), debtWith(1, '2026-11-13')));
    // The source reverts 2026-09-15 on a weekday: invisible to a windowed request.
    await go(root, '2026-11-24T22:17:00Z', data(effrTo('2026-11-23'), debtWith(0, '2026-11-23')));
    expect(manifest(root).series['debt-total'].status).toBe('frozen');
    // Sunday: the full fetch shows the change gone: the lock lifts and the new days publish.
    const r = await go(root, '2026-11-29T15:17:00Z', data(effrTo('2026-11-27'), debtWith(0, '2026-11-27')));
    expect(r.outcome).toBe('published');
    expect(manifest(root).series['debt-total']).toMatchObject({ last_period: '2026-11-27' });
    expect(manifest(root).series['debt-total'].status).not.toBe('frozen');
    expect(queue(root).frozen).toEqual([]);
  });

  it('opens a new hold when the source revises the rejected value again (a delayed revision)', async () => {
    const { root, hash } = await rejectedRoot();
    await go(root, '2026-11-16T22:17:00Z', data(effrTo('2026-11-13'), debtWith(1, '2026-11-13')));
    const r = await go(root, '2026-11-22T15:17:00Z', data(effrTo('2026-11-20'), debtWith(7, '2026-11-20')));
    const hold = r.snapshot.holds.find((h: Loose) => h.series === 'debt-total');
    expect(hold).toBeDefined();
    expect(hold.candidate.sha256).not.toBe(hash);
    expect(manifest(root).series['debt-total']).toMatchObject({ status: 'held', last_period: '2026-11-12' });
    expect(queue(root).frozen).toEqual([]);
  });

  it('rebuilds the lock from the published state after a run died between its manifest and its state files', async () => {
    const root = newRoot();
    await go(root, FIRST, data(inputs.effr, inputs.debt));
    const held = await go(root, '2026-11-15T15:17:00Z', data(inputs.effr, debtWith(1, '2026-11-12')));
    const hash = held.snapshot.holds.find((h: Loose) => h.series === 'debt-total').candidate.sha256;
    await expect(review(root, '2026-11-16T13:00:00Z', 'debt-total', hash, 'reject', { faults: { die: 'after-manifest' } })).rejects.toThrow(/simulated death/);
    // The manifest names the snapshot with the lock; the queue was not written.
    expect(json(root, `live/${manifest(root).snapshot.path}`).frozen.map((f: Loose) => f.series)).toEqual(['debt-total']);
    expect(queue(root).frozen).toEqual([]);
    await go(root, '2026-11-16T22:17:00Z', data(effrTo('2026-11-13'), debtWith(1, '2026-11-13')));
    expect(manifest(root).series['debt-total']).toMatchObject({ status: 'frozen', last_period: '2026-11-12' });
    expect(queue(root).frozen).toEqual([expect.objectContaining({ series: 'debt-total', origin: 'rejected', candidate_sha256: hash })]);
  });

  it('keeps the lock through retention cleanup and a restore from the archive', async () => {
    const { root, hash } = await rejectedRoot();
    // Six weeks of weekday EFFR days: older snapshots leave the live window.
    let pruned = 0;
    let previous = '2026-11-16';
    for (let d = '2026-11-17'; d <= '2026-12-31'; d = calendar.addBusinessDays(d, 3)) {
      const r = await go(root, `${d}T14:17:00Z`, data(effrTo(previous), debtWith(1, '2026-11-12')));
      pruned += (r.record?.pruned ?? []).length;
      previous = d;
    }
    expect(pruned).toBeGreaterThan(0);
    expect(manifest(root).series['debt-total'].status).toBe('frozen');
    expect(existsSync(join(root, 'archive/holds/debt-total', `${hash.slice(0, 16)}.json`))).toBe(true);
    rmSync(join(root, 'live'), { recursive: true, force: true });
    expect(restore({ root, now: '2027-01-01T12:00:00Z', run: { id: 'restore' } }).outcome).toBe('published');
    await go(root, '2027-01-04T22:17:00Z', data(effrTo('2026-12-31'), debtWith(1, '2026-12-31')));
    expect(manifest(root).series['debt-total']).toMatchObject({ status: 'frozen', last_period: '2026-11-12' });
  }, 120_000);
});

describe('a rollback locks what it took back until an authorized review clears it', () => {
  const rolledBack = async () => {
    const root = newRoot();
    const first = await go(root, FIRST, data(inputs.effr, inputs.debt));
    await go(root, '2026-11-16T14:17:00Z', data(effrTo('2026-11-13'), inputs.debt));
    const rb = await rollback({ ...base(root), now: '2026-11-16T15:00:00Z', run: { id: 'rb', attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, to: first.snapshot.id, reason: 'test rollback' });
    expect(rb.outcome).toBe('published');
    return { root };
  };

  it('locks every changed series, shows it frozen, and never republishes the withdrawn data on its own', async () => {
    const { root } = await rolledBack();
    let m = manifest(root);
    expect(m.rollback.locked).toEqual(['effr']);
    expect(m.series.effr.status).toBe('frozen');
    expect(m.series['debt-total'].status).not.toBe('frozen');
    const lock = queue(root).frozen.find((f: Loose) => f.series === 'effr');
    expect(lock).toMatchObject({ origin: 'rolled-back', reviewer: null, locked_changes: [{ period: '2026-11-13', field: 'period' }] });
    // The source still serves the withdrawn day, then a new one, then drops the withdrawn day.
    await go(root, '2026-11-16T16:17:00Z', data(effrTo('2026-11-13'), inputs.debt));
    await go(root, '2026-11-17T14:17:00Z', data(effrTo('2026-11-16'), inputs.debt));
    await go(root, '2026-11-18T14:17:00Z', data(effrTo('2026-11-17').filter((r: Loose) => r.effectiveDate !== '2026-11-13'), inputs.debt));
    m = manifest(root);
    expect(m.series.effr).toMatchObject({ status: 'frozen', last_period: '2026-11-12' });
    expect(json(root, `live/${m.snapshot.path}`).frozen).toEqual([expect.objectContaining({ series: 'effr', origin: 'rolled-back' })]);
  });

  it('turns away a clear without write access, then lets a maintainer clear it, after which the series publishes again', async () => {
    const { root } = await rolledBack();
    const hash = queue(root).frozen.find((f: Loose) => f.series === 'effr').candidate_sha256;
    const refused = await review(root, '2026-11-16T16:00:00Z', 'effr', hash, 'clear', { reviewer: 'example-reader', reviewer_permission: 'read' });
    expect(refused).toMatchObject({ outcome: 'refused', refused: 'permission' });
    expect((await review(root, '2026-11-16T16:01:00Z', 'debt-total', hash, 'clear')).refused).toBe('not-locked');
    expect((await review(root, '2026-11-16T16:02:00Z', 'effr', 'f'.repeat(64), 'clear')).refused).toBe('stale-candidate');
    const cleared = await review(root, '2026-11-16T16:05:00Z', 'effr', hash, 'clear');
    expect(cleared.outcome).toBe('published');
    const d = queue(root).decisions.find((x: Loose) => x.decision === 'clear');
    expect(d).toMatchObject({ series: 'effr', reviewer: 'example-maintainer', publication: { outcome: 'cleared' } });
    expect(manifest(root).series.effr.last_period).toBe('2026-11-12');
    await go(root, '2026-11-16T17:17:00Z', data(effrTo('2026-11-13'), inputs.debt));
    expect(manifest(root).series.effr).toMatchObject({ last_period: '2026-11-13', status: 'fresh' });
    expect(validate(JSON.parse(readFileSync('pipeline/schemas/review-queue.schema.json', 'utf8')), queue(root))).toEqual([]);
  });

  it('keeps a rollback lock after a run died before its state files, and after a restore', async () => {
    const root = newRoot();
    const first = await go(root, FIRST, data(inputs.effr, inputs.debt));
    await go(root, '2026-11-16T14:17:00Z', data(effrTo('2026-11-13'), inputs.debt));
    await expect(rollback({ ...base(root), now: '2026-11-16T15:00:00Z', run: { id: 'rb', attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, to: first.snapshot.id, reason: 'test rollback', faults: { die: 'after-manifest' } })).rejects.toThrow(/simulated death/);
    expect(manifest(root).rollback.locked).toEqual(['effr']);
    rmSync(join(root, 'live'), { recursive: true, force: true });
    expect(restore({ root, now: '2026-11-16T15:30:00Z', run: { id: 'restore' } }).outcome).toBe('published');
    await go(root, '2026-11-16T16:17:00Z', data(effrTo('2026-11-13'), inputs.debt));
    expect(manifest(root).series.effr).toMatchObject({ status: 'frozen', last_period: '2026-11-12' });
    expect(queue(root).frozen).toEqual([expect.objectContaining({ series: 'effr', origin: 'rolled-back' })]);
  });

  it('turns away an approval of a hold on a locked series until the lock is cleared', async () => {
    const root = newRoot();
    await go(root, FIRST, data(inputs.effr, inputs.debt));
    const changed = inputs.debt.map((r: Loose) => (r.record_date === '2026-11-10' ? { ...r, tot_pub_debt_out_amt: plusCents(r.tot_pub_debt_out_amt, 1) } : r));
    const held = await go(root, '2026-11-16T22:17:00Z', data(inputs.effr, changed));
    const holdHash = held.snapshot.holds[0].candidate.sha256;
    await review(root, '2026-11-17T13:00:00Z', 'debt-total', holdHash, 'approve');
    // Roll back to the held snapshot: the approved value is withdrawn and the hold comes back.
    const rb = await rollback({ ...base(root), now: '2026-11-17T14:00:00Z', run: { id: 'rb2', attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, to: held.snapshot.id, reason: 'test rollback' });
    expect(rb.outcome).toBe('published');
    expect(manifest(root).series['debt-total'].status).toBe('held');
    expect(manifest(root).rollback.locked).toEqual(['debt-total']);
    expect((await review(root, '2026-11-17T14:30:00Z', 'debt-total', holdHash, 'approve')).refused).toBe('locked');
    const lockHash = queue(root).frozen.find((f: Loose) => f.series === 'debt-total').candidate_sha256;
    expect((await review(root, '2026-11-17T14:35:00Z', 'debt-total', lockHash, 'clear')).outcome).toBe('published');
    expect((await review(root, '2026-11-17T14:40:00Z', 'debt-total', holdHash, 'approve')).outcome).toBe('published');
  });
});

describe('Fiscal Data missing values and zero', () => {
  const row = (over: Loose) => ({ ...lastOf(inputs.debt), ...over });
  const s = (id: string) => inputs.registry.series.find((x: Loose) => x.id === id);

  it('stores the string "null" as not published, never as zero', () => {
    const n = normalizeDebt([{ data: [row({ debt_held_public_amt: 'null', intragov_hold_amt: 'null' })], meta: { 'total-count': 1 } }], inputs.registry, inputs.sourceTable, { start: null });
    expect(n.problems).toEqual([]);
    expect(n.series['debt-held-public'][0]).toMatchObject({ value: null, missing: { code: 'not-published', note: '' } });
  });

  it('treats a JSON null or an empty amount as a format failure of the whole response', () => {
    for (const v of [null, '']) {
      const n = normalizeDebt([{ data: [row({ intragov_hold_amt: v })], meta: { 'total-count': 1 } }], inputs.registry, inputs.sourceTable, { start: null });
      expect(n.problems.length).toBeGreaterThan(0);
    }
  });

  it('never stores a zero amount: the series is invalid with its own problem', () => {
    for (const zero of ['0', '0.0', '0.00']) {
      const n = normalizeDebt([{ data: [row({ debt_held_public_amt: zero })], meta: { 'total-count': 1 } }], inputs.registry, inputs.sourceTable, { start: null });
      const obs = n.series['debt-held-public'];
      const problems = validateSeries(s('debt-held-public'), obs, '2026-11-18', null);
      expect(problems.join(' ')).toMatch(/zero/);
    }
  });
});

describe('request identification', () => {
  it('names RadMage Finance and its public URL on every request and never a browser', async () => {
    const raw = loadRawFixtures();
    const transport = makeFixtureTransport(raw, {});
    const fetch = adapterFetch({ registry: full.registry, transport, wait: makeWait() });
    await fetch({ group: 'effr', source: 'nyfed-markets', start: '2026-11-01', end: '2026-11-12', page: 1, full: false });
    await fetch({ group: 'debt-total', source: 'fiscaldata', start: '2026-11-01', end: '2026-11-12', page: 1, full: false });
    await fetch({ group: 'm1-sa', source: 'frb-releases', start: '1959-01', end: '2026-11-12', page: 1, full: true });
    expect(transport.calls.length).toBeGreaterThanOrEqual(4);
    for (const c of transport.calls) {
      expect(c.headers['User-Agent']).toBe('RadMage Finance (+https://radmagelabs.com/finance/)');
      expect(c.headers['User-Agent']).not.toMatch(/Mozilla|Chrome|Safari/);
      expect(c.headers.From).toBeUndefined();
    }
  });
});

describe('the lock rules', () => {
  const s = inputs.registry.series.find((x: Loose) => x.id === 'debt-total');
  const ob = (period: string, value: string) => ({ period, value, released: { date: null, basis: 'not-recorded' }, flags: [] });
  const published = [ob('2026-11-09', '1.00'), ob('2026-11-10', '2.00'), ob('2026-11-12', '3.00')];
  it('names the changed members, and new periods only for a rollback', () => {
    const locked = [ob('2026-11-09', '1.00'), ob('2026-11-10', '2.50'), ob('2026-11-11', '9.00'), ob('2026-11-12', '3.00'), ob('2026-11-13', '4.00')];
    expect(lockedChanges(s, published, locked, 'rejected')).toEqual([{ period: '2026-11-10', field: 'value' }, { period: '2026-11-11', field: 'period' }]);
    expect(lockedChanges(s, published, locked, 'rolled-back')).toEqual([{ period: '2026-11-10', field: 'value' }, { period: '2026-11-11', field: 'period' }, { period: '2026-11-13', field: 'period' }]);
  });
  it('tells whether a candidate still carries a locked change, for members, inserted and removed periods', () => {
    const locked = [ob('2026-11-09', '1.00'), ob('2026-11-10', '2.50'), ob('2026-11-11', '9.00')];
    const value = [{ period: '2026-11-10', field: 'value' }];
    const inserted = [{ period: '2026-11-11', field: 'period' }];
    const removed = [{ period: '2026-11-12', field: 'period' }];
    expect(carriesLock(s, locked, [...locked, ob('2026-11-12', '3.00')], value)).toBe(true);
    expect(carriesLock(s, locked, published, value)).toBe(false);
    expect(carriesLock(s, locked, [ob('2026-11-09', '1.00'), ob('2026-11-10', '2.70')], value)).toBe(false);
    expect(carriesLock(s, locked, [...locked], inserted)).toBe(true);
    expect(carriesLock(s, locked, [ob('2026-11-11', '9.10')], inserted)).toBe(false);
    expect(carriesLock(s, locked, published, inserted)).toBe(false);
    expect(carriesLock(s, locked, locked, removed)).toBe(true);
    expect(carriesLock(s, locked, published, removed)).toBe(false);
  });
  it('keeps a snapshot that locks or unlocks a series', () => {
    const snap = (frozen: string[]) => ({ previous: 'x', revisions: [], run: { trigger: 'schedule' }, holds: [], frozen: frozen.map((series) => ({ series })) });
    expect(isSignificant(snap(['effr']), snap([]))).toBe(true);
    expect(isSignificant(snap([]), snap(['effr']))).toBe(true);
    expect(isSignificant(snap(['effr']), snap(['effr']))).toBe(false);
  });
  it('turns away a live collection before it touches the root', async () => {
    const root = newRoot();
    await expect(collect({ mode: 'live', root })).rejects.toThrow(/live collection is not activated/);
    expect(existsSync(join(root, 'archive'))).toBe(false);
  });
});
