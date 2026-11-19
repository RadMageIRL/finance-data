// The live transport (DATA_CONVENTIONS 20.2): the only module of the pipeline that opens a network
// connection. One HTTPS GET per call, only to a host the registry names, never following a
// redirect, with a whole-request timeout and a size cap; every answer is handed to `record` with
// its provenance so the run can save it byte for byte. The request function is injectable so that
// tests never touch the network.
import { createHash } from 'node:crypto';
import { request as httpsRequest } from 'node:https';

/** Conservative limits of a Stage B request (20.2). */
export const LIVE_LIMITS = { timeoutMs: 60_000, maxBytes: 64_000_000 };

/** The only headers a request may carry (18): the identity, an optional contact, and Accept. */
const ALLOWED_HEADERS = ['User-Agent', 'From', 'Accept'];
/** Response headers kept as provenance. */
const KEPT = ['content-type', 'content-length', 'etag', 'last-modified', 'date', 'retry-after'];

/**
 * A transport for the adapters: transport({ url, headers }) answers { status, headers, bytes } or
 * { timeout: true }. A refused request (not https, an unregistered host, credentials in the URL,
 * an answer over the size cap) answers { status: 0, headers: {}, bytes, refused } without a byte
 * sent or kept beyond the cap. `record(entry)` receives every answered request.
 */
export function makeLiveTransport({ registry, request = httpsRequest, limits = LIVE_LIMITS, record = null, clock = () => new Date() }) {
  const hosts = new Set(Object.values(registry.sources).map((s) => s.host));
  let n = 0;
  const transport = ({ url, headers }) => new Promise((resolve) => {
    let u;
    try {
      u = new URL(url);
    } catch {
      resolve({ status: 0, headers: {}, bytes: Buffer.alloc(0), refused: 'not a URL' });
      return;
    }
    if (u.protocol !== 'https:' || !hosts.has(u.host) || u.username !== '' || u.password !== '') {
      resolve({ status: 0, headers: {}, bytes: Buffer.alloc(0), refused: 'not an https request to a registered host' });
      return;
    }
    const sent = Object.fromEntries(Object.entries(headers ?? {}).filter(([k]) => ALLOWED_HEADERS.includes(k)));
    const requestedAt = clock().toISOString().slice(0, 19) + 'Z';
    n += 1;
    const index = n;
    let done = false;
    const finish = (value) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolve(value);
    };
    // node:https never follows a redirect: a 3xx comes back as its status, a failure (17.4).
    const req = request(u, { method: 'GET', headers: sent }, (res) => {
      const chunks = [];
      let size = 0;
      res.on('data', (chunk) => {
        size += chunk.length;
        if (size > limits.maxBytes) {
          req.destroy();
          finish({ status: 0, headers: {}, bytes: Buffer.alloc(0), refused: 'answer over the size cap' });
          return;
        }
        chunks.push(chunk);
      });
      res.on('end', () => {
        const bytes = Buffer.concat(chunks);
        const kept = Object.fromEntries(KEPT.filter((k) => res.headers[k] !== undefined).map((k) => [k, String(res.headers[k])]));
        const out = { status: res.statusCode, headers: kept, bytes };
        if (record) {
          record({
            n: index,
            host: u.host,
            url: u.toString(),
            requested_at: requestedAt,
            status: res.statusCode,
            content_type: kept['content-type'] ?? null,
            content_length: kept['content-length'] ?? null,
            etag: kept.etag ?? null,
            last_modified: kept['last-modified'] ?? null,
            date: kept.date ?? null,
            bytes: bytes.length,
            sha256: createHash('sha256').update(bytes).digest('hex'),
            body: bytes,
          });
        }
        finish(out);
      });
      res.on('error', () => finish({ timeout: true }));
    });
    const timer = setTimeout(() => {
      req.destroy();
      finish({ timeout: true });
    }, limits.timeoutMs);
    // A connection failure is transient, like a timeout (17.4): retried within the run's bounds.
    req.on('error', () => finish({ timeout: true }));
    req.end();
  });
  return transport;
}
