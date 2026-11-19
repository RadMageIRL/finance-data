// DATA_CONVENTIONS v0.6 regression coverage (owner brief 2026-11-19, Stage B): rejected additions
// stay locked while they persist, a rollback keeps rejections decided after its target, a series
// with two locks lifts them one by one, the rollback record rebuilds the locks after a crash and a
// restore, and a source-confirmed zero is accepted only for the period an entry names.
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
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
const { restore, reviewHold, rollback, runCollector } = m3 as unknown as Loose;
import * as m4 from '../../../pipeline/lib/normalize.mjs';
const { validateSeries } = m4 as unknown as Loose;
import * as m5 from '../../../pipeline/lib/registry-policy.mjs';
const { registryProblems } = m5 as unknown as Loose;
import * as m6 from '../../../pipeline/lib/json-schema.mjs';
const { validate } = m6 as unknown as Loose;

const inputs = loadInputs({ slice: true });
const roots: string[] = [];
const newRoot = () => {
  const d = mkdtempSync(join(tmpdir(), 'rmf-v06-'));
  roots.push(d);
  return d;
};
afterAll(() => {
  for (const r of roots) rmSync(r, { recursive: true, force: true });
});
const base = (root: string) => ({ root, mode: 'fixture', registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays });
const data = (effr: Loose[], debt: Loose[]): Loose => ({ effr: { records: effr }, debt: { rows: debt }, h6: { body: inputs.h6 } });
let counter = 0;
const go = (root: string, now: string, d: Loose, more: Loose = {}) => {
  counter += 1;
  return runCollector({ ...base(root), now, run: { id: `v06-${counter}`, attempt: 1, trigger: 'schedule', collector_commit: '0'.repeat(40) }, fetch: makeFixtureFetch(d), wait: makeWait(), ...more });
};
const review = (root: string, now: string, series: string, candidate_sha256: string, decision: string) => reviewHold({ ...base(root), now, run: { id: `review-${now.replace(/[-:]/g, '')}`, attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, series, candidate_sha256, decision, reviewer: 'example-maintainer', reviewer_permission: 'maintain', permission_checked_at: now, reason: 'test decision' });
const roll = (root: string, now: string, to: string, more: Loose = {}) => rollback({ ...base(root), now, run: { id: `rb-${now.replace(/[-:]/g, '')}`, attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, to, reason: 'test rollback', ...more });
const json = (root: string, rel: string) => JSON.parse(readFileSync(join(root, rel), 'utf8'));
const manifest = (root: string) => json(root, 'live/manifest.json');
const queue = (root: string) => json(root, 'archive/state/review-queue.json');
const locksOf = (root: string, id: string) => queue(root).frozen.filter((f: Loose) => f.series === id).map((f: Loose) => f.origin).sort();
const FIRST = '2026-11-13T14:17:00Z';
const lastOf = (rows: Loose[]): Loose => rows[rows.length - 1] as Loose;
const cents = (text: string, n: number) => {
  const [i = '0', f = '0'] = text.split('.');
  const t = BigInt(i) * 100n + BigInt(f) + BigInt(n);
  return `${t / 100n}.${String(t % 100n).padStart(2, '0')}`;
};
const change = (rows: Loose[], date: string, n: number) => rows.map((r) => (r.record_date === date ? { ...r, tot_pub_debt_out_amt: cents(r.tot_pub_debt_out_amt, n) } : r));
const plusDay = (rows: Loose[], date: string, amount = 1_000_000) => [...rows, debtDay(lastOf(rows), date, amount)];
const holdHash = (r: Loose, id: string) => r.snapshot.holds.find((h: Loose) => h.series === id).candidate.sha256;

describe('rejected additions stay locked while they persist', () => {
  it('keeps the lock after the changed value reverts, because the rejected new day is still there', async () => {
    const root = newRoot();
    await go(root, FIRST, data(inputs.effr, inputs.debt));
    const rejected = plusDay(change(inputs.debt, '2026-11-10', 1), '2026-11-13');
    const held = await go(root, '2026-11-16T22:17:00Z', data(inputs.effr, rejected));
    expect((await review(root, '2026-11-17T13:00:00Z', 'debt-total', holdHash(held, 'debt-total'), 'reject')).outcome).toBe('published');
    expect(queue(root).frozen.find((f: Loose) => f.series === 'debt-total').locked_changes).toEqual([{ period: '2026-11-10', field: 'value' }, { period: '2026-11-13', field: 'period' }]);
    // The source reverts 2026-11-10 but keeps the rejected day 2026-11-13 unchanged, and adds one.
    const reverted = plusDay(plusDay(inputs.debt, '2026-11-13'), '2026-11-16');
    await go(root, '2026-11-17T22:17:00Z', data(inputs.effr, reverted));
    expect(manifest(root).series['debt-total']).toMatchObject({ status: 'frozen', last_period: '2026-11-12' });
    expect(manifest(root).series['debt-held-public'].last_period).toBe('2026-11-16');
    // Only when the rejected addition changes in the source does the lock lift.
    const moved = reverted.map((r) => (r.record_date === '2026-11-13' ? { ...r, tot_pub_debt_out_amt: cents(r.tot_pub_debt_out_amt, 5) } : r));
    await go(root, '2026-11-18T22:17:00Z', data(inputs.effr, moved));
    expect(manifest(root).series['debt-total']).toMatchObject({ last_period: '2026-11-16' });
    expect(locksOf(root, 'debt-total')).toEqual([]);
  });
});

describe('a rollback keeps every lock in force', () => {
  /** S1 first; S2 an EFFR day; S3 a debt hold, rejected after S2; S4 another EFFR day. */
  const built = async () => {
    const root = newRoot();
    await go(root, FIRST, data(inputs.effr, inputs.debt));
    const s2 = await go(root, '2026-11-16T14:17:00Z', data([...inputs.effr, effrDay('2026-11-13')], inputs.debt));
    const held = await go(root, '2026-11-16T22:17:00Z', data([...inputs.effr, effrDay('2026-11-13')], change(inputs.debt, '2026-11-10', 1)));
    await review(root, '2026-11-17T13:00:00Z', 'debt-total', holdHash(held, 'debt-total'), 'reject');
    await go(root, '2026-11-17T14:17:00Z', data([...inputs.effr, effrDay('2026-11-13'), effrDay('2026-11-16')], change(inputs.debt, '2026-11-10', 1)));
    return { root, s2: s2.snapshot.id as string };
  };

  it('keeps a rejection decided after its target, records it, and shows both series frozen', async () => {
    const { root, s2 } = await built();
    expect((await roll(root, '2026-11-17T15:00:00Z', s2)).outcome).toBe('published');
    const m = manifest(root);
    expect(m.rollback.locked).toEqual(['effr', 'debt-total']);
    expect(m.series.effr.status).toBe('frozen');
    expect(m.series['debt-total'].status).toBe('frozen');
    const rec = json(root, 'archive/rollbacks/20261117T150000Z.json');
    expect(validate(JSON.parse(readFileSync('pipeline/schemas/rollback.schema.json', 'utf8')), rec)).toEqual([]);
    expect(rec.locks.map((l: Loose) => [l.series, l.origin])).toEqual([['effr', 'rolled-back'], ['debt-total', 'rejected']]);
    // The next run still publishes nothing of either.
    await go(root, '2026-11-17T22:17:00Z', data([...inputs.effr, effrDay('2026-11-13'), effrDay('2026-11-16')], plusDay(change(inputs.debt, '2026-11-10', 1), '2026-11-13')));
    expect(manifest(root).series['debt-total']).toMatchObject({ status: 'frozen', last_period: '2026-11-12' });
    expect(locksOf(root, 'debt-total')).toEqual(['rejected']);
    expect(locksOf(root, 'effr')).toEqual(['rolled-back']);
  });

  it('rebuilds those locks from the rollback record after a run that died, and after a restore', async () => {
    const { root, s2 } = await built();
    await expect(roll(root, '2026-11-17T15:00:00Z', s2, { faults: { die: 'after-manifest' } })).rejects.toThrow(/simulated death/);
    rmSync(join(root, 'live'), { recursive: true, force: true });
    expect(restore({ root, now: '2026-11-17T15:30:00Z', run: { id: 'restore' } }).outcome).toBe('published');
    await go(root, '2026-11-17T22:17:00Z', data([...inputs.effr, effrDay('2026-11-13'), effrDay('2026-11-16')], change(inputs.debt, '2026-11-10', 1)));
    expect(manifest(root).series['debt-total'].status).toBe('frozen');
    expect(manifest(root).series.effr.status).toBe('frozen');
    expect(locksOf(root, 'debt-total')).toEqual(['rejected']);
  });

  it('lifts two locks of one series one at a time', async () => {
    const root = newRoot();
    const first = await go(root, FIRST, data(inputs.effr, inputs.debt));
    await go(root, '2026-11-16T22:17:00Z', data(inputs.effr, plusDay(inputs.debt, '2026-11-13')));
    const changed = plusDay(change(plusDay(inputs.debt, '2026-11-13'), '2026-11-10', 1), '2026-11-16');
    const held = await go(root, '2026-11-17T22:17:00Z', data(inputs.effr, changed));
    await review(root, '2026-11-18T13:00:00Z', 'debt-total', holdHash(held, 'debt-total'), 'reject');
    // Rolling back to the first snapshot withdraws 2026-11-13 of debt-total: a second lock.
    await roll(root, '2026-11-18T14:00:00Z', first.snapshot.id);
    expect(locksOf(root, 'debt-total')).toEqual(['rejected', 'rolled-back']);
    const lockOf = (origin: string) => queue(root).frozen.find((f: Loose) => f.series === 'debt-total' && f.origin === origin).candidate_sha256;
    expect((await review(root, '2026-11-18T14:10:00Z', 'debt-total', lockOf('rolled-back'), 'clear')).outcome).toBe('published');
    expect(locksOf(root, 'debt-total')).toEqual(['rejected']);
    expect(manifest(root).series['debt-total'].status).toBe('frozen');
    expect((await review(root, '2026-11-18T14:20:00Z', 'debt-total', lockOf('rejected'), 'clear')).outcome).toBe('published');
    expect(locksOf(root, 'debt-total')).toEqual([]);
    expect(manifest(root).series['debt-total'].status).not.toBe('frozen');
  });
});

describe('a source-confirmed zero', () => {
  const s = inputs.registry.series.find((x: Loose) => x.id === 'debt-held-public');
  const ob = (period: string, value: string) => ({ period, value, released: { date: null, basis: 'not-recorded' }, flags: [] });
  const entry = { period: '2026-11-10', field: 'value', checked: '2026-11-19', evidence: 'test evidence', authorized_by: 'example-maintainer', authorized_at: '2026-11-19T12:00:00Z' };
  const accepted = { ...s, accepted_zeros: [entry] };
  const obs = [ob('2026-11-09', '29000000000000.00'), ob('2026-11-10', '0.00'), ob('2026-11-12', '29000000000001.00')];

  it('is accepted for exactly the named period, stored as zero, never as missing', () => {
    expect(validateSeries(accepted, obs, '2026-11-19', null)).toEqual([]);
    const zero = obs[1] as Loose;
    expect(zero).toEqual(expect.objectContaining({ value: '0.00' }));
    expect('missing' in zero).toBe(false);
    expect(validateSeries(s, obs, '2026-11-19', null).join(' ')).toMatch(/is zero/);
    const other = [ob('2026-11-09', '0.00'), ob('2026-11-10', '0.00'), ob('2026-11-12', '1.00')];
    expect(validateSeries(accepted, other, '2026-11-19', null).join(' ')).toMatch(/2026-11-09: value 0.00 is zero/);
  });

  it('cannot name a future period, a series without refuse_zero, or an automation account', () => {
    const reg = (patch: Loose) => {
      const r = JSON.parse(JSON.stringify(inputs.registry));
      Object.assign(r.series.find((x: Loose) => x.id === patch.id), patch.fields);
      return registryProblems(r);
    };
    expect(reg({ id: 'debt-held-public', fields: { accepted_zeros: [entry] } })).toEqual([]);
    expect(reg({ id: 'debt-held-public', fields: { accepted_zeros: [{ ...entry, period: '2026-11-20' }] } }).join(' ')).toMatch(/after the date it was checked or authorized/);
    expect(reg({ id: 'effr', fields: { accepted_zeros: [{ ...entry, period: '2026-11-10' }] } }).join(' ')).toMatch(/refuse_zero/);
    expect(reg({ id: 'debt-held-public', fields: { accepted_zeros: [{ ...entry, authorized_by: 'github-actions[bot]' }] } }).join(' ')).toMatch(/by a person/);
    expect(reg({ id: 'debt-held-public', fields: { accepted_zeros: [entry, entry] } }).join(' ')).toMatch(/duplicate/);
  });
});
