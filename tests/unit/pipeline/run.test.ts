// End-to-end fixture runs in temporary pipeline roots (DATA_CONVENTIONS v0.4 section 17): the
// scenario of appendix B, determinism, the publish gate, atomic publication with simulated
// deaths, failure recovery, review, rollback, restore, retention and the activation guard.
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';

// The pipeline modules are plain JavaScript: tests use them through a loose type.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/bin/fixture-scenario.mjs';
const { debtDay, effrDay, loadInputs } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/lib/canonical.mjs';
const { canonicalJson } = m2 as unknown as Loose;
import * as m3 from '../../../pipeline/lib/fixture-fetch.mjs';
const { makeFixtureFetch, makeWait } = m3 as unknown as Loose;
import * as m4 from '../../../pipeline/lib/json-schema.mjs';
const { validate } = m4 as unknown as Loose;
import * as m5 from '../../../pipeline/lib/run.mjs';
const { pinSnapshot, requestGroups, restore, reviewHold, rollback, runCollector } = m5 as unknown as Loose;
import * as m6 from '../../../pipeline/lib/store.mjs';
const { listFiles } = m6 as unknown as Loose;


const inputs = loadInputs({ slice: true });
const a = (root: string) => join(root, 'archive');
const roots: string[] = [];
const newRoot = () => {
  const dir = mkdtempSync(join(tmpdir(), 'rmf-p22-'));
  roots.push(dir);
  return dir;
};
afterAll(() => {
  for (const r of roots) rmSync(r, { recursive: true, force: true });
});

const base = (root: string) => ({ root, mode: 'fixture', registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays });
const data = (effr = inputs.effr, debt = inputs.debt, h6 = inputs.h6): Loose => ({ effr: { records: effr }, debt: { rows: debt }, h6: { body: h6 } });
let counter = 0;
const go = (root: string, now: string, d = data(), scripted = {}, more = {}) => {
  counter += 1;
  const fetch = makeFixtureFetch(d, scripted);
  const wait = makeWait();
  return runCollector({ ...base(root), now, run: { id: `test-${counter}`, attempt: 1, trigger: 'schedule', collector_commit: '0'.repeat(40) }, fetch, wait, ...more }).then((r: Record<string, unknown>) => ({ ...r, fetch, wait }));
};
const json = (root: string, rel: string) => JSON.parse(readFileSync(join(root, rel), 'utf8'));
const treeHash = (root: string) => {
  const h = createHash('sha256');
  for (const f of listFiles(root)) h.update(f).update('\0').update(readFileSync(join(root, f))).update('\0');
  return h.digest('hex');
};
const FIRST = '2026-11-13T14:17:00Z';

describe('state files and the publication record', () => {
  it('keeps every state file in its schema and one active snapshot in the publication record', async () => {
    const root = newRoot();
    await go(root, FIRST);
    await go(root, '2026-11-16T14:17:00Z', data([...inputs.effr, effrDay('2026-11-13')]));
    const schema = (n: string) => JSON.parse(readFileSync(`pipeline/schemas/${n}.schema.json`, 'utf8'));
    expect(validate(schema('review-queue'), json(root, 'archive/state/review-queue.json'))).toEqual([]);
    expect(validate(schema('pins'), json(root, 'archive/state/pins.json'))).toEqual([]);
    expect(validate(schema('alerts'), json(root, 'archive/state/alerts.json'))).toEqual([]);
    expect(validate(schema('runs'), json(root, 'live/status/runs.json'))).toEqual([]);
    expect(validate(schema('holidays'), inputs.holidays)).toEqual([]);
    const record = json(root, 'live/status/publications.json');
    expect(validate(schema('publications'), record)).toEqual([]);
    expect(record.publications.map((e: Loose) => [e.snapshot, e.events.map((x: Loose) => x.status)])).toEqual([['20261113T141700Z', ['active', 'superseded']], ['20261116T141700Z', ['active']]]);
    expect(json(root, 'archive/state/publications.json')).toEqual(record);
    expect(existsSync(join(root, 'staging'))).toBe(false);
    // The same runs in another root write the same bytes.
    const twin = newRoot();
    await go(twin, FIRST);
    await go(twin, '2026-11-16T14:17:00Z', data([...inputs.effr, effrDay('2026-11-13')]));
    const strip = (r: string) => listFiles(r).filter((f: string) => !f.includes('run-records') && !f.endsWith('runs.json') && !f.endsWith('publications.json') && !f.includes('/snapshots/') && !f.endsWith('manifest.json') && !f.includes('/manifests/'));
    expect(strip(a(root))).toEqual(strip(a(twin)));
  });
});

describe('a first publication', () => {
  it('publishes all nine series with one request per group and names only content-addressed files', async () => {
    const root = newRoot();
    const r = await go(root, FIRST);
    expect(r.outcome).toBe('published');
    expect(requestGroups(inputs.registry).map((g: { id: string }) => g.id)).toEqual(['effr', 'debt-total', 'm1-sa']);
    expect(r.fetch.calls.map((c: { group: string; full: boolean }) => [c.group, c.full])).toEqual([['effr', true], ['debt-total', true], ['m1-sa', true]]);
    const m = json(root, 'live/manifest.json');
    expect(Object.keys(m.series).length).toBe(9);
    expect(m.health).toEqual({ schedule: ['17 */4 * * *'], expected_next_update_by: '2026-11-16T20:00:00Z' });
    expect(m.series.effr).toMatchObject({ status: 'fresh', last_period: '2026-11-12', last_value: '3.88', last_released: { date: '2026-11-13', basis: 'rule' } });
    expect(m.series['fomc-target'].last_range).toEqual({ lower: '3.75', upper: '4.00' });
    // The attribution year is the ET year of retrieval (decision P5).
    expect(m.series.effr.attribution).toBe('© 2026 Federal Reserve Bank of New York. Content from the New York Fed subject to the Terms of Use at newyorkfed.org.');
    // Backfill has no release date; H.6 months released since the first monthly release have one.
    expect(m.series['debt-total'].last_released).toEqual({ date: null, basis: 'not-recorded' });
    expect(m.series['m1-sa'].last_released).toEqual({ date: '2026-10-27', basis: 'calendar' });
    const csv = readFileSync(join(root, 'live', m.series['debt-held-public'].csvs[0].path), 'utf8');
    expect(csv.split('\n')[5]).toBe('period,value_usd,missing_code,released,released_basis');
    expect(listFiles(join(root, 'live')).every((f: string) => existsSync(join(root, 'archive/files', f)) || f === 'manifest.json' || f.startsWith('status/'))).toBe(true);
  });

  it('refuses a live run while collection is not activated, before touching the root', async () => {
    const root = newRoot();
    await expect(runCollector({ ...base(root), mode: 'live', now: FIRST, run: { id: 'live-1', attempt: 1, trigger: 'schedule', collector_commit: '0'.repeat(40) }, fetch: makeFixtureFetch(data()) })).rejects.toThrow(/run refused: live collection is not activated/);
    await expect(runCollector({ ...base(root), now: FIRST, run: { id: 'a/b', attempt: 1, trigger: 'schedule', collector_commit: '0'.repeat(40) }, fetch: makeFixtureFetch(data()) })).rejects.toThrow(/run refused: the run id/);
    expect(listFiles(root)).toEqual([]);
  });
});

describe('the publish gate', () => {
  const breakWith = (fn: (staged: Map<string, string>) => void) => ({ faults: { breakStaged: fn } });

  it('publishes nothing when a staged object was altered after it was addressed', async () => {
    const root = newRoot();
    const r = await go(root, FIRST, data(), {}, breakWith((staged) => {
      const path = [...staged.keys()].find((k) => k.startsWith('objects/effr/'))!;
      staged.set(path, staged.get(path)!.replace('"3.88"', '"3.89"'));
    }));
    expect(r.outcome).toBe('gate-failed');
    expect((r.problems as string[]).some((p) => /gate 3: .*does not match its hash/.test(p))).toBe(true);
    expect(existsSync(join(root, 'live'))).toBe(false);
    expect(existsSync(join(root, 'archive/files'))).toBe(false);
    expect(existsSync(join(root, 'staging'))).toBe(false);
    expect(json(root, 'archive/state/alerts.json').open.map((a: { key: string }) => a.key)).toEqual(['gate-failed']);
    // The next good run publishes and the alert closes.
    const next = await go(root, '2026-11-13T15:17:00Z');
    expect(next.outcome).toBe('published');
    expect((next.plan as { action: string; key: string }[]).map((x) => `${x.action} ${x.key}`)).toEqual(['close gate-failed']);
  });

  it('fails the gate for a snapshot that drops a registered series, a non-canonical file and a revision without its record', async () => {
    const dropped = await go(newRoot(), FIRST, data(), {}, breakWith((staged) => {
      const path = [...staged.keys()].find((k) => k.startsWith('snapshots/'))!;
      const snap = JSON.parse(staged.get(path)!);
      delete snap.series['m2-nsa'];
      staged.set(path, JSON.stringify(snap));
    }));
    expect(dropped.outcome).toBe('gate-failed');
    const spaced = await go(newRoot(), FIRST, data(), {}, breakWith((staged) => staged.set('manifest.json', `${staged.get('manifest.json')}\n`)));
    expect((spaced.problems as string[])[0]).toBe('gate 8: manifest.json is not canonical');
    // A same-day revision whose log version is removed from the candidate.
    const root = newRoot();
    await go(root, FIRST);
    const effr = inputs.effr.map((x: { effectiveDate: string }) => (x.effectiveDate === '2026-11-12' ? { ...x, percentRate: 3.87 } : x));
    const r = await go(root, '2026-11-13T16:17:00Z', data(effr), {}, breakWith((staged) => {
      for (const k of [...staged.keys()]) if (k.startsWith('revisions/')) staged.delete(k);
    }));
    expect(r.outcome).toBe('gate-failed');
    expect(json(root, 'live/manifest.json').snapshot.id).toBe('20261113T141700Z');
  });

  it('refuses a consistent candidate whose revision has no record, whose carried data was restamped, or that rewrites an archived file', async () => {
    const sha = (text: string) => createHash('sha256').update(text).digest('hex');
    const root = newRoot();
    await go(root, FIRST);
    const effr = inputs.effr.map((x: { effectiveDate: string }) => (x.effectiveDate === '2026-11-12' ? { ...x, percentRate: 3.87 } : x));
    // Rebuild the snapshot and manifest so every hash still agrees, then let the gate judge.
    const rebuild = (staged: Map<string, string>, edit: (snap: any, manifest: any) => void) => {
      const path = [...staged.keys()].find((k) => k.startsWith('snapshots/'))!;
      const snap = JSON.parse(staged.get(path)!);
      const manifest = JSON.parse(staged.get('manifest.json')!);
      edit(snap, manifest);
      const text = canonicalJson(snap);
      staged.set(path, text);
      manifest.snapshot.sha256 = sha(text);
      staged.set('manifest.json', canonicalJson(manifest));
    };
    const noRecord = await go(root, '2026-11-13T16:17:00Z', data(effr), {}, breakWith((staged) => {
      for (const k of [...staged.keys()]) if (k.startsWith('revisions/')) staged.delete(k);
      rebuild(staged, (snap, manifest) => {
        snap.revisions = [];
        manifest.series.effr.revisions = [];
      });
    }));
    expect(noRecord.problems).toEqual(['gate 6: effr: 1 published change(s) but 0 matching revision record(s)']);
    const restamped = await go(root, '2026-11-13T16:27:00Z', data(effr), {}, breakWith((staged) => rebuild(staged, (snap, manifest) => {
      snap.series['debt-total'].retrieved_at = '2026-11-13T16:27:00Z';
      manifest.series['debt-total'].retrieved_at = '2026-11-13T16:27:00Z';
    })));
    expect(restamped.problems).toEqual(['gate 5: debt-total: carried-forward but its objects or retrieved_at changed']);
    const archived = listFiles(join(root, 'archive/files')).find((f: string) => f.startsWith('series/effr/'))!;
    const rewritten = await go(root, '2026-11-13T16:37:00Z', data(effr), {}, breakWith((staged) => staged.set(archived, 'period,value_percent\n')));
    expect(rewritten.problems).toEqual([`gate 4: ${archived} exists in the archive with different bytes`]);
    expect(json(root, 'live/manifest.json').snapshot.id).toBe('20261113T141700Z');
  });

  it('fails over a hard storage limit and deletes nothing to make room', async () => {
    const root = newRoot();
    await go(root, FIRST);
    const before = listFiles(join(root, 'live'));
    const r = await go(root, '2026-11-16T14:17:00Z', data([...inputs.effr, effrDay('2026-11-13')]), {}, { limits: { published: 50_000 } });
    expect(r.outcome).toBe('gate-failed');
    expect((r.problems as string[])[0]).toMatch(/^gate 7: published storage would be \d+ bytes, over 50000; nothing is dropped to make room: a retention decision is needed$/);
    expect(listFiles(join(root, 'live'))).toEqual(before);
  });
});

describe('atomic publication', () => {
  const more = [...inputs.effr, effrDay('2026-11-13')];

  it('leaves the live manifest on the previous complete snapshot when the process dies after the archive write', async () => {
    const root = newRoot();
    await go(root, FIRST);
    const before = readFileSync(join(root, 'live/manifest.json'), 'utf8');
    await expect(go(root, '2026-11-16T14:17:00Z', data(more), {}, { faults: { die: 'after-archive' } })).rejects.toThrow(/simulated death/);
    expect(readFileSync(join(root, 'live/manifest.json'), 'utf8')).toBe(before);
    expect(existsSync(join(root, 'archive/files/snapshots/20261116T141700Z.json'))).toBe(true);
    expect(existsSync(join(root, 'live/snapshots/20261116T141700Z.json'))).toBe(false);
    expect(existsSync(join(root, 'staging'))).toBe(true);
    // The next run removes the leftover staging folder, says so, and publishes.
    const next = await go(root, '2026-11-16T15:17:00Z', data(more));
    expect(next.outcome).toBe('published');
    expect((next.record as { alerts: string[] }).alerts).toEqual(['recovered-staging']);
    expect(json(root, 'live/manifest.json').series.effr.last_period).toBe('2026-11-13');
  });

  it('never names a missing file: a death just before the manifest leaves the old manifest and all its files', async () => {
    const root = newRoot();
    await go(root, FIRST);
    await expect(go(root, '2026-11-16T14:17:00Z', data(more), {}, { faults: { die: 'before-manifest' } })).rejects.toThrow(/simulated death/);
    const m = json(root, 'live/manifest.json');
    expect(m.snapshot.id).toBe('20261113T141700Z');
    for (const s of Object.values(m.series) as { objects: { path: string }[]; csvs: { path: string }[] }[]) {
      for (const o of s.objects) expect(existsSync(join(root, 'live', o.path))).toBe(true);
      for (const c of s.csvs) expect(existsSync(join(root, 'live', c.path))).toBe(true);
    }
  });

  it('fails a run whose time is not later than the newest snapshot', async () => {
    const root = newRoot();
    await go(root, FIRST);
    const r = await go(root, FIRST, data(more));
    expect(r.outcome).toBe('failed');
    expect(r.error).toBe('run refused: 20261113T141700Z is not later than the newest snapshot 20261113T141700Z');
  });
});

describe('failure recovery', () => {
  it('retries a server error up to 3 times with backoff, honoring a longer Retry-After, then carries forward', async () => {
    const root = newRoot();
    await go(root, FIRST);
    const r = await go(root, '2026-11-13T15:17:00Z', data(), { effr: [{ status: 500 }, { status: 502, retry_after: 30 }, { timeout: true }, { status: 503 }] });
    expect(r.wait.calls).toEqual([2, 30, 8]);
    expect(r.fetch.calls.length).toBe(4);
    expect(r.outcome).toBe('no-change');
    expect((r.record as { series: Record<string, string> }).series.effr).toBe('failed');
    expect(json(root, 'live/manifest.json').snapshot.id).toBe('20261113T141700Z');
  });

  it('opens fetch-failures after 3 consecutive failed runs and closes it on success', async () => {
    const root = newRoot();
    await go(root, FIRST);
    const down = { effr: Array(4).fill({ timeout: true }) };
    const a = await go(root, '2026-11-13T15:17:00Z', data(), down);
    const b = await go(root, '2026-11-13T16:17:00Z', data(), down);
    const c = await go(root, '2026-11-13T17:17:00Z', data(), down);
    expect([a, b, c].map((r) => (r.record as { alerts: string[] }).alerts)).toEqual([[], [], ['fetch-failures:nyfed-markets']]);
    const ok = await go(root, '2026-11-13T18:17:00Z');
    expect((ok.plan as { action: string; key: string }[])).toEqual([{ action: 'close', key: 'fetch-failures:nyfed-markets' }]);
  });

  it('stops requesting a source after 403 or 429 and never retries it', async () => {
    const root = newRoot();
    const r = await go(root, FIRST, data(), { 'debt-total': [{ status: 403 }] });
    expect(r.fetch.calls.filter((c: { group: string }) => c.group === 'debt-total').length).toBe(1);
    expect(r.wait.calls).toEqual([]);
    expect(r.outcome).toBe('published');
    const m = json(root, 'live/manifest.json');
    expect(m.series['debt-total'].status).toBe('not-yet-published');
    expect(m.series.effr.status).toBe('fresh');
    expect((r.record as { alerts: string[] }).alerts).toEqual(['blocked:fiscaldata']);
  });

  it('treats a 404 on a page as a failure, never as no data', async () => {
    const root = newRoot();
    const r = await go(root, FIRST, { ...data(), debt: { rows: inputs.debt, pageSize: 20 } }, { 'debt-total': [{ status: 200, body: { data: inputs.debt.slice(0, 20), meta: { 'total-count': inputs.debt.length } } }, { status: 404 }] });
    expect((r.record as { series: Record<string, string> }).series['debt-total']).toBe('failed');
    expect(json(root, 'live/manifest.json').series['debt-total'].status).toBe('not-yet-published');
  });

  it('reads every page of a paged response', async () => {
    const root = newRoot();
    const r = await go(root, FIRST, { ...data(), debt: { rows: inputs.debt, pageSize: 20 } });
    expect(r.fetch.calls.filter((c: { group: string }) => c.group === 'debt-total').map((c: { page: number }) => c.page)).toEqual([1, 2, 3]);
    expect(json(root, 'live/manifest.json').series['debt-total'].last_period).toBe('2026-11-12');
  });

  it('carries every series of an invalid response forward and alerts until a valid one', async () => {
    const root = newRoot();
    await go(root, FIRST);
    const r = await go(root, '2026-11-13T15:17:00Z', data(), { effr: [{ status: 200, body: { refRates: [{ ...effrDay('2026-11-12'), surprise: 1 }] } }] });
    expect((r.record as { series: Record<string, string> }).series).toMatchObject({ effr: 'invalid', 'fomc-target': 'invalid' });
    expect((r.record as { alerts: string[] }).alerts).toEqual(['invalid:nyfed-markets']);
    // A value outside the range invalidates the series, and the target derived from it.
    const wild = inputs.effr.map((x: { effectiveDate: string }) => (x.effectiveDate === '2026-11-12' ? { ...x, percentRate: 99 } : x));
    const s = await go(root, '2026-11-13T16:17:00Z', data(wild));
    expect((s.record as { alerts: string[] }).alerts).toEqual(['invalid-series:effr', 'invalid-series:fomc-target']);
    expect(json(root, 'live/manifest.json').series.effr.last_value).toBe('3.88');
  });

  it('answers nothing-due without a request when no publication is expected', async () => {
    const root = newRoot();
    await go(root, FIRST);
    // Saturday: no EFFR publication day, the next debt and H.6 times not reached.
    const r = await go(root, '2026-11-14T15:17:00Z');
    expect(r.outcome).toBe('nothing-due');
    expect(r.fetch.calls).toEqual([]);
    // Sunday: the weekly full fetch of every group.
    const sunday = await go(root, '2026-11-15T15:17:00Z');
    expect(sunday.fetch.calls.map((c: { group: string; full: boolean; start: string }) => [c.group, c.full, c.start])).toEqual([['effr', true, '2026-09-01'], ['debt-total', true, '2026-09-01'], ['m1-sa', true, '2024-10']]);
    // A weekday run asks for the last 60 days only.
    const monday = await go(root, '2026-11-16T14:17:00Z');
    expect(monday.fetch.calls.map((c: { group: string; full: boolean; start: string }) => [c.group, c.full, c.start])).toEqual([['effr', false, '2026-09-18']]);
  });
});

describe('review, rollback and restore', () => {
  const heldRoot = async () => {
    const root = newRoot();
    await go(root, FIRST);
    const debt = inputs.debt.map((r: { record_date: string }) => (r.record_date === '2026-11-10' ? { ...r, tot_pub_debt_out_amt: '40584130080272.90' } : r));
    const held = await go(root, '2026-11-16T22:17:00Z', data(inputs.effr, debt));
    return { root, debt, held };
  };
  const review = (root: string, now: string, candidate_sha256: string, decision: string) => reviewHold({ ...base(root), now, run: { id: `review-${now.replace(/[-:]/g, '')}`, attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, series: 'debt-total', candidate_sha256, decision, reviewer: 'example-maintainer', reviewer_permission: 'maintain', permission_checked_at: now, reason: 'test decision' });

  it('holds an unexpected change: the published value stays, the candidate goes to the archive and the queue', async () => {
    const { root, held } = await heldRoot();
    expect(held.outcome).toBe('published');
    const m = json(root, 'live/manifest.json');
    expect(m.series['debt-total']).toMatchObject({ status: 'held', status_reason: 'a published value changed and no revision is expected for this series' });
    expect(m.series['debt-held-public'].status).toBe('fresh');
    const snap = json(root, `live/${m.snapshot.path}`);
    const hold = snap.holds[0];
    expect(hold.candidate.archive_asset).toBe(`archive-2026-11/hold-debt-total-${hold.candidate.sha256.slice(0, 16)}.json`);
    const candidate = readFileSync(join(root, 'archive/holds/debt-total', `${hold.candidate.sha256.slice(0, 16)}.json`), 'utf8');
    expect(createHash('sha256').update(candidate).digest('hex')).toBe(hold.candidate.sha256);
    expect(json(root, 'archive/state/review-queue.json').open[0]).toMatchObject({ series: 'debt-total', changes: { changed: 1, removed: 0, added: 0 } });
    // Expiry of the review is not automatic: the hold is still there on the next run.
    expect(existsSync(join(root, 'live/holds'))).toBe(false);
  });

  it('turns away a stale approval and an approval of a series that is not held, changing nothing but the refusal record', async () => {
    const { root } = await heldRoot();
    const before = treeHash(join(root, 'live'));
    expect(await review(root, '2026-11-17T15:00:00Z', 'f'.repeat(64), 'approve')).toMatchObject({ outcome: 'refused', refused: 'stale-candidate', error: 'the held candidate has changed since; review the current one' });
    const other = await reviewHold({ ...base(root), now: '2026-11-17T15:00:00Z', run: { id: 'r', attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, series: 'effr', candidate_sha256: 'f'.repeat(64), decision: 'approve', reviewer: 'example-maintainer', reviewer_permission: 'maintain', permission_checked_at: '2026-11-17T15:00:00Z', reason: 'test decision' });
    expect(other).toMatchObject({ outcome: 'refused', refused: 'not-held', error: 'series effr is not held' });
    expect(treeHash(join(root, 'live'))).toBe(before);
    const queue = json(root, 'archive/state/review-queue.json');
    expect(queue.refusals.map((x: Loose) => x.refused)).toEqual(['stale-candidate', 'not-held']);
    expect(queue.open.map((x: Loose) => x.series)).toEqual(['debt-total']);
  });

  it('publishes an approved candidate with one approved-hold record and closes the hold', async () => {
    const { root, held } = await heldRoot();
    const hash = (held.snapshot as Loose).holds[0].candidate.sha256;
    const r = await review(root, '2026-11-17T15:00:00Z', hash, 'approve');
    expect(r.outcome).toBe('published');
    const m = json(root, 'live/manifest.json');
    expect(m.series['debt-total'].status).toBe('fresh');
    const log = json(root, `live/${m.series['debt-total'].revisions[0].path}`);
    expect(log.records).toEqual([{ detected_at: '2026-11-17T15:00:00Z', snapshot: '20261117T150000Z', period: '2026-11-10', field: 'value', before: '40584130080272.89', after: '40584130080272.90', kind: 'approved-hold', basis: 'approved in review run review-20261117T150000Z on 2026-11-17', release_date: null }]);
    expect(json(root, 'archive/state/review-queue.json').open).toEqual([]);
  });

  it('locks a series when its candidate is rejected, keeps the others moving, and keeps the lock while the rejected value persists', async () => {
    const { root, held, debt } = await heldRoot();
    const hash = (held.snapshot as Loose).holds[0].candidate.sha256;
    expect((await review(root, '2026-11-17T15:00:00Z', hash, 'reject')).outcome).toBe('published');
    let m = json(root, 'live/manifest.json');
    expect(m.series['debt-total']).toMatchObject({ status: 'frozen', status_reason: 'a proposed revision was rejected on 2026-11-17 and the source still carries it: test decision', last_period: '2026-11-12' });
    expect(m.series['debt-held-public'].status).toBe('fresh');
    // The original value, the proposed value, the reason, the decision and the affected period are kept.
    const queue = json(root, 'archive/state/review-queue.json');
    expect(queue.frozen[0]).toMatchObject({ series: 'debt-total', reviewer: 'example-maintainer', reason: 'test decision', affected_periods: ['2026-11-10'] });
    expect(queue.decisions[0]).toMatchObject({ decision: 'reject', reviewer: 'example-maintainer', reason: 'test decision', affected_periods: ['2026-11-10'], record: `reviews/debt-total/${hash.slice(0, 16)}-reject-20261117T150000Z.json` });
    const record = json(root, `archive/${queue.decisions[0].record}`);
    expect(validate(JSON.parse(readFileSync('pipeline/schemas/review.schema.json', 'utf8')), record)).toEqual([]);
    expect(record.changes).toEqual([{ period: '2026-11-10', field: 'value', before: '40584130080272.89', after: '40584130080272.90' }]);
    expect(record.hold.reason).toBe('a published value changed and no revision is expected for this series');
    // The rejected candidate again: nothing published, the series stays frozen.
    const again = await go(root, '2026-11-17T22:17:00Z', data(inputs.effr, debt));
    expect(again.outcome).toBe('no-change');
    // The test source also lacks its newest days past their deadlines: late at the source (11.6).
    expect((again.record as Loose).alerts.filter((k: string) => !k.startsWith('source-overdue:'))).toEqual(['frozen:debt-total']);
    // The locked series is checked again without a second hold or any new issue action for its alert.
    expect((again.plan as Loose[]).filter((x) => x.key === 'frozen:debt-total')).toEqual([]);
    expect(json(root, 'archive/state/review-queue.json').open).toEqual([]);
    // A new day while the rejected value persists: the other series publish it, and the locked
    // series stays locked, publishing nothing, not even the new day (v0.5, 11.5).
    const next = [...debt, debtDay(debt[debt.length - 1], '2026-11-13', 1000)];
    const r = await go(root, '2026-11-18T22:17:00Z', data(inputs.effr, next));
    m = json(root, 'live/manifest.json');
    expect(m.series['debt-held-public'].last_period).toBe('2026-11-13');
    expect(m.series['debt-total']).toMatchObject({ status: 'frozen', last_period: '2026-11-12', last_value: inputs.debt[inputs.debt.length - 1].tot_pub_debt_out_amt });
    expect((r.record as Loose).alerts.filter((k: string) => !k.startsWith('source-overdue:'))).toEqual(['frozen:debt-total']);
    expect(json(root, 'archive/state/review-queue.json').frozen.map((f: Loose) => [f.series, f.origin])).toEqual([['debt-total', 'rejected']]);
    expect((r.plan as Loose[]).filter((x) => x.key === 'frozen:debt-total')).toEqual([]);
    expect(json(root, 'archive/state/review-queue.json').open).toEqual([]);
  });

  it('thaws a frozen series when the source returns exactly to the published data', async () => {
    const { root, held } = await heldRoot();
    await review(root, '2026-11-17T15:00:00Z', (held.snapshot as Loose).holds[0].candidate.sha256, 'reject');
    const r = await go(root, '2026-11-17T22:17:00Z');
    expect(r.outcome).toBe('published');
    expect(json(root, 'live/manifest.json').series['debt-total'].status).toBe('fresh');
    expect(json(root, 'archive/state/review-queue.json').frozen).toEqual([]);
    // The test source is also late for its newest days (11.6): those alerts open in the same run.
    const plan = (r.plan as Loose[]).map((x) => `${x.action} ${x.key}`);
    expect(plan).toContain('close frozen:debt-total');
    expect(plan.filter((x) => x !== 'close frozen:debt-total').every((x) => x.startsWith('open source-overdue:'))).toBe(true);
  });

  it('turns away a review without a reviewer or a reason', async () => {
    const { root, held } = await heldRoot();
    const args = { ...base(root), now: '2026-11-17T15:00:00Z', run: { id: 'rv', attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, series: 'debt-total', candidate_sha256: (held.snapshot as Loose).holds[0].candidate.sha256, decision: 'approve' };
    expect(await reviewHold({ ...args, reviewer: 'example-maintainer', reason: ' ' })).toMatchObject({ outcome: 'refused', refused: 'missing-text', error: 'a review needs a reviewer and a reason' });
    expect(await reviewHold({ ...args, run: { ...args.run, id: 'rv2' }, reason: 'fine' })).toMatchObject({ outcome: 'refused', refused: 'missing-text', error: 'a review needs a reviewer and a reason' });
  });

  it('closes a hold as withdrawn when the source returns to the published data', async () => {
    const { root } = await heldRoot();
    const r = await go(root, '2026-11-17T14:17:00Z');
    expect(r.outcome).toBe('published');
    expect(json(root, 'live/manifest.json').series['debt-total'].status).toBe('fresh');
    expect(json(root, 'archive/state/review-queue.json').decisions[0]).toMatchObject({ series: 'debt-total', decision: 'withdrawn', reviewer: null, reason: null, affected_periods: ['2026-11-10'] });
  });

  it('keeps a hold open when the new candidate would be allowed alone: only a review or an exact return closes it', async () => {
    const { root } = await heldRoot();
    // The source drops the disputed change but adds a new day: appended alone, yet still held.
    const next = [...inputs.debt, debtDay(inputs.debt[inputs.debt.length - 1], '2026-11-13', 1000)];
    const r = await go(root, '2026-11-17T22:17:00Z', data(inputs.effr, next));
    const m = json(root, 'live/manifest.json');
    expect(m.series['debt-total']).toMatchObject({ status: 'held', last_period: '2026-11-12' });
    expect(m.series['debt-held-public'].last_period).toBe('2026-11-13');
    expect((r.record as Loose).series['debt-total']).toBe('revised-unexpected');
    expect(json(root, 'archive/state/review-queue.json').decisions).toEqual([]);
  });

  it('rolls back with a manifest and rollback records, keeps the publication record, and turns away an unknown target or a missing reason', async () => {
    const root = newRoot();
    await go(root, FIRST);
    const revised = inputs.effr.map((x: Loose) => (x.effectiveDate === '2026-11-12' ? { ...x, percentRate: 3.87 } : x));
    await go(root, '2026-11-13T16:17:00Z', data(revised));
    const args = { ...base(root), now: '2026-11-13T17:00:00Z', run: { id: 'rb', attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) } };
    expect((await rollback({ ...args, to: '20200101T000000Z', reason: 'x' })).outcome).toBe('refused');
    expect((await rollback({ ...args, to: '20261113T141700Z', reason: '' })).error).toBe('a rollback needs a reason');
    const snapshots = listFiles(join(root, 'archive/files/snapshots'));
    const objects = listFiles(join(root, 'archive/files/objects'));
    const r = await rollback({ ...args, to: '20261113T141700Z', reason: 'bad publication' });
    expect(r.outcome).toBe('published');
    // No snapshot or object is written or rewritten; the manifest names the last accepted data.
    expect(listFiles(join(root, 'archive/files/snapshots'))).toEqual(snapshots);
    expect(listFiles(join(root, 'archive/files/objects'))).toEqual(objects);
    const m = json(root, 'live/manifest.json');
    expect(m).toMatchObject({ previous_snapshot: '20261113T161700Z', rollback: { from: '20261113T161700Z', to: '20261113T141700Z', reason: 'bad publication' } });
    expect(m.series.effr.last_value).toBe('3.88');
    // The audit history keeps the revision and shows it being taken back.
    const log = json(root, `live/${m.series.effr.revisions[0].path}`);
    expect(log.records.map((x: Loose) => x.kind)).toEqual(['expected', 'rollback']);
    expect(log.records[1]).toMatchObject({ period: '2026-11-12', field: 'value', before: '3.87', after: '3.88', snapshot: '20261113T141700Z', basis: 'rolled back to snapshot 20261113T141700Z in run rb on 2026-11-13', detected_at: '2026-11-13T17:00:00Z' });
    const status = () => json(root, 'live/status/publications.json').publications.map((e: Loose) => [e.snapshot, e.events.map((x: Loose) => x.status)]);
    expect(status()).toEqual([['20261113T141700Z', ['active', 'superseded', 'active']], ['20261113T161700Z', ['active', 'withdrawn']]]);
    expect(json(root, 'live/status/publications.json').publications[1].events[1].reason).toBe('bad publication');
    // The next publishing run starts from the rolled-back data and extends the same log.
    const next = await go(root, '2026-11-13T18:17:00Z', data(revised));
    expect(next.outcome).toBe('published');
    const after = json(root, 'live/manifest.json');
    expect(after.rollback).toBeNull();
    expect(after.previous_snapshot).toBe('20261113T141700Z');
    expect(json(root, `live/${after.snapshot.path}`).previous).toBe('20261113T161700Z');
    // v0.5: the rollback locked effr, so that run publishes nothing of it while the source still
    // serves the withdrawn value; its snapshot lists the lock.
    expect(json(root, `live/${after.series.effr.revisions[0].path}`).records.map((x: Loose) => x.kind)).toEqual(['expected', 'rollback']);
    expect(after.series.effr).toMatchObject({ status: 'frozen', last_value: '3.88' });
    expect(json(root, `live/${after.snapshot.path}`).frozen).toEqual([expect.objectContaining({ series: 'effr', origin: 'rolled-back' })]);
    // Even when the source returns exactly to the reinstated data, a rolled-back lock stays until
    // a person clears it.
    const back = await go(root, '2026-11-13T18:25:00Z', data());
    expect(back.outcome).toBe('no-change');
    expect(json(root, 'live/manifest.json').series.effr.status).toBe('frozen');
    expect(json(root, 'archive/state/review-queue.json').frozen.map((f: Loose) => [f.series, f.origin])).toEqual([['effr', 'rolled-back']]);
    // After an authorized clear, the next run extends the same log with the revision again.
    const lock = json(root, 'archive/state/review-queue.json').frozen.find((f: Loose) => f.series === 'effr');
    const cleared = await reviewHold({ ...base(root), now: '2026-11-13T18:30:00Z', run: { id: 'clear', attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, series: 'effr', candidate_sha256: lock.candidate_sha256, decision: 'clear', reviewer: 'example-maintainer', reviewer_permission: 'maintain', permission_checked_at: '2026-11-13T18:30:00Z', reason: 'test clear' });
    expect(cleared.outcome).toBe('published');
    await go(root, '2026-11-13T19:17:00Z', data(revised));
    const later = json(root, 'live/manifest.json');
    expect(json(root, `live/${later.series.effr.revisions[0].path}`).records.map((x: Loose) => x.kind)).toEqual(['expected', 'rollback', 'expected']);
    expect(later.series.effr.last_value).toBe('3.87');
    expect(status()).toEqual([['20261113T141700Z', ['active', 'superseded', 'active', 'superseded']], ['20261113T161700Z', ['active', 'withdrawn']], ['20261113T181700Z', ['active', 'superseded']], ['20261113T183000Z', ['active', 'superseded']], ['20261113T191700Z', ['active']]]);
  });

  it('fails the gate for a rollback whose records do not match the difference', async () => {
    const root = newRoot();
    await go(root, FIRST);
    const revised = inputs.effr.map((x: Loose) => (x.effectiveDate === '2026-11-12' ? { ...x, percentRate: 3.87 } : x));
    await go(root, '2026-11-13T16:17:00Z', data(revised));
    const r = await rollback({ ...base(root), now: '2026-11-13T17:00:00Z', run: { id: 'rb', attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, to: '20261113T141700Z', reason: 'bad publication', faults: { breakStaged: (staged: Map<string, string>) => {
      // Drop the new log version and name the earlier one again: the rollback goes unrecorded.
      const manifest = JSON.parse(staged.get('manifest.json')!);
      const path = [...staged.keys()].find((k) => k.startsWith('revisions/'))!;
      staged.delete(path);
      manifest.series.effr.revisions = json(root, 'live/manifest.json').series.effr.revisions;
      staged.set('manifest.json', canonicalJson(manifest));
    } } });
    expect(r.outcome).toBe('gate-failed');
    expect(r.problems).toEqual(['gate 6: effr: the rollback changes 1 member(s) but records 0']);
    expect(json(root, 'live/manifest.json').rollback).toBeNull();
  });

  it('restores the live tree from the archive alone and stops on a file that fails its hash', async () => {
    const root = newRoot();
    await go(root, FIRST);
    const before = listFiles(join(root, 'live')).map((f: string) => [f, f === 'status/runs.json' ? '' : readFileSync(join(root, 'live', f), 'utf8')]);
    rmSync(join(root, 'live'), { recursive: true, force: true });
    const r = restore({ root, now: '2026-11-13T15:00:00Z', run: { id: 'restore-1' } });
    expect(r.outcome).toBe('published');
    expect(listFiles(join(root, 'live')).map((f: string) => [f, f === 'status/runs.json' ? '' : readFileSync(join(root, 'live', f), 'utf8')])).toEqual(before);
    // Damage one archived object: the restore refuses before writing a manifest.
    const object = listFiles(join(root, 'archive/files')).find((f: string) => f.startsWith('objects/effr/'))!;
    writeFileSync(join(root, 'archive/files', object), '{"damaged":true}');
    rmSync(join(root, 'live'), { recursive: true, force: true });
    const bad = restore({ root, now: '2026-11-13T16:00:00Z', run: { id: 'restore-2' } });
    expect(bad).toEqual({ outcome: 'refused', error: `${object} does not match its hash` });
    expect(existsSync(join(root, 'live/manifest.json'))).toBe(false);
  });
});

describe('retention in a run', () => {
  const upTo = (d: string) => inputs.effr.filter((r: { effectiveDate: string }) => r.effectiveDate <= d);
  const debtTo = (d: string) => inputs.debt.filter((r: { record_date: string }) => r.record_date <= d);

  it('prunes from the live tree only snapshots outside the window, lists them, and keeps everything in the archive', async () => {
    const root = newRoot();
    await go(root, '2026-10-06T14:17:00Z', data(upTo('2026-10-05'), debtTo('2026-10-02')));
    await go(root, '2026-10-07T14:17:00Z', data(upTo('2026-10-06'), debtTo('2026-10-02')));
    await go(root, '2026-10-08T14:17:00Z', data(upTo('2026-10-07'), debtTo('2026-10-02')));
    const r = await go(root, '2026-11-13T14:17:00Z', data(upTo('2026-11-12'), debtTo('2026-10-02')));
    expect(r.outcome).toBe('published');
    const pruned = (r.record as { pruned: string[] }).pruned;
    expect(pruned).toContain('snapshots/20261007T141700Z.json');
    expect(pruned).not.toContain('snapshots/20261006T141700Z.json');
    expect(pruned).not.toContain('snapshots/20261008T141700Z.json');
    for (const f of pruned) {
      expect(existsSync(join(root, 'live', f))).toBe(false);
      expect(existsSync(join(root, 'archive/files', f))).toBe(true);
    }
    // Every file the current manifest names is still live.
    const m = json(root, 'live/manifest.json');
    for (const o of m.series.effr.objects) expect(existsSync(join(root, 'live', o.path))).toBe(true);
  });

  it('never prunes a pinned snapshot', async () => {
    const root = newRoot();
    await go(root, '2026-10-06T14:17:00Z', data(upTo('2026-10-05'), debtTo('2026-10-02')));
    await go(root, '2026-10-07T14:17:00Z', data(upTo('2026-10-06'), debtTo('2026-10-02')));
    await go(root, '2026-10-08T14:17:00Z', data(upTo('2026-10-07'), debtTo('2026-10-02')));
    expect(pinSnapshot({ root, snapshot: '20261007T141700Z', site_release: 'v0.2.0', reason: 'site build', now: '2026-10-08T15:00:00Z' }).ok).toBe(true);
    const r = await go(root, '2026-11-13T14:17:00Z', data(upTo('2026-11-12'), debtTo('2026-10-02')));
    expect((r.record as { pruned: string[] }).pruned.filter((f) => f.startsWith('snapshots/'))).toEqual([]);
    expect(existsSync(join(root, 'live/snapshots/20261007T141700Z.json'))).toBe(true);
    expect(json(root, 'live/manifest.json').pages_window.pinned).toEqual(['20261007T141700Z']);
  });

  it('marks a series stale in the manifest once its staleness time has passed', async () => {
    const root = newRoot();
    await go(root, '2026-10-06T14:17:00Z', data(upTo('2026-10-05'), debtTo('2026-10-02')));
    const r = await go(root, '2026-10-20T14:17:00Z', data(upTo('2026-10-19'), debtTo('2026-10-02')));
    const m = json(root, 'live/manifest.json');
    // Fiscal Data's zone is unknown: the deadline uses the ET reading of 21:15 (4.5).
    expect(m.series['debt-total']).toMatchObject({ status: 'stale', status_reason: 'no new period after 2026-10-02; expected by 2026-10-07T07:15:00Z' });
    expect(m.series.effr.status).toBe('fresh');
    // The source answers without the missing days: late at the source (11.6), not a failed collection.
    expect([...(r.record as { alerts: string[] }).alerts].sort()).toEqual(['source-overdue:debt-held-public', 'source-overdue:debt-intragov', 'source-overdue:debt-total', 'stale:debt-held-public', 'stale:debt-intragov', 'stale:debt-total']);
  });
});

describe('the self-check layer', () => {
  it('adds schedule-health findings to the run alerts when the facts are given', async () => {
    const root = newRoot();
    mkdirSync(root, { recursive: true });
    const healthFacts = { workflow: { state: 'active' }, repository: { pushed_at: '2026-09-20T00:00:00Z' }, runs: [{ event: 'schedule', conclusion: 'success', created_at: '2026-11-13T13:17:00Z' }], manifest: { health: { expected_next_update_by: '2026-11-16T20:00:00Z' }, series: {} } };
    const r = await go(root, FIRST, data(), {}, { healthFacts });
    expect((r.record as { alerts: string[] }).alerts).toEqual(['inactivity']);
    expect((r.alerts as { key: string; severity: string; body: string }[])[0]).toMatchObject({ severity: 'warning', body: 'No repository activity for 54 days; GitHub disables scheduled workflows after 60.' });
  });
});
