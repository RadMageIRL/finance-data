// Stage D gate 10, drills on fixtures (docs/P31_STAGE_D_IMPLEMENTATION_PLAN.md P4; DATA_CONVENTIONS
// v0.8 22.3 to 22.6): restore then publication, the state store unreachable (nothing is assembled),
// the private deployment log rebuilt from its public copy, rollback then publication (refused while
// a withdrawn snapshot was never public, allowed once it was), and a redeploy to a verified pair that
// rebuilds the target's archived window. Appendix J covers the rest (CAS, older data, the automatic
// redeploy, unpublish, the pause).
import { cpSync, existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/bin/state-scenario.mjs';
const { runStateScenario } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/bin/publish.mjs';
const { assemble } = m2 as unknown as Loose;
import * as m3 from '../../../pipeline/bin/state-op.mjs';
const { operate } = m3 as unknown as Loose;
import * as m4 from '../../../pipeline/lib/publication.mjs';
const { privateLogCopy, releaseTag } = m4 as unknown as Loose;
import * as m5 from '../../../pipeline/lib/publish-store.mjs';
const { archivedManifestText, archivedWindow } = m5 as unknown as Loose;
import * as m8 from '../../../pipeline/lib/store.mjs';
const { archiveIndex, paths } = m8 as unknown as Loose;
import * as m6 from '../../../pipeline/lib/canonical.mjs';
const { sha256Hex } = m6 as unknown as Loose;
import * as m7 from '../../../pipeline/bin/fixture-scenario.mjs';
const { loadInputs } = m7 as unknown as Loose;

const passing = () => ({ pass: 1, fail: 0, skip: 0 });
const dirs: string[] = [];
const newDir = () => {
  const d = mkdtempSync(join(tmpdir(), 'rmf-drill-'));
  dirs.push(d);
  return d;
};
afterAll(() => {
  for (const d of dirs) rmSync(d, { recursive: true, force: true });
});
const copyOf = (src: string) => {
  const d = join(newDir(), 'store');
  cpSync(src, d, { recursive: true });
  return d;
};
const acceptedOf = (s: string) => JSON.parse(readFileSync(join(s, 'state', 'STATE.json'), 'utf8')).accepted;
const go = (storeDir: string, more: Loose = {}) => assemble({ storeDir, mode: 'manual', input: more.input ?? acceptedOf(storeDir), runId: 700, attempt: 1, now: '2026-11-24T15:00:00Z', facts: null, siteCommit: 'a'.repeat(40), deployed: null, validateState: passing, validatePublication: passing, outDir: newDir(), ...more });
const deployedEntry = (dataset: Loose, n = 1) => ({ number: n, published_at: '2026-11-23T12:00:00Z', run: `pub-${600 + n}-1`, trigger: 'manual', dataset, release: releaseTag(dataset.snapshot, 600 + n, 1), site_commit: 'a'.repeat(40), artifact: { files: 1, bytes: 1, sha256: 'b'.repeat(64) }, previous: null, verification: { checker: { pass: 1, fail: 0, skip: 0 }, post: 'passed' } });

let g4 = '';
let g11 = '';
beforeAll(async () => {
  const a = join(newDir(), 'g');
  await runStateScenario(a, { validate: passing, upTo: 4 });
  g4 = join(a, 'store');
  const b = join(newDir(), 'g');
  await runStateScenario(b, { validate: passing });
  g11 = join(b, 'store');
}, 600_000);

describe('gate 10 drills on fixtures', () => {
  it('publishes after a restore, and assembles nothing from an unreachable, damaged or unpromoted store', async () => {
    const s = copyOf(g4);
    const at = '2026-11-24T14:00:00Z';
    const r = await operate({ op: 'restore', state: s, root: newDir(), run: 'drill-restore', actor: 'example-maintainer', permission: 'maintain', checkedAt: at, now: at, clock: () => at, validate: passing, inputs: loadInputs(), reason: 'Drill: rebuild the live tree from the archive.' });
    expect(r.outcome).toBe('published');
    expect(go(s).outcome).toBe('assembled');
    const gone = go(join(newDir(), 'no-store'), { input: acceptedOf(g4) });
    expect(gone).toEqual({ outcome: 'refused-v2', problems: ['V2a: the state store is fresh, not a promoted store'] });
    // A store whose descriptor names the v0.6 layout is not promoted (21.3), whatever else it holds.
    const old = copyOf(g4);
    const descriptor = JSON.parse(readFileSync(join(old, 'state', 'STATE.json'), 'utf8'));
    writeFileSync(join(old, 'state', 'STATE.json'), JSON.stringify({ ...descriptor, schema: 'rmf.econ.state/1' }));
    expect(go(old, { input: acceptedOf(g4) })).toEqual({ outcome: 'refused-v2', problems: ['V2a: the state store is v0.6, not a promoted store'] });
    const damaged = copyOf(g4);
    writeFileSync(join(damaged, 'state', 'STATE.json'), '{}');
    const out = newDir();
    expect(go(damaged, { outDir: out, input: acceptedOf(g4) }).outcome).toBe('refused-v2');
    expect(readdirSync(out)).toEqual([]);
  });

  it('rebuilds the private deployment log from its public copy', () => {
    const r = go(copyOf(g4));
    const publicCopy = JSON.parse(JSON.stringify(r.log));
    expect(privateLogCopy(publicCopy, null)).toEqual(r.log);
    expect(privateLogCopy(publicCopy, 'passed').deployments[0].verification.post).toBe('passed');
  });

  it('after a rollback, refuses publication while the withdrawn snapshots were never public, and allows it once a deployed release held them', () => {
    const s = copyOf(g11);
    expect(go(s)).toMatchObject({ outcome: 'refused-d5' });
    // The archived manifest that named the newest withdrawn snapshot, as a deployed release's dataset.
    const pubs = JSON.parse(readFileSync(join(s, 'root', 'live', 'status', 'publications.json'), 'utf8')).publications;
    const withdrawn = pubs.filter((p: Loose) => p.events.some((e: Loose) => e.status === 'withdrawn')).map((p: Loose) => p.snapshot).sort();
    expect(withdrawn.length).toBeGreaterThan(0);
    const manifests = readdirSync(join(s, 'root', 'archive', 'manifests')).map((f) => readFileSync(join(s, 'root', 'archive', 'manifests', f), 'utf8'));
    const named = manifests.find((t) => JSON.parse(t).snapshot.id === withdrawn[withdrawn.length - 1]);
    expect(named).toBeDefined();
    const dataset = { snapshot: withdrawn[withdrawn.length - 1], manifest_sha256: sha256Hex(named) };
    const facts = { newestLog: { schema: 'rmf.econ.deployments/1', deployments: [deployedEntry(dataset)] }, newestRun: { completed: true, siteConclusion: 'success', verifyConclusion: 'success' } };
    expect(go(s, { facts }).outcome).toBe('assembled');
  });

  it('rebuilds an older archived window without the snapshots created after its manifest (I37)', () => {
    const root = join(g11, 'root');
    const index = archiveIndex(paths(root));
    const created = Object.entries(index.snapshots as Record<string, Loose>).map(([id, snap]) => [id, snap.created_at] as [string, string]);
    const texts = readdirSync(join(root, 'archive', 'manifests')).map((f) => readFileSync(join(root, 'archive', 'manifests', f), 'utf8'));
    // The oldest archived manifest after which a later snapshot was still inside the 30-day window.
    const older = texts
      .map((t) => ({ t, at: JSON.parse(t).generated_at as string }))
      .sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0))
      .find(({ at }) => created.some(([, c]) => c > at && Date.parse(c) - Date.parse(at) < 30 * 86_400_000));
    expect(older).toBeDefined();
    const later = created.filter(([, c]) => c > older!.at).map(([id]) => id);
    expect(later.length).toBeGreaterThan(0);
    const w = archivedWindow(root, older!.t);
    expect(Object.keys(w.kept).filter((id) => later.includes(id))).toEqual([]);
    expect([...w.files.keys()].filter((path: string) => later.some((id) => path.includes(id)))).toEqual([]);
    expect(w.files.get('manifest.json').toString('utf8')).toBe(older!.t);
  });

  it('redeploys a verified pair by rebuilding its archived window exactly', () => {
    const s = copyOf(g4);
    const first = go(s);
    const facts = { newestLog: first.log, newestRun: { completed: true, siteConclusion: 'success', verifyConclusion: 'success' } };
    const out = newDir();
    const r = go(s, { mode: 'redeploy', target: { dataset: acceptedOf(s), site_commit: 'a'.repeat(40) }, facts, outDir: out });
    expect(r.outcome).toBe('assembled');
    expect(r.log.deployments.map((d: Loose) => [d.number, d.trigger, d.verification.post])).toEqual([[1, 'manual', 'passed'], [2, 'redeploy', null]]);
    expect(readFileSync(join(out, 'econ', 'manifest.json'), 'utf8')).toBe(archivedManifestText(join(s, 'root'), acceptedOf(s).manifest_sha256));
    expect(existsSync(join(out, 'econ', 'NOTICE.txt'))).toBe(true);
  });
});
