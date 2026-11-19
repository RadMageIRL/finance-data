// Freshness at a run's time (DATA_CONVENTIONS v0.7 section 21.4): per series the status the
// accepted manifest gives for held, frozen and not-yet-published series, otherwise `stale` at or
// after the series' staleness time (the rule the manifest's `stale` status and the
// `stale:<series>` alert use, measured from the 14.2 deadline of its next unseen period), else
// `fresh`; and `expected_next_update_by` at that time. Pure: no file is read here.
import { deadlines } from './tree.mjs';

/**
 * { registry, calendar, manifest, snapshot, now } -> { freshness, expected_next_update_by }.
 * `manifest` and `snapshot` are the accepted ones after the run (the snapshot the manifest names).
 */
export function freshnessAt({ registry, calendar, manifest, snapshot, now }) {
  const times = {};
  for (const s of registry.series) {
    const st = snapshot.series[s.id];
    if (st && st.status !== 'not-yet-published') times[s.id] = deadlines(s, st, registry, calendar);
  }
  const out = [];
  let earliest = null;
  for (const s of registry.series) {
    const shown = manifest.series[s.id]?.status;
    const st = snapshot.series[s.id];
    const own = times[s.id] ?? null;
    let status;
    if (shown === 'held' || shown === 'frozen' || shown === 'not-yet-published') status = shown;
    else {
      // A series whose staleness follows another uses that series' staleness time (4.4).
      const t = s.staleness.follows !== undefined ? times[s.staleness.follows] : own;
      status = t && now >= t.staleAt ? 'stale' : 'fresh';
    }
    if (own && shown !== 'held' && shown !== 'frozen' && (earliest === null || own.deadline < earliest)) earliest = own.deadline;
    out.push({ series: s.id, status, last_period: st?.last_period ?? null, deadline: own ? own.deadline : null });
  }
  // With no series that qualifies, the next update is due at once (17.3, 21.4).
  return { freshness: out, expected_next_update_by: earliest ?? now };
}
