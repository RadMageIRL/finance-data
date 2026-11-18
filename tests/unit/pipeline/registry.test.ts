// The econ source registry (DATA_CONVENTIONS v0.1 section 4) against its JSON Schema and the
// class and reference rules of sections 2 and 12.1, plus registries broken on purpose.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { validate } from '../../../pipeline/lib/json-schema.mjs';
import { CLASS_RULES, compareDecimal, RESERVED_IDS, registryProblems } from '../../../pipeline/lib/registry-policy.mjs';

const registry = JSON.parse(readFileSync('pipeline/registry/econ.json', 'utf8'));
const schema = JSON.parse(readFileSync('pipeline/schemas/registry.schema.json', 'utf8'));
const copy = () => JSON.parse(JSON.stringify(registry));
const find = (r: typeof registry, id: string) => r.series.find((s: { id: string }) => s.id === id);

describe('econ registry', () => {
  it('validates against its schema and passes every policy rule', () => {
    expect(validate(schema, registry)).toEqual([]);
    expect(registryProblems(registry)).toEqual([]);
  });

  it('registers exactly the D3 datasets: EFFR, the FOMC target, Debt to the Penny, H.6 M1 and M2', () => {
    expect(registry.series.map((s: { id: string }) => s.id)).toEqual(['effr', 'fomc-target', 'debt-total', 'debt-held-public', 'debt-intragov', 'm1-sa', 'm2-sa', 'm1-nsa', 'm2-nsa']);
    expect(Object.keys(registry.sources).sort()).toEqual(['fiscaldata', 'frb-releases', 'nyfed-markets']);
    // No BEA or BLS (D1, D2) and no keyed source (S1).
    expect(JSON.stringify(registry)).not.toMatch(/bea\.gov|bls\.gov/i);
    for (const s of Object.values(registry.sources) as { key_required: boolean }[]) expect(s.key_required).toBe(false);
  });

  it('gives each kind of series its own revision behavior', () => {
    const cls = Object.fromEntries(registry.series.map((s: { id: string; class: string; revision: unknown }) => [s.id, [s.class, s.revision]]));
    expect(cls.effr).toEqual(['market_observation', { window: 'publication-day', statistics_window_business_days: 20 }]);
    expect(cls['fomc-target']).toEqual(['policy_target', { window: 'none' }]);
    expect(cls['debt-total']).toEqual(['administrative_daily', { window: 'none' }]);
    for (const id of ['m1-sa', 'm2-sa', 'm1-nsa', 'm2-nsa']) expect(cls[id]).toEqual(['revised_aggregate', { window: 'scheduled-release', alert_ratio: '0.05' }]);
    expect(Object.keys(CLASS_RULES).sort()).toEqual(['administrative_daily', 'market_observation', 'policy_target', 'revised_aggregate']);
  });

  it('carries the providers\' own license words and the New York Fed notice with its placeholders', () => {
    const ny = registry.sources['nyfed-markets'];
    expect(ny.pass_through).toBe(true);
    expect(ny.modification_label).toBe(true);
    expect(ny.notice).toContain('is subject to the Terms of Use posted at newyorkfed.org');
    expect(ny.notice).toContain('does not sanction or endorse any particular republication');
    expect(registry.sources.fiscaldata.license).toContain('for non-commercial or commercial purposes');
    expect(registry.sources['frb-releases'].license).toContain('Please cite to the Board as the source of the information.');
    expect(find(registry, 'fomc-target').derived_from.method).toMatch(/^Derived by RadMage Finance/);
  });

  it('dates releases by rule, calendar or first sight, each from when its source supports it', () => {
    const basis = Object.fromEntries(registry.series.map((s: { id: string; release: { basis: string } }) => [s.id, s.release.basis]));
    expect(basis).toEqual({ effr: 'rule', 'fomc-target': 'rule', 'debt-total': 'first-seen', 'debt-held-public': 'first-seen', 'debt-intragov': 'first-seen', 'm1-sa': 'calendar', 'm2-sa': 'calendar', 'm1-nsa': 'calendar', 'm2-nsa': 'calendar' });
    expect(registry.calendars['nyfed-business-days']).toMatchObject({ kind: 'rule', publish_time: '09:00', publish_time_zone: 'America/New_York', grace_hours: 6, rule_valid_from: '2026-10-05' });
    expect(registry.calendars['frb-h6-release-dates']).toMatchObject({ kind: 'calendar', publish_time: '13:00', publish_time_zone: 'America/New_York', calendar_valid_from: '2021-02-23' });
    expect(registry.calendars['fiscaldata-release']).toMatchObject({ publish_time: null, publish_time_zone: 'unknown', publish_time_zone_candidates: ['America/New_York', 'UTC'] });
    expect(registry.family_policy.review).toEqual({ permissions: ['admin', 'maintain', 'write'] });
    expect(registry.sources['frb-releases'].route_notices.map((n: { date: string; affects_registered_route: boolean }) => [n.date, n.affects_registered_route])).toEqual([['2027-03-31', false], ['2027-07-01', false]]);
    expect(registry.family_policy.archive).toBe('permanent');
  });

  it('records the publisher data kept as published: the Sunday EFFR record and the two debt dates', () => {
    expect(find(registry, 'effr').known_inconsistencies.map((k: { period: string }) => k.period)).toEqual(['2003-07-20']);
    expect(find(registry, 'fomc-target').known_inconsistencies).toBeUndefined();
    expect(find(registry, 'debt-total').known_inconsistencies.map((k: { period: string }) => k.period)).toEqual(['2011-02-01', '2025-08-04']);
  });
});

describe('registry rules catch broken registries', () => {
  const problemsAfter = (change: (r: ReturnType<typeof copy>) => void) => {
    const r = copy();
    change(r);
    return registryProblems(r).join('\n');
  };

  it('a class whose fields do not fit it', () => {
    expect(problemsAfter((r) => (find(r, 'effr').class = 'revised_aggregate'))).toMatch(/series effr: class revised_aggregate needs frequency month/);
    expect(problemsAfter((r) => (find(r, 'm2-sa').revision = { window: 'none' }))).toMatch(/m2-sa: class revised_aggregate needs revision window scheduled-release[\s\S]*needs revision.alert_ratio/);
    expect(problemsAfter((r) => (find(r, 'debt-total').revision.alert_ratio = '0.05'))).toMatch(/debt-total: revision.alert_ratio does not apply/);
    expect(problemsAfter((r) => (find(r, 'm1-sa').revision.alert_ratio = '1.5'))).toMatch(/m1-sa: alert_ratio must be between 0 and 1/);
    expect(problemsAfter((r) => (find(r, 'effr').staleness = { after_business_days: 3, follows: 'm1-sa' }))).toMatch(/effr: class market_observation needs exactly staleness.after_business_days/);
    expect(problemsAfter((r) => (find(r, 'm1-sa').continuity = { max_gap: 2, unit: 'months' }))).toMatch(/no missing month/);
    expect(problemsAfter((r) => (find(r, 'fomc-target').segment = 'year'))).toMatch(/fomc-target: class policy_target needs segment all/);
  });

  it('reserved or duplicate ids and unknown references', () => {
    expect(RESERVED_IDS).toContain('econ');
    expect(problemsAfter((r) => (find(r, 'debt-intragov').id = 'status'))).toMatch(/series status: reserved id/);
    expect(problemsAfter((r) => (find(r, 'm2-nsa').id = 'm1-nsa'))).toMatch(/series m1-nsa: duplicate id/);
    expect(problemsAfter((r) => (find(r, 'effr').source = 'nowhere'))).toMatch(/effr: unknown source nowhere/);
    expect(problemsAfter((r) => (find(r, 'fomc-target').staleness.follows = 'fomc-target'))).toMatch(/follows unknown or itself/);
    expect(problemsAfter((r) => (find(r, 'm1-sa').release.calendar = 'nyfed-business-days'))).toMatch(/m1-sa: release basis calendar but calendar nyfed-business-days is a rule/);
    expect(problemsAfter((r) => (r.sources.fiscaldata.attribution = 'Source: {publisher}'))).toMatch(/unknown placeholder \{publisher\}/);
    expect(problemsAfter((r) => (find(r, 'debt-total').release.calendar = 'frb-h6-release-dates'))).toMatch(/debt-total: release calendar frb-h6-release-dates is not its source's calendar/);
  });

  it('calendars that do not say from when they hold', () => {
    expect(problemsAfter((r) => delete r.calendars['nyfed-business-days'].rule_valid_from)).toMatch(/calendar nyfed-business-days: a rule needs rule_valid_from and no url/);
    expect(problemsAfter((r) => delete r.calendars['frb-h6-release-dates'].url)).toMatch(/calendar frb-h6-release-dates: a calendar needs a url and no rule_valid_from/);
    expect(problemsAfter((r) => (r.calendars['nyfed-business-days'].publish_time = null))).toMatch(/a rule needs a publish_time/);
  });

  it('shared requests that are not symmetric or not the same request', () => {
    expect(problemsAfter((r) => (find(r, 'm2-nsa').fetch.shared_with = ['m1-sa', 'm2-sa']))).toMatch(/m1-nsa: shared_with m2-nsa is not symmetric/);
    expect(problemsAfter((r) => (find(r, 'debt-intragov').fetch.parameters.sort = '-record_date'))).toMatch(/shared_with debt-intragov uses a different request/);
    expect(problemsAfter((r) => (find(r, 'fomc-target').fetch.shared_with = []))).toMatch(/derived_from series must be in fetch.shared_with/);
    expect(problemsAfter((r) => delete find(r, 'fomc-target').derived_from)).toMatch(/policy targets in this family are derived/);
  });

  it('extract eras with a gap, an overlap, an open end before the last, or the wrong fields', () => {
    expect(problemsAfter((r) => (find(r, 'effr').extract[1].from = '2008-12-17'))).toMatch(/extract effr-2008 does not start the period after effr-2000 ends/);
    expect(problemsAfter((r) => (find(r, 'effr').extract[1].from = '2008-12-15'))).toMatch(/does not start the period after/);
    expect(problemsAfter((r) => (find(r, 'effr').extract[0].to = null))).toMatch(/effr-2000 is open-ended but not last/);
    expect(problemsAfter((r) => (find(r, 'effr').extract[2].to = '2030-01-01'))).toMatch(/last extract era must be open-ended/);
    expect(problemsAfter((r) => (find(r, 'fomc-target').extract[0].lower = 'targetRateFrom'))).toMatch(/a rate takes value only/);
    expect(problemsAfter((r) => delete find(r, 'fomc-target').extract[1].upper)).toMatch(/a range takes lower and upper only/);
    expect(problemsAfter((r) => (find(r, 'm1-sa').extract[0].from = '1959-01-31'))).toMatch(/m1-sa: extract h6-sdmx-2021 periods are not month periods/);
    expect(problemsAfter((r) => (find(r, 'm2-nsa').extract[0].adjusted = 'SA'))).toMatch(/m2-nsa: extract h6-sdmx-2021: adjusted SA but seasonal_adjustment nsa/);
    expect(problemsAfter((r) => delete find(r, 'm1-sa').extract[0].series_name)).toMatch(/m1-sa: extract h6-sdmx-2021: SDMX needs series_name/);
    expect(problemsAfter((r) => delete find(r, 'm1-sa').extract[0].value)).toMatch(/m1-sa: extract h6-sdmx-2021: needs value/);
    expect(problemsAfter((r) => (find(r, 'effr').extract[0].series_name = 'M1.M'))).toMatch(/effr: extract effr-2000: SDMX fields on a json source/);
    expect(problemsAfter((r) => (find(r, 'debt-total').earliest = '1990-01-01'))).toMatch(/earliest 1990-01-01 comes before the first extract era/);
  });

  it('ranges out of order or with the wrong decimals', () => {
    expect(problemsAfter((r) => (find(r, 'effr').range = { min: '25.00', max: '-1.00' }))).toMatch(/effr: range min is not below max/);
    expect(problemsAfter((r) => (find(r, 'm2-sa').range.max = '1000000.00'))).toMatch(/m2-sa: range.max needs 1 decimals/);
  });

  it('the schema refuses unknown fields, keyed sources and family policy overrides', () => {
    const r = copy();
    find(r, 'effr').colour = 'blue';
    r.sources.fiscaldata.key_required = true;
    r.family_policy.unexpected_revision = 'publish';
    const errors = validate(schema, r).join('\n');
    expect(errors).toMatch(/\$\.series\[0\]: unknown property colour/);
    expect(errors).toMatch(/\$\.sources\.fiscaldata\.key_required: must be false/);
    expect(errors).toMatch(/\$\.family_policy\.unexpected_revision: must be "hold"/);
  });
});

describe('decimal comparison without floating point', () => {
  it('orders signs, zeros and long fractions exactly', () => {
    expect(compareDecimal('0.05', '1')).toBe(-1);
    expect(compareDecimal('1000000000000000.00', '999999999999999.99')).toBe(1);
    expect(compareDecimal('-0.00', '0')).toBe(0);
    expect(compareDecimal('-0.00', '1')).toBe(-1);
    expect(compareDecimal('-1.00', '-0.99')).toBe(-1);
    expect(compareDecimal('0.10', '0.1')).toBe(0);
    // Floating point would call these equal.
    expect(compareDecimal('9007199254740993.00', '9007199254740992.00')).toBe(1);
  });
});
