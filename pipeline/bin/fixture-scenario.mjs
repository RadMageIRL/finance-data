#!/usr/bin/env node
// Writes a pipeline root by running a fixed sequence of fixture runs (DATA_CONVENTIONS
// appendix B) through the collector adapters and the fixture transport, with the committed
// registry and holiday table. Test data, never a publication: the first run publishes the whole
// saved history of all nine series, and every later value is synthetic and exists only to
// exercise a rule. The same command always writes the same bytes. No network.
//
//   node pipeline/bin/fixture-scenario.mjs <dir>
import { existsSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { adapterFetch } from '../collectors/adapters.mjs';
import { makeWait } from '../lib/fixture-fetch.mjs';
import { effrRawRecord, loadRawFixtures, makeFixtureTransport } from '../lib/fixture-transport.mjs';
import { pinSnapshot, restore, reviewHold, rollback, runCollector } from '../lib/run.mjs';
import { zipRead, zipWrite } from '../lib/zip.mjs';

const HERE = join(dirname(fileURLToPath(import.meta.url)), '..');
const json = (rel) => JSON.parse(readFileSync(join(HERE, rel), 'utf8'));
export const SCHEMA_NAMES = ['registry', 'manifest', 'snapshot', 'object', 'revisions', 'runs', 'publications'];

/** A registry whose series begin where a slice of history begins (tests on small data only). */
export function sliceRegistry(registry, starts) {
  const copy = JSON.parse(JSON.stringify(registry));
  for (const s of copy.series) {
    const start = starts[s.source];
    s.earliest = start;
    if (s.known_gaps) s.known_gaps = s.known_gaps.filter((g) => g.period >= start);
  }
  return copy;
}

/**
 * The inputs of a fixture run. With `slice`, the small contiguous excerpts (EFFR and Debt to
 * the Penny from 2026-09-01, H.6 from 2024-10) and a registry that begins there, for fast
 * tests; without, the committed registry, for runs on the whole saved history.
 */
export function loadInputs({ slice = false } = {}) {
  const registry = json('registry/econ.json');
  return {
    registry: slice ? sliceRegistry(registry, { 'nyfed-markets': '2026-09-01', fiscaldata: '2026-09-01', 'frb-releases': '2024-10' }) : registry,
    schemas: Object.fromEntries(SCHEMA_NAMES.map((n) => [n, json(`schemas/${n}.schema.json`)])),
    sourceTable: json('schemas/source-records.json'),
    holidays: json(`registry/${registry.holiday_table}`),
    effr: json('fixtures/sources/effr-recent.json').refRates,
    debt: json('fixtures/sources/dtp-recent.json').data,
    h6: json('fixtures/sources/h6-excerpt.json'),
  };
}

/** A synthetic EFFR record for a day after the saved data. */
export const effrDay = (date, rate = 3.88, extra = {}) => ({ effectiveDate: date, type: 'EFFR', percentRate: rate, percentPercentile1: 3.85, percentPercentile25: 3.87, percentPercentile75: 3.89, percentPercentile99: 3.9, targetRateFrom: 3.75, targetRateTo: 4, volumeInBillions: 97, revisionIndicator: '', ...extra });

const addDollars = (text, n) => {
  const [int, frac] = text.split('.');
  return `${(BigInt(int) + BigInt(n)).toString()}.${frac}`;
};

/** A synthetic Debt to the Penny record: the last record's amounts plus whole dollars. */
export function debtDay(last, date, plus) {
  const [y, m, d] = date.split('-');
  return { ...last, record_date: date, debt_held_public_amt: addDollars(last.debt_held_public_amt, plus), intragov_hold_amt: addDollars(last.intragov_hold_amt, plus), tot_pub_debt_out_amt: addDollars(last.tot_pub_debt_out_amt, 2 * plus), record_calendar_year: y, record_calendar_month: m, record_calendar_day: d };
}

/**
 * A synthetic H.6 release: in every copy of every registered monthly series the last month is
 * changed by `revise(name, value)` and a new month is added.
 */
export function h6Release(xml, { prepared, lastPeriod, newPeriod, revise }) {
  let out = xml.replace(/(<message:Prepared>)[^<]*(<\/message:Prepared>)/, `$1${prepared}$2`);
  out = out.replace(/<(\w+):Series\b([^>]*)>[\s\S]*?<\/\1:Series>/g, (block, _prefix, attrs) => {
    const name = /SERIES_NAME="([^"]+)"/.exec(attrs)[1];
    const unit = /UNIT_MULT="([^"]+)"/.exec(attrs)[1];
    if (!/\.M$/.test(name) || unit !== '1e+09' || !/FREQ="129"/.test(attrs)) return block;
    const last = new RegExp(`(\\n\\s*)<frb:Obs OBS_STATUS="A" OBS_VALUE="([^"]+)" TIME_PERIOD="${lastPeriod}" />`);
    return block.replace(last, (_m, indent, value) => {
      const revised = revise(name, value);
      return `${indent}<frb:Obs OBS_STATUS="A" OBS_VALUE="${revised}" TIME_PERIOD="${lastPeriod}" />${indent}<frb:Obs OBS_STATUS="A" OBS_VALUE="${(Number(value) + 12.4).toFixed(1)}" TIME_PERIOD="${newPeriod}" />`;
    });
  });
  return out;
}

const COMMIT = '0'.repeat(40);
const empty = Buffer.alloc(0);

export async function runScenario(root) {
  if (existsSync(root) && readdirSync(root).length) throw new Error(`${root} is not empty`);
  const inputs = loadInputs();
  const base = { root, mode: 'fixture', registry: inputs.registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays };
  const state = loadRawFixtures();
  let h6Xml = zipRead(state.h6Zip, 'H6_data.xml', 64_000_000).toString('utf8');
  const log = [];
  const wait = makeWait();
  const pace = makeWait();
  let n = 0;
  const id = () => `scenario-${String(n).padStart(2, '0')}`;
  const note = (r, more) => log.push({ step: n, outcome: r.outcome, snapshot: r.record?.snapshot ?? null, alerts: r.record?.alerts ?? [], plan: (r.plan ?? []).map((a) => `${a.action} ${a.key}`), problems: r.problems ?? [], error: r.error ?? null, ...more });
  const run = async (now, scripted = {}) => {
    n += 1;
    const transport = makeFixtureTransport(state, scripted);
    const fetch = adapterFetch({ registry: inputs.registry, transport, wait: pace });
    const r = await runCollector({ ...base, now, run: { id: id(), attempt: 1, trigger: 'schedule', collector_commit: COMMIT }, fetch, wait });
    note(r, { now, requests: transport.calls.length });
    return r;
  };
  const op = async (name, fn, args) => {
    n += 1;
    const r = await fn({ ...base, ...args, run: { id: id(), attempt: 1, trigger: 'manual', collector_commit: COMMIT } });
    note(r, { now: args.now, op: name });
    return r;
  };
  const effr = (date, rate, extra) => state.effr.push(effrRawRecord(effrDay(date, rate, extra)));
  const lastDebt = () => state.debt[state.debt.length - 1];
  const debtValue = (date, field) => state.debt.find((r) => r.record_date === date)[field];
  const setDebt = (date, field, value) => {
    state.debt = state.debt.map((r) => (r.record_date === date ? { ...r, [field]: value } : r));
  };

  // 1. First publication of all nine series, the whole saved history (Friday 09:17 ET).
  const first = await run('2026-11-13T14:17:00Z');
  // 2. An hour later: nothing changed.
  await run('2026-11-13T15:17:00Z');
  // 3. A same-day EFFR revision of 2026-11-12, flagged by the publisher: expected.
  state.effr = state.effr.map((r) => (r.date === '2026-11-12' ? { date: r.date, text: r.text.replace('"percentRate": 3.88', '"percentRate": 3.87').replace('"revisionIndicator": ""', '"revisionIndicator": "r"') } : r));
  await run('2026-11-13T16:17:00Z');
  // 4. Sunday: the weekly full fetch finds the published total of 2019-12-31 one dollar higher,
  //    a historical period: held.
  setDebt('2019-12-31', 'tot_pub_debt_out_amt', addDollars(debtValue('2019-12-31', 'tot_pub_debt_out_amt'), 1));
  await run('2026-11-15T15:17:00Z');
  // 5. Monday: a new EFFR day; the held series' windowed candidate keeps the 2019 change.
  effr('2026-11-13');
  await run('2026-11-16T14:17:00Z');
  // 6. Monday evening: a new debt day, and the published total of 2026-11-10 changed: the held
  //    candidate is replaced (the 2019 change, the 2026-11-10 change and the new day).
  const total1110 = debtValue('2026-11-10', 'tot_pub_debt_out_amt');
  state.debt.push(debtDay(lastDebt(), '2026-11-13', 1_000_000_000));
  setDebt('2026-11-10', 'tot_pub_debt_out_amt', addDollars(total1110, 5_000_000));
  await run('2026-11-16T22:17:00Z');
  // 7. Tuesday: a new EFFR day; the held candidate changed again (the reviewer sees the latest).
  effr('2026-11-16', 3.87);
  setDebt('2026-11-10', 'tot_pub_debt_out_amt', addDollars(total1110, 6_000_000));
  const refreshed = await run('2026-11-17T14:17:00Z');
  // 8. A maintainer approves the held candidate: only the 2019 and 2026 segments of
  //    debt-total get new objects and CSVs.
  const held = refreshed.snapshot.holds.find((h) => h.series === 'debt-total');
  await op('approve', reviewHold, { now: '2026-11-17T15:00:00Z', series: 'debt-total', candidate_sha256: held.candidate.sha256, decision: 'approve', reviewer: 'example-maintainer', reviewer_permission: 'maintain', permission_checked_at: '2026-11-17T15:00:00Z', reason: 'Synthetic scenario: the publisher corrected the totals for 2019-12-31 and 2026-11-10.' });
  // 9. Two server errors, then an answer: retried inside the run.
  const ny = 'markets.newyorkfed.org';
  await run('2026-11-17T15:17:00Z', { [ny]: [{ status: 503, headers: {}, bytes: empty }, { status: 503, headers: { 'retry-after': '5' }, bytes: empty }] });
  // 10. The provider refuses requests.
  await run('2026-11-17T16:17:00Z', { [ny]: [{ status: 429, headers: {}, bytes: empty }] });
  // 11. A response in an unknown format.
  await run('2026-11-17T17:17:00Z', { [ny]: [{ status: 200, headers: {}, bytes: Buffer.from(JSON.stringify({ refRates: [{ ...effrDay('2026-11-16'), surprise: 1 }] })) }] });
  // 12. Wednesday: a new EFFR day and debt day; a published intragovernmental value changed: held.
  effr('2026-11-17');
  state.debt.push(debtDay(lastDebt(), '2026-11-16', 2_000_000_000));
  const intragov1112 = debtValue('2026-11-12', 'intragov_hold_amt');
  setDebt('2026-11-12', 'intragov_hold_amt', addDollars(intragov1112, 7));
  const heldAgain = await run('2026-11-18T14:17:00Z');
  const rejectHash = heldAgain.snapshot.holds.find((h) => h.series === 'debt-intragov').candidate.sha256;
  // 13. An account with read access only tries to approve it: refused, nothing changes.
  await op('refused review', reviewHold, { now: '2026-11-18T14:25:00Z', series: 'debt-intragov', candidate_sha256: rejectHash, decision: 'approve', reviewer: 'example-reader', reviewer_permission: 'read', permission_checked_at: '2026-11-18T14:25:00Z', reason: 'Synthetic scenario: an approval by an account without write access.' });
  // 14. A writer rejects it: the series is frozen.
  await op('reject', reviewHold, { now: '2026-11-18T14:30:00Z', series: 'debt-intragov', candidate_sha256: rejectHash, decision: 'reject', reviewer: 'example-writer', reviewer_permission: 'write', permission_checked_at: '2026-11-18T14:30:00Z', reason: 'Synthetic scenario: the changed value does not agree with the published total.' });
  // 15. The rejected candidate comes back identical: still frozen, nothing published.
  await run('2026-11-18T22:17:00Z');
  // The site build pins the first snapshot for its no-JavaScript pages (no run).
  pinSnapshot({ root, snapshot: first.record.snapshot, site_release: 'v0.2.0', reason: 'pinned by the site build for the no-JavaScript data pages', now: '2026-11-19T12:00:00Z' });
  // 16. Thursday evening: the source returns the published value, with the new days: thawed.
  setDebt('2026-11-12', 'intragov_hold_amt', intragov1112);
  state.debt.push(debtDay(lastDebt(), '2026-11-17', 1_500_000_000));
  state.debt.push(debtDay(lastDebt(), '2026-11-18', 1_500_000_000));
  effr('2026-11-18');
  await run('2026-11-19T22:17:00Z');
  // 17. H.6 release day: a new month, a revision of M1 above the alert ratio, a small one of
  //     M2; new EFFR days; the debt source is down.
  for (const [d, rate] of [['2026-11-19', 3.88], ['2026-11-20', 3.87], ['2026-11-23', 3.88]]) effr(d, rate);
  h6Xml = h6Release(h6Xml, {
    prepared: '2026-11-17T15:17:34',
    lastPeriod: '2026-09-30',
    newPeriod: '2026-10-31',
    revise: (name, value) => (name === 'M1.M' ? (Number(value) * 1.06).toFixed(1) : name === 'M2.M' ? (Number(value) + 0.3).toFixed(1) : value),
  });
  state.h6Zip = zipWrite([{ name: 'H6_data.xml', data: h6Xml }]);
  state.h6Dates = state.h6Dates.map((y) => (y.yearValue === '2026' ? { ...y, Months: [{ MonthName: 'November', MonthValue: '202611', Dates: ['20261124'] }, ...y.Months] } : y));
  const release = await run('2026-11-24T19:17:00Z', { 'api.fiscaldata.treasury.gov': [{ timeout: true }, { timeout: true }, { timeout: true }, { timeout: true }] });
  // 18. A rollback to the snapshot before the release.
  await op('rollback', rollback, { now: '2026-11-24T20:00:00Z', to: release.snapshot.previous, reason: 'example rollback in the fixture scenario' });
  // 19. The live tree is lost and restored from the archive.
  rmSync(join(root, 'live'), { recursive: true, force: true });
  n += 1;
  const restored = restore({ root, now: '2026-11-24T20:30:00Z', run: { id: id() } });
  log.push({ step: n, now: '2026-11-24T20:30:00Z', op: 'restore', outcome: restored.outcome, snapshot: restored.record?.snapshot ?? null, restored: restored.restored ?? 0, error: restored.error ?? null });
  // 20. The debt source answers again with three new days; the EFFR and H.6 sources still serve
  //     the withdrawn data: the five locked series publish nothing.
  for (const d of ['2026-11-19', '2026-11-20', '2026-11-23']) state.debt.push(debtDay(lastDebt(), d, 1_000_000_000));
  await run('2026-11-24T22:17:00Z');
  // 21. A maintainer clears the lock of m1-sa.
  const queue = JSON.parse(readFileSync(join(root, 'archive', 'state', 'review-queue.json'), 'utf8'));
  const m1Lock = queue.frozen.find((f) => f.series === 'm1-sa');
  await op('clear', reviewHold, { now: '2026-11-25T15:00:00Z', series: 'm1-sa', candidate_sha256: m1Lock.candidate_sha256, decision: 'clear', reviewer: 'example-maintainer', reviewer_permission: 'maintain', permission_checked_at: '2026-11-25T15:00:00Z', reason: 'Synthetic scenario: the H.6 release was checked against the Board and may be published again.' });
  // 22. The H.6 source still serves the release: only m1-sa gets it again.
  await run('2026-11-25T15:17:00Z');
  return { log, waits: wait.calls, pacing: pace.calls };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const dir = process.argv[2];
  if (!dir) {
    console.error('usage: node pipeline/bin/fixture-scenario.mjs <dir>');
    process.exit(2);
  }
  const { log, waits, pacing } = await runScenario(dir);
  for (const l of log) console.log(JSON.stringify(l));
  console.log(`waits (seconds, injected, never slept): retries ${JSON.stringify(waits)}, pacing ${JSON.stringify(pacing)}`);
}
