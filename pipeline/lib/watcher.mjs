// The independent daily watcher (DATA_CONVENTIONS section 17.8, decision P4, layer 3). It uses
// none of the collector's state: only facts gathered from outside (the collector workflow's
// state, the repository's pushed_at, the run list, and the live manifest as fetched), so it
// still reports when the data repository's schedule has stopped. It keeps its own ledger and
// only plans issues: no commit, no push, no re-enabling.
import { scheduleHealth } from './schedule-health.mjs';
import { healthAlerts, planIssues } from './alerts.mjs';

/**
 * facts: { now, workflow, repository, runs, manifest } as schedule-health.mjs takes them
 * (manifest null when it could not be read). ledger: the watcher's own ledger or null.
 * Returns { findings, ledger, plan }.
 */
export function watch(facts, ledger = null) {
  const findings = scheduleHealth(facts);
  const { ledger: next, plan } = planIssues(ledger, healthAlerts(findings), facts.now);
  return { findings, ledger: next, plan };
}
