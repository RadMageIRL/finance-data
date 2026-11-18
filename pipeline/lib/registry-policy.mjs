// Registry rules beyond the JSON Schema (DATA_CONVENTIONS sections 2, 4 and 12.1): every
// series' class-specific fields are present and consistent with its class, references resolve,
// shared requests are symmetric, date-bounded extract eras are contiguous, and ids never
// collide with published paths. Returns every problem found; an empty list means it passes.

export const RESERVED_IDS = ['econ', 'news', 'manifest', 'snapshots', 'objects', 'series', 'revisions', 'status', 'holds'];

/** What each class requires (section 2). */
export const CLASS_RULES = {
  market_observation: { frequency: 'business-day', window: 'publication-day', staleness: 'after_business_days', continuity: 'days', segment: 'year', needs: ['statistics_window_business_days'], forbids: ['alert_ratio'] },
  policy_target: { frequency: 'change-point', window: 'none', staleness: 'follows', continuity: null, segment: 'all', needs: [], forbids: ['statistics_window_business_days', 'alert_ratio'] },
  administrative_daily: { frequency: 'business-day', window: 'none', staleness: 'after_business_days', continuity: 'days', segment: 'year', needs: [], forbids: ['statistics_window_business_days', 'alert_ratio'] },
  revised_aggregate: { frequency: 'month', window: 'scheduled-release', staleness: 'after_days_past_expected_release', continuity: 'months', segment: 'all', needs: ['alert_ratio'], forbids: ['statistics_window_business_days'] },
};

/** The publication zones a calendar may name or consider, in the order candidates are listed (4.5). */
const ZONES = ['America/New_York', 'UTC'];
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const MONTH = /^\d{4}-\d{2}$/;
const PLACEHOLDER = /\{([a-z_]+)\}/g;

const fractionDigits = (d) => (d.includes('.') ? d.split('.')[1].length : 0);

/** Compares two decimal strings exactly (no floating point): negative, zero or positive. */
export function compareDecimal(a, b) {
  const parse = (s) => {
    const neg = s.startsWith('-');
    const [int, frac = ''] = (neg ? s.slice(1) : s).split('.');
    return { neg, int: int.replace(/^0+(?=\d)/, ''), frac };
  };
  const zero = (p) => /^0*$/.test(p.int) && /^0*$/.test(p.frac);
  const x = parse(a);
  const y = parse(b);
  // Negative zero is zero.
  if (zero(x)) x.neg = false;
  if (zero(y)) y.neg = false;
  if (x.neg !== y.neg) return x.neg ? -1 : 1;
  const width = Math.max(x.frac.length, y.frac.length);
  const xs = x.int.padStart(40, '0') + x.frac.padEnd(width, '0');
  const ys = y.int.padStart(40, '0') + y.frac.padEnd(width, '0');
  const c = xs < ys ? -1 : xs > ys ? 1 : 0;
  return x.neg ? -c : c;
}

function nextPeriod(p) {
  if (MONTH.test(p)) {
    const [y, m] = p.split('-').map(Number);
    return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`;
  }
  const d = new Date(`${p}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

export function registryProblems(registry) {
  const problems = [];
  const add = (where, message) => problems.push(`${where}: ${message}`);
  const series = registry.series ?? [];
  const byId = new Map();
  for (const s of series) {
    if (byId.has(s.id)) add(`series ${s.id}`, 'duplicate id');
    byId.set(s.id, s);
  }
  // A rule says from when it is VERIFIED (release dates before it are not recorded); a published
  // calendar has an address and, where it starts, its first valid date (section 6.3).
  for (const [id, cal] of Object.entries(registry.calendars ?? {})) {
    if (cal.kind === 'rule' && (cal.rule_valid_from === undefined || cal.url !== undefined)) add(`calendar ${id}`, 'a rule needs rule_valid_from and no url');
    if (cal.kind === 'calendar' && (cal.url === undefined || cal.rule_valid_from !== undefined)) add(`calendar ${id}`, 'a calendar needs a url and no rule_valid_from');
    if (cal.publish_time === null && cal.kind === 'rule') add(`calendar ${id}`, 'a rule needs a publish_time');
    // An unverified zone stays unknown, with its readings in a fixed order (4.5).
    const candidates = cal.publish_time_zone_candidates;
    if (cal.publish_time_zone === 'unknown') {
      const ok = Array.isArray(candidates) && candidates.length >= 2 && new Set(candidates).size === candidates.length && ZONES.filter((z) => candidates.includes(z)).join() === candidates.join();
      if (!ok) add(`calendar ${id}`, 'an unknown zone needs at least two distinct candidates in the order America/New_York, UTC');
    } else if (candidates !== undefined) add(`calendar ${id}`, 'zone candidates are allowed only with an unknown zone');
  }
  // Who may decide a hold (4.2): exactly the GitHub roles with write access, in this order.
  if ((registry.family_policy?.review?.permissions ?? []).join() !== 'admin,maintain,write') add('family_policy', 'review permissions must be admin, maintain, write');
  for (const [id, src] of Object.entries(registry.sources ?? {})) {
    for (const n of src.route_notices ?? []) {
      if (!(n.checked <= n.date)) add(`source ${id}`, `route notice ${n.date} read on ${n.checked}, after its date`);
    }
  }
  for (const [id, src] of Object.entries(registry.sources ?? {})) {
    if (!(src.calendar in (registry.calendars ?? {}))) add(`source ${id}`, `unknown calendar ${src.calendar}`);
    for (const field of ['attribution', 'notice']) {
      for (const m of String(src[field] ?? '').matchAll(PLACEHOLDER)) {
        if (!['data_name', 'year'].includes(m[1])) add(`source ${id}`, `unknown placeholder {${m[1]}} in ${field}`);
      }
    }
  }
  for (const s of series) {
    const where = `series ${s.id}`;
    if (RESERVED_IDS.includes(s.id)) add(where, 'reserved id');
    const rule = CLASS_RULES[s.class];
    if (!rule) {
      add(where, `unknown class ${s.class}`);
      continue;
    }
    if (!(s.source in (registry.sources ?? {}))) add(where, `unknown source ${s.source}`);
    if (s.frequency !== rule.frequency) add(where, `class ${s.class} needs frequency ${rule.frequency}`);
    if (s.segment !== rule.segment) add(where, `class ${s.class} needs segment ${rule.segment}`);
    if (s.revision?.window !== rule.window) add(where, `class ${s.class} needs revision window ${rule.window}`);
    for (const f of rule.needs) if (s.revision?.[f] === undefined) add(where, `class ${s.class} needs revision.${f}`);
    for (const f of rule.forbids) if (s.revision?.[f] !== undefined) add(where, `revision.${f} does not apply to class ${s.class}`);
    if (s.revision?.alert_ratio !== undefined && !(compareDecimal(s.revision.alert_ratio, '0') > 0 && compareDecimal(s.revision.alert_ratio, '1') < 0)) add(where, 'alert_ratio must be between 0 and 1');
    const staleKeys = Object.keys(s.staleness ?? {});
    if (staleKeys.length !== 1 || staleKeys[0] !== rule.staleness) add(where, `class ${s.class} needs exactly staleness.${rule.staleness}`);
    if (s.staleness?.follows !== undefined && (s.staleness.follows === s.id || !byId.has(s.staleness.follows))) add(where, `staleness follows unknown or itself: ${s.staleness.follows}`);
    if ((s.continuity?.unit ?? null) !== rule.continuity) add(where, `class ${s.class} needs continuity unit ${rule.continuity}`);
    if (rule.continuity === null ? s.continuity?.max_gap !== null : !Number.isInteger(s.continuity?.max_gap)) add(where, 'continuity max_gap does not fit its unit');
    if (rule.continuity === 'months' && s.continuity?.max_gap !== 1) add(where, 'monthly series allow no missing month (max_gap 1)');
    // Periods use the format of the frequency.
    const periodRe = s.frequency === 'month' ? MONTH : DATE;
    if (!periodRe.test(s.earliest ?? '')) add(where, `earliest ${s.earliest} is not a ${s.frequency} period`);
    // Release basis matches the calendar kind (first-seen uses the calendar for scheduling only).
    const cal = registry.calendars?.[s.release?.calendar];
    if (!cal) add(where, `unknown release calendar ${s.release?.calendar}`);
    else if (s.release.basis !== 'first-seen' && cal.kind !== s.release.basis) add(where, `release basis ${s.release.basis} but calendar ${s.release.calendar} is a ${cal.kind}`);
    if (cal && s.release.calendar !== registry.sources?.[s.source]?.calendar) add(where, `release calendar ${s.release.calendar} is not its source's calendar`);
    // Range bounds: ordered, with the series' decimals.
    if (s.range) {
      if (compareDecimal(s.range.min, s.range.max) >= 0) add(where, 'range min is not below max');
      for (const k of ['min', 'max']) if (fractionDigits(s.range[k]) !== s.decimals) add(where, `range.${k} needs ${s.decimals} decimals`);
    }
    // Extract eras: contiguous, ascending, only the last open-ended, covering earliest.
    const eras = s.extract ?? [];
    eras.forEach((e, i) => {
      if (!periodRe.test(e.from) || (e.to !== null && !periodRe.test(e.to))) add(where, `extract ${e.schema} periods are not ${s.frequency} periods`);
      if (e.to !== null && e.to < e.from) add(where, `extract ${e.schema} ends before it starts`);
      if (i < eras.length - 1) {
        if (e.to === null) add(where, `extract ${e.schema} is open-ended but not last`);
        else if (eras[i + 1].from !== nextPeriod(e.to)) add(where, `extract ${eras[i + 1].schema} does not start the period after ${e.schema} ends`);
      } else if (e.to !== null) add(where, 'the last extract era must be open-ended (to: null)');
      if (s.class === 'policy_target') {
        if (e.kind === 'rate' && (e.value === undefined || e.lower !== undefined || e.upper !== undefined)) add(where, `extract ${e.schema}: a rate takes value only`);
        if (e.kind === 'range' && (e.lower === undefined || e.upper === undefined || e.value !== undefined)) add(where, `extract ${e.schema}: a range takes lower and upper only`);
        if (e.kind === undefined) add(where, `extract ${e.schema}: policy targets need kind`);
      } else {
        if (e.value === undefined) add(where, `extract ${e.schema}: needs value`);
        if (e.kind !== undefined) add(where, `extract ${e.schema}: kind applies to policy targets only`);
      }
      // SDMX extracts name the series and its declared attributes; the adjustment must agree.
      if (s.fetch?.format === 'sdmx-zip') {
        for (const f of ['series_name', 'adjusted', 'unit', 'unit_mult']) if (e[f] === undefined) add(where, `extract ${e.schema}: SDMX needs ${f}`);
        if (e.adjusted !== undefined && e.adjusted.toLowerCase() !== s.seasonal_adjustment) add(where, `extract ${e.schema}: adjusted ${e.adjusted} but seasonal_adjustment ${s.seasonal_adjustment}`);
      } else if (e.series_name !== undefined || e.adjusted !== undefined) add(where, `extract ${e.schema}: SDMX fields on a ${s.fetch?.format} source`);
    });
    if (eras.length && eras[0].from > s.earliest) add(where, `earliest ${s.earliest} comes before the first extract era`);
    // Derived series name their source series and share its request.
    if (s.class === 'policy_target' && !s.derived_from) add(where, 'policy targets in this family are derived and need derived_from');
    if (s.derived_from) {
      if (!byId.has(s.derived_from.series)) add(where, `derived from unknown series ${s.derived_from.series}`);
      if (!(s.fetch?.shared_with ?? []).includes(s.derived_from.series)) add(where, 'derived_from series must be in fetch.shared_with');
    }
    for (const other of s.fetch?.shared_with ?? []) {
      const o = byId.get(other);
      if (!o || other === s.id) {
        add(where, `shared_with unknown or itself: ${other}`);
        continue;
      }
      if (!(o.fetch?.shared_with ?? []).includes(s.id)) add(where, `shared_with ${other} is not symmetric`);
      if (o.fetch.endpoint !== s.fetch.endpoint || JSON.stringify(o.fetch.parameters) !== JSON.stringify(s.fetch.parameters) || o.source !== s.source) add(where, `shared_with ${other} uses a different request`);
    }
  }
  return problems;
}
