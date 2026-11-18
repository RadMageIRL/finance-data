// Time, business days and classification (DATA_CONVENTIONS v0.3 sections 2, 3, 11, 14.2, 17.3
// and 17.9): every class rule at and around its boundary, with the fixture holiday table.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// The pipeline modules are plain JavaScript: tests use them through a loose type.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/lib/calendar.mjs';
const { addDays, etDate, fourthTuesday, holidayTableProblems, makeCalendar, nextFourthTuesdayAfter, previousQuarter, snapshotId, snapshotTime, zonedTime } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/lib/classify.mjs';
const { classify, diffObservations, exceedsRatio } = m2 as unknown as Loose;
import * as m3 from '../../../pipeline/lib/tree.mjs';
const { deadlines } = m3 as unknown as Loose;


const registry = JSON.parse(readFileSync('pipeline/registry/econ.json', 'utf8'));
const holidays = JSON.parse(readFileSync('pipeline/registry/fed-holidays.json', 'utf8'));
const calendar = makeCalendar(holidays);
const series = (id: string) => registry.series.find((s: { id: string }) => s.id === id);
const none = { date: null, basis: 'not-recorded' };
const day = (period: string, value: string, more: Record<string, unknown> = {}) => ({ period, value, flags: [] as string[], released: none, extra: { p1: '3.85', p25: '3.87', p75: '3.89', p99: '3.90', volume_usd_billions: '99' }, ...more });

describe('time and business days', () => {
  it('derives ET dates from UTC times on both sides of midnight and of a clock change', () => {
    expect(etDate('2026-11-13T04:59:59Z')).toBe('2026-11-12');
    expect(etDate('2026-11-13T05:00:00Z')).toBe('2026-11-13');
    expect(etDate('2026-07-01T03:59:59Z')).toBe('2026-06-30');
    expect(etDate('2026-07-01T04:00:00Z')).toBe('2026-07-01');
  });

  it('converts a New York wall-clock time to UTC in winter and in summer', () => {
    expect(zonedTime('2026-11-16', '09:00', 'America/New_York')).toBe('2026-11-16T14:00:00Z');
    expect(zonedTime('2026-07-15', '09:00', 'America/New_York')).toBe('2026-07-15T13:00:00Z');
    expect(zonedTime('2026-11-18', '21:15', 'UTC')).toBe('2026-11-18T21:15:00Z');
  });

  it('skips weekends and the fixture holidays when counting business days', () => {
    expect(calendar.isBusinessDay('2026-11-11')).toBe(false);
    expect(calendar.nextBusinessDay('2026-11-10')).toBe('2026-11-12');
    expect(calendar.nextBusinessDay('2026-11-13')).toBe('2026-11-16');
    expect(calendar.addBusinessDays('2026-11-24', 3)).toBe('2026-11-30');
    expect(calendar.isBusinessDay('2026-07-03')).toBe(true);
  });

  it('refuses a date in a year the holiday table does not cover', () => {
    expect(() => calendar.isBusinessDay('2031-01-02')).toThrow(/does not cover/);
    expect(() => calendar.nextBusinessDay('2030-12-31')).toThrow(/does not cover/);
    expect(() => calendar.isBusinessDay('1992-12-31')).toThrow(/does not cover/);
    // A year end inside the table is no obstacle.
    expect(calendar.nextBusinessDay('2026-12-31')).toBe('2027-01-04');
  });

  it('refuses a malformed holiday table', () => {
    expect(holidayTableProblems(holidays)).toEqual([]);
    expect(holidayTableProblems({ ...holidays, status: 'guess' })).toEqual(['holiday table: status must be verified or fixture']);
    expect(holidayTableProblems({ ...holidays, holidays: ['2026-11-14'] })).toEqual(['holiday table: 2026-11-14 is a weekend day']);
    expect(() => makeCalendar({ ...holidays, years: [2027, 2026] })).toThrow(/years/);
  });

  it('finds the fourth Tuesday, the H.6 release rule', () => {
    expect(fourthTuesday(2026, 11)).toBe('2026-11-24');
    expect(fourthTuesday(2026, 10)).toBe('2026-10-27');
    expect(fourthTuesday(2026, 9)).toBe('2026-09-22');
    expect(nextFourthTuesdayAfter('2026-10-27')).toBe('2026-11-24');
    expect(nextFourthTuesdayAfter('2026-11-24')).toBe('2026-12-22');
  });

  it('names the previous calendar quarter of a date', () => {
    expect(previousQuarter('2026-10-01')).toEqual({ start: '2026-07-01', end: '2026-09-30' });
    expect(previousQuarter('2026-02-10')).toEqual({ start: '2025-10-01', end: '2025-12-31' });
  });

  it('turns a time into a snapshot id and back', () => {
    expect(snapshotId('2026-11-16T14:17:00Z')).toBe('20261116T141700Z');
    expect(snapshotTime('20261116T141700Z')).toBe('2026-11-16T14:17:00Z');
    expect(addDays('2026-11-16', -59)).toBe('2026-09-18');
  });

  it('computes each class its own deadline for the next unseen period', () => {
    const effr = deadlines(series('effr'), { last_period: '2026-11-12' }, registry, calendar);
    expect(effr).toEqual({ expected: '2026-11-16T14:00:00Z', deadline: '2026-11-16T20:00:00Z', staleAt: '2026-11-19T20:00:00Z' });
    const debt = deadlines(series('debt-total'), { last_period: '2026-11-12' }, registry, calendar);
    // Fiscal Data's zone is unknown (4.5): due at the UTC reading, late only after the ET reading.
    expect(debt).toEqual({ expected: '2026-11-16T21:15:00Z', deadline: '2026-11-17T08:15:00Z', staleAt: '2026-11-20T08:15:00Z' });
    const h6 = deadlines(series('m1-sa'), { last_period: '2026-09', source_marker: { data_release_date: '2026-10-27' } }, registry, calendar);
    expect(h6).toEqual({ expected: '2026-11-24T18:00:00Z', deadline: '2026-11-25T00:00:00Z', staleAt: '2026-12-02T00:00:00Z' });
    expect(deadlines(series('fomc-target'), { last_period: '2026-09-17' }, registry, calendar)).toBeNull();
  });
});

describe('differences and the alert ratio', () => {
  it('ignores released and reports added, removed and changed members', () => {
    const a = [day('2026-11-10', '3.88'), day('2026-11-12', '3.88')];
    const b = [day('2026-11-10', '3.88', { released: { date: '2026-11-12', basis: 'rule' } }), day('2026-11-12', '3.87', { flags: ['r'] }), day('2026-11-13', '3.88')];
    const d = diffObservations(a, b);
    expect(d.added).toEqual(['2026-11-13']);
    expect(d.removed).toEqual([]);
    expect(d.changed).toEqual([{ period: '2026-11-12', fields: [{ field: 'flags', before: '[]', after: '["r"]' }, { field: 'value', before: '3.88', after: '3.87' }] }]);
  });

  it('alerts above 5 percent and not at exactly 5 percent', () => {
    expect(exceedsRatio('100.0', '105.0', '0.05')).toBe(false);
    expect(exceedsRatio('100.0', '105.1', '0.05')).toBe(true);
    expect(exceedsRatio('100.0', '94.9', '0.05')).toBe(true);
    expect(exceedsRatio('100.0', '95.0', '0.05')).toBe(false);
    expect(exceedsRatio('0.0', '0.1', '0.05')).toBe(true);
    expect(exceedsRatio('0.0', '0.0', '0.05')).toBe(false);
  });
});

describe('market observation (EFFR)', () => {
  const effr = series('effr');
  const published = [day('2026-11-09', '3.88'), day('2026-11-10', '3.88'), day('2026-11-12', '3.88')];
  const ctx = (runEtDate: string) => ({ runEtDate, calendar });
  const revised = (more = {}) => [published[0], published[1], day('2026-11-12', '3.87', more)];

  it('publishes a new day as appended and an identical candidate as unchanged', () => {
    expect(classify(effr, published, [...published, day('2026-11-13', '3.88')], ctx('2026-11-16')).outcome).toBe('appended');
    expect(classify(effr, published, published, ctx('2026-11-16')).outcome).toBe('unchanged');
  });

  it('expects a revision on the publication day and holds it the day after', () => {
    const on = classify(effr, published, revised(), ctx('2026-11-13'));
    expect(on.outcome).toBe('revised-expected');
    expect(on.basis.get('2026-11-12')).toBe('EFFR publication day 2026-11-13');
    expect(classify(effr, published, revised(), ctx('2026-11-16')).outcome).toBe('revised-unexpected');
  });

  it('expects a revision the publisher flagged r up to 2 business days after the publication day, and holds on the third', () => {
    expect(classify(effr, published, revised({ flags: ['r'] }), ctx('2026-11-16')).outcome).toBe('revised-expected');
    expect(classify(effr, published, revised({ flags: ['r'] }), ctx('2026-11-17')).outcome).toBe('revised-expected');
    expect(classify(effr, published, revised({ flags: ['r'] }), ctx('2026-11-18')).outcome).toBe('revised-unexpected');
  });

  it('holds a flag that appears on its own outside the publication day', () => {
    const flagOnly = [published[0], published[1], day('2026-11-12', '3.88', { flags: ['footnote:7'] })];
    expect(classify(effr, published, flagOnly, ctx('2026-11-20')).outcome).toBe('revised-unexpected');
  });

  it('expects quarterly statistics updates from business day 1 through 20 after the quarter and holds on day 21', () => {
    const q = [day('2026-09-29', '3.63'), day('2026-09-30', '3.63')];
    const stats = [q[0], day('2026-09-30', '3.63', { extra: { p1: '3.85', p25: '3.87', p75: '3.89', p99: '3.95', volume_usd_billions: '101' } })];
    expect(calendar.addBusinessDays('2026-09-30', 20)).toBe('2026-10-29');
    expect(classify(effr, q, stats, ctx('2026-10-01')).outcome).toBe('revised-expected');
    expect(classify(effr, q, stats, ctx('2026-10-29')).outcome).toBe('revised-expected');
    expect(classify(effr, q, stats, ctx('2026-10-30')).outcome).toBe('revised-unexpected');
    // A value change in the same window is not a statistics update.
    expect(classify(effr, q, [q[0], day('2026-09-30', '3.64')], ctx('2026-10-15')).outcome).toBe('revised-unexpected');
  });

  it('holds a removed period and a period inserted into history', () => {
    expect(classify(effr, published, [published[0], published[2]], ctx('2026-11-13')).reason).toBe('a published period was removed');
    const inserted = [published[0], published[1], day('2026-11-11', '3.88'), published[2]];
    expect(classify(effr, published, inserted, ctx('2026-11-13')).reason).toBe('a new period on or before the last published period');
  });

  it('holds the whole series when an allowed change comes with a disallowed one', () => {
    const mixed = [published[0], day('2026-11-10', '3.90'), day('2026-11-12', '3.87')];
    expect(classify(effr, published, mixed, ctx('2026-11-13')).outcome).toBe('revised-unexpected');
  });
});

describe('policy target (FOMC)', () => {
  const target = series('fomc-target');
  const point = (effective: string, lower: string, upper: string, more = {}) => ({ effective, kind: 'range', lower, upper, released: none, ...more });
  const published = [point('2026-09-01', '3.50', '3.75', { starts_before_data: true }), point('2026-09-17', '3.75', '4.00')];
  const ctx = { runEtDate: '2026-11-13', calendar };

  it('publishes a new change point after the last one as appended', () => {
    expect(classify(target, published, [...published, point('2026-11-12', '3.50', '3.75')], ctx).outcome).toBe('appended');
  });

  it('holds a moved change point on its own', () => {
    const moved = [published[0], point('2026-09-18', '3.75', '4.00')];
    expect(classify(target, published, moved, ctx).outcome).toBe('revised-unexpected');
  });

  it('expects a change point that follows an expected EFFR correction of the same record', () => {
    const basis = new Map([['2026-11-12', 'EFFR publication day 2026-11-13']]);
    const source = { outcome: 'revised-expected', diff: { changed: [{ period: '2026-11-12', fields: [] }] }, basis, candidate: [{ period: '2026-11-10' }, { period: '2026-11-12' }] };
    const before = [...published, point('2026-11-12', '3.50', '3.75')];
    const r = classify(target, before, published, { ...ctx, source });
    expect(r.outcome).toBe('revised-expected');
    expect(r.basis.get('2026-11-12')).toBe('EFFR publication day 2026-11-13');
  });

  it('holds any difference while the series it is derived from is held', () => {
    const source = { outcome: 'revised-unexpected', diff: { changed: [] }, basis: new Map(), candidate: [] };
    const r = classify(target, published, [...published, point('2026-11-12', '3.50', '3.75')], { ...ctx, source });
    expect(r.outcome).toBe('revised-unexpected');
    expect(r.reason).toBe('derived from a held series');
  });
});

describe('administrative daily (Debt to the Penny)', () => {
  const debt = series('debt-total');
  const row = (period: string, value: string) => ({ period, value, flags: [], released: none });
  const published = [row('2026-11-10', '40584130080272.89'), row('2026-11-12', '40594506856903.25')];
  const ctx = { runEtDate: '2026-11-16', calendar };

  it('publishes new record dates and holds any change to a published value', () => {
    expect(classify(debt, published, [...published, row('2026-11-13', '40596506856903.25')], ctx).outcome).toBe('appended');
    const corrected = [row('2026-11-10', '40584130080272.90'), published[1]];
    const r = classify(debt, published, corrected, ctx);
    expect(r.outcome).toBe('revised-unexpected');
    expect(r.reason).toBe('a published value changed and no revision is expected for this series');
  });
});

describe('revised aggregate (H.6)', () => {
  const m1 = series('m1-sa');
  const month = (period: string, value: string) => ({ period, value, flags: [], released: none });
  const published = [month('2026-08', '19950.0'), month('2026-09', '20000.0')];
  const ctx = (latest: string) => ({ runEtDate: '2026-11-24', calendar, marker: { latest_release_date: latest }, publishedMarker: { data_release_date: '2026-10-27' } });

  it('expects revisions that come with a newer release date and marks the large ones', () => {
    const next = [month('2026-08', '19951.0'), month('2026-09', '21000.1'), month('2026-10', '21100.0')];
    const r = classify(m1, published, next, ctx('2026-11-24'));
    expect(r.outcome).toBe('revised-expected');
    expect(r.basis.get('2026-09')).toBe('H.6 release 2026-11-24');
    expect(r.large).toEqual(['2026-09']);
  });

  it('holds a change, and even a new month, that arrives without a new release date', () => {
    expect(classify(m1, published, [published[0], month('2026-09', '20000.1')], ctx('2026-10-27')).outcome).toBe('revised-unexpected');
    expect(classify(m1, published, [...published, month('2026-10', '20100.0')], ctx('2026-10-27')).reason).toBe('the data changed without a new release date');
  });

  it('publishes new months alone as appended and holds a removed month even with a new release', () => {
    expect(classify(m1, published, [...published, month('2026-10', '20100.0')], ctx('2026-11-24')).outcome).toBe('appended');
    expect(classify(m1, published, [published[0]], ctx('2026-11-24')).outcome).toBe('revised-unexpected');
  });
});
