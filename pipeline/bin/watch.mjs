#!/usr/bin/env node
// The independent run-gap watcher for Stage C (DATA_CONVENTIONS 21.9, decision P43): layer 3 of
// 17.8. It reads the collect workflow's state and runs and the repository's pushed_at from the
// GitHub API, evaluates 14.3 with the same function the collector uses, keeps only the run keys,
// and reconciles only the issues with those keys (21.5). It reads no state store and writes
// nothing but issues, so it reports a gap even when no collect run starts at all. The job fails
// when a gap, a disabled workflow or a failure streak is present, so GitHub's failed-run
// notification is a second channel; when the facts cannot be read it fails and changes nothing.
//
//   GITHUB_TOKEN=... GITHUB_REPOSITORY=owner/repo node pipeline/bin/watch.mjs
import { fileURLToPath } from 'node:url';
import { healthAlerts, sanitizeAlerts } from '../lib/alerts.mjs';
import { runFacts } from '../lib/run-facts.mjs';
import { scheduleHealth } from '../lib/schedule-health.mjs';
import { applyPlan, githubApi, reconcilePlan } from './issues.mjs';
import { releaseHistoryProblems } from '../lib/publication.mjs';

/** The findings of 14.3 that need no manifest (21.9). */
export const RUN_KEYS = ['consecutive-failures', 'inactivity', 'scheduled-run-gap', 'workflow-disabled'];
/** The findings that fail the job (21.9); `inactivity` alone does not. */
export const FAILING_KEYS = ['consecutive-failures', 'scheduled-run-gap', 'workflow-disabled'];
/** v0.8 (21.9, 22.7): once a `data-*` release exists, the public manifest's keys and the release history. */
export const MANIFEST_KEYS = ['manifest-missing', 'manifest-overdue'];
export const HISTORY_KEY = 'publication-history-changed';
export const WATCH_KEYS = [...RUN_KEYS, ...MANIFEST_KEYS, HISTORY_KEY];
/** The public data address (22.1). */
export const PUBLIC_BASE = 'https://radmagelabs.com/finance/data/econ/';

/** Reads the facts of 21.9 through the GitHub REST API; any refused read throws. */
export async function readFacts({ token, repository, now, fetchImpl = fetch }) {
  const base = `https://api.github.com/repos/${repository}`;
  const get = async (path) => {
    const r = await fetchImpl(`${base}${path}`, { headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'RadMage Finance watcher' } });
    if (!r.ok) throw new Error(`GitHub API GET ${path.split('?')[0] || '/'} answered ${r.status}`);
    return r.json();
  };
  const workflow = await get('/actions/workflows/collect.yml');
  const runs = await get('/actions/workflows/collect.yml/runs?per_page=30');
  const repo = await get('');
  if (typeof workflow.state !== 'string' || !Array.isArray(runs.workflow_runs) || typeof repo.pushed_at !== 'string') throw new Error('the GitHub API answered without the expected fields');
  return { now, workflow: { state: workflow.state }, repository: { pushed_at: repo.pushed_at }, runs: runFacts(runs.workflow_runs), manifest: null };
}

/**
 * The release and public facts of 21.9 (v0.8): every published `data-*` release with its asset
 * names and log, the newest release's four assets, the public manifest and deployed log (null
 * when they cannot be read). Returns null when no `data-*` release exists. Any refused GitHub read throws.
 */
export async function readPublicationFacts({ token, repository, fetchImpl = fetch, publicBase = PUBLIC_BASE }) {
  const api = `https://api.github.com/repos/${repository}`;
  const headers = (accept) => ({ Authorization: `Bearer ${token}`, Accept: accept, 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'RadMage Finance watcher' });
  const listed = [];
  for (let page = 1; ; page += 1) {
    const r = await fetchImpl(`${api}/releases?per_page=100&page=${page}`, { headers: headers('application/vnd.github+json') });
    if (!r.ok) throw new Error(`GitHub API GET /releases answered ${r.status}`);
    const batch = await r.json();
    listed.push(...batch);
    if (batch.length < 100) break;
  }
  const data = listed.filter((r) => !r.draft && /^data-/.test(r.tag_name));
  if (!data.length) return null;
  const asset = async (rel, name) => {
    const a = rel.assets.find((x) => x.name === name);
    if (!a) return null;
    const r = await fetchImpl(a.url, { headers: headers('application/octet-stream') });
    if (!r.ok) throw new Error(`GitHub API GET a release asset answered ${r.status}`);
    return Buffer.from(await r.arrayBuffer());
  };
  const releases = [];
  for (const rel of data) {
    const logBytes = await asset(rel, 'deployments.json');
    releases.push({ tag: rel.tag_name, assetNames: rel.assets.map((x) => x.name), log: logBytes ? JSON.parse(logBytes.toString('utf8')) : { deployments: [] }, rel });
  }
  const top = [...releases].sort((a, b) => a.log.deployments.length - b.log.deployments.length).pop();
  const assets = {};
  for (const name of top.assetNames) assets[name] = await asset(top.rel, name);
  const publicJson = async (path) => {
    try {
      const r = await fetchImpl(`${publicBase}${path}`, { cache: 'no-store', headers: { 'User-Agent': 'RadMage Finance watcher' } });
      return r.ok ? JSON.parse(await r.text()) : null;
    } catch {
      return null;
    }
  };
  return {
    releases: releases.map(({ tag, assetNames, log }) => ({ tag, assetNames, log })),
    newest: { tag: top.tag, assets },
    manifest: await publicJson('manifest.json'),
    deployedLog: await publicJson('status/deployments.json'),
  };
}

/**
 * 14.3 on the facts: the run keys; and from v0.8, once a `data-*` release exists
 * (`facts.publication`), the public manifest's keys and the release history (22.7). Pure.
 */
export function watchFindings(facts) {
  const run = scheduleHealth({ ...facts, manifest: null }).filter((f) => RUN_KEYS.includes(f.key));
  const pub = facts.publication ?? null;
  if (!pub) return run;
  const manifest = scheduleHealth({ ...facts, manifest: pub.manifest }).filter((f) => MANIFEST_KEYS.includes(f.key));
  const problems = releaseHistoryProblems(pub);
  const history = problems.length ? [{ key: HISTORY_KEY, severity: 'critical', message: `The publication history changed: ${problems.slice(0, 5).join('; ')}.` }] : [];
  return [...run, ...manifest, ...history];
}

/** The reconcile of 21.5 limited to the watcher's keys (22.6 table). Pure. */
export function watchPlan(open, findings) {
  return reconcilePlan(open, sanitizeAlerts(healthAlerts(findings)), { only: new Set(WATCH_KEYS) });
}

/** True when the job must fail (21.9): a run key that fails, `manifest-missing`, a critical `manifest-overdue`, or the history check. */
export const watchFails = (findings) => findings.some((f) => FAILING_KEYS.includes(f.key) || f.key === 'manifest-missing' || f.key === HISTORY_KEY || (f.key === 'manifest-overdue' && f.severity === 'critical'));

/** One watch: findings, the issue changes made through `api`, and whether the job fails. */
export async function watch({ api, facts }) {
  const findings = watchFindings(facts);
  const done = await applyPlan(api, watchPlan(await api.listOpen(), findings));
  return { findings, done, fail: watchFails(findings) };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const token = process.env.GITHUB_TOKEN;
  const repository = process.env.GITHUB_REPOSITORY;
  if (!token || !repository) {
    console.error('watch: GITHUB_TOKEN and GITHUB_REPOSITORY are required');
    process.exit(2);
  }
  const now = `${new Date().toISOString().slice(0, 19)}Z`;
  try {
    const facts = await readFacts({ token, repository, now });
    facts.publication = await readPublicationFacts({ token, repository });
    const { findings, done, fail } = await watch({ api: githubApi({ token, repository }), facts });
    console.log(`watch ${now}: ${facts.runs.length} collect runs listed; ${findings.length ? findings.map((f) => `${f.severity} ${f.key}: ${f.message}`).join(' | ') : 'no run finding'}`);
    console.log(done.length ? done.join('\n') : 'issues: nothing to change');
    if (fail) {
      console.error('watch: a run finding is present (21.9); see the rmf-alert issues');
      process.exit(1);
    }
  } catch (e) {
    console.error(`watch: ${e.message}`);
    process.exit(1);
  }
}
