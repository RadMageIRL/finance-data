// Stage B mechanics (DATA_CONVENTIONS v0.6 section 20): the live transport with an injected
// request function (no test opens a network connection), and the durable state store: fresh,
// verified, corrupted, partial and missing state, and a competing writer whose push is refused.
import { createHash } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/collectors/live-transport.mjs';
const { makeLiveTransport } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/lib/state-store.mjs';
const { commitAndPush, exportState, importState, verifyState } = m2 as unknown as Loose;
import * as m3 from '../../../pipeline/bin/fixture-scenario.mjs';
const { loadInputs } = m3 as unknown as Loose;

const inputs = loadInputs();
const roots: string[] = [];
const newDir = () => {
  const d = mkdtempSync(join(tmpdir(), 'rmf-stageb-'));
  roots.push(d);
  return d;
};
afterAll(() => {
  for (const d of roots) rmSync(d, { recursive: true, force: true });
});

/** A fake https.request: answers with `status`, `headers` and `chunks`, or never, or with an error. */
function fakeRequest(plan: Loose) {
  const calls: Loose[] = [];
  const request = (url: URL, opts: Loose, cb: (res: Loose) => void) => {
    calls.push({ url: url.toString(), opts });
    const req = new EventEmitter() as Loose;
    req.destroyed = false;
    req.destroy = () => {
      req.destroyed = true;
    };
    req.end = () => {
      if (plan.never) return;
      setTimeout(() => {
        if (plan.error) {
          req.emit('error', new Error('connection refused'));
          return;
        }
        const res = new EventEmitter() as Loose;
        res.statusCode = plan.status ?? 200;
        res.headers = plan.headers ?? { 'content-type': 'application/json' };
        cb(res);
        for (const c of plan.chunks ?? [Buffer.from('{"ok":true}')]) {
          if (req.destroyed) return;
          res.emit('data', c);
        }
        if (!req.destroyed) res.emit('end');
      }, 1);
    };
    return req;
  };
  return { request, calls };
}

const NYF = 'https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2026-11-01&endDate=2026-11-12';
const UA = 'RadMage Finance (+https://radmagelabs.com/finance/)';

describe('the live transport', () => {
  it('turns away anything but https to a registered host, before any connection', async () => {
    const fake = fakeRequest({});
    const t = makeLiveTransport({ registry: inputs.registry, request: fake.request });
    for (const url of ['http://markets.newyorkfed.org/api/x', 'https://example.com/x', 'https://user:pw@markets.newyorkfed.org/api/x', 'not a url']) {
      const r = await t({ url, headers: { 'User-Agent': UA } });
      expect(r.status).toBe(0);
      expect(r.refused).toBeDefined();
    }
    expect(fake.calls).toEqual([]);
  });

  it('sends only the identity, contact and Accept headers, and records provenance with the hash of the bytes', async () => {
    const body = Buffer.from('{"refRates":[]}');
    const fake = fakeRequest({ chunks: [body], headers: { 'content-type': 'application/json', etag: '"abc"', 'set-cookie': 'x=1' } });
    const recorded: Loose[] = [];
    const t = makeLiveTransport({ registry: inputs.registry, request: fake.request, record: (e: Loose) => recorded.push(e), clock: () => new Date('2026-11-19T12:00:00Z') });
    const r = await t({ url: NYF, headers: { 'User-Agent': UA, Accept: '*/*', Cookie: 'no' } });
    expect(r.status).toBe(200);
    const call = fake.calls[0] as Loose;
    expect(call.opts.headers).toEqual({ 'User-Agent': UA, Accept: '*/*' });
    expect(call.opts.method).toBe('GET');
    expect(r.headers).toEqual({ 'content-type': 'application/json', etag: '"abc"' });
    expect(recorded[0]).toMatchObject({ n: 1, host: 'markets.newyorkfed.org', status: 200, etag: '"abc"', bytes: body.length, requested_at: '2026-11-19T12:00:00Z', sha256: createHash('sha256').update(body).digest('hex') });
  });

  it('never follows a redirect: a 3xx comes back as its status', async () => {
    const fake = fakeRequest({ status: 302, headers: { location: 'https://elsewhere.example/' }, chunks: [] });
    const t = makeLiveTransport({ registry: inputs.registry, request: fake.request });
    expect((await t({ url: NYF, headers: {} })).status).toBe(302);
    expect(fake.calls.length).toBe(1);
  });

  it('stops reading an answer over the size cap and keeps nothing of it', async () => {
    const fake = fakeRequest({ chunks: [Buffer.alloc(60), Buffer.alloc(60)] });
    const recorded: Loose[] = [];
    const t = makeLiveTransport({ registry: inputs.registry, request: fake.request, limits: { timeoutMs: 1000, maxBytes: 100 }, record: (e: Loose) => recorded.push(e) });
    const r = await t({ url: NYF, headers: {} });
    expect(r).toMatchObject({ status: 0, refused: 'answer over the size cap' });
    expect(r.bytes.length).toBe(0);
    expect(recorded).toEqual([]);
  });

  it('answers a timeout for no answer and for a connection error', async () => {
    const t1 = makeLiveTransport({ registry: inputs.registry, request: fakeRequest({ never: true }).request, limits: { timeoutMs: 30, maxBytes: 100 } });
    expect(await t1({ url: NYF, headers: {} })).toEqual({ timeout: true });
    const t2 = makeLiveTransport({ registry: inputs.registry, request: fakeRequest({ error: true }).request });
    expect(await t2({ url: NYF, headers: {} })).toEqual({ timeout: true });
  });
});

/** A run record of the fixture scenario, valid against its schema. */
const RUN_RECORD = '{"absences":[],"alerts":[],"ended_at":"2026-11-13T14:17:00Z","id":"scenario-01","outcome":"published","series":{},"snapshot":"20261113T141700Z","started_at":"2026-11-13T14:17:00Z","trigger":"schedule"}';

describe('the durable state store', () => {
  const root = () => {
    const r = newDir();
    mkdirSync(join(r, 'archive', 'state', 'run-records'), { recursive: true });
    mkdirSync(join(r, 'live'), { recursive: true });
    writeFileSync(join(r, 'archive', 'state', 'review-queue.json'), '{"schema":"rmf.econ.review-queue/4","open":[],"frozen":[],"decisions":[],"refusals":[]}');
    writeFileSync(join(r, 'archive', 'state', 'run-records', 'r1.json'), RUN_RECORD);
    writeFileSync(join(r, 'live', 'manifest.json'), '{"schema":"x"}');
    return r;
  };

  it('treats an empty checkout as a fresh store, and verifies what it wrote', () => {
    const checkout = newDir();
    expect(verifyState(checkout)).toMatchObject({ ok: true, fresh: true });
    const d = exportState(root(), checkout, { run: 'run-1', writtenAt: '2026-11-19T12:00:00Z' });
    expect(d.files.map((f: Loose) => f.path)).toEqual(['state/review-queue.json', 'state/run-records/r1.json']);
    expect(d.root).toBe('unpublished/run-1');
    expect(existsSync(join(checkout, 'unpublished', 'run-1', 'live', 'manifest.json'))).toBe(true);
    expect(verifyState(checkout)).toMatchObject({ ok: true, fresh: false, problems: [] });
    // Restoring into a new root brings back the state and the candidate root.
    const again = newDir();
    importState(checkout, again);
    expect(readFileSync(join(again, 'archive', 'state', 'run-records', 'r1.json'), 'utf8')).toBe(RUN_RECORD);
    expect(existsSync(join(again, 'live', 'manifest.json'))).toBe(true);
  });

  it('fails closed on a changed, missing, extra, unreadable or schema-breaking state file, a missing descriptor, and a changed or lost root manifest', () => {
    const cases: [string, (c: string) => void][] = [
      ['changed', (c) => writeFileSync(join(c, 'state', 'run-records', 'r1.json'), RUN_RECORD.replace('scenario-01', 'scenario-02'))],
      ['missing', (c) => rmSync(join(c, 'state', 'run-records', 'r1.json'))],
      ['extra', (c) => writeFileSync(join(c, 'state', 'stray.json'), '{}')],
      ['descriptor', (c) => writeFileSync(join(c, 'state', 'STATE.json'), 'not json')],
      ['root', (c) => rmSync(join(c, 'unpublished'), { recursive: true, force: true })],
      ['root manifest changed', (c) => writeFileSync(join(c, 'unpublished', 'run-1', 'live', 'manifest.json'), '{"schema":"y"}')],
      ['root manifest missing', (c) => rmSync(join(c, 'unpublished', 'run-1', 'live', 'manifest.json'))],
      ['not its schema', (c) => {
        // A well-formed queue whose STATE.json entry matches, but that breaks the queue schema.
        const bad = '{"schema":"rmf.econ.review-queue/4","open":"none"}';
        writeFileSync(join(c, 'state', 'review-queue.json'), bad);
        const d = JSON.parse(readFileSync(join(c, 'state', 'STATE.json'), 'utf8'));
        const f = d.files.find((x: Loose) => x.path === 'state/review-queue.json');
        f.sha256 = createHash('sha256').update(bad).digest('hex');
        f.bytes = Buffer.byteLength(bad);
        writeFileSync(join(c, 'state', 'STATE.json'), JSON.stringify(d));
      }],
    ];
    for (const [label, damage] of cases) {
      const checkout = newDir();
      exportState(root(), checkout, { run: 'run-1', writtenAt: '2026-11-19T12:00:00Z' });
      damage(checkout);
      const v = verifyState(checkout);
      expect(v.ok, label).toBe(false);
      expect(() => importState(checkout, newDir()), label).toThrow(/state store refused/);
    }
  });

  it('detects an interrupted write: state files replaced but the descriptor not yet written', () => {
    const checkout = newDir();
    exportState(root(), checkout, { run: 'run-1', writtenAt: '2026-11-19T12:00:00Z' });
    const descriptor = readFileSync(join(checkout, 'state', 'STATE.json'));
    writeFileSync(join(checkout, 'state', 'review-queue.json'), '{"schema":"rmf.econ.review-queue/4","open":[1]}');
    writeFileSync(join(checkout, 'state', 'STATE.json'), descriptor);
    expect(verifyState(checkout).ok).toBe(false);
  });

  it('refuses to overwrite a run already in the store', () => {
    const checkout = newDir();
    exportState(root(), checkout, { run: 'run-1', writtenAt: '2026-11-19T12:00:00Z' });
    expect(() => exportState(root(), checkout, { run: 'run-1', writtenAt: '2026-11-19T13:00:00Z' })).toThrow(/exists already/);
  });

  it('refuses a competing writer: the second push is not a fast-forward and the store keeps the first', () => {
    const remote = newDir();
    const git = (cwd: string, ...args: string[]) => spawnSync('git', ['-C', cwd, ...args], { encoding: 'utf8' });
    spawnSync('git', ['init', '-q', '--bare', '-b', 'main', remote]);
    const clone = (name: string) => {
      const d = join(newDir(), name);
      spawnSync('git', ['clone', '-q', remote, d]);
      git(d, 'config', 'user.name', 'test');
      git(d, 'config', 'user.email', 'test@example.invalid');
      return d;
    };
    const seed = clone('seed');
    writeFileSync(join(seed, 'README'), 'state');
    expect(commitAndPush(seed, { message: 'seed' }).ok).toBe(true);
    const a = clone('a');
    const b = clone('b');
    exportState(root(), a, { run: 'run-a', writtenAt: '2026-11-19T12:00:00Z' });
    exportState(root(), b, { run: 'run-b', writtenAt: '2026-11-19T12:00:00Z' });
    const first = commitAndPush(a, { message: 'run a' });
    expect(first.ok).toBe(true);
    const second = commitAndPush(b, { message: 'run b' });
    expect(second).toMatchObject({ ok: false, step: 'push' });
    expect(git(remote, 'rev-parse', 'main').stdout.trim()).toBe(first.commit);
  });
});

import * as m4 from '../../../pipeline/bin/collect.mjs';
const { collect } = m4 as unknown as Loose;
import * as m5 from '../../../pipeline/lib/fixture-transport.mjs';
const { loadRawFixtures, makeFixtureTransport } = m5 as unknown as Loose;
import * as m6 from '../../../pipeline/lib/activation.mjs';
const { activationProblems } = m6 as unknown as Loose;

/** A fake https.request that answers from the saved provider bytes (no network). */
function fromFixtures(scripted: Loose = {}) {
  const ft = makeFixtureTransport(loadRawFixtures(), scripted);
  return (url: URL, opts: Loose, cb: (res: Loose) => void) => {
    const req = new EventEmitter() as Loose;
    req.destroy = () => {};
    req.end = () => {
      ft({ url: url.toString(), headers: opts.headers }).then((r: Loose) => {
        if (r.timeout) {
          req.emit('error', new Error('timeout'));
          return;
        }
        const res = new EventEmitter() as Loose;
        res.statusCode = r.status;
        res.headers = r.headers ?? {};
        cb(res);
        res.emit('data', r.bytes);
        res.emit('end');
      });
    };
    return req;
  };
}

describe('a live-mode collection (fake network, temporary state store)', () => {
  const env = { LIVE_COLLECTION_AUTHORIZED: 'true' };
  const hashTree = (dir: string) => {
    const h = createHash('sha256');
    const walk = (d: string, rel = '') => {
      if (!existsSync(d)) return;
      for (const e of readdirSync(d, { withFileTypes: true }).sort((a, b) => (a.name < b.name ? -1 : 1))) {
        const p = join(d, e.name);
        if (e.isDirectory()) walk(p, `${rel}${e.name}/`);
        else h.update(`${rel}${e.name}\0`).update(readFileSync(p)).update('\0');
      }
    };
    walk(dir);
    return h.digest('hex');
  };

  it('collects into the unpublished tree with saved, hash-checked responses, and publishes nothing', async () => {
    const root = newDir();
    const responses = newDir();
    const state = newDir();
    const r = await collect({ mode: 'live', root, responses, state, run: 'live-test-1', env, transportRequest: fromFixtures(), clock: () => '2026-11-19T15:17:00Z' });
    expect(r.outcome).toBe('published');
    expect(r.requests.map((x: Loose) => [x.status, x.url.split('/')[2]])).toEqual([[200, 'markets.newyorkfed.org'], [200, 'api.fiscaldata.treasury.gov'], [200, 'www.federalreserve.gov'], [200, 'www.federalreserve.gov']]);
    for (const x of r.requests) expect(createHash('sha256').update(readFileSync(join(responses, `${x.base}.bin`))).digest('hex')).toBe(x.sha256);
    expect(verifyState(state)).toMatchObject({ ok: true, fresh: false });
    expect(existsSync(join(state, 'unpublished', 'live-test-1', 'live', 'manifest.json'))).toBe(true);
    expect(existsSync(join(state, 'unpublished', 'live-test-1', 'responses'))).toBe(true);
    expect(JSON.parse(readFileSync(join(state, 'state', 'STATE.json'), 'utf8')).root).toBe('unpublished/live-test-1');
    // Publication stays blocked whatever the collection did.
    expect(activationProblems({ pipelineDir: 'pipeline', liveTransportExists: true, liveCollectionAuthorized: true, stateStoreExists: true }, 'publish').length).toBe(3);
  }, 60_000);

  it('a failed collection leaves the last accepted state as it was', async () => {
    const state = newDir();
    await collect({ mode: 'live', root: newDir(), responses: newDir(), state, run: 'live-test-a', env, transportRequest: fromFixtures(), clock: () => '2026-11-19T15:17:00Z' });
    const before = hashTree(join(state, 'unpublished', 'live-test-a'));
    // Every host times out; the run carries everything forward and adds its own folder only.
    const down = { 'markets.newyorkfed.org': Array(8).fill({ timeout: true }), 'api.fiscaldata.treasury.gov': Array(8).fill({ timeout: true }), 'www.federalreserve.gov': Array(8).fill({ timeout: true }) };
    // The retries are paced by a wait that records the pauses instead of sleeping through them.
    const pauses: number[] = [];
    const r = await collect({ mode: 'live', root: newDir(), responses: newDir(), state, run: 'live-test-b', env, transportRequest: fromFixtures(down), clock: () => '2026-11-20T15:17:00Z', wait: async (ms: number) => void pauses.push(ms) });
    expect(pauses.length).toBeGreaterThan(0);
    expect(['no-change', 'nothing-due']).toContain(r.outcome);
    expect(hashTree(join(state, 'unpublished', 'live-test-a'))).toBe(before);
    expect(readFileSync(join(state, 'unpublished', 'live-test-b', 'live', 'manifest.json'))).toEqual(readFileSync(join(state, 'unpublished', 'live-test-a', 'live', 'manifest.json')));
    // A run refused before it starts changes nothing in the store at all.
    const whole = hashTree(state);
    await expect(collect({ mode: 'live', root: newDir(), state, run: 'live-test-c', env: {}, transportRequest: fromFixtures() })).rejects.toThrow(/not activated/);
    expect(hashTree(state)).toBe(whole);
  }, 60_000);
});
