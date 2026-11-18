// Retention enforcement and budgets (DATA_CONVENTIONS sections 13, 17.6 and 17.7, decision
// P2): 35 days of live snapshots, at most 12 pins, 250 MB published, 50 MB of new archive a
// month, with warnings before either limit. Nothing pinned or significant is ever pruned, and
// nothing is pruned to make a budget fit.
import { snapshotTime } from './calendar.mjs';

export const WINDOW_DAYS = 35;
export const MAX_PINS = 12;
export const PIN_WARNING = 10;

/** Warning and critical levels in bytes, decimal units (17.7). */
export const BUDGET_LEVELS = {
  published: { warning: 125_000_000, critical: 200_000_000, hard: 250_000_000 },
  'archive-month': { warning: 25_000_000, critical: 40_000_000, hard: 50_000_000 },
  object: { warning: 1_000_000, hard: 2_000_000 },
  file: { warning: 2_000_000, hard: 5_000_000 },
  manifest: { warning: 128_000, hard: 256_000 },
};

export const emptyPins = () => ({ schema: 'rmf.econ.pins/1', pins: [], unpinned: [] });

/** Adds a pin. A 13th is refused; nothing is unpinned to make room. */
export function addPin(pins, { snapshot, site_release, reason, pinned_at }, knownSnapshots) {
  if (!knownSnapshots.includes(snapshot)) return { ok: false, error: `snapshot ${snapshot} is not in the archive`, pins };
  if (pins.pins.some((p) => p.snapshot === snapshot)) return { ok: false, error: `snapshot ${snapshot} is already pinned`, pins };
  if (pins.pins.length >= MAX_PINS) return { ok: false, error: `${MAX_PINS} snapshots are pinned already; unpin one explicitly first`, pins };
  if (!reason || !site_release) return { ok: false, error: 'a pin needs a site release and a reason', pins };
  return { ok: true, error: null, pins: { ...pins, pins: [...pins.pins, { snapshot, site_release, reason, pinned_at }] } };
}

/** Removes a pin on an explicit, recorded request. */
export function removePin(pins, { snapshot, reason, unpinned_at }) {
  if (!pins.pins.some((p) => p.snapshot === snapshot)) return { ok: false, error: `snapshot ${snapshot} is not pinned`, pins };
  if (!reason) return { ok: false, error: 'unpinning needs a reason', pins };
  return { ok: true, error: null, pins: { ...pins, pins: pins.pins.filter((p) => p.snapshot !== snapshot), unpinned: [...pins.unpinned, { snapshot, reason, unpinned_at }] } };
}

/**
 * Whether a snapshot is significant (17.6). `previous` is the snapshot before it in time (or
 * null): a hold opened, changed or closed when the two lists of holds differ.
 */
export function isSignificant(snapshot, previous) {
  const holds = (s) => JSON.stringify((s?.holds ?? []).map((h) => [h.series, h.candidate.sha256]).sort());
  // A snapshot that locks or unlocks a series is kept too (v0.5, 17.6).
  const locks = (s) => JSON.stringify((s?.frozen ?? []).map((f) => f.series).sort());
  return snapshot.previous === null || snapshot.revisions.length > 0 || snapshot.run.trigger === 'review' || holds(snapshot) !== holds(previous) || locks(snapshot) !== locks(previous);
}

/** The namespace paths a snapshot names, itself included. */
export function filesOfSnapshot(snapshot) {
  const out = [`snapshots/${snapshot.id}.json`];
  for (const s of Object.values(snapshot.series)) for (const o of s.objects) out.push(o.path);
  for (const r of snapshot.revisions) out.push(r.path);
  return out;
}

/**
 * The live window (13, 17.6). snapshots: every archived snapshot by id; manifests: every
 * archived manifest (the CSVs and revision logs a snapshot's manifest named stay with it).
 * Returns { keep: Set(paths), kept: { snapshotId: reason } }.
 */
export function liveWindow({ manifest, snapshots, manifests, pins, days = WINDOW_DAYS }) {
  const ids = Object.keys(snapshots).sort();
  const kept = {};
  const mark = (id, why) => {
    if (id && snapshots[id] && !kept[id]) kept[id] = why;
  };
  const current = manifest.snapshot.id;
  mark(current, 'current');
  mark(snapshots[current]?.previous, 'previous');
  mark(manifest.previous_snapshot, 'manifest-previous');
  const cutoff = Date.parse(manifest.generated_at) - days * 86_400_000;
  ids.forEach((id, i) => {
    const s = snapshots[id];
    if (pins.pins.some((p) => p.snapshot === id)) mark(id, 'pinned');
    if (isSignificant(s, i > 0 ? snapshots[ids[i - 1]] : null)) mark(id, 'significant');
    if (Date.parse(s.created_at ?? snapshotTime(id)) > cutoff) mark(id, 'window');
  });
  const keep = new Set(['manifest.json', 'status/runs.json']);
  for (const id of Object.keys(kept)) for (const p of filesOfSnapshot(snapshots[id])) keep.add(p);
  // The files the manifests of kept snapshots named (CSVs, revision log versions).
  for (const m of [manifest, ...manifests]) {
    if (!kept[m.snapshot.id]) continue;
    for (const s of Object.values(m.series)) {
      for (const c of s.csvs ?? []) keep.add(c.path);
      for (const r of s.revisions) keep.add(r.path);
      for (const o of s.objects) keep.add(o.path);
    }
  }
  return { keep, kept };
}

/** Paths in the live tree that are outside the window: what a run may prune, sorted. */
export function prunable(livePaths, window) {
  return livePaths.filter((p) => !window.keep.has(p) && !p.startsWith('status/')).sort();
}

/** Budget alerts for the measured values (17.7). */
export function budgetAlerts(measured, pinCount) {
  const mb = (n) => `${(n / 1_000_000).toFixed(1)} MB`;
  const alerts = [];
  const level = (key, value, text) => {
    const l = BUDGET_LEVELS[key];
    const severity = l.critical !== undefined && value >= l.critical ? 'critical' : value >= l.warning ? 'warning' : null;
    if (severity) alerts.push({ key: `budget:${key}`, severity, title: `Budget ${severity}: ${text}`, body: `${text} is ${mb(value)}; warning at ${mb(l.warning)}${l.critical ? `, critical at ${mb(l.critical)}` : ''}, hard limit ${mb(l.hard)}. Nothing is deleted automatically; over the hard limit the publish gate fails and a person decides.` });
  };
  level('published', measured.publishedBytes, 'published storage');
  // Everything left after pruning must be kept: at the critical level the limits conflict and
  // only the owner can decide (17.6).
  if (measured.publishedBytes >= BUDGET_LEVELS.published.critical) alerts.push({ key: 'retention-decision', severity: 'critical', title: 'A retention decision is needed', body: `Published storage is ${mb(measured.publishedBytes)} of the ${mb(BUDGET_LEVELS.published.hard)} budget after pruning everything outside the live window. What remains is the 35 day window, pinned snapshots and significant snapshots. Decide: raise the budget, shorten the window, or release named pins or significant snapshots from the live tree (the archive keeps them). Nothing is removed automatically; at the hard limit publication stops.` });
  level('archive-month', measured.archiveMonthBytes, 'new archive bytes this month');
  level('object', measured.largestObject, 'the largest object');
  level('file', measured.largestFile, 'the largest published file');
  level('manifest', measured.manifestBytes, 'the manifest');
  if (pinCount >= PIN_WARNING) alerts.push({ key: 'budget:pins', severity: 'warning', title: 'Budget warning: pinned snapshots', body: `${pinCount} of ${MAX_PINS} pins are in use. A pin beyond ${MAX_PINS} is refused; unpin explicitly to make room.` });
  return alerts;
}
