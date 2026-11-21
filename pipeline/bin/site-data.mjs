#!/usr/bin/env node
// The data steps of the RadMage Finance site build (DATA_CONVENTIONS 22.8, v0.8), run by the
// Finance `pages.yml` from a checkout of finance-data at a pinned commit (the data steps and the
// independent checker come from the same place; nothing is vendored into the site repository).
//
//   node pipeline/bin/site-data.mjs deployed --site-repository <owner/repo>      (prints <snapshot>:<sha256> <tag>, or none none)
//   node pipeline/bin/site-data.mjs check-inputs --site-repository <owner/repo> --mode <m> [--tag --snapshot --manifest-sha256 --site-commit --expected-current]
//   node pipeline/bin/site-data.mjs fetch --release-repository <owner/repo> --tag <tag> --snapshot <id> --manifest-sha256 <hex> --assets <dir> --out <dir> --verified <file outside dist>
//   node pipeline/bin/site-data.mjs deploy-check --site-repository <owner/repo> --mode site|data|unpublish --expected-current <none|snap:sha> [--snapshot <id>] [--assets <dir>]
//
// `deployed` and `deploy-check` read the site repository's own completed `pages.yml` runs with the
// job's token (actions: read); `fetch` downloads public release assets without authentication.
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { sha256Hex } from '../lib/canonical.mjs';
import { checkRelease, currentText, deployRefusal, deployedState, inputRefusal } from '../lib/site-build.mjs';

const ASSETS = ['SHA256SUMS', 'artifact.tar.gz', 'deployments.json', 'manifest.json'];

/**
 * The completed site runs, oldest first, as deployedState takes them: { name, conclusion, deployed }.
 * `deployed` is true when the run's `deploy` job concluded `success` (it ran and was not skipped).
 */
export async function siteRuns({ token, siteRepository, fetchImpl = fetch, limit = 30 }) {
  const headers = { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'RadMage Finance site build' };
  const get = async (path) => {
    const r = await fetchImpl(`https://api.github.com/repos/${siteRepository}${path}`, { headers });
    if (!r.ok) throw new Error(`GitHub API GET ${path.split('?')[0]} answered ${r.status}`);
    return r.json();
  };
  const runs = ((await get('/actions/workflows/pages.yml/runs?status=completed&per_page=50')).workflow_runs ?? []).filter((r) => typeof r.display_title === 'string' && r.display_title.startsWith('pages ')).slice(0, limit);
  const out = [];
  for (const r of runs) {
    let deployed = false;
    if (r.conclusion === 'success') {
      const jobs = (await get(`/actions/runs/${r.id}/jobs?per_page=50`)).jobs ?? [];
      deployed = jobs.some((j) => j.name === 'deploy' && j.conclusion === 'success');
    }
    out.push({ name: r.display_title, conclusion: r.conclusion, deployed, created_at: r.created_at });
  }
  return out.sort((a, b) => (a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : 0));
}

/** Downloads a public release's four assets without authentication into `dir`. */
export async function downloadRelease({ releaseRepository, tag, dir, fetchImpl = fetch }) {
  mkdirSync(dir, { recursive: true });
  for (const n of ASSETS) {
    const r = await fetchImpl(`https://github.com/${releaseRepository}/releases/download/${tag}/${n}`, { headers: { 'User-Agent': 'RadMage Finance site build' } });
    if (!r.ok) throw new Error(`release asset ${n} of ${tag} answered ${r.status}`);
    writeFileSync(join(dir, n), Buffer.from(await r.arrayBuffer()));
  }
}

const readAssets = (dir) => Object.fromEntries(readdirSync(dir).map((n) => [n, readFileSync(join(dir, n))]));

/**
 * The fetch step: the release check of 22.8, then the tree written to `out` (`dist/data/econ`) and
 * its verified file list (path and SHA-256, in path order) to `verifiedFile`, which must lie outside
 * the build output (it is never deployed); dist-check compares it with the built tree.
 */
export function placeRelease({ assetsDir, snapshot, manifest_sha256, out, verifiedFile }) {
  const { files } = checkRelease(readAssets(assetsDir), { snapshot, manifest_sha256 });
  for (const [p, b] of files) {
    mkdirSync(join(out, p, '..'), { recursive: true });
    writeFileSync(join(out, p), b);
  }
  const list = [...files.keys()].sort().map((p) => ({ path: p, sha256: sha256Hex(files.get(p)) }));
  writeFileSync(verifiedFile, JSON.stringify(list));
  return list;
}

/**
 * A `site` run's inputs must name the deployed dataset and release (22.8, I48): run names are
 * fixed when the run starts, and the deployed state is read from them. Returns the refusal or null.
 */
export function siteInputRefusal({ deployed, snapshot, manifest_sha256, tag }) {
  const want = deployed.dataset ? `${deployed.dataset.snapshot} ${deployed.dataset.manifest_sha256} ${deployed.release}` : 'none none none';
  const got = `${snapshot || 'none'} ${manifest_sha256 || 'none'} ${tag || 'none'}`;
  return want === got ? null : `a site run must name the deployed dataset and release (${want}), not ${got}`;
}

const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : undefined;
};

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const job = process.argv[2];
  const token = process.env.GITHUB_TOKEN;
  try {
    if (job === 'deployed') {
      const d = deployedState(await siteRuns({ token, siteRepository: arg('--site-repository') }));
      console.log(`${currentText(d.dataset)} ${d.release ?? 'none'}`);
      process.exit(0);
    }
    if (job === 'check-inputs') {
      // The input patterns (22.8); for a site run also I48 against the deployed state at build start.
      const mode = arg('--mode');
      const refusal = inputRefusal({ mode, tag: arg('--tag') || null, snapshot: arg('--snapshot') || null, manifest_sha256: arg('--manifest-sha256') || null, site_commit: arg('--site-commit') || null, expected_current: arg('--expected-current') || null });
      if (refusal) throw new Error(`input refused: ${refusal}`);
      if (mode === 'site') {
        const d = deployedState(await siteRuns({ token, siteRepository: arg('--site-repository') }));
        const why = siteInputRefusal({ deployed: d, snapshot: arg('--snapshot'), manifest_sha256: arg('--manifest-sha256'), tag: arg('--tag') });
        if (why) throw new Error(`input refused: ${why}`);
      }
      console.log('site data: inputs accepted');
      process.exit(0);
    }
    if (job === 'fetch') {
      const refusal = inputRefusal({ mode: 'data', tag: arg('--tag'), snapshot: arg('--snapshot'), manifest_sha256: arg('--manifest-sha256'), site_commit: '0'.repeat(40), expected_current: 'none' });
      if (refusal) throw new Error(`input refused: ${refusal}`);
      await downloadRelease({ releaseRepository: arg('--release-repository'), tag: arg('--tag'), dir: arg('--assets') });
      const list = placeRelease({ assetsDir: arg('--assets'), snapshot: arg('--snapshot'), manifest_sha256: arg('--manifest-sha256'), out: arg('--out'), verifiedFile: arg('--verified') });
      console.log(`site data: ${list.length} verified files from ${arg('--tag')}`);
      process.exit(0);
    }
    if (job === 'deploy-check') {
      const now = deployedState(await siteRuns({ token, siteRepository: arg('--site-repository') }));
      const mode = arg('--mode');
      const assets = arg('--assets');
      const log = assets ? JSON.parse(readFileSync(join(assets, 'deployments.json'), 'utf8')) : null;
      const why = deployRefusal({ mode, expected_current: arg('--expected-current'), deployed: now, input: arg('--snapshot') ? { snapshot: arg('--snapshot') } : null, log });
      if (why) throw new Error(`deploy refused: ${why}`);
      console.log('site data: deploy allowed (compare-and-swap and the monotonic rule hold)');
      process.exit(0);
    }
    throw new Error(`unknown job ${job}`);
  } catch (e) {
    console.error(`site-data ${job}: ${e.message}`);
    process.exit(3);
  }
}
