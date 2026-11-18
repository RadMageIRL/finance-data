// The first collector adapters against the saved provider bytes (DATA_CONVENTIONS v0.3 section
// 18): the zip and SDMX readers, the requests each adapter sends, pacing and budgets, and a
// first publication of the whole saved history through the adapters. No network.
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import * as m1 from '../../../pipeline/collectors/adapters.mjs';
import * as m2 from '../../../pipeline/lib/fixture-transport.mjs';
import * as m3 from '../../../pipeline/lib/zip.mjs';
import * as m4 from '../../../pipeline/lib/sdmx.mjs';
import * as m5 from '../../../pipeline/lib/normalize.mjs';
import * as m6 from '../../../pipeline/bin/fixture-scenario.mjs';
import * as m7 from '../../../pipeline/lib/run.mjs';
import * as m8 from '../../../pipeline/lib/fixture-fetch.mjs';

// The pipeline modules are plain JavaScript: tests use them through a loose type.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
const { ADAPTERS, adapterFetch, fiscalCalendarTimes, h6ReleaseDates, requestHeaders } = m1 as unknown as Loose;
const { effrRawRecord, loadRawFixtures, makeFixtureTransport } = m2 as unknown as Loose;
const { zipEntries, zipRead, zipWrite } = m3 as unknown as Loose;
const { readSdmx } = m4 as unknown as Loose;
const { normalizeDebt, normalizeEffr, normalizeH6 } = m5 as unknown as Loose;
const { effrDay, loadInputs } = m6 as unknown as Loose;
const { runCollector } = m7 as unknown as Loose;
const { makeWait } = m8 as unknown as Loose;

const inputs = loadInputs();
const raw = loadRawFixtures();
const state = () => ({ ...raw, effr: [...raw.effr], debt: [...raw.debt] });
const roots: string[] = [];
afterAll(() => {
  for (const r of roots) rmSync(r, { recursive: true, force: true });
});

describe('zip reader', () => {
  const xml = '<a>hello</a>'.repeat(50);
  const zip = zipWrite([{ name: 'H6_data.xml', data: xml }, { name: 'other.txt', data: 'x' }]);

  it('reads a named file back and writes the same bytes for the same input', () => {
    expect(zipEntries(zip).map((e: Loose) => e.name)).toEqual(['H6_data.xml', 'other.txt']);
    expect(zipRead(zip, 'H6_data.xml', 10_000).toString('utf8')).toBe(xml);
    expect(zipWrite([{ name: 'H6_data.xml', data: xml }, { name: 'other.txt', data: 'x' }]).equals(zip)).toBe(true);
  });

  it('refuses a file over the size limit before inflating, a damaged file and a missing name', () => {
    expect(() => zipRead(zip, 'H6_data.xml', 100)).toThrow(/is 600 bytes, over the limit 100/);
    expect(() => zipRead(zip, 'absent.xml', 10_000)).toThrow(/0 entries named absent.xml/);
    const damaged = Buffer.from(zip);
    // Flip a bit of the stored CRC-32 in the central directory entry of the first file.
    const central = damaged.indexOf(Buffer.from([0x50, 0x4b, 0x01, 0x02]));
    damaged.writeUInt8(damaged.readUInt8(central + 16) ^ 0x01, central + 16);
    expect(() => zipRead(damaged, 'H6_data.xml', 10_000)).toThrow(/fails its CRC-32/);
    expect(() => zipRead(Buffer.from('not a zip at all, just some text'), 'H6_data.xml', 10_000)).toThrow(/no end of central directory record/);
  });

  it('refuses an encrypted entry and an unknown compression method', () => {
    const central = zip.indexOf(Buffer.from([0x50, 0x4b, 0x01, 0x02]));
    const encrypted = Buffer.from(zip);
    encrypted.writeUInt8(encrypted.readUInt8(central + 8) | 0x01, central + 8);
    expect(() => zipRead(encrypted, 'H6_data.xml', 10_000)).toThrow(/is encrypted/);
    const method = Buffer.from(zip);
    method[central + 10] = 12;
    expect(() => zipRead(method, 'H6_data.xml', 10_000)).toThrow(/uses compression method 12/);
  });
});

describe('SDMX reader', () => {
  const doc = (inner: string) => `<?xml version="1.0"?><m:G xmlns:m="x"><m:Header><m:Prepared>2026-10-19T15:17:34</m:Prepared></m:Header><f:DataSet>${inner}</f:DataSet></m:G>`;
  const seriesXml = (name: string, value: string) => `<kf:Series ADJUSTED="SA" SERIES_NAME="${name}" UNIT_MULT="1e+09"><f:Annotations><c:Annotation><c:AnnotationText>M1; adjusted &amp; more</c:AnnotationText></c:Annotation></f:Annotations><f:Obs OBS_STATUS="A" OBS_VALUE="${value}" TIME_PERIOD="2026-09-30" /></kf:Series>`;

  it('keeps every copy of the series asked for, with their attributes, and nothing else', () => {
    const r = readSdmx(doc(seriesXml('M1.M', '1.0') + seriesXml('M1.WM', '2.0') + seriesXml('M1.M', '1.0')), ['M1.M', 'M2.M']);
    expect(r.prepared).toBe('2026-10-19T15:17:34');
    expect(r.series).toEqual([
      { attributes: { ADJUSTED: 'SA', SERIES_NAME: 'M1.M', UNIT_MULT: '1e+09' }, observations: [{ OBS_STATUS: 'A', OBS_VALUE: '1.0', TIME_PERIOD: '2026-09-30' }] },
      { attributes: { ADJUSTED: 'SA', SERIES_NAME: 'M1.M', UNIT_MULT: '1e+09' }, observations: [{ OBS_STATUS: 'A', OBS_VALUE: '1.0', TIME_PERIOD: '2026-09-30' }] },
    ]);
  });

  it('refuses a document type declaration, an entity declaration and an unknown entity', () => {
    expect(() => readSdmx(`<!DOCTYPE x SYSTEM "http://example.invalid/x.dtd">${doc('')}`, ['M1.M'])).toThrow(/document type or entity declaration is refused/);
    expect(() => readSdmx(`<!ENTITY e "v">${doc('')}`, ['M1.M'])).toThrow(/document type or entity declaration is refused/);
    expect(() => readSdmx(doc('<kf:Series SERIES_NAME="M1.M" NOTE="&e;"></kf:Series>'), ['M1.M'])).toThrow(/unsupported entity in attribute NOTE/);
    expect(() => readSdmx(doc('<kf:Series SERIES_NAME="M1.M">'), ['M1.M'])).toThrow(/is not closed/);
  });

  it('reads the reduced H.6 release: four registered series, two of them twice, 813 months each', () => {
    const r = readSdmx(zipRead(raw.h6Zip, 'H6_data.xml', 64_000_000).toString('utf8'), ['M1.M', 'M2.M', 'M1_N.M', 'M2_N.M']);
    expect(r.series.map((s: Loose) => s.attributes.SERIES_NAME)).toEqual(['M1.M', 'M1_N.M', 'M1.M', 'M2.M', 'M1_N.M', 'M2_N.M']);
    expect(r.series.every((s: Loose) => s.observations.length === 813)).toBe(true);
    expect(r.series[0].observations[0]).toEqual({ OBS_STATUS: 'A', OBS_VALUE: '138.9', TIME_PERIOD: '1959-01-31' });
  });
});

describe('adapters', () => {
  const fetchOver = (transport: Loose, more: Loose = {}) => adapterFetch({ registry: inputs.registry, transport, ...more });

  it('send exactly the registered requests, named RadMage Finance with its public URL, with no cookies or keys', async () => {
    const transport = makeFixtureTransport(state());
    const fetch = fetchOver(transport);
    await fetch({ group: 'effr', start: '2026-09-18', end: '2026-11-16', page: 1 });
    await fetch({ group: 'debt-total', start: '2026-09-18', end: '2026-11-16', page: 1 });
    await fetch({ group: 'm1-sa', start: '1959-01', end: '2026-11-16', page: 1 });
    expect(transport.calls.map((c: Loose) => c.url)).toEqual([
      'https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2026-09-18&endDate=2026-11-16',
      'https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?filter=record_date:gte:2026-09-18&sort=record_date&page[size]=10000&page[number]=1',
      'https://www.federalreserve.gov/releases/h6/data/FRB_h6_xml.zip',
      'https://www.federalreserve.gov/releases/h6/releaseDates.json',
    ]);
    // RadMage Finance and its public URL (18); no provider requires a contact, so no From header.
    const expected = { 'User-Agent': 'RadMage Finance (+https://radmagelabs.com/finance/)', Accept: '*/*' };
    for (const id of Object.keys(inputs.registry.sources)) expect(requestHeaders(inputs.registry.sources[id])).toEqual(expected);
    expect(transport.calls.every((c: Loose) => JSON.stringify(c.headers) === JSON.stringify(expected))).toBe(true);
    expect(Object.keys(ADAPTERS)).toEqual(['effr', 'debt-total', 'm1-sa']);
  });

  it('read the whole saved history of every source into valid responses', async () => {
    const fetch = fetchOver(makeFixtureTransport(state()));
    const e = normalizeEffr((await fetch({ group: 'effr', start: '2000-07-03', end: '2026-11-18', page: 1 })).body, inputs.registry, inputs.sourceTable);
    expect([e.problems, e.series.effr.length, e.series.effr[0].period]).toEqual([[], 6625, '2000-07-03']);
    const d = normalizeDebt([(await fetch({ group: 'debt-total', start: '1993-04-01', end: '2026-11-18', page: 1 })).body], inputs.registry, inputs.sourceTable);
    expect([d.problems, d.series['debt-total'].length, d.marker]).toEqual([[], 8433, { total_count: 8433 }]);
    const h = normalizeH6((await fetch({ group: 'm1-sa', start: '1959-01', end: '2026-11-18', page: 1 })).body, inputs.registry, inputs.sourceTable);
    expect([h.problems, h.series['m2-nsa'].length, h.series['m1-sa'][0], h.marker.latest_release_date]).toEqual([[], 813, { period: '1959-01', value: '138.9', flags: [] }, '2026-10-27']);
  });

  it('wait the minimum interval between two requests to the same host and stop at the request budget', async () => {
    const wait = makeWait();
    const fetch = fetchOver(makeFixtureTransport(state()), { wait, budgets: { requestsPerHost: 3, downloadBytesPerRun: 25_000_000 } });
    await fetch({ group: 'm1-sa', start: '1959-01', end: '2026-11-16', page: 1 });
    expect(wait.calls).toEqual([1]);
    const second = await fetch({ group: 'm1-sa', start: '1959-01', end: '2026-11-16', page: 1 });
    expect(second).toEqual({ status: 0, body: null, budget: 'requests per host' });
    expect(fetch.log.length).toBe(3);
  });

  it('stop at the download budget', async () => {
    const fetch = fetchOver(makeFixtureTransport(state()), { budgets: { requestsPerHost: 10, downloadBytesPerRun: 1000 } });
    expect(await fetch({ group: 'effr', start: '2000-07-03', end: '2026-11-16', page: 1 })).toEqual({ status: 0, body: null, budget: 'download bytes per run' });
  });

  it('pass a failure status with its Retry-After, and a timeout, to the run', async () => {
    const empty = Buffer.alloc(0);
    const transport = makeFixtureTransport(state(), { 'markets.newyorkfed.org': [{ status: 503, headers: { 'retry-after': '30' }, bytes: empty }, { timeout: true }, { status: 404, headers: {}, bytes: empty }] });
    const fetch = fetchOver(transport);
    const r = { group: 'effr', start: '2026-09-18', end: '2026-11-16', page: 1 };
    expect(await fetch(r)).toEqual({ status: 503, retry_after: 30 });
    expect(await fetch(r)).toEqual({ timeout: true });
    expect(await fetch(r)).toEqual({ status: 404 });
  });

  it('never send a request to a host other than the registered one', async () => {
    const registry = JSON.parse(JSON.stringify(inputs.registry));
    registry.series[0].fetch.endpoint = 'https://example.invalid/api/rates/unsecured/effr/search.json';
    const transport = makeFixtureTransport(state());
    const fetch = adapterFetch({ registry, transport });
    expect(await fetch({ group: 'effr', start: '2026-09-18', end: '2026-11-16', page: 1 })).toEqual({ status: 0, body: null });
    expect(transport.calls).toEqual([]);
  });

  it('turn unreadable bytes into an invalid response, never a guess', async () => {
    const bad = (bytes: Buffer) => ({ status: 200, headers: {}, bytes });
    const fetch = fetchOver(makeFixtureTransport(state(), { 'markets.newyorkfed.org': [bad(Buffer.from('<html>busy</html>'))], 'www.federalreserve.gov': [bad(Buffer.from('not a zip, only words long enough'))] }));
    const e = await fetch({ group: 'effr', start: '2026-09-18', end: '2026-11-16', page: 1 });
    expect(normalizeEffr(e.body, inputs.registry, inputs.sourceTable).problems).toEqual(['refRates is not a list']);
    const h = await fetch({ group: 'm1-sa', start: '1959-01', end: '2026-11-16', page: 1 });
    expect(h.body).toEqual({ unreadable: 'zip: no end of central directory record' });
    expect(normalizeH6(h.body, inputs.registry, inputs.sourceTable).problems).toEqual(['series is not a list']);
  });

  it('answer like the providers: newest first, pages, 404 past the last page and for a page size over 10,000', async () => {
    const transport = makeFixtureTransport(state());
    const get = async (url: string) => transport({ url, headers: {} });
    const effr = JSON.parse((await get('https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2026-11-09&endDate=2026-11-12')).bytes.toString('utf8'));
    expect(effr.refRates.map((r: Loose) => r.effectiveDate)).toEqual(['2026-11-12', '2026-11-10', '2026-11-09']);
    const base = 'https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?filter=record_date:gte:2026-11-01&sort=record_date';
    const page = JSON.parse((await get(`${base}&page[size]=5&page[number]=2`)).bytes.toString('utf8'));
    expect([page.data.length, page.meta['total-count'], page.meta['total-pages']]).toEqual([3, 8, 2]);
    expect((await get(`${base}&page[size]=5&page[number]=3`)).status).toBe(404);
    expect((await get(`${base}&page[size]=10001&page[number]=1`)).status).toBe(404);
  });

  it('read the Board release dates with their markers and the Fiscal Data calendar times', () => {
    const dates = h6ReleaseDates(raw.h6Dates);
    expect(dates[dates.length - 1]).toBe('2026-10-27');
    expect(dates).toContain('2021-02-23***');
    expect(dates).toContain('2021-03-23**');
    const times = fiscalCalendarTimes(raw.calendar, '015-BFS-2014Q3-065');
    expect(times['2026-11-16']).toBe('21:15');
    expect(new Set(Object.values(times))).toEqual(new Set(['21:15']));
    expect(fiscalCalendarTimes(raw.calendar, 'another-dataset')).toEqual({});
  });
});

describe('a first publication of the whole saved history', () => {
  it('publishes all nine series from their expected beginnings, keeping the three kinds of number apart', async () => {
    const root = mkdtempSync(join(tmpdir(), 'rmf-p23-'));
    roots.push(root);
    const s = state();
    s.effr.push(effrRawRecord(effrDay('2026-11-13')));
    const transport = makeFixtureTransport(s);
    const r = await runCollector({ root, mode: 'fixture', registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays, now: '2026-11-16T14:17:00Z', run: { id: 'full-1', attempt: 1, trigger: 'schedule', collector_commit: '0'.repeat(40) }, fetch: adapterFetch({ registry: inputs.registry, transport }), wait: makeWait() });
    expect(r.outcome).toBe('published');
    expect((r.record as Loose).alerts).toEqual([]);
    const m = JSON.parse(readFileSync(join(root, 'live/manifest.json'), 'utf8'));
    const facts = Object.fromEntries(Object.entries(m.series).map(([id, v]) => [id, [(v as Loose).class, (v as Loose).frequency, (v as Loose).last_period, (v as Loose).status]]));
    expect(facts).toEqual({
      effr: ['market_observation', 'business-day', '2026-11-13', 'fresh'],
      'fomc-target': ['policy_target', 'change-point', '2026-09-17', 'fresh'],
      'debt-total': ['administrative_daily', 'business-day', '2026-11-12', 'fresh'],
      'debt-held-public': ['administrative_daily', 'business-day', '2026-11-12', 'fresh'],
      'debt-intragov': ['administrative_daily', 'business-day', '2026-11-12', 'fresh'],
      'm1-sa': ['revised_aggregate', 'month', '2026-09', 'fresh'],
      'm2-sa': ['revised_aggregate', 'month', '2026-09', 'fresh'],
      'm1-nsa': ['revised_aggregate', 'month', '2026-09', 'fresh'],
      'm2-nsa': ['revised_aggregate', 'month', '2026-09', 'fresh'],
    });
    const snap = JSON.parse(readFileSync(join(root, 'live', m.snapshot.path), 'utf8'));
    expect([snap.series.effr.observation_count, snap.series['fomc-target'].observation_count, snap.series['debt-total'].observation_count, snap.series['m1-sa'].observation_count]).toEqual([6626, 73, 8433, 813]);
    // The anomalies are published exactly as the source has them.
    const object = (path: string) => JSON.parse(readFileSync(join(root, 'live', path), 'utf8')).observations;
    const year = (id: string, y: string) => object(snap.series[id].objects.find((o: Loose) => o.segment === y).path);
    expect(year('debt-total', '2025').find((o: Loose) => o.period === '2025-08-04').value).toBe('36828164797914.31');
    expect(year('effr', '2003').some((o: Loose) => o.period === '2003-07-20')).toBe(true);
    expect(year('debt-total', '2019').some((o: Loose) => o.period === '2019-04-03')).toBe(false);
    expect(year('debt-held-public', '1993')[0]).toMatchObject({ period: '1993-04-01', value: null, missing: { code: 'not-published', note: '' } });
  });

  it('carries a series forward when its history arrives cut short', async () => {
    const root = mkdtempSync(join(tmpdir(), 'rmf-p23-'));
    roots.push(root);
    const s = state();
    s.effr = s.effr.filter((x: Loose) => x.date >= '2001-01-02');
    const r = await runCollector({ root, mode: 'fixture', registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays, now: '2026-11-13T14:17:00Z', run: { id: 'short-1', attempt: 1, trigger: 'schedule', collector_commit: '0'.repeat(40) }, fetch: adapterFetch({ registry: inputs.registry, transport: makeFixtureTransport(s) }), wait: makeWait() });
    expect((r.record as Loose).series).toMatchObject({ effr: 'invalid', 'fomc-target': 'invalid', 'debt-total': 'appended' });
    expect((r.record as Loose).alerts).toEqual(['invalid-series:effr', 'invalid-series:fomc-target']);
    const m = JSON.parse(readFileSync(join(root, 'live/manifest.json'), 'utf8'));
    expect(m.series.effr.status).toBe('not-yet-published');
    const snap = JSON.parse(readFileSync(join(root, 'live', m.snapshot.path), 'utf8'));
    expect(snap.series.effr.attempt.error).toBe('2001-01-02: the series must begin at 2000-07-03');
  });
});
