// A reader for the Board's SDMX-ML compact data files (DATA_CONVENTIONS sections 5 and 18),
// with no dependencies. It is not a general XML parser: it scans for Series elements and their
// Obs children and reads their attributes, which is all the registered H.6 series need. The
// file is untrusted data: a document type declaration or an entity declaration is refused (no
// DTD is ever loaded and no entity other than the five predefined ones is expanded), and only
// the series asked for are kept.

const ATTRIBUTE = /([A-Za-z_][\w.-]*)\s*=\s*"([^"]*)"/g;
const ENTITIES = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&apos;': "'" };

function attributes(text) {
  const out = {};
  for (const m of text.matchAll(ATTRIBUTE)) {
    if (m[1] in out) throw new RangeError(`sdmx: duplicate attribute ${m[1]}`);
    if (/&(?!(amp|lt|gt|quot|apos);)/.test(m[2])) throw new RangeError(`sdmx: unsupported entity in attribute ${m[1]}`);
    out[m[1]] = m[2].replace(/&(amp|lt|gt|quot|apos);/g, (e) => ENTITIES[e]);
  }
  return out;
}

/**
 * Reads the series named in `wanted` (a list of SERIES_NAME values) from SDMX-ML compact text.
 * Returns { prepared, series: [{ attributes, observations: [{ OBS_STATUS, OBS_VALUE, TIME_PERIOD }] }] }
 * with every copy of each wanted series, in file order. Namespace prefixes are ignored;
 * Annotations children are skipped and not stored.
 */
export function readSdmx(text, wanted) {
  if (typeof text !== 'string') throw new TypeError('sdmx: not text');
  if (/<!DOCTYPE/i.test(text) || /<!ENTITY/i.test(text)) throw new RangeError('sdmx: a document type or entity declaration is refused');
  const want = new Set(wanted);
  const prepared = /<(?:[\w.-]+:)?Prepared>([^<]*)<\/(?:[\w.-]+:)?Prepared>/.exec(text)?.[1]?.trim() ?? '';
  const series = [];
  const open = /<((?:[\w.-]+:)?)Series\b([^>]*)>/g;
  let m;
  while ((m = open.exec(text)) !== null) {
    if (m[2].trimEnd().endsWith('/')) continue; // an empty series element holds nothing
    const close = `</${m[1]}Series>`;
    const end = text.indexOf(close, open.lastIndex);
    if (end < 0) throw new RangeError('sdmx: a Series element is not closed');
    const attrs = attributes(m[2]);
    if (want.has(attrs.SERIES_NAME)) {
      const body = text.slice(open.lastIndex, end);
      if (/<(?:[\w.-]+:)?Series\b/.test(body)) throw new RangeError('sdmx: nested Series elements');
      const observations = [];
      for (const o of body.matchAll(/<(?:[\w.-]+:)?Obs\b([^>]*?)\/?>/g)) observations.push(attributes(o[1]));
      series.push({ attributes: attrs, observations });
    }
    open.lastIndex = end + close.length;
  }
  return { prepared, series };
}
