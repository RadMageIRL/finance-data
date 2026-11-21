#!/usr/bin/env node
// The state store scenario (DATA_CONVENTIONS v0.7 appendix G): from the saved histories only,
// through the collector adapters, the live transport (answered by the fixture transport, so no
// network connection is opened) and the state store, eleven steps on a fixed clock: a Stage B
// collection into an empty store, the promotion, scheduled runs (unchanged, new observations, the
// Sunday full fetch with a historical revision, a later Sunday run, failed requests), a review,
// a rollback, a restore, and a last scheduled run. Writes <dir>/store (a plain folder: nothing is
// committed or pushed) and <dir>/steps.json. The same bytes every time.
//
//   node pipeline/bin/state-scenario.mjs <empty dir>
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { effrDay, debtDay } from './fixture-scenario.mjs';
import { collect, collectStageC, validateRoot } from './collect.mjs';
import { operate } from './state-op.mjs';
import { effrRawRecord, fixtureRequest, loadRawFixtures, makeFixtureTransport } from '../lib/fixture-transport.mjs';
import { canonicalJson } from '../lib/canonical.mjs';

const REVIEWER = 'example-maintainer';
const PERMISSION = 'maintain';
const AUTHORIZED = { LIVE_COLLECTION_AUTHORIZED: 'true' };
const PUSHED_AT = '2026-11-16T15:00:00Z';

const addDollars = (text, n) => {
  const [int, frac] = text.split('.');
  return `${(BigInt(int) + BigInt(n)).toString()}.${frac}`;
};

/**
 * Runs appendix G into `dir`. Options: `validate`, the live root check (the independent checker
 * unless a test gives another); `upTo`, the last step to run (appendix J starts after step 4, I46).
 * Returns { steps, pauses, data }: `data` is the fixture data as the last step left it.
 */
export async function runStateScenario(dir, { validate = validateRoot, upTo = 11 } = {}) {
  if (existsSync(dir) && readdirSync(dir).length) throw new Error(`${dir} is not empty`);
  const store = join(dir, 'store');
  const work = join(dir, 'work');
  mkdirSync(store, { recursive: true });
  const data = loadRawFixtures();
  const steps = [];
  const pauses = [];
  const wait = async (seconds) => void pauses.push(seconds);
  const ledgerOfStore = () => {
    const f = join(store, 'state', 'alerts.json');
    return existsSync(f) ? JSON.parse(readFileSync(f, 'utf8')).open.map(({ key, severity, title, body }) => ({ key, severity, title, body })) : [];
  };
  const fresh = (n) => {
    const d = join(work, `g${n}`);
    rmSync(d, { recursive: true, force: true });
    mkdirSync(d, { recursive: true });
    return d;
  };
  const note = (n, at, trigger, operation, r) => {
    steps.push({ step: n, run: `g${n}`, trigger, operation, at, outcome: r.outcome, record: n === 1 ? null : `runs/g${n}.json`, plan: (r.plan ?? []).map((p) => ({ action: p.action, key: p.key })), ledger: ledgerOfStore() });
  };
  const request = (scripted = {}) => fixtureRequest(makeFixtureTransport(data, scripted));
  // The self-check facts of every scheduled step (21.3 step 4): an active workflow, a repository
  // last pushed before the scenario, and the earlier scheduled steps as successful runs, newest
  // first, after the current one, which is still in progress.
  const succeeded = [];
  const scheduled = async (n, at, scripted = {}) => {
    const healthFacts = { workflow: { state: 'active' }, repository: { pushed_at: PUSHED_AT }, runs: [{ event: 'schedule', conclusion: null, created_at: at }, ...[...succeeded].reverse()] };
    const r = await collectStageC({ root: fresh(n), state: store, run: `g${n}`, trigger: 'schedule', env: AUTHORIZED, transportRequest: request(scripted), clock: () => at, transportClock: () => new Date(at), wait, validate, healthFacts });
    if (r.outcome !== 'failed' && r.outcome !== 'gate-failed') succeeded.push({ event: 'schedule', conclusion: 'success', created_at: at });
    note(n, at, 'schedule', null, r);
    return r;
  };
  const operation = async (n, at, op, more) => {
    const r = await operate({ op, state: store, root: fresh(n), run: `g${n}`, actor: REVIEWER, permission: PERMISSION, checkedAt: at, now: at, clock: () => at, validate, ...more });
    note(n, at, 'operation', op, r);
    return r;
  };
  const lastDebt = () => data.debt[data.debt.length - 1];

  // 1. A manual Stage B collection into an empty store: the saved histories.
  const t1 = '2026-11-16T16:17:00Z';
  const first = await collect({ mode: 'live', root: fresh(1), responses: join(work, 'g1-responses'), state: store, run: 'g1', env: AUTHORIZED, transportRequest: request(), clock: () => t1, transportClock: () => new Date(t1), wait, timer: () => 0 });
  note(1, t1, 'manual', null, first);
  // 2. The promotion, with step 1's manifest SHA-256 (the reviewed dataset).
  const manifestSha256 = createHash('sha256').update(readFileSync(join(store, 'unpublished', 'g1', 'live', 'manifest.json'))).digest('hex');
  await operation(2, '2026-11-16T16:30:00Z', 'promote', { manifestSha256, decision: { brief: 'docs/P26_STAGE_B_ACCEPTANCE_STAGE_C.md', decided_on: '2026-11-16' } });
  // 3. Scheduled; the sources unchanged; only the EFFR group is due (windowed).
  await scheduled(3, '2026-11-16T20:17:00Z');
  // 4. Scheduled; a new EFFR day and a new debt record date, 2026-11-13.
  data.effr.push(effrRawRecord(effrDay('2026-11-13')));
  data.debt.push(debtDay(lastDebt(), '2026-11-13', 1_000_000_000));
  const fourth = await scheduled(4, '2026-11-17T00:17:00Z');
  if (upTo <= 4) return finish();
  // 5. The first Sunday run: the weekly full fetch; the 2019-12-31 total one dollar higher.
  data.debt = data.debt.map((r) => (r.record_date === '2019-12-31' ? { ...r, tot_pub_debt_out_amt: addDollars(r.tot_pub_debt_out_amt, 1) } : r));
  await scheduled(5, '2026-11-22T16:17:00Z');
  // 6. A later Sunday run: no weekly full fetch again.
  await scheduled(6, '2026-11-22T20:17:00Z');
  // 7. Monday: the debt source answers 500 to the request and its three retries; new EFFR days.
  for (const d of ['2026-11-16', '2026-11-17', '2026-11-18', '2026-11-19', '2026-11-20']) data.effr.push(effrRawRecord(effrDay(d)));
  const failing = { status: 500, headers: {}, bytes: Buffer.from('Internal Server Error') };
  await scheduled(7, '2026-11-23T16:17:00Z', { 'api.fiscaldata.treasury.gov': [failing, failing, failing, failing] });
  // 8. Review: reject the debt-total hold.
  const queue = JSON.parse(readFileSync(join(store, 'state', 'review-queue.json'), 'utf8'));
  const hold = queue.open.find((q) => q.series === 'debt-total');
  if (!hold) throw new Error('state scenario: no debt-total hold to review at step 8');
  await operation(8, '2026-11-23T16:30:00Z', 'review', { series: 'debt-total', candidate: hold.candidate_sha256, reviewDecision: 'reject', reason: 'Scenario: the historical change is not accepted.' });
  // 9. Rollback to the snapshot of step 4.
  await operation(9, '2026-11-23T16:45:00Z', 'rollback', { to: fourth.accepted.snapshot, reason: 'Scenario: return to the step 4 snapshot.' });
  // 10. Restore: the working root's live tree is deleted and rebuilt from the archive.
  await operation(10, '2026-11-23T17:00:00Z', 'restore', { reason: 'Scenario: rebuild the live tree from the archive.' });
  // 11. Scheduled; the sources as at step 7, the debt source answering again.
  await scheduled(11, '2026-11-23T20:17:00Z');
  return finish();

  function finish() {
    rmSync(work, { recursive: true, force: true });
    writeFileSync(join(dir, 'steps.json'), canonicalJson(steps));
    return { steps, pauses, data };
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const dir = process.argv[2];
  if (!dir) {
    console.error('usage: node pipeline/bin/state-scenario.mjs <empty dir>');
    process.exit(2);
  }
  const { steps } = await runStateScenario(dir);
  for (const s of steps) console.log(JSON.stringify({ step: s.step, at: s.at, operation: s.operation, outcome: s.outcome, plan: s.plan.map((p) => `${p.action} ${p.key}`) }));
}
