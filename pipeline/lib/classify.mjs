// Classification of a candidate against the published observations (DATA_CONVENTIONS sections
// 2, 11 and 17.3). The rules describe expected behavior, not guarantees (decision P1): a change
// outside them is never discarded, it holds for a person to review. A candidate with any
// disallowed change holds as a whole (decision P7).
import { canonicalJson } from './canonical.mjs';
import { addDays, daysBetween, previousQuarter } from './calendar.mjs';

const STATISTICS = new Set(['extra.p1', 'extra.p25', 'extra.p75', 'extra.p99', 'extra.volume_usd_billions']);
const DECIMAL_FIELDS = new Set(['value', 'lower', 'upper']);

export const keyOf = (series) => (series.frequency === 'change-point' ? 'effective' : 'period');

/** The members of an observation that a comparison looks at: everything but `released`. */
function members(o) {
  const out = {};
  for (const [k, v] of Object.entries(o)) {
    if (k === 'released' || k === 'period' || k === 'effective') continue;
    if (k === 'extra') for (const [n, x] of Object.entries(v)) out[`extra.${n}`] = x;
    else out[k] = v;
  }
  return out;
}

/** The text a revision record stores for a member (section 10). */
function recordText(field, value) {
  if (value === undefined) return null;
  if (DECIMAL_FIELDS.has(field) || field.startsWith('extra.')) return value;
  return canonicalJson(value);
}

/**
 * Differences between two observation lists in period order, ignoring `released`:
 * { added: [periods], removed: [observations], changed: [{ period, fields: [{ field, before, after }] }] }.
 */
export function diffObservations(published, candidate, key = 'period') {
  const before = new Map(published.map((o) => [o[key], o]));
  const after = new Map(candidate.map((o) => [o[key], o]));
  const added = candidate.filter((o) => !before.has(o[key])).map((o) => o[key]);
  const removed = published.filter((o) => !after.has(o[key]));
  const changed = [];
  for (const [period, a] of after) {
    const b = before.get(period);
    if (!b) continue;
    const x = members(b);
    const y = members(a);
    const fields = [];
    for (const field of [...new Set([...Object.keys(x), ...Object.keys(y)])].sort()) {
      const bt = recordText(field, x[field]);
      const at = recordText(field, y[field]);
      if (bt !== at) fields.push({ field, before: bt, after: at });
    }
    if (fields.length) changed.push({ period, fields });
  }
  return { added, removed, changed };
}

export const isSame = (d) => d.added.length === 0 && d.removed.length === 0 && d.changed.length === 0;

/** Exact test of |new - old| / |old| > ratio on decimal strings (17.3), no floating point. */
export function exceedsRatio(oldText, newText, ratioText) {
  const scale = (t, places) => {
    const neg = t.startsWith('-');
    const [int, frac = ''] = (neg ? t.slice(1) : t).split('.');
    const n = BigInt(int + frac.padEnd(places, '0'));
    return neg ? -n : n;
  };
  const places = Math.max(...[oldText, newText].map((t) => (t.includes('.') ? t.split('.')[1].length : 0)));
  const o = scale(oldText, places);
  const n = scale(newText, places);
  const abs = (x) => (x < 0n ? -x : x);
  if (o === 0n) return n !== 0n;
  const rPlaces = ratioText.includes('.') ? ratioText.split('.')[1].length : 0;
  return abs(n - o) * 10n ** BigInt(rPlaces) > scale(ratioText, rPlaces) * abs(o);
}

const hold = (diff, reason) => ({ outcome: 'revised-unexpected', diff, reason, basis: new Map(), releaseDates: new Map(), large: [] });

/**
 * Classifies one series. `published` and `candidate` are whole observation lists in period
 * order. ctx: { runEtDate, calendar, series, marker, publishedMarker, source } where `source`
 * is the classification of the series this one is derived from (policy targets), with its
 * candidate list.
 * Returns { outcome, diff, reason, basis: Map(period -> text), releaseDates: Map(period -> date|null), large: [periods] }.
 */
export function classify(series, published, candidate, ctx) {
  const key = keyOf(series);
  const diff = diffObservations(published, candidate, key);
  const base = { diff, reason: null, basis: new Map(), releaseDates: new Map(), large: [] };
  if (published.length === 0) return { ...base, outcome: candidate.length ? 'appended' : 'unchanged' };
  const last = published[published.length - 1][key];
  const insideHistory = diff.added.filter((p) => p <= last);

  if (series.class === 'policy_target') {
    if (ctx.source?.outcome === 'revised-unexpected' && !isSame(diff)) return hold(diff, 'derived from a held series');
    if (isSame(diff)) return { ...base, outcome: 'unchanged' };
    if (diff.removed.length === 0 && diff.changed.length === 0 && insideHistory.length === 0) return { ...base, outcome: 'appended' };
    // A corrected EFFR record can move a change point by one record (2.2).
    const allowed = new Map();
    const src = ctx.source;
    if (src?.outcome === 'revised-expected') {
      const periods = src.candidate.map((o) => o.period);
      for (const c of src.diff.changed) {
        const text = src.basis.get(c.period);
        allowed.set(c.period, text);
        const next = periods[periods.indexOf(c.period) + 1];
        if (next !== undefined && !allowed.has(next)) allowed.set(next, text);
      }
    }
    const touched = [...diff.removed.map((o) => o[key]), ...insideHistory, ...diff.changed.map((c) => c.period)];
    if (!touched.every((p) => allowed.has(p))) return hold(diff, 'a change point changed, moved or disappeared');
    for (const p of touched) {
      base.basis.set(p, allowed.get(p));
      base.releaseDates.set(p, null);
    }
    return { ...base, outcome: 'revised-expected' };
  }

  if (isSame(diff)) return { ...base, outcome: 'unchanged' };
  if (diff.removed.length) return hold(diff, 'a published period was removed');
  if (insideHistory.length) return hold(diff, 'a new period on or before the last published period');

  if (series.class === 'administrative_daily') {
    if (diff.changed.length) return hold(diff, 'a published value changed and no revision is expected for this series');
    return { ...base, outcome: 'appended' };
  }

  if (series.class === 'revised_aggregate') {
    const latest = ctx.marker?.latest_release_date;
    const seen = ctx.publishedMarker?.data_release_date;
    if (!(typeof latest === 'string' && typeof seen === 'string' && latest > seen)) return hold(diff, 'the data changed without a new release date');
    if (diff.changed.length === 0) return { ...base, outcome: 'appended' };
    for (const c of diff.changed) {
      base.basis.set(c.period, `H.6 release ${latest}`);
      base.releaseDates.set(c.period, latest);
      const v = c.fields.find((f) => f.field === 'value');
      if (v && v.before !== null && v.after !== null && exceedsRatio(v.before, v.after, series.revision.alert_ratio)) base.large.push(c.period);
    }
    return { ...base, outcome: 'revised-expected' };
  }

  // market_observation (2.1).
  if (diff.changed.length === 0) return { ...base, outcome: 'appended' };
  const { calendar, runEtDate } = ctx;
  const byPeriod = new Map(candidate.map((o) => [o.period, o]));
  const quarter = previousQuarter(runEtDate);
  const inStatisticsWindow = () => runEtDate >= calendar.addBusinessDays(quarter.end, 1) && runEtDate <= calendar.addBusinessDays(quarter.end, series.revision.statistics_window_business_days);
  for (const c of diff.changed) {
    const age = daysBetween(c.period, runEtDate);
    let text = null;
    let released = null;
    // Only a period of the last few days can be on, or just after, its publication day.
    if (age >= 0 && age <= 15) {
      const pub = calendar.publicationDay(c.period);
      if (runEtDate === pub) {
        text = `EFFR publication day ${pub}`;
        released = pub;
      } else if (byPeriod.get(c.period).flags.includes('r') && runEtDate > pub && runEtDate <= calendar.addBusinessDays(pub, 2)) {
        text = `EFFR revision flagged r within 2 business days of publication day ${pub}`;
      }
    }
    if (text === null && c.fields.every((f) => STATISTICS.has(f.field)) && c.period >= '2016-03-01' && c.period >= quarter.start && c.period <= quarter.end && addDays(quarter.end, 1) <= runEtDate && inStatisticsWindow()) {
      text = `EFFR quarterly statistics update for the quarter ending ${quarter.end}`;
    }
    if (text === null) return hold(diff, 'a published period changed outside its publication day');
    base.basis.set(c.period, text);
    base.releaseDates.set(c.period, released);
  }
  return { ...base, outcome: 'revised-expected' };
}

/**
 * Revision records for a published change (section 10), in period then field order. `kind` is
 * `expected` or `approved-hold`; `basisFor(period)` and `releaseFor(period)` give the texts.
 * A removed period is one record with field `period`; so is a period inserted into history
 * (before null, after the observation).
 */
export function revisionRecords({ diff, key, published, candidate, last, detectedAt, snapshot, kind, basisFor, releaseFor }) {
  const out = [];
  const pub = new Map(published.map((o) => [o[key], o]));
  const cand = new Map(candidate.map((o) => [o[key], o]));
  const rec = (period, field, before, after) => out.push({ detected_at: detectedAt, snapshot, period, field, before, after, kind, basis: basisFor(period), release_date: releaseFor(period) ?? null });
  for (const o of diff.removed) rec(o[key], 'period', canonicalJson(o), null);
  for (const p of diff.added) if (last !== null && p <= last) rec(p, 'period', null, canonicalJson(cand.get(p)));
  for (const c of diff.changed) for (const f of c.fields) rec(c.period, f.field, f.before, f.after);
  void pub;
  return out.sort((a, b) => (a.period < b.period ? -1 : a.period > b.period ? 1 : a.field < b.field ? -1 : a.field > b.field ? 1 : 0));
}
