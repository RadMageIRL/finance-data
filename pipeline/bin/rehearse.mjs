#!/usr/bin/env node
// Rehearsal of review authorization, rollback, restore and clearing a lock, on fixtures only
// (DATA_CONVENTIONS 11.5 and 17.5). Writes the appendix B scenario into <dir>/scenario, then, in a
// copy at <dir>/authorization, tries to clear one of the scenario's rollback locks twice: once as
// an account with read access only, which must be refused, and once as the account and permission
// given (in a workflow: the triggering account and the permission GitHub reports for it), which
// must succeed exactly when that permission is one the registry allows. Nothing is collected.
//
//   REVIEWER=<login> REVIEWER_PERMISSION=<permission> node pipeline/bin/rehearse.mjs <dir>
import { cpSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadInputs, runScenario } from './fixture-scenario.mjs';
import { reviewHold } from '../lib/run.mjs';

const AUTOMATION = /(\[bot\]$|^github-actions$)/i;

export async function rehearse(dir, { reviewer, permission }) {
  const scenario = join(dir, 'scenario');
  const auth = join(dir, 'authorization');
  const { log } = await runScenario(scenario);
  cpSync(scenario, auth, { recursive: true });
  const inputs = loadInputs();
  const base = { root: auth, mode: 'fixture', registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays };
  const lock = JSON.parse(readFileSync(join(auth, 'archive', 'state', 'review-queue.json'), 'utf8')).frozen.find((f) => f.series === 'm2-sa');
  const attempt = (now, id, who, perm) => reviewHold({ ...base, now, run: { id, attempt: 1, trigger: 'manual', collector_commit: '0'.repeat(40) }, series: 'm2-sa', candidate_sha256: lock.candidate_sha256, decision: 'clear', reviewer: who, reviewer_permission: perm, permission_checked_at: now, reason: 'Rehearsal on fixtures: clearing a rollback lock.' });
  const reader = await attempt('2026-11-25T16:00:00Z', 'rehearsal-reader', 'rehearsal-reader', 'read');
  const given = await attempt('2026-11-25T16:05:00Z', 'rehearsal-given', reviewer, permission);
  const allowed = inputs.registry.family_policy.review.permissions.includes(permission) && !AUTOMATION.test(reviewer);
  const ok = reader.outcome === 'refused' && reader.refused === 'permission' && (allowed ? given.outcome === 'published' : given.outcome === 'refused');
  return { ok, steps: log.length, reader: { outcome: reader.outcome, refused: reader.refused ?? null }, given: { permission, allowed, outcome: given.outcome, refused: given.refused ?? null } };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const dir = process.argv[2];
  if (!dir) {
    console.error('usage: REVIEWER=<login> REVIEWER_PERMISSION=<permission> node pipeline/bin/rehearse.mjs <dir>');
    process.exit(2);
  }
  const r = await rehearse(dir, { reviewer: process.env.REVIEWER || 'local-rehearsal', permission: process.env.REVIEWER_PERMISSION || 'admin' });
  console.log(JSON.stringify(r));
  process.exit(r.ok ? 0 : 1);
}
