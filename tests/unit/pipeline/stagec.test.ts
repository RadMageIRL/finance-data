// Stage C mechanics (DATA_CONVENTIONS v0.7 section 21): the promotion, the v0.7 state store and
// its fail-closed reader, scheduled runs (unchanged, new observations, a historical revision on
// the Sunday full fetch, missing data, failed requests), validation before any write, idempotent
// retries, a competing writer, operations, issue reconciliation and cross-platform bytes. No test
// opens a network connection: the live transport is answered by the fixture transport. The small
// sliced registry keeps every run short; the independent checker is replaced by a stand-in here
// (the data check runs the real one on appendix G).
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { cpSync, existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, unlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/bin/collect.mjs';
const { collect, collectStageC, checkerCounts } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/bin/state-op.mjs';
const { operate, actorRefusal } = m2 as unknown as Loose;
import * as m3 from '../../../pipeline/lib/state-store.mjs';
const { GITATTRIBUTES, bodyPath, storeBudgetAlert, storeLayout, verifyStateV2 } = m3 as unknown as Loose;
import * as m4 from '../../../pipeline/lib/fixture-transport.mjs';
const { effrRawRecord, fixtureRequest, loadRawFixtures, makeFixtureTransport } = m4 as unknown as Loose;
import * as m5 from '../../../pipeline/bin/fixture-scenario.mjs';
const { debtDay, effrDay, loadInputs } = m5 as unknown as Loose;
import * as m6 from '../../../pipeline/bin/issues.mjs';
const { issueText, reconcileFailed, reconcileLedger, reconcilePlan } = m6 as unknown as Loose;
import * as m7 from '../../../pipeline/lib/run.mjs';
const { runCollector } = m7 as unknown as Loose;
import * as m8 from '../../../pipeline/lib/freshness.mjs';
const { freshnessAt } = m8 as unknown as Loose;
import * as m9 from '../../../pipeline/lib/calendar.mjs';
const { makeCalendar } = m9 as unknown as Loose;
import * as m10 from '../../../pipeline/lib/canonical.mjs';
const { canonicalJson } = m10 as unknown as Loose;
import * as m11 from '../../../pipeline/lib/json-schema.mjs';
const { validate } = m11 as unknown as Loose;

const inputs = loadInputs({ slice: true });
const AUTH = { LIVE_COLLECTION_AUTHORIZED: 'true' };
const passing = () => ({ pass: 1, fail: 0, skip: 0 });
const T1 = '2026-11-16T16:17:00Z';
const dirs: string[] = [];
const newDir = () => {
  const d = mkdtempSync(join(tmpdir(), 'rmf-stagec-'));
  dirs.push(d);
  return d;
};
afterAll(() => {
  for (const d of dirs) rmSync(d, { recursive: true, force: true });
});
const sha = (b: Buffer) => createHash('sha256').update(b).digest('hex');
const hashTree = (dir: string, skip = ''): string => {
  const h = createHash('sha256');
  const walk = (d: string, rel = '') => {
    if (!existsSync(d)) return;
    for (const e of readdirSync(d, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1))) {
      if (rel === '' && e.name === skip) continue;
      const p = join(d, e.name);
      if (e.isDirectory()) walk(p, `${rel}${e.name}/`);
      else h.update(`${rel}${e.name}\0`).update(readFileSync(p)).update('\0');
    }
  };
  walk(dir);
  return h.digest('hex');
};
const json = (p: string) => JSON.parse(readFileSync(p, 'utf8'));

let base = '';
let manifestSha = '';
const data = () => loadRawFixtures();
const request = (d: Loose, scripted: Loose = {}) => {
  const t = makeFixtureTransport(d, scripted);
  return { request: fixtureRequest(t), calls: t.calls };
};
const scheduled = (state: string, run: string, at: string, d: Loose, more: Loose = {}) => {
  const r = request(d, more.scripted ?? {});
  return collectStageC({ root: newDir(), state, run, trigger: 'schedule', env: AUTH, transportRequest: r.request, clock: () => at, transportClock: () => new Date(at), wait: async () => {}, validate: more.validate ?? passing, inputs, ...(more.facts ? { healthFacts: more.facts } : {}) }).then((x: Loose) => ({ ...x, calls: r.calls }));
};
const op = (state: string, opName: string, run: string, at: string, more: Loose = {}) => operate({ op: opName, state, root: newDir(), run, actor: 'example-maintainer', permission: 'maintain', checkedAt: at, now: at, clock: () => at, validate: passing, inputs, ...more });
const copyOfBase = () => {
  const d = newDir();
  cpSync(base, d, { recursive: true });
  return d;
};

beforeAll(async () => {
  // A Stage B collection into an empty store, then the promotion: the base of every test.
  base = newDir();
  await collect({ mode: 'live', root: newDir(), responses: newDir(), state: base, run: 'b1', env: AUTH, transportRequest: request(data()).request, clock: () => T1, transportClock: () => new Date(T1), wait: async () => {}, inputs });
  manifestSha = sha(readFileSync(join(base, 'unpublished', 'b1', 'live', 'manifest.json')));
  await op(base, 'promote', 'p1', '2026-11-16T16:30:00Z', { manifestSha256: manifestSha, decision: { brief: 'docs/P26_STAGE_B_ACCEPTANCE_STAGE_C.md', decided_on: '2026-11-16' } });
}, 120_000);

describe('the baseline promotion and the v0.7 store', () => {
  it('promotes the reviewed dataset once, as a byte copy, with the Stage B bodies stored by content', async () => {
    expect(storeLayout(base)).toBe('v0.7');
    expect(verifyStateV2(base)).toMatchObject({ ok: true, problems: [] });
    expect(readFileSync(join(base, 'root', 'live', 'manifest.json'))).toEqual(readFileSync(join(base, 'unpublished', 'b1', 'live', 'manifest.json')));
    const accepted = json(join(base, 'state', 'accepted.json'));
    expect(accepted.dataset.manifest_sha256).toBe(manifestSha);
    expect(json(join(base, 'state', 'STATE.json')).accepted).toEqual(accepted.dataset);
    for (const f of readdirSync(join(base, 'unpublished', 'b1', 'responses')).filter((x) => x.endsWith('.json'))) {
      const meta = json(join(base, 'unpublished', 'b1', 'responses', f));
      expect(sha(readFileSync(join(base, bodyPath(meta.sha256))))).toBe(meta.sha256);
    }
    expect(readFileSync(join(base, '.gitattributes'), 'utf8')).toBe('* -text\n');
    // A second promotion is turned away, and so is a promotion of another manifest.
    await expect(op(copyOfBase(), 'promote', 'p2', '2026-11-16T17:00:00Z', { manifestSha256: manifestSha, decision: accepted.decision })).rejects.toThrow(/promotion refused/);
    const stageB = newDir();
    await collect({ mode: 'live', root: newDir(), responses: newDir(), state: stageB, run: 'b2', env: AUTH, transportRequest: request(data()).request, clock: () => T1, transportClock: () => new Date(T1), wait: async () => {}, inputs });
    await expect(op(stageB, 'promote', 'p3', '2026-11-16T16:30:00Z', { manifestSha256: '0'.repeat(64), decision: accepted.decision })).rejects.toThrow(/not the reviewed one/);
    expect(storeLayout(stageB)).toBe('v0.6');
  }, 60_000);

  it('fails closed on a missing, converted, extra or changed file, naming converted line endings', () => {
    const problems = (mutate: (d: string) => void) => {
      const d = copyOfBase();
      mutate(d);
      return verifyStateV2(d).problems.join(' | ');
    };
    expect(problems((d) => unlinkSync(join(d, '.gitattributes')))).toMatch(/\.gitattributes is missing/);
    expect(problems((d) => writeFileSync(join(d, '.gitattributes'), '* -text\r\n'))).toMatch(/line endings converted/);
    // A CSV segment checked out with CRLF line ends: named, refused.
    expect(problems((d) => {
      const m = json(join(d, 'root', 'live', 'manifest.json'));
      const csv = join(d, 'root', 'live', m.series.effr.csvs[0].path);
      writeFileSync(csv, readFileSync(csv, 'latin1').split('\n').join('\r\n'), 'latin1');
    })).toMatch(/series\/effr\/.*line endings converted/);
    expect(problems((d) => writeFileSync(join(d, 'state', 'extra.json'), '{}'))).toMatch(/state\/extra\.json is not listed/);
    expect(problems((d) => writeFileSync(join(d, 'state', 'pins.json'), '{"schema":"rmf.econ.pins/1","pins":[],"unpinned":[]} '))).toMatch(/state\/pins\.json does not match/);
    expect(problems((d) => unlinkSync(join(d, 'state', 'accepted.json')))).toMatch(/accepted\.json/);
    expect(problems((d) => writeFileSync(join(d, 'state', 'STATE.json'), `${readFileSync(join(d, 'state', 'STATE.json'), 'utf8')}\n`))).toMatch(/not canonical/);
    // A store whose descriptor no longer lists accepted.json was not promoted (21.2).
    const rewrite = (d: string, change: (x: Loose) => Loose) => writeFileSync(join(d, 'state', 'STATE.json'), canonicalJson(change(json(join(d, 'state', 'STATE.json')))));
    expect(problems((d) => {
      unlinkSync(join(d, 'state', 'accepted.json'));
      rewrite(d, (x) => ({ ...x, files: x.files.filter((f: Loose) => f.path !== 'state/accepted.json') }));
    })).toBe('state/accepted.json is missing: the store was not promoted (21.2)');
    expect(problems((d) => rewrite(d, (x) => ({ ...x, accepted: { ...x.accepted, snapshot: '20200101T000000Z' } })))).toBe('STATE.json accepted does not name the root manifest and its snapshot');
    // A state file that breaks its schema although STATE.json lists its exact bytes.
    expect(problems((d) => {
      const bad = Buffer.from(canonicalJson({ schema: 'rmf.econ.pins/1', pins: 'none' }));
      writeFileSync(join(d, 'state', 'pins.json'), bad);
      rewrite(d, (x) => ({ ...x, files: x.files.map((f: Loose) => (f.path === 'state/pins.json' ? { ...f, sha256: sha(bad), bytes: bad.length } : f)) }));
    })).toMatch(/^state\/pins\.json does not satisfy its schema/);
  });

  it('has a descriptor schema that turns away a descriptor listing itself', () => {
    const d0 = json(join(base, 'state', 'STATE.json'));
    expect(validate(json('pipeline/schemas/state-v2.schema.json'), d0)).toEqual([]);
    expect(validate(json('pipeline/schemas/state-v2.schema.json'), { ...d0, files: [...d0.files, { path: 'state/STATE.json', sha256: '0'.repeat(64), bytes: 1 }] }).join(' ')).toMatch(/must not match/);
  });

  it('gives each series its freshness at the run time, the FOMC target by the EFFR staleness time', () => {
    const manifest = json(join(base, 'root', 'live', 'manifest.json'));
    const snapshot = json(join(base, 'root', 'live', manifest.snapshot.path));
    const at = (now: string) => freshnessAt({ registry: inputs.registry, calendar: makeCalendar(inputs.holidays), manifest, snapshot, now });
    const status = (now: string) => Object.fromEntries(at(now).freshness.map((f: Loose) => [f.series, f.status]));
    expect(status(T1)).toMatchObject({ effr: 'fresh', 'fomc-target': 'fresh', 'debt-total': 'fresh' });
    expect(status('2026-12-20T12:00:00Z')).toMatchObject({ effr: 'stale', 'fomc-target': 'stale', 'debt-total': 'stale' });
    expect(at(T1).expected_next_update_by).toBe(at(T1).freshness.filter((f: Loose) => f.deadline).map((f: Loose) => f.deadline).sort()[0]);
  });

  it('turns a Stage C run away from an empty, Stage B or refused store and leaves it unchanged', async () => {
    await expect(scheduled(newDir(), 's0', '2026-11-16T20:17:00Z', data())).rejects.toThrow(/found fresh/);
    const broken = copyOfBase();
    unlinkSync(join(broken, '.gitattributes'));
    const before = hashTree(broken);
    await expect(scheduled(broken, 's0', '2026-11-16T20:17:00Z', data())).rejects.toThrow(/state store refused/);
    expect(hashTree(broken)).toBe(before);
  }, 60_000);
});

describe('the order of writes', () => {
  it('writes STATE.json last, not before the end of the record, with a clock that advances', async () => {
    // A clock that moves one second at every reading, as a real run's does.
    let tick = Date.parse('2026-11-19T06:39:35Z');
    const clock = () => `${new Date((tick += 1000)).toISOString().slice(0, 19)}Z`;
    const store = newDir();
    await collect({ mode: 'live', root: newDir(), responses: newDir(), state: store, run: 'b9', env: AUTH, transportRequest: request(data()).request, clock: () => T1, transportClock: () => new Date(T1), wait: async () => {}, inputs });
    const msha = sha(readFileSync(join(store, 'unpublished', 'b9', 'live', 'manifest.json')));
    const now = clock();
    await operate({ op: 'promote', state: store, root: newDir(), run: 'p9', actor: 'example-maintainer', permission: 'maintain', checkedAt: now, now, clock, validate: passing, inputs, manifestSha256: msha, decision: { brief: 'docs/P26_STAGE_B_ACCEPTANCE_STAGE_C.md', decided_on: '2026-11-19' } });
    const promoted = json(join(store, 'runs', 'p9.json'));
    expect(json(join(store, 'state', 'STATE.json')).written_at >= promoted.ended_at).toBe(true);
    expect(promoted.ended_at > promoted.started_at).toBe(true);
    await collectStageC({ root: newDir(), state: store, run: 's9', trigger: 'schedule', env: AUTH, transportRequest: request(data()).request, clock, transportClock: () => new Date(tick), wait: async () => {}, validate: passing, inputs });
    const collected = json(join(store, 'runs', 's9.json'));
    expect(json(join(store, 'state', 'STATE.json')).written_at >= collected.ended_at).toBe(true);
    expect(verifyStateV2(store).ok).toBe(true);
  }, 60_000);
});

describe('scheduled runs', () => {
  it('an unchanged run adds nothing under root/, a retry accepts nothing twice, and a run id is used once', async () => {
    const s = copyOfBase();
    const rootBefore = hashTree(join(s, 'root'));
    const bodiesBefore = new Set(readdirSync(join(s, 'responses'), { recursive: true }).map(String));
    const d = data();
    const a = await scheduled(s, 's1-1', '2026-11-16T20:17:00Z', d);
    expect(a.outcome).toBe('no-change');
    expect(hashTree(join(s, 'root'))).toBe(rootBefore);
    // Only the bodies not stored before are added (here the windowed EFFR answer; the H.6 files,
    // due on every run under this test registry, are the ones the promotion stored).
    const added = readdirSync(join(s, 'responses'), { recursive: true }).map(String).filter((f) => f.endsWith('.bin') && !bodiesBefore.has(f));
    expect(a.requests.length).toBe(3);
    expect(json(join(s, 'runs', 's1-1.json')).added.files).toBe(added.length);
    expect(added.length).toBe(1);
    // The retry of the same run (a new attempt) finds the same accepted state: nothing accepted.
    const b = await scheduled(s, 's1-2', '2026-11-16T20:18:00Z', d);
    expect(b.outcome).toBe('no-change');
    expect(b.accepted).toEqual(a.accepted);
    expect(json(join(s, 'runs', 's1-2.json')).added).toEqual({ files: 0, bytes: 0 });
    await expect(scheduled(s, 's1-1', '2026-11-16T20:19:00Z', d)).rejects.toThrow(/exists already/);
  }, 60_000);

  it('continues without the self-check facts when they cannot be read, and says so', async () => {
    const s = copyOfBase();
    const d = data();
    const c = await collectStageC({ root: newDir(), state: s, run: 's1-3', trigger: 'schedule', env: AUTH, transportRequest: request(d).request, clock: () => '2026-11-16T20:20:00Z', transportClock: () => new Date('2026-11-16T20:20:00Z'), wait: async () => {}, validate: passing, inputs, factsUnavailable: true });
    expect(c.ledger.find((x: Loose) => x.key === 'self-check-unavailable')).toMatchObject({ severity: 'warning' });
  }, 60_000);

  it('accepts new observations only after validation, and a failed validation writes nothing', async () => {
    const s = copyOfBase();
    const d = data();
    d.effr.push(effrRawRecord(effrDay('2026-11-13')));
    d.debt.push(debtDay(d.debt[d.debt.length - 1], '2026-11-13', 1_000_000_000));
    const before = hashTree(s);
    await expect(scheduled(s, 's2-1', '2026-11-17T00:17:00Z', d, { validate: () => ({ pass: 1, fail: 1, skip: 0, failures: ['FAIL T1'] }) })).rejects.toThrow(/validation failed/);
    expect(hashTree(s)).toBe(before);
    const r = await scheduled(s, 's2-2', '2026-11-17T00:17:00Z', d);
    expect(r.outcome).toBe('published');
    expect(r.accepted.snapshot).toBe('20261117T001700Z');
    expect(json(join(s, 'state', 'STATE.json')).accepted).toEqual(r.accepted);
    expect(json(join(s, 'root', 'live', 'manifest.json')).series.effr.last_period).toBe('2026-11-13');
    expect(verifyStateV2(s).ok).toBe(true);
  }, 60_000);

  it('fetches every group in full once on a Sunday, holds a historical revision, and windows the later Sunday runs', async () => {
    const s = copyOfBase();
    const d = data();
    d.debt = d.debt.map((x: Loose) => (x.record_date === '2026-09-15' ? { ...x, tot_pub_debt_out_amt: `${BigInt(x.tot_pub_debt_out_amt.split('.')[0]) + 1n}.${x.tot_pub_debt_out_amt.split('.')[1]}` } : x));
    const first = await scheduled(s, 's3-1', '2026-11-22T16:17:00Z', d);
    const hosts = first.calls.map((c: Loose) => new URL(c.url).host);
    expect(hosts).toEqual(['markets.newyorkfed.org', 'api.fiscaldata.treasury.gov', 'www.federalreserve.gov', 'www.federalreserve.gov']);
    expect(new URL(first.calls[0].url).searchParams.get('startDate')).toBe('2026-09-01');
    expect(first.ledger.map((a: Loose) => a.key)).toContain('hold:debt-total');
    // H.6 is invalid under this test registry (its saved zip begins before the slice), so its full
    // fetch is not recorded as successful (17.3); the two other groups are.
    expect(first.series['m1-sa']).toBe('invalid');
    expect(json(join(s, 'state', 'collector.json')).full_fetches).toEqual({ 'debt-total': '2026-11-22T16:17:00Z', effr: '2026-11-22T16:17:00Z' });
    const later = await scheduled(s, 's3-2', '2026-11-22T20:17:00Z', d);
    expect(new URL(later.calls[0].url).searchParams.get('startDate')).toBe('2026-09-24');
    expect(later.calls.some((c: Loose) => new URL(c.url).host === 'api.fiscaldata.treasury.gov' && /gte:2026-09-24/.test(decodeURIComponent(c.url)))).toBe(true);
    expect(later.outcome).toBe('no-change');
  }, 60_000);

  it('repeats a weekly full fetch whose response was invalid', async () => {
    const s = copyOfBase();
    const bad = { status: 200, headers: {}, bytes: Buffer.from('{"refRates": "not a list"}') };
    await scheduled(s, 's4-1', '2026-11-22T16:17:00Z', data(), { scripted: { 'markets.newyorkfed.org': [bad] } });
    // The Sunday fetch was invalid: the last successful full fetch is still the Stage B one.
    expect(json(join(s, 'state', 'collector.json')).full_fetches.effr).toBe('2026-11-16T16:17:00Z');
    const again = await scheduled(s, 's4-2', '2026-11-22T20:17:00Z', data());
    expect(new URL(again.calls[0].url).searchParams.get('startDate')).toBe('2026-09-01');
  }, 60_000);

  it('carries a failed source forward after a request and three retries, records missing data, and still writes the store', async () => {
    const s = copyOfBase();
    const d = data();
    d.effr.push(effrRawRecord(effrDay('2026-11-13')));
    const failing = { status: 500, headers: {}, bytes: Buffer.from('Internal Server Error') };
    // After the debt deadline for 2026-11-13 (08:15 UTC on 2026-11-17), so the failed request leaves
    // a collection failure, not a period that is not yet due.
    const r = await scheduled(s, 's5-1', '2026-11-17T14:17:00Z', d, { scripted: { 'api.fiscaldata.treasury.gov': [failing, failing, failing, failing] } });
    expect(r.requests.filter((x: Loose) => x.host === 'api.fiscaldata.treasury.gov').map((x: Loose) => x.status)).toEqual([500, 500, 500, 500]);
    // The four identical error bodies are stored once.
    expect(existsSync(join(s, bodyPath(sha(Buffer.from('Internal Server Error')))))).toBe(true);
    const rec = json(join(s, 'runs', 's5-1.json'));
    expect(r.series['debt-total']).toBe('failed');
    expect(r.series.effr).toBe('appended');
    expect(json(join(s, 'state', 'collector.json')).sources.fiscaldata.consecutive_failures).toBe(1);
    // Missing data: the run record lists the debt period it could not collect (11.6), and the
    // freshness record keeps the series' deadline.
    const runRecord = json(join(s, 'state', 'run-records', 's5-1.json'));
    expect(runRecord.absences.filter((x: Loose) => x.series === 'debt-total').map((x: Loose) => x.kind)).toContain('collection-failure');
    const debt = rec.freshness.find((f: Loose) => f.series === 'debt-total');
    expect(debt).toMatchObject({ status: 'fresh', last_period: '2026-11-12' });
    expect(typeof debt.deadline).toBe('string');
    expect(rec.freshness.map((f: Loose) => f.series)).toEqual(inputs.registry.series.map((x: Loose) => x.id));
    expect(rec.freshness.find((f: Loose) => f.series === 'fomc-target').deadline).toBeNull();
  }, 60_000);

  it('turns away a competing writer: the second push is not a fast-forward and the store keeps the first', async () => {
    const env = { ...process.env, GIT_AUTHOR_NAME: 't', GIT_AUTHOR_EMAIL: 't@example.invalid', GIT_COMMITTER_NAME: 't', GIT_COMMITTER_EMAIL: 't@example.invalid' };
    const git = (cwd: string, ...args: string[]) => spawnSync('git', args, { cwd, env, encoding: 'utf8' });
    const bare = newDir();
    git(bare, 'init', '-q', '--bare');
    const seed = copyOfBase();
    git(seed, 'init', '-q', '-b', 'main');
    git(seed, 'add', '-A');
    git(seed, 'commit', '-q', '-m', 'seed');
    git(seed, 'push', '-q', bare, 'HEAD:main');
    const one = newDir();
    const two = newDir();
    git(one, 'clone', '-q', '-b', 'main', '-c', 'core.autocrlf=false', bare, '.');
    git(two, 'clone', '-q', '-b', 'main', '-c', 'core.autocrlf=false', bare, '.');
    const saved = { ...process.env };
    Object.assign(process.env, { GIT_AUTHOR_NAME: 't', GIT_AUTHOR_EMAIL: 't@example.invalid', GIT_COMMITTER_NAME: 't', GIT_COMMITTER_EMAIL: 't@example.invalid' });
    try {
      const d = data();
      const a = await collectStageC({ root: newDir(), state: one, run: 'w1', trigger: 'schedule', env: AUTH, transportRequest: request(d).request, clock: () => '2026-11-16T20:17:00Z', transportClock: () => new Date('2026-11-16T20:17:00Z'), wait: async () => {}, validate: passing, inputs, push: true });
      expect(a.commit).toMatch(/^[0-9a-f]{40}$/);
      await expect(collectStageC({ root: newDir(), state: two, run: 'w2', trigger: 'schedule', env: AUTH, transportRequest: request(d).request, clock: () => '2026-11-16T20:18:00Z', transportClock: () => new Date('2026-11-16T20:18:00Z'), wait: async () => {}, validate: passing, inputs, push: true })).rejects.toThrow(/push refused/);
      expect(git(bare, 'rev-parse', 'main').stdout.trim()).toBe(a.commit);
    } finally {
      for (const k of ['GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL']) if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  }, 60_000);
});

describe('operations on the store', () => {
  it('turns away an automation account, a reader and an old permission reading', () => {
    const at = '2026-11-23T16:30:00Z';
    expect(actorRefusal(inputs.registry, { actor: 'radmage-finance-state-writer[bot]', permission: 'admin', checkedAt: at, now: at })).toMatch(/automation/);
    expect(actorRefusal(inputs.registry, { actor: 'example-reader', permission: 'read', checkedAt: at, now: at })).toMatch(/write access/);
    expect(actorRefusal(inputs.registry, { actor: 'example-maintainer', permission: 'maintain', checkedAt: '2026-11-23T15:00:00Z', now: at })).toMatch(/within the hour/);
    expect(actorRefusal(inputs.registry, { actor: 'example-maintainer', permission: 'maintain', checkedAt: at, now: at })).toBeNull();
  });

  it('rejects a hold, rolls back and restores through the store, each validated and verified', async () => {
    const s = copyOfBase();
    const d = data();
    d.debt = d.debt.map((x: Loose) => (x.record_date === '2026-09-15' ? { ...x, tot_pub_debt_out_amt: `${BigInt(x.tot_pub_debt_out_amt.split('.')[0]) + 1n}.${x.tot_pub_debt_out_amt.split('.')[1]}` } : x));
    await scheduled(s, 'o1', '2026-11-22T16:17:00Z', d);
    const hold = json(join(s, 'state', 'review-queue.json')).open.find((q: Loose) => q.series === 'debt-total');
    const promoted = json(join(s, 'state', 'accepted.json')).dataset.snapshot;
    const rej = await op(s, 'review', 'o2', '2026-11-23T16:30:00Z', { series: 'debt-total', candidate: hold.candidate_sha256, reviewDecision: 'reject', reason: 'Test: not accepted.' });
    expect(rej.outcome).toBe('published');
    expect(json(join(s, 'state', 'review-queue.json')).frozen.map((f: Loose) => [f.series, f.origin])).toEqual([['debt-total', 'rejected']]);
    const back = await op(s, 'rollback', 'o3', '2026-11-23T16:45:00Z', { to: promoted, reason: 'Test: back to the baseline.' });
    expect(back.accepted.snapshot).toBe(promoted);
    const rest = await op(s, 'restore', 'o4', '2026-11-23T17:00:00Z', { reason: 'Test: rebuild live.' });
    expect(rest.outcome).toBe('published');
    expect(rest.accepted).toEqual(back.accepted);
    expect(verifyStateV2(s).ok).toBe(true);
    for (const id of ['o2', 'o3', 'o4']) expect(json(join(s, 'runs', `${id}.json`))).toMatchObject({ trigger: 'operation', requests: [] });
    await expect(op(s, 'review', 'o5', '2026-11-23T17:10:00Z', { actor: 'github-actions', series: 'debt-total', candidate: hold.candidate_sha256, reviewDecision: 'clear', reason: 'x' })).rejects.toThrow(/automation/);
  }, 90_000);

  it('does not run a collection in mode operation', async () => {
    await expect(runCollector({ root: newDir(), mode: 'operation', registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays, now: T1, run: { id: 'x', attempt: 1, trigger: 'schedule', collector_commit: '0'.repeat(40) }, fetch: async () => ({ status: 500 }) })).rejects.toThrow(/mode "fixture" or "live"/);
  });
});

describe('issue delivery by reconciliation', () => {
  const fakeApi = () => {
    let n = 0;
    const issues: Loose[] = [];
    const api = {
      issues,
      listOpen: async () => issues.filter((i) => i.state === 'open').map((i) => ({ ...i })),
      create: async (t: Loose) => void issues.push({ number: ++n, title: t.title, body: t.body, state: 'open', created_at: `2026-11-20T00:00:${String(n).padStart(2, '0')}Z` }),
      edit: async (num: number, t: Loose) => void Object.assign(issues.find((i) => i.number === num) as Loose, { title: t.title, body: t.body }),
      close: async (num: number) => void Object.assign(issues.find((i) => i.number === num) as Loose, { state: 'closed' }),
    };
    return api;
  };
  const hold = { key: 'hold:debt-total', severity: 'critical', title: 'Held for review: debt-total', body: 'Series debt-total is held.' };
  const stale = { key: 'stale:effr', severity: 'warning', title: 'Stale series: effr', body: 'Series effr has no new period.' };

  it('opens one issue per key, edits a change, closes a cleared key, repairs a duplicate, and changes nothing when run again', async () => {
    const api = fakeApi();
    expect(await reconcileLedger(api, [hold, stale])).toEqual(['create hold:debt-total', 'create stale:effr']);
    expect(await reconcileLedger(api, [hold, stale])).toEqual([]);
    expect(await reconcileLedger(api, [hold, { ...stale, body: 'Series effr has no new period since 2026-11-13.' }])).toEqual(['edit stale:effr #2']);
    expect((api.issues[1] as Loose).body).toBe('Series effr has no new period since 2026-11-13.\n\nrmf-alert-key: stale:effr');
    expect(await reconcileLedger(api, [hold])).toEqual(['close stale:effr #2']);
    api.issues.push({ number: 9, ...issueText(hold), state: 'open', created_at: '2026-11-21T00:00:00Z' });
    expect(await reconcileLedger(api, [hold])).toEqual(['close hold:debt-total #9']);
    expect(api.issues.filter((i: Loose) => i.state === 'open').map((i: Loose) => i.number)).toEqual([1]);
    expect(reconcilePlan([], [hold])[0]).toMatchObject({ action: 'create', title: 'Held for review: debt-total [hold:debt-total]' });
  });

  it('keeps one collect-failed issue while runs fail, without touching other keys, and the next written ledger closes it', async () => {
    const api = fakeApi();
    await reconcileLedger(api, [hold]);
    expect(await reconcileFailed(api, { step: 'collection', run: '1-1', at: '2026-11-20T04:17:00Z' })).toEqual(['create collect-failed']);
    expect(await reconcileFailed(api, { step: 'collection', run: '1-1', at: '2026-11-20T04:17:00Z' })).toEqual([]);
    expect(await reconcileFailed(api, { step: 'collection', run: '2-1', at: '2026-11-20T08:17:00Z' })).toEqual(['edit collect-failed #2']);
    expect(await reconcileLedger(api, [hold])).toEqual(['close collect-failed #2']);
    expect(api.issues.filter((i: Loose) => i.state === 'open').map((i: Loose) => i.title)).toEqual(['Held for review: debt-total [hold:debt-total]']);
  });
});

describe('bytes, budgets and the checker summary', () => {
  it('writes LF only and no byte order mark outside the saved response bodies, and .gitattributes exactly', () => {
    expect(GITATTRIBUTES).toBe('* -text\n');
    const bad: string[] = [];
    const walk = (d: string, rel = '') => {
      for (const e of readdirSync(d, { withFileTypes: true })) {
        const r = `${rel}${e.name}`;
        if (r === 'responses' || /^unpublished\/[^/]+\/responses$/.test(r)) continue;
        if (e.isDirectory()) walk(join(d, e.name), `${r}/`);
        else {
          const b = readFileSync(join(d, e.name));
          if (b.includes(13) || (b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf)) bad.push(r);
        }
      }
    };
    walk(base);
    expect(bad).toEqual([]);
  });

  it('raises the storage budget alert from the earlier records of the ET month', () => {
    const s = copyOfBase();
    const rec = (run: string, startedAt: string, bytes: number) => writeFileSync(join(s, 'runs', `${run}.json`), JSON.stringify({ run, started_at: startedAt, added: { files: 1, bytes } }));
    expect(storeBudgetAlert(s, '2026-11-20T12:17:00Z')).toBeNull();
    rec('x1', '2026-11-18T12:17:00Z', 49_000_000);
    rec('x2', '2026-10-31T12:17:00Z', 90_000_000);
    expect(storeBudgetAlert(s, '2026-11-20T12:17:00Z')).toBeNull();
    rec('x3', '2026-11-19T12:17:00Z', 2_000_000);
    expect(storeBudgetAlert(s, '2026-11-20T12:17:00Z')).toMatchObject({ key: 'budget:state-store', severity: 'warning' });
    rec('x4', '2026-11-20T03:00:00Z', 50_000_000);
    expect(storeBudgetAlert(s, '2026-11-20T12:17:00Z')).toMatchObject({ severity: 'critical' });
    // 2026-12-01T03:00Z is still November in New York.
    expect(storeBudgetAlert(s, '2026-12-01T03:00:00Z')).toMatchObject({ severity: 'critical' });
    expect(storeBudgetAlert(s, '2026-12-01T06:00:00Z')).toBeNull();
  });

  it('reads the independent checker summary line and nothing else', () => {
    expect(checkerCounts('PASS C0 x\nSUMMARY 153 PASS, 0 FAIL, 2 SKIP\n')).toEqual({ pass: 153, fail: 0, skip: 2 });
    expect(checkerCounts('PASS C0 x\n')).toBeNull();
  });
});
