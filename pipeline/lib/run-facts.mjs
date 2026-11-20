// Which runs of the collect workflow are scheduled runs (DATA_CONVENTIONS 21.3, amendment 1 to
// v0.7, decision P43): a run with the event `schedule`, or the event `workflow_dispatch` and a
// title starting `collect timer ` (the Cloudflare timer names its slot in the title). Turns the
// GitHub REST API's workflow runs into the run facts of 14.3, with `event` given as `schedule` for
// every scheduled run. collect.yml applies the same rule in its facts step (jq).

export const TIMER_TITLE_PREFIX = 'collect timer ';

/** True for a scheduled run of the collect workflow (21.3). */
export function isScheduledRun(run) {
  if (run.event === 'schedule') return true;
  return run.event === 'workflow_dispatch' && typeof run.display_title === 'string' && run.display_title.startsWith(TIMER_TITLE_PREFIX);
}

/** The run facts of 14.3 from the API's `workflow_runs`, newest first as the API lists them. */
export function runFacts(workflowRuns) {
  return workflowRuns.map((r) => ({ event: isScheduledRun(r) ? 'schedule' : r.event, conclusion: r.conclusion ?? null, created_at: r.created_at }));
}
