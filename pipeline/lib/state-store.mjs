// The durable private state store (DATA_CONVENTIONS 20.3): a git checkout of the private state
// repository with `state/` (the operational state files and STATE.json) and `unpublished/<run>/`
// (the candidate roots, never a publication). Reads fail closed: any missing, extra, changed or
// unreadable state file refuses the run. Writes add files and STATE.json last; the commit and a
// push that is never forced make them durable, and a competing writer makes the push fail.
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join, relative } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { canonicalJson } from './canonical.mjs';
import { validate } from './json-schema.mjs';

export const STATE_DIR = 'state';
export const UNPUBLISHED_DIR = 'unpublished';
const DESCRIPTOR = 'STATE.json';
const RUN_ID = /^[A-Za-z0-9._-]{1,80}$/;

const sha = (b) => createHash('sha256').update(b).digest('hex');
const SCHEMA_DIR = fileURLToPath(new URL('../schemas/', import.meta.url));
const schemaNamed = (name) => JSON.parse(readFileSync(join(SCHEMA_DIR, `${name}.schema.json`), 'utf8'));
/** The schema a state file must satisfy (20.3), or null for a file without one (collector.json). */
function stateSchema(path) {
  const rel = path.slice(STATE_DIR.length + 1);
  const named = { 'alerts.json': 'alerts', 'pins.json': 'pins', 'publications.json': 'publications', 'review-queue.json': 'review-queue' }[rel];
  if (named) return schemaNamed(named);
  if (rel.startsWith('run-records/')) {
    const runs = schemaNamed('runs');
    return { $defs: runs.$defs, ...runs.properties.runs.items };
  }
  return null;
}
const posix = (p) => p.split('\\').join('/');

function listFiles(dir) {
  if (!existsSync(dir)) return [];
  const out = [];
  const walk = (d) => {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, e.name);
      if (e.isDirectory()) walk(p);
      else out.push(posix(relative(dir, p)));
    }
  };
  walk(dir);
  return out.sort();
}

/** The descriptor of the state files in a checkout (rmf.econ.state/1). */
export function describeState(checkout, { run, writtenAt, root, manifestSha256 }) {
  const files = listFiles(join(checkout, STATE_DIR)).filter((f) => f !== DESCRIPTOR).map((f) => {
    const bytes = readFileSync(join(checkout, STATE_DIR, f));
    return { path: `${STATE_DIR}/${f}`, sha256: sha(bytes), bytes: bytes.length };
  });
  return { schema: 'rmf.econ.state/1', run, written_at: writtenAt, root, manifest_sha256: manifestSha256, files };
}

/**
 * Verifies a checkout's state (20.3). A checkout with no `state/` at all is a fresh store. Any
 * other shape that does not match STATE.json exactly is refused: the run must not start.
 */
export function verifyState(checkout) {
  const dir = join(checkout, STATE_DIR);
  if (!existsSync(dir)) return { ok: true, fresh: true, problems: [], descriptor: null };
  const problems = [];
  let descriptor = null;
  try {
    descriptor = JSON.parse(readFileSync(join(dir, DESCRIPTOR), 'utf8'));
  } catch {
    return { ok: false, fresh: false, problems: ['state/STATE.json is missing or not JSON'], descriptor: null };
  }
  if (descriptor.schema !== 'rmf.econ.state/1' || !Array.isArray(descriptor.files) || validate(schemaNamed('state'), descriptor).length) return { ok: false, fresh: false, problems: ['state/STATE.json is not an rmf.econ.state/1 descriptor'], descriptor };
  const listed = new Map(descriptor.files.map((f) => [f.path, f]));
  const present = listFiles(dir).filter((f) => f !== DESCRIPTOR).map((f) => `${STATE_DIR}/${f}`);
  for (const p of present) if (!listed.has(p)) problems.push(`${p} is not listed in STATE.json`);
  for (const [p, f] of listed) {
    const full = join(checkout, p);
    if (!existsSync(full)) {
      problems.push(`${p} is missing`);
      continue;
    }
    const bytes = readFileSync(full);
    if (sha(bytes) !== f.sha256 || bytes.length !== f.bytes) problems.push(`${p} does not match STATE.json`);
    else if (p.endsWith('.json')) {
      let value;
      try {
        value = JSON.parse(bytes.toString('utf8'));
      } catch {
        problems.push(`${p} is not JSON`);
        continue;
      }
      const schema = stateSchema(p);
      const errors = schema ? validate(schema, value) : [];
      if (errors.length) problems.push(`${p} does not satisfy its schema (${errors.slice(0, 3).join('; ')})`);
    }
  }
  if (descriptor.root !== null && !existsSync(join(checkout, descriptor.root, 'archive'))) problems.push(`${descriptor.root} named by STATE.json is missing`);
  else if (descriptor.root !== null && descriptor.manifest_sha256 !== null) {
    // The root's manifest is the one the descriptor recorded: a changed or lost manifest fails closed.
    const manifest = join(checkout, descriptor.root, 'live', 'manifest.json');
    if (!existsSync(manifest) || sha(readFileSync(manifest)) !== descriptor.manifest_sha256) problems.push(`${descriptor.root}/live/manifest.json does not match STATE.json`);
  }
  return { ok: problems.length === 0, fresh: false, problems, descriptor };
}

/**
 * Restores a pipeline root from a verified checkout: the newest unpublished root it names, then
 * the state files. Refuses an unverified checkout.
 */
export function importState(checkout, root) {
  const v = verifyState(checkout);
  if (!v.ok) throw new Error(`state store refused: ${v.problems.join('; ')}`);
  if (v.fresh) return v;
  if (v.descriptor.root !== null) {
    for (const part of ['live', 'archive']) {
      const from = join(checkout, v.descriptor.root, part);
      if (existsSync(from)) cpSync(from, join(root, part), { recursive: true });
    }
  }
  const stateDir = join(root, 'archive', 'state');
  rmSync(stateDir, { recursive: true, force: true });
  mkdirSync(stateDir, { recursive: true });
  for (const f of v.descriptor.files) cpSync(join(checkout, f.path), join(stateDir, f.path.slice(STATE_DIR.length + 1)));
  return v;
}

/**
 * Writes a run's root into a checkout (20.1, 20.3): `unpublished/<run>/` (live, archive and
 * the saved responses), then the state files, then STATE.json last.
 */
export function exportState(root, checkout, { run, writtenAt, responses = null }) {
  if (!RUN_ID.test(run)) throw new Error('state store: the run id must be 1 to 80 letters, digits, dots, hyphens or underscores');
  const target = join(checkout, UNPUBLISHED_DIR, run);
  if (existsSync(target)) throw new Error(`state store: ${UNPUBLISHED_DIR}/${run} exists already`);
  for (const part of ['live', 'archive']) if (existsSync(join(root, part))) cpSync(join(root, part), join(target, part), { recursive: true });
  if (responses && existsSync(responses)) cpSync(responses, join(target, 'responses'), { recursive: true });
  const stateDir = join(checkout, STATE_DIR);
  rmSync(stateDir, { recursive: true, force: true });
  mkdirSync(stateDir, { recursive: true });
  const from = join(root, 'archive', 'state');
  if (existsSync(from)) cpSync(from, stateDir, { recursive: true });
  const manifest = join(root, 'live', 'manifest.json');
  const manifestSha256 = existsSync(manifest) && statSync(manifest).isFile() ? sha(readFileSync(manifest)) : null;
  const descriptor = describeState(checkout, { run, writtenAt, root: `${UNPUBLISHED_DIR}/${run}`, manifestSha256 });
  writeFileSync(join(stateDir, DESCRIPTOR), canonicalJson(descriptor));
  return descriptor;
}

/**
 * Commits the checkout and pushes it without force (20.3). If the remote branch moved since the
 * checkout was made (a competing writer), git refuses the push and so does this function.
 */
export function commitAndPush(checkout, { message, branch = 'main', remote = 'origin', git = 'git' }) {
  const run = (args) => spawnSync(git, ['-C', checkout, ...args], { encoding: 'utf8' });
  const add = run(['add', '-A']);
  if (add.status !== 0) return { ok: false, step: 'add', detail: add.stderr };
  const commit = run(['commit', '-q', '-m', message]);
  if (commit.status !== 0) return { ok: false, step: 'commit', detail: commit.stderr || commit.stdout };
  // Never forced: a push that is not a fast-forward of the remote branch is refused (fail closed).
  const push = run(['push', '-q', remote, `HEAD:${branch}`]);
  if (push.status !== 0) return { ok: false, step: 'push', detail: push.stderr };
  return { ok: true, commit: run(['rev-parse', 'HEAD']).stdout.trim() };
}
