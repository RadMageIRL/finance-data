// The pipeline root on disk (DATA_CONVENTIONS section 17.1 and 17.5): the live window, the
// append-only archive, the state files and the staging folder. Every write goes to a temporary
// name in the target folder and is renamed into place, and the manifest is always written last.
import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { canonicalJson, sha256Hex } from './canonical.mjs';

export function paths(root) {
  return {
    root,
    live: join(root, 'live'),
    files: join(root, 'archive', 'files'),
    manifests: join(root, 'archive', 'manifests'),
    holds: join(root, 'archive', 'holds'),
    state: join(root, 'archive', 'state'),
    records: join(root, 'archive', 'state', 'run-records'),
    staging: join(root, 'staging'),
  };
}

export function readText(path) {
  return existsSync(path) ? readFileSync(path, 'utf8') : null;
}

export function writeAtomic(path, text) {
  mkdirSync(dirname(path), { recursive: true });
  const tmp = `${path}.tmp`;
  writeFileSync(tmp, text);
  renameSync(tmp, path);
}

/** Every file under a folder as sorted relative paths with forward slashes. */
export function listFiles(dir) {
  const out = [];
  const walk = (d, rel) => {
    if (!existsSync(d)) return;
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const r = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) walk(join(d, e.name), r);
      else out.push(r);
    }
  };
  walk(dir, '');
  return out.sort();
}

export const fileBytes = (path) => statSync(path).size;

export function readState(p, name, fallback) {
  const text = readText(join(p.state, name));
  return text === null ? fallback : JSON.parse(text);
}

export function writeState(p, name, value) {
  writeAtomic(join(p.state, name), canonicalJson(value));
}

/** A namespace file from the archive first, then the live tree; null when in neither. */
export function reader(p) {
  return (path) => readText(join(p.files, path)) ?? readText(join(p.live, path));
}

function verified(text, sha256, what) {
  if (text === null) throw new Error(`${what} is missing`);
  if (sha256Hex(text) !== sha256) throw new Error(`${what} does not match its hash`);
  return text;
}

/** The observations a snapshot names for one series, each object verified by its hash. */
export function observationsOf(snapshot, seriesId, read) {
  const out = [];
  for (const o of snapshot.series[seriesId].objects) out.push(...JSON.parse(verified(read(o.path), o.sha256, o.path)).observations);
  return out;
}

/**
 * The published state: the snapshot the live manifest names, verified, and every series'
 * observations. With no live manifest nothing is published yet.
 */
export function loadPublished(p, registry) {
  const manifestText = readText(join(p.live, 'manifest.json'));
  const read = reader(p);
  if (manifestText === null) return { manifest: null, snapshot: null, observations: Object.fromEntries(registry.series.map((s) => [s.id, []])) };
  const manifest = JSON.parse(manifestText);
  const snapshot = JSON.parse(verified(read(manifest.snapshot.path), manifest.snapshot.sha256, manifest.snapshot.path));
  const observations = Object.fromEntries(registry.series.map((s) => [s.id, snapshot.series[s.id] ? observationsOf(snapshot, s.id, read) : []]));
  return { manifest, snapshot, observations };
}

/** Every archived snapshot by id, and every archived manifest oldest first. */
export function archiveIndex(p) {
  const snapshots = {};
  for (const f of listFiles(join(p.files, 'snapshots'))) snapshots[f.replace(/\.json$/, '')] = JSON.parse(readFileSync(join(p.files, 'snapshots', f), 'utf8'));
  const manifests = listFiles(p.manifests).map((f) => JSON.parse(readFileSync(join(p.manifests, f), 'utf8')));
  return { snapshots, manifests };
}

/** Removes leftover staging folders of runs that died; returns how many there were. */
export function clearStaging(p) {
  if (!existsSync(p.staging)) return 0;
  const n = readdirSync(p.staging).length;
  rmSync(p.staging, { recursive: true, force: true });
  return n;
}

/** Writes the candidate files of a run under staging/<run id>/ (namespace and hold paths). */
export function writeStaging(p, runId, staged, stagedHolds) {
  const dir = join(p.staging, runId);
  for (const [path, text] of staged) writeAtomic(join(dir, 'files', path), text);
  for (const [path, text] of stagedHolds) writeAtomic(join(dir, path), text);
}

/**
 * Atomic publication (17.5): archive first, then the live immutable files, then the run list,
 * then the manifest last. `die` (tests only) names a point at which the process is simulated
 * to die: 'after-archive', 'before-manifest' or 'after-manifest' (before the state files).
 */
export function publish(p, { staged, stagedHolds, manifestText, generatedAt, die = null }) {
  let added = 0;
  const archive = (path, text) => {
    const old = readText(path);
    if (old !== null) {
      if (old !== text) throw new Error(`archive: ${path} exists with different bytes`);
      return;
    }
    writeAtomic(path, text);
    added += Buffer.byteLength(text, 'utf8');
  };
  // Live only, never archived: the manifest, `status/`, and from v0.8 `NOTICE.txt` (22.9).
  const liveOnly = (path) => path === 'NOTICE.txt' || path.startsWith('status/');
  const mutable = (path) => path === 'manifest.json' || liveOnly(path);
  for (const [path, text] of staged) if (!mutable(path)) archive(join(p.files, path), text);
  for (const [path, text] of stagedHolds) archive(join(p.root, 'archive', path), text);
  if (manifestText !== null) archive(join(p.manifests, `${generatedAt.replace(/[-:]/g, '')}.json`), manifestText);
  if (die === 'after-archive') throw new Error('simulated death after the archive was written');
  for (const [path, text] of staged) if (!mutable(path)) writeAtomic(join(p.live, path), text);
  for (const [path, text] of staged) if (liveOnly(path)) writeAtomic(join(p.live, path), text);
  if (die === 'before-manifest') throw new Error('simulated death before the manifest was written');
  if (manifestText !== null) writeAtomic(join(p.live, 'manifest.json'), manifestText);
  if (die === 'after-manifest') throw new Error('simulated death after the manifest was written');
  return added;
}

/** Copies a namespace file from the archive into the live tree if it is not there. */
export function ensureLive(p, path, sha256 = null) {
  const live = join(p.live, path);
  if (existsSync(live)) return false;
  const text = readText(join(p.files, path));
  if (text === null) throw new Error(`restore: ${path} is not in the archive`);
  if (sha256 !== null && sha256Hex(text) !== sha256) throw new Error(`restore: ${path} does not match its hash`);
  writeAtomic(live, text);
  return true;
}

export function removeLive(p, path) {
  rmSync(join(p.live, path), { force: true });
}

/** The newest 100 run records, newest first (14.1), as the runs file's value. */
export function runsFile(records) {
  const sorted = [...records].sort((a, b) => (a.started_at > b.started_at ? -1 : a.started_at < b.started_at ? 1 : a.id > b.id ? -1 : 1));
  return { schema: 'rmf.econ.runs/2', runs: sorted.slice(0, 100) };
}

export function allRunRecords(p) {
  return listFiles(p.records).map((f) => JSON.parse(readFileSync(join(p.records, f), 'utf8')));
}
