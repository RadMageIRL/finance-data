// Source normalization, alerts and retention (DATA_CONVENTIONS v0.3 sections 5, 6, 11.4, 17.6,
// 17.7 and 17.8), on the committed excerpts of the saved provider responses.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import * as m0 from '../../../pipeline/lib/calendar.mjs';

// The pipeline modules are plain JavaScript: tests use them through a loose type.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/lib/normalize.mjs';
const { changePoints, normalizeDebt, normalizeEffr, normalizeH6, padDecimal, validateSeries } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/lib/alerts.mjs';
const { healthAlerts, planIssues, PLAN_ACTIONS, sanitizeAlerts, textRefusal } = m2 as unknown as Loose;
import * as m3 from '../../../pipeline/lib/retention.mjs';
const { addPin, budgetAlerts, emptyPins, isSignificant, liveWindow, MAX_PINS, prunable, removePin } = m3 as unknown as Loose;
import * as m4 from '../../../pipeline/lib/watcher.mjs';
const { watch } = m4 as unknown as Loose;
import * as m5 from '../../../pipeline/lib/activation.mjs';
const { activationProblems } = m5 as unknown as Loose;


const { makeCalendar } = m0 as unknown as Loose;
const read = (p: string) => JSON.parse(readFileSync(p, 'utf8'));
const registry = read('pipeline/registry/econ.json');
const table = read('pipeline/schemas/source-records.json');
const effrExcerpt = read('pipeline/fixtures/sources/effr-excerpt.json');
const dtpExcerpt = read('pipeline/fixtures/sources/dtp-excerpt.json');
const h6Excerpt = read('pipeline/fixtures/sources/h6-excerpt.json');
const series = (id: string) => registry.series.find((s: { id: string }) => s.id === id);
const copy = <T>(v: T): T => JSON.parse(JSON.stringify(v));

describe('EFFR records', () => {
  const n = normalizeEffr({ refRates: effrExcerpt.refRates }, registry, table);

  it('reads every era of the saved excerpt in period order with the provider digits kept', () => {
    expect(n.problems).toEqual([]);
    const first = n.series.effr[0];
    expect(first.period).toBe('2000-07-03');
    expect(first.value).toMatch(/^\d+\.\d{2}$/);
    expect(Object.keys(first.extra).sort()).toEqual(['intraday_high', 'intraday_low', 'std_deviation']);
    const last = n.series.effr[n.series.effr.length - 1];
    expect(last).toEqual({ period: '2026-11-12', value: '3.88', flags: [], extra: { p1: '3.85', p25: '3.87', p75: '3.89', p99: '3.90', volume_usd_billions: '99' } });
  });

  it('keeps the publisher flags r and the footnote of 2023-07-25', () => {
    expect(n.series.effr.find((o: { period: string }) => o.period === '2000-07-10').flags).toEqual(['r']);
    expect(n.series.effr.find((o: { period: string }) => o.period === '2023-07-25').flags[0]).toMatch(/^footnote:\d+$/);
  });

  it('derives change points as a single rate before 2008-12-16 and a range from then on', () => {
    const points = changePoints(n.targets);
    expect(points[0]).toEqual({ effective: '2000-07-03', kind: 'rate', value: '6.50' });
    const range = points.find((p: { effective: string }) => p.effective === '2008-12-16');
    expect(range.kind).toBe('range');
    expect(points.every((p: { effective: string; kind: string }) => (p.effective < '2008-12-16' ? p.kind === 'rate' : p.kind === 'range'))).toBe(true);
  });

  it('refuses the whole response for an unknown field, a missing field or a record before the window', () => {
    const extra = copy(effrExcerpt.refRates);
    extra[0].surprise = 1;
    expect(normalizeEffr({ refRates: extra }, registry, table).problems).toEqual(['2000-07-03: unknown field surprise (effr-2000)']);
    const missing = copy(effrExcerpt.refRates);
    delete missing[0].percentRate;
    expect(normalizeEffr({ refRates: missing }, registry, table).problems).toEqual(['2000-07-03: missing percentRate (effr-2000)']);
    expect(normalizeEffr({ refRates: effrExcerpt.refRates }, registry, table, { start: '2026-01-01' }).problems.length).toBe(11);
    expect(normalizeEffr({ rates: [] }, registry, table).problems).toEqual(['refRates is not a list']);
  });
});

describe('Debt to the Penny records', () => {
  const body = { data: dtpExcerpt.data, meta: { 'total-count': dtpExcerpt.data.length } };
  const n = normalizeDebt([body], registry, table);

  it('gives every record date an observation in all three series, with a recorded absence for "null"', () => {
    expect(n.problems).toEqual([]);
    expect(n.series['debt-total'].length).toBe(9);
    expect(n.series['debt-held-public'][0]).toEqual({ period: '1993-04-01', value: null, missing: { code: 'not-published', note: '' }, flags: [] });
    expect(n.series['debt-held-public'].find((o: { period: string }) => o.period === '2003-01-31').value).toBeNull();
    expect(n.marker).toEqual({ total_count: 9 });
  });

  it('keeps the two dates whose parts do not add up exactly as published', () => {
    const at = (id: string, d: string) => n.series[id].find((o: { period: string }) => o.period === d).value;
    expect(at('debt-total', '2025-08-04')).toBe('36828164797914.31');
    expect(at('debt-held-public', '2025-08-04')).toBe('29523300148538.85');
    expect(at('debt-intragov', '2025-08-04')).toBe('7314864649375.46');
    expect(at('debt-total', '2011-02-01')).toBe('14109842878903.50');
  });

  it('refuses a response whose total-count differs from the rows received', () => {
    expect(normalizeDebt([{ ...body, meta: { 'total-count': 10 } }], registry, table).problems).toEqual(['meta.total-count 10 but 9 rows received']);
  });

  it('refuses an amount with more precision than cents', () => {
    const bad = copy(body);
    bad.data[0].tot_pub_debt_out_amt = '4225873987843.444';
    expect(normalizeDebt([bad], registry, table).problems).toEqual(['1993-04-01: debt-total 4225873987843.444: more than 2 decimals']);
    expect(() => padDecimal('1e5', 2)).toThrow(/not a decimal string/);
  });
});

describe('H.6 reader output', () => {
  it('reads the four registered series as months with one decimal and the release marker', () => {
    const n = normalizeH6(h6Excerpt, registry, table);
    expect(n.problems).toEqual([]);
    expect(Object.keys(n.series).sort()).toEqual(['m1-nsa', 'm1-sa', 'm2-nsa', 'm2-sa']);
    expect(n.series['m1-sa'][23]).toEqual({ period: '2026-09', value: '20061.2', flags: [] });
    expect(n.marker).toEqual({ latest_release_date: '2026-10-27', prepared: '2026-10-19T15:17:34' });
    expect(n.releaseDates).toContain('2021-02-23');
  });

  it('invalidates only the series whose copies differ', () => {
    const body = copy(h6Excerpt);
    const copies = body.series.filter((s: { attributes: { SERIES_NAME: string } }) => s.attributes.SERIES_NAME === 'M1.M');
    expect(copies.length).toBe(2);
    copies[1].observations[0].OBS_VALUE = '1.0';
    const n = normalizeH6(body, registry, table);
    expect(n.problems).toEqual([]);
    expect(n.seriesProblems).toEqual({ 'm1-sa': ['M1.M: copies of the series differ'] });
    expect(Object.keys(n.series).sort()).toEqual(['m1-nsa', 'm2-nsa', 'm2-sa']);
  });

  it('invalidates the whole response when a unit multiplier changes', () => {
    const body = copy(h6Excerpt);
    for (const s of body.series) s.attributes.UNIT_MULT = '1e+06';
    expect(normalizeH6(body, registry, table).problems[0]).toBe('M1.M: UNIT_MULT is 1e+06');
  });

  it('stores a status other than A as a recorded absence with the codelist text', () => {
    const body = copy(h6Excerpt);
    for (const s of body.series) s.observations[23] = { ...s.observations[23], OBS_STATUS: 'ND' };
    const n = normalizeH6(body, registry, table);
    expect(n.series['m2-sa'][23]).toEqual({ period: '2026-09', value: null, missing: { code: 'ND', note: 'No data' }, flags: [] });
  });
});

describe('series validity', () => {
  const effr = series('effr');
  const o = (period: string, value = '3.88') => ({ period, value, flags: [] });

  it('reports a value outside the range, a long gap, a duplicate and a future period', () => {
    expect(validateSeries(effr, [o('2026-11-12', '25.01')], '2026-11-13')).toEqual(['2026-11-12: value 25.01 outside -1.00 to 25.00']);
    expect(validateSeries(effr, [o('2026-11-02'), o('2026-11-09')], '2026-11-13')).toEqual(['2026-11-09: 7 days after 2026-11-02, more than 6']);
    expect(validateSeries(effr, [o('2026-11-12'), o('2026-11-12')], '2026-11-13')).toEqual(['2026-11-12: duplicate period']);
    expect(validateSeries(effr, [o('2026-11-13')], '2026-11-12')).toEqual(["2026-11-13: after the run's ET date 2026-11-12"]);
    expect(validateSeries(effr, [o('2026-11-12', '3.9')], '2026-11-13')).toEqual(['2026-11-12: value 3.9 does not have 2 decimals']);
  });

  it('reports a weekend period unless the registry lists it as a known inconsistency', () => {
    expect(validateSeries(effr, [o('2026-11-14')], '2026-11-16')).toEqual(['2026-11-14: weekend period not listed in known_inconsistencies']);
    expect(validateSeries(effr, [o('2003-07-18'), o('2003-07-20'), o('2003-07-21')], '2026-11-16')).toEqual([]);
  });

  it('reports a missing month in a monthly series', () => {
    const m = (period: string) => ({ period, value: '100.0', flags: [] });
    expect(validateSeries(series('m1-sa'), [m('2026-07'), m('2026-09')], '2026-11-16')).toEqual(['2026-09: not the month after 2026-07']);
  });
});

describe('alert text and the issue plan', () => {
  const alert = (key: string, body = 'Series effr is held.', severity = 'critical') => ({ key, severity, title: `Alert ${key}`, body });

  it('withholds text that could carry request details or credentials', () => {
    const cases: [string, string][] = [
      ['https://api.example.gov/v2/data?filter=x', 'a query string'],
      ['see https://example.gov/path/file', 'a URL with a path'],
      ['mail owner@example.com', 'an email address'],
      ['from 10.1.2.3', 'an IPv4 address'],
      ['Authorization failed', 'a header name'],
      ['sent Bearer abc', 'a bearer credential'],
      ['ghp_abc', 'a token'],
      [`key ${'a1'.repeat(20)}`, 'a long run of key-like characters'],
      ['x'.repeat(2001), 'longer than 2000 characters'],
    ];
    for (const [text, why] of cases) expect(textRefusal(text)).toBe(why);
    expect(textRefusal(`Candidate sha256:${'ab12'.repeat(16)}, status 503 at 2026-11-17T15:17:00Z.`)).toBeNull();
  });

  it('withholds a refused alert and raises alert-text-refused naming only its key', () => {
    const out = sanitizeAlerts([alert('hold:effr'), alert('blocked:nyfed-markets', 'token ghp_secret')]);
    expect(out.map((a: { key: string }) => a.key)).toEqual(['alert-text-refused', 'hold:effr']);
    expect(out[0].body).toBe('Withheld alert keys: blocked:nyfed-markets. Read the run record for details.');
    expect(JSON.stringify(out)).not.toContain('ghp_');
  });

  it('opens once, stays silent while unchanged, updates on a change and closes when clear', () => {
    const a = planIssues(null, [alert('hold:effr')], '2026-11-16T14:17:00Z');
    expect(a.plan.map((x: { action: string; key: string }) => [x.action, x.key])).toEqual([['open', 'hold:effr']]);
    const b = planIssues(a.ledger, [alert('hold:effr')], '2026-11-16T15:17:00Z');
    expect(b.plan).toEqual([]);
    expect(b.ledger.open[0]).toMatchObject({ first_seen: '2026-11-16T14:17:00Z', last_seen: '2026-11-16T15:17:00Z', runs: 2 });
    const c = planIssues(b.ledger, [alert('hold:effr', 'Series effr is held with a new candidate.')], '2026-11-16T16:17:00Z');
    expect(c.plan.map((x: { action: string }) => x.action)).toEqual(['update']);
    const d = planIssues(c.ledger, [], '2026-11-16T17:17:00Z');
    expect(d.plan).toEqual([{ action: 'close', key: 'hold:effr' }]);
    expect(d.ledger.open).toEqual([]);
  });

  it('plans only issue actions: nothing commits, pushes or re-enables a workflow', () => {
    expect(PLAN_ACTIONS).toEqual(['open', 'update', 'close']);
    const facts = { now: '2026-11-18T12:00:00Z', workflow: { state: 'disabled_inactivity' }, repository: { pushed_at: '2026-09-01T00:00:00Z' }, runs: [], manifest: null };
    const w = watch(facts);
    expect(w.findings.map((f: { key: string }) => f.key)).toEqual(['inactivity', 'manifest-missing', 'scheduled-run-gap', 'workflow-disabled']);
    expect(w.plan.every((x: { action: string }) => PLAN_ACTIONS.includes(x.action))).toBe(true);
    expect(w.plan.length).toBe(4);
    // A second look with the same facts says nothing new.
    expect(watch(facts, w.ledger).plan).toEqual([]);
    expect(healthAlerts(w.findings)[0]).toMatchObject({ key: 'inactivity', severity: 'critical' });
  });

  it('warns about repository inactivity at 45 days, before GitHub disables schedules at 60', () => {
    const facts = (pushed: string) => ({ now: '2026-11-18T12:00:00Z', workflow: { state: 'active' }, repository: { pushed_at: pushed }, runs: [{ event: 'schedule', conclusion: 'success', created_at: '2026-11-18T11:17:00Z' }], manifest: { health: { expected_next_update_by: '2026-11-18T20:00:00Z' }, series: {} } });
    expect(watch(facts('2026-10-05T12:00:00Z')).findings).toEqual([]);
    expect(watch(facts('2026-10-04T12:00:00Z')).findings.map((f: { key: string; severity: string }) => [f.key, f.severity])).toEqual([['inactivity', 'warning']]);
  });
});

describe('retention and budgets', () => {
  const pin = (i: number) => ({ snapshot: `202611${String(i).padStart(2, '0')}T141700Z`, site_release: 'v0.2.0', reason: 'site build', pinned_at: '2026-11-18T12:00:00Z' });
  const known = Array.from({ length: 20 }, (_, i) => pin(i + 1).snapshot);

  it('accepts 12 pins and refuses a 13th without unpinning anything', () => {
    let pins = emptyPins();
    for (let i = 1; i <= MAX_PINS; i += 1) pins = addPin(pins, pin(i), known).pins;
    expect(pins.pins.length).toBe(12);
    const r = addPin(pins, pin(13), known);
    expect(r.ok).toBe(false);
    expect(r.error).toBe('12 snapshots are pinned already; unpin one explicitly first');
    expect(r.pins.pins.length).toBe(12);
  });

  it('refuses to pin an unknown snapshot and records every unpinning', () => {
    expect(addPin(emptyPins(), { ...pin(1), snapshot: '20200101T000000Z' }, known).ok).toBe(false);
    const one = addPin(emptyPins(), pin(1), known).pins;
    expect(removePin(one, { snapshot: pin(1).snapshot, reason: '', unpinned_at: '2026-11-19T00:00:00Z' }).ok).toBe(false);
    const gone = removePin(one, { snapshot: pin(1).snapshot, reason: 'site release retired', unpinned_at: '2026-11-19T00:00:00Z' });
    expect(gone.pins.pins).toEqual([]);
    expect(gone.pins.unpinned).toEqual([{ snapshot: pin(1).snapshot, reason: 'site release retired', unpinned_at: '2026-11-19T00:00:00Z' }]);
  });

  const snap = (id: string, previous: string | null, more = {}) => ({ id, previous, created_at: `${id.slice(0, 4)}-${id.slice(4, 6)}-${id.slice(6, 8)}T14:17:00Z`, run: { trigger: 'schedule' }, revisions: [], holds: [], series: { effr: { objects: [{ path: `objects/effr/2026/${id.slice(0, 16).toLowerCase().replace(/[^0-9a-f]/g, '0')}.json` }] } }, ...more });

  it('counts a snapshot as significant when it is first, wrote revisions, touched a hold or came from a review', () => {
    const plain = snap('20261007T141700Z', '20261006T141700Z');
    expect(isSignificant(plain, snap('20261006T141700Z', null))).toBe(false);
    expect(isSignificant(snap('20261006T141700Z', null), null)).toBe(true);
    expect(isSignificant({ ...plain, revisions: [{ path: 'revisions/effr/2026/0000000000000000.json' }] }, plain)).toBe(true);
    expect(isSignificant({ ...plain, run: { trigger: 'review' } }, plain)).toBe(true);
    const held = { ...plain, holds: [{ series: 'effr', candidate: { sha256: 'a'.repeat(64) } }] };
    expect(isSignificant(held, plain)).toBe(true);
    expect(isSignificant(plain, held)).toBe(true);
  });

  it('keeps 35 days of snapshots, the previous ones, pins and significant ones, and lists the rest as prunable', () => {
    const ids = ['20261001T141700Z', '20261002T141700Z', '20261005T141700Z', '20261006T141700Z', '20261113T141700Z'] as const;
    const snapshots = Object.fromEntries(ids.map((id, i) => [id, snap(id, i ? (ids[i - 1] ?? null) : null)]));
    const manifest = { generated_at: '2026-11-13T14:17:00Z', snapshot: { id: ids[4] }, previous_snapshot: ids[3], series: {} };
    const w = liveWindow({ manifest, snapshots, manifests: [], pins: { pins: [{ snapshot: ids[1] }] } });
    expect(w.kept).toEqual({ [ids[0]]: 'significant', [ids[1]]: 'pinned', [ids[3]]: 'previous', [ids[4]]: 'current' });
    const live = ids.map((id) => `snapshots/${id}.json`).concat(['manifest.json', 'status/runs.json']);
    expect(prunable(live, w)).toEqual([`snapshots/${ids[2]}.json`]);
    // A snapshot created exactly 35 days before is outside the window; one second later is inside.
    const edge = liveWindow({ manifest: { ...manifest, generated_at: '2026-11-09T14:17:00Z' }, snapshots, manifests: [], pins: { pins: [] } });
    expect(edge.kept[ids[2]]).toBeUndefined();
    expect(liveWindow({ manifest: { ...manifest, generated_at: '2026-11-09T14:16:59Z' }, snapshots, manifests: [], pins: { pins: [] } }).kept[ids[2]]).toBe('window');
  });

  it('warns before either storage limit: 125 and 200 MB published, 25 and 40 MB of new archive in a month', () => {
    const m = (publishedBytes: number, archiveMonthBytes: number) => budgetAlerts({ publishedBytes, archiveMonthBytes, largestObject: 0, largestFile: 0, manifestBytes: 0 }, 0).map((a: { key: string; severity: string }) => [a.key, a.severity]);
    expect(m(124_999_999, 24_999_999)).toEqual([]);
    expect(m(125_000_000, 25_000_000)).toEqual([['budget:published', 'warning'], ['budget:archive-month', 'warning']]);
    expect(m(200_000_000, 40_000_000)).toEqual([['budget:published', 'critical'], ['retention-decision', 'critical'], ['budget:archive-month', 'critical']]);
    expect(m(199_999_999, 0)).toEqual([['budget:published', 'warning']]);
    expect(budgetAlerts({ publishedBytes: 0, archiveMonthBytes: 0, largestObject: 0, largestFile: 0, manifestBytes: 0 }, 10).map((a: { key: string }) => a.key)).toEqual(['budget:pins']);
    expect(budgetAlerts({ publishedBytes: 0, archiveMonthBytes: 0, largestObject: 0, largestFile: 0, manifestBytes: 0 }, 9)).toEqual([]);
  });
});

describe('whole-candidate safeguards', () => {
  const table = JSON.parse(readFileSync('pipeline/registry/fed-holidays.json', 'utf8'));
  const calendar = makeCalendar(table);
  const debt = series('debt-total');
  const row = (period: string) => ({ period, value: '100.00', flags: [] });
  const from = (start: string, days: string[]) => [{ ...debt, earliest: start }, days.map(row)] as const;

  it('reports a history that does not begin where the series begins', () => {
    const [s, obs] = from('2026-11-02', ['2026-11-03', '2026-11-04']);
    expect(validateSeries(s, obs, '2026-11-13', calendar)).toEqual(['2026-11-03: the series must begin at 2026-11-02']);
  });

  it('reports a business day without a record unless the registry documents the gap, and never fills it', () => {
    const [s, obs] = from('2026-11-02', ['2026-11-02', '2026-11-03', '2026-11-05']);
    expect(validateSeries(s, obs, '2026-11-13', calendar)).toEqual(['2026-11-04: a business day without a record that is not a documented gap']);
    const documented = { ...s, known_gaps: [{ period: '2026-11-04', text: 'documented' }] };
    expect(validateSeries(documented, obs, '2026-11-13', calendar)).toEqual([]);
    expect(obs.length).toBe(3);
    expect(validateSeries(documented, [...obs.slice(0, 2), row('2026-11-04'), obs[2]], '2026-11-13', calendar)).toEqual(['2026-11-04: a documented gap has a record']);
  });

  it('accepts a holiday without a record and reports a record on a holiday', () => {
    const [s, obs] = from('2026-11-09', ['2026-11-09', '2026-11-10', '2026-11-12']);
    expect(validateSeries(s, obs, '2026-11-13', calendar)).toEqual([]);
    expect(validateSeries(s, [obs[0], obs[1], row('2026-11-11'), obs[2]], '2026-11-13', calendar)).toEqual(['2026-11-11: a record on a Federal Reserve holiday']);
  });

  it('holds the 18 documented Debt to the Penny gaps and the verified holiday table', () => {
    expect(debt.known_gaps.length).toBe(18);
    expect(debt.known_gaps[0].period).toBe('1995-11-20');
    expect(debt.known_gaps[17].period).toBe('2019-04-03');
    expect(table).toMatchObject({ status: 'verified', source: 'https://www.federalreserve.gov/aboutthefed/k8.htm', years: [1993, 2030] });
    expect(registry.holiday_table).toBe('fed-holidays.json');
    // K.8 for 2026: Independence Day falls on a Saturday, so nothing closes; 2027: July 5.
    expect(table.holidays.filter((d: string) => d.startsWith('2026'))).toEqual(['2026-01-01', '2026-01-19', '2026-02-16', '2026-05-25', '2026-06-19', '2026-09-07', '2026-10-12', '2026-11-11', '2026-11-26', '2026-12-25']);
    expect(table.holidays).toContain('2027-07-05');
    expect(table.holidays).not.toContain('2021-06-18');
    expect(table.holidays).toContain('2022-06-20');
  });
});

describe('activation guard', () => {
  it('lists what blocks live collection today, with the holiday table no longer among them', () => {
    const problems = activationProblems({ pipelineDir: 'pipeline' });
    expect(problems[0]).toBe('there is no live transport: live network collection is not written and not authorized');
    expect(problems).toContain('live collection is not authorized (stage B)');
    expect(problems).toContain('there is no durable private state store (finance-data-state is not created)');
    expect(problems.length).toBe(6);
  });
});
