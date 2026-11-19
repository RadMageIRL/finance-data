// The published files of a run (DATA_CONVENTIONS sections 6 to 10, 14.2 and 16): objects per
// segment, CSVs, revision log versions, the snapshot and the manifest. Pure functions: bytes in
// the result depend only on the arguments.
import { canonicalJson, objectAddress, sha256Hex } from './canonical.mjs';
import { addHours, etClock, etDate, nextFourthTuesdayAfter, zonedTime } from './calendar.mjs';
import { keyOf } from './classify.mjs';

const ET = 'America/New_York';
export const SCHEDULE = ['17 * * * 1-5', '17 15 * * 0,6'];
export const PAGES_WINDOW_DAYS = 35;
/** Fiscal Data's publication time when no calendar entry was collected (17.3). */
export const FISCAL_DATA_TIME = '21:15';

const bytes = (text) => Buffer.byteLength(text, 'utf8');
export const fileRef = (path, text) => ({ path, sha256: sha256Hex(text), bytes: bytes(text) });

export function fill(text, values) {
  return text === null ? null : text.replace(/\{([a-z_]+)\}/g, (_, k) => values[k]);
}

/** One object per segment (section 7): a year of periods, or everything. */
export function buildObjects(series, observations) {
  const key = keyOf(series);
  const groups = new Map();
  for (const o of observations) {
    const segment = series.segment === 'year' ? o[key].slice(0, 4) : 'all';
    if (!groups.has(segment)) groups.set(segment, []);
    groups.get(segment).push(o);
  }
  return [...groups.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([segment, list]) => {
    const a = objectAddress({ schema: 'rmf.econ.object/1', series: series.id, segment, observations: list });
    return { segment, path: a.path, sha256: a.sha256, bytes: a.bytes, text: a.text, observations: list };
  });
}

/**
 * The CSV of one segment of a series (section 16), exact to the byte: the observations of one
 * object, with the retrieval time of that segment.
 */
export function csvSegment(series, source, segment, observations, retrievedAt) {
  const values = { year: etDate(retrievedAt).slice(0, 4), data_name: series.data_name };
  const unit = series.unit.replace(/-/g, '_');
  const key = keyOf(series);
  const lines = [
    `# ${series.title} (${series.unit_label})`,
    `# ${fill(source.attribution, values)}`,
    ...(source.notice ? [`# ${fill(source.notice, values)}`] : []),
    `# Terms: ${source.terms_url}`,
    ...(series.derived_from ? [`# ${series.derived_from.method}`] : []),
    `# Segment ${segment}: ${observations[0][key]} to ${observations[observations.length - 1][key]}.`,
    `# Retrieved ${retrievedAt} by RadMage Finance.`,
  ];
  const rel = (o) => `${o.released.date ?? ''},${o.released.basis}`;
  if (series.frequency === 'change-point') {
    lines.push(`effective,kind,value_${unit},lower_${unit},upper_${unit},released,released_basis`);
    for (const o of observations) lines.push(`${o.effective},${o.kind},${o.value ?? ''},${o.lower ?? ''},${o.upper ?? ''},${rel(o)}`);
  } else {
    const withCode = series.extract.some((e) => e.null_text !== undefined || e.missing_codes !== undefined);
    lines.push(`period,value_${unit}${withCode ? ',missing_code' : ''},released,released_basis`);
    for (const o of observations) lines.push(`${o.period},${o.value ?? ''}${withCode ? `,${o.missing?.code ?? ''}` : ''},${rel(o)}`);
  }
  const text = `${lines.join('\n')}\n`;
  const sha256 = sha256Hex(text);
  return { segment, path: `series/${series.id}/${segment}/${sha256.slice(0, 16)}.csv`, sha256, bytes: bytes(text), text, retrieved_at: retrievedAt };
}

/**
 * The CSV segments of a series (16, 12.9): one per object. A segment whose object is the one
 * the replaced manifest's snapshot named keeps that manifest's retrieval time for it; every
 * other segment takes `retrievedAt`. `objects` carry their observations (buildObjects);
 * `prior` is { objects, csvs } of the series in the manifest being replaced, or null.
 */
export function csvSegments(series, source, objects, retrievedAt, prior) {
  return objects.map((o) => {
    const before = prior?.objects?.find((x) => x.segment === o.segment);
    const csv = prior?.csvs?.find((x) => x.segment === o.segment);
    const at = before && csv && before.sha256 === o.sha256 ? csv.retrieved_at : retrievedAt;
    return csvSegment(series, source, o.segment, o.observations, at);
  });
}

/** A revision log version (section 10): the previous records plus new ones at the end. */
export function revisionLog(seriesId, year, previousRecords, newRecords) {
  const text = canonicalJson({ schema: 'rmf.econ.revisions/1', series: seriesId, year, records: [...previousRecords, ...newRecords] });
  const sha256 = sha256Hex(text);
  return { path: `revisions/${seriesId}/${year}/${sha256.slice(0, 16)}.json`, sha256, bytes: bytes(text), text };
}

/** The readings of a calendar's publication zone (4.5): one zone, or the candidates of an unknown one. */
export const zoneReadings = (cal) => (cal.publish_time_zone === 'unknown' ? cal.publish_time_zone_candidates : [cal.publish_time_zone]);

/** The earliest and latest instants of a clock time on a date, over the zone's readings (4.5). */
export function readings(date, clock, cal) {
  const times = zoneReadings(cal).map((z) => zonedTime(date, clock, z)).sort();
  return { earliest: times[0], latest: times[times.length - 1] };
}

/** The next unseen period of a business-day series after `last`: documented gaps are skipped (14.2). */
export function nextUnseen(series, last, calendar) {
  const gaps = new Set((series.known_gaps ?? []).map((g) => g.period));
  let d = calendar.nextBusinessDay(last);
  while (gaps.has(d)) d = calendar.nextBusinessDay(d);
  return d;
}

/**
 * The publication of business-day period P (14.2, 11.6): { expected, deadline }, `expected` at
 * the earliest reading of the zone (when to look) and `deadline` at the latest plus the grace hours.
 */
export function periodDeadline(series, period, registry, calendar) {
  const cal = registry.calendars[series.release.calendar];
  const day = series.class === 'market_observation' ? calendar.publicationDay(period) : calendar.nextBusinessDay(period);
  const r = readings(day, cal.publish_time ?? FISCAL_DATA_TIME, cal);
  return { expected: r.earliest, deadline: addHours(r.latest, cal.grace_hours) };
}

/**
 * Publication times for the next unseen period of a published series (14.2):
 * { expected, deadline, staleAt } as stored times, or null for a series that follows another.
 * `expected` uses the earliest reading of an unknown zone; the deadline and staleness the latest.
 */
export function deadlines(series, state, registry, calendar) {
  const cal = registry.calendars[series.release.calendar];
  if (series.class === 'policy_target') return null;
  let expected;
  let deadline;
  if (series.class === 'market_observation' || series.class === 'administrative_daily') {
    ({ expected, deadline } = periodDeadline(series, nextUnseen(series, state.last_period, calendar), registry, calendar));
  } else {
    const r = readings(nextFourthTuesdayAfter(state.source_marker.data_release_date), cal.publish_time, cal);
    expected = r.earliest;
    deadline = addHours(r.latest, cal.grace_hours);
  }
  let staleAt;
  if (series.staleness.after_business_days !== undefined) staleAt = zonedTime(calendar.addBusinessDays(etDate(deadline), series.staleness.after_business_days), etClock(deadline), ET);
  else staleAt = addHours(deadline, 24 * series.staleness.after_days_past_expected_release);
  return { expected, deadline, staleAt };
}

/** The last value, range and release of a series' observations, for the manifest (section 9). */
export function lastSummary(series, observations) {
  if (observations.length === 0) return { last_period: null, last_value: null, last_range: null, last_released: null };
  const o = observations[observations.length - 1];
  const range = o.kind === 'range';
  return { last_period: o[keyOf(series)], last_value: range ? null : o.value, last_range: range ? { lower: o.lower, upper: o.upper } : null, last_released: o.released };
}

/**
 * The manifest (section 9). `parts[id]` = { observations, csvs: [refs with segment and retrieved_at], revisions: [refs] }.
 */
export function buildManifest({ registry, snapshot, snapshotRef, parts, now, previousSnapshot, rollback, locks = null, pinned, calendar }) {
  const series = {};
  const times = {};
  for (const s of registry.series) {
    const st = snapshot.series[s.id];
    if (st.status !== 'not-yet-published') times[s.id] = deadlines(s, st, registry, calendar);
  }
  const heldReason = new Map(snapshot.holds.map((h) => [h.series, h.reason]));
  // The locks in force (11.5): the snapshot's, plus those of the rollback this manifest records.
  // A rollback passes every lock in force after it (v0.6); otherwise the snapshot's, plus those of
  // the rollback this manifest records. A series with several locks shows the newest one's reason.
  const frozen = new Map();
  for (const f of [...(locks ?? snapshot.frozen ?? [])].sort((a, b) => (a.frozen_at < b.frozen_at ? -1 : 1))) frozen.set(f.series, { origin: 'rejected', ...f });
  if (!locks) for (const id of rollback?.locked ?? []) if (!frozen.has(id)) frozen.set(id, { series: id, origin: 'rolled-back', frozen_at: rollback.at, reason: rollback.reason });
  const staleOf = (s) => {
    const t = s.staleness.follows !== undefined ? times[s.staleness.follows] : times[s.id];
    return t ? now >= t.staleAt : false;
  };
  let earliest = null;
  for (const s of registry.series) {
    const st = snapshot.series[s.id];
    const source = registry.sources[s.source];
    const p = parts[s.id];
    let status;
    let reason = null;
    if (st.status === 'not-yet-published') {
      status = 'not-yet-published';
      reason = 'no data published yet';
    } else if (st.status === 'held') {
      status = 'held';
      reason = heldReason.get(s.id) ?? 'held for review';
    } else if (frozen.has(s.id)) {
      status = 'frozen';
      const f = frozen.get(s.id);
      reason = f.origin === 'rolled-back'
        ? `rolled back on ${etDate(f.frozen_at)}; nothing of the withdrawn data is published until a person with write access clears the lock: ${f.reason}`
        : `a proposed revision was rejected on ${etDate(f.frozen_at)} and the source still carries it: ${f.reason}`;
    } else if (staleOf(s)) {
      status = 'stale';
      const followed = s.staleness.follows;
      reason = followed !== undefined ? `follows ${followed}, which is stale` : `no new period after ${st.last_period}; expected by ${times[s.id].deadline}`;
    } else status = 'fresh';
    if (times[s.id] && st.status !== 'held' && !frozen.has(s.id) && (earliest === null || times[s.id].deadline < earliest)) earliest = times[s.id].deadline;
    const values = { year: etDate(st.retrieved_at ?? now).slice(0, 4), data_name: s.data_name };
    series[s.id] = {
      title: s.title,
      unit_label: s.unit_label,
      frequency: s.frequency,
      class: s.class,
      objects: st.objects.map((o) => ({ path: o.path, sha256: o.sha256 })),
      csvs: (p.csvs ?? []).map((c) => ({ segment: c.segment, path: c.path, sha256: c.sha256, retrieved_at: c.retrieved_at })),
      revisions: p.revisions.map((r) => ({ path: r.path, sha256: r.sha256 })),
      ...lastSummary(s, p.observations),
      retrieved_at: st.retrieved_at,
      checked_at: st.checked_at,
      status,
      status_reason: reason,
      attribution: fill(source.attribution, values),
      notice: fill(source.notice, values),
    };
  }
  const manifest = {
    schema: 'rmf.econ.manifest/3',
    generated_at: now,
    snapshot: { id: snapshot.id, path: snapshotRef.path, sha256: snapshotRef.sha256 },
    previous_snapshot: previousSnapshot,
    rollback,
    series,
    // With no published series that is not held, the manifest is due at once (17.3).
    health: { schedule: SCHEDULE, expected_next_update_by: earliest ?? now },
    pages_window: { days: PAGES_WINDOW_DAYS, pinned: [...pinned].sort() },
  };
  return { manifest, text: canonicalJson(manifest) };
}

/** Snapshot notices: the registry texts with their placeholders kept (section 8). */
export function snapshotNotices(registry) {
  return Object.fromEntries(Object.entries(registry.sources).map(([k, s]) => [k, { attribution: s.attribution, notice: s.notice, terms_url: s.terms_url }]));
}

export const registryHash = (registry) => sha256Hex(canonicalJson(registry));

/** A hold candidate: the canonical JSON of all its observations (11.5). */
export function holdCandidate(seriesId, observations, openedAt) {
  const text = canonicalJson(observations);
  const sha256 = sha256Hex(text);
  const month = etDate(openedAt).slice(0, 7);
  return { text, sha256, bytes: bytes(text), local: `holds/${seriesId}/${sha256.slice(0, 16)}.json`, archive_asset: `archive-${month}/hold-${seriesId}-${sha256.slice(0, 16)}.json` };
}
