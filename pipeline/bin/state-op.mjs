#!/usr/bin/env node
// Operations on the private state store (DATA_CONVENTIONS v0.7 section 21.6): `promote` (the
// one-time promotion of the reviewed Stage B dataset, 21.1), `review` (approve, reject or clear,
// 11.5 and 17.5), `rollback` and `restore` (17.5). Each reads and verifies the store, applies the
// operation to a working root, validates it with the independent checker, writes the store with a
// collection record (trigger `operation`) and, with --push, commits and pushes without force.
// The account that started the operation must hold one of the registry's review permissions on
// the data repository, read within the hour; automation accounts are refused. Nothing is
// published and no request is sent to any provider.
//
//   ACTOR=<login> ACTOR_PERMISSION=<permission> PERMISSION_CHECKED_AT=<time>
//   node pipeline/bin/state-op.mjs --op promote --state <dir> --root <dir> --run <id> --manifest-sha256 <hex> [--push]
//   ... --op review --series <id> --candidate <sha256> --decision approve|reject|clear --reason <text>
//   ... --op rollback --to <snapshot id> --reason <text>
//   ... --op restore --reason <text>
//   ... --op pin --snapshot <id> --site-release <name> --reason <text>   (v0.8, 17.6, 21.6)
//   ... --op unpin --snapshot <id> --reason <text>
import { cpSync, existsSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadInputs } from './fixture-scenario.mjs';
import { runChecker, validateRoot, writeStore } from './collect.mjs';
import { pinSnapshot, reviewHold, rollback, restore, unpinSnapshot } from '../lib/run.mjs';
import { textRefusal } from '../lib/alerts.mjs';
import { acceptedRecord, commitAndPush, importStateV2, promoteStore, storeLayout, verifyState, verifyStateV2 } from '../lib/state-store.mjs';
import { canonicalJson } from '../lib/canonical.mjs';
import { freshnessAt } from '../lib/freshness.mjs';
import { makeCalendar } from '../lib/calendar.mjs';
import { createHash } from 'node:crypto';

const AUTOMATION = /(\[bot\]$|^github-actions$)/i;
const nowIso = () => `${new Date().toISOString().slice(0, 19)}Z`;
const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : undefined;
};

/** Why the account may not operate on the store, or null (21.6). */
export function actorRefusal(registry, { actor, permission, checkedAt, now }) {
  if (typeof actor !== 'string' || actor.trim() === '') return 'no account given';
  if (AUTOMATION.test(actor.trim())) return 'an automation account cannot operate on the state store';
  if (!registry.family_policy.review.permissions.includes(permission)) return 'the account does not have write access to the data repository';
  const at = typeof checkedAt === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(checkedAt) ? Date.parse(checkedAt) : NaN;
  const t = Date.parse(now);
  if (!(at <= t && t - at <= 3600 * 1000)) return 'the permission was not read within the hour before the operation';
  return null;
}

/** The collection record of an operation (21.4), without `added` and `month_added_bytes`. */
function operationRecord({ run, operation, startedAt, endedAt, outcome, checker, live, inputs, now }) {
  const manifestBytes = readFileSync(join(live, 'manifest.json'));
  const manifest = JSON.parse(manifestBytes.toString('utf8'));
  const snapshot = JSON.parse(readFileSync(join(live, manifest.snapshot.path), 'utf8'));
  const f = freshnessAt({ registry: inputs.registry, calendar: makeCalendar(inputs.holidays), manifest, snapshot, now });
  return {
    schema: 'rmf.econ.collection/1',
    run,
    trigger: 'operation',
    operation,
    started_at: startedAt,
    ended_at: endedAt,
    outcome,
    requests: [],
    validation: { checker: { mode: 'live', pass: checker.pass, fail: checker.fail, skip: checker.skip }, state: 'ok' },
    accepted: { snapshot: manifest.snapshot.id, manifest_sha256: createHash('sha256').update(manifestBytes).digest('hex') },
    freshness: f.freshness,
    expected_next_update_by: f.expected_next_update_by,
  };
}

/** The current commit of a git checkout, or 40 zeros for a plain folder (the scenario). */
const headOf = (dir) => {
  // Only the store's own repository counts (a plain folder inside another checkout has none).
  if (!existsSync(join(dir, '.git'))) return '0'.repeat(40);
  const r = spawnSync('git', ['-C', dir, 'rev-parse', 'HEAD'], { encoding: 'utf8' });
  return r.status === 0 && /^[0-9a-f]{40}$/.test(r.stdout.trim()) ? r.stdout.trim() : '0'.repeat(40);
};

/**
 * One operation. o: { op, state, root, run, actor, permission, checkedAt, now?, clock?, push?,
 * manifestSha256 (promote), decision: { brief, decided_on } (promote), series, candidate,
 * reviewDecision, reason, to, validate?, validateStore? }.
 */
export async function operate(o) {
  const inputs = o.inputs ?? loadInputs();
  const clock = o.clock ?? nowIso;
  const now = o.now ?? clock();
  const refusal = actorRefusal(inputs.registry, { actor: o.actor, permission: o.permission, checkedAt: o.checkedAt, now });
  if (refusal) throw new Error(`operation refused: ${refusal}`);
  // v0.8 (21.6, 22.3, D6): a reason that can become public passes the reason check before any
  // read or write; the refusal names the rule that failed, never the text.
  if (['review', 'rollback', 'restore', 'pin', 'unpin'].includes(o.op)) {
    const why = textRefusal(o.reason);
    if (why) throw new Error(`operation refused: the reason fails the publication text check (${why}); nothing is written`);
  }
  const validate = o.validate ?? validateRoot;
  if (o.op === 'promote') {
    if (storeLayout(o.state) !== 'v0.6') throw new Error(`promotion refused: the store is ${storeLayout(o.state)}, not the Stage B layout`);
    const v = verifyState(o.state);
    if (!v.ok) throw new Error(`promotion refused: ${v.problems.join('; ')}`);
    const named = join(o.state, v.descriptor.root);
    if (existsSync(join(o.state, 'state', 'accepted.json'))) throw new Error('promotion refused: the store was promoted already');
    const manifestFile = join(named, 'live', 'manifest.json');
    if (createHash('sha256').update(readFileSync(manifestFile)).digest('hex') !== o.manifestSha256) throw new Error('promotion refused: the root manifest is not the reviewed one');
    // The independent hash and schema verification of the reviewed dataset (21.1): on a working
    // copy of the root that already holds the store's state files and the accepted.json about to
    // be written (its counts are filled in after the check).
    const storeCommit = headOf(o.state);
    const snapshotId = JSON.parse(readFileSync(manifestFile, 'utf8')).snapshot.id;
    rmSync(o.root, { recursive: true, force: true });
    cpSync(join(named, 'live'), join(o.root, 'live'), { recursive: true });
    // The archive without its archive/state/ (the store's state/ files take its place).
    cpSync(join(named, 'archive'), join(o.root, 'archive'), { recursive: true, filter: (src) => relative(join(named, 'archive'), src).split(sep)[0] !== 'state' });
    cpSync(join(o.state, 'state'), join(o.root, 'archive', 'state'), { recursive: true, filter: (src) => !src.endsWith('STATE.json') });
    const provisional = acceptedRecord({ snapshot: snapshotId, manifestSha256: o.manifestSha256, storeCommit, named: v.descriptor.root, checker: { pass: 1, fail: 0, skip: 0 }, verifiedAt: now, decision: o.decision, promotedBy: o.actor, run: o.run, now });
    writeFileSync(join(o.root, 'archive', 'state', 'accepted.json'), canonicalJson(provisional));
    const checker = validate(o.root);
    if (checker.fail !== 0) throw new Error(`promotion refused: the independent checker found ${checker.fail} failure(s) (${(checker.failures ?? []).join(' | ')})`);
    const record = operationRecord({ run: o.run, operation: 'promote', startedAt: now, endedAt: clock(), outcome: 'promoted', checker, live: join(named, 'live'), inputs, now });
    const r = promoteStore(o.state, { manifestSha256: o.manifestSha256, storeCommit, checker, verifiedAt: now, decision: o.decision, promotedBy: o.actor, run: o.run, now, record, writtenAt: clock() });
    const again = verifyStateV2(o.state);
    if (!again.ok) throw new Error(`promotion not written: the written checkout does not verify (${again.problems.join('; ')})`);
    if (o.validateStore) {
      const c = o.validateStore(o.state);
      if (c.fail !== 0) throw new Error(`promotion not written: the independent checker failed on the written store (${(c.failures ?? []).join(' | ')})`);
    }
    let commit = null;
    if (o.push) {
      const pushed = commitAndPush(o.state, { message: `Stage C promotion ${o.run}: the reviewed Stage B dataset ${r.accepted.dataset.snapshot} becomes the accepted private baseline` });
      if (!pushed.ok) throw new Error(`promotion not written: ${pushed.step} refused (${String(pushed.detail).trim()})`);
      commit = pushed.commit;
    }
    // The ledger is the store's own (the promotion changes no alert), so the issue job keeps it.
    const alertsFile = join(o.state, 'state', 'alerts.json');
    const ledger = existsSync(alertsFile) ? JSON.parse(readFileSync(alertsFile, 'utf8')).open.map(({ key, severity, title, body }) => ({ key, severity, title, body })) : [];
    return { outcome: 'promoted', run: o.run, accepted: r.accepted.dataset, added: r.record.added, commit, ledger, plan: [] };
  }
  if (!['review', 'rollback', 'restore', 'pin', 'unpin'].includes(o.op)) throw new Error(`operation refused: unknown operation ${o.op}`);
  importStateV2(o.state, o.root);
  if (o.op === 'pin' || o.op === 'unpin') {
    // v0.8 (17.6, 21.6): a pin changes `pins.json` only. Like the promotion it runs no pipeline
    // step and writes no run record; its collection record's outcome is `no-change` (21.4).
    const r = o.op === 'pin'
      ? pinSnapshot({ root: o.root, snapshot: o.snapshot, site_release: o.siteRelease, reason: o.reason, now })
      : unpinSnapshot({ root: o.root, snapshot: o.snapshot, reason: o.reason, now });
    if (!r.ok) throw new Error(`operation refused: ${r.error}; nothing is written`);
    const checker = validate(o.root);
    if (checker.fail !== 0) throw new Error(`validation failed: the independent checker found ${checker.fail} failure(s); the store is not written (${(checker.failures ?? []).join(' | ')})`);
    const record = operationRecord({ run: o.run, operation: o.op, startedAt: now, endedAt: clock(), outcome: 'no-change', checker, live: join(o.root, 'live'), inputs, now });
    const w = writeStore({ root: o.root, state: o.state, run: o.run, record, bodies: [], push: o.push, message: `Stage C operation ${o.run}: ${o.op} ${o.snapshot} (private)`, clock, validateStore: o.validateStore ?? null });
    return { outcome: 'no-change', run: o.run, accepted: w.record.accepted, added: w.record.added, commit: w.commit, ledger: [], plan: [], refused: null, error: null };
  }
  const base = { root: o.root, mode: 'operation', registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays, now, run: { id: o.run, attempt: 1, trigger: 'manual', collector_commit: process.env.GITHUB_SHA ?? '0'.repeat(40) } };
  let result;
  if (o.op === 'review') result = await reviewHold({ ...base, series: o.series, candidate_sha256: o.candidate, decision: o.reviewDecision, reviewer: o.actor, reviewer_permission: o.permission, permission_checked_at: o.checkedAt, reason: o.reason });
  else if (o.op === 'rollback') result = await rollback({ ...base, to: o.to, reason: o.reason });
  else {
    // A restore rebuilds the live tree from the archive alone (17.5).
    rmSync(join(o.root, 'live'), { recursive: true, force: true });
    result = restore({ ...base, reason: o.reason });
  }
  if (result.outcome === 'failed') throw new Error(`operation failed: ${result.error ?? 'unknown error'}; the store is not written`);
  if (!existsSync(join(o.root, 'live', 'manifest.json'))) throw new Error('operation failed: the working root has no manifest; the store is not written');
  const checker = validate(o.root);
  if (checker.fail !== 0) throw new Error(`validation failed: the independent checker found ${checker.fail} failure(s); the store is not written (${(checker.failures ?? []).join(' | ')})`);
  const record = operationRecord({ run: o.run, operation: o.op, startedAt: now, endedAt: clock(), outcome: result.outcome, checker, live: join(o.root, 'live'), inputs, now });
  const w = writeStore({ root: o.root, state: o.state, run: o.run, record, bodies: [], push: o.push, message: `Stage C operation ${o.run}: ${o.op} ${result.outcome} (private)`, clock, validateStore: o.validateStore ?? null });
  const alerts = join(o.root, 'archive', 'state', 'alerts.json');
  const ledger = existsSync(alerts) ? JSON.parse(readFileSync(alerts, 'utf8')).open.map(({ key, severity, title, body }) => ({ key, severity, title, body })) : [];
  return { outcome: result.outcome, run: o.run, accepted: w.record.accepted, added: w.record.added, commit: w.commit, ledger, plan: result.plan ?? [], refused: result.refused ?? null, error: result.error ?? null };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  try {
    const r = await operate({
      op: arg('--op'),
      state: arg('--state'),
      root: arg('--root'),
      run: arg('--run'),
      actor: process.env.ACTOR,
      permission: process.env.ACTOR_PERMISSION,
      checkedAt: process.env.PERMISSION_CHECKED_AT,
      push: process.argv.includes('--push'),
      manifestSha256: arg('--manifest-sha256'),
      decision: { brief: arg('--brief') ?? 'docs/P26_STAGE_B_ACCEPTANCE_STAGE_C.md', decided_on: arg('--decided-on') ?? '2026-11-19' },
      series: arg('--series'),
      candidate: arg('--candidate'),
      reviewDecision: arg('--decision'),
      reason: arg('--reason'),
      to: arg('--to'),
      snapshot: arg('--snapshot'),
      siteRelease: arg('--site-release'),
      validateStore: (s) => runChecker(['--state', s]),
    });
    if (arg('--summary')) writeFileSync(arg('--summary'), JSON.stringify(r));
    console.log(JSON.stringify({ ...r, ledger: r.ledger.map((a) => a.key), plan: r.plan.map((p) => `${p.action} ${p.key}`) }));
    process.exit(0);
  } catch (e) {
    console.error(e.message);
    process.exit(3);
  }
}
