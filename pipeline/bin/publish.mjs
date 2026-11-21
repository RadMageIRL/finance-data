#!/usr/bin/env node
// The publication workflow's jobs (DATA_CONVENTIONS 22.6, v0.8; `publish.yml` of finance-data):
// assemble, release, dispatch, verify and report. Each job is a function with its reads and
// writes given as arguments, so it is tested on fakes; the command line wires it to the GitHub
// REST API and the public addresses. Nothing here is enabled by itself: the workflow's gates
// (PUBLICATION_ENABLED, the guard purpose `publish`, 22.6) decide whether a job runs at all.
//
//   node pipeline/bin/publish.mjs assemble --store <dir> --out <dir> --mode manual|timer|redeploy ...
//   node pipeline/bin/publish.mjs release|dispatch|verify|report --out <dir>
import { mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { canonicalJson, sha256Hex } from '../lib/canonical.mjs';
import { storeLayout, verifyStateV2 } from '../lib/state-store.mjs';
import { ownV2Refusal, publicationWindow } from '../lib/publish-store.mjs';
import { artifactSummary, fixPost, nextLog, nothingToPublish, releaseAssets, releaseTag, sameDataset, verifiedPairs } from '../lib/publication.mjs';
import { currentText } from '../lib/site-build.mjs';
import { reconcilePlan } from './issues.mjs';

export const OWN_KEYS = new Set(['publish-failed', 'publication-verify-failed']);

/**
 * The assemble job (22.6 job 1). o: { storeDir, mode, input ({ snapshot, manifest_sha256 } for
 * manual), target (a verified pair for redeploy), runId, attempt, now, facts (the newest
 * release's log and run outcomes, publication-facts.mjs), siteCommit (the Finance `main` commit,
 * unused for redeploy), deployed (the deployed dataset from the site runs, or null), validateState
 * (V2b), validatePublication (V2c), outDir }. Returns { outcome, ... }; writes `outDir/econ/`,
 * `outDir/assets/` and `outDir/release.json` only for `assembled`.
 */
export function assemble(o) {
  // V2a fails closed (22.5): only a promoted state store is read (as 21.3 refuses any other).
  const layout = storeLayout(o.storeDir);
  if (layout !== 'v0.7') return { outcome: 'refused-v2', problems: [`V2a: the state store is ${layout}, not a promoted store`] };
  const v = verifyStateV2(o.storeDir);
  if (!v.ok) return { outcome: 'refused-v2', problems: v.problems.map((p) => `V2a: ${p}`) };
  const accepted = JSON.parse(readFileSync(join(o.storeDir, 'state', 'STATE.json'), 'utf8')).accepted;
  if (o.mode === 'manual' && !sameDataset(o.input, accepted)) return { outcome: 'refused-gate', problems: ['the inputs are not the accepted identifier'] };
  // The newest earlier release, with its last post fixed once its run completed (22.4, I33).
  const prevLog = o.facts?.newestLog ? structuredClone(o.facts.newestLog) : null;
  const prevPost = prevLog ? fixPost(o.facts.newestRun) : null;
  if (prevLog) {
    const last = prevLog.deployments[prevLog.deployments.length - 1];
    if (last && last.verification.post === null) {
      if (prevPost === null) return { outcome: 'refused-gate', problems: ['the previous publication run has not completed'] };
      last.verification.post = prevPost;
    }
  }
  if ((o.mode === 'manual' || o.mode === 'timer') && nothingToPublish(prevLog, accepted)) return { outcome: 'no-op', problems: [] };
  if (o.mode === 'redeploy' && !verifiedPairs(prevLog).some((p) => sameDataset(p.dataset, o.target.dataset) && p.site_commit === o.target.site_commit)) return { outcome: 'refused-gate', problems: ['the redeploy target is not a verified pair'] };
  const dataset = o.mode === 'redeploy' ? o.target.dataset : accepted;
  const siteCommit = o.mode === 'redeploy' ? o.target.site_commit : o.siteCommit;
  const files = publicationWindow(o.storeDir, o.mode, dataset);
  const own = ownV2Refusal(o.storeDir, files, prevLog);
  if (own) return own;
  const counts = o.validateState(o.storeDir);
  if (counts.fail !== 0) return { outcome: 'refused-v2', problems: [`V2b: ${counts.fail} failure(s)`, ...(counts.failures ?? [])] };
  const tag = releaseTag(dataset.snapshot, o.runId, o.attempt);
  const log = nextLog(prevLog, prevPost, { published_at: o.now, run: `pub-${o.runId}-${o.attempt}`, trigger: o.mode, dataset, release: tag, site_commit: siteCommit, artifact: artifactSummary(files), checker: { pass: counts.pass, fail: counts.fail, skip: counts.skip } });
  files.set('status/deployments.json', Buffer.from(canonicalJson(log), 'utf8'));
  for (const [p, b] of files) {
    mkdirSync(join(o.outDir, 'econ', p, '..'), { recursive: true });
    writeFileSync(join(o.outDir, 'econ', p), b);
  }
  // V2c: the independent checker on the tree, the store and the newest earlier release.
  const c = o.validatePublication(join(o.outDir, 'econ'), o.storeDir);
  if (c.fail !== 0) return { outcome: 'refused-v2', problems: [`V2c: ${c.fail} failure(s)`, ...(c.failures ?? [])] };
  const assets = releaseAssets(files);
  mkdirSync(join(o.outDir, 'assets'), { recursive: true });
  for (const [n, b] of Object.entries(assets)) writeFileSync(join(o.outDir, 'assets', n), b);
  const info = { tag, mode: o.mode, dataset, site_commit: siteCommit, expected_current: currentText(o.deployed), artifact: artifactSummary(files), log };
  writeFileSync(join(o.outDir, 'release.json'), canonicalJson(info));
  return { outcome: 'assembled', ...info, problems: [] };
}

/** The release body (22.4). */
export const releaseBody = (info) => [
  `Dataset: snapshot ${info.dataset.snapshot}, manifest sha256:${info.dataset.manifest_sha256}.`,
  `Artifact: ${info.artifact.files} files, ${info.artifact.bytes} bytes, sha256:${info.artifact.sha256}.`,
  `Trigger: ${info.mode}. Site commit: ${info.site_commit}.`,
].join('\n');

/**
 * The release job (22.6 job 2): stale `data-*` drafts deleted, then a draft with exactly the
 * four assets, then published (release immutability makes it unchangeable, 22.4). `api`: {
 * listReleases, deleteRelease(id), createDraft({ tag, name, body }), uploadAsset(id, name, bytes), publish(id) }.
 */
export async function release({ api, info, assets }) {
  for (const r of await api.listReleases()) if (r.draft && /^data-/.test(r.tag_name)) await api.deleteRelease(r.id);
  const draft = await api.createDraft({ tag: info.tag, name: info.tag, body: releaseBody(info) });
  for (const name of ['SHA256SUMS', 'artifact.tar.gz', 'deployments.json', 'manifest.json']) await api.uploadAsset(draft.id, name, assets[name]);
  await api.publish(draft.id);
  return { id: draft.id, tag: info.tag };
}

/** The inputs of the Finance `pages.yml` dispatch (22.6 job 3, 22.8). */
export const dispatchInputs = (info) => ({ mode: 'data', tag: info.tag, snapshot: info.dataset.snapshot, manifest_sha256: info.dataset.manifest_sha256, site_commit: info.site_commit, expected_current: info.expected_current, dry_run: 'false' });

/**
 * V3 (22.5) at one address: the manifest until its bytes hash to the dataset's, then every file
 * the manifest and its snapshot name. `get(url)` returns { ok, bytes } and never throws. Returns
 * { passed, problems }.
 */
export async function v3At({ base, dataset, get, sleep, attempts = 31 }) {
  let manifestBytes = null;
  for (let i = 0; i < attempts; i += 1) {
    const r = await get(`${base}manifest.json`);
    if (r.ok && sha256Hex(r.bytes) === dataset.manifest_sha256) {
      manifestBytes = r.bytes;
      break;
    }
    if (i < attempts - 1) await sleep(30);
  }
  if (!manifestBytes) return { passed: false, problems: [`${base}manifest.json never matched the dataset`] };
  const manifest = JSON.parse(Buffer.from(manifestBytes).toString('utf8'));
  const refs = [manifest.snapshot];
  for (const s of Object.values(manifest.series)) refs.push(...s.objects, ...s.csvs, ...s.revisions, ...(s.revision_csvs ?? []));
  if (manifest.rules) refs.push(manifest.rules.registry, manifest.rules.holidays, manifest.rules.notice, ...manifest.rules.registry_versions);
  const problems = [];
  for (const ref of refs) {
    const r = await get(`${base}${ref.path}`);
    if (!r.ok || sha256Hex(r.bytes) !== ref.sha256) problems.push(`${ref.path} does not match`);
  }
  return { passed: problems.length === 0, problems };
}

/**
 * The report job (22.6 job 5): the reconcile of the two keys this workflow owns. `result`: {
 * failedAfterGates, v3 ('passed' | 'failed' | null), person }. `open` is the ledger of open
 * issues with these keys as alerts. Returns the plan.
 */
export function reportPlan({ openIssues, openKeys, result, now }) {
  const want = new Map([...openKeys].filter((k) => OWN_KEYS.has(k)).map((k) => [k, true]));
  if (result.v3 === 'passed') {
    want.delete('publish-failed');
    if (result.person) want.delete('publication-verify-failed');
  }
  if (result.failedAfterGates) want.set('publish-failed', true);
  if (result.v3 === 'failed') want.set('publication-verify-failed', true);
  const alert = (key) => (key === 'publish-failed'
    ? { key, severity: 'critical', title: 'Publication failed', body: `A publication run failed after its gates at ${now}. Read the run's log.` }
    : { key, severity: 'critical', title: 'Post-deploy verification failed', body: `The post-deploy verification failed at ${now}; the newest verified pair was redeployed and timer publication is paused until a person-started publication passes.` });
  return reconcilePlan(openIssues, [...want.keys()].sort().map(alert), { only: OWN_KEYS });
}

// ---- The command line (the workflow). Network code only below. ----

const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : undefined;
};

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const job = process.argv[2];
  const out = arg('--out');
  const fail = (m) => {
    console.error(`publish ${job}: ${m}`);
    process.exit(3);
  };
  try {
    if (!out) fail('--out is required');
    const { runChecker } = await import('./collect.mjs');
    if (job === 'assemble') {
      const { readCollectFacts } = await import('./publication-facts.mjs');
      const env = process.env;
      const facts = await readCollectFacts({ token: env.GITHUB_TOKEN, repository: env.GITHUB_REPOSITORY, siteRepository: env.SITE_REPOSITORY });
      const mode = arg('--mode');
      const target = mode === 'redeploy' ? JSON.parse(readFileSync(arg('--target'), 'utf8')) : null;
      const r = assemble({
        storeDir: arg('--store'), mode, input: mode === 'manual' ? { snapshot: arg('--snapshot'), manifest_sha256: arg('--manifest-sha256') } : null, target,
        runId: Number(env.GITHUB_RUN_ID), attempt: Number(env.GITHUB_RUN_ATTEMPT ?? 1), now: `${new Date().toISOString().slice(0, 19)}Z`, facts,
        siteCommit: arg('--site-commit'), deployed: arg('--deployed') && arg('--deployed') !== 'none' ? { snapshot: arg('--deployed').split(':')[0], manifest_sha256: arg('--deployed').split(':')[1] } : null,
        validateState: (s) => runChecker(['--state', s]),
        validatePublication: (tree, s) => runChecker(['--publication', tree, '--state', s]),
        outDir: out,
      });
      writeFileSync(join(out, 'outcome.json'), JSON.stringify(r));
      console.log(`publish assemble: ${r.outcome}${r.problems?.length ? ` (${r.problems.slice(0, 5).join('; ')})` : ''}`);
      process.exit(r.outcome === 'assembled' || r.outcome === 'no-op' ? 0 : 1);
    }
    const env = process.env;
    const outcome = existsSync(join(out, 'outcome.json')) ? JSON.parse(readFileSync(join(out, 'outcome.json'), 'utf8')) : null;
    const info = existsSync(join(out, 'release.json')) ? JSON.parse(readFileSync(join(out, 'release.json'), 'utf8')) : null;
    const gh = (token, repo) => {
      const call = async (method, url, body, extra = {}) => {
        const r = await fetch(url.startsWith('https://') ? url : `https://api.github.com/repos/${repo}${url}`, { method, headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'RadMage Finance publication', ...(body && !(body instanceof Buffer) ? { 'Content-Type': 'application/json' } : {}), ...extra }, body: body instanceof Buffer ? body : body ? JSON.stringify(body) : undefined });
        if (!r.ok) throw new Error(`GitHub API ${method} ${url.split('?')[0].replace(/^https:\/\/[^/]+/, '')} answered ${r.status}`);
        return r.status === 204 ? null : r.json();
      };
      return call;
    };
    if (job === 'release') {
      if (!info) fail('no assembled release');
      const call = gh(env.GITHUB_TOKEN, env.GITHUB_REPOSITORY);
      const assets = Object.fromEntries(['SHA256SUMS', 'artifact.tar.gz', 'deployments.json', 'manifest.json'].map((n_) => [n_, readFileSync(join(out, 'assets', n_))]));
      const r = await release({ info, assets, api: {
        listReleases: () => call('GET', '/releases?per_page=100'),
        deleteRelease: (id) => call('DELETE', `/releases/${id}`),
        createDraft: ({ tag, name, body }) => call('POST', '/releases', { tag_name: tag, name, body, draft: true, target_commitish: 'main' }),
        uploadAsset: (id, name, bytes) => call('POST', `https://uploads.github.com/repos/${env.GITHUB_REPOSITORY}/releases/${id}/assets?name=${encodeURIComponent(name)}`, bytes, { 'Content-Type': 'application/octet-stream' }),
        publish: (id) => call('PATCH', `/releases/${id}`, { draft: false }),
      } });
      console.log(`publish release: ${r.tag} published`);
      process.exit(0);
    }
    if (job === 'dispatch') {
      if (!info) fail('no assembled release');
      await gh(env.PAGES_DISPATCH_TOKEN, env.SITE_REPOSITORY)('POST', '/actions/workflows/pages.yml/dispatches', { ref: 'main', inputs: dispatchInputs(info) });
      console.log(`publish dispatch: pages.yml dispatched for ${info.tag}`);
      process.exit(0);
    }
    if (job === 'verify') {
      if (!info) fail('no assembled release');
      const site = gh(env.GITHUB_TOKEN, env.SITE_REPOSITORY);
      const name = `pages data ${info.dataset.snapshot} ${info.dataset.manifest_sha256} ${info.tag}`;
      const sleep = (s_) => new Promise((res) => setTimeout(res, s_ * 1000));
      let run = null;
      for (let i = 0; i < 60 && !(run && run.status === 'completed'); i += 1) {
        const runs = (await site('GET', '/actions/workflows/pages.yml/runs?per_page=50')).workflow_runs ?? [];
        run = runs.find((r_) => r_.display_title === name) ?? null;
        if (!(run && run.status === 'completed')) await sleep(30);
      }
      const get = async (url) => {
        try {
          const r_ = await fetch(url, { cache: 'no-store', headers: { 'User-Agent': 'RadMage Finance publication' } });
          return r_.ok ? { ok: true, bytes: Buffer.from(await r_.arrayBuffer()) } : { ok: false };
        } catch {
          return { ok: false };
        }
      };
      let v3 = null;
      if (run?.status === 'completed' && run.conclusion === 'success') {
        const a = await v3At({ base: 'https://radmagelabs.com/finance/data/econ/', dataset: info.dataset, get, sleep });
        const b = await v3At({ base: 'https://radmageirl.github.io/finance/data/econ/', dataset: info.dataset, get, sleep });
        v3 = a.passed && b.passed ? 'passed' : 'failed';
        for (const p_ of [...a.problems, ...b.problems]) console.log(`V3: ${p_}`);
      }
      writeFileSync(join(out, 'verify.json'), JSON.stringify({ site: run?.conclusion ?? null, v3 }));
      if (v3 === 'failed') {
        // D13: an automatic redeploy of the newest verified pair, with this entry's post failed.
        const fixed = structuredClone(info.log);
        fixed.deployments[fixed.deployments.length - 1].verification.post = 'failed';
        const pair = verifiedPairs(fixed)[0];
        if (pair) await gh(env.GITHUB_TOKEN, env.GITHUB_REPOSITORY)('POST', '/actions/workflows/publish.yml/dispatches', { ref: 'main', inputs: { mode: 'redeploy', target: JSON.stringify({ dataset: pair.dataset, site_commit: pair.site_commit }), automatic: 'true' } });
      }
      console.log(`publish verify: site ${run?.conclusion ?? 'not found'}, V3 ${v3 ?? 'not run'}`);
      process.exit(v3 === 'passed' ? 0 : 1);
    }
    if (job === 'report') {
      const { githubApi, applyPlan } = await import('./issues.mjs');
      const api = githubApi({ token: env.GITHUB_TOKEN, repository: env.GITHUB_REPOSITORY });
      const open = await api.listOpen();
      const { keyOf } = await import('./issues.mjs');
      const openKeys = new Set(open.map((i_) => keyOf(i_)).filter((k) => OWN_KEYS.has(k)));
      const verify = existsSync(join(out, 'verify.json')) ? JSON.parse(readFileSync(join(out, 'verify.json'), 'utf8')) : { v3: null };
      const gatedOut = !outcome || outcome.outcome === 'no-op' || outcome.outcome === 'refused-gate';
      const failedAfterGates = !gatedOut && (outcome.outcome !== 'assembled' || env.JOBS_FAILED === 'true' || verify.v3 === null);
      const plan = reportPlan({ openIssues: open, openKeys, result: { failedAfterGates, v3: verify.v3, person: env.AUTOMATIC !== 'true' }, now: `${new Date().toISOString().slice(0, 19)}Z` });
      const done = await applyPlan(api, plan);
      console.log(done.length ? done.join('\n') : 'issues: nothing to change');
      process.exit(0);
    }
    fail(`unknown job ${job}`);
  } catch (e) {
    fail(e.message);
  }
}
