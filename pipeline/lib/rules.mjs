// The rule files of a manifest (DATA_CONVENTIONS 22.9, v0.8; decision D8): canonical copies of
// the registry versions the window's snapshots name (the current registry and the earlier
// versions that appendix I row I7 derives from it), the holiday table in use, and the notice
// file, with its convenience copy `NOTICE.txt`. Pure functions: bytes depend only on the arguments.
import { canonicalJson, sha256Hex } from './canonical.mjs';
import { etDate } from './calendar.mjs';

/** The L1 statement (owner decision P56), exactly this one line of the notice file. */
export const L1_STATEMENT = 'RadMage Finance dedicates to the public domain under CC0 1.0 Universal (https://creativecommons.org/publicdomain/zero/1.0/) only these original contributions of its own: the run, publication and deployment records in status/, and the status, freshness, deadline and timing fields it adds to these files. Nothing else is designated. The data from each provider, including values derived from it, stays under that provider\'s terms above; RadMage Finance claims no ownership of it and grants no license to it. The software that produces these files is licensed separately.';

/** The New York Fed terms address before v0.8 (22.9, I7). */
export const V07_NYFED_TERMS = 'https://www.newyorkfed.org/termsofuse';
const V07_TERMS_CHECKED = '2026-11-16';

const fillText = (text, values) => text.replace(/\{([a-z_]+)\}/g, (_, k) => values[k]);
const ref = (path, text) => ({ path, sha256: sha256Hex(text) });

/**
 * Every registry version this registry can stand for (I7), newest first: the registry itself,
 * and for v0.8 the v0.7 registry (the three v0.8 substitutions reversed) and the v0.6 registry
 * (v0.7 with `conventions` v0.6, 21.1). Each is { version, registry, text, sha256 }.
 */
export function registryVersions(registry) {
  const entry = (r) => {
    const text = canonicalJson(r);
    return { version: r.conventions, registry: r, text, sha256: sha256Hex(text) };
  };
  const out = [entry(registry)];
  if (registry.conventions === 'v0.8') {
    const v07 = structuredClone(registry);
    v07.conventions = 'v0.7';
    v07.sources['nyfed-markets'].terms_url = V07_NYFED_TERMS;
    for (const s of Object.values(v07.sources)) s.terms_checked = V07_TERMS_CHECKED;
    out.push(entry(v07));
    const v06 = structuredClone(v07);
    v06.conventions = 'v0.6';
    out.push(entry(v06));
  }
  return out;
}

/** The registry version whose canonical hash is `sha256`, or null when none can be derived. */
export function registryVersionOf(registry, sha256) {
  return registryVersions(registry).find((v) => v.sha256 === sha256) ?? null;
}

/** The copy file of a registry version: `registry/econ-<16 hex>.json`. */
export const registryCopyPath = (sha256) => `registry/econ-${sha256.slice(0, 16)}.json`;

/** The holiday copy: `registry/holidays-<16 hex>.json`, the canonical JSON of the table in use. */
export function holidayCopy(holidays) {
  const text = canonicalJson(holidays);
  const sha256 = sha256Hex(text);
  return { path: `registry/holidays-${sha256.slice(0, 16)}.json`, sha256, text };
}

/**
 * The notice file (22.9): sources in byte order of their ids, a blank line after each; per
 * source its publisher, attribution, notice (if not null), license sentence and terms line;
 * then the L1 statement. `{year}` is the ET year of `generatedAt`. A line holding `{data_name}`
 * is written once per series of the source in registry order; a filled line identical to one
 * already written for the same source is not repeated.
 */
export function noticeText(registry, generatedAt) {
  const year = etDate(generatedAt).slice(0, 4);
  const lines = [];
  for (const id of Object.keys(registry.sources).sort()) {
    const src = registry.sources[id];
    const series = registry.series.filter((s) => s.source === id);
    const seen = new Set();
    const add = (line) => {
      if (!seen.has(line)) {
        seen.add(line);
        lines.push(line);
      }
    };
    const placeholders = (text) => {
      if (text.includes('{data_name}')) for (const s of series) add(fillText(text, { year, data_name: s.data_name }));
      else add(fillText(text, { year }));
    };
    add(src.publisher);
    placeholders(src.attribution);
    if (src.notice !== null && src.notice !== undefined) placeholders(src.notice);
    add(src.license);
    add(`Terms: ${src.terms_url}`);
    lines.push('');
  }
  lines.push(L1_STATEMENT);
  return `${lines.join('\n')}\n`;
}

/**
 * The rule files of a manifest written at `generatedAt` by a run with `registry` and
 * `holidays`, for the registry hashes the window's snapshots name. An earlier registry version
 * is the archived copy that an earlier v0.8 run wrote (`archivedRegistry(sha256)` returns its
 * text or null; every run that writes a manifest archives its own registry), or, for snapshots
 * written before v0.8, the version that I7 derives (22.9, I44). Returns { files: Map(path ->
 * text), rules (the manifest's `rules`), notice (the text of NOTICE.txt) }. Throws when a window
 * snapshot names a registry version found neither way.
 */
export function ruleFiles({ registry, holidays, generatedAt, windowRegistryHashes, archivedRegistry = () => null }) {
  const files = new Map();
  const versions = registryVersions(registry);
  const own = versions[0];
  files.set(registryCopyPath(own.sha256), own.text);
  const others = [];
  for (const h of [...new Set(windowRegistryHashes)].sort()) {
    if (h === own.sha256) continue;
    let text = versions.find((x) => x.sha256 === h)?.text ?? null;
    if (text === null) {
      const archived = archivedRegistry(h);
      if (archived !== null && sha256Hex(archived) === h) text = archived;
    }
    if (text === null) throw new Error(`a window snapshot names the registry ${h}, which is neither archived nor a version of appendix I row I7`);
    files.set(registryCopyPath(h), text);
    others.push(ref(registryCopyPath(h), text));
  }
  const hol = holidayCopy(holidays);
  files.set(hol.path, hol.text);
  const notice = noticeText(registry, generatedAt);
  const noticeSha = sha256Hex(notice);
  const noticePath = `notices/${noticeSha.slice(0, 16)}.txt`;
  files.set(noticePath, notice);
  return {
    files,
    notice,
    rules: {
      registry: ref(registryCopyPath(own.sha256), own.text),
      holidays: { path: hol.path, sha256: hol.sha256 },
      notice: { path: noticePath, sha256: noticeSha },
      registry_versions: others.sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0)),
    },
  };
}
