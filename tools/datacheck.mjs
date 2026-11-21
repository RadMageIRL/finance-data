#!/usr/bin/env node
// Independent verification of the data pipeline (DATA_CONVENTIONS appendix B): writes the
// fixture scenario's pipeline root, then runs the independent Python checker on it. The
// checker was written by a separate agent from the conventions text alone and never reads
// pipeline/lib, so it and the pipeline can only agree by both following the text.
//
// No open item remains: the holiday table was resolved on 2026-11-18, so any failure of the
// checker fails this step. Should an item ever have to stay open, it is named in OPEN with its
// reason, and the step then also fails when that item unexpectedly passes.
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { runScenario } from '../pipeline/bin/fixture-scenario.mjs';
import { runStateScenario } from '../pipeline/bin/state-scenario.mjs';
import { runPublishScenario } from '../pipeline/bin/publish-scenario.mjs';

const OPEN = {};

const root = join('local', 'data-out', 'check');
rmSync(root, { recursive: true, force: true });
mkdirSync(root, { recursive: true });
const { log } = await runScenario(root);
console.log(`data check: fixture scenario wrote ${root} (${log.length} steps: ${log.map((l) => l.outcome).join(', ')})`);

// The same scenario again, in a second folder: every file must be byte for byte the same.
const twin = join('local', 'data-out', 'check-twin');
rmSync(twin, { recursive: true, force: true });
mkdirSync(twin, { recursive: true });
await runScenario(twin);
const treeHash = (dir) => {
  const h = createHash('sha256');
  const walk = (d, rel) => {
    for (const e of readdirSync(d, { withFileTypes: true }).sort((x, y) => (x.name < y.name ? -1 : 1))) {
      const r = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) walk(join(d, e.name), r);
      else h.update(r).update('\0').update(readFileSync(join(d, e.name))).update('\0');
    }
  };
  walk(dir, '');
  return h.digest('hex');
};
const rootHash = treeHash(root);
const same = rootHash === treeHash(twin);
rmSync(twin, { recursive: true, force: true });
console.log(`data check: a second run of the scenario wrote ${same ? 'the same bytes' : 'DIFFERENT bytes'}`);
if (!same) process.exit(1);
// Cross-platform byte consistency (21.2, v0.7): the scenario's tree hash is committed, and the
// same value must come out on Windows and on Linux. After a deliberate change to the pipeline's
// output, write the new hash printed here into pipeline/fixtures/scenario-tree.sha256.
const committed = readFileSync(join('pipeline', 'fixtures', 'scenario-tree.sha256'), 'utf8').trim().split(/\s+/)[0];
console.log(`data check: scenario tree hash ${rootHash} ${rootHash === committed ? 'equals the committed one' : `DIFFERS from the committed ${committed}`}`);
if (rootHash !== committed) process.exit(1);

let run = null;
for (const python of ['python', 'python3']) {
  run = spawnSync(python, ['-I', join('tests', 'datacheck', 'check_p22.py'), '--root', root], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  run.python = python;
  if (!run.error) break;
}
if (!run || run.error) {
  console.log('data check: Python is not available');
  process.exit(1);
}
const lines = `${run.stdout ?? ''}`.split(/\r?\n/);
const count = { PASS: 0, FAIL: 0, SKIP: 0 };
const failed = [];
for (const line of lines) {
  const m = /^(PASS|FAIL|SKIP)\s+(\S+)/.exec(line);
  if (!m) continue;
  count[m[1]] += 1;
  if (m[1] === 'FAIL') failed.push({ id: m[2], line });
}
const unexpected = failed.filter((f) => !(f.id in OPEN));
const stillOpen = Object.keys(OPEN).filter((id) => failed.some((f) => f.id === id));
const closed = Object.keys(OPEN).filter((id) => !stillOpen.includes(id));
for (const f of unexpected) console.log(f.line);
if (run.stderr) process.stdout.write(run.stderr);
console.log(`data check: ${count.PASS} passed, ${count.FAIL} failed, ${count.SKIP} skipped`);
for (const id of stillOpen) console.log(`data check: ${id} fails as expected and stays open: ${OPEN[id]}`);
for (const id of closed) console.log(`data check: ${id} is listed as open but no longer fails; remove it from tools/datacheck.mjs`);
if (count.PASS === 0) console.log('data check: the checker reported nothing');
if (unexpected.length || closed.length || count.PASS === 0) process.exit(1);

// The comparison mode (20.4) against synthetic collections with known edits: it must report
// exactly those edits, refuse tampered or unsafe responses, and never write into a collection.
const selfOut = join('local', 'data-out', 'compare-selftest');
rmSync(selfOut, { recursive: true, force: true });
const self = spawnSync(run.python, ['-I', join('tests', 'datacheck', 'compare_selftest.py'), selfOut], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
const summary = /^SELFTEST (\d+) PASS, (\d+) FAIL/m.exec(self.stdout ?? '');
for (const line of `${self.stdout ?? ''}`.split(/\r?\n/)) if (line.startsWith('FAIL')) console.log(line);
if (self.stderr) process.stdout.write(self.stderr);
console.log(`data check: comparison self-test ${summary ? `${summary[1]} passed, ${summary[2]} failed` : 'reported nothing'}`);
if (!(self.status === 0 && summary && summary[2] === '0' && Number(summary[1]) > 0)) process.exit(1);

// The state store scenario (appendix G, v0.7), twice: the same bytes; then the independent
// checker's scenario mode on it, which also runs the state mode on the final store.
const stateDir = join('local', 'data-out', 'state-check');
const stateTwin = join('local', 'data-out', 'state-check-twin');
for (const d of [stateDir, stateTwin]) rmSync(d, { recursive: true, force: true });
const g = await runStateScenario(stateDir);
await runStateScenario(stateTwin);
const stateSame = treeHash(stateDir) === treeHash(stateTwin);
console.log(`data check: state scenario wrote ${stateDir} (${g.steps.length} steps: ${g.steps.map((s) => s.outcome).join(', ')}); a second run wrote ${stateSame ? 'the same bytes' : 'DIFFERENT bytes'}`);
if (!stateSame) {
  // Keep the twin and name the files that differ, so the cause can be read.
  const files = (dir) => {
    const out = new Map();
    const walk = (d, rel) => {
      for (const e of readdirSync(d, { withFileTypes: true })) {
        const r = rel ? `${rel}/${e.name}` : e.name;
        if (e.isDirectory()) walk(join(d, e.name), r);
        else out.set(r, createHash('sha256').update(readFileSync(join(d, e.name))).digest('hex'));
      }
    };
    walk(dir, '');
    return out;
  };
  const x = files(stateDir);
  const y = files(stateTwin);
  const differ = [...new Set([...x.keys(), ...y.keys()])].filter((k) => x.get(k) !== y.get(k)).sort();
  for (const k of differ.slice(0, 20)) console.log(`data check: differs: ${k}`);
  console.log(`data check: ${differ.length} file(s) differ; the second run is kept in ${stateTwin}`);
  process.exit(1);
}
rmSync(stateTwin, { recursive: true, force: true });
const sc = spawnSync(run.python, ['-I', join('tests', 'datacheck', 'check_p22.py'), '--state-scenario', stateDir], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
const scCount = /^SUMMARY (\d+) PASS, (\d+) FAIL, (\d+) SKIP$/m.exec(sc.stdout ?? '');
for (const line of `${sc.stdout ?? ''}`.split(/\r?\n/)) if (line.startsWith('FAIL')) console.log(line);
if (sc.stderr) process.stdout.write(sc.stderr);
console.log(`data check: state scenario check ${scCount ? `${scCount[1]} passed, ${scCount[2]} failed, ${scCount[3]} skipped` : 'reported nothing'}`);
if (!(sc.status === 0 && scCount && scCount[2] === '0' && Number(scCount[1]) > 0)) process.exit(1);

// The publication scenario (appendix J, v0.8), twice: the same bytes, releases included; then the
// independent checker's appendix J mode on it.
const pubDir = join('local', 'data-out', 'publish-check');
const pubTwin = join('local', 'data-out', 'publish-check-twin');
for (const d of [pubDir, pubTwin]) rmSync(d, { recursive: true, force: true });
const j = await runPublishScenario(pubDir);
await runPublishScenario(pubTwin);
const pubSame = treeHash(pubDir) === treeHash(pubTwin);
console.log(`data check: publication scenario wrote ${pubDir} (${j.steps.length} steps: ${j.steps.map((s) => s.outcome).join(', ')}); a second run wrote ${pubSame ? 'the same bytes' : 'DIFFERENT bytes'}`);
if (!pubSame) process.exit(1);
rmSync(pubTwin, { recursive: true, force: true });
const pc = spawnSync(run.python, ['-I', join('tests', 'datacheck', 'check_p22.py'), '--publication-scenario', pubDir], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
const pcCount = /^SUMMARY (\d+) PASS, (\d+) FAIL, (\d+) SKIP$/m.exec(pc.stdout ?? '');
for (const line of `${pc.stdout ?? ''}`.split(/\r?\n/)) if (line.startsWith('FAIL')) console.log(line);
if (pc.stderr) process.stdout.write(pc.stderr);
console.log(`data check: publication scenario check ${pcCount ? `${pcCount[1]} passed, ${pcCount[2]} failed, ${pcCount[3]} skipped` : 'reported nothing'}`);
if (!(pc.status === 0 && pcCount && pcCount[2] === '0' && Number(pcCount[1]) > 0)) process.exit(1);

// The checker's own self-test of the state and scenario modes, where its local evidence exists
// (it builds on the saved copy of the real Stage B store, which only the Finance checkout has).
const evidence = join('local', 'research', 'p26', 'live', 'state-store');
if (!existsSync(evidence)) {
  console.log('data check: state self-test not run here (the saved Stage B store is local evidence)');
  process.exit(0);
}
const stOut = join('local', 'data-out', 'state-selftest');
rmSync(stOut, { recursive: true, force: true });
const st = spawnSync(run.python, ['-I', join('tests', 'datacheck', 'state_selftest.py'), stOut], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
const stCount = /^SELFTEST (\d+) PASS, (\d+) FAIL/m.exec(st.stdout ?? '');
for (const line of `${st.stdout ?? ''}`.split(/\r?\n/)) if (line.startsWith('FAIL')) console.log(line);
if (st.stderr) process.stdout.write(st.stderr);
console.log(`data check: state self-test ${stCount ? `${stCount[1]} passed, ${stCount[2]} failed` : 'reported nothing'}`);
if (!(st.status === 0 && stCount && stCount[2] === '0' && Number(stCount[1]) > 0)) process.exit(1);

// The checker's publication self-test (v0.8), on the saved copy of the accepted store where it exists.
const pubEvidence = join('local', 'research', 'p27', 'observe', 'state');
if (!existsSync(pubEvidence)) {
  console.log('data check: publication self-test not run here (the saved accepted store is local evidence)');
  process.exit(0);
}
const ptOut = join('local', 'data-out', 'publication-selftest');
rmSync(ptOut, { recursive: true, force: true });
const pt = spawnSync(run.python, ['-I', join('tests', 'datacheck', 'publication_selftest.py'), ptOut], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
const ptCount = /^SUMMARY (\d+) PASS, (\d+) FAIL/m.exec(pt.stdout ?? '');
for (const line of `${pt.stdout ?? ''}`.split(/\r?\n/)) if (line.startsWith('FAIL')) console.log(line);
if (pt.stderr) process.stdout.write(pt.stderr);
console.log(`data check: publication self-test ${ptCount ? `${ptCount[1]} passed, ${ptCount[2]} failed` : 'reported nothing'}`);
process.exit(pt.status === 0 && ptCount && ptCount[2] === '0' && Number(ptCount[1]) > 0 ? 0 : 1);
