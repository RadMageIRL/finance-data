// Operational alerts and the issue plan (DATA_CONVENTIONS sections 15 and 17.8, decisions P3
// and P4). Alerts become public GitHub issues later, so their text is sanitized here and an
// alert that fails the check never leaves this module. The plan only opens, updates or closes
// issues: nothing here commits, pushes, re-enables a workflow or keeps a repository active.

import { etDate } from './calendar.mjs';

export const PLAN_ACTIONS = ['open', 'update', 'close'];
const MAX_TEXT = 2000;

const REFUSALS = [
  ['a query string', /[?&][A-Za-z0-9_.[\]-]+=/],
  ['a URL with a path', /https?:\/\/[^\s/]+\/\S/i],
  ['an email address', /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/],
  ['an IPv4 address', /\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/],
  ['a header name', /\b(authorization|cookie|set-cookie|x-api-key|user-agent)\b/i],
  ['a bearer credential', /Bearer /],
  ['a token', /\b(gh[pousr]_|github_pat_)/],
];
const LONG_RUN = /[A-Za-z0-9+/=_-]{32,}/g;
const HASH = /sha256:[0-9a-f]{64}/g;

/** Why a text may not be published, or null when it may (17.8). */
export function textRefusal(text) {
  if (typeof text !== 'string' || text.length === 0) return 'empty text';
  // Characters are Unicode code points (22.3 item 1, v0.8).
  if ([...text].length > MAX_TEXT) return `longer than ${MAX_TEXT} characters`;
  for (const [what, pattern] of REFUSALS) if (pattern.test(text)) return what;
  // A labeled content hash is allowed; any other long run of key-like characters is not.
  const rest = text.replace(HASH, 'sha256');
  for (const run of rest.match(LONG_RUN) ?? []) if (/[0-9]/.test(run) && /[A-Za-z]/.test(run)) return 'a long run of key-like characters';
  return null;
}

const KEY = /^[a-z][a-z0-9-]*(:[a-z0-9][a-z0-9-]*)?$/;

/** Sanitizes a list of alerts; a refused one becomes `alert-text-refused` naming only its key. */
export function sanitizeAlerts(alerts) {
  const out = new Map();
  const refused = [];
  for (const a of alerts) {
    const keyOk = typeof a.key === 'string' && KEY.test(a.key);
    const why = !keyOk ? 'a malformed key' : !['critical', 'warning'].includes(a.severity) ? 'an unknown severity' : (textRefusal(a.title) ?? textRefusal(a.body));
    if (why) refused.push(keyOk ? a.key : 'unknown');
    else if (!out.has(a.key)) out.set(a.key, { key: a.key, severity: a.severity, title: a.title, body: a.body });
  }
  if (refused.length) {
    out.set('alert-text-refused', {
      key: 'alert-text-refused',
      severity: 'critical',
      title: 'An alert was withheld because its text failed the publication check',
      body: `Withheld alert keys: ${[...new Set(refused)].sort().join(', ')}. Read the run record for details.`,
    });
  }
  return [...out.values()].sort((a, b) => (a.key < b.key ? -1 : 1));
}

export const emptyLedger = () => ({ schema: 'rmf.econ.alerts/1', open: [] });

/**
 * Compares the alerts current after a run with the ledger. Returns { ledger, plan }: the new
 * ledger and the issue actions. An unchanged alert yields no action (no duplicate issues and no
 * repeated comments); a key that is no longer current is closed.
 */
export function planIssues(ledger, alerts, now) {
  const current = sanitizeAlerts(alerts);
  const before = new Map((ledger?.open ?? []).map((a) => [a.key, a]));
  const plan = [];
  const open = [];
  for (const a of current) {
    const old = before.get(a.key);
    if (!old) {
      plan.push({ action: 'open', key: a.key, severity: a.severity, title: a.title, body: a.body });
      open.push({ ...a, first_seen: now, last_seen: now, runs: 1 });
    } else {
      if (old.severity !== a.severity || old.title !== a.title || old.body !== a.body) plan.push({ action: 'update', key: a.key, severity: a.severity, title: a.title, body: a.body });
      open.push({ ...a, first_seen: old.first_seen, last_seen: now, runs: old.runs + 1 });
    }
    before.delete(a.key);
  }
  for (const key of [...before.keys()].sort()) plan.push({ action: 'close', key });
  return { ledger: { schema: 'rmf.econ.alerts/1', open }, plan };
}

/** Schedule-health findings (14.3) as alerts under their finding keys. */
export function healthAlerts(findings) {
  return findings.map((f) => ({ key: f.key, severity: f.severity, title: `Schedule health: ${f.key}`, body: f.message }));
}

const dayDiff = (from, to) => Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);

/**
 * Route notice alerts (4.3, 17.8), evaluated on the ET date `today` of a run: a retirement of the
 * registered route warns from 180 days before its date and is critical from 60 days before, with
 * no end while the entry stands; a route check warns from 7 days before its date to 30 days after.
 * The earliest date that applies counts. The text names only the source id, dates and day counts.
 */
export function routeNoticeAlertsOn(registry, today) {
  const out = [];
  for (const id of Object.keys(registry.sources).sort()) {
    const notices = registry.sources[id].route_notices ?? [];
    const retiring = notices.filter((n) => n.affects_registered_route).map((n) => n.date).sort();
    if (retiring.length) {
      const date = retiring[0];
      const left = dayDiff(today, date);
      const severity = left <= 60 ? 'critical' : left <= 180 ? 'warning' : null;
      const when = left >= 0 ? `ends on ${date}, ${left} day(s) from ${today}` : `ended on ${date}, ${-left} day(s) before ${today}`;
      if (severity) out.push({ key: `source-retirement:${id}`, severity, title: `Source route retirement: ${id}`, body: `A route that the series of source ${id} use ${when}. The source migration milestone (conventions 19) must be done before the route ends; the registry entry stands until a conventions change switches the route.` });
    }
    const checks = notices.filter((n) => !n.affects_registered_route && dayDiff(today, n.date) <= 7 && dayDiff(today, n.date) >= -30).map((n) => n.date).sort();
    if (checks.length) {
      const date = checks[0];
      const left = dayDiff(today, date);
      const when = left >= 0 ? `${left} day(s) after ${today}` : `${-left} day(s) before ${today}`;
      out.push({ key: `source-route-check:${id}`, severity: 'warning', title: `Route check due: ${id}`, body: `The provider of source ${id} ends a route on ${date} (${when}) that the registered route does not depend on. On the first due run on or after ${date}, a person confirms that the registered route still answers in its registered format (registry route_notices).` });
    }
  }
  return out;
}

/** The route notice alerts of a run at the stored time `now` (its ET date counts). */
export const routeNoticeAlerts = (registry, now) => routeNoticeAlertsOn(registry, etDate(now));
