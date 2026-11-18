// The fixture fetch function (DATA_CONVENTIONS section 17.4): answers a run's requests from
// data held in memory and from scripted failures. It is the only fetch function that exists;
// nothing here, or anywhere in the pipeline, opens a network connection.

/**
 * data: { effr: { records }, debt: { rows, pageSize? }, h6: { body } }  (any may be absent)
 * scripted: { effr: [response, ...], 'debt-total': [...], 'm1-sa': [...] }: responses given
 * first, one per request to that group, before the data answers.
 * The returned function records every request in its `calls` list.
 */
export function makeFixtureFetch(data, scripted = {}) {
  const queue = Object.fromEntries(Object.entries(scripted).map(([k, v]) => [k, [...v]]));
  const fetch = async (request) => {
    fetch.calls.push({ ...request });
    const q = queue[request.group];
    if (q && q.length) return q.shift();
    if (request.group === 'effr') {
      if (!data.effr) return { status: 404, body: null };
      // The provider answers newest first (6.2).
      const refRates = data.effr.records.filter((r) => r.effectiveDate >= request.start && r.effectiveDate <= request.end).sort((a, b) => (a.effectiveDate < b.effectiveDate ? 1 : -1));
      return { status: 200, body: { refRates } };
    }
    if (request.group === 'debt-total') {
      if (!data.debt) return { status: 404, body: null };
      const size = data.debt.pageSize ?? 10000;
      const rows = data.debt.rows.filter((r) => r.record_date >= request.start).sort((a, b) => (a.record_date < b.record_date ? -1 : 1));
      const pages = Math.max(1, Math.ceil(rows.length / size));
      if (request.page > pages) return { status: 404, body: null };
      return { status: 200, body: { data: rows.slice((request.page - 1) * size, request.page * size), meta: { count: Math.min(size, rows.length), 'total-count': rows.length, 'total-pages': pages } } };
    }
    if (request.group === 'm1-sa') {
      if (!data.h6) return { status: 404, body: null };
      return { status: 200, body: data.h6.body };
    }
    return { status: 404, body: null };
  };
  fetch.calls = [];
  return fetch;
}

/** A wait function that only records the seconds it was asked to wait. */
export function makeWait() {
  const wait = async (seconds) => {
    wait.calls.push(seconds);
  };
  wait.calls = [];
  return wait;
}
