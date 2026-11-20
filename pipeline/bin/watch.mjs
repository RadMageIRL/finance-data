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

/** The findings of 14.3 that need no manifest (21.9). */
export const RUN_KEYS = ['consecutive-failures', 'inactivity', 'scheduled-run-gap', 'workflow-disabled'];
/** The findings that fail the job (21.9); `inactivity` alone does not. */
export const FAILING_KEYS = ['consecutive-failures', 'scheduled-run-gap', 'workflow-disabled'];

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

/** 14.3 on the facts, the run keys only. Pure. */
export function watchFindings(facts) {
  return scheduleHealth({ ...facts, manifest: null }).filter((f) => RUN_KEYS.includes(f.key));
}

/** The reconcile of 21.5 limited to the run keys. Pure. */
export function watchPlan(open, findings) {
  return reconcilePlan(open, sanitizeAlerts(healthAlerts(findings)), { only: new Set(RUN_KEYS) });
}

/** True when the job must fail (21.9). */
export const watchFails = (findings) => findings.some((f) => FAILING_KEYS.includes(f.key));

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
