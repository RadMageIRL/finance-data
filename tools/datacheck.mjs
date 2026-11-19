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
import { mkdirSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { runScenario } from '../pipeline/bin/fixture-scenario.mjs';

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
const same = treeHash(root) === treeHash(twin);
rmSync(twin, { recursive: true, force: true });
console.log(`data check: a second run of the scenario wrote ${same ? 'the same bytes' : 'DIFFERENT bytes'}`);
if (!same) process.exit(1);

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
process.exit(self.status === 0 && summary && summary[2] === '0' && Number(summary[1]) > 0 ? 0 : 1);
