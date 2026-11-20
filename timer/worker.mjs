// The Stage C timer (DATA_CONVENTIONS 21.3, decision P43): a Cloudflare Worker whose cron
// trigger, the one line 17 */4 * * * (UTC), dispatches the collect workflow of
// RadMageIRL/finance-data in mode timer with the slot it fired for, so every scheduled run names
// its slot. It holds one secret, GITHUB_TOKEN: a fine-grained token for that repository alone with
// Actions read and write (it can start, cancel or re-run workflows, never write the state store).
// It has no fetch handler and no route. The pause switch stays on GitHub: while
// COLLECTION_SCHEDULE_ENABLED is not "true", the dispatched run's collect job is skipped.
// Deployed as the Worker finance-collect-timer.

const DISPATCH_URL = 'https://api.github.com/repos/RadMageIRL/finance-data/actions/workflows/collect.yml/dispatches';
const RETRY_WAITS_MS = [5000, 30000];

/** The slot as the workflow input expects it: UTC, whole seconds, YYYY-MM-DDTHH:MM:SSZ. */
export function slotOf(scheduledTime) {
  return new Date(scheduledTime).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/** Network errors, 429 and 5xx are retried; any other status is final. */
export function retryable(status) {
  return status === 0 || status === 429 || status >= 500;
}

export async function dispatchSlot({ token, slot, request = fetch, wait = (ms) => new Promise((r) => setTimeout(r, ms)), log = console }) {
  if (!token) throw new Error(`timer ${slot}: the secret GITHUB_TOKEN is not set`);
  for (let attempt = 1; ; attempt += 1) {
    let status = 0;
    try {
      const res = await request(DISPATCH_URL, {
        method: 'POST',
        headers: {
          Accept: 'application/vnd.github+json',
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'User-Agent': 'radmage-finance-timer',
          'X-GitHub-Api-Version': '2022-11-28',
        },
        body: JSON.stringify({ ref: 'main', inputs: { mode: 'timer', slot } }),
      });
      status = res.status;
      if (status === 204 || status === 200) {
        log.log(`timer ${slot}: dispatched, HTTP ${status}, attempt ${attempt}`);
        return { slot, status, attempt };
      }
      const text = (await res.text()).slice(0, 300);
      log.error(`timer ${slot}: HTTP ${status} on attempt ${attempt}: ${text}`);
    } catch (e) {
      log.error(`timer ${slot}: request failed on attempt ${attempt}: ${e && e.message ? e.message : e}`);
    }
    if (!retryable(status) || attempt > RETRY_WAITS_MS.length) {
      throw new Error(`timer ${slot}: dispatch failed after ${attempt} attempt(s), last HTTP ${status || 'none'}`);
    }
    await wait(RETRY_WAITS_MS[attempt - 1]);
  }
}

export default {
  async scheduled(controller, env) {
    await dispatchSlot({ token: env.GITHUB_TOKEN, slot: slotOf(controller.scheduledTime) });
  },
};
