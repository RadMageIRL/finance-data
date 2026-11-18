// The fixture transport (DATA_CONVENTIONS section 18 and appendix B): answers the collector
// adapters' requests from saved provider bytes held in memory, behaving like each provider's
// endpoint for the parameters the adapters send (date filters, paging, the page size limit).
// It is the only transport that exists; nothing here opens a network connection.
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const RAW = join(dirname(fileURLToPath(import.meta.url)), '..', 'fixtures', 'raw');
const EFFR_RECORD = /\{ "effectiveDate": "(\d{4}-\d{2}-\d{2})"[^{}]*\}/g;

/**
 * The saved provider responses: the whole EFFR history as raw record texts (so every number
 * keeps the provider's digits), the whole Debt to the Penny history as rows, the reduced H.6
 * release zip with its release dates, and the Fiscal Data release calendar excerpt.
 */
export function loadRawFixtures() {
  const effrText = gunzipSync(readFileSync(join(RAW, 'nyfed-effr-full.json.gz'))).toString('utf8');
  const effr = [...effrText.matchAll(EFFR_RECORD)].map((m) => ({ date: m[1], text: m[0] }));
  if (effr.length !== JSON.parse(effrText).refRates.length) throw new Error('fixture: the EFFR raw records do not split cleanly');
  const debt = JSON.parse(gunzipSync(readFileSync(join(RAW, 'fiscaldata-dtp-full.json.gz'))).toString('utf8')).data;
  return {
    effr,
    debt,
    h6Zip: readFileSync(join(RAW, 'frb-h6-reduced.zip')),
    h6Dates: JSON.parse(readFileSync(join(RAW, 'frb-h6-releaseDates.json'), 'utf8')),
    calendar: JSON.parse(readFileSync(join(RAW, 'fiscaldata-calendar-excerpt.json'), 'utf8')),
  };
}

/** A synthetic EFFR record as raw text in the provider's layout. */
export function effrRawRecord(record) {
  return { date: record.effectiveDate, text: `{ ${Object.entries(record).map(([k, v]) => `${JSON.stringify(k)}: ${JSON.stringify(v)}`).join(" ,")}}` };
}

const bytes = (text) => Buffer.from(text, 'utf8');
const ok = (body) => ({ status: 200, headers: {}, bytes: Buffer.isBuffer(body) ? body : bytes(body) });
const notFound = () => ({ status: 404, headers: {}, bytes: bytes('Not Found') });

/**
 * state: { effr: [{ date, text }], debt: [rows], h6Zip: Buffer, h6Dates: value } (read at each
 * request, so a scenario can change it between runs). scripted: { '<host>': [response, ...] },
 * given first, one per request to that host. The returned function records its requests.
 */
export function makeFixtureTransport(state, scripted = {}) {
  const queue = Object.fromEntries(Object.entries(scripted).map(([k, v]) => [k, [...v]]));
  const transport = async ({ url, headers }) => {
    const u = new URL(url);
    transport.calls.push({ url, headers: { ...headers } });
    const q = queue[u.host];
    if (q && q.length) return q.shift();
    if (u.host === 'markets.newyorkfed.org' && u.pathname === '/api/rates/unsecured/effr/search.json') {
      const start = u.searchParams.get('startDate');
      const end = u.searchParams.get('endDate');
      if (!start || !end) return { status: 400, headers: {}, bytes: bytes('Bad Request') };
      // The provider answers newest first.
      const records = state.effr.filter((r) => r.date >= start && r.date <= end).sort((a, b) => (a.date < b.date ? 1 : -1));
      return ok(`{"refRates": [\n${records.map((r) => r.text).join(',\n')}\n]}\n`);
    }
    if (u.host === 'api.fiscaldata.treasury.gov' && u.pathname.endsWith('/accounting/od/debt_to_penny')) {
      const size = Number(u.searchParams.get('page[size]') ?? 100);
      const page = Number(u.searchParams.get('page[number]') ?? 1);
      const from = /^record_date:gte:(\d{4}-\d{2}-\d{2})$/.exec(u.searchParams.get('filter') ?? '')?.[1] ?? '0000-00-00';
      // VERIFIED provider behavior: a page size over 10,000 answers 404.
      if (!Number.isInteger(size) || size < 1 || size > 10000 || !Number.isInteger(page) || page < 1) return notFound();
      const rows = state.debt.filter((r) => r.record_date >= from).sort((a, b) => (a.record_date < b.record_date ? -1 : 1));
      const pages = Math.max(1, Math.ceil(rows.length / size));
      if (page > pages) return notFound();
      const data = rows.slice((page - 1) * size, page * size);
      return ok(JSON.stringify({ data, meta: { count: data.length, 'total-count': rows.length, 'total-pages': pages } }));
    }
    if (u.host === 'www.federalreserve.gov' && u.pathname === '/releases/h6/data/FRB_h6_xml.zip') return ok(state.h6Zip);
    if (u.host === 'www.federalreserve.gov' && u.pathname === '/releases/h6/releaseDates.json') return ok(JSON.stringify(state.h6Dates));
    return notFound();
  };
  transport.calls = [];
  return transport;
}
