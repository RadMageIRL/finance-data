// The collector run and the manual operations (DATA_CONVENTIONS section 17): due, fetch with
// failure handling, normalize, validate, classify, build, gate, atomic publish, prune, alerts.
// Everything from outside is an argument (the time, the fetch function, the holiday table, the
// health facts), so the same inputs always give the same bytes. No network code lives here.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { canonicalJson, sha256Hex } from './canonical.mjs';
import { addDays, etDate, makeCalendar, snapshotId, weekday } from './calendar.mjs';
import { GAP_PROBLEM, changePoints, normalizeDebt, normalizeEffr, normalizeH6, undocumentedGaps, validateSeries } from './normalize.mjs';
import { classify, diffObservations, isSame, keyOf, revisionRecords } from './classify.mjs';
import { buildManifest, buildObjects, csvSegments, deadlines, fileRef, holdCandidate, periodDeadline, registryHash, revisionCsv, revisionLog, snapshotNotices } from './tree.mjs';
import { registryCopyPath, ruleFiles } from './rules.mjs';
import { gateProblems } from './gate.mjs';
import { addPin, budgetAlerts, emptyPins, liveWindow, prunable, removePin } from './retention.mjs';
import { emptyLedger, healthAlerts, planIssues, routeNoticeAlerts } from './alerts.mjs';
import { scheduleHealth } from './schedule-health.mjs';
import { activationProblems } from './activation.mjs';
import * as store from './store.mjs';

const bytes = (text) => Buffer.byteLength(text, 'utf8');
/** The pipeline directory this module belongs to (for the activation guard's facts). */
const PIPELINE_DIR = fileURLToPath(new URL('..', import.meta.url));
const NYP = (at, outcome = 'not-due', error = null) => ({ objects: [], last_period: null, observation_count: 0, status: 'not-yet-published', retrieved_at: null, checked_at: null, attempt: { at, outcome, error }, source_marker: null });
const category = (status) => (status === 'not-yet-published' ? 'unpublished' : status === 'held' ? 'held' : 'published');
/** The schedule-health findings the collector's self-check raises (17.8 layer 2, v0.8): the run keys. */
export const SELF_CHECK_KEYS = new Set(['workflow-disabled', 'inactivity', 'scheduled-run-gap', 'consecutive-failures']);
const emptyQueue = () => ({ schema: 'rmf.econ.review-queue/4', open: [], frozen: [], decisions: [], refusals: [] });
const emptyCollector = () => ({ schema: 'rmf.econ.collector/1', sources: {}, invalid_series: [], source_gaps: {}, gate_failed: false, archive_bytes_by_month: {}, hold_meta: {}, full_fetches: {} });
/** At most this many undocumented gaps of a series are listed (11.6); the alert gives the count. */
const MAX_GAPS = 50;
/** A review's permission must have been read at most this long before it (11.5). */
const PERMISSION_MAX_AGE_SECONDS = 3600;
const AUTOMATION = /(\[bot\]$|^github-actions$)/i;

/** The request groups of a registry (11.3), named by their first series in registry order. */
export function requestGroups(registry) {
  const groups = [];
  const seen = new Set();
  for (const s of registry.series) {
    if (seen.has(s.id)) continue;
    const members = [s, ...registry.series.filter((x) => (s.fetch.shared_with ?? []).includes(x.id))];
    members.forEach((m) => seen.add(m.id));
    groups.push({ id: s.id, source: s.source, format: s.fetch.format, members });
  }
  return groups;
}

/** The observations of a held or locked candidate in the archive, verified by its hash, or null. */
function candidateObservations(p, seriesId, sha, stagedHolds = null) {
  const local = `holds/${seriesId}/${sha.slice(0, 16)}.json`;
  const text = stagedHolds?.get(local) ?? store.readText(join(p.root, 'archive', local));
  return text !== null && sha256Hex(text) === sha ? JSON.parse(text) : null;
}

/**
 * The locked changes of a lock (11.5): the (period, field) pairs in which the locked candidate
 * differs from the published observations. Every difference counts, new periods included, for both
 * origins (v0.6): rejected additions stay locked while the source keeps them.
 */
export function lockedChanges(series, published, locked) {
  const key = keyOf(series);
  const diff = diffObservations(published, locked, key);
  const out = [];
  for (const o of diff.removed) out.push({ period: o[key], field: 'period' });
  for (const p of diff.added) out.push({ period: p, field: 'period' });
  for (const x of diff.changed) for (const f of x.fields) out.push({ period: x.period, field: f.field });
  return out.sort((a, b) => (a.period < b.period ? -1 : a.period > b.period ? 1 : a.field < b.field ? -1 : a.field > b.field ? 1 : 0));
}

/** Whether a candidate carries any locked change: the same member as the locked candidate (11.5). */
export function carriesLock(series, lockedObs, candidate, changes) {
  const key = keyOf(series);
  const L = new Map(lockedObs.map((o) => [o[key], o]));
  const C = new Map(candidate.map((o) => [o[key], o]));
  const whole = (o) => {
    const { released: _released, ...rest } = o;
    return canonicalJson(rest);
  };
  const member = (o, field) => canonicalJson((field.startsWith('extra.') ? (o.extra ?? {})[field.slice(6)] : o[field]) ?? null);
  return changes.some(({ period, field }) => {
    const l = L.get(period);
    const c = C.get(period);
    if (field === 'period') return l ? c !== undefined && whole(c) === whole(l) : c === undefined;
    return l !== undefined && c !== undefined && member(c, field) === member(l, field);
  });
}

/** The archive path of a rollback's record (17.5, v0.6). */
export const rollbackRecordPath = (at) => `rollbacks/${snapshotId(at)}.json`;
/** A lock's identity: its series, origin and candidate (11.5, v0.6). */
const lockKey = (l) => `${l.series}|${l.origin ?? 'rejected'}|${l.candidate_sha256}`;

/**
 * The locks in force (11.5), several per series possible: the published state is the record, the
 * queue keeps the details. The named snapshot's `frozen`, plus the locks of the rollback record
 * when the live manifest is a rollback manifest; a queue entry is used when it matches, and the
 * details are rebuilt from the archive when it is missing (a run that died between its manifest and
 * its state files). Returns a list of locks, each with its observations.
 */
function locksInForce(ctx) {
  const snap = ctx.published.snapshot;
  const man = ctx.published.manifest;
  const list = (snap?.frozen ?? []).map((f) => ({ series: f.series, candidate_sha256: f.candidate_sha256, origin: f.origin ?? 'rejected', frozen_at: f.frozen_at, reason: f.reason, locked_changes: null }));
  if (man?.rollback) {
    const text = store.readText(join(ctx.p.root, 'archive', rollbackRecordPath(man.rollback.at)));
    if (text === null) throw new Error(`the rollback record of ${man.rollback.at} is missing from the archive`);
    for (const l of JSON.parse(text).locks) list.push({ series: l.series, candidate_sha256: l.candidate_sha256, origin: l.origin, frozen_at: man.rollback.at, reason: man.rollback.reason, locked_changes: l.locked_changes });
  }
  const out = [];
  const seen = new Set();
  for (const l of list) {
    if (seen.has(lockKey(l))) continue;
    seen.add(lockKey(l));
    const s = ctx.registry.series.find((x) => x.id === l.series);
    const observations = candidateObservations(ctx.p, l.series, l.candidate_sha256);
    if (!s || !observations) throw new Error(`the locked candidate of ${l.series} is missing from the archive or does not match its hash`);
    const known = ctx.queue.frozen.find((e) => lockKey(e) === lockKey(l));
    const changes = known?.locked_changes ?? l.locked_changes ?? lockedChanges(s, ctx.published.observations[l.series], observations);
    const entry = known
      ? { ...known, origin: l.origin }
      : { series: l.series, candidate_sha256: l.candidate_sha256, origin: l.origin, frozen_at: l.frozen_at, run: 'rebuilt-from-published-state', reviewer: null, reason: l.reason, affected_periods: [...new Set(changes.map((x) => x.period))].sort(), locked_changes: changes };
    out.push({ ...entry, observations });
  }
  return out;
}

/** The queue's `frozen` entries for a list of locks: details without the observations. */
const queueLocks = (locks) => locks.map(({ observations: _o, ...e }) => e).sort((a, b) => (lockKey(a) < lockKey(b) ? -1 : lockKey(a) > lockKey(b) ? 1 : 0));
/** A snapshot's `frozen` entry for a lock (8). */
const snapshotLock = (l) => ({ series: l.series, candidate_sha256: l.candidate_sha256, origin: l.origin, frozen_at: l.frozen_at, reason: l.reason });

function open(o) {
  // v0.7 (21.6): mode "operation" is a review, rollback or restore on the private store; it
  // makes no request, so it needs no collection activation, and a collection never uses it.
  if (o.mode !== 'fixture' && o.mode !== 'live' && o.mode !== 'operation') throw new Error('run refused: mode must be "fixture", "live" or "operation"');
  if (o.mode === 'live') {
    // A nonpublishing live collection (Stage B, 20) runs only with every collection requirement
    // given; nothing in the pipeline publishes.
    const blockers = activationProblems({ ...(o.activationFacts ?? {}), pipelineDir: PIPELINE_DIR }, 'collect');
    if (blockers.length) throw new Error(`run refused: live collection is not activated (${blockers.join('; ')})`);
  }
  // The run id names files: letters, digits, dots, hyphens and underscores only.
  if (typeof o.run?.id !== 'string' || !/^[A-Za-z0-9._-]{1,80}$/.test(o.run.id)) throw new Error('run refused: the run id must be 1 to 80 letters, digits, dots, hyphens or underscores');
  const p = store.paths(o.root);
  const recovered = store.clearStaging(p);
  const calendar = makeCalendar(o.holidays);
  const published = store.loadPublished(p, o.registry);
  const ctx = {
    o, p, recovered, calendar, published,
    registry: o.registry, schemas: o.schemas, table: o.sourceTable, now: o.now, run: o.run,
    runEt: etDate(o.now),
    read: store.reader(p),
    index: store.archiveIndex(p),
    collector: { ...emptyCollector(), ...store.readState(p, 'collector.json', emptyCollector()) },
    queue: readQueue(p),
    pins: store.readState(p, 'pins.json', emptyPins()),
    ledger: store.readState(p, 'alerts.json', emptyLedger()),
  };
  // The locks in force come from the published state, whatever the queue says (11.5).
  ctx.locks = locksInForce(ctx);
  ctx.queue = { ...ctx.queue, frozen: queueLocks(ctx.locks) };
  return ctx;
}

/** The review queue as stored, in the current shape (17.5). */
function readQueue(p) {
  return { ...emptyQueue(), ...store.readState(p, 'review-queue.json', emptyQueue()), schema: 'rmf.econ.review-queue/4' };
}

const stateOf = (ctx, id) => ctx.published.snapshot?.series[id] ?? NYP(ctx.now);

/** Whether a group is due, and its window start (null for a full request) (17.3). */
export function dueWindow(ctx, group) {
  const states = group.members.map((s) => [s, stateOf(ctx, s.id)]);
  const unpublished = states.some(([, st]) => st.status === 'not-yet-published');
  // The weekly full fetch (v0.7): on a Sunday (ET), once per group, until one succeeds that day.
  const last = ctx.collector.full_fetches?.[group.id];
  const sunday = weekday(ctx.runEt) === 0 && !(typeof last === 'string' && etDate(last) === ctx.runEt);
  let due = unpublished || sunday || states.some(([, st]) => st.status === 'held');
  if (!due) {
    for (const [s, st] of states) {
      const d = deadlines(s, st, ctx.registry, ctx.calendar);
      if (d && d.expected <= ctx.now) due = true;
      if (s.class === 'market_observation' && ctx.runEt === ctx.calendar.publicationDay(st.last_period)) due = true;
    }
  }
  const full = unpublished || sunday || group.format === 'sdmx-zip';
  return { due, start: full ? null : addDays(ctx.runEt, -59) };
}

async function fetchWithRetries(ctx, group, request) {
  const source = ctx.registry.sources[group.source];
  if (ctx.blocked.has(group.source)) return { failed: 'blocked earlier in this run' };
  for (let attempt = 0; ; attempt += 1) {
    const r = await ctx.o.fetch({ group: group.id, source: group.source, ...request });
    ctx.requests += 1;
    const transient = r.timeout === true || (r.status >= 500 && r.status <= 599);
    if (transient) {
      if (attempt < source.request.max_retries) {
        await ctx.o.wait(Math.max(2 ** (attempt + 1), Number.isInteger(r.retry_after) ? r.retry_after : 0));
        continue;
      }
      return { failed: r.timeout === true ? 'timeout' : `status ${r.status}` };
    }
    if (r.status === 403 || r.status === 429) {
      ctx.blocked.add(group.source);
      return { failed: `status ${r.status}`, blockedNow: true };
    }
    if (r.status !== 200) return { failed: `status ${Number.isInteger(r.status) ? r.status : 'unknown'}` };
    return { body: r.body };
  }
}

/** The published observations before the window plus the response's (section 5). */
const assemble = (published, fresh, start, key = 'period') => (start === null ? fresh : [...published.filter((o) => o[key] < start), ...fresh]);

function assembleTarget(published, targets, start) {
  const points = changePoints(targets);
  if (start === null) return points.map((pt, i) => (i === 0 ? { ...pt, starts_before_data: true } : pt));
  const prior = published.filter((o) => o.effective < start);
  // A window that covers the whole published history starts the series, like a full request.
  if (prior.length === 0) return points.map((pt, i) => (i === 0 ? { ...pt, starts_before_data: true } : pt));
  const entering = prior[prior.length - 1];
  const same = (a, b) => a && b && a.kind === b.kind && a.value === b.value && a.lower === b.lower && a.upper === b.upper;
  return [...prior, ...(same(entering, points[0]) ? points.slice(1) : points)];
}

/** Gives each candidate observation its `released` (6.3): published ones keep theirs. */
function assignReleased(ctx, series, published, candidate, releaseDates = null) {
  const key = keyOf(series);
  const before = new Map(published.map((o) => [o[key], o]));
  const cal = ctx.registry.calendars[series.release.calendar];
  const none = { date: null, basis: 'not-recorded' };
  return candidate.map((o) => {
    const { released: _dropped, ...rest } = o;
    const old = before.get(o[key]);
    let released = none;
    if (old) released = old.released;
    else if (series.class === 'market_observation') released = o.period >= cal.rule_valid_from ? { date: ctx.calendar.publicationDay(o.period), basis: 'rule' } : none;
    else if (series.class === 'policy_target') released = !o.starts_before_data && o.effective >= cal.rule_valid_from ? { date: ctx.calendar.publicationDay(o.effective), basis: 'rule' } : none;
    else if (series.class === 'revised_aggregate') {
      const [y, m] = o.period.split('-').map(Number);
      const monthEnd = addDays(m === 12 ? `${y + 1}-01-01` : `${y}-${String(m + 1).padStart(2, '0')}-01`, -1);
      const first = (releaseDates ?? []).find((d) => d > monthEnd);
      released = first && first >= cal.calendar_valid_from ? { date: first, basis: 'calendar' } : none;
    } else released = published.length ? { date: ctx.runEt, basis: 'first-seen' } : none;
    return { ...rest, released };
  });
}

async function collectGroup(ctx, group, start) {
  const out = {};
  const all = (outcome, error) => {
    for (const s of group.members) out[s.id] = { outcome, error };
    return out;
  };
  const pub = (id) => ctx.published.observations[id];
  // A held series' windowed candidate is assembled over its held candidate (5); a locked series is
  // assembled like any other (v0.6), its locks judged by the window rule.
  const baseOf = (id) => ctx.heldObservations[id] ?? pub(id);
  const judge = (s, candidate, extra = {}) => {
    const problems = validateSeries(s, candidate, ctx.runEt, ctx.calendar);
    if (problems.length) {
      // Undocumented gaps are kept apart from the other checks (11.6).
      const gaps = undocumentedGaps(s, candidate, ctx.calendar);
      const other = problems.filter((p) => !GAP_PROBLEM.test(p));
      return { outcome: 'invalid', error: (other[0] ?? problems[0]), seriesInvalid: true, gaps, otherProblems: other.length > 0 || gaps.length === 0 };
    }
    const cls = classify(s, pub(s.id), candidate, { runEtDate: ctx.runEt, calendar: ctx.calendar, ...extra });
    return { ...cls, candidate, error: null, gaps: [] };
  };
  const first = group.members[0];
  const request = { start: start ?? first.earliest, end: ctx.runEt, page: 1, full: start === null };

  if (group.id === 'effr') {
    const f = await fetchWithRetries(ctx, group, request);
    if (f.failed) return all('failed', f.failed);
    const n = normalizeEffr(f.body, ctx.registry, ctx.table, { start });
    if (n.problems.length) return all('invalid', n.problems[0]);
    const [effr, target] = group.members;
    out.effr = judge(effr, assignReleased(ctx, effr, pub('effr'), assemble(baseOf('effr'), n.series.effr, start)));
    if (out.effr.outcome === 'invalid') out[target.id] = { outcome: 'invalid', error: 'derived from an invalid series', seriesInvalid: true, gaps: [], otherProblems: true };
    else out[target.id] = judge(target, assignReleased(ctx, target, pub(target.id), assembleTarget(baseOf(target.id), n.targets, start)), { source: out.effr });
    return out;
  }

  if (group.format === 'sdmx-zip') {
    const f = await fetchWithRetries(ctx, group, request);
    if (f.failed) return all('failed', f.failed);
    const n = normalizeH6(f.body, ctx.registry, ctx.table);
    if (n.problems.length) return all('invalid', n.problems[0]);
    for (const s of group.members) {
      if (n.seriesProblems[s.id]) {
        out[s.id] = { outcome: 'invalid', error: n.seriesProblems[s.id][0], seriesInvalid: true, gaps: [], otherProblems: true };
        continue;
      }
      const old = stateOf(ctx, s.id).source_marker;
      out[s.id] = judge(s, assignReleased(ctx, s, pub(s.id), n.series[s.id], n.releaseDates), { marker: n.marker, publishedMarker: old });
      // The marker binds the release to the data actually seen (2.4).
      const changed = out[s.id].outcome === 'appended' || out[s.id].outcome === 'revised-expected' || out[s.id].outcome === 'revised-unexpected';
      out[s.id].marker = { latest_release_date: n.marker.latest_release_date, data_release_date: changed || !old ? n.marker.latest_release_date : old.data_release_date, prepared: n.marker.prepared };
    }
    return out;
  }

  // Fiscal Data: explicit pages; a 404 on any page is a failure (5).
  const pages = [];
  for (let page = 1; page <= 10; page += 1) {
    const f = await fetchWithRetries(ctx, group, { ...request, page });
    if (f.failed) return all('failed', f.failed);
    pages.push(f.body);
    const total = f.body?.meta?.['total-count'];
    const got = pages.reduce((n, b) => n + (Array.isArray(b?.data) ? b.data.length : 0), 0);
    if (!Number.isInteger(total) || got >= total || !Array.isArray(f.body?.data) || f.body.data.length === 0) break;
  }
  const n = normalizeDebt(pages, ctx.registry, ctx.table, { start });
  if (n.problems.length) return all('invalid', n.problems[0]);
  for (const s of group.members) {
    out[s.id] = judge(s, assignReleased(ctx, s, pub(s.id), assemble(baseOf(s.id), n.series[s.id], start)));
    out[s.id].marker = n.marker;
  }
  return out;
}

const errorText = (text) => String(text).replace(/\s+/g, ' ').slice(0, 200);

/** The alerts current after a run, before sanitizing (17.8). */
function currentAlerts(ctx, { snapshot, frozen = null, runAlerts, measured, records }) {
  const alerts = [...runAlerts];
  const c = ctx.collector;
  for (const h of snapshot?.holds ?? []) {
    const meta = ctx.queue.open.find((q) => q.series === h.series);
    const n = meta?.changes ?? { changed: 0, removed: 0, added: 0 };
    alerts.push({ key: `hold:${h.series}`, severity: 'critical', title: `Held for review: ${h.series}`, body: `Series ${h.series} is held: ${h.reason}. Candidate sha256:${h.candidate.sha256}, ${n.changed} changed, ${n.removed} removed and ${n.added} added period(s). The published data is unchanged until a person approves or rejects the candidate.` });
  }
  // The locks after this run: given by a run that changes them, else the published state (11.5).
  const lockList = frozen ?? ctx.locks;
  for (const id of [...new Set(lockList.map((f) => f.series))].sort()) {
    const mine = lockList.filter((f) => f.series === id);
    const origins = [...new Set(mine.map((f) => f.origin ?? 'rejected'))].sort();
    const since = mine.map((f) => f.frozen_at).sort()[0];
    const hashes = mine.map((f) => `sha256:${f.candidate_sha256}`).join(', ');
    alerts.push({ key: `frozen:${id}`, severity: 'warning', title: `Locked series: ${id}`, body: `Series ${id} is locked (origin ${origins.join(' and ')}) since ${since}, candidate ${hashes}. Nothing of this series is published until each lock lifts: a rejected one when the source no longer carries the rejected observations, a rolled-back one only when a person with write access clears it; other series continue.` });
  }
  for (const [id, s] of Object.entries(c.sources).sort(([a], [b]) => (a < b ? -1 : 1))) {
    if (s.blocked) alerts.push({ key: `blocked:${id}`, severity: 'critical', title: `Requests refused by ${id}`, body: `Source ${id} answered ${s.blocked}. No further request was sent to it in that run. A person must check the provider's terms and limits before anything else changes.` });
    if (s.invalid) alerts.push({ key: `invalid:${id}`, severity: 'critical', title: `Invalid response from ${id}`, body: `The response of source ${id} failed its format checks; every series it feeds is carried forward. A new format needs a conventions change and a review.` });
    if (s.consecutive_failures >= 3) alerts.push({ key: `fetch-failures:${id}`, severity: 'warning', title: `Fetch failures for ${id}`, body: `Source ${id} failed in ${s.consecutive_failures} consecutive runs (last: ${s.last_failure}). Its series are carried forward.` });
  }
  for (const id of c.invalid_series) alerts.push({ key: `invalid-series:${id}`, severity: 'critical', title: `Invalid data for ${id}`, body: `The candidate for series ${id} failed a validity check (range, continuity, order, decimals or dates) and is carried forward.` });
  for (const [id, g] of Object.entries(c.source_gaps ?? {}).sort(([a], [b]) => (a < b ? -1 : 1))) {
    alerts.push({ key: `source-gap:${id}`, severity: 'critical', title: `Undocumented gap in ${id}`, body: `The source has no record for ${g.count} period(s) inside the history of series ${id} that are not documented gaps (first: ${g.periods[0]}). Nothing is filled in: the series is carried forward until the source fills the period(s) or a person checks the source and documents them in the registry's known_gaps.` });
  }
  alerts.push(...routeNoticeAlerts(ctx.registry, ctx.now));
  if (c.gate_failed) alerts.push({ key: 'gate-failed', severity: 'critical', title: 'The publish gate failed', body: 'The last candidate failed the publish gate. Nothing was written to the manifest, the archive or the live tree; the live data stays on the last good snapshot.' });
  let streak = 0;
  for (const r of records) {
    if (r.outcome === 'failed' || r.outcome === 'gate-failed') streak += 1;
    else break;
  }
  if (streak >= 3) alerts.push({ key: 'failed-runs', severity: 'critical', title: 'Consecutive failed runs', body: `The newest ${streak} runs ended failed or gate-failed.` });
  if (snapshot) {
    for (const s of ctx.registry.series) {
      const st = snapshot.series[s.id];
      if (st.status === 'not-yet-published') continue;
      const ref = s.staleness.follows !== undefined ? ctx.registry.series.find((x) => x.id === s.staleness.follows) : s;
      const refState = snapshot.series[ref.id];
      if (refState.status === 'not-yet-published') continue;
      const d = deadlines(ref, refState, ctx.registry, ctx.calendar);
      if (d && ctx.now >= d.staleAt) alerts.push({ key: `stale:${s.id}`, severity: 'warning', title: `Stale series: ${s.id}`, body: `Series ${s.id} has no new period after ${st.last_period}; the next was expected by ${d.deadline}.` });
    }
  }
  if (measured) alerts.push(...budgetAlerts(measured, ctx.pins.pins.length));
  else if (ctx.pins.pins.length) alerts.push(...budgetAlerts({ publishedBytes: 0, archiveMonthBytes: 0, largestObject: 0, largestFile: 0, manifestBytes: 0 }, ctx.pins.pins.length));
  if (ctx.recovered) alerts.push({ key: 'recovered-staging', severity: 'warning', title: 'A leftover staging folder was removed', body: `${ctx.recovered} staging folder(s) of a run that did not finish were deleted before this run. The live tree was not affected.` });
  // v0.8 (17.8 layer 2, I35): the self-check gives only the run keys; the manifest findings are the
  // watcher's (21.9), and series-stale and series-held are not delivered (stale: and hold: carry them).
  if (ctx.o.healthFacts) alerts.push(...healthAlerts(scheduleHealth({ ...ctx.o.healthFacts, now: ctx.now, manifest: ctx.o.healthFacts.manifest ?? null }).filter((f) => SELF_CHECK_KEYS.has(f.key))));
  // Alerts the caller found (v0.7, 21.3 and 21.4: self-check-unavailable, budget:state-store).
  for (const a of ctx.o.extraAlerts ?? []) alerts.push(a);
  return alerts;
}

/** Writes the run record, the ledgers and the state files, and clears staging. */
function persist(ctx, record, alerts) {
  const { ledger, plan } = planIssues(ctx.ledger, alerts, ctx.now);
  record.alerts = ledger.open.map((a) => a.key);
  store.writeState(ctx.p, 'alerts.json', ledger);
  store.writeState(ctx.p, 'collector.json', ctx.collector);
  store.writeState(ctx.p, 'review-queue.json', ctx.queue);
  store.writeState(ctx.p, 'pins.json', ctx.pins);
  store.writeAtomic(join(ctx.p.records, `${record.id}.json`), canonicalJson(record));
  store.clearStaging(ctx.p);
  return { record, plan, alerts: ledger.open };
}

const newRecord = (ctx, outcome, snapshot, series, absences = []) => ({ id: ctx.run.id, trigger: ctx.run.trigger, started_at: ctx.now, ended_at: ctx.now, outcome, snapshot, series, alerts: [], pruned: [], absences });

/**
 * Gate, publish and prune a candidate (17.2 steps 5 and 6). c: { staged, stagedHolds, snapshot,
 * parts, previousSnapshot, rollback, outcomes, runAlerts }.
 */
function publishCandidate(ctx, c) {
  const { p } = ctx;
  const snapPath = `snapshots/${c.snapshot.id}.json`;
  const snapText = c.staged.get(snapPath) ?? ctx.read(snapPath);
  const snapshots = { ...ctx.index.snapshots, [c.snapshot.id]: c.snapshot };

  // v0.8 (10, D17): a CSV for every revision log version the manifest names. Content-addressed,
  // so a CSV already in the archive is not staged again.
  for (const s of ctx.registry.series) {
    const part = c.parts[s.id];
    part.revisionCsvs = part.revisions.map((r) => {
      const logText = c.staged.get(r.path) ?? ctx.read(r.path);
      if (logText === null) throw new Error(`run refused: the revision log ${r.path} is missing`);
      const csv = revisionCsv(s, ctx.registry.sources[s.source], logText);
      if (ctx.read(csv.path) === null) c.staged.set(csv.path, csv.text);
      return { path: csv.path, sha256: csv.sha256 };
    });
  }
  // v0.8 (22.9, D8): the rule files, for the registry versions the window's snapshots name. The
  // window's snapshots do not depend on the manifest's series, so they are known before it.
  const provisional = liveWindow({ manifest: { snapshot: { id: c.snapshot.id }, previous_snapshot: c.previousSnapshot, generated_at: ctx.now, series: {} }, snapshots, manifests: [], pins: ctx.pins });
  const rules = ruleFiles({ registry: ctx.registry, holidays: ctx.o.holidays, generatedAt: ctx.now, windowRegistryHashes: Object.keys(provisional.kept).map((id) => snapshots[id].run.registry_sha256), archivedRegistry: (h) => store.readText(join(p.files, registryCopyPath(h))) });
  for (const [path, text] of rules.files) if (ctx.read(path) === null) c.staged.set(path, text);
  c.staged.set('NOTICE.txt', rules.notice);

  const built = buildManifest({ registry: ctx.registry, snapshot: c.snapshot, snapshotRef: fileRef(snapPath, snapText), parts: c.parts, now: ctx.now, previousSnapshot: c.previousSnapshot, rollback: c.rollback, locks: c.lockList ?? null, pinned: ctx.pins.pins.map((x) => x.snapshot), calendar: ctx.calendar, rules: rules.rules });
  c.staged.set('manifest.json', built.text);

  // The window, the prune list and the budgets, on the state as it will be.
  const window = liveWindow({ manifest: built.manifest, snapshots, manifests: ctx.index.manifests, pins: ctx.pins });
  const liveNow = store.listFiles(p.live);
  const pruned = prunable(liveNow, window);
  const sizes = new Map(liveNow.filter((f) => !pruned.includes(f)).map((f) => [f, store.fileBytes(join(p.live, f))]));
  for (const path of window.keep) if (!sizes.has(path) && !c.staged.has(path)) {
    const text = ctx.read(path);
    if (text !== null) sizes.set(path, bytes(text));
  }
  for (const [path, text] of c.staged) sizes.set(path, bytes(text));
  const month = ctx.runEt.slice(0, 7);
  let added = bytes(built.text);
  for (const [path, text] of c.staged) if (path !== 'manifest.json' && path !== 'NOTICE.txt' && !path.startsWith('status/') && !existsSync(join(p.files, path))) added += bytes(text);
  for (const [path, text] of c.stagedHolds) if (!existsSync(join(p.root, 'archive', path))) added += bytes(text);
  const objectSizes = [...sizes].filter(([f]) => f.startsWith('objects/')).map(([, n]) => n);
  const measure = () => ({
    publishedBytes: [...sizes.values()].reduce((a, b) => a + b, 0),
    archiveMonthBytes: (ctx.collector.archive_bytes_by_month[month] ?? 0) + added,
    largestObject: Math.max(0, ...objectSizes),
    largestFile: Math.max(0, ...sizes.values()),
    manifestBytes: bytes(built.text),
  });

  // The publication record (17.5): never shortened; one snapshot is active.
  const ledger = store.readState(p, 'publications.json', { schema: 'rmf.econ.publications/1', publications: [] });
  const event = (status, reason = null) => ({ at: ctx.now, run: ctx.run.id, status, reason });
  const statusOf = (e) => e.events[e.events.length - 1].status;
  const publications = ledger.publications.map((e) => ({ snapshot: e.snapshot, events: [...e.events] }));
  if (c.rollback) {
    for (const e of publications) if (e.snapshot > c.rollback.to && statusOf(e) !== 'withdrawn') e.events.push(event('withdrawn', c.rollback.reason));
    publications.find((e) => e.snapshot === c.rollback.to)?.events.push(event('active', c.rollback.reason));
  } else {
    for (const e of publications) if (statusOf(e) === 'active') e.events.push(event('superseded'));
    publications.push({ snapshot: c.snapshot.id, events: [event('active')] });
  }
  ctx.publications = { schema: 'rmf.econ.publications/1', publications };
  c.staged.set('status/publications.json', canonicalJson(ctx.publications));
  const record = newRecord(ctx, 'published', c.snapshot.id, c.outcomes, c.absences ?? []);
  record.pruned = pruned;
  const records = [record, ...store.allRunRecords(p).filter((r) => r.id !== record.id)].sort((a, b) => (a.started_at > b.started_at ? -1 : a.started_at < b.started_at ? 1 : 0));
  const gateFlagBefore = ctx.collector.gate_failed;
  ctx.collector.gate_failed = false;
  let alerts = currentAlerts(ctx, { snapshot: c.snapshot, frozen: c.lockList ?? c.frozen ?? null, runAlerts: c.runAlerts, measured: measure(), records });
  record.alerts = planIssues(ctx.ledger, alerts, ctx.now).ledger.open.map((a) => a.key);
  const runsText = canonicalJson(store.runsFile(records));
  c.staged.set('status/runs.json', runsText);
  sizes.set('status/runs.json', bytes(runsText));
  store.writeStaging(p, ctx.run.id, c.staged, c.stagedHolds);
  if (ctx.o.faults?.breakStaged) ctx.o.faults.breakStaged(c.staged, c.stagedHolds);

  const problems = gateProblems({
    registry: ctx.registry,
    schemas: ctx.schemas,
    staged: c.staged,
    read: ctx.read,
    archived: (path) => store.readText(join(p.files, path)),
    holdText: (h) => {
      const local = `holds/${h.series}/${h.candidate.sha256.slice(0, 16)}.json`;
      return c.stagedHolds.get(local) ?? store.readText(join(p.root, 'archive', local));
    },
    previous: ctx.published.snapshot ? { snapshot: ctx.published.snapshot, manifest: ctx.published.manifest } : null,
    rollbackNamed: c.named ?? null,
    measured: measure(),
    limits: ctx.o.limits,
    calendar: ctx.calendar,
    holidays: ctx.o.holidays,
    windowRegistryHashes: Object.keys(provisional.kept).map((id) => snapshots[id].run.registry_sha256),
  });
  if (problems.length) {
    ctx.collector.gate_failed = true;
    void gateFlagBefore;
    const failed = newRecord(ctx, 'gate-failed', null, c.outcomes, c.absences ?? []);
    // Holds opened by this candidate were not published: the queue stays as it was.
    ctx.queue = { ...readQueue(p), frozen: queueLocks(ctx.locks) };
    alerts = currentAlerts(ctx, { snapshot: ctx.published.snapshot, runAlerts: [], measured: null, records: [failed, ...records.slice(1)] });
    return { outcome: 'gate-failed', problems, ...persist(ctx, failed, alerts) };
  }

  const archived = store.publish(p, { staged: c.staged, stagedHolds: c.stagedHolds, manifestText: built.text, generatedAt: ctx.now, die: ctx.o.faults?.die ?? null });
  for (const path of pruned) store.removeLive(p, path);
  for (const path of window.keep) if (path !== 'manifest.json' && path !== 'NOTICE.txt' && !path.startsWith('status/') && !existsSync(join(p.live, path))) store.ensureLive(p, path);
  store.writeState(p, 'publications.json', ctx.publications);
  ctx.collector.archive_bytes_by_month[month] = (ctx.collector.archive_bytes_by_month[month] ?? 0) + archived;
  return { outcome: 'published', problems: [], manifest: built.manifest, snapshot: c.snapshot, ...persist(ctx, record, alerts) };
}

/** The parts of the manifest for a series that did not change: carried from the published one. */
function carriedParts(ctx, id) {
  const m = ctx.published.manifest?.series[id];
  return { observations: ctx.published.observations[id], csvs: m?.csvs ?? [], revisions: m?.revisions ?? [] };
}

/** Stages a series' new objects and revision log; returns its snapshot state and parts (CSVs: stageCsvs). */
function stageSeries(ctx, c, s, { observations, retrievedAt, marker, records }) {
  const objects = buildObjects(s, observations);
  for (const o of objects) c.staged.set(o.path, o.text);
  let revisions = carriedParts(ctx, s.id).revisions;
  if (records.length) {
    const year = Number(ctx.runEt.slice(0, 4));
    const prefix = `revisions/${s.id}/${year}/`;
    const old = revisions.find((r) => r.path.startsWith(prefix));
    const log = revisionLog(s.id, year, old ? JSON.parse(ctx.read(old.path)).records : [], records);
    c.staged.set(log.path, log.text);
    c.snapshotRevisions.push({ path: log.path, sha256: log.sha256, bytes: log.bytes });
    revisions = [...revisions.filter((r) => !r.path.startsWith(prefix)), { path: log.path, sha256: log.sha256 }].sort((a, b) => (a.path < b.path ? -1 : 1));
  }
  c.parts[s.id] = { observations, csvs: [], revisions };
  return {
    objects: objects.map(({ segment, path, sha256, bytes: n }) => ({ segment, path, sha256, bytes: n })),
    last_period: observations[observations.length - 1][keyOf(s)],
    observation_count: observations.length,
    status: 'refreshed',
    retrieved_at: retrievedAt,
    checked_at: ctx.now,
    attempt: { at: ctx.now, outcome: 'ok', error: null },
    source_marker: marker ?? null,
  };
}

/**
 * The CSV segments of every published series in a new snapshot (16, 12.9): a segment whose
 * object the replaced manifest's snapshot named keeps its retrieval time; only CSVs that the
 * replaced manifest did not name are staged, so an unchanged segment is never written again.
 */
function stageCsvs(ctx, c) {
  for (const s of ctx.registry.series) {
    const st = c.series[s.id];
    if (st.status === 'not-yet-published') {
      c.parts[s.id].csvs = [];
      continue;
    }
    const before = ctx.published.manifest?.series[s.id];
    const prior = before ? { objects: ctx.published.snapshot.series[s.id].objects, csvs: before.csvs ?? [] } : null;
    const named = new Set((before?.csvs ?? []).map((x) => x.path));
    const csvs = csvSegments(s, ctx.registry.sources[s.source], buildObjects(s, c.parts[s.id].observations), st.retrieved_at, prior);
    for (const x of csvs) if (!named.has(x.path)) c.staged.set(x.path, x.text);
    c.parts[s.id].csvs = csvs.map(({ segment, path, sha256, retrieved_at }) => ({ segment, path, sha256, retrieved_at }));
  }
}

function newCandidate(ctx) {
  const newest = Object.keys(ctx.index.snapshots).sort().pop() ?? null;
  const id = snapshotId(ctx.now);
  if (newest !== null && id <= newest) throw new Error(`run refused: ${id} is not later than the newest snapshot ${newest}`);
  return { id, newest, staged: new Map(), stagedHolds: new Map(), parts: {}, snapshotRevisions: [], series: {}, holds: [], frozen: [], keptLocks: [], runAlerts: [], outcomes: {} };
}

function finishSnapshot(ctx, c) {
  const snapshot = {
    schema: 'rmf.econ.snapshot/2',
    id: c.id,
    previous: c.newest,
    created_at: ctx.now,
    run: { id: ctx.run.id, attempt: ctx.run.attempt, trigger: ctx.run.trigger, collector_commit: ctx.run.collector_commit, registry_sha256: registryHash(ctx.registry) },
    series: c.series,
    revisions: c.snapshotRevisions,
    holds: c.holds.sort((a, b) => (a.series < b.series ? -1 : 1)),
    frozen: c.frozen.sort((a, b) => (a.series < b.series ? -1 : 1)),
    notices: snapshotNotices(ctx.registry),
  };
  c.staged.set(`snapshots/${c.id}.json`, canonicalJson(snapshot));
  return snapshot;
}

async function collect(ctx) {
  ctx.blocked = new Set();
  ctx.requests = 0;
  // The held candidates in force, the base of a held series' windowed candidate (5).
  ctx.heldObservations = {};
  for (const h of ctx.published.snapshot?.holds ?? []) {
    const text = store.readText(join(ctx.p.root, 'archive', `holds/${h.series}/${h.candidate.sha256.slice(0, 16)}.json`));
    if (text !== null && sha256Hex(text) === h.candidate.sha256) ctx.heldObservations[h.series] = JSON.parse(text);
  }
  const results = {};
  const groups = requestGroups(ctx.registry);
  let anyDue = false;
  for (const g of groups) {
    const { due, start } = dueWindow(ctx, g);
    if (!due) {
      for (const s of g.members) results[s.id] = { outcome: 'not-due', error: null };
      continue;
    }
    anyDue = true;
    Object.assign(results, await collectGroup(ctx, g, start));
    for (const m of g.members) results[m.id].start = start;
    // A full fetch counts when its response was received and read (17.3, v0.7).
    if (start === null && !g.members.every((s) => ['failed', 'invalid'].includes(results[s.id].outcome))) ctx.collector.full_fetches = { ...(ctx.collector.full_fetches ?? {}), [g.id]: ctx.now };
    // Source state for alerts and failure counts (17.4).
    const src = (ctx.collector.sources[g.source] ??= { consecutive_failures: 0, last_failure: null, blocked: null, invalid: false });
    const outcomes = g.members.map((s) => results[s.id]);
    if (outcomes.every((r) => r.outcome === 'failed')) {
      src.consecutive_failures += 1;
      src.last_failure = outcomes[0].error;
      if (ctx.blocked.has(g.source)) src.blocked = outcomes[0].error;
    } else {
      src.consecutive_failures = 0;
      src.last_failure = null;
      src.blocked = null;
      src.invalid = outcomes.every((r) => r.outcome === 'invalid' && !r.seriesInvalid);
    }
    for (const s of g.members) {
      const r = results[s.id];
      // An undocumented gap alone is a source gap (11.6), not an invalid series.
      const bad = r.seriesInvalid === true && r.otherProblems !== false;
      ctx.collector.invalid_series = [...new Set([...ctx.collector.invalid_series.filter((x) => x !== s.id), ...(bad ? [s.id] : [])])].sort();
      // Gaps are known only when a candidate was read; a failed fetch or format keeps the state.
      if (r.gaps !== undefined) {
        const gaps = { ...ctx.collector.source_gaps };
        if (r.gaps.length) gaps[s.id] = { count: r.gaps.length, periods: r.gaps.slice(0, MAX_GAPS) };
        else delete gaps[s.id];
        ctx.collector.source_gaps = gaps;
      }
    }
  }
  const outcomes = Object.fromEntries(ctx.registry.series.map((s) => [s.id, results[s.id].outcome]));
  const records = () => store.allRunRecords(ctx.p).sort((a, b) => (a.started_at > b.started_at ? -1 : 1));
  if (!anyDue) {
    const record = newRecord(ctx, 'nothing-due', null, outcomes);
    return { outcome: 'nothing-due', requests: 0, ...persist(ctx, record, currentAlerts(ctx, { snapshot: ctx.published.snapshot, runAlerts: [], measured: null, records: [record, ...records()] })) };
  }

  const c = newCandidate(ctx);
  c.outcomes = outcomes;
  const oldHolds = new Map((ctx.published.snapshot?.holds ?? []).map((h) => [h.series, h]));
  const oldFrozen = ctx.published.snapshot?.frozen ?? [];
  let needSnapshot = false;
  for (const s of ctx.registry.series) {
    let r = results[s.id];
    const prev = stateOf(ctx, s.id);
    const oldHold = oldHolds.get(s.id);
    const locks = ctx.locks.filter((l) => l.series === s.id);
    const keep = (list) => {
      for (const l of list) {
        c.frozen.push(snapshotLock(l));
        c.keptLocks.push(l);
      }
    };
    const carry = (status, attemptOutcome, extra = {}) => ({ ...prev, status: prev.status === 'not-yet-published' ? 'not-yet-published' : status, attempt: { at: ctx.now, outcome: attemptOutcome, error: r.error ? errorText(r.error) : null }, ...extra });
    c.parts[s.id] = carriedParts(ctx, s.id);
    if (r.outcome === 'not-due' || r.outcome === 'failed' || r.outcome === 'invalid') {
      c.series[s.id] = carry(oldHold ? 'held' : 'carried-forward', r.outcome === 'not-due' ? 'not-due' : r.outcome);
      if (oldHold) c.holds.push(oldHold);
      keep(locks);
      continue;
    }
    if (locks.length) {
      // A locked series publishes nothing (11.5): each lock stands by its own rule, a rolled-back
      // one until a person clears it, a rejected one while the candidate carries any of its locked
      // changes or, on a windowed run, while one of them lies before the window (v0.6).
      const beforeWindow = (l) => r.start !== null && r.start !== undefined && l.locked_changes.some((x) => x.period < r.start);
      const standing = locks.filter((l) => l.origin === 'rolled-back' || beforeWindow(l) || carriesLock(s, l.observations, r.candidate, l.locked_changes));
      if (standing.length) {
        const same = r.outcome === 'unchanged';
        c.series[s.id] = oldHold ? carry('held', 'ok') : same ? carry('unchanged', 'ok', { checked_at: ctx.now }) : carry('carried-forward', 'ok');
        if (oldHold) c.holds.push(oldHold);
        keep(standing);
        outcomes[s.id] = same ? 'unchanged' : 'revised-unexpected';
        continue;
      }
      // No lock stands: the candidate carries none of the rejected observations and is classified
      // afresh below.
    }
    if (r.outcome === 'unchanged') {
      // The source exactly matches the published data: the only automatic way out of a hold
      // (11.5).
      c.series[s.id] = prev.status === 'not-yet-published' ? carry('not-yet-published', 'ok') : carry('unchanged', 'ok', { checked_at: ctx.now });
      if (oldHold) withdrawHold(ctx, c, s, oldHold);
      continue;
    }
    const cand = holdCandidate(s.id, r.candidate, ctx.now);
    if (oldHold && r.outcome !== 'revised-unexpected') {
      // An open hold is closed only by a person or by an exact return to the published data.
      r = { ...r, outcome: 'revised-unexpected', reason: oldHold.reason };
      outcomes[s.id] = 'revised-unexpected';
    }
    if (r.outcome === 'revised-unexpected') {
      const same = oldHold?.candidate.sha256 === cand.sha256;
      const hold = same ? oldHold : { series: s.id, candidate: { archive_asset: oldHold && !same ? cand.archive_asset : cand.archive_asset, sha256: cand.sha256, bytes: cand.bytes }, reason: r.reason, opened_at: oldHold?.opened_at ?? ctx.now };
      if (!same) {
        c.stagedHolds.set(cand.local, cand.text);
        const changes = { changed: r.diff.changed.length, removed: r.diff.removed.length, added: r.diff.added.length };
        const entry = { series: s.id, candidate_sha256: cand.sha256, archive_asset: cand.archive_asset, bytes: cand.bytes, reason: r.reason, opened_at: hold.opened_at, updated_at: ctx.now, changes };
        ctx.queue = { ...ctx.queue, open: [...ctx.queue.open.filter((q) => q.series !== s.id), entry].sort((a, b) => (a.series < b.series ? -1 : 1)) };
        ctx.collector.hold_meta[`${s.id}:${cand.sha256}`] = { ...entry, source_marker: r.marker ?? prev.source_marker };
      }
      c.holds.push(hold);
      c.series[s.id] = carry('held', 'ok');
      continue;
    }
    // appended or revised-expected: publish.
    const key = keyOf(s);
    const published = ctx.published.observations[s.id];
    const records2 = r.outcome === 'revised-expected'
      ? revisionRecords({ diff: r.diff, key, published, candidate: r.candidate, last: published.length ? published[published.length - 1][key] : null, detectedAt: ctx.now, snapshot: c.id, kind: 'expected', basisFor: (period) => r.basis.get(period), releaseFor: (period) => r.releaseDates.get(period) })
      : [];
    c.series[s.id] = stageSeries(ctx, c, s, { observations: r.candidate, retrievedAt: ctx.now, marker: r.marker ?? null, records: records2 });
    if (r.large?.length) c.runAlerts.push({ key: `revision-large:${s.id}`, severity: 'warning', title: `Large expected revision: ${s.id}`, body: `An expected revision of series ${s.id} changed ${r.large.length} period(s) by more than the alert ratio ${s.revision.alert_ratio} (first: ${r.large[0]}). It was published and logged.` });
    needSnapshot = true;
  }
  c.absences = absencesOf(ctx, c, results);
  for (const id of [...new Set(c.absences.filter((a) => a.detail === 'after-deadline').map((a) => a.series))]) {
    const first = c.absences.find((a) => a.series === id && a.detail === 'after-deadline');
    c.runAlerts.push({ key: `source-overdue:${id}`, severity: 'warning', title: `Source late: ${id}`, body: `The source answered and its data was valid, but it has no record yet for period ${first.period} of series ${id}, whose deadline has passed. This is the source being late, not a failure of collection.` });
  }
  // The queue keeps the details of the locks still in force; lifted ones leave it (11.5).
  ctx.queue = { ...ctx.queue, frozen: queueLocks(c.keptLocks) };
  const frozenKey = (list) => JSON.stringify(list.map((f) => [f.series, f.origin ?? 'rejected', f.candidate_sha256]).sort());
  if (frozenKey(c.frozen) !== frozenKey(oldFrozen)) needSnapshot = true;
  const holdKey = (list) => JSON.stringify(list.map((h) => [h.series, h.candidate.sha256]).sort());
  if (holdKey(c.holds) !== holdKey([...oldHolds.values()])) needSnapshot = true;
  for (const s of ctx.registry.series) if (category(c.series[s.id].status) !== category(stateOf(ctx, s.id).status)) needSnapshot = true;

  if (!needSnapshot) {
    const record = newRecord(ctx, 'no-change', null, outcomes, c.absences);
    return { outcome: 'no-change', requests: ctx.requests, ...persist(ctx, record, currentAlerts(ctx, { snapshot: ctx.published.snapshot, frozen: c.frozen, runAlerts: c.runAlerts, measured: null, records: [record, ...records()] })) };
  }
  stageCsvs(ctx, c);
  const snapshot = finishSnapshot(ctx, c);
  const result = publishCandidate(ctx, { ...c, snapshot, previousSnapshot: ctx.published.manifest?.snapshot.id ?? null, rollback: null });
  return { ...result, requests: ctx.requests };
}

/**
 * The absent periods of a run that sent requests (11.6): for each requested business-day or
 * monthly series with published data after this run, the periods after its last period (up to
 * the run's ET date; a monthly series only its next month) with their kind, then the
 * undocumented gaps of every requested series. A period that the candidate in force (a held or
 * frozen one) holds is not absent.
 */
function absencesOf(ctx, c, results) {
  const out = [];
  const holdText = (id, sha) => {
    const local = `holds/${id}/${sha.slice(0, 16)}.json`;
    return c.stagedHolds.get(local) ?? store.readText(join(ctx.p.root, 'archive', local));
  };
  for (const s of ctx.registry.series) {
    const r = results[s.id];
    if (r.outcome === 'not-due' || (s.frequency !== 'business-day' && s.frequency !== 'month')) continue;
    const st = c.series[s.id];
    const list = [];
    if (st.status !== 'not-yet-published') {
      const inForce = new Set();
      const held = c.holds.find((h) => h.series === s.id);
      const shas = [held?.candidate.sha256, ...c.frozen.filter((f) => f.series === s.id).map((f) => f.candidate_sha256)].filter(Boolean);
      for (const sha of shas) {
        const text = holdText(s.id, sha);
        if (text !== null) for (const o of JSON.parse(text)) inForce.add(o.period);
      }
      for (const o of r.candidate ?? []) inForce.add(o.period);
      const passedKind = () => (r.outcome === 'failed' ? ['collection-failure', 'fetch-failed'] : r.outcome === 'invalid' ? ['collection-failure', 'response-invalid'] : ['source-overdue', 'after-deadline']);
      const gaps = new Set((s.known_gaps ?? []).map((g) => g.period));
      if (s.frequency === 'business-day') {
        for (let d = addDays(st.last_period, 1); d <= ctx.runEt; d = addDays(d, 1)) {
          if (weekday(d) === 0 || weekday(d) === 6 || inForce.has(d)) continue;
          let kind;
          if (!ctx.calendar.isBusinessDay(d)) kind = ['expected-nonpublication', 'holiday'];
          else if (gaps.has(d)) kind = ['documented-gap', 'known-gap'];
          else if (!(ctx.now > periodDeadline(s, d, ctx.registry, ctx.calendar).deadline)) kind = ['expected-nonpublication', 'not-yet-due'];
          else kind = passedKind();
          list.push({ series: s.id, period: d, kind: kind[0], detail: kind[1] });
        }
      } else {
        const [y, m] = st.last_period.split('-').map(Number);
        const next = m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`;
        if (!inForce.has(next)) {
          const kind = !(ctx.now > deadlines(s, st, ctx.registry, ctx.calendar).deadline) ? ['expected-nonpublication', 'not-yet-due'] : passedKind();
          list.push({ series: s.id, period: next, kind: kind[0], detail: kind[1] });
        }
      }
    }
    for (const p of (r.gaps ?? []).slice(0, MAX_GAPS)) list.push({ series: s.id, period: p, kind: 'undocumented-gap', detail: 'inside-history' });
    out.push(...list);
  }
  return out;
}

function failed(ctx, error) {
  store.clearStaging(ctx.p);
  // Reload the state as it is on disk: nothing of the failed run is kept but its record.
  ctx.collector = { ...emptyCollector(), ...store.readState(ctx.p, 'collector.json', emptyCollector()) };
  ctx.queue = { ...readQueue(ctx.p), frozen: queueLocks(ctx.locks) };
  const record = newRecord(ctx, 'failed', null, {});
  const records = [record, ...store.allRunRecords(ctx.p).sort((a, b) => (a.started_at > b.started_at ? -1 : 1))];
  return { outcome: 'failed', error: error.message, ...persist(ctx, record, currentAlerts(ctx, { snapshot: ctx.published.snapshot, runAlerts: [], measured: null, records })) };
}

async function guarded(o, body) {
  const ctx = open(o);
  try {
    return await body(ctx);
  } catch (e) {
    if (/^simulated death/.test(e.message)) throw e;
    return failed(ctx, e);
  }
}

/**
 * One collector run. o: { root, mode, registry, schemas, sourceTable, holidays, now,
 * run: { id, attempt, trigger, collector_commit }, fetch, wait, healthFacts?, limits?, faults? }.
 */
export function runCollector(o) {
  if (o.mode === 'operation') return Promise.reject(new Error('run refused: a collection runs in mode "fixture" or "live"'));
  return guarded({ wait: async () => {}, ...o }, collect);
}

/**
 * The record of one review decision (17.5): the original values, the proposed values, the
 * affected periods, why the hold opened, the decision, who took it and why.
 */
function reviewRecord(ctx, c, s, hold, decision, reviewer, reason, auth) {
  const local = `holds/${s.id}/${hold.candidate.sha256.slice(0, 16)}.json`;
  const text = store.readText(join(ctx.p.root, 'archive', local));
  if (text === null || sha256Hex(text) !== hold.candidate.sha256) throw new Error('the held candidate is missing from the archive or does not match its hash');
  const candidate = JSON.parse(text);
  const key = keyOf(s);
  const diff = diffObservations(ctx.published.observations[s.id], candidate, key);
  const byPeriod = new Map(candidate.map((o) => [o[key], o]));
  const changes = [
    ...diff.removed.map((o) => ({ period: o[key], field: 'period', before: canonicalJson(o), after: null })),
    ...diff.added.map((p) => ({ period: p, field: 'period', before: null, after: canonicalJson(byPeriod.get(p)) })),
    ...diff.changed.flatMap((x) => x.fields.map((f) => ({ period: x.period, field: f.field, before: f.before, after: f.after }))),
  ].sort((a, b) => (a.period < b.period ? -1 : a.period > b.period ? 1 : a.field < b.field ? -1 : a.field > b.field ? 1 : 0));
  const affected = [...new Set(changes.map((x) => x.period))].sort();
  const publication = { outcome: { approve: 'published', reject: 'frozen', clear: 'cleared', withdrawn: 'withdrawn' }[decision], snapshot: c.id };
  const record = { schema: 'rmf.econ.review/3', series: s.id, candidate_sha256: hold.candidate.sha256, decision, decided_at: ctx.now, run: ctx.run.id, reviewer, reviewer_permission: auth.reviewer_permission, permission_checked_at: auth.permission_checked_at, reason, hold: { reason: hold.reason, opened_at: hold.opened_at }, affected_periods: affected, changes, publication };
  // The decision time is in the name: the same candidate can be decided more than once (17.1).
  const path = `reviews/${s.id}/${hold.candidate.sha256.slice(0, 16)}-${decision}-${snapshotId(ctx.now)}.json`;
  return { path, text: canonicalJson(record), candidate, diff, affected, publication };
}

/** Closes a hold with a decision, keeping the review record (17.5). */
function decide(ctx, c, s, hold, decision, reviewer, reason, auth = { reviewer_permission: null, permission_checked_at: null }) {
  const rec = reviewRecord(ctx, c, s, hold, decision, reviewer, reason, auth);
  c.stagedHolds.set(rec.path, rec.text);
  ctx.queue = {
    ...ctx.queue,
    // Clearing a lock leaves a hold of the same series open (11.5).
    open: decision === 'clear' ? ctx.queue.open : ctx.queue.open.filter((q) => q.series !== s.id),
    decisions: [...ctx.queue.decisions, { series: s.id, candidate_sha256: hold.candidate.sha256, decision, decided_at: ctx.now, run: ctx.run.id, reviewer, reviewer_permission: auth.reviewer_permission, permission_checked_at: auth.permission_checked_at, reason, affected_periods: rec.affected, publication: rec.publication, record: rec.path }],
  };
  return rec;
}

/** The source returned exactly to the published data: the hold closes as withdrawn. */
function withdrawHold(ctx, c, s, hold) {
  decide(ctx, c, s, hold, 'withdrawn', null, null);
}

/**
 * Why a review is refused (11.5, 17.5), checked in this order, or null when it may proceed:
 * the series is not held, the candidate changed, the decision, the texts, the reviewer's
 * permission (one of the registry's review permissions), the time it was read (within the hour
 * before the review, both ends included), and an automation login. Nothing approves on its own.
 */
function reviewRefusal(ctx, o) {
  if (o.decision === 'clear') {
    // Clearing a lock (v0.5): the series must be locked, with this candidate (v0.6: several locks).
    const mine = ctx.locks.filter((l) => l.series === o.series);
    if (!mine.length) return { rule: 'not-locked', error: `series ${o.series} is not locked` };
    if (!mine.some((l) => l.candidate_sha256 === o.candidate_sha256)) return { rule: 'stale-candidate', error: 'no lock of this series has this candidate; review the current locks' };
  } else {
    const hold = (ctx.published.snapshot?.holds ?? []).find((h) => h.series === o.series);
    if (!hold) return { rule: 'not-held', error: `series ${o.series} is not held` };
    if (hold.candidate.sha256 !== o.candidate_sha256) return { rule: 'stale-candidate', error: 'the held candidate has changed since; review the current one' };
    if (!['approve', 'reject'].includes(o.decision)) return { rule: 'bad-decision', error: 'the decision must be approve, reject or clear' };
    if (ctx.locks.some((l) => l.series === o.series)) return { rule: 'locked', error: `series ${o.series} is locked; clear the lock before deciding its hold` };
  }
  const text = (v) => typeof v === 'string' && v.trim() !== '';
  if (!text(o.reviewer) || !text(o.reason)) return { rule: 'missing-text', error: 'a review needs a reviewer and a reason' };
  if (!ctx.registry.family_policy.review.permissions.includes(o.reviewer_permission)) return { rule: 'permission', error: 'the reviewer does not have write access to the data repository' };
  const at = typeof o.permission_checked_at === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(o.permission_checked_at) ? Date.parse(o.permission_checked_at) : NaN;
  const now = Date.parse(ctx.now);
  if (!(at <= now && now - at <= PERMISSION_MAX_AGE_SECONDS * 1000)) return { rule: 'permission-time', error: 'the reviewer\'s permission was not read within the hour before the review' };
  if (AUTOMATION.test(o.reviewer.trim())) return { rule: 'automation', error: 'an automation account cannot decide a hold' };
  return null;
}

/** A review run (17.5): approve or reject the held candidate of a series, or clear its lock. */
export function reviewHold(o) {
  return guarded({ ...o, run: { ...o.run, trigger: 'review' } }, async (ctx) => {
    const refusal = reviewRefusal(ctx, o);
    if (refusal) {
      // A refused review changes nothing but its run record and the queue's refusals (11.5, 17.5).
      const given = (v) => (typeof v === 'string' ? v : null);
      ctx.queue = { ...ctx.queue, refusals: [...ctx.queue.refusals, { series: given(o.series), candidate_sha256: given(o.candidate_sha256), decision: given(o.decision), reviewer: given(o.reviewer), reviewer_permission: given(o.reviewer_permission), permission_checked_at: given(o.permission_checked_at), at: ctx.now, run: ctx.run.id, refused: refusal.rule }] };
      const record = newRecord(ctx, 'refused', null, {});
      const records = [record, ...store.allRunRecords(ctx.p).filter((r) => r.id !== record.id).sort((a, b) => (a.started_at > b.started_at ? -1 : 1))];
      return { outcome: 'refused', refused: refusal.rule, error: refusal.error, ...persist(ctx, record, currentAlerts(ctx, { snapshot: ctx.published.snapshot, runAlerts: [], measured: null, records })) };
    }
    const auth = { reviewer_permission: o.reviewer_permission, permission_checked_at: o.permission_checked_at };
    const s = ctx.registry.series.find((x) => x.id === o.series);
    const lock = ctx.locks.find((l) => l.series === o.series && l.candidate_sha256 === o.candidate_sha256);
    // A cleared lock is reviewed like a hold of its locked candidate.
    const hold = o.decision === 'clear'
      ? { series: s.id, candidate: { sha256: lock.candidate_sha256 }, reason: lock.reason, opened_at: lock.frozen_at }
      : ctx.published.snapshot.holds.find((h) => h.series === o.series);
    const c = newCandidate(ctx);
    for (const x of ctx.registry.series) {
      // A review fetches nothing: every other series is carried forward as it stands.
      const st = stateOf(ctx, x.id);
      c.series[x.id] = { ...st, status: st.status === 'not-yet-published' || st.status === 'held' ? st.status : 'carried-forward', attempt: { at: ctx.now, outcome: 'not-due', error: null } };
      c.parts[x.id] = carriedParts(ctx, x.id);
      c.outcomes[x.id] = 'not-due';
    }
    c.holds = o.decision === 'clear' ? [...ctx.published.snapshot.holds] : ctx.published.snapshot.holds.filter((h) => h.series !== o.series);
    // The locks in force carry on; a clear removes its own (11.5).
    const kept = ctx.locks.filter((l) => !(o.decision === 'clear' && l.series === o.series && l.candidate_sha256 === o.candidate_sha256));
    c.frozen = kept.map(snapshotLock);
    const prev = stateOf(ctx, s.id);
    const rec = decide(ctx, c, s, hold, o.decision, o.reviewer, o.reason, auth);
    let locks = kept;
    if (o.decision === 'clear') {
      // Nothing is published by clearing; from the next run the series is classified normally.
      c.outcomes[s.id] = 'not-due';
    } else if (o.decision === 'approve') {
      const key = keyOf(s);
      const published = ctx.published.observations[s.id];
      const meta = ctx.collector.hold_meta[`${s.id}:${hold.candidate.sha256}`];
      const basis = `approved in review run ${ctx.run.id} on ${ctx.runEt}`;
      const records = revisionRecords({ diff: rec.diff, key, published, candidate: rec.candidate, last: published[published.length - 1][key], detectedAt: ctx.now, snapshot: c.id, kind: 'approved-hold', basisFor: () => basis, releaseFor: () => null });
      c.series[s.id] = stageSeries(ctx, c, s, { observations: rec.candidate, retrievedAt: meta?.updated_at ?? ctx.now, marker: meta?.source_marker ?? prev.source_marker, records });
      c.series[s.id].checked_at = meta?.updated_at ?? ctx.now;
      c.series[s.id].attempt = { at: ctx.now, outcome: 'not-due', error: null };
      c.outcomes[s.id] = isSame(rec.diff) ? 'unchanged' : 'revised-unexpected';
    } else {
      // Rejected: the series is locked while the source carries the rejected change (11.5).
      c.series[s.id] = { ...prev, status: 'carried-forward', attempt: { at: ctx.now, outcome: 'not-due', error: null } };
      c.outcomes[s.id] = 'revised-unexpected';
      const changes = lockedChanges(s, ctx.published.observations[s.id], rec.candidate);
      const lockNew = { series: s.id, candidate_sha256: hold.candidate.sha256, origin: 'rejected', frozen_at: ctx.now, run: ctx.run.id, reviewer: o.reviewer, reason: o.reason, affected_periods: rec.affected, locked_changes: changes, observations: rec.candidate };
      locks = [...kept, lockNew];
      c.frozen.push(snapshotLock(lockNew));
    }
    ctx.queue = { ...ctx.queue, frozen: queueLocks(locks) };
    stageCsvs(ctx, c);
    const snapshot = finishSnapshot(ctx, c);
    return publishCandidate(ctx, { ...c, snapshot, previousSnapshot: ctx.published.manifest.snapshot.id, rollback: null });
  });
}

/**
 * A rollback (17.5): the manifest goes back to an earlier snapshot. Nothing published is
 * erased: the change is recorded in the revision logs and in the publication record.
 */
export function rollback(o) {
  return guarded({ ...o, run: { ...o.run, trigger: 'rollback' } }, async (ctx) => {
    const target = ctx.index.snapshots[o.to];
    if (!target) return { outcome: 'refused', error: `snapshot ${o.to} is not in the archive` };
    if (!ctx.published.manifest) return { outcome: 'refused', error: 'nothing is published' };
    if (ctx.published.manifest.snapshot.id === o.to) return { outcome: 'refused', error: `snapshot ${o.to} is already current` };
    if (typeof o.reason !== 'string' || o.reason.trim() === '') return { outcome: 'refused', error: 'a rollback needs a reason' };
    const named = [...ctx.index.manifests].reverse().find((m) => m.snapshot.id === o.to);
    if (!named) throw new Error(`no archived manifest names snapshot ${o.to}`);
    const staged = new Map();
    const stagedHolds = new Map();
    const parts = {};
    const rolledBack = [];
    const year = Number(ctx.runEt.slice(0, 4));
    const basis = `rolled back to snapshot ${o.to} in run ${ctx.run.id} on ${ctx.runEt}`;
    for (const s of ctx.registry.series) {
      const key = keyOf(s);
      const before = ctx.published.observations[s.id];
      const after = store.observationsOf(target, s.id, ctx.read);
      // The audit history keeps every version: the newest log versions, extended, never the
      // target's older ones.
      let revisions = ctx.published.manifest.series[s.id].revisions;
      const diff = diffObservations(before, after, key);
      if (!isSame(diff)) {
        // Every member that differs is recorded, a period taken away as a removed period.
        const records = revisionRecords({ diff, key, published: before, candidate: after, last: '9999-99-99', detectedAt: ctx.now, snapshot: o.to, kind: 'rollback', basisFor: () => basis, releaseFor: () => null });
        const prefix = `revisions/${s.id}/${year}/`;
        const old = revisions.find((r) => r.path.startsWith(prefix));
        const log = revisionLog(s.id, year, old ? JSON.parse(ctx.read(old.path)).records : [], records);
        staged.set(log.path, log.text);
        revisions = [...revisions.filter((r) => !r.path.startsWith(prefix)), { path: log.path, sha256: log.sha256 }].sort((a, b) => (a.path < b.path ? -1 : 1));
        // The series is locked (v0.5, 11.5): nothing of the withdrawn data is published again
        // until an authorized review clears the lock. The withdrawn observations are its candidate.
        const withdrawn = holdCandidate(s.id, before, ctx.now);
        stagedHolds.set(withdrawn.local, withdrawn.text);
        const changes = lockedChanges(s, after, before);
        rolledBack.push({ series: s.id, candidate_sha256: withdrawn.sha256, origin: 'rolled-back', frozen_at: ctx.now, run: ctx.run.id, reviewer: null, reason: o.reason, affected_periods: [...new Set(changes.map((x) => x.period))].sort(), locked_changes: changes, observations: before });
      }
      // The CSV segments of the newest archived manifest that names the target, exactly (12.9).
      parts[s.id] = { observations: after, csvs: named.series[s.id].csvs, revisions };
    }
    // The holds and locks of the target are in force again, as they were, and the rollback adds
    // its own locks, which replace a target lock of the same series.
    const targetLocks = (target.frozen ?? []).map((f) => {
      const known = ctx.queue.frozen.find((e) => lockKey(e) === lockKey({ ...f, origin: f.origin ?? 'rejected' }));
      const observations = candidateObservations(ctx.p, f.series, f.candidate_sha256);
      if (!observations) throw new Error(`the locked candidate of ${f.series} is missing from the archive`);
      const s = ctx.registry.series.find((x) => x.id === f.series);
      const changes = known?.locked_changes ?? lockedChanges(s, store.observationsOf(target, f.series, ctx.read), observations);
      return known ? { ...known, observations } : { series: f.series, candidate_sha256: f.candidate_sha256, origin: f.origin ?? 'rejected', frozen_at: f.frozen_at, run: 'rebuilt-from-published-state', reviewer: null, reason: f.reason, affected_periods: [...new Set(changes.map((x) => x.period))].sort(), locked_changes: changes, observations };
    });
    // Every lock in force before the rollback is kept (v0.6): rejections, also those decided after
    // the target, and earlier rollbacks' locks; then the rollback's own.
    const locks = [];
    const seen = new Set();
    for (const l of [...targetLocks, ...ctx.locks, ...rolledBack]) {
      if (seen.has(lockKey(l))) continue;
      seen.add(lockKey(l));
      locks.push(l);
    }
    const targetKeys = new Set(targetLocks.map(lockKey));
    const order = new Map(ctx.registry.series.map((x, i) => [x.id, i]));
    const recordLocks = locks.filter((l) => !targetKeys.has(lockKey(l))).sort((a, b) => order.get(a.series) - order.get(b.series) || (a.origin < b.origin ? -1 : a.origin > b.origin ? 1 : 0));
    const record = { schema: 'rmf.econ.rollback/1', from: ctx.published.manifest.snapshot.id, to: o.to, at: ctx.now, run: ctx.run.id, reason: o.reason, locks: recordLocks.map((l) => ({ series: l.series, origin: l.origin, candidate_sha256: l.candidate_sha256, locked_changes: l.locked_changes })) };
    stagedHolds.set(rollbackRecordPath(ctx.now), canonicalJson(record));
    const lockedIds = new Set(recordLocks.map((l) => l.series));
    ctx.queue = {
      ...ctx.queue,
      open: target.holds.map((h) => {
        const meta = ctx.collector.hold_meta[`${h.series}:${h.candidate.sha256}`];
        return { series: h.series, candidate_sha256: h.candidate.sha256, archive_asset: h.candidate.archive_asset, bytes: h.candidate.bytes, reason: h.reason, opened_at: h.opened_at, updated_at: meta?.updated_at ?? h.opened_at, changes: meta?.changes ?? { changed: 0, removed: 0, added: 0 } };
      }).sort((a, b) => (a.series < b.series ? -1 : 1)),
      frozen: queueLocks(locks),
    };
    const from = ctx.published.manifest.snapshot.id;
    const outcomes = Object.fromEntries(ctx.registry.series.map((s) => [s.id, 'not-due']));
    const locked = ctx.registry.series.map((s) => s.id).filter((id) => lockedIds.has(id));
    return publishCandidate(ctx, { staged, stagedHolds, snapshot: target, parts, previousSnapshot: from, rollback: { from, to: o.to, at: ctx.now, reason: o.reason, locked }, outcomes, runAlerts: [], named, lockList: locks.map(snapshotLock) });
  });
}

/** A restore (17.5): rebuilds the live tree from the archive alone, verifying every file. */
export function restore(o) {
  const p = store.paths(o.root);
  const index = store.archiveIndex(p);
  const names = store.listFiles(p.manifests);
  if (names.length === 0) return { outcome: 'refused', error: 'the archive holds no manifest' };
  const manifestText = readFileSync(join(p.manifests, names[names.length - 1]), 'utf8');
  const manifest = JSON.parse(manifestText);
  if (canonicalJson(manifest) !== manifestText) return { outcome: 'refused', error: 'the newest archived manifest is not canonical' };
  const pins = store.readState(p, 'pins.json', emptyPins());
  const window = liveWindow({ manifest, snapshots: index.snapshots, manifests: index.manifests, pins });
  // The hash that names each file: its address, or for a snapshot the manifest that named it.
  const snapshotHash = new Map(index.manifests.map((m) => [m.snapshot.path, m.snapshot.sha256]));
  const files = [];
  for (const path of [...window.keep].sort()) {
    if (path === 'manifest.json' || path === 'status/runs.json' || path === 'NOTICE.txt') continue;
    const text = store.readText(join(p.files, path));
    if (text === null) return { outcome: 'refused', error: `${path} is not in the archive` };
    const hash = sha256Hex(text);
    const expected = path.startsWith('snapshots/') ? snapshotHash.get(path) : null;
    // Content addresses: `<16 hex>.json|csv`, and from v0.8 the rule files `econ-` and
    // `holidays-<16 hex>.json` and `notices/<16 hex>.txt` (22.9).
    const addressed = /(?:\/|\/econ-|\/holidays-)([0-9a-f]{16})\.(json|csv|txt)$/.exec(path);
    if ((expected && expected !== hash) || (!path.startsWith('snapshots/') && (!addressed || addressed[1] !== hash.slice(0, 16)))) return { outcome: 'refused', error: `${path} does not match its hash` };
    files.push([path, text]);
  }
  const record = { id: o.run.id, trigger: 'restore', started_at: o.now, ended_at: o.now, outcome: 'published', snapshot: manifest.snapshot.id, series: {}, alerts: [], pruned: [], absences: [] };
  const ledger = store.readState(p, 'alerts.json', emptyLedger());
  record.alerts = ledger.open.map((a) => a.key);
  store.writeAtomic(join(p.records, `${record.id}.json`), canonicalJson(record));
  for (const f of store.listFiles(p.live)) store.removeLive(p, f);
  for (const [path, text] of files) store.writeAtomic(join(p.live, path), text);
  // v0.8 (22.9): NOTICE.txt is live only; it is a byte copy of the notice file the manifest names.
  if (manifest.rules) {
    const notice = files.find(([path]) => path === manifest.rules.notice.path);
    if (!notice) return { outcome: 'refused', error: `${manifest.rules.notice.path} is not in the window` };
    store.writeAtomic(join(p.live, 'NOTICE.txt'), notice[1]);
  }
  const publications = store.readText(join(p.state, 'publications.json'));
  if (publications !== null) store.writeAtomic(join(p.live, 'status/publications.json'), publications);
  store.writeAtomic(join(p.live, 'status/runs.json'), canonicalJson(store.runsFile(store.allRunRecords(p))));
  store.writeAtomic(join(p.live, 'manifest.json'), manifestText);
  store.clearStaging(p);
  return { outcome: 'published', record, restored: files.length };
}

/** Pins a snapshot (17.6). The manifest shows it from the next publication. */
export function pinSnapshot(o) {
  const p = store.paths(o.root);
  const pins = store.readState(p, 'pins.json', emptyPins());
  const known = Object.keys(store.archiveIndex(p).snapshots);
  const r = addPin(pins, { snapshot: o.snapshot, site_release: o.site_release, reason: o.reason, pinned_at: o.now }, known);
  if (r.ok) store.writeState(p, 'pins.json', r.pins);
  return r;
}

/** Unpins a snapshot on an explicit, recorded request (17.6). */
export function unpinSnapshot(o) {
  const p = store.paths(o.root);
  const r = removePin(store.readState(p, 'pins.json', emptyPins()), { snapshot: o.snapshot, reason: o.reason, unpinned_at: o.now });
  if (r.ok) store.writeState(p, 'pins.json', r.pins);
  return r;
}
