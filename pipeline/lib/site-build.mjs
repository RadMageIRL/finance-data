// The data steps of the site build (DATA_CONVENTIONS 22.8, v0.8): input patterns, the release
// check, the deployed state read from the site build's own run names, compare-and-swap, the
// monotonic rule and carry-forward. Pure functions; the Finance `pages.yml` and the publication
// scenario give them what they read. The independent checker repeats the tree checks (22.5).
import { sha256Hex } from './canonical.mjs';
import { artifactSha256, readArtifactArchive, sha256Sums } from './publication.mjs';

export const PATTERNS = {
  tag: /^data-\d{8}T\d{6}Z-\d+-\d+$/,
  snapshot: /^\d{8}T\d{6}Z$/,
  sha256: /^[0-9a-f]{64}$/,
  commit: /^[0-9a-f]{40}$/,
  expectedCurrent: /^(none|\d{8}T\d{6}Z:[0-9a-f]{64})$/,
};
export const MODES = ['site', 'data', 'unpublish'];

/** Why the inputs are refused (22.8), or null. */
export function inputRefusal({ mode, tag = null, snapshot = null, manifest_sha256 = null, site_commit = null, expected_current = null }) {
  if (!MODES.includes(mode)) return `mode ${mode} is not one of ${MODES.join(', ')}`;
  if (expected_current !== null && !PATTERNS.expectedCurrent.test(expected_current)) return 'expected_current is not none or <snapshot>:<sha256>';
  if (mode === 'data') {
    if (!PATTERNS.tag.test(tag ?? '')) return 'the release tag does not match its pattern';
    if (!PATTERNS.snapshot.test(snapshot ?? '')) return 'the snapshot does not match its pattern';
    if (!PATTERNS.sha256.test(manifest_sha256 ?? '')) return 'the manifest SHA-256 does not match its pattern';
    if (!PATTERNS.commit.test(site_commit ?? '')) return 'the site commit does not match its pattern';
    if (expected_current === null) return 'a data build needs expected_current';
  }
  return null;
}

/** The run name of a site build (22.8): `pages <mode> <snapshot or none> <manifest_sha256 or none> <release or none>`. */
export const runName = (mode, dataset, release) => `pages ${mode} ${dataset?.snapshot ?? 'none'} ${dataset?.manifest_sha256 ?? 'none'} ${release ?? 'none'}`;

/**
 * The deployed state (22.8): from the completed site runs, oldest first, each { name,
 * conclusion, deployed } (deployed: the deploy step ran, not skipped), the newest that concluded
 * `success` and deployed. Returns { dataset (or null for none), release (or null), mode }.
 */
export function deployedState(runs) {
  const r = [...runs].reverse().find((x) => x.conclusion === 'success' && x.deployed);
  if (!r) return { dataset: null, release: null, mode: null };
  const m = /^pages (site|data|unpublish) (\S+) (\S+) (\S+)$/.exec(r.name);
  if (!m) throw new Error(`site build: the run name "${r.name}" is not a pages run name`);
  const dataset = m[2] === 'none' ? null : { snapshot: m[2], manifest_sha256: m[3] };
  return { dataset, release: m[4] === 'none' ? null : m[4], mode: m[1] };
}

/** `expected_current` text of a dataset (22.8). */
export const currentText = (dataset) => (dataset ? `${dataset.snapshot}:${dataset.manifest_sha256}` : 'none');

/**
 * The deploy decision (22.8), read immediately before the deploy. Returns null to deploy or the
 * refusal. `newestEntry` and `log` are the release's deployment log facts (data mode).
 */
export function deployRefusal({ mode, expected_current, deployed, input = null, log = null }) {
  if (currentText(deployed.dataset) !== expected_current) return `compare-and-swap: the deployed dataset is ${currentText(deployed.dataset)}, not ${expected_current}`;
  if (mode !== 'data' || deployed.dataset === null) return null;
  if (input.snapshot > deployed.dataset.snapshot) return null;
  // The one exception: a redeploy to a known-good pair of the same log (rollback, safeguard 3).
  const list = log?.deployments ?? [];
  const newest = list[list.length - 1];
  if (newest && newest.trigger === 'redeploy') {
    const target = list.slice(0, -1).find((d) => d.verification.post === 'passed' && d.site_commit === newest.site_commit && d.dataset.snapshot === newest.dataset.snapshot && d.dataset.manifest_sha256 === newest.dataset.manifest_sha256);
    if (target) return null;
  }
  return `the input snapshot ${input.snapshot} is not newer than the deployed ${deployed.dataset.snapshot}`;
}

/**
 * The release check of a data build (22.8): the four assets, SHA256SUMS, the manifest hash and
 * snapshot, safe extraction, the artifact SHA-256 against the newest log entry. Returns { files
 * (Map of the econ tree), log } or throws with the refusal.
 */
export function checkRelease(assets, { snapshot, manifest_sha256 }) {
  const names = ['SHA256SUMS', 'artifact.tar.gz', 'deployments.json', 'manifest.json'];
  for (const n of names) if (!assets[n]) throw new Error(`release check: the asset ${n} is missing`);
  if (Object.keys(assets).sort().join() !== names.join()) throw new Error('release check: the release does not hold exactly its four assets');
  const { SHA256SUMS: sums, ...rest } = assets;
  if (Buffer.from(sums).toString('utf8') !== sha256Sums(rest)) throw new Error('release check: SHA256SUMS does not match the assets');
  if (sha256Hex(Buffer.from(assets['manifest.json'])) !== manifest_sha256) throw new Error('release check: manifest.json does not hash to the input manifest SHA-256');
  const manifest = JSON.parse(Buffer.from(assets['manifest.json']).toString('utf8'));
  if (manifest.snapshot.id !== snapshot) throw new Error('release check: manifest.json does not name the input snapshot');
  const files = readArtifactArchive(assets['artifact.tar.gz']);
  if (!files.has('manifest.json') || !files.get('manifest.json').equals(Buffer.from(assets['manifest.json']))) throw new Error('release check: the archive\'s manifest differs from the asset');
  if (!files.has('status/deployments.json') || !files.get('status/deployments.json').equals(Buffer.from(assets['deployments.json']))) throw new Error('release check: the archive\'s deployment log differs from the asset');
  const log = JSON.parse(Buffer.from(assets['deployments.json']).toString('utf8'));
  const newest = log.deployments[log.deployments.length - 1];
  if (!newest || newest.dataset.snapshot !== snapshot || newest.dataset.manifest_sha256 !== manifest_sha256) throw new Error('release check: the newest log entry is not this dataset');
  if (artifactSha256(files) !== newest.artifact.sha256) throw new Error('release check: the artifact SHA-256 differs from the log entry');
  return { files, log };
}
