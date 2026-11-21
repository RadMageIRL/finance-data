// DATA_CONVENTIONS v0.8 22.8 (Stage D P3): the site build's data steps as the Finance pages.yml runs
// them from a pinned finance-data checkout: the site runs and their deployed flags, the release
// placed into dist/data/econ with its verified file list, and the site input rule (I48).
import { mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/bin/site-data.mjs';
const { placeRelease, siteInputRefusal, siteRuns } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/lib/publication.mjs';
const { artifactSummary, nextLog, releaseAssets, releaseTag } = m2 as unknown as Loose;
import * as m3 from '../../../pipeline/lib/site-build.mjs';
const { deployedState, runName } = m3 as unknown as Loose;
import * as m4 from '../../../pipeline/lib/canonical.mjs';
const { canonicalJson, sha256Hex } = m4 as unknown as Loose;

const dirs: string[] = [];
const newDir = () => {
  const d = mkdtempSync(join(tmpdir(), 'rmf-site-'));
  dirs.push(d);
  return d;
};
afterAll(() => {
  for (const d of dirs) rmSync(d, { recursive: true, force: true });
});
const S1 = '20261124T150000Z';
const tree = () => new Map<string, string>([['manifest.json', canonicalJson({ snapshot: { id: S1 } })], ['objects/effr/2026/0123456789abcdef.json', '{"x":1}']]);
const dataset = () => ({ snapshot: S1, manifest_sha256: sha256Hex(tree().get('manifest.json')) });

describe('the site build data steps (22.8)', () => {
  it('lists the completed site runs oldest first, deployed only when the deploy job succeeded', async () => {
    const tag = releaseTag(S1, 5, 1);
    const fetchImpl = async (url: string) => {
      const json = (v: unknown) => ({ ok: true, status: 200, json: async () => v });
      if (url.includes('/actions/workflows/pages.yml/runs')) return json({ workflow_runs: [
        { id: 3, display_title: runName('site', dataset(), tag), conclusion: 'success', created_at: '2026-11-24T16:00:00Z' },
        { id: 2, display_title: runName('data', dataset(), tag), conclusion: 'success', created_at: '2026-11-24T15:10:00Z' },
        { id: 1, display_title: 'Deploy to GitHub Pages', conclusion: 'success', created_at: '2026-11-18T16:07:01Z' },
      ] });
      if (url.includes('/actions/runs/3/jobs')) return json({ jobs: [{ name: 'build', conclusion: 'success' }, { name: 'deploy', conclusion: 'skipped' }] });
      if (url.includes('/actions/runs/2/jobs')) return json({ jobs: [{ name: 'build', conclusion: 'success' }, { name: 'deploy', conclusion: 'success' }] });
      return { ok: false, status: 404 };
    };
    const runs = await siteRuns({ token: 't', siteRepository: 'RadMageIRL/finance', fetchImpl });
    expect(runs.map((r: Loose) => [r.name.split(' ')[1], r.deployed])).toEqual([['data', true], ['site', false]]);
    expect(deployedState(runs)).toEqual({ dataset: dataset(), release: tag, mode: 'data' });
  });

  it('places a checked release into dist/data/econ with its verified list, and refuses a mismatched one', () => {
    const files = tree();
    const log = nextLog(null, null, { published_at: '2026-11-24T15:00:00Z', run: 'pub-5-1', trigger: 'manual', dataset: dataset(), release: releaseTag(S1, 5, 1), site_commit: '0'.repeat(40), artifact: artifactSummary(files), checker: { pass: 1, fail: 0, skip: 0 } });
    const assets = releaseAssets(new Map([...files, ['status/deployments.json', canonicalJson(log)]]));
    const assetsDir = newDir();
    for (const [n, b] of Object.entries(assets)) writeFileSync(join(assetsDir, n), b as Buffer);
    const dist = join(newDir(), 'dist');
    const out = join(dist, 'data', 'econ');
    const verifiedFile = join(newDir(), 'econ-verified.json');
    const list = placeRelease({ assetsDir, ...dataset(), out, verifiedFile });
    expect(list.map((x: Loose) => x.path)).toEqual(['manifest.json', 'objects/effr/2026/0123456789abcdef.json', 'status/deployments.json']);
    expect(readFileSync(join(out, 'objects/effr/2026/0123456789abcdef.json'), 'utf8')).toBe('{"x":1}');
    expect(JSON.parse(readFileSync(verifiedFile, 'utf8'))).toEqual(list);
    expect(existsSync(join(dist, 'data', 'econ-verified.json'))).toBe(false);
    const other = join(newDir(), 'econ');
    expect(() => placeRelease({ assetsDir, snapshot: S1, manifest_sha256: 'f'.repeat(64), out: other, verifiedFile })).toThrow(/input manifest SHA-256/);
    expect(existsSync(other)).toBe(false);
  });

  it('refuses a site run whose inputs do not name the deployed dataset and release (I48)', () => {
    const tag = releaseTag(S1, 5, 1);
    const deployed = { dataset: dataset(), release: tag };
    expect(siteInputRefusal({ deployed, snapshot: S1, manifest_sha256: dataset().manifest_sha256, tag })).toBeNull();
    expect(siteInputRefusal({ deployed, snapshot: '', manifest_sha256: '', tag: '' })).toMatch(/must name the deployed dataset/);
    expect(siteInputRefusal({ deployed: { dataset: null, release: null }, snapshot: '', manifest_sha256: '', tag: '' })).toBeNull();
  });
});
