// Publication of the accepted dataset (DATA_CONVENTIONS 22, v0.8, Stage D): the artifact, its
// deterministic archive, the release assets, the deployment log as a chain of releases, verified
// pairs, the no-op rule and D5.5. Pure functions over bytes and parsed values: no network, no
// git; the workflow and the scenario give them the files they read.
import { gzipSync, gunzipSync } from 'node:zlib';
import { canonicalJson, sha256Hex } from './canonical.mjs';
import { textRefusal } from './alerts.mjs';

const enc = new TextEncoder();
const asBytes = (v) => (typeof v === 'string' ? Buffer.from(enc.encode(v)) : Buffer.from(v));

/** Paths an artifact may hold (22.3), relative to `econ/`. */
export function allowedPath(path) {
  return path === 'manifest.json'
    || path === 'NOTICE.txt'
    || path === 'status/runs.json'
    || path === 'status/publications.json'
    || path === 'status/deployments.json'
    || /^(objects|series|snapshots|revisions|registry|notices)\//.test(path);
}

const byPath = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
/** Byte order of UTF-8 paths (ids and paths are ASCII, so code unit order is byte order). */
const sortedPaths = (files) => [...files.keys()].sort(byPath);

/** The artifact SHA-256 (22.3): every file but status/deployments.json, `<sha256>  <path>` lines in path order. */
export function artifactSha256(files) {
  const lines = sortedPaths(files).filter((p) => p !== 'status/deployments.json').map((p) => `${sha256Hex(asBytes(files.get(p)))}  ${p}\n`);
  return sha256Hex(lines.join(''));
}

/** Files and bytes of the artifact without the deployment log (22.4 `artifact`). */
export function artifactSummary(files) {
  let bytes = 0;
  let count = 0;
  for (const p of sortedPaths(files)) {
    if (p === 'status/deployments.json') continue;
    count += 1;
    bytes += asBytes(files.get(p)).length;
  }
  return { files: count, bytes, sha256: artifactSha256(files) };
}

// ---- POSIX ustar, deterministic (22.3) ----

const octal = (n, width) => `${n.toString(8).padStart(width - 1, '0')}\0`;
function ustarHeader(name, size) {
  const h = Buffer.alloc(512, 0);
  let prefix = '';
  let base = name;
  if (Buffer.byteLength(name) > 100) {
    const cut = name.lastIndexOf('/', 155);
    if (cut <= 0 || Buffer.byteLength(name.slice(cut + 1)) > 100) throw new Error(`archive: the name ${name} is too long for ustar`);
    prefix = name.slice(0, cut);
    base = name.slice(cut + 1);
  }
  h.write(base, 0, 100, 'utf8');
  h.write('0000644\0', 100, 8, 'ascii');
  h.write('0000000\0', 108, 8, 'ascii');
  h.write('0000000\0', 116, 8, 'ascii');
  h.write(octal(size, 12), 124, 12, 'ascii');
  h.write(octal(0, 12), 136, 12, 'ascii');
  h.write('        ', 148, 8, 'ascii');
  h.write('0', 156, 1, 'ascii');
  h.write('ustar\0', 257, 6, 'ascii');
  h.write('00', 263, 2, 'ascii');
  h.write(prefix, 345, 155, 'utf8');
  let sum = 0;
  for (const b of h) sum += b;
  h.write(`${sum.toString(8).padStart(6, '0')}\0 `, 148, 8, 'ascii');
  return h;
}

/** The deterministic archive of a tree (22.3): ustar, `econ/<path>` in byte order, gzip level 9, OS byte 255. */
export function artifactArchive(files) {
  const parts = [];
  for (const p of sortedPaths(files)) {
    const body = asBytes(files.get(p));
    parts.push(ustarHeader(`econ/${p}`, body.length), body, Buffer.alloc((512 - (body.length % 512)) % 512, 0));
  }
  parts.push(Buffer.alloc(1024, 0));
  const gz = gzipSync(Buffer.concat(parts), { level: 9 });
  // RFC 1952: no file name (flags 0), modification time 0, OS 255 (unknown). The CRC covers the
  // uncompressed data only, so setting the header bytes keeps the stream valid.
  gz[3] = 0;
  gz.writeUInt32LE(0, 4);
  gz[9] = 255;
  return gz;
}

/**
 * Reads an artifact archive safely (22.8): regular files only, every name under `econ/`, no `..`,
 * no absolute path, no duplicate. Returns Map(path relative to econ/ -> Buffer). Throws on any refusal.
 */
export function readArtifactArchive(bytes) {
  const data = gunzipSync(Buffer.from(bytes));
  const out = new Map();
  let off = 0;
  while (off + 512 <= data.length) {
    const h = data.subarray(off, off + 512);
    if (h.every((b) => b === 0)) break;
    const str = (a, n) => h.subarray(a, a + n).toString('utf8').replace(/\0.*$/s, '');
    const name = (str(345, 155) ? `${str(345, 155)}/` : '') + str(0, 100);
    const type = String.fromCharCode(h[156]);
    const size = parseInt(str(124, 12).trim() || '0', 8);
    if (type !== '0' && type !== '\0') throw new Error(`archive: ${name} is not a regular file`);
    if (!name.startsWith('econ/') || name.includes('/../') || name.endsWith('/..') || name.includes('\\') || name === 'econ/') throw new Error(`archive: ${name} is outside econ/`);
    const rel = name.slice(5);
    if (rel.split('/').some((s) => s === '' || s === '.' || s === '..')) throw new Error(`archive: ${name} is not a clean path`);
    if (out.has(rel)) throw new Error(`archive: ${name} appears twice`);
    out.set(rel, Buffer.from(data.subarray(off + 512, off + 512 + size)));
    off += 512 + Math.ceil(size / 512) * 512;
  }
  return out;
}

// ---- Release assets (22.4) ----

/** `SHA256SUMS`: one line per asset, in name order. */
export function sha256Sums(assets) {
  return Object.keys(assets).sort(byPath).map((n) => `${sha256Hex(asBytes(assets[n]))}  ${n}\n`).join('');
}

/** The four assets of a release from the artifact tree (which holds status/deployments.json). */
export function releaseAssets(files) {
  const assets = {
    'artifact.tar.gz': artifactArchive(files),
    'deployments.json': asBytes(files.get('status/deployments.json')),
    'manifest.json': asBytes(files.get('manifest.json')),
  };
  return { ...assets, SHA256SUMS: Buffer.from(sha256Sums(assets), 'utf8') };
}

/** The release tag (22.4). */
export const releaseTag = (snapshot, runId, attempt) => `data-${snapshot}-${runId}-${attempt}`;

// ---- The deployment log as a chain of releases (22.4) ----

export const emptyLog = () => ({ schema: 'rmf.econ.deployments/1', deployments: [] });

/**
 * The `post` of a release's entry from its run's outcomes (22.4): `passed` when the site run
 * succeeded and V3 passed, `failed` when the site run succeeded and V3 did not, `not-deployed`
 * otherwise. `facts`: { completed, siteConclusion (or null), verifyConclusion (or null) }.
 * Returns null while the run has not completed (I33).
 */
export function fixPost(facts) {
  if (!facts || !facts.completed) return null;
  if (facts.siteConclusion === 'success') return facts.verifyConclusion === 'success' ? 'passed' : 'failed';
  return 'not-deployed';
}

/** The log of a new release: the previous release's log with its last `post` fixed, plus one entry. */
export function nextLog(previousLog, previousPost, entry) {
  const log = previousLog ? structuredClone(previousLog) : emptyLog();
  const list = log.deployments;
  if (list.length) {
    const last = list[list.length - 1];
    if (last.verification.post === null) {
      if (previousPost === null) throw new Error('publication refused: the previous release\'s run has not completed');
      last.verification.post = previousPost;
    }
  }
  const number = list.length ? list[list.length - 1].number + 1 : 1;
  const previous = list.length ? list[list.length - 1].dataset : null;
  list.push({ ...entry, number, previous, verification: { checker: entry.checker, post: null } });
  delete list[list.length - 1].checker;
  return log;
}

/**
 * The private deployment log (22.4, state/deployments.json): a copy of the newest release's log
 * with that release's last `post` fixed when its run has completed (I33), or empty with no release.
 */
export function privateLogCopy(newestLog, newestPost) {
  if (!newestLog) return emptyLog();
  const log = structuredClone(newestLog);
  const last = log.deployments[log.deployments.length - 1];
  if (last && last.verification.post === null && newestPost !== null) last.verification.post = newestPost;
  return log;
}

// ---- The order of releases (22.4, amendment 3 to v0.8, owner decision P115) ----

const releaseKey = (r) => {
  const t = typeof r?.published_at === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(r.published_at) ? Date.parse(r.published_at) : NaN;
  if (!Number.isFinite(t)) throw new Error(`the release ${r?.tag_name} has no valid published_at`);
  if (!Number.isSafeInteger(r.id) || r.id <= 0) throw new Error(`the release ${r?.tag_name} has no valid numeric id`);
  return [t, r.id];
};

/**
 * Orders GitHub releases oldest first: by `published_at`, ties broken by the numeric release id.
 * Never by `created_at`, which GitHub sets to the date of the tagged commit, so releases tagged on
 * one commit share it (the 2026-11-28 04:37Z duplicate release). Throws on a release without a
 * valid `published_at` or id, so a reader fails closed instead of guessing.
 */
export function compareReleases(a, b) {
  const [ta, ia] = releaseKey(a);
  const [tb, ib] = releaseKey(b);
  return ta - tb || ia - ib;
}

/** The newest of the given published releases (22.4), or null when there is none. */
export function newestRelease(releases) {
  const list = [...releases];
  for (const r of list) releaseKey(r);
  return list.length ? list.sort(compareReleases)[list.length - 1] : null;
}

/** Null when a release's own log ends with its own entry (22.4), else the problem. */
export function ownLogProblem(tag, log) {
  const last = log?.deployments?.at(-1);
  return last && last.release === tag ? null : `the log of the newest release ${tag} does not end with its own entry (it ends with ${last ? last.release : 'nothing'})`;
}

/** The dataset of the newest entry whose `post` is `passed` or `failed` (22.4), or null. */
export function deployedDataset(log) {
  const e = [...(log?.deployments ?? [])].reverse().find((d) => d.verification.post === 'passed' || d.verification.post === 'failed');
  return e ? { dataset: e.dataset, post: e.verification.post, entry: e } : null;
}

/** The verified pairs (22.4): (site_commit, dataset) of entries with `post` `passed`, newest first. */
export const verifiedPairs = (log) => [...(log?.deployments ?? [])].reverse().filter((d) => d.verification.post === 'passed').map((d) => ({ site_commit: d.site_commit, dataset: d.dataset, release: d.release, number: d.number }));

const sameDataset = (a, b) => a && b && a.snapshot === b.snapshot && a.manifest_sha256 === b.manifest_sha256;
export { sameDataset };

/** Manual and timer end without releasing when the accepted dataset is the deployed one and its `post` is `passed` (22.6). */
export function nothingToPublish(log, accepted) {
  const d = deployedDataset(log);
  return Boolean(d && d.post === 'passed' && sameDataset(d.dataset, accepted));
}

// ---- V2 pre-checks the pipeline makes itself (the independent checker repeats them, 22.5) ----

/** Every reason in the artifact that the reason check refuses (22.3, D6): [path, field, rule]. */
export function reasonProblems(files) {
  const out = [];
  const check = (path, field, text) => {
    if (text === null || text === undefined) return;
    const why = textRefusal(text);
    if (why) out.push([path, field, why]);
  };
  for (const [path, bytes] of files) {
    if (path.startsWith('snapshots/')) {
      const s = JSON.parse(asBytes(bytes).toString('utf8'));
      for (const h of s.holds ?? []) check(path, 'holds[].reason', h.reason);
      for (const f of s.frozen ?? []) check(path, 'frozen[].reason', f.reason);
    } else if (path === 'manifest.json') {
      const m = JSON.parse(asBytes(bytes).toString('utf8'));
      if (m.rollback) check(path, 'rollback.reason', m.rollback.reason);
    } else if (path === 'status/publications.json') {
      for (const p of JSON.parse(asBytes(bytes).toString('utf8')).publications) for (const e of p.events) check(path, 'reason', e.reason);
    }
  }
  return out;
}

/**
 * D5.5 (22.3): the withdrawn snapshots in the window that have not been public. `publications`
 * is the publication record; `publicSnapshots` the set of snapshot ids that an earlier deployed
 * release contained.
 */
export function neverPublicWithdrawn(files, publications, publicSnapshots) {
  const inWindow = new Set([...files.keys()].filter((p) => p.startsWith('snapshots/')).map((p) => p.slice(10, -5)));
  const withdrawn = publications.publications.filter((e) => e.events.some((ev) => ev.status === 'withdrawn')).map((e) => e.snapshot);
  return withdrawn.filter((id) => inWindow.has(id) && !publicSnapshots.has(id)).sort();
}

/** The hours after which an accepted dataset not yet deployed raises `publication-behind` (17.8, PROPOSED). */
export const BEHIND_HOURS = 12;

/**
 * `publication-behind` (17.8, v0.8): the warning when the accepted dataset has been newer than the
 * deployed one for more than BEHIND_HOURS, or null. `publications` is the publication record; the
 * acceptance time is the `at` of the accepted snapshot's newest `active` event.
 */
export function publicationBehind({ log, accepted, publications, now }) {
  const d = deployedDataset(log);
  if (!d || sameDataset(d.dataset, accepted)) return null;
  const e = publications.publications.find((p) => p.snapshot === accepted.snapshot);
  const active = [...(e?.events ?? [])].reverse().find((ev) => ev.status === 'active');
  if (!active) return null;
  const hours = (Date.parse(now) - Date.parse(active.at)) / 3_600_000;
  if (hours <= BEHIND_HOURS) return null;
  return { key: 'publication-behind', severity: 'warning', title: 'Publication is behind the accepted data', body: `The accepted snapshot ${accepted.snapshot} has not been deployed for ${Math.floor(hours)} hours; the deployed snapshot is ${d.dataset.snapshot}.` };
}

/** The paths of an artifact the allow-list refuses (22.3). */
export const disallowedPaths = (files) => sortedPaths(files).filter((p) => !allowedPath(p));

const ASSET_NAMES = ['SHA256SUMS', 'artifact.tar.gz', 'deployments.json', 'manifest.json'];

/**
 * The watcher's release history check (22.7, 21.9), from public data only. `releases`: every
 * published `data-*` release, each { tag, assetNames, log }; `newest`: { tag, assets: { name:
 * bytes } } of the release whose log is longest; `deployedLog`: the deployed
 * status/deployments.json as fetched, or null. Returns the problems found (empty: none).
 */
export function releaseHistoryProblems({ releases, newest, deployedLog }) {
  const out = [];
  if (!releases.length) return out;
  const byTag = new Map(releases.map((r) => [r.tag, r]));
  const top = byTag.get(newest.tag);
  if (!top) return [`the newest release ${newest.tag} is not listed`];
  const list = top.log.deployments;
  for (const d of list) {
    const r = byTag.get(d.release);
    if (!r) out.push(`release ${d.release} of entry ${d.number} does not exist`);
    else if ([...r.assetNames].sort().join() !== ASSET_NAMES.join()) out.push(`release ${d.release} does not hold exactly its four assets`);
  }
  const named = new Set(list.map((d) => d.release));
  for (const r of releases) if (!named.has(r.tag)) out.push(`release ${r.tag} is not named by the newest log`);
  const { SHA256SUMS: sums, ...rest } = newest.assets;
  if (!sums || Buffer.from(sums).toString('utf8') !== sha256Sums(rest)) out.push(`the SHA256SUMS of ${newest.tag} does not match its assets`);
  for (const r of releases) {
    const k = list.findIndex((d) => d.release === r.tag);
    if (k < 0) continue;
    const want = structuredClone(list.slice(0, k + 1));
    want[k].verification.post = null;
    if (canonicalJson(r.log.deployments) !== canonicalJson(want)) out.push(`the log of ${r.tag} is not the newest log up to its own entry`);
  }
  if (deployedLog) {
    for (const d of deployedLog.deployments) if (!byTag.has(d.release)) out.push(`the deployed log names ${d.release}, which does not exist`);
    const last = deployedLog.deployments[deployedLog.deployments.length - 1];
    if (last && last.number > list[list.length - 1].number) out.push(`the deployed log reaches entry ${last.number}, beyond the newest release`);
  }
  return out;
}

/** The canonical text of a deployment log. */
export const logText = (log) => canonicalJson(log);
