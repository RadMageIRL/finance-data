// Source responses to candidate observations (DATA_CONVENTIONS sections 5, 6 and 11.3, 11.4).
// A response is untrusted data: it is checked field for field against the schema in force for
// each record's date and never executed. A format failure makes the whole response invalid
// (every series it feeds); the per-series checks live in validateSeries.
import { checkRecord, decimalFromNumber } from './source-records.mjs';
import { compareDecimal } from './registry-policy.mjs';
import { addDays, daysBetween, weekday } from './calendar.mjs';

const DECIMAL_TEXT = /^-?\d+(\.\d+)?$/;
const EXTRA_DECIMALS = { volume_usd_billions: 0 };

/** A decimal string padded to exactly `decimals` places; throws on more precision. */
export function padDecimal(text, decimals) {
  if (typeof text !== 'string' || !DECIMAL_TEXT.test(text)) throw new RangeError(`${text}: not a decimal string`);
  const [int, frac = ''] = text.split('.');
  if (frac.length > decimals) throw new RangeError(`${text}: more than ${decimals} decimals`);
  return decimals === 0 ? int : `${int}.${frac.padEnd(decimals, '0')}`;
}

const eraFor = (series, period) => series.extract.find((e) => e.from <= period && (e.to === null || period <= e.to));
const byId = (registry, id) => registry.series.find((s) => s.id === id);

/**
 * New York Fed EFFR response to the `effr` observations and the `fomc-target` change points.
 * Returns { problems, series: { effr: [...], 'fomc-target': [...] } }; problems are format
 * failures of the whole response.
 */
export function normalizeEffr(body, registry, table, { start = null } = {}) {
  const problems = [];
  const effr = byId(registry, 'effr');
  const target = byId(registry, 'fomc-target');
  const records = body?.refRates;
  if (!Array.isArray(records)) return { problems: ['refRates is not a list'], series: {} };
  const observations = [];
  for (const r of records) {
    const { problems: p } = checkRecord(table, 'nyfed-markets', r);
    if (p.length) {
      problems.push(...p);
      continue;
    }
    const period = r.effectiveDate;
    if (start !== null && period < start) problems.push(`${period}: before the requested window (${start})`);
    const era = eraFor(effr, period);
    if (!era) {
      problems.push(`${period}: no extract era`);
      continue;
    }
    try {
      const extra = {};
      for (const [field, name] of Object.entries(era.extra ?? {})) {
        if (r[field] !== undefined) extra[name] = decimalFromNumber(r[field], EXTRA_DECIMALS[name] ?? 2);
      }
      const flags = [];
      if (r.revisionIndicator === 'r') flags.push('r');
      if (r.footnoteId !== undefined) flags.push(`footnote:${r.footnoteId}`);
      const tEra = eraFor(target, period);
      const point = tEra.kind === 'range'
        ? { kind: 'range', lower: decimalFromNumber(r[tEra.lower], target.decimals), upper: decimalFromNumber(r[tEra.upper], target.decimals) }
        : { kind: 'rate', value: decimalFromNumber(r[tEra.value], target.decimals) };
      observations.push({ observation: { period, value: decimalFromNumber(r[era.value], effr.decimals), flags, ...(Object.keys(extra).length ? { extra } : {}) }, point });
    } catch (e) {
      problems.push(`${period}: ${e.message}`);
    }
  }
  if (problems.length) return { problems, series: {} };
  // Either order is accepted; stored ascending (6.2).
  observations.sort((a, b) => (a.observation.period < b.observation.period ? -1 : a.observation.period > b.observation.period ? 1 : 0));
  return { problems, series: { effr: observations.map((o) => o.observation) }, targets: observations.map((o) => ({ period: o.observation.period, ...o.point })) };
}

/**
 * Change points from per-record targets in period order (2.2): a point starts at the first
 * record that carries a new target. `first` marks the series' very first point.
 */
export function changePoints(targets) {
  const points = [];
  let prev = null;
  for (const t of targets) {
    const key = t.kind === 'range' ? `range|${t.lower}|${t.upper}` : `rate|${t.value}`;
    if (key !== prev) {
      const { period, ...rest } = t;
      points.push({ effective: period, ...rest });
      prev = key;
    }
  }
  return points;
}

/**
 * Fiscal Data Debt to the Penny pages to the three debt series. `pages` are the response bodies
 * in page order.
 */
export function normalizeDebt(pages, registry, table, { start = null } = {}) {
  const problems = [];
  const ids = ['debt-total', 'debt-held-public', 'debt-intragov'];
  const out = Object.fromEntries(ids.map((id) => [id, []]));
  if (!Array.isArray(pages) || pages.length === 0) return { problems: ['no pages'], series: {}, marker: null };
  const rows = [];
  for (const page of pages) {
    if (!Array.isArray(page?.data)) return { problems: ['data is not a list'], series: {}, marker: null };
    rows.push(...page.data);
  }
  const total = pages[0]?.meta?.['total-count'];
  if (!Number.isInteger(total)) problems.push('meta.total-count missing');
  else if (total !== rows.length) problems.push(`meta.total-count ${total} but ${rows.length} rows received`);
  for (const r of rows) {
    const { problems: p } = checkRecord(table, 'fiscaldata', r);
    if (p.length) {
      problems.push(...p);
      continue;
    }
    const period = r.record_date;
    if (start !== null && period < start) problems.push(`${period}: before the requested window (${start})`);
    for (const id of ids) {
      const s = byId(registry, id);
      const era = eraFor(s, period);
      if (!era) {
        problems.push(`${period}: no extract era for ${id}`);
        continue;
      }
      const text = r[era.value];
      try {
        if (era.null_text !== undefined && text === era.null_text) out[id].push({ period, value: null, missing: { code: era.missing_code, note: '' }, flags: [] });
        else out[id].push({ period, value: padDecimal(text, s.decimals), flags: [] });
      } catch (e) {
        problems.push(`${period}: ${id} ${e.message}`);
      }
    }
  }
  if (problems.length) return { problems, series: {}, marker: null };
  for (const id of ids) out[id].sort((a, b) => (a.period < b.period ? -1 : a.period > b.period ? 1 : 0));
  return { problems, series: out, marker: { total_count: total } };
}

const MISSING_NOTES = { NA: 'Not available', ND: 'No data', NC: 'Not calculable' };

/**
 * The SDMX reader's output for H.6 to the four money stock series. `body` is
 * { prepared, series: [{ attributes, observations: [{ TIME_PERIOD, OBS_VALUE, OBS_STATUS }] }], release_dates }.
 * Returns per-series problems as well: differing copies invalidate that series only (11.3).
 */
export function normalizeH6(body, registry, table) {
  const problems = [];
  const seriesProblems = {};
  const out = {};
  const spec = table.sdmx['h6-sdmx-2021'];
  if (!Array.isArray(body?.series)) return { problems: ['series is not a list'], series: {}, seriesProblems, marker: null };
  const dates = [];
  for (const d of body.release_dates ?? []) {
    const m = /^(\d{4}-\d{2}-\d{2})(\*{0,3})$/.exec(String(d));
    if (!m) problems.push(`release date ${d} is not a date`);
    else dates.push(m[1]);
  }
  if (dates.length === 0) problems.push('no release dates');
  dates.sort();
  for (const s of registry.series.filter((x) => x.fetch.format === 'sdmx-zip')) {
    const era = s.extract[0];
    const copies = body.series.filter((x) => x?.attributes?.SERIES_NAME === era.series_name);
    if (copies.length === 0) {
      problems.push(`${era.series_name}: series missing from the response`);
      continue;
    }
    for (const c of copies) {
      const a = c.attributes;
      for (const [name, allowed] of Object.entries(spec.series_attributes)) {
        if (a[name] === undefined) problems.push(`${era.series_name}: attribute ${name} missing`);
        else if (Array.isArray(allowed) && !allowed.includes(a[name])) problems.push(`${era.series_name}: ${name} is ${a[name]}`);
      }
      for (const name of Object.keys(a)) if (!(name in spec.series_attributes)) problems.push(`${era.series_name}: unknown attribute ${name}`);
      if (a.ADJUSTED !== era.adjusted) problems.push(`${era.series_name}: ADJUSTED is ${a.ADJUSTED}, registered ${era.adjusted}`);
      if (a.UNIT !== era.unit || a.UNIT_MULT !== era.unit_mult) problems.push(`${era.series_name}: unit ${a.UNIT} ${a.UNIT_MULT}, registered ${era.unit} ${era.unit_mult}`);
    }
    const text = (c) => JSON.stringify([Object.entries(c.attributes).sort(), c.observations]);
    if (copies.some((c) => text(c) !== text(copies[0]))) {
      seriesProblems[s.id] = [`${era.series_name}: copies of the series differ`];
      continue;
    }
    const mine = [];
    const list = [];
    for (const o of copies[0].observations ?? []) {
      const keys = Object.keys(o).sort().join(',');
      if (keys !== 'OBS_STATUS,OBS_VALUE,TIME_PERIOD' || !/^\d{4}-\d{2}-\d{2}$/.test(o.TIME_PERIOD) || !spec.observation_attributes.OBS_STATUS.includes(o.OBS_STATUS)) {
        problems.push(`${era.series_name}: observation ${JSON.stringify(o).slice(0, 80)} does not match h6-sdmx-2021`);
        continue;
      }
      const period = o.TIME_PERIOD.slice(0, 7);
      if (o.OBS_STATUS === 'A') {
        try {
          list.push({ period, value: padDecimal(o.OBS_VALUE, s.decimals), flags: [] });
        } catch (e) {
          mine.push(`${period}: ${e.message}`);
        }
      } else list.push({ period, value: null, missing: { code: o.OBS_STATUS, note: MISSING_NOTES[o.OBS_STATUS] }, flags: [] });
    }
    if (mine.length) seriesProblems[s.id] = mine;
    else out[s.id] = list.sort((a, b) => (a.period < b.period ? -1 : a.period > b.period ? 1 : 0));
  }
  if (problems.length) return { problems, series: {}, seriesProblems: {}, marker: null };
  return { problems, series: out, seriesProblems, marker: { latest_release_date: dates[dates.length - 1], prepared: String(body.prepared ?? '') }, releaseDates: dates };
}

const nextMonth = (p) => {
  const [y, m] = p.split('-').map(Number);
  return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`;
};

/** A decimal string equal to zero. */
const ZERO = /^-?0+(\.0+)?$/;

/** The validator's message for a missing period: an undocumented gap (11.6), not another check. */
export const GAP_PROBLEM = /: (a business day without a record that is not a documented gap|not the month after \d{4}-\d{2})$/;

/**
 * The undocumented gaps of a candidate (11.4, 11.6): business days (or months) from its first
 * period to its last without an observation and not listed in `known_gaps`, oldest first.
 */
export function undocumentedGaps(series, observations, calendar) {
  if (series.frequency === 'change-point' || observations.length < 2) return [];
  const format = series.frequency === 'month' ? /^\d{4}-\d{2}$/ : /^\d{4}-\d{2}-\d{2}$/;
  const periods = observations.map((o) => o.period);
  if (!periods.every((p) => typeof p === 'string' && format.test(p))) return [];
  const have = new Set(periods);
  const sorted = [...have].sort();
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  const out = [];
  if (series.frequency === 'business-day') {
    const gaps = new Set((series.known_gaps ?? []).map((g) => g.period));
    for (let d = first; d < last; d = addDays(d, 1)) if (!have.has(d) && !gaps.has(d) && calendar.isBusinessDay(d)) out.push(d);
  } else {
    for (let m = first; m < last; m = nextMonth(m)) if (!have.has(m)) out.push(m);
  }
  return out;
}

/**
 * Per-series validity (11.4): order, duplicates, future periods, weekend periods, decimals,
 * range and continuity. `observations` is the whole candidate in period order (for change
 * points, `effective` is the period). With a calendar (always, in a run) the whole-candidate
 * safeguards run too: the expected beginning, missing business days, documented gaps and
 * records on holidays. Returns a list of problems.
 */
export function validateSeries(series, observations, runEtDate, calendar = null) {
  const problems = [];
  const known = new Set((series.known_inconsistencies ?? []).map((k) => k.period));
  const key = series.frequency === 'change-point' ? 'effective' : 'period';
  const format = series.frequency === 'month' ? /^\d{4}-\d{2}$/ : /^\d{4}-\d{2}-\d{2}$/;
  const places = (v) => (v.includes('.') ? v.split('.')[1].length : 0);
  const eraOf = (p) => series.extract.find((e) => e.from <= p && (e.to === null || p <= e.to));
  const accepted = new Set((series.accepted_zeros ?? []).map((z) => `${z.period}|${z.field}`));
  let prev = null;
  for (const o of observations) {
    const p = o[key];
    if (typeof p !== 'string' || !format.test(p)) {
      problems.push(`${p}: not a ${series.frequency} period`);
      continue;
    }
    if (prev !== null && p === prev) problems.push(`${p}: duplicate period`);
    else if (prev !== null && p < prev) problems.push(`${p}: out of order`);
    const asDate = series.frequency === 'month' ? `${p}-01` : p;
    if (asDate > runEtDate) problems.push(`${p}: after the run's ET date ${runEtDate}`);
    if (series.frequency !== 'month' && [0, 6].includes(weekday(p)) && !known.has(p)) {
      // A change point derived from a listed weekend record would start on a weekend (2.2).
      problems.push(`${p}: weekend period not listed in known_inconsistencies`);
    }
    for (const field of ['value', 'lower', 'upper']) {
      const v = o[field];
      if (v === undefined || v === null) continue;
      if (places(v) !== series.decimals) problems.push(`${p}: ${field} ${v} does not have ${series.decimals} decimals`);
      // A zero where the source documents zero as its display of a missing amount is stored
      // neither as zero nor as missing (2.3, refuse_zero).
      // A zero named by an accepted_zeros entry (v0.6) is the source's confirmed value: stored as
      // zero, exempt from the range; no other zero and no other value is exempt.
      else if (eraOf(p)?.refuse_zero === true && ZERO.test(v) && accepted.has(`${p}|${field}`)) continue;
      else if (eraOf(p)?.refuse_zero === true && ZERO.test(v)) problems.push(`${p}: ${field} ${v} is zero, which the source documents as its display of a missing amount; it is stored neither as zero nor as missing`);
      else if (compareDecimal(v, series.range.min) < 0 || compareDecimal(v, series.range.max) > 0) problems.push(`${p}: ${field} ${v} outside ${series.range.min} to ${series.range.max}`);
    }
    if (series.frequency !== 'change-point' && (o.value === null) !== (o.missing !== undefined)) problems.push(`${p}: missing must be present exactly when value is null`);
    if (prev !== null && p > prev) {
      if (series.continuity.unit === 'days' && daysBetween(prev, p) > series.continuity.max_gap) problems.push(`${p}: ${daysBetween(prev, p)} days after ${prev}, more than ${series.continuity.max_gap}`);
      if (series.continuity.unit === 'months' && nextMonth(prev) !== p) problems.push(`${p}: not the month after ${prev}`);
    }
    prev = p;
  }
  if (calendar === null || problems.length) return problems;
  // Safeguards on the whole candidate (11.4). Nothing is filled in to pass them.
  const firstWithValue = series.frequency === 'change-point' ? observations[0] : observations.find((o) => o.value !== null);
  if (firstWithValue && firstWithValue[key] !== series.earliest) problems.push(`${firstWithValue[key]}: the series must begin at ${series.earliest}`);
  if (series.frequency === 'business-day') {
    const gaps = new Set((series.known_gaps ?? []).map((g) => g.period));
    const have = new Set(observations.map((o) => o.period));
    for (const o of observations) {
      if (gaps.has(o.period)) problems.push(`${o.period}: a documented gap has a record`);
      else if (![0, 6].includes(weekday(o.period)) && !calendar.isBusinessDay(o.period) && !known.has(o.period)) problems.push(`${o.period}: a record on a Federal Reserve holiday`);
    }
    if (observations.length) {
      const last = observations[observations.length - 1].period;
      for (let d = observations[0].period; d < last; d = addDays(d, 1)) {
        if (!have.has(d) && !gaps.has(d) && calendar.isBusinessDay(d)) problems.push(`${d}: a business day without a record that is not a documented gap`);
        if (problems.length >= 20) break;
      }
    }
  }
  return problems;
}
