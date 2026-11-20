// The Stage C timer and the independent run-gap watcher (DATA_CONVENTIONS 21.3 and 21.9,
// amendment 1 to v0.7, decision P43): which collect runs are scheduled runs, the watcher's
// findings, its issue reconcile limited to the run keys, its fail rule, its reads of the GitHub
// API, and the Cloudflare Worker's routing, request and retries. No test opens a network
// connection: every request goes to a fake.
import { afterEach, describe, expect, it, vi } from 'vitest';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/lib/run-facts.mjs';
const { TIMER_TITLE_PREFIX, isScheduledRun, runFacts } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/bin/watch.mjs';
const { FAILING_KEYS, RUN_KEYS, readFacts, watch, watchFails, watchFindings, watchPlan } = m2 as unknown as Loose;
import * as m3 from '../../../pipeline/timer/worker.mjs';
const worker = m3 as unknown as Loose;
const { CRON_LINES, dispatchSlot, retryable, slotOf, targetFor } = worker;
import * as m4 from '../../../pipeline/bin/issues.mjs';
const { issueText } = m4 as unknown as Loose;

const NOW = '2026-11-20T20:00:00Z';
const hoursBefore = (h: number) => new Date(Date.parse(NOW) - h * 3_600_000).toISOString().replace(/\.\d{3}Z$/, 'Z');
const base = (runs: Loose[], over: Loose = {}) => ({ now: NOW, workflow: { state: 'active' }, repository: { pushed_at: hoursBefore(24) }, runs, ...over });
const timerRun = (h: number, conclusion: string | null = 'success') => ({ event: 'schedule', conclusion, created_at: hoursBefore(h) });
const manualRun = (h: number, conclusion = 'success') => ({ event: 'workflow_dispatch', conclusion, created_at: hoursBefore(h) });
const keys = (findings: Loose[]) => findings.map((f) => `${f.severity} ${f.key}`);

describe('scheduled runs of the collect workflow (21.3)', () => {
  it('counts the schedule event and timer dispatches, nothing else', () => {
    expect(TIMER_TITLE_PREFIX).toBe('collect timer ');
    expect(isScheduledRun({ event: 'schedule', display_title: 'collect' })).toBe(true);
    expect(isScheduledRun({ event: 'workflow_dispatch', display_title: 'collect timer 2026-11-20T16:17:00Z' })).toBe(true);
    expect(isScheduledRun({ event: 'workflow_dispatch', display_title: 'collect' })).toBe(false);
    expect(isScheduledRun({ event: 'workflow_dispatch', display_title: 'collect timers' })).toBe(false);
    expect(isScheduledRun({ event: 'workflow_dispatch' })).toBe(false);
    expect(isScheduledRun({ event: 'push', display_title: 'collect timer 2026-11-20T16:17:00Z' })).toBe(false);
  });

  it('turns API runs into the facts of 14.3, newest first, conclusion kept', () => {
    const api = [
      { event: 'workflow_dispatch', display_title: 'collect timer 2026-11-20T16:17:00Z', conclusion: null, created_at: '2026-11-20T16:17:09Z', id: 3 },
      { event: 'workflow_dispatch', display_title: 'collect', conclusion: 'success', created_at: '2026-11-20T13:08:54Z', id: 2 },
      { event: 'schedule', display_title: 'collect', conclusion: 'success', created_at: '2026-11-20T01:47:32Z', id: 1 },
    ];
    expect(runFacts(api)).toEqual([
      { event: 'schedule', conclusion: null, created_at: '2026-11-20T16:17:09Z' },
      { event: 'workflow_dispatch', conclusion: 'success', created_at: '2026-11-20T13:08:54Z' },
      { event: 'schedule', conclusion: 'success', created_at: '2026-11-20T01:47:32Z' },
    ]);
  });
});

describe('the watcher findings (21.9)', () => {
  it('keeps only the four run keys', () => {
    expect([...RUN_KEYS].sort()).toEqual(['consecutive-failures', 'inactivity', 'scheduled-run-gap', 'workflow-disabled']);
    expect([...FAILING_KEYS].sort()).toEqual(['consecutive-failures', 'scheduled-run-gap', 'workflow-disabled']);
  });

  it('has no finding after a recent scheduled success, and never a manifest finding', () => {
    expect(watchFindings(base([timerRun(3)]))).toEqual([]);
  });

  it('raises the gap over 9 hours (warning) and over 26 (critical), counting scheduled runs only', () => {
    expect(keys(watchFindings(base([timerRun(10)])))).toEqual(['warning scheduled-run-gap']);
    expect(keys(watchFindings(base([timerRun(27)])))).toEqual(['critical scheduled-run-gap']);
    // A recent manual success does not hide a gap in the schedule.
    expect(keys(watchFindings(base([manualRun(1), timerRun(12)])))).toEqual(['warning scheduled-run-gap']);
    // A scheduled run still in progress does not count; the last success does.
    expect(keys(watchFindings(base([timerRun(0.1, null), timerRun(10)])))).toEqual(['warning scheduled-run-gap']);
    expect(keys(watchFindings(base([])))).toEqual(['critical scheduled-run-gap']);
  });

  it('raises a disabled workflow, a failure streak and inactivity', () => {
    expect(keys(watchFindings(base([timerRun(1)], { workflow: { state: 'disabled_manually' } })))).toEqual(['critical workflow-disabled']);
    expect(keys(watchFindings(base([timerRun(1, 'failure'), timerRun(5, 'failure'), timerRun(9, 'failure'), timerRun(12)])))).toEqual(['critical consecutive-failures', 'warning scheduled-run-gap']);
    expect(keys(watchFindings(base([timerRun(1)], { repository: { pushed_at: hoursBefore(46 * 24) } })))).toEqual(['warning inactivity']);
  });

  it('fails the job on a gap, a disabled workflow or a failure streak, not on inactivity alone', () => {
    expect(watchFails([])).toBe(false);
    expect(watchFails([{ key: 'inactivity', severity: 'warning', message: 'x' }])).toBe(false);
    for (const key of ['scheduled-run-gap', 'workflow-disabled', 'consecutive-failures']) expect(watchFails([{ key, severity: 'warning', message: 'x' }])).toBe(true);
  });
});

// An open issue as the API lists it; the key is only in its body (21.5).
const issue = (number: number, text: Loose, created_at = `2026-11-1${number}T00:00:00Z`) => ({ number, created_at, ...text });
const alertFor = (findings: Loose[]) => findings.map((f) => issueText({ key: f.key, title: `Schedule health: ${f.key}`, body: f.message }));

describe('the watcher reconcile (21.5 limited to the run keys)', () => {
  const gap = watchFindings(base([timerRun(10)]));

  it('creates the gap issue in the 21.5 form', () => {
    expect(watchPlan([], gap)).toEqual([{ action: 'create', key: 'scheduled-run-gap', ...alertFor(gap)[0] }]);
    expect(alertFor(gap)[0].body.endsWith('\n\nrmf-alert-key: scheduled-run-gap')).toBe(true);
  });

  it('changes nothing when the issue already says the same', () => {
    expect(watchPlan([issue(1, alertFor(gap)[0])], gap)).toEqual([]);
  });

  it('closes a cleared run key and never touches any other key', () => {
    const open = [
      issue(1, alertFor(gap)[0]),
      issue(2, { title: 'Held [series-held:effr]', body: 'held\n\nrmf-alert-key: series-held:effr' }),
      issue(3, { title: 'A collection run failed [collect-failed]', body: 'failed\n\nrmf-alert-key: collect-failed' }),
      issue(4, { title: 'Budget [budget:state-store]', body: 'b\n\nrmf-alert-key: budget:state-store' }),
    ];
    expect(watchPlan(open, [])).toEqual([{ action: 'close', number: 1, key: 'scheduled-run-gap', why: 'cleared' }]);
  });

  it('closes duplicates of a run key but the oldest', () => {
    const t = alertFor(gap)[0];
    expect(watchPlan([issue(5, t, '2026-11-20T02:00:00Z'), issue(6, t, '2026-11-20T01:00:00Z')], gap)).toEqual([{ action: 'close', number: 5, key: 'scheduled-run-gap', why: 'duplicate' }]);
  });

  it('applies the plan through the issue API and reports whether the job fails', async () => {
    const calls: string[] = [];
    const api = { listOpen: async () => [], create: async (t: Loose) => calls.push(`create ${t.title}`), edit: async () => calls.push('edit'), close: async (n: number) => calls.push(`close ${n}`) };
    const r = await watch({ api, facts: base([timerRun(10)]) });
    expect(calls).toEqual(['create Schedule health: scheduled-run-gap [scheduled-run-gap]']);
    expect(r.done).toEqual(['create scheduled-run-gap']);
    expect(r.fail).toBe(true);
    const quiet = await watch({ api: { ...api, listOpen: async () => [] }, facts: base([timerRun(2)]) });
    expect(quiet).toEqual({ findings: [], done: [], fail: false });
  });
});

describe('the watcher reads the GitHub API (21.9)', () => {
  const answers = (over: Loose = {}) => {
    const seen: Loose[] = [];
    const fetchImpl = async (url: string, init: Loose) => {
      seen.push({ url, init });
      const path = url.replace('https://api.github.com/repos/RadMageIRL/finance-data', '');
      const body = over[path] ?? {
        '/actions/workflows/collect.yml': { state: 'active' },
        '/actions/workflows/collect.yml/runs?per_page=30': { workflow_runs: [{ event: 'workflow_dispatch', display_title: 'collect timer 2026-11-20T16:17:00Z', conclusion: 'success', created_at: '2026-11-20T16:17:09Z' }] },
        '': { pushed_at: '2026-11-20T13:00:00Z' },
      }[path];
      if (body === 'refuse') return { ok: false, status: 403, json: async () => ({}) };
      return { ok: true, status: 200, json: async () => body };
    };
    return { seen, fetchImpl };
  };

  it('reads the workflow state, its newest 30 runs and pushed_at, with the job token', async () => {
    const { seen, fetchImpl } = answers();
    const facts = await readFacts({ token: 'tok', repository: 'RadMageIRL/finance-data', now: NOW, fetchImpl });
    expect(seen.map((s) => s.url)).toEqual([
      'https://api.github.com/repos/RadMageIRL/finance-data/actions/workflows/collect.yml',
      'https://api.github.com/repos/RadMageIRL/finance-data/actions/workflows/collect.yml/runs?per_page=30',
      'https://api.github.com/repos/RadMageIRL/finance-data',
    ]);
    expect(seen.every((s) => s.init.headers.Authorization === 'Bearer tok' && !s.init.method)).toBe(true);
    expect(facts).toEqual({ now: NOW, workflow: { state: 'active' }, repository: { pushed_at: '2026-11-20T13:00:00Z' }, runs: [{ event: 'schedule', conclusion: 'success', created_at: '2026-11-20T16:17:09Z' }], manifest: null });
  });

  it('throws on a refused read or a missing field, so no issue is changed', async () => {
    await expect(readFacts({ token: 't', repository: 'RadMageIRL/finance-data', now: NOW, fetchImpl: answers({ '/actions/workflows/collect.yml/runs?per_page=30': 'refuse' }).fetchImpl })).rejects.toThrow(/answered 403/);
    await expect(readFacts({ token: 't', repository: 'RadMageIRL/finance-data', now: NOW, fetchImpl: answers({ '': {} }).fetchImpl })).rejects.toThrow(/expected fields/);
  });
});

describe('the Cloudflare timer (21.3, 21.9)', () => {
  const quiet = { log() {}, error() {} };
  const noWait = async () => {};
  const fake = (statuses: (number | 'throw')[]) => {
    const calls: Loose[] = [];
    const request = async (url: string, init: Loose) => {
      calls.push({ url, init, body: JSON.parse(init.body) });
      const s = statuses.shift();
      if (s === 'throw') throw new Error('network down');
      return { status: s, text: async () => 'answer' };
    };
    return { calls, request };
  };
  afterEach(() => vi.unstubAllGlobals());

  it('has the two cron lines of the conventions', () => {
    expect(CRON_LINES).toEqual(['17 */4 * * *', '47 2-22/4 * * *']);
  });

  it('turns the scheduled time into the slot: its cron minute, seconds and milliseconds dropped', () => {
    expect(slotOf(Date.UTC(2026, 10, 20, 16, 17, 0))).toBe('2026-11-20T16:17:00Z');
    // The test firing of 2026-11-20 gave a scheduledTime 4 seconds into its minute.
    expect(slotOf(Date.UTC(2026, 10, 20, 13, 56, 4))).toBe('2026-11-20T13:56:00Z');
    expect(slotOf(Date.UTC(2026, 10, 20, 16, 17, 59, 999))).toBe('2026-11-20T16:17:00Z');
    expect(slotOf(Date.UTC(2026, 10, 20, 16, 17, 0, 250))).toBe('2026-11-20T16:17:00Z');
  });

  it('routes by the minute: 17 collect in mode timer, 47 watch, anything else refused', () => {
    expect(targetFor('2026-11-20T16:17:00Z')).toEqual({ workflow: 'collect.yml', inputs: { mode: 'timer', slot: '2026-11-20T16:17:00Z' } });
    expect(targetFor('2026-11-20T14:47:00Z')).toEqual({ workflow: 'watch.yml', inputs: { slot: '2026-11-20T14:47:00Z' } });
    expect(() => targetFor('2026-11-20T16:18:00Z')).toThrow(/no workflow/);
  });

  it('dispatches on main with exactly the inputs, the token as a bearer', async () => {
    const { calls, request } = fake([204]);
    const r = await dispatchSlot({ token: 'tok', slot: '2026-11-20T16:17:00Z', request, wait: noWait, log: quiet });
    expect(r).toEqual({ slot: '2026-11-20T16:17:00Z', workflow: 'collect.yml', status: 204, attempt: 1 });
    const [c] = calls as Loose[];
    expect(c?.url).toBe('https://api.github.com/repos/RadMageIRL/finance-data/actions/workflows/collect.yml/dispatches');
    expect(c?.init.method).toBe('POST');
    expect(c?.init.headers.Authorization).toBe('Bearer tok');
    expect(c?.body).toEqual({ ref: 'main', inputs: { mode: 'timer', slot: '2026-11-20T16:17:00Z' } });
    const w = fake([200]);
    await dispatchSlot({ token: 'tok', slot: '2026-11-20T14:47:00Z', request: w.request, wait: noWait, log: quiet });
    const [wc] = w.calls as Loose[];
    expect(wc?.url.endsWith('/actions/workflows/watch.yml/dispatches')).toBe(true);
    expect(wc?.body).toEqual({ ref: 'main', inputs: { slot: '2026-11-20T14:47:00Z' } });
  });

  it('retries a network error, 429 and 5xx twice, never a 4xx', async () => {
    expect([0, 429, 500, 502, 503].every(retryable)).toBe(true);
    expect([400, 401, 403, 404, 422].some(retryable)).toBe(false);
    const ok = fake(['throw', 502, 204]);
    const waits: number[] = [];
    expect((await dispatchSlot({ token: 't', slot: '2026-11-20T16:17:00Z', request: ok.request, wait: async (ms: number) => waits.push(ms), log: quiet })).attempt).toBe(3);
    expect(waits).toEqual([5000, 30000]);
    const denied = fake([401, 204]);
    await expect(dispatchSlot({ token: 't', slot: '2026-11-20T16:17:00Z', request: denied.request, wait: noWait, log: quiet })).rejects.toThrow(/after 1 attempt\(s\), last HTTP 401/);
    expect(denied.calls.length).toBe(1);
    const down = fake([503, 503, 503, 204]);
    await expect(dispatchSlot({ token: 't', slot: '2026-11-20T16:17:00Z', request: down.request, wait: noWait, log: quiet })).rejects.toThrow(/after 3 attempt/);
    expect(down.calls.length).toBe(3);
  });

  it('refuses without the secret before any request', async () => {
    const { calls, request } = fake([204]);
    await expect(dispatchSlot({ token: '', slot: '2026-11-20T16:17:00Z', request, wait: noWait, log: quiet })).rejects.toThrow(/GITHUB_TOKEN is not set/);
    expect(calls.length).toBe(0);
  });

  it('the scheduled handler dispatches the firing slot with the env secret', async () => {
    const seen: Loose[] = [];
    vi.stubGlobal('fetch', async (url: string, init: Loose) => {
      seen.push({ url, body: JSON.parse(init.body), auth: init.headers.Authorization });
      return { status: 204, text: async () => '' };
    });
    const log = vi.spyOn(console, 'log').mockImplementation(() => {});
    // Seconds into the minute, as Cloudflare's scheduledTime can be: still the collect slot.
    await worker.default.scheduled({ scheduledTime: Date.UTC(2026, 10, 20, 20, 17, 4), cron: '17 */4 * * *' }, { GITHUB_TOKEN: 'sec' });
    await worker.default.scheduled({ scheduledTime: Date.UTC(2026, 10, 20, 22, 47, 3), cron: '47 2-22/4 * * *' }, { GITHUB_TOKEN: 'sec' });
    log.mockRestore();
    expect(seen).toEqual([
      { url: 'https://api.github.com/repos/RadMageIRL/finance-data/actions/workflows/collect.yml/dispatches', body: { ref: 'main', inputs: { mode: 'timer', slot: '2026-11-20T20:17:00Z' } }, auth: 'Bearer sec' },
      { url: 'https://api.github.com/repos/RadMageIRL/finance-data/actions/workflows/watch.yml/dispatches', body: { ref: 'main', inputs: { slot: '2026-11-20T22:47:00Z' } }, auth: 'Bearer sec' },
    ]);
  });
});
