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
  const named = { 'alerts.json': 'alerts', 'deployments.json': 'deployments', 'pins.json': 'pins', 'publications.json': 'publications', 'review-queue.json': 'review-queue' }[rel];
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

// ---------------------------------------------------------------------------------------------
// The v0.7 layout (DATA_CONVENTIONS 21.1, 21.2): one root updated in place under `root/`,
// content-addressed response bodies under `responses/`, one collection record per run under
// `runs/`, and `.gitattributes` so that git never converts a byte.

export const GITATTRIBUTES = '* -text\n';
export const ROOT_DIR = 'root';
export const RUNS_DIR = 'runs';
export const RESPONSES_DIR = 'responses';
const ACCEPTED = 'accepted.json';
const LAYOUT_ENTRIES = new Set(['.git', '.gitattributes', STATE_DIR, ROOT_DIR, RUNS_DIR, RESPONSES_DIR, UNPUBLISHED_DIR]);

/** The content address of a response body (21.2). */
export const bodyPath = (sha256) => `${RESPONSES_DIR}/${sha256.slice(0, 2)}/${sha256}.bin`;

/** Which layout a checkout holds: 'fresh' (no state), 'v0.6' (state/1), 'v0.7' (state/2) or 'unknown'. */
export function storeLayout(checkout) {
  const file = join(checkout, STATE_DIR, DESCRIPTOR);
  if (!existsSync(join(checkout, STATE_DIR))) return 'fresh';
  try {
    const schema = JSON.parse(readFileSync(file, 'utf8')).schema;
    return schema === 'rmf.econ.state/1' ? 'v0.6' : schema === 'rmf.econ.state/2' ? 'v0.7' : 'unknown';
  } catch {
    return 'unknown';
  }
}

/** The text for a file that does not match its recorded hash; names converted line endings (21.2). */
function mismatchText(path, bytes, sha256, what) {
  // Undo a CRLF conversion byte for byte (latin1 keeps every byte as one character).
  const lf = Buffer.from(bytes.toString('latin1').split('\r\n').join('\n'), 'latin1');
  return lf.length !== bytes.length && sha(lf) === sha256 ? `${path} does not match ${what}: line endings converted (clone with core.autocrlf=false)` : `${path} does not match ${what}`;
}

const stateSchemaV2 = (path) => (path === `${STATE_DIR}/${ACCEPTED}` ? schemaNamed('accepted') : stateSchema(path));

/**
 * Verifies a v0.7 checkout (21.2). Refuses on: `.gitattributes` missing or not its 8 bytes;
 * STATE.json missing, unreadable, not canonical or not state/2; a state file missing, unlisted,
 * changed or breaking its schema; no `accepted.json`; the root manifest not matching
 * `manifest_sha256`; `accepted` not naming that manifest's snapshot and hash.
 */
export function verifyStateV2(checkout) {
  const problems = [];
  const ga = join(checkout, '.gitattributes');
  if (!existsSync(ga)) problems.push('.gitattributes is missing');
  else if (!readFileSync(ga).equals(Buffer.from(GITATTRIBUTES))) problems.push(mismatchText('.gitattributes', readFileSync(ga), sha(Buffer.from(GITATTRIBUTES)), 'its 8 bytes'));
  const dir = join(checkout, STATE_DIR);
  let text;
  let descriptor;
  try {
    text = readFileSync(join(dir, DESCRIPTOR), 'utf8');
    descriptor = JSON.parse(text);
  } catch {
    return { ok: false, problems: [...problems, 'state/STATE.json is missing or not JSON'], descriptor: null };
  }
  if (validate(schemaNamed('state-v2'), descriptor).length) return { ok: false, problems: [...problems, 'state/STATE.json is not an rmf.econ.state/2 descriptor'], descriptor };
  if (canonicalJson(descriptor) !== text) problems.push('state/STATE.json is not canonical JSON');
  const listed = new Map(descriptor.files.map((f) => [f.path, f]));
  const paths = descriptor.files.map((f) => f.path);
  if (paths.some((p, i) => i > 0 && paths[i - 1] >= p)) problems.push('state/STATE.json files are not sorted and unique');
  for (const p of listFiles(dir).filter((f) => f !== DESCRIPTOR).map((f) => `${STATE_DIR}/${f}`)) if (!listed.has(p)) problems.push(`${p} is not listed in STATE.json`);
  if (!listed.has(`${STATE_DIR}/${ACCEPTED}`)) problems.push('state/accepted.json is missing: the store was not promoted (21.2)');
  for (const [p, f] of listed) {
    const full = join(checkout, p);
    if (!existsSync(full)) {
      problems.push(`${p} is missing`);
      continue;
    }
    const bytes = readFileSync(full);
    if (sha(bytes) !== f.sha256 || bytes.length !== f.bytes) {
      problems.push(mismatchText(p, bytes, f.sha256, 'STATE.json'));
      continue;
    }
    let value;
    try {
      value = JSON.parse(bytes.toString('utf8'));
    } catch {
      problems.push(`${p} is not JSON`);
      continue;
    }
    const schema = stateSchemaV2(p);
    const errors = schema ? validate(schema, value) : [];
    if (errors.length) problems.push(`${p} does not satisfy its schema (${errors.slice(0, 3).join('; ')})`);
  }
  const manifestFile = join(checkout, ROOT_DIR, 'live', 'manifest.json');
  if (descriptor.manifest_sha256 === null) {
    if (existsSync(manifestFile)) problems.push('root/live/manifest.json exists but STATE.json names none');
  } else if (!existsSync(manifestFile)) problems.push('root/live/manifest.json named by STATE.json is missing');
  else {
    const bytes = readFileSync(manifestFile);
    if (sha(bytes) !== descriptor.manifest_sha256) problems.push(mismatchText('root/live/manifest.json', bytes, descriptor.manifest_sha256, 'STATE.json'));
    else {
      const manifest = JSON.parse(bytes.toString('utf8'));
      const a = descriptor.accepted;
      if (!a || a.snapshot !== manifest.snapshot.id || a.manifest_sha256 !== descriptor.manifest_sha256) problems.push('STATE.json accepted does not name the root manifest and its snapshot');
      // Every file the accepted manifest names matches its hash (21.2): a converted checkout of a
      // CSV segment is caught here, before any run starts.
      const named = [manifest.snapshot, ...Object.values(manifest.series).flatMap((s) => [...(s.objects ?? []), ...(s.csvs ?? []), ...(s.revisions ?? [])])];
      for (const ref of named) {
        const file = join(checkout, ROOT_DIR, 'live', ref.path);
        if (!existsSync(file)) problems.push(`root/live/${ref.path} named by the manifest is missing`);
        else {
          const b = readFileSync(file);
          if (sha(b) !== ref.sha256) problems.push(mismatchText(`root/live/${ref.path}`, b, ref.sha256, 'the manifest'));
        }
      }
    }
  }
  return { ok: problems.length === 0, problems, descriptor };
}

/** Restores a working root from a verified v0.7 checkout: root/live, root/archive, then the state files. */
export function importStateV2(checkout, root) {
  const v = verifyStateV2(checkout);
  if (!v.ok) throw new Error(`state store refused: ${v.problems.join('; ')}`);
  for (const part of ['live', 'archive']) {
    const from = join(checkout, ROOT_DIR, part);
    if (existsSync(from)) cpSync(from, join(root, part), { recursive: true });
  }
  const stateDir = join(root, 'archive', 'state');
  rmSync(stateDir, { recursive: true, force: true });
  mkdirSync(stateDir, { recursive: true });
  for (const f of v.descriptor.files) {
    const to = join(stateDir, f.path.slice(STATE_DIR.length + 1));
    mkdirSync(join(to, '..'), { recursive: true });
    cpSync(join(checkout, f.path), to);
  }
  return v;
}

/** Every file path under a checkout's `root/` and `responses/` (posix, relative to the checkout). */
function storedPaths(checkout) {
  return new Set([ROOT_DIR, RESPONSES_DIR].flatMap((d) => listFiles(join(checkout, d)).map((f) => `${d}/${f}`)));
}

/** The ET month (YYYY-MM) of a time. America/New_York, as every period of the conventions. */
function etMonth(iso) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit' }).formatToParts(new Date(iso));
  return `${parts.find((p) => p.type === 'year').value}-${parts.find((p) => p.type === 'month').value}`;
}

/** The bytes the collection records of an ET month added (21.4), `exceptRun` left out. */
export function monthAddedBytes(checkout, month, exceptRun = null) {
  let total = 0;
  for (const f of listFiles(join(checkout, RUNS_DIR))) {
    if (!f.endsWith('.json') || f === `${exceptRun}.json`) continue;
    const r = JSON.parse(readFileSync(join(checkout, RUNS_DIR, f), 'utf8'));
    if (etMonth(r.started_at) === month) total += r.added.bytes;
  }
  return total;
}

/** The storage budget alert of 21.4 for a run at `now`: earlier records of its ET month. */
export function storeBudgetAlert(checkout, now) {
  const month = etMonth(now);
  const bytes = monthAddedBytes(checkout, month);
  if (bytes <= 50_000_000) return null;
  const severity = bytes > 100_000_000 ? 'critical' : 'warning';
  return { key: 'budget:state-store', severity, title: 'State store growth over budget', body: `Runs of ${month} added ${bytes} bytes to the state store, over the ${severity === 'critical' ? '100000000' : '50000000'} byte level. Nothing is deleted; a person decides.` };
}

/** Writes a canonical JSON file with LF only (21.2). */
const writeCanonical = (file, value) => {
  mkdirSync(join(file, '..'), { recursive: true });
  writeFileSync(file, canonicalJson(value));
};

/** Writes the response bodies a run received at their content addresses, each once (21.2). */
function writeBodies(checkout, bodies) {
  for (const b of bodies) {
    if (sha(b.bytes) !== b.sha256) throw new Error(`state store: a response body does not match its record (${b.sha256})`);
    const file = join(checkout, bodyPath(b.sha256));
    if (existsSync(file)) continue;
    mkdirSync(join(file, '..'), { recursive: true });
    writeFileSync(file, b.bytes);
  }
}

/** The state descriptor (state/2) of a checkout as it is now (21.2). */
function describeV2(checkout, { run, writtenAt }) {
  const files = listFiles(join(checkout, STATE_DIR)).filter((f) => f !== DESCRIPTOR).map((f) => {
    const bytes = readFileSync(join(checkout, STATE_DIR, f));
    return { path: `${STATE_DIR}/${f}`, sha256: sha(bytes), bytes: bytes.length };
  });
  const manifestFile = join(checkout, ROOT_DIR, 'live', 'manifest.json');
  let manifestSha256 = null;
  let accepted = null;
  if (existsSync(manifestFile)) {
    const bytes = readFileSync(manifestFile);
    manifestSha256 = sha(bytes);
    accepted = { snapshot: JSON.parse(bytes.toString('utf8')).snapshot.id, manifest_sha256: manifestSha256 };
  }
  return { schema: 'rmf.econ.state/2', run, written_at: writtenAt, root: ROOT_DIR, manifest_sha256: manifestSha256, accepted, files };
}

/**
 * Writes a working root back into a v0.7 checkout (21.2), with the run's collection record
 * (21.4): the response bodies, `root/` replaced by the working root's live/ and archive/ (no
 * staging, no archive/state), the record with `added` and `month_added_bytes`, the state files,
 * `.gitattributes`, and STATE.json last. `record` is the collection record without those fields.
 */
export function exportStateV2(root, checkout, { run, writtenAt, record, bodies = [] }) {
  if (!RUN_ID.test(run)) throw new Error('state store: the run id must be 1 to 80 letters, digits, dots, hyphens or underscores');
  const recordFile = join(checkout, RUNS_DIR, `${run}.json`);
  if (existsSync(recordFile)) throw new Error(`state store: ${RUNS_DIR}/${run}.json exists already`);
  const before = storedPaths(checkout);
  writeBodies(checkout, bodies);
  rmSync(join(checkout, ROOT_DIR), { recursive: true, force: true });
  if (existsSync(join(root, 'live'))) cpSync(join(root, 'live'), join(checkout, ROOT_DIR, 'live'), { recursive: true });
  if (existsSync(join(root, 'archive'))) cpSync(join(root, 'archive'), join(checkout, ROOT_DIR, 'archive'), { recursive: true, filter: (src) => posix(relative(join(root, 'archive'), src)).split('/')[0] !== 'state' });
  const added = [...storedPaths(checkout)].filter((p) => !before.has(p));
  const addedBytes = added.reduce((n, p) => n + statSync(join(checkout, p)).size, 0);
  const month = etMonth(record.started_at);
  const full = { ...record, added: { files: added.length, bytes: addedBytes }, month_added_bytes: monthAddedBytes(checkout, month, run) + addedBytes };
  if (validate(schemaNamed('collection'), full).length) throw new Error(`state store: the collection record is invalid (${validate(schemaNamed('collection'), full).slice(0, 3).join('; ')})`);
  writeCanonical(recordFile, full);
  const stateDir = join(checkout, STATE_DIR);
  rmSync(stateDir, { recursive: true, force: true });
  mkdirSync(stateDir, { recursive: true });
  const from = join(root, 'archive', 'state');
  if (existsSync(from)) cpSync(from, stateDir, { recursive: true });
  writeFileSync(join(checkout, '.gitattributes'), GITATTRIBUTES);
  // STATE.json is written last (21.2): its time is not before the record's end.
  const descriptor = describeV2(checkout, { run, writtenAt: writtenAt < full.ended_at ? full.ended_at : writtenAt });
  writeFileSync(join(stateDir, DESCRIPTOR), canonicalJson(descriptor));
  return { descriptor, record: full };
}

/** The promotion record of 21.1 (`rmf.econ.accepted/1`). */
export function acceptedRecord({ snapshot, manifestSha256, storeCommit, named, checker, verifiedAt, decision, promotedBy, run, now }) {
  return { schema: 'rmf.econ.accepted/1', dataset: { snapshot, manifest_sha256: manifestSha256 }, source: { store_commit: storeCommit, root: named, run: named.slice(UNPUBLISHED_DIR.length + 1) }, verification: { checker: { mode: 'live', pass: checker.pass, fail: checker.fail, skip: checker.skip }, state: 'ok', at: verifiedAt }, decision, promoted_at: now, promoted_by: promotedBy, run };
}

/**
 * The baseline promotion (21.1), once: from a verified v0.6 store whose named root's manifest
 * has the reviewed SHA-256, after the independent checker passed on that root in live mode.
 * Writes root/ (byte copies), the Stage B bodies at their content addresses, state/accepted.json,
 * the promotion's collection record, `.gitattributes`, and STATE.json (state/2) last. The Stage B
 * folder stays as it is. `record` is the promotion's collection record without `added`.
 */
export function promoteStore(checkout, { manifestSha256, storeCommit, checker, verifiedAt, decision, promotedBy, run, now, record, writtenAt = now }) {
  if (existsSync(join(checkout, STATE_DIR, ACCEPTED))) throw new Error('promotion refused: the store was promoted already');
  const v = verifyState(checkout);
  if (!v.ok || v.fresh) throw new Error(`promotion refused: ${v.fresh ? 'the store is empty' : v.problems.join('; ')}`);
  const named = v.descriptor.root;
  if (named === null) throw new Error('promotion refused: STATE.json names no root');
  const manifest = join(checkout, named, 'live', 'manifest.json');
  if (sha(readFileSync(manifest)) !== manifestSha256) throw new Error('promotion refused: the root manifest is not the reviewed one');
  if (!checker || checker.fail !== 0 || !(checker.pass > 0)) throw new Error('promotion refused: the independent checker did not pass on the root');
  const before = storedPaths(checkout);
  // The Stage B bodies, by their content addresses (the Stage B folder is not changed).
  const responses = join(checkout, named, 'responses');
  const bodies = existsSync(responses)
    ? readdirSync(responses).filter((f) => f.endsWith('.json')).sort().map((f) => {
      const meta = JSON.parse(readFileSync(join(responses, f), 'utf8'));
      return { sha256: meta.sha256, bytes: readFileSync(join(responses, `${f.slice(0, -5)}.bin`)) };
    })
    : [];
  writeBodies(checkout, bodies);
  cpSync(join(checkout, named, 'live'), join(checkout, ROOT_DIR, 'live'), { recursive: true });
  cpSync(join(checkout, named, 'archive'), join(checkout, ROOT_DIR, 'archive'), { recursive: true, filter: (src) => posix(relative(join(checkout, named, 'archive'), src)).split('/')[0] !== 'state' });
  const snapshot = JSON.parse(readFileSync(manifest, 'utf8')).snapshot.id;
  const accepted = acceptedRecord({ snapshot, manifestSha256, storeCommit, named, checker, verifiedAt, decision, promotedBy, run, now });
  if (validate(schemaNamed('accepted'), accepted).length) throw new Error(`promotion refused: the promotion record is invalid (${validate(schemaNamed('accepted'), accepted).slice(0, 3).join('; ')})`);
  writeCanonical(join(checkout, STATE_DIR, ACCEPTED), accepted);
  const added = [...storedPaths(checkout)].filter((p) => !before.has(p));
  const addedBytes = added.reduce((n, p) => n + statSync(join(checkout, p)).size, 0);
  const full = { ...record, accepted: accepted.dataset, added: { files: added.length, bytes: addedBytes }, month_added_bytes: monthAddedBytes(checkout, etMonth(record.started_at), run) + addedBytes };
  if (validate(schemaNamed('collection'), full).length) throw new Error(`promotion refused: the collection record is invalid (${validate(schemaNamed('collection'), full).slice(0, 3).join('; ')})`);
  writeCanonical(join(checkout, RUNS_DIR, `${run}.json`), full);
  writeFileSync(join(checkout, '.gitattributes'), GITATTRIBUTES);
  // STATE.json is written last (21.2): its time is not before the record's end.
  const descriptor = describeV2(checkout, { run, writtenAt: writtenAt < record.ended_at ? record.ended_at : writtenAt });
  writeFileSync(join(checkout, STATE_DIR, DESCRIPTOR), canonicalJson(descriptor));
  return { descriptor, accepted, record: full };
}

/** Top-level entries of a checkout that the v0.7 layout does not name (21.2), for diagnostics. */
export const unexpectedEntries = (checkout) => readdirSync(checkout).filter((e) => !LAYOUT_ENTRIES.has(e)).sort();
