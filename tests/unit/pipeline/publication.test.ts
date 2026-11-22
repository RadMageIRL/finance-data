// DATA_CONVENTIONS v0.8 section 22 (Stage D P3): the artifact and its deterministic archive, the
// release assets, the deployment log as a chain of releases, verified pairs, the no-op rule,
// D5.5, the allow-list, and the site build's data steps: input patterns, the deployed state,
// compare-and-swap, the monotonic rule with its rollback exception, and the release check.
import { gzipSync } from 'node:zlib';
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/lib/publication.mjs';
const { artifactArchive, artifactSha256, artifactSummary, deployedDataset, disallowedPaths, fixPost, neverPublicWithdrawn, nextLog, nothingToPublish, readArtifactArchive, reasonProblems, releaseAssets, releaseTag, sha256Sums, verifiedPairs } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/lib/site-build.mjs';
const { checkRelease, currentText, deployRefusal, deployedState, inputRefusal, runName } = m2 as unknown as Loose;
import * as m5 from '../../../pipeline/bin/publish.mjs';
const { assemble, COMPAT_DATASET, COMPAT_LINE, dispatchInputs, isCompatDataset, release, releaseBody, reportPlan, v3At } = m5 as unknown as Loose;
import * as m6 from '../../../pipeline/bin/state-scenario.mjs';
const { runStateScenario } = m6 as unknown as Loose;
import * as m4 from '../../../pipeline/bin/publication-facts.mjs';
const { readCollectFacts } = m4 as unknown as Loose;
import * as m3 from '../../../pipeline/lib/canonical.mjs';
const { canonicalJson, sha256Hex } = m3 as unknown as Loose;

const S1 = '20261124T150000Z';
const S2 = '20261124T161700Z';
const H1 = 'a'.repeat(64);
const H2 = 'b'.repeat(64);
const COMMIT = '0'.repeat(40);
const manifestOf = (id: string) => canonicalJson({ schema: 'rmf.econ.manifest/4', snapshot: { id, path: `snapshots/${id}.json`, sha256: 'c'.repeat(64) } });
const tree = (id: string, extra: Record<string, string> = {}) => new Map<string, string>(Object.entries({
  'manifest.json': manifestOf(id),
  [`snapshots/${id}.json`]: canonicalJson({ id, holds: [], frozen: [] }),
  'objects/effr/2026/0123456789abcdef.json': '{"x":1}',
  'status/publications.json': canonicalJson({ publications: [{ snapshot: id, events: [{ status: 'active', reason: null }] }] }),
  ...extra,
}));
const entry = (snapshot: string, sha: string, run: number, trigger = 'manual', files?: Map<string, string>) => ({
  published_at: '2026-11-24T15:00:00Z', run: `pub-${run}-1`, trigger, dataset: { snapshot, manifest_sha256: sha }, release: releaseTag(snapshot, run, 1),
  site_commit: COMMIT, artifact: files ? artifactSummary(files) : { files: 0, bytes: 0, sha256: 'd'.repeat(64) }, checker: { pass: 10, fail: 0, skip: 0 },
});
const withLog = (files: Map<string, string>, log: Loose) => new Map([...files, ['status/deployments.json', canonicalJson(log)]]);

describe('the artifact and its archive (22.3)', () => {
  it('is deterministic, holds econ/ names in byte order, has gzip mtime 0 and OS 255, and reads back exactly', () => {
    const files = tree(S1);
    const a = artifactArchive(files);
    expect(artifactArchive(tree(S1)).equals(a)).toBe(true);
    expect([a[0], a[1], a[3], a.readUInt32LE(4), a[9]]).toEqual([0x1f, 0x8b, 0, 0, 255]);
    const back = readArtifactArchive(a);
    expect([...back.keys()]).toEqual([...files.keys()].sort());
    for (const [p, t] of files) expect(back.get(p).toString('utf8')).toBe(t);
  });

  it('refuses a link, a name outside econ/ and a path with ..', () => {
    const header = (name: string, type: string, body = '') => {
      const h = Buffer.alloc(512, 0);
      h.write(name, 0);
      h.write('0000644\0', 100);
      h.write(`${body.length.toString(8).padStart(11, '0')}\0`, 124);
      h.write(type, 156);
      h.write('ustar\0', 257);
      const pad = Buffer.alloc((512 - (body.length % 512)) % 512, 0);
      return Buffer.concat([h, Buffer.from(body), pad]);
    };
    const pack = (...parts: Buffer[]) => gzipSync(Buffer.concat([...parts, Buffer.alloc(1024, 0)]));
    expect(() => readArtifactArchive(pack(header('econ/a.json', '2')))).toThrow(/not a regular file/);
    expect(() => readArtifactArchive(pack(header('other/a.json', '0', 'x')))).toThrow(/outside econ/);
    expect(() => readArtifactArchive(pack(header('econ/../a.json', '0', 'x')))).toThrow(/outside econ|clean path/);
    expect(() => readArtifactArchive(pack(header('econ/a.json', '0', 'x'), header('econ/a.json', '0', 'y')))).toThrow(/appears twice/);
  });

  it('computes the artifact SHA-256 without the deployment log', () => {
    const files = tree(S1);
    expect(artifactSha256(withLog(files, { deployments: [] }))).toBe(artifactSha256(files));
    const lines = [...files.keys()].sort().map((p) => `${sha256Hex(files.get(p))}  ${p}\n`).join('');
    expect(artifactSha256(files)).toBe(sha256Hex(lines));
  });

  it('lists every path outside the allow-list, and every refused reason', () => {
    expect(disallowedPaths(tree(S1, { 'state/x.json': '{}', 'NOTICE.txt': 'n\n', 'responses/ab/x.bin': 'b' }))).toEqual(['responses/ab/x.bin', 'state/x.json']);
    const bad = tree(S1, { 'status/publications.json': canonicalJson({ publications: [{ snapshot: S1, events: [{ status: 'withdrawn', reason: 'mail a@b.co' }] }] }) });
    expect(reasonProblems(bad)).toEqual([['status/publications.json', 'reason', 'an email address']]);
  });
});

describe('releases and the deployment log (22.4)', () => {
  it('adds the compatibility line to the release body for the dataset of 22.2 amendment 1 only (both values together)', () => {
    const info = (dataset: Loose) => ({ dataset, artifact: { files: 3, bytes: 10, sha256: 'e'.repeat(64) }, mode: 'manual', site_commit: COMMIT });
    const plain = releaseBody(info({ snapshot: S1, manifest_sha256: H1 }));
    const NL = String.fromCharCode(10);
    expect(plain.split(NL)).toHaveLength(3);
    expect(plain).not.toContain('Compatibility exception');
    const compat = releaseBody(info({ ...COMPAT_DATASET }));
    expect(compat.split(NL)).toEqual([...plain.replaceAll(S1, COMPAT_DATASET.snapshot).replaceAll(H1, COMPAT_DATASET.manifest_sha256).split(NL), COMPAT_LINE]);
    expect(COMPAT_LINE).toBe('Compatibility exception: this dataset is the accepted rmf.econ.manifest/3 dataset published unchanged, without rule files, under a one-time owner authorization of 2026-11-22 (data conventions v0.8 amendment 1). Every other dataset needs a manifest/4.');
    expect(COMPAT_DATASET).toEqual({ snapshot: '20261121T001752Z', manifest_sha256: '180a1991a56582e8a03813efa556d2695b3f28f7e415b763b06e499e57c1188d' });
    expect(isCompatDataset({ snapshot: COMPAT_DATASET.snapshot, manifest_sha256: H1 })).toBe(false);
    expect(isCompatDataset({ snapshot: S1, manifest_sha256: COMPAT_DATASET.manifest_sha256 })).toBe(false);
    expect(isCompatDataset(null)).toBe(false);
    expect(releaseBody(info({ snapshot: COMPAT_DATASET.snapshot, manifest_sha256: H1 }))).not.toContain('Compatibility exception');
  });

  it('chains the log: numbers continue, previous links, and the previous post is fixed only once its run completed', () => {
    const one = nextLog(null, null, entry(S1, H1, 1));
    expect(one.deployments.map((d: Loose) => [d.number, d.previous, d.verification.post])).toEqual([[1, null, null]]);
    expect(() => nextLog(one, null, entry(S2, H2, 2))).toThrow(/has not completed/);
    const two = nextLog(one, 'passed', entry(S2, H2, 2));
    expect(two.deployments.map((d: Loose) => [d.number, d.previous?.snapshot ?? null, d.verification.post])).toEqual([[1, null, 'passed'], [2, S1, null]]);
    expect(one.deployments[0].verification.post).toBeNull();
    expect(two.deployments[1].verification.checker).toEqual({ pass: 10, fail: 0, skip: 0 });
    expect('checker' in two.deployments[1]).toBe(false);
  });

  it('fixes post from the run outcomes', () => {
    expect(fixPost({ completed: false })).toBeNull();
    expect(fixPost({ completed: true, siteConclusion: 'success', verifyConclusion: 'success' })).toBe('passed');
    expect(fixPost({ completed: true, siteConclusion: 'success', verifyConclusion: 'failure' })).toBe('failed');
    expect(fixPost({ completed: true, siteConclusion: 'failure', verifyConclusion: 'success' })).toBe('not-deployed');
    expect(fixPost({ completed: true, siteConclusion: null, verifyConclusion: null })).toBe('not-deployed');
  });

  it('finds the deployed dataset and the verified pairs, and the no-op rule', () => {
    let log = nextLog(null, null, entry(S1, H1, 1));
    log = nextLog(log, 'passed', entry(S2, H2, 2));
    log = nextLog(log, 'failed', entry(S1, H1, 3, 'redeploy'));
    expect(deployedDataset(log).dataset.snapshot).toBe(S2);
    expect(deployedDataset(log).post).toBe('failed');
    expect(verifiedPairs(log).map((p: Loose) => p.dataset.snapshot)).toEqual([S1]);
    expect(nothingToPublish(log, { snapshot: S2, manifest_sha256: H2 })).toBe(false);
    const passed = nextLog(nextLog(null, null, entry(S1, H1, 1)), 'passed', entry(S2, H2, 2));
    expect(nothingToPublish(passed, { snapshot: S1, manifest_sha256: H1 })).toBe(true);
    expect(nothingToPublish(passed, { snapshot: S1, manifest_sha256: H2 })).toBe(false);
  });

  it('writes the four assets with SHA256SUMS in name order', () => {
    const files = withLog(tree(S1), nextLog(null, null, entry(S1, H1, 1, 'manual', tree(S1))));
    const a = releaseAssets(files);
    expect(Object.keys(a).sort()).toEqual(['SHA256SUMS', 'artifact.tar.gz', 'deployments.json', 'manifest.json']);
    expect(a.SHA256SUMS.toString('utf8').split('\n').filter(Boolean).map((l: string) => l.split('  ')[1])).toEqual(['artifact.tar.gz', 'deployments.json', 'manifest.json']);
    expect(a.SHA256SUMS.toString('utf8')).toBe(sha256Sums({ 'artifact.tar.gz': a['artifact.tar.gz'], 'deployments.json': a['deployments.json'], 'manifest.json': a['manifest.json'] }));
  });

  it('refuses publication while the window holds a withdrawn snapshot that no deployed release contained (D5.5)', () => {
    const files = tree(S2, { [`snapshots/${S1}.json`]: '{}' });
    const pubs = { publications: [{ snapshot: S1, events: [{ status: 'active' }, { status: 'withdrawn' }] }, { snapshot: S2, events: [{ status: 'active' }] }] };
    expect(neverPublicWithdrawn(files, pubs, new Set())).toEqual([S1]);
    expect(neverPublicWithdrawn(files, pubs, new Set([S1]))).toEqual([]);
  });
});

describe('the site build data steps (22.8)', () => {
  it('validates the inputs against their patterns', () => {
    expect(inputRefusal({ mode: 'data', tag: releaseTag(S1, 5, 1), snapshot: S1, manifest_sha256: H1, site_commit: COMMIT, expected_current: 'none' })).toBeNull();
    expect(inputRefusal({ mode: 'data', tag: `data-${S1}-j1-1`, snapshot: S1, manifest_sha256: H1, site_commit: COMMIT, expected_current: 'none' })).toMatch(/release tag/);
    expect(inputRefusal({ mode: 'data', tag: releaseTag(S1, 5, 1), snapshot: S1, manifest_sha256: H1, site_commit: COMMIT, expected_current: 'x' })).toMatch(/expected_current/);
    expect(inputRefusal({ mode: 'deploy-all' })).toMatch(/mode/);
  });

  it('reads the deployed state from the newest successful run that deployed', () => {
    const runs = [
      { name: runName('data', { snapshot: S1, manifest_sha256: H1 }, releaseTag(S1, 1, 1)), conclusion: 'success', deployed: true },
      { name: runName('data', { snapshot: S2, manifest_sha256: H2 }, releaseTag(S2, 5, 1)), conclusion: 'failure', deployed: false },
      { name: runName('site', { snapshot: S1, manifest_sha256: H1 }, releaseTag(S1, 1, 1)), conclusion: 'success', deployed: false },
    ];
    expect(deployedState(runs).dataset).toEqual({ snapshot: S1, manifest_sha256: H1 });
    expect(deployedState([...runs, { name: runName('unpublish', null, null), conclusion: 'success', deployed: true }]).dataset).toBeNull();
    expect(deployedState([]).dataset).toBeNull();
  });

  it('refuses a stale compare-and-swap, an older or equal snapshot, but allows a redeploy to a verified pair', () => {
    const d1 = { dataset: { snapshot: S1, manifest_sha256: H1 } };
    const d2 = { dataset: { snapshot: S2, manifest_sha256: H2 } };
    expect(deployRefusal({ mode: 'data', expected_current: 'none', deployed: d1, input: { snapshot: S2 } })).toMatch(/compare-and-swap/);
    expect(deployRefusal({ mode: 'data', expected_current: currentText(d1.dataset), deployed: d1, input: { snapshot: S2 } })).toBeNull();
    expect(deployRefusal({ mode: 'data', expected_current: currentText(d2.dataset), deployed: d2, input: { snapshot: S1 } })).toMatch(/not newer/);
    expect(deployRefusal({ mode: 'data', expected_current: currentText(d2.dataset), deployed: d2, input: { snapshot: S2 } })).toMatch(/not newer/);
    let log = nextLog(null, null, entry(S1, H1, 1));
    log = nextLog(log, 'passed', entry(S2, H2, 2));
    log = nextLog(log, 'failed', entry(S1, H1, 3, 'redeploy'));
    expect(deployRefusal({ mode: 'data', expected_current: currentText(d2.dataset), deployed: d2, input: { snapshot: S1 }, log })).toBeNull();
    const unverified = nextLog(nextLog(nextLog(null, null, entry(S1, H1, 1)), 'failed', entry(S2, H2, 2)), 'passed', entry(S1, H1, 3, 'redeploy'));
    expect(deployRefusal({ mode: 'data', expected_current: currentText(d2.dataset), deployed: d2, input: { snapshot: S1 }, log: unverified })).toMatch(/not newer/);
    expect(deployRefusal({ mode: 'site', expected_current: currentText(d2.dataset), deployed: d2 })).toBeNull();
  });

  it('checks a release: SHA256SUMS, the manifest hash and snapshot, and the artifact SHA-256 against the log', () => {
    const files = tree(S1);
    const log = nextLog(null, null, entry(S1, sha256Hex(files.get('manifest.json')), 1, 'manual', files));
    const assets = releaseAssets(withLog(files, log));
    const sha = sha256Hex(files.get('manifest.json'));
    const ok = checkRelease(assets, { snapshot: S1, manifest_sha256: sha });
    expect([...ok.files.keys()].sort()).toEqual([...withLog(files, log).keys()].sort());
    expect(() => checkRelease({ ...assets, SHA256SUMS: Buffer.from('x') }, { snapshot: S1, manifest_sha256: sha })).toThrow(/SHA256SUMS/);
    expect(() => checkRelease(assets, { snapshot: S1, manifest_sha256: H1 })).toThrow(/input manifest SHA-256/);
    expect(() => checkRelease(assets, { snapshot: S2, manifest_sha256: sha })).toThrow(/input snapshot/);
    const { 'manifest.json': _m, ...three } = assets;
    expect(() => checkRelease(three, { snapshot: S1, manifest_sha256: sha })).toThrow(/missing/);
    // A changed file inside the archive: the artifact SHA-256 no longer matches the log entry.
    const changed = new Map(withLog(files, log));
    changed.set('objects/effr/2026/0123456789abcdef.json', '{"x":2}');
    const tampered = releaseAssets(changed);
    expect(() => checkRelease(tampered, { snapshot: S1, manifest_sha256: sha })).toThrow(/artifact SHA-256/);
  });
});

describe('the collection run reads the publication facts (22.4)', () => {
  const A = releaseTag(S1, 11, 1);
  const B = releaseTag(S2, 22, 1);
  const logA = nextLog(null, null, entry(S1, H1, 11));
  const logB = nextLog(logA, 'passed', entry(S2, H2, 22));
  const fake = (over: Loose = {}) => {
    const seen: string[] = [];
    const fetchImpl = async (url: string) => {
      seen.push(url);
      const json = (v: unknown) => ({ ok: true, status: 200, json: async () => v });
      if (url.includes('/finance-data/releases?')) return json(over.releases ?? [
        { tag_name: B, draft: false, created_at: '2026-11-24T17:00:00Z', assets: [{ name: 'deployments.json', url: 'https://api.github.com/assets/b' }] },
        { tag_name: A, draft: false, created_at: '2026-11-24T15:00:00Z', assets: [{ name: 'deployments.json', url: 'https://api.github.com/assets/a' }] },
        { tag_name: 'v0.2.0', draft: false, created_at: '2026-11-25T00:00:00Z', assets: [] },
      ]);
      if (url === 'https://api.github.com/assets/b') return { ok: true, status: 200, arrayBuffer: async () => Buffer.from(canonicalJson(logB)) };
      if (url.endsWith('/actions/runs/22')) return over.run === 'refuse' ? { ok: false, status: 403 } : json({ status: over.status ?? 'completed' });
      if (url.includes('/actions/runs/22/jobs')) return json({ jobs: [{ name: 'assemble', conclusion: 'success' }, { name: 'verify', conclusion: over.verify ?? 'success' }] });
      if (url.includes('/finance/actions/workflows/pages.yml/runs')) return json({ workflow_runs: [{ display_title: runName('data', { snapshot: S2, manifest_sha256: H2 }, B), status: 'completed', conclusion: over.site ?? 'success' }] });
      return { ok: false, status: 500 };
    };
    return { seen, fetchImpl };
  };
  const read = (f: Loose) => readCollectFacts({ token: 't', repository: 'RadMageIRL/finance-data', siteRepository: 'RadMageIRL/finance', fetchImpl: f.fetchImpl });

  it('takes the newest data release by creation time with its run outcomes', async () => {
    const f = await read(fake());
    expect(f.newestLog).toEqual(logB);
    expect(f.newestRun).toEqual({ completed: true, siteConclusion: 'success', verifyConclusion: 'success' });
    expect(fixPost(f.newestRun)).toBe('passed');
    expect(fixPost((await read(fake({ verify: 'failure' }))).newestRun)).toBe('failed');
    expect(fixPost((await read(fake({ site: 'failure' }))).newestRun)).toBe('not-deployed');
  });

  it('reports a run in progress, nothing without a data release, and throws on a refused read', async () => {
    expect((await read(fake({ status: 'in_progress' }))).newestRun).toEqual({ completed: false });
    expect(await read(fake({ releases: [{ tag_name: 'v0.2.0', draft: false, created_at: '2026-11-25T00:00:00Z', assets: [] }] }))).toEqual({ newestLog: null, newestRun: null });
    await expect(read(fake({ run: 'refuse' }))).rejects.toThrow(/answered 403/);
  });
});

describe('the publication workflow jobs (22.6)', () => {
  const dirs: string[] = [];
  const newDir = () => {
    const d = mkdtempSync(join(tmpdir(), 'rmf-pub-'));
    dirs.push(d);
    return d;
  };
  afterAll(() => {
    for (const d of dirs) rmSync(d, { recursive: true, force: true });
  });
  const passing = () => ({ pass: 7, fail: 0, skip: 0 });
  let storeDir = '';
  let accepted: Loose = {};
  beforeAll(async () => {
    const g = join(newDir(), 'g');
    await runStateScenario(g, { validate: () => ({ pass: 1, fail: 0, skip: 0 }), upTo: 4 });
    storeDir = join(g, 'store');
    accepted = JSON.parse(readFileSync(join(storeDir, 'state', 'STATE.json'), 'utf8')).accepted;
  }, 240_000);
  const run = (more: Loose = {}) => assemble({ storeDir, mode: 'manual', input: accepted, runId: 501, attempt: 1, now: '2026-11-24T15:00:00Z', facts: null, siteCommit: 'a'.repeat(40), deployed: null, validateState: passing, validatePublication: passing, outDir: newDir(), ...more });

  it('assembles the accepted window with the log, the four assets and the release facts, after V2b and V2c', () => {
    const seen: string[] = [];
    const out = newDir();
    const r = run({ outDir: out, validatePublication: (tree: string, s: string) => { seen.push(tree, s); return passing(); } });
    expect(r.outcome).toBe('assembled');
    expect(r.tag).toBe(releaseTag(accepted.snapshot, 501, 1));
    expect(r.log.deployments).toHaveLength(1);
    expect(r.log.deployments[0]).toMatchObject({ number: 1, trigger: 'manual', previous: null, site_commit: 'a'.repeat(40), verification: { checker: { pass: 7, fail: 0, skip: 0 }, post: null } });
    expect(seen).toEqual([join(out, 'econ'), storeDir]);
    expect(readdirSync(join(out, 'assets')).sort()).toEqual(['SHA256SUMS', 'artifact.tar.gz', 'deployments.json', 'manifest.json']);
    expect(readFileSync(join(out, 'econ', 'manifest.json'))).toEqual(readFileSync(join(storeDir, 'root', 'live', 'manifest.json')));
    expect(JSON.parse(readFileSync(join(out, 'release.json'), 'utf8')).expected_current).toBe('none');
    const ok = checkRelease(Object.fromEntries(readdirSync(join(out, 'assets')).map((n: string) => [n, readFileSync(join(out, 'assets', n))])), accepted);
    expect(ok.log.deployments[0].release).toBe(r.tag);
  });

  it('refuses inputs that are not the accepted identifier, an unfinished previous run, an unverified redeploy target and a failing V2c; ends without releasing when nothing is new', () => {
    expect(run({ input: { ...accepted, manifest_sha256: 'f'.repeat(64) } }).outcome).toBe('refused-gate');
    const first = run();
    const facts = (run_: Loose) => ({ newestLog: structuredClone(first.log), newestRun: run_ });
    expect(run({ facts: facts({ completed: false }) }).outcome).toBe('refused-gate');
    expect(run({ facts: facts({ completed: true, siteConclusion: 'success', verifyConclusion: 'success' }) }).outcome).toBe('no-op');
    const next = run({ facts: facts({ completed: true, siteConclusion: 'failure', verifyConclusion: null }) });
    expect(next.outcome).toBe('assembled');
    expect(next.log.deployments.map((d: Loose) => [d.number, d.verification.post])).toEqual([[1, 'not-deployed'], [2, null]]);
    expect(run({ mode: 'redeploy', target: { dataset: accepted, site_commit: 'a'.repeat(40) }, facts: facts({ completed: true, siteConclusion: 'failure', verifyConclusion: null }) }).outcome).toBe('refused-gate');
    expect(run({ validatePublication: () => ({ pass: 1, fail: 2, skip: 0, failures: ['FAIL P1 x'] }) })).toMatchObject({ outcome: 'refused-v2', problems: ['V2c: 2 failure(s)', 'FAIL P1 x'] });
    expect(run({ validateState: () => ({ pass: 1, fail: 1, skip: 0, failures: [] }) }).outcome).toBe('refused-v2');
  });

  it('deletes stale drafts, uploads exactly the four assets to a draft, then publishes it', async () => {
    const calls: string[] = [];
    const api = {
      listReleases: async () => [{ id: 1, draft: true, tag_name: 'data-x' }, { id: 2, draft: false, tag_name: 'data-y' }, { id: 3, draft: true, tag_name: 'v0.2.0' }],
      deleteRelease: async (id: number) => calls.push(`delete ${id}`),
      createDraft: async (o: Loose) => { calls.push(`draft ${o.tag}`); return { id: 9 }; },
      uploadAsset: async (id: number, name: string) => calls.push(`upload ${id} ${name}`),
      publish: async (id: number) => calls.push(`publish ${id}`),
    };
    const info = { tag: 'data-20261124T150000Z-501-1', mode: 'manual', dataset: accepted, site_commit: 'a'.repeat(40), artifact: { files: 1, bytes: 1, sha256: 'b'.repeat(64) } };
    await release({ api, info, assets: { SHA256SUMS: 'x', 'artifact.tar.gz': 'x', 'deployments.json': 'x', 'manifest.json': 'x' } });
    expect(calls).toEqual(['delete 1', 'draft data-20261124T150000Z-501-1', 'upload 9 SHA256SUMS', 'upload 9 artifact.tar.gz', 'upload 9 deployments.json', 'upload 9 manifest.json', 'publish 9']);
    expect(dispatchInputs(info)).toEqual({ mode: 'data', tag: info.tag, snapshot: accepted.snapshot, manifest_sha256: accepted.manifest_sha256, site_commit: 'a'.repeat(40), expected_current: undefined, dry_run: 'false' });
  });

  it('verifies the deployed files at an address (V3) and plans the report keys', async () => {
    const live = join(storeDir, 'root', 'live');
    const get = async (url: string) => {
      const rel = url.replace('https://example.test/econ/', '');
      return existsSync(join(live, rel)) ? { ok: true, bytes: readFileSync(join(live, rel)) } : { ok: false };
    };
    expect(await v3At({ base: 'https://example.test/econ/', dataset: accepted, get, sleep: async () => {} })).toEqual({ passed: true, problems: [] });
    const wrong = await v3At({ base: 'https://example.test/econ/', dataset: { ...accepted, manifest_sha256: 'f'.repeat(64) }, get, sleep: async () => {}, attempts: 2 });
    expect(wrong.passed).toBe(false);
    const issue = (n: number, key: string) => ({ number: n, created_at: `2026-11-24T0${n}:00:00Z`, title: `x [${key}]`, body: `x\n\nrmf-alert-key: ${key}` });
    const keys = (plan: Loose[]) => plan.map((a: Loose) => [a.action, a.key]);
    expect(keys(reportPlan({ openIssues: [], openKeys: new Set(), result: { failedAfterGates: true, v3: null, person: true }, now: 'T' }))).toEqual([['create', 'publish-failed']]);
    expect(keys(reportPlan({ openIssues: [issue(1, 'publish-failed')], openKeys: new Set(['publish-failed']), result: { failedAfterGates: false, v3: 'passed', person: true }, now: 'T' }))).toEqual([['close', 'publish-failed']]);
    expect(keys(reportPlan({ openIssues: [], openKeys: new Set(), result: { failedAfterGates: false, v3: 'failed', person: true }, now: 'T' }))).toEqual([['create', 'publication-verify-failed']]);
    // The automatic redeploy passing does not close publication-verify-failed; a person's run does.
    const open = [issue(2, 'publication-verify-failed')];
    expect(keys(reportPlan({ openIssues: open, openKeys: new Set(['publication-verify-failed']), result: { failedAfterGates: false, v3: 'passed', person: false }, now: 'T' })).filter(([a]: string[]) => a === 'close')).toEqual([]);
    expect(keys(reportPlan({ openIssues: open, openKeys: new Set(['publication-verify-failed']), result: { failedAfterGates: false, v3: 'passed', person: true }, now: 'T' }))).toEqual([['close', 'publication-verify-failed']]);
  });
});
