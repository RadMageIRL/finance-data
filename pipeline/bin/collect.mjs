#!/usr/bin/env node
// The collector's entry point for workflows (DATA_CONVENTIONS 17.9 and 18). Fixture mode runs the
// deterministic scenario of appendix B into an empty root. Live mode is refused: no live
// transport exists and live collection is not authorized; the refusal is the expected answer.
//
//   node pipeline/bin/collect.mjs --mode fixture|live --root <dir>
import { fileURLToPath } from 'node:url';
import { loadInputs, runScenario } from './fixture-scenario.mjs';
import { runCollector } from '../lib/run.mjs';

const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : undefined;
};

export async function collect({ mode, root }) {
  if (mode === 'fixture') {
    const { log } = await runScenario(root);
    return { outcome: 'fixture-scenario', steps: log.length, outcomes: log.map((l) => l.outcome) };
  }
  const inputs = loadInputs();
  // A live run is refused by the pipeline before it touches the root (17.9).
  await runCollector({ root, mode, registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays, now: new Date().toISOString().slice(0, 19) + 'Z', run: { id: 'live-attempt', attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, fetch: async () => ({ status: 0 }) });
  return { outcome: 'unexpected' };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const mode = arg('--mode');
  const root = arg('--root');
  if (!['fixture', 'live'].includes(mode) || !root) {
    console.error('usage: node pipeline/bin/collect.mjs --mode fixture|live --root <dir>');
    process.exit(2);
  }
  try {
    const r = await collect({ mode, root });
    console.log(JSON.stringify(r));
    process.exit(mode === 'fixture' ? 0 : 1);
  } catch (e) {
    console.error(e.message);
    process.exit(3);
  }
}
