#!/usr/bin/env node
// The publication scenario (DATA_CONVENTIONS v0.8 appendix J): from the appendix G store as after
// its step 4, nineteen steps on a fixed clock against two local stand-ins: a release store
// `<dir>/releases/<tag>/` and a production `<dir>/production/` (its site runs and its deployed
// `econ/` tree). It runs the publication run of 22.6 (assembly, the pipeline's own V2 checks, the
// release, the dispatch, V3 on the production tree, the report job's alerts), the site build's data
// steps of 22.8, collections and operations on the store. Fixtures only: nothing leaves the
// machine. Writes <dir>/store, <dir>/releases, <dir>/production and <dir>/steps.json; the same
// bytes every time. The independent checker then checks the output (its appendix J mode).
//
//   node pipeline/bin/publish-scenario.mjs <empty dir>
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runStateScenario } from './state-scenario.mjs';
import { debtDay, effrDay, loadInputs } from './fixture-scenario.mjs';
import { collectStageC, validateRoot } from './collect.mjs';
import { operate } from './state-op.mjs';
import { effrRawRecord, fixtureRequest, makeFixtureTransport } from '../lib/fixture-transport.mjs';
import { canonicalJson, sha256Hex } from '../lib/canonical.mjs';
import { verifyStateV2 } from '../lib/state-store.mjs';
import { ownV2Refusal, publicationWindow, readTree } from '../lib/publish-store.mjs';
import { artifactSummary, fixPost, nextLog, nothingToPublish, releaseAssets, releaseTag, sameDataset, verifiedPairs } from '../lib/publication.mjs';
import { checkRelease, currentText, deployRefusal, deployedState, inputRefusal, runName } from '../lib/site-build.mjs';

const SITE_COMMIT = '0'.repeat(40);
const REVIEWER = 'example-maintainer';
const PERMISSION = 'maintain';
const AUTHORIZED = { LIVE_COLLECTION_AUTHORIZED: 'true' };
/** V2b's counts in the scenario (I47): the independent checker checks the scenario's output afterwards. */
const SCENARIO_CHECKER = { pass: 1, fail: 0, skip: 0 };

const writeTree = (dir, files) => {
  rmSync(dir, { recursive: true, force: true });
  for (const [p, b] of files) {
    mkdirSync(join(dir, p, '..'), { recursive: true });
    writeFileSync(join(dir, p), b);
  }
};

export async function runPublishScenario(dir, { validate = validateRoot } = {}) {
  if (existsSync(dir) && readdirSync(dir).length) throw new Error(`${dir} is not empty`);
  // The appendix G store as after its step 4 (I46), and the fixture data as that step left it.
  const g = join(dir, 'g');
  const { data } = await runStateScenario(g, { validate, upTo: 4 });
  const storeDir = join(dir, 'store');
  cpSync(join(g, 'store'), storeDir, { recursive: true });
  rmSync(g, { recursive: true, force: true });
  const releasesDir = join(dir, 'releases');
  const prodDir = join(dir, 'production');
  mkdirSync(releasesDir, { recursive: true });
  mkdirSync(prodDir, { recursive: true });
  const work = join(dir, 'work');
  const inputs = loadInputs();
  const runs = [];
  // J's runs.json shape exactly: { run, mode, dataset, release, conclusion, deployed } (internal fields stay out).
  const writeRuns = () => writeFileSync(join(prodDir, 'runs.json'), canonicalJson(runs.map(({ run, mode, dataset, release, conclusion, deployed }) => ({ run, mode, dataset, release, conclusion, deployed }))));
  writeRuns();
  const verifyOutcome = new Map();
  const alerts = new Set();
  const steps = [];
  const fresh = (n) => {
    const d = join(work, `j${n}`);
    rmSync(d, { recursive: true, force: true });
    mkdirSync(d, { recursive: true });
    return d;
  };

  const releases = () => (existsSync(releasesDir) ? readdirSync(releasesDir) : []).map((tag) => ({ tag, log: JSON.parse(readFileSync(join(releasesDir, tag, 'deployments.json'), 'utf8')) }));
  const newestRelease = () => releases().sort((a, b) => a.log.deployments.length - b.log.deployments.length).pop() ?? null;
  const assetsOf = (tag) => Object.fromEntries(readdirSync(join(releasesDir, tag)).map((n) => [n, readFileSync(join(releasesDir, tag, n))]));
  const runFacts = (rel) => {
    if (!rel) return null;
    const last = rel.log.deployments[rel.log.deployments.length - 1];
    const site = [...runs].reverse().find((r) => r.release === rel.tag && r.dispatched);
    return { completed: true, siteConclusion: site?.conclusion ?? null, verifyConclusion: verifyOutcome.get(last.run) ?? null };
  };
  const productionDataset = () => deployedState(runs.map((r) => ({ name: runName(r.mode, r.dataset, r.release), conclusion: r.conclusion, deployed: r.deployed }))).dataset;
  const note = (n, run, at, kind, mode, outcome, release = null) => steps.push({ step: n, run, at, kind, mode, outcome, release, deployed: productionDataset(), alerts: [...alerts].sort() });

  // ---- The site build (22.8), local: data steps, compare-and-swap, deploy ----
  const siteBuild = ({ run, mode, tag = null, dataset = null, expected = null, dispatched = false, faults = {} }) => {
    const before = deployedState(runs.map((r) => ({ name: runName(r.mode, r.dataset, r.release), conclusion: r.conclusion, deployed: r.deployed })));
    let expected_current = expected ?? currentText(before.dataset);
    let files = null;
    let log = null;
    let useTag = tag;
    let useDataset = dataset;
    const fail = (why) => {
      runs.push({ run, mode, dataset: useDataset, release: useTag, conclusion: 'failure', deployed: false, dispatched, why });
      writeRuns();
      return { ok: false, why };
    };
    if (mode === 'site') {
      useTag = before.release;
      useDataset = before.dataset;
    }
    const refusal = inputRefusal({ mode, tag: useTag, snapshot: useDataset?.snapshot ?? null, manifest_sha256: useDataset?.manifest_sha256 ?? null, site_commit: SITE_COMMIT, expected_current });
    if (refusal) return fail(refusal);
    if (useTag && mode !== 'unpublish') {
      try {
        ({ files, log } = checkRelease(assetsOf(useTag), useDataset));
      } catch (e) {
        return fail(e.message);
      }
    }
    // Immediately before the deploy: the deployed state again (22.8).
    const now = deployedState(runs.map((r) => ({ name: runName(r.mode, r.dataset, r.release), conclusion: r.conclusion, deployed: r.deployed })));
    const why = deployRefusal({ mode, expected_current, deployed: now, input: useDataset, log });
    if (why) return fail(why);
    if (mode === 'unpublish' || !files) {
      rmSync(join(prodDir, 'econ'), { recursive: true, force: true });
      useTag = null;
      useDataset = null;
    } else writeTree(join(prodDir, 'econ'), files);
    if (faults.alterAfterDeploy) {
      const path = [...files.keys()].find((p) => p.startsWith('objects/'));
      writeFileSync(join(prodDir, 'econ', path), Buffer.concat([files.get(path), Buffer.from(' ')]));
    }
    runs.push({ run, mode, dataset: useDataset, release: useTag, conclusion: 'success', deployed: true, dispatched });
    writeRuns();
    return { ok: true, files };
  };

  // ---- V3 on the production tree (22.5) ----
  const v3 = (files) => {
    const prod = readTree(join(prodDir, 'econ'));
    if (prod.size !== files.size) return false;
    for (const [p, b] of files) if (!prod.has(p) || !prod.get(p).equals(Buffer.from(b))) return false;
    return true;
  };

  // ---- The publication run (22.6) ----
  const publish = async ({ n, run, at, mode, input = null, target = null, person = true, faults = {} }) => {
    const done = (outcome, release = null) => {
      note(n, run, at, 'publish', mode, outcome, release);
      return { outcome, release };
    };
    // Gates (22.6): timer pauses while publication-verify-failed is open.
    if (mode === 'timer' && alerts.has('publication-verify-failed')) return done('refused-paused');
    const v = verifyStateV2(storeDir);
    if (!v.ok) throw new Error(`publish scenario: the store does not verify (${v.problems.join('; ')})`);
    const state = JSON.parse(readFileSync(join(storeDir, 'state', 'STATE.json'), 'utf8'));
    const accepted = state.accepted;
    if (mode === 'manual' && !sameDataset(input, accepted)) return done('refused-gate');
    // The previous release, with its last post fixed (22.4).
    const prev = newestRelease();
    const prevPost = prev ? fixPost(runFacts(prev)) : null;
    const prevLog = prev ? structuredClone(prev.log) : null;
    if (prevLog && prevLog.deployments.length && prevLog.deployments[prevLog.deployments.length - 1].verification.post === null) prevLog.deployments[prevLog.deployments.length - 1].verification.post = prevPost;
    if ((mode === 'manual' || mode === 'timer') && nothingToPublish(prevLog, accepted)) return done('no-op');
    // The window (22.3).
    const dataset = mode === 'redeploy' ? target.dataset : accepted;
    const siteCommit = mode === 'redeploy' ? target.site_commit : SITE_COMMIT;
    const files = publicationWindow(storeDir, mode, dataset);
    if (faults.plant) files.set(faults.plant, Buffer.from('{}'));
    // The pipeline's own V2 checks (the independent checker repeats them, 22.5).
    const refusal = ownV2Refusal(storeDir, files, prevLog);
    if (refusal) {
      alerts.add('publish-failed');
      return done(refusal.outcome);
    }
    // The log and the release (22.4).
    const runId = `pub-${run}-1`;
    const tag = releaseTag(dataset.snapshot, run, 1);
    const log = nextLog(prevLog, prevPost, { published_at: at, run: runId, trigger: mode, dataset, release: tag, site_commit: siteCommit, artifact: artifactSummary(files), checker: SCENARIO_CHECKER });
    files.set('status/deployments.json', Buffer.from(canonicalJson(log), 'utf8'));
    const assets = releaseAssets(files);
    mkdirSync(join(releasesDir, tag), { recursive: true });
    for (const [name, b] of Object.entries(assets)) writeFileSync(join(releasesDir, tag, name), b);
    // The dispatch and the site build.
    const deployed = deployedState(runs.map((r) => ({ name: runName(r.mode, r.dataset, r.release), conclusion: r.conclusion, deployed: r.deployed })));
    const site = siteBuild({ run, mode: 'data', tag, dataset, expected: faults.expected ?? currentText(deployed.dataset), dispatched: true, faults });
    if (!site.ok) {
      alerts.add('publish-failed');
      return done('refused-cas', tag);
    }
    // V3 and the report.
    const passed = v3(site.files);
    verifyOutcome.set(runId, passed ? 'success' : 'failure');
    if (passed) {
      alerts.delete('publish-failed');
      if (person) alerts.delete('publication-verify-failed');
      return done(mode === 'redeploy' ? 'redeployed' : 'released-deployed', tag);
    }
    alerts.add('publication-verify-failed');
    const r = done('verify-failed', tag);
    // D13: an automatic redeploy of the newest verified pair, started by this run (run id x100 + 1).
    const fixed = structuredClone(log);
    fixed.deployments[fixed.deployments.length - 1].verification.post = 'failed';
    const pair = verifiedPairs(fixed)[0];
    await publish({ n: n + 1, run: run * 100 + 1, at, mode: 'redeploy', target: pair, person: false });
    return r;
  };

  // ---- Collections and operations on the store ----
  const publicationFacts = () => {
    const rel = newestRelease();
    return rel ? { newestLog: rel.log, newestRun: runFacts(rel) } : { newestLog: null, newestRun: null };
  };
  const collectStep = async (n, at, trigger) => {
    const healthFacts = { workflow: { state: 'active' }, repository: { pushed_at: '2026-11-16T15:00:00Z' }, runs: [{ event: 'schedule', conclusion: null, created_at: at }] };
    const r = await collectStageC({ root: fresh(n), state: storeDir, run: `j${n}`, trigger, env: AUTHORIZED, transportRequest: fixtureRequest(makeFixtureTransport(data, {})), clock: () => at, transportClock: () => new Date(at), wait: async () => {}, validate, healthFacts, publicationFacts: publicationFacts(), inputs });
    note(n, n, at, 'collect', trigger === 'schedule' ? 'timer' : 'manual', r.outcome);
    return r;
  };
  const operateStep = async (n, at, op, more) => {
    try {
      const r = await operate({ op, state: storeDir, root: fresh(n), run: `j${n}`, actor: REVIEWER, permission: PERMISSION, checkedAt: at, now: at, clock: () => at, validate, inputs, ...more });
      note(n, n, at, 'operate', op, op === 'rollback' && r.outcome === 'published' ? 'rollback' : r.outcome);
    } catch (e) {
      if (!/the reason fails the publication text check/.test(e.message)) throw e;
      note(n, n, at, 'operate', op, 'refused-reason');
    }
  };
  const site = (n, at, mode, more = {}) => {
    const r = siteBuild({ run: n, mode, ...more });
    const outcome = !r.ok ? (/not newer/.test(r.why) ? 'refused-older' : /compare-and-swap/.test(r.why) ? 'refused-cas' : 'refused') : mode === 'unpublish' ? 'unpublished' : r.files ? 'site-carried' : 'site-no-data';
    note(n, n, at, 'site', mode, outcome);
  };
  const acceptedNow = () => JSON.parse(readFileSync(join(storeDir, 'state', 'STATE.json'), 'utf8')).accepted;
  const lastDebt = () => data.debt[data.debt.length - 1];

  // ---- The nineteen steps (appendix J) ----
  const N1 = acceptedNow();
  await publish({ n: 1, run: 1, at: '2026-11-24T15:00:00Z', mode: 'manual', input: N1 });
  await publish({ n: 2, run: 2, at: '2026-11-24T15:10:00Z', mode: 'manual', input: { snapshot: N1.snapshot, manifest_sha256: 'f'.repeat(64) } });
  site(3, '2026-11-24T15:20:00Z', 'site');
  for (const d of ['2026-11-16', '2026-11-17', '2026-11-18', '2026-11-19', '2026-11-20', '2026-11-23']) data.effr.push(effrRawRecord(effrDay(d)));
  await collectStep(4, '2026-11-24T16:17:00Z', 'schedule');
  const N2 = acceptedNow();
  await publish({ n: 5, run: 5, at: '2026-11-24T16:40:00Z', mode: 'manual', input: N2, faults: { expected: 'none' } });
  await publish({ n: 6, run: 6, at: '2026-11-24T16:50:00Z', mode: 'manual', input: N2 });
  site(7, '2026-11-24T17:00:00Z', 'data', { tag: releaseTag(N1.snapshot, 1, 1), dataset: N1, expected: currentText(N2) });
  await publish({ n: 8, run: 8, at: '2026-11-24T17:10:00Z', mode: 'manual', input: N2 });
  for (const d of ['2026-11-16', '2026-11-17', '2026-11-18', '2026-11-19', '2026-11-20']) data.debt.push(debtDay(lastDebt(), d, 1_000_000_000));
  await collectStep(9, '2026-11-24T17:20:00Z', 'manual');
  const N3 = acceptedNow();
  await publish({ n: 10, run: 10, at: '2026-11-24T17:25:00Z', mode: 'manual', input: N3, faults: { alterAfterDeploy: true } });
  await publish({ n: 12, run: 12, at: '2026-11-24T17:40:00Z', mode: 'timer' });
  await operateStep(13, '2026-11-24T17:50:00Z', 'rollback', { to: N2.snapshot, reason: 'Ask a@b.co why this changed.' });
  await publish({ n: 14, run: 14, at: '2026-11-24T18:00:00Z', mode: 'manual', input: N3, faults: { plant: 'state/planted.json' } });
  data.effr.push(effrRawRecord(effrDay('2026-11-24')));
  await collectStep(15, '2026-11-25T16:17:00Z', 'schedule');
  await operateStep(16, '2026-11-25T16:30:00Z', 'rollback', { to: N3.snapshot, reason: 'Scenario: return to the snapshot of step 9.' });
  await publish({ n: 17, run: 17, at: '2026-11-25T16:40:00Z', mode: 'manual', input: acceptedNow() });
  site(18, '2026-11-25T16:50:00Z', 'unpublish');
  site(19, '2026-11-25T17:00:00Z', 'site');

  rmSync(work, { recursive: true, force: true });
  steps.sort((a, b) => a.step - b.step);
  writeFileSync(join(dir, 'steps.json'), canonicalJson(steps));
  return { steps };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const dir = process.argv[2];
  if (!dir) {
    console.error('usage: node pipeline/bin/publish-scenario.mjs <empty dir>');
    process.exit(2);
  }
  const { steps } = await runPublishScenario(dir);
  for (const s of steps) console.log(JSON.stringify({ step: s.step, run: s.run, kind: s.kind, mode: s.mode, outcome: s.outcome, release: s.release, deployed: s.deployed?.snapshot ?? null, alerts: s.alerts }));
}
