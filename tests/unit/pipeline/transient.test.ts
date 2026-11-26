// Transient network failures (DATA_CONVENTIONS v0.8 amendment 2): the live transport numbers every
// request sent, answered or not, so a timeout leaves a gap in the record numbers (20.2); a Stage C
// collection whose request times out and whose retry is answered writes the store through the real
// independent state checker; and V3 retries a transient file fetch failure a bounded number of
// times, never a SHA-256 mismatch (22.5). No test opens a network connection.
import { createHash } from 'node:crypto';
import { EventEmitter } from 'node:events';
import { cpSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/collectors/live-transport.mjs';
const { makeLiveTransport } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/bin/collect.mjs';
const { collect, collectStageC, runChecker } = m2 as unknown as Loose;
import * as m3 from '../../../pipeline/bin/state-op.mjs';
const { operate } = m3 as unknown as Loose;
import * as m4 from '../../../pipeline/lib/fixture-transport.mjs';
const { effrRawRecord, fixtureRequest, loadRawFixtures, makeFixtureTransport } = m4 as unknown as Loose;
import * as m5 from '../../../pipeline/bin/fixture-scenario.mjs';
const { effrDay, loadInputs } = m5 as unknown as Loose;
import * as m6 from '../../../pipeline/bin/publish.mjs';
const { V3_RETRY_WAITS, v3At, v3Get, v3Transient } = m6 as unknown as Loose;

const sha = (b: Buffer) => createHash('sha256').update(b).digest('hex');
const dirs: string[] = [];
const newDir = () => {
  const d = mkdtempSync(join(tmpdir(), 'rmf-transient-'));
  dirs.push(d);
  return d;
};
afterAll(() => {
  for (const d of dirs) rmSync(d, { recursive: true, force: true });
});

/** A request that is sent and never answered (the live transport's timeout ends it). */
const hanging = () => {
  const req = new EventEmitter() as Loose;
  req.destroyed = false;
  req.destroy = () => {
    req.destroyed = true;
  };
  req.end = () => {};
  return req;
};

/** A fake https.request that plays one plan per call: 'ok', 'hang', 'error' or 'late' (answers after the timeout, ignoring destroy). */
function sequence(plans: string[]) {
  let i = 0;
  return (_url: URL, _opts: Loose, cb: (res: Loose) => void) => {
    const plan = plans[Math.min(i, plans.length - 1)];
    i += 1;
    if (plan === 'hang') return hanging();
    const req = new EventEmitter() as Loose;
    req.destroyed = false;
    req.destroy = () => {
      req.destroyed = true;
    };
    req.end = () => {
      setTimeout(() => {
        if (plan === 'error') {
          req.emit('error', new Error('connection reset'));
          return;
        }
        const res = new EventEmitter() as Loose;
        res.statusCode = 200;
        res.headers = { 'content-type': 'application/json' };
        cb(res);
        res.emit('data', Buffer.from(`{"call":${i}}`));
        res.emit('end');
      }, plan === 'late' ? 80 : 1);
    };
    return req;
  };
}

const inputs = loadInputs();
const NYF = 'https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2026-11-01&endDate=2026-11-12';
const LIMITS = { timeoutMs: 30, maxBytes: 1000 };

describe('the live transport numbers every request sent (20.2, amendment 2)', () => {
  it('leaves the number of a timed-out request without a record, and gives its retry the next number', async () => {
    const recorded: Loose[] = [];
    const t = makeLiveTransport({ registry: inputs.registry, request: sequence(['ok', 'hang', 'ok']), limits: LIMITS, record: (e: Loose) => recorded.push(e) });
    expect((await t({ url: NYF, headers: {} })).status).toBe(200);
    expect(await t({ url: NYF, headers: {} })).toEqual({ timeout: true });
    expect((await t({ url: NYF, headers: {} })).status).toBe(200);
    expect(recorded.map((r) => r.n)).toEqual([1, 3]);
  });

  it('does the same for a connection failure', async () => {
    const recorded: Loose[] = [];
    const t = makeLiveTransport({ registry: inputs.registry, request: sequence(['error', 'ok']), limits: LIMITS, record: (e: Loose) => recorded.push(e) });
    expect(await t({ url: NYF, headers: {} })).toEqual({ timeout: true });
    expect((await t({ url: NYF, headers: {} })).status).toBe(200);
    expect(recorded.map((r) => r.n)).toEqual([2]);
  });

  it('never records an answer that arrives after the transport gave the request up', async () => {
    const recorded: Loose[] = [];
    const t = makeLiveTransport({ registry: inputs.registry, request: sequence(['late', 'ok']), limits: LIMITS, record: (e: Loose) => recorded.push(e) });
    expect(await t({ url: NYF, headers: {} })).toEqual({ timeout: true });
    await new Promise((r) => setTimeout(r, 120));
    expect(recorded).toEqual([]);
    expect((await t({ url: NYF, headers: {} })).status).toBe(200);
    expect(recorded.map((r) => r.n)).toEqual([2]);
  });

  it('gives no number to a request refused before it is sent', async () => {
    const recorded: Loose[] = [];
    const t = makeLiveTransport({ registry: inputs.registry, request: sequence(['ok']), limits: LIMITS, record: (e: Loose) => recorded.push(e) });
    await t({ url: NYF, headers: {} });
    expect((await t({ url: 'https://example.org/x', headers: {} })).refused).toBeTruthy();
    expect((await t({ url: NYF.replace('https', 'http'), headers: {} })).refused).toBeTruthy();
    await t({ url: NYF, headers: {} });
    expect(recorded.map((r) => r.n)).toEqual([1, 2]);
  });
});

describe('a Stage C collection whose request times out once (the 2026-11-26 00:17Z case)', () => {
  // The full inputs: the sliced registry of stagec.test.ts cuts every history short, which the
  // real checker rightly refuses (11.4), so this test pays for the whole fixture history.
  const full = inputs;
  const AUTH = { LIVE_COLLECTION_AUTHORIZED: 'true' };
  const T1 = '2026-11-16T16:17:00Z';
  const passing = () => ({ pass: 1, fail: 0, skip: 0 });
  let base = '';
  const fixtures = (d: Loose) => fixtureRequest(makeFixtureTransport(d));

  beforeAll(async () => {
    base = newDir();
    await collect({ mode: 'live', root: newDir(), responses: newDir(), state: base, run: 'b1', env: AUTH, transportRequest: fixtures(loadRawFixtures()), clock: () => T1, transportClock: () => new Date(T1), wait: async () => {}, inputs: full });
    const manifestSha256 = sha(readFileSync(join(base, 'unpublished', 'b1', 'live', 'manifest.json')));
    await operate({ op: 'promote', state: base, root: newDir(), run: 'p1', actor: 'example-maintainer', permission: 'maintain', checkedAt: '2026-11-16T16:30:00Z', now: '2026-11-16T16:30:00Z', clock: () => '2026-11-16T16:30:00Z', validate: passing, inputs: full, manifestSha256, decision: { brief: 'docs/P26_STAGE_B_ACCEPTANCE_STAGE_C.md', decided_on: '2026-11-16' } });
  }, 300_000);

  it('records the requests 1 and 3, retries the timed-out source, and the independent state checker accepts the written store', async () => {
    const state = newDir();
    cpSync(base, state, { recursive: true });
    const d = loadRawFixtures();
    d.effr.push(effrRawRecord(effrDay('2026-11-13')));
    // The second request sent hangs past the transport's timeout; every other is answered.
    const answer = fixtures(d);
    let calls = 0;
    let hungHost = '';
    const request = (url: URL, opts: Loose, cb: (res: Loose) => void) => {
      calls += 1;
      if (calls !== 2) return answer(url, opts, cb);
      hungHost = url.host;
      return hanging();
    };
    const at = '2026-11-17T14:17:00Z';
    const waits: number[] = [];
    const checked: Loose[] = [];
    const r = await collectStageC({
      root: newDir(), state, run: 's-timeout-1', trigger: 'schedule', env: AUTH, transportRequest: request, transportLimits: { timeoutMs: 50, maxBytes: 64_000_000 },
      clock: () => at, transportClock: () => new Date(at), wait: async (ms: number) => void waits.push(ms), validate: passing, inputs: full,
      // The production command line's store check: the independent checker's state mode.
      validateStore: (s: string) => {
        const c = runChecker(['--state', s]);
        checked.push(c);
        return c;
      },
    });
    expect(checked).toHaveLength(1);
    expect(checked[0]).toMatchObject({ fail: 0 });
    expect(checked[0]?.pass).toBeGreaterThan(0);
    const record = JSON.parse(readFileSync(join(state, 'runs', 's-timeout-1.json'), 'utf8'));
    const ns = record.requests.map((x: Loose) => x.n);
    expect(ns.slice(0, 2)).toEqual([1, 3]);
    expect(ns).toEqual([...ns].sort((a: number, b: number) => a - b));
    expect(new Set(ns).size).toBe(ns.length);
    // The retry went to the host of the request that timed out, after the run's backoff.
    expect(hungHost).not.toBe('');
    expect(record.requests[1].host).toBe(hungHost);
    expect(waits.length).toBeGreaterThan(0);
    expect(r.series.effr).toBe('appended');
    expect(JSON.parse(readFileSync(join(state, 'state', 'STATE.json'), 'utf8')).accepted.snapshot).toBe(record.accepted.snapshot);
  }, 300_000);
});

// ---- V3 (22.5, amendment 2) ----

const FILES = new Map<string, Buffer>([
  ['snapshots/s1.json', Buffer.from('{"snapshot":1}')],
  ['objects/a.json', Buffer.from('{"a":1}')],
  ['csv/a.csv', Buffer.from('date,value')],
]);
const ref = (path: string) => ({ path, sha256: sha(FILES.get(path) as Buffer) });
const MANIFEST = Buffer.from(JSON.stringify({ snapshot: ref('snapshots/s1.json'), series: { a: { objects: [ref('objects/a.json')], csvs: [ref('csv/a.csv')], revisions: [] } } }));
const DATASET = { snapshot: 's1', manifest_sha256: sha(MANIFEST) };
const BASE = 'https://example.test/econ/';
const OK = (b: Buffer) => ({ ok: true, status: 200, bytes: b });

/** A V3 `get` that plays a script per path (the last answer repeats), counting the calls. */
function scripted(script: Record<string, Loose[]>) {
  const calls: Record<string, number> = {};
  const get = async (url: string) => {
    const path = url.slice(BASE.length);
    const i = calls[path] ?? 0;
    calls[path] = i + 1;
    if (path === 'manifest.json') return OK(MANIFEST);
    const plan = script[path];
    return plan ? plan[Math.min(i, plan.length - 1)] : OK(FILES.get(path) as Buffer);
  };
  return { get, calls };
}
const v3 = async (script: Record<string, Loose[]>) => {
  const s = scripted(script);
  const waits: number[] = [];
  const out = await v3At({ base: BASE, dataset: DATASET, get: s.get, sleep: async (sec: number) => void waits.push(sec) });
  return { ...out, waits, calls: s.calls };
};

describe('V3 retries a transient failure of a file fetch, never an integrity failure (22.5, amendment 2)', () => {
  it('passes when every file is answered at once, with no wait', async () => {
    expect(await v3({})).toMatchObject({ passed: true, problems: [], waits: [] });
  });

  it('passes after a 503 and a network error, waiting 2 and then 4 seconds', async () => {
    const r = await v3({ 'objects/a.json': [{ ok: false, status: 503 }, { ok: false, network: true }, OK(FILES.get('objects/a.json') as Buffer)] });
    expect(r).toMatchObject({ passed: true, problems: [], waits: [2, 4] });
    expect(r.calls['objects/a.json']).toBe(3);
  });

  it('retries 408, 429 and every status from 500 to 599', async () => {
    for (const status of [408, 429, 500, 502, 504, 599]) {
      const r = await v3({ 'csv/a.csv': [{ ok: false, status }, OK(FILES.get('csv/a.csv') as Buffer)] });
      expect(r, `status ${status}`).toMatchObject({ passed: true, waits: [2] });
    }
  });

  it('fails a transient failure still there after three retries, waiting 2, 4 and 8 seconds', async () => {
    expect(V3_RETRY_WAITS).toEqual([2, 4, 8]);
    const r = await v3({ 'objects/a.json': [{ ok: false, status: 503 }] });
    expect(r).toMatchObject({ passed: false, problems: ['objects/a.json answered status 503 after 3 retries'], waits: [2, 4, 8] });
    expect(r.calls['objects/a.json']).toBe(4);
    const n = await v3({ 'objects/a.json': [{ ok: false, network: true }] });
    expect(n).toMatchObject({ passed: false, problems: ['objects/a.json failed with a network error after 3 retries'], waits: [2, 4, 8] });
  });

  it('never retries a SHA-256 mismatch', async () => {
    const r = await v3({ 'objects/a.json': [OK(Buffer.from('{"a":2}')), OK(FILES.get('objects/a.json') as Buffer)] });
    expect(r).toMatchObject({ passed: false, problems: ['objects/a.json does not match'], waits: [] });
    expect(r.calls['objects/a.json']).toBe(1);
    // A transient failure, then a body that does not match: the mismatch ends the retries.
    const t = await v3({ 'objects/a.json': [{ ok: false, status: 502 }, OK(Buffer.from('{"a":2}')), OK(FILES.get('objects/a.json') as Buffer)] });
    expect(t).toMatchObject({ passed: false, problems: ['objects/a.json does not match after 1 retry'], waits: [2] });
    expect(t.calls['objects/a.json']).toBe(2);
  });

  it('never retries a status that is not transient', async () => {
    for (const status of [400, 403, 404, 410]) {
      const r = await v3({ 'csv/a.csv': [{ ok: false, status }, OK(FILES.get('csv/a.csv') as Buffer)] });
      expect(r, `status ${status}`).toMatchObject({ passed: false, problems: [`csv/a.csv answered status ${status}`], waits: [] });
      expect(r.calls['csv/a.csv']).toBe(1);
    }
    expect(v3Transient({ ok: true, status: 200 })).toBe(false);
    expect(v3Transient({ ok: false })).toBe(false);
  });

  it('keeps the manifest wait as it was: every 30 seconds until the bytes match, then the files', async () => {
    let n = 0;
    const waits: number[] = [];
    const get = async (url: string) => {
      const path = url.slice(BASE.length);
      if (path === 'manifest.json') return (n += 1) < 3 ? { ok: false, status: 503 } : OK(MANIFEST);
      return OK(FILES.get(path) as Buffer);
    };
    expect(await v3At({ base: BASE, dataset: DATASET, get, sleep: async (s: number) => void waits.push(s) })).toEqual({ passed: true, problems: [] });
    expect(waits).toEqual([30, 30]);
  });
});

describe("V3's fetch (22.5, amendment 2)", () => {
  it('answers the bytes of a 2xx, the status of anything else, and a network error for a throw, a failed body or a timeout', async () => {
    const seen: Loose[] = [];
    const ok = v3Get(async (url: string, opts: Loose) => {
      seen.push({ url, opts });
      return new Response('abc', { status: 200 });
    });
    const r = await ok('https://example.test/econ/a');
    expect(r).toMatchObject({ ok: true, status: 200 });
    expect(Buffer.from(r.bytes).toString()).toBe('abc');
    const sent = seen[0]?.opts ?? {};
    expect(sent.cache).toBe('no-store');
    expect(sent.headers['User-Agent']).toBe('RadMage Finance publication');
    expect(sent.signal).toBeInstanceOf(AbortSignal);
    expect(await v3Get(async () => new Response('busy', { status: 503 }))('u')).toEqual({ ok: false, status: 503 });
    expect(await v3Get(async () => new Response(null, { status: 404 }))('u')).toEqual({ ok: false, status: 404 });
    expect(await v3Get(async () => {
      throw new TypeError('fetch failed');
    })('u')).toEqual({ ok: false, network: true });
    const broken = new ReadableStream({
      pull(c) {
        c.error(new Error('connection reset'));
      },
    });
    expect(await v3Get(async () => new Response(broken, { status: 200 }))('u')).toEqual({ ok: false, network: true });
    const slow = v3Get((_url: string, opts: Loose) => new Promise((_res, rej) => opts.signal.addEventListener('abort', () => rej(opts.signal.reason))), 20);
    expect(await slow('u')).toEqual({ ok: false, network: true });
  });
});
