// DATA_CONVENTIONS v0.8 regression coverage (owner briefs L to O, Stage D P3): manifest/4 with
// per-series deadlines and staleness times, revision CSVs, the rule files (registry versions,
// holiday table, notice file with the L1 statement, NOTICE.txt), the gate's checks on them, and
// the reason check exactly as 22.3 states it.
import { mkdtempSync, readFileSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = Record<string, any>;
import * as m1 from '../../../pipeline/bin/fixture-scenario.mjs';
const { effrDay, loadInputs } = m1 as unknown as Loose;
import * as m2 from '../../../pipeline/lib/fixture-fetch.mjs';
const { makeFixtureFetch, makeWait } = m2 as unknown as Loose;
import * as m3 from '../../../pipeline/lib/run.mjs';
const { restore, runCollector } = m3 as unknown as Loose;
import * as m4 from '../../../pipeline/lib/rules.mjs';
const { L1_STATEMENT, V07_NYFED_TERMS, noticeText, registryCopyPath, registryVersions, ruleFiles } = m4 as unknown as Loose;
import * as m5 from '../../../pipeline/lib/tree.mjs';
const { registryHash, revisionCsv } = m5 as unknown as Loose;
import * as m6 from '../../../pipeline/lib/alerts.mjs';
const { textRefusal } = m6 as unknown as Loose;
import * as m7 from '../../../pipeline/lib/canonical.mjs';
const { canonicalJson, sha256Hex } = m7 as unknown as Loose;

const inputs = loadInputs({ slice: true });
const roots: string[] = [];
const newRoot = () => {
  const d = mkdtempSync(join(tmpdir(), 'rmf-v08-'));
  roots.push(d);
  return d;
};
afterAll(() => {
  for (const r of roots) rmSync(r, { recursive: true, force: true });
});
const base = (root: string, registry = inputs.registry) => ({ root, mode: 'fixture', registry, schemas: inputs.schemas, sourceTable: inputs.sourceTable, holidays: inputs.holidays });
const data = (effr: Loose[] = inputs.effr): Loose => ({ effr: { records: effr }, debt: { rows: inputs.debt }, h6: { body: inputs.h6 } });
let counter = 0;
const go = (root: string, now: string, d: Loose, more: Loose = {}) => {
  counter += 1;
  return runCollector({ ...base(root, more.registry), now, run: { id: `v08-${counter}`, attempt: 1, trigger: 'schedule', collector_commit: '0'.repeat(40) }, fetch: makeFixtureFetch(d), wait: makeWait(), ...more });
};
const text = (root: string, rel: string) => readFileSync(join(root, rel), 'utf8');
const json = (root: string, rel: string) => JSON.parse(text(root, rel));
const FIRST = '2026-11-13T14:17:00Z';

describe('registry versions (22.9, appendix I row I7)', () => {
  it('derives v0.7 and v0.6 by exactly the three substitutions and nothing else', () => {
    const [v08, v07, v06] = registryVersions(inputs.registry);
    expect([v08.version, v07.version, v06.version]).toEqual(['v0.8', 'v0.7', 'v0.6']);
    expect(v08.sha256).toBe(registryHash(inputs.registry));
    expect(v07.registry.sources['nyfed-markets'].terms_url).toBe(V07_NYFED_TERMS);
    expect(Object.values(v07.registry.sources as Record<string, Loose>).map((s: Loose) => s.terms_checked)).toEqual(['2026-11-16', '2026-11-16', '2026-11-16']);
    // Undo the three substitutions: the rest is byte for byte the current registry.
    const back = structuredClone(v07.registry);
    back.conventions = 'v0.8';
    back.sources['nyfed-markets'].terms_url = inputs.registry.sources['nyfed-markets'].terms_url;
    for (const [k, s] of Object.entries(back.sources) as [string, Loose][]) s.terms_checked = inputs.registry.sources[k].terms_checked;
    expect(canonicalJson(back)).toBe(v08.text);
    expect(v06.registry.conventions).toBe('v0.6');
    expect({ ...v06.registry, conventions: 'v0.7' }).toEqual(v07.registry);
    expect(registryCopyPath(v08.sha256)).toBe(`registry/econ-${v08.sha256.slice(0, 16)}.json`);
  });

  it('takes an earlier v0.8 registry from its archived copy, and refuses a version found neither way (I44)', () => {
    const edited = structuredClone(inputs.registry);
    edited.sources.fiscaldata.terms_checked = '2026-11-21';
    const editedText = canonicalJson(edited);
    const editedHash = sha256Hex(editedText);
    const r = ruleFiles({ registry: inputs.registry, holidays: inputs.holidays, generatedAt: FIRST, windowRegistryHashes: [registryHash(inputs.registry), editedHash], archivedRegistry: (h: string) => (h === editedHash ? editedText : null) });
    expect(r.rules.registry_versions).toEqual([{ path: registryCopyPath(editedHash), sha256: editedHash }]);
    expect(r.files.get(registryCopyPath(editedHash))).toBe(editedText);
    expect(() => ruleFiles({ registry: inputs.registry, holidays: inputs.holidays, generatedAt: FIRST, windowRegistryHashes: [editedHash] })).toThrow(/neither archived nor a version of appendix I row I7/);
    // An archived copy whose bytes do not hash to the name is not taken.
    expect(() => ruleFiles({ registry: inputs.registry, holidays: inputs.holidays, generatedAt: FIRST, windowRegistryHashes: [editedHash], archivedRegistry: () => `${editedText} ` })).toThrow(/neither archived/);
  });
});

describe('the notice file (22.9, L1)', () => {
  it('lists the sources in id order with a blank line after each, writes a shared line once, and ends with the L1 statement', () => {
    const t = noticeText(inputs.registry, '2026-12-31T23:00:00Z');
    expect(t.endsWith(`\n\n${L1_STATEMENT}\n`)).toBe(true);
    const blocks = t.slice(0, t.length - L1_STATEMENT.length - 1).split('\n\n').filter(Boolean);
    expect(blocks.map((b: string) => b.split('\n')[0])).toEqual(Object.keys(inputs.registry.sources).sort().map((k) => inputs.registry.sources[k].publisher));
    const ny = blocks[Object.keys(inputs.registry.sources).sort().indexOf('nyfed-markets')]!.split('\n');
    expect(ny[ny.length - 1]).toBe('Terms: https://www.newyorkfed.org/privacy/termsofuse');
    expect(new Set(ny).size).toBe(ny.length);
    expect(t).toContain('© 2026 Federal Reserve Bank of New York.');
    // {year} is the ET year: 03:00 UTC on 1 January is still 31 December in New York.
    expect(noticeText(inputs.registry, '2027-01-01T03:00:00Z')).toBe(t);
    expect(noticeText(inputs.registry, '2027-01-01T06:00:00Z')).toContain('© 2027 Federal Reserve Bank');
    expect(L1_STATEMENT.startsWith('RadMage Finance dedicates to the public domain under CC0 1.0 Universal')).toBe(true);
  });
});

describe('the revision CSV (10, D17)', () => {
  it('quotes fields with a comma, a quote or a line feed, leaves null empty, and is named by its own hash', () => {
    const effr = inputs.registry.series.find((s: Loose) => s.id === 'effr');
    const log = canonicalJson({ schema: 'rmf.econ.revisions/1', series: 'effr', year: 2026, records: [
      { detected_at: '2026-11-13T14:17:00Z', snapshot: '20261113T141700Z', period: '2026-11-12', field: 'value', before: '3.88', after: '3.87', kind: 'expected', basis: 'EFFR publication day 2026-11-13', release_date: null },
      { detected_at: '2026-11-14T14:17:00Z', snapshot: '20261114T141700Z', period: '2026-11-12', field: 'flags', before: '{"a":"x,y"}', after: 'say "hi"', kind: 'expected', basis: 'line\nbreak', release_date: '2026-11-14' },
    ] });
    const csv = revisionCsv(effr, inputs.registry.sources['nyfed-markets'], log);
    const lines = csv.text.split('\n');
    expect(lines[0]).toBe(`# ${effr.title} (${effr.unit_label}): changes we observed between our collections, 2026`);
    expect(lines).toContain('detected_at,snapshot,period,field,before,after,kind,basis,release_date');
    expect(csv.text).toContain('2026-11-13T14:17:00Z,20261113T141700Z,2026-11-12,value,3.88,3.87,expected,EFFR publication day 2026-11-13,\n');
    expect(csv.text).toContain('flags,"{""a"":""x,y""}","say ""hi""",expected,"line\nbreak",2026-11-14\n');
    expect(csv.path).toBe(`revisions/effr/2026/${sha256Hex(csv.text).slice(0, 16)}.csv`);
    expect(csv.text.endsWith('\n')).toBe(true);
  });
});

describe('manifest/4 and the rule files in a publication (9, 22.9)', () => {
  it('writes deadlines and staleness times, names the rule files, archives them and keeps NOTICE.txt live only', async () => {
    const root = newRoot();
    const r = await go(root, FIRST, data());
    expect(r.outcome).toBe('published');
    const m = json(root, 'live/manifest.json');
    expect(m.schema).toBe('rmf.econ.manifest/4');
    expect(m.series.effr.deadline).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
    expect(m.series.effr.stale_at > m.series.effr.deadline).toBe(true);
    // The target follows the EFFR: no deadline of its own, the EFFR's staleness time.
    expect(m.series['fomc-target'].deadline).toBeNull();
    expect(m.series['fomc-target'].stale_at).toBe(m.series.effr.stale_at);
    for (const s of Object.values(m.series) as Loose[]) expect(s.revision_csvs).toHaveLength(s.revisions.length);
    expect(m.rules.registry).toEqual({ path: registryCopyPath(registryHash(inputs.registry)), sha256: registryHash(inputs.registry) });
    expect(m.rules.registry_versions).toEqual([]);
    for (const ref of [m.rules.registry, m.rules.holidays, m.rules.notice]) {
      expect(sha256Hex(text(root, `live/${ref.path}`))).toBe(ref.sha256);
      expect(existsSync(join(root, 'archive/files', ref.path))).toBe(true);
    }
    expect(text(root, 'live/NOTICE.txt')).toBe(text(root, `live/${m.rules.notice.path}`));
    expect(existsSync(join(root, 'archive/files/NOTICE.txt'))).toBe(false);
  });

  it('names the earlier registry copy after a registry edit within v0.8 (I44)', async () => {
    const root = newRoot();
    await go(root, FIRST, data());
    const first = registryHash(inputs.registry);
    const edited = structuredClone(inputs.registry);
    edited.sources.fiscaldata.terms_checked = '2026-11-21';
    const recs = [...inputs.effr, effrDay('2026-11-13')];
    const r = await go(root, '2026-11-16T14:17:00Z', data(recs), { registry: edited });
    expect(r.outcome).toBe('published');
    const m = json(root, 'live/manifest.json');
    expect(m.rules.registry.sha256).toBe(registryHash(edited));
    expect(m.rules.registry_versions).toEqual([{ path: registryCopyPath(first), sha256: first }]);
    // The window keeps every rule file its manifests name (17.6): nothing of them is pruned.
    for (const ref of [m.rules.registry, m.rules.holidays, m.rules.notice, ...m.rules.registry_versions]) expect(sha256Hex(text(root, `live/${ref.path}`))).toBe(ref.sha256);
  });

  it('restores NOTICE.txt from the notice file the manifest names', async () => {
    const root = newRoot();
    await go(root, FIRST, data());
    const before = text(root, 'live/NOTICE.txt');
    rmSync(join(root, 'live'), { recursive: true, force: true });
    const r = restore({ ...base(root), now: '2026-11-13T15:00:00Z', run: { id: 'v08-restore', attempt: 1, trigger: 'restore', collector_commit: '0'.repeat(40) }, reason: 'test restore' });
    expect(r.outcome).toBe('published');
    expect(text(root, 'live/NOTICE.txt')).toBe(before);
    expect(text(root, 'live/NOTICE.txt')).toBe(text(root, `live/${json(root, 'live/manifest.json').rules.notice.path}`));
  });

  it('fails the gate when NOTICE.txt or the notice file is changed, or a registry version is dropped', async () => {
    const notice = await go(newRoot(), FIRST, data(), { faults: { breakStaged: (staged: Map<string, string>) => staged.set('NOTICE.txt', 'changed\n') } });
    expect(notice.outcome).toBe('gate-failed');
    expect(notice.problems).toContain('gate 9: NOTICE.txt does not equal the notice file the manifest names');
    const named = await go(newRoot(), FIRST, data(), {
      faults: {
        breakStaged: (staged: Map<string, string>) => {
          for (const k of [...staged.keys()]) if (k.startsWith('notices/')) staged.set(k, `${staged.get(k)}x`);
        },
      },
    });
    expect(named.outcome).toBe('gate-failed');
    expect(named.problems.some((p: string) => /^gate 3: rules notice: notices\/[0-9a-f]{16}\.txt does not match its hash$/.test(p))).toBe(true);
    const root = newRoot();
    await go(root, FIRST, data());
    const edited = structuredClone(inputs.registry);
    edited.sources.fiscaldata.terms_checked = '2026-11-21';
    const recs = [...inputs.effr, effrDay('2026-11-13')];
    const dropped = await go(root, '2026-11-16T14:17:00Z', data(recs), {
      registry: edited,
      faults: {
        breakStaged: (staged: Map<string, string>) => {
          const m = JSON.parse(staged.get('manifest.json')!);
          m.rules.registry_versions = [];
          staged.set('manifest.json', canonicalJson(m));
        },
      },
    });
    expect(dropped.outcome).toBe('gate-failed');
    expect(dropped.problems).toContain('gate 9: rules.registry_versions does not list exactly the other registry versions the window names');
  });
});

describe('the collector self-check (17.8 layer 2, I35)', () => {
  it('raises only the run keys, never the manifest findings', async () => {
    const root = newRoot();
    await go(root, FIRST, data());
    const m = json(root, 'live/manifest.json');
    // Long after the manifest's expected update: 14.3 would give manifest-overdue and a run gap.
    const late = '2026-11-20T14:17:00Z';
    const facts = { workflow: { state: 'active' }, repository: { pushed_at: '2026-11-13T00:00:00Z' }, runs: [{ event: 'schedule', conclusion: 'success', created_at: FIRST }], manifest: m };
    const r = await go(root, late, data(), { healthFacts: facts });
    const keys = r.alerts.map((a: Loose) => a.key);
    expect(keys).toContain('scheduled-run-gap');
    expect(keys).not.toContain('manifest-overdue');
    expect(keys.some((k: string) => k === 'series-stale' || k === 'series-held' || k === 'manifest-missing')).toBe(false);
  });
});

describe('the reason check (22.3 items 1 to 9)', () => {
  it('counts code points, refuses whole-word header names but not longer words, and refuses empty text', () => {
    const astral = '\u{1F600}';
    expect(textRefusal(astral.repeat(2000))).toBeNull();
    expect(textRefusal(astral.repeat(2001))).toBe('longer than 2000 characters');
    expect(textRefusal('owner authorization P56')).toBe('a header name');
    expect(textRefusal('authorized by the owner on 2026-11-20')).toBeNull();
    expect(textRefusal('')).toBe('empty text');
    expect(textRefusal('why? because the source said so & we agreed')).toBeNull();
    expect(textRefusal('see https://example.com/a')).toBe('a URL with a path');
    expect(textRefusal('mail a@b.co')).toBe('an email address');
    expect(textRefusal(`hash sha256:${'a'.repeat(64)} is fine`)).toBeNull();
  });
});
