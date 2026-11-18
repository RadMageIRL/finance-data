// Canonical JSON bytes and content addresses for objects (DATA_CONVENTIONS section 7):
// UTF-8, object keys sorted by code point, no whitespace outside strings, no trailing newline,
// numbers only as integers (decimal values are strings), strings escaped exactly as JSON
// requires (quote, backslash, control characters) and nothing else.
import { createHash } from 'node:crypto';

function escapeString(s) {
  let out = '"';
  for (const ch of s) {
    const c = ch.codePointAt(0);
    // A lone surrogate has no UTF-8 encoding: refuse rather than write a replacement character.
    if (c >= 0xd800 && c <= 0xdfff) throw new TypeError('canonicalJson: lone surrogate in a string');
    if (ch === '"') out += '\\"';
    else if (ch === '\\') out += '\\\\';
    else if (c === 0x08) out += '\\b';
    else if (c === 0x0c) out += '\\f';
    else if (c === 0x0a) out += '\\n';
    else if (c === 0x0d) out += '\\r';
    else if (c === 0x09) out += '\\t';
    else if (c < 0x20) out += `\\u${c.toString(16).padStart(4, '0')}`;
    else out += ch;
  }
  return `${out}"`;
}

/** Sorts keys by code point (not by UTF-16 unit order, which differs above U+FFFF). */
function byCodePoint(a, b) {
  const x = [...a].map((c) => c.codePointAt(0));
  const y = [...b].map((c) => c.codePointAt(0));
  for (let i = 0; i < Math.min(x.length, y.length); i += 1) if (x[i] !== y[i]) return x[i] - y[i];
  return x.length - y.length;
}

export function canonicalJson(value) {
  if (value === null) return 'null';
  if (value === true) return 'true';
  if (value === false) return 'false';
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new TypeError(`canonicalJson: ${value} is not a safe integer; decimals are strings`);
    // String(-0) is "0": negative zero is written as 0.
    return String(value);
  }
  if (typeof value === 'string') return escapeString(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (typeof value === 'object') {
    const keys = Object.keys(value).sort(byCodePoint);
    return `{${keys.map((k) => `${escapeString(k)}:${canonicalJson(value[k])}`).join(',')}}`;
  }
  throw new TypeError(`canonicalJson: unsupported ${typeof value}`);
}

export function sha256Hex(text) {
  return createHash('sha256').update(Buffer.from(text, 'utf8')).digest('hex');
}

/** The canonical bytes, hash and published path of an object. */
export function objectAddress(object) {
  const text = canonicalJson(object);
  const sha256 = sha256Hex(text);
  return { text, sha256, bytes: Buffer.byteLength(text, 'utf8'), path: `objects/${object.series}/${object.segment}/${sha256.slice(0, 16)}.json` };
}
