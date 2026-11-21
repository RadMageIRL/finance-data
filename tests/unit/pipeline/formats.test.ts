// The published file formats (DATA_CONVENTIONS v0.1 sections 5 to 10): the JSON Schema subset
// validator, canonical JSON and content addresses (checked against a vector computed with
// Python's json module, not this code), the date-bounded source record schemas on records copied
// from saved provider responses, and the example published tree's schemas and closure.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';
import { canonicalJson, objectAddress, sha256Hex } from '../../../pipeline/lib/canonical.mjs';
import { validate } from '../../../pipeline/lib/json-schema.mjs';
import { checkRecord, decimalFromNumber } from '../../../pipeline/lib/source-records.mjs';

const json = (p: string) => JSON.parse(readFileSync(p, 'utf8'));
const schemas = Object.fromEntries(['object', 'snapshot', 'manifest', 'manifest-v3', 'revisions', 'runs'].map((n) => [n, json(`pipeline/schemas/${n}.schema.json`)]));
const sources = json('pipeline/schemas/source-records.json');
const TREE = 'pipeline/fixtures/tree';

describe('JSON Schema subset', () => {
  const s = {
    $defs: { d: { type: 'string', pattern: '^\\d{4}$' } },
    type: 'object',
    additionalProperties: false,
    required: ['a'],
    properties: {
      a: { $ref: '#/$defs/d' },
      b: { type: ['integer', 'null'], minimum: 1 },
      c: { oneOf: [{ type: 'string' }, { type: 'string', minLength: 3 }] },
      d: { anyOf: [{ const: 1 }, { enum: ['x', 'y'] }] },
      e: { type: 'array', items: { type: 'number' }, maxItems: 2 },
    },
  };

  it('accepts what matches and names every problem otherwise', () => {
    expect(validate(s, { a: '2026', b: null, c: 'ab', d: 'y', e: [1, 2.5] })).toEqual([]);
    expect(validate(s, { a: '26', b: 0, c: 'abcd', d: 2, e: [1, 2, 3], f: true })).toEqual([
      '$.a: does not match ^\\d{4}$',
      '$.b: less than 1',
      '$.c: matches 2 of oneOf (exactly 1 required)',
      '$.d: matches none of anyOf',
      '$.e: more than 2 items',
      '$: unknown property f',
    ]);
    expect(validate(s, { b: 1.5 })).toEqual(['$: missing a', '$.b: expected integer or null, got number']);
  });

  it('refuses a schema keyword it does not implement instead of ignoring it', () => {
    expect(() => validate({ type: 'string', format: 'date' }, 'x')).toThrow(/unsupported schema keyword format/);
    expect(() => validate({ $ref: '#/definitions/x' }, 'x')).toThrow(/unsupported or unknown \$ref/);
  });
});

describe('canonical JSON and content addresses', () => {
  it('matches the vector computed independently with Python (sort_keys, compact separators, no ASCII escaping)', () => {
    const value = { series: 'effr', b: [1, 'x'], a: 'café "q" \\ \n\t\u0001', A: null, z: { y: true, x: false }, '\u{1F600}': 1, '\uFF5E': 2 };
    const text = canonicalJson(value);
    expect(text).toBe('{"A":null,"a":"café \\"q\\" \\\\ \\n\\t\\u0001","b":[1,"x"],"series":"effr","z":{"x":false,"y":true},"\uFF5E":2,"\u{1F600}":1}');
    expect(sha256Hex(text)).toBe('44aff3b5ac1e0229d6e02f1e06a4af5549a9e1da5299b5867dd6436d7b2d13d6');
  });

  it('refuses non-integer numbers and lone surrogates, and writes negative zero as 0', () => {
    expect(() => canonicalJson({ v: 3.88 })).toThrow(/not a safe integer/);
    expect(() => canonicalJson({ v: 2 ** 53 })).toThrow(/not a safe integer/);
    expect(() => canonicalJson({ v: 'a\uD800b' })).toThrow(/lone surrogate/);
    expect(canonicalJson({ v: -0 })).toBe('{"v":0}');
    // Characters other than the quote, the backslash and C0 controls are written as themselves.
    expect(canonicalJson('\u007F ﻿/')).toBe('"\u007F ﻿/"');
  });

  it('gives the same bytes and address whatever the key order, and a different one for any change', () => {
    const a = { schema: 'rmf.econ.object/1', series: 'effr', segment: '2026', observations: [] };
    const b = { observations: [], segment: '2026', series: 'effr', schema: 'rmf.econ.object/1' };
    expect(objectAddress(a)).toEqual(objectAddress(b));
    expect(objectAddress(a).path).toMatch(/^objects\/effr\/2026\/[0-9a-f]{16}\.json$/);
    expect(objectAddress({ ...a, segment: '2025' }).sha256).not.toBe(objectAddress(a).sha256);
  });
});

describe('source records, date-bounded', () => {
  const effr = json('pipeline/fixtures/sources/effr-excerpt.json').refRates;
  const dtp = json('pipeline/fixtures/sources/dtp-excerpt.json').data;

  it('accepts every saved EFFR record under the schema of its era, including the r flag and the one footnote', () => {
    const got = effr.map((r: { effectiveDate: string }) => [r.effectiveDate, checkRecord(sources, 'nyfed-markets', r)]);
    for (const [date, c] of got) expect(c.problems, date).toEqual([]);
    expect(Object.fromEntries(got.map(([d, c]: [string, { schema: string }]) => [d, c.schema]))).toEqual({
      '2000-07-03': 'effr-2000', '2000-07-10': 'effr-2000', '2003-07-18': 'effr-2000', '2003-07-20': 'effr-2000', '2003-07-21': 'effr-2000', '2008-10-29': 'effr-2000', '2008-12-15': 'effr-2000',
      '2008-12-16': 'effr-2008', '2016-02-29': 'effr-2008',
      '2016-03-01': 'effr-2016', '2023-07-25': 'effr-2016', '2026-09-16': 'effr-2016', '2026-09-17': 'effr-2016', '2026-11-12': 'effr-2016',
    });
    expect(effr.find((r: { effectiveDate: string }) => r.effectiveDate === '2000-07-10').revisionIndicator).toBe('r');
    expect(effr.find((r: { effectiveDate: string }) => r.effectiveDate === '2023-07-25').footnoteId).toBe(1);
  });

  it('accepts a 2016-era record without percentiles or volume (not published when the prior day\'s rate is republished)', () => {
    const r = { ...effr.find((x: { effectiveDate: string }) => x.effectiveDate === '2026-11-12') };
    for (const f of ['percentPercentile1', 'percentPercentile25', 'percentPercentile75', 'percentPercentile99', 'volumeInBillions']) delete r[f];
    expect(checkRecord(sources, 'nyfed-markets', r)).toEqual({ schema: 'effr-2016', problems: [] });
  });

  it('keeps the excerpt\'s numbers as the provider wrote them (6.50, not 6.5)', () => {
    const raw = readFileSync('pipeline/fixtures/sources/effr-excerpt.json', 'utf8');
    expect(raw).toContain('{ "effectiveDate": "2000-07-03", "type": "EFFR" ,"percentRate": 7.03 ,"targetRateFrom": 6.50');
    expect(raw).toContain('"percentPercentile99": 3.90 ,"targetRateFrom": 3.75 ,"targetRateTo": 4.00');
  });

  it('refuses a record with a field of another era, a missing field, an unknown field or a wrong type', () => {
    const at = (d: string) => ({ ...effr.find((r: { effectiveDate: string }) => r.effectiveDate === d) });
    const late = at('2008-12-15');
    late.targetRateTo = 0.25;
    expect(checkRecord(sources, 'nyfed-markets', late).problems).toEqual(['2008-12-15: unknown field targetRateTo (effr-2000)']);
    const missing = at('2026-11-12');
    delete missing.targetRateTo;
    expect(checkRecord(sources, 'nyfed-markets', missing).problems).toEqual(['2026-11-12: missing targetRateTo (effr-2016)']);
    const text = at('2026-11-12');
    text.percentRate = '3.88';
    expect(checkRecord(sources, 'nyfed-markets', text).problems).toEqual(['2026-11-12: percentRate not a JSON number (effr-2016)']);
    const flag = at('2026-11-12');
    flag.revisionIndicator = 'R';
    expect(checkRecord(sources, 'nyfed-markets', flag).problems[0]).toMatch(/revisionIndicator not one of/);
    expect(checkRecord(sources, 'nyfed-markets', { ...at('2026-11-12'), effectiveDate: '1999-12-31' }).problems).toEqual(['no schema in force on 1999-12-31']);
  });

  it('accepts every saved Debt to the Penny record, with "null" breakouts as absences', () => {
    for (const r of dtp) expect(checkRecord(sources, 'fiscaldata', r).problems, r.record_date).toEqual([]);
    const nulls = dtp.filter((r: { debt_held_public_amt: string }) => r.debt_held_public_amt === 'null').map((r: { record_date: string }) => r.record_date);
    // Breakouts are missing before 1997-09-30, on most days until 2005-03-30, and on the month end 2003-01-31.
    expect(nulls).toEqual(['1993-04-01', '1997-09-29', '2003-01-31', '2005-03-30']);
    const bad = { ...dtp[0], tot_pub_debt_out_amt: 'null' };
    expect(checkRecord(sources, 'fiscaldata', bad).problems).toEqual(['1993-04-01: tot_pub_debt_out_amt not a decimal string (dtp-1993)']);
  });

  it('keeps the two published inconsistencies as published', () => {
    const cents = (s: string) => BigInt(s.replace('.', ''));
    const gap = (d: string) => {
      const r = dtp.find((x: { record_date: string }) => x.record_date === d);
      return cents(r.debt_held_public_amt) + cents(r.intragov_hold_amt) - cents(r.tot_pub_debt_out_amt);
    };
    expect(gap('2011-02-01')).toBe(3n);
    expect(gap('2025-08-04')).toBe(1_000_000_000_000n);
    expect(gap('2026-11-12')).toBe(0n);
  });

  it('stores JSON numbers as decimal strings with the declared places, refusing extra precision', () => {
    expect(decimalFromNumber(3.9, 2)).toBe('3.90');
    expect(decimalFromNumber(0.25, 2)).toBe('0.25');
    expect(decimalFromNumber(-0.5, 2)).toBe('-0.50');
    expect(decimalFromNumber(99, 0)).toBe('99');
    expect(decimalFromNumber(7, 2)).toBe('7.00');
    expect(() => decimalFromNumber(3.885, 2)).toThrow(/more than 2 decimals/);
    expect(() => decimalFromNumber(1e21, 2)).toThrow(/exponent form refused/);
    expect(() => decimalFromNumber(1234567890123456, 0)).toThrow(/more than 15 significant digits/);
  });
});

describe('example published tree', () => {
  const files = (dir: string): string[] => readdirSync(dir).flatMap((n) => (statSync(join(dir, n)).isDirectory() ? files(join(dir, n)) : [join(dir, n)]));
  const tree = Object.fromEntries(files(TREE).map((p) => [relative(TREE, p).split('\\').join('/'), readFileSync(p, 'utf8')]));

  it('has only files with extensions, and every JSON file in canonical form valid against its schema', () => {
    for (const path of Object.keys(tree)) expect(path, path).toMatch(/\.(json|csv)$/);
    const kind = (p: string) => (p === 'manifest.json' ? 'manifest' : p.startsWith('snapshots/') ? 'snapshot' : p.startsWith('objects/') ? 'object' : p.startsWith('revisions/') ? 'revisions' : p === 'status/runs.json' ? 'runs' : null);
    for (const [path, text] of Object.entries(tree)) {
      if (!path.endsWith('.json')) continue;
      const k = kind(path);
      expect(k, path).not.toBeNull();
      // The committed example tree predates v0.8: its manifest/3 keeps its own schema (I31, I41).
      const value = JSON.parse(text);
      const schema = k === 'manifest' && value.schema === 'rmf.econ.manifest/3' ? schemas['manifest-v3'] : schemas[k!];
      expect(validate(schema, value), path).toEqual([]);
      expect(canonicalJson(JSON.parse(text)), path).toBe(text);
    }
  });

  it('is closed: the manifest, the snapshot and the objects name only files that exist, with matching hashes', () => {
    const manifest = JSON.parse(tree['manifest.json']!);
    const named: { path: string; sha256: string }[] = [manifest.snapshot];
    for (const s of Object.values(manifest.series) as { objects: { path: string; sha256: string }[]; csvs: { path: string; sha256: string }[]; revisions: { path: string; sha256: string }[] }[]) named.push(...s.objects, ...s.csvs, ...s.revisions);
    // Every file the manifest names is content-addressed, so a cached manifest never names a changed file.
    for (const ref of named.slice(1)) expect(ref.path).toMatch(new RegExp(`/${ref.sha256.slice(0, 16)}\\.(json|csv)$`));
    const snapshot = JSON.parse(tree[manifest.snapshot.path]!);
    for (const s of Object.values(snapshot.series) as { objects: { path: string; sha256: string; bytes: number }[] }[]) {
      for (const o of s.objects) {
        named.push(o);
        expect(Buffer.byteLength(tree[o.path] ?? '', 'utf8'), o.path).toBe(o.bytes);
        // An object's path is its own address.
        expect(objectAddress(JSON.parse(tree[o.path]!)).path).toBe(o.path);
      }
    }
    for (const ref of named) {
      expect(tree[ref.path], ref.path).toBeDefined();
      expect(sha256Hex(tree[ref.path]!), ref.path).toBe(ref.sha256);
    }
    // The manifest's summary agrees with the snapshot.
    for (const [id, s] of Object.entries(manifest.series) as [string, { last_period: string; objects: { path: string }[] }][]) {
      expect(s.last_period).toBe(snapshot.series[id].last_period);
      expect(s.objects.map((o) => o.path)).toEqual(snapshot.series[id].objects.map((o: { path: string }) => o.path));
    }
  });

  it('stores the FOMC target as change points: a rate before December 16, 2008, a range after, none invented', () => {
    const snapshot = JSON.parse(tree['snapshots/20261116T141700Z.json']!);
    const target = JSON.parse(tree[snapshot.series['fomc-target'].objects[0].path]!).observations;
    expect(target).toHaveLength(73);
    expect(target[0]).toEqual({ effective: '2000-07-03', kind: 'rate', value: '6.50', starts_before_data: true, released: { date: null, basis: 'not-recorded' } });
    expect(target.filter((p: { kind: string }) => p.kind === 'rate').every((p: { effective: string }) => p.effective < '2008-12-16')).toBe(true);
    expect(target.find((p: { kind: string }) => p.kind === 'range').effective).toBe('2008-12-16');
    expect(target.at(-1)).toEqual({ effective: '2026-09-17', kind: 'range', lower: '3.75', upper: '4.00', released: { date: null, basis: 'not-recorded' } });
    expect(target.slice(1).some((p: { starts_before_data?: boolean }) => p.starts_before_data)).toBe(false);
  });

  it('lists every registered series in the snapshot and the manifest, unpublished ones as not-yet-published', () => {
    const registry = json('pipeline/registry/econ.json');
    const ids = registry.series.map((s: { id: string }) => s.id).sort();
    const snapshot = JSON.parse(tree['snapshots/20261116T141700Z.json']!);
    const manifest = JSON.parse(tree['manifest.json']!);
    expect(Object.keys(snapshot.series).sort()).toEqual(ids);
    expect(Object.keys(manifest.series).sort()).toEqual(ids);
    const waiting = ids.filter((id: string) => snapshot.series[id].status === 'not-yet-published');
    expect(waiting).toEqual(['debt-held-public', 'debt-intragov', 'debt-total', 'm1-nsa', 'm1-sa', 'm2-nsa', 'm2-sa']);
    for (const id of waiting) {
      expect(snapshot.series[id]).toMatchObject({ objects: [], last_period: null, observation_count: 0, retrieved_at: null });
      expect(manifest.series[id]).toMatchObject({ objects: [], csvs: [], status: 'not-yet-published' });
    }
    // The snapshot keeps the registry's notices as written; the manifest fills them for display.
    expect(snapshot.notices['nyfed-markets'].notice).toBe(registry.sources['nyfed-markets'].notice);
    expect(manifest.series.effr.notice).toContain('The Effective Federal Funds Rate (EFFR) is subject to the Terms of Use posted at newyorkfed.org.');
    expect(manifest.series['fomc-target'].last_range).toEqual({ lower: '3.75', upper: '4.00' });
  });

  it('every CSV carries the title, the attribution, the notice, the terms and, for derived data, the label', () => {
    const manifest = JSON.parse(tree['manifest.json']!);
    const effr = tree[manifest.series.effr.csvs[0].path]!;
    const target = tree[manifest.series['fomc-target'].csvs[0].path]!;
    expect(effr).toContain('# Segment 2026: 2026-11-09 to 2026-11-12.');
    for (const text of [effr, target]) {
      expect(text).toContain('# © 2026 Federal Reserve Bank of New York. Content from the New York Fed subject to the Terms of Use at newyorkfed.org.');
      expect(text).toContain('does not sanction or endorse any particular republication, and has no liability for your use.');
      expect(text).toContain('# Terms: https://www.newyorkfed.org/termsofuse');
    }
    expect(target).toContain('# Derived by RadMage Finance from the New York Fed');
    expect(effr).not.toContain('Derived by RadMage Finance');
    expect(effr.split('\n').find((l) => l.startsWith('2026-11-12'))).toBe('2026-11-12,3.88,2026-11-13,rule');
  });

  it('dates releases only where a source states them: by rule from rule_valid_from, never before', () => {
    const snapshot = JSON.parse(tree['snapshots/20261116T141700Z.json']!);
    const effr = JSON.parse(tree[snapshot.series.effr.objects[0].path]!).observations;
    // 2026-11-11 is a holiday (Veterans Day), so the rate for 2026-11-10 is published on 2026-11-12.
    expect(effr.map((o: { period: string; released: unknown }) => [o.period, o.released])).toEqual([
      ['2026-11-09', { date: '2026-11-10', basis: 'rule' }],
      ['2026-11-10', { date: '2026-11-12', basis: 'rule' }],
      ['2026-11-12', { date: '2026-11-13', basis: 'rule' }],
    ]);
    // Every change point predates the rule's valid-from date (2026-10-05), so none has a date.
    const target = JSON.parse(tree[snapshot.series['fomc-target'].objects[0].path]!).observations;
    expect(target.every((p: { released: { basis: string } }) => p.released.basis === 'not-recorded')).toBe(true);
  });

  it('a changed byte anywhere breaks the address check', () => {
    const snapshot = JSON.parse(tree['snapshots/20261116T141700Z.json']!);
    const ref = snapshot.series.effr.objects[0];
    const tampered = tree[ref.path]!.replace('"3.88"', '"3.89"');
    expect(tampered).not.toBe(tree[ref.path]);
    expect(sha256Hex(tampered)).not.toBe(ref.sha256);
  });
});
