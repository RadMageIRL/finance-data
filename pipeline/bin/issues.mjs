#!/usr/bin/env node
// Issue delivery for Stage C (DATA_CONVENTIONS v0.7 section 21.5): reconciles the open issues
// labeled `rmf-alert` in the private data repository with the alert ledger a run wrote (17.8).
// One open issue per key; a changed title or body is edited, never commented; an issue whose key
// is no longer in the ledger is closed; duplicates of a key are closed but the oldest. Running it
// again changes nothing. When the collection job failed (the store was not written), only the
// one `collect-failed` issue is made sure of. Alert texts are sanitized before they get here
// (17.8) and checked again.
//
//   GITHUB_TOKEN=... GITHUB_REPOSITORY=owner/repo node pipeline/bin/issues.mjs --summary <file>
//   GITHUB_TOKEN=... GITHUB_REPOSITORY=owner/repo node pipeline/bin/issues.mjs --failed <step> --run <id>
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { sanitizeAlerts } from '../lib/alerts.mjs';

export const LABEL = 'rmf-alert';
const KEY_LINE = /^rmf-alert-key: ([a-z][a-z0-9-]*(?::[a-z0-9][a-z0-9-]*)?)$/m;

/** The issue title and body of an alert (21.5). */
export const issueText = (a) => ({ title: `${a.title} [${a.key}]`, body: `${a.body}\n\nrmf-alert-key: ${a.key}` });

/** The key an issue carries, or null. */
export const keyOf = (issue) => KEY_LINE.exec(issue.body ?? '')?.[1] ?? null;

/**
 * The actions that make the open `rmf-alert` issues match `wanted` (alerts with key, severity,
 * title, body), with `only` the keys this reconcile may touch (null: all). Pure.
 */
export function reconcilePlan(open, wanted, { only = null } = {}) {
  const byKey = new Map();
  for (const i of [...open].sort((a, b) => (a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : a.number - b.number))) {
    const k = keyOf(i);
    if (k === null) continue;
    if (!byKey.has(k)) byKey.set(k, []);
    byKey.get(k).push(i);
  }
  const actions = [];
  const want = new Map(wanted.map((a) => [a.key, a]));
  for (const [k, issues] of [...byKey].sort(([a], [b]) => (a < b ? -1 : 1))) {
    if (only && !only.has(k)) continue;
    const [keep, ...extra] = issues;
    for (const x of extra) actions.push({ action: 'close', number: x.number, key: k, why: 'duplicate' });
    if (!want.has(k)) actions.push({ action: 'close', number: keep.number, key: k, why: 'cleared' });
    else {
      const t = issueText(want.get(k));
      if (keep.title !== t.title || keep.body !== t.body) actions.push({ action: 'edit', number: keep.number, key: k, ...t });
    }
  }
  for (const [k, a] of [...want].sort(([x], [y]) => (x < y ? -1 : 1))) if (!byKey.has(k) && (!only || only.has(k))) actions.push({ action: 'create', key: k, ...issueText(a) });
  return actions;
}

/** The GitHub REST API for one repository, through fetch, with the job's token. */
export function githubApi({ token, repository, fetchImpl = fetch }) {
  const base = `https://api.github.com/repos/${repository}`;
  const call = async (method, path, body) => {
    const r = await fetchImpl(`${base}${path}`, { method, headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'RadMage Finance issue delivery' }, body: body ? JSON.stringify(body) : undefined });
    if (!r.ok) throw new Error(`GitHub API ${method} ${path.split('?')[0]} answered ${r.status}`);
    return r.status === 204 ? null : r.json();
  };
  return {
    async listOpen() {
      const out = [];
      for (let page = 1; page <= 20; page += 1) {
        const batch = await call('GET', `/issues?state=open&labels=${LABEL}&per_page=100&page=${page}`);
        out.push(...batch.filter((i) => !i.pull_request));
        if (batch.length < 100) break;
      }
      return out;
    },
    create: (t) => call('POST', '/issues', { title: t.title, body: t.body, labels: [LABEL] }),
    edit: (number, t) => call('PATCH', `/issues/${number}`, { title: t.title, body: t.body }),
    close: (number) => call('PATCH', `/issues/${number}`, { state: 'closed', state_reason: 'completed' }),
  };
}

/** Applies a plan through an api ({ create, edit, close }); returns what it did. */
export async function applyPlan(api, actions) {
  for (const a of actions) {
    if (a.action === 'create') await api.create(a);
    else if (a.action === 'edit') await api.edit(a.number, a);
    else if (a.action === 'close') await api.close(a.number);
  }
  return actions.map((a) => `${a.action} ${a.key}${a.number ? ` #${a.number}` : ''}`);
}

/** The reconcile after a run that wrote the store: the ledger it wrote is the wanted set. */
export async function reconcileLedger(api, ledger) {
  const wanted = sanitizeAlerts(ledger);
  const open = await api.listOpen();
  return applyPlan(api, reconcilePlan(open, wanted));
}

/** The reconcile after a failed collection job: only the `collect-failed` issue (21.5). */
export async function reconcileFailed(api, { step, run, at }) {
  const safe = (v) => String(v).replace(/[^A-Za-z0-9._:-]/g, '').slice(0, 80);
  const alert = { key: 'collect-failed', severity: 'critical', title: 'A collection run failed', body: `Run ${safe(run)} failed at step ${safe(step)} at ${safe(at)}. The state store was not written; the accepted state is unchanged. The next scheduled run retries.` };
  const open = await api.listOpen();
  return applyPlan(api, reconcilePlan(open, sanitizeAlerts([alert]), { only: new Set(['collect-failed']) }));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const arg = (name) => {
    const i = process.argv.indexOf(name);
    return i > 0 ? process.argv[i + 1] : undefined;
  };
  const token = process.env.GITHUB_TOKEN;
  const repository = process.env.GITHUB_REPOSITORY;
  if (!token || !repository) {
    console.error('issues: GITHUB_TOKEN and GITHUB_REPOSITORY are required');
    process.exit(2);
  }
  const api = githubApi({ token, repository });
  try {
    const done = arg('--failed')
      ? await reconcileFailed(api, { step: arg('--failed'), run: arg('--run') ?? 'unknown', at: `${new Date().toISOString().slice(0, 19)}Z` })
      : await reconcileLedger(api, JSON.parse(readFileSync(arg('--summary'), 'utf8')).ledger);
    console.log(done.length ? done.join('\n') : 'issues: nothing to change');
  } catch (e) {
    console.error(`issues: ${e.message}`);
    process.exit(1);
  }
}
