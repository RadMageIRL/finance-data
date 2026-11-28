#!/usr/bin/env node
// The publication facts of a collection run (DATA_CONVENTIONS 22.4, v0.8): the newest `data-*`
// release's deployment log and the outcomes of the publication run that made it (whether it has
// completed, its `verify` job, and the Finance site run that names the release). Reads only,
// through the GitHub REST API. Publications are serial (22.6), so the newest release (by
// published_at, then numeric id: 22.4, amendment 3) carries the longest log; the watcher checks
// the whole history (22.7). Writes the facts as
// JSON; exits 3 when they cannot be read, so the collection run continues with
// --publication-facts-unavailable (22.4).
//
//   GITHUB_TOKEN=... GITHUB_REPOSITORY=owner/data-repo SITE_REPOSITORY=owner/site-repo \
//     node pipeline/bin/publication-facts.mjs --out <file>
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { newestRelease, ownLogProblem } from '../lib/publication.mjs';

const TAG = /^data-(\d{8}T\d{6}Z)-(\d+)-(\d+)$/;

/** Reads the facts; returns { newestLog: null, newestRun: null } when no `data-*` release exists. Throws on a refused read. */
export async function readCollectFacts({ token, repository, siteRepository, fetchImpl = fetch }) {
  const headers = (accept) => ({ Authorization: `Bearer ${token}`, Accept: accept, 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'RadMage Finance collection' });
  const get = async (url, accept = 'application/vnd.github+json') => {
    const r = await fetchImpl(url, { headers: headers(accept) });
    if (!r.ok) throw new Error(`GitHub API GET ${url.replace(/^https:\/\/api\.github\.com/, '').split('?')[0]} answered ${r.status}`);
    return r;
  };
  const api = (repo) => `https://api.github.com/repos/${repo}`;
  const releases = [];
  for (let page = 1; ; page += 1) {
    const batch = await (await get(`${api(repository)}/releases?per_page=100&page=${page}`)).json();
    releases.push(...batch);
    if (batch.length < 100) break;
  }
  // The newest release by published_at, then numeric id (22.4, amendment 3): never created_at,
  // which is the tagged commit's date and ties for releases tagged on one commit.
  const newest = newestRelease(releases.filter((r) => !r.draft && TAG.test(r.tag_name)));
  if (!newest) return { newestLog: null, newestRun: null };
  const logAsset = newest.assets.find((a) => a.name === 'deployments.json');
  if (!logAsset) throw new Error(`the release ${newest.tag_name} has no deployments.json`);
  const newestLog = JSON.parse(Buffer.from(await (await get(logAsset.url, 'application/octet-stream')).arrayBuffer()).toString('utf8'));
  const own = ownLogProblem(newest.tag_name, newestLog);
  if (own) throw new Error(own);
  const runId = TAG.exec(newest.tag_name)[2];
  const run = await (await get(`${api(repository)}/actions/runs/${runId}`)).json();
  if (run.status !== 'completed') return { newestLog, newestRun: { completed: false } };
  const jobs = (await (await get(`${api(repository)}/actions/runs/${runId}/jobs?per_page=100`)).json()).jobs ?? [];
  const verify = jobs.find((j) => j.name === 'verify');
  const siteRuns = (await (await get(`${api(siteRepository)}/actions/workflows/pages.yml/runs?per_page=100`)).json()).workflow_runs ?? [];
  const site = siteRuns.find((r) => typeof r.display_title === 'string' && r.display_title.startsWith('pages data ') && r.display_title.endsWith(` ${newest.tag_name}`));
  return { newestLog, newestRun: { completed: true, siteConclusion: site?.status === 'completed' ? site.conclusion : null, verifyConclusion: verify?.conclusion ?? null } };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const i = process.argv.indexOf('--out');
  const out = i > 0 ? process.argv[i + 1] : null;
  const { GITHUB_TOKEN: token, GITHUB_REPOSITORY: repository, SITE_REPOSITORY: siteRepository } = process.env;
  if (!out || !token || !repository || !siteRepository) {
    console.error('usage: GITHUB_TOKEN=... GITHUB_REPOSITORY=... SITE_REPOSITORY=... node pipeline/bin/publication-facts.mjs --out <file>');
    process.exit(2);
  }
  try {
    const facts = await readCollectFacts({ token, repository, siteRepository });
    writeFileSync(out, JSON.stringify(facts));
    console.log(`publication facts: ${facts.newestLog ? `newest release log has ${facts.newestLog.deployments.length} entries; run ${facts.newestRun.completed ? 'completed' : 'in progress'}` : 'no data release'}`);
  } catch (e) {
    console.error(`publication facts unavailable: ${e.message}`);
    process.exit(3);
  }
}
