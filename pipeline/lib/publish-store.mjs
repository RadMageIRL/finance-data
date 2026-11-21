// The publication run's reads of a state store checkout (DATA_CONVENTIONS 22.3 to 22.6, v0.8):
// the accepted window, a redeploy window rebuilt from the archive as it stood at the target's
// manifest (I37), the snapshots earlier deployed releases contained (D5.5), and the pipeline's own
// V2 checks. Shared by the publication workflow (pipeline/bin/publish.mjs) and the publication
// scenario. Reads only; nothing here writes the store.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { sha256Hex } from './canonical.mjs';
import * as store from './store.mjs';
import { liveWindow } from './retention.mjs';
import { disallowedPaths, neverPublicWithdrawn, reasonProblems } from './publication.mjs';

/** Every file of a folder as Map(relative path -> Buffer). */
export function readTree(dir) {
  const out = new Map();
  if (!existsSync(dir)) return out;
  for (const f of store.listFiles(dir)) out.set(f, readFileSync(join(dir, f)));
  return out;
}

/** The archived manifest whose bytes hash to `sha256`, as text, or null. */
export function archivedManifestText(storeRoot, sha256) {
  const p = store.paths(storeRoot);
  for (const f of store.listFiles(p.manifests)) {
    const t = readFileSync(join(p.manifests, f), 'utf8');
    if (sha256Hex(t) === sha256) return t;
  }
  return null;
}

/**
 * The window of an archived manifest (13, 17.6), rebuilt from `root/archive/` as it stood when
 * that manifest was written: no snapshot or manifest after its `generated_at`, its own pins (I37).
 * Returns { files (without status/), manifest, kept }.
 */
export function archivedWindow(storeRoot, manifestText) {
  const p = store.paths(storeRoot);
  const manifest = JSON.parse(manifestText);
  const index = store.archiveIndex(p);
  const asOf = manifest.generated_at;
  const snapshots = Object.fromEntries(Object.entries(index.snapshots).filter(([, s]) => s.created_at <= asOf));
  const manifests = index.manifests.filter((m) => m.generated_at <= asOf);
  const pins = { pins: manifest.pages_window.pinned.map((snapshot) => ({ snapshot })) };
  const window = liveWindow({ manifest, snapshots, manifests, pins });
  const files = new Map();
  for (const path of [...window.keep].sort()) {
    if (path === 'manifest.json' || path.startsWith('status/') || path === 'NOTICE.txt') continue;
    files.set(path, readFileSync(join(p.files, path)));
  }
  files.set('manifest.json', Buffer.from(manifestText, 'utf8'));
  if (manifest.rules) files.set('NOTICE.txt', files.get(manifest.rules.notice.path));
  return { files, manifest, kept: window.kept };
}

/**
 * The window of a publication (22.3): `root/live/` for `manual` and `timer`; for `redeploy`, the
 * target dataset's window rebuilt from the archive plus `status/runs.json` and
 * `status/publications.json` as they are now. Throws when a redeploy target has no archived manifest.
 */
export function publicationWindow(storeDir, mode, dataset) {
  const storeRoot = join(storeDir, 'root');
  if (mode !== 'redeploy') return readTree(join(storeRoot, 'live'));
  const text = archivedManifestText(storeRoot, dataset.manifest_sha256);
  if (text === null) throw new Error(`publication refused: the redeploy target ${dataset.snapshot} has no archived manifest`);
  const { files } = archivedWindow(storeRoot, text);
  for (const s of ['status/runs.json', 'status/publications.json']) files.set(s, readFileSync(join(storeRoot, 'live', s)));
  return files;
}

/** The snapshot ids that the deployed releases of a log contained (D5.5): their archived windows. */
export function publicSnapshots(storeDir, log) {
  const storeRoot = join(storeDir, 'root');
  const out = new Set();
  for (const d of log?.deployments ?? []) {
    if (d.verification.post !== 'passed' && d.verification.post !== 'failed') continue;
    const t = archivedManifestText(storeRoot, d.dataset.manifest_sha256);
    if (t) for (const id of Object.keys(archivedWindow(storeRoot, t).kept)) out.add(id);
  }
  return out;
}

/**
 * The pipeline's own V2 checks on a window (22.5; the independent checker repeats them in V2c):
 * returns null, or { outcome: 'refused-v2' | 'refused-d5', problems }.
 */
export function ownV2Refusal(storeDir, files, log) {
  const disallowed = disallowedPaths(files);
  const reasons = reasonProblems(files);
  if (disallowed.length || reasons.length) return { outcome: 'refused-v2', problems: [...disallowed.map((p) => `not allowed: ${p}`), ...reasons.map(([p, f, r]) => `${p} ${f}: ${r}`)] };
  const publications = JSON.parse(Buffer.from(files.get('status/publications.json')).toString('utf8'));
  const never = neverPublicWithdrawn(files, publications, publicSnapshots(storeDir, log));
  if (never.length) return { outcome: 'refused-d5', problems: never.map((id) => `withdrawn and never public: ${id}`) };
  return null;
}
