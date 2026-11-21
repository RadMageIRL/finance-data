// The Stage C timer (DATA_CONVENTIONS 21.3 and 21.9, decision P43): the Cloudflare Worker
// finance-collect-timer. Its cron line 17 */4 * * * (UTC) dispatches the collect workflow of
// RadMageIRL/finance-data in mode timer with the slot it fired for; its cron line 47 2-22/4 * * *
// dispatches the watch workflow with the slot. The minute of the scheduled time decides which
// (17 collect, 47 watch), so the routing does not depend on how the cron line is spelled back.
// One secret, GITHUB_TOKEN: a fine-grained token for that repository alone with Actions read and
// write (it can start, cancel or re-run workflows, never touch the state store). No fetch handler
// and no route. The pause switch stays on GitHub: while COLLECTION_SCHEDULE_ENABLED is not
// "true", a dispatched collect run's job is skipped.

export const REPOSITORY = 'RadMageIRL/finance-data';
export const CRON_LINES = ['17 */4 * * *', '47 2-22/4 * * *'];
const RETRY_WAITS_MS = [5000, 30000];

/**
 * The slot as the workflow inputs expect it: the firing's cron minute, UTC, YYYY-MM-DDTHH:MM:00Z.
 * Cloudflare's scheduledTime can carry seconds (the test firing of 2026-11-20 13:56 UTC gave
 * 13:56:04), so it is truncated to its minute.
 */
export function slotOf(scheduledTime) {
  return new Date(Math.floor(scheduledTime / 60_000) * 60_000).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/** The workflow and inputs a firing dispatches, by the minute of its slot. */
export function targetFor(slot) {
  const minute = slot.slice(14, 19);
  if (minute === '17:00') return { workflow: 'collect.yml', inputs: { mode: 'timer', slot } };
  if (minute === '47:00') return { workflow: 'watch.yml', inputs: { slot } };
  // v0.8 (22.6, D2 (c)): timer publication on the third cron line `37 */4 * * *`, which is not in
  // CRON_LINES and not deployed before gate 22; publish.yml refuses a timer run unless
  // PUBLICATION_ENABLED and PUBLICATION_SCHEDULE_ENABLED are true and nothing pauses it.
  if (minute === '37:00') return { workflow: 'publish.yml', inputs: { mode: 'timer' } };
  throw new Error(`timer ${slot}: no workflow is dispatched at this minute`);
}

/** Network errors, 429 and 5xx are retried; any other status is final. */
export function retryable(status) {
  return status === 0 || status === 429 || status >= 500;
}

export async function dispatchSlot({ token, slot, request = fetch, wait = (ms) => new Promise((r) => setTimeout(r, ms)), log = console }) {
  const { workflow, inputs } = targetFor(slot);
  if (!token) throw new Error(`timer ${slot}: the secret GITHUB_TOKEN is not set`);
  const url = `https://api.github.com/repos/${REPOSITORY}/actions/workflows/${workflow}/dispatches`;
  for (let attempt = 1; ; attempt += 1) {
    let status = 0;
    try {
      const res = await request(url, {
        method: 'POST',
        headers: {
          Accept: 'application/vnd.github+json',
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'User-Agent': 'radmage-finance-timer',
          'X-GitHub-Api-Version': '2022-11-28',
        },
        body: JSON.stringify({ ref: 'main', inputs }),
      });
      status = res.status;
      if (status === 204 || status === 200) {
        log.log(`timer ${slot}: ${workflow} dispatched, HTTP ${status}, attempt ${attempt}`);
        return { slot, workflow, status, attempt };
      }
      const text = (await res.text()).slice(0, 300);
      log.error(`timer ${slot}: ${workflow} HTTP ${status} on attempt ${attempt}: ${text}`);
    } catch (e) {
      log.error(`timer ${slot}: ${workflow} request failed on attempt ${attempt}: ${e && e.message ? e.message : e}`);
    }
    if (!retryable(status) || attempt > RETRY_WAITS_MS.length) {
      throw new Error(`timer ${slot}: ${workflow} dispatch failed after ${attempt} attempt(s), last HTTP ${status || 'none'}`);
    }
    await wait(RETRY_WAITS_MS[attempt - 1]);
  }
}

export default {
  async scheduled(controller, env) {
    await dispatchSlot({ token: env.GITHUB_TOKEN, slot: slotOf(controller.scheduledTime) });
  },
};
