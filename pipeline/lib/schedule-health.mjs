// Schedule health (DATA_CONVENTIONS section 14.3, owner decision D7): a pure evaluation of facts
// gathered outside the collector (GitHub REST API workflow state, the repository's pushed_at,
// the workflow's runs, the live manifest). It needs no person to commit anything; whoever runs
// it (see docs/P22_DESIGN.md section 5) turns findings into alerts.

/** PROPOSED thresholds (owner approval pending, D6 and D7). */
export const DEFAULT_THRESHOLDS = {
  inactivityWarningDays: 45,
  inactivityCriticalDays: 55,
  runGapWarningHours: 26,
  runGapCriticalHours: 50,
  consecutiveFailures: 3,
  overdueCriticalHours: 24,
};

const HOUR = 3_600_000;
const DAY = 24 * HOUR;
const SEVERITY_ORDER = { critical: 0, warning: 1 };

function time(value, name) {
  const t = Date.parse(value);
  if (!Number.isFinite(t)) throw new TypeError(`${name}: not a time (${value})`);
  return t;
}

/**
 * input: {
 *   now: ISO time,
 *   workflow: { state: 'active' | 'disabled_inactivity' | 'disabled_manually' | ... },
 *   repository: { pushed_at: ISO time },
 *   runs: [{ event: 'schedule' | 'workflow_dispatch' | ..., conclusion: 'success' | 'failure' | ..., created_at }] newest first,
 *   manifest: null | { health: { expected_next_update_by }, series: { [id]: { status, status_reason } } },
 * }
 * Returns findings sorted by severity, then key: [{ key, severity, message }].
 */
export function scheduleHealth(input, thresholds = DEFAULT_THRESHOLDS) {
  const t = { ...DEFAULT_THRESHOLDS, ...thresholds };
  const now = time(input.now, 'now');
  const findings = [];
  const add = (key, severity, message) => findings.push({ key, severity, message });

  if (input.workflow?.state !== 'active') add('workflow-disabled', 'critical', `The collector workflow is ${input.workflow?.state ?? 'unknown'}, not active.`);

  const idleDays = Math.floor((now - time(input.repository.pushed_at, 'repository.pushed_at')) / DAY);
  if (idleDays >= t.inactivityCriticalDays) add('inactivity', 'critical', `No repository activity for ${idleDays} days; GitHub disables scheduled workflows after 60.`);
  else if (idleDays >= t.inactivityWarningDays) add('inactivity', 'warning', `No repository activity for ${idleDays} days; GitHub disables scheduled workflows after 60.`);

  const runs = input.runs ?? [];
  const scheduled = runs.filter((r) => r.event === 'schedule');
  const lastGood = scheduled.find((r) => r.conclusion === 'success');
  // With no successful scheduled run listed, measure from the oldest run listed (or flag at once).
  const since = lastGood ? time(lastGood.created_at, 'run.created_at') : runs.length ? time(runs[runs.length - 1].created_at, 'run.created_at') : null;
  if (since === null) add('scheduled-run-gap', 'critical', 'No runs are listed for the collector workflow.');
  else {
    const hours = (now - since) / HOUR;
    const what = lastGood ? 'since the last successful scheduled run' : 'with no successful scheduled run listed';
    if (hours > t.runGapCriticalHours) add('scheduled-run-gap', 'critical', `${Math.floor(hours)} hours ${what}.`);
    else if (hours > t.runGapWarningHours) add('scheduled-run-gap', 'warning', `${Math.floor(hours)} hours ${what}.`);
  }

  let failures = 0;
  for (const r of runs) {
    if (r.conclusion === 'failure' || r.conclusion === 'timed_out') failures += 1;
    else if (r.conclusion === 'success') break;
    // Cancelled, skipped or still running runs neither count nor break the streak.
  }
  if (failures >= t.consecutiveFailures) add('consecutive-failures', 'critical', `The last ${failures} runs failed.`);

  if (!input.manifest) add('manifest-missing', 'critical', 'The live manifest could not be read.');
  else {
    const due = time(input.manifest.health.expected_next_update_by, 'manifest.health.expected_next_update_by');
    if (now > due) {
      const late = (now - due) / HOUR;
      add('manifest-overdue', late > t.overdueCriticalHours ? 'critical' : 'warning', `The next update was due ${Math.floor(late)} hours ago (${input.manifest.health.expected_next_update_by}).`);
    }
    for (const [id, s] of Object.entries(input.manifest.series ?? {}).sort(([a], [b]) => (a < b ? -1 : 1))) {
      if (s.status === 'stale') add(`series-stale:${id}`, 'warning', `${id} is stale${s.status_reason ? `: ${s.status_reason}` : ''}.`);
      if (s.status === 'held') add(`series-held:${id}`, 'warning', `${id} is held for review${s.status_reason ? `: ${s.status_reason}` : ''}.`);
    }
  }

  return findings.sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
}
