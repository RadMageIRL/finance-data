// DATA_CONVENTIONS v0.4 regression coverage (owner brief 2026-11-18): CSV segments that are
// never rewritten when unchanged, historical revisions that keep the earlier segment versions
// recoverable, manifest consistency, the five kinds of absent data and source gaps, rollback
// and restore of segmented data, review authorization, unknown publication zones, held
// windowed candidates and route notices.
import { createHash } from 'node:crypto';
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/bin/fixture-scenario.mjs';
const { debtDay, effrDay, loadInputs, sliceRegistry } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/lib/fixture-fetch.mjs';
const { makeFixtureFetch, makeWait } = m2 as unknown as Loose;
import * as m3 from '../../../pipeline/lib/run.mjs';
const { restore, reviewHold, rollback, runCollector } = m3 as unknown as Loose;
import * as m4 from '../../../pipeline/lib/fixture-transport.mjs';
const { loadRawFixtures } = m4 as unknown as Loose;
import * as m5 from '../../../pipeline/lib/tree.mjs';
const { deadlines } = m5 as unknown as Loose;
import * as m6 from '../../../pipeline/lib/calendar.mjs';
const { makeCalendar } = m6 as unknown as Loose;
import * as m7 from '../../../pipeline/lib/alerts.mjs';
const { routeNoticeAlerts } = m7 as unknown as Loose;
import * as m8 from '../../../pipeline/lib/store.mjs';
const { listFiles } = m8 as unknown as Loose;
import * as m9 from '../../../pipeline/lib/json-schema.mjs';
const { validate } = m9 as unknown as Loose;
import * as m10 from '../../../pipeline/lib/canonical.mjs';
const { canonicalJson } = m10 as unknown as Loose;

const full = loadInputs();
const slice = loadInputs({ slice: true });
const raw = loadRawFixtures();
const START = '2025-10-01';
// A registry whose daily series begin on 2025-10-01: two years of objects and CSV segments.
const registry = sliceRegistry(full.registry, { 'nyfed-markets': START, fiscaldata: START, 'frb-releases': '2024-10' });
const effr0 = raw.effr.map((r: Loose) => JSON.parse(r.text)).filter((r: Loose) => r.effectiveDate >= START);
const debt0 = raw.debt.filter((r: Loose) => r.record_date >= START);
const h6 = slice.h6;
const calendar = makeCalendar(full.holidays);

const roots: string[] = [];
const newRoot = () => {
  const dir = mkdtempSync(join(tmpdir(), 'rmf-v04-'));
  roots.push(dir);
  return dir;
};
afterAll(() => {
  for (const r of roots) rmSync(r, { recursive: true, force: true });
});
const base = (root: string, reg = registry) => ({ root, mode: 'fixture', registry: reg, schemas: full.schemas, sourceTable: full.sourceTable, holidays: full.holidays });
const data = (effr = effr0, debt = debt0): Loose => ({ effr: { records: effr }, debt: { rows: debt }, h6: { body: h6 } });
let counter = 0;
const go = (root: string, now: string, d = data(), scripted = {}, reg = registry) => {
  counter += 1;
  return runCollector({ ...base(root, reg), now, run: { id: `v04-${counter}`, attempt: 1, trigger: 'schedule', collector_commit: '0'.repeat(40) }, fetch: makeFixtureFetch(d, scripted), wait: makeWait() });
};
const json = (root: string, rel: string) => JSON.parse(readFileSync(join(root, rel), 'utf8'));
const manifest = (root: string) => json(root, 'live/manifest.json');
const archived = (root: string, dir: string) => (existsSync(join(root, 'archive/files', dir)) ? listFiles(join(root, 'archive/files', dir)) : []);
const sha = (text: string) => createHash('sha256').update(text).digest('hex');
const review = (root: string, now: string, more: Loose) => reviewHold({ ...base(root), now, run: { id: `review-${now.replace(/[-:]/g, '')}`, attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, series: 'debt-total', reviewer: 'example-maintainer', reviewer_permission: 'maintain', permission_checked_at: now, reason: 'test decision', ...more });
const FIRST = '2026-11-13T14:17:00Z';
const lastDebt = (rows: Loose[]) => rows[rows.length - 1];

describe('CSV segments', () => {
  it('writes one CSV per object and never writes or archives an unchanged year again', async () => {
    const root = newRoot();
    expect((await go(root, FIRST)).outcome).toBe('published');
    const m = manifest(root);
    const effr = m.series.effr;
    expect(effr.csvs.map((c: Loose) => c.segment)).toEqual(['2025', '2026']);
    expect(effr.csvs.map((c: Loose) => c.path.split('/')[2])).toEqual(['2025', '2026']);
    expect(effr.objects.length).toBe(2);
    for (const c of effr.csvs) {
      const text = readFileSync(join(root, 'live', c.path), 'utf8');
      expect(sha(text)).toBe(c.sha256);
      expect(c.retrieved_at).toBe(FIRST);
      expect(text).toContain(`# Segment ${c.segment}: ${c.segment === '2025' ? '2025-10-01' : '2026-01-02'} to ${c.segment === '2025' ? '2025-12-31' : '2026-11-12'}.\n# Retrieved ${FIRST} by RadMage Finance.\n`);
    }
    expect(m.series['m1-sa'].csvs.map((c: Loose) => c.segment)).toEqual(['all']);
    expect(archived(root, 'series/effr').length).toBe(2);
    // A new day: only the 2026 segment is new; 2025 keeps its file and its retrieval time.
    const now = '2026-11-16T14:17:00Z';
    expect((await go(root, now, data([...effr0, effrDay('2026-11-13')]))).outcome).toBe('published');
    const next = manifest(root).series.effr.csvs;
    expect(next[0]).toEqual(effr.csvs[0]);
    expect(next[1].retrieved_at).toBe(now);
    expect(next[1].path).not.toBe(effr.csvs[1].path);
    expect(archived(root, 'series/effr').length).toBe(3);
    // Unchanged series wrote no CSV at all.
    expect(archived(root, 'series/debt-total').length).toBe(2);
    expect(manifest(root).series['debt-total'].csvs).toEqual(m.series['debt-total'].csvs);
  });

  it('keeps the manifest consistent: no full-history CSV, segments match objects, schemas pass', async () => {
    const root = newRoot();
    await go(root, FIRST);
    const m = manifest(root);
    expect(validate(full.schemas.manifest, m)).toEqual([]);
    for (const [id, s] of Object.entries(m.series) as [string, Loose][]) {
      expect(s.csvs.map((c: Loose) => c.segment)).toEqual(s.objects.map((o: Loose) => o.path.split('/')[2]));
      for (const c of s.csvs) expect(c.path).toMatch(new RegExp(`^series/${id}/(\\d{4}|all)/[0-9a-f]{16}\\.csv$`));
    }
    expect(listFiles(join(root, 'live/series')).every((p: string) => p.split('/').length === 3)).toBe(true);
  });
});

describe('the gate on CSV segments', () => {
  const broken = async (mutate: (m: Loose) => void) => {
    const root = newRoot();
    await go(root, FIRST);
    const r = await runCollector({
      ...base(root),
      now: '2026-11-16T14:17:00Z',
      run: { id: 'broken', attempt: 1, trigger: 'schedule', collector_commit: '0'.repeat(40) },
      fetch: makeFixtureFetch(data([...effr0, effrDay('2026-11-13')])),
      wait: makeWait(),
      faults: {
        breakStaged: (staged: Map<string, string>) => {
          const m = JSON.parse(staged.get('manifest.json') as string);
          mutate(m);
          staged.set('manifest.json', canonicalJson(m));
        },
      },
    });
    return { root, r };
  };
  it('fails the gate for a carried segment with a new retrieval time', async () => {
    const { r } = await broken((m) => {
      m.series.effr.csvs[0].retrieved_at = '2026-11-16T14:17:00Z';
    });
    expect(r.outcome).toBe('gate-failed');
    expect(r.problems.join('\n')).toMatch(/gate 9: effr: CSV segment 2025/);
  });
  it('fails the gate for a manifest that drops a segment', async () => {
    const { r } = await broken((m) => {
      m.series.effr.csvs = m.series.effr.csvs.slice(1);
    });
    expect(r.outcome).toBe('gate-failed');
    expect(r.problems.join('\n')).toMatch(/gate 9: effr/);
  });
});

describe('historical revisions and rollback recovery', () => {
  // A Sunday full fetch finds the published total of 2025-10-15 one dollar higher.
  const changed = debt0.map((r: Loose) => (r.record_date === '2025-10-15' ? { ...r, tot_pub_debt_out_amt: r.tot_pub_debt_out_amt.replace(/^(\d+)/, (x: string) => (BigInt(x) + 1n).toString()) } : r));
  const heldRoot = async () => {
    const root = newRoot();
    await go(root, FIRST);
    const held = await go(root, '2026-11-15T15:17:00Z', data(effr0, changed));
    return { root, held };
  };

  it('keeps the historical change in the held candidate on weekday windowed runs', async () => {
    const { root, held } = await heldRoot();
    expect(held.snapshot.holds.map((h: Loose) => h.series)).toEqual(['debt-total']);
    const withDay = [...changed, debtDay(lastDebt(changed), '2026-11-13', 1_000_000_000)];
    const r = await go(root, '2026-11-16T22:17:00Z', data([...effr0, effrDay('2026-11-13')], withDay));
    const h = r.snapshot.holds.find((x: Loose) => x.series === 'debt-total');
    const candidate = JSON.parse(readFileSync(join(root, 'archive/holds/debt-total', `${h.candidate.sha256.slice(0, 16)}.json`), 'utf8'));
    const oct15 = candidate.find((o: Loose) => o.period === '2025-10-15');
    expect(oct15.value).toBe(changed.find((x: Loose) => x.record_date === '2025-10-15').tot_pub_debt_out_amt);
    expect(candidate[candidate.length - 1].period).toBe('2026-11-13');
  });

  it('rewrites only the revised year, keeps the earlier version recoverable, and rolls back and restores it', async () => {
    const { root, held } = await heldRoot();
    const before = manifest(root).series['debt-total'];
    const hash = held.snapshot.holds[0].candidate.sha256;
    const approved = await review(root, '2026-11-16T15:00:00Z', { candidate_sha256: hash, decision: 'approve' });
    expect(approved.outcome).toBe('published');
    const after = manifest(root).series['debt-total'];
    expect(after.csvs[1]).toEqual(before.csvs[1]);
    expect(after.csvs[0].path).not.toBe(before.csvs[0].path);
    expect(after.objects[1]).toEqual(before.objects[1]);
    // The earlier 2025 versions stay in the archive and still match their hashes.
    const oldCsv = readFileSync(join(root, 'archive/files', before.csvs[0].path), 'utf8');
    expect(sha(oldCsv)).toBe(before.csvs[0].sha256);
    expect(sha(readFileSync(join(root, 'archive/files', before.objects[0].path), 'utf8'))).toBe(before.objects[0].sha256);
    // Rollback to the first publication names the earlier segments again, and they are live.
    const firstId = json(root, 'live/status/publications.json').publications[0].snapshot;
    const rb = await rollback({ ...base(root), now: '2026-11-16T16:00:00Z', run: { id: 'rb', attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, to: firstId, reason: 'test rollback' });
    expect(rb.outcome).toBe('published');
    const rolled = manifest(root).series['debt-total'];
    expect(rolled.csvs).toEqual(before.csvs);
    for (const c of rolled.csvs) expect(sha(readFileSync(join(root, 'live', c.path), 'utf8'))).toBe(c.sha256);
    const log = json(root, `live/${rolled.revisions[rolled.revisions.length - 1].path}`);
    expect(log.records.map((x: Loose) => [x.period, x.kind])).toEqual([['2025-10-15', 'approved-hold'], ['2025-10-15', 'rollback']]);
    // Restore from the archive alone gives the same live tree.
    const liveBefore = listFiles(join(root, 'live')).filter((f: string) => !f.startsWith('status/'));
    rmSync(join(root, 'live'), { recursive: true, force: true });
    const r = restore({ root, now: '2026-11-16T16:30:00Z', run: { id: 'restore' } });
    expect(r.outcome).toBe('published');
    expect(manifest(root).series['debt-total'].csvs).toEqual(before.csvs);
    expect(listFiles(join(root, 'live')).filter((f: string) => !f.startsWith('status/'))).toEqual(liveBefore);
  });
});

describe('review authorization', () => {
  const heldRoot = async () => {
    const root = newRoot();
    await go(root, FIRST);
    const debt = debt0.map((r: Loose) => (r.record_date === '2026-11-10' ? { ...r, tot_pub_debt_out_amt: r.tot_pub_debt_out_amt.replace(/\.\d\d$/, '.01') } : r));
    const held = await go(root, '2026-11-16T22:17:00Z', data(effr0, debt));
    return { root, hash: held.snapshot.holds[0].candidate.sha256 as string };
  };
  const NOW = '2026-11-17T15:00:00Z';

  for (const [label, more, rule] of [
    ['a reader', { reviewer_permission: 'read' }, 'permission'],
    ['a triage account', { reviewer_permission: 'triage' }, 'permission'],
    ['an account without access', { reviewer_permission: 'none' }, 'permission'],
    ['a permission read more than an hour before', { permission_checked_at: '2026-11-17T13:59:59Z' }, 'permission-time'],
    ['a permission read after the review', { permission_checked_at: '2026-11-17T15:00:01Z' }, 'permission-time'],
    ['an automation account', { reviewer: 'github-actions[bot]', reviewer_permission: 'write' }, 'automation'],
    ['the Actions login', { reviewer: 'github-actions', reviewer_permission: 'admin' }, 'automation'],
    ['an empty reason', { reason: ' ' }, 'missing-text'],
  ] as [string, Loose, string][]) {
    it(`turns away ${label}, records the refusal and changes nothing else`, async () => {
      const { root, hash } = await heldRoot();
      const liveBefore = readFileSync(join(root, 'live/manifest.json'), 'utf8');
      const r = await review(root, NOW, { candidate_sha256: hash, decision: 'approve', ...more });
      expect(r.outcome).toBe('refused');
      expect(r.refused).toBe(rule);
      expect(readFileSync(join(root, 'live/manifest.json'), 'utf8')).toBe(liveBefore);
      const q = json(root, 'archive/state/review-queue.json');
      expect(q.open.map((x: Loose) => x.series)).toEqual(['debt-total']);
      expect(q.decisions).toEqual([]);
      expect(q.refusals).toHaveLength(1);
      expect(q.refusals[0]).toMatchObject({ series: 'debt-total', candidate_sha256: hash, decision: 'approve', at: NOW, refused: rule });
      expect(JSON.stringify(q.refusals[0])).not.toContain('test decision');
      expect(json(root, `archive/state/run-records/review-${NOW.replace(/[-:]/g, '')}.json`)).toMatchObject({ outcome: 'refused', snapshot: null, absences: [] });
    });
  }

  it('accepts a permission read exactly an hour before, and records permission and publication outcome', async () => {
    const { root, hash } = await heldRoot();
    const r = await review(root, NOW, { candidate_sha256: hash, decision: 'approve', reviewer_permission: 'write', permission_checked_at: '2026-11-17T14:00:00Z' });
    expect(r.outcome).toBe('published');
    const d = json(root, 'archive/state/review-queue.json').decisions[0];
    expect(d).toMatchObject({ decision: 'approve', reviewer: 'example-maintainer', reviewer_permission: 'write', permission_checked_at: '2026-11-17T14:00:00Z', publication: { outcome: 'published', snapshot: '20261117T150000Z' } });
    expect(d.record).toBe(`reviews/debt-total/${hash.slice(0, 16)}-approve-20261117T150000Z.json`);
    const rec = json(root, `archive/${d.record}`);
    expect(rec).toMatchObject({ schema: 'rmf.econ.review/3', reviewer_permission: 'write', publication: { outcome: 'published', snapshot: '20261117T150000Z' } });
    expect(validate(JSON.parse(readFileSync('pipeline/schemas/review.schema.json', 'utf8')), rec)).toEqual([]);
    expect(validate(JSON.parse(readFileSync('pipeline/schemas/review-queue.schema.json', 'utf8')), json(root, 'archive/state/review-queue.json'))).toEqual([]);
  });

  it('keeps every candidate: a candidate withdrawn twice gets two records, and rejected ones stay in the archive', async () => {
    const { root, hash } = await heldRoot();
    const debt = debt0.map((r: Loose) => (r.record_date === '2026-11-10' ? { ...r, tot_pub_debt_out_amt: r.tot_pub_debt_out_amt.replace(/\.\d\d$/, '.01') } : r));
    await go(root, '2026-11-17T14:17:00Z'); // the source returns: withdrawn
    await go(root, '2026-11-17T22:17:00Z', data(effr0, debt)); // the same candidate again: held
    await go(root, '2026-11-18T14:17:00Z'); // withdrawn again
    const q = json(root, 'archive/state/review-queue.json');
    expect(q.decisions.map((d: Loose) => [d.decision, d.publication.outcome])).toEqual([['withdrawn', 'withdrawn'], ['withdrawn', 'withdrawn']]);
    expect(new Set(q.decisions.map((d: Loose) => d.record)).size).toBe(2);
    for (const d of q.decisions) expect(existsSync(join(root, 'archive', d.record))).toBe(true);
    expect(existsSync(join(root, 'archive/holds/debt-total', `${hash.slice(0, 16)}.json`))).toBe(true);
  });
});

describe('absent data', () => {
  const kinds = (r: Loose, id: string) => r.record.absences.filter((a: Loose) => a.series === id).map((a: Loose) => [a.period, a.kind, a.detail]);

  it('tells a holiday, a period not yet due, a late source and a failing collection apart', async () => {
    const root = newRoot();
    const to1110 = effr0.filter((r: Loose) => r.effectiveDate <= '2026-11-10');
    await go(root, '2026-11-11T14:17:00Z', data(to1110, debt0.filter((r: Loose) => r.record_date <= '2026-11-09')));
    // Thursday 11:17 ET: 2026-11-11 is Veterans Day; 2026-11-12 is not due yet.
    const thu = await go(root, '2026-11-12T16:17:00Z', data(to1110, debt0.filter((r: Loose) => r.record_date <= '2026-11-09')));
    expect(kinds(thu, 'effr')).toEqual([['2026-11-11', 'expected-nonpublication', 'holiday'], ['2026-11-12', 'expected-nonpublication', 'not-yet-due']]);
    // Friday 16:17 ET: the EFFR for 2026-11-12 was due by 15:00 ET; the source still lacks it.
    const late = await go(root, '2026-11-13T21:17:00Z', data(to1110, debt0.filter((r: Loose) => r.record_date <= '2026-11-09')));
    expect(kinds(late, 'effr')).toEqual([['2026-11-11', 'expected-nonpublication', 'holiday'], ['2026-11-12', 'source-overdue', 'after-deadline'], ['2026-11-13', 'expected-nonpublication', 'not-yet-due']]);
    expect(late.record.alerts).toContain('source-overdue:effr');
    expect(late.record.alerts).not.toContain('fetch-failures:nyfed-markets');
    // The same moment with the request failing: a collection failure.
    const failing = await go(root, '2026-11-13T22:17:00Z', data(to1110, debt0.filter((r: Loose) => r.record_date <= '2026-11-09')), { effr: [{ status: 503 }, { status: 503 }, { status: 503 }, { status: 503 }] });
    expect(kinds(failing, 'effr')).toEqual([['2026-11-11', 'expected-nonpublication', 'holiday'], ['2026-11-12', 'collection-failure', 'fetch-failed'], ['2026-11-13', 'expected-nonpublication', 'not-yet-due']]);
    expect(failing.record.alerts).not.toContain('source-overdue:effr');
  });

  it('keeps an undocumented gap out, raises source-gap, and publishes once the gap is documented', async () => {
    const root = newRoot();
    const gap = debt0.filter((r: Loose) => r.record_date !== '2026-10-15');
    const r = await go(root, FIRST, data(effr0, gap));
    expect(manifest(root).series['debt-total'].status).toBe('not-yet-published');
    expect(kinds(r, 'debt-total')).toEqual([['2026-10-15', 'undocumented-gap', 'inside-history']]);
    expect(r.record.alerts).toEqual(expect.arrayContaining(['source-gap:debt-total', 'source-gap:debt-held-public', 'source-gap:debt-intragov']));
    expect(r.record.alerts).not.toContain('invalid-series:debt-total');
    // Documented in the registry: the same data publishes and the deadline skips the gap.
    const documented = JSON.parse(JSON.stringify(registry));
    for (const s of documented.series) if (s.source === 'fiscaldata') s.known_gaps = [...(s.known_gaps ?? []), { period: '2026-10-15', text: 'test gap' }];
    const ok = await go(root, '2026-11-13T22:17:00Z', data(effr0, gap), {}, documented);
    expect(manifest(root).series['debt-total'].status).not.toBe('not-yet-published');
    expect(ok.record.alerts).not.toContain('source-gap:debt-total');
  });

  it('skips a documented gap when computing the next deadline', () => {
    const s = registry.series.find((x: Loose) => x.id === 'debt-total');
    const plain = deadlines(s, { last_period: '2026-11-12' }, registry, calendar);
    const gapped = deadlines({ ...s, known_gaps: [{ period: '2026-11-13', text: 'test gap' }] }, { last_period: '2026-11-12' }, registry, calendar);
    expect(plain.deadline).toBe('2026-11-17T08:15:00Z');
    expect(gapped.deadline).toBe('2026-11-18T08:15:00Z');
  });
});

describe('unknown publication zones', () => {
  it('looks for Fiscal Data data at the earliest reading and calls it late only after the latest', () => {
    const s = registry.series.find((x: Loose) => x.id === 'debt-total');
    const d = deadlines(s, { last_period: '2026-11-12' }, registry, calendar);
    // 21:15 on 2026-11-16: UTC reading 21:15Z, ET reading 02:15Z the next day, plus 6 hours.
    expect(d.expected).toBe('2026-11-16T21:15:00Z');
    expect(d.deadline).toBe('2026-11-17T08:15:00Z');
    const h = registry.series.find((x: Loose) => x.id === 'm1-sa');
    const dh = deadlines(h, { last_period: '2026-09', source_marker: { data_release_date: '2026-10-27' } }, registry, calendar);
    expect(dh.expected).toBe('2026-11-24T18:00:00Z');
    expect(dh.deadline).toBe('2026-11-25T00:00:00Z');
  });
});

describe('route notices', () => {
  const keys = (now: string) => routeNoticeAlerts(full.registry, now).map((a: Loose) => `${a.key} ${a.severity}`);
  it('raises the route check only in its window and never as a retirement for the Board', () => {
    expect(keys('2026-11-18T12:00:00Z')).toEqual([]);
    expect(keys('2027-03-23T12:00:00Z')).toEqual([]);
    expect(keys('2027-03-24T12:00:00Z')).toEqual(['source-route-check:frb-releases warning']);
    expect(keys('2027-04-30T12:00:00Z')).toEqual(['source-route-check:frb-releases warning']);
    expect(keys('2027-05-01T12:00:00Z')).toEqual([]);
    expect(keys('2027-06-24T12:00:00Z')).toEqual(['source-route-check:frb-releases warning']);
  });
  it('tracks a retirement that affects the registered route: warning at 180 days, critical at 60', () => {
    const r = JSON.parse(JSON.stringify(full.registry));
    r.sources['frb-releases'].route_notices = [{ ...r.sources['frb-releases'].route_notices[0], affects_registered_route: true }];
    const at = (now: string) => routeNoticeAlerts(r, now).map((a: Loose) => `${a.key} ${a.severity}`);
    expect(at('2026-10-01T12:00:00Z')).toEqual([]);
    expect(at('2026-10-02T12:00:00Z')).toEqual(['source-retirement:frb-releases warning']);
    expect(at('2027-01-30T12:00:00Z')).toEqual(['source-retirement:frb-releases critical']);
    expect(at('2027-06-01T12:00:00Z')).toEqual(['source-retirement:frb-releases critical']);
  });
});

describe('run records', () => {
  it('validate against runs/2 with absences', async () => {
    const root = newRoot();
    await go(root, FIRST);
    expect(validate(full.schemas.runs, json(root, 'live/status/runs.json'))).toEqual([]);
    for (const f of readdirSync(join(root, 'archive/state/run-records'))) expect(Array.isArray(json(root, `archive/state/run-records/${f}`).absences)).toBe(true);
  });
});
