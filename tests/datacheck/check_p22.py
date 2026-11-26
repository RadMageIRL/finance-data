#!/usr/bin/env python3
"""Independent checker for docs/DATA_CONVENTIONS.md v0.8 (RadMage Finance, P2.2 to P2.6, Stages B to D).

Written from the spec text, pipeline/schemas/, pipeline/registry/econ.json,
pipeline/fixtures/ and the saved provider responses and pages under local/research/
(p21/raw, p23/raw, p24/*/raw, p25/*) only, never from the pipeline implementation. Python
standard library only. Where the text and a schema or fixture disagree, the text is
implemented (DATA_CONVENTIONS, preamble).

v0.4 additions (appendix C): CSV segments (T57, T87 to T93), review authorization and
refusals (T94 to T97), the five kinds of absent data (T98, T99, T23), unknown publication
zones and the next unseen period (C2, T100), route notices (R28, C3, T101), held windowed
candidates (T102), registry/2 and the v0.4 schemas (R2, R3, R10, R27, S2).

v0.5 additions (appendix D): locks of origin rejected and rolled-back recomputed from the
published state (C4, T85, T105 to T112), the clear decision (T94 to T96, T81, T108),
rollback.locked (T107, T52), the new schema ids (S2, S4, T35), missing versus zero
(R29, F28, SR1, SR6, SR11, T113), client identification (R6, F29), and the 22 steps of
appendix B (T84, T103, T104, T114).

v0.6 additions (appendix E): rejected locks count new periods, several locks per series, each
lifting by its own rule, a rollback keeping every rejection lock (C5, T85, T105, T107, T108,
T109, T115), the window rule for locks (T102, T112), accepted_zeros (R30, C6, S5, SR1, T113),
rollback records in archive/rollbacks/ (T115, T31, T34, T35), review-queue/4 with one entry
per lock (T69, T109), the state descriptor (S5), the changed rows 16, 18 and 20 of appendix B
(T84, T114), and the comparison mode of section 20.4 (compare_saved.py beside this file).

v0.7 additions (appendix F): the four-hour schedule and the run-gap thresholds (C7, T19, T55),
the weekly full fetch once per group per Sunday and collector.json full_fetches (C8, T100,
T102, T116), the twelve response record fields (C9, S6, compare_saved.py), the new schemas
state/2, accepted/1 and collection/1 (S6), the conventions value (R2), LF only and the "line
endings converted" diagnosis (T117), the alert keys of 17.8 (T118), the live root mode of 21.3,
the state store mode (20.3, 21.1, 21.2, 21.4) and the appendix G scenario mode (check_state.py
beside this file).

v0.8 additions (appendix I): the registry changes and the I7 derivation of the v0.7 and v0.6
registries (R2, R31, C13, T46, T9); the first v0.8 run and the transition rules of 22.9 for files
written under v0.7 (T119, T46, the New York Fed terms line in T17, T57 and T92); manifest/4 with
deadline, stale_at, revision_csvs and rules, its shape built from the text (S7, T35, T120); the
revision CSVs of 10 (T37, T121, C15); the rule files, the notice file with the CC0 statement and
NOTICE.txt (T122, T123, T33, T62, T63, T117, C15); the window with the rule files (T66 to T68);
the D6 reason check (T124, C14); the v0.8 alert keys (T70, T125); state/deployments.json (ST6,
ST20 in check_state.py); and, in check_publication.py beside this file, the publication mode (V2c
checks 1 to 11 of 22.5, P0 to P11), the release mode of 22.8 (RL1 to RL5), the release history of
22.7 (RH1), the appendix J mode (J0 to J6) and the self-tests C10 to C18 (the compare-and-swap and
monotonic decision, D5.5, the archive format, the reason check, the deployment log, its chain of
releases and the release history, the deployed state and the pages run name). --registry <file> replaces the committed registry, for
the self-tests only.

Run from the repository root:

    python -I tests/datacheck/check_p22.py
    python -I tests/datacheck/check_p22.py --root <dir> [--live]
    python -I tests/datacheck/check_p22.py --state <store dir>
    python -I tests/datacheck/check_p22.py --state-scenario <dir>
    python -I tests/datacheck/check_p22.py --compare-saved <collection dir> [--compare-out <file.json>]
    python -I tests/datacheck/check_p22.py --publication <econ dir or artifact.tar.gz> --state <store dir> [--previous-release <release dir>]
    python -I tests/datacheck/check_p22.py --release <release dir> [--expect <snapshot>:<sha256>] [--previous-release <release dir>]
    python -I tests/datacheck/check_p22.py --release-history <folder of release folders> [--deployed <deployed status/deployments.json>]
    python -I tests/datacheck/check_p22.py --publication-scenario <dir>

With --root the pipeline root <dir> (section 17.1: live/, archive/files/,
archive/manifests/, archive/holds/, archive/state/) is verified in addition to the
checks above; those checks have ids T30 and up.

With --root <dir> --live (21.3) the root is a live root, not the scenario: every root check
runs except the four that follow the table of appendix B (T84, T103, T104, T114), and of the
plain checks only those the root checks rest on (the C self-tests, the S schema checks other
than S1 on the example tree, the R registry checks and the H holiday checks); the example
tree (T1 to T29), the collector fixtures (SR), the source fixtures and the saved evidence (F)
are not read. 21.1 (v0.7, F10): when the root's archive/state/ holds accepted.json (a working
root, 21.3), the manifests and snapshots whose time is not after the promoted snapshot's, and
collector.json until a v0.7 run rewrites it, are read by exactly three v0.6 rules: T46 (the
registry hash with conventions v0.6), T55 (the v0.6 cron lines) and T116 (no full_fetches).
Without accepted.json every rule is strict.

With --state <store dir> the private state store is verified: the Stage B layout of 20.3
(STATE.json rmf.econ.state/1) or the v0.7 layout of 21.1, 21.2 and 21.4 (rmf.econ.state/2),
including its root in live mode. With --state-scenario <dir>, <dir>/steps.json and
<dir>/store are checked against appendix G, then the store in state mode. These checks have
ids ST1 and up, and G0 and up.

Prints one line per check: PASS, FAIL with a reason, or SKIP when a saved raw file is
absent (local/ is not committed). Exits non-zero if any check fails.

Raw provider files are untrusted data: they are parsed as data only, never executed.
XML is refused if it declares a DTD or an entity; xml.etree never fetches external
resources.

"guessed" in a check name marks a reading the text does not state outright; "reading:"
in a comment marks the same next to the rule.
"""

import calendar
import csv as csv_lib
import datetime as dt
import decimal
import gzip
import hashlib
import html as html_lib
import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

try:
    sys.stdout.reconfigure(errors="backslashreplace")
except Exception:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parents[2]
TREE = ROOT / "pipeline" / "fixtures" / "tree"
SCHEMA_DIR = ROOT / "pipeline" / "schemas"
REGISTRY = ROOT / "pipeline" / "registry" / "econ.json"
SOURCE_FIXTURES = ROOT / "pipeline" / "fixtures" / "sources"
RAW = ROOT / "local" / "research" / "p21" / "raw" / "fed-treasury"
RAW_EFFR = RAW / "nyfed_effr_search_full_2000-07-01_2026-11-16.json"
RAW_EFFR_HEADERS = RAW / "nyfed_effr_full_head.txt"
RAW_EFFR_EARLY = RAW / "nyfed_effr_search_1990-01-01_2000-07-10.json"
RAW_DTP = RAW / "fiscaldata_dtp_full_pagesize10000.json"
RAW_DTP_HEADERS = RAW / "fiscaldata_dtp_full_pagesize10000_headers.txt"
RAW_DTP_10001_HEADERS = RAW / "fiscaldata_dtp_pagesize10001_headers.txt"
RAW_H6_ZIP = RAW / "h6_zip" / "FRB_h6_xml.zip"
RAW_H6_DATES = RAW / "frb_h6_releaseDates.json"
RAW_H6_DATES_HEADERS = RAW / "frb_h6_releaseDates_headers.txt"
RAW_FD_CAL = RAW / "fiscaldata_calendar_release.json"
RAW_FD_CAL_HEADERS = RAW / "fiscaldata_calendar_release_headers.txt"
RAW_TERMS = {
    "nyfed-markets": RAW / "nyfed_termsofuse.htm",
    "fiscaldata": RAW / "fiscaldata_api_documentation.htm",
    "frb-releases": RAW / "frb_disclaimer.htm",
}
RAW_PAGES = {
    "nyfed-addl": RAW / "nyfed_refrates_addl_info.htm",
    "nyfed-terms": RAW / "nyfed_termsofuse.htm",
    "dtp-dataset": RAW / "fiscaldata_dataset_debt-to-the-penny.htm",
    "h6-landing": RAW / "frb_h6_landing.htm",
    "ddp-faq": RAW / "frb_ddp_retirement_faq.htm",
}
P24_H6 = ROOT / "local" / "research" / "p24" / "h6" / "raw"
P24_FD = ROOT / "local" / "research" / "p24" / "fiscaldata" / "raw"
RAW_PAGES_V04 = {
    "h6-20260324": P24_H6 / "https___www.federalreserve.gov_releases_h6_20260324_",
    "ddp-retirement-faq": P24_H6 / "https___www.federalreserve.gov_data_ddp-retirement-frequently-asked-questions.htm",
    "ddp-fred-info": P24_H6 / "https___www.federalreserve.gov_data_data-download-fred-information.htm",
}
RAW_FD_CATALOG = P24_FD / "treasury_jsonfiles_data.json"
RAW_FD_DATASET_PAGEDATA = P24_FD / "pagedata_datasets_debt-to-the-penny.json"

UTC = dt.timezone.utc
D = decimal.Decimal
SAFE_INT = 2 ** 53 - 1

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

COUNTS = {"PASS": 0, "FAIL": 0, "SKIP": 0}
ROOT_MODE = False  # set by --root
LIVE_MODE = False  # set by --live, --state and --state-scenario (21.3: a live root is not the scenario)
CONVENTIONS = "v0.8"  # 4.1: the version of the text the registry was written for (v0.8, 22.9)
V07_CONVENTIONS = "v0.7"  # I7: the registry version before v0.8
LEGACY_CONVENTIONS = "v0.6"  # the version a Stage B root was written under (see LEGACY in section_root)
REGISTRY_SCHEMA = "rmf.econ.registry/4"  # 4.1 (v0.6, appendix E8; unchanged in v0.7)
SCHEMA_IDS = {  # 8, 9, 14.1, 17.5, 4.1, 20.3, 21.1, 21.2, 21.4 (v0.7, appendix F9)
    "registry": "rmf.econ.registry/4", "snapshot": "rmf.econ.snapshot/2", "manifest": "rmf.econ.manifest/3",
    "runs": "rmf.econ.runs/2", "review": "rmf.econ.review/3", "review-queue": "rmf.econ.review-queue/4",
    "rollback": "rmf.econ.rollback/1", "state": "rmf.econ.state/1",
    "state-v2": "rmf.econ.state/2", "accepted": "rmf.econ.accepted/1", "collection": "rmf.econ.collection/1"}
# v0.7 (appendix F)
SCHEDULE_LINES = ["17 */4 * * *"]  # 14.2, 21.3 (F7): the one cron line in force for Stage C
SCHEDULE_LINES_V06 = ["17 * * * 1-5", "17 15 * * 0,6"]  # decision P8, in force before v0.7
SCHEDULE_UTC_TIMES = ("00:17", "04:17", "08:17", "12:17", "16:17", "20:17")  # 14.2 lists them
RUN_GAP_WARNING_HOURS, RUN_GAP_CRITICAL_HOURS = 9, 26  # 14.3 (F7): it was 26 and 50
GITATTRIBUTES = b"* -text\n"  # 21.2: exactly these 8 bytes
# v0.8 (appendix I)
MANIFEST_V4 = "rmf.econ.manifest/4"  # 9 (I2); no schema file exists, the shape is built from the text (build_v08_shapes)
DEPLOYMENTS_ID = "rmf.econ.deployments/1"  # 22.4; no schema file exists either
NYFED = "nyfed-markets"
NYFED_TERMS_V07 = "https://www.newyorkfed.org/termsofuse"  # I7: the v0.7 value
NYFED_TERMS_V08 = "https://www.newyorkfed.org/privacy/termsofuse"  # 22.9: the v0.8 value
TERMS_CHECKED_V07, TERMS_CHECKED_V08 = "2026-11-16", "2026-11-20"  # I7, 22.9
NOTICE_STATEMENT = ("RadMage Finance dedicates to the public domain under CC0 1.0 Universal (https://creativecommons.org/publicdomain/zero/1.0/) "
                    "only these original contributions of its own: the run, publication and deployment records in status/, and the status, "
                    "freshness, deadline and timing fields it adds to these files. Nothing else is designated. The data from each provider, "
                    "including values derived from it, stays under that provider's terms above; RadMage Finance claims no ownership of it and "
                    "grants no license to it. The software that produces these files is licensed separately.")  # 22.9 (brief O), exactly one line
NOT_COLLECTION_KEYS = {"publish-failed": "publish.yml report", "publication-verify-failed": "publish.yml report", "manifest-missing": "the watcher",
                       "manifest-overdue": "the watcher", "publication-history-changed": "the watcher"}  # 22.6 table, 21.5 v0.8
PUBLICATION_ALERT_KEYS = ("publish-failed", "publication-verify-failed", "publication-behind", "publication-facts-unavailable", "publication-history-changed")  # 17.8 v0.8
RESPONSE_FIELDS = ("n", "host", "url", "requested_at", "status", "content_type", "content_length", "etag",
                   "last_modified", "date", "bytes", "sha256")  # 20.2 (F1): exactly twelve, each always present
RESPONSE_INT_FIELDS = ("n", "status", "bytes")  # 20.2: integers; the others text
RESPONSE_HEADER_FIELDS = ("content_type", "content_length", "etag", "last_modified", "date")  # text or null
STATE_BUDGET_WARNING, STATE_BUDGET_CRITICAL = 50_000_000, 100_000_000  # 21.4
FD_DEFAULT_TIME = "21:15"  # 17.3: Fiscal Data's time when no calendar entry has been collected (zone unknown, 4.5)
REVIEW_PERMISSIONS_ALL = ("admin", "maintain", "write", "triage", "read", "none")  # 11.5
# 17.5 (v0.5): the refusal rules, each list in the order it is checked.
REFUSAL_RULES = ("not-held", "stale-candidate", "bad-decision", "locked", "missing-text", "permission", "permission-time", "automation")
CLEAR_REFUSAL_RULES = ("not-locked", "stale-candidate", "missing-text", "permission", "permission-time", "automation")
ALL_REFUSAL_RULES = ("not-held", "not-locked", "stale-candidate", "bad-decision", "locked", "missing-text", "permission", "permission-time", "automation")
LOCK_ORIGINS = ("rejected", "rolled-back")  # 8, 11.5
USER_AGENT = "RadMage Finance (+https://radmagelabs.com/finance/)"  # 4.3, 18 (owner brief item 5)
PROJECT_CONTACT = "radmageirl@radmagelabs.com"  # 4.3: the only address a From header may carry
DEBT_SERIES = ("debt-total", "debt-held-public", "debt-intragov")  # 2.3: the three series with refuse_zero
ABSENCE_KINDS = {  # 11.6: detail to kind
    "holiday": "expected-nonpublication", "not-yet-due": "expected-nonpublication", "known-gap": "documented-gap",
    "fetch-failed": "collection-failure", "response-invalid": "collection-failure", "after-deadline": "source-overdue",
    "inside-history": "undocumented-gap"}
PERMISSION_WINDOW_SECONDS = 3600  # 11.5


def emit(status, name, detail=""):
    COUNTS[status] += 1
    if not detail:
        print(f"{status} {name}")
    elif status == "PASS":
        print(f"{status} {name} ({detail})")
    else:
        print(f"{status} {name}: {detail}")


def check(name, problems, ok_detail=""):
    """problems: a list of strings (empty means PASS) or a bool (True means PASS)."""
    if isinstance(problems, bool):
        problems = [] if problems else ["condition not met"]
    if problems:
        shown = "; ".join(str(p) for p in problems[:8])
        if len(problems) > 8:
            shown += f"; and {len(problems) - 8} more"
        emit("FAIL", name, shown)
        return False
    emit("PASS", name, ok_detail)
    return True


def skip(name, why):
    emit("SKIP", name, why)


def guarded(label, fn, *args):
    try:
        fn(*args)
    except Exception as exc:  # a crash in a section is a failure, never a silent pass
        emit("FAIL", f"{label} (section aborted)", f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Strict JSON (tree files) and number-preserving JSON (provider responses)
# ---------------------------------------------------------------------------


class StrictJsonError(ValueError):
    pass


def _pairs_no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise StrictJsonError(f"duplicate key {k!r}")
        out[k] = v
    return out


def _no_float(text):
    raise StrictJsonError(f"non-integer JSON number {text} (decimals must be strings)")


def _no_const(text):
    raise StrictJsonError(f"non-standard JSON constant {text}")


def load_strict(data):
    if data.startswith(b"\xef\xbb\xbf"):
        raise StrictJsonError("byte order mark")
    text = data.decode("utf-8")
    return json.loads(text, object_pairs_hook=_pairs_no_dupes, parse_float=_no_float, parse_constant=_no_const)


class Num(str):
    """The exact text of a JSON number as received (never converted to binary float)."""


def load_numtext(data):
    if data.startswith(b"\xef\xbb\xbf"):
        raise StrictJsonError("byte order mark")
    return json.loads(data.decode("utf-8"), object_pairs_hook=_pairs_no_dupes,
                      parse_float=Num, parse_int=Num, parse_constant=_no_const)


# ---------------------------------------------------------------------------
# Canonical JSON (section 7), my own implementation
# ---------------------------------------------------------------------------

_BS = chr(0x5C)
_SHORT_ESCAPES = {'"': _BS + '"', _BS: _BS + _BS, chr(8): _BS + "b", chr(9): _BS + "t",
                  chr(10): _BS + "n", chr(12): _BS + "f", chr(13): _BS + "r"}


def canon_str(s):
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch in _SHORT_ESCAPES:
            out.append(_SHORT_ESCAPES[ch])
        elif o < 0x20:
            out.append(_BS + "u%04x" % o)
        elif 0xD800 <= o <= 0xDFFF:
            raise ValueError("lone surrogate refused")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def canon_text(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        if abs(v) > SAFE_INT:
            raise ValueError(f"integer {v} outside the safe range")
        return str(v)
    if isinstance(v, str):
        return canon_str(v)
    if isinstance(v, list):
        return "[" + ",".join(canon_text(x) for x in v) + "]"
    if isinstance(v, dict):
        # Python compares str by code point, which is what section 7 asks for.
        return "{" + ",".join(canon_str(k) + ":" + canon_text(v[k]) for k in sorted(v)) + "}"
    raise ValueError(f"a {type(v).__name__} has no canonical form (integers only)")


def canon_bytes(v):
    return canon_text(v).encode("utf-8")


def sha256_hex(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------
# Minimal JSON Schema validator for the keywords these schema files use
# ---------------------------------------------------------------------------

SUPPORTED_KEYWORDS = {
    "type", "const", "enum", "pattern", "minLength", "maxLength", "minimum", "maximum",
    "required", "properties", "patternProperties", "additionalProperties", "minProperties",
    "items", "minItems", "maxItems", "anyOf", "oneOf", "$ref", "not",
}
ANNOTATION_KEYWORDS = {"$schema", "$id", "title", "description", "$defs"}


class SchemaKeywordError(Exception):
    pass


def collect_keywords(s, acc):
    if isinstance(s, bool):
        return
    if not isinstance(s, dict):
        raise SchemaKeywordError(f"schema node is a {type(s).__name__}")
    for k, v in s.items():
        acc.add(k)
        if k in ("properties", "patternProperties", "$defs"):
            for sub in v.values():
                collect_keywords(sub, acc)
        elif k in ("items", "additionalProperties", "not", "contains", "propertyNames") and isinstance(v, (dict, bool)):
            collect_keywords(v, acc)
        elif k in ("anyOf", "oneOf", "allOf", "prefixItems"):
            for sub in v:
                collect_keywords(sub, acc)


_RX_CACHE = {}


def ecma_regex(p):
    """Compile an ECMA-262 pattern of the simple kind these schemas use. An unescaped '$'
    outside a class becomes an end-of-string anchor (Python's '$' would also match before
    a final newline); digit classes are ASCII only."""
    rx = _RX_CACHE.get(p)
    if rx is not None:
        return rx
    out, i, in_class = [], 0, False
    while i < len(p):
        c = p[i]
        if c == _BS:
            out.append(p[i:i + 2])
            i += 2
            continue
        if in_class:
            if c == "]":
                in_class = False
            out.append(c)
        elif c == "[":
            in_class = True
            out.append(c)
        elif c == "$":
            out.append(_BS + "Z")
        else:
            out.append(c)
        i += 1
    rx = re.compile("".join(out), re.ASCII)
    _RX_CACHE[p] = rx
    return rx


def json_type_name(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__


def json_type_ok(v, t):
    if t == "null":
        return v is None
    if t == "boolean":
        return isinstance(v, bool)
    if t == "integer":
        return (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer())
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "string":
        return isinstance(v, str)
    if t == "array":
        return isinstance(v, list)
    if t == "object":
        return isinstance(v, dict)
    raise SchemaKeywordError(f"unknown type {t!r}")


def json_equal(a, b):
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    return False


def resolve_ref(root, ref):
    if not ref.startswith("#/"):
        raise SchemaKeywordError(f"non-local $ref {ref!r}")
    node = root
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def validate(v, s, root, path, errs):
    if s is True:
        return
    if s is False:
        errs.append(f"{path}: not allowed")
        return
    for k in s:
        if k not in SUPPORTED_KEYWORDS and k not in ANNOTATION_KEYWORDS:
            raise SchemaKeywordError(f"unsupported keyword {k!r} at {path}")
    if "$ref" in s:
        validate(v, resolve_ref(root, s["$ref"]), root, path, errs)
    if "type" in s:
        types = s["type"] if isinstance(s["type"], list) else [s["type"]]
        if not any(json_type_ok(v, t) for t in types):
            errs.append(f"{path}: {json_type_name(v)} is not {'/'.join(map(str, types))}")
    if "const" in s and not json_equal(v, s["const"]):
        errs.append(f"{path}: {v!r} is not the constant {s['const']!r}")
    if "enum" in s and not any(json_equal(v, e) for e in s["enum"]):
        errs.append(f"{path}: {v!r} not in {s['enum']!r}")
    if isinstance(v, str):
        if "pattern" in s and not ecma_regex(s["pattern"]).search(v):
            errs.append(f"{path}: {v!r} does not match {s['pattern']}")
        if "minLength" in s and len(v) < s["minLength"]:
            errs.append(f"{path}: shorter than {s['minLength']}")
        if "maxLength" in s and len(v) > s["maxLength"]:
            errs.append(f"{path}: longer than {s['maxLength']}")
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if "minimum" in s and v < s["minimum"]:
            errs.append(f"{path}: {v} below minimum {s['minimum']}")
        if "maximum" in s and v > s["maximum"]:
            errs.append(f"{path}: {v} above maximum {s['maximum']}")
    if isinstance(v, dict):
        for r in s.get("required", []):
            if r not in v:
                errs.append(f"{path}: missing required {r!r}")
        if "minProperties" in s and len(v) < s["minProperties"]:
            errs.append(f"{path}: fewer than {s['minProperties']} properties")
        props = s.get("properties", {})
        pprops = s.get("patternProperties", {})
        for key, val in v.items():
            matched = False
            if key in props:
                matched = True
                validate(val, props[key], root, f"{path}.{key}", errs)
            for pat, sub in pprops.items():
                if ecma_regex(pat).search(key):
                    matched = True
                    validate(val, sub, root, f"{path}.{key}", errs)
            if not matched and "additionalProperties" in s:
                ap = s["additionalProperties"]
                if ap is False:
                    errs.append(f"{path}: unknown property {key!r}")
                elif ap is not True:
                    validate(val, ap, root, f"{path}.{key}", errs)
    if isinstance(v, list):
        if "minItems" in s and len(v) < s["minItems"]:
            errs.append(f"{path}: fewer than {s['minItems']} items")
        if "maxItems" in s and len(v) > s["maxItems"]:
            errs.append(f"{path}: more than {s['maxItems']} items")
        if "items" in s:
            for i, item in enumerate(v):
                validate(item, s["items"], root, f"{path}[{i}]", errs)
    if "anyOf" in s:
        if not any(not schema_errors_at(v, sub, root, path) for sub in s["anyOf"]):
            errs.append(f"{path}: matches none of anyOf")
    if "oneOf" in s:
        n = sum(1 for sub in s["oneOf"] if not schema_errors_at(v, sub, root, path))
        if n != 1:
            errs.append(f"{path}: matches {n} of oneOf (exactly 1 required)")
    if "not" in s and not schema_errors_at(v, s["not"], root, path):  # v0.7: state/2 uses it (files never list STATE.json)
        errs.append(f"{path}: {v!r} matches the schema under not")


def schema_errors_at(v, s, root, path):
    errs = []
    validate(v, s, root, path, errs)
    return errs


def schema_errors(v, schema):
    return schema_errors_at(v, schema, schema, "$")


# ---------------------------------------------------------------------------
# Calendars and time (sections 1 and 3): ET dates, New York Fed business days
# ---------------------------------------------------------------------------


def nth_weekday(y, m, weekday, n):
    first = dt.date(y, m, 1)
    return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def last_weekday(y, m, weekday):
    last = dt.date(y, m, calendar.monthrange(y, m)[1])
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


_HOLIDAYS = {}
_HOLIDAY_TABLE = None  # the registry's holiday table (3), set by load_holiday_table


def fed_holidays(y):
    """The Reserve Bank closures of year y from the registry's holiday table (3). My own
    rules are used only when no table could be loaded (R11 then fails), and as the
    independent cross-check H2."""
    if _HOLIDAY_TABLE is not None:
        if not _HOLIDAY_TABLE["first"] <= y <= _HOLIDAY_TABLE["last"]:
            # 3: a date in a year outside `years` is an error, never a guess.
            raise ValueError(f"year {y} is outside the holiday table ({_HOLIDAY_TABLE['first']} to {_HOLIDAY_TABLE['last']})")
        return _HOLIDAY_TABLE["days"]
    return _own_fed_holidays(y)


def _own_fed_holidays(y):
    """My own Federal Reserve holiday table (the registry has none: section 3 leaves it
    PROPOSED). A holiday on Sunday moves to Monday; on Saturday the Banks are open the
    preceding Friday (observed in the saved data, section 3). Juneteenth from 2022."""
    if y in _HOLIDAYS:
        return _HOLIDAYS[y]
    h = set()
    fixed = [(1, 1), (7, 4), (11, 11), (12, 25)] + ([(6, 19)] if y >= 2022 else [])
    for m, d in fixed:
        day = dt.date(y, m, d)
        if day.weekday() == 6:
            h.add(day + dt.timedelta(days=1))
        elif day.weekday() < 5:
            h.add(day)
    h |= {nth_weekday(y, 1, 0, 3), nth_weekday(y, 2, 0, 3), last_weekday(y, 5, 0),
          nth_weekday(y, 9, 0, 1), nth_weekday(y, 10, 0, 2), nth_weekday(y, 11, 3, 4)}
    _HOLIDAYS[y] = h
    return h


def is_business_day(d):
    return d.weekday() < 5 and d not in fed_holidays(d.year)


def next_business_day(d):
    d += dt.timedelta(days=1)
    while not is_business_day(d):
        d += dt.timedelta(days=1)
    return d


def _dst_window_utc(year):
    if year >= 2007:
        start, end = nth_weekday(year, 3, 6, 2), nth_weekday(year, 11, 6, 1)
    else:
        start, end = nth_weekday(year, 4, 6, 1), last_weekday(year, 10, 6)
    return (dt.datetime(start.year, start.month, start.day, 7, tzinfo=UTC),
            dt.datetime(end.year, end.month, end.day, 6, tzinfo=UTC))


def et_offset_hours(t_utc):
    s, e = _dst_window_utc(t_utc.year)
    return -4 if s <= t_utc < e else -5


def et_local(t_utc):
    return t_utc + dt.timedelta(hours=et_offset_hours(t_utc))


def et_date(t_utc):
    return et_local(t_utc).date()


def et_wall_to_utc(d, hour, minute=0):
    naive = dt.datetime(d.year, d.month, d.day, hour, minute, tzinfo=UTC)
    off = et_offset_hours(naive + dt.timedelta(hours=5))
    return naive - dt.timedelta(hours=off)


def wall_to_utc(d, hhmm, zone):
    hour, minute = int(hhmm[:2]), int(hhmm[3:5])
    if zone == "UTC":
        return dt.datetime(d.year, d.month, d.day, hour, minute, tzinfo=UTC)
    if zone == "America/New_York":
        return et_wall_to_utc(d, hour, minute)
    raise ValueError(f"zone {zone!r} not handled")


def cal_instant(d, hhmm, cal, reading):
    """4.5: the instant a calendar's clock time names on date d. A verified zone names one
    instant; with "unknown" the clock time names one instant per candidate zone, and
    `reading` picks the earliest (whether a request is due, 17.3) or the latest (deadlines,
    staleness, expected_next_update_by and absences, 14.2, 11.6)."""
    zone = cal.get("publish_time_zone")
    if zone == "unknown":
        cands = cal.get("publish_time_zone_candidates") or []
        if not cands:
            raise ValueError("publish_time_zone is unknown but no candidates are given (4.5)")
        xs = [wall_to_utc(d, hhmm, z) for z in cands]
        if reading == "earliest":
            return min(xs)
        if reading == "latest":
            return max(xs)
        raise ValueError(f"reading {reading!r}")
    return wall_to_utc(d, hhmm, zone)


def parse_utc(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def fmt_utc(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot_id_of(t):
    return t.strftime("%Y%m%dT%H%M%SZ")


def snapshot_time(sid):
    return dt.datetime.strptime(sid, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)


def parse_date(s):
    return dt.date.fromisoformat(s)


def month_add(ym, n):
    y, m = int(ym[:4]), int(ym[5:7])
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


_MONTH_END = {}


def month_end(ym):
    if ym not in _MONTH_END:  # cached: the live mode calls it for every month of every H.6 series (21.3: fast)
        y, m = int(ym[:4]), int(ym[5:7])
        _MONTH_END[ym] = dt.date(y, m, calendar.monthrange(y, m)[1])
    return _MONTH_END[ym]


def next_fourth_tuesday_after(d):
    y, m = d.year, d.month
    for _ in range(3):
        cand = nth_weekday(y, m, 1, 4)
        if cand > d:
            return cand
        m += 1
        if m == 13:
            y, m = y + 1, 1
    raise ValueError("no fourth Tuesday found")


def http_date(path):
    if not path.is_file():
        return None
    for line in path.read_bytes().decode("utf-8", "replace").splitlines():
        if line.lower().startswith("date:"):
            return dt.datetime.strptime(line.split(":", 1)[1].strip(), "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=UTC)
    return None


def http_header(path, name):
    if not path.is_file():
        return None
    for line in path.read_bytes().decode("utf-8", "replace").splitlines():
        if line.lower().startswith(name.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return None


# ---------------------------------------------------------------------------
# Decimals (section 5, numbers)
# ---------------------------------------------------------------------------

_DECIMAL_TEXT = re.compile(r"[+-]?\d+(\.\d+)?", re.ASCII)
EXTRA_PLACES = {"p1": 2, "p25": 2, "p75": 2, "p99": 2, "volume_usd_billions": 0,
                "intraday_low": 2, "intraday_high": 2, "std_deviation": 2}
H6_STATUS_NOTE = {"NA": "Not available", "ND": "No data", "NC": "Not calculable"}


def frac_digits(text):
    return len(text.split(".", 1)[1]) if "." in text else 0


def sig_digits(text):
    digits = re.sub(r"[^0-9]", "", text.split("e")[0].split("E")[0]).lstrip("0")
    return len(digits) if digits else 1


def pad_decimal(text, places):
    m = re.fullmatch(r"([+-]?)(\d+)(?:\.(\d+))?", text, re.ASCII)
    if not m:
        raise ValueError(f"{text!r} is not a plain decimal")
    sign, ip, fp = m.group(1), m.group(2), m.group(3) or ""
    if len(fp) > places:
        raise ValueError(f"{text} has more than {places} fraction digits")
    fp += "0" * (places - len(fp))
    if sign == "+":
        sign = ""
    return sign + ip + ("." + fp if places else "")


def exact_places(text, places):
    if not isinstance(text, str):
        return False
    pat = r"-?\d+\.\d{%d}" % places if places else r"-?\d+"
    return re.fullmatch(pat, text, re.ASCII) is not None


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def era_for(series, period):
    hits = []
    for era in series["extract"]:
        lo, hi = era["from"], era["to"]
        if period[:len(lo)] >= lo and (hi is None or period[:len(hi)] <= hi):
            hits.append(era)
    return hits[0] if len(hits) == 1 else None


def fill_placeholders(text, data_name, year):
    if text is None:
        return None
    return text.replace("{data_name}", data_name).replace("{year}", str(year))


def placeholders_in(text):
    return re.findall(r"\{[^{}]*\}", text or "")


def ki_periods(ser):
    return {k["period"] for k in ser.get("known_inconsistencies", [])}


RX_GITHUB_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", re.ASCII)


def is_exact_zero(text):
    """2.3: an amount equal to zero (0, 0.0, 0.00, and their signed forms), read as a decimal, never a float."""
    return isinstance(text, str) and bool(_DECIMAL_TEXT.fullmatch(text)) and D(text) == 0


def accepted_zero_periods(ser, field="value"):
    """2.3, 4.4 (v0.6): the periods for which the series' accepted_zeros accept an exact zero in `field`."""
    entries = ser.get("accepted_zeros") if isinstance(ser.get("accepted_zeros"), list) else []
    return {e.get("period") for e in entries if isinstance(e, dict) and e.get("field") == field and isinstance(e.get("period"), str)}


def accepted_zero_problems(ser, entries, today=None):
    """R30 and C6 (2.3, 4.4, v0.6): what the text refuses in a series' accepted_zeros list.
    reading: "only on a series whose eras carry refuse_zero" means the era in force for each
    named period carries refuse_zero true; a period must be one the series can have (its
    frequency's form, a real date, a New York Fed business day not in known_gaps, since a
    documented gap has no record to check); and the source can only have been checked for a
    period that exists, so the period is on or before `checked`."""
    out = []
    if not isinstance(entries, list):
        return [f"accepted_zeros is {type(entries).__name__}, not a list (4.4)"]
    if not any(isinstance(e, dict) and e.get("refuse_zero") is True for e in ser.get("extract", [])):
        out.append("accepted_zeros on a series whose eras carry no refuse_zero (4.4: only on such a series)")
    month = ser.get("frequency") == "month"
    fmt = r"\d{4}-\d{2}" if month else r"\d{4}-\d{2}-\d{2}"
    gaps = {g.get("period") for g in ser.get("known_gaps", []) if isinstance(g, dict)}
    seen = []
    for i, e in enumerate(entries):
        w = f"accepted_zeros[{i}]"
        if not isinstance(e, dict):
            out.append(f"{w} is not an object")
            continue
        if sorted(e) != sorted(ACCEPTED_ZERO_FIELDS):
            out.append(f"{w} has fields {sorted(e)}; 4.4 gives exactly {list(ACCEPTED_ZERO_FIELDS)}")
        period = e.get("period")
        seen.append(period)
        if not (isinstance(period, str) and re.fullmatch(fmt, period, re.ASCII)):
            out.append(f"{w}: period {period!r} is not one {ser.get('frequency')} period (2.3: exactly one period, no ranges or patterns)")
            period = None
        else:
            try:
                d = parse_date(period) if not month else None
            except ValueError:
                out.append(f"{w}: period {period!r} is not a calendar date")
                d, period = None, None
            if d is not None:
                if period in gaps:
                    out.append(f"{w}: period {period} is a documented gap of the series (2.3: no record exists there to accept)")
                elif not is_business_day(d) and period not in ki_periods(ser):
                    out.append(f"{w}: period {period} is not a New York Fed business day (3, 6.2)")
            era = era_for(ser, period) if period else None
            if period and (era is None or era.get("refuse_zero") is not True):
                out.append(f"{w}: the era in force for {period} carries no refuse_zero (4.4)")
        if e.get("field") != "value":
            out.append(f"{w}: field {e.get('field')!r}; 4.4 gives value")
        checked = e.get("checked")
        if not (isinstance(checked, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked, re.ASCII)):
            out.append(f"{w}: checked {checked!r} is not a date")
            checked = None
        if not is_str(e.get("evidence")):
            out.append(f"{w}: evidence is not a text (4.4: the evidence in words)")
        who = e.get("authorized_by")
        if not (isinstance(who, str) and RX_GITHUB_LOGIN.fullmatch(who)) or rx_automation_login(who):
            out.append(f"{w}: authorized_by {who!r} is not a person's GitHub login (4.4, 11.5)")
        at = e.get("authorized_at")
        if not is_time(at):
            out.append(f"{w}: authorized_at {at!r} is not a UTC time to the second (4.4)")
        elif period and period[:10] > et_date(parse_utc(at)).isoformat()[:len(period)]:
            out.append(f"{w}: period {period} is after {et_date(parse_utc(at)).isoformat()}, the ET date of authorized_at {at} (2.3, 4.4: never a future observation)")
        if period and checked and period > checked[:len(period)]:
            out.append(f"{w}: period {period} is after checked {checked}; the source cannot have shown it (reading of 2.3: confirmed in the source)")
        if today is not None and is_time(at) and parse_utc(at) > today:
            out.append(f"{w}: authorized_at {at} is in the future")
    dup = sorted({str(x) for x in seen if seen.count(x) > 1})
    if dup:
        out.append(f"periods {dup} named more than once (4.4: periods unique)")
    return out


# ---------------------------------------------------------------------------
# Shared state and raw loaders
# ---------------------------------------------------------------------------


class State:
    pass


def rel(p):
    return p.relative_to(TREE).as_posix()


def tree_bytes(relpath):
    p = TREE / relpath
    return p.read_bytes() if relpath and p.is_file() else None


def load_state():
    st = State()
    st.registry_bytes = REGISTRY.read_bytes()
    st.registry = load_strict(st.registry_bytes)
    st.series = {s["id"]: s for s in st.registry.get("series", []) if isinstance(s, dict) and "id" in s}
    st.schemas = {}
    for name in ("registry", "object", "snapshot", "manifest", "revisions", "runs", "review", "review-queue", "publications", "pins", "alerts", "holidays",
                 "rollback", "state", "state-v2", "accepted", "collection"):  # v0.6 adds rollback/1 and state/1; v0.7 state/2, accepted/1, collection/1
        f = SCHEMA_DIR / f"{name}.schema.json"
        if name == "manifest" and (SCHEMA_DIR / "manifest-v3.schema.json").is_file():
            f = SCHEMA_DIR / "manifest-v3.schema.json"  # I31, I41: the historical manifest/3 files
        st.schemas[name] = load_strict(f.read_bytes())
    build_v08_shapes(st)  # v0.8: manifest/4 and deployments/1 are built from the text; their schema files are probed by S7 (I31)
    st.source_records = load_strict((SCHEMA_DIR / "source-records.json").read_bytes())
    st.tree_files = sorted(p for p in TREE.rglob("*") if p.is_file())
    st.tree_json, st.tree_json_errors = {}, {}
    for p in st.tree_files:
        if p.suffix == ".json":
            try:
                st.tree_json[rel(p)] = load_strict(p.read_bytes())
            except Exception as exc:
                st.tree_json_errors[rel(p)] = f"{type(exc).__name__}: {exc}"
    st.raw = {}
    return st


def load_raw(st, key, path):
    if key not in st.raw:
        st.raw[key] = load_numtext(path.read_bytes()) if path.is_file() else None
    return st.raw[key]


def h6_release_dates(st):
    """releaseDates.json dates as YYYY-MM-DD with markers stripped, or None if absent."""
    if "h6dates_list" in st.raw:
        return st.raw["h6dates_list"]
    doc = load_raw(st, "h6dates", RAW_H6_DATES) if RAW_H6_DATES.is_file() else None
    out = None
    if doc is not None:
        out = sorted(f"{x[:4]}-{x[4:6]}-{x[6:8]}" for y in doc for m in y["Months"] for x in m["Dates"])
    st.raw["h6dates_list"] = out
    return out


def fd_calendar_time(st, dataset_id, day):
    if not RAW_FD_CAL.is_file():
        return None
    cal = st.raw.get("fdcal")
    if cal is None:
        cal = st.raw["fdcal"] = json.loads(RAW_FD_CAL.read_bytes().decode("utf-8"))
    hit = [e["time"] for e in cal if e.get("datasetId") == dataset_id and e.get("date") == day.isoformat()]
    return hit[0] if hit else None


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def read_zip_xml(name):
    with zipfile.ZipFile(RAW_H6_ZIP) as z:
        info = z.getinfo(name)
        data = z.read(name)
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ValueError(f"{name} declares a DTD or entity: refused")
    return info, data


def load_h6(st):
    if "h6" in st.raw:
        return st.raw["h6"]
    info, data = read_zip_xml("H6_data.xml")
    out = {"series": {}, "prepared": None, "entry_time": dt.datetime(*info.date_time), "bytes": len(data), "obs_total": 0, "status_all": set()}
    dataset = None
    for event, el in ET.iterparse(io.BytesIO(data), events=("start", "end")):
        name = _local(el.tag)
        if event == "start":
            if name == "DataSet":
                dataset = el.attrib.get("id")
            continue
        if name == "Prepared" and out["prepared"] is None:
            out["prepared"] = (el.text or "").strip()
        elif name == "Series":
            ann = [(_local(x.tag), (x.text or "").strip()) for a in el if _local(a.tag) == "Annotations" for x in a.iter()]
            obs = [dict(o.attrib) for o in el if _local(o.tag) == "Obs"]
            out["obs_total"] += len(obs)
            out["status_all"] |= {o.get("OBS_STATUS") for o in obs}
            other = sorted({_local(c.tag) for c in el} - {"Annotations", "Obs"})
            out["series"].setdefault(el.attrib.get("SERIES_NAME"), []).append(
                {"dataset": dataset, "ns": el.tag.split("}")[0].lstrip("{"), "attrs": dict(el.attrib), "ann": ann, "obs": obs, "other": other})
            el.clear()
    st.raw["h6"] = out
    return out


def h6_codelist(name):
    _, data = read_zip_xml("H6_struct.xml")
    root = ET.fromstring(data)
    for cl in root.iter():
        if _local(cl.tag) == "CodeList" and cl.attrib.get("id") == name:
            out = {}
            for code in cl:
                if _local(code.tag) == "Code":
                    desc = [x.text for x in code if _local(x.tag) == "Description"]
                    out[code.attrib.get("value")] = (desc[0] or "").strip() if desc else ""
            return out
    return None


def norm_text(s):
    for a, b in ((chr(0x2019), "'"), (chr(0x2018), "'"), (chr(0x201C), '"'), (chr(0x201D), '"'), (chr(0xA0), " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def html_text(b):
    try:
        t = b.decode("utf-8")
    except UnicodeDecodeError:
        t = b.decode("cp1252", "replace")
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return norm_text(html_lib.unescape(t))


# ---------------------------------------------------------------------------
# Section 7: canonical JSON
# ---------------------------------------------------------------------------


def section_canonical(st):
    problems = []
    e_acute, full_a, emoji, line_sep, bom_char = chr(0xE9), chr(0xFF21), chr(0x1F600), chr(0x2028), chr(0xFEFF)
    q = '"'
    cases = [
        ({"b": 1, "a": [True, False, None, "x/y", e_acute + chr(10) + q + _BS]},
         "{" + q + "a" + q + ":[true,false,null," + q + "x/y" + q + "," + q + e_acute + _BS + "n" + _BS + q + _BS + _BS + q + "]," + q + "b" + q + ":1}"),
        ({emoji: 2, full_a: 1}, "{" + q + full_a + q + ":1," + q + emoji + q + ":2}"),
        (chr(8) + chr(9) + chr(12) + chr(13), q + _BS + "b" + _BS + "t" + _BS + "f" + _BS + "r" + q),
        (chr(1) + chr(0x1F) + chr(0x7F) + chr(0x85) + line_sep + bom_char,
         q + _BS + "u0001" + _BS + "u001f" + chr(0x7F) + chr(0x85) + line_sep + bom_char + q),
        ([-5, 0, SAFE_INT, -SAFE_INT], "[-5,0,9007199254740991,-9007199254740991]"),
    ]
    for value, expected in cases:
        got = canon_text(value)
        if got != expected:
            problems.append(f"{value!r} gave {got!r}, expected {expected!r}")
    for bad in (1.5, chr(0xD800), SAFE_INT + 1, -(SAFE_INT + 1)):
        try:
            canon_text(bad)
            problems.append(f"{bad!r} was accepted")
        except ValueError:
            pass
    for bad_json in (b'{"a":1,"a":2}', b'{"a":1.0}', b'{"a":1e2}', b'[NaN]', b'[01]', b'\xef\xbb\xbf{}'):
        try:
            load_strict(bad_json)
            problems.append(f"{bad_json!r} was accepted by the strict reader")
        except (StrictJsonError, ValueError):
            pass
    if canon_text(load_strict(b"[-0]")) != "[0]":
        problems.append("negative zero is not written as 0")
    check("C0 canonical serializer self-test (7: code point order, the five short escapes, lowercase \\u00xx, U+007F..U+009F/U+2028/U+FEFF raw, safe integers, -0 as 0)", problems)
    section_selftests_v04(st)
    section_selftests_v05(st)
    section_selftests_v07(st)


def section_selftests_v05(st):
    """C4 (v0.6 lock rules), C5 (several locks per series, the rollback's lock sets, the
    window rule) and C6 (accepted zeros): this checker's rules on fixed cases, including the
    adversarial ones (5, 11.5, 17.3, 17.5, 2.3, 4.4)."""
    p = []

    def expect(label, got, want, bucket=None):
        if got != want:
            (p if bucket is None else bucket).append(f"{label}: got {got}, expected {want}")

    def ob(day, value, **kw):
        o = {"period": f"2026-10-{day:02d}", "value": value, "released": {"date": None, "basis": "not-recorded"}, "flags": []}
        o.update(kw)
        return o

    def assemble(base, response, start):  # 5: the base's observations before the window, the response's from it on
        return [o for o in base if o["period"] < start] + [o for o in response if o["period"] >= start]
    try:
        pub = [ob(1, "1.00"), ob(2, "2.00"), ob(5, "5.00")]
        rej = [ob(1, "1.00"), ob(2, "9.00"), ob(5, "5.00"), ob(6, "6.00")]
        both = [("2026-10-02", "value"), ("2026-10-06", "period")]
        expect("rejected (v0.6, E1): the new period counts too", lock_changes(pub, rej, "rejected"), both)
        expect("rolled-back: the new period counts", lock_changes(pub, rej, "rolled-back"), both)
        ch = lock_changes(pub, rej)
        expect("the source keeps the rejected value with more new periods: carried, the lock stays",
               lock_stands("rejected", rej + [ob(7, "7.00")], rej, ch), True)
        expect("the source returns the published value but keeps the rejected new period (appendix B row 16): carried, the lock stays",
               lock_stands("rejected", pub + [ob(6, "6.00"), ob(7, "7.00")], rej, ch), True)
        expect("the source returns the published value and drops the rejected new period: nothing carried, the lock lifts",
               lock_stands("rejected", pub + [ob(7, "7.00")], rej, ch), False)
        expect("the rejected new period changes to another value: not carried; with the old value back the lock lifts",
               lock_stands("rejected", pub + [ob(6, "6.50")], rej, ch), False)
        expect("a delayed revision to a third value, the new period gone: nothing carried, the lock lifts (then a new hold)",
               lock_stands("rejected", [ob(1, "1.00"), ob(2, "7.00"), ob(5, "5.00")], rej, ch), False)
        add_only = pub + [ob(6, "6.00")]
        cha = lock_changes(pub, add_only)
        expect("a rejection of new periods alone has locked changes (v0.5 had none and lifted at once)", cha, [("2026-10-06", "period")])
        expect("... and stays while the source keeps them unchanged", lock_stands("rejected", add_only + [ob(7, "7.00")], add_only, cha), True)
        expect("the rejected new period released ignored: still carried", lock_stands("rejected", pub + [ob(6, "6.00", released={"date": "2026-10-07", "basis": "first-seen"})], add_only, cha), True)
        removed = [ob(1, "1.00"), ob(5, "5.00")]
        chr_ = lock_changes(pub, removed)
        expect("a removed period is a locked change of field period", chr_, [("2026-10-02", "period")])
        expect("a candidate still lacking it carries it", bool(lock_carried([ob(1, "1.00"), ob(5, "5.00"), ob(6, "6.00")], removed, chr_)), True)
        expect("a candidate that has it again carries none", lock_carried(pub, removed, chr_), [])
        inserted = [ob(1, "1.00"), ob(2, "2.00"), ob(3, "3.00"), ob(5, "5.00")]
        chi = lock_changes(pub, inserted)
        expect("a period inserted on or before the last published one is a locked change", chi, [("2026-10-03", "period")])
        expect("reading: it is carried by the same observation, released ignored", bool(lock_carried(pub + [ob(3, "3.00", released={"date": "2026-10-06", "basis": "first-seen"})], inserted, chi)), True)
        expect("reading: not by the same period at another value", lock_carried(pub + [ob(3, "4.00")], inserted, chi), [])
        flag = [ob(1, "1.00"), ob(2, "2.00", flags=["r"]), ob(5, "5.00")]
        expect("a flag change is a member change", lock_changes(pub, flag), [("2026-10-02", "flags")])
        ext = [ob(1, "1.00"), ob(2, "2.00", extra={"p1": "1.90"}), ob(5, "5.00")]
        expect("an extra field change is extra.<name>", lock_changes(pub, ext), [("2026-10-02", "extra.p1")])
        expect("a lock on a series never published: every period of the locked candidate", lock_changes([], pub), [("2026-10-01", "period"), ("2026-10-02", "period"), ("2026-10-05", "period")])
        expect("a rolled-back lock stands whatever the source returns", lock_stands("rolled-back", pub, rej, ch), True)
        # 5 (v0.6, E3): the windowed candidate is assembled over the published data, and a lock with a
        # locked change before the window's first period stays in force on that run.
        start = "2026-10-04"
        response = [ob(5, "5.00"), ob(6, "6.00")]
        cand = assemble(pub, response, start)
        expect("windowed over the published data: the old change is not in the candidate", lock_carried(cand, rej, ch), [("2026-10-06", "period")])
        response2 = [ob(5, "5.00")]
        cand2 = assemble(pub, response2, start)
        expect("the candidate carries none of the locked changes, yet a change lies before the window: the lock stands (E3)",
               (lock_carried(cand2, rej, ch), lock_stands("rejected", cand2, rej, ch, start)), ([], True))
        expect("the same candidate on a full fetch: the lock lifts", lock_stands("rejected", cand2, rej, ch, None), False)
        expect("a window that reaches back before every locked change can lift it", lock_stands("rejected", assemble(pub, [ob(2, "2.00"), ob(5, "5.00")], "2026-10-02"), rej, ch, "2026-10-02"), False)
        expect("reading: the window's first period itself is inside the window", lock_stands("rejected", pub, [ob(5, "9.00")], [("2026-10-05", "value")], "2026-10-05"), False)
        expect("... and the day before it is not", lock_stands("rejected", pub, [ob(5, "9.00")], [("2026-10-05", "value")], "2026-10-06"), True)
        expect("windowed over the locked candidate (v0.5, E3 replaced it) would wrongly carry the change and differ before the window",
               assemble(rej, response, start) != cand, True)
        # 17.5: refusal rules and their order, with several locks per series (v0.6).
        perms = ["admin", "maintain", "write"]
        now = "2026-11-25T15:00:00Z"
        locks, held = {"m1-sa": {"a" * 64}, "debt-intragov": {"d" * 64, "e" * 64}}, {"debt-total": "b" * 64}
        for label, args, want in (
                ("clear of a series without a lock", ("clear", "m2-sa", "a" * 64, "x", "maintain", now), "not-locked"),
                ("clear naming another candidate", ("clear", "m1-sa", "c" * 64, "x", "maintain", now), "stale-candidate"),
                ("clear naming the second of two locks of a series (v0.6: named by its hash)", ("clear", "debt-intragov", "e" * 64, "x", "maintain", now), None),
                ("clear naming the hash of another series' lock", ("clear", "debt-intragov", "a" * 64, "x", "maintain", now), "stale-candidate"),
                ("clear by a reader", ("clear", "m1-sa", "a" * 64, "x", "read", now), "permission"),
                ("clear with the permission read 3,601 s before", ("clear", "m1-sa", "a" * 64, "x", "maintain", "2026-11-25T13:59:59Z"), "permission-time"),
                ("clear with the permission read 3,600 s before (both ends included)", ("clear", "m1-sa", "a" * 64, "x", "maintain", "2026-11-25T14:00:00Z"), None),
                ("clear by github-actions with write", ("clear", "m1-sa", "a" * 64, "GitHub-Actions", "write", now), "automation"),
                ("clear without a reviewer and without a lock", ("clear", "m2-sa", "a" * 64, "", "read", now), "not-locked"),
                ("approve of a held series that a rollback also locked", ("approve", "m1-sa", "a" * 64, "x", "maintain", now), "locked"),
                ("approve of a series locked but not held", ("approve", "m2-sa", "a" * 64, "x", "maintain", now), "not-held"),
                ("reject of a held, unlocked series", ("reject", "debt-total", "b" * 64, "x", "write", now), None),
                ("a decision outside the three on a held series", ("thaw", "debt-total", "b" * 64, "x", "write", now), "bad-decision")):
            h = dict(held, **({"m1-sa": "a" * 64} if label.startswith("approve of a held") else {}))
            got, _ = refusal_rule(args[0], args[1], args[2], args[3], args[4], args[5], now, h, locks, perms)
            expect(f"refusal: {label}", got, want)
    except Exception as exc:
        p.append(f"{type(exc).__name__}: {exc}")
    check("C4 lock rules self-test (v0.6): locked changes count new periods for both origins (E1), so rejected additions stay locked while the source keeps them; carrying a locked change (removed, inserted, changed member, flags, extras, released ignored); the lift on a third value or a return; the windowed candidate over the published data with a locked change before the window keeping the lock (E3); the refusal rules for clear and locked series in the order of 17.5 (5, 11.5, 17.5)", p)

    p = []
    try:
        def lk(sid, origin, h):
            return {"series": sid, "origin": origin, "candidate_sha256": h * 64, "frozen_at": "2026-11-18T14:30:00Z", "reason": "r"}

        def keyed(*es):
            return {lock_key(e): e for e in es}
        a_rej, b_rej, c_rb = lk("debt-intragov", "rejected", "a"), lk("debt-intragov", "rejected", "b"), lk("debt-intragov", "rolled-back", "c")
        locks = keyed(a_rej, b_rej, c_rb)
        expect("three locks on one series are three locks (11.5 v0.6: series, origin and hash identify a lock)", (len(locks), lock_series(locks)), (3, {"debt-intragov"}))
        expect("the same entry twice is one lock", len(keyed(a_rej, dict(a_rej))), 1)
        expect("a series stays locked while any of its locks stands", series_after_lifts({lock_key(a_rej): False, lock_key(b_rej): True}), "locked")
        expect("it is classified afresh only when the last lifts", series_after_lifts({lock_key(a_rej): False, lock_key(b_rej): False}), "classify")
        expect("a rolled-back lock keeps the series locked when a rejected lock of it lifts", series_after_lifts({lock_key(a_rej): False, lock_key(c_rb): lock_stands("rolled-back", [], [], [])}), "locked")
        # each lifts by its own rule: lock A on 10-02, lock B on the new period 10-06
        pub = [{"period": "2026-10-01", "value": "1.00"}, {"period": "2026-10-02", "value": "2.00"}]
        ca = pub[:1] + [{"period": "2026-10-02", "value": "9.00"}]
        cb = pub + [{"period": "2026-10-06", "value": "6.00"}]
        cha, chb = lock_changes(pub, ca), lock_changes(pub, cb)
        cand = pub + [{"period": "2026-10-06", "value": "6.00"}]
        expect("a candidate with the published 10-02 and the rejected 10-06: A lifts, B stands, the series stays locked",
               (lock_stands("rejected", cand, ca, cha), lock_stands("rejected", cand, cb, chb), series_after_lifts({"A": lock_stands("rejected", cand, ca, cha), "B": lock_stands("rejected", cand, cb, chb)})),
               (False, True, "locked"))
        # rollback lock sets (17.5 v0.6)
        own = keyed(lk("effr", "rolled-back", "1"), lk("debt-intragov", "rolled-back", "2"))
        t_rej = lk("debt-total", "rejected", "3")            # in the target's frozen
        late_rej = lk("debt-intragov", "rejected", "4")      # decided after the target
        old_rb = lk("m1-sa", "rolled-back", "5")             # an earlier rollback's lock the target does not carry
        before = keyed(t_rej, late_rej, old_rb)
        target = keyed(t_rej)
        kept, required, tolerated = rollback_lock_sets(own, before, target)
        expect("kept: every rejection lock in force before the rollback, the target's and the later one", set(kept), {lock_key(t_rej), lock_key(late_rej)})
        expect("the record must list the own locks and the later rejection lock, not the target's", set(required), set(own) | {lock_key(late_rej)})
        expect("a series changed by the rollback and rejected after the target carries both locks", sorted(k[1] for k in required if k[0] == "debt-intragov"), ["rejected", "rolled-back"])
        expect("an earlier rollback's lock the target does not carry is tolerated, not required (reading, see the report)", set(tolerated), {lock_key(old_rb)})
        order = [s["id"] for s in st.registry.get("series", [])]
        ranks = sorted(required, key=lambda k: (order.index(k[0]), LOCK_ORIGINS.index(k[1])))
        expect("registry order then origin: effr, then debt-intragov rejected before rolled-back", [(k[0], k[1]) for k in ranks],
               [("effr", "rolled-back"), ("debt-intragov", "rejected"), ("debt-intragov", "rolled-back")])
        locked_series = [sid for sid in order if sid in lock_series(required) and sid not in lock_series(target)]
        expect("rollback.locked: the series of the record's locks the target does not lock, in registry order", locked_series, ["effr", "debt-intragov"])
        kept2, required2, _ = rollback_lock_sets(own, keyed(t_rej), keyed(t_rej))
        expect("a rejection lock the target lists stays in the target's frozen, not in the record", (lock_key(t_rej) in required2, set(required2)), (False, set(own)))
        _, required3, _ = rollback_lock_sets({}, {}, {})
        expect("a rollback that changes nothing and keeps nothing: an empty record", required3, {})
    except Exception as exc:
        p.append(f"{type(exc).__name__}: {exc}")
    check("C5 several locks per series self-test (v0.6): identity by series, origin and hash; a series locked while any lock stands and classified afresh only when the last lifts; each lock lifting by its own rule; a rollback's record listing its own locks and every rejection lock in force before it (including one decided after its target) that the target does not list, in registry order then origin, and rollback.locked their series (11.5, 12.9, 17.5)", p)

    p = []
    try:
        base = json.loads(json.dumps(st.series["debt-intragov"]))
        az = {"period": "2026-11-10", "field": "value", "checked": "2026-11-19", "evidence": "a saved response", "authorized_by": "example-maintainer", "authorized_at": "2026-11-19T15:00:00Z"}
        for label, entries, want_ok in (
                ("one entry with the six fields", [az], True),
                ("the period on the ET date of authorized_at", [dict(az, period="2026-11-19", checked="2026-11-19")], True),
                ("authorized at 01:00 UTC, still the previous ET date: a period of that UTC day is after it", [dict(az, period="2026-11-19", checked="2026-11-19", authorized_at="2026-11-19T01:00:00Z")], False),
                ("a period after the ET date of authorized_at", [dict(az, period="2026-11-20", checked="2026-11-20")], False),
                ("a period after checked (reading: the source cannot show it)", [dict(az, period="2026-11-12", checked="2026-11-11")], False),
                ("a range of periods", [dict(az, period="2026-11-01..2026-11-10")], False),
                ("a month on a business-day series", [dict(az, period="2026-11")], False),
                ("a Saturday", [dict(az, period="2026-11-14")], False),
                ("a documented gap", [dict(az, period=(base.get("known_gaps") or [{"period": "2019-04-03"}])[0]["period"])], False),
                ("a source field instead of value", [dict(az, field="intragov_hold_amt")], False),
                ("a bot", [dict(az, authorized_by="renovate[bot]")], False),
                ("github-actions", [dict(az, authorized_by="github-actions")], False),
                ("a time with an offset", [dict(az, authorized_at="2026-11-19T10:00:00-05:00")], False),
                ("an empty evidence", [dict(az, evidence="")], False),
                ("two entries for one period", [az, dict(az, evidence="again")], False),
                ("an extra field", [dict(az, until="2027-01-01")], False)):
            got = accepted_zero_problems(base, entries)
            expect(f"accepted_zeros: {label}", not got, want_ok)
        effr = json.loads(json.dumps(st.series["effr"]))
        expect("accepted_zeros on a series without refuse_zero", bool(accepted_zero_problems(effr, [dict(az, period="2026-11-10")])), True)
        expect("only an exact zero is accepted: 0, 0.0, 0.00 and -0.00 are zero; 0.01 and 'null' are not",
               [is_exact_zero(x) for x in ("0", "0.0", "0.00", "-0.00", "0.01", "null", "")], [True, True, True, True, False, False, False])
        ser = dict(base, accepted_zeros=[az])
        expect("the accepted period and field", (accepted_zero_periods(ser), accepted_zero_periods(ser, "lower")), ({"2026-11-10"}, set()))
        expect("the accepted zero is stored as the padded number zero", pad_decimal("0", ser["decimals"]), "0.00")
    except Exception as exc:
        p.append(f"{type(exc).__name__}: {exc}")
    check("C6 accepted zeros self-test (v0.6): an entry names one business-day period (no range, pattern or month), field value, on or before the ET date of authorized_at and of checked, not a documented gap, authorized by a person, periods unique, only on a series with refuse_zero; only an exact zero is covered and it is stored as 0.00 (2.3, 4.4)", p)


# ---------------------------------------------------------------------------
# v0.7 rules as pure functions (14.2, 14.3, 17.3, 20.2) and their self-tests C7 to C9
# ---------------------------------------------------------------------------


def _cron_field_matches(field, value, lo, hi):
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            step = int(s)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
        else:
            a = b = int(part)
        if a <= value <= b and (value - a) % step == 0:
            return True
    return False


def cron_fires(line, t):
    """Whether a five-field cron line (minute, hour, day of month, month, day of week with 0 for
    Sunday; UTC, as GitHub schedules read it) fires at the UTC minute of t. Supports *, */n,
    a-b, lists and numbers, which is all 14.2 uses."""
    f = line.split()
    if len(f) != 5:
        raise ValueError(f"not a five-field cron line: {line!r}")
    dow = (t.weekday() + 1) % 7
    return (_cron_field_matches(f[0], t.minute, 0, 59) and _cron_field_matches(f[1], t.hour, 0, 23) and _cron_field_matches(f[2], t.day, 1, 31)
            and _cron_field_matches(f[3], t.month, 1, 12) and _cron_field_matches(f[4], dow, 0, 6))


def run_gap_severity(hours):
    """14.3 (v0.7): scheduled-run-gap is a warning when the hours exceed 9, critical over 26."""
    if hours > RUN_GAP_CRITICAL_HOURS:
        return "critical"
    if hours > RUN_GAP_WARNING_HOURS:
        return "warning"
    return None


def schedule_health_findings(now, workflow_state, pushed_at, runs):
    """14.3 (v0.7) on the facts of 17.8 and 21.3: the workflow's state, the repository's
    pushed_at and the run list, newest first, each {"event", "conclusion", "created_at"}
    (datetimes). Returns {finding key: severity}. A run still in progress (no conclusion yet, such
    as the run evaluating the facts) neither counts nor breaks the failure streak, like cancelled
    and skipped; no run listed at all is a critical scheduled-run-gap (14.3 v0.7, F13)."""
    out = {}
    if workflow_state != "active":
        out["workflow-disabled"] = "critical"
    if pushed_at is not None:
        days = int((now - pushed_at).total_seconds() // 86400)
        if days >= 55:
            out["inactivity"] = "critical"
        elif days >= 45:
            out["inactivity"] = "warning"
    ok = [r["created_at"] for r in runs if r.get("event") == "schedule" and r.get("conclusion") == "success"]
    ref = max(ok) if ok else (min(r["created_at"] for r in runs) if runs else None)
    if ref is None:
        out["scheduled-run-gap"] = "critical"
    else:
        sev = run_gap_severity((now - ref).total_seconds() / 3600)
        if sev:
            out["scheduled-run-gap"] = sev
    streak = 0
    for r in runs:
        c = r.get("conclusion")
        if c in ("cancelled", "skipped", None):
            continue
        if c in ("failure", "timed_out"):
            streak += 1
        else:
            break
    if streak >= 3:
        out["consecutive-failures"] = "critical"
    return out


def full_fetch_sim(runs, record_legacy=False):
    """17.3 (v0.7, F8, F12): the weekly full fetch is due when the run's ET weekday is Sunday and
    the group has no successful full fetch on that ET date yet; the window is full for a group
    with an unpublished series, when its weekly full fetch is due, and always for H.6. A full
    fetch is successful when its response was received and read: neither failed nor invalid for
    the group as a whole, so after a failed or invalid one the next Sunday run fetches in full
    again. `runs`: in time order, each {"now": datetime, "legacy": bool, "groups": {group:
    {"requested", "unpublished", "h6", "result"}}} with result "ok", "invalid", "failed" or None.
    A run before the boundary of 21.1 ("legacy") may have kept no full_fetches (the real Stage B
    files, v0.6 form): its full fetches are then not recorded and a group without an entry counts
    as never fetched in full; with `record_legacy` (its collector.json carried them, the v0.7 form
    of appendix G step 1) they are. Returns (plan, last):
    plan[i][group] is {"weekly", "full", "success"}; last[group] is the now of its last recorded
    successful full fetch."""
    last, plan = {}, []
    for r in runs:
        today = et_date(r["now"])
        row = {}
        for g, f in r["groups"].items():
            prev = last.get(g)
            weekly = today.weekday() == 6 and not (prev is not None and et_date(prev) == today)
            full = bool(f.get("unpublished") or f.get("h6") or weekly)
            ok = bool(f.get("requested")) and f.get("result") == "ok"
            row[g] = {"weekly": weekly, "full": full, "success": full and ok}
        if record_legacy or not r.get("legacy"):
            for g, x in row.items():
                if x["success"]:
                    last[g] = r["now"]
        plan.append(row)
    return plan, last


def hash_mismatch_note(data, want_sha):
    """21.2 (F2): the cause named when bytes do not match their recorded SHA-256 but would once
    every carriage return and line feed pair is turned back into a line feed."""
    if data is None or not isinstance(want_sha, str):
        return ""
    if b"\r\n" in data and sha256_hex(data.replace(b"\r\n", b"\n")) == want_sha:
        return " (line endings converted: a checkout made with conversion; clone with core.autocrlf=false, 21.2)"
    return ""


def response_record_problems(rec, body=None, n=None, host=None):
    """20.2 (v0.7, F1): a response record has exactly the twelve fields, each present; n, status
    and bytes are integers, the five header fields text or null, the others text; bytes and
    sha256 match the saved body when it is given; n and host match the expected ones when given.
    Readings for what the text only implies (the collection schema states them too): n at least
    1, status 100 to 599, url https on the record's host, requested_at a UTC time, sha256 lowercase."""
    if not isinstance(rec, dict):
        return ["the record is not a JSON object"]
    p = []
    missing = [f for f in RESPONSE_FIELDS if f not in rec]
    extra = sorted(set(rec) - set(RESPONSE_FIELDS))
    if missing:
        p.append(f"fields missing {missing}")
    if extra:
        p.append(f"fields not in 20.2 {extra}")
    for f in RESPONSE_INT_FIELDS:
        if f in rec and type(rec[f]) is not int:
            p.append(f"{f} {rec[f]!r} is not an integer")
    for f in ("host", "url", "requested_at", "sha256"):
        if f in rec and not isinstance(rec[f], str):
            p.append(f"{f} {rec[f]!r} is not text")
    for f in RESPONSE_HEADER_FIELDS:
        if f in rec and rec[f] is not None and not isinstance(rec[f], str):
            p.append(f"{f} {rec[f]!r} is neither text nor null")
    if type(rec.get("n")) is int and rec["n"] < 1:
        p.append(f"n {rec['n']} is not a request number from 1")
    if type(rec.get("status")) is int and not 100 <= rec["status"] <= 599:
        p.append(f"status {rec['status']} is not an HTTP status")
    if isinstance(rec.get("url"), str):
        u = urlsplit(rec["url"])
        if u.scheme != "https":
            p.append(f"url {rec['url'][:60]!r} is not https (20.2)")
        if isinstance(rec.get("host"), str) and u.hostname != rec["host"]:
            p.append(f"host {rec['host']!r} is not the url's host {u.hostname!r}")
    if isinstance(rec.get("requested_at"), str) and not RX_TIME.fullmatch(rec["requested_at"]):
        p.append(f"requested_at {rec['requested_at']!r} is not a UTC time")
    if isinstance(rec.get("sha256"), str) and not re.fullmatch(r"[0-9a-f]{64}", rec["sha256"], re.ASCII):
        p.append(f"sha256 {rec['sha256'][:20]!r} is not 64 lowercase hex digits")
    if n is not None and rec.get("n") != n:
        p.append(f"n {rec.get('n')!r}, expected {n}")
    if host is not None and rec.get("host") != host:
        p.append(f"host {rec.get('host')!r}, expected {host!r}")
    if body is not None:
        if rec.get("bytes") != len(body):
            p.append(f"bytes {rec.get('bytes')!r} but the body has {len(body)} bytes")
        if sha256_hex(body) != rec.get("sha256"):
            p.append(f"sha256 does not match the body ({sha256_hex(body)[:16]})" + hash_mismatch_note(body, rec.get("sha256")))
    return p


def request_number_problems(ns):
    """20.2, 21.4 (amendment 2 to v0.8, I50): n numbers the requests sent, not the responses, so in
    request order the numbers of a run's records rise strictly from 1, each used once, and may skip
    the numbers of requests without an answer (records 1, 3 and 4 are valid when request 2 timed out).
    ns: the n of every record of one run, in request order. Returns (position in ns, problem) pairs:
    a number two records share, and a number not above that of the record before it. A value that
    is not an integer of at least 1 is the record's own problem (response_record_problems, which
    every caller runs on each record) and is passed over here; the next record is compared with the
    nearest earlier one whose number is valid (reading: the text names "the record before it" only
    for valid numbers). Reading: the first record may have any number from 1 (request 1 without an
    answer, its retry answered as request 2, gives records from 2); the text refuses only the cases
    it lists, and nothing it records counts the requests without an answer, so a gap is never checked."""
    p, seen, prev = [], set(), None
    for i, n in enumerate(ns):
        if type(n) is not int or n < 1:
            continue
        if n in seen:
            p.append((i, f"n {n} is also the number of an earlier record (20.2 amendment 2: each number used once)"))
        elif prev is not None and n <= prev:
            p.append((i, f"n {n} is not above {prev}, the number of the record before it (20.2 amendment 2: rising strictly in request order)"))
        seen.add(n)
        prev = n
    return p


def section_selftests_v07(st):
    """C7 (14.2, 14.3), C8 (17.3 weekly full fetch), C9 (20.2 response records): this checker's
    v0.7 rules on fixed cases, the boundaries included."""
    p = []

    def expect(label, got, want):
        if got != want:
            p.append(f"{label}: got {got!r}, expected {want!r}")

    # C7: the cron line fires at exactly the six listed UTC times, every day; the v0.6 lines differ.
    monday = dt.datetime(2026, 11, 23, tzinfo=UTC)
    fired = [monday + dt.timedelta(minutes=m) for m in range(7 * 24 * 60) if cron_fires(SCHEDULE_LINES[0], monday + dt.timedelta(minutes=m))]
    expect("17 */4 * * * fires 42 times in a week", len(fired), 42)
    expect("17 */4 * * * fires at the six times of 14.2", sorted({t.strftime("%H:%M") for t in fired}), list(SCHEDULE_UTC_TIMES))
    expect("17 */4 * * * fires on every weekday and weekend day", sorted({t.weekday() for t in fired}), list(range(7)))
    old = [t for t in (monday + dt.timedelta(minutes=m) for m in range(7 * 24 * 60)) if any(cron_fires(x, t) for x in SCHEDULE_LINES_V06)]
    expect("the v0.6 lines fire 24 times a weekday and once a weekend day", len(old), 24 * 5 + 2)
    expect("13:17 UTC Monday: v0.6 fires, v0.7 does not", (any(cron_fires(x, monday.replace(hour=13, minute=17)) for x in SCHEDULE_LINES_V06),
                                                          cron_fires(SCHEDULE_LINES[0], monday.replace(hour=13, minute=17))), (True, False))
    h = dt.timedelta(hours=1)
    s = dt.timedelta(seconds=1)
    now = dt.datetime(2026, 11, 23, 9, 17, tzinfo=UTC)
    ok = lambda t, ev="schedule", c="success": {"event": ev, "conclusion": c, "created_at": t}
    gap = lambda runs: schedule_health_findings(now, "active", now, runs).get("scheduled-run-gap")
    expect("two missed four-hour runs and an hour of delay, exactly 9 hours: no finding", gap([ok(now - 9 * h)]), None)
    expect("9 hours and one second: warning", gap([ok(now - 9 * h - s)]), "warning")
    expect("exactly 26 hours: still a warning", gap([ok(now - 26 * h)]), "warning")
    expect("26 hours and one second: critical", gap([ok(now - 26 * h - s)]), "critical")
    expect("a successful manual run is not a scheduled run", gap([ok(now - h, "workflow_dispatch"), ok(now - 10 * h)]), "warning")
    expect("a skipped scheduled run (gates off) is not a success", gap([ok(now - h, c="skipped"), ok(now - 27 * h)]), "critical")
    expect("none succeeded: hours since the oldest run listed", gap([ok(now - h, c="failure"), ok(now - 12 * h, c="failure")]), "warning")
    expect("no run listed at all: critical (14.3 v0.7, F13)", gap([]), "critical")
    cf = lambda cs: schedule_health_findings(now, "active", now, [ok(now - i * h, c=c) for i, c in enumerate(cs)]).get("consecutive-failures")
    expect("failure, cancelled, timed_out, skipped, failure: 3 in a row", cf(["failure", "cancelled", "timed_out", "skipped", "failure"]), "critical")
    expect("failure, failure, success, failure: 2 in a row", cf(["failure", "failure", "success", "failure"]), None)
    expect("the run in progress neither counts nor breaks the streak (14.3 v0.7)", cf([None, "failure", "failure", "failure"]), "critical")
    ia = lambda days: schedule_health_findings(now, "active", now - dt.timedelta(days=days), []).get("inactivity")
    expect("inactivity at 44.9 days, 45, 55", (ia(44.9), ia(45), ia(54.99), ia(55)), (None, "warning", "warning", "critical"))
    expect("a workflow that is not active", schedule_health_findings(now, "disabled_manually", now, []).get("workflow-disabled"), "critical")
    check("C7 schedule self-test (v0.7, F7, F13): the one cron line 17 */4 * * * fires at exactly 00:17, 04:17, 08:17, 12:17, 16:17 and 20:17 UTC every day and differs from the v0.6 lines; scheduled-run-gap over 9 hours a warning and over 26 critical, both boundaries excluded, counting scheduled successes only (or the oldest run listed), critical with no run listed; consecutive-failures (a run in progress neither counts nor breaks the streak), inactivity and workflow-disabled as 14.3 gives (14.2, 14.3, 21.3)", p)

    # C8: the weekly full fetch once per group per Sunday (ET).
    p = []
    T = lambda s_: parse_utc(s_)

    def g(requested=True, unpublished=False, h6=False, result="ok"):
        return {"requested": requested, "unpublished": unpublished, "h6": h6, "result": result if requested else None}

    sun1, sun2, sun3 = T("2026-11-22T16:17:00Z"), T("2026-11-22T20:17:00Z"), T("2026-11-23T04:17:00Z")
    plan, last = full_fetch_sim([{"now": sun1, "groups": {"effr": g()}}, {"now": sun2, "groups": {"effr": g()}}])
    expect("first Sunday run: weekly due, full", (plan[0]["effr"]["weekly"], plan[0]["effr"]["full"]), (True, True))
    expect("a later Sunday run after a successful full fetch that day: windowed", (plan[1]["effr"]["weekly"], plan[1]["effr"]["full"]), (False, False))
    expect("the last successful full fetch is the first Sunday run", last.get("effr"), sun1)
    plan, _ = full_fetch_sim([{"now": sun1, "groups": {"effr": g(result="failed")}}, {"now": sun2, "groups": {"effr": g()}}])
    expect("the first Sunday fetch failed: the next Sunday run fetches in full again", plan[1]["effr"]["full"], True)
    plan, last = full_fetch_sim([{"now": sun1, "groups": {"effr": g(result="invalid")}}, {"now": sun2, "groups": {"effr": g()}}])
    expect("the first Sunday response was invalid: not a successful full fetch, the next Sunday run repeats it (F12)", (plan[1]["effr"]["full"], last.get("effr")), (True, sun2))
    plan, _ = full_fetch_sim([{"now": sun1, "groups": {"effr": g(), "debt-total": g(requested=False)}}, {"now": sun2, "groups": {"effr": g(), "debt-total": g()}}])
    expect("a group not requested by the first Sunday run is due in full later that Sunday", plan[1]["debt-total"]["full"], True)
    sat = T("2026-11-22T03:17:00Z")  # 22:17 ET on Saturday 2026-11-21
    plan, _ = full_fetch_sim([{"now": sat, "groups": {"effr": g()}}, {"now": sun3, "groups": {"effr": g()}}])
    expect("03:17 UTC on a Sunday is Saturday in New York: not weekly", plan[0]["effr"]["weekly"], False)
    expect("04:17 UTC on a Monday is Sunday 23:17 in New York: weekly due", plan[1]["effr"]["weekly"], True)
    plan, _ = full_fetch_sim([{"now": sun1, "groups": {"effr": g()}}, {"now": sun3, "groups": {"effr": g()}}])
    expect("the Sunday 23:17 ET run after a successful 11:17 ET full fetch: not again", plan[1]["effr"]["full"], False)
    plan, _ = full_fetch_sim([{"now": T("2026-11-19T16:17:00Z"), "groups": {"m1-sa": g(h6=True)}}, {"now": sun1, "groups": {"m1-sa": g(h6=True)}}])
    expect("H.6 is always full, also on weekdays", plan[0]["m1-sa"]["full"], True)
    plan, _ = full_fetch_sim([{"now": T("2026-11-22T05:17:00Z"), "groups": {"effr": g(unpublished=True)}}, {"now": sun1, "groups": {"effr": g()}}])
    expect("a first publication earlier that Sunday (00:17 ET) is that day's full fetch", plan[1]["effr"]["full"], False)
    legacy_runs = [{"now": T("2026-11-22T05:17:00Z"), "legacy": True, "groups": {"effr": g(unpublished=True)}}, {"now": sun1, "groups": {"effr": g()}}]
    plan, last = full_fetch_sim(legacy_runs)
    expect("a full fetch before the boundary whose collector.json kept no full_fetches is not recorded: the group counts as never fetched in full (21.1)", (plan[1]["effr"]["full"], last.get("effr")), (True, sun1))
    plan, last = full_fetch_sim(legacy_runs, record_legacy=True)
    expect("a full fetch before the boundary whose collector.json carried full_fetches is recorded (21.1, appendix G step 1)", (plan[1]["effr"]["full"], last.get("effr")), (False, legacy_runs[0]["now"]))
    plan, _ = full_fetch_sim([{"now": T("2026-11-23T16:17:00Z"), "groups": {"effr": g()}}])
    expect("a Monday run: windowed", plan[0]["effr"]["full"], False)
    check("C8 weekly full fetch self-test (v0.7, F8, F12): once per group per Sunday (ET); a failed or invalid Sunday fetch is not successful and the next Sunday run repeats it; the ET date decides (03:17 UTC Sunday is Saturday, 04:17 UTC Monday is Sunday); H.6 and unpublished groups always full, and that counts as the day's full fetch; a v0.6 run's full fetch is not recorded (5, 17.1, 17.3, 21.1)", p)

    # C9: response records (20.2, F1).
    p = []
    body = b'{"refRates":[]}'
    good = {"n": 1, "host": "markets.newyorkfed.org", "url": "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2026-09-18&endDate=2026-11-16",
            "requested_at": "2026-11-16T20:17:01Z", "status": 200, "content_type": "application/json", "content_length": None, "etag": None,
            "last_modified": None, "date": "Mon, 16 Nov 2026 20:17:01 GMT", "bytes": len(body), "sha256": sha256_hex(body)}
    expect("a record with the twelve fields", response_record_problems(good, body, 1, "markets.newyorkfed.org"), [])
    for f in RESPONSE_FIELDS:
        expect(f"without {f}", bool(response_record_problems({k: v for k, v in good.items() if k != f}, body)), True)
    for k, v in (("base", "001-markets.newyorkfed.org"), ("headers", {}), ("error", None)):
        expect(f"an extra field {k}", bool(response_record_problems(dict(good, **{k: v}), body)), True)
    for k, v in (("n", "1"), ("status", "200"), ("bytes", str(len(body))), ("n", True), ("status", 200.5), ("content_length", 15), ("etag", 5),
                 ("url", None), ("sha256", None), ("requested_at", None), ("host", None), ("date", ["x"])):
        expect(f"{k} as {v!r}", bool(response_record_problems(dict(good, **{k: v}), body)), True)
    expect("bytes not the body's", bool(response_record_problems(dict(good, bytes=len(body) + 1), body)), True)
    expect("sha256 not the body's", bool(response_record_problems(dict(good, sha256="0" * 64), body)), True)
    expect("an http url", bool(response_record_problems(dict(good, url=good["url"].replace("https", "http", 1)), body)), True)
    expect("a host that is not the url's", bool(response_record_problems(dict(good, host="example.org"), body)), True)
    crlf = b'[\r\n1]'
    conv = response_record_problems(dict(good, bytes=len(crlf), sha256=sha256_hex(b'[\n1]')), crlf)
    expect("a body converted to CRLF is named 'line endings converted'", any("line endings converted" in x for x in conv), True)

    # 20.2, 21.4 (amendment 2 to v0.8, I50): the numbers of a run's records, in request order, as ST9 reads them
    def numbering(ns):
        per_record = [i for i, x in enumerate(ns) if response_record_problems(dict(good, n=x), body)]
        return sorted(set(per_record) | {i for i, _ in request_number_problems(ns)})

    expect("records 1, 2, 3", numbering([1, 2, 3]), [])
    expect("records 1, 3, 4 (request 2 had no answer)", numbering([1, 3, 4]), [])
    expect("records 2, 3 (request 1 had no answer, its retry is request 2)", numbering([2, 3]), [])
    expect("one record numbered 7", numbering([7]), [])
    expect("no record (every request unanswered, or none sent)", numbering([]), [])
    expect("records 1, 1 (a number used twice)", numbering([1, 1]), [1])
    expect("records 1, 2, 1 (a number used again later)", numbering([1, 2, 1]), [2])
    expect("records 2, 1 (falling)", numbering([2, 1]), [1])
    expect("records 1, 4, 3 (not above the record before it)", numbering([1, 4, 3]), [2])
    expect("records 0, 1 (zero)", numbering([0, 1]), [0])
    expect("records 1, -2 (negative)", numbering([1, -2]), [1])
    expect("records 1, 1.5 (not an integer)", numbering([1, 1.5]), [1])
    expect("records 1, '2' (text)", numbering([1, "2"]), [1])
    expect("records True, 2 (a boolean)", numbering([True, 2]), [0])
    expect("records 1, None (null)", numbering([1, None]), [1])
    expect("records 3, 1.5, 2: the next valid number is compared with 3", numbering([3, 1.5, 2]), [1, 2])
    expect("request_number_problems passes over invalid values (the record check names them)", request_number_problems([0, -1, 1.5, "2", True, None]), [])
    check("C9 response record self-test (v0.7, F1): exactly the twelve fields of 20.2, each present (header fields null allowed, never absent); n, status and bytes integers (a string, a boolean or a fraction refused), the others text; an extra field (base, headers, error) refused; bytes and sha256 must match the body, with the line endings diagnosis of 21.2; amendment 2 to v0.8 (I50): a run's record numbers rise strictly from 1 in request order and may skip (1, 3, 4 and 2, 3 valid; a repeated, falling, zero, negative, fractional, text or boolean number refused) (20.2, 21.4)", p)


def section_selftests_v04(st):
    """C2 and C3: the v0.4 time rules on fixed cases, computed with the committed registry
    and holiday table, so a later change to either shows here first."""
    p = []

    def expect(label, got, want):
        if got != want:
            p.append(f"{label}: got {got}, expected {want}")
    try:
        fd = st.registry["calendars"]["fiscaldata-release"]
        expect("21:15 on 2026-11-16, earliest reading (17.3: due)", fmt_utc(cal_instant(dt.date(2026, 11, 16), "21:15", fd, "earliest")), "2026-11-16T21:15:00Z")
        expect("21:15 on 2026-11-16, latest reading (14.2: deadlines)", fmt_utc(cal_instant(dt.date(2026, 11, 16), "21:15", fd, "latest")), "2026-11-17T02:15:00Z")
        expect("21:15 on 2026-07-01, latest reading in daylight time", fmt_utc(cal_instant(dt.date(2026, 7, 1), "21:15", fd, "latest")), "2026-07-02T01:15:00Z")
        dl, _ = deadline_for(st, "debt-total", "2026-11-12", {"total_count": "1"})
        expect("debt-total deadline after 2026-11-12: record 11-13, out 11-16 at 21:15 latest reading, plus 6 hours (14.2)", fmt_utc(dl), "2026-11-17T08:15:00Z")
        due, _ = deadline_for(st, "debt-total", "2026-11-12", {"total_count": "1"}, reading="earliest", grace=False)
        expect("debt-total expected publication of 2026-11-13 for due (17.3: earliest reading, no grace)", fmt_utc(due), "2026-11-16T21:15:00Z")
        gaps = [g["period"] for g in st.series["debt-total"].get("known_gaps", [])]
        expect("2019-04-03 is a documented gap of debt-total (2.3)", "2019-04-03" in gaps, True)
        expect("next unseen period after 2019-04-02 skips the documented gap 2019-04-03 (14.2)", next_unseen_period(st.series["debt-total"], "2019-04-02").isoformat(), "2019-04-04")
        dl, _ = deadline_for(st, "debt-total", "2019-04-02", {"total_count": "1"})
        expect("debt-total deadline after 2019-04-02: record 2019-04-04, out 04-05 21:15 EDT, plus 6 hours", fmt_utc(dl), "2019-04-06T07:15:00Z")
        dl, _ = deadline_for(st, "effr", "2026-11-12", None)
        expect("EFFR deadline after 2026-11-12: publication day 11-16 at 09:00 ET plus 6 hours", fmt_utc(dl), "2026-11-16T20:00:00Z")
        dl, _ = deadline_for(st, "m1-sa", "2026-09", {"data_release_date": "2026-10-27", "latest_release_date": "2026-10-27", "prepared": "x"})
        expect("H.6 deadline after the 2026-10-27 release: 2026-11-24 13:00 ET plus 6 hours", fmt_utc(dl), "2026-11-25T00:00:00Z")
        expect("the FOMC target has no deadline (14.2: it follows the EFFR)", deadline_for(st, "fomc-target", "2026-09-17", None)[0], None)
    except Exception as exc:
        p.append(f"{type(exc).__name__}: {exc}")
    check("C2 time rules self-test: an unknown zone gives the earliest instant for due and the latest for deadlines (4.5), the deadlines of 14.2 per source, and the next unseen period skipping documented gaps (14.2, 17.3)", p)

    p = []
    try:
        for day, want in (("2026-11-13", {}), ("2026-11-24", {}), ("2027-03-23", {}), ("2027-03-24", {"source-route-check:frb-releases": "warning"}),
                          ("2027-04-30", {"source-route-check:frb-releases": "warning"}), ("2027-05-01", {}), ("2027-06-23", {}),
                          ("2027-06-24", {"source-route-check:frb-releases": "warning"}), ("2027-07-31", {"source-route-check:frb-releases": "warning"}), ("2027-08-01", {})):
            got = {k: v[0] for k, v in route_alerts(st, parse_date(day)).items()}
            expect(f"route alerts on {day} with the registry's Board entries", got, want)
        probe = State()
        probe.registry = {"sources": {"x": {"route_notices": [{"date": "2027-06-01", "affects_registered_route": True}, {"date": "2027-09-01", "affects_registered_route": True}]}}}
        for day, want in (("2026-12-02", {}), ("2026-12-03", {"source-retirement:x": "warning"}), ("2027-04-01", {"source-retirement:x": "warning"}),
                          ("2027-04-02", {"source-retirement:x": "critical"}), ("2027-06-01", {"source-retirement:x": "critical"}), ("2028-01-01", {"source-retirement:x": "critical"})):
            got = {k: v[0] for k, v in route_alerts(probe, parse_date(day)).items()}
            expect(f"a retirement on 2027-06-01 (and one on 2027-09-01) seen on {day}", got, want)
        got = route_alerts(probe, parse_date("2027-07-01"))["source-retirement:x"][1].isoformat()
        expect("the earliest date that applies counts when a source has several (17.8)", got, "2027-06-01")
    except Exception as exc:
        p.append(f"{type(exc).__name__}: {exc}")
    check("C3 route alert self-test: source-route-check:<source> warning from 7 days before a route check's date to 30 days after; source-retirement:<source> warning from 180 days before, critical from 60 days before and after; none for the Board in November 2026 (17.8, 4.3)", p)

    for relpath in sorted(rel(p) for p in st.tree_files if p.suffix == ".json"):
        data = tree_bytes(relpath)
        if relpath in st.tree_json_errors:
            check(f"C1 {relpath} is canonical JSON (7, 12.8)", [st.tree_json_errors[relpath]])
            continue
        try:
            again = canon_bytes(st.tree_json[relpath])
        except ValueError as exc:
            check(f"C1 {relpath} is canonical JSON (7, 12.8)", [str(exc)])
            continue
        if again == data:
            check(f"C1 {relpath} is canonical JSON (7, 12.8)", [], f"{len(data)} bytes, sha256 {sha256_hex(data)[:16]}")
        else:
            i = next((k for k in range(min(len(again), len(data))) if again[k] != data[k]), min(len(again), len(data)))
            check(f"C1 {relpath} is canonical JSON (7, 12.8)", [f"bytes differ from the canonical form at offset {i} (file {len(data)} bytes, canonical {len(again)})"])


# ---------------------------------------------------------------------------
# Schemas (12.8)
# ---------------------------------------------------------------------------


def schema_for_path(relpath):
    if relpath == "manifest.json":
        return "manifest"
    if relpath == "status/runs.json":
        return "runs"
    if relpath.startswith("snapshots/"):
        return "snapshot"
    if relpath.startswith("objects/"):
        return "object"
    if relpath.startswith("revisions/"):
        return "revisions"
    return None


def section_schemas(st):
    for name, schema in sorted(st.schemas.items()):
        used = set()
        collect_keywords(schema, used)
        unknown = sorted(used - SUPPORTED_KEYWORDS - ANNOTATION_KEYWORDS)
        check(f"S0 {name}.schema.json uses only keywords this validator implements",
              [f"unsupported: {', '.join(unknown)}"] if unknown else [], ", ".join(sorted(used - ANNOTATION_KEYWORDS)))
    for relpath, value in sorted(st.tree_json.items()) if not LIVE_MODE else ():  # S1 reads the example tree: not in the live modes
        name = schema_for_path(relpath)
        if name is None:
            check(f"S1 {relpath} has a schema (12.8)", ["no schema in pipeline/schemas/ covers this path"])
            continue
        schema = manifest_schema_for(st, value) if name == "manifest" else st.schemas[name]
        label = "manifest/4 (built from the text)" if schema is not st.schemas.get(name) else f"{name}.schema.json"
        try:
            errs = schema_errors(value, schema)
        except SchemaKeywordError as exc:
            check(f"S1 {relpath} validates against {label} (12.8)", [f"validator cannot evaluate: {exc}"])
            continue
        check(f"S1 {relpath} validates against {label} (12.8)", errs)
    section_schemas_v04(st)
    section_schemas_v08(st)


def section_schemas_v08(st):
    """S7 (v0.8): manifest/4 (9) and deployments/1 (22.4) have no schema file in pipeline/schemas/;
    the checker builds both from the text (build_v08_shapes). The probes are documents the text
    accepts or refuses."""
    files = {doc.get("$id") for doc in (load_strict(x.read_bytes()) for x in sorted(SCHEMA_DIR.glob("*.json"))) if isinstance(doc, dict)}
    missing = [x for x in (MANIFEST_V4, DEPLOYMENTS_ID) if x not in files]
    sh = getattr(st, "v08_schemas", None) or build_v08_shapes(st)
    p, n = [], 0
    t, sha = "2026-11-24T15:00:00Z", "a" * 64

    by_id = {}
    for x in sorted(SCHEMA_DIR.glob("*.json")):
        try:
            doc = load_strict(x.read_bytes())
        except Exception:
            continue
        if isinstance(doc, dict) and doc.get("$id") in (MANIFEST_V4, DEPLOYMENTS_ID):
            by_id[doc["$id"]] = (x.name, doc)
    file_for = {"manifest-v4": by_id.get(MANIFEST_V4), "deployments": by_id.get(DEPLOYMENTS_ID)}

    def probe(label, name, doc, want):
        nonlocal n
        n += 1
        for which, schema in [("the checker's shape", sh[name])] + ([(file_for[name][0], file_for[name][1])] if file_for[name] else []):
            try:
                got = not schema_errors(doc, schema)
            except SchemaKeywordError as exc:
                p.append(f"{label}: {which}: cannot evaluate: {exc}")
                continue
            if got != want:
                p.append(f"{label}: {which} {'accepts' if got else 'refuses'} it, the text {'accepts' if want else 'refuses'} it")

    ds = {"snapshot": "20261124T150000Z", "manifest_sha256": sha}
    e = {"number": 1, "published_at": t, "run": "pub-123-1", "trigger": "manual", "dataset": ds, "release": "data-20261124T150000Z-123-1",
         "site_commit": "0" * 40, "artifact": {"files": 10, "bytes": 1000, "sha256": sha}, "previous": None,
         "verification": {"checker": {"pass": 5, "fail": 0, "skip": 0}, "post": None}}
    dep = {"schema": DEPLOYMENTS_ID, "deployments": [e]}
    probe("a deployment entry with the ten fields of 22.4", "deployments", dep, True)
    for f in e:
        probe(f"a deployment entry without {f} (22.4)", "deployments", dict(dep, deployments=[{k: v for k, v in e.items() if k != f}]), False)
    probe("a trigger outside manual, timer, redeploy (22.4)", "deployments", dict(dep, deployments=[dict(e, trigger="schedule")]), False)
    probe("post passed (22.4)", "deployments", dict(dep, deployments=[dict(e, verification={"checker": {"pass": 1, "fail": 0, "skip": 0}, "post": "passed"})]), True)
    probe("post 'success' (22.4: passed or failed)", "deployments", dict(dep, deployments=[dict(e, verification={"checker": {"pass": 1, "fail": 0, "skip": 0}, "post": "success"})]), False)
    probe("a 39-hex site_commit (22.4: 40-hex)", "deployments", dict(dep, deployments=[dict(e, site_commit="0" * 39)]), False)
    probe("an extra top-level field", "deployments", dict(dep, note="x"), False)
    m3, _ = None, None
    tree_m = st.tree_json.get("manifest.json") if hasattr(st, "tree_json") else None
    if isinstance(tree_m, dict):
        m4 = json.loads(json.dumps(tree_m))
        m4["schema"] = MANIFEST_V4
        m4["rules"] = {"registry": {"path": "registry/econ-" + "a" * 16 + ".json", "sha256": sha}, "holidays": {"path": "registry/holidays-" + "b" * 16 + ".json", "sha256": sha},
                       "notice": {"path": "notices/" + "c" * 16 + ".txt", "sha256": sha}, "registry_versions": []}
        for summ in m4.get("series", {}).values():
            summ.update(deadline=None, stale_at=None, revision_csvs=[])
        probe("the example tree's manifest with the v0.8 fields (9)", "manifest-v4", m4, True)
        probe("a manifest/4 without rules (9)", "manifest-v4", {k: v for k, v in m4.items() if k != "rules"}, False)
        sid0 = sorted(m4.get("series", {}))[0]
        for f in ("deadline", "stale_at", "revision_csvs"):
            bad = json.loads(json.dumps(m4))
            del bad["series"][sid0][f]
            probe(f"a manifest/4 series without {f} (9)", "manifest-v4", bad, False)
        bad = json.loads(json.dumps(m4))
        bad["series"][sid0]["revision_csvs"] = [{"path": "revisions/effr/2026/" + "d" * 16 + ".json", "sha256": sha}]
        probe("a revision CSV path ending .json (10)", "manifest-v4", bad, False)
        bad = json.loads(json.dumps(m4))
        bad["rules"]["notice"]["path"] = "NOTICE.txt"
        probe("rules.notice naming NOTICE.txt (22.9: outside the manifest)", "manifest-v4", bad, False)
        probe("a manifest/3 document under the manifest/4 shape", "manifest-v4", tree_m, False)
    check("S7 the v0.8 shapes built from the text: manifest/4 (9: deadline, stale_at, revision_csvs, rules) and deployments/1 (22.4) accept and refuse what the text does" +
          (f"; pipeline/schemas/ has no file for {', '.join(missing)} (the shapes are the checker's own, 12.8)" if missing else ""), p, f"{n} probes")


def _schema_accepts(schema, doc):
    try:
        return not schema_errors(doc, schema)
    except SchemaKeywordError:
        return None


def section_schemas_v04(st):
    """S2: the v0.4 schemas against the text (where they disagree the text wins, preamble).
    Each probe is a small document the text accepts or refuses."""
    sc = st.schemas
    p, n, loose = [], 0, []
    for name, want in SCHEMA_IDS.items():
        if sc[name].get("$id") != want:
            p.append(f"{name}.schema.json has $id {sc[name].get('$id')!r}, the text names {want} (4.1, 8, 9, 14.1, 17.5)")
        const = ((sc[name].get("properties") or {}).get("schema") or {}).get("const")
        if const != want:
            p.append(f"{name}.schema.json requires schema {const!r}, the text names {want}")

    def probe(label, schema_name, doc, want, enforced_by=None, bucket=None):
        """want: what the text says. A schema that refuses what the text accepts, or accepts a
        shape the text replaced, fails S2 (S4 for the v0.5 probes). A schema that accepts what
        the text refuses only through a rule JSON Schema leaves to the checker (order, repeats,
        a field tied to another) is listed by S3 with the check that enforces the rule instead."""
        nonlocal n
        n += 1
        out = p if bucket is None else bucket
        got = _schema_accepts(sc[schema_name], doc)
        if got is None:
            out.append(f"{label}: the validator cannot evaluate {schema_name}.schema.json")
        elif got != want:
            if got and not want and enforced_by:
                loose.append(f"{schema_name}.schema.json accepts {label}; enforced by {enforced_by}")
            else:
                out.append(f"{label}: {schema_name}.schema.json {'accepts' if got else 'refuses'} it, the text {'accepts' if want else 'refuses'} it")

    t = "2026-11-17T15:00:00Z"
    sha = "a" * 64
    # 14.1, 11.6: run records
    run = {"id": "r1", "trigger": "schedule", "started_at": t, "ended_at": t, "outcome": "no-change", "snapshot": None,
           "series": {"effr": "unchanged"}, "alerts": [], "absences": [{"series": "effr", "period": "2026-11-17", "kind": "expected-nonpublication", "detail": "not-yet-due"}]}
    probe("a run record with an absence (14.1)", "runs", {"schema": "rmf.econ.runs/2", "runs": [run]}, True)
    probe("a run record without absences (14.1: every record has the list)", "runs", {"schema": "rmf.econ.runs/2", "runs": [{k: v for k, v in run.items() if k != "absences"}]}, False)
    probe("a refused review run (14.1 outcome refused)", "runs", {"schema": "rmf.econ.runs/2", "runs": [dict(run, trigger="review", outcome="refused", series={}, absences=[])]}, True)
    for detail, kind in ABSENCE_KINDS.items():
        probe(f"absence kind {kind} with detail {detail} (11.6)", "runs", {"schema": "rmf.econ.runs/2", "runs": [dict(run, absences=[{"series": "effr", "period": "2026-11", "kind": kind, "detail": detail}])]}, True)
    probe("an absence kind outside the five of 11.6", "runs", {"schema": "rmf.econ.runs/2", "runs": [dict(run, absences=[{"series": "effr", "period": "2026-11-17", "kind": "late", "detail": "after-deadline"}])]}, False)
    probe("an absence whose detail belongs to another kind (11.6 table: after-deadline is source-overdue)", "runs",
          {"schema": "rmf.econ.runs/2", "runs": [dict(run, absences=[{"series": "effr", "period": "2026-11-17", "kind": "documented-gap", "detail": "after-deadline"}])]}, False,
          "T23 and T98 (detail to kind, 11.6 table)")
    # 9, 16: manifest CSV segments
    csv_ref = {"segment": "2026", "path": "series/effr/2026/" + "a" * 16 + ".csv", "sha256": sha, "retrieved_at": t}
    defs = sc["manifest"].get("$defs", {})
    csv_def = defs.get("csvRef")
    if csv_def is None:
        p.append("manifest.schema.json has no csvRef definition for the 9 csvs entries")
    else:
        wrap = dict(csv_def, **({"$defs": defs} if "$defs" not in csv_def else {}))
        for label, doc, want in (("a csvs entry with segment, path, sha256, retrieved_at (9)", csv_ref, True),
                                 ("a csvs entry without retrieved_at (9)", {k: v for k, v in csv_ref.items() if k != "retrieved_at"}, False),
                                 ("a full-history CSV path series/<id>/<16 hex>.csv (9: none is published)", dict(csv_ref, path="series/effr/" + "a" * 16 + ".csv"), False),
                                 ("a CSV path for segment all (16)", dict(csv_ref, segment="all", path="series/fomc-target/all/" + "b" * 16 + ".csv"), True)):
            n += 1
            got = _schema_accepts(wrap, doc)
            if got != want:
                p.append(f"{label}: the manifest schema {'accepts' if got else 'refuses'} it, the text {'accepts' if want else 'refuses'} it")
    ser_schema = (sc["manifest"].get("properties") or {}).get("series") or {}
    items = [x for x in [ser_schema.get("additionalProperties")] + list((ser_schema.get("patternProperties") or {}).values()) if isinstance(x, dict)]
    item = items[0] if items else {}
    if "$ref" in item:
        item = resolve_ref(sc["manifest"], item["$ref"])
    req = set((item or {}).get("required", []))
    if "csvs" not in req or "csv" in req or "csv" in (item or {}).get("properties", {}):
        p.append(f"the manifest series entry requires {sorted(req)}; 9 gives csvs and no csv")
    # 11.5, 17.5: decisions, review records, refusals
    pub = {"outcome": "published", "snapshot": "20261117T150000Z"}
    rec = {"schema": SCHEMA_IDS["review"], "series": "debt-total", "candidate_sha256": sha, "decision": "approve", "decided_at": t, "run": "r8",
           "reviewer": "example-maintainer", "reason": "checked", "hold": {"reason": "x", "opened_at": t}, "affected_periods": ["2019-12-31"],
           "changes": [], "reviewer_permission": "maintain", "permission_checked_at": t, "publication": pub}
    probe("a review record with permission, the time it was read and the publication outcome (17.5)", "review", rec, True)
    for f in ("reviewer_permission", "permission_checked_at", "publication"):
        probe(f"a review record without {f} (17.5)", "review", {k: v for k, v in rec.items() if k != f}, False)
    probe("a publication outcome outside published, frozen, withdrawn, cleared (17.5)", "review", dict(rec, publication={"outcome": "approved", "snapshot": "20261117T150000Z"}), False)
    for perm in REVIEW_PERMISSIONS_ALL:
        probe(f"a reviewer_permission {perm!r} as GitHub reports it (11.5)", "review", dict(rec, reviewer_permission=perm), True)
    probe("a reviewer_permission GitHub never reports (11.5)", "review", dict(rec, reviewer_permission="owner"), False)
    dec = {k: v for k, v in rec.items() if k not in ("schema", "hold", "changes")}
    dec["record"] = "reviews/debt-total/" + "a" * 16 + "-approve-20261117T150000Z.json"
    q = {"schema": SCHEMA_IDS["review-queue"], "open": [], "frozen": [], "decisions": [dec], "refusals": []}
    probe("a review queue decision with permission, its time and publication, record named with the decision time (17.1, 17.5)", "review-queue", q, True)
    probe("a decision record path without the decision time (17.1: the time is in the name)", "review-queue",
          dict(q, decisions=[dict(dec, record="reviews/debt-total/" + "a" * 16 + "-approve.json")]), False)
    probe("a review queue without refusals (17.5)", "review-queue", {k: v for k, v in q.items() if k != "refusals"}, False)
    ref = {"series": "debt-intragov", "candidate_sha256": sha, "decision": "approve", "reviewer": "example-reader", "reviewer_permission": "read",
           "permission_checked_at": t, "at": t, "run": "r13", "refused": "permission"}
    probe("a refusal with the 17.5 fields", "review-queue", dict(q, refusals=[ref]), True)
    probe("a refusal with nothing given (17.5: null when not given)", "review-queue",
          dict(q, refusals=[dict(ref, series=None, candidate_sha256=None, decision=None, reviewer=None, reviewer_permission=None, permission_checked_at=None, refused="not-held")]), True)
    for rule in ALL_REFUSAL_RULES:
        probe(f"a refusal by the rule {rule} (17.5)", "review-queue", dict(q, refusals=[dict(ref, refused=rule)]), True)
    probe("a refusal by a rule 17.5 does not name", "review-queue", dict(q, refusals=[dict(ref, refused="rate-limit")]), False)
    probe("a refusal carrying free text (17.5: no reason text is kept)", "review-queue", dict(q, refusals=[dict(ref, reason="please approve")]), False)
    # 4.2, 4.3, 4.5: registry/2
    reg = json.loads(json.dumps(st.registry))
    probe("the committed registry (4)", "registry", reg, True)
    bad = json.loads(json.dumps(st.registry))
    bad["family_policy"]["review"]["permissions"] = ["write", "maintain", "admin"]
    probe("review permissions in another order (4.2: exactly these three, in this order)", "registry", bad, False, "R3")
    bad = json.loads(json.dumps(st.registry))
    bad["family_policy"]["review"]["permissions"] = ["write", "write", "write"]
    probe("review permissions repeating one value (4.2)", "registry", bad, False, "R3")
    bad = json.loads(json.dumps(st.registry))
    bad["calendars"]["fiscaldata-release"]["publish_time_zone_candidates"] = ["UTC", "America/New_York"]
    probe("unknown-zone candidates in the other order (4.5: in that order)", "registry", bad, False, "R10 and R27")
    bad = json.loads(json.dumps(st.registry))
    bad["calendars"]["fiscaldata-release"]["publish_time_zone_candidates"] = ["UTC", "UTC"]
    probe("unknown-zone candidates repeating one zone (4.5: at least two of the two zones)", "registry", bad, False, "R10 and R27")
    bad = json.loads(json.dumps(st.registry))
    del bad["calendars"]["fiscaldata-release"]["publish_time_zone_candidates"]
    probe("an unknown zone without candidates (4.5: present exactly when the zone is unknown)", "registry", bad, False, "R10 and R27")
    bad = json.loads(json.dumps(st.registry))
    bad["calendars"]["nyfed-business-days"]["publish_time_zone_candidates"] = ["America/New_York", "UTC"]
    probe("candidates on a verified zone (4.5: present exactly when the zone is unknown)", "registry", bad, False, "R10")
    bad = json.loads(json.dumps(st.registry))
    bad["sources"]["frb-releases"]["route_notices"] = []
    probe("an empty route_notices list (4.3: not empty when present)", "registry", bad, False)
    bad = json.loads(json.dumps(st.registry))
    if bad["sources"]["frb-releases"].get("route_notices"):
        bad["sources"]["frb-releases"]["route_notices"][0]["affects_registered_route"] = "false"
        probe("a route notice whose affects_registered_route is not a boolean (4.3)", "registry", bad, False)
    # 11.5: approve and reject carry a permission and its time; withdrawn carries none.
    probe("an approve decision with a null reviewer_permission (11.5: required for a person's decision)", "review-queue",
          dict(q, decisions=[dict(dec, reviewer_permission=None, permission_checked_at=None)]), False, "T94")
    probe("a withdrawn decision carrying a reviewer_permission (17.5: null for withdrawn)", "review-queue",
          dict(q, decisions=[dict(dec, decision="withdrawn", reviewer=None, reason=None, record="reviews/debt-total/" + "a" * 16 + "-withdrawn-20261117T150000Z.json",
                                  publication={"outcome": "withdrawn", "snapshot": "20261117T150000Z"})]), False, "T94")
    n_v04 = n
    p4 = section_schemas_v05_probes(st, probe, rec, dec, q, ref, t, sha)
    n_v05 = n
    p5 = section_schemas_v06_probes(st, probe, q, t, sha)
    n_v06 = n
    p6 = section_schemas_v07_probes(st, probe, t, sha)
    check("S6 the v0.7 schemas agree with the text: the state descriptor state/2 (root always root, accepted, files without STATE.json), the promotion record accepted/1, the collection record collection/1 with the twelve response record fields of 20.2 and their types; state/1 refused for the v0.7 layout (20.2, 21.1, 21.2, 21.4, appendix F)", p6, f"{n - n_v06} probes")
    check("S2 the schemas agree with the text on what v0.7 kept from v0.4, under the v0.7 ids: $id and schema const registry/4, snapshot/2, manifest/3, runs/2, review/3, review-queue/4, rollback/1, state/1, state/2, accepted/1, collection/1; csvs entries; absences and their kinds; permissions, publication outcomes and refusal rules; registry review policy, unknown zones and route notices (4.1 to 4.5, 9, 11.5, 11.6, 14.1, 17.5, 20.3; the text wins)", p, f"{n_v04} probes")
    check("S4 the schemas agree with the text on the v0.5 shapes v0.6 keeps: snapshot frozen[].origin, manifest rollback.locked, the clear decision and its cleared outcome, review-queue frozen entries with origin, reviewer null for a rollback and locked_changes, the refusal rules not-locked and locked, the registry's user_agent, contact and refuse_zero; the older ids refused (4.3, 4.4, 8, 9, 11.5, 17.5, appendix D)", p4, f"{n_v05 - n_v04} probes")
    check("S5 the v0.6 schemas agree with the text on the v0.6 shapes: several locks per series in a snapshot and in the queue (one entry per lock), accepted_zeros entries, the rollback record rollback/1, the state descriptor state/1; registry/3 and review-queue/3 refused (4.4, 11.5, 17.5, 20.3, appendix E)", p5, f"{n - n_v05} probes")
    check("S3 where a schema is looser than the text, the rule is enforced by a named check of this checker (listed here as schema findings)", [],
          f"{len(loose)} looser rule(s): " + "; ".join(loose) if loose else "none")


def section_schemas_v05_probes(st, probe, rec, dec, q, ref, t, sha):
    """S4: documents the v0.5 text accepts or refuses, against the committed schemas."""
    p4 = []
    snap_key = next((k for k in sorted(st.tree_json) if k.startswith("snapshots/")), None)
    man = st.tree_json.get("manifest.json")
    if snap_key is None or not isinstance(man, dict):
        p4.append("the example tree has no snapshot or manifest to build probes from")
    else:
        snap = json.loads(json.dumps(st.tree_json[snap_key]))
        fz = {"series": "debt-intragov", "candidate_sha256": sha, "origin": "rejected", "frozen_at": t, "reason": "rejected by the reviewer"}
        probe("a snapshot frozen entry with origin rejected (8)", "snapshot", dict(snap, frozen=[fz]), True, bucket=p4)
        probe("a snapshot frozen entry with origin rolled-back (8)", "snapshot", dict(snap, frozen=[dict(fz, origin="rolled-back")]), True, bucket=p4)
        probe("a snapshot frozen entry without origin (8: v0.5 adds it)", "snapshot", dict(snap, frozen=[{k: v for k, v in fz.items() if k != "origin"}]), False, bucket=p4)
        probe("a snapshot frozen entry whose origin 11.5 does not name", "snapshot", dict(snap, frozen=[dict(fz, origin="expired")]), False, bucket=p4)
        probe("a snapshot with the v0.4 schema id rmf.econ.snapshot/1", "snapshot", dict(snap, schema="rmf.econ.snapshot/1"), False, bucket=p4)
        rb = {"from": "20261124T191700Z", "to": "20261119T221700Z", "at": "2026-11-24T20:00:00Z", "reason": "bad release", "locked": ["effr", "m1-sa"]}
        probe("a rollback with locked (9)", "manifest", dict(man, rollback=rb), True, bucket=p4)
        probe("a rollback that locks nothing (9: no series differs)", "manifest", dict(man, rollback=dict(rb, locked=[])), True, bucket=p4)
        probe("a rollback without locked (9: v0.5 adds it)", "manifest", dict(man, rollback={k: v for k, v in rb.items() if k != "locked"}), False, bucket=p4)
        probe("rollback.locked out of registry order (9: in registry order)", "manifest", dict(man, rollback=dict(rb, locked=["m1-sa", "effr"])), False, "T107", bucket=p4)
        probe("rollback.locked naming a series twice (9)", "manifest", dict(man, rollback=dict(rb, locked=["effr", "effr"])), False, "T107", bucket=p4)
        probe("rollback.locked naming an unregistered series (9)", "manifest", dict(man, rollback=dict(rb, locked=["gdp"])), False, "T107", bucket=p4)
        m2 = json.loads(json.dumps(man))
        first = sorted(m2.get("series", {}))[0] if m2.get("series") else None
        if first:
            m2["series"][first]["status"] = "frozen"
            probe("a manifest series with status frozen (9)", "manifest", m2, True, bucket=p4)
        probe("a manifest with the v0.4 schema id rmf.econ.manifest/2", "manifest", dict(man, schema="rmf.econ.manifest/2"), False, bucket=p4)
    clr = dict(rec, series="m1-sa", decision="clear", publication={"outcome": "cleared", "snapshot": "20261125T150000Z"},
               hold={"reason": "bad release", "opened_at": "2026-11-24T20:00:00Z"})
    probe("a clear review record: publication cleared, the lock's reason and frozen_at under hold (17.5)", "review", clr, True, bucket=p4)
    probe("a clear review record whose publication is published (17.5: clear gives cleared)", "review", dict(clr, publication={"outcome": "published", "snapshot": "20261125T150000Z"}), False, "T96", bucket=p4)
    probe("a review record with the v0.4 schema id rmf.econ.review/2", "review", dict(rec, schema="rmf.econ.review/2"), False, bucket=p4)
    lock = {"series": "debt-intragov", "candidate_sha256": sha, "origin": "rejected", "frozen_at": t, "run": "r14", "reviewer": "example-writer",
            "reason": "rejected", "affected_periods": ["2026-11-17"], "locked_changes": [{"period": "2026-11-17", "field": "value"}]}
    probe("a queue frozen entry with origin and locked_changes (17.5)", "review-queue", dict(q, frozen=[lock]), True, bucket=p4)
    probe("a queue frozen entry of a rollback, reviewer null (17.5)", "review-queue", dict(q, frozen=[dict(lock, origin="rolled-back", reviewer=None, run="r18")]), True, bucket=p4)
    for f in ("origin", "locked_changes", "run"):
        probe(f"a queue frozen entry without {f} (17.5)", "review-queue", dict(q, frozen=[{k: v for k, v in lock.items() if k != f}]), False, bucket=p4)
    probe("a rejected lock whose reviewer is null (17.5: null only for a rollback)", "review-queue", dict(q, frozen=[dict(lock, reviewer=None)]), False, "T109", bucket=p4)
    probe("a locked change whose field section 10 does not name", "review-queue", dict(q, frozen=[dict(lock, locked_changes=[{"period": "2026-11-17", "field": "colour"}])]), False, "T109", bucket=p4)
    cdec = dict(dec, series="m1-sa", decision="clear", record="reviews/m1-sa/" + "a" * 16 + "-clear-20261125T150000Z.json",
                publication={"outcome": "cleared", "snapshot": "20261125T150000Z"})
    probe("a clear decision in the queue, publication cleared, record named <16 hex>-clear-<time> (17.1, 17.5)", "review-queue", dict(q, decisions=[cdec]), True, bucket=p4)
    probe("a clear refused by not-locked (17.5)", "review-queue", dict(q, refusals=[dict(ref, decision="clear", refused="not-locked")]), True, bucket=p4)
    probe("an approve refused by locked (17.5)", "review-queue", dict(q, refusals=[dict(ref, refused="locked")]), True, bucket=p4)
    probe("an approve refused by not-locked (17.5: that rule refuses only clear)", "review-queue", dict(q, refusals=[dict(ref, refused="not-locked")]), False, "T95", bucket=p4)
    probe("a clear refused by locked (17.5: that rule refuses only approve and reject)", "review-queue", dict(q, refusals=[dict(ref, decision="clear", refused="locked")]), False, "T95", bucket=p4)
    probe("a review queue with the v0.4 schema id rmf.econ.review-queue/2", "review-queue", dict(q, schema="rmf.econ.review-queue/2"), False, bucket=p4)
    probe("a review queue with the v0.5 schema id rmf.econ.review-queue/3", "review-queue", dict(q, schema="rmf.econ.review-queue/3"), False, bucket=p4)

    def reg_with(fn):
        r = json.loads(json.dumps(st.registry))
        fn(r)
        return r

    def set_rq(src, key, value):
        return lambda r: r["sources"][src]["request"].__setitem__(key, value)
    probe("a request with the project contact address (4.3)", "registry", reg_with(set_rq("fiscaldata", "contact", PROJECT_CONTACT)), True, bucket=p4)
    probe("a request with another contact address (4.3: null or the project address)", "registry", reg_with(set_rq("fiscaldata", "contact", "someone@example.com")), False, bucket=p4)
    probe("a request without contact (4.3: a required field)", "registry", reg_with(lambda r: r["sources"]["fiscaldata"]["request"].pop("contact")), False, bucket=p4)
    probe("the v0.4 user_agent 'generic' (4.3: the exact header, RadMage Finance and its URL)", "registry", reg_with(set_rq("nyfed-markets", "user_agent", "generic")), False, bucket=p4)
    probe("a browser user_agent (4.3: never a browser's)", "registry", reg_with(set_rq("nyfed-markets", "user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")), False, bucket=p4)
    probe("a user_agent with the URL changed (4.3: exactly)", "registry", reg_with(set_rq("frb-releases", "user_agent", "RadMage Finance (+https://radmagelabs.com/)")), False, bucket=p4)
    probe("a registry with the v0.4 schema id rmf.econ.registry/2", "registry", reg_with(lambda r: r.__setitem__("schema", "rmf.econ.registry/2")), False, bucket=p4)
    probe("a registry with the v0.5 schema id rmf.econ.registry/3", "registry", reg_with(lambda r: r.__setitem__("schema", "rmf.econ.registry/3")), False, bucket=p4)

    def set_era(sid, key, value):
        def fn(r):
            for s in r["series"]:
                if s["id"] == sid:
                    for e in s["extract"]:
                        e[key] = value
        return fn
    probe("refuse_zero as a text (4.4: a boolean)", "registry", reg_with(set_era("debt-total", "refuse_zero", "true")), False, bucket=p4)
    probe("refuse_zero false on a debt era (2.3, 4.4: the three debt series carry it, true)", "registry", reg_with(set_era("debt-total", "refuse_zero", False)), False, "R29", bucket=p4)
    probe("refuse_zero dropped from a debt era (2.3)", "registry", reg_with(lambda r: [e.pop("refuse_zero", None) for s in r["series"] if s["id"] == "debt-intragov" for e in s["extract"]]), False, "R29", bucket=p4)
    probe("refuse_zero on the FOMC target, whose lower bound was 0.00 (2.3 names the debt eras only)", "registry", reg_with(set_era("fomc-target", "refuse_zero", True)), False, "R29", bucket=p4)
    return p4


ACCEPTED_ZERO_FIELDS = ("period", "field", "checked", "evidence", "authorized_by", "authorized_at")  # 4.4 (v0.6)


def section_schemas_v06_probes(st, probe, q, t, sha):
    """S5: documents the v0.6 text accepts or refuses, against the committed schemas."""
    p5 = []
    snap_key = next((k for k in sorted(st.tree_json) if k.startswith("snapshots/")), None)
    if snap_key is None:
        p5.append("the example tree has no snapshot to build probes from")
    else:
        snap = json.loads(json.dumps(st.tree_json[snap_key]))
        fz = {"series": "debt-intragov", "candidate_sha256": sha, "origin": "rejected", "frozen_at": t, "reason": "rejected by the reviewer"}
        # 11.5 (v0.6): a series may carry several locks; a lock is identified by series, origin and candidate hash.
        probe("a snapshot with a rejected and a rolled-back lock on one series (11.5: several locks per series)", "snapshot",
              dict(snap, frozen=[fz, dict(fz, origin="rolled-back", candidate_sha256="b" * 64)]), True, bucket=p5)
        probe("a snapshot with two rejected locks of one series on different candidates (11.5)", "snapshot",
              dict(snap, frozen=[fz, dict(fz, candidate_sha256="c" * 64)]), True, bucket=p5)
        probe("a snapshot listing the same lock twice (11.5: series, origin and hash identify a lock)", "snapshot", dict(snap, frozen=[fz, dict(fz)]), False, "T44", bucket=p5)
    lock = {"series": "debt-intragov", "candidate_sha256": sha, "origin": "rejected", "frozen_at": t, "run": "r14", "reviewer": "example-writer",
            "reason": "rejected", "affected_periods": ["2026-11-16"], "locked_changes": [{"period": "2026-11-16", "field": "period"}]}
    probe("a review-queue/4 with one frozen entry per lock, a series twice (17.5 v0.6)", "review-queue",
          dict(q, frozen=[lock, dict(lock, origin="rolled-back", reviewer=None, run="r18", candidate_sha256="b" * 64)]), True, bucket=p5)
    probe("a rejected lock whose locked change is a new period (11.5 v0.6: new periods count)", "review-queue", dict(q, frozen=[lock]), True, bucket=p5)
    probe("the same lock listed twice in the queue (17.5: one entry per lock)", "review-queue", dict(q, frozen=[lock, dict(lock)]), False, "T109", bucket=p5)

    def reg_with(fn):
        r = json.loads(json.dumps(st.registry))
        fn(r)
        return r

    def with_zero(sid, entries):
        def fn(r):
            for s in r["series"]:
                if s["id"] == sid:
                    s["accepted_zeros"] = entries
        return fn
    az = {"period": "2026-11-10", "field": "value", "checked": "2026-11-19", "evidence": "Fiscal Data API response of 2026-11-19 gives \"0.00\" for this record date",
          "authorized_by": "example-maintainer", "authorized_at": "2026-11-19T15:00:00Z"}
    probe("an accepted_zeros entry with the six 4.4 fields on a debt series (2.3, 4.4)", "registry", reg_with(with_zero("debt-intragov", [az])), True, bucket=p5)
    for f in ACCEPTED_ZERO_FIELDS:
        probe(f"an accepted_zeros entry without {f} (4.4)", "registry", reg_with(with_zero("debt-intragov", [{k: v for k, v in az.items() if k != f}])), False, bucket=p5)
    probe("an accepted_zeros entry naming a source field instead of value (4.4: field value)", "registry", reg_with(with_zero("debt-intragov", [dict(az, field="intragov_hold_amt")])), False, bucket=p5)
    probe("an accepted_zeros entry with a range of periods (2.3: no ranges)", "registry", reg_with(with_zero("debt-intragov", [dict(az, period="2026-11-01/2026-11-30")])), False, bucket=p5)
    probe("an accepted_zeros entry with a pattern (2.3: no patterns)", "registry", reg_with(with_zero("debt-intragov", [dict(az, period="2026-11-*")])), False, bucket=p5)
    probe("an accepted_zeros entry with an extra field (4: unknown fields fail validation)", "registry", reg_with(with_zero("debt-intragov", [dict(az, until="2027-01-01")])), False, bucket=p5)
    probe("an accepted_zeros entry authorized by a bot (4.4: the GitHub login of a person)", "registry", reg_with(with_zero("debt-intragov", [dict(az, authorized_by="dependabot[bot]")])), False, bucket=p5)
    probe("an accepted_zeros entry with authorized_at not in UTC (4.4: the time, UTC)", "registry", reg_with(with_zero("debt-intragov", [dict(az, authorized_at="2026-11-19T10:00:00-05:00")])), False, bucket=p5)
    probe("an accepted_zeros entry with an empty evidence text (4.4)", "registry", reg_with(with_zero("debt-intragov", [dict(az, evidence="")])), False, bucket=p5)
    probe("an accepted_zeros period after the ET date of authorized_at (4.4: on or before)", "registry", reg_with(with_zero("debt-intragov", [dict(az, period="2026-11-20")])), False, "R30", bucket=p5)
    probe("two accepted_zeros entries for one period (4.4: periods unique)", "registry", reg_with(with_zero("debt-intragov", [az, dict(az, evidence="again")])), False, "R30", bucket=p5)
    probe("accepted_zeros on the EFFR, whose eras carry no refuse_zero (4.4: only on such a series)", "registry", reg_with(with_zero("effr", [dict(az, period="2026-11-10")])), False, "R30", bucket=p5)
    probe("an accepted_zeros period that is a month on a business-day series (4.4: one period of the series)", "registry", reg_with(with_zero("debt-intragov", [dict(az, period="2026-11")])), False, "R30", bucket=p5)
    # 17.5 (v0.6): the rollback record.
    rb = {"schema": SCHEMA_IDS["rollback"], "from": "20261124T191700Z", "to": "20261119T221700Z", "at": "2026-11-24T20:00:00Z", "run": "r18", "reason": "bad release",
          "locks": [{"series": "effr", "origin": "rolled-back", "candidate_sha256": sha, "locked_changes": [{"period": "2026-11-20", "field": "period"}]},
                    {"series": "debt-intragov", "origin": "rejected", "candidate_sha256": "b" * 64, "locked_changes": [{"period": "2026-11-16", "field": "period"}]}]}
    probe("a rollback record with from, to, at, run, reason and locks of both origins (17.5)", "rollback", rb, True, bucket=p5)
    probe("a rollback record that adds no lock (17.5: locks may be empty)", "rollback", dict(rb, locks=[]), True, bucket=p5)
    for f in ("from", "to", "at", "run", "reason", "locks"):
        probe(f"a rollback record without {f} (17.5)", "rollback", {k: v for k, v in rb.items() if k != f}, False, bucket=p5)
    for f in ("series", "origin", "candidate_sha256", "locked_changes"):
        probe(f"a rollback record lock without {f} (17.5)", "rollback", dict(rb, locks=[{k: v for k, v in rb["locks"][0].items() if k != f}]), False, bucket=p5)
    probe("a rollback record lock with frozen_at (17.5 names series, origin, candidate_sha256, locked_changes only)", "rollback", dict(rb, locks=[dict(rb["locks"][0], frozen_at=t)]), False, bucket=p5)
    probe("a rollback record lock of an origin 11.5 does not name", "rollback", dict(rb, locks=[dict(rb["locks"][0], origin="expired")]), False, bucket=p5)
    probe("a rollback record whose to is not a snapshot id (17.5: to is the target snapshot)", "rollback", dict(rb, to="2026-11-19T22:17:00Z"), False, bucket=p5)
    probe("a rollback record whose locks are not in registry order (17.5: registry order then origin)", "rollback", dict(rb, locks=list(reversed(rb["locks"]))), False, "T115", bucket=p5)
    probe("a rollback record lock whose locked change names a field section 10 does not name", "rollback",
          dict(rb, locks=[dict(rb["locks"][0], locked_changes=[{"period": "2026-11-20", "field": "colour"}])]), False, "T115", bucket=p5)
    probe("a rollback record whose run id is not in the 17.2 form", "rollback", dict(rb, run="run 18/x"), False, "T115", bucket=p5)
    probe("a rollback record with another schema id", "rollback", dict(rb, schema="rmf.econ.rollback/0"), False, bucket=p5)
    # 20.3 (v0.6): STATE.json.
    stt = {"schema": SCHEMA_IDS["state"], "run": "stage-b-1", "written_at": "2026-11-20T15:00:00Z", "root": "unpublished/stage-b-1", "manifest_sha256": sha,
           "files": [{"path": "state/review-queue.json", "sha256": sha, "bytes": 120}, {"path": "state/run-records/stage-b-1.json", "sha256": "b" * 64, "bytes": 900}]}
    probe("a state descriptor with run, written_at, root, manifest_sha256 and files (20.3)", "state", stt, True, bucket=p5)
    probe("a state descriptor whose root has no published manifest (20.3: manifest_sha256 null)", "state", dict(stt, manifest_sha256=None), True, bucket=p5)
    for f in ("run", "written_at", "root", "manifest_sha256", "files"):
        probe(f"a state descriptor without {f} (20.3)", "state", {k: v for k, v in stt.items() if k != f}, False, bucket=p5)
    probe("a state descriptor whose root is not under unpublished/ (20.1: candidate data is kept in unpublished/<run id>/)", "state", dict(stt, root="live"), False, bucket=p5)
    probe("a state descriptor whose root escapes unpublished/ (20.1)", "state", dict(stt, root="unpublished/../state"), False, bucket=p5)
    probe("a state file outside state/ (20.1: state/ holds the state files)", "state", dict(stt, files=[{"path": "unpublished/x/live/manifest.json", "sha256": sha, "bytes": 1}]), False, bucket=p5)
    probe("a state file entry without its SHA-256 (20.3)", "state", dict(stt, files=[{"path": "state/review-queue.json", "bytes": 1}]), False, bucket=p5)
    probe("a state descriptor with a root of null (20.1: a run always commits its root; the text gives no null root)", "state", dict(stt, root=None), False, "SB1 in the state mode (a Stage B STATE.json must name its root)", bucket=p5)
    return p5


def section_schemas_v07_probes(st, probe, t, sha):
    """S6: documents the v0.7 text accepts or refuses, against the committed schemas."""
    p6 = []
    ident = {"snapshot": "20261116T161700Z", "manifest_sha256": sha}
    # 21.2: STATE.json rmf.econ.state/2
    s2 = {"schema": SCHEMA_IDS["state-v2"], "run": "sched-1-1", "written_at": t, "root": "root", "manifest_sha256": sha, "accepted": ident,
          "files": [{"path": "state/accepted.json", "sha256": sha, "bytes": 900}, {"path": "state/alerts.json", "sha256": "b" * 64, "bytes": 40}]}
    probe("a state/2 descriptor (21.2)", "state-v2", s2, True, bucket=p6)
    for f in ("schema", "run", "written_at", "root", "manifest_sha256", "accepted", "files"):
        probe(f"a state/2 descriptor without {f} (21.2)", "state-v2", {k: v for k, v in s2.items() if k != f}, False, bucket=p6)
    probe("a state/2 descriptor with no manifest: manifest_sha256 and accepted null (21.2)", "state-v2", dict(s2, manifest_sha256=None, accepted=None), True, bucket=p6)
    probe("a state/2 descriptor whose root is a Stage B folder (21.2: root is always root)", "state-v2", dict(s2, root="unpublished/live-1-1"), False, bucket=p6)
    probe("a state/2 descriptor with the state/1 id (21.2)", "state-v2", dict(s2, schema=SCHEMA_IDS["state"]), False, bucket=p6)
    probe("a state/1 descriptor of the v0.7 layout (20.3 keeps state/1 for the Stage B layout only)", "state", dict(s2, schema=SCHEMA_IDS["state"]), False, bucket=p6)
    probe("a state/2 descriptor listing state/STATE.json (21.2: STATE.json itself is not listed)", "state-v2",
          dict(s2, files=s2["files"] + [{"path": "state/STATE.json", "sha256": sha, "bytes": 1}]), False, bucket=p6)
    probe("a state/2 descriptor with an extra field (21.2)", "state-v2", dict(s2, note="x"), False, bucket=p6)
    probe("an accepted identifier without manifest_sha256 (21.1: the pair)", "state-v2", dict(s2, accepted={"snapshot": ident["snapshot"]}), False, bucket=p6)
    probe("an accepted identifier whose snapshot is not a snapshot id (21.1)", "state-v2", dict(s2, accepted=dict(ident, snapshot="2026-11-16T16:17:00Z")), False, bucket=p6)
    probe("an accepted identifier with an extra field (21.1)", "state-v2", dict(s2, accepted=dict(ident, at=t)), False, bucket=p6)
    probe("a state file path escaping state/ (21.2: each state file's path)", "state-v2",
          dict(s2, files=[{"path": "state/../root/live/manifest.json", "sha256": sha, "bytes": 1}]), False, "ST4 (every listed path is a file under state/)", bucket=p6)
    probe("state files not sorted by path (21.2: sorted by path)", "state-v2", dict(s2, files=list(reversed(s2["files"]))), False, "ST4", bucket=p6)
    probe("a state file listed twice (21.2)", "state-v2", dict(s2, files=s2["files"] + [s2["files"][1]]), False, "ST4", bucket=p6)
    probe("accepted null while a manifest exists (21.2: null with no manifest only)", "state-v2", dict(s2, accepted=None), False, "ST5", bucket=p6)
    probe("accepted naming another manifest than manifest_sha256 (21.2)", "state-v2", dict(s2, accepted=dict(ident, manifest_sha256="c" * 64)), False, "ST5", bucket=p6)
    probe("a state/2 run id with a slash (17.2 run ids)", "state-v2", dict(s2, run="sched/1"), False, bucket=p6)
    probe("a state/2 written_at with an offset (3: UTC with Z)", "state-v2", dict(s2, written_at="2026-11-16T15:17:00-05:00"), False, bucket=p6)
    # 21.1: state/accepted.json rmf.econ.accepted/1
    acc = {"schema": SCHEMA_IDS["accepted"], "dataset": ident,
           "source": {"store_commit": "1" * 40, "root": "unpublished/live-1-1", "run": "live-1-1"},
           "verification": {"checker": {"mode": "live", "pass": 250, "fail": 0, "skip": 0}, "state": "ok", "at": t},
           "decision": {"brief": "docs/P26_STAGE_B_ACCEPTANCE_STAGE_C.md", "decided_on": "2026-11-19"},
           "promoted_at": t, "promoted_by": "example-maintainer", "run": "promote-1-1"}
    probe("a promotion record (21.1)", "accepted", acc, True, bucket=p6)
    for f in ("schema", "dataset", "source", "verification", "decision", "promoted_at", "promoted_by", "run"):
        probe(f"a promotion record without {f} (21.1)", "accepted", {k: v for k, v in acc.items() if k != f}, False, bucket=p6)
    for part, keys in (("source", ("store_commit", "root", "run")), ("verification", ("checker", "state", "at")), ("decision", ("brief", "decided_on"))):
        for f in keys:
            probe(f"a promotion record whose {part} lacks {f} (21.1)", "accepted", dict(acc, **{part: {k: v for k, v in acc[part].items() if k != f}}), False, bucket=p6)
    for f in ("mode", "pass", "fail", "skip"):
        probe(f"a promotion record whose checker lacks {f} (21.1)", "accepted",
              dict(acc, verification=dict(acc["verification"], checker={k: v for k, v in acc["verification"]["checker"].items() if k != f})), False, bucket=p6)
    probe("a promotion verified with a FAIL (21.1: fail 0)", "accepted", dict(acc, verification=dict(acc["verification"], checker=dict(acc["verification"]["checker"], fail=1))), False, bucket=p6)
    probe("a promotion verified by the plain mode, not live (21.1)", "accepted", dict(acc, verification=dict(acc["verification"], checker=dict(acc["verification"]["checker"], mode="plain"))), False, bucket=p6)
    probe("a promotion whose state verification is not ok (21.1)", "accepted", dict(acc, verification=dict(acc["verification"], state="partial")), False, bucket=p6)
    probe("a promotion whose source root is not a Stage B folder (21.1: unpublished/<run id>)", "accepted", dict(acc, source=dict(acc["source"], root="root")), False, bucket=p6)
    probe("a promotion whose source run is not the folder's run (21.1)", "accepted", dict(acc, source=dict(acc["source"], run="live-9-9")), False, "ST7", bucket=p6)
    probe("a promotion started by an automation account (21.6: automation accounts are refused)", "accepted", dict(acc, promoted_by="github-actions[bot]"), False, "ST7", bucket=p6)
    probe("a promotion record with an extra field (21.1)", "accepted", dict(acc, note="x"), False, bucket=p6)
    probe("a promotion whose decision date is a time (21.1: its date)", "accepted", dict(acc, decision=dict(acc["decision"], decided_on=t)), False, bucket=p6)
    probe("a promotion whose brief is a bare file name (21.1 v0.7: the path docs/<name>.md)", "accepted", dict(acc, decision=dict(acc["decision"], brief="P26_STAGE_B_ACCEPTANCE_STAGE_C.md")), False, bucket=p6)
    probe("a promotion whose dataset is not the pair (21.1)", "accepted", dict(acc, dataset={"manifest_sha256": sha}), False, bucket=p6)
    # 21.4: runs/<run id>.json rmf.econ.collection/1, with the 20.2 response records
    resp = {"n": 1, "host": "markets.newyorkfed.org", "url": "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2026-09-18&endDate=2026-11-16",
            "requested_at": t, "status": 200, "content_type": "application/json", "content_length": "100", "etag": None, "last_modified": None,
            "date": "Mon, 16 Nov 2026 20:17:01 GMT", "bytes": 100, "sha256": sha}
    cr = {"schema": SCHEMA_IDS["collection"], "run": "sched-2-1", "trigger": "schedule", "operation": None, "started_at": t, "ended_at": t,
          "outcome": "no-change", "requests": [resp], "validation": {"checker": {"mode": "live", "pass": 250, "fail": 0, "skip": 0}, "state": "ok"},
          "accepted": ident, "freshness": [{"series": s["id"], "status": "fresh", "last_period": "2026-11-12", "deadline": t} for s in st.registry.get("series", [])],
          "expected_next_update_by": t, "added": {"files": 1, "bytes": 100}, "month_added_bytes": 100}
    probe("a collection record (21.4)", "collection", cr, True, bucket=p6)
    for f in cr:
        probe(f"a collection record without {f} (21.4)", "collection", {k: v for k, v in cr.items() if k != f}, False, bucket=p6)
    for f in RESPONSE_FIELDS:
        probe(f"a response record without {f} (20.2 F1: each always present)", "collection", dict(cr, requests=[{k: v for k, v in resp.items() if k != f}]), False, bucket=p6)
    probe("a response record with the five header fields null (20.2)", "collection",
          dict(cr, requests=[dict(resp, **{f: None for f in RESPONSE_HEADER_FIELDS})]), True, bucket=p6)
    for k, v, why in (("base", "001-markets.newyorkfed.org", "an extra field"), ("n", "1", "n as text"), ("status", "200", "status as text"),
                      ("bytes", "100", "bytes as text"), ("content_length", 100, "content_length as a number (20.2: the others text)"),
                      ("etag", 5, "etag as a number"), ("n", 0, "n 0 (20.2: from 1)"), ("url", "http://markets.newyorkfed.org/x", "an http url (20.2: only https)"),
                      ("sha256", "A" * 64, "an uppercase sha256"), ("requested_at", "2026-11-16 20:17:01", "requested_at not in the UTC form"),
                      ("url", None, "url null (20.2: text)"), ("host", None, "host null")):
        probe(f"a response record with {why}", "collection", dict(cr, requests=[dict(resp, **{k: v})]), False, bucket=p6)
    op = dict(cr, run="promote-1-1", trigger="operation", operation="promote", outcome="promoted", requests=[])
    probe("the promotion's collection record (21.4: trigger operation, operation promote, outcome promoted, no requests)", "collection", op, True, bucket=p6)
    for o in ("review", "rollback", "restore"):
        probe(f"an operation record for {o} (21.4)", "collection", dict(op, operation=o, outcome="published"), True, bucket=p6)
    probe("a collection record with a run record trigger (21.4: schedule, manual or operation)", "collection", dict(cr, trigger="review"), False, bucket=p6)
    probe("an operation 21.6 does not name", "collection", dict(op, operation="approve"), False, bucket=p6)
    probe("an outcome 14.1 and 21.4 do not name", "collection", dict(cr, outcome="accepted"), False, bucket=p6)
    probe("a collection record validated with a FAIL (21.3: no FAIL before any write)", "collection",
          dict(cr, validation={"checker": {"mode": "live", "pass": 250, "fail": 1, "skip": 0}, "state": "ok"}), False, bucket=p6)
    probe("a collection record validated by another mode (21.3: live)", "collection",
          dict(cr, validation={"checker": {"mode": "root", "pass": 250, "fail": 0, "skip": 0}, "state": "ok"}), False, bucket=p6)
    probe("a collection record without an accepted identifier (21.4: the identifier after the run)", "collection", dict(cr, accepted=None), False, bucket=p6)
    probe("a freshness status 21.4 does not name", "collection", dict(cr, freshness=[dict(cr["freshness"][0], status="late")]), False, bucket=p6)
    probe("a freshness deadline that is not a time", "collection", dict(cr, freshness=[dict(cr["freshness"][0], deadline="2026-11-17")]), False, bucket=p6)
    probe("a freshness entry with an extra field", "collection", dict(cr, freshness=[dict(cr["freshness"][0], note="x")]), False, bucket=p6)
    probe("added with a negative count", "collection", dict(cr, added={"files": -1, "bytes": 0}), False, bucket=p6)
    probe("a scheduled record naming an operation (21.4: operation null unless trigger operation)", "collection", dict(cr, operation="review"), False, "ST9", bucket=p6)
    probe("outcome promoted outside the promotion (21.4)", "collection", dict(cr, outcome="promoted"), False, "ST9", bucket=p6)
    probe("an operation record with requests (21.4: empty for an operation)", "collection", dict(op, requests=[resp]), False, "ST9", bucket=p6)
    # 20.2, 21.4 (amendment 2 to v0.8, I50): n numbers the requests sent, so the records' numbers rise strictly from 1 and may skip
    numbered = lambda *ns: dict(cr, requests=[dict(resp, n=x) for x in ns])
    probe("requests numbered 1, 3 and 4 (20.2 amendment 2: request 2 had no answer and keeps its number)", "collection", numbered(1, 3, 4), True, bucket=p6)
    probe("requests numbered 2 and 3 (20.2 amendment 2: request 1 had no answer, its retry is request 2)", "collection", numbered(2, 3), True, bucket=p6)
    probe("requests numbered 1 and 1 (20.2 amendment 2: each number used once)", "collection", numbered(1, 1), False, "ST9", bucket=p6)
    probe("requests numbered 2 and 1 (20.2 amendment 2: rising strictly in request order)", "collection", numbered(2, 1), False, "ST9", bucket=p6)
    for x, why in ((-1, "n -1"), (1.5, "n 1.5"), (True, "n true")):
        probe(f"requests numbered 1 and then {why} (20.2 amendment 2: an integer of at least 1)", "collection", numbered(1, x), False, bucket=p6)
    probe("freshness for one series only (21.4: every registered series, in registry order)", "collection", dict(cr, freshness=cr["freshness"][:1]), False, "ST14", bucket=p6)
    probe("freshness in reverse registry order (21.4)", "collection", dict(cr, freshness=list(reversed(cr["freshness"]))), False, "ST14", bucket=p6)
    return p6


# ---------------------------------------------------------------------------
# Objects (sections 6 and 7) and release dates (6.3)
# ---------------------------------------------------------------------------


def observation_key(o):
    return o.get("period") if "period" in o else o.get("effective")


def expected_released(st, ser, o, is_first, first_snapshot_et):
    """The release a stored record must carry under 6.3. Returns (expected dict or None,
    note). None means the data needed to decide is not available."""
    cal = st.registry["calendars"][ser["release"]["calendar"]]
    basis = ser["release"]["basis"]
    nr = {"basis": "not-recorded", "date": None}
    if ser["frequency"] == "change-point":
        if is_first:
            return nr, "the first change point"
        if basis == "rule" and o["effective"] >= cal.get("rule_valid_from", "9999"):
            return {"basis": "rule", "date": next_business_day(parse_date(o["effective"])).isoformat()}, "rule"
        return nr, f"before rule_valid_from {cal.get('rule_valid_from')}"
    p = o["period"]
    if basis == "rule":
        if p >= cal.get("rule_valid_from", "9999"):
            return {"basis": "rule", "date": next_business_day(parse_date(p)).isoformat()}, "rule"
        return nr, f"before rule_valid_from {cal.get('rule_valid_from')}"
    if basis == "calendar":
        dates = h6_release_dates(st)
        if dates is None:
            return None, "releaseDates.json not available"
        after = [x for x in dates if x > month_end(p).isoformat()]
        if after and after[0] >= cal.get("calendar_valid_from", "9999"):
            return {"basis": "calendar", "date": after[0]}, "calendar"
        return nr, "release before calendar_valid_from"
    if basis == "first-seen":
        return {"basis": "first-seen", "date": first_snapshot_et.isoformat() if first_snapshot_et else None}, "first-seen"
    return None, f"basis {basis} unknown"


def object_semantics(st, obj, as_of_et):
    problems = []
    ser = st.series.get(obj.get("series"))
    if ser is None:
        return [f"series {obj.get('series')!r} is not registered"]
    freq, places = ser["frequency"], ser["decimals"]
    obs = obj.get("observations", [])
    seg = obj.get("segment")
    if ser["segment"] == "year":
        if not re.fullmatch(r"\d{4}", seg or "", re.ASCII):
            problems.append(f"segment {seg!r} is not a year for a year-segmented series")
    elif seg != "all":
        problems.append(f"segment {seg!r} should be 'all'")
    keys = [observation_key(o) for o in obs]
    if keys != sorted(keys) or len(set(keys)) != len(keys):
        problems.append("periods are not strictly ascending and unique (6.2)")
    if not obs:
        problems.append("object has no observations")
    min_v, max_v = D(ser["range"]["min"]), D(ser["range"]["max"])
    ki = ki_periods(ser)
    for i, o in enumerate(obs):
        where = f"{keys[i]}"
        if freq == "change-point":
            if "effective" not in o:
                problems.append(f"{where}: an observation record in a change-point series")
                continue
            era = era_for(ser, o["effective"])
            if era is None:
                problems.append(f"{where}: no extract era covers this date")
                continue
            if o["kind"] != era.get("kind"):
                problems.append(f"{where}: kind {o['kind']} but the era in force is {era.get('kind')} (2.2)")
            if o["kind"] == "rate":
                if "value" not in o or "lower" in o or "upper" in o:
                    problems.append(f"{where}: a rate change point needs value only (6.1)")
                fields = ["value"]
            else:
                if "lower" not in o or "upper" not in o or "value" in o:
                    problems.append(f"{where}: a range change point needs lower and upper only (6.1)")
                elif D(o["lower"]) > D(o["upper"]):
                    problems.append(f"{where}: lower above upper")
                fields = ["lower", "upper"]
            for f in fields:
                if f in o:
                    if not exact_places(o[f], places):
                        problems.append(f"{where}: {f} {o[f]!r} does not have exactly {places} decimals (4.4)")
                    elif not (min_v <= D(o[f]) <= max_v):
                        problems.append(f"{where}: {f} {o[f]} outside range (4.4)")
            if o.get("starts_before_data") and i != 0:
                problems.append(f"{where}: starts_before_data on a change point that is not the first (6.1)")
            if i == 0 and o.get("starts_before_data") is not True:
                problems.append(f"{where}: the first change point lacks starts_before_data (2.2, 6.1)")
            if i == 0 and o["effective"] != ser["earliest"]:
                problems.append(f"{where}: first change point is not the series' earliest date {ser['earliest']}")
            if i > 0:
                prev = obs[i - 1]
                if (prev.get("kind"), prev.get("value"), prev.get("lower"), prev.get("upper")) == (o.get("kind"), o.get("value"), o.get("lower"), o.get("upper")):
                    problems.append(f"{where}: repeats the previous target (not a change)")
            if not is_business_day(parse_date(o["effective"])):
                problems.append(f"{where}: effective is not a New York Fed business day (2.2)")
            if parse_date(o["effective"]) > as_of_et:
                problems.append(f"{where}: after the run's ET date (6.2)")
            continue
        if "period" not in o:
            problems.append(f"{where}: a change point in a {freq} series")
            continue
        p = o["period"]
        if freq == "business-day":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", p, re.ASCII):
                problems.append(f"{where}: period is not YYYY-MM-DD")
                continue
            pd = parse_date(p)
            if pd.weekday() >= 5 and p not in ki:
                problems.append(f"{where}: weekend period not listed in known_inconsistencies (6.2, 11.4)")
            if seg != "all" and p[:4] != seg:
                problems.append(f"{where}: period outside segment {seg}")
            if pd > as_of_et:
                problems.append(f"{where}: after the run's ET date (6.2)")
        elif freq == "month":
            if not re.fullmatch(r"\d{4}-\d{2}", p, re.ASCII):
                problems.append(f"{where}: period is not YYYY-MM (5)")
                continue
        era = era_for(ser, p)
        if era is None:
            problems.append(f"{where}: no extract era covers this period")
            continue
        v = o.get("value")
        if v is None:
            m = o.get("missing")
            if not m:
                problems.append(f"{where}: value null without missing (6.1)")
            elif m.get("code") == era.get("missing_code"):
                if era.get("missing_code") == "not-published" and m.get("note") != "":
                    problems.append(f"{where}: not-published should carry an empty note (6.1)")
            elif m.get("code") in era.get("missing_codes", []):
                if m.get("note") != H6_STATUS_NOTE.get(m["code"]):
                    problems.append(f"{where}: note {m.get('note')!r} is not the codelist text for {m['code']} (2.4)")
            else:
                problems.append(f"{where}: missing code {m.get('code')!r} not allowed by its era (6.1)")
        else:
            if "missing" in o:
                problems.append(f"{where}: missing given with a value (6.1)")
            if not exact_places(v, places):
                problems.append(f"{where}: value {v!r} does not have exactly {places} decimals (6.1)")
            elif not (min_v <= D(v) <= max_v):
                problems.append(f"{where}: value {v} outside range (4.4)")
        allowed_extra = set((era.get("extra") or {}).values())
        extra = o.get("extra") or {}
        if set(extra) - allowed_extra:
            problems.append(f"{where}: extra fields {sorted(set(extra) - allowed_extra)} not named by era {era['schema']} (6.1)")
        for k, x in extra.items():
            if x is not None and k in EXTRA_PLACES and not exact_places(x, EXTRA_PLACES[k]):
                problems.append(f"{where}: extra {k} {x!r} does not have {EXTRA_PLACES[k]} places (5)")
        for fl in o.get("flags", []):
            if not re.fullmatch(r"r|footnote:\d+", fl, re.ASCII):
                problems.append(f"{where}: flag {fl!r}")
    size = len(canon_bytes(obj))
    if size > 2_000_000:
        problems.append(f"object is {size} bytes, over 2 MB (12.7)")
    return problems


def csv_unit(ser):
    return ser["unit"].replace("-", "_")


def csv_table(ser, obs):
    """The header row and the data rows of a series CSV (16)."""
    u = csv_unit(ser)
    if ser["frequency"] == "change-point":
        header = f"effective,kind,value_{u},lower_{u},upper_{u},released,released_basis"
        rows = [",".join([o["effective"], o["kind"], o.get("value") or "", o.get("lower") or "", o.get("upper") or "",
                          o["released"]["date"] or "", o["released"]["basis"]]) for o in obs]
        return header, rows
    with_code = any("null_text" in era or "missing_codes" in era for era in ser["extract"])
    header = f"period,value_{u}," + ("missing_code," if with_code else "") + "released,released_basis"
    rows = []
    for o in obs:
        row = [o["period"], o["value"] or ""]
        if with_code:
            row.append((o.get("missing") or {}).get("code", ""))
        row += [o["released"]["date"] or "", o["released"]["basis"]]
        rows.append(",".join(row))
    return header, rows


def csv_segment_bytes(st, ser, obs, segment, retrieved_at, reg=None):
    """16 (v0.4): the CSV of one segment. Comment lines in this order: title with unit, the
    attribution and notice filled ({year} from the segment's retrieval time, decision P5),
    the terms link, the derivation text, 'Segment <segment>: <first> to <last>.' and
    'Retrieved <retrieval time> by RadMage Finance.'; then the header and the rows."""
    src = (reg or st.registry)["sources"][ser["source"]]  # v0.8: reg is an earlier registry version (22.9)
    year = et_date(parse_utc(retrieved_at)).year
    lines = [f"# {ser['title']} ({ser['unit_label']})", "# " + fill_placeholders(src["attribution"], ser["data_name"], year)]
    if src.get("notice"):
        lines.append("# " + fill_placeholders(src["notice"], ser["data_name"], year))
    lines.append(f"# Terms: {src['terms_url']}")
    if ser.get("derived_from"):
        lines.append("# " + ser["derived_from"]["method"])
    keys = [observation_key(o) for o in obs]
    lines.append(f"# Segment {segment}: {keys[0] if keys else ''} to {keys[-1] if keys else ''}.")
    lines.append(f"# Retrieved {retrieved_at} by RadMage Finance.")
    header, rows = csv_table(ser, obs)
    return ("\n".join(lines + [header] + rows) + "\n").encode("utf-8")


def first_line_difference(got, want):
    gl, wl = got.split(b"\n"), want.split(b"\n")
    i = next((k for k in range(min(len(gl), len(wl))) if gl[k] != wl[k]), min(len(gl), len(wl)))
    g = gl[i].decode("utf-8", "replace") if i < len(gl) else "<end of file>"
    x = wl[i].decode("utf-8", "replace") if i < len(wl) else "<end of file>"
    return f"line {i + 1}: got {g[:160]!r}, expected {x[:160]!r} ({len(got)} bytes, expected {len(want)})"


def summarize_series(st, objects_refs):
    all_obs, problems = [], []
    for ref in objects_refs:
        obj = st.tree_json.get(ref.get("path"))
        if obj is None:
            problems.append(f"{ref.get('path')} not readable")
            continue
        all_obs.extend(obj.get("observations", []))
    return all_obs, problems


# ---------------------------------------------------------------------------
# Deadlines and staleness (14.2, 4.4)
# ---------------------------------------------------------------------------


def next_unseen_period(ser, last_period):
    """14.2, 17.3: the first New York Fed business day after last_period that is not listed
    in the series' known_gaps (a documented gap is never waited for, 11.6)."""
    gaps = {g.get("period") for g in ser.get("known_gaps", [])}
    d = next_business_day(parse_date(last_period))
    while d.isoformat() in gaps:
        d = next_business_day(d)
    return d


def period_deadline(st, sid, period, marker, reading="latest", grace=True):
    """11.6: the deadline of period P is the deadline 14.2 gives when P is the next unseen
    period (EFFR: P's publication day at 09:00 ET; Debt to the Penny: the first business day
    after P at the calendar time, 21:15, in the given reading of the unknown zone; H.6: the
    next release after data_release_date by the fourth-Tuesday rule at 13:00 ET), plus the
    grace hours. Without grace it is the expected publication time of 17.3.
    Returns (datetime or None, explanation)."""
    ser = st.series[sid]
    cal = st.registry["calendars"][ser["release"]["calendar"]]
    extra = dt.timedelta(hours=cal["grace_hours"]) if grace else dt.timedelta(0)
    if ser["frequency"] == "business-day":
        p = parse_date(period) if isinstance(period, str) else period
        pub = next_business_day(p)
        # 17.3, 18: 21:15 when no calendar entry for the record date has been collected; a
        # pipeline root holds no collected calendar, so 21:15 applies throughout.
        t = cal["publish_time"] or FD_DEFAULT_TIME
        return cal_instant(pub, t, cal, reading) + extra, f"period {p} published {pub} {t} ({reading} reading)" if cal.get("publish_time_zone") == "unknown" else f"period {p} published {pub} {t}"
    if ser["frequency"] == "month":
        drd = (marker or {}).get("data_release_date")
        if not drd:
            return None, "no data_release_date"
        nxt = next_fourth_tuesday_after(parse_date(drd))
        return cal_instant(nxt, cal["publish_time"], cal, reading) + extra, f"release {nxt}"
    return None, "no deadline rule"


def deadline_for(st, sid, last_period, marker, reading="latest", grace=True):
    """Deadline for the next unseen period (14.2), latest reading of an unknown zone (4.5).
    Returns (datetime or None, explanation)."""
    ser = st.series[sid]
    if "follows" in ser["staleness"]:
        return None, "follows another series"
    if last_period is None:
        return None, "not yet published"
    if ser["frequency"] == "business-day":
        return period_deadline(st, sid, next_unseen_period(ser, last_period), marker, reading, grace)
    if ser["frequency"] == "month":
        return period_deadline(st, sid, None, marker, reading, grace)
    return None, "no deadline rule"


def request_group_of(st):
    """11.3, 17.3: series id to its request group, named by its first series in registry order."""
    order = [s["id"] for s in st.registry.get("series", [])]
    out = {}
    for s in st.registry.get("series", []):
        members = {s["id"], *s["fetch"].get("shared_with", [])}
        out[s["id"]] = min(members, key=lambda x: order.index(x) if x in order else len(order))
    return out


def requested_groups(st, rec):
    """The groups a run sent requests for, read from its per-series outcomes: every outcome
    other than not-due needs a response or a failed request (11.1). reading: a run record
    whose series map is empty sent no request we can see."""
    grp = request_group_of(st)
    return {grp[s] for s, o in (rec.get("series") or {}).items() if s in grp and o != "not-due"}


NO_REQUEST_TRIGGERS = ("review", "rollback", "restore")
NO_REQUEST_OUTCOMES = ("nothing-due", "refused")


def expected_absences(st, rec, after, has_record):
    """11.6 for one run record. `after` maps series id to its state after the run (the
    snapshot the manifest names once the run has ended); `has_record(sid, period)` says
    whether a held or frozen series' candidate after the run holds that period.
    Returns a list of (entry, optional): `optional` marks a period that the source does hold
    (in the held or frozen candidate) while the request succeeded, where 11.6 allows more than
    one reading (see the report): the entry 11.6 gives mechanically (not-yet-due, or
    after-deadline although "the source has no record" is not true), or no entry because the
    period is not absent from the source, only unpublished."""
    if rec.get("trigger") in NO_REQUEST_TRIGGERS or rec.get("outcome") in NO_REQUEST_OUTCOMES:
        return []
    groups = requested_groups(st, rec)
    if not groups:
        return []
    grp = request_group_of(st)
    now = parse_utc(rec["started_at"])
    today = et_date(now)
    out = []
    for s in st.registry.get("series", []):
        sid = s["id"]
        if grp.get(sid) not in groups or s["frequency"] not in ("business-day", "month"):
            continue
        state = after.get(sid) or {}
        if not state.get("objects") or not state.get("last_period"):
            continue  # only series with published data after this run
        outcome = (rec.get("series") or {}).get(sid)
        last = state["last_period"]
        gaps = {g.get("period") for g in s.get("known_gaps", [])}

        def classify(period, dl):
            if dl is None:
                raise ValueError(f"{sid} {period}: no deadline")
            if now <= dl:
                return "not-yet-due", bool(has_record(sid, period))
            # v0.6: a locked series' period present in its frozen candidate is not absent (11.6), also
            # when this run's fetch failed; like the other such periods it is accepted listed or not.
            if outcome == "failed":
                return "fetch-failed", bool(has_record(sid, period))
            if outcome == "invalid":
                return "response-invalid", bool(has_record(sid, period))
            return "after-deadline", bool(has_record(sid, period))

        if s["frequency"] == "business-day":
            for d in weekdays_between(parse_date(last) + dt.timedelta(days=1), today):
                p = d.isoformat()
                if not is_business_day(d):
                    detail, opt = "holiday", False
                elif p in gaps:
                    detail, opt = "known-gap", False
                else:
                    detail, opt = classify(p, period_deadline(st, sid, d, state.get("source_marker"))[0])
                out.append(({"series": sid, "period": p, "kind": ABSENCE_KINDS[detail], "detail": detail}, opt))
        else:
            p = month_add(last, 1)
            detail, opt = classify(p, period_deadline(st, sid, None, state.get("source_marker"))[0])
            out.append(({"series": sid, "period": p, "kind": ABSENCE_KINDS[detail], "detail": detail}, opt))
    return out


def absences_problems(st, rec, after, has_record):
    """Compare a run record's absences with 11.6. Returns (problems, counts)."""
    where = f"run {rec.get('id')}"
    got = rec.get("absences")
    if not isinstance(got, list):
        return [f"{where}: absences is not a list (14.1)"], {}
    p = []
    no_request = rec.get("trigger") in NO_REQUEST_TRIGGERS or rec.get("outcome") in NO_REQUEST_OUTCOMES or not requested_groups(st, rec)
    if no_request:
        if got:
            p.append(f"{where}: sent no request (trigger {rec.get('trigger')}, outcome {rec.get('outcome')}) but lists {len(got)} absence(s); 11.6 gives none")
        return p, {"entries": 0, "optional": 0}
    order = [s["id"] for s in st.registry.get("series", [])]
    # Form, order and the undocumented gaps (11.6, last bullet).
    regular, undocumented = [], {}
    for i, e in enumerate(got):
        if not isinstance(e, dict) or set(e) != {"series", "period", "kind", "detail"}:
            p.append(f"{where}: absences[{i}] is not {{series, period, kind, detail}}")
            continue
        if ABSENCE_KINDS.get(e.get("detail")) != e.get("kind"):
            p.append(f"{where}: absences[{i}] detail {e.get('detail')!r} with kind {e.get('kind')!r} (11.6 table)")
        if e.get("series") not in st.series or st.series[e["series"]]["frequency"] not in ("business-day", "month"):
            p.append(f"{where}: absences[{i}] series {e.get('series')!r} is not a business-day or monthly series (11.6: change points are never listed)")
            continue
        if e.get("detail") == "inside-history":
            undocumented.setdefault(e["series"], []).append(e.get("period"))
        else:
            regular.append(e)
    keyed = [(order.index(e["series"]), 1 if e.get("detail") == "inside-history" else 0, str(e.get("period"))) for e in got
             if isinstance(e, dict) and e.get("series") in order]
    if keyed != sorted(keyed):
        p.append(f"{where}: absences are not ordered by registry series order, then period, with a series' undocumented gaps after its other entries (11.6)")
    grp = request_group_of(st)
    groups = requested_groups(st, rec)
    for sid, periods in undocumented.items():
        if grp.get(sid) not in groups:
            p.append(f"{where}: undocumented gaps of {sid}, whose group the run did not request")
        if len(periods) > 50:
            p.append(f"{where}: {len(periods)} undocumented gaps of {sid}, at most 50 are listed (11.6)")
        if periods != sorted(periods) or len(set(periods)) != len(periods):
            p.append(f"{where}: undocumented gaps of {sid} are not oldest first without repeats")
        if (rec.get("series") or {}).get(sid) != "invalid":
            p.append(f"{where}: undocumented gaps of {sid} although its outcome is {(rec.get('series') or {}).get(sid)}; a candidate with an undocumented gap is invalid (11.4)")
        ser = st.series[sid]
        gaps = {g.get("period") for g in ser.get("known_gaps", [])}
        for x in periods:
            try:
                if ser["frequency"] == "business-day" and (not is_business_day(parse_date(x)) or x in gaps):
                    p.append(f"{where}: undocumented gap {sid} {x} is not a business day outside known_gaps (11.4, 11.6)")
                elif ser["frequency"] == "month" and not re.fullmatch(r"\d{4}-\d{2}", str(x), re.ASCII):
                    p.append(f"{where}: undocumented gap {sid} {x} is not a month")
            except ValueError as exc:
                p.append(f"{where}: undocumented gap {sid} {x}: {exc}")
    # The other entries, recomputed.
    exp = expected_absences(st, rec, after, has_record)
    want_req = [e for e, opt in exp if not opt]
    want_opt = [e for e, opt in exp if opt]
    left = list(regular)
    for e in want_req:
        if e in left:
            left.remove(e)
        else:
            alt = [x for x in left if x.get("series") == e["series"] and x.get("period") == e["period"]]
            p.append(f"{where}: {e['series']} {e['period']} should be {e['kind']}/{e['detail']}" + (f", the record says {alt[0].get('kind')}/{alt[0].get('detail')}" if alt else ", the record does not list it") + " (11.6)")
            if alt:
                left.remove(alt[0])
    for e in want_opt:
        if e in left:
            left.remove(e)
    for e in left:
        p.append(f"{where}: lists {e.get('series')} {e.get('period')} {e.get('kind')}/{e.get('detail')}, which 11.6 does not give")
    return p, {"entries": len(got), "optional": len(want_opt), "expected": len(exp)}


def route_alerts(st, day):
    """17.8: the route alerts current on ET date `day`, as {key: (severity, entry date)}.
    source-retirement:<source> for an entry that affects the registered route: warning from
    180 days before its date, critical from 60 days before it and after it, while it stands;
    source-route-check:<source> for one that does not: warning from 7 days before its date to
    30 days after it. With several entries the earliest date that applies counts."""
    out = {}
    for src_id, src in sorted(st.registry.get("sources", {}).items()):
        for e in src.get("route_notices") or []:
            try:
                d = parse_date(e["date"])
            except (KeyError, TypeError, ValueError):
                continue
            left = (d - day).days
            if e.get("affects_registered_route") is True:
                key, sev = f"source-retirement:{src_id}", ("critical" if left <= 60 else "warning" if left <= 180 else None)
            else:
                key, sev = f"source-route-check:{src_id}", ("warning" if -30 <= left <= 7 else None)
            if sev is None:
                continue
            if key not in out or d < out[key][1]:
                out[key] = (sev, d)
    return out


def stale_threshold(st, sid, deadline):
    stl = st.series[sid]["staleness"]
    if "after_business_days" in stl:
        local = et_local(deadline)
        d = local.date()
        for _ in range(stl["after_business_days"]):
            d = next_business_day(d)
        return et_wall_to_utc(d, local.hour, local.minute)
    if "after_days_past_expected_release" in stl:
        return deadline + dt.timedelta(days=stl["after_days_past_expected_release"])
    return None


def computed_status(st, snapshot, sid, at, depth=0):
    state = snapshot["series"].get(sid, {})
    if state.get("status") == "not-yet-published":
        return "not-yet-published"
    if state.get("status") == "held":
        return "held"
    ser = st.series[sid]
    if "follows" in ser["staleness"] and depth < 3:
        other = computed_status(st, snapshot, ser["staleness"]["follows"], at, depth + 1)
        return "stale" if other == "stale" else "fresh"
    dl, _ = deadline_for(st, sid, state.get("last_period"), state.get("source_marker"))
    if dl is None:
        return None
    thr = stale_threshold(st, sid, dl)
    return "stale" if thr is not None and at >= thr else "fresh"


# ---------------------------------------------------------------------------
# Tree: closure, snapshot, manifest, CSVs, runs (sections 8 to 14, 16)
# ---------------------------------------------------------------------------


def section_tree(st):
    objects = {k: v for k, v in st.tree_json.items() if k.startswith("objects/")}
    manifest = st.tree_json.get("manifest.json")
    if manifest is None:
        check("T0 manifest.json readable", ["missing or not valid JSON"])
        return
    snap_ref = manifest.get("snapshot", {})
    snapshot = st.tree_json.get(snap_ref.get("path"))
    runs = (st.tree_json.get("status/runs.json") or {}).get("runs", [])
    run = next((r for r in runs if r.get("snapshot") == snap_ref.get("id")), None)
    created = parse_utc(snapshot["created_at"]) if snapshot else None
    as_of_et = et_date(snapshot_time(snapshot["id"])) if snapshot else dt.date.max
    first_snapshot_et = as_of_et if snapshot and snapshot.get("previous") is None else None

    for relpath, obj in sorted(objects.items()):
        data = tree_bytes(relpath)
        expect = f"objects/{obj.get('series')}/{obj.get('segment')}/{sha256_hex(canon_bytes(obj))[:16]}.json"
        problems = [] if relpath == expect else [f"path should be {expect}"]
        if sha256_hex(data) != sha256_hex(canon_bytes(obj)):
            problems.append("file bytes are not the canonical bytes the hash is taken over")
        check(f"T1 {relpath} path is its address objects/<series>/<segment>/<16 hex>.json (7, 12.3)", problems)
        check(f"T2 {relpath} observations follow 4.4, 5, 6.1, 6.2", object_semantics(st, obj, as_of_et))

    problems = []
    if snapshot is None:
        problems.append(f"snapshot {snap_ref.get('path')} missing")
    else:
        if sha256_hex(tree_bytes(snap_ref["path"])) != snap_ref.get("sha256"):
            problems.append("snapshot sha256 differs")
        if snap_ref.get("path") != f"snapshots/{snap_ref.get('id')}.json":
            problems.append("snapshot path does not match its id")
        if snapshot.get("id") != snap_ref.get("id"):
            problems.append("snapshot id differs from the manifest's")
    check("T3 manifest names an existing snapshot with the stated path, id and sha256 (9, 12.3)", problems)
    if snapshot is None:
        return

    # Closure from the snapshot (bytes known)
    problems = []
    for sid, state in sorted(snapshot.get("series", {}).items()):
        for ref in state.get("objects", []):
            data = tree_bytes(ref.get("path", ""))
            if data is None:
                problems.append(f"{sid}: {ref.get('path')} missing")
                continue
            if sha256_hex(data) != ref.get("sha256"):
                problems.append(f"{sid}: {ref['path']} sha256 differs")
            if len(data) != ref.get("bytes"):
                problems.append(f"{sid}: {ref['path']} is {len(data)} bytes, snapshot says {ref.get('bytes')}")
            obj = st.tree_json.get(ref["path"], {})
            if obj.get("series") != sid or obj.get("segment") != ref.get("segment"):
                problems.append(f"{sid}: {ref['path']} holds series {obj.get('series')} segment {obj.get('segment')}")
    for ref in snapshot.get("revisions", []):
        data = tree_bytes(ref.get("path", ""))
        if data is None or sha256_hex(data) != ref.get("sha256") or len(data) != ref.get("bytes"):
            problems.append(f"revision log version {ref.get('path')} missing or hash/bytes differ")
        elif not re.fullmatch(r"revisions/[a-z0-9-]+/\d{4}/[0-9a-f]{16}\.json", ref["path"], re.ASCII) or ref["path"][-21:-5] != ref["sha256"][:16]:
            problems.append(f"{ref['path']} is not revisions/<series>/<YYYY>/<16 hex of its sha256>.json (10)")
    check("T4 closure: every object and revision log version the snapshot names exists with its sha256 and bytes; hold candidates live in the archive (8, 12.3)",
          problems, f"{len(snapshot.get('holds', []))} hold(s)")

    # Closure from the manifest (CSVs and log versions are content-addressed, 9)
    problems = []
    for sid, summ in sorted(manifest.get("series", {}).items()):
        if "csv" in summ:
            problems.append(f"{sid}: a full-history 'csv' reference; v0.4 has 'csvs', one per segment (9)")
        refs = list(summ.get("objects", [])) + list(summ.get("csvs") or []) + list(summ.get("revisions", []))
        for ref in refs:
            data = tree_bytes(ref.get("path", ""))
            if data is None:
                problems.append(f"{sid}: {ref.get('path')} missing")
                continue
            if sha256_hex(data) != ref.get("sha256"):
                problems.append(f"{sid}: {ref['path']} sha256 differs")
            path = ref["path"]
            if path.startswith(("series/", "revisions/")):
                stem = path.rsplit("/", 1)[1].split(".")[0]
                if stem != sha256_hex(data)[:16]:
                    problems.append(f"{sid}: {path} is not named by the first 16 hex of its sha256 (9)")
                if path.startswith("series/") and path != f"series/{sid}/{ref.get('segment')}/{stem}.csv":
                    problems.append(f"{sid}: CSV {path} is not series/{sid}/<its segment {ref.get('segment')}>/<16 hex>.csv (9, 12.3)")
    check("T5 closure: every object, CSV segment and revision log version the manifest names exists, matches its sha256 and is content-addressed; a CSV path names its series and segment (9, 12.3; the manifest gives no byte counts)", problems)

    # Pages window (13)
    problems = []
    for label, sid_ in (("previous_snapshot", manifest.get("previous_snapshot")), ("snapshot.previous", snapshot.get("previous"))):
        if sid_ is not None and tree_bytes(f"snapshots/{sid_}.json") is None:
            problems.append(f"{label} {sid_} not in the tree")
    for pid in manifest.get("pages_window", {}).get("pinned", []):
        if tree_bytes(f"snapshots/{pid}.json") is None:
            problems.append(f"pinned snapshot {pid} not in the tree")
    if tree_bytes("status/runs.json") is None:
        problems.append("status/runs.json missing")
    check("T6 the tree holds the Pages window: manifest, current and previous snapshots, pinned snapshots, status/ (13)", problems,
          f"window {manifest.get('pages_window', {}).get('days')} days")

    reg_ids, snap_ids, man_ids = set(st.series), set(snapshot.get("series", {})), set(manifest.get("series", {}))
    check("T7 every registered series appears in the snapshot (8, 12.2)",
          ([f"missing: {', '.join(sorted(reg_ids - snap_ids))}"] if reg_ids - snap_ids else []) +
          ([f"unregistered: {', '.join(sorted(snap_ids - reg_ids))}"] if snap_ids - reg_ids else []), f"{len(snap_ids)} series")
    check("T8 every registered series appears in the manifest (9)",
          ([f"missing: {', '.join(sorted(reg_ids - man_ids))}"] if reg_ids - man_ids else []) +
          ([f"unregistered: {', '.join(sorted(man_ids - reg_ids))}"] if man_ids - reg_ids else []), f"{len(man_ids)} series")

    rh = snapshot.get("run", {}).get("registry_sha256")
    canon_h = sha256_hex(canon_bytes(st.registry))
    tree_v07 = manifest.get("schema") != MANIFEST_V4  # 22.9: a manifest/3 tree is a file written under v0.7
    v07_h = registry_versions(st)["v0.7"][0]
    check("T9 snapshot run.registry_sha256 is the SHA-256 of the registry's canonical form, the current one or the v0.7 one of I7 (4, 8, 22.9: a file's own version marks it)",
          [] if rh in (canon_h, v07_h) else [f"{rh} is not {canon_h} nor the v0.7 registry's {v07_h}" + (" (it is the hash of the file bytes)" if rh == sha256_hex(st.registry_bytes) else "")])
    tree_reg = registry_by_hash(st).get(rh, (None, None, st.registry))[2]

    # Per-series snapshot state (8)
    for sid in sorted(snap_ids & reg_ids):
        state, ser = snapshot["series"][sid], st.series[sid]
        problems = []
        obs, more = summarize_series(st, state.get("objects", []))
        problems += more
        nyp = state.get("status") == "not-yet-published"
        if nyp:
            if state.get("objects") or state.get("last_period") is not None or state.get("retrieved_at") is not None or state.get("observation_count") != 0:
                problems.append("not-yet-published needs empty objects, null last_period and retrieved_at, count 0 (8)")
            if state.get("checked_at") is not None or state.get("source_marker") is not None:
                problems.append("not-yet-published needs null checked_at and source_marker (8)")
        else:
            if not state.get("objects"):
                problems.append("objects empty but the series is not 'not-yet-published' (8)")
            if state.get("retrieved_at") is None or state.get("checked_at") is None:
                problems.append("published series without retrieved_at or checked_at")
        segs = [r.get("segment") for r in state.get("objects", [])]
        if segs != sorted(segs) or len(set(segs)) != len(segs):
            problems.append("object segments not ascending and unique")
        if ser["segment"] == "year" and obs:
            years = sorted({observation_key(o)[:4] for o in obs})
            if years != sorted(segs):
                problems.append(f"segments {segs} are not the calendar years of the periods {years} (7)")
        keys = [observation_key(o) for o in obs]
        if keys != sorted(keys) or len(set(keys)) != len(keys):
            problems.append("periods across segments are not ascending and unique")
        if obs and state.get("last_period") != keys[-1]:
            problems.append(f"last_period {state.get('last_period')} but the objects end at {keys[-1]}")
        if state.get("observation_count") != len(obs):
            problems.append(f"observation_count {state.get('observation_count')} but the objects hold {len(obs)}")
        if state.get("status") == "refreshed" and state.get("checked_at") != state.get("retrieved_at"):
            problems.append("refreshed but checked_at differs from retrieved_at (8)")
        if state.get("retrieved_at") and state.get("checked_at") and state["retrieved_at"] > state["checked_at"]:
            problems.append("retrieved_at after checked_at")
        att = state.get("attempt", {})
        if att.get("outcome") == "ok" and att.get("error") is not None:
            problems.append("attempt ok with an error text")
        if att.get("outcome") in ("failed", "invalid") and not att.get("error"):
            problems.append("failed or invalid attempt without an error text")
        marker = state.get("source_marker")
        want_keys = {"nyfed-markets": None, "fiscaldata": {"total_count"}, "frb-releases": {"latest_release_date", "data_release_date", "prepared"}}.get(ser["source"])
        if want_keys is None:
            if marker is not None:
                problems.append("source_marker must be null for the New York Fed (8)")
        elif marker is None:
            if not nyp:
                problems.append(f"source_marker null but {sorted(want_keys)} required (8)")
        elif set(marker) != want_keys:
            problems.append(f"source_marker keys {sorted(marker)} are not {sorted(want_keys)} (8)")
        check(f"T10 snapshot state for {sid} follows 8 (a not-yet-published series has empty objects and null fields)", problems, state.get("status"))

    # Manifest per series (9, 12.9)
    gen = parse_utc(manifest["generated_at"])
    for sid in sorted(snap_ids & man_ids & reg_ids):
        state, summ, ser = snapshot["series"][sid], manifest["series"][sid], st.series[sid]
        problems = []
        obs, _ = summarize_series(st, state.get("objects", []))
        if [(r.get("path"), r.get("sha256")) for r in summ.get("objects", [])] != [(r.get("path"), r.get("sha256")) for r in state.get("objects", [])]:
            problems.append("object paths and hashes differ from the snapshot")
        for f in ("last_period", "retrieved_at", "checked_at"):
            if summ.get(f) != state.get(f):
                problems.append(f"{f} {summ.get(f)} vs snapshot {state.get(f)}")
        for f in ("title", "unit_label", "frequency", "class"):
            if summ.get(f) != ser.get(f):
                problems.append(f"{f} {summ.get(f)!r} differs from the registry {ser.get(f)!r}")
        if obs:
            last = obs[-1]
            want_value = last.get("value") if ("period" in last or last.get("kind") == "rate") else None
            want_range = {"lower": last["lower"], "upper": last["upper"]} if last.get("kind") == "range" else None
            if summ.get("last_value") != want_value:
                problems.append(f"last_value {summ.get('last_value')!r}, the last observation gives {want_value!r}")
            if summ.get("last_range") != want_range:
                problems.append(f"last_range {summ.get('last_range')!r}, the last observation gives {want_range!r}")
            if summ.get("last_released") != last.get("released"):
                problems.append(f"last_released {summ.get('last_released')} vs the last observation {last.get('released')}")
            segs = [r.get("segment") for r in state.get("objects", [])]
            csvs = summ.get("csvs") if isinstance(summ.get("csvs"), list) else []
            if [c.get("segment") for c in csvs] != segs:
                problems.append(f"csvs segments {[c.get('segment') for c in csvs]}, the objects' segments are {segs}: one entry per object, same order (9, 16)")
            # 12.9: the first manifest replaces none, so every entry takes the series' retrieved_at.
            if manifest.get("previous_snapshot") is None and any(c.get("retrieved_at") != state.get("retrieved_at") for c in csvs):
                problems.append(f"a csvs retrieved_at differs from the series' retrieved_at {state.get('retrieved_at')} in a manifest that replaces none (12.9)")
        else:
            for f in ("last_value", "last_range", "last_released"):
                if summ.get(f) is not None:
                    problems.append(f"{f} should be null when unpublished (8)")
            if summ.get("csvs") != []:
                problems.append("csvs should be empty when unpublished (9)")
            if summ.get("revisions") != []:
                problems.append("revisions should be empty when unpublished (8)")
        if summ.get("revisions") != [{"path": r["path"], "sha256": r["sha256"]} for r in snapshot.get("revisions", []) if r["path"].startswith(f"revisions/{sid}/")] and snapshot.get("previous") is None:
            problems.append("revision log versions differ from those the first snapshot wrote")
        want_status = computed_status(st, snapshot, sid, gen)
        if want_status is None:
            problems.append(f"status {summ.get('status')} cannot be recomputed (no saved calendar data)")
        elif summ.get("status") != want_status:
            problems.append(f"status {summ.get('status')} but as of generated_at it is {want_status} (9, 14.2, 4.4)")
        if (summ.get("status") == "fresh") != (summ.get("status_reason") is None):
            problems.append("status_reason should be null exactly when fresh (guessed)")
        check(f"T11 manifest summary for {sid} equals its snapshot and objects; status as of generated_at (9, 12.9, 14.2)", problems, summ.get("status"))

    # Notices and attribution (4.3, 8, 9)
    problems = []
    used_sources = {st.series[s]["source"] for s in reg_ids}
    notices = snapshot.get("notices", {})
    if set(notices) != used_sources:
        problems.append(f"snapshot notices for {sorted(notices)}, the registered series use {sorted(used_sources)}")
    for src in sorted(used_sources & set(notices)):
        reg_src = tree_reg["sources"][src]  # v0.8: the registry version the snapshot was built with (I7)
        for f in ("attribution", "notice", "terms_url"):
            if notices[src].get(f) != reg_src.get(f):
                problems.append(f"snapshot {src}: {f} is not the registry text with placeholders kept (8)")
    for sid in sorted(man_ids & reg_ids):
        ser, summ = st.series[sid], manifest["series"][sid]
        reg_src = st.registry["sources"][ser["source"]]
        ra = summ.get("retrieved_at")
        year = et_date(parse_utc(ra)).year if ra else et_date(parse_utc(manifest["generated_at"])).year
        for f in ("attribution", "notice"):
            tmpl = reg_src.get(f)
            if summ.get(f) != fill_placeholders(tmpl, ser["data_name"], year):
                problems.append(f"manifest {sid}: {f} is not the registry text filled with data_name and the ET year of retrieved_at, or of generated_at when unpublished (4.3, 8, 9)")
    check("T12 snapshot notices keep the registry placeholders; manifest attribution and notice are filled per series (4.3, 8, 9)", problems)

    # Run record, times and outcome-to-status mapping (3, 8, 14.1)
    problems = []
    if manifest.get("previous_snapshot") is not None and snapshot.get("previous") is None and manifest.get("rollback") is None:
        problems.append("previous_snapshot set although this is the first snapshot and no rollback is recorded (9)")
    if run is None:
        problems.append("status/runs.json has no run naming the current snapshot")
    else:
        if snapshot_id_of(parse_utc(run["started_at"])) != snapshot.get("id"):
            problems.append(f"snapshot id {snapshot.get('id')} is not the run start {run['started_at']} (3)")
        if run.get("id") != snapshot.get("run", {}).get("id") or run.get("trigger") != snapshot.get("run", {}).get("trigger"):
            problems.append("run id or trigger differs between runs.json and the snapshot")
        if run.get("outcome") != "published":
            problems.append(f"the run that wrote the current snapshot has outcome {run.get('outcome')}")
        order = [run["started_at"], snapshot["created_at"], manifest["generated_at"], run["ended_at"]]
        if order != sorted(order):
            problems.append(f"times out of order (started, created, generated, ended): {order}")
        for sid, state in snapshot.get("series", {}).items():
            if state.get("status") == "refreshed" and not (run["started_at"] <= (state.get("retrieved_at") or "") <= run["ended_at"]):
                problems.append(f"{sid}: refreshed but retrieved_at is outside the run")
        to_status = {"appended": "refreshed", "revised-expected": "refreshed", "unchanged": "unchanged", "not-due": "carried-forward",
                     "invalid": "carried-forward", "failed": "carried-forward", "revised-unexpected": "held"}
        to_attempt = {"appended": "ok", "revised-expected": "ok", "unchanged": "ok", "revised-unexpected": "ok", "not-due": "not-due", "invalid": "invalid", "failed": "failed"}
        for sid, outcome in run.get("series", {}).items():
            state = snapshot.get("series", {}).get(sid, {})
            st_status = state.get("status")
            if st_status == "not-yet-published":
                if outcome not in ("not-due", "invalid", "failed"):
                    problems.append(f"{sid}: outcome {outcome} but still not-yet-published (8)")
            elif to_status.get(outcome) != st_status:
                problems.append(f"{sid}: outcome {outcome} gives {to_status.get(outcome)}, snapshot says {st_status} (8)")
            if state.get("attempt", {}).get("outcome") != to_attempt.get(outcome):
                problems.append(f"{sid}: attempt outcome {state.get('attempt', {}).get('outcome')} for run outcome {outcome} (guessed mapping)")
            if state.get("attempt", {}).get("at", "") and not (run["started_at"] <= state["attempt"]["at"] <= run["ended_at"]):
                problems.append(f"{sid}: attempt.at outside the run")
        if set(run.get("series", {})) != reg_ids:
            problems.append("run series outcomes do not cover every registered series (guessed)")
    check("T13 snapshot id, run record, times and outcome-to-status mapping agree (3, 8, 14.1)", problems)

    # Revision log versions in the tree (10)
    problems, nlogs = [], 0
    for relpath, v in sorted(st.tree_json.items()):
        if not relpath.startswith("revisions/"):
            continue
        nlogs += 1
        data = tree_bytes(relpath)
        if relpath != f"revisions/{v.get('series')}/{v.get('year')}/{sha256_hex(data)[:16]}.json":
            problems.append(f"{relpath} is not revisions/<series>/<YYYY>/<16 hex>.json for its content")
        if v.get("series") not in st.series:
            problems.append(f"{relpath}: unregistered series")
        recs = v.get("records", [])
        if not recs:
            problems.append(f"{relpath}: a log with no record (10: a year has a log only once it has a record)")
        det = [r.get("detected_at") for r in recs]
        if det != sorted(det):
            problems.append(f"{relpath}: records not in detection order")
        for r in recs:
            if et_date(parse_utc(r["detected_at"])).year != v.get("year"):
                problems.append(f"{relpath}: a record whose ET detection year is not {v.get('year')}")
            if r["field"] in ("value", "lower", "upper") or r["field"].startswith("extra."):
                for side in ("before", "after"):
                    if r[side] is not None and not _DECIMAL_TEXT.fullmatch(r[side]):
                        problems.append(f"{relpath}: {side} of {r['field']} is not a decimal string")
    check("T14 revision log versions are content-addressed, non-empty, ET-dated and append-only in form (10)", problems, f"{nlogs} log version(s)")

    # Release dates (6.3)
    problems, unknown, n = [], [], 0
    for relpath, obj in sorted(objects.items()):
        ser = st.series.get(obj.get("series"))
        if not ser:
            continue
        for i, o in enumerate(obj.get("observations", [])):
            n += 1
            want, why = expected_released(st, ser, o, i == 0 and ser["frequency"] == "change-point", first_snapshot_et)
            got = o.get("released")
            if want is None:
                unknown.append(f"{observation_key(o)} ({why})")
            elif want["basis"] == "first-seen":
                if got.get("basis") not in ("first-seen", "not-recorded"):
                    problems.append(f"{relpath} {observation_key(o)}: basis {got.get('basis')}")
                elif got.get("basis") == "first-seen" and want["date"] and got.get("date") != want["date"]:
                    problems.append(f"{relpath} {observation_key(o)}: first-seen {got.get('date')}, first snapshot ET date {want['date']}")
            elif got != want:
                problems.append(f"{relpath} {observation_key(o)}: released {got}, 6.3 gives {want} ({why})")
    if unknown and not problems:
        skip("T15 every stored record's released follows 6.3", f"{len(unknown)} record(s) need saved calendar data: {unknown[:2]}")
    else:
        check("T15 every stored record's released follows 6.3 (rule from rule_valid_from, calendar from calendar_valid_from, first change point not-recorded)",
              problems, f"{n} records")

    # expected_next_update_by (14.2)
    deadlines, notes = [], []
    for sid in sorted(snap_ids & reg_ids):
        state = snapshot["series"][sid]
        if state.get("status") in ("not-yet-published", "held"):
            continue
        dl, why = deadline_for(st, sid, state.get("last_period"), state.get("source_marker"))
        if dl is not None:
            deadlines.append((dl, sid, why))
        elif "follows" not in st.series[sid]["staleness"]:
            notes.append(f"{sid}: {why}")
    got = manifest.get("health", {}).get("expected_next_update_by")
    if notes:
        skip("T16 health.expected_next_update_by is the earliest deadline among published, unheld series (14.2)", "; ".join(notes))
    elif deadlines:
        dl, sid, why = min(deadlines)
        check("T16 health.expected_next_update_by is the earliest deadline among published, unheld series (14.2)",
              [] if got == fmt_utc(dl) else [f"manifest says {got}, the earliest deadline is {fmt_utc(dl)} ({sid}: {why})"],
              f"{fmt_utc(dl)} from {sid}: {why}, publish time plus grace_hours")

    # CSV segments (16, v0.4): one per object, each built from that object's observations
    named_csvs = set()
    for sid in sorted(man_ids & reg_ids):
        summ, ser = manifest["series"][sid], st.series[sid]
        refs_by_seg = {r.get("segment"): r for r in snapshot["series"].get(sid, {}).get("objects", [])}
        for entry in summ.get("csvs") or []:
            path = entry.get("path")
            named_csvs.add(path)
            data = tree_bytes(path)
            if data is None:
                continue  # reported by T5
            problems = []
            if b"\r" in data:
                problems.append("CR found (16: LF)")
            if not data.endswith(b"\n"):
                problems.append("no final newline (16)")
            if len(data) > 5_000_000:
                problems.append("over 5 MB (12.7)")
            lines = data.decode("utf-8").split("\n")
            if lines and lines[-1] == "":
                lines = lines[:-1]
            comments = [l[2:] for l in lines if l.startswith("# ")]
            if any(l.startswith("#") and not l.startswith("# ") for l in lines):
                problems.append("a comment line does not start with '# '")
            body = [l for l in lines if not l.startswith("#")]
            ref = refs_by_seg.get(entry.get("segment"))
            obs = (st.tree_json.get(ref.get("path")) or {}).get("observations", []) if ref else []
            if ref is None:
                problems.append(f"no object of segment {entry.get('segment')} in the snapshot")
            want = csv_segment_bytes(st, ser, obs, entry.get("segment"), entry.get("retrieved_at")).decode("utf-8").split("\n")[:-1]
            if tree_v07 and ser["source"] == NYFED and data.decode("utf-8").split("\n")[:-1] != want:
                # 22.9: a manifest generated before the first v0.8 run may carry the old terms URL in a New York Fed CSV
                alt = csv_segment_bytes(st, ser, obs, entry.get("segment"), entry.get("retrieved_at"), reg=registry_versions(st)["v0.7"][2]).decode("utf-8").split("\n")[:-1]
                if data.decode("utf-8").split("\n")[:-1] == alt:
                    want = alt
            want_comments = [l[2:] for l in want if l.startswith("# ")]
            if len(comments) != len(want_comments):
                problems.append(f"{len(comments)} comment lines, 16 gives {len(want_comments)}: {want_comments}")
            else:
                for i, (g, w) in enumerate(zip(comments, want_comments), start=1):
                    if g != w:
                        problems.append(f"comment line {i} is {g!r}, 16 gives {w!r}")
            check(f"T17 {path} comment lines follow 16 (title with unit, attribution and notice with {{year}} of the segment's retrieval time, terms, derivation, 'Segment <segment>: <first> to <last>.', 'Retrieved <time> by RadMage Finance.')", problems)
            problems = []
            want_body = [l for l in want if not l.startswith("#")]
            if (body[0] if body else None) != (want_body[0] if want_body else None):
                problems.append(f"header {body[0] if body else None!r} is not {want_body[0] if want_body else None!r} (16)")
            if body[1:] != want_body[1:]:
                problems.append("data rows differ from the segment object's observations")
            check(f"T18 {path} header and rows equal its segment object's observations (16)", problems, f"{len(body) - 1} rows")
    tree_csvs = sorted(rel(p) for p in st.tree_files if p.suffix == ".csv")
    problems = []
    for f in tree_csvs:
        if re.fullmatch(r"series/%s/[0-9a-f]{16}\.csv" % r"[a-z0-9]+(?:-[a-z0-9]+)*", f, re.ASCII) or re.fullmatch(r"series/[a-z0-9-]+\.csv", f, re.ASCII):
            problems.append(f"{f} is a full-history CSV; v0.4 publishes none (9, 16)")
        elif not re.fullmatch(r"series/[a-z0-9]+(?:-[a-z0-9]+)*/(\d{4}|all)/[0-9a-f]{16}\.csv", f, re.ASCII):
            problems.append(f"{f} is not series/<id>/<segment>/<16 hex>.csv")
        if f not in named_csvs:
            problems.append(f"{f} is named by no csvs entry of the manifest")
    check("T22 the example tree holds CSV segments only: no full-history CSV, every CSV file named by the manifest's csvs (9, 16, appendix C1)", problems, f"{len(tree_csvs)} CSV file(s)")

    # Schedule (14.2)
    sched = manifest.get("health", {}).get("schedule", [])
    problems = []
    if not isinstance(sched, list):
        problems.append("schedule is not a list (9)")
    elif sorted(sched) != sorted(SCHEDULE_LINES):
        problems.append(f"{sched} is not the one cron line {SCHEDULE_LINES[0]!r} of 14.2 (v0.7, F7: every four hours at :17 UTC; it replaces decision P8's two lines)")
    check("T19 health.schedule lists the cron lines in force, the one line 17 */4 * * * of 14.2 (v0.7)", problems, " | ".join(sched) if isinstance(sched, list) else "")

    # Every run record (14.1)
    problems = []
    starts = [r.get("started_at") for r in runs]
    if starts != sorted(starts, reverse=True):
        problems.append("not newest first (14.1)")
    if len(runs) > 100:
        problems.append("more than 100 runs")
    for r in runs:
        if (r.get("outcome") == "published") != (r.get("snapshot") is not None):
            problems.append(f"{r.get('id')}: outcome {r.get('outcome')} with snapshot {r.get('snapshot')} (14.1: snapshot exactly when published)")
        if r.get("snapshot") and r["snapshot"] != snapshot_id_of(parse_utc(r["started_at"])):
            problems.append(f"{r.get('id')}: snapshot {r['snapshot']} is not its start time (3)")
        if r.get("ended_at", "") < r.get("started_at", ""):
            problems.append(f"{r.get('id')}: ends before it starts")
        unknown_ids = sorted(set(r.get("series", {})) - reg_ids)
        if unknown_ids:
            problems.append(f"{r.get('id')}: unregistered series {unknown_ids}")
        if r.get("outcome") not in ("published", "nothing-due", "no-change", "gate-failed", "failed", "refused"):
            problems.append(f"{r.get('id')}: outcome {r.get('outcome')!r} is not one of 14.1")
        if not isinstance(r.get("absences"), list):
            problems.append(f"{r.get('id')}: no absences list (14.1, 11.6)")
    check("T20 status/runs.json: newest first, at most 100, snapshot exactly when published, an outcome of 14.1, an absences list (14.1)", problems, f"{len(runs)} run(s)")

    # Absences of the example run (11.6, 14.1)
    problems, n = [], 0
    for r in runs:
        if r.get("snapshot") != snapshot.get("id"):
            continue  # only the run whose after-state is in the tree can be recomputed
        n += 1
        # reading: the example tree keeps no held candidate, so no period counts as held.
        p, _ = absences_problems(st, r, snapshot.get("series", {}), lambda sid, period: False)
        problems += p
    check("T23 the example run's absences are the 11.6 entries: for each requested business-day or monthly series published after the run, every weekday after last_period to the run's ET date with its kind (11.6, 14.1)", problems, f"{n} run(s) recomputed")

    # Sizes (12.7)
    problems = []
    for p in st.tree_files:
        size = p.stat().st_size
        if size > 5_000_000:
            problems.append(f"{rel(p)} is {size} bytes, over 5 MB")
    if len(tree_bytes("manifest.json")) > 256_000:
        problems.append("manifest over 256 KB")
    total = sum(p.stat().st_size for p in st.tree_files)
    if total > 250_000_000:
        problems.append("tree over 250 MB")
    check("T21 sizes: object 2 MB (in T2), file 5 MB, manifest 256 KB, site 250 MB (12.7, 17.7; decimal units)", problems, f"{total} bytes in {len(st.tree_files)} files")


# ---------------------------------------------------------------------------
# Registry (sections 4 and 4.6)
# ---------------------------------------------------------------------------

RESERVED_IDS = {"econ", "news", "manifest", "snapshots", "objects", "series", "revisions", "status", "holds"}
FAMILY_POLICY = {"retention": "full-history", "archive": "permanent", "unexpected_revision": "hold",
                 "interpolation": "never", "namespace": "/finance/data/econ/",
                 "review": {"permissions": ["admin", "maintain", "write"]}}  # 4.2: exactly these three, in this order
CLASS_TABLE = {
    "market_observation": ("business-day", "year", {"window": "publication-day", "statistics_window_business_days": 20}, "after_business_days"),
    "policy_target": ("change-point", "all", {"window": "none"}, "follows"),
    "administrative_daily": ("business-day", "year", {"window": "none"}, "after_business_days"),
    "revised_aggregate": ("month", "all", {"window": "scheduled-release", "alert_ratio": "0.05"}, "after_days_past_expected_release"),
}
FREQ_CONTINUITY = {"business-day": {"max_gap": 6, "unit": "days"}, "month": {"max_gap": 1, "unit": "months"},
                   "change-point": {"max_gap": None, "unit": None}}
SOURCE_DECIMALS = {"nyfed-markets": 2, "fiscaldata": 2, "frb-releases": 1}
CALENDAR_SPEC = {  # 4.5 as of v0.4; "<absent>" means the field must not be there
    "nyfed-business-days": {"kind": "rule", "publish_time": "09:00", "publish_time_zone": "America/New_York", "grace_hours": 6, "rule_valid_from": "2026-10-05",
                            "publish_time_zone_candidates": "<absent>"},
    "fiscaldata-release": {"kind": "calendar", "publish_time": None, "publish_time_zone": "unknown", "grace_hours": 6,
                           "publish_time_zone_candidates": ["America/New_York", "UTC"]},
    "frb-h6-release-dates": {"kind": "calendar", "publish_time": "13:00", "publish_time_zone": "America/New_York", "grace_hours": 6, "calendar_valid_from": "2021-02-23",
                             "publish_time_zone_candidates": "<absent>"},
}
# 4.5: a zone is written only when a provider text states it, quoted in `text`.
ZONE_QUOTES = {"nyfed-business-days": "about 9:00 a.m. ET", "frb-h6-release-dates": "\"For release at 1:00 p.m. Eastern Time\""}
ROUTE_NOTICE_FIELDS = ("route", "date", "affects_registered_route", "text", "checked", "milestone")
# 4.3 (v0.4): the Board's two entries, both route checks, read 2026-11-18.
BOARD_ROUTE_NOTICES = [("2027-03-31", False, "2026-11-18"), ("2027-07-01", False, "2026-11-18")]
H6_REGISTERED_ENDPOINT = ("www.federalreserve.gov", "/releases/h6/data/FRB_h6_xml.zip")
SHARED_GROUPS = [{"effr", "fomc-target"}, {"m1-sa", "m2-sa", "m1-nsa", "m2-nsa"},
                 {"debt-total", "debt-held-public", "debt-intragov"}]
EXPECTED_EARLIEST = {"effr": "2000-07-03", "fomc-target": "2000-07-03", "debt-total": "1993-04-01",
                     "debt-held-public": "1997-09-30", "debt-intragov": "1997-09-30",
                     "m1-sa": "1959-01", "m2-sa": "1959-01", "m1-nsa": "1959-01", "m2-nsa": "1959-01"}
SECTION16_ATTRIBUTION = {
    "frb-releases": "Source: Board of Governors of the Federal Reserve System, H.6 Money Stock Measures.",
    "fiscaldata": "Source: U.S. Department of the Treasury, Bureau of the Fiscal Service, Debt to the Penny.",
}
SDMX_FIELDS = ("series_name", "adjusted", "unit", "unit_mult", "missing_codes")


def section_registry(st):
    reg, raw = st.registry, st.registry_bytes
    p = [m for m, bad in (("CR found", b"\r" in raw), ("BOM found", raw.startswith(b"\xef\xbb\xbf")),
                          ("not indented", b"\n  " not in raw)) if bad]
    check("R0 registry is UTF-8, LF, no BOM, indented JSON (4)", p)
    check("R1 registry validates against registry.schema.json (12.1)", schema_errors(reg, st.schemas["registry"]))
    p = [f"{k} is {reg.get(k)!r}, expected {v!r}" for k, v in (("schema", REGISTRY_SCHEMA), ("family", "econ")) if reg.get(k) != v]
    if reg.get("conventions") != CONVENTIONS:
        p.append(f"conventions is {reg.get('conventions')!r}, expected {CONVENTIONS!r}")
    if reg.get("holiday_table") != "fed-holidays.json":
        p.append(f"holiday_table is {reg.get('holiday_table')!r}, expected 'fed-holidays.json'")
    want_top = ["schema", "conventions", "family", "holiday_table", "family_policy", "sources", "calendars", "series"]
    if sorted(reg) != sorted(want_top):
        p.append(f"top-level fields {sorted(reg)}, 4.1 names {sorted(want_top)} (unknown fields fail validation)")
    check(f"R2 top level: schema {REGISTRY_SCHEMA}, conventions {CONVENTIONS}, family econ, holiday_table fed-holidays.json, no other field (4.1)", p)
    # R31 (v0.8, 22.9, I7): the three registry changes of v0.8, and nothing else differs from the v0.7 version
    p = []
    srcs = reg.get("sources") if isinstance(reg.get("sources"), dict) else {}
    if (srcs.get(NYFED) or {}).get("terms_url") != NYFED_TERMS_V08:
        p.append(f"sources.{NYFED}.terms_url is {(srcs.get(NYFED) or {}).get('terms_url')!r}, 22.9 gives {NYFED_TERMS_V08!r}")
    for src_id, src in sorted(srcs.items()):
        if isinstance(src, dict) and src.get("terms_checked") != TERMS_CHECKED_V08:
            p.append(f"sources.{src_id}.terms_checked is {src.get('terms_checked')!r}, 22.9 gives {TERMS_CHECKED_V08!r}")
    v07 = registry_as_of(reg, "v0.7")
    back = json.loads(json.dumps(v07))
    back["conventions"] = CONVENTIONS
    for src_id, src in (back.get("sources") or {}).items():
        if isinstance(src, dict):
            src["terms_checked"] = TERMS_CHECKED_V08
            if src_id == NYFED:
                src["terms_url"] = NYFED_TERMS_V08
    if canon_bytes(back) != canon_bytes(reg) and not p:
        p.append("the registry differs from its v0.7 version (I7) in more than conventions, the New York Fed terms_url and terms_checked")
    vers = registry_versions(st)
    check("R31 the v0.8 registry changes (22.9): the New York Fed terms_url https://www.newyorkfed.org/privacy/termsofuse and terms_checked 2026-11-20 for all three sources; the v0.7 and v0.6 versions are derived by the substitutions of I7", p,
          f"current {vers['current'][0][:16]}, v0.7 {vers['v0.7'][0][:16]}, v0.6 {vers['v0.6'][0][:16]}")
    fp = reg.get("family_policy")
    p = [] if fp == FAMILY_POLICY else [f"got {fp}"]
    if isinstance(fp, dict) and fp.get("review") != FAMILY_POLICY["review"]:
        p.append(f"review is {fp.get('review')!r}; 4.2 gives exactly {{\"permissions\": [\"admin\", \"maintain\", \"write\"]}}, in this order (a narrower list needs a conventions change)")
    check("R3 family_policy holds exactly the econ values: archive permanent, review permissions admin, maintain, write in this order (4.2, 11.5)", p)
    series_list = reg.get("series", [])
    ids = [s.get("id") for s in series_list]
    p = []
    for i in ids:
        if not (isinstance(i, str) and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", i, re.ASCII) and 2 <= len(i) <= 40):
            p.append(f"{i!r} is not 2 to 40 lowercase letters, digits and single hyphens")
        if i in RESERVED_IDS:
            p.append(f"{i!r} is reserved")
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        p.append(f"duplicate ids {dup}")
    check("R4 series ids valid, unique and not reserved (4.1, 12.1)", p, ", ".join(ids))
    check("R5 no series overrides a family policy field (4.2)", [f"{s['id']} overrides {sorted(set(s) & set(FAMILY_POLICY))}" for s in series_list if set(s) & set(FAMILY_POLICY)])

    sources, cals = reg.get("sources", {}), reg.get("calendars", {})
    p = []
    for sid, src in sorted(sources.items()):
        if src.get("key_required") is not False:
            p.append(f"{sid}: key_required must be false")
        rq = src.get("request", {})
        if not (isinstance(rq.get("min_interval_seconds"), int) and rq["min_interval_seconds"] >= 1):
            p.append(f"{sid}: min_interval_seconds")
        if not (isinstance(rq.get("max_retries"), int) and 0 <= rq["max_retries"] <= 3):
            p.append(f"{sid}: max_retries")
        if rq.get("user_agent") != USER_AGENT:
            p.append(f"{sid}: user_agent {rq.get('user_agent')!r}; 4.3 gives exactly {USER_AGENT!r} for every source")
        if "contact" not in rq or rq["contact"] not in (None, PROJECT_CONTACT):
            p.append(f"{sid}: contact {rq.get('contact', '<absent>')!r}; 4.3 gives null or the project address {PROJECT_CONTACT}")
        elif rq["contact"] is not None:
            p.append(f"{sid}: contact {rq['contact']!r}; 4.3 (v0.5) states that on 2026-11-18 none of the three providers requires a contact, so contact is null for all three")
        if sorted(rq) != sorted(("min_interval_seconds", "max_retries", "user_agent", "contact")):
            p.append(f"{sid}: request fields {sorted(rq)}; 4.3 names min_interval_seconds, max_retries, user_agent, contact (unknown fields fail validation)")
        if src.get("calendar") not in cals:
            p.append(f"{sid}: calendar {src.get('calendar')!r} is not a registry calendar")
    check(f"R6 sources: keyless, request limits, user_agent exactly {USER_AGENT!r}, contact null or {PROJECT_CONTACT} and, as 4.3 states for 2026-11-18, null for all three; calendar references (4.3, 18)", p,
          ", ".join(f"{sid} contact {((src.get('request') or {}).get('contact'))}" for sid, src in sorted(sources.items())))

    # Placeholders (4.3, 4.4)
    p = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                yield from walk(v, path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from walk(v, path + [str(i)])
        elif isinstance(node, str):
            yield path, node
    for path, text in walk(reg, []):
        found = placeholders_in(text)
        if not found:
            continue
        where = ".".join(path)
        in_text = len(path) == 3 and path[0] == "sources" and path[2] in ("attribution", "notice")
        in_params = len(path) >= 4 and path[0] == "series" and path[2] == "fetch" and path[3] == "parameters"
        allowed = {"{data_name}", "{year}"} if in_text else {"{start}", "{end}", "{page}"} if in_params else set()
        bad = [x for x in found if x not in allowed]
        if bad:
            p.append(f"{where}: {bad}")
    check("R7 placeholders: {data_name} and {year} only in attribution and notice; {start}, {end}, {page} only in fetch parameters (4.3, 4.4)", p)
    p = [f"{sid}: {sources.get(sid, {}).get('attribution')!r} vs section 16 {want!r}" for sid, want in SECTION16_ATTRIBUTION.items()
         if sources.get(sid, {}).get("attribution") != want]
    check("R8 Board and Treasury attribution equal section 16 exactly, final period included (16)", p)
    if not any(path.is_file() for path in RAW_TERMS.values()):
        skip("R9 license texts appear word for word in the saved terms pages (4.3 VERIFIED)", "saved terms pages absent")
    else:
        p = []
        for sid, path in RAW_TERMS.items():
            if path.is_file() and norm_text(sources.get(sid, {}).get("license", "")) not in html_text(path.read_bytes()):
                p.append(f"{sid}: license sentence not found in {path.name}")
        nyf = sources.get("nyfed-markets", {}).get("attribution", "").replace("{year}", "[year]")
        if RAW_TERMS["nyfed-markets"].is_file() and norm_text(nyf) not in html_text(RAW_TERMS["nyfed-markets"].read_bytes()):
            p.append("nyfed-markets: default attribution form not found in the terms page")
        check("R9 license texts and the New York Fed default attribution appear word for word in the saved terms pages (4.3 VERIFIED)", p)

    # Calendars (4.5)
    p = []
    if set(cals) != set(CALENDAR_SPEC):
        p.append(f"calendar ids {sorted(cals)} differ from {sorted(CALENDAR_SPEC)}")
    for cid, want in CALENDAR_SPEC.items():
        cal = cals.get(cid, {})
        for k, v in want.items():
            if cal.get(k, "<absent>") != v:
                p.append(f"{cid}: {k} is {cal.get(k, '<absent>')!r}, 4.5/14.2 give {v!r}")
        zone = cal.get("publish_time_zone")
        if (zone == "unknown") != ("publish_time_zone_candidates" in cal):
            p.append(f"{cid}: publish_time_zone_candidates must be present exactly when the zone is \"unknown\" (4.5)")
        if cal.get("business_day_zone") != "America/New_York":
            p.append(f"{cid}: business_day_zone")
        if cal.get("kind") == "calendar" and not cal.get("url"):
            p.append(f"{cid}: a calendar without a url (4.5)")
        if cal.get("kind") == "rule" and ("url" in cal or "calendar_valid_from" in cal):
            p.append(f"{cid}: a rule with a url or calendar_valid_from (guessed)")
        if cal.get("kind") == "calendar" and "rule_valid_from" in cal:
            p.append(f"{cid}: a calendar with rule_valid_from (guessed)")
        if not cal.get("text"):
            p.append(f"{cid}: no provider text")
    fd = cals.get("fiscaldata-release", {})
    if urlsplit(fd.get("url", "")).path != "/services/calendar/release" or fd.get("dataset_id") != "015-BFS-2014Q3-065" or "released" not in fd.get("ignore_fields", []):
        p.append("fiscaldata-release url, dataset_id or ignored released flag")
    h6 = cals.get("frb-h6-release-dates", {})
    if urlsplit(h6.get("url", "")).path != "/releases/h6/releaseDates.json" or set(h6.get("markers", {})) != {"**", "***"}:
        p.append("frb-h6-release-dates url or markers")
    check("R10 calendars carry the 4.5 fields with the values the text gives (kinds, publish times, zones as of v0.4: New York Fed and H.6 America/New_York, Fiscal Data unknown with candidates America/New_York and UTC; grace 6, rule_valid_from 2026-10-05, calendar_valid_from 2021-02-23)", p)

    # R27: unknown zones stay explicitly unknown (4.5, owner brief of 2026-11-18)
    p = []
    for cid, cal in sorted(cals.items()):
        zone, text = cal.get("publish_time_zone"), cal.get("text") or ""
        if zone == "unknown":
            cands = cal.get("publish_time_zone_candidates")
            allowed = ["America/New_York", "UTC"]
            if not isinstance(cands, list) or len(cands) < 2 or len(set(cands)) != len(cands) or any(c not in allowed for c in cands) \
                    or cands != [c for c in allowed if c in cands]:
                p.append(f"{cid}: candidates {cands!r} are not at least two of America/New_York and UTC, in that order (4.5)")
            if re.search(r"\b(ET|EST|EDT|UTC|GMT|Eastern Time)\b", text.replace("no stated time zone", "")):
                p.append(f"{cid}: the zone is unknown but the text names one: {text!r}")
        elif zone in ("America/New_York", "UTC"):
            q = ZONE_QUOTES.get(cid)
            if q is None or q not in text:
                p.append(f"{cid}: zone {zone} is written, but the text does not quote the provider's statement of it ({q!r}) (4.5: a zone read from the clock times alone is not a verification)")
        else:
            p.append(f"{cid}: publish_time_zone {zone!r} is not America/New_York, UTC or \"unknown\" (4.5)")
    check("R27 a publication zone is written only with the provider's statement quoted in text (New York Fed 'about 9:00 a.m. ET', H.6 'For release at 1:00 p.m. Eastern Time'); Fiscal Data's stays \"unknown\" with its candidates and a text that names no zone (2.3, 2.4, 4.5)", p)

    # R28: route notices (4.3, 19)
    p, n = [], 0
    for sid, src in sorted(sources.items()):
        if "route_notices" not in src:
            continue
        rn = src["route_notices"]
        if not isinstance(rn, list) or not rn:
            p.append(f"{sid}: route_notices present but empty or not a list (4.3: not empty when present)")
            continue
        for i, e in enumerate(rn):
            n += 1
            w = f"{sid} route_notices[{i}]"
            if not isinstance(e, dict) or sorted(e) != sorted(ROUTE_NOTICE_FIELDS):
                p.append(f"{w}: fields {sorted(e) if isinstance(e, dict) else e!r}, 4.3 gives exactly {list(ROUTE_NOTICE_FIELDS)}")
                continue
            for f in ("date", "checked"):
                try:
                    if not (isinstance(e[f], str) and RX_DATE.fullmatch(e[f])):
                        raise ValueError("not YYYY-MM-DD")
                    parse_date(e[f])
                except ValueError as exc:
                    p.append(f"{w}: {f} {e[f]!r}: {exc}")
            if not isinstance(e["affects_registered_route"], bool):
                p.append(f"{w}: affects_registered_route is not a boolean")
            for f in ("route", "text", "milestone"):
                if not is_str(e[f]):
                    p.append(f"{w}: {f} is not a text")
        if sid == "frb-releases":
            got = [(e.get("date"), e.get("affects_registered_route"), e.get("checked")) for e in rn if isinstance(e, dict)]
            if got != BOARD_ROUTE_NOTICES:
                p.append(f"{sid}: entries (date, affects, checked) {got}; 4.3 gives the two route checks {BOARD_ROUTE_NOTICES}")
    if "route_notices" not in sources.get("frb-releases", {}):
        p.append("frb-releases has no route_notices; 4.3 lists the Board entries (2027-03-31, 2027-07-01)")
    h6_eps = {(urlsplit(s["fetch"]["endpoint"]).hostname, urlsplit(s["fetch"]["endpoint"]).path) for s in series_list if s.get("source") == "frb-releases"}
    if h6_eps != {H6_REGISTERED_ENDPOINT}:
        p.append(f"H.6 endpoints {sorted(h6_eps)}; 4.3 names the release-page XML {H6_REGISTERED_ENDPOINT[0]}{H6_REGISTERED_ENDPOINT[1]} as the registered route")
    check("R28 route_notices: optional, not empty when present, each entry exactly route, date, affects_registered_route (boolean), text, checked, milestone; the Board's two route checks 2027-03-31 and 2027-07-01 (affects false, read 2026-11-18); the registered H.6 route is the release-page XML (4.3, 19)", p,
          f"{n} entr{'y' if n == 1 else 'ies'}")

    def per_series(name, fn):
        probs = []
        for s in series_list:
            try:
                probs += [f"{s['id']}: {x}" for x in fn(s)]
            except Exception as exc:
                probs.append(f"{s.get('id')}: {type(exc).__name__}: {exc}")
        check(name, probs)

    def r_source(s):
        src = sources.get(s["source"])
        if src is None:
            return [f"source {s['source']!r} not registered"]
        host = urlsplit(s["fetch"]["endpoint"]).hostname
        return [] if host == src["host"] else [f"endpoint host {host} is not the source host {src['host']} (guessed)"]
    per_series("R12 every series names a registered source; endpoint on the source's host (4.4, 4.6 references resolve)", r_source)

    def r_class(s):
        out = []
        freq, seg, rev, stl = CLASS_TABLE[s["class"]]
        if s["frequency"] != freq:
            out.append(f"frequency {s['frequency']}, 4.6 gives {freq}")
        if s["segment"] != seg:
            out.append(f"segment {s['segment']}, 4.6 gives {seg}")
        if s.get("revision") != rev:
            out.append(f"revision {s.get('revision')}, 4.6 gives {rev}")
        if list(s.get("staleness", {})) != [stl]:
            out.append(f"staleness keys {list(s.get('staleness', {}))}, 4.6 gives exactly [{stl}]")
        if s.get("continuity") != FREQ_CONTINUITY[s["frequency"]]:
            out.append(f"continuity {s.get('continuity')} (4.4)")
        return out
    per_series("R13 the 4.6 class table: frequency, segment, revision, exactly one staleness key, continuity (4.4, 4.6)", r_class)

    def r_follows(s):
        stl = s.get("staleness", {})
        if "follows" not in stl:
            return []
        tgt = stl["follows"]
        out = []
        if tgt not in st.series or tgt == s["id"]:
            out.append(f"follows {tgt!r} is not another registered series")
        elif "follows" in st.series[tgt]["staleness"]:
            out.append("follows a series that itself follows another")
        if s.get("derived_from", {}).get("series") != tgt:
            out.append("follows a series other than its derived_from source (2.2)")
        return out
    per_series("R14 follows names the EFFR series the target is derived from (2.2, 4.4)", r_follows)
    per_series("R15 decimals: EFFR and target 2, debt 2, H.6 1 (4.4)",
               lambda s: [] if SOURCE_DECIMALS.get(s["source"]) == s["decimals"] else [f"decimals {s['decimals']}"])

    def r_range(s):
        r = s["range"]
        out = [f"range {f} {r[f]} does not have {s['decimals']} places (4.4)" for f in ("min", "max") if frac_digits(r[f]) != s["decimals"]]
        if D(r["min"]) >= D(r["max"]):
            out.append("range min not below max (4.4)")
        return out
    per_series("R16 range: decimal strings with decimals places, min below max (4.4)", r_range)

    def r_units(s):
        out = []
        want = {"nyfed-markets": ("percent", "none"), "fiscaldata": ("usd", "none"), "frb-releases": ("usd-billions", None)}[s["source"]]
        if s["unit"] != want[0] or (want[1] and s["seasonal_adjustment"] != want[1]):
            out.append(f"unit {s['unit']} seasonal_adjustment {s['seasonal_adjustment']} (guessed by source)")
        return out
    per_series("R17 unit and seasonal adjustment fit the source (4.4)", r_units)

    def r_fetch(s):
        out = []
        recs = st.source_records
        schema_ids = {e["schema"] for e in s["extract"]}
        if all(i in recs.get("sdmx", {}) for i in schema_ids) and s["fetch"]["format"] != "sdmx-zip":
            out.append("SDMX schema with a non sdmx-zip format")
        if all(i in recs.get("records", {}) for i in schema_ids) and s["fetch"]["format"] != "json":
            out.append("JSON record schema with a non json format")
        if s["source"] == "fiscaldata":
            params = s["fetch"]["parameters"]
            if "page[size]" not in params or "page[number]" not in params:
                out.append("Fiscal Data request without explicit page[size] and page[number] (5)")
            elif not params["page[size]"].isdigit() or int(params["page[size]"]) > 10000:
                out.append("page[size] over 10,000 (5)")
            if "{page}" not in params.get("page[number]", ""):
                out.append("page[number] does not use {page}")
        return out
    per_series("R18 fetch format matches the extract schemas; Fiscal Data pages explicit and at most 10,000 rows (5)", r_fetch)

    def r_shared(s):
        out = []
        sw = s["fetch"].get("shared_with", [])
        for o in sw:
            if o == s["id"] or o not in st.series:
                out.append(f"shared_with {o!r} is not another registered series")
                continue
            other = st.series[o]
            if s["id"] not in other["fetch"].get("shared_with", []):
                out.append(f"{o} does not list it back")
            if other["source"] != s["source"]:
                out.append(f"{o} has another source")
            for f in ("endpoint", "parameters", "format"):
                if other["fetch"].get(f) != s["fetch"].get(f):
                    out.append(f"{o} has another {f}")
        want = next((g for g in SHARED_GROUPS if s["id"] in g), {s["id"]})
        if {s["id"], *sw} != want:
            out.append(f"shares with {sorted(set(sw))}, 11.3 gives {sorted(want - {s['id']})}")
        return out
    per_series("R19 shared_with is symmetric with identical source, endpoint and parameters: the groups of 11.3 (4.6)", r_shared)

    def r_extract(s):
        out = []
        recs = st.source_records
        eras = s["extract"]
        month = s["frequency"] == "month"
        fmt = r"\d{4}-\d{2}" if month else r"\d{4}-\d{2}-\d{2}"
        for e in eras:
            for f in ("from", "to"):
                if e[f] is not None and not re.fullmatch(fmt, e[f], re.ASCII):
                    out.append(f"{e['schema']} {f} {e[f]} not a {s['frequency']} period")
        if sorted(eras, key=lambda e: e["from"]) != eras:
            out.append("eras not ascending (4.6)")
        for a, b in zip(eras, eras[1:]):
            if a["to"] is None:
                out.append(f"{a['schema']} is open but another era follows (4.6)")
                continue
            nxt = month_add(a["to"], 1) if month else (parse_date(a["to"]) + dt.timedelta(days=1)).isoformat()
            if b["from"] != nxt:
                out.append(f"{a['schema']} ends {a['to']} but {b['schema']} starts {b['from']} (4.6: each starts the period after the previous ends)")
        if eras and eras[-1]["to"] is not None:
            out.append("the last era is not open (4.6)")
        if eras and eras[0]["from"] > s["earliest"]:
            out.append(f"the first era starts after earliest {s['earliest']} (4.6)")
        for e in eras:
            sdmx = e["schema"] in recs.get("sdmx", {})
            if e["schema"] in recs["records"]:
                rs = recs["records"][e["schema"]]
                if rs["source"] != s["source"]:
                    out.append(f"{e['schema']} belongs to source {rs['source']}")
                if (rs["from"], rs["to"]) != (e["from"], e["to"]):
                    out.append(f"{e['schema']} era {e['from']}..{e['to']} differs from source-records {rs['from']}..{rs['to']}")
                fields = {**rs["fields"], **rs["optional"]}
                for u in [e[k] for k in ("value", "lower", "upper") if k in e] + list((e.get("extra") or {}).keys()):
                    if u not in fields:
                        out.append(f"{e['schema']}: field {u!r} not in the record schema")
                for k, x in (e.get("extra") or {}).items():
                    if x not in EXTRA_PLACES:
                        out.append(f"{e['schema']}: extra {x} has no places in 5")
                vtype = fields.get(e.get("value"), {}).get("type")
                if vtype == "decimal-text-or-null":
                    if e.get("null_text") != "null" or e.get("missing_code") != "not-published":
                        out.append(f"{e['schema']}: a nullable value needs null_text 'null' and missing_code 'not-published' (2.3, 4.4)")
                elif "null_text" in e or "missing_code" in e:
                    out.append(f"{e['schema']}: null_text or missing_code on a value that is never null")
                if any(k in e for k in SDMX_FIELDS):
                    out.append(f"{e['schema']}: a non-SDMX era carries SDMX fields (4.6)")
            elif sdmx:
                sd = recs["sdmx"][e["schema"]]
                if sd["source"] != s["source"]:
                    out.append(f"{e['schema']} belongs to source {sd['source']}")
                if e.get("value") != "OBS_VALUE":
                    out.append("SDMX value is not OBS_VALUE (4.4)")
                missing = [k for k in ("series_name", "adjusted", "unit", "unit_mult") if not e.get(k)]
                if missing:
                    out.append(f"SDMX era lacks {missing} (4.6)")
                if e.get("adjusted", "").lower() != s["seasonal_adjustment"]:
                    out.append(f"adjusted {e.get('adjusted')} is not seasonal_adjustment {s['seasonal_adjustment']} (4.6)")
                if e.get("unit") not in sd["series_attributes"]["UNIT"] or e.get("unit_mult") not in sd["series_attributes"]["UNIT_MULT"]:
                    out.append("unit or unit_mult not allowed by h6-sdmx-2021 (5)")
                if sorted(e.get("missing_codes", [])) != sorted(H6_STATUS_NOTE):
                    out.append("missing_codes are not NA, ND, NC (2.4)")
            else:
                out.append(f"schema {e['schema']!r} is not in source-records.json")
            if s["class"] == "policy_target":
                if e.get("kind") == "rate":
                    if "value" not in e or "lower" in e or "upper" in e:
                        out.append(f"{e['schema']}: a rate era maps value only (4.4)")
                    if e["to"] is None or e["to"] > "2008-12-15":
                        out.append(f"{e['schema']}: rate era beyond 2008-12-15 (2.2)")
                elif e.get("kind") == "range":
                    if "lower" not in e or "upper" not in e or "value" in e:
                        out.append(f"{e['schema']}: a range era maps lower and upper only (4.4)")
                    if e["from"] < "2008-12-16":
                        out.append(f"{e['schema']}: range era before 2008-12-16 (2.2)")
                else:
                    out.append(f"{e['schema']}: a policy target era without kind (4.6)")
            elif any(k in e for k in ("kind", "lower", "upper")):
                out.append(f"{e['schema']}: kind/lower/upper outside a policy target (guessed)")
        if s["class"] == "market_observation":
            names = {e["schema"]: set((e.get("extra") or {}).values()) for e in eras}
            if names.get("effr-2016") != {"p1", "p25", "p75", "p99", "volume_usd_billions"}:
                out.append("effr-2016 extras are not p1, p25, p75, p99, volume_usd_billions (2.1, 5)")
            for old in ("effr-2000", "effr-2008"):
                if names.get(old) != {"intraday_low", "intraday_high", "std_deviation"}:
                    out.append(f"{old} extras are not intraday low, high and standard deviation (5)")
        return out
    per_series("R20 extract eras: ascending, contiguous, only the last open, first on or before earliest; equal to source-records.json; SDMX fields only on SDMX eras (4.4, 4.6, 5)", r_extract)

    def r_h6names(s):
        if s["source"] != "frb-releases":
            return []
        want = {("m1", "sa"): "M1.M", ("m2", "sa"): "M2.M", ("m1", "nsa"): "M1_N.M", ("m2", "nsa"): "M2_N.M"}
        got = {e.get("series_name") for e in s["extract"]}
        key = (s["id"].split("-")[0], s["seasonal_adjustment"])
        return [] if got == {want.get(key)} else [f"series_name {got} for {key}"]
    per_series("R21 H.6 series names M1.M, M2.M (SA), M1_N.M, M2_N.M (NSA) (2.4, 5)", r_h6names)

    def r_release(s):
        rl = s["release"]
        cal = cals.get(rl.get("calendar"))
        if cal is None:
            return [f"release calendar {rl.get('calendar')!r} not registered"]
        out = []
        if rl["basis"] in ("rule", "calendar") and rl["basis"] != cal["kind"]:
            out.append(f"release basis {rl['basis']} but calendar {rl['calendar']} is a {cal['kind']} (4.4)")
        if rl["calendar"] != sources[s["source"]]["calendar"]:
            out.append("release calendar is not the source's calendar (4.4)")
        if s["source"] == "fiscaldata" and rl["basis"] != "first-seen":
            out.append("Debt to the Penny release basis is not first-seen (6.3)")
        return out
    per_series("R22 release: basis rule or calendar matches the calendar's kind, first-seen for Debt to the Penny, the source's calendar (4.4, 6.3)", r_release)

    def r_derived(s):
        out = []
        df = s.get("derived_from")
        if s["class"] == "policy_target" and not df:
            out.append("policy target without derived_from (4.6)")
        if not df:
            return out
        tgt = df.get("series")
        if tgt not in st.series or tgt == s["id"]:
            return out + [f"derived_from {tgt!r} is not another registered series"]
        if tgt not in s["fetch"].get("shared_with", []):
            out.append("derived_from series is not in fetch.shared_with (4.6)")
        if sources[s["source"]].get("modification_label") and "derived by radmage finance" not in df.get("method", "").lower():
            out.append("method text does not label the data 'derived by RadMage Finance' (2.2)")
        return out
    per_series("R23 derived_from: the policy target names its EFFR source, fetched by the same request, labeled derived (2.2, 4.6)", r_derived)

    def r_ki(s):
        ki = s.get("known_inconsistencies", [])
        out = []
        fmt = r"\d{4}-\d{2}" if s["frequency"] == "month" else r"\d{4}-\d{2}-\d{2}"
        for k in ki:
            if not re.fullmatch(fmt, k["period"], re.ASCII):
                out.append(f"{k['period']} is not a {s['frequency']} period")
            if k["period"] < s["earliest"][:len(k["period"])]:
                out.append(f"{k['period']} before earliest")
        got = {k["period"]: k["text"] for k in ki}
        if s["id"] == "debt-total":
            if set(got) != {"2011-02-01", "2025-08-04"}:
                out.append(f"periods {sorted(got)}, 2.3 names 2011-02-01 and 2025-08-04")
            elif "$0.03" not in got["2011-02-01"] or "$10,000,000,000.00" not in got["2025-08-04"]:
                out.append("texts do not state the amounts of 2.3")
        if s["id"] == "effr" and "2003-07-20" not in got:
            out.append("the Sunday record 2003-07-20 is not listed (6.2)")
        return out
    per_series("R24 known_inconsistencies: debt-total 2011-02-01 and 2025-08-04 (2.3); effr 2003-07-20 (6.2)", r_ki)
    per_series("R25 earliest is the first period with a published value, as the text states (2.3, 4.4, 6.1)",
               lambda s: [] if EXPECTED_EARLIEST.get(s["id"], s["earliest"]) == s["earliest"] else [f"earliest {s['earliest']}"])

    def r_zero(s):
        out = []
        for e in s["extract"]:
            got = e.get("refuse_zero", "<absent>")
            if s["id"] in DEBT_SERIES:
                if got is not True:
                    out.append(f"{e['schema']}: refuse_zero is {got!r}; 2.3 gives true on the extract eras of the three debt series")
                if e.get("null_text") not in (None, "null"):
                    out.append(f"{e['schema']}: null_text {e.get('null_text')!r}; 2.3: only the string \"null\" means not published")
            elif got != "<absent>":
                # reading: 2.3 and D6 name the debt eras only; elsewhere a zero can be a real value (the target's 0.00 lower bound).
                out.append(f"{e['schema']}: refuse_zero {got!r} outside the three debt series (2.3 names the debt eras only)")
        return out
    per_series("R29 missing versus zero: every extract era of debt-total, debt-held-public and debt-intragov carries refuse_zero true and no null text but \"null\"; no other series carries refuse_zero (reading: 2.3 and D6 name only the debt eras) (2.3, 4.4)", r_zero)

    def r_accepted(s):
        return accepted_zero_problems(s, s["accepted_zeros"]) if "accepted_zeros" in s else []
    n_az = sum(len(s.get("accepted_zeros") or []) for s in series_list if isinstance(s.get("accepted_zeros"), list))
    probs = []
    for s in series_list:
        try:
            probs += [f"{s['id']}: {x}" for x in r_accepted(s)]
        except Exception as exc:
            probs.append(f"{s.get('id')}: {type(exc).__name__}: {exc}")
    check("R30 accepted_zeros (v0.6): only on a series whose eras carry refuse_zero; each entry exactly period, field value, checked, evidence, authorized_by (a person's login), authorized_at (UTC); one business-day period, not a documented gap, on or before the ET date of authorized_at and on or before checked; periods unique; no ranges or patterns (2.3, 4.4)", probs,
          f"{n_az} entr{'y' if n_az == 1 else 'ies'} in the committed registry")


# ---------------------------------------------------------------------------
# Source records against the date-bounded schemas (section 5)
# ---------------------------------------------------------------------------


def type_ok(v, spec):
    t = spec["type"]
    plain = isinstance(v, str) and not isinstance(v, Num)
    if t == "date":
        if not (plain and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v, re.ASCII)):
            return False
        try:
            parse_date(v)
            return True
        except ValueError:
            return False
    if t == "number":
        return isinstance(v, Num)
    if t == "decimal-text":
        return plain and _DECIMAL_TEXT.fullmatch(v) is not None
    if t == "decimal-text-or-null":
        return plain and (v == "null" or _DECIMAL_TEXT.fullmatch(v) is not None)
    if t == "digits":
        return plain and re.fullmatch(r"\d+", v, re.ASCII) is not None
    if t == "flag":
        return plain and v in spec["values"]
    raise SchemaKeywordError(f"unknown source field type {t!r}")


def validate_records(st, records, container):
    schemas = {k: v for k, v in st.source_records["records"].items() if v["container"] == container}
    problems, counts = [], {}
    for r in records:
        if not isinstance(r, dict):
            problems.append("a record is not an object")
            continue
        date = next((r[s["date_field"]] for s in schemas.values() if s["date_field"] in r), None)
        if not isinstance(date, str):
            problems.append(f"record without a date field: {sorted(r)[:4]}")
            continue
        inforce = [k for k, s in schemas.items() if s["from"] <= date and (s["to"] is None or date <= s["to"])]
        if len(inforce) != 1:
            problems.append(f"{date}: {len(inforce)} schemas in force")
            continue
        sid = inforce[0]
        s = schemas[sid]
        counts[sid] = counts.get(sid, 0) + 1
        missing = sorted(set(s["fields"]) - set(r))
        unknown = sorted(set(r) - set(s["fields"]) - set(s["optional"]))
        if missing:
            problems.append(f"{date} ({sid}): missing {missing}")
        if unknown:
            problems.append(f"{date} ({sid}): unknown fields {unknown}")
        for f, spec in {**s["fields"], **s["optional"]}.items():
            if f not in r:
                continue
            v = r[f]
            if not type_ok(v, spec):
                shown = f"JSON number {v}" if isinstance(v, Num) else f"JSON {json_type_name(v)} {v!r}"
                problems.append(f"{date} ({sid}): {f} is a {shown}, not {spec['type']}")
            if isinstance(v, Num):
                if re.search(r"[eE]", v):
                    problems.append(f"{date} ({sid}): {f} uses an exponent (5)")
                if sig_digits(v) > 15:
                    problems.append(f"{date} ({sid}): {f} has more than 15 significant digits (5)")
        for ser in st.series.values():
            era = era_for(ser, date)
            if era is None or era["schema"] != sid:
                continue
            for k in ("value", "lower", "upper"):
                f = era.get(k)
                if f and f in r and str(r[f]) != era.get("null_text"):
                    v = str(r[f])
                    # 2.3 (v0.6): an accepted_zeros entry accepts an exact zero for its one period and field.
                    accepted = k == "value" and is_exact_zero(v) and date in accepted_zero_periods(ser)
                    if era.get("refuse_zero") is True and is_exact_zero(v) and not accepted:
                        problems.append(f"{date}: {f}={v!r} equals zero, which refuse_zero makes invalid for {ser['id']} (2.3, 11.4: never stored)")
                    if frac_digits(v) > ser["decimals"]:
                        problems.append(f"{date}: {f}={v} has more than {ser['decimals']} fraction digits ({ser['id']}, 5)")
                    elif accepted:
                        pass  # reading: an accepted zero is stored (2.3), so the range (min 1.00 for the debt series) cannot refuse it; see the report
                    elif _DECIMAL_TEXT.fullmatch(v) and not (D(ser["range"]["min"]) <= D(v) <= D(ser["range"]["max"])):
                        problems.append(f"{date}: {f}={v} outside the range of {ser['id']} (11.4)")
            for src_f, dst in (era.get("extra") or {}).items():
                if src_f in r and frac_digits(str(r[src_f])) > EXTRA_PLACES.get(dst, 99):
                    problems.append(f"{date}: {src_f}={r[src_f]} has more than {EXTRA_PLACES[dst]} places (5)")
    return problems, counts


def order_problems(dates, label):
    out = []
    if len(set(dates)) != len(dates):
        out.append(f"{label}: duplicate dates (11.4)")
    asc = all(a < b for a, b in zip(dates, dates[1:]))
    desc = all(a > b for a, b in zip(dates, dates[1:]))
    if not (asc or desc):
        out.append(f"{label}: dates not in one consistent order (6.2)")
    return out, ("ascending" if asc else "descending" if desc else "unordered")


def max_gap(dates):
    ds = sorted(parse_date(x) for x in dates)
    gaps = [((b - a).days, a.isoformat(), b.isoformat()) for a, b in zip(ds, ds[1:])]
    return max(gaps) if gaps else (0, None, None)


def weekend_problems(st, dates, series_ids):
    out = []
    for x in dates:
        if parse_date(x).weekday() >= 5:
            for sid in series_ids:
                if st.series[sid]["frequency"] == "business-day" and x not in ki_periods(st.series[sid]):
                    out.append(f"{x} ({parse_date(x).strftime('%A')}) not in {sid} known_inconsistencies")
    return out


def h6_fixture_checks(st, path, doc):
    """A fixture in the SDMX reader's output shape (17.4): `prepared`, the registered `series`
    with their attributes and observations, and the list of release dates."""
    sd = st.source_records["sdmx"]["h6-sdmx-2021"]
    by_name = {s["extract"][0]["series_name"]: s for s in st.series.values() if s["source"] == "frb-releases"}
    problems, copies = [], {}
    if not isinstance(doc.get("prepared"), str):
        problems.append("prepared missing (17.4)")
    for i, entry in enumerate(doc.get("series", [])):
        attrs, obs = entry.get("attributes", {}), entry.get("observations", [])
        name = attrs.get("SERIES_NAME")
        ser = by_name.get(name)
        if ser is None:
            problems.append(f"series[{i}]: {name!r} is not a registered series name (17.4: the registered series)")
            continue
        copies.setdefault(name, []).append((attrs, obs))
        if set(attrs) != set(sd["series_attributes"]):
            problems.append(f"{name}: series attributes {sorted(attrs)}")
        for a, allowed in sd["series_attributes"].items():
            if isinstance(allowed, list) and attrs.get(a) not in allowed:
                problems.append(f"{name}: {a}={attrs.get(a)}")
        if attrs.get("ADJUSTED") != ser["extract"][0]["adjusted"]:
            problems.append(f"{name}: ADJUSTED {attrs.get('ADJUSTED')} but the registry says {ser['extract'][0]['adjusted']}")
        months = []
        for o in obs:
            if set(o) != set(sd["observation_attributes"]):
                problems.append(f"{name}: obs attributes {sorted(o)}")
                break
            tp = o["TIME_PERIOD"]
            months.append(tp[:7])
            try:
                if parse_date(tp) != month_end(tp[:7]):
                    problems.append(f"{name}: {tp} not a month end")
            except ValueError:
                problems.append(f"{name}: TIME_PERIOD {tp!r}")
            if o["OBS_STATUS"] not in sd["observation_attributes"]["OBS_STATUS"]:
                problems.append(f"{name}: OBS_STATUS {o['OBS_STATUS']}")
            if o["OBS_STATUS"] != "A":
                continue
            if not isinstance(o["OBS_VALUE"], str) or not _DECIMAL_TEXT.fullmatch(o["OBS_VALUE"]):
                problems.append(f"{name}: OBS_VALUE {o['OBS_VALUE']!r}")
            elif frac_digits(o["OBS_VALUE"]) > ser["decimals"]:
                problems.append(f"{name}: {tp} has more than {ser['decimals']} fraction digits")
            elif not (D(ser["range"]["min"]) <= D(o["OBS_VALUE"]) <= D(ser["range"]["max"])):
                problems.append(f"{name}: {tp} outside range")
        if months != sorted(set(months)) or any(month_add(a, 1) != b for a, b in zip(months, months[1:])):
            problems.append(f"{name}: months are not ascending and contiguous (4.4)")
    for name in sorted(set(by_name) - set(copies)):
        problems.append(f"{name} is registered but not in the fixture")
    for name, cs in sorted(copies.items()):
        if any(c != cs[0] for c in cs):
            problems.append(f"{name}: copies differ in attributes or observations (5)")
    # 4.5: the markers are stripped from the dates and kept; the fetch body may still carry them.
    markers = sorted(st.registry["calendars"]["frb-h6-release-dates"].get("markers", {}), key=len, reverse=True)
    raw_dates = doc.get("release_dates", [])
    dates = [next((x[:-len(m)] for m in markers if x.endswith(m)), x) if isinstance(x, str) else x for x in raw_dates]
    if dates != sorted(set(map(str, dates))) or not all(isinstance(x, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", x, re.ASCII) for x in dates):
        problems.append("release_dates are not ascending unique YYYY-MM-DD dates, each with at most one registered marker (4.5)")
    check(f"SR8 {path.name}: the registered H.6 series match h6-sdmx-2021 in the SDMX reader's output shape (attributes, month ends, codelist, decimals, range, identical copies), with prepared and release dates (5, 17.4)",
          problems, f"{sum(len(v) for v in copies.values())} series entries, {len(dates)} release dates")
    if not RAW_H6_ZIP.is_file() or not RAW_H6_DATES.is_file():
        skip(f"SR9 {path.name} equals the saved H.6 release file and release dates", "saved H.6 files absent")
        return
    h6, problems = load_h6(st), []
    if doc.get("prepared") != h6["prepared"]:
        problems.append(f"prepared {doc.get('prepared')} vs saved {h6['prepared']}")
    for name, cs in sorted(copies.items()):
        saved = h6["series"].get(name, [])
        if len(cs) != len(saved):
            problems.append(f"{name}: {len(cs)} copies, the saved file has {len(saved)} (fixture says every copy)")
        for (attrs, obs), sv in zip(cs, saved):
            if dict(attrs) != sv["attrs"]:
                problems.append(f"{name}: attributes differ from the saved file")
            if [dict(o) for o in obs] != sv["obs"][-len(obs):]:
                problems.append(f"{name}: observations are not the last {len(obs)} of the saved file, unchanged")
    if dates != h6_release_dates(st):
        problems.append("release_dates differ from the saved releaseDates.json")
    check(f"SR9 {path.name} equals the saved H.6 release file (last months of every copy, unchanged) and the saved release dates (fixture says unchanged)", problems)


def section_source_records(st):
    for path in sorted(SOURCE_FIXTURES.glob("*.json")):
        doc = load_numtext(path.read_bytes())
        if "series" in doc and "release_dates" in doc:
            h6_fixture_checks(st, path, doc)
            continue
        containers = [c for c in ("refRates", "data") if c in doc]
        if len(containers) != 1:
            check(f"SR1 {path.name} has exactly one record container", [f"found {containers}"])
            continue
        c = containers[0]
        problems, counts = validate_records(st, doc[c], c)
        dates = [r.get("effectiveDate") or r.get("record_date") for r in doc[c]]
        more, order = order_problems(dates, path.name)
        fed = [s for s in st.series if st.series[s]["extract"][0]["schema"] in {k for k, v in st.source_records["records"].items() if v["container"] == c}]
        check(f"SR1 {path.name}: every record matches the schema in force for its date, field for field; weekends only as known inconsistencies (5, 6.2)",
              problems + more + weekend_problems(st, dates, fed), f"{len(doc[c])} records ({order}), {', '.join(f'{k} {v}' for k, v in sorted(counts.items()))}")
        raw_path, raw_key = (RAW_EFFR, "effr") if c == "refRates" else (RAW_DTP, "dtp")
        raw = load_raw(st, raw_key, raw_path)
        if raw is None:
            skip(f"SR2 {path.name} records equal the saved full response", f"{raw_path.name} absent")
            continue
        by_date = {r.get("effectiveDate") or r.get("record_date"): r for r in raw[c]}
        val_problems, text_problems = [], []
        for r in doc[c]:
            d = r.get("effectiveDate") or r.get("record_date")
            o = by_date.get(d)
            if o is None:
                val_problems.append(f"{d} not in the saved response")
                continue
            if list(o) != list(r):
                val_problems.append(f"{d}: field sets or order differ")
                continue
            for f in r:
                a, b = r[f], o[f]
                if isinstance(a, Num) != isinstance(b, Num):
                    val_problems.append(f"{d}: {f} type differs")
                elif isinstance(a, Num):
                    if D(a) != D(b):
                        val_problems.append(f"{d}: {f} {a} vs {b}")
                    elif str(a) != str(b):
                        text_problems.append(f"{d} {f} {a} (saved {b})")
                elif a != b:
                    val_problems.append(f"{d}: {f} {a!r} vs {b!r}")
        check(f"SR2 {path.name} records equal the saved full response, number text included (fixture says unchanged)",
              val_problems + ([f"{len(text_problems)} number texts rewritten, e.g. {', '.join(text_problems[:3])}"] if text_problems else []))

    raw = load_raw(st, "effr", RAW_EFFR)
    if raw is None:
        skip("SR3 saved EFFR response matches its schema eras (5)", f"{RAW_EFFR.name} absent")
    else:
        recs = raw.get("refRates", [])
        problems, counts = validate_records(st, recs, "refRates")
        top = sorted(set(raw) - {"refRates"})
        if top:
            problems.append(f"unexpected top-level keys {top}")
        dates = [r.get("effectiveDate") for r in recs]
        more, order = order_problems(dates, "EFFR")
        check("SR3 saved EFFR response: every record matches the schema in force, field for field; numbers within decimals, 15 digits, no exponent; one order (5, 6.2, 11.4)",
              problems + more, f"{len(recs)} records {min(dates)} to {max(dates)} ({order}), {', '.join(f'{k} {v}' for k, v in sorted(counts.items()))}")
        g = max_gap(dates)
        check("SR4 saved EFFR response: no gap over 6 days; weekend records only as known inconsistencies (4.4, 6.2, 11.4)",
              ([] if g[0] <= 6 else [f"gap {g}"]) + weekend_problems(st, dates, ["effr"]),
              f"longest gap {g[0]} days ({g[1]} to {g[2]}); weekend records {[x for x in dates if parse_date(x).weekday() >= 5]}")
        stats = [r["effectiveDate"] for r in recs if r["effectiveDate"] >= "2016-03-01" and not all(k in r for k in ("percentPercentile1", "volumeInBillions"))]
        check("SR5 saved EFFR response: effr-2016 records without statistics (now optional, 5)", [], f"{len(stats)} such records")

    raw = load_raw(st, "dtp", RAW_DTP)
    if raw is None:
        skip("SR6 saved Debt to the Penny response matches dtp-1993 (5)", f"{RAW_DTP.name} absent")
    else:
        recs = raw.get("data", [])
        problems, counts = validate_records(st, recs, "data")
        meta = raw.get("meta", {})
        if str(meta.get("total-count")) != str(len(recs)):
            problems.append(f"meta.total-count {meta.get('total-count')} but {len(recs)} rows received (5, 11.4)")
        dates = [r.get("record_date") for r in recs]
        more, order = order_problems(dates, "DTP")
        g = max_gap(dates)
        if g[0] > 6:
            more.append(f"gap {g}")
        check("SR6 saved Debt to the Penny response: every record matches dtp-1993; total-count equals rows; no gap over 6 days; no weekend record (5, 6.2, 11.4)",
              problems + more + weekend_problems(st, dates, ["debt-total", "debt-held-public", "debt-intragov"]),
              f"{len(recs)} records {dates[0]} to {dates[-1]} ({order}), total-count {meta.get('total-count')}, longest gap {g[0]} days")

    if not RAW_H6_ZIP.is_file():
        skip("SR7 saved H.6 zip: registered series match h6-sdmx-2021 (5)", f"{RAW_H6_ZIP.name} absent")
    else:
        h6 = load_h6(st)
        sd = st.source_records["sdmx"]["h6-sdmx-2021"]
        problems = []
        for ser in (s for s in st.series.values() if s["source"] == "frb-releases"):
            name = ser["extract"][0]["series_name"]
            copies = h6["series"].get(name, [])
            if not copies:
                problems.append(f"{name} not in the file")
            for cp in copies:
                if set(cp["attrs"]) != set(sd["series_attributes"]):
                    problems.append(f"{name}: series attributes {sorted(cp['attrs'])}")
                for a, allowed in sd["series_attributes"].items():
                    if isinstance(allowed, list) and cp["attrs"].get(a) not in allowed:
                        problems.append(f"{name}: {a}={cp['attrs'].get(a)}")
                if cp["attrs"].get("ADJUSTED") != ser["extract"][0]["adjusted"]:
                    problems.append(f"{name}: ADJUSTED {cp['attrs'].get('ADJUSTED')} but the registry says {ser['extract'][0]['adjusted']}")
                if cp["other"]:
                    problems.append(f"{name}: children other than Annotations and Obs: {cp['other']}")
                for o in cp["obs"]:
                    if set(o) != set(sd["observation_attributes"]):
                        problems.append(f"{name}: obs attributes {sorted(o)}")
                        break
                    tp = o["TIME_PERIOD"]
                    try:
                        if parse_date(tp) != month_end(tp[:7]):
                            problems.append(f"{name}: {tp} not a month end")
                    except ValueError:
                        problems.append(f"{name}: TIME_PERIOD {tp!r}")
                    if o["OBS_STATUS"] not in sd["observation_attributes"]["OBS_STATUS"]:
                        problems.append(f"{name}: OBS_STATUS {o['OBS_STATUS']}")
                    if o["OBS_STATUS"] != "A":
                        continue  # 2.4: OBS_VALUE then ignored
                    if not _DECIMAL_TEXT.fullmatch(o["OBS_VALUE"]):
                        problems.append(f"{name}: OBS_VALUE {o['OBS_VALUE']!r}")
                    elif frac_digits(o["OBS_VALUE"]) > ser["decimals"]:
                        problems.append(f"{name}: {tp} has more than {ser['decimals']} fraction digits")
                    elif not (D(ser["range"]["min"]) <= D(o["OBS_VALUE"]) <= D(ser["range"]["max"])):
                        problems.append(f"{name}: {tp} outside range")
            if any((c["attrs"], c["obs"]) != (copies[0]["attrs"], copies[0]["obs"]) for c in copies):
                problems.append(f"{name}: copies differ in attributes or observations (5)")
        check("SR7 saved H.6 zip: the registered series match h6-sdmx-2021 (attributes, Annotations allowed, month ends, codelist, decimals, range, identical copies with namespace ignored) (5)",
              problems, f"Prepared {h6['prepared']}")


# ---------------------------------------------------------------------------
# Facts the text states about the saved data
# ---------------------------------------------------------------------------


def derive_change_points(st, records):
    fomc = st.series["fomc-target"]
    rows = sorted((r for r in records if is_business_day(parse_date(r["effectiveDate"]))), key=lambda r: r["effectiveDate"])
    out, prev = [], None
    for r in rows:
        era = era_for(fomc, r["effectiveDate"])
        if era["kind"] == "rate":
            key = ("rate", pad_decimal(str(r[era["value"]]), fomc["decimals"]))
        else:
            key = ("range", pad_decimal(str(r[era["lower"]]), fomc["decimals"]), pad_decimal(str(r[era["upper"]]), fomc["decimals"]))
        if key != prev:
            cp = {"effective": r["effectiveDate"], "kind": key[0]}
            if key[0] == "rate":
                cp["value"] = key[1]
            else:
                cp["lower"], cp["upper"] = key[1], key[2]
            out.append(cp)
            prev = key
    if out:
        out[0]["starts_before_data"] = True
    return out


def missing_business_days(dates):
    s = set(dates)
    out = []
    d, last = parse_date(min(dates)), parse_date(max(dates))
    while d <= last:
        if is_business_day(d) and d.isoformat() not in s:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


QUOTES = [
    ("nyfed-addl", "except in extraordinary circumstances", "2.1"),
    ("nyfed-addl", "on the same day", "2.1 'the same day'"),
    ("nyfed-addl", "Any time a rate were to be revised, a footnote would indicate the revision", "2.1"),
    ("nyfed-addl", "updated summary statistics are published on a lagged basis shortly after the end of each quarter", "2.1"),
    ("nyfed-addl", "The New York Fed may decide to revise the summary statistics or publish additional summary statistics on a lagged basis", "2.1"),
    ("nyfed-addl", "Additional Reference Rate Data", "2.1"),
    ("nyfed-addl", "Should the prior day's rate be published, neither the percentile nor volume summary statistics will be published", "5"),
    ("nyfed-addl", "Last Updated: 10/5/2026", "2.1, 4.5 rule_valid_from"),
    ("nyfed-terms", "may alter the methods of calculation, publication schedule, rate revision practices or availability of reference rates", "2.1"),
    ("dtp-dataset", "updated at the end of each business day with data from the previous business day", "2.3"),
    ("h6-landing", "on the fourth Tuesday of every month, generally at 1:00 p.m.", "2.4"),
    ("h6-landing", "Annual seasonal factor review", "2.4"),
    ("h6-landing", "First monthly release", "2.4"),
    ("ddp-faq", "overwritten as the release updates", "2.4"),
    ("ddp-faq", "archived versions from previous dates will not be available", "2.4"),
]


def section_facts(st):
    present = {k: p for k, p in RAW_PAGES.items() if p.is_file()}
    if not present:
        skip("F0 quoted provider text appears in the saved pages", "saved pages absent")
    else:
        texts = {k: html_text(p.read_bytes()).lower() for k, p in present.items()}
        p = [f"{where}: {q!r} not in {RAW_PAGES[k].name}" for k, q, where in QUOTES if k in texts and norm_text(q).lower() not in texts[k]]
        check("F0 every VERIFIED quotation of 2.1, 2.3, 2.4 and 5 appears in the saved provider pages", p, f"{len(QUOTES)} quotations")

    raw = load_raw(st, "effr", RAW_EFFR)
    if raw is None:
        skip("F1 EFFR facts", f"{RAW_EFFR.name} absent")
    else:
        recs = raw["refRates"]
        by = {r["effectiveDate"]: r for r in recs}
        cps = derive_change_points(st, recs)
        check("F1 EFFR: 73 change points from 2000-07-03 to 2026-09-17 (6.1)",
              [] if (len(cps), cps[0]["effective"], cps[-1]["effective"]) == (73, "2000-07-03", "2026-09-17") else [f"{len(cps)} change points {cps[0]['effective']} to {cps[-1]['effective']}"],
              f"{len(cps)}, {cps[0]['effective']} ({cps[0].get('value')}) to {cps[-1]['effective']} ({cps[-1].get('lower')} to {cps[-1].get('upper')})")
        with_to = sorted(r["effectiveDate"] for r in recs if "targetRateTo" in r)
        without_to = sorted(r["effectiveDate"] for r in recs if "targetRateTo" not in r)
        check("F2 EFFR: a single target rate to 2008-12-15, a range from 2008-12-16 (2.2, 6.1)",
              [] if with_to[0] == "2008-12-16" and without_to[-1] == "2008-12-15" else [f"range from {with_to[0]}, last single rate {without_to[-1]}"])
        rr = sorted(r["effectiveDate"] for r in recs if r.get("revisionIndicator") == "r")
        check("F3 EFFR: revisionIndicator 'r' on 35 rows, 2000-07-10 to 2017-05-31 (2.1)",
              [] if (len(rr), rr[0], rr[-1]) == (35, "2000-07-10", "2017-05-31") else [f"{len(rr)} rows {rr[0]} to {rr[-1]}"], f"{len(rr)} rows")
        fn = [r["effectiveDate"] for r in recs if "footnoteId" in r]
        check("F4 EFFR: footnoteId seen once, 2023-07-25 (5)", [] if fn == ["2023-07-25"] else [f"{fn}"])
        g = max_gap(list(by))
        check("F5 EFFR: longest gap 4 days (4.4)", [] if g[0] == 4 else [f"{g}"], f"{g[0]} days")
        wk = sorted(x for x in by if parse_date(x).weekday() >= 5)
        same = wk == ["2003-07-20"] and {k: v for k, v in by["2003-07-20"].items() if k != "effectiveDate"} == {k: v for k, v in by["2003-07-21"].items() if k != "effectiveDate"}
        check("F6 EFFR: one weekend record, Sunday 2003-07-20, equal to Monday 2003-07-21 (6.2)", [] if same else [f"weekend records {wk}"])
        mbd = missing_business_days(list(by))
        nonbd = sorted(x for x in by if not is_business_day(parse_date(x)))
        check("F7 EFFR: a record on every New York Fed business day, and on no other day except 2003-07-20 (3; the registry holiday table)",
              ([f"{len(mbd)} business days without a record: {mbd[:3]}"] if mbd else []) + ([f"non-business-day records {nonbd}"] if nonbd != ["2003-07-20"] else []))
        early = load_raw(st, "effr_early", RAW_EFFR_EARLY)
        p = [] if min(by) == st.series["effr"]["earliest"] else [f"first record {min(by)}"]
        if early is not None and min(r["effectiveDate"] for r in early["refRates"]) != "2000-07-03":
            p.append("a search from 1990-01-01 starts elsewhere")
        check("F8 EFFR: earliest record 2000-07-03, also from a 1990-01-01 search (4.4 earliest)", p)
        fetched = http_date(RAW_EFFR_HEADERS)
        if fetched:
            last_due = max(x for x in by if et_wall_to_utc(next_business_day(parse_date(x)), 9) <= fetched)
            check("F9 EFFR: the saved response ends at the last period published by its fetch time under the 2.1 publication day rule",
                  [] if last_due == max(by) else [f"rule gives {last_due}, response ends {max(by)}"], f"fetched {fmt_utc(fetched)}, last period {max(by)}")

    raw = load_raw(st, "dtp", RAW_DTP)
    if raw is None:
        skip("F10 Debt to the Penny facts", f"{RAW_DTP.name} absent")
    else:
        recs = raw["data"]
        dates = [r["record_date"] for r in recs]
        check("F10 Debt to the Penny: 8,433 rows to 2026-11-12 (2.3)", [] if (len(recs), dates[-1]) == (8433, "2026-11-12") else [f"{len(recs)} rows to {dates[-1]}"])
        nul = [r["record_date"] for r in recs if r["debt_held_public_amt"] == "null" or r["intragov_hold_amt"] == "null"]
        both = [r["record_date"] for r in recs if r["debt_held_public_amt"] == "null" and r["intragov_hold_amt"] == "null"]
        check("F11 Debt to the Penny: breakouts 'null' on 2,958 record dates, both fields together, last 2005-03-30 (2.3)",
              [] if len(nul) == 2958 and nul == both and nul[-1] == "2005-03-30" else [f"{len(nul)} ({len(both)} both), last {nul[-1]}"])
        nonnull = [r["record_date"] for r in recs if r["debt_held_public_amt"] != "null"]
        nn = set(nonnull)
        last_in_month = {}
        for x in dates:
            last_in_month[x[:7]] = x
        fy = sorted(x for x in nonnull if x < "2001-10-01")
        fy_ends = sorted(v for k, v in last_in_month.items() if k[5:7] == "09" and "1997-09" <= k <= "2001-09")
        me_missing = sorted(v for k, v in last_in_month.items() if "2001-10" <= k <= "2005-02" and v not in nn)
        off_me = [x for x in nonnull if "2001-10-01" <= x < "2005-03-31" and x not in set(last_in_month.values())]
        p = []
        if fy != fy_ends or fy[0] != "1997-09-30" or fy[-1] != "2001-09-28":
            p.append(f"fiscal year ends with breakouts {fy}, all fiscal year ends {fy_ends}")
        if me_missing != ["2003-01-31"]:
            p.append(f"month ends without breakouts {me_missing}")
        if off_me:
            p.append(f"breakouts off a month end before 2005-03-31: {off_me}")
        if any(x not in nn for x in dates if x >= "2005-03-31"):
            p.append("a null on or after 2005-03-31")
        check("F12 Debt to the Penny: breakouts at fiscal year ends 1997-09-30 to 2001-09-28, month ends from 2001-10-31 except 2003-01-31, daily from 2005-03-31 (2.3)", p)
        mism = []
        for r in recs:
            if r["debt_held_public_amt"] != "null":
                diff = D(r["debt_held_public_amt"]) + D(r["intragov_hold_amt"]) - D(r["tot_pub_debt_out_amt"])
                if diff != 0:
                    mism.append((r["record_date"], diff))
        check("F13 Debt to the Penny: parts exceed the total only on 2011-02-01 ($0.03) and 2025-08-04 ($10,000,000,000.00) (2.3)",
              [] if mism == [("2011-02-01", D("0.03")), ("2025-08-04", D("10000000000.00"))] else [f"{mism}"])
        mbd = missing_business_days(dates)
        g = max_gap(dates)
        check("F14 Debt to the Penny: no record on 18 business days, 1995-11-20 to 2019-04-03; longest gap 5 days (2.3, 4.4)",
              [] if (len(mbd), mbd[0], mbd[-1], g[0]) == (18, "1995-11-20", "2019-04-03", 5) else [f"{len(mbd)} days {mbd[:1]} to {mbd[-1:]}, gap {g[0]}"],
              f"{len(mbd)} days; longest gap {g[0]} ({g[1]} to {g[2]})")
        effr = load_raw(st, "effr", RAW_EFFR)
        if effr is not None:
            ed = {r["effectiveDate"] for r in effr["refRates"]}
            dd = set(dates)
            p = [x for x in ("2021-12-24", "2021-12-31", "2026-07-03") if x not in ed or x not in dd]
            check("F15 EFFR and Debt to the Penny both have 2021-12-24, 2021-12-31 and 2026-07-03 (3)", p)
        for s_id, field in (("debt-total", "tot_pub_debt_out_amt"), ("debt-held-public", "debt_held_public_amt"), ("debt-intragov", "intragov_hold_amt")):
            first = next(r["record_date"] for r in recs if r[field] != "null")
            check(f"F16 {s_id}: earliest is the first published value (4.4)", [] if first == st.series[s_id]["earliest"] else [f"first value {first}"], first)
        fetched = http_date(RAW_DTP_HEADERS)
        if fetched and RAW_FD_CAL.is_file():
            cal = st.registry["calendars"]["fiscaldata-release"]
            nxt = next_business_day(parse_date(dates[-1]))
            pub = next_business_day(nxt)
            t = fd_calendar_time(st, "015-BFS-2014Q3-065", pub)
            prev_pub = next_business_day(parse_date(dates[-1]))
            # 4.5: the zone is unknown, so the response must fit every candidate reading: the last
            # record was out by the fetch even at the latest reading, the next not even at the earliest.
            last_out = cal_instant(prev_pub, FD_DEFAULT_TIME, cal, "latest")
            next_out = cal_instant(pub, t or FD_DEFAULT_TIME, cal, "earliest")
            ok = t is not None and next_out > fetched and last_out <= fetched
            check("F17 Debt to the Penny: the saved response ends at the last record published by its fetch time under 14.2 (next record date, published the following business day at 21:15) in every candidate reading of the unknown zone (4.5)",
                  [] if ok else [f"record {nxt} due {pub} {t} (earliest {fmt_utc(next_out)}), {dates[-1]} out by {fmt_utc(last_out)} at the latest, fetched {fmt_utc(fetched)}"],
                  f"fetched {fmt_utc(fetched)}; {dates[-1]} published {prev_pub} at 21:15, out by {fmt_utc(last_out)} at the latest; {nxt} due {pub} at {t}, not before {fmt_utc(next_out)}")
    if RAW_DTP_10001_HEADERS.is_file():
        status = RAW_DTP_10001_HEADERS.read_bytes().decode("utf-8", "replace").splitlines()[0]
        check("F18 Fiscal Data page[size]=10001 returned HTTP 404 (5)", [] if " 404 " in status + " " else [status], status)

    if not RAW_H6_ZIP.is_file():
        skip("F19 H.6 facts", f"{RAW_H6_ZIP.name} absent")
    else:
        h6 = load_h6(st)
        for name in ("M1.M", "M2.M", "M1_N.M", "M2_N.M"):
            copies = h6["series"].get(name, [])
            obs = copies[0]["obs"] if copies else []
            months = [o["TIME_PERIOD"][:7] for o in obs]
            p = []
            contiguous = all(month_add(a, 1) == b for a, b in zip(months, months[1:]))
            places = sorted({frac_digits(o["OBS_VALUE"]) for o in obs})
            status = sorted({o["OBS_STATUS"] for o in obs})
            ident = all((c["attrs"], c["ann"], c["obs"]) == (copies[0]["attrs"], copies[0]["ann"], copies[0]["obs"]) for c in copies)
            if not obs or not contiguous or places != [1] or status != ["A"] or months[0] != "1959-01" or not ident:
                p.append(f"contiguous {contiguous}, places {places}, status {status}, first {months[:1]}, identical {ident}")
            if name in ("M1.M", "M1_N.M") and (len(copies) != 2 or len({c["ns"] for c in copies}) != 2):
                p.append(f"{len(copies)} copies in {len({c['ns'] for c in copies})} namespaces (5 says twice, different namespaces)")
            check(f"F19 H.6 {name}: monthly from 1959-01, contiguous, 1 decimal, OBS_STATUS A, copies identical (2.4, 5)", p,
                  f"{len(obs)} obs {months[0]} to {months[-1]}, {len(copies)} cop{'y' if len(copies) == 1 else 'ies'}")
        check("F20 H.6: the file holds 133 series names (5)", [] if len(h6["series"]) == 133 else [f"{len(h6['series'])} names"],
              f"{len(h6['series'])} names, {sum(len(v) for v in h6['series'].values())} Series elements")
        m12 = sum(len(c["obs"]) for n in ("M1.M", "M2.M", "M1_N.M", "M2_N.M") for c in h6["series"][n])
        check("F21 H.6: every observation has OBS_STATUS A, 213,575 of 213,575 (2.4)",
              [] if h6["obs_total"] == 213575 and h6["status_all"] == {"A"} else [f"{h6['obs_total']} observations, statuses {sorted(h6['status_all'])}"],
              f"213,575 is the whole file (all 165 Series elements); M1 and M2 alone are {m12} including duplicate copies")
        cl = h6_codelist("CL_OBS_STATUS")
        check("F22 H.6 codelist texts for NA, ND, NC are 'Not available', 'No data', 'Not calculable' (2.4)",
              [] if cl and all(cl.get(k) == v for k, v in H6_STATUS_NOTE.items()) else [f"{cl}"], f"from H6_struct.xml: {cl}")
        dates = h6_release_dates(st)
        if dates:
            prep = h6["prepared"]
            latest = dates[-1]
            gap = (parse_date(latest) - parse_date(prep[:10])).days
            lm = http_header(RAW_H6_DATES_HEADERS, "Last-Modified")
            lm_t = dt.datetime.strptime(lm, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=UTC) if lm else None
            check("F23 H.6: Prepared 2026-10-19T15:17:34 without a zone, 8 days before the release carrying the data (2.4)",
                  [] if prep == "2026-10-19T15:17:34" and gap == 8 else [f"Prepared {prep}, {gap} days before {latest}"],
                  f"latest release {latest}, newest month {h6['series']['M1.M'][0]['obs'][-1]['TIME_PERIOD'][:7]}; releaseDates.json Last-Modified {lm} = {et_local(lm_t).strftime('%H:%M:%S') if lm_t else '?'} ET")
    if not RAW_H6_DATES.is_file():
        skip("F24 H.6 releaseDates.json facts", f"{RAW_H6_DATES.name} absent")
    else:
        doc = load_raw(st, "h6dates", RAW_H6_DATES)
        raw_dates = [x for y in doc for m in y["Months"] for x in m["Dates"]]
        marks = {}
        for x in raw_dates:
            m = re.fullmatch(r"(\d{8})(\*{0,3})", x, re.ASCII)
            if m and m.group(2):
                marks.setdefault(m.group(2), []).append(m.group(1))
        dates = h6_release_dates(st)
        exc = [x for x in dates if x >= "2021-02-23" and parse_date(x) != nth_weekday(int(x[:4]), int(x[5:7]), 1, 4)]
        p = []
        if set(marks) != {"**", "***"} or max(marks["**"]) != "20210323" or marks["***"] != ["20210223"]:
            p.append(f"markers {sorted(marks)}, last ** {max(marks.get('**', ['none']))}, *** {marks.get('***')}")
        if exc != ["2024-12-26"]:
            p.append(f"monthly releases not on the fourth Tuesday: {exc}")
        if st.registry["calendars"]["frb-h6-release-dates"].get("calendar_valid_from") != f"{marks['***'][0][:4]}-{marks['***'][0][4:6]}-{marks['***'][0][6:]}":
            p.append("calendar_valid_from is not the *** first monthly release")
        check("F24 H.6 releaseDates.json: past dates only, last ** 2021-03-23, *** 2021-02-23 = calendar_valid_from, fourth Tuesdays except 2024-12-26 (2.4, 4.5)", p,
              f"{len(dates)} dates {dates[0]} to {dates[-1]}")
    if not RAW_FD_CAL.is_file():
        skip("F25 Fiscal Data calendar facts", f"{RAW_FD_CAL.name} absent")
    else:
        cal = json.loads(RAW_FD_CAL.read_bytes().decode("utf-8"))
        fcal = st.registry["calendars"]["fiscaldata-release"]
        dtp = [e for e in cal if e.get("datasetId") == "015-BFS-2014Q3-065"]
        fetched = http_date(RAW_FD_CAL_HEADERS)

        def at_earliest(e):  # 4.5: an entry is surely in the future only if even its earliest reading is
            return cal_instant(parse_date(e["date"]), e["time"], fcal, "earliest")
        future = all(at_earliest(e) > fetched for e in dtp) if fetched else None
        fut_true = [e for e in cal if e.get("released") == "true" and fetched and at_earliest(e) > fetched]
        zone_fields = sorted({k for e in cal for k in e if "zone" in k.lower() or "utc" in k.lower()})
        check("F25 Fiscal Data calendar: Debt to the Penny at 21:15, future dates only in every candidate reading, no field naming a zone; the released flag is true on future entries (2.3, 4.5, 6.3)",
              ([] if sorted({e["time"] for e in dtp}) == ["21:15"] else ["times differ"]) + ([] if future else ["past entries present"]) + ([] if fut_true else ["no future entry flagged released"])
              + ([f"fields naming a zone: {zone_fields}"] if zone_fields else []),
              f"{len(dtp)} entries {min(e['date'] for e in dtp)} to {max(e['date'] for e in dtp)}; {len(fut_true)} future entries of other datasets flagged released")
    section_facts_v04(st)


def quote_in(text, quote):
    """A quotation with '...' elisions appears when its parts appear in order."""
    pos = 0
    for part in [norm_text(x).lower() for x in quote.split("...")]:
        if not part:
            continue
        i = text.find(part, pos)
        if i < 0:
            return False
        pos = i + len(part)
    return True


def section_facts_v04(st):
    name = "F26 the v0.4 VERIFIED quotations appear in the saved Board pages: H.6 'For release at 1:00 p.m. Eastern Time' (March 24, 2026); each route_notices text word for word, its route's date, and 'Last Update: November 12, 2026' on both DDP pages (2.4, 4.3, 4.5)"
    present = {k: p for k, p in RAW_PAGES_V04.items() if p.is_file()}
    if not present:
        skip(name, "local/research/p24/h6/raw/ absent")
    else:
        texts = {k: html_text(p.read_bytes()).lower() for k, p in present.items()}
        p = []
        checks = [("h6-20260324", "For release at 1:00 p.m. Eastern Time"), ("h6-20260324", "Release Date: March 24, 2026"),
                  ("ddp-retirement-faq", "Last Update: November 12, 2026"), ("ddp-fred-info", "Last Update: November 12, 2026"),
                  ("ddp-retirement-faq", "removed on March 31, 2027"), ("ddp-fred-info", "July 1, 2027")]
        for e in st.registry["sources"].get("frb-releases", {}).get("route_notices", []):
            hits = [k for k in ("ddp-retirement-faq", "ddp-fred-info") if k in texts and quote_in(texts[k], e.get("text", ""))]
            if not hits:
                p.append(f"route notice {e.get('date')}: its text is not found word for word in the saved DDP pages")
        for k, q in checks:
            if k not in texts:
                p.append(f"{RAW_PAGES_V04[k].name} absent")
            elif norm_text(q).lower() not in texts[k]:
                p.append(f"{q!r} not in {RAW_PAGES_V04[k].name}")
        check(name, p, f"{len(checks)} quotations and {len(st.registry['sources'].get('frb-releases', {}).get('route_notices', []))} route notice texts")
    name = "F27 Fiscal Data states no zone for 21:15: the saved dataset page data gives timeExpected 21:15 with no zone field, and the 2020 federal catalog entry says '3:00 PM EST' (4.5: neither is a statement of the calendar's zone)"
    if not (RAW_FD_CATALOG.is_file() and RAW_FD_DATASET_PAGEDATA.is_file()):
        skip(name, "local/research/p24/fiscaldata/raw/ absent")
    else:
        p = []
        cat = json.loads(RAW_FD_CATALOG.read_bytes().decode("utf-8-sig"))
        entries = [e for e in (cat.get("dataset") if isinstance(cat, dict) else cat) or [] if isinstance(e, dict) and e.get("identifier") == "015-BFS-2014Q3-065"]
        if len(entries) != 1 or entries[0].get("modified") != "2020-07-28" or "3:00 PM EST" not in str(entries[0].get("description")):
            p.append(f"catalog entry 015-BFS-2014Q3-065: {[(e.get('modified'), '3:00 PM EST' in str(e.get('description'))) for e in entries]}")
        raw = RAW_FD_DATASET_PAGEDATA.read_bytes().decode("utf-8", "replace")
        if '"timeExpected":"21:15"' not in raw.replace(" ", ""):
            p.append("the dataset page data has no timeExpected 21:15")
        zone_keys = sorted(set(re.findall(r'"([A-Za-z_]*[Zz]one[A-Za-z_]*)"\s*:', raw)))
        if zone_keys:
            p.append(f"the dataset page data has zone fields {zone_keys}")
        check(name, p, "catalog modified 2020-07-28; page data timeExpected 21:15, no zone field")
    section_facts_v05(st)


P25 = ROOT / "local" / "research" / "p25"
P25_FD = P25 / "fiscaldata" / "raw"
P25_ID = P25 / "identification"
DTP_ZERO_QUOTE = "Where this occurred, the dataset shows a value of $0.00 instead of a null value."  # 2.3, VERIFIED
DTP_DATASET_PAGES = [P25_ID / "raw" / "fiscaldata_datasets_debt-to-the-penny.html", P24_FD / "page_datasets_debt-to-the-penny.html",
                     RAW / "fiscaldata_dataset_debt-to-the-penny.htm"]
DTP_AMOUNTS = ("debt_held_public_amt", "intragov_hold_amt", "tot_pub_debt_out_amt")
ID_QUOTES = [  # 4.3: the provider texts behind contact null, as the saved identification evidence quotes them
    ("fiscaldata_api-documentation.html", "Our API is open, meaning that it does not require a user account or registration for a token."),
    ("nyfed_privacy_termsofuse.html", "Access the Content, manually or through an automated process or device, provided your access does not have the effect of disabling, damaging, or interfering with the function of the Website"),
]
ID_PAGE_PREFIX = {"nyfed-markets": ("nyfed_",), "fiscaldata": ("fiscaldata_", "fiscal_", "treasurydirect_"), "frb-releases": ("frb_",)}
ID_REPORT_ROWS = {"nyfed-markets": "markets.newyorkfed.org", "fiscaldata": "api.fiscaldata.treasury.gov", "frb-releases": "www.federalreserve.gov"}


def amount_problems(recs, label):
    """2.3 (v0.5): each amount is a decimal text or the string "null" (breakouts only), never zero."""
    out, nulls = [], 0
    for r in recs:
        for f in DTP_AMOUNTS:
            v = r.get(f, _ABSENT)
            if v == "null" and f != "tot_pub_debt_out_amt":
                nulls += 1
            elif not (isinstance(v, str) and not isinstance(v, Num) and _DECIMAL_TEXT.fullmatch(v)):
                out.append(f"{label} {r.get('record_date')}: {f} is {v!r}, neither a decimal text nor (for a breakout) the string \"null\"")
            elif D(v) == 0:
                out.append(f"{label} {r.get('record_date')}: {f} is {v!r}, an amount equal to zero")
    return out, nulls


def robots_disallows(text, path, agent_token):
    """A small robots.txt reading: the rules of the groups for '*' or for our agent token; the
    longest matching rule decides (Allow wins a tie); '*' and '$' in a rule are honored. A file
    without any User-agent line (empty, 'Not Found', an HTML error page) has no rules."""
    groups, cur, in_rules = [], None, False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if cur is None or in_rules:
                cur, in_rules = {"agents": [], "rules": []}, False
                groups.append(cur)
            cur["agents"].append(v.lower())
        elif k in ("allow", "disallow") and cur is not None:
            in_rules = True
            cur["rules"].append((k, v))
    if not groups:
        return None, "no rules (no User-agent line)"
    mine = [g for g in groups if any(a != "*" and a in agent_token.lower() for a in g["agents"])] or [g for g in groups if "*" in g["agents"]]
    best = None
    for g in mine:
        for k, v in g["rules"]:
            if v == "":
                continue
            rx = "".join(".*" if ch == "*" else "$" if ch == "$" and i == len(v) - 1 else re.escape(ch) for i, ch in enumerate(v))
            if re.match(rx, path):
                key = (len(v), k == "allow")
                if best is None or key > best[0]:
                    best = (key, k, v)
    if best is None:
        return False, f"{len(mine)} applicable group(s), no matching rule"
    return best[1] == "disallow", f"{best[1]}: {best[2]}"


def section_facts_v05(st):
    # F28: missing versus zero (2.3, v0.5)
    name = "F28 missing versus zero, VERIFIED in the saved evidence: the live JSON and CSV of 2026-11-18 give both breakouts of 1997-09-29 as the string \"null\" and 1997-09-30 as amounts; the saved full history (8,433 rows) and its fixture hold no amount equal to zero and no other missing marker; the dataset page says '$0.00 instead of a null value' (2.3)"
    files = {k: P25_FD / k for k in ("dtp_1997_json.json", "dtp_1997_csv.csv", "json.headers.txt", "csv.headers.txt")}
    if not all(x.is_file() for x in files.values()):
        skip(name, f"{', '.join(k for k, x in files.items() if not x.is_file())} absent under local/research/p25/fiscaldata/raw/")
    else:
        p, notes = [], []
        doc = load_numtext(files["dtp_1997_json.json"].read_bytes())
        rows = {r.get("record_date"): r for r in doc.get("data", []) if isinstance(r, dict)}
        crow = {r.get("record_date"): r for r in csv_lib.DictReader(io.StringIO(files["dtp_1997_csv.csv"].read_bytes().decode("utf-8-sig")))}
        for label, rs in (("JSON", rows), ("CSV", crow)):
            a, b = rs.get("1997-09-29") or {}, rs.get("1997-09-30") or {}
            if not (a.get("debt_held_public_amt") == "null" and a.get("intragov_hold_amt") == "null" and isinstance(a.get("debt_held_public_amt"), str)):
                p.append(f"{label}: 1997-09-29 breakouts {a.get('debt_held_public_amt')!r}, {a.get('intragov_hold_amt')!r}; 2.3 says the string \"null\" in both formats")
            for r in (a, b):
                if not (_DECIMAL_TEXT.fullmatch(str(r.get("tot_pub_debt_out_amt"))) and D(str(r.get("tot_pub_debt_out_amt"))) != 0):
                    p.append(f"{label}: total {r.get('tot_pub_debt_out_amt')!r} is not a non-zero amount")
            if not all(_DECIMAL_TEXT.fullmatch(str(b.get(f))) and D(str(b.get(f))) != 0 for f in ("debt_held_public_amt", "intragov_hold_amt")):
                p.append(f"{label}: 1997-09-30 breakouts are not amounts")
        if {k: {f: str(v) for f, v in r.items()} for k, r in rows.items()} != {k: dict(r) for k, r in crow.items()}:
            p.append("the JSON and CSV records differ")
        for h in ("json.headers.txt", "csv.headers.txt"):
            first = files[h].read_bytes().decode("utf-8", "replace").splitlines()[:1]
            when = http_date(files[h])
            if not first or " 200 " not in first[0] + " " or when is None or when.date().isoformat() != "2026-11-18":
                p.append(f"{h}: status {first[:1]}, Date {when}; 2.3 says live on 2026-11-18")
            else:
                notes.append(f"{h[:-12]} {fmt_utc(when)}")
        for label, path, gz in (("saved response", RAW_DTP, False), ("fixture", FX_DTP, True)):
            if not path.is_file():
                notes.append(f"{label} absent")
                continue
            data = gzip.decompress(path.read_bytes()) if gz else path.read_bytes()
            recs = load_numtext(data).get("data", [])
            probs, nulls = amount_problems(recs, label)
            if len(recs) != 8433:
                probs.append(f"{label}: {len(recs)} rows, 2.3 says 8,433")
            p += probs
            notes.append(f"{label}: {len(recs)} rows, {3 * len(recs) - nulls} amounts, none zero, {nulls} \"null\" breakouts")
        hits = [x.name for x in DTP_DATASET_PAGES if x.is_file() and norm_text(DTP_ZERO_QUOTE).lower() in html_text(x.read_bytes()).lower()]
        if not hits:
            p.append(f"the quotation {DTP_ZERO_QUOTE!r} is not in any saved dataset page ({', '.join(x.name for x in DTP_DATASET_PAGES if x.is_file()) or 'none saved'})")
        else:
            notes.append(f"quotation in {', '.join(hits)}")
        check(name, p, "; ".join(notes))

    # F29: client identification (4.3, 18)
    name = "F29 client identification agrees with the saved evidence: no saved page of a provider states a User-Agent, From header or contact requirement, so contact null stands for all three sources; the identification report gives no contact requirement for any provider; its quotations appear in the saved pages; the saved robots.txt of each registered host disallows none of the registered paths for our User-Agent (4.3, 18)"
    raw = P25_ID / "raw"
    if not raw.is_dir():
        skip(name, "local/research/p25/identification/raw/ absent")
        return
    p, notes = [], []
    sources = st.registry["sources"]
    texts = {}
    for f in sorted(raw.iterdir()):
        if f.suffix.lower() in (".html", ".htm", ".txt", ".yml") and not f.name.startswith("robots_"):
            texts[f.name] = html_text(f.read_bytes())
    req_rx = re.compile(r"[^.]{0,200}\b(user[- ]agent|from header|from: header|contact (address|e-?mail) in (the|each|your) request)\b[^.]{0,200}", re.I)
    for sid, src in sorted(sources.items()):
        pages = [k for k in texts if k.startswith(ID_PAGE_PREFIX.get(sid, ("?",)))]
        if not pages:
            p.append(f"{sid}: no saved page of this provider in the identification evidence (4.3: VERIFIED per source)")
            continue
        found = [(k, m.group(0).strip()[:160]) for k in pages for m in req_rx.finditer(texts[k])]
        contact = (src.get("request") or {}).get("contact")
        if found and contact is None:
            p.append(f"{sid}: contact is null but saved pages mention request identification, which a person must judge: {found[:2]}")
        if not found and contact is not None:
            p.append(f"{sid}: contact {contact!r} is sent although no saved page of the provider requires a contact (4.3: only when the documentation requires one)")
        notes.append(f"{sid}: {len(pages)} pages, {len(found)} identification statements, contact {contact}")
    for fname, quote in ID_QUOTES:
        if fname not in texts:
            p.append(f"{fname} absent")
        elif norm_text(quote).lower() not in texts[fname].lower():
            p.append(f"{quote[:60]!r}... not in {fname}")
    report = P25_ID / "REPORT.md"
    if not report.is_file():
        p.append("local/research/p25/identification/REPORT.md absent (4.3 names this evidence)")
    else:
        lines = report.read_bytes().decode("utf-8", "replace").splitlines()
        head = next((ln for ln in lines if ln.startswith("|") and "Contact requirement" in ln), None)
        if head is None:
            p.append("REPORT.md has no summary table with a Contact requirement column")
        else:
            cols = [c.strip() for c in head.strip("|").split("|")]
            ci = cols.index("Contact requirement")
            for sid, host in ID_REPORT_ROWS.items():
                row = next((ln for ln in lines if ln.startswith("|") and host in ln), None)
                cell = [c.strip() for c in row.strip("|").split("|")][ci] if row and len(row.strip("|").split("|")) > ci else None
                contact = (sources.get(sid, {}).get("request") or {}).get("contact")
                if cell is None:
                    p.append(f"REPORT.md has no row for {host}")
                elif cell.lower().startswith("none") != (contact is None):
                    p.append(f"{sid}: the report's contact requirement is {cell!r}, the registry's contact is {contact!r}")
    for sid, src in sorted(sources.items()):
        host = src.get("host")
        robots = raw / f"robots_{host}.txt"
        paths = sorted({urlsplit(s["fetch"]["endpoint"]).path for s in st.series.values() if s["source"] == sid}
                       | {urlsplit(c["url"]).path for c in st.registry["calendars"].values() if c.get("url") and urlsplit(c["url"]).hostname == host})
        if not robots.is_file():
            p.append(f"{sid}: robots_{host}.txt not saved")
            continue
        text = robots.read_bytes().decode("utf-8", "replace")
        for path in paths:
            dis, why = robots_disallows(text, path, (src.get("request") or {}).get("user_agent") or "")
            if dis:
                p.append(f"{sid}: robots.txt of {host} disallows {path} ({why})")
            notes.append(f"{host}{path}: {why}")
    check(name, p, "; ".join(notes))
# ---------------------------------------------------------------------------


def section_change_points(st):
    raw = load_raw(st, "effr", RAW_EFFR)
    if raw is None:
        skip("CP1 change-point object equals change points derived from the saved EFFR response", f"{RAW_EFFR.name} absent")
        return
    derived = derive_change_points(st, raw["refRates"])
    cal = st.registry["calendars"]["nyfed-business-days"]
    for relpath, obj in sorted((k, v) for k, v in st.tree_json.items() if k.startswith("objects/fomc-target/")):
        got = [{k: v for k, v in o.items() if k != "released"} for o in obj["observations"]]
        p = [f"{len(got)} change points, derived {len(derived)}"] if len(got) != len(derived) else []
        p += [f"{a} vs derived {b}" for a, b in zip(got, derived) if a != b]
        check(f"CP1 {relpath} equals the change points derived from the saved EFFR response (2.2, 6.1)", p, f"{len(derived)} change points")
        want = [{"basis": "not-recorded", "date": None} if i == 0 or c["effective"] < cal["rule_valid_from"] else
                {"basis": "rule", "date": next_business_day(parse_date(c["effective"])).isoformat()} for i, c in enumerate(derived)]
        diff = [f"{o['effective']} {o.get('released')} (6.3 gives {w})" for o, w in zip(obj["observations"], want) if o.get("released") != w]
        check(f"CP2 {relpath} released dates follow 6.3 (rule only from rule_valid_from {cal['rule_valid_from']}; all 73 predate it)", diff)
    by = {r["effectiveDate"]: r for r in raw["refRates"]}
    ser = st.series["effr"]
    for relpath, obj in sorted((k, v) for k, v in st.tree_json.items() if k.startswith("objects/effr/")):
        p = []
        for o in obj["observations"]:
            r = by.get(o["period"])
            if r is None:
                p.append(f"{o['period']} not in the saved response")
                continue
            era = era_for(ser, o["period"])
            if o["value"] != pad_decimal(str(r[era["value"]]), ser["decimals"]):
                p.append(f"{o['period']}: value {o['value']} vs {r[era['value']]}")
            want_extra = {dst: pad_decimal(str(r[src]), EXTRA_PLACES[dst]) for src, dst in era["extra"].items() if src in r}
            if o.get("extra", {}) != want_extra:
                p.append(f"{o['period']}: extra {o.get('extra')} vs {want_extra}")
            flags = (["r"] if r.get("revisionIndicator") == "r" else []) + ([f"footnote:{r['footnoteId']}"] if "footnoteId" in r else [])
            if o["flags"] != flags:
                p.append(f"{o['period']}: flags {o['flags']} vs {flags}")
        check(f"CP3 {relpath} observations equal the saved EFFR records (value and extras padded to their places, flags) (5, 6.1)", p)


# BEGIN ROOT MODE
# ---------------------------------------------------------------------------
# Pipeline root (section 17): checks T30 and up, run with --root <dir>
# ---------------------------------------------------------------------------
#
# Everything below is derived from the text of sections 7 to 17. Readings the text does
# not state outright are marked "reading:" in a comment next to the rule.

HOLIDAY_FIXTURE = ROOT / "pipeline" / "fixtures" / "calendar" / "holidays-fixture.json"

SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
RX_OBJECT_PATH = re.compile(r"objects/(%s)/(\d{4}|all)/([0-9a-f]{16})\.json" % SLUG, re.ASCII)
RX_CSV_PATH = re.compile(r"series/(%s)/(\d{4}|all)/([0-9a-f]{16})\.csv" % SLUG, re.ASCII)  # 9, 16 (v0.4): one per segment
RX_FULL_CSV_PATH = re.compile(r"series/(%s)/([0-9a-f]{16})\.csv" % SLUG, re.ASCII)  # v0.3 full-history CSV: none in v0.4
RX_LOG_PATH = re.compile(r"revisions/(%s)/(\d{4})/([0-9a-f]{16})\.json" % SLUG, re.ASCII)
RX_REVCSV_PATH = re.compile(r"revisions/(%s)/(\d{4})/([0-9a-f]{16})\.csv" % SLUG, re.ASCII)  # 10 (v0.8): a CSV per log version
RX_REGCOPY_PATH = re.compile(r"registry/econ-([0-9a-f]{16})\.json", re.ASCII)  # 22.9: a registry version
RX_HOLCOPY_PATH = re.compile(r"registry/holidays-([0-9a-f]{16})\.json", re.ASCII)  # 22.9: the holiday table in use
RX_NOTICE_PATH = re.compile(r"notices/([0-9a-f]{16})\.txt", re.ASCII)  # 22.9: the notice file
RX_SNAPSHOT_PATH = re.compile(r"snapshots/(\d{8}T\d{6}Z)\.json", re.ASCII)
RX_COPY_PATH = re.compile(r"series/(%s)\.csv" % SLUG, re.ASCII)
RX_HOLD_PATH = re.compile(r"(%s)/([0-9a-f]{16})\.json" % SLUG, re.ASCII)
RX_SNAPSHOT_ID = re.compile(r"\d{8}T\d{6}Z", re.ASCII)
RX_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", re.ASCII)
RX_DATE = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
RX_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
RX_RUN_ID = re.compile(r"[A-Za-z0-9._-]{1,80}", re.ASCII)

LIMIT_OBJECT, LIMIT_FILE, LIMIT_MANIFEST = 2_000_000, 5_000_000, 256_000
LIMIT_SITE, LIMIT_ARCHIVE_MONTH, LIMIT_PINS = 250_000_000, 50_000_000, 12
WINDOW_DAYS = 35
DECIMAL_FIELDS = ("value", "lower", "upper")
_ABSENT = object()


def is_str(x):
    return isinstance(x, str) and x != ""


def is_time(x):
    return isinstance(x, str) and RX_TIME.fullmatch(x) is not None


def is_snapshot_id(x):
    return isinstance(x, str) and RX_SNAPSHOT_ID.fullmatch(x) is not None


def is_sha256(x):
    return isinstance(x, str) and RX_SHA256.fullmatch(x) is not None


def is_count(x):
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def shape_problems(where, v, spec):
    """spec maps each field the text names to a predicate."""
    if not isinstance(v, dict):
        return [f"{where}: not an object"]
    out = [f"{where}: field {k!r} missing" for k in spec if k not in v]
    out += [f"{where}: {k} is {v[k]!r}" for k, ok in spec.items() if k in v and not ok(v[k])]
    return out


def canonical_problem(data, value):
    try:
        again = canon_bytes(value)
    except ValueError as exc:
        return str(exc)
    if again == data:
        return None
    n = min(len(again), len(data))
    i = next((k for k in range(n) if again[k] != data[k]), n)
    return f"bytes differ from the canonical form at offset {i} (file {len(data)} bytes, canonical {len(again)})"


class RootView:
    """Read-only view of a pipeline root (17.1). Files are data: parsed, never executed."""

    def __init__(self, root, state=None, state_exclude=()):
        """`state` and `state_exclude` (v0.7, 21.2): the state mode composes the working root of
        21.3 from the store's root/ and state/; the state files then live outside the root, and
        STATE.json and accepted.json, which are not root files, are left out of the listing."""
        self.root = Path(root).resolve()
        self.live = self.root / "live"
        self.arch = self.root / "archive" / "files"
        self.manifests = self.root / "archive" / "manifests"
        self.holds = self.root / "archive" / "holds"
        self.reviews = self.root / "archive" / "reviews"
        self.rollbacks = self.root / "archive" / "rollbacks"  # 17.5 (v0.6): the rollback records
        self.state = Path(state).resolve() if state is not None else self.root / "archive" / "state"
        self.state_exclude = set(state_exclude)
        self.staging = self.root / "staging"
        self._bytes, self._json, self._files, self._sets = {}, {}, {}, {}

    @staticmethod
    def safe(relpath):
        return (isinstance(relpath, str) and relpath != "" and not relpath.startswith("/") and _BS not in relpath
                and ":" not in relpath and all(part not in ("", ".", "..") for part in relpath.split("/")))

    def name(self, base):
        try:
            return base.relative_to(self.root).as_posix()
        except ValueError:  # the store's state/ beside root/ (21.2): named as the working root names it
            return "archive/state" if base == self.state else base.as_posix()

    def files(self, base):
        if base not in self._files:
            got = sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()) if base.is_dir() else []
            if base == self.state and self.state_exclude:
                got = [f for f in got if f not in self.state_exclude]
            self._files[base] = got
        return self._files[base]

    def has(self, base, relpath):
        if base not in self._sets:
            self._sets[base] = set(self.files(base))
        return self.safe(relpath) and relpath in self._sets[base]

    def read(self, base, relpath):
        key = (base, relpath)
        if key not in self._bytes:
            # Membership in the listing, not is_file(): the file system may ignore case.
            self._bytes[key] = (base / relpath).read_bytes() if self.has(base, relpath) else None
        return self._bytes[key]

    def load(self, base, relpath):
        key = (base, relpath)
        if key not in self._json:
            data = self.read(base, relpath)
            if data is None:
                self._json[key] = (None, "missing")
            else:
                try:
                    self._json[key] = (load_strict(data), None)
                except Exception as exc:
                    self._json[key] = (None, f"{type(exc).__name__}: {exc}")
        return self._json[key]


def rx_schema_by_id(st, schema_id):
    if not hasattr(st, "schemas_by_id"):
        st.schemas_by_id = {}
        for p in sorted(SCHEMA_DIR.glob("*.json")):
            try:
                doc = load_strict(p.read_bytes())
            except Exception:
                continue
            if isinstance(doc, dict) and isinstance(doc.get("$id"), str):
                st.schemas_by_id[doc["$id"]] = (p.name, doc)
    return st.schemas_by_id.get(schema_id)


def rx_kind(relpath):
    """Which schema covers a path of the namespace (17.1), or None."""
    if relpath == "manifest.json":
        return "manifest"
    if relpath == "status/runs.json":
        return "runs"
    if relpath == "status/publications.json":
        return "publications"
    if RX_SNAPSHOT_PATH.fullmatch(relpath):
        return "snapshot"
    if RX_OBJECT_PATH.fullmatch(relpath):
        return "object"
    if RX_LOG_PATH.fullmatch(relpath):
        return "revisions"
    if RX_REGCOPY_PATH.fullmatch(relpath):
        return "registry"  # 22.9 (v0.8): a registry version
    if RX_HOLCOPY_PATH.fullmatch(relpath):
        return "holidays"  # 22.9 (v0.8): the holiday table in use
    return None


def rx_hold_set(snapshot):
    return {(h.get("series"), (h.get("candidate") or {}).get("sha256")) for h in (snapshot or {}).get("holds", [])}


def rx_snapshot_files(snapshot):
    """Every file a snapshot names (8): path to (sha256, bytes). Hold candidates live in the archive."""
    out = {}
    for state in snapshot.get("series", {}).values():
        for r in state.get("objects", []):
            out[r.get("path")] = (r.get("sha256"), r.get("bytes"))
    for r in snapshot.get("revisions", []):
        out[r.get("path")] = (r.get("sha256"), r.get("bytes"))
    return out


def rx_named_files(ctx, snap_id):
    """17.6: the files a snapshot names are its own file, its objects and revision log versions,
    and the CSVs and revision log versions named by every archived manifest that names it."""
    if snap_id not in ctx.named_cache:
        out = {f"snapshots/{snap_id}.json": (None, None)}
        s = ctx.snaps.get(snap_id)
        if s is not None:
            out.update(rx_snapshot_files(s))
        for _, m, err in ctx.arch_manifests:
            if err or (m.get("snapshot") or {}).get("id") != snap_id:
                continue
            for summ in m.get("series", {}).values():
                for r in rx_csv_refs(summ) + list(summ.get("revisions", [])) + rx_list(summ.get("revision_csvs")):
                    out.setdefault(r.get("path"), (r.get("sha256"), None))
            for r in rx_rule_refs(m):  # reading (v0.8): the rule files of every archived manifest that names the snapshot, like its CSVs (9: a cached manifest never names a missing file)
                out.setdefault(r.get("path"), (r.get("sha256"), None))
        ctx.named_cache[snap_id] = out
    return ctx.named_cache[snap_id]


def rx_first_held(ctx, series_id, sha):
    """The first snapshot, in time, whose holds list this candidate of this series, or None."""
    for sid_ in ctx.order:
        if (series_id, sha) in rx_hold_set(ctx.snaps[sid_]):
            return sid_
    return None


def rx_csv_refs(summ):
    """The CSV references of a manifest series entry: v0.4 `csvs`; a v0.3 `csv` is read too so
    that T90 can report it."""
    refs = [r for r in (summ.get("csvs") or []) if isinstance(r, dict)] if isinstance(summ.get("csvs"), list) else []
    if isinstance(summ.get("csv"), dict):
        refs.append(summ["csv"])
    return refs


def rx_list(x):
    return [r for r in x if isinstance(r, dict)] if isinstance(x, list) else []


def rx_rule_refs(manifest):
    """9, 22.9 (v0.8): the rule files a manifest/4 names: rules.registry, holidays, notice and registry_versions."""
    rules = manifest.get("rules") if isinstance(manifest, dict) and isinstance(manifest.get("rules"), dict) else {}
    return [rules[k] for k in ("registry", "holidays", "notice") if isinstance(rules.get(k), dict)] + rx_list(rules.get("registry_versions"))


def rx_manifest_files(manifest):
    out = {}
    for summ in manifest.get("series", {}).values():
        for r in list(summ.get("objects", [])) + rx_csv_refs(summ) + list(summ.get("revisions", [])) + rx_list(summ.get("revision_csvs")):
            out[r.get("path")] = (r.get("sha256"), None)
    for r in rx_rule_refs(manifest):
        out[r.get("path")] = (r.get("sha256"), None)
    return out


def rx_manifest_at(ctx, t, inclusive=True):
    """The archived manifest in place at time t (the newest generated at or before t, or
    strictly before t), as (name, manifest), or (None, None) when nothing was published."""
    hit = (None, None)
    for name, m, err in ctx.arch_manifests:
        if err or not is_time(m.get("generated_at")):
            continue
        g = m["generated_at"]
        if g < t or (inclusive and g == t):
            hit = (name, m)
    return hit


def rx_state_at(ctx, t, inclusive=True):
    """The published snapshot at time t (17.2 step 1: the snapshot the live manifest names)."""
    _, m = rx_manifest_at(ctx, t, inclusive)
    return ctx.snaps.get((m.get("snapshot") or {}).get("id")) if m else None


def rx_obs(ctx, state):
    """All observations of a series state, in segment order, read from the archive."""
    refs = (state or {}).get("objects") or []
    key = tuple((r.get("path"), r.get("sha256")) for r in refs)
    if key not in ctx.obs_cache:
        out = []
        for r in refs:
            v, _ = ctx.rv.load(ctx.rv.arch, r.get("path"))
            if isinstance(v, dict) and isinstance(v.get("observations"), list):
                out.extend(v["observations"])
        ctx.obs_cache[key] = out
    return ctx.obs_cache[key]


def rx_base_id(ctx, snap_id):
    """The snapshot that was published when `snap_id` was written: the previous_snapshot of
    the first manifest that named it without a rollback (9, 17.2 step 1); it differs from
    `previous` only after a rollback (17.5). Falls back to `previous`."""
    for _, m, _ in ctx.arch_manifests:
        if isinstance(m, dict) and (m.get("snapshot") or {}).get("id") == snap_id and m.get("rollback") is None:
            return m.get("previous_snapshot")
    return ctx.snaps[snap_id].get("previous")


def rx_category(snapshot, sid):
    state = snapshot.get("series", {}).get(sid, {})
    if state.get("status") == "not-yet-published":
        return "not-yet-published"
    if state.get("status") == "held" or any(h.get("series") == sid for h in snapshot.get("holds", [])):
        return "held"
    return "published"


def rx_significant(ctx):
    """17.6: snapshot id to the reasons it is significant."""
    if ctx.significant is None:
        ctx.significant = {}
        for i, sid_ in enumerate(ctx.order):
            s, why = ctx.snaps[sid_], []
            if i == 0:
                why.append("first snapshot of the archive")
            if s.get("revisions"):
                why.append("revisions not empty")
            base = ctx.snaps.get(rx_base_id(ctx, sid_))
            if rx_hold_set(base) != rx_hold_set(s):
                why.append("opened, changed or closed a hold")
            # 17.6: its list of locked series differs from the previous snapshot's. reading (v0.6):
            # the previous snapshot is `previous` (8), and the list is the set of locks (series,
            # origin, hash), as 17.3 glosses "the list of locked series changes (a lock added or lifted)".
            if set(rx_frozen(s)) != set(rx_frozen(ctx.snaps.get(s.get("previous")))):
                why.append("its list of locked series differs from the previous snapshot's")
            if (s.get("run") or {}).get("trigger") == "review":
                why.append("trigger review")
            if why:
                ctx.significant[sid_] = why
    return ctx.significant


def rx_pins(ctx):
    over = getattr(ctx, "pins_override", None)
    if over is not None:  # 22.3 (v0.8): a release's window uses its manifest's own pages_window
        return [{"snapshot": x} for x in over]
    doc, _ = ctx.rv.load(ctx.rv.state, "pins.json")
    pins = doc.get("pins") if isinstance(doc, dict) else None
    return [p for p in pins if isinstance(p, dict)] if isinstance(pins, list) else []


def rx_window(ctx):
    """13, 17.6: (snapshot id to reasons, file path to (sha256, bytes, reasons))."""
    if ctx.window is not None:
        return ctx.window
    m, cur = ctx.manifest, ctx.cur
    gen = parse_utc(m["generated_at"])
    snaps = {}

    def add(sid_, why):
        if sid_ is not None:
            snaps.setdefault(sid_, []).append(why)

    add(ctx.cur_id, "current")
    if cur is not None:
        add(cur.get("previous"), "previous of the current snapshot")
    add(m.get("previous_snapshot"), "previous_snapshot of the manifest")
    for sid_ in ctx.order:
        s = ctx.snaps[sid_]
        if is_time(s.get("created_at")) and parse_utc(s["created_at"]) > gen - dt.timedelta(days=WINDOW_DAYS):
            add(sid_, f"created in the {WINDOW_DAYS} days before generated_at")
    for p in rx_pins(ctx):
        add(p.get("snapshot"), "pinned")
    for sid_, why in rx_significant(ctx).items():
        add(sid_, "significant: " + ", ".join(why))
    files = {}
    for path, (sha, _) in rx_manifest_files(m).items():
        files[path] = [sha, None, ["named by the manifest"]]
    if m.get("schema") == MANIFEST_V4:
        nref = (m.get("rules") or {}).get("notice") or {}
        files["NOTICE.txt"] = [nref.get("sha256"), None, ["the live copy of the notice file (22.9)"]]
    for sid_, why in sorted(snaps.items()):
        label = f"snapshot {sid_} ({'; '.join(why)})"
        for path, (sha, nbytes) in rx_named_files(ctx, sid_).items():
            entry = files.setdefault(path, [sha, nbytes, []])
            entry[0], entry[1] = entry[0] or sha, entry[1] if entry[1] is not None else nbytes
            entry[2].append(label if path == f"snapshots/{sid_}.json" else "named by " + label)
    ctx.window = (snaps, files)
    return ctx.window


# ---------------------------------------------------------------------------
# The holiday table (section 3) and the documented gaps (2.3, 4.4): R11, R26, H1 to H5
# ---------------------------------------------------------------------------

K8_PAGE = ROOT / "local" / "research" / "p23" / "raw" / "k8.htm"
RAW_FIXTURES = ROOT / "pipeline" / "fixtures" / "raw"
FX_EFFR = RAW_FIXTURES / "nyfed-effr-full.json.gz"
FX_DTP = RAW_FIXTURES / "fiscaldata-dtp-full.json.gz"
FX_H6_ZIP = RAW_FIXTURES / "frb-h6-reduced.zip"
FX_H6_DATES = RAW_FIXTURES / "frb-h6-releaseDates.json"
FX_FD_CAL = RAW_FIXTURES / "fiscaldata-calendar-excerpt.json"
K8_RULE = ("For holidays falling on Saturday, Federal Reserve Banks and Branches will be open the preceding Friday; however, the Board of Governors "
           "will be closed. For holidays falling on Sunday, all Federal Reserve offices will be closed the following Monday.")
MONTHS = {m: i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                                       "November", "December"), start=1)}


def load_holiday_table(st):
    """Read the table the registry names (3, 4.1) and make it the calendar of every business
    day computation. Problems are kept for R11; with no usable table my own rules stay in force."""
    global _HOLIDAY_TABLE
    st.holiday_doc, st.holiday_problems = None, []
    name = st.registry.get("holiday_table")
    if name != "fed-holidays.json":
        st.holiday_problems.append(f"registry holiday_table is {name!r}, expected 'fed-holidays.json' (4.1)")
        return
    path = REGISTRY.parent / name
    if not path.is_file():
        st.holiday_problems.append(f"pipeline/registry/{name} is missing (3)")
        return
    try:
        doc = load_strict(path.read_bytes())
    except Exception as exc:
        st.holiday_problems.append(f"pipeline/registry/{name}: {type(exc).__name__}: {exc}")
        return
    p = shape_problems("holiday table", doc, {
        "schema": lambda x: x == "rmf.econ.holidays/1", "status": lambda x: x == "verified", "source": is_str,
        "checked": lambda x: isinstance(x, str) and RX_DATE.fullmatch(x) is not None,
        "years": lambda x: isinstance(x, list) and len(x) == 2 and all(isinstance(y, int) and not isinstance(y, bool) for y in x) and x[0] <= x[1],
        "holidays": lambda x: isinstance(x, list) and all(isinstance(d, str) and RX_DATE.fullmatch(d) for d in x)})
    st.holiday_problems += p
    if p:
        return
    st.holiday_doc = doc
    extra = sorted(set(doc) - {"schema", "status", "source", "checked", "years", "holidays", "note"})
    if extra:
        st.holiday_problems.append(f"fields {extra} are not named by section 3")
    if "note" in doc and not isinstance(doc["note"], str):
        st.holiday_problems.append("note is not a string")
    if doc["years"] != [1993, 2030]:
        st.holiday_problems.append(f"years {doc['years']}, section 3 says 1993 to 2030")
    days = set()
    for d in doc["holidays"]:
        try:
            day = parse_date(d)
        except ValueError:
            st.holiday_problems.append(f"{d} is not a date")
            continue
        if not doc["years"][0] <= day.year <= doc["years"][1]:
            st.holiday_problems.append(f"{d} is outside years {doc['years']}")
        if day.weekday() >= 5:
            st.holiday_problems.append(f"{d} is a {day.strftime('%A')}: a weekend day is never a business day, and a Saturday holiday closes nothing (3)")
        days.add(day)
    if doc["holidays"] != sorted(set(doc["holidays"])):
        st.holiday_problems.append("holidays are not ascending and unique")
    hit = rx_schema_by_id(st, "rmf.econ.holidays/1")
    if hit:
        st.holiday_problems += [f"{hit[0]}: {e}" for e in schema_errors(doc, hit[1])[:3]]
    _HOLIDAY_TABLE = {"first": doc["years"][0], "last": doc["years"][1], "days": days}


def k8_closures():
    """The Reserve Bank closures the saved K.8 page gives under the rule it states.
    Returns (closures, holidays listed, problems, facts)."""
    text = K8_PAGE.read_bytes().decode("utf-8", "replace")
    problems = []
    plain = html_text(K8_PAGE.read_bytes())
    if norm_text(K8_RULE) not in plain:
        problems.append("the Saturday and Sunday rule quoted in section 3 is not on the saved page")
    if "Last Update: July 8, 2026" not in plain:
        problems.append("the page does not say 'Last Update: July 8, 2026'")
    tables = [t for t in re.findall(r"(?is)<table.*?</table>", text) if "New Year" in t]
    if len(tables) != 1:
        return set(), 0, problems + [f"{len(tables)} holiday tables found on the page"], ""
    years = [int(y) for y in re.findall(r"(?is)<th[^>]*>\s*(?:<h6>)?\s*(\d{4})\s*(?:</h6>)?\s*</th>", tables[0])]
    closures, listed, sat, sun = set(), 0, 0, 0
    rows = re.findall(r"(?is)<tr>\s*<th[^>]*>(.*?)</th>(.*?)</tr>", tables[0].split("<tbody>", 1)[-1])
    for name, cells_html in rows:
        cells = [html_lib.unescape(re.sub(r"(?s)<[^>]+>", "", c)).strip() for c in re.findall(r"(?is)<td[^>]*>(.*?)</td>", cells_html)]
        if len(cells) != len(years):
            problems.append(f"{name}: {len(cells)} cells for {len(years)} years")
            continue
        for year, cell in zip(years, cells):
            mt = re.fullmatch(r"([A-Z][a-z]+) (\d{1,2})(\**)", cell)
            if not mt or mt.group(1) not in MONTHS:
                problems.append(f"{name} {year}: cell {cell!r} not understood")
                continue
            day = dt.date(year, MONTHS[mt.group(1)], int(mt.group(2)))
            listed += 1
            stars = {5: "*", 6: "**"}.get(day.weekday(), "")
            if mt.group(3) != stars:
                problems.append(f"{name} {year}: {cell!r} is a {day.strftime('%A')}, the page's marks say otherwise")
            if day.weekday() == 5:
                sat += 1          # the Reserve Banks are open the preceding Friday: no closure
            elif day.weekday() == 6:
                sun += 1
                closures.add(day + dt.timedelta(days=1))
            else:
                closures.add(day)
    return closures, listed, problems, f"{len(rows)} holidays, years {years[0] if years else '?'} to {years[-1] if years else '?'}, {listed} dates, {sat} on a Saturday, {sun} on a Sunday"


def fixture_json_gz(path):
    return load_numtext(gzip.decompress(path.read_bytes()))


def weekdays_between(first, last):
    d = first
    while d <= last:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def section_holidays(st):
    doc = st.holiday_doc
    check("R11 the registry names the Federal Reserve holiday table fed-holidays.json, which has the section 3 shape: schema rmf.econ.holidays/1, status verified, source, checked, years 1993 to 2030, ascending weekday holidays (3, 4.1)",
          st.holiday_problems, f"{len(doc['holidays'])} holidays, source {doc['source']}, checked {doc['checked']}" if doc else "")
    if doc is None or _HOLIDAY_TABLE is None:
        for name in ("H1", "H2", "H3", "H4", "H5"):
            skip(f"{name} holiday table verification", "no usable holiday table (see R11)")
        return
    table = _HOLIDAY_TABLE["days"]

    # H1: the K.8 page, 2026 to 2030
    name = "H1 the holiday table equals the saved K.8 page for 2026 to 2030 under the page's Saturday and Sunday rule: 50 closures (3)"
    if not K8_PAGE.is_file():
        skip(name, "local/research/p23/raw/k8.htm absent")
    else:
        closures, listed, p, facts = k8_closures()
        mine = {d for d in table if 2026 <= d.year <= 2030}
        if closures != mine:
            p.append(f"only in the table {sorted(x.isoformat() for x in mine - closures)}, only on the page {sorted(x.isoformat() for x in closures - mine)}")
        if len(closures) != 50:
            p.append(f"the page gives {len(closures)} closures, section 3 says 50")
        if listed != 55:
            p.append(f"the page lists {listed} holiday dates, eleven holidays in five years are 55")
        check(name, p, f"{facts}; {len(closures)} closures, {len(mine)} table dates in those years")

    # H2: my own rules, every year of the table
    p = []
    for y in range(_HOLIDAY_TABLE["first"], _HOLIDAY_TABLE["last"] + 1):
        own, theirs = _own_fed_holidays(y), {d for d in table if d.year == y}
        if own != theirs:
            p.append(f"{y}: only in the table {sorted(x.isoformat() for x in theirs - own)}, only in my rules {sorted(x.isoformat() for x in own - theirs)}")
    check("H2 the holiday table equals this checker's own rules for every year, 1993 to 2030: the eleven holidays (Juneteenth from 2022), Sunday moved to Monday, Saturday dropped (3; independent cross-check)", p,
          f"{len(table)} table dates, {sum(len(_own_fed_holidays(y)) for y in range(_HOLIDAY_TABLE['first'], _HOLIDAY_TABLE['last'] + 1))} by my rules")

    effr_dates = dtp_dates = None
    if FX_EFFR.is_file():
        effr_dates = {r.get("effectiveDate") for r in fixture_json_gz(FX_EFFR).get("refRates", [])}
    if FX_DTP.is_file():
        dtp_dates = {r.get("record_date") for r in fixture_json_gz(FX_DTP).get("data", [])}

    # H3: the saved EFFR response
    name = "H3 from 2000-07-03 to 2026-11-12 the weekdays without a record in the saved EFFR response are exactly the table's dates, 255 of 255, and 2021-06-18 has a record (3)"
    if effr_dates is None:
        skip(name, f"{FX_EFFR.name} absent")
    else:
        first, last = dt.date(2000, 7, 3), dt.date(2026, 11, 12)
        p = []
        if (min(effr_dates), max(effr_dates)) != (first.isoformat(), last.isoformat()):
            p.append(f"the response runs from {min(effr_dates)} to {max(effr_dates)}")
        without = {d for d in weekdays_between(first, last) if d.isoformat() not in effr_dates}
        in_range = {d for d in table if first <= d <= last}
        if without != in_range:
            p.append(f"weekdays without a record that are not in the table {sorted(x.isoformat() for x in without - in_range)}; table dates with a record {sorted(x.isoformat() for x in in_range - without)}")
        if len(in_range) != 255:
            p.append(f"{len(in_range)} table dates in the range, section 3 says 255")
        if "2021-06-18" not in effr_dates:
            p.append("2021-06-18 has no record")
        check(name, p, f"{len(without)} weekdays without a record, {len(in_range)} table dates, {len(effr_dates)} records")

    # H4: Debt to the Penny on the table's dates; Saturday holidays close nothing
    name = "H4 Debt to the Penny has no record on any date of the table, and both saved responses have records on 2021-12-24, 2021-12-31 and 2026-07-03, the Fridays before a Saturday holiday (3)"
    if dtp_dates is None or effr_dates is None:
        skip(name, "saved response fixtures absent")
    else:
        p = [f"Debt to the Penny has a record on the holiday {d.isoformat()}" for d in sorted(table) if d.isoformat() in dtp_dates]
        for d in ("2021-12-24", "2021-12-31", "2026-07-03"):
            if d not in effr_dates or d not in dtp_dates:
                p.append(f"{d}: EFFR record {d in effr_dates}, Debt to the Penny record {d in dtp_dates}")
        n = sum(1 for d in table if min(dtp_dates) <= d.isoformat() <= max(dtp_dates))
        check(name, p, f"{n} table dates between {min(dtp_dates)} and {max(dtp_dates)}, none with a record")

    # H5: the 18 documented gaps
    name = "H5 the Federal Reserve business days without a Debt to the Penny record are exactly the 18 known_gaps of each debt series, 1995-11-20 to 2019-04-03; the longest gap stays 5 days; the EFFR has none (2.3, 4.4)"
    if dtp_dates is None or effr_dates is None:
        skip(name, "saved response fixtures absent")
    else:
        p = []
        missing = [d.isoformat() for d in weekdays_between(parse_date(min(dtp_dates)), parse_date(max(dtp_dates)))
                   if d not in table and d.isoformat() not in dtp_dates]
        if len(missing) != 18 or (missing[:1], missing[-1:]) != (["1995-11-20"], ["2019-04-03"]):
            p.append(f"{len(missing)} business days without a record, {missing[:1]} to {missing[-1:]}; 2.3 says 18, 1995-11-20 to 2019-04-03")
        for sid, ser in st.series.items():
            gaps = [g.get("period") for g in ser.get("known_gaps", [])]
            if ser["source"] == "fiscaldata" and gaps != missing:
                p.append(f"{sid}: known_gaps differ from the data: only listed {sorted(set(gaps) - set(missing))}, only in the data {sorted(set(missing) - set(gaps))}")
        g = max_gap(sorted(dtp_dates))
        if g[0] != 5:
            p.append(f"longest gap {g[0]} days ({g[1]} to {g[2]}), 2.3 says 5")
        effr_missing = [d.isoformat() for d in weekdays_between(parse_date(min(effr_dates)), parse_date(max(effr_dates)))
                        if d not in table and d.isoformat() not in effr_dates]
        if effr_missing or st.series["effr"].get("known_gaps"):
            p.append(f"EFFR: business days without a record {effr_missing}, known_gaps {st.series['effr'].get('known_gaps')}")
        check(name, p, f"{len(missing)} gaps: {', '.join(missing)}; longest gap {g[0]} days ({g[1]} to {g[2]})")

    # R26: known_gaps in the registry (4.4)
    p = []
    for sid, ser in st.series.items():
        if "known_gaps" not in ser:
            continue
        if ser["frequency"] != "business-day":
            p.append(f"{sid}: known_gaps on a {ser['frequency']} series (4.4: business-day series only)")
            continue
        periods = [g.get("period") for g in ser["known_gaps"]]
        if periods != sorted(set(map(str, periods))):
            p.append(f"{sid}: known_gaps are not ascending and unique")
        for g in ser["known_gaps"]:
            if set(g) != {"period", "text"} or not is_str(g.get("text")):
                p.append(f"{sid}: a known gap needs exactly period and text: {sorted(g)}")
                continue
            try:
                if not is_business_day(parse_date(g["period"])):
                    p.append(f"{sid}: known gap {g['period']} is not a New York Fed business day (4.4)")
            except ValueError as exc:
                p.append(f"{sid}: known gap {g.get('period')!r}: {exc}")
            if g["period"] in ki_periods(ser):
                p.append(f"{sid}: {g['period']} is both a known gap and a known inconsistency")
    check("R26 known_gaps: on business-day series only, each a New York Fed business day with a text, ascending (4.4)", p,
          ", ".join(f"{sid} {len(ser['known_gaps'])}" for sid, ser in st.series.items() if "known_gaps" in ser))


# ---------------------------------------------------------------------------
# The collector fixtures of section 18 (pipeline/fixtures/raw/): SR10 to SR14
# ---------------------------------------------------------------------------


def parse_h6_document(data):
    """Series of an H6_data.xml document: name to copies (attributes, observations), plus the
    local names of every element seen. A document type or entity declaration is refused."""
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ValueError("the document declares a DTD or an entity: refused")
    series, names, prepared = {}, set(), None
    for event, el in ET.iterparse(io.BytesIO(data), events=("end",)):
        name = _local(el.tag)
        names.add(name)
        if name == "Prepared" and prepared is None:
            prepared = (el.text or "").strip()
        elif name == "Series":
            obs = [dict(o.attrib) for o in el if _local(o.tag) == "Obs"]
            series.setdefault(el.attrib.get("SERIES_NAME"), []).append((dict(el.attrib), obs))
            el.clear()
    return series, names, prepared


def section_raw_fixtures(st):
    if not RAW_FIXTURES.is_dir():
        skip("SR10 collector fixtures of section 18", "pipeline/fixtures/raw/ absent")
        return
    for sr, path, raw_path, container, count, first, date_field in (
            ("SR10", FX_EFFR, RAW_EFFR, "refRates", 6625, "2000-07-03", "effectiveDate"),
            ("SR11", FX_DTP, RAW_DTP, "data", 8433, "1993-04-01", "record_date")):
        name = f"{sr} {path.name} is the saved response of 2026-11-16 byte for byte, gzipped: {count:,} records from {first}, each matching the schema in force (18, 5)"
        if not path.is_file():
            check(name, [f"{path.name} missing"])
            continue
        data = gzip.decompress(path.read_bytes())
        doc = load_numtext(data)
        recs = doc.get(container, [])
        p, counts = validate_records(st, recs, container)
        dates = [r.get(date_field) for r in recs]
        if len(recs) != count or min(dates) != first:
            p.append(f"{len(recs)} records from {min(dates)}")
        if container == "data" and str(doc.get("meta", {}).get("total-count")) != str(len(recs)):
            p.append(f"meta.total-count {doc.get('meta', {}).get('total-count')} for {len(recs)} rows")
        note = "saved response absent, bytes not compared"
        if raw_path.is_file():
            note = "bytes equal the saved response"
            if raw_path.read_bytes() != data:
                p.append(f"the gunzipped bytes ({len(data)}, sha256 {sha256_hex(data)[:16]}) differ from {raw_path.name} ({raw_path.stat().st_size} bytes)")
        check(name, p, f"{len(data)} bytes, {len(recs)} records {min(dates)} to {max(dates)}; {note}")

    name = "SR12 frb-h6-reduced.zip holds H6_data.xml alone: the four registered series in every copy, 813 months from 1959-01, equal to the saved release file, two unregistered series of eight observations (one weekly, one in millions), no contact element (18, 5)"
    if not FX_H6_ZIP.is_file():
        check(name, ["frb-h6-reduced.zip missing"])
    else:
        p = []
        with zipfile.ZipFile(FX_H6_ZIP) as z:
            infos = z.infolist()
            if [i.filename for i in infos] != ["H6_data.xml"]:
                p.append(f"entries {[i.filename for i in infos]}")
            if any(i.flag_bits & 0x1 or i.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) or i.file_size > 64_000_000 for i in infos):
                p.append("an entry is encrypted, uses another method or states more than 64 MB")
            data = z.read("H6_data.xml") if "H6_data.xml" in z.namelist() else b""
        series, names, prepared = parse_h6_document(data)
        sd = st.source_records["sdmx"]["h6-sdmx-2021"]
        registered = {s["extract"][0]["series_name"]: s for s in st.series.values() if s["source"] == "frb-releases"}
        if any("contact" in n.lower() for n in names):
            p.append(f"contact elements present: {sorted(n for n in names if 'contact' in n.lower())}")
        for rn, ser in sorted(registered.items()):
            copies = series.get(rn, [])
            if not copies:
                p.append(f"{rn} missing")
                continue
            if any(c != copies[0] for c in copies):
                p.append(f"{rn}: copies differ")
            attrs, obs = copies[0]
            months = [o.get("TIME_PERIOD", "")[:7] for o in obs]
            if len(obs) != 813 or months[:1] != ["1959-01"] or any(month_add(a, 1) != b for a, b in zip(months, months[1:])):
                p.append(f"{rn}: {len(obs)} observations from {months[:1]}, not 813 contiguous months from 1959-01")
            if set(attrs) != set(sd["series_attributes"]) or attrs.get("ADJUSTED") != ser["extract"][0]["adjusted"]:
                p.append(f"{rn}: series attributes {attrs}")
            if any(set(o) != set(sd["observation_attributes"]) for o in obs):
                p.append(f"{rn}: observation attributes differ from the schema")
        others = sorted(set(series) - set(registered), key=str)
        if len(others) != 2 or any(len(c) != 1 or len(c[0][1]) != 8 for c in (series[o] for o in others)):
            p.append(f"unregistered series {others} with {[len(series[o][0][1]) for o in others]} observations; 18 says two, eight observations each")
        else:
            other_attrs = [series[o][0][0] for o in others]
            if sum(1 for a in other_attrs if a.get("UNIT_MULT") != "1e+09") != 1 or sum(1 for a in other_attrs if a.get("FREQ") != "129") != 1:
                p.append(f"the unregistered series are not one weekly and one in millions: {[(a.get('FREQ'), a.get('UNIT_MULT')) for a in other_attrs]}")
        note = "saved release file absent, not compared"
        if RAW_H6_ZIP.is_file():
            note = "registered series equal the saved release file"
            saved = load_h6(st)
            if prepared != saved["prepared"]:
                p.append(f"Prepared {prepared} vs saved {saved['prepared']}")
            for rn in sorted(registered):
                want = [(c["attrs"], c["obs"]) for c in saved["series"].get(rn, [])]
                if series.get(rn, []) != want:
                    p.append(f"{rn}: {len(series.get(rn, []))} copies differ from the saved file's {len(want)} (attributes or observations)")
        check(name, p, f"{len(data)} bytes, {sum(len(v) for v in series.values())} Series elements, unregistered {others}; {note}")

    name = "SR13 frb-h6-releaseDates.json is the saved file (18; the text claims byte identity only for the two gzipped responses, so equal content is accepted here)"
    if not FX_H6_DATES.is_file():
        check(name, ["frb-h6-releaseDates.json missing"])
    elif not RAW_H6_DATES.is_file():
        skip(name, "saved releaseDates.json absent")
    else:
        a, b = FX_H6_DATES.read_bytes(), RAW_H6_DATES.read_bytes()
        if a == b:
            check(name, [], f"{len(a)} bytes, byte for byte")
        elif load_strict(a) == load_strict(b):
            how = "line endings only (CRLF in the saved file, LF in the fixture)" if b.replace(bytes([13, 10]), bytes([10])) == a else "whitespace"
            check(name, [], f"same JSON content; the bytes differ in {how}: fixture {len(a)} bytes, saved {len(b)} bytes")
        else:
            check(name, [f"content differs from the saved file ({len(a)} bytes against {len(b)})"])

    name = "SR14 fiscaldata-calendar-excerpt.json holds the Debt to the Penny entries of the saved release calendar, every one at 21:15 (18, 17.3)"
    if not FX_FD_CAL.is_file():
        check(name, ["fiscaldata-calendar-excerpt.json missing"])
    else:
        entries = load_strict(FX_FD_CAL.read_bytes())
        ds = st.registry["calendars"]["fiscaldata-release"].get("dataset_id")
        p = [f"entry {e} is not a Debt to the Penny entry at 21:15" for e in entries if e.get("datasetId") != ds or e.get("time") != "21:15"][:5]
        note = "saved calendar absent, not compared"
        if RAW_FD_CAL.is_file():
            note = "equal to the saved calendar's entries"
            saved = [e for e in json.loads(RAW_FD_CAL.read_bytes().decode("utf-8")) if e.get("datasetId") == ds]
            if saved != entries:
                p.append(f"{len(entries)} entries differ from the saved calendar's {len(saved)} Debt to the Penny entries")
        check(name, p, f"{len(entries)} entries; {note}")


# --- T31 to T35: layout, canonical form, schemas ---


def rc_layout(ctx):
    rv = ctx.rv
    p = [f"{rv.name(d)}/ is not a folder" for d in (rv.live, rv.arch, rv.manifests, rv.state) if not d.is_dir()]
    held_ever = any(s.get("holds") for s in ctx.snaps.values())
    if not rv.holds.is_dir() and held_ever:
        p.append("archive/holds/ is not a folder although a snapshot lists a hold")
    if not rv.reviews.is_dir() and rx_decisions(ctx):
        p.append("archive/reviews/ is not a folder although review-queue.json has decisions")
    if not rv.rollbacks.is_dir() and any(not e and isinstance(m, dict) and m.get("rollback") is not None for _, m, e in ctx.arch_manifests):
        p.append("archive/rollbacks/ is not a folder although an archived manifest is a rollback (17.5 v0.6: every rollback leaves a rollback record)")
    for f in ("review-queue.json", "publications.json", "pins.json", "alerts.json", "collector.json"):
        if rv.read(rv.state, f) is None:
            p.append(f"archive/state/{f} missing")
    if not (rv.state / "run-records").is_dir():
        p.append("archive/state/run-records/ is not a folder")
    check("T31 the root has live/, archive/files/, archive/manifests/, archive/holds/, archive/reviews/, archive/rollbacks/ (after a rollback, v0.6) and archive/state/ with its state files (17.1, 17.5)", p,
          "" if rv.holds.is_dir() and rv.reviews.is_dir() else "archive/holds/ or archive/reviews/ absent, accepted because no snapshot lists a hold and no decision was taken")
    left = sorted(x.name for x in rv.staging.iterdir()) if rv.staging.is_dir() else []
    check("T32 no leftover staging content (17.1: removed when the run ends)", [f"staging/{x}" for x in left])
    top = {x.split("/", 1)[0] for x in rv.files(rv.live)} | {x.name for x in rv.live.iterdir()} if rv.live.is_dir() else set()
    allowed = {"manifest.json", "objects", "snapshots", "series", "revisions", "status"}
    if isinstance(ctx.manifest, dict) and ctx.manifest.get("schema") == MANIFEST_V4:
        allowed |= {"registry", "notices", "NOTICE.txt"}  # 22.3, 22.9 (v0.8): the rule files, live with every manifest/4
    p = [f"live/{x} is not part of the namespace" + (" (the rule files of 22.9 come with a manifest/4)" if x in ("registry", "notices", "NOTICE.txt") else "") for x in sorted(top - allowed)]
    for must in ("manifest.json", "status/runs.json", "status/publications.json"):
        if rv.read(rv.live, must) is None:
            p.append(f"live/{must} missing")
    check("T33 live/ is laid out as the namespace: manifest.json, objects/, snapshots/, series/, revisions/, status/runs.json, status/publications.json (17.1)", p)


def rx_json_files(ctx):
    """(base, relpath, schema kind or None) for every JSON file a rule of 7 or 17.1 covers."""
    rv, out = ctx.rv, []
    for base in (rv.live, rv.arch):
        for f in rv.files(base):
            if f.endswith(".json"):
                out.append((base, f, rx_kind(f)))
    out += [(rv.manifests, f, "manifest") for f in rv.files(rv.manifests) if f.endswith(".json")]
    out += [(rv.holds, f, None) for f in rv.files(rv.holds)]
    out += [(rv.reviews, f, "review") for f in rv.files(rv.reviews)]
    out += [(rv.rollbacks, f, "rollback") for f in rv.files(rv.rollbacks)]  # 17.5 (v0.6)
    out += [(rv.state, f, None) for f in rv.files(rv.state) if f.endswith(".json")]
    return out


def rc_canonical(ctx):
    rv, p, n = ctx.rv, [], 0
    for base, f, _ in rx_json_files(ctx):
        n += 1
        v, err = rv.load(base, f)
        if err:
            p.append(f"{rv.name(base)}/{f}: {err}")
            continue
        why = canonical_problem(rv.read(base, f), v)
        if why:
            p.append(f"{rv.name(base)}/{f}: {why}")
    check("T34 every JSON file in live/ and archive/ (files, manifests, holds, reviews, rollbacks, state) is canonical JSON (7, 12.8, 17.1; reading: the rollback records of 17.5 like the review records)", p, f"{n} files")


def rc_schemas(ctx):
    rv, st, p, n = ctx.rv, ctx.st, [], 0
    for base, f, kind in rx_json_files(ctx):
        v, err = rv.load(base, f)
        if err:
            continue  # reported by T34
        where = f"{rv.name(base)}/{f}"
        if base in (rv.live, rv.arch) and kind is None:
            p.append(f"{where}: no schema covers this path (12.8)")
            continue
        schema = st.schemas.get(kind) if kind else None
        if kind in ("publications", "review"):
            want_id = {"publications": "rmf.econ.publications/1", "review": SCHEMA_IDS["review"]}[kind]  # 17.5
            hit = rx_schema_by_id(st, want_id)
            if hit is None:
                p.append(f"{where}: no schema file with $id {want_id}")
                continue
            schema = hit[1]
        if base == rv.state and f == "review-queue.json" and isinstance(v, dict) and v.get("schema") != SCHEMA_IDS["review-queue"]:
            p.append(f"{where}: schema {v.get('schema')!r}, 17.5 gives {SCHEMA_IDS['review-queue']}")
        if kind == "manifest" and isinstance(v, dict) and v.get("schema") in (SCHEMA_IDS["manifest"], MANIFEST_V4):
            schema = manifest_schema_for(st, v)  # 9, 22.9 (v0.8): manifest/3 before the first v0.8 run, manifest/4 from it (T119)
        elif kind in SCHEMA_IDS and isinstance(v, dict) and v.get("schema") != SCHEMA_IDS[kind]:
            p.append(f"{where}: schema {v.get('schema')!r}, the text gives {SCHEMA_IDS[kind]} (8, 9, 14.1, 17.5)")
        if schema is None and base == rv.state and isinstance(v, dict) and isinstance(v.get("schema"), str):
            hit = rx_schema_by_id(st, v["schema"])
            schema = hit[1] if hit else None
        if schema is None:
            continue
        n += 1
        try:
            p += [f"{where}: {e}" for e in schema_errors(v, schema)[:3]]
        except SchemaKeywordError as exc:
            p.append(f"{where}: validator cannot evaluate: {exc}")
    check("T35 every JSON file validates against its schema and carries the v0.6 id: objects, snapshots (snapshot/2), manifests (manifest/3), revision logs, status/runs.json (runs/2), status/publications.json, review records (review/3), rollback records (rollback/1), and state files whose schema id has a schema file (review-queue/4) (8, 9, 12.8, 14.1, 17.5)", p, f"{n} files")


# --- T36 to T41: manifests ---


def rc_manifest_live(ctx):
    rv, st, m = ctx.rv, ctx.st, ctx.manifest
    man_ids, reg_ids = set(m.get("series", {})), ctx.reg_ids
    check("T36 every registered series is in the live manifest, and no other (9)",
          ([f"missing: {', '.join(sorted(reg_ids - man_ids))}"] if reg_ids - man_ids else []) +
          ([f"unregistered: {', '.join(sorted(man_ids - reg_ids))}"] if man_ids - reg_ids else []), f"{len(man_ids)} series")
    p, n = [], 0
    for sid, summ in sorted(m.get("series", {}).items()):
        groups = (("object", RX_OBJECT_PATH, summ.get("objects", [])), ("CSV segment", RX_CSV_PATH, rx_csv_refs(summ)),
                  ("revision log version", RX_LOG_PATH, summ.get("revisions", [])), ("revision CSV", RX_REVCSV_PATH, rx_list(summ.get("revision_csvs"))))
        for label, rx, refs in groups:
            for ref in refs:
                n += 1
                path, sha = ref.get("path"), ref.get("sha256")
                mt = rx.fullmatch(path) if isinstance(path, str) else None
                if not mt:
                    p.append(f"{sid}: {label} path {path!r} is not a content-addressed path (9)")
                    continue
                if mt.group(1) != sid:
                    p.append(f"{sid}: {path} is under another series")
                if label == "CSV segment" and mt.group(2) != ref.get("segment"):
                    p.append(f"{sid}: {path} names segment {mt.group(2)}, the entry says {ref.get('segment')} (12.3: a CSV segment's path names its series and segment)")
                if not is_sha256(sha) or mt.group(mt.lastindex) != sha[:16]:
                    p.append(f"{sid}: {path} is not named by the first 16 hex of its sha256 {sha}")
                data = rv.read(rv.live, path)
                if data is None:
                    p.append(f"{sid}: {path} missing from live/")
                elif sha256_hex(data) != sha:
                    p.append(f"{sid}: live/{path} has sha256 {sha256_hex(data)}, the manifest says {sha}" + hash_mismatch_note(data, sha))
    check("T37 the live manifest names only content-addressed files (objects, CSV segments, revision log versions); each exists in live/ with its SHA-256; every path equals its address and a CSV path names its series and segment (9, 12.3)", p, f"{n} files")
    ref, p = m.get("snapshot") or {}, []
    if ref.get("path") != f"snapshots/{ref.get('id')}.json":
        p.append(f"path {ref.get('path')} is not snapshots/{ref.get('id')}.json")
    for base in (rv.live, rv.arch):
        data = rv.read(base, ref.get("path"))
        if data is None:
            p.append(f"{rv.name(base)}/{ref.get('path')} missing")
        elif sha256_hex(data) != ref.get("sha256"):
            p.append(f"{rv.name(base)}/{ref.get('path')} has sha256 {sha256_hex(data)}, the manifest says {ref.get('sha256')}" + hash_mismatch_note(data, ref.get("sha256")))
    if ctx.cur is not None and ctx.cur.get("id") != ref.get("id"):
        p.append(f"the snapshot's own id is {ctx.cur.get('id')}")
    check("T38 the live manifest names its snapshot by id, path and SHA-256, present in live/ and in the archive (9, 12.3)", p, str(ref.get("id")))


def rc_manifest_archive(ctx):
    rv, p = ctx.rv, []
    names = rv.files(rv.manifests)
    for name, m, err in ctx.arch_manifests:
        if err:
            p.append(f"archive/manifests/{name}: {err}")
            continue
        want = snapshot_id_of(parse_utc(m["generated_at"])) + ".json" if is_time(m.get("generated_at")) else None
        if name != want:
            p.append(f"archive/manifests/{name} should be named {want} for generated_at {m.get('generated_at')}")
        size = len(rv.read(rv.manifests, name))
        if size > LIMIT_MANIFEST:
            p.append(f"archive/manifests/{name} is {size} bytes, over 256 KB (17.7)")
    live = rv.read(rv.live, "manifest.json")
    if not names:
        p.append("archive/manifests/ is empty")
    elif live != rv.read(rv.manifests, names[-1]):
        p.append(f"live/manifest.json ({sha256_hex(live or b'')[:16]}, {len(live or b'')} bytes) is not byte for byte the newest archived manifest {names[-1]} ({sha256_hex(rv.read(rv.manifests, names[-1]))[:16]})")
    check("T39 archive/manifests holds every manifest under its generated_at name, and the live manifest equals the newest one byte for byte (17.1, 17.5)", p, f"{len(names)} manifests")

    p, prev = [], None
    for name, m, err in ctx.arch_manifests:
        if err:
            continue
        sid_ = (m.get("snapshot") or {}).get("id")
        if sid_ not in ctx.snaps:
            p.append(f"{name}: names snapshot {sid_}, which is not in archive/files/snapshots")
        elif sha256_hex(rv.read(rv.arch, f"snapshots/{sid_}.json")) != m["snapshot"].get("sha256"):
            p.append(f"{name}: snapshot {sid_} sha256 differs from the archive's copy")
        want = (prev.get("snapshot") or {}).get("id") if prev else None
        if m.get("previous_snapshot") != want:
            p.append(f"{name}: previous_snapshot {m.get('previous_snapshot')}, the manifest before it named {want}")
        if prev and not m.get("generated_at", "") > prev.get("generated_at", ""):
            p.append(f"{name}: generated_at {m.get('generated_at')} is not later than the manifest before it")
        if m.get("rollback") is None and sid_ in ctx.snaps and ctx.snaps[sid_].get("created_at") != m.get("generated_at"):
            # 17.2: created_at and generated_at are both the run's now.
            p.append(f"{name}: generated_at {m.get('generated_at')} is not its snapshot's created_at {ctx.snaps[sid_].get('created_at')} (17.2)")
        prev = m
    check("T40 the manifest chain: each previous_snapshot is the snapshot the manifest before it named; every named snapshot is archived with its SHA-256; times ascend (9, 17.2)", p)

    p, n = [], 0
    for name, m, err in ctx.arch_manifests:
        rb = None if err else m.get("rollback")
        if rb is None:
            continue
        n += 1
        if rb.get("to") != (m.get("snapshot") or {}).get("id"):
            p.append(f"{name}: rollback.to {rb.get('to')} is not snapshot.id {(m.get('snapshot') or {}).get('id')}")
        if rb.get("from") != m.get("previous_snapshot"):
            p.append(f"{name}: rollback.from {rb.get('from')} is not previous_snapshot {m.get('previous_snapshot')}")
        if rb.get("to") not in ctx.snaps:
            p.append(f"{name}: rollback target {rb.get('to')} is not in the archive")
    check("T41 rollback consistency: a manifest's rollback.to is its snapshot.id and rollback.from its previous_snapshot; the target is archived (9, 17.5)", p,
          f"{n} rollback manifest(s); live rollback is {'set' if ctx.manifest.get('rollback') else 'null'}")


# --- T42 to T46: snapshots ---


def rc_snapshots(ctx):
    rv, st = ctx.rv, ctx.st
    paths = sorted({f for base in (rv.live, rv.arch) for f in rv.files(base) if f.startswith("snapshots/")})
    p = []
    for f in paths:
        mt = RX_SNAPSHOT_PATH.fullmatch(f)
        if not mt:
            p.append(f"{f} is not snapshots/<id>.json")
            continue
        if rv.read(rv.arch, f) is None:
            p.append(f"{f} is in live/ but not in archive/files/")
            continue
        v, err = rv.load(rv.arch, f)
        if err:
            p.append(f"{f}: {err}")
            continue
        if v.get("id") != mt.group(1):
            p.append(f"{f}: its id is {v.get('id')}")
        ids = set(v.get("series", {}))
        if ids != ctx.reg_ids:
            p.append(f"{f}: series missing {sorted(ctx.reg_ids - ids)}, unregistered {sorted(ids - ctx.reg_ids)} (8, 12.2)")
    check("T42 every snapshot in live/snapshots and archive/files/snapshots is archived, sits at snapshots/<id>.json and lists every registered series (8, 12.2, 17.1)", p, f"{len(paths)} snapshots")

    win_snaps, _ = rx_window(ctx)
    p, n = [], 0
    for sid_ in ctx.order:
        s = ctx.snaps[sid_]
        bases = [rv.arch] + ([rv.live] if sid_ in win_snaps else [])
        for series_id, state in sorted(s.get("series", {}).items()):
            for ref in state.get("objects", []):
                n += 1
                path = ref.get("path")
                for base in bases:
                    data = rv.read(base, path)
                    where = f"{sid_} {series_id}: {rv.name(base)}/{path}"
                    if data is None:
                        p.append(f"{where} missing")
                        continue
                    if sha256_hex(data) != ref.get("sha256"):
                        p.append(f"{where} has sha256 {sha256_hex(data)}, expected {ref.get('sha256')}")
                    if len(data) != ref.get("bytes"):
                        p.append(f"{where} is {len(data)} bytes, expected {ref.get('bytes')}")
                obj, _ = rv.load(rv.arch, path)
                if isinstance(obj, dict) and (obj.get("series") != series_id or obj.get("segment") != ref.get("segment")):
                    p.append(f"{sid_} {series_id}: {path} holds series {obj.get('series')} segment {obj.get('segment')}, the reference says segment {ref.get('segment')}")
        for ref in s.get("revisions", []):
            n += 1
            path = ref.get("path")
            if not (isinstance(path, str) and RX_LOG_PATH.fullmatch(path)):
                p.append(f"{sid_}: revision reference {path!r} is not revisions/<series>/<YYYY>/<16 hex>.json (9, 10)")
                continue
            for base in bases:
                data = rv.read(base, path)
                where = f"{sid_}: {rv.name(base)}/{path}"
                if data is None:
                    p.append(f"{where} missing")
                elif sha256_hex(data) != ref.get("sha256") or len(data) != ref.get("bytes"):
                    p.append(f"{where} has sha256 {sha256_hex(data)} and {len(data)} bytes, expected {ref.get('sha256')} and {ref.get('bytes')}")
    check("T43 snapshot closure: every object and revision log version a snapshot names exists in the archive, and in live/ for a snapshot of the window, with its SHA-256 and byte count (8, 12.3)", p,
          f"{n} references in {len(ctx.order)} snapshots, {len(win_snaps)} in the window")


def rc_snapshot_state(ctx):
    st, p, n = ctx.st, [], 0
    marker_keys = {"nyfed-markets": None, "fiscaldata": {"total_count"}, "frb-releases": {"latest_release_date", "data_release_date", "prepared"}}
    for sid_ in ctx.order:
        s = ctx.snaps[sid_]
        created = s.get("created_at")
        held = [h.get("series") for h in s.get("holds", [])]
        if len(set(held)) != len(held):
            p.append(f"{sid_}: a series has more than one open hold (11.5)")
        for e in s.get("frozen", []):
            p += shape_problems(f"{sid_} frozen {e.get('series') if isinstance(e, dict) else e}", e, {
                "series": lambda x: x in ctx.reg_ids, "candidate_sha256": is_sha256, "origin": lambda x: x in LOCK_ORIGINS, "frozen_at": is_time, "reason": is_str})
            if isinstance(e, dict) and is_time(e.get("frozen_at")) and is_time(created) and e["frozen_at"] > created:
                p.append(f"{sid_}: lock on {e.get('series')} frozen_at {e['frozen_at']} is after created_at")
        if not isinstance(s.get("frozen"), list):
            p.append(f"{sid_}: no frozen list (8)")
        elif len(rx_frozen(s)) != len(s["frozen"]):
            p.append(f"{sid_}: a lock (series, origin, candidate hash) is listed twice under frozen (11.5 v0.6: a series may carry several locks, each identified by its series, origin and hash)")
        for h in s.get("holds", []):
            if h.get("series") not in ctx.reg_ids:
                p.append(f"{sid_}: hold on unregistered series {h.get('series')!r}")
            elif s.get("series", {}).get(h["series"], {}).get("status") == "not-yet-published":
                p.append(f"{sid_}: hold on {h['series']}, which is not yet published")
            if is_time(h.get("opened_at")) and is_time(created) and h["opened_at"] > created:
                p.append(f"{sid_}: hold on {h.get('series')} opened_at {h['opened_at']} is after created_at")
        review = (s.get("run") or {}).get("trigger") == "review"
        for series_id in sorted(set(s.get("series", {})) & ctx.reg_ids):
            n += 1
            state, ser = s["series"][series_id], st.series[series_id]
            w = f"{sid_} {series_id}"
            marker, want = state.get("source_marker"), marker_keys.get(ser["source"])
            if review and state.get("attempt") != {"at": created, "outcome": "not-due", "error": None}:
                p.append(f"{w}: attempt {state.get('attempt')} in a review run, 17.2 gives at {created}, outcome not-due, error null")
            if state.get("status") == "not-yet-published":
                bad = [f for f in ("last_period", "retrieved_at", "checked_at", "source_marker") if state.get(f) is not None]
                if state.get("objects") != [] or bad or state.get("observation_count") != 0:
                    p.append(f"{w}: not-yet-published needs objects empty, count 0 and null last_period, retrieved_at, checked_at, source_marker; got objects {len(state.get('objects') or [])}, count {state.get('observation_count')}, non-null {bad} (8)")
                continue
            if not state.get("objects"):
                p.append(f"{w}: objects empty although the status is {state.get('status')} (8: empty only when not yet published)")
                continue
            obs = rx_obs(ctx, state)
            keys = [observation_key(o) for o in obs]
            segs = [r.get("segment") for r in state["objects"]]
            if segs != sorted(segs) or len(set(segs)) != len(segs):
                p.append(f"{w}: object segments {segs} are not ascending and unique")
            if ser["segment"] == "year":
                years = sorted({k[:4] for k in keys})
                if years != segs:
                    p.append(f"{w}: segments {segs} are not the calendar years of the periods {years} (7)")
            elif segs != ["all"]:
                p.append(f"{w}: segments {segs}, expected ['all'] (7)")
            if keys != sorted(keys) or len(set(keys)) != len(keys):
                p.append(f"{w}: periods across segments are not ascending and unique (6.2)")
            if keys and state.get("last_period") != keys[-1]:
                p.append(f"{w}: last_period {state.get('last_period')}, the objects end at {keys[-1]}")
            if state.get("observation_count") != len(obs):
                p.append(f"{w}: observation_count {state.get('observation_count')}, the objects hold {len(obs)}")
            ra, ca = state.get("retrieved_at"), state.get("checked_at")
            if ra is None or ca is None:
                p.append(f"{w}: a published series needs retrieved_at and checked_at")
            elif not ra <= ca <= created:
                p.append(f"{w}: retrieved_at {ra}, checked_at {ca}, created_at {created} are out of order (8)")
            # In a review run an approved series keeps the times of the run that fetched the candidate (T61).
            if state.get("status") == "refreshed" and not review and not (ra == ca == created):
                p.append(f"{w}: refreshed, so retrieved_at {ra} and checked_at {ca} must be the run's now {created} (17.2)")
            if state.get("status") == "unchanged" and ca != created:
                p.append(f"{w}: unchanged, so checked_at {ca} must be updated to the run's now {created} (8, 17.2)")
            if state.get("status") in ("refreshed", "unchanged") and not review and (state.get("attempt") or {}).get("outcome") != "ok":
                p.append(f"{w}: status {state.get('status')} with attempt outcome {(state.get('attempt') or {}).get('outcome')} (8)")
            if state.get("status") == "held" and series_id not in held:
                p.append(f"{w}: status held but the snapshot lists no hold for it (8)")
            if want is None:
                if marker is not None:
                    p.append(f"{w}: source_marker must be null for the New York Fed (8)")
            elif not isinstance(marker, dict) or set(marker) != want:
                p.append(f"{w}: source_marker {marker!r} does not have exactly {sorted(want)} (8)")
            elif "data_release_date" in marker and str(marker["latest_release_date"]) < str(marker["data_release_date"]):
                p.append(f"{w}: latest_release_date {marker['latest_release_date']} is before data_release_date {marker['data_release_date']} (2.4)")
    check("T44 every series state follows 8 and 17.2: the not-yet-published fields, objects and segments, last_period, observation_count, times per status, the not-due attempt of a review run, source_marker; a held status has its hold; each frozen entry has series, candidate_sha256, origin rejected or rolled-back, frozen_at not after the run, reason, one per lock (v0.6: several per series allowed) (8, 11.5)", p,
          f"{n} series states in {len(ctx.order)} snapshots")


def rc_first_change_point(ctx):
    st, p, seen = ctx.st, [], set()
    for sid_ in ctx.order:
        states = ctx.snaps[sid_].get("series", {})
        for series_id, ser in sorted(st.series.items()):
            src = (ser.get("derived_from") or {}).get("series")
            a, b = states.get(series_id, {}), states.get(src, {})
            if ser["frequency"] != "change-point" or not a.get("objects"):
                continue
            key = (series_id, tuple(r.get("sha256") for r in a["objects"]), tuple(r.get("sha256") for r in b.get("objects", [])))
            if key in seen:
                continue
            seen.add(key)
            points, records = rx_obs(ctx, a), rx_obs(ctx, b)
            marked = [o.get("effective") for o in points if o.get("starts_before_data")]
            if not points or marked != [points[0].get("effective")]:
                p.append(f"{sid_} {series_id}: starts_before_data is on {marked}, it belongs on the first change point alone (2.2, 6.1)")
            if not records:
                p.append(f"{sid_} {series_id}: published although {src}, the series it is derived from, is not")
            elif points and points[0].get("effective") != records[0].get("period"):
                p.append(f"{sid_} {series_id}: first change point {points[0].get('effective')}, the first {src} record is {records[0].get('period')} (2.2, 17.3, appendix B)")
            if points and points[0].get("effective", "") < ser["earliest"]:
                p.append(f"{sid_} {series_id}: first change point {points[0].get('effective')} is before the registry earliest {ser['earliest']} (4.4)")
    check("T77 the first change point, alone marked starts_before_data, is the first record of the series it is derived from (2.2, 17.3; with T78 both are the registry earliest)", p,
          f"{len(seen)} distinct states")


def rc_snapshot_chain(ctx):
    st, p = ctx.st, []
    reg_hash = sha256_hex(canon_bytes(st.registry))
    used_sources = {st.series[s]["source"] for s in ctx.reg_ids}
    for i, sid_ in enumerate(ctx.order):
        s = ctx.snaps[sid_]
        want_prev = ctx.order[i - 1] if i else None
        if s.get("previous") != want_prev:
            p.append(f"{sid_}: previous {s.get('previous')}, the snapshot before it in time is {want_prev} (8, 17.5)")
        if not is_time(s.get("created_at")) or snapshot_id_of(parse_utc(s["created_at"])) != sid_:
            p.append(f"{sid_}: created_at {s.get('created_at')} is not the id's time (3, 17.2)")
        for series_id, state in sorted(s.get("series", {}).items()):
            at = (state.get("attempt") or {}).get("at")
            if at != s.get("created_at"):
                p.append(f"{sid_} {series_id}: attempt.at {at} is not the run's now {s.get('created_at')} (17.2)")
        base_id = rx_base_id(ctx, sid_)
        base = ctx.snaps.get(base_id)
        if base is not None:
            changed = rx_hold_set(base) != rx_hold_set(s) or set(rx_frozen(base)) != set(rx_frozen(s))  # 17.3: a lock added or lifted
            for series_id in ctx.reg_ids:
                a, b = base.get("series", {}).get(series_id, {}), s.get("series", {}).get(series_id, {})
                if a.get("objects") != b.get("objects") or rx_category(base, series_id) != rx_category(s, series_id):
                    changed = True
            if not changed:
                p.append(f"{sid_}: no series' objects, no status between published, held and not yet published, no hold candidate and no frozen series differs from {base_id} (8, 17.3: no snapshot is written then)")
    check("T45 the snapshot chain: previous is the snapshot before in time, ids are the run's time, attempt.at is the run's now, and each snapshot records a change (3, 8, 17.2, 17.3)", p, f"{len(ctx.order)} snapshots")

    p, n_legacy, n_v07, n_arch = [], 0, 0, 0
    by_hash = registry_by_hash(st)
    arch_regs = rx_archived_registries(ctx)
    seen_v08 = None
    for sid_ in ctx.order:
        s = ctx.snaps[sid_]
        rh = (s.get("run") or {}).get("registry_sha256")
        allowed = rx_snapshot_registry(ctx, s)  # 22.9 (v0.8) and 21.1: which registry versions this snapshot may record
        found = rx_registry_for(ctx, rh)
        if rh not in allowed and found is not None and found[0] == "archived":
            n_arch += 1  # 22.9 (I44): the archived copy of an earlier v0.8 run's registry (an edit within the version)
        elif rh in arch_regs and arch_regs[rh][2] and rh not in allowed:
            p.append(f"{sid_}: its registry copy registry/econ-{rh[:16]}.json is not a valid registry: {arch_regs[rh][2][0]} (22.9)")
        elif rh in allowed:
            if allowed[rh] == "v0.6" and rh != registry_versions(st)["v0.7"][0]:
                n_legacy += 1  # written under v0.6: the v0.7 registry with conventions v0.6 (21.1, I7)
            elif allowed[rh] == "v0.7" and rh != reg_hash:
                n_v07 += 1  # written under v0.7: the current registry with the substitutions of I7 reversed
        else:
            p.append(f"{sid_}: run.registry_sha256 {str(rh)[:16]} is found neither as an archived registry copy of a v0.8 run nor as " + " nor ".join(f"the {v} registry's {h[:16]}" for h, v in allowed.items())
                     + " (22.9, I44, I7" + (", 21.1" if rx_legacy(ctx, s.get("created_at")) else "") + ")")
        reg_used = (found or (None, None, st.registry))[2]
        conv = reg_used.get("conventions") if isinstance(reg_used, dict) else None
        if conv not in (V07_CONVENTIONS, LEGACY_CONVENTIONS) and found is not None and conv == CONVENTIONS:
            seen_v08 = seen_v08 or sid_
        elif conv in (V07_CONVENTIONS, LEGACY_CONVENTIONS) and seen_v08 is not None:
            p.append(f"{sid_}: records a {conv} registry although {seen_v08} before it records a {CONVENTIONS} one (22.9: no snapshot with a v0.7 or v0.6 hash after one with the v0.8 hash)")
        notices = s.get("notices", {})
        if set(notices) != used_sources:
            p.append(f"{sid_}: notices for {sorted(notices)}, the registered series use {sorted(used_sources)}")
        for src in sorted(used_sources & set(notices)):
            for f in ("attribution", "notice", "terms_url"):
                if notices[src].get(f) != reg_used["sources"][src].get(f):
                    p.append(f"{sid_}: notices.{src}.{f} is not the text of the registry version it records, placeholders kept (8, 22.9)")
    check("T46 every snapshot carries the canonical SHA-256 of the registry it was built with and its notices as written there, placeholders kept: the current registry, the archived copy of an earlier v0.8 run's registry (I44), or before v0.8 the v0.7 one of I7 and the v0.6 one up to the promoted dataset; none with a v0.7 or v0.6 registry after one with v0.8 (4, 4.3, 8, 21.1, 22.9)", p,
          "; ".join(x for x in (f"{n_v07} snapshot(s) carry the v0.7 registry of I7" if n_v07 else "", f"{n_legacy} snapshot(s) written before v0.7 carry the v0.6 registry (21.1)" if n_legacy else "",
                               f"{n_arch} snapshot(s) carry an archived v0.8 registry copy (I44)" if n_arch else "") if x))


# --- T47 to T50: objects ---


def rc_objects(ctx):
    rv, st = ctx.rv, ctx.st
    first_named = {}
    for sid_ in ctx.order:
        for state in ctx.snaps[sid_].get("series", {}).values():
            for r in state.get("objects", []):
                first_named.setdefault(r.get("path"), sid_)
    paths = sorted({f for base in (rv.live, rv.arch) for f in rv.files(base) if f.startswith("objects/")})
    p1, p2, orphans = [], [], 0
    for f in paths:
        base = rv.arch if rv.read(rv.arch, f) is not None else rv.live
        obj, err = rv.load(base, f)
        if err:
            p1.append(f"{f}: {err}")
            continue
        try:
            canon = canon_bytes(obj)
        except ValueError as exc:
            p1.append(f"{f}: {exc}")
            continue
        expect = f"objects/{obj.get('series')}/{obj.get('segment')}/{sha256_hex(canon)[:16]}.json"
        if f != expect:
            p1.append(f"{f}: its content's address is {expect}")
        if len(rv.read(base, f)) > LIMIT_OBJECT:
            p2.append(f"{f}: {len(rv.read(base, f))} bytes, over 2 MB (17.7)")
        if f not in first_named:
            orphans += 1
        as_of = et_date(snapshot_time(first_named[f])) if f in first_named else dt.date.max
        try:
            p2 += [f"{f}: {x}" for x in object_semantics(st, obj, as_of)]
        except Exception as exc:
            p2.append(f"{f}: cannot be checked ({type(exc).__name__}: {exc})")
    check("T47 every object's path equals its address objects/<series>/<segment>/<first 16 hex of its SHA-256>.json (7, 12.3)", p1,
          f"{len(paths)} objects" + (f", {orphans} named by no snapshot (orphans are kept, 17.4)" if orphans else ""))
    check("T48 every object's observations follow 6.1, 6.2, 4.4 and 11.4: ascending, no duplicates, decimals per registry, range, weekend rule with known_inconsistencies, missing exactly when value is null, none after the run's ET date", p2,
          f"{len(paths)} objects")

    p, seen = [], set()
    for sid_ in ctx.order:
        for series_id, state in sorted(ctx.snaps[sid_].get("series", {}).items()):
            key = (series_id, tuple(r.get("sha256") for r in state.get("objects", [])))
            ser = st.series.get(series_id)
            if key in seen or ser is None or not state.get("objects"):
                continue
            seen.add(key)
            cont = ser["continuity"]
            keys = [observation_key(o) for o in rx_obs(ctx, state)]
            for a, b in zip(keys, keys[1:]):
                try:
                    if cont["unit"] == "days":
                        gap = (parse_date(b) - parse_date(a)).days
                    elif cont["unit"] == "months":
                        gap = (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])
                    else:
                        break
                except ValueError:
                    continue
                if gap > cont["max_gap"]:
                    p.append(f"{series_id} (first in snapshot {sid_}): gap of {gap} {cont['unit']} from {a} to {b}, over max_gap {cont['max_gap']}")
    check("T49 continuity: no gap over continuity.max_gap between consecutive periods, across segments, in any snapshot (4.4, 11.4)", p, f"{len(seen)} distinct series states")


H6_FIXTURE = FX_H6_DATES


def rx_fixture_release_dates():
    """The H.6 release dates of the section 18 fixture (the saved releaseDates.json), markers
    stripped (4.5), or [] when it cannot be read."""
    try:
        doc = load_strict(H6_FIXTURE.read_bytes())
        return sorted(f"{x[:4]}-{x[4:6]}-{x[6:8]}" for y in doc for m in y["Months"] for x in m["Dates"])
    except Exception:
        return []


def rc_released(ctx):
    st, p, n, lenient = ctx.st, [], 0, 0
    h6_dates = rx_fixture_release_dates()
    nr = {"basis": "not-recorded", "date": None}
    for series_id in sorted(ctx.reg_ids):
        ser = st.series[series_id]
        cal = st.registry["calendars"][ser["release"]["calendar"]]
        basis = ser["release"]["basis"]
        seen, first_published, last_key = set(), None, None
        for sid_ in ctx.order:
            state = ctx.snaps[sid_].get("series", {}).get(series_id, {})
            if not state.get("objects"):
                continue
            key = tuple(r.get("sha256") for r in state["objects"])
            if first_published is None:
                first_published = sid_
            if key == last_key:
                continue
            last_key = key
            obs = rx_obs(ctx, state)
            for i, o in enumerate(obs):
                k = observation_key(o)
                if k in seen:
                    continue  # an already published period keeps its released (17.3); a change needs a record (T60)
                seen.add(k)
                n += 1
                got = o.get("released")
                if ser["frequency"] == "change-point" and i == 0:
                    want = nr
                elif basis == "rule":
                    want = {"basis": "rule", "date": next_business_day(parse_date(k)).isoformat()} if k >= cal.get("rule_valid_from", "9999") else nr
                elif basis == "first-seen":
                    want = nr if sid_ == first_published else {"basis": "first-seen", "date": et_date(snapshot_time(sid_)).isoformat()}
                    snap = ctx.snaps[sid_]
                    if (snap.get("run") or {}).get("trigger") == "review" and isinstance(got, dict) and got.get("basis") == "first-seen":
                        # reading: an approved candidate is published exactly as held (17.5), so its new
                        # periods may carry the ET date of the run that built it (17.3) instead of the
                        # approval's; any date from the hold's opening to the approval is accepted.
                        base = ctx.snaps.get(rx_base_id(ctx, sid_)) or {}
                        opened = [h.get("opened_at") for h in base.get("holds", []) if h.get("series") == series_id and is_time(h.get("opened_at"))]
                        if opened and et_date(parse_utc(opened[0])).isoformat() <= str(got.get("date")) <= want["date"]:
                            continue
                else:
                    # calendar: the first release date after the month ends, when the source fixture's
                    # release dates reach past the month end. The dates a run was given are not stored in
                    # the root, so for later months only the form can be checked: not-recorded, or a date
                    # after the month ends, on or after calendar_valid_from, not after the snapshot's ET date.
                    me = month_end(k).isoformat()
                    after = [x for x in h6_dates if x > me]
                    if after:
                        want = {"basis": "calendar", "date": after[0]} if after[0] >= cal.get("calendar_valid_from", "9999") else nr
                        if got != want:
                            p.append(f"{series_id} {k} (first in {sid_}): released {got}, 6.3 with the fixture release dates gives {want}")
                        continue
                    lenient += 1
                    ok = got == nr or (isinstance(got, dict) and got.get("basis") == "calendar" and isinstance(got.get("date"), str)
                                       and got["date"] > month_end(k).isoformat() and got["date"] >= cal.get("calendar_valid_from", "9999")
                                       and got["date"] <= et_date(snapshot_time(sid_)).isoformat())
                    if not ok:
                        p.append(f"{series_id} {k} (first in {sid_}): released {got} is neither not-recorded nor a calendar date after the month end, from {cal.get('calendar_valid_from')}, up to the snapshot's ET date (6.3)")
                    continue
                if got != want:
                    p.append(f"{series_id} {k} (first in {sid_}): released {got}, 6.3 gives {want}")
    check("T50 every period's released follows 6.3 when it first appears: rule from rule_valid_from, first-seen as the snapshot's ET date after the first published snapshot, not-recorded for the backfill and the first change point", p,
          f"{n} periods; H.6 release dates from {H6_FIXTURE.name if h6_dates else 'no fixture'}"
          + (f"; {lenient} calendar-basis periods past those dates checked for form only" if lenient else ""))


# --- T51 to T57: manifest summaries, health, CSVs ---


def rx_stale(ctx, series_id, state_of, at, depth=0):
    """True, False, or None when it cannot be computed (4.4, 14.2)."""
    ser = ctx.st.series[series_id]
    if "follows" in ser["staleness"]:
        return rx_stale(ctx, ser["staleness"]["follows"], state_of, at, depth + 1) if depth < 3 else None
    state = state_of.get(series_id, {})
    dl, _ = deadline_for(ctx.st, series_id, state.get("last_period"), state.get("source_marker"))
    if dl is None:
        return None
    thr = stale_threshold(ctx.st, series_id, dl)
    return None if thr is None else at >= thr


def rc_manifest_summaries(ctx):
    rv, st = ctx.rv, ctx.st
    p_sum, p_status, p_attr, p_win, p_sched, p_next, p_csv = [], [], [], [], [], [], []
    n_csv, csv_done, next_notes, n_next, n_sched_legacy = 0, {}, [], 0, 0
    pins_doc, _ = rv.load(rv.state, "pins.json")
    pins = rx_pins(ctx)
    unpinned = {u.get("snapshot") for u in (pins_doc.get("unpinned") or []) if isinstance(u, dict)} if isinstance(pins_doc, dict) and isinstance(pins_doc.get("unpinned"), list) else set()
    for name, m, err in ctx.arch_manifests:
        if err:
            continue
        s = ctx.snaps.get((m.get("snapshot") or {}).get("id"))
        if s is None:
            continue  # reported by T40
        gen = parse_utc(m["generated_at"])
        gen_year = et_date(gen).year
        logs = rx_logs_as_of(ctx).get(s["id"], {})
        frozen = rx_locks_of(ctx, m)  # 9, 12.9 (v0.6): the snapshot's frozen plus, after a rollback, its record's locks
        frozen_series = lock_series(frozen) | set(((m.get("rollback") or {}).get("locked") or []) if isinstance(m.get("rollback"), dict) else [])
        state_of = s.get("series", {})
        held = {h.get("series") for h in s.get("holds", [])}
        if set(m.get("series", {})) != ctx.reg_ids:
            p_sum.append(f"{name}: series are not exactly the registered ones")
        for sid in sorted(set(m.get("series", {})) & set(state_of) & ctx.reg_ids):
            summ, state, ser = m["series"][sid], state_of[sid], st.series[sid]
            w = f"{name} {sid}"
            obs = rx_obs(ctx, state)
            for f in ("title", "unit_label", "frequency", "class"):
                if summ.get(f) != ser.get(f):
                    p_sum.append(f"{w}: {f} {summ.get(f)!r}, the registry has {ser.get(f)!r}")
            got_objs = [(r.get("path"), r.get("sha256")) for r in summ.get("objects", [])]
            want_objs = [(r.get("path"), r.get("sha256")) for r in state.get("objects", [])]
            if got_objs != want_objs:
                p_sum.append(f"{w}: objects {got_objs[:2]} differ from the snapshot's {want_objs[:2]} (12.9: hashes)")
            for f in ("last_period", "retrieved_at", "checked_at"):
                if summ.get(f) != state.get(f):
                    p_sum.append(f"{w}: {f} {summ.get(f)}, the snapshot has {state.get(f)}")
            want_logs = [logs[k] for k in sorted(logs) if k[0] == sid]
            if state.get("status") == "not-yet-published":
                bad = [f for f in ("last_value", "last_range", "last_released") if summ.get(f) is not None]
                if bad or summ.get("revisions") != [] or summ.get("csvs") != []:
                    p_sum.append(f"{w}: not yet published, so last_value, last_range, last_released must be null and revisions and csvs empty; non-null {bad}, revisions {len(summ.get('revisions') or [])}, csvs {summ.get('csvs')!r:.60} (8, 9)")
            elif obs:
                last = obs[-1]
                want_value = last.get("value") if ("period" in last or last.get("kind") == "rate") else None
                want_range = {"lower": last.get("lower"), "upper": last.get("upper")} if last.get("kind") == "range" else None
                if summ.get("last_value") != want_value:
                    p_sum.append(f"{w}: last_value {summ.get('last_value')!r}, the last observation {observation_key(last)} gives {want_value!r} (9)")
                if summ.get("last_range") != want_range:
                    p_sum.append(f"{w}: last_range {summ.get('last_range')!r}, the last observation gives {want_range!r} (9)")
                if summ.get("last_released") != last.get("released"):
                    p_sum.append(f"{w}: last_released {summ.get('last_released')}, the last observation has {last.get('released')}")
                if m.get("rollback") is None and summ.get("revisions") != want_logs:
                    p_sum.append(f"{w}: revisions {[r.get('path') for r in summ.get('revisions', [])]}, the latest log version of each year up to snapshot {s['id']} is {[r['path'] for r in want_logs]} (9)")
                if not summ.get("csvs"):
                    p_sum.append(f"{w}: a published series without CSV segments (9, 16)")
            # Status as of generated_at (9, 11.5, 14.2, 4.4)
            if state.get("status") == "not-yet-published":
                want_status = "not-yet-published"
            elif sid in held or state.get("status") == "held":
                want_status = "held"
            elif sid in frozen_series:
                want_status = "frozen"  # 9: held and frozen come before staleness
                # reading (as in v0.4): status_reason shows the lock's reason, the reviewer's or the rollback's;
                # v0.6: with several locks, the reason of at least one of them.
                reasons = [str(e.get("reason")) for e in locks_of_series(frozen, sid) if e.get("reason") is not None]
                if not is_str(summ.get("status_reason")) or (reasons and not any(r in summ["status_reason"] for r in reasons)):
                    p_status.append(f"{w}: status_reason {summ.get('status_reason')!r} does not show the reason of a lock of the series {reasons} (11.5)")
            else:
                stale = rx_stale(ctx, sid, state_of, gen)
                want_status = None if stale is None else ("stale" if stale else "fresh")
            if want_status is None:
                p_status.append(f"{w}: status {summ.get('status')} cannot be recomputed (no deadline)")
            elif summ.get("status") != want_status:
                p_status.append(f"{w}: status {summ.get('status')}, as of generated_at {m['generated_at']} it is {want_status}")
            # Attribution and notice (4.3, 8, decision P5)
            src = st.registry["sources"][ser["source"]]
            year = et_date(parse_utc(summ["retrieved_at"])).year if is_time(summ.get("retrieved_at")) else gen_year
            for f in ("attribution", "notice"):
                want = fill_placeholders(src.get(f), ser["data_name"], year)
                if summ.get(f) != want:
                    p_attr.append(f"{w}: {f} is {summ.get(f)!r}, expected {want!r} ({{year}} is the ET year of {'retrieved_at' if summ.get('retrieved_at') else 'generated_at'})")
            # CSV segments, byte for byte (16, 12.9): each from its segment object's observations
            # and the entry's own retrieved_at.
            by_seg = {r.get("segment"): r for r in state.get("objects", [])}
            for ref in rx_csv_refs(summ):
                n_csv += 1
                oref = by_seg.get(ref.get("segment"))
                if oref is None or not is_time(ref.get("retrieved_at")):
                    p_csv.append(f"{w}: CSV {ref.get('path')} of segment {ref.get('segment')!r} has no object of that segment in the snapshot, or no retrieved_at (T87)")
                    continue
                pre_v08 = m.get("schema") != MANIFEST_V4  # 22.9: in a manifest/3
                key = (ref.get("path"), ref.get("sha256"), ref["retrieved_at"], oref.get("sha256"), pre_v08)
                if key not in csv_done:
                    data = rv.read(rv.arch, ref.get("path"))
                    seg_obs = rx_obs(ctx, {"objects": [oref]})
                    want = csv_segment_bytes(st, ser, seg_obs, ref.get("segment"), ref["retrieved_at"])
                    if pre_v08 and ser["source"] == NYFED and data is not None and data != want:
                        # 22.9: in a manifest/3 a New York Fed CSV's Terms: line may carry the old URL;
                        # every other byte must match.
                        alt = csv_segment_bytes(st, ser, seg_obs, ref.get("segment"), ref["retrieved_at"], reg=registry_versions(st)["v0.7"][2])
                        if data == alt:
                            want = alt
                    if data is None:
                        csv_done[key] = f"{ref.get('path')} is not in archive/files/"
                    elif sha256_hex(data) != ref.get("sha256"):
                        csv_done[key] = f"archive/files/{ref.get('path')} has sha256 {sha256_hex(data)}, the manifest says {ref.get('sha256')}" + hash_mismatch_note(data, ref.get("sha256"))
                    elif data != want:
                        csv_done[key] = f"{ref.get('path')} differs from the segment CSV recomputed from object {oref.get('path')}, the registry and retrieved_at {ref['retrieved_at']} at {first_line_difference(data, want)}"
                    else:
                        csv_done[key] = None
                if csv_done[key]:
                    p_csv.append(f"{w}: {csv_done[key]}")
        # pages_window (9, 13, 17.6)
        pw = m.get("pages_window") or {}
        if pw.get("days") != WINDOW_DAYS:
            p_win.append(f"{name}: pages_window.days {pw.get('days')}, expected {WINDOW_DAYS}")
        pinned = pw.get("pinned") or []
        if name == ctx.arch_manifests[-1][0]:
            known = {x.get("snapshot") for x in pins} | unpinned
            if set(pinned) - known:
                p_win.append(f"{name}: pinned {sorted(set(pinned) - known)} not in archive/state/pins.json")
            late = sorted(x.get("snapshot") for x in pins if is_time(x.get("pinned_at")) and x["pinned_at"] <= m["generated_at"] and x.get("snapshot") not in pinned)
            if late:
                p_win.append(f"{name}: pins.json pins {late} made before generated_at are not in pages_window.pinned")
        # schedule (14.2)
        sched = (m.get("health") or {}).get("schedule")
        if isinstance(sched, list) and sorted(sched) == sorted(SCHEDULE_LINES_V06) and rx_legacy(ctx, m.get("generated_at")):
            n_sched_legacy += 1  # written under v0.6, when decision P8's lines were the ones listed (see LEGACY in section_root)
        elif not isinstance(sched, list) or sorted(sched) != sorted(SCHEDULE_LINES):
            p_sched.append(f"{name}: schedule {sched!r}, expected the cron line in force {SCHEDULE_LINES} (14.2 v0.7; {SCHEDULE_LINES_V06} were decision P8's lines before v0.7)")
        # expected_next_update_by (14.2)
        deadlines, missing = [], []
        for sid in sorted(set(state_of) & ctx.reg_ids):
            state = state_of[sid]
            if state.get("status") == "not-yet-published" or sid in held or sid in frozen_series or state.get("status") == "held" or "follows" in st.series[sid]["staleness"]:
                continue
            dl, why = deadline_for(st, sid, state.get("last_period"), state.get("source_marker"))
            if dl is None:
                missing.append(f"{sid}: {why}")
            else:
                deadlines.append((dl, sid, why))
        got = (m.get("health") or {}).get("expected_next_update_by")
        if missing:
            next_notes.append(f"{name}: {'; '.join(missing)}")
        elif not deadlines:
            n_next += 1
            if got != m["generated_at"]:
                p_next.append(f"{name}: expected_next_update_by {got}; with no published series that is neither held nor frozen it is generated_at {m['generated_at']} (17.3)")
        else:
            n_next += 1
            dl, sid, why = min(deadlines)
            if got != fmt_utc(dl):
                p_next.append(f"{name}: expected_next_update_by {got}, the earliest deadline is {fmt_utc(dl)} ({sid}: {why}, plus grace)")
    nm = len(ctx.arch_manifests)
    check("T51 every manifest's per-series summary equals its snapshot and objects: registry names, object hashes, last period, last value or range, last released, times, latest revision log versions (9, 12.9)", p_sum, f"{nm} manifests")
    check("T52 every manifest's series status is right as of its generated_at: not-yet-published, held for a series with an open hold, frozen with the lock's reason for a series listed in the snapshot's frozen or the manifest's rollback.locked (either origin), else stale or fresh by the 14.2 deadline and the registry staleness rule (9, 11.5, 12.9, 14.2, 4.4)", p_status, f"{nm} manifests")
    check("T53 every manifest's attribution and notice are the registry texts filled with data_name and {year} as the ET year of retrieved_at, or of generated_at when not yet published (4.3, 8, decision P5)", p_attr, f"{nm} manifests")
    check("T54 pages_window.days is 35 and the newest manifest's pinned ids agree with archive/state/pins.json (9, 13, 17.6)", p_win)
    check("T55 every manifest's health.schedule lists the cron lines in force: the one line 17 */4 * * * of 14.2 (v0.7, F7)", p_sched,
          " | ".join(SCHEDULE_LINES) + (f"; {n_sched_legacy} manifest(s) written before v0.7 list decision P8's lines (21.1)" if n_sched_legacy else ""))
    if p_next or n_next:
        check("T56 health.expected_next_update_by is the earliest 14.2 deadline among published series that are neither held nor frozen, or generated_at when there is none (14.2, 17.3)", p_next,
              f"{n_next} manifests recomputed" + (f"; not computable for {len(next_notes)}: {next_notes[0]}" if next_notes else ""))
    else:
        skip("T56 health.expected_next_update_by is the earliest 14.2 deadline among published series that are neither held nor frozen, or generated_at when there is none (14.2, 17.3)", "; ".join(next_notes[:3]) or "no manifest")
    check("T57 every CSV segment a manifest names is, byte for byte, the section 16 file recomputed from that segment's object, the registry and the entry's retrieved_at: the 'Segment <segment>: <first> to <last>.' line, the per-segment 'Retrieved' time and {year} (16, 12.9)", p_csv,
          f"{n_csv} references, {len(csv_done)} distinct CSV segments")


# --- T58 to T61: revision logs and provenance ---


def rx_member_form(field, v):
    """How a member is written in a revision record's before and after (10)."""
    decimal_field = field in DECIMAL_FIELDS or field.startswith("extra.")
    if v is _ABSENT or (v is None and decimal_field):
        return None
    return v if decimal_field else canon_text(v)


def rx_diff(a, b):
    out = []
    for k in sorted((set(a) | set(b)) - {"extra", "period", "effective"}):
        va, vb = a.get(k, _ABSENT), b.get(k, _ABSENT)
        if (va is _ABSENT) != (vb is _ABSENT) or (va is not _ABSENT and not json_equal(va, vb)):
            out.append((k, rx_member_form(k, va), rx_member_form(k, vb)))
    ea = a.get("extra") if isinstance(a.get("extra"), dict) else {}
    eb = b.get("extra") if isinstance(b.get("extra"), dict) else {}
    for k in sorted(set(ea) | set(eb)):
        fa, fb = rx_member_form("extra." + k, ea.get(k, _ABSENT)), rx_member_form("extra." + k, eb.get(k, _ABSENT))
        if fa != fb:
            out.append(("extra." + k, fa, fb))
    return out


def rx_record_key(r):
    def norm(x):
        # reading: an absent member may be written as JSON null or as the text "null"
        return None if x == "null" and not (r.get("field") in DECIMAL_FIELDS or str(r.get("field")).startswith("extra.")) else x
    return (r.get("period"), r.get("field"), norm(r.get("before")), norm(r.get("after")))


def rc_revision_logs(ctx):
    rv, st = ctx.rv, ctx.st
    paths = sorted({f for base in (rv.live, rv.arch) for f in rv.files(base) if f.startswith("revisions/")})
    p, versions = [], {}
    for f in paths:
        if RX_REVCSV_PATH.fullmatch(f):
            continue  # 10 (v0.8): a revision CSV beside its log version, checked by T121
        mt = RX_LOG_PATH.fullmatch(f)
        base = rv.arch if rv.read(rv.arch, f) is not None else rv.live
        v, err = rv.load(base, f)
        if not mt:
            p.append(f"{f} is not revisions/<series>/<YYYY>/<16 hex>.json")
            continue
        if err:
            p.append(f"{f}: {err}")
            continue
        data = rv.read(base, f)
        if f != f"revisions/{v.get('series')}/{v.get('year')}/{sha256_hex(data)[:16]}.json":
            p.append(f"{f}: its content's address is revisions/{v.get('series')}/{v.get('year')}/{sha256_hex(data)[:16]}.json")
        ser = st.series.get(v.get("series"))
        if ser is None:
            p.append(f"{f}: series {v.get('series')!r} is not registered")
            continue
        recs = v.get("records") if isinstance(v.get("records"), list) else []
        versions.setdefault((v.get("series"), v.get("year")), []).append((f, recs))
        if not recs:
            p.append(f"{f}: no record (10: a year has a log only once it has a record)")
        for i, r in enumerate(recs):
            w = f"{f} record {i}"
            if not is_time(r.get("detected_at")) or et_date(parse_utc(r["detected_at"])).year != v.get("year"):
                p.append(f"{w}: detected_at {r.get('detected_at')} is not in ET year {v.get('year')} (10)")
            if r.get("snapshot") not in ctx.snaps:
                p.append(f"{w}: snapshot {r.get('snapshot')} is not in the archive")
            field = str(r.get("field"))
            for side in ("before", "after"):
                x = r.get(side)
                if x is None:
                    continue
                if field in DECIMAL_FIELDS:
                    if not exact_places(x, ser["decimals"]):
                        p.append(f"{w}: {side} {x!r} of {field} is not the decimal string with {ser['decimals']} places (10)")
                elif field.startswith("extra."):
                    places = EXTRA_PLACES.get(field[6:])
                    if not (_DECIMAL_TEXT.fullmatch(x) if places is None else exact_places(x, places)):
                        p.append(f"{w}: {side} {x!r} of {field} is not its decimal string (10)")
                else:
                    try:
                        if canon_text(load_strict(x.encode("utf-8"))) != x:
                            p.append(f"{w}: {side} of {field} is not canonical JSON text (10)")
                    except Exception:
                        p.append(f"{w}: {side} {x[:60]!r} of {field} is not JSON text (10)")
            if field == "period":
                sides = [r.get("before"), r.get("after")]
                if sum(x is None for x in sides) != 1 or not all(x is None or (isinstance(x, str) and x.startswith("{")) for x in sides):
                    p.append(f"{w}: a period record needs the canonical JSON of the observation in before (removed) or in after (inserted), and null in the other (10)")
            if r.get("kind") == "approved-hold" and not re.fullmatch(r"approved in review run \S.* on \d{4}-\d{2}-\d{2}", str(r.get("basis")), re.ASCII):
                p.append(f"{w}: basis {r.get('basis')!r} is not 'approved in review run <run id> on <ET date>' (10, 17.5)")
            if r.get("kind") == "rollback" and not re.fullmatch(r"rolled back to snapshot \d{8}T\d{6}Z in run \S+ on \d{4}-\d{2}-\d{2}", str(r.get("basis")), re.ASCII):
                p.append(f"{w}: basis {r.get('basis')!r} is not 'rolled back to snapshot <to> in run <run id> on <ET date>' (17.5)")
            if r.get("kind") not in ("expected", "approved-hold", "rollback") or not is_str(r.get("basis")):
                p.append(f"{w}: kind {r.get('kind')!r}, basis {r.get('basis')!r} (10)")
    check("T58 every revision log version sits at its address, belongs to a registered series, has records, and each record has the 10 forms: ET year of detection, decimal strings or canonical JSON text in before and after, kind and basis", p,
          f"{len(paths)} log versions")

    p = []
    for (series_id, year), vs in sorted(versions.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        vs.sort(key=lambda x: len(x[1]))
        for (fa, ra), (fb, rb) in zip(vs, vs[1:]):
            if len(ra) == len(rb):
                p.append(f"{series_id} {year}: {fa} and {fb} both have {len(ra)} records but differ")
            elif rb[:len(ra)] != ra:
                i = next(k for k in range(len(ra)) if rb[k] != ra[k])
                p.append(f"{series_id} {year}: {fb} ({len(rb)} records) does not extend {fa} ({len(ra)} records): record {i} differs")
    check("T59 revision logs are append-only: the versions of one series and year form one chain, each equal to the one before plus new records at the end (10, 12.6)", p,
          f"{len(versions)} logs")
    ctx.log_versions = versions


def rx_changes(old_obs, new_obs):
    """Section 10: what differs between two states of a series as (period, field, before, after):
    every changed member, every removed period, every period inserted on or before the last
    old one. A period appended after the last old one is not a change."""
    old = {observation_key(o): o for o in old_obs}
    new = {observation_key(o): o for o in new_obs}
    out = []
    if not old:
        return out
    last = max(old)
    for k in sorted(set(old) | set(new)):
        if k not in new:
            out.append((k, "period", canon_text(old[k]), None))
        elif k not in old:
            if k <= last:
                out.append((k, "period", None, canon_text(new[k])))
        else:
            out += [(k, f, a, b) for f, a, b in rx_diff(old[k], new[k])]
    return out


def rx_rollback_run(ctx, at):
    """The id of the rollback run that wrote the manifest generated at `at`, from the run records, or None."""
    for f in ctx.rv.files(ctx.rv.state):
        if f.startswith("run-records/"):
            v, err = ctx.rv.load(ctx.rv.state, f)
            if not err and isinstance(v, dict) and v.get("trigger") == "rollback" and v.get("started_at") == at:
                return v.get("id")
    return None


def rx_events(ctx):
    """Everything that can write a revision log version, in time order: ("snapshot", id) for a
    publishing run and ("rollback", manifest name, manifest) for a rollback (10, 17.5)."""
    ev = [(snapshot_time(sid_), 0, ("snapshot", sid_, None)) for sid_ in ctx.order]
    for name, m, err in ctx.arch_manifests:
        if not err and m.get("rollback") is not None and is_time(m.get("generated_at")):
            ev.append((parse_utc(m["generated_at"]), 1, ("rollback", name, m)))
    return [e[2] for e in sorted(ev, key=lambda e: (e[0], e[1]))]


def rx_logs_as_of(ctx):
    """Snapshot id to the latest revision log version of each (series, year) once that snapshot
    is written, rollback versions of earlier rollbacks included (9, 17.5)."""
    if ctx.logs_as_of is None:
        ctx.logs_as_of, latest = {}, {}
        for kind, name, m in rx_events(ctx):
            if kind == "snapshot":
                for r in ctx.snaps[name].get("revisions", []):
                    mt = RX_LOG_PATH.fullmatch(r.get("path") or "")
                    if mt:
                        latest[(mt.group(1), mt.group(2))] = {"path": r["path"], "sha256": r.get("sha256")}
                ctx.logs_as_of[name] = dict(latest)
            else:
                for sid, summ in m.get("series", {}).items():
                    for r in summ.get("revisions", []):
                        mt = RX_LOG_PATH.fullmatch(r.get("path") or "")
                        if mt and mt.group(1) == sid:
                            latest[(mt.group(1), mt.group(2))] = {"path": r["path"], "sha256": r.get("sha256")}
    return ctx.logs_as_of


def rc_revision_records(ctx):
    rv, st = ctx.rv, ctx.st
    p, p_rb, latest, latest_ref, n_changes, n_records, n_rb, n_rb_records = [], [], {}, {}, 0, 0, 0, 0
    for kind, name, m in rx_events(ctx):
        if kind == "rollback":
            # 10, 17.5: a rollback writes, for every series whose observations differ between the two
            # states, the newest log version plus one `rollback` record per differing member.
            n_rb += 1
            now = m["generated_at"]
            frm, to = ctx.snaps.get(m.get("previous_snapshot")), ctx.snaps.get((m.get("snapshot") or {}).get("id"))
            if frm is None or to is None:
                p_rb.append(f"{name}: the snapshot before the rollback or its target is not in the archive")
                continue
            year = str(et_date(parse_utc(now)).year)
            run_id = rx_rollback_run(ctx, now)
            want_basis = f"rolled back to snapshot {to.get('id')} in run {run_id} on {et_date(parse_utc(now)).isoformat()}"
            named = {}
            for sid, summ in m.get("series", {}).items():
                for r in summ.get("revisions", []):
                    mt = RX_LOG_PATH.fullmatch(r.get("path") or "")
                    if mt:
                        named[(mt.group(1), mt.group(2))] = r
            for key in sorted(set(latest_ref) - set(named)):
                p_rb.append(f"{name}: the {key[0]} {key[1]} revision log ({latest_ref[key]}) is not named by the rollback manifest; nothing is ever deleted from a log (10, 17.5)")
            for sid in sorted(ctx.reg_ids):
                exp = rx_changes(rx_obs(ctx, frm.get("series", {}).get(sid, {})), rx_obs(ctx, to.get("series", {}).get(sid, {})))
                key, before = (sid, year), latest.get((sid, year), [])
                ref = named.get(key)
                for other in sorted(k for k in named if k[0] == sid and k != key):
                    if named[other].get("path") != latest_ref.get(other):
                        p_rb.append(f"{name} {sid}: the {other[1]} log version {named[other].get('path')} is not the newest one {latest_ref.get(other)}")
                if not exp:
                    if (ref or {}).get("path") != latest_ref.get(key):
                        p_rb.append(f"{name} {sid}: its observations do not differ between {frm.get('id')} and {to.get('id')}, yet the manifest names {(ref or {}).get('path')} instead of the newest version {latest_ref.get(key)}")
                    continue
                if ref is None:
                    p_rb.append(f"{name} {sid}: {len(exp)} members differ between {frm.get('id')} and {to.get('id')} but the manifest names no {year} revision log version with their rollback records (10, 17.5)")
                    continue
                v, err = rv.load(rv.arch, ref.get("path"))
                recs = v.get("records", []) if not err and isinstance(v, dict) else []
                if err:
                    p_rb.append(f"{name} {sid}: {ref.get('path')} unreadable in the archive ({err})")
                    continue
                if recs[:len(before)] != before:
                    p_rb.append(f"{name} {sid}: {ref.get('path')} does not extend the newest version ({len(before)} records): nothing is ever deleted from a log (10)")
                tail = recs[len(before):] if recs[:len(before)] == before else [r for r in recs if r.get("kind") == "rollback" and r.get("detected_at") == now]
                got = [rx_record_key(r) for r in tail]
                n_rb_records += len(got)
                for k in sorted(set(exp) | set(got), key=repr):
                    ne, ng = exp.count(k), got.count(k)
                    if ne != ng:
                        p_rb.append(f"{name} {sid}: {k[0]} {k[1]} ({k[2]!r:.60} to {k[3]!r:.60}): {ne} differing member(s) between the two states, {ng} rollback record(s) (10, 17.5)")
                for r in tail:
                    if r.get("kind") != "rollback" or r.get("snapshot") != to.get("id") or r.get("detected_at") != now:
                        p_rb.append(f"{name} {sid}: record {r.get('period')} {r.get('field')} has kind {r.get('kind')!r}, snapshot {r.get('snapshot')}, detected_at {r.get('detected_at')}; expected rollback, {to.get('id')}, {now}")
                    if (run_id is not None and r.get("basis") != want_basis) or not re.fullmatch(r"rolled back to snapshot \d{8}T\d{6}Z in run \S+ on \d{4}-\d{2}-\d{2}", str(r.get("basis")), re.ASCII):
                        p_rb.append(f"{name} {sid}: record {r.get('period')} {r.get('field')} has basis {r.get('basis')!r}, expected {want_basis!r} (17.5)")
                latest[key], latest_ref[key] = recs, ref.get("path")
            continue
        sid_ = name
        s = ctx.snaps[sid_]
        base_id = rx_base_id(ctx, sid_)
        base = ctx.snaps.get(base_id)
        run = s.get("run") or {}
        new, seen_logs = {}, set()
        for ref in s.get("revisions", []):
            mt = RX_LOG_PATH.fullmatch(ref.get("path") or "")
            v, err = rv.load(rv.arch, ref.get("path"))
            if not mt or err:
                p.append(f"{sid_}: revision log version {ref.get('path')} unreadable ({err})")
                continue
            key = (mt.group(1), mt.group(2))
            if key in seen_logs:
                p.append(f"{sid_}: two versions of the {key[0]} {key[1]} log written by one snapshot")
            seen_logs.add(key)
            recs = v.get("records", [])
            before = latest.get(key, [])
            if recs[:len(before)] != before:
                p.append(f"{sid_}: {ref['path']} does not extend the newest version before it, {latest_ref.get(key)} ({len(before)} records) (10, 12.6)")
            tail = recs[len(before):]
            if not tail:
                p.append(f"{sid_}: {ref['path']} adds no record to the version before it")
            if is_time(s.get("created_at")) and str(et_date(parse_utc(s["created_at"])).year) != key[1]:
                p.append(f"{sid_}: {ref['path']} is the log of {key[1]}, the ET year of detection is {et_date(parse_utc(s['created_at'])).year} (10)")
            for r in tail:
                if r.get("snapshot") != sid_ or r.get("detected_at") != s.get("created_at"):
                    p.append(f"{sid_}: new record for {key[0]} {r.get('period')} {r.get('field')} names snapshot {r.get('snapshot')} and detected_at {r.get('detected_at')}; expected this snapshot and the run's now {s.get('created_at')} (10)")
                if run.get("trigger") == "review":
                    want = f"approved in review run {run.get('id')} on {et_date(parse_utc(s['created_at'])).isoformat()}"
                    if r.get("kind") != "approved-hold" or r.get("basis") != want:
                        p.append(f"{sid_}: record for {key[0]} {r.get('period')} {r.get('field')} has kind {r.get('kind')!r}, basis {r.get('basis')!r}; a review run gives approved-hold and {want!r} (10, 17.5)")
                elif r.get("kind") != "expected":
                    p.append(f"{sid_}: record for {key[0]} {r.get('period')} {r.get('field')} has kind {r.get('kind')!r} in a run with trigger {run.get('trigger')!r} (10: expected)")
            latest[key], latest_ref[key] = recs, ref["path"]
            new.setdefault(key[0], []).extend(tail)
        for series_id in sorted(ctx.reg_ids | set(new)):
            ser = st.series.get(series_id)
            got = [rx_record_key(r) for r in new.get(series_id, [])]
            n_records += len(got)
            old_state = (base or {}).get("series", {}).get(series_id, {})
            new_state = s.get("series", {}).get(series_id, {})
            exp = []
            if ser is not None and old_state.get("objects") and old_state.get("objects") != new_state.get("objects"):
                exp = rx_changes(rx_obs(ctx, old_state), rx_obs(ctx, new_state))
                # reading: a moved change point may also be logged as one `effective` record (10 lists
                # the field); then it stands for the removed and the inserted period records.
                if ser["frequency"] == "change-point":
                    for r in new.get(series_id, []):
                        if r.get("field") != "effective":
                            continue
                        try:
                            a, b = json.loads(r.get("before") or "null"), json.loads(r.get("after") or "null")
                        except ValueError:
                            continue
                        rm = [e for e in exp if e[1] == "period" and e[0] == a and e[3] is None]
                        ins = [e for e in exp if e[1] == "period" and e[0] == b and e[2] is None]
                        if rm and ins:
                            exp.remove(rm[0])
                            exp.remove(ins[0])
                            exp.append(rx_record_key(r))
            n_changes += len(exp)
            for key in sorted(set(exp) | set(got), key=repr):
                ne, ng = exp.count(key), got.count(key)
                if ne and not ng:
                    p.append(f"{sid_} {series_id}: change to {key[0]} {key[1]} ({key[2]!r:.80} to {key[3]!r:.80}) against {base_id} has no record (12.6)")
                elif ng and not ne:
                    p.append(f"{sid_} {series_id}: record {key[0]} {key[1]} ({key[2]!r:.80} to {key[3]!r:.80}) matches no change against {base_id} (12.6)")
                elif ne != ng:
                    p.append(f"{sid_} {series_id}: {ng} records for the change to {key[0]} {key[1]}, expected exactly one (12.6)")
    check("T60 across consecutive snapshots every changed member, removed period and period inserted on or before the last published one has exactly one record in the log versions that snapshot wrote, and no record lacks a change; each version extends the newest one; kind and basis follow the trigger (10, 12.6, 17.5)", p,
          f"{n_changes} changes, {n_records} records, {len(ctx.order)} snapshots")
    check("T83 every rollback keeps the whole record: for each series whose observations differ between the two states its manifest names a log version that is the newest one plus exactly the rollback records of the difference (snapshot the target, basis 'rolled back to snapshot <to> in run <run id> on <ET date>'), and it drops no revision log (10, 17.5)", p_rb,
          f"{n_rb} rollback(s), {n_rb_records} rollback records")


# --- T78 to T80: the safeguards of 11.4 on what was published ---


def rc_safeguards(ctx):
    st, p_begin, p_missing, p_cal, seen = ctx.st, [], [], [], set()
    for sid_ in ctx.order:
        for series_id, state in sorted(ctx.snaps[sid_].get("series", {}).items()):
            ser = st.series.get(series_id)
            key = (series_id, tuple(r.get("sha256") for r in state.get("objects", [])))
            if ser is None or not state.get("objects") or key in seen:
                continue
            seen.add(key)
            obs = rx_obs(ctx, state)
            w = f"{series_id} (first in snapshot {sid_})"
            if ser["frequency"] == "change-point":
                first = obs[0].get("effective") if obs else None
            else:
                first = next((o.get("period") for o in obs if o.get("value") is not None), None)
            if first != ser["earliest"]:
                p_begin.append(f"{w}: the first period with a value is {first}, the registry earliest is {ser['earliest']} (a history cut short never publishes)")
            keys = [observation_key(o) for o in obs]
            have = set(keys)
            if ser["frequency"] == "business-day":
                gaps, inc = {g["period"] for g in ser.get("known_gaps", [])}, ki_periods(ser)
                try:
                    days = list(weekdays_between(parse_date(keys[0]), parse_date(keys[-1])))
                    missing = [d.isoformat() for d in days if d.isoformat() not in have and d.isoformat() not in gaps and is_business_day(d)]
                except ValueError as exc:
                    p_missing.append(f"{w}: {exc}")
                    continue
                if missing:
                    p_missing.append(f"{w}: no observation and no known_gaps entry for {len(missing)} business day(s): {', '.join(missing[:6])}{' ...' if len(missing) > 6 else ''}")
                for k in keys:
                    d = parse_date(k)
                    if k in inc:
                        continue
                    if d.weekday() >= 5:
                        p_cal.append(f"{w}: {k} is a {d.strftime('%A')} and not a known inconsistency")
                    elif not is_business_day(d):
                        p_cal.append(f"{w}: {k} is a Federal Reserve holiday and not a known inconsistency")
                for k in sorted(have & gaps):
                    p_cal.append(f"{w}: {k} is listed in known_gaps but has an observation")
            elif ser["frequency"] == "month":
                missing = []
                for a, b in zip(keys, keys[1:]):
                    x = month_add(a, 1)
                    while x < b and len(missing) < 12:
                        missing.append(x)
                        x = month_add(x, 1)
                if missing:
                    p_missing.append(f"{w}: months without an observation: {', '.join(missing[:6])}")
    detail = f"{len(seen)} distinct series states"
    check("T78 expected beginning: in every published state the first period with a value, or the first change point, is the series' registry earliest (11.4, appendix B)", p_begin, detail)
    check("T79 missing periods: every New York Fed business day from the first period to the last has an observation or is listed in known_gaps; a monthly series has every month (11.4, 2.3)", p_missing, detail)
    check("T80 source calendar: no period of a business-day series falls on a Federal Reserve holiday or a weekend unless it is a known inconsistency, and no known_gaps date has an observation (11.4, 3)", p_cal, detail)


# --- Locks (v0.5, v0.6: 5, 8, 9, 11.5, 17.3, 17.5, 17.6): T85, T86, T105 to T112, T115 ---
#
# v0.6 (appendix E1, E2, E3, E5): a lock is identified by its series, origin and candidate hash
# (11.5); a series may carry several, each lifting by its own rule. Lock sets are dicts from
# (series, origin, candidate_sha256) to the snapshot frozen entry form, in the order listed.

SECTION10_FIELDS = ("value", "lower", "upper", "kind", "effective", "flags", "missing", "released", "starts_before_data", "period")
RX_ROLLBACK_PATH = re.compile(r"(\d{8}T\d{6}Z)\.json", re.ASCII)


def rx_bare(o):
    """17.3: comparison ignores released."""
    return {k: v for k, v in o.items() if k != "released"} if isinstance(o, dict) else o


def lock_key(e):
    """11.5 (v0.6): a lock is identified by its series, origin and candidate hash."""
    return (e.get("series"), e.get("origin"), e.get("candidate_sha256")) if isinstance(e, dict) else (None, None, None)


def lock_series(locks):
    """The locked series of a lock set (a series is locked while any of its locks stands)."""
    return {k[0] for k in locks}


def lock_shas(locks):
    """Series id to the set of its locks' candidate hashes."""
    out = {}
    for k in locks:
        out.setdefault(k[0], set()).add(k[2])
    return out


def locks_of_series(locks, sid):
    return [e for k, e in locks.items() if k[0] == sid]


def lock_changes(published, locked, origin=None):
    """11.5 (v0.6): the locked changes, every member in which the locked candidate differs from
    the published observations at the time of locking, as sorted (period, field) pairs in the
    forms of section 10. Every difference counts, for both origins, new periods included (E1):
    a period the locked candidate has and the published observations lack is a `period` change.
    `origin` is kept for the callers; v0.6 no longer tells the origins apart here."""
    out = {(k, f) for k, f, _, _ in rx_changes(published, locked)}
    pub = {observation_key(o) for o in published if isinstance(o, dict)}
    out |= {(observation_key(o), "period") for o in locked if isinstance(o, dict) and observation_key(o) not in pub}
    return sorted(out, key=lambda c: (str(c[0]), str(c[1])))


def lock_carries(cand_map, lock_map, period, field):
    """11.5: a candidate carries a locked change when its member at that period and field
    equals the locked candidate's; for a period the locked candidate lacks, when the candidate
    lacks it too. reading: for a `period` change on a period the locked candidate has, the
    candidate carries it when it has that period with the same observation (released ignored)."""
    c, lk = cand_map.get(period), lock_map.get(period)
    if lk is None:
        return c is None
    if c is None:
        return False
    if field == "period":
        return json_equal(rx_bare(c), rx_bare(lk))
    if field.startswith("extra."):
        ce = c.get("extra") if isinstance(c.get("extra"), dict) else {}
        le = lk.get("extra") if isinstance(lk.get("extra"), dict) else {}
        return rx_member_form(field, ce.get(field[6:], _ABSENT)) == rx_member_form(field, le.get(field[6:], _ABSENT))
    cv, lv = c.get(field, _ABSENT), lk.get(field, _ABSENT)
    if cv is _ABSENT or lv is _ABSENT:
        return cv is lv
    return json_equal(cv, lv)


def lock_carried(candidate, locked, changes):
    cm = {observation_key(o): o for o in candidate if isinstance(o, dict)}
    lm = {observation_key(o): o for o in locked if isinstance(o, dict)}
    return [c for c in changes if lock_carries(cm, lm, c[0], c[1])]


def lock_stands(origin, candidate, locked, changes, start=None):
    """11.5, 5 (v0.6): whether a lock is still in force after a collecting run that requested its
    series and received a valid response. A rolled-back lock always stands (only a clear lifts
    it). A rejected lock stands when a locked change lies before the window's first period
    `start` (a windowed run, E3), or when the candidate carries any of its locked changes; it is
    lifted only when the candidate carries none of them."""
    if origin != "rejected":
        return True
    if start is not None and any(str(c[0]) < start for c in changes):
        return True
    return bool(lock_carried(candidate, locked, changes))


def series_after_lifts(stands_by_lock):
    """11.5 (v0.6): `stands_by_lock` maps each lock of one series to whether it stands after the
    run. The series stays locked while any stands; only when none stands is the candidate
    classified afresh. Returns 'locked' or 'classify'."""
    return "locked" if any(stands_by_lock.values()) else "classify"


def refusal_rule(decision, series, sha, reviewer, permission, checked_at, now, held, locks, perms):
    """17.5 (v0.5, v0.6): the first rule that refuses a review request, or None. `held` maps a
    series to its held candidate's hash; `locks` maps a series to the set of its locks'
    candidate hashes (v0.6: a series may carry several locks, and a clear names one by its
    hash). An empty reason refuses by missing-text but is not kept, so the caller allows
    missing-text where nothing else fails (T95)."""
    fails = []
    if decision == "clear":
        order = CLEAR_REFUSAL_RULES
        if series not in locks:
            fails.append("not-locked")
        if sha not in (locks.get(series) or ()):
            fails.append("stale-candidate")
    else:
        order = REFUSAL_RULES
        if series not in held:
            fails.append("not-held")
        if sha != held.get(series):
            fails.append("stale-candidate")
        if decision not in ("approve", "reject"):
            fails.append("bad-decision")
        if series in locks:
            fails.append("locked")
    if not is_str(reviewer):
        fails.append("missing-text")
    if permission not in perms:
        fails.append("permission")
    if not (is_time(checked_at) and is_time(now) and 0 <= (parse_utc(now) - parse_utc(checked_at)).total_seconds() <= PERMISSION_WINDOW_SECONDS):
        fails.append("permission-time")
    if rx_automation_login(reviewer):
        fails.append("automation")
    return (min(fails, key=order.index) if fails else None), order


def rx_frozen(snapshot):
    """A snapshot's frozen list as a lock set: (series, origin, sha) to its entry (v0.6)."""
    out = {}
    for e in (snapshot or {}).get("frozen", []) or []:
        if isinstance(e, dict):
            out.setdefault(lock_key(e), e)
    return out


def rx_rollback_record(ctx, m):
    """17.5 (v0.6): the rollback record of a rollback manifest, archive/rollbacks/<at as
    YYYYMMDDTHHMMSSZ>.json, as (record or None, error or None, relative path)."""
    rb = (m or {}).get("rollback") if isinstance(m, dict) else None
    if not isinstance(rb, dict) or not is_time(rb.get("at")):
        return None, "the manifest's rollback has no time", None
    f = snapshot_id_of(parse_utc(rb["at"])) + ".json"
    v, err = ctx.rv.load(ctx.rv.rollbacks, f)
    if err:
        return None, err, f
    if not isinstance(v, dict) or not isinstance(v.get("locks"), list):
        return None, "not an object with a locks list", f
    return v, None, f


def rx_rollback_expected(ctx, m, before):
    """17.5 (v0.6), computed by this checker from the archive alone for a rollback manifest `m`
    with `before` the locks in force under the manifest it replaced:
      own: a rolled-back lock for each series whose observations differ between rollback.from
           and the target, the withdrawn observations as its candidate, its locked changes;
      kept: every rejection lock in force before the rollback (a rollback never undoes a
           person's rejection, including one decided after the target);
      required: own and kept, less the locks the target snapshot's frozen already lists;
      tolerated: rolled-back locks in force before the rollback that the target does not list.
    reading: the text keeps every rejection lock and says nothing of an earlier rollback's locks
    that the target does not carry; a record may list them or not (see the report)."""
    rb = m.get("rollback") or {}
    frm, to = ctx.snaps.get(rb.get("from")), ctx.snaps.get(rb.get("to"))
    order = [s["id"] for s in ctx.st.registry.get("series", [])]
    own = {}
    if frm is not None and to is not None:
        for sid in order:
            a = rx_obs(ctx, (frm.get("series") or {}).get(sid) or {})
            b = rx_obs(ctx, (to.get("series") or {}).get(sid) or {})
            if canon_bytes(a) != canon_bytes(b):
                e = {"series": sid, "origin": "rolled-back", "candidate_sha256": sha256_hex(canon_bytes(a)), "frozen_at": rb.get("at"),
                     "reason": rb.get("reason"), "locked_changes": [{"period": x, "field": y} for x, y in lock_changes(b, a)]}
                own[lock_key(e)] = e
    kept, required, tolerated = rollback_lock_sets(own, before, rx_frozen(to))
    return own, kept, required, tolerated


def rollback_lock_sets(own, before, target):
    """17.5 (v0.6), the pure part of rx_rollback_expected (C5 tests it): from the rollback's own
    locks, the locks in force before it and the target snapshot's frozen, the kept rejection
    locks, the locks its record must list, and those it may list."""
    kept = {k: e for k, e in before.items() if k[1] == "rejected"}
    required = {}
    for k, e in list(own.items()) + list(kept.items()):
        if k not in target:
            required.setdefault(k, e)
    tolerated = {k: e for k, e in before.items() if k[1] == "rolled-back" and k not in target and k not in required}
    return kept, required, tolerated


def rx_lock_history(ctx):
    """(manifests in time order as (name, manifest), the lock set in force under each, the
    index of the first manifest under which each lock is in force, and per manifest how the
    rollback locks were read). 11.5 (v0.6): the locks in force are the frozen list of the
    snapshot the manifest names plus, for a rollback manifest, the locks of its rollback
    record. A rollback manifest without a readable record (a root of an older pipeline) has its
    locks derived from rollback.locked as v0.5 did, so the other checks still run; T115 fails."""
    if getattr(ctx, "lock_history", None) is None:
        ms = [(name, m) for name, m, err in ctx.arch_manifests if not err and isinstance(m, dict)]
        ls, info, prev = [], [], {}
        for name, m in ms:
            locks = dict(rx_frozen(ctx.snaps.get((m.get("snapshot") or {}).get("id"))))
            rb = m.get("rollback")
            how = None
            if isinstance(rb, dict):
                rec, err, f = rx_rollback_record(ctx, m)
                if rec is not None:
                    how = ("record", f)
                    for x in rec["locks"]:
                        if not isinstance(x, dict):
                            continue
                        k = lock_key(x)
                        was = prev.get(k) or {}
                        e = {"series": x.get("series"), "candidate_sha256": x.get("candidate_sha256"), "origin": x.get("origin"),
                             # reading: a kept lock keeps its frozen_at and reason; a rollback's own lock has the rollback's
                             "frozen_at": was.get("frozen_at", rb.get("at") if x.get("origin") == "rolled-back" else None),
                             "reason": was.get("reason", rb.get("reason") if x.get("origin") == "rolled-back" else None),
                             "locked_changes": x.get("locked_changes")}
                        locks.setdefault(k, e)
                else:
                    how = ("derived from rollback.locked", err)
                    frm = ctx.snaps.get(rb.get("from"))
                    for sid in rb.get("locked") or []:
                        if not isinstance(sid, str):
                            continue
                        obs = rx_obs(ctx, (((frm or {}).get("series") or {}).get(sid)) or {})
                        e = {"series": sid, "candidate_sha256": sha256_hex(canon_bytes(obs)), "origin": "rolled-back", "frozen_at": rb.get("at"), "reason": rb.get("reason")}
                        locks.setdefault(lock_key(e), e)
            ls.append(locks)
            info.append(how)
            prev = locks
        first = {}
        for i, locks in enumerate(ls):
            for k in locks:
                first.setdefault(k, i)
        ctx.lock_history = (ms, ls, first, info)
    return ctx.lock_history


def rx_locks_of(ctx, m):
    """11.5: the lock set in force under a manifest (an archived one, or the live one)."""
    if not isinstance(m, dict):
        return {}
    ms, ls, _, _ = rx_lock_history(ctx)
    for i, (_, x) in enumerate(ms):
        if x is m:
            return ls[i]
    sid_ = (m.get("snapshot") or {}).get("id")
    for i, (_, x) in enumerate(ms):
        if x.get("generated_at") == m.get("generated_at") and (x.get("snapshot") or {}).get("id") == sid_:
            return ls[i]
    return dict(rx_frozen(ctx.snaps.get(sid_)))


def rx_locks_at(ctx, t, inclusive=True):
    _, m = rx_manifest_at(ctx, t, inclusive)
    return rx_locks_of(ctx, m)


def rx_lock_candidate(ctx, sid, sha):
    v, err = ctx.rv.load(ctx.rv.holds, f"{sid}/{str(sha)[:16]}.json")
    return v if not err and isinstance(v, list) else None


def rx_lock_detail(ctx, sid, entry):
    """(published observations at the time of locking, locked candidate or None, locked changes
    recomputed by this checker or None). The time of locking is the first manifest under which
    the lock (series, origin, hash) is in force: a reject's review manifest (the published data
    is unchanged by a reject) or a rollback manifest (the target's data)."""
    ms, _, first, _ = rx_lock_history(ctx)
    i = first.get(lock_key(entry) if entry.get("series") else (sid, entry.get("origin"), entry.get("candidate_sha256")))
    m = ms[i][1] if i is not None else None
    s = ctx.snaps.get(((m or {}).get("snapshot") or {}).get("id")) or {}
    published = rx_obs(ctx, (s.get("series") or {}).get(sid) or {})
    locked = rx_lock_candidate(ctx, sid, entry.get("candidate_sha256"))
    return published, locked, (lock_changes(published, locked) if locked is not None else None)


def rx_legacy(ctx, t):
    """21.1 (v0.7, F10): whether a manifest, snapshot or run made at time t is up to and including
    the promoted dataset (time not after the promoted snapshot's), so that exactly three rules are
    read as v0.6 wrote them (T46, T55, T116). The boundary comes from archive/state/accepted.json
    of a working root (the state mode composes one from the store); without it, never."""
    lu = getattr(ctx, "legacy_until", None)
    return lu is not None and isinstance(t, str) and t <= lu


def rx_legacy_registry_hash(ctx):
    """The canonical hash of the committed registry with `conventions` set to v0.6: the registry
    a v0.6 run used when v0.7 changed nothing else in it (appendix F9 changes only conventions)."""
    return registry_versions(ctx.st)["v0.6"][0]  # v0.8: the v0.6 registry is derived by I7 (22.9)


def rx_full_plan(ctx):
    """17.3 (v0.7): for every collecting run record, per request group, whether the weekly full
    fetch was due and whether the window was full (C8, full_fetch_sim). A group's fetch failed
    when a series of it failed (a fetch failure carries every series of the group forward), and
    was invalid as a whole when every series of it was invalid (a format failure, 11.3); a
    per-series invalid leaves the fetch successful. Returns {"runs": {run id: {group: row}},
    "last": {group: datetime}, "groups": [...]}."""
    if getattr(ctx, "full_plan", None) is not None:
        return ctx.full_plan
    st = ctx.st
    grp = request_group_of(st)
    groups = sorted(set(grp.values()), key=[s["id"] for s in st.registry.get("series", [])].index)
    runs, ids = [], []
    for rec in rx_records_in_time(ctx):
        if rec.get("trigger") not in ("schedule", "manual") or not is_time(rec.get("started_at")):
            continue
        before = rx_state_at(ctx, rec["started_at"], inclusive=False) or {}
        req = requested_groups(st, rec)
        outcomes = rec.get("series") or {}
        row = {}
        for g in groups:
            members = [s for s in st.series if grp[s] == g]
            oc = [outcomes.get(s) for s in members]
            result = "failed" if "failed" in oc else ("invalid" if oc and all(x == "invalid" for x in oc) else ("ok" if g in req else None))
            row[g] = {"requested": g in req, "h6": any(st.series[s]["frequency"] == "month" for s in members),
                      "unpublished": any(not ((before.get("series") or {}).get(s) or {}).get("objects") for s in members), "result": result}
        runs.append({"now": parse_utc(rec["started_at"]), "legacy": rx_legacy(ctx, rec["started_at"]), "groups": row})
        ids.append(rec.get("id"))
    # 21.1 (v0.7): the full fetches of runs before the boundary count when the collector.json of that
    # time carried them (the v0.7 form). The state mode knows it from the Stage B folder's collector.json
    # (ctx.legacy_ff); a working root alone shows it when its full_fetches still holds a time not after the boundary.
    record_legacy = getattr(ctx, "legacy_ff", None)
    if record_legacy is None:
        doc, err = ctx.rv.load(ctx.rv.state, "collector.json")
        ff = doc.get("full_fetches") if not err and isinstance(doc, dict) else None
        record_legacy = isinstance(ff, dict) and any(isinstance(v, str) and rx_legacy(ctx, v) for v in ff.values())
    pv, lv = full_fetch_sim(runs, record_legacy)
    _, lw = full_fetch_sim(runs, True)
    ctx.full_plan = {"runs": {rid: {g: pv[i][g] for g in groups} for i, rid in enumerate(ids)}, "last": lv, "last_with_legacy": lw,
                     "record_legacy": record_legacy, "groups": groups}
    return ctx.full_plan


def rx_window_start(ctx, rec, sid):
    """17.3: the first period of the window a collecting run requested for the group of `sid`,
    as an ISO date, or None for a full request (a group with an unpublished series, H.6, or a
    Sunday ET run before the group's first successful full fetch that day, v0.7)."""
    st = ctx.st
    if not is_time(rec.get("started_at")):
        return None
    grp = request_group_of(st)
    row = rx_full_plan(ctx)["runs"].get(rec.get("id"), {}).get(grp[sid])
    if row is not None and row["full"]:
        return None
    if row is None:
        members = [s for s in st.series if grp[s] == grp[sid]]
        before = rx_state_at(ctx, rec["started_at"], inclusive=False) or {}
        if any(st.series[s]["frequency"] == "month" for s in members) or any(not ((before.get("series") or {}).get(s) or {}).get("objects") for s in members):
            return None
    today = et_date(parse_utc(rec["started_at"]))
    return (today - dt.timedelta(days=59)).isoformat()


def rx_decisions(ctx):
    doc, _ = ctx.rv.load(ctx.rv.state, "review-queue.json")
    ds = doc.get("decisions") if isinstance(doc, dict) else None
    return [d for d in ds if isinstance(d, dict)] if isinstance(ds, list) else []


def rx_refusals(ctx):
    doc, _ = ctx.rv.load(ctx.rv.state, "review-queue.json")
    rs = doc.get("refusals") if isinstance(doc, dict) else None
    return [r for r in rs if isinstance(r, dict)] if isinstance(rs, list) else []


def rx_run_records(ctx):
    """Run id to its record from archive/state/run-records/ (17.1)."""
    if getattr(ctx, "run_records", None) is None:
        ctx.run_records = {}
        for f in ctx.rv.files(ctx.rv.state):
            if f.startswith("run-records/"):
                v, err = ctx.rv.load(ctx.rv.state, f)
                if not err and isinstance(v, dict):
                    ctx.run_records[v.get("id")] = v
    return ctx.run_records


def rx_records_in_time(ctx):
    return sorted(rx_run_records(ctx).values(), key=lambda v: (str(v.get("started_at")), str(v.get("id"))))


def rx_policy_permissions(ctx):
    return list(((ctx.st.registry.get("family_policy") or {}).get("review") or {}).get("permissions") or [])


def rx_automation_login(login):
    """11.5: a login that ends in [bot], or is github-actions, is refused. reading: GitHub
    logins are case-insensitive, so the comparison ignores case."""
    return isinstance(login, str) and (login.lower().endswith("[bot]") or login.lower() == "github-actions")


def _k16(k):
    return f"{k[0]} {k[1]} {str(k[2])[:16]}"


def rc_locks(ctx):
    """T85 (transitions), T105 (nothing published while locked), T106 (locked candidates kept),
    T107 (rollback locks), T110 (lock list changes are significant), T111 (locks survive a
    restore), T115 (rollback records), all per lock (series, origin, hash) as v0.6 gives."""
    rv = ctx.rv
    ms, ls, first, info = rx_lock_history(ctx)
    decisions, recs = rx_decisions(ctx), rx_run_records(ctx)
    p85, p105, p106, p107, p110, p111, p115 = [], [], [], [], [], [], []
    n_add, n_keep, n_lift, n_auto, n_multi = 0, 0, 0, 0, 0
    for i, (name, m) in enumerate(ms):
        locks, prev = ls[i], (ls[i - 1] if i else {})
        for k, e in locks.items():
            if k[0] not in ctx.reg_ids:
                p85.append(f"{name}: a lock on {k[0]!r}, which is not a registered series")
            if k[1] not in LOCK_ORIGINS:
                p85.append(f"{name} {k[0]}: lock origin {k[1]!r}; 11.5 names rejected and rolled-back")
        if len(lock_series(locks)) < len(locks):
            n_multi += 1
        if m.get("rollback") is not None:
            continue  # T107, T115; the target's locks are restored as they were
        s = ctx.snaps.get((m.get("snapshot") or {}).get("id"))
        base = ctx.snaps.get((ms[i - 1][1].get("snapshot") or {}).get("id")) if i else None
        if s is None or s.get("created_at") != m.get("generated_at") or base is None:
            if set(locks) != set(prev):
                p85.append(f"{name}: the locks change ({sorted(map(_k16, prev))} to {sorted(map(_k16, locks))}) in a manifest that no snapshot run wrote")
            continue
        run = s.get("run") or {}
        trig, rec = run.get("trigger"), recs.get(run.get("id")) or {}
        outcomes = rec.get("series") or {}
        collecting = trig in ("schedule", "manual")
        held_before = {h.get("series"): (h.get("candidate") or {}).get("sha256") for h in base.get("holds", [])}
        held_after = {h.get("series"): (h.get("candidate") or {}).get("sha256") for h in s.get("holds", [])}
        for k in sorted(set(prev) | set(locks), key=lambda x: tuple(map(str, x))):
            a, b = prev.get(k), locks.get(k)
            sid = k[0]
            w = f"{s['id']} {_k16(k)}"
            if a is not None and b is not None:
                n_keep += 1
                diff = [f for f in ("frozen_at", "reason") if a.get(f) != b.get(f)]
                if diff:
                    p85.append(f"{w}: the lock changed while in force ({', '.join(f'{f} {a.get(f)!r} to {b.get(f)!r}' for f in diff)}); every snapshot carries a lock forward as it is (11.5, 17.5)")
                if collecting and k[1] == "rejected" and outcomes.get(sid) == "unchanged":
                    _, locked, changes = rx_lock_detail(ctx, sid, b)
                    start = rx_window_start(ctx, rec, sid)
                    if changes and not (start is not None and any(str(c[0]) < start for c in changes)):
                        p85.append(f"{w}: the rejected lock stays although the candidate equals the published observations, carries none of its {len(changes)} locked change(s), and the request covered all of them; 11.5 lifts it then")
            elif b is not None:
                n_add += 1
                if k[1] != "rejected":
                    p85.append(f"{w}: a lock of origin {k[1]!r} appears in a snapshot without being in force under the manifest before it; only a rollback adds a rolled-back lock (17.5)")
                    continue
                d = [x for x in decisions if x.get("series") == sid and x.get("decision") == "reject" and x.get("run") == run.get("id")
                     and x.get("candidate_sha256") == k[2]]
                if trig != "review" or held_before.get(sid) != k[2] or not d:
                    p85.append(f"{w}: newly locked, but only the reject of its held candidate in a review run locks a series (trigger {trig}, held {str(held_before.get(sid))[:16]}, reject decisions of the run {len(d)}) (11.5)")
                elif b.get("reason") != d[0].get("reason"):
                    p85.append(f"{w}: lock reason {b.get('reason')!r} is not the reviewer's {d[0].get('reason')!r} (8)")
                if b.get("frozen_at") != s.get("created_at"):
                    p85.append(f"{w}: frozen_at {b.get('frozen_at')} is not the time of the rejecting run {s.get('created_at')} (8)")
            else:
                n_lift += 1
                if trig == "review":
                    d = [x for x in decisions if x.get("series") == sid and x.get("decision") == "clear" and x.get("run") == run.get("id") and x.get("candidate_sha256") == k[2]]
                    if not d:
                        p85.append(f"{w}: lifted in review run {run.get('id')} without a clear naming its candidate (11.5: a clear names the lock by its candidate hash)")
                    continue
                if k[1] != "rejected":
                    p85.append(f"{w}: a {k[1]} lock lifted by a {trig} run; it is lifted only by an authorized clear, whatever the source returns (11.5)")
                    continue
                n_auto += 1
                oc = outcomes.get(sid)
                if not collecting or oc in (None, "not-due", "failed", "invalid"):
                    p85.append(f"{w}: the rejected lock lifted in a {trig} run whose outcome for it is {oc!r}; only a collecting run whose candidate carries none of the locked changes lifts it (11.5)")
                    continue
                published, locked, changes = rx_lock_detail(ctx, sid, a)
                if locked is None:
                    p85.append(f"{w}: the locked candidate is not readable in archive/holds/, so the lift cannot be verified")
                    continue
                state = (s.get("series") or {}).get(sid) or {}
                if any(x[0] == sid for x in locks):
                    cand = rx_obs(ctx, state) if oc == "unchanged" else None  # still locked by another lock: the candidate is not kept
                elif state.get("status") == "held":
                    cand = rx_lock_candidate(ctx, sid, held_after.get(sid))
                else:
                    cand = rx_obs(ctx, state)
                if cand is not None:
                    carried = lock_carried(cand, locked, changes)
                    if carried:
                        p85.append(f"{w}: the rejected lock lifted although the candidate carries {len(carried)} of its locked changes, e.g. {carried[:3]} (11.5)")
        # Per series (11.5, 17.3): locked while any lock stands; classified afresh when the last lifts.
        for sid in sorted(lock_series(prev) | lock_series(locks), key=str):
            lb, la = [x for x in prev if x[0] == sid], [x for x in locks if x[0] == sid]
            w = f"{s['id']} {sid}"
            state = (s.get("series") or {}).get(sid) or {}
            old = (base.get("series") or {}).get(sid) or {}
            kept = [f for f in ("objects", "retrieved_at") if state.get(f) != old.get(f)]
            if la and lb:
                if kept:
                    p105.append(f"{w}: locked ({', '.join(sorted(str(x[1]) for x in la))}), yet its {kept} changed against {base['id']}; no run publishes anything of a locked series (11.5)")
                if state.get("status") not in ("carried-forward", "unchanged", "held"):
                    p105.append(f"{w}: locked, status {state.get('status')}; a locked series is carried forward (11.5, 17.3)")
                if state.get("status") == "held" and sid not in held_before:
                    p105.append(f"{w}: locked and newly held; a locked series whose candidate carries a locked change, or that has a rolled-back lock, is not held again (17.3)")
                if collecting:
                    oc = outcomes.get(sid)
                    if oc not in ("revised-unexpected", "unchanged", "not-due", "failed", "invalid"):
                        p105.append(f"{w}: locked, run outcome {oc!r}; 17.3 gives revised-unexpected or unchanged when it was requested")
                    if state.get("status") == "unchanged" and oc != "unchanged":
                        p105.append(f"{w}: locked with status unchanged but outcome {oc}")
            elif la:
                if state.get("status") != "carried-forward" or kept:
                    p105.append(f"{w}: rejected, so carried forward with its published data exactly kept; status {state.get('status')}, changed {kept} (11.5, 17.5)")
            else:
                if trig == "review":
                    if state.get("status") != "carried-forward" or [f for f in ("objects", "retrieved_at", "checked_at") if state.get(f) != old.get(f)]:
                        p85.append(f"{w}: cleared, so carried forward with nothing published in that run; status {state.get('status')} (11.5, 17.5)")
                elif state.get("status") not in ("refreshed", "unchanged", "held"):
                    p85.append(f"{w}: its last lock lifted, so the candidate is classified afresh: published, unchanged or held; status {state.get('status')} (11.5)")
    # T105: the frozen alert lasts exactly while the series is locked (11.5, 17.8)
    n_alert = 0
    for rec in rx_records_in_time(ctx):
        if rec.get("trigger") not in ("schedule", "manual") or rec.get("outcome") not in ("published", "no-change", "nothing-due") or not is_time(rec.get("ended_at")):
            continue
        n_alert += 1
        after = rx_locks_at(ctx, rec["ended_at"], True)
        alerts = {str(k) for k in rec.get("alerts") or []}
        for sid in sorted(lock_series(after), key=str):
            if f"frozen:{sid}" not in alerts:
                p105.append(f"run {rec.get('id')}: {sid} is locked ({', '.join(sorted(e.get('origin') for e in locks_of_series(after, sid)))}) after the run but the warning frozen:{sid} is not among its alerts (11.5: it lasts)")
        for k in sorted(alerts):
            if k.startswith("frozen:") and k[7:] not in lock_series(after):
                p105.append(f"run {rec.get('id')}: alert {k} although {k[7:]} is not locked after the run")
        if rec.get("outcome") == "no-change" and is_time(rec.get("started_at")):
            # 11.5, 17.3: a candidate equal to the published observations carries none of a rejected
            # lock's changes, so the lock lifts and, the locks changing, a snapshot is written;
            # v0.6 (5): unless the run is windowed and a locked change lies before the window.
            before = rx_locks_at(ctx, rec["started_at"], False)
            for k, e in sorted(before.items(), key=lambda kv: tuple(map(str, kv[0]))):
                if k[1] == "rejected" and (rec.get("series") or {}).get(k[0]) == "unchanged":
                    _, _, changes = rx_lock_detail(ctx, k[0], e)
                    start = rx_window_start(ctx, rec, k[0])
                    if changes and not (start is not None and any(str(c[0]) < start for c in changes)):
                        p85.append(f"run {rec.get('id')}: {k[0]}'s candidate equals the published observations (outcome unchanged), so its rejected lock {str(k[2])[:16]} lifts and a snapshot is written; the run wrote none (11.5, 17.3)")
    # T106: every locked candidate is kept in archive/holds/ (11.5, 17.1, 17.5)
    for k, i in sorted(first.items(), key=lambda kv: tuple(map(str, kv[0]))):
        name, m = ms[i]
        sid, origin, sha = k
        f = f"{sid}/{str(sha)[:16]}.json"
        data = rv.read(rv.holds, f)
        if data is None:
            p106.append(f"{sid} locked candidate {str(sha)[:16]} ({origin}, in force from {name}) is not in archive/holds/ (11.5: locked candidates are never pruned)")
            continue
        if sha256_hex(data) != sha:
            p106.append(f"archive/holds/{f} has sha256 {sha256_hex(data)[:16]}, the lock names {str(sha)[:16]}")
        if origin == "rejected" and rx_first_held(ctx, sid, sha) is None:
            p106.append(f"{sid}: the rejected lock's candidate {str(sha)[:16]} was never held by a snapshot (11.5: the locked candidate is the rejected one)")
    # T107 (rollback.locked, statuses, withdrawn candidates, kept locks) and T115 (the rollback records)
    order = [s["id"] for s in ctx.st.registry.get("series", [])]
    origin_rank = {o: n for n, o in enumerate(LOCK_ORIGINS)}
    n_rb, n_tol, wanted_records = 0, 0, set()
    for i, (name, m) in enumerate(ms):
        rb = m.get("rollback")
        if rb is None:
            continue
        n_rb += 1
        frm, to = ctx.snaps.get((rb or {}).get("from")), ctx.snaps.get((rb or {}).get("to"))
        if not isinstance(rb, dict) or frm is None or to is None:
            p107.append(f"{name}: rollback {rb!r:.80} does not name two archived snapshots")
            continue
        before = ls[i - 1] if i else {}
        own, kept, required, tolerated = rx_rollback_expected(ctx, m, before)
        target = rx_frozen(to)
        target_series = lock_series(target)
        # T107: rollback.locked (9, 12.9): the series of the record's locks that the target does not lock, registry order.
        want_locked = [sid for sid in order if sid in lock_series(required) and sid not in target_series]
        if rb.get("locked") != want_locked:
            p107.append(f"{name}: rollback.locked {rb.get('locked')!r}; the series locked after the rollback that the target snapshot does not lock (its own: those differing between {frm['id']} and {to['id']}; kept rejection locks), in registry order, are {want_locked} (9, 12.9, 17.5)")
        if rb.get("at") != m.get("generated_at"):
            p107.append(f"{name}: rollback.at {rb.get('at')} is not the manifest's generated_at {m.get('generated_at')} (reading: the lock's frozen_at is the rollback run's time)")
        for k, e in own.items():
            sid = k[0]
            withdrawn = rx_obs(ctx, frm.get("series", {}).get(sid, {}))
            if rv.read(rv.holds, f"{sid}/{str(k[2])[:16]}.json") != canon_bytes(withdrawn):
                p107.append(f"{name} {sid}: the withdrawn observations of {frm['id']} are not stored as its locked candidate in archive/holds/ (17.5)")
            summ = (m.get("series") or {}).get(sid) or {}
            held = any(h.get("series") == sid for h in to.get("holds", []))
            ws = "held" if held else ("not-yet-published" if not (to.get("series", {}).get(sid) or {}).get("objects") else "frozen")
            if summ.get("status") != ws:
                p107.append(f"{name} {sid}: status {summ.get('status')}; a series the rollback locks is {ws} (9, 17.5: held stays held)")
        for k in target:
            if k not in ls[i]:
                p107.append(f"{name}: the target's lock {_k16(k)} is not in force after the rollback (17.5: restored as it was)")
        for k in kept:
            if k not in ls[i]:
                p107.append(f"{name}: the rejection lock {_k16(k)} in force before the rollback is not in force after it (17.5 v0.6: a rollback keeps every rejection lock, including those decided after its target)")
        for k in own:
            if k not in ls[i]:
                p107.append(f"{name}: the rollback's own lock {_k16(k)} is not in force after it (17.5: it locks every series it changes)")
        # T115: the rollback record (17.5 v0.6)
        rec, err, f = rx_rollback_record(ctx, m)
        if f:
            wanted_records.add(f)
        if rec is None:
            p115.append(f"{name}: no readable rollback record archive/rollbacks/{f} ({err}); 17.5 (v0.6) writes one with the rollback manifest")
            continue
        try:
            errs = schema_errors(rec, ctx.st.schemas["rollback"])
        except SchemaKeywordError as exc:
            errs = [f"validator cannot evaluate: {exc}"]
        p115 += [f"archive/rollbacks/{f}: {x} (rollback.schema.json)" for x in errs[:3]]
        if rec.get("schema") != SCHEMA_IDS["rollback"]:
            p115.append(f"archive/rollbacks/{f}: schema {rec.get('schema')!r}, 17.5 gives {SCHEMA_IDS['rollback']}")
        for fld in ("from", "to", "at", "reason"):
            if rec.get(fld) != rb.get(fld):
                p115.append(f"archive/rollbacks/{f}: {fld} {rec.get(fld)!r}, the rollback manifest {name} has {rb.get(fld)!r}")
        run_id = rx_rollback_run(ctx, rb.get("at"))
        if rec.get("run") != run_id or not (isinstance(rec.get("run"), str) and RX_RUN_ID.fullmatch(rec["run"])):
            p115.append(f"archive/rollbacks/{f}: run {rec.get('run')!r}, the rollback run recorded at {rb.get('at')} is {run_id!r} (17.2 form)")
        got = [lock_key(x) for x in rec["locks"] if isinstance(x, dict)]
        if len(set(got)) != len(got):
            p115.append(f"archive/rollbacks/{f}: a lock is listed twice")
        miss = [k for k in required if k not in got]
        extra = [k for k in got if k not in required and k not in tolerated]
        n_tol += sum(1 for k in got if k in tolerated)
        for k in miss:
            why = "its own lock" if k in own else "a rejection lock in force before it"
            p115.append(f"archive/rollbacks/{f}: lacks {_k16(k)}, {why} that the target's frozen does not list (17.5 v0.6)")
        for k in extra:
            why = "the target's frozen already lists it" if k in target else "it is neither the rollback's own lock nor a lock in force before it"
            p115.append(f"archive/rollbacks/{f}: lists {_k16(k)}, but {why} (17.5: each lock in force after the rollback that the target snapshot's frozen does not list)")
        ranks = [(order.index(k[0]) if k[0] in order else len(order), origin_rank.get(k[1], 9)) for k in got]
        if ranks != sorted(ranks):
            p115.append(f"archive/rollbacks/{f}: locks {[_k16(k) for k in got]} are not in registry order then origin (17.5)")
        for x in rec["locks"]:
            if not isinstance(x, dict):
                continue
            k = lock_key(x)
            pairs = [(c.get("period"), c.get("field")) if isinstance(c, dict) and set(c) == {"period", "field"} else None for c in (x.get("locked_changes") or [])]
            if None in pairs or not isinstance(x.get("locked_changes"), list):
                p115.append(f"archive/rollbacks/{f} {_k16(k)}: locked_changes are not a list of {{period, field}}")
                continue
            bad = sorted({fd for _, fd in pairs if not (isinstance(fd, str) and (fd in SECTION10_FIELDS or (fd.startswith("extra.") and len(fd) > 6)))}, key=str)
            if bad:
                p115.append(f"archive/rollbacks/{f} {_k16(k)}: locked_changes fields {bad} are not section 10 member names")
            if k in own:
                want = [(c["period"], c["field"]) for c in own[k]["locked_changes"]]
            elif k in before:
                want = rx_lock_detail(ctx, k[0], before[k])[2]
            else:
                continue
            if want is None:
                p115.append(f"archive/rollbacks/{f} {_k16(k)}: the locked candidate is not readable, so locked_changes cannot be recomputed")
            elif sorted(pairs, key=lambda c: tuple(map(str, c))) != sorted(want, key=lambda c: tuple(map(str, c))) or len(set(pairs)) != len(pairs):
                ms_, ex_ = sorted(set(want) - set(pairs)), sorted(set(pairs) - set(want))
                p115.append(f"archive/rollbacks/{f} {_k16(k)}: locked_changes differ from the {len(want)} recomputed: missing {ms_[:4]}, not a change {ex_[:4]} (11.5)")
        # the locks in force after the rollback are derived from the record (11.5 v0.6)
        derived = dict(target)
        for x in rec["locks"]:
            if isinstance(x, dict):
                derived.setdefault(lock_key(x), x)
        if set(derived) != set(ls[i]):
            p115.append(f"{name}: the locks in force under the rollback manifest are not the target's frozen plus the record's locks")
        rec_series = [sid for sid in order if sid in {k[0] for k in got} and sid not in target_series]
        if rb.get("locked") != rec_series:
            p115.append(f"{name}: rollback.locked {rb.get('locked')!r}, the series of the record's locks that the target does not lock are {rec_series} (12.9)")
    for f in rv.files(rv.rollbacks):
        if not RX_ROLLBACK_PATH.fullmatch(f):
            p115.append(f"archive/rollbacks/{f} is not <YYYYMMDDTHHMMSSZ>.json (17.5)")
        elif f not in wanted_records:
            p115.append(f"archive/rollbacks/{f} belongs to no archived rollback manifest (17.5: written with the rollback manifest)")
    # T110: a snapshot whose locks differ from the previous snapshot's is significant and kept (17.3, 17.6)
    sig = rx_significant(ctx)
    n_sig = 0
    for sid_ in ctx.order:
        s = ctx.snaps[sid_]
        if set(rx_frozen(s)) == set(rx_frozen(ctx.snaps.get(s.get("previous")))):
            continue
        n_sig += 1
        if sid_ not in sig:
            p110.append(f"{sid_}: its locks {sorted(map(_k16, rx_frozen(s)))} differ from its previous snapshot's, but it is not treated as significant")
        for path, (sha, nbytes) in sorted(rx_named_files(ctx, sid_).items(), key=lambda kv: str(kv[0])):
            data = rv.read(rv.live, path) if isinstance(path, str) else None
            if data is None or (sha is not None and sha256_hex(data) != sha):
                p110.append(f"{sid_}: live/{path} {'missing' if data is None else 'differs'}; a significant snapshot's files are never pruned (17.6)")
    # T111: the locks in force survive a restore (11.5, 17.5)
    n_restore = 0
    for rec in rx_records_in_time(ctx):
        if rec.get("trigger") != "restore" or not (is_time(rec.get("started_at")) and is_time(rec.get("ended_at"))):
            continue
        n_restore += 1
        before, after = rx_locks_at(ctx, rec["started_at"], False), rx_locks_at(ctx, rec["ended_at"], True)
        if set(before) != set(after):
            p111.append(f"restore {rec.get('id')}: locks before {sorted(map(_k16, before))}, after {sorted(map(_k16, after))}")
        nxt = next((x for x in rx_records_in_time(ctx) if str(x.get("started_at")) > rec["ended_at"] and x.get("outcome") == "published" and x.get("snapshot") in ctx.snaps), None)
        if nxt is not None:
            later = rx_locks_at(ctx, nxt["ended_at"], True) if is_time(nxt.get("ended_at")) else {}
            cleared = {(d.get("series"), d.get("candidate_sha256")) for d in decisions if d.get("decision") == "clear" and d.get("run") == nxt.get("id")}
            for k in sorted(after, key=lambda x: tuple(map(str, x))):
                if k[1] == "rolled-back" and k not in later and (k[0], k[2]) not in cleared:
                    p111.append(f"restore {rec.get('id')}: the rolled-back lock {_k16(k)} is gone after the next publishing run {nxt.get('id')} without a clear")
    check("T85 lock transitions recomputed per lock (series, origin, hash) from the published state (each snapshot's frozen plus, for a rollback manifest, its rollback record): a lock appears only by the reject of the held candidate in a review run (frozen_at the run's time, the reviewer's reason) or by a rollback; it is carried forward unchanged; a rejected lock is lifted without a person only in a collecting run whose candidate carries none of its locked changes and whose request covers them all (v0.6: new periods count, a locked change before the window keeps it); a series stays locked while any of its locks stands and is classified afresh only when the last lifts; a rolled-back lock is lifted only by a clear naming its hash (5, 8, 11.5, 17.3, 17.5)", p85,
          f"{len(ms)} manifests: {n_add} lock(s) added by a reject, {n_keep} kept, {n_lift} lifted ({n_auto} without a person); {n_multi} manifest(s) with a series under several locks")
    check("T105 while a series is locked (by any of its locks) no run publishes anything of it: objects and retrieved_at kept, carried forward (or unchanged, or held when the target held it), run outcome revised-unexpected or unchanged when requested, never held again; frozen:<series> among the alerts of every collecting run exactly while it is locked (11.5, 17.3, 17.8)", p105,
          f"{n_keep} kept lock state(s), {n_alert} run record(s)")
    check("T106 every locked candidate ever in force is in archive/holds/<series>/<16 hex>.json with its SHA-256, a rejected one having been held; none is pruned (11.5, 17.1, 17.5)", p106, f"{len(first)} lock(s)")
    check("T107 every rollback: rollback.locked is exactly the series locked after it that the target does not lock, in registry order; its own locks (each series whose observations differ, the withdrawn observations stored as the locked candidate) show frozen in its manifest (held stays held); the target's locks and every rejection lock in force before it stay in force (9, 11.5, 12.9, 17.5 v0.6)", p107, f"{n_rb} rollback(s)")
    check("T110 every snapshot whose locks differ from its previous snapshot's (a lock added or lifted) is significant and every file it names is in live/ (17.3, 17.6)", p110, f"{n_sig} such snapshot(s)")
    check("T111 the locks in force survive every restore: the same locks before and after, and the next publishing run keeps each rolled-back lock unless it clears it (11.5, 17.4, 17.5)", p111, f"{n_restore} restore(s)")
    check("T115 every rollback has its rollback record archive/rollbacks/<at as YYYYMMDDTHHMMSSZ>.json (schema rollback/1; nothing else in that folder): from, to, at, reason as the manifest, run the rollback run; locks exactly the locks in force after the rollback that the target's frozen does not list (its own rolled-back locks and the kept rejection locks), in registry order then origin, each with its locked changes recomputed; the locks in force under the rollback manifest are the target's frozen plus these, and rollback.locked their series the target does not lock (9, 11.5, 12.9, 17.5 v0.6)", p115,
          f"{n_rb} rollback(s), {len(rv.files(rv.rollbacks))} record(s)" + (f"; {n_tol} earlier rolled-back lock(s) kept, accepted (see the report)" if n_tol else ""))


def rc_withdrawals(ctx):
    p_wd, n_wd = [], 0
    decisions = rx_decisions(ctx)
    for sid_ in ctx.order:
        s = ctx.snaps[sid_]
        base_id = rx_base_id(ctx, sid_)
        base = ctx.snaps.get(base_id) or {}
        run = s.get("run") or {}
        holds_old = {h.get("series"): h for h in base.get("holds", [])}
        holds_new = {h.get("series"): h for h in s.get("holds", [])}
        if run.get("trigger") == "review":
            for series_id in [x for x in holds_old if x not in holds_new]:
                st_new = s.get("series", {}).get(series_id, {}).get("status")
                sha = (holds_old[series_id].get("candidate") or {}).get("sha256")
                want = "approve" if st_new == "refreshed" else "reject"
                if not any(x.get("series") == series_id and x.get("candidate_sha256") == sha and x.get("decision") == want and x.get("run") == run.get("id") for x in decisions):
                    p_wd.append(f"{sid_} {series_id}: the hold was closed by review run {run.get('id')} but review-queue.json has no {want} decision for candidate {str(sha)[:16]} in that run (11.5: every decision is kept)")
            continue
        for series_id in sorted(x for x in holds_old if x not in holds_new):
            # 11.5, 17.3: a hold closes without a person only when the candidate equals the published data.
            n_wd += 1
            state = s.get("series", {}).get(series_id, {})
            old = base.get("series", {}).get(series_id, {})
            sha = (holds_old[series_id].get("candidate") or {}).get("sha256")
            if state.get("status") != "unchanged" or state.get("objects") != old.get("objects"):
                p_wd.append(f"{sid_} {series_id}: its hold was closed by a {run.get('trigger')} run, which happens only when the source equals the published data: outcome unchanged, nothing overwritten; status {state.get('status')}, objects {'kept' if state.get('objects') == old.get('objects') else 'changed'} against {base_id} (11.5, 17.3)")
            if not any(x.get("series") == series_id and x.get("candidate_sha256") == sha and x.get("decision") == "withdrawn" and x.get("run") == run.get("id") for x in decisions):
                p_wd.append(f"{sid_} {series_id}: the hold on candidate {str(sha)[:16]} closed without a person but review-queue.json has no withdrawn decision of run {run.get('id')} (11.5)")
    for d in decisions:
        if d.get("decision") != "withdrawn":
            continue
        snap = next((x for x in ctx.snaps.values() if (x.get("run") or {}).get("id") == d.get("run")), None)
        base = ctx.snaps.get(rx_base_id(ctx, snap["id"])) if snap else None
        was = any(h.get("series") == d.get("series") and (h.get("candidate") or {}).get("sha256") == d.get("candidate_sha256") for h in (base or {}).get("holds", []))
        if snap is None or not was or any(h.get("series") == d.get("series") for h in snap.get("holds", [])):
            p_wd.append(f"withdrawn decision for {d.get('series')} candidate {str(d.get('candidate_sha256'))[:16]} in run {d.get('run')}: that run's snapshot does not close a hold on that candidate")
    check("T86 a hold closes only by a review decision or by automatic withdrawal on an exact match: the series is then unchanged with its objects kept and the decision withdrawn is recorded; every closing has its decision (11.5, 17.3)", p_wd,
          f"{n_wd} hold(s) closed without a person, {sum(1 for d in decisions if d.get('decision') == 'withdrawn')} withdrawn decision(s)")


# --- T81: review records (17.5) ---


def rc_reviews(ctx):
    rv, st = ctx.rv, ctx.st
    p, decisions, expected_files = [], rx_decisions(ctx), set()
    for i, d in enumerate(decisions):
        sid, sha, dec = d.get("series"), str(d.get("candidate_sha256")), d.get("decision")
        stamp = snapshot_id_of(parse_utc(d["decided_at"])) if is_time(d.get("decided_at")) else "?"
        rel = f"{sid}/{sha[:16]}-{dec}-{stamp}.json"  # 17.1 (v0.4): the decision time is in the name
        expected_files.add(rel)
        w = f"decisions[{i}] {sid} {dec}"
        if d.get("record") != "reviews/" + rel:
            p.append(f"{w}: record {d.get('record')!r} is not the review record's path under archive/, 'reviews/{rel}' (17.1, 17.5)")
        v, err = rv.load(rv.reviews, rel)
        if err or not isinstance(v, dict):
            p.append(f"{w}: review record archive/reviews/{rel} {err or 'is not an object'} (17.5: one per decision)")
            continue
        if v.get("schema") != SCHEMA_IDS["review"]:
            p.append(f"{w}: schema {v.get('schema')!r}, 17.5 gives {SCHEMA_IDS['review']}")
        for f in ("series", "candidate_sha256", "decision", "decided_at", "run", "reviewer", "reason", "affected_periods",
                  "reviewer_permission", "permission_checked_at", "publication"):
            if not json_equal(v.get(f, _ABSENT) if f in v else None, d.get(f)) or f not in v:
                p.append(f"{w}: review record {f} {v.get(f)!r}, the decision has {d.get(f)!r}")
        snap = next((x for x in ctx.snaps.values() if (x.get("run") or {}).get("id") == d.get("run")), None)
        base = ctx.snaps.get(rx_base_id(ctx, snap["id"])) if snap else None
        if dec == "clear":
            # 17.5 (v0.5): for clear, hold carries the lock's reason and frozen_at, and the changes
            # are measured against the lock's candidate. The lock is the one in force when the run started.
            # v0.6: the lock is named by its candidate hash among the series' locks.
            named = [e for e in locks_of_series(rx_locks_at(ctx, d["decided_at"], inclusive=False), sid) if e.get("candidate_sha256") == sha] if is_time(d.get("decided_at")) else []
            if not named:
                p.append(f"{w}: no lock on that candidate was in force when run {d.get('run')} started")
                continue
            lock = next((e for e in named if v.get("hold") == {"reason": e.get("reason"), "opened_at": e.get("frozen_at")}), named[0])
            hold = {"reason": lock.get("reason"), "opened_at": lock.get("frozen_at")}
        else:
            hold = next((h for h in (base or {}).get("holds", []) if h.get("series") == sid and (h.get("candidate") or {}).get("sha256") == sha), None)
        if hold is None:
            p.append(f"{w}: no hold on that candidate in the snapshot published before run {d.get('run')}")
            continue
        if base is None:
            p.append(f"{w}: the snapshot published before run {d.get('run')} is not in the archive")
            continue
        if v.get("hold") != {"reason": hold.get("reason"), "opened_at": hold.get("opened_at")}:
            p.append(f"{w}: hold {v.get('hold')}, the {'lock' if dec == 'clear' else 'hold'} gives reason {hold.get('reason')!r} opened_at {hold.get('opened_at')}")
        cand, cerr = rv.load(rv.holds, f"{sid}/{sha[:16]}.json")
        if cerr or not isinstance(cand, list):
            p.append(f"{w}: the held candidate archive/holds/{sid}/{sha[:16]}.json is not readable, so the proposed values are not kept")
            continue
        published = rx_obs(ctx, base.get("series", {}).get(sid, {}))
        exp = rx_changes(published, cand)
        old_keys = {observation_key(o) for o in published}
        appended = {observation_key(o): o for o in cand if observation_key(o) not in old_keys and observation_key(o) > max(old_keys, default="")}
        got = [(c.get("period"), c.get("field"), c.get("before"), c.get("after")) for c in v.get("changes", []) if isinstance(c, dict)]
        # reading: section 10 gives an appended period no record; a review record may list it or not.
        optional = {(k, "period", None, canon_text(o)) for k, o in appended.items()}
        for k in sorted(set(exp) | set(got), key=repr):
            ne, ng = exp.count(k), got.count(k)
            if ne != ng and not (k in optional and ng == 1):
                p.append(f"{w}: changes: {k[0]} {k[1]} ({k[2]!r:.60} to {k[3]!r:.60}) differs {ne} time(s) between the published observations and the candidate, the record lists it {ng} time(s)")
        aff = v.get("affected_periods") if isinstance(v.get("affected_periods"), list) else []
        need, allowed = {e[0] for e in exp}, {e[0] for e in exp} | set(appended)
        if aff != sorted(set(aff)) or not need <= set(aff) or not set(aff) <= allowed:
            p.append(f"{w}: affected_periods {aff[:6]} are not the periods that differ: changed, removed or inserted {sorted(need)[:6]}, appended {sorted(appended)[:6]}")
    for f in rv.files(rv.reviews):
        if f not in expected_files:
            p.append(f"archive/reviews/{f} belongs to no decision in review-queue.json")
    check("T81 every decision has its review record at archive/reviews/<series>/<16 hex>-<decision>-<decided_at as YYYYMMDDTHHMMSSZ>.json (schema review/3) with the decision's fields including reviewer_permission, permission_checked_at and publication, the hold's reason and opening time (for clear the lock's reason and frozen_at), the affected periods, and every member that differs between the published observations and the candidate (for clear the lock's candidate) in the forms of section 10 (11.5, 17.1, 17.5)", p,
          f"{len(decisions)} decision(s), {len(rv.files(rv.reviews))} review record(s)")


# --- T82: the publication record (17.5) ---


def rc_publications(ctx):
    rv = ctx.rv
    name = "T82 the publication record lists every snapshot ever published, oldest first, with the events the archived manifests imply: active when a manifest starts naming it, superseded when a later one replaces it, withdrawn by a rollback with its reason; exactly one snapshot is active, the one the manifest names; archive/state keeps a copy (17.1, 17.5)"
    live = rv.read(rv.live, "status/publications.json")
    doc, err = rv.load(rv.live, "status/publications.json")
    if err or not isinstance(doc, dict) or not isinstance(doc.get("publications"), list):
        check(name, [f"live/status/publications.json: {err or 'no publications list'}"])
        return
    p = []
    if doc.get("schema") != "rmf.econ.publications/1":
        p.append(f"schema {doc.get('schema')!r}")
    if rv.read(rv.state, "publications.json") != live:
        p.append("archive/state/publications.json is not a byte for byte copy of live/status/publications.json (17.1)")
    pubs = [x for x in doc["publications"] if isinstance(x, dict)]
    ids = [x.get("snapshot") for x in pubs]
    if ids != sorted(set(map(str, ids))):
        p.append("entries are not one per snapshot, oldest first")
    named = [(m.get("snapshot") or {}).get("id") for _, m, e in ctx.arch_manifests if not e]
    if set(ids) != set(named):
        p.append(f"snapshots in the record but named by no archived manifest {sorted(set(map(str, ids)) - set(map(str, named)))}; published but not in the record {sorted(set(map(str, named)) - set(map(str, ids)))}")
    # Replay the archived manifests.
    want, active = {}, None
    for mname, m, e in ctx.arch_manifests:
        if e:
            continue
        at, target = m.get("generated_at"), (m.get("snapshot") or {}).get("id")
        if m.get("rollback") is not None:
            run, reason = rx_rollback_run(ctx, at), m["rollback"].get("reason")
            for sid_ in sorted(want):
                if sid_ > target and want[sid_][-1][0] != "withdrawn":
                    want[sid_].append(("withdrawn", at, run, reason))
            want.setdefault(target, []).append(("active", at, run, reason))
        else:
            run = (ctx.snaps.get(target, {}).get("run") or {}).get("id")
            if active is not None and active != target and want[active][-1][0] == "active":
                want[active].append(("superseded", at, run, None))
            want.setdefault(target, []).append(("active", at, run, None))
        active = target
    for x in pubs:
        sid_ = x.get("snapshot")
        events = [e for e in x.get("events", []) if isinstance(e, dict)]
        got = [(e.get("status"), e.get("at")) for e in events]
        exp = [(s, at) for s, at, _, _ in want.get(sid_, [])]
        if got != exp:
            p.append(f"{sid_}: events {got}, the archived manifests imply {exp}")
            continue
        for e, (status, at, run, reason) in zip(events, want[sid_]):
            if run is not None and e.get("run") != run:
                p.append(f"{sid_}: the {status} event at {at} names run {e.get('run')!r}, the run that wrote that manifest is {run!r}")
            if status == "withdrawn" and e.get("reason") != reason:
                p.append(f"{sid_}: withdrawn with reason {e.get('reason')!r}, the rollback's reason is {reason!r}")
            if reason is None and e.get("reason") is not None:
                p.append(f"{sid_}: the {status} event at {at} has a reason although it is not a rollback's (17.5: null except for a rollback)")
    actives = [x.get("snapshot") for x in pubs if x.get("events") and isinstance(x["events"][-1], dict) and x["events"][-1].get("status") == "active"]
    if actives != [ctx.cur_id]:
        p.append(f"active snapshots {actives}; exactly one is active, the one the manifest names, {ctx.cur_id}")
    check(name, p, f"{len(pubs)} snapshots, {sum(len(x.get('events', [])) for x in pubs)} events, active {actives}")


# --- T84: the scenario of appendix B ---

SCENARIO_STEPS = [  # appendix B (v0.6): time, outcome, kind of run
    ("2026-11-13T14:17:00Z", "published", "collect"),   # 1 first publication of all nine series
    ("2026-11-13T15:17:00Z", "no-change", "collect"),   # 2 nothing changed
    ("2026-11-13T16:17:00Z", "published", "collect"),   # 3 same-day EFFR revision of 2026-11-12, flagged r
    ("2026-11-15T15:17:00Z", "published", "collect"),   # 4 Sunday full fetch: debt-total 2019-12-31 one dollar higher; held
    ("2026-11-16T14:17:00Z", "published", "collect"),   # 5 new EFFR day; the held windowed candidate keeps the 2019 change
    ("2026-11-16T22:17:00Z", "published", "collect"),   # 6 new debt day; 2026-11-10 changed; hold candidate replaced
    ("2026-11-17T14:17:00Z", "published", "collect"),   # 7 new EFFR day; hold candidate replaced
    ("2026-11-17T15:00:00Z", "published", "review"),    # 8 example-maintainer (maintain) approves debt-total
    ("2026-11-17T15:17:00Z", "no-change", "collect"),   # 9 two server errors, then an answer
    ("2026-11-17T16:17:00Z", "no-change", "collect"),   # 10 the EFFR source answers 429
    ("2026-11-17T17:17:00Z", "no-change", "collect"),   # 11 an EFFR response with an unknown field
    ("2026-11-18T14:17:00Z", "published", "collect"),   # 12 new EFFR and debt days; debt-intragov held
    ("2026-11-18T14:25:00Z", "refused", "review"),      # 13 example-reader (read) approves debt-intragov: refused (permission)
    ("2026-11-18T14:30:00Z", "published", "review"),    # 14 example-writer (write) rejects debt-intragov: locked (rejected)
    ("2026-11-18T22:17:00Z", "no-change", "collect"),   # 15 the rejected candidate comes back identical: still locked
    ("2026-11-19T22:17:00Z", "published", "collect"),   # 16 the published value returns, the rejected new day 2026-11-16 stays: still locked (v0.6)
    ("2026-11-24T19:17:00Z", "published", "collect"),   # 17 H.6 release, M1 above the alert ratio; new EFFR days; debt times out
    ("2026-11-24T20:00:00Z", "published", "rollback"),  # 18 rollback to step 16; five series locked (rolled-back); debt-intragov's rejection lock kept
    ("2026-11-24T20:30:00Z", "published", "restore"),   # 19 live deleted and restored from the archive; the locks still in force
    ("2026-11-24T22:17:00Z", "published", "collect"),   # 20 three new debt days for debt-total, debt-held-public; the six locked series publish nothing
    ("2026-11-25T15:00:00Z", "published", "review"),    # 21 example-maintainer (maintain) clears the lock of m1-sa
    ("2026-11-25T15:17:00Z", "published", "collect"),   # 22 m1-sa gets the release again (expected revision); four still locked
]
SCENARIO_PIN_AT = "2026-11-19T12:00:00Z"  # the first snapshot is pinned (no run)
SCENARIO_REVIEWS = {8: ("debt-total", "approve", "example-maintainer", "maintain"), 13: ("debt-intragov", "approve", "example-reader", "read"),
                    14: ("debt-intragov", "reject", "example-writer", "write"), 21: ("m1-sa", "clear", "example-maintainer", "maintain")}


def rx_is_scenario(ctx):
    """Root mode verifies a root written by the appendix B scenario: its first run starts at
    step 1's time (or its first snapshot is step 1's). Anything else fails T84, T103, T104."""
    first_run = min((str(v.get("started_at")) for v in rx_run_records(ctx).values()), default=None)
    return first_run == SCENARIO_STEPS[0][0] or (bool(ctx.order) and ctx.order[0] == snapshot_id_of(parse_utc(SCENARIO_STEPS[0][0])))


def rx_not_scenario(ctx, name):
    first_run = min((str(v.get("started_at")) for v in rx_run_records(ctx).values()), default=None)
    check(name, [f"not a root written by the appendix B scenario: the first run starts at {first_run}, the first snapshot is {ctx.order[0] if ctx.order else None}; step 1 is {SCENARIO_STEPS[0][0]}"])


class ScenarioView:
    """Step-numbered access to a scenario root (appendix B)."""

    def __init__(self, ctx):
        self.ctx = ctx

    def snap(self, step):
        return self.ctx.snaps.get(snapshot_id_of(parse_utc(SCENARIO_STEPS[step - 1][0])), {})

    def manifest(self, step):
        t = SCENARIO_STEPS[step - 1][0]
        return next((m for _, m, e in self.ctx.arch_manifests if not e and m.get("generated_at") == t), None)

    def status(self, step, sid):
        return self.snap(step).get("series", {}).get(sid, {}).get("status")

    def held(self, step):
        return sorted(h.get("series") for h in self.snap(step).get("holds", []))

    def cand_sha(self, step, sid):
        return next(((h.get("candidate") or {}).get("sha256") for h in self.snap(step).get("holds", []) if h.get("series") == sid), None)

    def cand(self, step, sid):
        sha = self.cand_sha(step, sid)
        v, err = self.ctx.rv.load(self.ctx.rv.holds, f"{sid}/{str(sha)[:16]}.json") if sha else (None, "no hold")
        return v if not err and isinstance(v, list) else None

    def record(self, step):
        t = SCENARIO_STEPS[step - 1][0]
        return next((v for v in rx_run_records(self.ctx).values() if v.get("started_at") == t), None)

    def obs(self, step, sid):
        return rx_obs(self.ctx, self.snap(step).get("series", {}).get(sid, {}))


def rc_scenario(ctx):
    rv = ctx.rv
    name = "T84 a scenario root follows the table of appendix B (v0.6): 22 runs at the listed times with the listed outcomes and triggers, and the listed holds, approval, refusal, rejected lock (kept at step 16 because its rejected new day persists), pin, revisions, rollback with its locks, restore, clear"
    if not rx_is_scenario(ctx):
        rx_not_scenario(ctx, name)
        return
    sv = ScenarioView(ctx)
    p = []
    records = rx_records_in_time(ctx)
    got = [(v.get("started_at"), v.get("outcome"), "collect" if v.get("trigger") in ("schedule", "manual") else v.get("trigger")) for v in records]
    for i, step in enumerate(SCENARIO_STEPS):
        if i >= len(got) or got[i] != step:
            p.append(f"step {i + 1}: run record {got[i] if i < len(got) else None}, appendix B gives {step}")
    if len(got) != len(SCENARIO_STEPS):
        p.append(f"{len(got)} run records, appendix B has {len(SCENARIO_STEPS)} steps")
    snap_steps = [snapshot_id_of(parse_utc(t)) for t, o, k in SCENARIO_STEPS if o == "published" and k in ("collect", "review")]
    if ctx.order != snap_steps:
        p.append(f"snapshots {ctx.order}, the publishing steps give {snap_steps}")

    def expect(cond, text):
        if not cond:
            p.append(text)

    s1 = sv.snap(1)
    expect(all(x.get("status") == "refreshed" for x in s1.get("series", {}).values()) and len(s1.get("series", {})) == 9, "step 1: not all nine series are published")
    v3 = [rv.load(rv.arch, r.get("path"))[0] for r in sv.snap(3).get("revisions", [])]
    recs3 = [r for v in v3 if isinstance(v, dict) for r in v.get("records", []) if r.get("snapshot") == sv.snap(3).get("id")]
    expect(recs3 and all(r.get("period") == "2026-11-12" and r.get("kind") == "expected" for r in recs3) and any(r.get("field") == "flags" and r.get("after") == '["r"]' for r in recs3),
           f"step 3: the records are not an expected revision of 2026-11-12 flagged r: {[(r.get('period'), r.get('field')) for r in recs3]}")
    expect(sv.held(4) == ["debt-total"], f"step 4: holds {sv.held(4)}, appendix B gives debt-total")
    expect(sv.held(5) == ["debt-total"] and sv.cand_sha(5, "debt-total") == sv.cand_sha(4, "debt-total") and sv.status(5, "effr") == "refreshed",
           "step 5: the hold is not unchanged (same candidate as step 4), or no new EFFR day")
    expect(sv.held(6) == ["debt-total"] and sv.cand_sha(6, "debt-total") not in (None, sv.cand_sha(5, "debt-total")), "step 6: the hold candidate was not replaced")
    expect(sv.held(7) == ["debt-total"] and sv.cand_sha(7, "debt-total") not in (None, sv.cand_sha(6, "debt-total")) and sv.status(7, "effr") == "refreshed",
           "step 7: the hold candidate was not replaced, or no new EFFR day")
    expect(sv.held(8) == [] and sv.status(8, "debt-total") == "refreshed" and (sv.snap(8).get("run") or {}).get("trigger") == "review", "step 8: debt-total not approved in a review run")
    r10, r11 = sv.record(10) or {}, sv.record(11) or {}
    expect((r10.get("series") or {}).get("effr") == "failed" and "blocked:nyfed-markets" in (r10.get("alerts") or []), f"step 10: effr {(r10.get('series') or {}).get('effr')}, alerts {r10.get('alerts')}; a 429 fails the fetch and raises blocked:nyfed-markets (17.4)")
    expect((r11.get("series") or {}).get("effr") == "invalid" and "invalid:nyfed-markets" in (r11.get("alerts") or []), f"step 11: effr {(r11.get('series') or {}).get('effr')}, alerts {r11.get('alerts')}; an unknown field makes the response invalid and raises invalid:nyfed-markets (5, 17.4)")
    expect(sv.held(12) == ["debt-intragov"], f"step 12: holds {sv.held(12)}, appendix B gives debt-intragov")
    expect(sv.held(14) == [] and [(k[0], k[1]) for k in rx_frozen(sv.snap(14))] == [("debt-intragov", "rejected")],
           f"step 14: frozen {sorted(map(_k16, rx_frozen(sv.snap(14))))}, appendix B gives debt-intragov locked with origin rejected")
    r15 = sv.record(15) or {}
    expect((r15.get("series") or {}).get("debt-intragov") == "revised-unexpected" and "frozen:debt-intragov" in (r15.get("alerts") or []),
           f"step 15: debt-intragov outcome {(r15.get('series') or {}).get('debt-intragov')}, alerts {r15.get('alerts')}; still locked gives revised-unexpected and frozen:debt-intragov (17.3)")
    # v0.6 row 16: the source returns the published intragovernmental value with the new days; the rejected
    # new day 2026-11-16 is still there unchanged, so debt-intragov stays locked (11.5: rejected additions stay
    # locked); debt-total and debt-held-public are appended.
    fz14, fz16 = rx_frozen(sv.snap(14)), rx_frozen(sv.snap(16))
    r16 = sv.record(16) or {}
    expect(set(fz16) == set(fz14) and len(fz16) == 1 and all(fz16[k] == fz14[k] for k in fz16),
           f"step 16: locks {sorted(map(_k16, fz16))}, appendix B (v0.6) keeps step 14's rejected lock of debt-intragov unchanged {sorted(map(_k16, fz14))}")
    expect(sv.status(16, "debt-intragov") == "carried-forward" and (r16.get("series") or {}).get("debt-intragov") == "revised-unexpected" and "frozen:debt-intragov" in (r16.get("alerts") or []),
           f"step 16: debt-intragov status {sv.status(16, 'debt-intragov')}, outcome {(r16.get('series') or {}).get('debt-intragov')}, alerts {r16.get('alerts')}; still locked: carried-forward, revised-unexpected, frozen:debt-intragov (17.3)")
    expect(all(sv.status(16, x) == "refreshed" and (r16.get("series") or {}).get(x) == "appended" for x in ("debt-total", "debt-held-public")),
           f"step 16: debt-total {sv.status(16, 'debt-total')}/{(r16.get('series') or {}).get('debt-total')}, debt-held-public {sv.status(16, 'debt-held-public')}/{(r16.get('series') or {}).get('debt-held-public')}; appendix B gives both appended")
    lk14 = next(iter(fz14.values()), {})
    _, locked14, ch14 = rx_lock_detail(ctx, "debt-intragov", lk14) if lk14 else (None, None, None)
    new14 = [c for c in (ch14 or []) if c[1] == "period"]
    expect(any(c[0] == "2026-11-16" for c in new14), f"step 14: the rejected lock's locked changes {ch14}; appendix B (v0.6) has its rejected candidate carry the new day 2026-11-16, a locked change of field period")
    o16 = {observation_key(o): o for o in sv.obs(16, "debt-total")}
    lmap = {observation_key(o): o for o in (locked14 or [])}
    expect("2026-11-16" in o16 and "2026-11-16" in lmap, "step 16: 2026-11-16 is not both published for debt-total and in debt-intragov's rejected candidate (the source keeps the rejected new day)")
    h6 = [sid for sid, ser in ctx.st.series.items() if ser["source"] == "frb-releases"]
    debt = [sid for sid, ser in ctx.st.series.items() if ser["source"] == "fiscaldata"]
    expect(all(sv.status(17, sid) == "refreshed" for sid in h6), "step 17: an H.6 series is not refreshed")
    expect(all(sv.status(17, sid) == "carried-forward" and sv.snap(17).get("series", {}).get(sid, {}).get("attempt", {}).get("outcome") == "failed" for sid in debt),
           "step 17: the debt series are not carried forward with a failed attempt (the source times out)")
    expect(sv.status(17, "effr") == "refreshed", "step 17: no new EFFR days")
    r17 = sv.record(17) or {}
    a17 = set(r17.get("alerts") or [])
    # reading: "M1" and "M2" name the measures, not one adjustment; at least one M1 series is over the ratio, no M2 series is.
    expect(bool(a17 & {"revision-large:m1-sa", "revision-large:m1-nsa"}) and not a17 & {"revision-large:m2-sa", "revision-large:m2-nsa"},
           f"step 17: alerts {sorted(a17)}; M1 revised above the alert ratio raises revision-large for an M1 series, M2 slightly raises none (2.4, 17.3)")
    rb = (sv.manifest(18) or {}).get("rollback") or {}
    expect(rb.get("to") == sv.snap(16).get("id") and rb.get("from") == sv.snap(17).get("id") and rb.get("at") == SCENARIO_STEPS[17][0],
           f"step 18: the manifest of the rollback is not one to step 16's snapshot from step 17's at its time (rollback {rb})")
    expect(ctx.cur_id == sv.snap(22).get("id") and ctx.manifest.get("rollback") is None, f"the live manifest names {ctx.cur_id}, rollback {ctx.manifest.get('rollback')}; after step 22 it names step 22's snapshot")
    pins = rx_pins(ctx)
    expect([(x.get("snapshot"), x.get("pinned_at")) for x in pins] == [(sv.snap(1).get("id"), SCENARIO_PIN_AT)], f"the first snapshot is not the one pin, made {SCENARIO_PIN_AT}: {pins}")
    decs = [(d.get("series"), d.get("decision"), d.get("run")) for d in rx_decisions(ctx)]
    expect(decs == [("debt-total", "approve", (sv.snap(8).get("run") or {}).get("id")), ("debt-intragov", "reject", (sv.snap(14).get("run") or {}).get("id")),
                    ("m1-sa", "clear", (sv.snap(21).get("run") or {}).get("id"))],
           f"decisions {decs}, appendix B gives an approval of debt-total at step 8, a rejection of debt-intragov at step 14 and a clear of m1-sa at step 21")
    refs = [(r.get("series"), r.get("decision"), r.get("run"), r.get("refused")) for r in rx_refusals(ctx)]
    expect(refs == [("debt-intragov", "approve", (sv.record(13) or {}).get("id"), "permission")], f"refusals {refs}, appendix B gives one: step 13, debt-intragov, approve, refused by permission")
    check(name, p, f"{len(got)} run records, {len(ctx.order)} snapshots")


def rc_scenario_v04(ctx):
    """T103 and T104: the v0.4 steps of appendix B."""
    name103 = "T103 appendix B, the v0.4 steps kept in v0.5: the 2019-12-31 change of debt-total (one dollar higher) stays in the held candidate from step 4 through the weekday runs 5 to 7 and is published by the approval of step 8 with an approved-hold record; step 8 rewrites only the 2019 and 2026 segments of debt-total (objects and CSVs); the reviews read the permission at the run's time; step 13 refused by permission changes nothing; step 17's debt absences are collection-failure or expected-nonpublication; no route alert in November 2026"
    name104 = "T104 appendix B, which files each step wrote: a snapshot and a manifest exactly at the publishing collect and review steps, a manifest without a snapshot at the rollback, nothing at the no-change, refused and restore steps; new objects and CSVs only for changed segments; a review record exactly at the review steps that decide; a rollback writes revision log versions only"
    if not rx_is_scenario(ctx):
        rx_not_scenario(ctx, name103)
        rx_not_scenario(ctx, name104)
        return
    sv, rv, st = ScenarioView(ctx), ctx.rv, ctx.st
    p = []
    base_obs = {observation_key(o): o for o in sv.obs(1, "debt-total")}
    old = base_obs.get("2019-12-31", {}).get("value")
    want_new = None
    try:
        want_new = pad_decimal(str(D(old) + 1), st.series["debt-total"]["decimals"]) if old is not None else None
    except Exception:
        pass
    for step in (4, 5, 6, 7):
        c = sv.cand(step, "debt-total")
        got = next((o.get("value") for o in (c or []) if o.get("period") == "2019-12-31"), None)
        if c is None:
            p.append(f"step {step}: no held candidate of debt-total in archive/holds")
        elif got != want_new:
            p.append(f"step {step}: the held candidate of debt-total has 2019-12-31 = {got}, the published {old} plus one dollar is {want_new} (5: a held series' windowed candidate keeps the held candidate's history)")
    pub8 = {observation_key(o): o for o in sv.obs(8, "debt-total")}
    if pub8.get("2019-12-31", {}).get("value") != want_new:
        p.append(f"step 8: published debt-total 2019-12-31 is {pub8.get('2019-12-31', {}).get('value')}, the approved change is {want_new}")
    recs8 = [r for ref in sv.snap(8).get("revisions", []) for r in (rv.load(rv.arch, ref.get("path"))[0] or {}).get("records", [])
             if r.get("snapshot") == sv.snap(8).get("id")]
    if not any(r.get("period") == "2019-12-31" and r.get("field") == "value" and r.get("kind") == "approved-hold" and r.get("before") == old and r.get("after") == want_new for r in recs8):
        p.append(f"step 8: no approved-hold record of debt-total 2019-12-31 value {old} to {want_new}")
    seg7 = {r.get("segment"): r.get("sha256") for r in sv.snap(7).get("series", {}).get("debt-total", {}).get("objects", [])}
    seg8 = {r.get("segment"): r.get("sha256") for r in sv.snap(8).get("series", {}).get("debt-total", {}).get("objects", [])}
    changed = sorted(s for s in set(seg7) | set(seg8) if seg7.get(s) != seg8.get(s))
    if changed != ["2019", "2026"]:
        p.append(f"step 8: debt-total segments with new objects {changed}, appendix B gives only 2019 and 2026")
    m7, m8 = sv.manifest(7), sv.manifest(8)
    if m7 and m8:
        c7 = {c.get("segment"): c for c in rx_csv_refs(m7["series"].get("debt-total", {}))}
        c8 = {c.get("segment"): c for c in rx_csv_refs(m8["series"].get("debt-total", {}))}
        csv_changed = sorted(s for s in set(c7) | set(c8) if c7.get(s) != c8.get(s))
        if csv_changed != ["2019", "2026"]:
            p.append(f"step 8: debt-total CSV entries that changed {csv_changed}, appendix B gives only 2019 and 2026")
        for sid in sorted(ctx.reg_ids - {"debt-total"}):
            if rx_csv_refs(m7["series"].get(sid, {})) != rx_csv_refs(m8["series"].get(sid, {})):
                p.append(f"step 8: the CSV entries of {sid} changed in a review run that decided only debt-total")
    else:
        p.append("the manifests of steps 7 and 8 are not both archived")
    for step, (sid, dec, who, perm) in SCENARIO_REVIEWS.items():
        t = SCENARIO_STEPS[step - 1][0]
        rows = [d for d in rx_decisions(ctx) if d.get("decided_at") == t] + [r for r in rx_refusals(ctx) if r.get("at") == t]
        if len(rows) != 1:
            p.append(f"step {step}: {len(rows)} decisions or refusals at {t}, appendix B gives one")
            continue
        r = rows[0]
        if (r.get("series"), r.get("decision"), r.get("reviewer"), r.get("reviewer_permission"), r.get("permission_checked_at")) != (sid, dec, who, perm, t):
            p.append(f"step {step}: {(r.get('series'), r.get('decision'), r.get('reviewer'), r.get('reviewer_permission'), r.get('permission_checked_at'))}, appendix B gives {(sid, dec, who, perm, t)} (permission_checked_at equals now)")
    r13 = sv.record(13) or {}
    if r13.get("outcome") != "refused" or r13.get("snapshot") is not None or r13.get("absences") != []:
        p.append(f"step 13: run record outcome {r13.get('outcome')}, snapshot {r13.get('snapshot')}, absences {r13.get('absences')!r:.40}")
    if rx_manifest_at(ctx, SCENARIO_STEPS[12][0], False)[0] != rx_manifest_at(ctx, str(r13.get("ended_at") or SCENARIO_STEPS[12][0]), True)[0]:
        p.append("step 13: a manifest was published by the refused review")
    r17 = sv.record(17) or {}
    debt = {sid for sid, ser in st.series.items() if ser["source"] == "fiscaldata"}
    bad = [e for e in r17.get("absences") or [] if isinstance(e, dict) and e.get("series") in debt and e.get("kind") not in ("collection-failure", "expected-nonpublication")]
    if bad or not any(isinstance(e, dict) and e.get("series") in debt for e in r17.get("absences") or []):
        p.append(f"step 17: the debt absences are {[(e.get('series'), e.get('period'), e.get('kind')) for e in (r17.get('absences') or []) if isinstance(e, dict) and e.get('series') in debt][:6]}; appendix B gives collection-failure or expected-nonpublication")
    route = sorted({k for v in rx_run_records(ctx).values() for k in (v.get("alerts") or []) if str(k).startswith(("source-retirement:", "source-route-check:"))})
    if route:
        p.append(f"route alerts {route} raised in November 2026; the Board's entries are route checks dated 2027 (4.3, 17.8)")
    check(name103, p, f"2019-12-31: {old} to {want_new}")

    # T104: which files each step wrote
    p = []
    first_snap_obj, first_man_csv, first_man_log = {}, {}, {}
    for sid_ in ctx.order:
        for state in ctx.snaps[sid_].get("series", {}).values():
            for r in state.get("objects", []):
                first_snap_obj.setdefault(r.get("path"), snapshot_time(sid_))
    for _, m, err in ctx.arch_manifests:
        if err:
            continue
        g = m.get("generated_at")
        for summ in m.get("series", {}).values():
            for r in rx_csv_refs(summ):
                first_man_csv.setdefault(r.get("path"), g)
            for r in summ.get("revisions", []):
                first_man_log.setdefault(r.get("path"), g)
    man_times = [m.get("generated_at") for _, m, err in ctx.arch_manifests if not err]
    review_times = {f.rsplit("-", 1)[-1][:-5] for f in rv.files(rv.reviews)}
    for i, (t, outcome, kind) in enumerate(SCENARIO_STEPS, start=1):
        sid_ = snapshot_id_of(parse_utc(t))
        has_snap, has_man = sid_ in ctx.snaps, man_times.count(t)
        new_obj = sorted(f for f, at in first_snap_obj.items() if at == parse_utc(t))
        new_csv = sorted(f for f, at in first_man_csv.items() if at == t)
        new_log = sorted(f for f, at in first_man_log.items() if at == t)
        rev = sid_ in review_times
        if outcome == "published" and kind in ("collect", "review"):
            if not has_snap or has_man != 1:
                p.append(f"step {i}: snapshot written {has_snap}, manifests at its time {has_man}; a publishing step writes one of each")
        elif kind == "rollback":
            if has_snap or has_man != 1 or new_obj or new_csv:
                p.append(f"step {i} (rollback): snapshot {has_snap}, manifests {has_man}, new objects {len(new_obj)}, new CSVs {len(new_csv)}; a rollback writes one manifest and revision log versions, nothing else (17.5)")
        elif has_snap or has_man or new_obj or new_csv or new_log:
            p.append(f"step {i} ({kind}, {outcome}): wrote snapshot {has_snap}, manifests {has_man}, objects {len(new_obj)}, CSVs {len(new_csv)}, log versions {len(new_log)}; it writes none")
        if rev != (kind == "review" and outcome == "published"):
            p.append(f"step {i} ({kind}, {outcome}): review record named with its time {rev}; one exactly for a review that decides (17.1, 17.5)")
        if kind == "review" and outcome == "published":
            d = next((x for x in rx_decisions(ctx) if x.get("decided_at") == t), {})
            touched = sorted({f.split("/")[1] for f in new_obj + new_csv})
            want = ["debt-total"] if d.get("decision") == "approve" else []
            if touched != want:
                p.append(f"step {i} (review, {d.get('decision')}): new objects or CSVs for {touched}; only an approval writes them, for the approved series")
        if outcome == "published" and kind == "collect" and has_snap:
            s = ctx.snaps[sid_]
            base = ctx.snaps.get(rx_base_id(ctx, sid_)) or {}
            for f in new_obj:
                ser_id, seg = f.split("/")[1], f.split("/")[2]
                old = {r.get("segment"): r.get("sha256") for r in base.get("series", {}).get(ser_id, {}).get("objects", [])}
                new = {r.get("segment"): r.get("sha256") for r in s.get("series", {}).get(ser_id, {}).get("objects", [])}
                if old.get(seg) == new.get(seg):
                    p.append(f"step {i}: object {f} is new although segment {seg} of {ser_id} did not change")
    check(name104, p, f"{len(SCENARIO_STEPS)} steps, {len(first_snap_obj)} objects, {len(first_man_csv)} CSV segments, {len(first_man_log)} log versions")


# --- T108, T113, T114 (v0.5) ---


def rx_manifest_of_snapshot(ctx, snap_id, at=None):
    """The archived manifest that published a snapshot (generated at `at` when given)."""
    return next((m for _, m, e in ctx.arch_manifests if not e and (m.get("snapshot") or {}).get("id") == snap_id and m.get("rollback") is None
                 and (at is None or m.get("generated_at") == at)), None)


def rc_clear(ctx):
    """T108: a clear lifts exactly the lock it names, in a review run that publishes nothing else (11.5, 17.5)."""
    p, n = [], 0
    recs = rx_run_records(ctx)
    for i, d in enumerate(rx_decisions(ctx)):
        if d.get("decision") != "clear":
            continue
        n += 1
        sid, sha = d.get("series"), d.get("candidate_sha256")
        w = f"decisions[{i}] clear {sid} in run {d.get('run')}"
        rec = recs.get(d.get("run")) or {}
        if rec.get("trigger") != "review" or rec.get("outcome") != "published":
            p.append(f"{w}: its run record has trigger {rec.get('trigger')}, outcome {rec.get('outcome')}; a clear is a review run that publishes a snapshot (17.5)")
        snap_id = (d.get("publication") or {}).get("snapshot")
        s = ctx.snaps.get(snap_id)
        if s is None or not is_time(d.get("decided_at")):
            p.append(f"{w}: publication snapshot {snap_id} is not archived, or decided_at is not a time")
            continue
        m_now = rx_manifest_of_snapshot(ctx, snap_id, d.get("decided_at"))
        base = ctx.snaps.get(rx_base_id(ctx, snap_id)) or {}
        before, after = rx_locks_at(ctx, d["decided_at"], inclusive=False), rx_locks_of(ctx, m_now)
        named = {k for k in before if k[0] == sid and k[2] == sha}
        if not named:
            p.append(f"{w}: the locks in force before it ({sorted(map(_k16, before))}) hold no lock of {sid} on candidate {str(sha)[:16]}")
        if named & set(after):
            p.append(f"{w}: the lock it names is still in force under the manifest of snapshot {snap_id}")
        # v0.6: a clear names one lock by its hash; every other lock, of this series too, stays.
        others_b, others_a = set(before) - named, set(after)
        if others_b != others_a:
            p.append(f"{w}: other locks changed in the same run ({sorted(map(_k16, others_b - others_a))} lifted, {sorted(map(_k16, others_a - others_b))} added)")
        if any(k[0] == sid for k in others_b) and sid not in lock_series(after):
            p.append(f"{w}: {sid} has another lock, so it stays locked after the clear (11.5 v0.6)")
        if rx_hold_set(base) != rx_hold_set(s):
            p.append(f"{w}: the holds changed in a clear run")
        if s.get("revisions"):
            p.append(f"{w}: snapshot {snap_id} writes revision log versions; a clear publishes nothing in its own run")
        for series_id, state in sorted((s.get("series") or {}).items()):
            old = (base.get("series") or {}).get(series_id) or {}
            if state.get("objects") != old.get("objects"):
                p.append(f"{w}: {series_id} has new objects in the clear run (17.5: it fetches and publishes nothing)")
        if named & set(rx_locks_at(ctx, d["decided_at"], inclusive=True)):
            p.append(f"{w}: the manifest in place right after the run still has the lock it names")
    check("T108 every clear (an authorized review, T94; refusals, T95) lifts exactly the lock it names by its candidate hash, in a review run whose snapshot keeps every other lock (of the same series too, v0.6) and hold, writes no revision record and publishes no new object; the series is carried forward and stays locked only while another of its locks stands (11.5, 17.5)", p,
          f"{n} clear decision(s)")


def rc_zero(ctx):
    """T113: missing versus zero in what was published and held (2.3, v0.5)."""
    rv, st = ctx.rv, ctx.st
    p, seen, n_obs, n_null, n_zero = [], set(), 0, 0, 0
    for sid_ in ctx.order:
        for series_id in DEBT_SERIES:
            state = (ctx.snaps[sid_].get("series") or {}).get(series_id) or {}
            key = (series_id, tuple(r.get("sha256") for r in state.get("objects", [])))
            if not state.get("objects") or key in seen:
                continue
            seen.add(key)
            ser = st.series[series_id]
            accepted = accepted_zero_periods(ser)
            zero_text = pad_decimal("0", ser["decimals"])
            for o in rx_obs(ctx, state):
                n_obs += 1
                v, era = o.get("value"), era_for(ser, str(o.get("period")))
                w = f"{series_id} {o.get('period')} (first in {sid_})"
                if v is None:
                    n_null += 1
                    if not (era or {}).get("null_text"):
                        p.append(f"{w}: value null in an era without null_text; only a breakout's \"null\" means not published (2.3)")
                    if o.get("missing") != {"code": "not-published", "note": ""}:
                        p.append(f"{w}: missing {o.get('missing')!r}; 2.3 stores \"null\" as missing.code not-published with an empty note")
                elif is_exact_zero(v):
                    if o.get("period") not in accepted:
                        p.append(f"{w}: value {v!r} equals zero and no accepted_zeros entry names this period; refuse_zero makes such a candidate invalid, so it is never stored (2.3)")
                    elif v != zero_text or "missing" in o:
                        p.append(f"{w}: an accepted zero stored as {v!r} (missing {o.get('missing')!r}); 2.3 (v0.6) stores it as the number zero {zero_text!r}, never as missing")
                    else:
                        n_zero += 1
    n_cand = 0
    for f in rv.files(rv.holds):
        series_id = f.split("/", 1)[0]
        if series_id not in DEBT_SERIES:
            continue
        v, err = rv.load(rv.holds, f)
        if err or not isinstance(v, list):
            continue  # T64
        n_cand += 1
        accepted = accepted_zero_periods(st.series[series_id])
        zero = [o.get("period") for o in v if isinstance(o, dict) and is_exact_zero(o.get("value")) and o.get("period") not in accepted]
        if zero:
            p.append(f"archive/holds/{f}: values equal to zero on {zero[:3]} that no accepted_zeros entry names; a candidate with such a zero is invalid (11.4), never held or locked")
    n_entries = sum(len(accepted_zero_periods(st.series[x])) for x in DEBT_SERIES)
    check("T113 missing versus zero: no observation of debt-total, debt-held-public or debt-intragov in any snapshot, and no held or locked candidate of them, has a value equal to zero unless an accepted_zeros entry names that period (v0.6), and an accepted zero is stored as the number zero (0.00), never as missing; every null value is a breakout stored as missing not-published with an empty note (2.3, 6.1, 11.4)", p,
          f"{n_obs} observations in {len(seen)} distinct states, {n_null} not published, {n_zero} accepted zero(s) stored; {n_cand} candidate file(s); {n_entries} accepted_zeros entr{'y' if n_entries == 1 else 'ies'} in the registry")


SCENARIO_LOCKED = ["effr", "m1-sa", "m2-sa", "m1-nsa", "m2-nsa"]  # appendix B step 18, in registry order
SCENARIO_KEPT = "debt-intragov"  # appendix B (v0.6) steps 14 to 22: its rejection lock stands throughout


def rc_scenario_v05(ctx):
    """T114: the steps of appendix B that v0.5 added and v0.6 changed (16, 18, 20) or kept (19, 21, 22)."""
    name = "T114 appendix B in v0.6, steps 18 to 22: the rollback of step 18 locks effr, m1-sa, m2-sa, m1-nsa, m2-nsa (rolled-back, step 17's withdrawn observations as locked candidates, frozen in its manifest) and keeps debt-intragov's rejection lock, its rollback record listing exactly the five; the restore of step 19 keeps all six; step 20 appends three days to debt-total and debt-held-public while the six locked series publish nothing (revised-unexpected, frozen alerts, listed under frozen); step 21 clears m1-sa (example-maintainer, maintain, cleared); step 22 republishes only m1-sa, the release again as an expected revision with revision-large:m1-sa, the four others and debt-intragov still locked"
    if not rx_is_scenario(ctx):
        rx_not_scenario(ctx, name)
        return
    sv, st, rv = ScenarioView(ctx), ctx.st, ctx.rv
    p = []

    def expect(cond, text):
        if not cond:
            p.append(text)
    kept = rx_frozen(sv.snap(14))
    kept_keys = {k for k in kept if k[0] == SCENARIO_KEPT and k[1] == "rejected"}
    expect(len(kept_keys) == 1, f"step 14: rejected locks of {SCENARIO_KEPT} {sorted(map(_k16, kept_keys))}; appendix B gives one")
    m18 = sv.manifest(18) or {}
    rb = m18.get("rollback") or {}
    expect(rb.get("locked") == SCENARIO_LOCKED, f"step 18: rollback.locked {rb.get('locked')}, appendix B gives {SCENARIO_LOCKED} (debt-intragov's kept lock is already in the target's frozen)")
    expect(rb.get("to") == sv.snap(16).get("id") and rb.get("from") == sv.snap(17).get("id"), f"step 18: rollback {rb.get('from')} to {rb.get('to')}, appendix B gives step 17's to step 16's")
    for sid in SCENARIO_LOCKED + [SCENARIO_KEPT]:
        expect(((m18.get("series") or {}).get(sid) or {}).get("status") == "frozen", f"step 18: {sid} status {((m18.get('series') or {}).get(sid) or {}).get('status')}, a locked series shows frozen")
    want_sha = {sid: sha256_hex(canon_bytes(sv.obs(17, sid))) for sid in SCENARIO_LOCKED}
    want18 = {(sid, "rolled-back", sha) for sid, sha in want_sha.items()} | kept_keys
    l18 = rx_locks_of(ctx, m18)
    expect(set(l18) == want18, f"step 18: locks in force {sorted(map(_k16, l18))}; appendix B gives the five rolled-back on step 17's observations and debt-intragov's rejection lock")
    rec, err, f = rx_rollback_record(ctx, m18)
    got_rec = [lock_key(x) for x in (rec or {}).get("locks", []) if isinstance(x, dict)]
    expect(rec is not None and got_rec == [(sid, "rolled-back", want_sha[sid]) for sid in SCENARIO_LOCKED],
           f"step 18: rollback record archive/rollbacks/{f} {'locks ' + str([_k16(k) for k in got_rec]) if rec is not None else err}; appendix B gives the five rolled-back locks in registry order (debt-intragov's lock is in the target's frozen, so not listed)")
    for sid, sha in want_sha.items():
        expect(rv.read(rv.holds, f"{sid}/{sha[:16]}.json") == canon_bytes(sv.obs(17, sid)), f"step 18: {sid}'s withdrawn observations are not its locked candidate in archive/holds/")
    r19 = sv.record(19) or {}
    expect(r19.get("trigger") == "restore" and r19.get("outcome") == "published" and r19.get("snapshot") == sv.snap(16).get("id"),
           f"step 19: restore record {r19.get('trigger')}, {r19.get('outcome')}, snapshot {r19.get('snapshot')}")
    if is_time(r19.get("ended_at")):
        l19 = rx_locks_at(ctx, r19["ended_at"], True)
        expect(set(l19) == want18, f"step 19: locks after the restore {sorted(map(_k16, l19))}")
    s20, r20 = sv.snap(20), sv.record(20) or {}
    for sid in ("debt-total", "debt-held-public"):
        o16, o20 = sv.obs(16, sid), sv.obs(20, sid)
        k16 = {observation_key(o): rx_bare(o) for o in o16}
        new = [observation_key(o) for o in o20 if observation_key(o) not in k16]
        same = all(json_equal(k16.get(observation_key(o)), rx_bare(o)) for o in o20 if observation_key(o) in k16) and len(o20) - len(new) == len(o16)
        expect(sv.status(20, sid) == "refreshed" and len(new) == 3 and same and all(k > max(k16) for k in new),
               f"step 20: {sid} status {sv.status(20, sid)}, {len(new)} new period(s) {new}; appendix B gives three new days appended, nothing else changed")
    fz20 = rx_frozen(s20)
    for sid in SCENARIO_LOCKED:
        es = locks_of_series(fz20, sid)
        e = es[0] if len(es) == 1 else {}
        expect(e.get("origin") == "rolled-back" and e.get("candidate_sha256") == want_sha[sid] and e.get("frozen_at") == SCENARIO_STEPS[17][0] and e.get("reason") == rb.get("reason"),
               f"step 20: frozen entries of {sid} {es}; the rollback's lock carried forward (rolled-back, step 17's observations, {SCENARIO_STEPS[17][0]}, the rollback's reason)")
    for sid in SCENARIO_LOCKED + [SCENARIO_KEPT]:
        expect(sv.status(20, sid) == "carried-forward" and (s20.get("series", {}).get(sid) or {}).get("objects") == (sv.snap(16).get("series", {}).get(sid) or {}).get("objects"),
               f"step 20: {sid} status {sv.status(20, sid)}; a locked series publishes nothing (objects of step 16)")
        expect((r20.get("series") or {}).get(sid) == "revised-unexpected" and f"frozen:{sid}" in (r20.get("alerts") or []),
               f"step 20: {sid} outcome {(r20.get('series') or {}).get(sid)}, alert frozen:{sid} {f'frozen:{sid}' in (r20.get('alerts') or [])}; the source still serves the withdrawn or rejected data: revised-unexpected, frozen alert (17.3)")
    k20 = {k for k in fz20 if k[0] == SCENARIO_KEPT}
    expect(k20 == kept_keys and all(fz20[k] == kept[k] for k in k20), f"step 20: {SCENARIO_KEPT} locks {sorted(map(_k16, k20))}; its rejection lock of step 14 carried forward unchanged")
    expect(set(fz20) == want18, f"step 20: frozen {sorted(map(_k16, fz20))}")
    d21 = [d for d in rx_decisions(ctx) if d.get("decided_at") == SCENARIO_STEPS[20][0]]
    want21 = ("m1-sa", "clear", "example-maintainer", "maintain", SCENARIO_STEPS[20][0], want_sha["m1-sa"], {"outcome": "cleared", "snapshot": sv.snap(21).get("id")})
    got21 = [(d.get("series"), d.get("decision"), d.get("reviewer"), d.get("reviewer_permission"), d.get("permission_checked_at"), d.get("candidate_sha256"), d.get("publication")) for d in d21]
    expect(got21 == [want21], f"step 21: decisions {got21}; appendix B gives {want21}")
    want21_locks = want18 - {("m1-sa", "rolled-back", want_sha["m1-sa"])}
    expect(set(rx_frozen(sv.snap(21))) == want21_locks and sv.status(21, "m1-sa") == "carried-forward"
           and (sv.snap(21).get("series", {}).get("m1-sa") or {}).get("objects") == (s20.get("series", {}).get("m1-sa") or {}).get("objects"),
           f"step 21: frozen {sorted(map(_k16, rx_frozen(sv.snap(21))))}, m1-sa {sv.status(21, 'm1-sa')}; the clear lifts m1-sa's lock only and publishes nothing")
    s22, r22 = sv.snap(22), sv.record(22) or {}
    expect(sv.status(22, "m1-sa") == "refreshed" and (r22.get("series") or {}).get("m1-sa") == "revised-expected",
           f"step 22: m1-sa status {sv.status(22, 'm1-sa')}, outcome {(r22.get('series') or {}).get('m1-sa')}; appendix B gives an expected revision")
    expect([rx_bare(o) for o in sv.obs(22, "m1-sa")] == [rx_bare(o) for o in sv.obs(17, "m1-sa")],
           "step 22: m1-sa's observations are not the release step 17 published (the source still serves it)")
    recs22 = [r for ref in s22.get("revisions", []) for r in (rv.load(rv.arch, ref.get("path"))[0] or {}).get("records", [])
              if r.get("snapshot") == s22.get("id")]
    expect(bool(recs22) and all(r.get("kind") == "expected" for r in recs22),
           f"step 22: revision records {[(r.get('period'), r.get('field'), r.get('kind')) for r in recs22][:4]}; the release is logged as expected")
    logged = {ref.get("path", "").split("/")[1] for ref in s22.get("revisions", []) if isinstance(ref.get("path"), str) and ref["path"].count("/") >= 2}
    expect(logged == {"m1-sa"}, f"step 22: revision logs written for {sorted(logged)}; only m1-sa is republished")
    expect("revision-large:m1-sa" in (r22.get("alerts") or []), f"step 22: alerts {r22.get('alerts')}; appendix B gives revision-large:m1-sa")
    for sid in [x for x in SCENARIO_LOCKED if x != "m1-sa"]:
        expect(sv.status(22, sid) == "carried-forward" and (s22.get("series", {}).get(sid) or {}).get("objects") == (sv.snap(16).get("series", {}).get(sid) or {}).get("objects")
               and sid in lock_series(rx_frozen(s22)) and f"frozen:{sid}" in (r22.get("alerts") or []),
               f"step 22: {sid} status {sv.status(22, sid)}, locked {sid in lock_series(rx_frozen(s22))}; the other four locked series publish nothing")
    expect(set(rx_frozen(s22)) == want21_locks, f"step 22: frozen {sorted(map(_k16, rx_frozen(s22)))}, appendix B gives the four rolled-back locks and debt-intragov's rejection lock")
    live = ctx.manifest or {}
    expect((live.get("snapshot") or {}).get("id") == s22.get("id") and live.get("rollback") is None, f"the live manifest names {(live.get('snapshot') or {}).get('id')} with rollback {live.get('rollback')}; after step 22 it names step 22's snapshot, rollback null")
    check(name, p, f"locks {', '.join(SCENARIO_LOCKED)} and {SCENARIO_KEPT} (rejected); reason {rb.get('reason')!r}")


# --- T87 to T93: CSV segments (9, 12.9, 16, 17.6, appendix C1) ---


def rx_seg_objects(snapshot, sid):
    return {r.get("segment"): r for r in (((snapshot or {}).get("series") or {}).get(sid) or {}).get("objects", [])}


def rc_csv_segments(ctx):
    rv = ctx.rv
    p87, p88, p89, p90, p91, p92, p93 = [], [], [], [], [], [], []
    good = [(name, m) for name, m, err in ctx.arch_manifests if not err]
    n_entries, n_carry, n_rb = 0, 0, 0
    first_named, named_sha = {}, {}
    for idx, (name, m) in enumerate(good):
        s = ctx.snaps.get((m.get("snapshot") or {}).get("id"))
        prev = good[idx - 1][1] if idx else None
        prev_s = ctx.snaps.get((prev.get("snapshot") or {}).get("id")) if prev else None
        rb = m.get("rollback")
        for sid in sorted(ctx.reg_ids & set(m.get("series", {}))):
            summ, w = m["series"][sid], f"{name} {sid}"
            if "csv" in summ:
                p90.append(f"{w}: a full-history 'csv' reference; v0.4 names csvs only (9)")
            csvs = summ.get("csvs")
            if not isinstance(csvs, list):
                p87.append(f"{w}: csvs is {csvs!r:.40}, not a list (9)")
                continue
            n_entries += len(csvs)
            for c in csvs:
                path = c.get("path") if isinstance(c, dict) else None
                if isinstance(path, str):
                    first_named.setdefault(path, (idx, name, sid, c.get("segment"), rb is not None))
                    named_sha.setdefault(path, set()).add(c.get("sha256"))
            if s is None:
                continue  # reported by T40
            state = s.get("series", {}).get(sid, {})
            objs = state.get("objects") or []
            if not objs:
                if csvs:
                    p87.append(f"{w}: {len(csvs)} CSV entries for a series without objects (9: empty when not yet published)")
                continue
            if [c.get("segment") for c in csvs] != [o.get("segment") for o in objs]:
                p87.append(f"{w}: csvs segments {[c.get('segment') for c in csvs]}, the snapshot's objects {[o.get('segment') for o in objs]}: one entry per object, same segments, same order (9, 12.9)")
            for c in csvs:
                mt = RX_CSV_PATH.fullmatch(c.get("path") or "") if isinstance(c.get("path"), str) else None
                if sorted(c) != ["path", "retrieved_at", "segment", "sha256"]:
                    p87.append(f"{w}: entry fields {sorted(c)}, 9 gives segment, path, sha256, retrieved_at")
                if not mt or mt.group(1) != sid or mt.group(2) != c.get("segment") or not is_sha256(c.get("sha256")) or mt.group(3) != str(c.get("sha256"))[:16]:
                    p87.append(f"{w}: entry {c.get('path')} is not series/{sid}/{c.get('segment')}/<first 16 hex of {str(c.get('sha256'))[:16]}...>.csv (9, 12.3)")
                if not is_time(c.get("retrieved_at")):
                    p87.append(f"{w}: entry {c.get('path')} has retrieved_at {c.get('retrieved_at')!r}")
            if rb is not None:
                continue  # 17.5: a rollback manifest copies its entries (T89)
            prev_entries = {c.get("segment"): c for c in rx_csv_refs((prev or {}).get("series", {}).get(sid, {}))}
            prev_objs = rx_seg_objects(prev_s, sid)
            for c, o in zip(csvs, objs):
                seg = c.get("segment")
                po = prev_objs.get(seg)
                n_carry += 1
                if po is not None and po.get("sha256") == o.get("sha256") and seg in prev_entries:
                    want, why = prev_entries[seg].get("retrieved_at"), f"the entry of {good[idx - 1][0]}, whose snapshot names the same object"
                else:
                    want, why = state.get("retrieved_at"), "the series' retrieved_at in this snapshot, the object being new"
                if c.get("retrieved_at") != want:
                    p88.append(f"{w} segment {seg}: retrieved_at {c.get('retrieved_at')}, 12.9 gives {want} ({why})")
        if rb is not None:
            n_rb += 1
            target = rb.get("to")
            ref = None
            for jname, jm in good[:idx]:
                if (jm.get("snapshot") or {}).get("id") == target:
                    ref = (jname, jm)
            if ref is None:
                p89.append(f"{name}: no archived manifest before it names the rollback target {target}")
            else:
                for sid in sorted(ctx.reg_ids):
                    a, b = rx_csv_refs(m.get("series", {}).get(sid, {})), rx_csv_refs(ref[1].get("series", {}).get(sid, {}))
                    if a != b:
                        p89.append(f"{name} {sid}: csvs differ from those of {ref[0]}, the newest archived manifest naming the target {target} (12.9, 17.5)")
    # T90, T91: what lies in live/ and archive/files under series/
    for base in (rv.live, rv.arch):
        for f in rv.files(base):
            if not f.startswith("series/"):
                continue
            if RX_FULL_CSV_PATH.fullmatch(f) or RX_COPY_PATH.fullmatch(f):
                p90.append(f"{rv.name(base)}/{f} is a full-history CSV (9, 16: none is published or archived)")
                continue
            mt = RX_CSV_PATH.fullmatch(f)
            if not mt:
                p91.append(f"{rv.name(base)}/{f} is not series/<id>/<segment>/<16 hex>.csv")
                continue
            if f not in first_named:
                p91.append(f"{rv.name(base)}/{f} is named by no archived manifest (13, 17.1)")
            elif sha256_hex(rv.read(base, f)) not in named_sha[f]:
                p91.append(f"{rv.name(base)}/{f} has sha256 {sha256_hex(rv.read(base, f))[:16]}, the manifests name {sorted(named_sha[f])}")
    # T92: never written again
    for path, (idx, name, sid, seg, is_rb) in sorted(first_named.items()):
        if is_rb:
            p92.append(f"{path} first appears in the rollback manifest {name}; a rollback writes no CSV (17.5)")
            continue
        if idx == 0:
            continue
        cur = ctx.snaps.get((good[idx][1].get("snapshot") or {}).get("id"))
        prev = ctx.snaps.get((good[idx - 1][1].get("snapshot") or {}).get("id"))
        o, po = rx_seg_objects(cur, sid).get(seg), rx_seg_objects(prev, sid).get(seg)
        if (o is not None and po is not None and o.get("sha256") == po.get("sha256") and ctx.st.series.get(sid, {}).get("source") == NYFED
                and good[idx][1].get("schema") == MANIFEST_V4 and good[idx - 1][1].get("schema") != MANIFEST_V4):
            continue  # 22.9 (v0.8): the first accepting run after the registry change rewrites the New York Fed CSV segments under new paths
        if o is not None and po is not None and o.get("sha256") == po.get("sha256"):
            p92.append(f"{path} first appears in {name} although segment {seg} of {sid} has the same object as in the manifest it replaces {good[idx - 1][0]}: an unchanged segment written again (16, appendix C1)")
    # T93: every version is recoverable by its hash
    versions = {}
    for path, shas in sorted(named_sha.items()):
        data = rv.read(rv.arch, path)
        for sha in shas:
            if data is None:
                p93.append(f"archive/files/{path} is missing; a manifest names it with sha256 {str(sha)[:16]}")
            elif sha256_hex(data) != sha:
                p93.append(f"archive/files/{path} has sha256 {sha256_hex(data)[:16]}, a manifest names {str(sha)[:16]}")
        _, _, sid, seg, _ = first_named[path]
        versions.setdefault((sid, seg), []).append(path)
    revised = sum(1 for v in versions.values() if len(v) > 1)
    check("T87 every manifest's csvs has one entry per object, with the same segments in the same order, each {segment, path, sha256, retrieved_at} at series/<id>/<segment>/<16 hex>.csv; empty when not yet published (9, 12.3, 12.9, 16)", p87,
          f"{len(good)} manifests, {n_entries} entries")
    check("T88 the retrieval time of every CSV segment follows the carry rule: the entry of the manifest it replaces when that manifest's snapshot names the same object, else the series' retrieved_at in this snapshot (12.9, 16), across every archived manifest", p88,
          f"{n_carry} entries in non-rollback manifests")
    check("T89 a rollback manifest names exactly the CSV entries of the newest archived manifest that names its target (12.9, 17.5)", p89, f"{n_rb} rollback manifest(s)")
    check("T90 no full-history CSV anywhere: no series/<id>/<16 hex>.csv or series/<id>.csv in live/ or archive/files, no manifest csv reference (9, 16, appendix C1)", p90)
    check("T91 every CSV file in live/ and archive/files is a segment CSV named, with its SHA-256, by an archived manifest (13, 17.1; the scenario has no crash, so no orphan is expected)", p91,
          f"{len(first_named)} CSV paths named")
    check("T92 an unchanged segment is never written again: each archived CSV first appears in the first manifest or in one whose snapshot changed that segment's object; no rollback manifest introduces one (16, 17.5, appendix C1)", p92,
          f"{len(first_named)} CSV segments")
    check("T93 every CSV version any archived manifest named is in archive/files and matches its SHA-256: earlier versions of revised segments stay recoverable by hash (13, 16)", p93,
          f"{len(versions)} segments, {revised} with more than one version")


# --- T94 to T97: review authorization, refusals, publication outcomes, held candidates (11.5, 17.1, 17.5) ---


def rc_review_authorization(ctx):
    perms = rx_policy_permissions(ctx)
    p, n, n_wd = [], 0, 0
    for i, d in enumerate(rx_decisions(ctx)):
        w = f"decisions[{i}] {d.get('series')} {d.get('decision')} in run {d.get('run')}"
        if d.get("decision") in ("approve", "reject", "clear"):  # 11.5 (v0.5): clear is authorized like the others
            n += 1
            if d.get("reviewer_permission") not in perms:
                p.append(f"{w}: reviewer_permission {d.get('reviewer_permission')!r} is not one of family_policy.review.permissions {perms} (11.5)")
            pc, da = d.get("permission_checked_at"), d.get("decided_at")
            if not (is_time(pc) and is_time(da)):
                p.append(f"{w}: permission_checked_at {pc!r} or decided_at {da!r} is not a time")
            else:
                gap = (parse_utc(da) - parse_utc(pc)).total_seconds()
                if gap < 0:
                    p.append(f"{w}: permission read at {pc}, after the decision at {da} (11.5)")
                elif gap > PERMISSION_WINDOW_SECONDS:
                    p.append(f"{w}: permission read at {pc}, {int(gap)} seconds before the decision, more than 3,600 (11.5)")
            if not is_str(d.get("reviewer")) or rx_automation_login(d.get("reviewer")):
                p.append(f"{w}: reviewer {d.get('reviewer')!r} is not a person's login (11.5: no [bot], no github-actions)")
            if not is_str(d.get("reason")):
                p.append(f"{w}: no reason (11.5: a required text)")
        elif d.get("decision") == "withdrawn":
            n_wd += 1
            bad = [f for f in ("reviewer", "reviewer_permission", "permission_checked_at", "reason") if d.get(f) is not None]
            if bad:
                p.append(f"{w}: {bad} are not null; 17.5 gives all four null for withdrawn")
    check("T94 every approve, reject and clear carries a reviewer_permission within family_policy.review.permissions, read not after the decision and at most 3,600 seconds before it, a person's login (no [bot], no github-actions) and a reason; withdrawn carries all four null (no automatic approval) (4.2, 11.5, 17.5)", p,
          f"{n} person decision(s), {n_wd} withdrawal(s)")


def rc_refusals(ctx):
    perms = rx_policy_permissions(ctx)
    recs = rx_run_records(ctx)
    p, by_run, n_amb = [], {}, 0
    want_keys = {"series", "candidate_sha256", "decision", "reviewer", "reviewer_permission", "permission_checked_at", "at", "run", "refused"}
    refusals = rx_refusals(ctx)
    for i, r in enumerate(refusals):
        w = f"refusals[{i}] run {r.get('run')}"
        if set(r) != want_keys:
            p.append(f"{w}: fields {sorted(r)}; 17.5 gives exactly {sorted(want_keys)} (a refusal keeps no free text)")
        by_run.setdefault(r.get("run"), []).append(r)
        rec = recs.get(r.get("run"))
        if rec is None:
            p.append(f"{w}: no run record")
            continue
        if rec.get("trigger") != "review" or rec.get("outcome") != "refused" or rec.get("snapshot") is not None or rec.get("absences") != []:
            p.append(f"{w}: its run record has trigger {rec.get('trigger')}, outcome {rec.get('outcome')}, snapshot {rec.get('snapshot')}; 17.5 gives review, refused, null, absences empty")
        at = r.get("at")
        if at != rec.get("started_at") or not is_time(at):
            p.append(f"{w}: at {at!r} is not the run's now {rec.get('started_at')}")
            continue
        if snapshot_id_of(parse_utc(at)) in ctx.snaps:
            p.append(f"{w}: a snapshot was written at the refused run's time")
        before = rx_manifest_at(ctx, at, inclusive=False)
        after = rx_manifest_at(ctx, str(rec.get("ended_at")), inclusive=True)
        if before[0] != after[0]:
            p.append(f"{w}: the manifest in place changed from {before[0]} to {after[0]} during the refused run (11.5: a refused attempt changes no published, held or frozen state)")
        state = ctx.snaps.get(((before[1] or {}).get("snapshot") or {}).get("id")) or {}
        held = {h.get("series"): (h.get("candidate") or {}).get("sha256") for h in state.get("holds", [])}
        locks = lock_shas(rx_locks_of(ctx, before[1]))  # 11.5: the locks in force at the start, series to their hashes (v0.6)
        pc = r.get("permission_checked_at")
        first, order = refusal_rule(r.get("decision"), r.get("series"), r.get("candidate_sha256"), r.get("reviewer"), r.get("reviewer_permission"), pc, at, held, locks, perms)
        got = r.get("refused")
        if got not in order:
            p.append(f"{w}: refused {got!r} is not a rule 17.5 gives for the decision {r.get('decision')!r} ({', '.join(order)})")
        elif got == first:
            pass
        elif got == "missing-text" and (first is None or order.index(first) > order.index("missing-text")):
            n_amb += 1  # reading: an empty reason refuses by missing-text, and the reason is not kept, so this cannot be told
        else:
            p.append(f"{w}: refused by {got}, the rules checked in the order of 17.5 give {first} (series held: {r.get('series') in held}, locked: {r.get('series') in locks}, permission {r.get('reviewer_permission')!r}, read at {pc})")
    for rid, rec in sorted(recs.items(), key=lambda kv: str(kv[0])):
        if rec.get("outcome") == "refused" and len(by_run.get(rid, [])) != 1:
            p.append(f"run {rid}: outcome refused with {len(by_run.get(rid, []))} refusal entries in review-queue.json; 17.5 appends one")
    at_list = [str(r.get("at")) for r in refusals]
    if at_list != sorted(at_list):
        p.append("refusals are not in time order (append-only)")
    check("T95 every refusal names the rule that refused it, the first that fails in the order of 17.5 (for clear: not-locked, stale-candidate, missing-text, permission, permission-time, automation; for any other decision: not-held, stale-candidate, bad-decision, locked, missing-text, permission, permission-time, automation), against the holds and locks in force when the run started; keeps who asked for what and no free text, belongs to a refused review run at its time, and changes nothing: no snapshot, no manifest (11.5, 14.1, 17.5)", p,
          f"{len(refusals)} refusal(s)" + (f"; {n_amb} by missing-text where only an empty reason, not kept, can explain it" if n_amb else ""))


def rc_publication_outcomes(ctx):
    rv, recs = ctx.rv, rx_run_records(ctx)
    p, n = [], 0
    want_outcome = {"approve": "published", "reject": "frozen", "withdrawn": "withdrawn", "clear": "cleared"}
    for i, d in enumerate(rx_decisions(ctx)):
        n += 1
        w = f"decisions[{i}] {d.get('series')} {d.get('decision')}"
        pub = d.get("publication") if isinstance(d.get("publication"), dict) else {}
        if pub.get("outcome") != want_outcome.get(d.get("decision")):
            p.append(f"{w}: publication.outcome {pub.get('outcome')!r}, 17.5 gives {want_outcome.get(d.get('decision'))!r}")
        rec = recs.get(d.get("run"))
        snap_id = pub.get("snapshot")
        if rec is None or rec.get("snapshot") != snap_id:
            p.append(f"{w}: publication.snapshot {snap_id} is not the snapshot its run {d.get('run')} wrote ({(rec or {}).get('snapshot')})")
        s = ctx.snaps.get(snap_id)
        if s is None:
            p.append(f"{w}: snapshot {snap_id} is not in the archive")
            continue
        if not any(not e and (m.get("snapshot") or {}).get("id") == snap_id and m.get("rollback") is None and m.get("generated_at") == d.get("decided_at") for _, m, e in ctx.arch_manifests):
            p.append(f"{w}: no archived manifest generated at {d.get('decided_at')} published snapshot {snap_id}")
        sid, sha = d.get("series"), d.get("candidate_sha256")
        state = s.get("series", {}).get(sid, {})
        if any(h.get("series") == sid for h in s.get("holds", [])):
            p.append(f"{w}: snapshot {snap_id} still holds {sid}")
        if d.get("decision") == "approve":
            cand, err = rv.load(rv.holds, f"{sid}/{str(sha)[:16]}.json")
            if err or canon_bytes(cand) != canon_bytes(rx_obs(ctx, state)) or state.get("status") != "refreshed":
                p.append(f"{w}: snapshot {snap_id} does not publish exactly the candidate {str(sha)[:16]} (status {state.get('status')})")
        elif d.get("decision") == "reject":
            if (sid, "rejected", sha) not in rx_frozen(s) or state.get("status") != "carried-forward":
                p.append(f"{w}: snapshot {snap_id} does not lock {sid} with origin rejected on candidate {str(sha)[:16]} (locks {sorted(map(_k16, rx_frozen(s)))}, status {state.get('status')})")
        elif d.get("decision") == "clear":
            # 11.5, 17.5 (v0.5, v0.6): the lock named by its hash lifted in that snapshot, nothing published in that run.
            before = rx_locks_at(ctx, d["decided_at"], inclusive=False) if is_time(d.get("decided_at")) else {}
            m_now = next((m for _, m, e in ctx.arch_manifests if not e and (m.get("snapshot") or {}).get("id") == snap_id and m.get("generated_at") == d.get("decided_at")), None)
            base = ctx.snaps.get(rx_base_id(ctx, snap_id)) or {}
            if not any(k[0] == sid and k[2] == sha for k in before):
                p.append(f"{w}: no lock on candidate {str(sha)[:16]} was in force before the run")
            if any(k[0] == sid and k[2] == sha for k in rx_locks_of(ctx, m_now)):
                p.append(f"{w}: snapshot {snap_id} still has the lock of {sid} on candidate {str(sha)[:16]}")
            if state.get("status") != "carried-forward" or state.get("objects") != base.get("series", {}).get(sid, {}).get("objects"):
                p.append(f"{w}: snapshot {snap_id} publishes something for {sid} (status {state.get('status')}); a clear publishes nothing in its own run")
        elif d.get("decision") == "withdrawn":
            base = ctx.snaps.get(rx_base_id(ctx, snap_id)) or {}
            if state.get("objects") != base.get("series", {}).get(sid, {}).get("objects") or state.get("status") != "unchanged":
                p.append(f"{w}: snapshot {snap_id} publishes something for {sid} (status {state.get('status')}); a withdrawal publishes nothing from the candidate")
    check("T96 every decision's publication outcome agrees with the snapshots and manifests: approve published in the snapshot its review run wrote (exactly the candidate), reject frozen from it (a rejected lock), withdrawn closed in it with nothing published from the candidate, clear cleared in it (the lock lifted, nothing published); that snapshot was published at the decision time (11.5, 17.5)", p,
          f"{n} decision(s)")


def rc_candidates_kept(ctx):
    rv = ctx.rv
    p = []
    held_ever, replaced, current = {}, set(), {}
    for sid_ in ctx.order:
        s = ctx.snaps[sid_]
        now_held = {}
        for h in s.get("holds", []):
            key = (h.get("series"), (h.get("candidate") or {}).get("sha256"))
            held_ever.setdefault(key, sid_)
            now_held[h.get("series")] = key[1]
        for series_id, sha in now_held.items():
            if current.get(series_id) not in (None, sha):
                replaced.add((series_id, current[series_id]))
        current = now_held
    decided = {(d.get("series"), d.get("candidate_sha256")): d.get("decision") for d in rx_decisions(ctx)}
    _, _, lock_first, _ = rx_lock_history(ctx)
    lock_cands = {(k[0], k[2]) for k in lock_first}
    rolled = {k for k in lock_cands if k not in held_ever}  # 17.5 (v0.5): a rollback's locked candidate was never held
    for (series_id, sha), first in sorted(held_ever.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        data = rv.read(rv.holds, f"{series_id}/{str(sha)[:16]}.json")
        if data is None:
            p.append(f"{series_id} candidate {str(sha)[:16]} (first held in {first}) is not in archive/holds/ (11.5: every candidate ever held stays)")
        elif sha256_hex(data) != sha:
            p.append(f"archive/holds/{series_id}/{str(sha)[:16]}.json has sha256 {sha256_hex(data)[:16]}, the hold names {str(sha)[:16]}")
    for key, dec in decided.items():
        if key not in held_ever and not (dec == "clear" and key in lock_cands):
            p.append(f"the {dec} decision on {key[0]} candidate {str(key[1])[:16]} names a candidate no snapshot ever held")
    doc, _ = rv.load(rv.state, "review-queue.json")
    for e in ((doc or {}).get("frozen") or []) + ((doc or {}).get("open") or []) if isinstance(doc, dict) else []:
        if isinstance(e, dict) and (e.get("series"), e.get("candidate_sha256")) not in held_ever and (e.get("series"), e.get("candidate_sha256")) not in rolled:
            p.append(f"review-queue entry for {e.get('series')} candidate {str(e.get('candidate_sha256'))[:16]} was never held by a snapshot nor locked by a rollback")
    held_files = {f"{k[0]}/{str(k[1])[:16]}.json" for k in set(held_ever) | rolled}
    for f in rv.files(rv.holds):
        if f not in held_files:
            p.append(f"archive/holds/{f} was held by no snapshot and is no rollback's locked candidate")
    cats = {"replaced": len(replaced), "approved": sum(1 for v in decided.values() if v == "approve"), "rejected": sum(1 for v in decided.values() if v == "reject"),
            "withdrawn": sum(1 for v in decided.values() if v == "withdrawn"), "open": len(current), "rolled-back locked candidates": len(rolled)}
    check("T97 every candidate ever held (replaced, rejected, withdrawn, approved, open) is in archive/holds/ and matches its SHA-256; every file there was held by a snapshot or is a rollback's locked candidate; every decided or queued candidate was held or locked by a rollback (11.5, 17.1, 17.5)", p,
          f"{len(held_ever)} candidate(s): " + ", ".join(f"{k} {v}" for k, v in cats.items()))


# --- T98 to T102: absences, unknown zones, due, route alerts, windowed candidates (5, 11.6, 14.2, 17.3, 17.8) ---


def rx_candidate_lookup(ctx, snapshot, manifest=None, rec=None):
    """has_record(series, period) for the held candidates of a snapshot and the locked
    candidates in force under its manifest (11.6; v0.5: the locks include rollback.locked;
    v0.6: every lock of a series, and the rollback record's locks).
    v0.6: a locked series' candidate of this run is kept nowhere, yet 11.6 does not list a period
    present in it. reading: for a locked series whose outcome is revised-unexpected, a period is
    taken as present when a series sharing its request (11.3) whose candidate of this run is
    published or held after the run has it (Debt to the Penny gives every record date an
    observation in all three series, 17.3); with no such series to tell, the period is optional."""
    held = {h.get("series"): (h.get("candidate") or {}).get("sha256") for h in (snapshot or {}).get("holds", [])}
    locks = rx_locks_of(ctx, manifest) if manifest else rx_frozen(snapshot)
    shas = {}
    for sid, sha in held.items():
        shas.setdefault(sid, set()).add(sha)
    for k in locks:
        shas.setdefault(k[0], set()).add(k[2])
    cache = {}
    outcomes = (rec or {}).get("series") or {}
    grp = request_group_of(ctx.st)
    states = (snapshot or {}).get("series") or {}

    def periods_of(sid, sha):
        if (sid, sha) not in cache:
            v, err = ctx.rv.load(ctx.rv.holds, f"{sid}/{str(sha)[:16]}.json")
            cache[(sid, sha)] = {observation_key(o) for o in v if isinstance(o, dict)} if not err and isinstance(v, list) else set()
        return cache[(sid, sha)]

    def sibling_periods(sid):
        key = ("siblings", sid)
        if key not in cache:
            found = None
            for other, ser in ctx.st.series.items():
                if other == sid or grp.get(other) != grp.get(sid) or ser["frequency"] != ctx.st.series[sid]["frequency"]:
                    continue
                if lock_series(locks) & {other} or outcomes.get(other) not in ("appended", "revised-expected", "unchanged", "revised-unexpected"):
                    continue
                if other in held:
                    found = (found or set()) | periods_of(other, held[other])
                elif outcomes.get(other) != "revised-unexpected":
                    found = (found or set()) | {observation_key(o) for o in rx_obs(ctx, states.get(other) or {}) if isinstance(o, dict)}
            cache[key] = found
        return cache[key]

    def has_record(sid, period):
        if any(period in periods_of(sid, sha) for sha in shas.get(sid, ())):
            return True
        if sid in lock_series(locks) and sid not in held and outcomes.get(sid) == "revised-unexpected":
            sib = sibling_periods(sid)
            return True if sib is None else period in sib
        return False
    return has_record


def rc_absences(ctx):
    st = ctx.st
    p98, p99 = [], []
    n_runs, n_entries, n_opt, n_quiet = 0, 0, 0, 0
    for rec in rx_records_in_time(ctx):
        if not (is_time(rec.get("started_at")) and is_time(rec.get("ended_at"))):
            p98.append(f"run {rec.get('id')}: no started_at or ended_at")
            continue
        _, m_after = rx_manifest_at(ctx, rec["ended_at"], inclusive=True)
        s_after = ctx.snaps.get(((m_after or {}).get("snapshot") or {}).get("id"))
        try:
            pr, cnt = absences_problems(st, rec, (s_after or {}).get("series", {}), rx_candidate_lookup(ctx, s_after, m_after, rec))
        except Exception as exc:
            pr, cnt = [f"run {rec.get('id')}: cannot be recomputed ({type(exc).__name__}: {exc})"], {}
        p98 += pr
        if cnt.get("expected") is None:
            n_quiet += 1
        else:
            n_runs += 1
        n_entries += cnt.get("entries", 0)
        n_opt += cnt.get("optional", 0)
        # T99: the alerts that go with the absences (11.6, 17.8)
        alerts = set(rec.get("alerts") or [])
        ab = [e for e in rec.get("absences") or [] if isinstance(e, dict)]
        over = {e.get("series") for e in ab if e.get("detail") == "after-deadline"}
        for sid in sorted(ctx.reg_ids):
            if f"source-overdue:{sid}" in alerts and sid not in over:
                p99.append(f"run {rec.get('id')}: source-overdue:{sid} raised without an after-deadline absence of {sid} (17.8)")
            elif sid in over and f"source-overdue:{sid}" not in alerts:
                p99.append(f"run {rec.get('id')}: an after-deadline absence of {sid} without the warning source-overdue:{sid} (11.6, 17.8)")
        for sid in sorted(over & ctx.reg_ids):
            src = st.series[sid]["source"]
            bad = [f"{h}:{src}" for h in COLLECTION_ALERT_HEADS if f"{h}:{src}" in alerts] + [f"{h}:{sid}" for h in COLLECTION_ALERT_SERIES_HEADS if f"{h}:{sid}" in alerts]
            if bad:
                p99.append(f"run {rec.get('id')}: {sid} is source-overdue but the collection alerts {bad} are raised in the same run (11.6: none of them is)")
        for sid in sorted({e.get("series") for e in ab if e.get("detail") == "inside-history"}):
            if f"source-gap:{sid}" not in alerts:
                p99.append(f"run {rec.get('id')}: undocumented gaps of {sid} without the alert source-gap:{sid} (11.4, 11.6)")
    check("T98 every run record's absences are exactly 11.6: for a run that sent requests, each requested business-day or monthly series published after the run, every weekday after last_period to the run's ET date (holiday, known-gap, not-yet-due by the latest reading, fetch-failed, response-invalid, after-deadline) or the month after it, then its undocumented gaps; empty for a run that sent none", p98,
          f"{n_runs} requesting run(s) recomputed, {n_quiet} without requests, {n_entries} entries"
          + (f"; {n_opt} period(s) that a held or frozen candidate holds accepted listed or not (11.6 allows both readings, see the report)" if n_opt else ""))
    check("T99 source-overdue:<series> is raised exactly in a run whose absences hold an after-deadline entry for it, with none of the collection alerts of its source or series; undocumented gaps come with source-gap:<series> (11.6, 17.8)", p99)


def rc_due(ctx):
    """T100: the groups a collecting run requested are the groups due by 17.3, with the
    earliest reading of an unknown zone and the next unseen period skipping documented gaps."""
    st = ctx.st
    grp = request_group_of(st)
    order = [s["id"] for s in st.registry.get("series", [])]
    groups = sorted(set(grp.values()), key=order.index)
    p, n, skipped = [], 0, []
    for rec in rx_records_in_time(ctx):
        if rec.get("trigger") not in ("schedule", "manual"):
            continue
        outcomes = rec.get("series") or {}
        if set(outcomes) != ctx.reg_ids and rec.get("outcome") != "nothing-due":
            if rec.get("outcome") in ("failed", "gate-failed"):
                # reading: a run that ended on an error (17.2) may record no per-series outcomes.
                skipped.append(f"{rec.get('id')} ({rec.get('outcome')}, {len(outcomes)} series outcomes)")
            else:
                p.append(f"run {rec.get('id')}: outcome {rec.get('outcome')} with outcomes for {len(outcomes)} of {len(ctx.reg_ids)} series (14.1: per-series outcomes)")
            continue
        if not is_time(rec.get("started_at")):
            continue
        n += 1
        now = parse_utc(rec["started_at"])
        state = rx_state_at(ctx, rec["started_at"], inclusive=False)
        today = et_date(now)
        due = {}
        plan_rows = rx_full_plan(ctx)["runs"].get(rec.get("id"), {})
        for g in groups:
            members = [s for s in order if grp[s] == g]
            why = []
            row = plan_rows.get(g)
            if row is not None and row["weekly"]:
                why.append("weekly full fetch due (Sunday ET, no successful full fetch of the group that day yet, v0.7)")
            for sid in members:
                stt = (state or {}).get("series", {}).get(sid) or {}
                if not stt.get("objects"):
                    why.append(f"{sid} not yet published")
                    continue
                if any(h.get("series") == sid for h in (state or {}).get("holds", [])):
                    why.append(f"{sid} held")
                exp, _ = deadline_for(st, sid, stt.get("last_period"), stt.get("source_marker"), reading="earliest", grace=False)
                if exp is not None and exp <= now:
                    why.append(f"{sid}: next unseen period expected {fmt_utc(exp)}")
                if st.series[sid]["class"] == "market_observation" and today == next_business_day(parse_date(stt["last_period"])):
                    why.append(f"{sid}: publication day of its last_period")
            if why:
                due[g] = why
        req = requested_groups(st, rec)
        if set(due) != req:
            p.append(f"run {rec.get('id')} at {rec['started_at']}: requested {sorted(req)}, 17.3 makes due {sorted(due)} ({'; '.join(f'{g}: {due[g][0]}' for g in sorted(due))})")
        if rec.get("outcome") == "nothing-due" and due:
            p.append(f"run {rec.get('id')}: nothing-due although {sorted(due)} are due")
    check("T100 every collecting run requested exactly the groups 17.3 makes due: a series not yet published or held, the weekly full fetch (Sunday ET, once per group per Sunday: no successful full fetch of the group that ET date yet, v0.7), the expected publication time of a series' next unseen period (skipping documented gaps; the earliest reading of an unknown zone, 21:15 UTC for Fiscal Data) not after now, or an EFFR publication day (4.5, 14.2, 17.3)", p,
          f"{n} run(s)" + (f"; {len(skipped)} without per-series outcomes not recomputable: {', '.join(skipped[:3])}" if skipped else ""))


def rc_route_alerts(ctx):
    st, p, n = ctx.st, [], 0
    for rec in rx_records_in_time(ctx):
        if not is_time(rec.get("started_at")):
            continue
        n += 1
        want = route_alerts(st, et_date(parse_utc(rec["started_at"])))
        got = {k for k in rec.get("alerts") or [] if str(k).startswith(("source-retirement:", "source-route-check:"))}
        if set(want) != got:
            p.append(f"run {rec.get('id')} on {et_date(parse_utc(rec['started_at']))}: route alerts {sorted(got)}, 17.8 gives {sorted(want)}")
    check("T101 every run record carries source-retirement:<source> and source-route-check:<source> exactly when its ET date is inside the window of a route_notices entry (17.8; reading: route alerts are current in every run, whatever its trigger)", p,
          f"{n} run(s); windows {', '.join(e['date'] for s in st.registry['sources'].values() for e in s.get('route_notices') or [])}")


def rc_windowed(ctx):
    st, rv = ctx.st, ctx.rv
    grp = request_group_of(st)
    p, n = [], 0
    p112, n112 = [], 0

    def before_start(obs, start):
        return [o for o in obs if isinstance(o, dict) and str(observation_key(o)) < start]

    def load_cand(sid, sha):
        v, err = rv.load(rv.holds, f"{sid}/{str(sha)[:16]}.json")
        return v if not err and isinstance(v, list) else None

    for rec in rx_records_in_time(ctx):
        if rec.get("trigger") not in ("schedule", "manual") or not is_time(rec.get("started_at")) or not is_time(rec.get("ended_at")):
            continue
        before = rx_state_at(ctx, rec["started_at"], inclusive=False)
        after = rx_state_at(ctx, rec["ended_at"], inclusive=True)
        if before is None or after is None:
            continue
        today = et_date(parse_utc(rec["started_at"]))
        start = (today - dt.timedelta(days=59)).isoformat()
        outcomes = rec.get("series") or {}
        locks_b = rx_locks_at(ctx, rec["started_at"], inclusive=False)
        locks_a = rx_locks_at(ctx, rec["ended_at"], inclusive=True)
        plan_rows = rx_full_plan(ctx)["runs"].get(rec.get("id"), {})
        for g in sorted(requested_groups(st, rec)):
            members = [s for s in st.series if grp[s] == g]
            row = plan_rows.get(g)
            if (row is not None and row["full"]) or any(st.series[s]["frequency"] == "month" for s in members) \
                    or any(not (before.get("series", {}).get(s) or {}).get("objects") for s in members):
                continue  # 17.3: the window is full
            for sid in members:
                if outcomes.get(sid) in (None, "failed", "invalid", "not-due"):
                    continue
                n += 1
                b_state, a_state = before["series"].get(sid, {}), after["series"].get(sid, {})
                b_hold = next(((h.get("candidate") or {}).get("sha256") for h in before.get("holds", []) if h.get("series") == sid), None)
                a_hold = next(((h.get("candidate") or {}).get("sha256") for h in after.get("holds", []) if h.get("series") == sid), None)
                published = rx_obs(ctx, b_state)
                # 5 (v0.6, E3): a locked series assembles its windowed candidate like any other series:
                # over its held candidate when held, else over the published observations; never over a locked candidate.
                if b_hold:
                    base, label = load_cand(sid, b_hold), f"the held candidate {str(b_hold)[:16]}"
                else:
                    base, label = published, "the published observations"
                for k, lk in sorted(locks_b.items(), key=lambda kv: tuple(map(str, kv[0]))):
                    if k[0] != sid:
                        continue
                    # T112 (v0.6): a lock with a locked change before the window's first period stays in force
                    # on a windowed run whatever the candidate shows; only a request covering every locked change lifts it.
                    _, locked, changes = rx_lock_detail(ctx, sid, lk)
                    old = [c for c in (changes or []) if str(c[0]) < start]
                    if not old:
                        continue
                    n112 += 1
                    if k not in locks_a:
                        p112.append(f"run {rec.get('id')} {sid} (window from {start}): the {k[1]} lock {str(k[2])[:16]} was lifted although {len(old)} of its locked change(s) lie before the window, e.g. {old[:2]} (5, 11.5 v0.6: it stays in force on that run)")
                    if a_hold and not b_hold and k in locks_a:
                        p112.append(f"run {rec.get('id')} {sid}: newly held while its lock {str(k[2])[:16]} stands (17.3: a locked series is not held again)")
                if base is None:
                    p.append(f"run {rec.get('id')} {sid}: the held candidate {str(b_hold)[:16]} is not readable")
                    continue
                w = f"run {rec.get('id')} {sid} (window from {start})"
                if a_hold:
                    cand = load_cand(sid, a_hold)
                    if cand is not None and before_start(cand, start) != before_start(base, start):
                        p.append(f"{w}: the held candidate {str(a_hold)[:16]} before the window differs from {label}; 5 (v0.6) assembles a held series' candidate over its held candidate and every other series' (a locked one too) over the published observations")
                elif a_state.get("objects") != b_state.get("objects"):
                    if before_start(rx_obs(ctx, a_state), start) != before_start(base, start):
                        p.append(f"{w}: the observations published before the window differ from {label} in a windowed run (5: periods before the window come from it)")
                elif b_hold and not a_hold:
                    if before_start(base, start) != before_start(published, start):
                        p.append(f"{w}: the hold was withdrawn as an exact return, but the held candidate's history before the window differs from the published data, so the assembled candidate could not equal it (5, 11.5)")
    check("T102 windowed candidates (5 v0.6; v0.7: a later Sunday run is windowed too): in a run that requests a 60-day window, the observations before the window come from the held candidate for a held series and from the published observations for every other series, a locked one included (never from a locked candidate); a published series never changes before the window otherwise", p,
          f"{n} series candidate(s) in windowed runs")
    check("T112 a lock with a locked change before the window's first period stays in force on a windowed run whatever the candidate shows, and its series is not held again; only a request covering every locked change can lift it (5, 11.5 v0.6)", p112,
          f"{n112} lock(s) with a locked change before the window in windowed runs")


def rc_provenance(ctx):
    p, n = [], 0
    for sid_ in ctx.order:
        s = ctx.snaps[sid_]
        base_id = rx_base_id(ctx, sid_)
        base = ctx.snaps.get(base_id)
        if (s.get("run") or {}).get("trigger") == "review":
            # 17.2, 17.5: a review run fetches nothing and decides one hold.
            base_holds = {h.get("series"): h for h in (base or {}).get("holds", [])}
            reviewed = sorted(x for x in base_holds if x not in {h.get("series") for h in s.get("holds", [])})
            # v0.5: a clear removes one lock and no hold; approve and reject remove one hold.
            m_now = next((m for _, m, e in ctx.arch_manifests if not e and m.get("generated_at") == s.get("created_at") and (m.get("snapshot") or {}).get("id") == sid_), None)
            locks_before = rx_locks_at(ctx, s["created_at"], inclusive=False) if is_time(s.get("created_at")) else {}
            cleared = sorted({k[0] for k in locks_before if k not in rx_locks_of(ctx, m_now)}) if m_now else []  # v0.6: series whose lock(s) were lifted
            if len(reviewed) + len(cleared) != 1:
                p.append(f"{sid_}: a review run removes the hold or the lock of the reviewed series and nothing else; holds removed against {base_id}: {reviewed}, locks lifted: {cleared}")
            reviewed = reviewed + cleared
            for series_id, state in sorted(s.get("series", {}).items()):
                n += 1
                status, w = state.get("status"), f"{sid_} {series_id}"
                old = (base or {}).get("series", {}).get(series_id) or {}
                kept = [f for f in ("objects", "retrieved_at", "checked_at") if state.get(f) != old.get(f)]
                if series_id in reviewed and status == "refreshed" and series_id in base_holds:
                    sha = (base_holds[series_id].get("candidate") or {}).get("sha256")
                    first = rx_first_held(ctx, series_id, sha)
                    t = ctx.snaps[first].get("created_at") if first else None
                    if not (state.get("retrieved_at") == state.get("checked_at") == t):
                        p.append(f"{w}: approved, so retrieved_at {state.get('retrieved_at')} and checked_at {state.get('checked_at')} must be the time {t} of the run that fetched the candidate, the one whose snapshot {first} first held it (17.2, 17.5)")
                    cand, cerr = ctx.rv.load(ctx.rv.holds, f"{series_id}/{str(sha)[:16]}.json")
                    if not cerr and canon_bytes(cand) != canon_bytes(rx_obs(ctx, state)):
                        p.append(f"{w}: the published observations are not exactly the held candidate {str(sha)[:16]} (11.5, 17.5)")
                elif series_id in reviewed:
                    if status != "carried-forward" or kept:
                        p.append(f"{w}: a rejected or cleared series is carried-forward with its objects and times kept; status {status}, changed {kept} (17.2, 17.5)")
                elif old.get("status") in ("held", "not-yet-published"):
                    if status != old.get("status") or kept:
                        p.append(f"{w}: in a review run a {old.get('status')} series stays as it is; status {status}, changed {kept} (17.2)")
                elif status != "carried-forward" or kept:
                    p.append(f"{w}: in a review run every other series is carried-forward with its objects, retrieved_at and checked_at kept; status {status}, changed {kept} (17.2)")
            continue
        for series_id, state in sorted(s.get("series", {}).items()):
            status = state.get("status")
            old = (base or {}).get("series", {}).get(series_id)
            w = f"{sid_} {series_id}"
            if status in ("carried-forward", "unchanged", "held"):
                n += 1
                rule = "12.5" if status == "carried-forward" else "8"
                if old is None or not old.get("objects"):
                    p.append(f"{w}: status {status} but the series was not published in {base_id}")
                    continue
                if state.get("objects") != old.get("objects"):
                    p.append(f"{w}: status {status} but its objects differ from those in {base_id} ({rule})")
                if state.get("retrieved_at") != old.get("retrieved_at"):
                    p.append(f"{w}: status {status} but retrieved_at {state.get('retrieved_at')} is not the {old.get('retrieved_at')} of {base_id} ({rule}: never restamped)")
            elif status == "refreshed" and old is not None and old.get("objects") and old.get("objects") == state.get("objects"):
                p.append(f"{w}: refreshed but its objects equal those in {base_id} (8: refreshed means appended or revised)")
            elif status == "not-yet-published" and old is not None and old.get("objects"):
                p.append(f"{w}: not-yet-published although {base_id} had published it")
    check("T61 provenance: a carried-forward series keeps its objects and retrieved_at exactly from the snapshot published before it; so do unchanged and held series; a refreshed one changed; a review run changes only the reviewed series (one hold closed, or one lock cleared), and an approved one is exactly the held candidate with the times of the run that fetched it (12.5, 8, 17.2, 17.5)", p, f"{n} states")


# --- T62 to T68: archive, holds, pins, the live window ---


def rc_archive(ctx):
    rv = ctx.rv
    p, n = [], 0
    for f in rv.files(rv.live):
        # 9 (v0.4): convenience copies at fixed paths exist only "if a later version adds any";
        # v0.4 adds none, so every live file but the manifest and status/ is archived.
        if f == "manifest.json" or f.startswith("status/") or f == "NOTICE.txt":  # 22.9: NOTICE.txt is live only
            continue
        n += 1
        a = rv.read(rv.arch, f)
        if a is None:
            p.append(f"live/{f} is not in archive/files/")
        elif a != rv.read(rv.live, f):
            p.append(f"live/{f} ({sha256_hex(rv.read(rv.live, f))[:16]}) differs from archive/files/{f} ({sha256_hex(a)[:16]})")
    check("T62 every file in live/ except manifest.json and status/ exists byte-identical at the same path in archive/files/ (17.1, 17.5, 12.4)", p, f"{n} files")

    p, named = [], set()
    for s in ctx.snaps.values():
        named |= set(rx_snapshot_files(s))
    for _, m, err in ctx.arch_manifests:
        if not err:
            named |= set(rx_manifest_files(m))
    orphans = 0
    for f in rv.files(rv.arch):
        data = rv.read(rv.arch, f)
        mt = (RX_OBJECT_PATH.fullmatch(f) or RX_CSV_PATH.fullmatch(f) or RX_LOG_PATH.fullmatch(f) or RX_REVCSV_PATH.fullmatch(f)
              or RX_REGCOPY_PATH.fullmatch(f) or RX_HOLCOPY_PATH.fullmatch(f) or RX_NOTICE_PATH.fullmatch(f))  # v0.8: revision CSVs and the rule files (10, 22.9)
        if mt:
            if mt.group(mt.lastindex) != sha256_hex(data)[:16]:
                p.append(f"archive/files/{f}: content sha256 starts {sha256_hex(data)[:16]}, the name says {mt.group(mt.lastindex)}")
            if f not in named:
                orphans += 1
        elif not RX_SNAPSHOT_PATH.fullmatch(f):
            p.append(f"archive/files/{f} is not an object, snapshot, revision log version, CSV path, revision CSV or rule file (17.1, 10, 22.9)")
        if len(data) > LIMIT_FILE:
            p.append(f"archive/files/{f} is {len(data)} bytes, over 5 MB (17.7)")
    check("T63 archive/files holds only objects, snapshots, revision log versions, CSV segments and, from v0.8, revision CSVs and the rule files (registry and holiday copies, notice files), each content-addressed file named by its own SHA-256 (17.1, 12.3, 10, 22.9)", p,
          f"{len(rv.files(rv.arch))} files" + (f", {orphans} named by no snapshot or manifest (orphans are kept, 17.4)" if orphans else ""))


def rc_holds(ctx):
    rv, st = ctx.rv, ctx.st
    p, candidates = [], {}
    for f in rv.files(rv.holds):
        mt = RX_HOLD_PATH.fullmatch(f)
        data = rv.read(rv.holds, f)
        if not mt:
            p.append(f"archive/holds/{f} is not <series>/<16 hex>.json (17.1)")
            continue
        if mt.group(2) != sha256_hex(data)[:16]:
            p.append(f"archive/holds/{f}: content sha256 starts {sha256_hex(data)[:16]}")
        v, err = rv.load(rv.holds, f)
        if err or not isinstance(v, list):
            p.append(f"archive/holds/{f}: not a JSON array of observations ({err})")
            continue
        if canonical_problem(data, v):
            p.append(f"archive/holds/{f}: not the canonical JSON of the array (11.5)")
        ser = st.series.get(mt.group(1))
        if ser is None:
            p.append(f"archive/holds/{f}: series not registered")
            continue
        errs = schema_errors({"schema": "rmf.econ.object/1", "series": mt.group(1), "segment": "all", "observations": v}, st.schemas["object"])
        if errs:
            p.append(f"archive/holds/{f}: elements are not observations ({errs[0]})")
            continue
        keys = [observation_key(o) for o in v]
        if keys != sorted(keys) or len(set(keys)) != len(keys):
            p.append(f"archive/holds/{f}: observations are not in period order without duplicates (11.5)")
        candidates[f] = v
    n = 0
    for sid_ in ctx.order:
        s = ctx.snaps[sid_]
        for h in s.get("holds", []):
            n += 1
            cand = h.get("candidate") or {}
            sha = cand.get("sha256")
            f = f"{h.get('series')}/{str(sha)[:16]}.json"
            data = rv.read(rv.holds, f)
            w = f"{sid_} hold on {h.get('series')}"
            if data is None:
                p.append(f"{w}: candidate archive/holds/{f} missing (17.1)")
                continue
            if sha256_hex(data) != sha:
                p.append(f"{w}: archive/holds/{f} has sha256 {sha256_hex(data)}, the snapshot says {sha}")
            if len(data) != cand.get("bytes"):
                p.append(f"{w}: archive/holds/{f} is {len(data)} bytes, the snapshot says {cand.get('bytes')}")
            first = rx_first_held(ctx, h.get("series"), sha)
            month = et_date(parse_utc(ctx.snaps[first]["created_at"])).isoformat()[:7]
            want_asset = f"archive-{month}/hold-{h.get('series')}-{str(sha)[:16]}.json"
            if cand.get("archive_asset") != want_asset:
                p.append(f"{w}: archive_asset {cand.get('archive_asset')!r}, 17.1 gives {want_asset!r} (ET month in which the candidate was first held, snapshot {first})")
            published = rx_obs(ctx, s.get("series", {}).get(h.get("series"), {}))
            if f in candidates and canon_bytes(candidates[f]) == canon_bytes(published):
                p.append(f"{w}: the held candidate equals the published observations")
    check("T64 held candidates: every hold of every snapshot has its candidate at archive/holds/<series>/<16 hex>.json with the stated SHA-256 and byte count, that hash is the SHA-256 of the canonical JSON array of observations, and archive_asset is archive-<YYYY-MM>/hold-<series>-<16 hex>.json (8, 11.5, 17.1)", p,
          f"{n} hold(s) in snapshots, {len(rv.files(rv.holds))} candidate file(s)")


def rc_pins(ctx):
    rv = ctx.rv
    doc, err = rv.load(rv.state, "pins.json")
    name = "T65 pins.json: schema rmf.econ.pins/1, each pin has snapshot, site_release, reason, pinned_at and names an archived snapshot; at most 12 (17.6)"
    if err:
        check(name, [f"archive/state/pins.json: {err}"])
        return
    p = shape_problems("pins.json", doc, {"schema": lambda x: x == "rmf.econ.pins/1", "pins": lambda x: isinstance(x, list)})
    pins = doc.get("pins") if isinstance(doc, dict) and isinstance(doc.get("pins"), list) else []
    for i, pin in enumerate(pins):
        p += shape_problems(f"pins[{i}]", pin, {"snapshot": is_snapshot_id, "site_release": is_str, "reason": is_str, "pinned_at": is_time})
        if isinstance(pin, dict) and is_snapshot_id(pin.get("snapshot")) and pin["snapshot"] not in ctx.snaps:
            p.append(f"pins[{i}]: snapshot {pin['snapshot']} is not in the archive")
    ids = [pin.get("snapshot") for pin in pins if isinstance(pin, dict)]
    if len(set(ids)) != len(ids):
        p.append("a snapshot is pinned twice")
    if len(pins) > LIMIT_PINS:
        p.append(f"{len(pins)} pins, the limit is {LIMIT_PINS} (a 13th pin is refused)")
    if isinstance(doc, dict) and "unpinned" in doc:
        if not isinstance(doc["unpinned"], list):
            p.append("unpinned is not a list")
        else:
            for i, u in enumerate(doc["unpinned"]):
                p += shape_problems(f"unpinned[{i}]", u, {"snapshot": is_snapshot_id, "reason": is_str})
    check(name, p, f"{len(pins)} pin(s)")


def rc_window(ctx):
    rv = ctx.rv
    snaps, files = rx_window(ctx)
    strong = set(rx_significant(ctx)) | {x.get("snapshot") for x in rx_pins(ctx)}
    p_all, p_strong = [], []
    for path in sorted(files, key=str):
        sha, nbytes, why = files[path]
        data = rv.read(rv.live, path) if isinstance(path, str) else None
        if data is None:
            msg = f"live/{path} missing ({why[0]}" + (f", and {len(why) - 1} more" if len(why) > 1 else "") + ")"
        elif sha is not None and sha256_hex(data) != sha:
            msg = f"live/{path} has sha256 {sha256_hex(data)}, expected {sha} ({why[0]})"
        elif nbytes is not None and len(data) != nbytes:
            msg = f"live/{path} is {len(data)} bytes, expected {nbytes} ({why[0]})"
        else:
            continue
        p_all.append(msg)
        if any(f"snapshot {x} " in y for x in strong if x for y in why):
            p_strong.append(msg)
    for must in ("manifest.json", "status/runs.json"):
        if rv.read(rv.live, must) is None:
            p_all.append(f"live/{must} missing")
    check("T66 the live window is complete: the manifest and its files, the current snapshot, its previous, the manifest's previous_snapshot, every snapshot of the last 35 days, every pinned and significant snapshot, with the files they name, and status/ (13, 17.6)", p_all,
          f"{len(snaps)} snapshots, {len(files)} files")
    check("T67 nothing a pinned or significant snapshot names is missing from live/ (17.6: never pruned)", p_strong,
          f"{len(strong - {None})} pinned or significant snapshot(s)")
    p = []
    for f in rv.files(rv.live):
        if f in files or f == "manifest.json" or f.startswith("status/"):
            continue
        why = ""
        mt = RX_SNAPSHOT_PATH.fullmatch(f)
        if mt and mt.group(1) in ctx.snaps:
            why = f" (snapshot created {ctx.snaps[mt.group(1)].get('created_at')}, not in the window as of generated_at {ctx.manifest.get('generated_at')})"
        elif any(not err and f in rx_manifest_files(m) for _, m, err in ctx.arch_manifests[:-1]):
            why = " (named only by a manifest whose snapshot is not in the window)"
        elif rv.read(rv.arch, f) is None:
            why = " (not in the archive either)"
        p.append(f"live/{f}{why}")
    check("T68 no file in live/ lies outside the window, status/ and manifest.json (13, 17.6: pruning removes them)", p, f"{len(rv.files(rv.live))} live files")


# --- T69 to T71: review queue and alerts ---


def rc_review_queue(ctx):
    rv, st = ctx.rv, ctx.st
    name = "T69 review-queue.json: schema rmf.econ.review-queue/4, open entries with the 17.5 fields that match the current snapshot's holds and candidates, a frozen list (its entries: T109), decisions with their fields, a refusals list"
    doc, err = rv.load(rv.state, "review-queue.json")
    if err:
        check(name, [f"archive/state/review-queue.json: {err}"])
        return
    p = shape_problems("review-queue.json", doc, {"schema": lambda x: x == SCHEMA_IDS["review-queue"], "open": lambda x: isinstance(x, list),
                                                  "frozen": lambda x: isinstance(x, list), "decisions": lambda x: isinstance(x, list),
                                                  "refusals": lambda x: isinstance(x, list)})
    opens = doc.get("open") if isinstance(doc.get("open"), list) else []
    cur = ctx.cur or {}
    holds = {h.get("series"): h for h in cur.get("holds", [])}
    seen = set()
    for i, e in enumerate(opens):
        p += shape_problems(f"open[{i}]", e, {
            "series": lambda x: x in ctx.reg_ids, "candidate_sha256": is_sha256, "archive_asset": is_str,
            "bytes": lambda x: is_count(x) and x > 0, "reason": is_str, "opened_at": is_time, "updated_at": is_time,
            "changes": lambda x: isinstance(x, dict) and set(x) == {"changed", "removed", "added"} and all(is_count(v) for v in x.values())})
        if not isinstance(e, dict):
            continue
        sid = e.get("series")
        if sid in seen:
            p.append(f"open[{i}]: a second entry for {sid} (17.5: one entry per held series)")
        seen.add(sid)
        h = holds.get(sid)
        if h is None:
            p.append(f"open[{i}]: {sid} has no open hold in the current snapshot {cur.get('id')}")
            continue
        cand = h.get("candidate") or {}
        for mine, theirs, label in ((e.get("candidate_sha256"), cand.get("sha256"), "candidate_sha256"), (e.get("archive_asset"), cand.get("archive_asset"), "archive_asset"),
                                    (e.get("bytes"), cand.get("bytes"), "bytes"), (e.get("reason"), h.get("reason"), "reason"), (e.get("opened_at"), h.get("opened_at"), "opened_at")):
            if mine != theirs:
                p.append(f"open[{i}] {sid}: {label} {mine!r}, the snapshot's hold has {theirs!r}")
        if is_time(e.get("opened_at")) and is_time(e.get("updated_at")) and e["updated_at"] < e["opened_at"]:
            p.append(f"open[{i}] {sid}: updated_at before opened_at")
        v, cerr = rv.load(rv.holds, f"{sid}/{str(e.get('candidate_sha256'))[:16]}.json")
        if cerr or not isinstance(v, list) or not isinstance(e.get("changes"), dict):
            continue  # a missing candidate is reported by T64

        def bare(o):
            return {k: x for k, x in o.items() if k != "released"}  # 17.3: comparison ignores released

        old = {observation_key(o): bare(o) for o in rx_obs(ctx, cur.get("series", {}).get(sid, {}))}
        new = {observation_key(o): bare(o) for o in v if isinstance(o, dict)}
        want = {"changed": sum(1 for k in old if k in new and not json_equal(old[k], new[k])),
                "removed": sum(1 for k in old if k not in new), "added": sum(1 for k in new if k not in old)}
        if e["changes"] != want:
            p.append(f"open[{i}] {sid}: changes {e['changes']}, the candidate against the published observations gives {want}")
    for sid in sorted(set(holds) - seen, key=str):
        p.append(f"the current snapshot holds {sid} but review-queue.json has no open entry for it")
    decisions = doc.get("decisions") if isinstance(doc.get("decisions"), list) else []
    p_decision = []
    review_runs = {(s.get("run") or {}).get("id") for s in ctx.snaps.values() if (s.get("run") or {}).get("trigger") == "review"}
    other_runs = {(s.get("run") or {}).get("id") for s in ctx.snaps.values() if (s.get("run") or {}).get("trigger") in ("schedule", "manual")}
    times = []
    for i, d in enumerate(decisions):
        p += shape_problems(f"decisions[{i}]", d, {"series": lambda x: x in ctx.reg_ids, "candidate_sha256": is_sha256,
                                                   "decision": lambda x: isinstance(x, str), "decided_at": is_time, "run": is_str,
                                                   "reviewer": lambda x: x is None or is_str(x), "reason": lambda x: x is None or is_str(x),
                                                   "affected_periods": lambda x: isinstance(x, list), "record": is_str,
                                                   "reviewer_permission": lambda x: x is None or x in REVIEW_PERMISSIONS_ALL,
                                                   "permission_checked_at": lambda x: x is None or is_time(x),
                                                   "publication": lambda x: isinstance(x, dict) and set(x) == {"outcome", "snapshot"}})
        if isinstance(d, dict) and d.get("decision") in ("approve", "reject", "clear") and not (is_str(d.get("reviewer")) and is_str(d.get("reason"))):
            p_decision.append(f"decisions[{i}]: {d.get('decision')} without a reviewer or a reason; both texts are required (11.5)")
        if isinstance(d, dict) and d.get("decision") == "withdrawn" and (d.get("reviewer") is not None or d.get("reason") is not None):
            p_decision.append(f"decisions[{i}]: withdrawn with reviewer {d.get('reviewer')!r} and reason {d.get('reason')!r}; both are null for withdrawn (17.5)")
        if isinstance(d, dict) and is_str(d.get("run")):
            ds = next((x for x in ctx.snaps.values() if (x.get("run") or {}).get("id") == d["run"]), None)
            if ds is not None and d.get("decided_at") != ds.get("created_at"):
                p_decision.append(f"decisions[{i}]: decided_at {d.get('decided_at')} is not the time {ds.get('created_at')} of run {d['run']}")
        if isinstance(d, dict):
            times.append(str(d.get("decided_at")))
            if isinstance(d.get("decision"), str) and d["decision"] not in ("approve", "reject", "clear", "withdrawn"):
                p_decision.append(f"decisions[{i}]: decision {d['decision']!r} for {d.get('series')}; 17.5 names approve, reject, clear or withdrawn")
            elif d.get("decision") == "withdrawn" and is_str(d.get("run")) and d["run"] not in other_runs:
                p_decision.append(f"decisions[{i}]: withdrawn in run {d['run']!r}, which is not the run of an archived snapshot written by a collecting run (17.3: the candidate is classified and published like any other)")
            elif d.get("decision") in ("approve", "reject", "clear") and is_str(d.get("run")) and d["run"] not in review_runs:
                p_decision.append(f"decisions[{i}]: {d['decision']} in run {d['run']!r}, which is not the run of an archived snapshot with trigger review (17.5: approve, reject and clear each publish a snapshot)")
            if is_sha256(d.get("candidate_sha256")) and rv.read(rv.holds, f"{d.get('series')}/{d['candidate_sha256'][:16]}.json") is None:
                p.append(f"decisions[{i}]: the decided candidate {d['candidate_sha256'][:16]} of {d.get('series')} is not in archive/holds/ (11.5: the proposed values, or the locked candidate, are kept)")
    if times != sorted(times):
        p.append("decisions are not in time order (append-only)")
    check(name, p, f"{len(opens)} open, {len(decisions)} decision(s)")
    check("T76 every decision is approve, reject or clear, taken in a review run that wrote a snapshot, with a reviewer and a reason, or withdrawn, recorded by a collecting run that wrote one, with both null; decided_at is the run's time (11.5, 17.3, 17.5)", p_decision, f"{len(decisions)} decision(s)")


def rc_queue_locks(ctx):
    """T109: the review queue's frozen entries against the locks in force (11.5, 17.5)."""
    rv = ctx.rv
    name = "T109 review-queue.json frozen (review-queue/4): exactly one entry per lock in force in the published state (the live manifest's snapshot frozen plus, after a rollback, its rollback record's locks), a series once per lock (v0.6); each with series, candidate_sha256, origin, frozen_at and reason as the lock; for a rejected lock the run, reviewer, reason and affected_periods of its reject decision; for a rolled-back lock the rollback's run, reviewer null, the rollback's reason; locked_changes exactly the 11.5 pairs recomputed from the archive (v0.6: new periods count for both origins), in period order, and equal to the rollback record's (11.5, 17.5)"
    doc, err = rv.load(rv.state, "review-queue.json")
    if err or not isinstance(doc, dict):
        check(name, [f"archive/state/review-queue.json: {err or 'not an object'}"])
        return
    locks = rx_locks_of(ctx, ctx.manifest)
    fz = doc.get("frozen") if isinstance(doc.get("frozen"), list) else []
    p, n_changes = [], 0
    if not isinstance(doc.get("frozen"), list):
        p.append("no frozen list")
    decisions = rx_decisions(ctx)
    fields_ok = lambda f: isinstance(f, str) and (f in SECTION10_FIELDS or (f.startswith("extra.") and len(f) > 6))
    seen = []
    for i, e in enumerate(fz):
        p += shape_problems(f"frozen[{i}]", e, {"series": lambda x: x in ctx.reg_ids, "candidate_sha256": is_sha256, "origin": lambda x: x in LOCK_ORIGINS,
                                                 "frozen_at": is_time, "run": is_str, "reviewer": lambda x: x is None or is_str(x), "reason": is_str,
                                                 "affected_periods": lambda x: isinstance(x, list), "locked_changes": lambda x: isinstance(x, list)})
        if not isinstance(e, dict):
            continue
        sid = e.get("series")
        k = lock_key(e)
        seen.append(k)
        w = f"frozen[{i}] {_k16(k)}"
        lk = locks.get(k)
        if lk is None:
            p.append(f"{w}: not a lock in force in the published state (11.5: a queue entry the published state does not list is dropped)")
            continue
        for f in ("frozen_at", "reason"):
            if e.get(f) != lk.get(f):
                p.append(f"{w}: {f} {e.get(f)!r}, the published lock has {lk.get(f)!r}")
        if lk.get("origin") == "rejected":
            d = [x for x in decisions if x.get("series") == sid and x.get("candidate_sha256") == lk.get("candidate_sha256") and x.get("decision") == "reject"]
            if not d or any(e.get(f) != d[-1].get(f) for f in ("run", "reviewer", "reason", "affected_periods")):
                p.append(f"{w}: run, reviewer, reason or affected_periods differ from its reject decision {({f: d[-1].get(f) for f in ('run', 'reviewer', 'reason')}) if d else None}")
            if not is_str(e.get("reviewer")):
                p.append(f"{w}: reviewer {e.get('reviewer')!r}; a rejected lock names the reviewer (null only for a rollback)")
        else:
            if e.get("reviewer") is not None:
                p.append(f"{w}: reviewer {e.get('reviewer')!r}; 17.5 gives null for a rollback")
            rid = rx_rollback_run(ctx, lk.get("frozen_at")) if is_time(lk.get("frozen_at")) else None
            if rid is not None and e.get("run") != rid:
                p.append(f"{w}: run {e.get('run')!r}, the rollback that locked it ran as {rid!r}")
        _, locked, want = rx_lock_detail(ctx, sid, lk)
        got = e.get("locked_changes") if isinstance(e.get("locked_changes"), list) else []
        pairs = [(c.get("period"), c.get("field")) if isinstance(c, dict) and set(c) == {"period", "field"} else None for c in got]
        if None in pairs:
            p.append(f"{w}: a locked_changes entry is not exactly {{period, field}}")
            continue
        bad = sorted({f for _, f in pairs if not fields_ok(f)}, key=str)
        if bad:
            p.append(f"{w}: locked_changes fields {bad} are not section 10 member names")
        if [x for x, _ in pairs] != sorted(x for x, _ in pairs):
            p.append(f"{w}: locked_changes are not in period order (17.5)")
        if want is None:
            p.append(f"{w}: the locked candidate is not readable in archive/holds/, so locked_changes cannot be recomputed")
            continue
        n_changes += len(want)
        if sorted(pairs) != want:
            miss, extra = sorted(set(want) - set(pairs)), sorted(set(pairs) - set(want))
            p.append(f"{w}: locked_changes differ from the {len(want)} pair(s) recomputed for a {lk.get('origin')} lock: missing {miss[:4]}, not a change {extra[:4]} (11.5)")
        if len(set(pairs)) != len(pairs):
            p.append(f"{w}: a locked change is listed twice")
        if isinstance(lk.get("locked_changes"), list):
            rec_pairs = sorted((c.get("period"), c.get("field")) for c in lk["locked_changes"] if isinstance(c, dict))
            if rec_pairs != sorted(pairs):
                p.append(f"{w}: locked_changes differ from the rollback record's for this lock (17.5 v0.6)")
        if lk.get("origin") == "rolled-back":
            # reading: the affected periods of a rolled-back lock are the periods of its locked changes.
            if e.get("affected_periods") != sorted({x for x, _ in want}):
                p.append(f"{w}: affected_periods {e.get('affected_periods')!r:.80}, the periods of its locked changes are {sorted({x for x, _ in want})[:6]}")
    if sorted(map(str, seen)) != sorted(map(str, locks)) or len(set(seen)) != len(seen):
        p.append(f"frozen entries {[_k16(x) for x in seen]}, the locks in force are {sorted(map(_k16, locks))} (17.5 v0.6: one entry per lock)")
    check(name, p, f"{len(fz)} entr{'y' if len(fz) == 1 else 'ies'}, {len(locks)} lock(s) in force, {n_changes} locked change(s) recomputed")


ALERT_HEADER_NAMES = ("authorization", "cookie", "set-cookie", "x-api-key", "user-agent")
ALERT_TOKEN_SHAPES = ("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_")
ALERT_FIXED_KEYS = {"retention-decision": "critical", "gate-failed": "critical", "failed-runs": "critical", "recovered-staging": "warning", "alert-text-refused": "critical",
                    "workflow-disabled": "critical", "inactivity": None, "scheduled-run-gap": None, "consecutive-failures": "critical",
                    "manifest-overdue": None, "series-stale": "warning", "series-held": "warning", "manifest-missing": "critical",
                    "self-check-unavailable": "warning",  # v0.7 (17.8, 21.3); collect-failed is the issue job's only (21.5), never a ledger key
                    "publication-behind": "warning", "publication-facts-unavailable": "warning",  # v0.8 (17.8, 22.4): the collection run's
                    "publish-failed": "critical", "publication-verify-failed": "critical", "publication-history-changed": "critical"}  # v0.8: never in the collection ledger (T125)
ALERT_SERIES_KEYS = {"frozen": "warning", "hold": "critical", "revision-large": "warning", "invalid-series": "critical", "stale": None,
                     "source-gap": "critical", "source-overdue": "warning"}  # 17.8 (v0.4 adds source-gap and source-overdue)
ALERT_SOURCE_KEYS = {"invalid": "critical", "blocked": "critical", "fetch-failures": "warning",
                     "source-retirement": None, "source-route-check": "warning"}  # 17.8 (v0.4 adds the route alerts)
COLLECTION_ALERT_HEADS = ("fetch-failures", "blocked", "invalid")  # per source (11.6: none is raised with source-overdue)
COLLECTION_ALERT_SERIES_HEADS = ("invalid-series", "source-gap")
ALERT_BUDGET_KEYS = ("published", "archive-month", "object", "file", "manifest", "pins", "state-store")  # v0.7 adds budget:state-store (21.4)


def alert_text_problems(text):
    """17.8 (v0.8): the alert text check is the reason check of 22.3, items 1 to 9 (d6_problems)."""
    return [f"refused by the 22.3 item {name}" for name in d6_problems(text)]


def rc_alerts(ctx):
    rv, st = ctx.rv, ctx.st
    name = "T70 alerts.json: schema rmf.econ.alerts/1, open alerts with key, severity, title, body, first_seen, last_seen, runs; keys and severities are those of 11.5, 11.6, 17.4, 17.6, 17.7, 17.8 and 14.3 (v0.4: source-gap, source-overdue, source-retirement, source-route-check); an open hold has its hold alert and a locked series (snapshot frozen or rollback.locked) its frozen alert, whose body names the origin; route alerts exactly in their windows, without the route text"
    doc, err = rv.load(rv.state, "alerts.json")
    if err:
        check(name, [f"archive/state/alerts.json: {err}"])
        check("T71 every alert title and body in the ledger passes the sanitization rules of 17.8", [f"archive/state/alerts.json: {err}"])
        return
    p = shape_problems("alerts.json", doc, {"schema": lambda x: x == "rmf.econ.alerts/1", "open": lambda x: isinstance(x, list)})
    opens = doc.get("open") if isinstance(doc.get("open"), list) else []
    p_text, keys = [], []
    for i, a in enumerate(opens):
        p += shape_problems(f"open[{i}]", a, {
            "key": is_str, "severity": lambda x: x in ("warning", "critical"), "title": lambda x: isinstance(x, str), "body": lambda x: isinstance(x, str),
            "first_seen": is_time, "last_seen": is_time,
            "runs": lambda x: (is_count(x) and x >= 1) or (isinstance(x, list) and len(x) >= 1)})
        if not isinstance(a, dict):
            continue
        key, sev = str(a.get("key")), a.get("severity")
        keys.append(key)
        if is_time(a.get("first_seen")) and is_time(a.get("last_seen")) and a["last_seen"] < a["first_seen"]:
            p.append(f"open[{i}] {key}: last_seen before first_seen")
        head, _, tail = key.partition(":")
        if key in ALERT_FIXED_KEYS:
            want = ALERT_FIXED_KEYS[key]
        elif head in ("series-stale", "series-held") and tail in ctx.reg_ids:
            want = "warning"  # reading: a 14.3 finding about one series may carry its id
        elif head in ALERT_SERIES_KEYS and tail in ctx.reg_ids:
            want = ALERT_SERIES_KEYS[head]
        elif head in ALERT_SOURCE_KEYS and tail in st.registry["sources"]:
            want = ALERT_SOURCE_KEYS[head]
        elif head == "budget" and tail in ALERT_BUDGET_KEYS:
            want = None
        else:
            p.append(f"open[{i}]: key {key!r} is not an alert key of 17.4, 17.7, 17.8 or a finding of 14.3 with a registered id")
            want = None
        if want is not None and sev != want:
            p.append(f"open[{i}] {key}: severity {sev!r}, the text gives {want}")
        for field in ("title", "body"):
            if isinstance(a.get(field), str):
                p_text += [f"open[{i}] {key} {field}: {x}" for x in alert_text_problems(a[field])]
    if len(set(keys)) != len(keys):
        p.append("an alert key appears twice (15: one issue per alert key)")
    held = {h.get("series") for h in (ctx.cur or {}).get("holds", [])}
    for sid in sorted(held, key=str):
        if f"hold:{sid}" not in keys:
            p.append(f"the current snapshot holds {sid} but the ledger has no open alert hold:{sid} (11.5: an alert opens)")
    locks_now = rx_locks_of(ctx, ctx.manifest)  # 11.5 (v0.6): the locks in force, the rollback record's included
    frozen_now = lock_series(locks_now)
    bodies = {str(a.get("key")): str(a.get("body")) for a in opens if isinstance(a, dict)}
    for sid in sorted(frozen_now, key=str):
        if f"frozen:{sid}" not in keys:
            p.append(f"{sid} is locked in the published state but the ledger has no open alert frozen:{sid} (11.5: it lasts while the series is locked)")
            continue
        # 17.8: the body names the origin. reading (v0.6): with several locks, every origin among them.
        for origin in sorted({str(e.get("origin")) for e in locks_of_series(locks_now, sid)}):
            if origin not in bodies.get(f"frozen:{sid}", ""):
                p.append(f"alert frozen:{sid}: the body does not name the origin {origin!r} of one of its locks (17.8)")
    for key in keys:
        if key.startswith("frozen:") and key[7:] not in frozen_now:
            p.append(f"alert {key} is open but that series is not locked in the published state")
        if key.startswith("hold:") and key[5:] not in held:
            p.append(f"alert {key} is open but the current snapshot has no hold on that series (17.8: closed when no longer current)")
    # 17.8: route alerts in the ledger match the newest run's ET date; their body never carries the route text.
    newest = max((str(v.get("started_at")) for v in rx_run_records(ctx).values() if is_time(v.get("started_at"))), default=None)
    if newest:
        want = route_alerts(st, et_date(parse_utc(newest)))
        got = {str(a.get("key")): a for a in opens if isinstance(a, dict) and str(a.get("key")).startswith(("source-retirement:", "source-route-check:"))}
        for k in sorted(set(want) | set(got)):
            if k not in got:
                p.append(f"the newest run ({newest}) is inside the window of {k} ({want[k][0]}, entry {want[k][1]}) but the ledger has no open {k} (17.8)")
            elif k not in want:
                p.append(f"alert {k} is open but no route_notices entry puts {et_date(parse_utc(newest))} inside its window (17.8)")
            else:
                if got[k].get("severity") != want[k][0]:
                    p.append(f"alert {k}: severity {got[k].get('severity')}, 17.8 gives {want[k][0]}")
                src = st.registry["sources"].get(k.split(":", 1)[1], {})
                for e in src.get("route_notices") or []:
                    for f in ("route", "text"):
                        if is_str(e.get(f)) and e[f][:40] in str(got[k].get("body")):
                            p.append(f"alert {k}: the body carries the route notice's {f} (17.8: never the route text)")
    check(name, p, f"{len(opens)} open alert(s)")
    check("T71 every alert title and body in the ledger passes the sanitization rules of 17.8: no query string or URL with a path, email, IPv4 address, header name, Bearer, token shape, long hex or base64 run, at most 2,000 characters", p_text,
          f"{2 * len(opens)} texts")


# --- T72 to T75: runs, run records, budgets ---


def rc_runs(ctx):
    rv, st = ctx.rv, ctx.st
    doc, err = rv.load(rv.live, "status/runs.json")
    name = "T72 status/runs.json: the last 100 runs at most, newest first, snapshot exactly when published and archived (14.1)"
    runs = doc.get("runs") if not err and isinstance(doc, dict) and isinstance(doc.get("runs"), list) else []
    p = [f"live/status/runs.json: {err}"] if err else []
    starts = [str(r.get("started_at")) for r in runs]
    if starts != sorted(starts, reverse=True):
        p.append("runs are not newest first")
    if len(runs) > 100:
        p.append(f"{len(runs)} runs, more than 100")
    for r in runs:
        if (r.get("outcome") == "published") != (r.get("snapshot") is not None):
            p.append(f"{r.get('id')}: outcome {r.get('outcome')} with snapshot {r.get('snapshot')} (snapshot exactly when published)")
        if r.get("snapshot") is not None and r["snapshot"] not in ctx.snaps:
            p.append(f"{r.get('id')}: snapshot {r['snapshot']} is not in the archive")
        if r.get("snapshot") and r.get("trigger") in ("schedule", "manual", "review") and is_time(r.get("started_at")) and r["snapshot"] != snapshot_id_of(parse_utc(r["started_at"])):
            p.append(f"{r.get('id')}: snapshot {r['snapshot']} is not the run's start time {r['started_at']} (3)")
        if str(r.get("ended_at")) < str(r.get("started_at")):
            p.append(f"{r.get('id')}: ends before it starts")
        if set(r.get("series") or {}) - ctx.reg_ids:
            p.append(f"{r.get('id')}: unregistered series {sorted(set(r['series']) - ctx.reg_ids)}")
    check(name, p, f"{len(runs)} run(s)")

    p, records = [], {}
    for f in rv.files(rv.state):
        if not f.startswith("run-records/"):
            continue
        v, err = rv.load(rv.state, f)
        if err or not isinstance(v, dict):
            p.append(f"archive/state/{f}: {err or 'not an object'}")
            continue
        p += shape_problems(f"archive/state/{f}", v, {
            "id": is_str, "trigger": lambda x: x in ("schedule", "manual", "rollback", "restore", "review"), "started_at": is_time, "ended_at": is_time,
            "outcome": lambda x: x in ("published", "nothing-due", "no-change", "gate-failed", "failed", "refused"),
            "snapshot": lambda x: x is None or is_snapshot_id(x), "series": lambda x: isinstance(x, dict), "alerts": lambda x: isinstance(x, list),
            "absences": lambda x: isinstance(x, list)})
        try:
            errs = schema_errors({"schema": st.schemas["runs"].get("properties", {}).get("schema", {}).get("const", "rmf.econ.runs/2"), "runs": [v]}, st.schemas["runs"])
        except SchemaKeywordError as exc:
            errs = [f"validator cannot evaluate: {exc}"]
        p += [f"archive/state/{f}: {e} (runs.schema.json, one record)" for e in errs[:2]]
        if v.get("outcome") == "refused" and (v.get("trigger") != "review" or v.get("snapshot") is not None or v.get("absences") != []):
            p.append(f"archive/state/{f}: outcome refused with trigger {v.get('trigger')}, snapshot {v.get('snapshot')}, absences {v.get('absences')!r:.40}; 17.5 gives a review run, snapshot null, absences empty")
        for key in v.get("alerts") or []:
            head, _, tail = str(key).partition(":")
            ok = key in ALERT_FIXED_KEYS or (head in ALERT_SERIES_KEYS and tail in ctx.reg_ids) or (head in ALERT_SOURCE_KEYS and tail in st.registry["sources"]) \
                or (head == "budget" and tail in ALERT_BUDGET_KEYS) or (head in ("series-stale", "series-held") and tail in ctx.reg_ids)
            if not ok:
                p.append(f"archive/state/{f}: alert key {key!r} is not an alert key of 17.4, 17.7, 17.8 or a finding of 14.3")
        if not (isinstance(v.get("id"), str) and RX_RUN_ID.fullmatch(v["id"])):
            p.append(f"archive/state/{f}: run id {v.get('id')!r} is not 1 to 80 letters, digits, dots, hyphens or underscores (17.2)")
        if not isinstance(v.get("pruned"), list):
            p.append(f"archive/state/{f}: no pruned list (17.1: the run record has one more field than 14.1 lists)")
        if v.get("trigger") in ("rollback", "restore") and v.get("outcome") == "published":
            # 17.2: no snapshot is written; snapshot is the id the manifest names afterwards.
            named = [(m.get("snapshot") or {}).get("id") for _, m, merr in ctx.arch_manifests
                     if not merr and str(m.get("generated_at")) <= str(v.get("ended_at"))]
            if not named or v.get("snapshot") != named[-1]:
                p.append(f"archive/state/{f}: a {v.get('trigger')} run with snapshot {v.get('snapshot')}; the manifest in place after it names {named[-1] if named else None} (17.2)")
        if f != f"run-records/{v.get('id')}.json":
            p.append(f"archive/state/{f}: the record's id is {v.get('id')!r} (17.1: run-records/<run id>.json)")
        records[v.get("id")] = v
        if "pruned" in v:
            if not isinstance(v["pruned"], list):
                p.append(f"archive/state/{f}: pruned is not a list")
                continue
            sig = rx_significant(ctx)
            for path in v["pruned"]:
                if rv.read(rv.arch, path) is None:
                    p.append(f"archive/state/{f}: pruned {path!r} is not in archive/files/ (17.6: never removed from the archive)")
                for sid_ in sig:
                    if path in rx_named_files(ctx, sid_):
                        p.append(f"archive/state/{f}: pruned {path}, which the significant snapshot {sid_} names (17.6)")
                        break
    for r in runs:
        rec = records.get(r.get("id"))
        if rec is None:
            p.append(f"status/runs.json run {r.get('id')!r} has no archive/state/run-records/{r.get('id')}.json (17.1: the run record of every run)")
        else:
            diff = sorted(k for k in r if not json_equal(r[k], rec.get(k)))
            if diff:
                p.append(f"status/runs.json run {r.get('id')!r} differs from its run record in {diff}")
    # 14.1: quiet runs do not deploy, so status/runs.json holds the newest 100 run records as of the
    # last run that wrote live/ (a publishing run of any trigger; a restore rebuilds it); the records
    # of the quiet runs after it are folded in by the next publication (v0.7: most Stage C runs are quiet).
    by_time = sorted(records.values(), key=lambda v: (str(v.get("started_at")), str(v.get("id"))))
    last_pub = max((i for i, v in enumerate(by_time) if v.get("outcome") == "published"), default=len(by_time) - 1)
    newest = list(reversed(by_time[:last_pub + 1]))[:100]
    if {v.get("id") for v in newest} != {r.get("id") for r in runs}:
        only_rec = sorted(str(x) for x in {v.get("id") for v in newest} - {r.get("id") for r in runs})
        only_run = sorted(str(x) for x in {r.get("id") for r in runs} - {v.get("id") for v in newest})
        p.append(f"status/runs.json is not the newest 100 run records up to the last publishing run: only in run-records {only_rec[:5]}, only in runs.json {only_run[:5]} (14.1, 17.5 restore)")
    to_status = {"appended": {"refreshed"}, "revised-expected": {"refreshed"}, "unchanged": {"unchanged"},
                 "not-due": {"carried-forward", "not-yet-published"}, "invalid": {"carried-forward", "not-yet-published"},
                 "failed": {"carried-forward", "not-yet-published"}, "revised-unexpected": {"held", "carried-forward"}}
    for sid_ in ctx.order:
        s = ctx.snaps[sid_]
        rid = (s.get("run") or {}).get("id")
        if not (isinstance(rid, str) and RX_RUN_ID.fullmatch(rid)):
            p.append(f"snapshot {sid_}: run id {rid!r} is not 1 to 80 letters, digits, dots, hyphens or underscores (17.2)")
        if (s.get("run") or {}).get("trigger") in ("rollback", "restore"):
            p.append(f"snapshot {sid_}: written by a {s['run']['trigger']} run, which writes no snapshot (17.2, 17.5)")
        rec = records.get(rid)
        if rec is None:
            p.append(f"snapshot {sid_}: no run record for its run {(s.get('run') or {}).get('id')!r}")
            continue
        if rec.get("outcome") != "published" or rec.get("snapshot") != sid_:
            p.append(f"snapshot {sid_}: its run record has outcome {rec.get('outcome')} and snapshot {rec.get('snapshot')}")
        if rec.get("trigger") != (s.get("run") or {}).get("trigger"):
            p.append(f"snapshot {sid_}: trigger {(s.get('run') or {}).get('trigger')} but its run record says {rec.get('trigger')}")
        if rec.get("trigger") in ("schedule", "manual"):
            for series_id, outcome in sorted((rec.get("series") or {}).items()):
                got = s.get("series", {}).get(series_id, {}).get("status")
                if got == "held" and outcome in ("not-due", "invalid", "failed") and any(h.get("series") == series_id for h in s.get("holds", [])):
                    continue  # reading: a hold stays open when its refresh fails
                if outcome == "unchanged" and got == "carried-forward" and series_id in lock_series(rx_locks_of(ctx, next((m for _, m, e in ctx.arch_manifests if not e and (m.get("snapshot") or {}).get("id") == sid_), None))):
                    continue  # reading: 17.3 says a locked series with outcome unchanged "is carried forward"
                if got not in to_status.get(outcome, set()):
                    p.append(f"snapshot {sid_} {series_id}: run outcome {outcome} gives {sorted(to_status.get(outcome, set()))}, the snapshot says {got} (8, 17.3)")
    check("T73 run records: one per run at archive/state/run-records/<run id>.json with the 14.1 fields (runs/2: absences, outcome refused) and pruned, valid alert keys, run ids in the 17.2 form; a refused record is a review run with snapshot null and no absences; a rollback or restore record names the snapshot the manifest names afterwards; status/runs.json equals the newest of them up to the last publishing run (quiet runs do not deploy); every snapshot's run is recorded as published and its series outcomes give the snapshot statuses of 8; nothing pruned is lost or significant (14.1, 17.1, 17.5, 17.6)", p,
          f"{len(records)} run record(s)")


def rc_budgets(ctx):
    rv, p = ctx.rv, []
    total = 0
    for f in rv.files(rv.live):
        size = (rv.live / f).stat().st_size
        total += size
        if size > LIMIT_FILE:
            p.append(f"live/{f} is {size} bytes, over the 5 MB limit for one published file")
        if f.startswith("objects/") and size > LIMIT_OBJECT:
            p.append(f"live/{f} is {size} bytes, over the 2 MB limit for one object")
        if f == "manifest.json" and size > LIMIT_MANIFEST:
            p.append(f"live/manifest.json is {size} bytes, over the 256 KB limit")
    if total > LIMIT_SITE:
        p.append(f"live/ holds {total} bytes, over the 250 MB limit for published storage")
    for f in rv.files(rv.arch):
        size = (rv.arch / f).stat().st_size
        if f.startswith("objects/") and size > LIMIT_OBJECT:
            p.append(f"archive/files/{f} is {size} bytes, over the 2 MB limit for one object")
    check("T74 budgets, hard limits in decimal units: live/ at most 250 MB, an object 2 MB, a published file 5 MB, manifest.json 256 KB (12.7, 17.7)", p,
          f"live/ {total} bytes in {len(rv.files(rv.live))} files")
    arch_total = sum((base / f).stat().st_size for base in (rv.arch, rv.holds, rv.manifests) for f in rv.files(base))
    name = "T75 new archive bytes in one ET month stay within 50 MB (12.7, 17.7)"
    if arch_total <= LIMIT_ARCHIVE_MONTH:
        check(name, [], f"archive/files, holds and manifests hold {arch_total} bytes in all, so no month can exceed the limit")
    else:
        skip(name, f"the archive holds {arch_total} bytes and the text gives no way to tell from the root alone in which month each file was added (the shape of collector.json is not specified)")


def rc_full_fetches(ctx):
    """T116 (v0.7, 17.1, 17.3): collector.json full_fetches against the run records."""
    rv = ctx.rv
    name = ("T116 archive/state/collector.json has full_fetches (v0.7): per request group the time (the run's now) of its last successful full fetch, "
            "recomputed from the run records with the once-per-Sunday rule (a group with an unpublished series, H.6 and the weekly fetch are full); a group never fetched in full successfully has no time; before the boundary of 21.1 also no full_fetches at all (17.1, 17.3, 21.1)")
    doc, err = rv.load(rv.state, "collector.json")
    if err or not isinstance(doc, dict):
        check(name, [f"archive/state/collector.json: {err or 'not an object'}"])
        return
    plan = rx_full_plan(ctx)
    p, notes = [], []
    newest = max((str(r.get("started_at")) for r in rx_run_records(ctx).values() if is_time(r.get("started_at"))), default=None)
    before_boundary = newest is not None and rx_legacy(ctx, newest)  # 21.1: not yet rewritten by a run after the promoted dataset
    # 21.1: written before the boundary, collector.json has no full_fetches (the v0.6 form) or exactly the value the
    # runs give, counting their full fetches (the v0.7 form); after it, the value carried forward or recomputed exactly.
    last = plan["last_with_legacy"] if before_boundary else plan["last"]
    if "full_fetches" not in doc:
        if before_boundary:
            notes.append(f"no full_fetches: the state was written before the boundary of 21.1 (the v0.6 form; newest run {newest})")
        else:
            p.append(f"collector.json has no full_fetches (17.1 v0.7); its keys are {sorted(doc)}")
    else:
        ff = doc["full_fetches"]
        if not isinstance(ff, dict):
            p.append(f"full_fetches is {type(ff).__name__}, not an object keyed by request group")
            ff = {}
        for g in sorted(set(ff) - set(plan["groups"])):
            p.append(f"full_fetches names {g!r}, which is not a request group (17.1: keyed by the group's name, effr, debt-total, m1-sa)")
        for g in plan["groups"]:
            got = ff.get(g)
            want = fmt_utc(last[g]) if last.get(g) else None
            if got is not None and not is_time(got):
                p.append(f"full_fetches.{g} {got!r} is not a UTC time")
            elif got != want:
                p.append(f"full_fetches.{g} is {got!r}; the run records give {want!r} (the now of the last run that fetched the group in full successfully, neither failed nor invalid as a whole; "
                         + ("counting the runs before the boundary of 21.1, as this collector.json carries them)" if before_boundary or plan["record_legacy"] else "the runs before the boundary of 21.1 kept no full_fetches, so they do not count)"))
            else:
                notes.append(f"{g} {got}")
    check(name, p, "; ".join(notes))


def rc_line_endings(ctx):
    """T117 (v0.7, 21.2, F2): no file the pipeline writes holds a carriage return or a byte order
    mark; a file that would match its recorded hash after turning CRLF back into LF is named."""
    rv = ctx.rv
    snap_sha = {}
    for _, m, err in ctx.arch_manifests:
        if not err:
            ref = m.get("snapshot") or {}
            snap_sha[ref.get("path")] = ref.get("sha256")
    p, n, n_conv = [], 0, 0
    for base in (rv.live, rv.arch, rv.manifests, rv.holds, rv.reviews, rv.rollbacks, rv.state):
        for f in rv.files(base):
            data = rv.read(base, f)
            if data is None:
                continue
            n += 1
            where = f"{rv.name(base)}/{f}"
            if data.startswith(b"\xef\xbb\xbf"):
                p.append(f"{where}: starts with a byte order mark (21.2: none in any file the pipeline writes)")
            if b"\r" not in data:
                continue
            conv = data.replace(b"\r\n", b"\n")
            mt = re.search(r"([0-9a-f]{16})\.(?:json|csv|txt)$", f)
            if mt and (base == rv.holds or RX_OBJECT_PATH.fullmatch(f) or RX_CSV_PATH.fullmatch(f) or RX_LOG_PATH.fullmatch(f) or RX_REVCSV_PATH.fullmatch(f)
                       or RX_REGCOPY_PATH.fullmatch(f) or RX_HOLCOPY_PATH.fullmatch(f) or RX_NOTICE_PATH.fullmatch(f)):
                match = sha256_hex(conv)[:16] == mt.group(1)
            elif base in (rv.live, rv.arch) and f in snap_sha:
                match = sha256_hex(conv) == snap_sha[f]
            elif f.endswith(".json"):
                try:
                    match = canonical_problem(conv, load_strict(conv)) is None
                except Exception:
                    match = False
            else:
                match = False
            if match and b"\r" not in conv:
                n_conv += 1
                p.append(f"{where}: line endings converted (it matches its recorded hash or canonical form only after CRLF is turned back into LF: a checkout made with conversion; clone with core.autocrlf=false, 21.2)")
            else:
                n_cr = data.count(b"\r")
                p.append(f"{where}: {n_cr} carriage return(s) in a file the pipeline writes (21.2: LF only)")
    check("T117 no file of the root holds a carriage return or a byte order mark (21.2 v0.7: every text file the pipeline writes ends its lines with LF only); a file that matches its address or canonical form only after CRLF is turned back into LF is named 'line endings converted'", p,
          f"{n} files")


def rc_alert_keys_v07(ctx):
    """T118 (v0.7, 17.8, 21.3, 21.4, 21.5): the new keys and the one that never enters a ledger."""
    rv, p = ctx.rv, []
    doc, err = rv.load(rv.state, "alerts.json")
    opens = doc.get("open") if not err and isinstance(doc, dict) and isinstance(doc.get("open"), list) else []
    for a in opens:
        if not isinstance(a, dict):
            continue
        k, sev = a.get("key"), a.get("severity")
        if k == "collect-failed":
            p.append("alerts.json lists collect-failed; 21.5 raises it from the issue job only and it is never in the ledger, so the next run that writes the store closes it")
        if k == "self-check-unavailable" and sev != "warning":
            p.append(f"self-check-unavailable has severity {sev!r}; 21.3 gives a warning")
        if k == "budget:state-store" and sev not in ("warning", "critical"):
            p.append(f"budget:state-store has severity {sev!r}; 21.4 gives a warning over 50,000,000 bytes and critical over 100,000,000")
    n = 0
    for rec in rx_records_in_time(ctx):
        n += 1
        if "collect-failed" in (rec.get("alerts") or []):
            p.append(f"run record {rec.get('id')} lists collect-failed among its alerts (21.5: from the issue job only)")
    check("T118 the alert keys of v0.7: self-check-unavailable a warning (21.3), budget:state-store a warning or critical (21.4), and collect-failed never in the ledger nor in a run record (21.5: the issue job's own key) (17.8)", p,
          f"{len(opens)} open alert(s), {n} run record(s)")


# ---------------------------------------------------------------------------
# v0.8 (appendix I): registry versions (I7), the first v0.8 run, manifest/4 (9), revision CSVs
# (10), the rule files and the notice file (22.9), the reasons (D6, 17.8, 21.6, 22.3), the
# deployment log (22.4) and the publication alert keys (17.8). Root checks T119 to T125.
# ---------------------------------------------------------------------------


def registry_as_of(reg, version):
    """22.9, I7: an earlier registry version is the current registry with the substitutions of
    appendix I. v0.7: conventions v0.7, the New York Fed terms_url https://www.newyorkfed.org/termsofuse,
    terms_checked 2026-11-16 for every source. v0.6: the v0.7 registry with conventions v0.6 (21.1).
    reading: a substitution sets the value, so deriving from a registry that still says v0.7 gives
    that registry itself, and the current registry is used as it is."""
    r = json.loads(json.dumps(reg))
    if version == "current":
        return r
    r["conventions"] = V07_CONVENTIONS
    srcs = r.get("sources") if isinstance(r.get("sources"), dict) else {}
    for src_id, src in srcs.items():
        if not isinstance(src, dict):
            continue
        if "terms_checked" in src:
            src["terms_checked"] = TERMS_CHECKED_V07
        if src_id == NYFED:
            src["terms_url"] = NYFED_TERMS_V07
    if version == "v0.6":
        r["conventions"] = LEGACY_CONVENTIONS
    return r


def registry_versions(st):
    """{'current' | 'v0.7' | 'v0.6': (sha256 of the canonical bytes, canonical bytes, registry)}."""
    if getattr(st, "reg_versions", None) is None:
        out = {}
        for v in ("current", "v0.7", "v0.6"):
            reg = registry_as_of(st.registry, v)
            b = canon_bytes(reg)
            out[v] = (sha256_hex(b), b, reg)
        st.reg_versions = out
    return st.reg_versions


def registry_by_hash(st):
    """sha256 to (version, canonical bytes, registry); the current registry wins on equal hashes."""
    out = {}
    for v in ("v0.6", "v0.7", "current"):
        h, b, r = registry_versions(st)[v]
        out[h] = (v, b, r)
    return out


def registry_copy_problems(st, data, sha):
    """22.9 (I44): a registry copy is canonical JSON hashing to its name and valid against the registry schema."""
    try:
        doc = load_strict(data)
    except Exception as exc:
        return None, [f"{type(exc).__name__}: {exc}"]
    p = []
    if sha256_hex(data) != sha:
        p.append(f"it hashes to {sha256_hex(data)[:16]}, not {sha[:16]}")
    why = canonical_problem(data, doc)
    if why:
        p.append(why)
    try:
        p += schema_errors(doc, st.schemas["registry"])[:3]
    except SchemaKeywordError as exc:
        p.append(f"validator cannot evaluate: {exc}")
    return doc, p


def rx_archived_registries(ctx):
    """22.9 (I44): the registry copies in archive/files/, written by v0.8 runs: sha256 to (bytes, registry or None, problems)."""
    if getattr(ctx, "arch_regs", None) is None:
        ctx.arch_regs = {}
        for f in ctx.rv.files(ctx.rv.arch):
            mt = RX_REGCOPY_PATH.fullmatch(f)
            if mt:
                data = ctx.rv.read(ctx.rv.arch, f)
                h = sha256_hex(data)
                if h[:16] == mt.group(1):
                    doc, prob = registry_copy_problems(ctx.st, data, h)
                    ctx.arch_regs[h] = (data, doc, prob)
    return ctx.arch_regs


def rx_registry_for(ctx, sha):
    """22.9 (I44): the registry a hash names: the current one, an archived copy of an earlier v0.8 run, or
    for a snapshot written before v0.8 the I7 derivation. Returns (how, canonical bytes, registry) or None."""
    by_hash = registry_by_hash(ctx.st)
    if sha in by_hash and by_hash[sha][0] == "current":
        return by_hash[sha]
    arch = rx_archived_registries(ctx)
    if sha in arch and arch[sha][1] is not None and not arch[sha][2]:
        return ("archived", arch[sha][0], arch[sha][1])
    if sha in by_hash:
        return by_hash[sha]
    return None


def rx_v08_from(ctx):
    """22.9 'the first v0.8 run' (reading, the text gives no marker): the earliest of the first
    manifest that is rmf.econ.manifest/4 and, once the registry differs from its v0.7 version, the
    first snapshot carrying the current registry's hash. None while neither exists."""
    if getattr(ctx, "v08_from_cache", "unset") == "unset":
        times = []
        for _, m, err in getattr(ctx, "arch_manifests", []):
            if not err and isinstance(m, dict) and m.get("schema") == MANIFEST_V4 and is_time(m.get("generated_at")):
                times.append(m["generated_at"])
        man = getattr(ctx, "manifest", None)
        if isinstance(man, dict) and man.get("schema") == MANIFEST_V4 and is_time(man.get("generated_at")):
            times.append(man["generated_at"])
        vers = registry_versions(ctx.st)
        if vers["current"][0] != vers["v0.7"][0]:
            for s in getattr(ctx, "snaps", {}).values():
                if isinstance(s, dict) and (s.get("run") or {}).get("registry_sha256") == vers["current"][0] and is_time(s.get("created_at")):
                    times.append(s["created_at"])
        ctx.v08_from_cache = min(times) if times else None
    return ctx.v08_from_cache


def rx_v08(ctx, t):
    """Whether a file made at time t is from the first v0.8 run on (22.9)."""
    b = rx_v08_from(ctx)
    return b is not None and isinstance(t, str) and t >= b


def rx_snapshot_registry(ctx, snap):
    """22.9 (v0.8, I22): a file's own version marks it. A snapshot may record the current registry
    or the v0.7 one of I7; the v0.6 one only up to the promoted dataset (21.1). Returns {sha256: version}."""
    vers = registry_versions(ctx.st)
    out = {vers["current"][0]: "current"}
    out.setdefault(vers["v0.7"][0], "v0.7")
    if rx_legacy(ctx, (snap or {}).get("created_at")):
        out.setdefault(vers["v0.6"][0], "v0.6")
    return out


def build_v08_shapes(st):
    """9 and 22.4 give manifest/4 and deployments/1, but pipeline/schemas/ has no file for either
    (the text wins, preamble), so their shapes are built here from the text: manifest/4 is the
    manifest/3 schema file plus the four v0.8 fields; deployments/1 is written from 22.4."""
    m3 = json.loads(json.dumps(st.schemas["manifest"]))
    m4 = m3
    m4["$id"] = MANIFEST_V4
    m4["title"] = "manifest/4 built by the checker from section 9 (v0.8): no schema file exists"
    m4.setdefault("properties", {})["schema"] = {"const": MANIFEST_V4}
    defs = m4.setdefault("$defs", {})
    defs["regRef"] = {"type": "object", "additionalProperties": False, "required": ["path", "sha256"],
                      "properties": {"path": {"type": "string", "pattern": "^registry/econ-[0-9a-f]{16}\\.json$"}, "sha256": {"$ref": "#/$defs/sha256"}}}
    defs["holRef"] = {"type": "object", "additionalProperties": False, "required": ["path", "sha256"],
                      "properties": {"path": {"type": "string", "pattern": "^registry/holidays-[0-9a-f]{16}\\.json$"}, "sha256": {"$ref": "#/$defs/sha256"}}}
    defs["noticeRef"] = {"type": "object", "additionalProperties": False, "required": ["path", "sha256"],
                         "properties": {"path": {"type": "string", "pattern": "^notices/[0-9a-f]{16}\\.txt$"}, "sha256": {"$ref": "#/$defs/sha256"}}}
    defs["revCsvRef"] = {"type": "object", "additionalProperties": False, "required": ["path", "sha256"],
                         "properties": {"path": {"type": "string", "pattern": "^revisions/[a-z0-9]+(-[a-z0-9]+)*/\\d{4}/[0-9a-f]{16}\\.csv$"}, "sha256": {"$ref": "#/$defs/sha256"}}}
    m4["required"] = list(m4.get("required", [])) + ["rules"]
    m4["properties"]["rules"] = {"type": "object", "additionalProperties": False, "required": ["registry", "holidays", "notice", "registry_versions"],
                                 "properties": {"registry": {"$ref": "#/$defs/regRef"}, "holidays": {"$ref": "#/$defs/holRef"}, "notice": {"$ref": "#/$defs/noticeRef"},
                                                "registry_versions": {"type": "array", "items": {"$ref": "#/$defs/regRef"}}}}
    summ = defs.get("seriesSummary") or {}
    summ["required"] = list(summ.get("required", [])) + ["deadline", "stale_at", "revision_csvs"]
    props = summ.setdefault("properties", {})
    props["deadline"] = {"anyOf": [{"$ref": "#/$defs/time"}, {"type": "null"}]}
    props["stale_at"] = {"anyOf": [{"$ref": "#/$defs/time"}, {"type": "null"}]}
    props["revision_csvs"] = {"type": "array", "items": {"$ref": "#/$defs/revCsvRef"}}
    time = {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"}
    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    count = {"type": "integer", "minimum": 0}
    dataset = {"type": "object", "additionalProperties": False, "required": ["snapshot", "manifest_sha256"],
               "properties": {"snapshot": {"type": "string", "pattern": "^\\d{8}T\\d{6}Z$"}, "manifest_sha256": sha}}
    entry = {"type": "object", "additionalProperties": False,
             "required": ["number", "published_at", "run", "trigger", "dataset", "release", "site_commit", "artifact", "previous", "verification"],
             "properties": {
                 "number": {"type": "integer", "minimum": 1}, "published_at": time,
                 "run": {"type": "string", "pattern": "^pub-[A-Za-z0-9._-]{1,80}-\\d+$"},
                 "trigger": {"enum": ["manual", "timer", "redeploy"]}, "dataset": {"$ref": "#/$defs/dataset"},
                 "release": {"type": "string", "pattern": "^data-\\d{8}T\\d{6}Z-[A-Za-z0-9._-]{1,80}-\\d+$"},
                 "site_commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
                 "artifact": {"type": "object", "additionalProperties": False, "required": ["files", "bytes", "sha256"],
                              "properties": {"files": count, "bytes": count, "sha256": sha}},
                 "previous": {"anyOf": [{"$ref": "#/$defs/dataset"}, {"type": "null"}]},
                 "verification": {"type": "object", "additionalProperties": False, "required": ["checker", "post"],
                                  "properties": {"checker": {"type": "object", "additionalProperties": False, "required": ["pass", "fail", "skip"],
                                                             "properties": {"pass": count, "fail": count, "skip": count}},
                                                 "post": {"enum": ["passed", "failed", "not-deployed", None]}}}}}
    dep = {"$id": DEPLOYMENTS_ID, "title": "deployments/1 built by the checker from section 22.4 (v0.8): no schema file exists",
           "type": "object", "additionalProperties": False, "required": ["schema", "deployments"],
           "properties": {"schema": {"const": DEPLOYMENTS_ID}, "deployments": {"type": "array", "items": {"$ref": "#/$defs/entry"}}},
           "$defs": {"dataset": dataset, "entry": entry}}
    st.v08_schemas = {"manifest-v4": m4, "deployments": dep}
    return st.v08_schemas


def manifest_schema_for(st, doc):
    """The manifest shape a manifest names: manifest/4 (built from the text) or the manifest/3 file."""
    if isinstance(doc, dict) and doc.get("schema") == MANIFEST_V4:
        return (getattr(st, "v08_schemas", None) or build_v08_shapes(st))["manifest-v4"]
    return st.schemas["manifest"]


def v08_expect_deadlines(st, snapshot):
    """9 (v0.8, D7): per series (deadline, stale_at) as UTC texts or None: the 14.2 deadline of the
    next unseen period and the time its staleness rule makes it stale, measured from that deadline
    (21.4); a series that follows another takes that series' stale_at and has no deadline; both
    null when not yet published. reading: a held or frozen series has its deadline too (21.4)."""
    states = (snapshot or {}).get("series") or {}
    raw = {}

    def compute(sid, depth=0):
        if sid in raw:
            return raw[sid]
        ser, state = st.series[sid], states.get(sid) or {}
        if state.get("status") == "not-yet-published" or state.get("last_period") is None:
            res = (None, None)
        elif "follows" in ser["staleness"]:
            other = ser["staleness"]["follows"]
            res = (None, compute(other, depth + 1)[1] if depth < 3 and other in st.series else None)
        else:
            dl, _ = deadline_for(st, sid, state.get("last_period"), state.get("source_marker"))
            res = (dl, stale_threshold(st, sid, dl) if dl is not None else None)
        raw[sid] = res
        return res

    return {sid: tuple(fmt_utc(x) if x is not None else None for x in compute(sid)) for sid in st.series}


REVISION_CSV_COLUMNS = ("detected_at", "snapshot", "period", "field", "before", "after", "kind", "basis", "release_date")  # 10 (v0.8, D17)


def revision_csv_field(v):
    """10: quoted with " (inner quotes doubled) when it holds a comma, a quote or a line feed; null is empty."""
    if v is None:
        return ""
    s = v if isinstance(v, str) else canon_text(v)
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s


def revision_csv_bytes(reg, ser, year, records):
    """10 (v0.8): the CSV of one revision log version. Comment lines '<title> (<unit_label>): changes
    we observed between our collections, <YYYY>', the attribution, the notice (if any), 'Terms:
    <terms_url>'; then the header and one row per record in log order. {year} is the ET year of the
    version's newest detected_at."""
    src = reg["sources"][ser["source"]]
    times = [r.get("detected_at") for r in records if isinstance(r, dict) and is_time(r.get("detected_at"))]
    y = et_date(parse_utc(max(times))).year if times else year
    lines = [f"# {ser['title']} ({ser['unit_label']}): changes we observed between our collections, {year}",
             "# " + fill_placeholders(src["attribution"], ser["data_name"], y)]
    if src.get("notice"):
        lines.append("# " + fill_placeholders(src["notice"], ser["data_name"], y))
    lines.append(f"# Terms: {src['terms_url']}")
    lines.append(",".join(REVISION_CSV_COLUMNS))
    for r in records:
        lines.append(",".join(revision_csv_field((r or {}).get(c)) for c in REVISION_CSV_COLUMNS))
    return ("\n".join(lines) + "\n").encode("utf-8")


def notice_file_bytes(reg, generated_at):
    """22.9 (v0.8, I26): UTF-8, LF. The sources in byte order of their ids, a blank line after each;
    for each source one line each for its publisher, its attribution, its notice if not null, its
    license sentence and 'Terms: <terms_url>'. {year} is the ET year of generated_at; an
    attribution or notice holding {data_name} is written once per series of the source, in
    registry series order, with that series' data_name; otherwise once. After the last source's
    blank line, the one CC0 statement line."""
    year = et_date(parse_utc(generated_at)).year
    names = {}
    for s in reg.get("series", []):
        if isinstance(s, dict):
            names.setdefault(s.get("source"), []).append(s.get("data_name"))
    lines = []
    for src_id in sorted(reg["sources"], key=lambda x: x.encode("utf-8")):
        src = reg["sources"][src_id]
        lines.append(src["publisher"])
        block = []
        for field in ("attribution", "notice"):
            text = src.get(field)
            if text is None:
                continue
            filled = [fill_placeholders(text, dn, year) for dn in names.get(src_id, [])] if "{data_name}" in text else [fill_placeholders(text, "", year)]
            for line in filled:
                if line not in block:  # 22.9 (I43): a filled line identical to one already written for the same source is not repeated
                    block.append(line)
        lines += block
        lines.append(src["license"])
        lines.append(f"Terms: {src['terms_url']}")
        lines.append("")
    lines.append(NOTICE_STATEMENT)
    return ("\n".join(lines) + "\n").encode("utf-8")


D6_HEADERS = ("authorization", "cookie", "set-cookie", "x-api-key", "user-agent")  # 22.3 item 6
D6_TOKENS = ("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_")  # 22.3 item 8
_W = "A-Za-z0-9_"  # 22.3: a word character
_RX_D6 = {
    "query-string": re.compile(r"[?&][A-Za-z0-9_.\[\]-]+=", re.ASCII),  # item 2
    "url-with-path": re.compile(r"(?i:https?://)[^\s/]+/\S"),  # item 3
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.ASCII),  # item 4
    "ipv4": re.compile(r"(?<![%s])\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![%s])" % (_W, _W), re.ASCII),  # item 5
    "header-name": re.compile(r"(?<![%s])(?i:%s)(?![%s])" % (_W, "|".join(re.escape(h) for h in D6_HEADERS), _W), re.ASCII),  # item 6
    "bearer": re.compile(r"Bearer "),  # item 7
    "token-shape": re.compile(r"(?<![%s])(?:%s)" % (_W, "|".join(re.escape(t) for t in D6_TOKENS)), re.ASCII),  # item 8
}
_RX_D6_SHA = re.compile(r"sha256:[0-9a-f]{64}")  # item 9
_RX_D6_RUN = re.compile(r"[A-Za-z0-9+/=_-]{32,}", re.ASCII)  # item 9


def d6_problems(text):
    """22.3 (D6, PROVISIONAL) items 1 to 9, the reason check, which is also the alert check of 17.8.
    Characters are Unicode code points; a word character is A-Z, a-z, 0-9 or _, and a whole word is
    not preceded or followed by one. Returns the names of the items that refuse the text."""
    if not isinstance(text, str):
        return ["not-text"]
    out = []
    if text == "" or len(text) > 2000:
        out.append("length")  # item 1
    for name, rx in _RX_D6.items():
        if rx.search(text):
            out.append(name)
    rest = _RX_D6_SHA.sub("sha256", text)
    if any(re.search(r"[0-9]", m.group(0)) and re.search(r"[A-Za-z]", m.group(0)) for m in _RX_D6_RUN.finditer(rest)):
        out.append("long-run")  # item 9
    return out


def deployment_log_problems(doc, where, private, st=None, archived_pairs=None):
    """22.4 (v0.8): the rules of one deployment log: the private state/deployments.json when
    `private`, else a release's status/deployments.json. Its shape (deployments/1 as built from the
    text; canonical form is the caller's); numbers 1, 2, ...; published_at not decreasing (the
    publication run's now; an automatic redeploy can share its starter's); run pub-<run id>-<attempt>
    and release data-<snapshot>-<run id>-<attempt> for the entry's dataset; a release once;
    previous the dataset of the entry before; the checker counts (V2b's, I47) have no FAIL; post passed, failed or not-deployed
    once fixed, null only on the newest entry (a release's own, or in the private log while that
    release's run has not completed, 22.4); a
    redeploy's dataset and site commit those of an earlier entry with post passed (a verified pair,
    D13); every dataset an archived manifest's pair when `archived_pairs` is given."""
    p = []
    if st is not None:
        try:
            p += [f"{where}: {e}" for e in schema_errors(doc, (getattr(st, "v08_schemas", None) or build_v08_shapes(st))["deployments"])[:4]]
        except SchemaKeywordError as exc:
            p.append(f"{where}: validator cannot evaluate: {exc}")
    deps = doc.get("deployments") if isinstance(doc, dict) and isinstance(doc.get("deployments"), list) else []
    if not private and not deps:
        p.append(f"{where}: a release's log has at least its own entry (22.4)")
    seen_tags = set()
    for i, e in enumerate(deps):
        if not isinstance(e, dict):
            p.append(f"{where}: deployments[{i}] is not an object")
            continue
        w = f"{where}: entry {i + 1}"
        if e.get("number") != i + 1:
            p.append(f"{w}: number {e.get('number')!r}, the entries are numbered 1, 2, ... and numbers never repeat (22.4)")
        prev = deps[i - 1] if i and isinstance(deps[i - 1], dict) else None
        if prev is not None and is_time(prev.get("published_at")) and is_time(e.get("published_at")) and e["published_at"] < prev["published_at"]:
            p.append(f"{w}: published_at {e['published_at']} is before the entry before ({prev['published_at']}); oldest first (22.4)")
        want_prev = prev.get("dataset") if prev is not None else None
        if e.get("previous") != want_prev:
            p.append(f"{w}: previous {e.get('previous')}, the dataset of the entry before it is {want_prev} (22.4)")
        ds = e.get("dataset") if isinstance(e.get("dataset"), dict) else {}
        run, tag = e.get("run"), e.get("release")
        mt_run = re.fullmatch(r"pub-(.+)-(\d+)", run) if isinstance(run, str) else None
        if isinstance(tag, str) and mt_run and tag != f"data-{ds.get('snapshot')}-{mt_run.group(1)}-{mt_run.group(2)}":
            p.append(f"{w}: release {tag} is not data-<snapshot>-<publish run id>-<attempt> for snapshot {ds.get('snapshot')} and run {run} (22.4, 22.6)")
        if tag in seen_tags:
            p.append(f"{w}: release {tag} appears twice (22.4: a release is never reused)")
        seen_tags.add(tag)
        ver = e.get("verification") if isinstance(e.get("verification"), dict) else {}
        chk = ver.get("checker") if isinstance(ver.get("checker"), dict) else {}
        if chk.get("fail") not in (0, None):
            p.append(f"{w}: verification.checker.fail {chk.get('fail')}: the checker counts are V2b's, and a release is made only when V2 passes (22.4 I47, 22.5)")
        post = ver.get("post")
        last = i == len(deps) - 1
        if post is None and not last:
            p.append(f"{w}: post null on an earlier entry; a post once fixed is copied unchanged, null only on the newest entry (22.4)")
        if post is not None and not private and last:
            p.append(f"{w}: the release's own entry has post {post!r}; it is null in the release that adds it (22.4)")
        if e.get("trigger") == "redeploy":
            ok = any(isinstance(x, dict) and x.get("dataset") == e.get("dataset") and x.get("site_commit") == e.get("site_commit")
                     and (x.get("verification") or {}).get("post") == "passed" for x in deps[:i])
            if not ok:
                p.append(f"{w}: a redeploy whose dataset and site commit are not those of an earlier entry with post passed (a verified pair, 22.4, D13)")
        if archived_pairs is not None and ds and (ds.get("snapshot"), ds.get("manifest_sha256")) not in archived_pairs:
            p.append(f"{w}: dataset {ds.get('snapshot')} {str(ds.get('manifest_sha256'))[:16]} is not the pair of any archived manifest (22.3: a publication copies an accepted dataset)")
    return p


def log_chain_problems(new_doc, prev_doc, where="the log"):
    """22.4: the log in a new release equals the log of the newest earlier release with that
    release's own last entry's post fixed (passed, failed or not-deployed), plus exactly one new
    entry numbered one higher; the first release's log has one entry with previous null."""
    new = new_doc.get("deployments") if isinstance(new_doc, dict) and isinstance(new_doc.get("deployments"), list) else []
    if prev_doc is None:
        return [] if len(new) == 1 else [f"{where} has {len(new)} entries but no earlier release is given: the first release's log has one entry, and a later one extends the newest earlier release's (22.4, 22.5 check 8)"]
    old = prev_doc.get("deployments") if isinstance(prev_doc, dict) and isinstance(prev_doc.get("deployments"), list) else []
    p = []
    if len(new) != len(old) + 1:
        return [f"{where} has {len(new)} entries; the newest earlier release's has {len(old)}, so it needs exactly {len(old) + 1} (22.4)"]
    for i, (a, b) in enumerate(zip(old, new)):
        if i < len(old) - 1:
            if a != b:
                p.append(f"{where}: entry {i + 1} differs from the earlier release's (a post once fixed is copied unchanged, 22.4)")
            continue
        a2 = json.loads(json.dumps(a))
        b2 = json.loads(json.dumps(b))
        bpost = ((b2.get("verification") or {}).get("post"))
        if ((a2.get("verification") or {}).get("post")) is not None:
            p.append(f"{where}: the earlier release's own entry {i + 1} has post set; a release adds its entry with post null (22.4)")
        if bpost not in ("passed", "failed", "not-deployed"):
            p.append(f"{where}: entry {i + 1}, the earlier release's own, has post {bpost!r}; it is fixed to passed, failed or not-deployed (22.4)")
        for x in (a2, b2):
            if isinstance(x.get("verification"), dict):
                x["verification"]["post"] = None
        if a2 != b2:
            p.append(f"{where}: entry {i + 1} differs from the earlier release's own entry in more than its post (22.4)")
    return p


def rx_reg_copy_name(sha):
    return f"registry/econ-{sha[:16]}.json"


def rc_v08(ctx):
    """T119 to T125 (v0.8)."""
    rv, st = ctx.rv, ctx.st
    vers = registry_versions(st)
    by_hash = registry_by_hash(st)
    boundary = rx_v08_from(ctx)
    live_m = ctx.manifest if isinstance(ctx.manifest, dict) else {}
    manifests = [(f"archive/manifests/{n}", m) for n, m, err in ctx.arch_manifests if not err and isinstance(m, dict)]
    live_is_v4 = live_m.get("schema") == MANIFEST_V4

    # T119: the manifest version (22.9 'Files written under v0.7', I2, I22)
    p, n3, n4, seen4 = [], 0, 0, None
    for name, m in sorted(manifests, key=lambda x: str(x[1].get("generated_at"))) + ([("live/manifest.json", live_m)] if live_m else []):
        sch, t = m.get("schema"), m.get("generated_at")
        if sch == MANIFEST_V4:
            n4 += 1
            seen4 = seen4 or (name, t)
        elif sch == SCHEMA_IDS["manifest"]:
            n3 += 1
            if seen4 is not None and str(t) > str(seen4[1]):
                p.append(f"{name}: rmf.econ.manifest/3 generated at {t}, after the manifest/4 {seen4[0]} ({seen4[1]}): no manifest/3 is generated after a manifest/4 (22.9)")
        else:
            p.append(f"{name}: schema {sch!r} is neither rmf.econ.manifest/3 nor rmf.econ.manifest/4 (9)")
    p += [f"live/status/{f}: status/ holds runs.json and publications.json only; status/deployments.json is added by a publication to the artifact alone (22.3)"
          for f in sorted(x[7:] for x in rv.files(rv.live) if x.startswith("status/")) if f not in ("runs.json", "publications.json")]
    check("T119 no manifest/3 is generated after a manifest/4 in the archive; every manifest is one or the other (9, 22.9, I2: a file's own version marks it); live/status/ holds runs.json and publications.json only (22.3)", p,
          f"{n3} manifest/3, {n4} manifest/4")

    v4 = [(n, m) for n, m in manifests if m.get("schema") == MANIFEST_V4]
    live_name = ctx.arch_manifests[-1][0] if ctx.arch_manifests else None
    # T120: deadline and stale_at (9, D7)
    p, n = [], 0
    for name, m in v4:
        snap = ctx.snaps.get((m.get("snapshot") or {}).get("id"))
        if snap is None:
            continue  # T40 reports it
        want = v08_expect_deadlines(st, snap)
        for sid, summ in sorted((m.get("series") or {}).items()):
            if sid not in st.series or not isinstance(summ, dict):
                continue
            n += 1
            wd, ws = want[sid]
            if summ.get("deadline") != wd:
                p.append(f"{name} {sid}: deadline {summ.get('deadline')}, the 14.2 deadline of its next unseen period is {wd}")
            if summ.get("stale_at") != ws:
                p.append(f"{name} {sid}: stale_at {summ.get('stale_at')}, its staleness rule measured from that deadline gives {ws}")
    check("T120 every manifest/4 series has deadline (the 14.2 deadline of its next unseen period) and stale_at (its staleness rule measured from that deadline; a series that follows another takes its stale_at), both null when not yet published (9, 21.4, D7)", p, f"{n} series entries in {len(v4)} manifest/4")

    # T121: revision CSVs (10, 9)
    p, n, csv_cache = [], 0, {}
    for name, m in v4:
        is_live = name == f"archive/manifests/{live_name}"
        reg = (rx_registry_for(ctx, ((m.get("rules") or {}).get("registry") or {}).get("sha256")) or (None, None, st.registry))[2]
        for sid, summ in sorted((m.get("series") or {}).items()):
            if sid not in st.series or not isinstance(summ, dict):
                continue
            revs = summ.get("revisions") if isinstance(summ.get("revisions"), list) else []
            csvs = summ.get("revision_csvs") if isinstance(summ.get("revision_csvs"), list) else None
            if csvs is None:
                p.append(f"{name} {sid}: no revision_csvs list (9 v0.8)")
                continue
            if len(csvs) != len(revs):
                p.append(f"{name} {sid}: {len(csvs)} revision_csvs for {len(revs)} revisions entries (9: one per entry, in the same order)")
            for r, c in zip(revs, csvs):
                if not isinstance(r, dict) or not isinstance(c, dict):
                    continue
                n += 1
                mr = RX_LOG_PATH.fullmatch(str(r.get("path")))
                mc = RX_REVCSV_PATH.fullmatch(str(c.get("path")))
                if not mc:
                    p.append(f"{name} {sid}: revision CSV path {c.get('path')!r} is not revisions/<series>/<YYYY>/<16 hex>.csv (10)")
                    continue
                if mr and (mc.group(1), mc.group(2)) != (mr.group(1), mr.group(2)):
                    p.append(f"{name} {sid}: {c.get('path')} is not beside its log version {r.get('path')} (10: same series and year)")
                if mc.group(1) != sid:
                    p.append(f"{name} {sid}: {c.get('path')} is under another series")
                if not is_sha256(c.get("sha256")) or mc.group(3) != c["sha256"][:16]:
                    p.append(f"{name} {sid}: {c.get('path')} is not named by the first 16 hex of its sha256 (9: every file the manifest names is content-addressed; reading: its own hash)")
                key = (c.get("path"), c.get("sha256"), r.get("path"), reg.get("conventions"), is_live)
                if key not in csv_cache:
                    msg = None
                    data = rv.read(rv.arch, c.get("path"))
                    log, lerr = rv.load(rv.arch, r.get("path"))
                    if data is None:
                        msg = f"{c.get('path')} is not in archive/files/ (22.9: written into archive/files/ with every manifest)"
                    elif sha256_hex(data) != c.get("sha256"):
                        msg = f"archive/files/{c.get('path')} has sha256 {sha256_hex(data)[:16]}, the manifest says {str(c.get('sha256'))[:16]}" + hash_mismatch_note(data, c.get("sha256"))
                    elif lerr or not isinstance(log, dict):
                        msg = f"its log version {r.get('path')}: {lerr or 'not an object'}"
                    else:
                        want = revision_csv_bytes(reg, st.series[sid], int(mc.group(2)), [x for x in log.get("records", []) if isinstance(x, dict)])
                        if data != want:
                            msg = f"{c.get('path')} differs from the CSV of 10 built from {r.get('path')} and the registry at {first_line_difference(data, want)}"
                    if msg is None and is_live:
                        ld = rv.read(rv.live, c.get("path"))
                        if ld != data:
                            msg = f"live/{c.get('path')} is {'missing' if ld is None else 'not the archived bytes'} (the live manifest names it)"
                    csv_cache[key] = msg
                if csv_cache[key]:
                    p.append(f"{name} {sid}: {csv_cache[key]}")
    check("T121 every manifest/4 series lists revision_csvs, one per revisions entry in the same order, each at revisions/<series>/<YYYY>/<16 hex>.csv beside its log version, content-addressed, in archive/files/ (and live/ for the live manifest), its bytes the CSV of 10: the title line with the year, attribution, notice, terms, the header and one row per record, quoted fields, {year} from the newest detected_at (9, 10 v0.8, D17; reading: revision_csvs is a per-series field like revisions)", p,
          f"{n} revision CSV(s)")

    # T122: the rule files (22.9) and registry_versions
    p, n = [], 0
    hol_bytes = canon_bytes(st.holiday_doc) if getattr(st, "holiday_doc", None) is not None else None
    for name, m in v4:
        is_live = name == f"archive/manifests/{live_name}"
        rules = m.get("rules") if isinstance(m.get("rules"), dict) else {}
        snap = ctx.snaps.get((m.get("snapshot") or {}).get("id")) or {}
        refs = []
        for key, rx in (("registry", RX_REGCOPY_PATH), ("holidays", RX_HOLCOPY_PATH), ("notice", RX_NOTICE_PATH)):
            r = rules.get(key)
            if not isinstance(r, dict):
                p.append(f"{name}: rules.{key} missing (9 v0.8)")
                continue
            refs.append((key, r, rx))
        for i, r in enumerate(rules.get("registry_versions") if isinstance(rules.get("registry_versions"), list) else []):
            refs.append((f"registry_versions[{i}]", r, RX_REGCOPY_PATH))
        if not isinstance(rules.get("registry_versions"), list):
            p.append(f"{name}: rules.registry_versions is not a list (9 v0.8; reading: present, empty when no older registry version is in the window)")
        for key, r, rx in refs:
            n += 1
            path, sha = r.get("path"), r.get("sha256")
            mt = rx.fullmatch(str(path))
            if not mt or not is_sha256(sha) or mt.group(1) != sha[:16]:
                p.append(f"{name}: rules.{key} {path!r} is not its content address for sha256 {str(sha)[:16]} (9, 22.9)")
                continue
            data = rv.read(rv.arch, path)
            if data is None:
                p.append(f"{name}: rules.{key} {path} is not in archive/files/ (22.9)")
                continue
            if sha256_hex(data) != sha:
                p.append(f"{name}: archive/files/{path} has sha256 {sha256_hex(data)[:16]}, rules.{key} says {sha[:16]}" + hash_mismatch_note(data, sha))
                continue
            if is_live and rv.read(rv.live, path) != data:
                p.append(f"{name}: live/{path} is missing or differs (the live manifest names it, 22.9)")
            if key.startswith("registry"):
                _, cprob = registry_copy_problems(st, data, sha)
                if cprob:
                    p.append(f"{name}: {path} is not a valid canonical registry: {cprob[0]} (22.9: checked against the registry schema)")
                found = rx_registry_for(ctx, sha)
                if found is None:
                    p.append(f"{name}: rules.{key} {path} ({sha[:16]}) is found neither as the current registry, an archived copy of a v0.8 run, nor by the I7 derivation (22.9, I44: refused)")
                elif data != found[1]:
                    p.append(f"{name}: {path} is not the canonical JSON of registry version {found[0]} (22.9)")
            elif key == "holidays":
                if is_live and hol_bytes is not None and data != hol_bytes:
                    p.append(f"{name}: {path} is not the canonical JSON of the holiday table in use (pipeline/registry/fed-holidays.json, 22.9)")
            elif key == "notice":
                own = rx_registry_for(ctx, (rules.get("registry") or {}).get("sha256"))
                reg = own[2] if own else st.registry
                if is_time(m.get("generated_at")):
                    want = notice_file_bytes(reg, m["generated_at"])
                    if data != want:
                        p.append(f"{name}: {path} differs from the notice file of 22.9 at {first_line_difference(data, want)}")
        own_sha = (rules.get("registry") or {}).get("sha256")
        if m.get("rollback") is None and (snap.get("run") or {}).get("registry_sha256") not in (None, own_sha):
            p.append(f"{name}: rules.registry {str(own_sha)[:16]} is not the registry its own snapshot was built with ({str((snap.get('run') or {}).get('registry_sha256'))[:16]}) (22.9: this manifest's own registry)")
        if is_live and hol_bytes is not None and (rules.get("holidays") or {}).get("sha256") != sha256_hex(hol_bytes):
            p.append(f"{name}: rules.holidays does not name the holiday table in use (sha256 {sha256_hex(hol_bytes)[:16]})")
        if is_live:
            snaps_w, _ = rx_window(ctx)
            want = sorted({(ctx.snaps.get(s) or {}).get("run", {}).get("registry_sha256") for s in snaps_w if s in ctx.snaps} - {own_sha, None})
            got = [r.get("sha256") for r in (rules.get("registry_versions") or []) if isinstance(r, dict)]
            want_refs = sorted((rx_reg_copy_name(h), h) for h in want)
            got_refs = [(r.get("path"), r.get("sha256")) for r in (rules.get("registry_versions") or []) if isinstance(r, dict)]
            if got_refs != want_refs:
                p.append(f"{name}: rules.registry_versions names {[x[:16] for x in got]}; the older registry versions named by the window's snapshots are {[x[:16] for x in want]}, in path order (9, 22.9)")
    check("T122 every manifest/4 names its rule files in rules: registry/econ-<16 hex>.json (the canonical JSON of the registry of the run that wrote it; for a manifest that is not a rollback, the one its snapshot records), registry/holidays-<16 hex>.json (the holiday table in use), notices/<16 hex>.txt (the notice file of 22.9: sources in byte order of their ids, each publisher, attribution, notice, license, Terms: and a blank line, per-series lines for {data_name}, then the CC0 statement), and in registry_versions every older registry version a window snapshot names, each the current registry with the substitutions of I7; all content-addressed, in archive/files/ and in live/ for the live manifest (9, 22.9, I7)", p,
          f"{n} rule file reference(s) in {len(v4)} manifest/4")

    # T123: NOTICE.txt (22.9)
    p = []
    nt = rv.read(rv.live, "NOTICE.txt")
    if rv.read(rv.arch, "NOTICE.txt") is not None:
        p.append("archive/files/NOTICE.txt exists; NOTICE.txt is live only (22.9)")
    if live_is_v4:
        ref = (live_m.get("rules") or {}).get("notice") or {}
        named = rv.read(rv.live, ref.get("path")) if isinstance(ref.get("path"), str) else None
        if nt is None:
            p.append("live/NOTICE.txt is missing (22.9: a convenience copy of the notice file at the root)")
        elif named is not None and nt != named:
            p.append(f"live/NOTICE.txt differs from the named notice {ref.get('path')} at {first_line_difference(nt, named)}")
    elif nt is not None:
        p.append("live/NOTICE.txt exists although the live manifest is not rmf.econ.manifest/4 (a v0.7 run writes no rule files)")
    check("T123 live/NOTICE.txt equals the notice file the live manifest/4 names, is not archived and is not named by the manifest (22.9)", p,
          "live manifest is manifest/4" if live_is_v4 else "live manifest is manifest/3: no NOTICE.txt")

    # T124: the reasons of operations from the first v0.8 run on (21.6, D6)
    p, n_new, n_old_bad = [], 0, 0
    q, _ = rv.load(rv.state, "review-queue.json")
    pins, _ = rv.load(rv.state, "pins.json")
    texts = []
    cur_h, v07_h = vers["current"][0], vers["v0.7"][0]
    v08_snap = lambda sid_: cur_h != v07_h and ((ctx.snaps.get(sid_) or {}).get("run") or {}).get("registry_sha256") == cur_h  # noqa: E731
    v4_at = {m.get("generated_at") for _, m in manifests if m.get("schema") == MANIFEST_V4}
    for d in (q.get("decisions") if isinstance(q, dict) and isinstance(q.get("decisions"), list) else []):
        if isinstance(d, dict) and d.get("decision") in ("approve", "reject", "clear"):
            texts.append((v08_snap((d.get("publication") or {}).get("snapshot")), f"review decision {d.get('decision')} of {d.get('series')} at {d.get('decided_at')}", d.get("reason")))
    for f in rv.files(rv.rollbacks):
        rec, err = rv.load(rv.rollbacks, f)
        if not err and isinstance(rec, dict):
            texts.append((rec.get("at") in v4_at, f"rollback record {f}", rec.get("reason")))
    if isinstance(pins, dict):
        for x in pins.get("pins") or []:
            if isinstance(x, dict):
                texts.append((True, f"pin of {x.get('snapshot')}", x.get("reason")))
        for x in pins.get("unpinned") or []:
            if isinstance(x, dict):
                texts.append((True, f"unpin of {x.get('snapshot')}", x.get("reason")))
    for is_v08, label, text in texts:
        bad = d6_problems(text)
        if is_v08:
            n_new += 1
            if bad:
                p.append(f"{label}: the reason fails {', '.join(bad)} (21.6: refused before any write, so it is never accepted)")
        elif bad:
            n_old_bad += 1
    check("T124 every reason of an operation run by v0.8 code passes the reason check of 22.3: a review whose snapshot records the v0.8 registry, a rollback whose manifest is manifest/4, and every pin and unpin (21.6, 22.9; PROVISIONAL)", p,
          f"{n_new} reason(s) of v0.8 operations" + (f"; {n_old_bad} earlier reason(s) would fail it and would refuse a publication while in the window (22.5 check 6)" if n_old_bad else ""))

    # T125: the v0.8 alert keys (17.8)
    p = []
    doc, err = rv.load(rv.state, "alerts.json")
    opens = doc.get("open") if not err and isinstance(doc, dict) and isinstance(doc.get("open"), list) else []
    for a in opens:
        if not isinstance(a, dict):
            continue
        k, sev = a.get("key"), a.get("severity")
        if k in ("publication-behind", "publication-facts-unavailable") and sev != "warning":
            p.append(f"{k} has severity {sev!r}; 17.8 gives a warning")
        head = str(k).split(":", 1)[0]
        if k in NOT_COLLECTION_KEYS and (k in ("publish-failed", "publication-verify-failed", "publication-history-changed") or rx_v08_from(ctx) is not None):
            p.append(f"alerts.json lists {k}; its owner is {NOT_COLLECTION_KEYS[k]}, and it never enters the collection ledger (21.5, 22.6 table)")
        if head in ("series-stale", "series-held") and rx_v08_from(ctx) is not None:
            p.append(f"alerts.json lists {k}; from v0.8 the self-check gives only the run keys, and series-stale and series-held are not delivered (17.8 layer 2)")
    for rec in rx_records_in_time(ctx):
        if not rx_v08(ctx, rec.get("started_at")):
            continue  # reading: a v0.7 run's self-check could list the 14.3 manifest findings
        for k in rec.get("alerts") or []:
            if k in NOT_COLLECTION_KEYS or str(k).split(":", 1)[0] in ("series-stale", "series-held"):
                p.append(f"run record {rec.get('id')} lists {k}, which a v0.8 collection run never raises (17.8 layer 2, 21.5, 22.6 table)")
    check("T125 the alert keys and their owners (22.6 table, 17.8 layer 2): publication-behind and publication-facts-unavailable are warnings of the collection run; publish-failed and publication-verify-failed (publish.yml report) and publication-history-changed never enter the collection ledger; from v0.8 neither do manifest-missing and manifest-overdue (the watcher's) nor series-stale and series-held (not delivered), in the ledger or a v0.8 run record (reading: v0.8 from the first manifest/4 or v0.8 snapshot)", p,
          f"{len(opens)} open alert(s)")


SCENARIO_CHECKS = ("T84", "T103", "T104", "T114")  # the checks that follow the table of appendix B (21.3: not in live mode)


def root_context(st, rv, legacy_until=None, live=False, quiet=False, legacy_ff=None):
    """The view of a pipeline root the T checks read (also used by the state modes, 21.4).
    `legacy_ff`: whether the collector.json written before the boundary of 21.1 carried
    full_fetches (the state mode reads it from the Stage B folder); None lets T116 infer it."""
    ctx = State()
    ctx.legacy_ff = legacy_ff
    ctx.st, ctx.rv, ctx.reg_ids = st, rv, set(st.series)
    ctx.obs_cache, ctx.window, ctx.significant, ctx.log_versions, ctx.named_cache, ctx.logs_as_of = {}, None, None, {}, {}, None
    ctx.run_records, ctx.lock_history, ctx.full_plan = None, None, None
    ctx.legacy_until = legacy_until
    if legacy_until is None:
        # 21.1 (v0.7, F10): a working root holds archive/state/accepted.json (the state files are
        # imported, 21.3); it names the promoted dataset, and the manifests and snapshots whose time
        # is not after the promoted snapshot's are read by exactly three v0.6 rules (T46, T55, T116).
        # Without it every rule is strict.
        acc, acc_err = rv.load(rv.state, "accepted.json")
        snap = ((acc.get("dataset") or {}).get("snapshot")) if not acc_err and isinstance(acc, dict) else None
        if is_snapshot_id(snap):
            ctx.legacy_until = fmt_utc(snapshot_time(snap))
            if not quiet:
                print(f"check_p22.py: archive/state/accepted.json names the promoted dataset {snap}: the manifests and snapshots up to {ctx.legacy_until}, and collector.json until a run after it rewrites it, may have the v0.6 or the v0.7 form under the three rules of 21.1 (T46, T55, T116)")
    ctx.snaps = {}
    for f in rv.files(rv.arch):
        mt = RX_SNAPSHOT_PATH.fullmatch(f)
        v, err = rv.load(rv.arch, f) if mt else (None, "not a snapshot path")
        if mt and not err and isinstance(v, dict):
            ctx.snaps[mt.group(1)] = v
    ctx.order = sorted(ctx.snaps)
    ctx.arch_manifests = []
    for f in rv.files(rv.manifests):
        v, err = rv.load(rv.manifests, f)
        if not err and not isinstance(v, dict):
            v, err = None, "not an object"
        ctx.arch_manifests.append((f, v, err))
    ctx.manifest, ctx.manifest_err = rv.load(rv.live, "manifest.json")
    if not ctx.manifest_err and isinstance(ctx.manifest, dict):
        ctx.cur_id = (ctx.manifest.get("snapshot") or {}).get("id")
        ctx.cur = ctx.snaps.get(ctx.cur_id)
    else:
        ctx.cur_id, ctx.cur = None, None
    return ctx


def section_root(st, root, live=False, rv=None, legacy_until=None, legacy_ff=None):
    global ROOT_MODE
    ROOT_MODE = True
    rv = rv or RootView(root)
    print(f"check_p22.py: pipeline root {rv.root}" + (" (live mode, 21.3: the appendix B checks T84, T103, T104 and T114 are not run)" if live else ""))
    if not rv.root.is_dir():
        check("T31 the root has live/, archive/files/, archive/manifests/, archive/holds/ and archive/state/ with its state files (17.1)", [f"{rv.root} is not a directory"])
        return None
    ctx = root_context(st, rv, legacy_until, live, legacy_ff=legacy_ff)
    manifest_err = ctx.manifest_err
    guarded("T31 to T33 layout", rc_layout, ctx)
    guarded("T34 canonical JSON", rc_canonical, ctx)
    guarded("T35 schemas", rc_schemas, ctx)
    if manifest_err or not isinstance(ctx.manifest, dict):
        # 17.2: no manifest means nothing is published yet. The checks that read only the run
        # records and the state files still run, so a root whose runs all failed is still examined.
        check("T36 every registered series is in the live manifest, and no other (9)", [f"live/manifest.json: {manifest_err or 'not an object'}"])
        ctx.manifest, ctx.cur_id, ctx.cur = {}, None, None
        for label, fn in (("T72 to T73 runs", rc_runs), ("T69 review queue", rc_review_queue), ("T70 to T71 alerts", rc_alerts), ("T95 refusals", rc_refusals),
                          ("T98 to T99 absences", rc_absences), ("T100 due groups", rc_due), ("T101 route alerts", rc_route_alerts),
                          ("T116 full fetches", rc_full_fetches), ("T117 line endings", rc_line_endings), ("T118 alert keys of v0.7", rc_alert_keys_v07),
                          ("T119 to T125 v0.8", rc_v08),
                          ("T84 appendix B", rc_scenario), ("T103 to T104 appendix B in v0.4", rc_scenario_v04), ("T114 appendix B in v0.5", rc_scenario_v05)):
            if not (live and label.startswith(SCENARIO_CHECKS)):
                guarded(label, fn, ctx)
        return ctx
    ctx.cur_id = (ctx.manifest.get("snapshot") or {}).get("id")
    ctx.cur = ctx.snaps.get(ctx.cur_id)
    for label, fn in (("T36 to T38 live manifest", rc_manifest_live), ("T39 to T41 archived manifests", rc_manifest_archive),
                      ("T42 to T43 snapshots", rc_snapshots), ("T44 series states", rc_snapshot_state), ("T45 to T46 snapshot chain", rc_snapshot_chain),
                      ("T47 to T49 objects", rc_objects), ("T77 first change point", rc_first_change_point), ("T78 to T80 safeguards", rc_safeguards), ("T50 released", rc_released), ("T51 to T57 manifest summaries and CSVs", rc_manifest_summaries),
                      ("T58 to T59 revision logs", rc_revision_logs), ("T60, T83 revision records and rollbacks", rc_revision_records), ("T61 provenance", rc_provenance), ("T85, T105 to T107, T110, T111 locks", rc_locks), ("T86 withdrawals", rc_withdrawals),
                      ("T62 to T63 archive", rc_archive), ("T64 held candidates", rc_holds), ("T65 pins", rc_pins), ("T66 to T68 live window", rc_window),
                      ("T69 review queue", rc_review_queue), ("T81 review records", rc_reviews), ("T82 publication record", rc_publications), ("T70 to T71 alerts", rc_alerts), ("T72 to T73 runs", rc_runs), ("T74 to T75 budgets", rc_budgets),
                      ("T87 to T93 CSV segments", rc_csv_segments), ("T94 review authorization", rc_review_authorization), ("T95 refusals", rc_refusals),
                      ("T96 publication outcomes", rc_publication_outcomes), ("T97 held candidates kept", rc_candidates_kept), ("T98 to T99 absences", rc_absences),
                      ("T100 due groups", rc_due), ("T101 route alerts", rc_route_alerts), ("T102, T112 windowed candidates", rc_windowed),
                      ("T108 clear", rc_clear), ("T109 locks in the review queue", rc_queue_locks), ("T113 missing versus zero", rc_zero),
                      ("T116 full fetches", rc_full_fetches), ("T117 line endings", rc_line_endings), ("T118 alert keys of v0.7", rc_alert_keys_v07),
                      ("T119 to T125 v0.8", rc_v08),
                      ("T84 appendix B", rc_scenario), ("T103 to T104 appendix B in v0.4", rc_scenario_v04), ("T114 appendix B in v0.5", rc_scenario_v05)):
        if not (live and label.startswith(SCENARIO_CHECKS)):
            guarded(label, fn, ctx)
    return ctx


# END ROOT MODE
# ---------------------------------------------------------------------------


def compare_mode(collection, out):
    """20.4 (v0.6): the comparison mode lives in compare_saved.py beside this file, loaded by its
    path (python -I keeps this folder off sys.path); it shares no code with the pipeline."""
    import importlib.util
    path = Path(__file__).resolve().parent / "compare_saved.py"
    spec = importlib.util.spec_from_file_location("rmf_check_compare_saved", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run(collection, out, ROOT)


def load_helper(file_name, module_name):
    """A helper beside this file, loaded by its path (python -I keeps this folder off sys.path)."""
    import importlib.util
    path = Path(__file__).resolve().parent / file_name
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


USAGE = ("usage: python -I tests/datacheck/check_p22.py [--registry <file>] [--root <dir> [--live]]\n"
         "       python -I tests/datacheck/check_p22.py [--registry <file>] --state <store dir>\n"
         "       python -I tests/datacheck/check_p22.py --state-scenario <dir>\n"
         "       python -I tests/datacheck/check_p22.py [--registry <file>] --publication <econ dir or artifact.tar.gz> --state <store dir> [--previous-release <release dir>]\n"
         "       python -I tests/datacheck/check_p22.py [--registry <file>] --release <release dir> [--expect <snapshot>:<sha256>] [--previous-release <release dir>]\n"
         "       python -I tests/datacheck/check_p22.py [--registry <file>] --release-history <folder of release folders> [--deployed <deployed status/deployments.json>]\n"
         "       python -I tests/datacheck/check_p22.py [--registry <file>] --publication-scenario <dir>\n"
         "       python -I tests/datacheck/check_p22.py --compare-saved <collection dir> [--compare-out <file.json>]")


def run_plain_sections(st, live):
    """The plain checks: all of them, or in the live modes only those the root checks rest on."""
    guarded("holiday table", load_holiday_table, st)
    guarded("v0.8 self-tests", lambda: load_helper("check_publication.py", "rmf_check_publication").section_selftests_v08(sys.modules[__name__], st))
    guarded("canonical JSON", section_canonical, st)
    guarded("schemas", section_schemas, st)
    if not live:
        guarded("tree", section_tree, st)
    guarded("registry", section_registry, st)
    guarded("holiday table and known gaps", section_holidays, st)
    if not live:
        guarded("collector fixtures", section_raw_fixtures, st)
        guarded("source records", section_source_records, st)
        guarded("facts", section_facts, st)
        guarded("change points", section_change_points, st)


def main(argv=None):
    global LIVE_MODE, REGISTRY
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["--registry"] and len(argv) >= 2:
        # Self-tests only: another registry file (with fed-holidays.json beside it), for example the
        # committed one with the v0.8 substitutions of 22.9 applied, before the pipeline commits it.
        REGISTRY = Path(argv[1]).resolve()
        argv = argv[2:]
        print(f"check_p22.py: registry {REGISTRY} (given with --registry, not the committed one)")
    pub = {}
    for flag in ("--publication", "--release", "--release-history", "--publication-scenario"):
        if argv[:1] == [flag] and len(argv) >= 2:
            pub = {"mode": flag, "target": argv[1]}
            rest, opts = argv[2:], {}
            while len(rest) >= 2 and rest[0] in ("--state", "--expect", "--previous-release", "--deployed") and rest[0] not in opts:
                opts[rest[0]] = rest[1]
                rest = rest[2:]
            allowed = {"--publication": {"--state", "--previous-release"}, "--release": {"--expect", "--previous-release"}, "--release-history": {"--deployed"}}.get(flag, set())
            if rest or set(opts) - allowed or (flag == "--publication" and "--state" not in opts):
                print(USAGE)
                return 2
            pub.update(state=opts.get("--state"), expect=opts.get("--expect"), previous=opts.get("--previous-release"), deployed=opts.get("--deployed"))
            break
    if pub:
        LIVE_MODE = True
        print(f"check_p22.py: independent checker for DATA_CONVENTIONS {CONVENTIONS}, {pub['mode'][2:]} mode (repository {ROOT})")
        st = load_state()
        run_plain_sections(st, True)
        cp = load_helper("check_publication.py", "rmf_check_publication")
        if pub["mode"] == "--publication":
            guarded("publication", cp.run_publication, sys.modules[__name__], st, pub["target"], pub["state"], pub["previous"])
        elif pub["mode"] == "--release":
            guarded("release", cp.run_release, sys.modules[__name__], st, pub["target"], pub["expect"], pub["previous"])
        elif pub["mode"] == "--release-history":
            guarded("release history", cp.run_release_history, sys.modules[__name__], st, pub["target"], pub["deployed"])
        else:
            guarded("publication scenario", cp.run_pub_scenario, sys.modules[__name__], st, pub["target"])
        print(f"SUMMARY {COUNTS['PASS']} PASS, {COUNTS['FAIL']} FAIL, {COUNTS['SKIP']} SKIP")
        return 1 if COUNTS["FAIL"] else 0
    if "--compare-saved" in argv:
        opts, rest = {}, list(argv)
        while rest:
            flag = rest.pop(0)
            if flag in ("--compare-saved", "--compare-out") and rest and flag not in opts:
                opts[flag] = rest.pop(0)
            else:
                print(USAGE)
                return 2
        if "--compare-saved" not in opts:
            print(USAGE)
            return 2
        return compare_mode(opts["--compare-saved"], opts.get("--compare-out"))
    root = state_dir = scenario_dir = None
    live = False
    if len(argv) == 2 and argv[0] == "--state":
        state_dir = argv[1]
    elif len(argv) == 2 and argv[0] == "--state-scenario":
        scenario_dir = argv[1]
    elif argv[:1] == ["--root"] and len(argv) in (2, 3) and argv[2:] in ([], ["--live"]):
        root, live = argv[1], argv[2:] == ["--live"]
    elif argv:
        print(USAGE)
        return 2
    LIVE_MODE = live or state_dir is not None or scenario_dir is not None
    mode = ("live root mode" if live else "state store mode" if state_dir else
            "state scenario mode" if scenario_dir else "root mode" if root else "plain mode")
    print(f"check_p22.py: independent checker for DATA_CONVENTIONS {CONVENTIONS}, {mode} (repository {ROOT})")
    st = load_state()
    run_plain_sections(st, LIVE_MODE)
    if root is not None:
        guarded("pipeline root", section_root, st, root, live)
    if state_dir is not None or scenario_dir is not None:
        cs = load_helper("check_state.py", "rmf_check_state")
        if state_dir is not None:
            guarded("state store", cs.run_state, sys.modules[__name__], st, state_dir)
        else:
            guarded("state scenario", cs.run_scenario, sys.modules[__name__], st, scenario_dir)
    print(f"SUMMARY {COUNTS['PASS']} PASS, {COUNTS['FAIL']} FAIL, {COUNTS['SKIP']} SKIP")
    return 1 if COUNTS["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
