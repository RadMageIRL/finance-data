#!/usr/bin/env node
// The collector's entry point for workflows (DATA_CONVENTIONS 17.9, 18 and 20).
//
//   node pipeline/bin/collect.mjs --mode fixture --root <dir>
//   LIVE_COLLECTION_AUTHORIZED=true node pipeline/bin/collect.mjs --mode live --root <dir>
//     --responses <dir> --state <state store checkout> --run <run id> [--push]
//
// Fixture mode runs the deterministic scenario of appendix B into an empty root. Live mode is one
// nonpublishing collection (Stage B): it refuses to start unless the state store verifies, the
// authorization is given and the live transport is present; it saves every response with its
// provenance, re-checks their hashes, writes the root and the state into the state store checkout
// (unpublished/<run>/ and state/), and with --push commits and pushes it without force. Nothing is
// published: no Pages, no release, no Labs route.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadInputs, runScenario } from './fixture-scenario.mjs';
import { runCollector } from '../lib/run.mjs';
import { adapterFetch } from '../collectors/adapters.mjs';
import { makeLiveTransport } from '../collectors/live-transport.mjs';
import { commitAndPush, exportState, exportStateV2, importState, importStateV2, storeBudgetAlert, storeLayout, verifyState, verifyStateV2 } from '../lib/state-store.mjs';
import { canonicalJson } from '../lib/canonical.mjs';
import { freshnessAt } from '../lib/freshness.mjs';
import { makeCalendar } from '../lib/calendar.mjs';

const PIPELINE_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : undefined;
};
const nowIso = () => `${new Date().toISOString().slice(0, 19)}Z`;
const sleep = (seconds) => new Promise((r) => setTimeout(r, seconds * 1000));

export async function collect({ mode, root, responses = null, state = null, run = 'live-attempt', push = false, env = process.env, transportRequest = undefined, clock = nowIso, wait = sleep, transportClock = () => new Date(), inputs = loadInputs(), timer = () => Date.now() }) {
  if (mode === 'fixture') {
    const { log } = await runScenario(root);
    return { outcome: 'fixture-scenario', steps: log.length, outcomes: log.map((l) => l.outcome) };
  }
  // Live, nonpublishing (20). The state store must verify before anything else happens.
  const verified = state ? verifyState(state) : { ok: false, problems: ['no state store checkout given'] };
  if (!verified.ok) throw new Error(`state store refused: ${verified.problems.join('; ')}`);
  const facts = {
    pipelineDir: PIPELINE_DIR,
    liveTransportExists: existsSync(join(PIPELINE_DIR, 'collectors', 'live-transport.mjs')),
    liveCollectionAuthorized: env.LIVE_COLLECTION_AUTHORIZED === 'true',
    stateStoreExists: verified.ok,
  };
  const recorded = [];
  if (responses) mkdirSync(responses, { recursive: true });
  const record = (e) => {
    const { body, ...meta } = e;
    const base = `${String(e.n).padStart(3, '0')}-${e.host}`;
    if (responses) {
      writeFileSync(join(responses, `${base}.bin`), body);
      writeFileSync(join(responses, `${base}.json`), canonicalJson(meta));
    }
    recorded.push({ base, ...meta });
  };
  const transport = makeLiveTransport({ registry: inputs.registry, record, ...(transportRequest ? { request: transportRequest } : {}), clock: transportClock });
  // `wait` paces the retries (sleep in a real run; a test passes one that records instead).
  const fetch = adapterFetch({ registry: inputs.registry, transport, wait });
  // The root continues from the state store's newest unpublished root (an empty root the first time).
  if (!verified.fresh) importState(state, root);
  // The run's duration in the Stage B summary (a scenario passes a fixed timer: the same bytes).
  const started = timer();
  const result = await runCollector({ root, mode: 'live', activationFacts: facts, registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays, now: clock(), run: { id: run, attempt: 1, trigger: 'manual', collector_commit: env.GITHUB_SHA ?? '0'.repeat(40) }, fetch, wait });
  const seconds = Math.round((timer() - started) / 1000);
  // Provenance (20.2): every saved response must still match its recorded hash.
  if (responses) {
    for (const r of recorded) {
      const bytes = readFileSync(join(responses, `${r.base}.bin`));
      if (createHash('sha256').update(bytes).digest('hex') !== r.sha256) throw new Error(`saved response ${r.base} does not match its recorded hash`);
    }
  }
  const summary = { outcome: result.outcome, run, seconds, requests: recorded.map(({ base, url, status, bytes, sha256 }) => ({ base, url, status, bytes, sha256 })), series: result.record?.series ?? {}, error: result.error ?? null };
  if (state) {
    const descriptor = exportState(root, state, { run, writtenAt: clock(), responses });
    writeFileSync(join(state, 'unpublished', run, 'summary.json'), canonicalJson(summary));
    summary.state = { root: descriptor.root, files: descriptor.files.length };
    if (push) {
      const pushed = commitAndPush(state, { message: `Stage B collection ${run}: ${result.outcome} (nonpublishing)` });
      if (!pushed.ok) throw new Error(`state store not written: ${pushed.step} refused (${String(pushed.detail).trim()})`);
      summary.state.commit = pushed.commit;
    }
  }
  // The issue plan and the ledger are returned, not stored in the summary (the Stage B format).
  const alertsFile = join(root, 'archive', 'state', 'alerts.json');
  return { ...summary, plan: result.plan ?? [], ledger: existsSync(alertsFile) ? JSON.parse(readFileSync(alertsFile, 'utf8')).open.map(({ key, severity, title, body }) => ({ key, severity, title, body })) : [] };
}

/** The independent checker's summary line: { pass, fail, skip }, or null when there is none. */
export function checkerCounts(text) {
  const m = /^SUMMARY (\d+) PASS, (\d+) FAIL, (\d+) SKIP$/m.exec(text);
  return m ? { pass: Number(m[1]), fail: Number(m[2]), skip: Number(m[3]) } : null;
}

/**
 * Runs the independent checker (tests/datacheck/check_p22.py, which shares no code with the
 * pipeline) with the given arguments and returns its counts; refuses when it cannot run.
 */
export function runChecker(args) {
  const script = join(PIPELINE_DIR, '..', 'tests', 'datacheck', 'check_p22.py');
  for (const python of ['python3', 'python']) {
    const r = spawnSync(python, ['-I', script, ...args], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
    if (r.error) continue;
    const counts = checkerCounts(r.stdout ?? '');
    if (!counts) throw new Error(`the independent checker gave no summary (exit ${r.status})`);
    return { ...counts, exit: r.status, failures: (r.stdout ?? '').split('\n').filter((l) => l.startsWith('FAIL')).slice(0, 10) };
  }
  throw new Error('the independent checker could not be started (no python)');
}

/** The checker in live mode on a working root (21.3 step 6). */
export const validateRoot = (root) => runChecker(['--root', root, '--live']);

/** The record of 21.4 for a run, without `added` and `month_added_bytes` (the store adds them). */
function collectionRecord({ run, trigger, operation, startedAt, endedAt, outcome, requests, checker, root, inputs, now }) {
  const manifest = JSON.parse(readFileSync(join(root, 'live', 'manifest.json'), 'utf8'));
  const snapshot = JSON.parse(readFileSync(join(root, 'live', manifest.snapshot.path), 'utf8'));
  const manifestSha256 = createHash('sha256').update(readFileSync(join(root, 'live', 'manifest.json'))).digest('hex');
  const f = freshnessAt({ registry: inputs.registry, calendar: makeCalendar(inputs.holidays), manifest, snapshot, now });
  return {
    schema: 'rmf.econ.collection/1',
    run,
    trigger,
    operation,
    started_at: startedAt,
    ended_at: endedAt,
    outcome,
    requests,
    validation: { checker: { mode: 'live', pass: checker.pass, fail: checker.fail, skip: checker.skip }, state: 'ok' },
    accepted: { snapshot: manifest.snapshot.id, manifest_sha256: manifestSha256 },
    freshness: f.freshness,
    expected_next_update_by: f.expected_next_update_by,
  };
}

/** The response record of 20.2, exactly its twelve fields. */
const RECORD_FIELDS = ['n', 'host', 'url', 'requested_at', 'status', 'content_type', 'content_length', 'etag', 'last_modified', 'date', 'bytes', 'sha256'];
const responseRecord = (meta) => Object.fromEntries(RECORD_FIELDS.map((k) => [k, meta[k] ?? null]));

/** The open alerts of a working root's ledger (17.8), for the issue job (21.5). */
const ledgerOf = (root) => {
  const file = join(root, 'archive', 'state', 'alerts.json');
  return existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')).open.map(({ key, severity, title, body }) => ({ key, severity, title, body })) : [];
};

/**
 * Writes a validated working root into a v0.7 checkout, verifies the written checkout again, and
 * with `push` commits and pushes it without force (21.3 steps 7 and the fail-closed rule).
 */
export function writeStore({ root, state, run, record, bodies, push, message, clock, validateStore = null }) {
  const { descriptor, record: full } = exportStateV2(root, state, { run, writtenAt: clock(), record, bodies });
  const again = verifyStateV2(state);
  if (!again.ok) throw new Error(`state store not written: the written checkout does not verify (${again.problems.join('; ')})`);
  if (validateStore) {
    const c = validateStore(state);
    if (c.fail !== 0) throw new Error(`state store not written: the independent checker failed on the written store (${c.failures.join(' | ')})`);
  }
  const out = { descriptor, record: full, commit: null };
  if (push) {
    const pushed = commitAndPush(state, { message });
    if (!pushed.ok) throw new Error(`state store not written: ${pushed.step} refused (${String(pushed.detail).trim()})`);
    out.commit = pushed.commit;
  }
  return out;
}

/**
 * A Stage C collection (21.3): scheduled or manual, live, into a promoted v0.7 store. Refuses an
 * empty, Stage B or unpromoted store. Validation by the independent checker comes before any
 * write; any failure before the push leaves the store as it was.
 */
export async function collectStageC({ root, state, run, trigger = 'schedule', push = false, env = process.env, transportRequest = undefined, clock = nowIso, wait = sleep, healthFacts = null, factsUnavailable = false, validate = validateRoot, validateStore = null, transportClock = () => new Date(), inputs = loadInputs() }) {
  const layout = storeLayout(state);
  if (layout !== 'v0.7') throw new Error(`state store refused: Stage C needs a promoted v0.7 store, found ${layout}`);
  const verified = verifyStateV2(state);
  if (!verified.ok) throw new Error(`state store refused: ${verified.problems.join('; ')}`);
  const facts = { pipelineDir: PIPELINE_DIR, liveTransportExists: existsSync(join(PIPELINE_DIR, 'collectors', 'live-transport.mjs')), liveCollectionAuthorized: env.LIVE_COLLECTION_AUTHORIZED === 'true', stateStoreExists: true };
  importStateV2(state, root);
  const now = clock();
  const extraAlerts = [];
  const budget = storeBudgetAlert(state, now);
  if (budget) extraAlerts.push(budget);
  if (factsUnavailable) extraAlerts.push({ key: 'self-check-unavailable', severity: 'warning', title: 'Schedule self-check unavailable', body: 'The facts for the schedule self-check could not be read from the GitHub API in this run; the run continued without them.' });
  const accepted = JSON.parse(readFileSync(join(root, 'live', 'manifest.json'), 'utf8'));
  const recorded = [];
  const record = (e) => recorded.push(e);
  const transport = makeLiveTransport({ registry: inputs.registry, record, ...(transportRequest ? { request: transportRequest } : {}), clock: transportClock });
  const fetch = adapterFetch({ registry: inputs.registry, transport, wait });
  const result = await runCollector({ root, mode: 'live', activationFacts: facts, registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays, now, run: { id: run, attempt: 1, trigger, collector_commit: env.GITHUB_SHA ?? '0'.repeat(40) }, fetch, wait, healthFacts: healthFacts ? { ...healthFacts, manifest: accepted } : null, extraAlerts });
  // Provenance (20.2): every body must match its recorded hash before anything is kept.
  for (const r of recorded) if (createHash('sha256').update(r.body).digest('hex') !== r.sha256 || r.body.length !== r.bytes) throw new Error(`response ${r.n} does not match its recorded hash`);
  const checker = validate(root);
  if (checker.fail !== 0) throw new Error(`validation failed: the independent checker found ${checker.fail} failure(s) in the working root; the store is not written (${(checker.failures ?? []).join(' | ')})`);
  const rec = collectionRecord({ run, trigger, operation: null, startedAt: now, endedAt: clock(), outcome: result.outcome, requests: recorded.map(responseRecord), checker, root, inputs, now });
  const w = writeStore({ root, state, run, record: rec, bodies: recorded.map((r) => ({ sha256: r.sha256, bytes: r.body })), push, message: `Stage C collection ${run}: ${result.outcome} (private)`, clock, validateStore });
  return { outcome: result.outcome, run, requests: rec.requests.map(({ n, host, status, bytes, sha256 }) => ({ n, host, status, bytes, sha256 })), series: result.record?.series ?? {}, accepted: w.record.accepted, added: w.record.added, commit: w.commit, ledger: ledgerOf(root), plan: result.plan ?? [], error: result.error ?? null };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const mode = arg('--mode');
  const root = arg('--root');
  if (!['fixture', 'live'].includes(mode) || !root) {
    console.error('usage: node pipeline/bin/collect.mjs --mode fixture --root <dir>\n       node pipeline/bin/collect.mjs --mode live --root <dir> --state <dir> --run <id> --trigger schedule|manual [--facts <file> | --facts-unavailable] [--summary <file>] [--push]');
    process.exit(2);
  }
  try {
    if (mode === 'fixture') {
      const r = await collect({ mode, root });
      console.log(JSON.stringify(r));
      process.exit(0);
    }
    // Live mode is Stage C only: a promoted v0.7 store (the Stage B run is done).
    const factsFile = arg('--facts');
    const r = await collectStageC({ root, state: arg('--state'), run: arg('--run'), trigger: arg('--trigger') ?? 'manual', push: process.argv.includes('--push'), healthFacts: factsFile ? JSON.parse(readFileSync(factsFile, 'utf8')) : null, factsUnavailable: process.argv.includes('--facts-unavailable'), validateStore: (s) => runChecker(['--state', s]) });
    if (arg('--summary')) writeFileSync(arg('--summary'), JSON.stringify(r));
    console.log(JSON.stringify({ ...r, ledger: r.ledger.map((a) => a.key), plan: r.plan.map((p) => `${p.action} ${p.key}`) }));
    process.exit(r.outcome === 'failed' || r.outcome === 'gate-failed' ? 1 : 0);
  } catch (e) {
    console.error(e.message);
    process.exit(3);
  }
}
