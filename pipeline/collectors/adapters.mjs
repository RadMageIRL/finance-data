// The first collector adapters (DATA_CONVENTIONS section 18, P2.3): New York Fed EFFR (which
// also carries the FOMC target), Treasury Debt to the Penny, and the Board's H.6 release.
// An adapter knows one source's requests and how to read its bytes; it never interprets a
// value. The semantic classes stay apart downstream: a market rate, a policy target, an
// administrative total and a revised aggregate are classified by different rules.
//
// Adapters reach a source only through a transport function that is passed in:
//   transport({ url, headers }) -> { status, headers, bytes } | { timeout: true }
// The only transport that exists is the fixture transport. No module here, or anywhere in the
// pipeline, opens a network connection; a live transport needs its own authorization.
import { zipRead } from '../lib/zip.mjs';
import { readSdmx } from '../lib/sdmx.mjs';

/**
 * The headers of every request (18): the source's registered User-Agent (RadMage Finance and its
 * public URL, never a browser's), a From header only when the source requires a contact, and Accept.
 */
export const requestHeaders = (source) => ({ 'User-Agent': source.request.user_agent, ...(source.request.contact ? { From: source.request.contact } : {}), Accept: '*/*' });

/** Run budgets of the fetch layer (docs/P22_DESIGN.md 4.2, hard limits). */
export const FETCH_BUDGETS = { requestsPerHost: 10, downloadBytesPerRun: 25_000_000, h6XmlBytes: 64_000_000 };

const H6_FILE = 'H6_data.xml';

function query(endpoint, parameters) {
  const pairs = Object.entries(parameters).map(([k, v]) => `${encodeURIComponent(k).replace(/%5B/g, '[').replace(/%5D/g, ']')}=${encodeURIComponent(v).replace(/%3A/g, ':').replace(/%2C/g, ',')}`);
  return pairs.length ? `${endpoint}?${pairs.join('&')}` : endpoint;
}

const fillParameters = (parameters, values) => Object.fromEntries(Object.entries(parameters).map(([k, v]) => [k, String(v).replace(/\{([a-z]+)\}/g, (_, name) => values[name])]));

function parseJson(bytes) {
  try {
    return JSON.parse(bytes.toString('utf8'));
  } catch {
    return { unreadable: 'the response is not JSON' };
  }
}

/** The three adapters, by request group. Each gives the requests of a run and reads the bytes. */
export const ADAPTERS = {
  effr: {
    source: 'nyfed-markets',
    requests: (series, r) => [{ part: 'data', url: query(series.fetch.endpoint, fillParameters(series.fetch.parameters, { start: r.start, end: r.end })) }],
    read: (parts) => parseJson(parts.data),
  },
  'debt-total': {
    source: 'fiscaldata',
    requests: (series, r) => [{ part: 'data', url: query(series.fetch.endpoint, fillParameters(series.fetch.parameters, { start: r.start, end: r.end, page: r.page })) }],
    read: (parts) => parseJson(parts.data),
  },
  'm1-sa': {
    source: 'frb-releases',
    requests: (series, r, registry) => [
      { part: 'zip', url: series.fetch.endpoint },
      { part: 'dates', url: registry.calendars[series.release.calendar].url },
    ],
    read: (parts, registry) => {
      let reader;
      try {
        const names = registry.series.filter((s) => s.fetch.format === 'sdmx-zip').map((s) => s.extract[0].series_name);
        reader = readSdmx(zipRead(parts.zip, H6_FILE, FETCH_BUDGETS.h6XmlBytes).toString('utf8'), names);
      } catch (e) {
        return { unreadable: e.message };
      }
      return { prepared: reader.prepared, series: reader.series, release_dates: h6ReleaseDates(parseJson(parts.dates)) };
    },
  },
};

/**
 * The Board's releaseDates.json to a list of dates, markers kept: [{ yearValue, Months:
 * [{ Dates: ["20261027", "20210323**"] }] }] gives ["2026-10-27", "2021-03-23**"].
 */
export function h6ReleaseDates(value) {
  if (!Array.isArray(value)) return [];
  const out = [];
  for (const year of value) {
    for (const month of year?.Months ?? []) {
      for (const d of month?.Dates ?? []) {
        const m = /^(\d{4})(\d{2})(\d{2})(\*{0,3})$/.exec(String(d).trim());
        out.push(m ? `${m[1]}-${m[2]}-${m[3]}${m[4]}` : String(d));
      }
    }
  }
  return out.sort();
}

/**
 * Fiscal Data's release calendar to the publication times of one dataset:
 * [{ datasetId, date, time, released }] gives { "2026-11-17": "21:15", ... }. The `released`
 * flag is ignored (registry: unreliable).
 */
export function fiscalCalendarTimes(value, datasetId) {
  const out = {};
  for (const e of Array.isArray(value) ? value : []) {
    if (e?.datasetId === datasetId && /^\d{4}-\d{2}-\d{2}$/.test(e.date ?? '') && /^\d{2}:\d{2}$/.test(e.time ?? '')) out[e.date] = e.time;
  }
  return out;
}

/**
 * The fetch function a run takes (section 17.4), built over a transport. It sends only the
 * requests the registry describes, to the registered host over https, at least the source's
 * minimum interval apart, within the run budgets, and returns { status, body } with the body
 * read by the adapter, or { status, retry_after } or { timeout: true } for the run to handle.
 * `fetch.log` lists every request sent (URL and status only).
 */
export function adapterFetch({ registry, transport, wait = async () => {}, budgets = FETCH_BUDGETS }) {
  const sent = new Map();
  let downloaded = 0;
  const fetch = async (r) => {
    const adapter = ADAPTERS[r.group];
    const series = registry.series.find((s) => s.id === r.group);
    if (!adapter || !series || series.source !== adapter.source) return { status: 0, body: null };
    const source = registry.sources[adapter.source];
    const parts = {};
    for (const q of adapter.requests(series, r, registry)) {
      const url = new URL(q.url);
      // The H.6 release dates live on the same registered host as the release itself.
      if (url.protocol !== 'https:' || url.host !== source.host) return { status: 0, body: null };
      const n = sent.get(url.host) ?? 0;
      if (n >= budgets.requestsPerHost) return { status: 0, body: null, budget: 'requests per host' };
      if (n > 0) await wait(source.request.min_interval_seconds);
      sent.set(url.host, n + 1);
      const res = await transport({ url: q.url, headers: requestHeaders(source) });
      fetch.log.push({ url: q.url, status: res.timeout ? 'timeout' : res.status });
      if (res.timeout) return { timeout: true };
      if (res.status !== 200) {
        const after = Number.parseInt(res.headers?.['retry-after'] ?? '', 10);
        return { status: res.status, ...(Number.isInteger(after) && after >= 0 ? { retry_after: after } : {}) };
      }
      downloaded += res.bytes.length;
      if (downloaded > budgets.downloadBytesPerRun) return { status: 0, body: null, budget: 'download bytes per run' };
      parts[q.part] = res.bytes;
    }
    return { status: 200, body: adapter.read(parts, registry) };
  };
  fetch.log = [];
  return fetch;
}
