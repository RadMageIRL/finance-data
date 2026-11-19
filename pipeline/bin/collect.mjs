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
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadInputs, runScenario } from './fixture-scenario.mjs';
import { runCollector } from '../lib/run.mjs';
import { adapterFetch } from '../collectors/adapters.mjs';
import { makeLiveTransport } from '../collectors/live-transport.mjs';
import { commitAndPush, exportState, importState, verifyState } from '../lib/state-store.mjs';
import { canonicalJson } from '../lib/canonical.mjs';

const PIPELINE_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : undefined;
};
const nowIso = () => `${new Date().toISOString().slice(0, 19)}Z`;
const sleep = (seconds) => new Promise((r) => setTimeout(r, seconds * 1000));

export async function collect({ mode, root, responses = null, state = null, run = 'live-attempt', push = false, env = process.env, transportRequest = undefined, clock = nowIso, wait = sleep }) {
  const inputs = loadInputs();
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
  const transport = makeLiveTransport({ registry: inputs.registry, record, ...(transportRequest ? { request: transportRequest } : {}) });
  // `wait` paces the retries (sleep in a real run; a test passes one that records instead).
  const fetch = adapterFetch({ registry: inputs.registry, transport, wait });
  // The root continues from the state store's newest unpublished root (an empty root the first time).
  if (!verified.fresh) importState(state, root);
  const started = Date.now();
  const result = await runCollector({ root, mode: 'live', activationFacts: facts, registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays, now: clock(), run: { id: run, attempt: 1, trigger: 'manual', collector_commit: env.GITHUB_SHA ?? '0'.repeat(40) }, fetch, wait });
  const seconds = Math.round((Date.now() - started) / 1000);
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
  return summary;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const mode = arg('--mode');
  const root = arg('--root');
  if (!['fixture', 'live'].includes(mode) || !root) {
    console.error('usage: node pipeline/bin/collect.mjs --mode fixture|live --root <dir> [--responses <dir> --state <dir> --run <id> --push]');
    process.exit(2);
  }
  try {
    const r = await collect({ mode, root, responses: arg('--responses') ?? null, state: arg('--state') ?? null, run: arg('--run') ?? 'live-attempt', push: process.argv.includes('--push') });
    console.log(JSON.stringify(r));
    process.exit(r.outcome === 'failed' || r.outcome === 'gate-failed' ? 1 : 0);
  } catch (e) {
    console.error(e.message);
    process.exit(3);
  }
}
