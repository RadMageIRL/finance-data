// The publish gate (DATA_CONVENTIONS section 12 and 17.7): runs on the whole candidate view
// before anything reaches the archive or the live tree. Returns every problem found; an empty
// list means the run may publish.
import { canonicalJson, sha256Hex } from './canonical.mjs';
import { validate } from './json-schema.mjs';
import { registryProblems } from './registry-policy.mjs';
import { diffObservations, keyOf } from './classify.mjs';
import { csvSegments, lastSummary } from './tree.mjs';

/** Hard limits in bytes, decimal units (decision P2, section 17.7). */
export const HARD_LIMITS = { object: 2_000_000, file: 5_000_000, manifest: 256_000, published: 250_000_000, archiveMonth: 50_000_000 };

const bytes = (text) => Buffer.byteLength(text, 'utf8');
const ADDRESSED = /^(objects\/[a-z0-9-]+\/(\d{4}|all)|series\/[a-z0-9-]+\/(?:\d{4}|all)|revisions\/[a-z0-9-]+\/\d{4})\/([0-9a-f]{16})\.(json|csv)$/;

function schemaFor(path, schemas) {
  if (path === 'manifest.json') return schemas.manifest;
  if (path === 'status/runs.json') return schemas.runs;
  if (path === 'status/publications.json') return schemas.publications;
  if (path.startsWith('objects/')) return schemas.object;
  if (path.startsWith('snapshots/')) return schemas.snapshot;
  if (path.startsWith('revisions/')) return schemas.revisions;
  return null;
}

/**
 * view: {
 *   registry, schemas: { registry, manifest, snapshot, object, revisions, runs },
 *   staged: Map(path -> text),            the run's new files, namespace paths
 *   read(path) -> text | null,            archive first, then the live tree
 *   archived(path) -> text | null,        the archive as it stood before this run
 *   holdText(hold) -> text | null,        a held candidate's bytes (staged or archived)
 *   previous: { snapshot, manifest } | null,   the published state before this run
 *   measured: { publishedBytes, archiveMonthBytes },
 *   limits (optional)
 * }
 */
export function gateProblems(view) {
  const { registry, schemas, staged, previous } = view;
  const limits = { ...HARD_LIMITS, ...(view.limits ?? {}) };
  const problems = [];
  const add = (item, message) => problems.push(`gate ${item}: ${message}`);
  const get = (path) => staged.get(path) ?? view.read(path);

  // 1. Registry.
  for (const e of validate(schemas.registry, registry)) add(1, `registry schema ${e}`);
  for (const p of registryProblems(registry)) add(1, p);

  const manifestText = staged.get('manifest.json');
  if (manifestText === undefined) return [...problems, 'gate 3: no manifest staged'];
  let manifest;
  let snapshot;
  try {
    manifest = JSON.parse(manifestText);
    const snapText = get(manifest.snapshot.path);
    if (snapText === null) return [...problems, `gate 3: snapshot ${manifest.snapshot.path} missing`];
    if (sha256Hex(snapText) !== manifest.snapshot.sha256) add(3, `snapshot ${manifest.snapshot.path} does not match its hash`);
    snapshot = JSON.parse(snapText);
  } catch (e) {
    return [...problems, `gate 8: unreadable manifest or snapshot (${e.message})`];
  }
  if (manifest.snapshot.path !== `snapshots/${manifest.snapshot.id}.json` || snapshot.id !== manifest.snapshot.id) add(3, 'the manifest and its snapshot disagree on the id');

  // 8. Every staged JSON file validates and is canonical.
  for (const [path, text] of staged) {
    if (!path.endsWith('.json')) continue;
    let value;
    try {
      value = JSON.parse(text);
    } catch {
      add(8, `${path} is not JSON`);
      continue;
    }
    if (canonicalJson(value) !== text) add(8, `${path} is not canonical`);
    const schema = schemaFor(path, schemas);
    if (!schema) add(8, `${path}: no schema for this path`);
    else for (const e of validate(schema, value)) add(8, `${path} ${e}`);
  }
  if (problems.length) return problems;

  // 2. Every registered series, and only those.
  const ids = registry.series.map((s) => s.id).sort();
  for (const [name, obj] of [['snapshot', snapshot.series], ['manifest', manifest.series]]) {
    if (JSON.stringify(Object.keys(obj).sort()) !== JSON.stringify(ids)) add(2, `the ${name} does not list exactly the registered series`);
  }
  if (snapshot.run.registry_sha256 !== sha256Hex(canonicalJson(registry))) add(2, 'the snapshot was not built from this registry');
  if (problems.length) return problems;

  // 3. Closure and addresses.
  const closure = (ref, where, withBytes) => {
    const text = get(ref.path);
    if (text === null) return add(3, `${where}: ${ref.path} missing`);
    const hash = sha256Hex(text);
    if (hash !== ref.sha256) add(3, `${where}: ${ref.path} does not match its hash`);
    if (withBytes && bytes(text) !== ref.bytes) add(3, `${where}: ${ref.path} is ${bytes(text)} bytes, stated ${ref.bytes}`);
    const m = ADDRESSED.exec(ref.path);
    if (!m) add(3, `${where}: ${ref.path} is not a content-addressed path`);
    else if (m[3] !== hash.slice(0, 16)) add(3, `${where}: ${ref.path} is not at its address`);
    return text;
  };
  const observationsOf = (snap, id) => {
    const out = [];
    for (const o of snap.series[id].objects) {
      const text = get(o.path);
      if (text !== null) out.push(...JSON.parse(text).observations);
    }
    return out;
  };
  for (const s of registry.series) {
    const st = snapshot.series[s.id];
    const ms = manifest.series[s.id];
    for (const o of st.objects) {
      const text = closure(o, `snapshot ${s.id}`, true);
      if (text !== null) {
        const obj = JSON.parse(text);
        if (obj.series !== s.id || obj.segment !== o.segment || o.path !== `objects/${s.id}/${o.segment}/${o.sha256.slice(0, 16)}.json`) add(3, `${o.path} is not an object of ${s.id} segment ${o.segment}`);
        for (const e of validate(schemas.object, obj)) add(8, `${o.path} ${e}`);
        // 7. Sizes.
        if (bytes(text) > limits.object) add(7, `${o.path} is ${bytes(text)} bytes, over the object limit ${limits.object}`);
      }
    }
    for (const r of ms.objects) closure(r, `manifest ${s.id}`, false);
    for (const c of ms.csvs) {
      const text = closure(c, `manifest ${s.id}`, false);
      if (text !== null && bytes(text) > limits.file) add(7, `${c.path} is over the file limit`);
      if (!c.path.startsWith(`series/${s.id}/${c.segment}/`)) add(3, `${c.path} is not the ${c.segment} CSV segment of ${s.id}`);
    }
    for (const r of ms.revisions) {
      closure(r, `manifest ${s.id}`, false);
      if (!r.path.startsWith(`revisions/${s.id}/`)) add(3, `${r.path} is not a revision log of ${s.id}`);
    }
    // 9. The manifest's summary equals the snapshot and objects.
    const obs = observationsOf(snapshot, s.id);
    if (JSON.stringify(ms.objects) !== JSON.stringify(st.objects.map((o) => ({ path: o.path, sha256: o.sha256 })))) add(9, `${s.id}: the manifest's objects differ from the snapshot's`);
    if (obs.length !== st.observation_count) add(9, `${s.id}: observation_count ${st.observation_count} but ${obs.length} observations`);
    const sum = lastSummary(s, obs);
    if (st.last_period !== sum.last_period) add(9, `${s.id}: the snapshot's last_period is ${st.last_period}, the objects end at ${sum.last_period}`);
    for (const k of ['last_period', 'last_value', 'last_range', 'last_released']) if (JSON.stringify(ms[k]) !== JSON.stringify(sum[k])) add(9, `${s.id}: the manifest's ${k} differs from the objects`);
    if (ms.retrieved_at !== st.retrieved_at || ms.checked_at !== st.checked_at) add(9, `${s.id}: the manifest's times differ from the snapshot's`);
    if ((st.status === 'not-yet-published') !== (ms.status === 'not-yet-published') || (st.status === 'held') !== (ms.status === 'held')) add(9, `${s.id}: the manifest's status ${ms.status} does not fit the snapshot's ${st.status}`);
    const locked = (snapshot.frozen ?? []).some((f) => f.series === s.id) || (manifest.rollback?.locked ?? []).includes(s.id);
    if ((ms.status === 'frozen') !== (locked && st.status !== 'held' && st.status !== 'not-yet-published')) add(9, `${s.id}: the manifest's status ${ms.status} does not fit the locks in force`);
    if (st.status === 'not-yet-published' && (st.objects.length || st.last_period !== null || st.retrieved_at !== null || st.checked_at !== null || st.source_marker !== null || st.observation_count !== 0 || ms.csvs.length || ms.revisions.length)) add(9, `${s.id}: a not yet published series carries data`);
    if (st.status !== 'not-yet-published' && (st.objects.length === 0 || ms.csvs.length === 0)) add(9, `${s.id}: a published series has no objects or no CSV`);
    // CSV segments (12.9, 16): one per object, exactly as 16 builds them, with the retrieval
    // time carried for an unchanged object; a rollback names the target manifest's entries.
    if (st.status !== 'not-yet-published') {
      if (ms.csvs.map((c) => c.segment).join() !== st.objects.map((o) => o.segment).join()) add(9, `${s.id}: the CSV segments do not match the objects one to one`);
      let expected = null;
      if (manifest.rollback !== null) expected = view.rollbackNamed?.series[s.id]?.csvs ?? null;
      else {
        const prior = previous?.manifest ? { objects: previous.snapshot.series[s.id].objects, csvs: previous.manifest.series[s.id].csvs ?? [] } : null;
        const objs = st.objects.map((o) => {
          const t = get(o.path);
          return t === null ? null : { segment: o.segment, sha256: o.sha256, observations: JSON.parse(t).observations };
        });
        if (objs.every(Boolean)) expected = csvSegments(s, registry.sources[s.source], objs, st.retrieved_at, prior).map(({ segment, path, sha256, retrieved_at }) => ({ segment, path, sha256, retrieved_at }));
      }
      if (expected === null) add(9, `${s.id}: the CSV segments cannot be checked`);
      else for (const e of expected) {
        const g = ms.csvs.find((c) => c.segment === e.segment);
        if (!g || canonicalJson(g) !== canonicalJson(e)) add(9, `${s.id}: CSV segment ${e.segment} is not the one section 16 builds (path, hash or retrieval time)`);
      }
    }
  }
  for (const r of snapshot.revisions) closure(r, 'snapshot revisions', true);
  for (const h of snapshot.holds) {
    const text = view.holdText(h);
    if (text === null) add(3, `hold ${h.series}: candidate ${h.candidate.archive_asset} missing from the archive`);
    else if (sha256Hex(text) !== h.candidate.sha256 || bytes(text) !== h.candidate.bytes) add(3, `hold ${h.series}: the candidate does not match its hash or size`);
    if (snapshot.series[h.series]?.status !== 'held') add(3, `hold ${h.series}: the series is not held in the snapshot`);
  }
  for (const s of registry.series) if (snapshot.series[s.id].status === 'held' && !snapshot.holds.some((h) => h.series === s.id)) add(3, `${s.id} is held without a hold entry`);

  // 4. Immutability against the archive as it stood.
  for (const [path, text] of staged) {
    if (path === 'manifest.json' || path.startsWith('status/')) continue;
    const old = view.archived(path);
    if (old !== null && old !== text) add(4, `${path} exists in the archive with different bytes`);
  }

  // 5 and 6 compare with the published state before this run. A rollback writes no snapshot.
  const prev = previous?.snapshot ?? null;
  const rewritesSnapshot = staged.has(manifest.snapshot.path);
  if (rewritesSnapshot) {
    const wrote = new Map();
    for (const r of snapshot.revisions) {
      const m = /^revisions\/([a-z0-9-]+)\/(\d{4})\//.exec(r.path);
      if (!m) continue;
      if (!wrote.has(m[1])) wrote.set(m[1], []);
      wrote.get(m[1]).push({ ref: r, year: Number(m[2]) });
    }
    for (const s of registry.series) {
      const st = snapshot.series[s.id];
      const before = prev?.series[s.id];
      // 5. Provenance.
      if (st.status !== 'refreshed' && st.status !== 'not-yet-published') {
        if (!before || before.status === 'not-yet-published') add(5, `${s.id}: status ${st.status} without earlier published data`);
        else if (JSON.stringify(before.objects) !== JSON.stringify(st.objects) || before.retrieved_at !== st.retrieved_at) add(5, `${s.id}: ${st.status} but its objects or retrieved_at changed`);
      }
      // 6. Revision log.
      const key = keyOf(s);
      const old = before && before.status !== 'not-yet-published' ? observationsOf(prev, s.id) : [];
      const now = observationsOf(snapshot, s.id);
      const diff = diffObservations(old, now, key);
      const last = old.length ? old[old.length - 1][key] : null;
      const want = [];
      for (const o of diff.removed) want.push([o[key], 'period', canonicalJson(o), null]);
      for (const p of diff.added) if (last !== null && p <= last) want.push([p, 'period', null, canonicalJson(now.find((o) => o[key] === p))]);
      for (const c of diff.changed) for (const f of c.fields) want.push([c.period, f.field, f.before, f.after]);
      const got = [];
      for (const { ref, year } of wrote.get(s.id) ?? []) {
        const text = get(ref.path);
        if (text === null) continue;
        const log = JSON.parse(text);
        if (log.series !== s.id || log.year !== year) add(6, `${ref.path} is not the ${year} log of ${s.id}`);
        const mine = log.records.filter((r) => r.snapshot === snapshot.id);
        got.push(...mine.map((r) => [r.period, r.field, r.before, r.after]));
        const earlier = log.records.slice(0, log.records.length - mine.length);
        if (log.records.slice(log.records.length - mine.length).some((r) => r.snapshot !== snapshot.id)) add(6, `${ref.path}: this run's records are not at the end`);
        const prevRef = (previous?.manifest?.series[s.id]?.revisions ?? []).find((r) => r.path.startsWith(`revisions/${s.id}/${year}/`));
        const prevRecords = prevRef ? JSON.parse(get(prevRef.path) ?? '{"records":[]}').records : [];
        if (canonicalJson(earlier) !== canonicalJson(prevRecords)) add(6, `${ref.path} does not extend the previous version`);
        if (!manifest.series[s.id].revisions.some((r) => r.path === ref.path)) add(6, `${ref.path} is not named by the manifest`);
      }
      const norm = (list) => list.map((x) => JSON.stringify(x)).sort();
      const a = norm(want);
      const b = norm(got);
      if (JSON.stringify(a) !== JSON.stringify(b)) add(6, `${s.id}: ${a.length} published change(s) but ${b.length} matching revision record(s)`);
    }
  }

  // A rollback writes no snapshot: its revision log versions must hold exactly the rollback
  // records of the difference, and must extend, never replace, the versions before (17.5).
  if (!rewritesSnapshot && previous && manifest.rollback !== null) {
    for (const s of registry.series) {
      const key = keyOf(s);
      const before = previous.snapshot.series[s.id].status === 'not-yet-published' ? [] : observationsOf(previous.snapshot, s.id);
      const after = observationsOf(snapshot, s.id);
      const diff = diffObservations(before, after, key);
      const want = [];
      for (const o of diff.removed) want.push([o[key], 'period', canonicalJson(o), null]);
      for (const p of diff.added) want.push([p, 'period', null, canonicalJson(after.find((o) => o[key] === p))]);
      for (const c of diff.changed) for (const f of c.fields) want.push([c.period, f.field, f.before, f.after]);
      const yearOf = (ref) => /^revisions\/[a-z0-9-]+\/(\d{4})\//.exec(ref.path)?.[1];
      const prevRefs = previous.manifest.series[s.id].revisions;
      const nowRefs = manifest.series[s.id].revisions;
      const got = [];
      for (const ref of nowRefs) {
        const prevRef = prevRefs.find((r) => yearOf(r) === yearOf(ref));
        if (prevRef && prevRef.path === ref.path) continue;
        const text = get(ref.path);
        if (text === null) continue;
        const log = JSON.parse(text);
        const old = prevRef ? JSON.parse(get(prevRef.path) ?? '{"records":[]}').records : [];
        if (canonicalJson(log.records.slice(0, old.length)) !== canonicalJson(old)) add(6, `${ref.path} does not extend the previous version`);
        for (const r of log.records.slice(old.length)) {
          if (r.kind !== 'rollback' || r.snapshot !== manifest.snapshot.id) add(6, `${ref.path}: a rollback may only add rollback records naming its target`);
          got.push([r.period, r.field, r.before, r.after]);
        }
      }
      for (const prevRef of prevRefs) if (!nowRefs.some((r) => yearOf(r) === yearOf(prevRef))) add(6, `${s.id}: the rollback dropped the ${yearOf(prevRef)} revision log from the manifest`);
      const norm = (list) => list.map((x) => JSON.stringify(x)).sort();
      if (JSON.stringify(norm(want)) !== JSON.stringify(norm(got))) add(6, `${s.id}: the rollback changes ${want.length} member(s) but records ${got.length}`);
    }
  }
  if (!rewritesSnapshot && manifest.rollback === null) add(9, 'a manifest that is not a rollback must come with its snapshot');

  // 7. Sizes and budgets.
  for (const [path, text] of staged) if (bytes(text) > limits.file) add(7, `${path} is ${bytes(text)} bytes, over the file limit ${limits.file}`);
  if (bytes(manifestText) > limits.manifest) add(7, `manifest.json is ${bytes(manifestText)} bytes, over ${limits.manifest}`);
  if (view.measured.publishedBytes > limits.published) add(7, `published storage would be ${view.measured.publishedBytes} bytes, over ${limits.published}; nothing is dropped to make room: a retention decision is needed`);
  if (view.measured.archiveMonthBytes > limits.archiveMonth) add(7, `new archive bytes this month would be ${view.measured.archiveMonthBytes}, over ${limits.archiveMonth}`);

  // Rollback consistency (section 9).
  if (manifest.rollback !== null && (manifest.rollback.to !== manifest.snapshot.id || manifest.rollback.from !== manifest.previous_snapshot)) add(9, 'the rollback record does not match the manifest');
  return problems;
}
