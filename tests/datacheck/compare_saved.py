"""Comparison mode of the independent checker: DATA_CONVENTIONS v0.7, section 20.4 (records of 20.2 v0.7).

    python -I tests/datacheck/check_p22.py --compare-saved <collection dir> [--compare-out <file.json>]

<collection dir> holds responses/<n>-<host>.bin and responses/<n>-<host>.json as section 20.2
defines them. This program reads those live responses and the saved histories of
pipeline/fixtures/raw/ (EFFR JSON, Debt to the Penny JSON pages, the H.6 zip with H6_data.xml,
releaseDates.json) and lists, per source: the request and response status; the records in both;
the new records after the saved data; every record whose fields differ (each field with both
values, compared as the provider's text, never as floating point); saved records missing from
the live response; fields that appear or disappear; the latest period and the publication dates
(H.6 release dates). It never prefers either side and never edits anything: it reads the
collection and the fixtures and writes only the --compare-out file, which may not lie inside the
collection folder.

Written from the text of DATA_CONVENTIONS v0.6 and v0.7, the registry and the fixtures only; it
shares no code with the pipeline, nor with the rest of the checker. Python standard library only.
Every response and fixture is untrusted data: parsed, never executed. Each saved response's record
must have exactly the twelve fields of 20.2 (v0.7, F1) with their types, and its SHA-256 and byte
count are checked against the saved body before it is read; a response that fails is refused,
never compared. XML with a document type or an entity declaration is refused before
parsing; xml.etree never fetches external resources.
"""

import datetime as dt
import decimal
import gzip
import hashlib
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

MAX_RESPONSE_BYTES = 64_000_000        # 20.2: at most 64,000,000 bytes per response
MAX_XML_BYTES = 64 * 1024 * 1024       # 18: a zip member's stated size at most 64 MB before inflating
MAX_INFLATED_BYTES = 256 * 1024 * 1024  # a bound on a gzip body or fixture after inflating
RECORD_FIELDS = ("n", "host", "url", "requested_at", "status", "content_type", "content_length", "etag", "last_modified", "date",
                 "bytes", "sha256")  # 20.2 (v0.7, F1): exactly these twelve, each always present
RECORD_INT_FIELDS = ("n", "status", "bytes")  # 20.2: integers; the others text
RECORD_HEADER_FIELDS = ("content_type", "content_length", "etag", "last_modified", "date")  # the header text, or null
RX_UTC_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", re.ASCII)
RX_JSON_INTEGER = re.compile(r"-?(0|[1-9]\d*)", re.ASCII)
RX_RESPONSE_FILE = re.compile(r"(\d+)-([A-Za-z0-9](?:[A-Za-z0-9.-]{0,252}))\.(bin|json)", re.ASCII)
RX_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)
RX_RELEASE_DATE = re.compile(r"(\d{4})(\d{2})(\d{2})(\**)", re.ASCII)
SOURCE_ORDER = ("nyfed-markets", "fiscaldata", "frb-releases")
KIND_ORDER = ("integrity", "request", "format", "header", "field-set", "copies-differ", "duplicate", "changed-field", "field-appears",
              "field-disappears", "missing-record", "new-record", "earlier-record", "inserted-record", "not-in-received-pages", "latest-period",
              "release-dates", "note")


class Num(str):
    """A JSON number kept as the provider's text."""


class JsonRefused(ValueError):
    pass


def _pairs(pairs):
    seen = set()
    for k, _ in pairs:
        if k in seen:
            raise JsonRefused(f"duplicate key {k!r}")
        seen.add(k)
    return dict(pairs)


def _constant(name):
    raise JsonRefused(f"non-standard constant {name}")


def load_json(data):
    """UTF-8 JSON, numbers kept as their text, duplicate keys and NaN or Infinity refused."""
    text = data.decode("utf-8")  # UnicodeDecodeError is a format failure for the caller
    return json.loads(text, parse_float=Num, parse_int=Num, parse_constant=_constant, object_pairs_hook=_pairs)


def jtext(v):
    """The provider's text of a JSON value: a number as written, a string as JSON text (quotes
    included, so a type change shows), and so on."""
    if isinstance(v, Num):
        return str(v)
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ",".join(jtext(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + jtext(x) for k, x in sorted(v.items())) + "}"
    return json.dumps(v)


def same_decimal(a, b):
    """Whether two provider texts denote the same decimal number (an annotation only; the
    comparison itself is on the text). Decimal arithmetic, never floating point."""
    try:
        da = decimal.Decimal(a.strip('"')) if isinstance(a, str) else None
        db = decimal.Decimal(b.strip('"')) if isinstance(b, str) else None
    except (decimal.InvalidOperation, ValueError):
        return None
    if da is None or db is None or not da.is_finite() or not db.is_finite():
        return None
    return da == db


def sha256_hex(b):
    return hashlib.sha256(b).hexdigest()


def gunzip_bounded(data, limit=MAX_INFLATED_BYTES):
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as fh:
        while True:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            if out.tell() > limit:
                raise ValueError(f"inflates to more than {limit} bytes")
    return out.getvalue()


def _has_zip64(extra):
    i = 0
    while i + 4 <= len(extra):
        hid = int.from_bytes(extra[i:i + 2], "little")
        size = int.from_bytes(extra[i + 2:i + 4], "little")
        if hid == 0x0001:
            return True
        i += 4 + size
    return False


def read_zip_member(data, name):
    """18: a bounded zip reader: the member's stated size at most 64 MB before inflating, CRC-32
    checked, encryption, zip64 and methods other than stored and deflate refused. Returns
    (bytes, members) or raises ValueError."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"not a zip file ({exc})")
    members = [i.filename for i in zf.infolist()]
    if name not in members:
        raise ValueError(f"no {name} among the zip members {members[:8]}")
    if members.count(name) != 1:
        raise ValueError(f"{name} appears {members.count(name)} times in the zip")
    info = zf.getinfo(name)
    if info.flag_bits & 0x1:
        raise ValueError(f"{name} is encrypted")
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise ValueError(f"{name} uses compression method {info.compress_type}")
    if _has_zip64(info.extra) or info.file_size > 0xFFFFFFFF or info.compress_size > 0xFFFFFFFF:
        raise ValueError(f"{name} is a zip64 entry")
    if info.file_size > MAX_XML_BYTES:
        raise ValueError(f"{name} states {info.file_size} bytes, over 64 MB")
    out = io.BytesIO()
    try:
        with zf.open(info) as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                if out.tell() > info.file_size or out.tell() > MAX_XML_BYTES:
                    raise ValueError(f"{name} inflates beyond its stated size")
    except zipfile.BadZipFile as exc:  # a CRC-32 mismatch is reported here
        raise ValueError(f"{name}: {exc}")
    return out.getvalue(), members


def refuse_dtd(xml_bytes):
    """5, 18: XML with a document type or an entity declaration is refused."""
    low = xml_bytes.lower()
    for token in (b"<!doctype", b"<!entity", b"<!element", b"<!attlist"):
        if token in low:
            raise ValueError(f"the XML holds a {token[2:].decode().upper()} declaration, refused")


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def parse_h6_xml(xml_bytes):
    """The SDMX message as {header: {name: text}, series: [ {attrs, obs: [attrs], dataset} ]}.
    Namespaces are ignored (5: copies in table groups with different namespaces)."""
    refuse_dtd(xml_bytes)
    header, series, dataset = {}, [], None
    stack = []
    for event, el in ET.iterparse(io.BytesIO(xml_bytes), events=("start", "end")):
        name = _local(el.tag)
        if event == "start":
            stack.append(name)
            if name == "DataSet":
                dataset = el.attrib.get("id")
            continue
        stack.pop()
        if len(stack) >= 1 and stack[-1] == "Header" and name not in ("Contact",):
            if len(el) == 0:
                header[name] = (el.text or "").strip()
            else:
                header[name] = {_local(c.tag): (c.text or "").strip() for c in el}
                if el.attrib:
                    header[name]["@attributes"] = dict(el.attrib)
        if name == "Series":
            obs = [dict((_local(k), v) for k, v in o.attrib.items()) for o in el if _local(o.tag) == "Obs"]
            series.append({"attrs": dict((_local(k), v) for k, v in el.attrib.items()), "obs": obs, "dataset": dataset})
            el.clear()
    return {"header": header, "series": series}


def flatten_release_dates(doc):
    """releaseDates.json as [(YYYY-MM-DD, marker text, year entry, month entry)] and its key sets."""
    out, keys = [], {"year": set(), "month": set()}
    if not isinstance(doc, list):
        raise ValueError("releaseDates.json is not a JSON array")
    for y in doc:
        if not isinstance(y, dict):
            raise ValueError("a year entry is not an object")
        keys["year"] |= set(y)
        for m in y.get("Months") or []:
            if not isinstance(m, dict):
                raise ValueError("a month entry is not an object")
            keys["month"] |= set(m)
            for d in m.get("Dates") or []:
                mt = RX_RELEASE_DATE.fullmatch(d) if isinstance(d, str) else None
                if not mt:
                    raise ValueError(f"release date {d!r} is not YYYYMMDD with an optional marker")
                out.append((f"{mt.group(1)}-{mt.group(2)}-{mt.group(3)}", mt.group(4), y.get("yearValue"), m.get("MonthValue")))
    return out, keys


class Report:
    def __init__(self):
        self.findings = []
        self.responses = []
        self.sources = {s: {"requests": [], "notes": []} for s in SOURCE_ORDER}
        self.refused = False

    def add(self, source, kind, key=None, field=None, saved=None, live=None, note=None):
        f = {"source": source, "kind": kind, "key": key, "field": field, "saved": saved, "live": live, "note": note}
        if kind in ("changed-field",) and saved is not None and live is not None:
            f["same_decimal_value"] = same_decimal(saved, live)
        self.findings.append(f)
        return f


def compare_records(rep, source, label, saved, live, key_of, in_request=None, outside_note=None, after_live=None):
    """Compare two lists of records (dicts of provider values) by key. Returns a summary.
    `in_request(key)` says whether the live request covered that key (saved records outside it
    are counted, not reported missing); `after_live` is a key after which the live response
    could not hold records (later pages not received)."""
    def keyed(records, side):
        m, dup = {}, []
        for r in records:
            k = key_of(r)
            if k in m:
                dup.append(k)
            else:
                m[k] = r
        for k in sorted(set(dup), key=str):
            rep.add(source, "duplicate", f"{label} {k}", note=f"the {side} response lists this record {dup.count(k) + 1} times")
        return m
    sm, lm = keyed(saved, "saved"), keyed(live, "live")
    s_keys, l_keys = set(sm), set(lm)
    both = sorted(s_keys & l_keys, key=str)
    s_min, s_max = (min(s_keys, key=str), max(s_keys, key=str)) if s_keys else (None, None)
    n_changed_rec, n_changed_fields, n_appear, n_disappear = 0, 0, 0, 0
    for k in both:
        a, b = sm[k], lm[k]
        changed = False
        for f in sorted(set(a) | set(b)):
            if f in a and f in b:
                ta, tb = jtext(a[f]), jtext(b[f])
                if ta != tb:
                    rep.add(source, "changed-field", f"{label} {k}", f, ta, tb)
                    n_changed_fields += 1
                    changed = True
            elif f in b:
                rep.add(source, "field-appears", f"{label} {k}", f, None, jtext(b[f]))
                n_appear += 1
                changed = True
            else:
                rep.add(source, "field-disappears", f"{label} {k}", f, jtext(a[f]), None)
                n_disappear += 1
                changed = True
        n_changed_rec += changed
    new, earlier, inserted = [], [], []
    for k in sorted(l_keys - s_keys, key=str):
        if s_max is None or str(k) > str(s_max):
            new.append(k)
            rep.add(source, "new-record", f"{label} {k}", note=f"after the saved data (saved latest {s_max})", live=jtext(lm[k]))
        elif str(k) < str(s_min):
            earlier.append(k)
            rep.add(source, "earlier-record", f"{label} {k}", note=f"before the saved data (saved earliest {s_min})", live=jtext(lm[k]))
        else:
            inserted.append(k)
            rep.add(source, "inserted-record", f"{label} {k}", note="within the saved range, absent from the saved history", live=jtext(lm[k]))
    missing, outside, not_received = [], 0, 0
    for k in sorted(s_keys - l_keys, key=str):
        if in_request is not None and not in_request(k):
            outside += 1
        elif after_live is not None and str(k) > str(after_live):
            not_received += 1
        else:
            missing.append(k)
            rep.add(source, "missing-record", f"{label} {k}", saved=jtext(sm[k]), note="in the saved history, not in the live response")
    if outside:
        rep.add(source, "note", label, note=f"{outside} saved record(s) lie outside the live request ({outside_note}); not compared")
    if not_received:
        rep.add(source, "not-in-received-pages", label, note=f"{not_received} saved record(s) after {after_live}, the last record of the pages received; later pages were not requested")
    s_fields = set().union(*[set(r) for r in sm.values()]) if sm else set()
    l_fields = set().union(*[set(r) for r in lm.values()]) if lm else set()
    for f in sorted(l_fields - s_fields):
        rep.add(source, "field-set", label, f, None, "present", note="a field no saved record has appears in the live response")
    for f in sorted(s_fields - l_fields):
        rep.add(source, "field-set", label, f, "present", None, note="a field of the saved records appears in no live record")
    l_max = max(l_keys, key=str) if l_keys else None
    return {"saved_records": len(sm), "live_records": len(lm), "in_both": len(both), "changed_records": n_changed_rec, "changed_fields": n_changed_fields,
            "fields_appearing": n_appear, "fields_disappearing": n_disappear, "new_after_saved": len(new), "earlier_than_saved": len(earlier),
            "inserted": len(inserted), "missing_from_live": len(missing), "saved_outside_request": outside, "saved_not_in_received_pages": not_received,
            "saved_latest": s_max, "live_latest": l_max, "saved_earliest": s_min, "live_earliest": min(l_keys, key=str) if l_keys else None,
            "saved_fields": sorted(s_fields), "live_fields": sorted(l_fields)}


def read_registry(path):
    reg = load_json(Path(path).read_bytes())
    series = {s["id"]: s for s in reg.get("series", [])}
    routes = {}
    for s in reg.get("series", []):
        ep = s["fetch"]["endpoint"]
        u = urlsplit(ep)
        routes.setdefault((u.hostname, u.path), (s["source"], {"json": "effr" if s["source"] == "nyfed-markets" else "dtp", "sdmx-zip": "h6-zip"}[s["fetch"]["format"]]))
    for cid, cal in reg.get("calendars", {}).items():
        if cid == "frb-h6-release-dates" and isinstance(cal.get("url"), str):
            u = urlsplit(cal["url"])
            routes[(u.hostname, u.path)] = ("frb-releases", "h6-dates")
    hosts = {src["host"]: sid for sid, src in reg.get("sources", {}).items()}
    h6_names = []
    for s in reg.get("series", []):
        for e in s.get("extract", []):
            if e.get("series_name") and e["series_name"] not in h6_names:
                h6_names.append(e["series_name"])
    return reg, routes, hosts, h6_names


def record_problems(rec, n, host):
    """20.2 (v0.7, F1): a response record has exactly the twelve fields, each present; n, status
    and bytes are integers, the five header fields text or null, the others text; n and host are
    those of its file name. Any problem makes the record invalid, so its response is refused."""
    out = []
    missing = [f for f in RECORD_FIELDS if f not in rec]
    extra = sorted(set(rec) - set(RECORD_FIELDS))
    if missing:
        out.append(f"fields missing {missing}")
    if extra:
        out.append(f"fields not in 20.2 {extra}")
    for f in RECORD_INT_FIELDS:
        if f in rec and not (isinstance(rec[f], Num) and RX_JSON_INTEGER.fullmatch(str(rec[f]))):
            out.append(f"{f} {jtext(rec[f])} is not an integer")
    for f in ("host", "url", "requested_at", "sha256"):
        if f in rec and (not isinstance(rec[f], str) or isinstance(rec[f], Num)):
            out.append(f"{f} {jtext(rec[f])} is not text")
    for f in RECORD_HEADER_FIELDS:
        if f in rec and rec[f] is not None and (not isinstance(rec[f], str) or isinstance(rec[f], Num)):
            out.append(f"{f} {jtext(rec[f])} is neither text nor null")
    if isinstance(rec.get("n"), Num) and RX_JSON_INTEGER.fullmatch(str(rec["n"])) and int(rec["n"]) != n:
        out.append(f"n {rec['n']} is not the file name's {n}")
    if "host" in rec and rec.get("host") != host:
        out.append(f"host {jtext(rec.get('host'))} is not the file name's {host!r}")
    if isinstance(rec.get("requested_at"), str) and not isinstance(rec["requested_at"], Num) and not RX_UTC_TIME.fullmatch(rec["requested_at"]):
        out.append(f"requested_at {jtext(rec['requested_at'])} is not a UTC time")
    return out


def read_collection(rep, coll, hosts, routes):
    """20.2: responses/<n>-<host>.bin with responses/<n>-<host>.json. Integrity first."""
    rdir = Path(coll) / "responses"
    out = []
    if not rdir.is_dir():
        rep.add("collection", "integrity", str(rdir), note="no responses/ folder")
        rep.refused = True
        return out
    files = sorted(p.name for p in rdir.iterdir() if p.is_file())
    pairs = {}
    for name in files:
        mt = RX_RESPONSE_FILE.fullmatch(name)
        if not mt:
            rep.add("collection", "format", name, note="not <n>-<host>.bin or <n>-<host>.json (20.2); ignored")
            continue
        pairs.setdefault((int(mt.group(1)), mt.group(2)), {})[mt.group(3)] = rdir / name
    for (n, host), fs in sorted(pairs.items()):
        where = f"{n}-{host}"
        entry = {"n": n, "host": host, "integrity": None, "url": None, "status": None, "route": None, "source": None}
        out.append(entry)
        rep.responses.append(entry)
        if "bin" not in fs or "json" not in fs:
            entry["integrity"] = "incomplete"
            rep.add("collection", "integrity", where, note=f"only the .{next(iter(fs))} file is present (20.2 saves both)")
            rep.refused = True
            continue
        try:
            rec = load_json(fs["json"].read_bytes())
            if not isinstance(rec, dict):
                raise JsonRefused("not an object")
        except (JsonRefused, ValueError, UnicodeDecodeError) as exc:
            entry["integrity"] = "record unreadable"
            rep.add("collection", "integrity", where, note=f"{where}.json is not readable JSON ({exc}); the response is refused")
            rep.refused = True
            continue
        bad = record_problems(rec, n, host)
        if bad:
            entry["integrity"] = "record invalid"
            rep.add("collection", "integrity", where, "record", note="; ".join(bad) + " (20.2 v0.7: such a record is invalid); the response is refused, not compared")
            rep.refused = True
            continue
        data = fs["bin"].read_bytes()
        want_sha, want_bytes = rec.get("sha256"), rec.get("bytes")
        ok_sha = isinstance(want_sha, str) and RX_SHA256.fullmatch(want_sha) and sha256_hex(data) == want_sha
        ok_len = isinstance(want_bytes, Num) and want_bytes.isdigit() and int(want_bytes) == len(data)
        if not ok_sha or not ok_len:
            entry["integrity"] = "mismatch"
            rep.add("collection", "integrity", where, "sha256" if not ok_sha else "bytes", jtext(want_sha) if not ok_sha else jtext(want_bytes),
                    sha256_hex(data) if not ok_sha else str(len(data)), note="the saved response does not match its recorded hash or byte count (20.2); refused, not compared")
            rep.refused = True
            continue
        entry["integrity"] = "ok"
        url = rec.get("url") if isinstance(rec.get("url"), str) else ""
        u = urlsplit(url)
        entry.update(url=url, status=jtext(rec.get("status")), bytes=len(data), sha256=want_sha, requested_at=rec.get("requested_at"),
                     content_type=rec.get("content_type"), date=rec.get("date"), last_modified=rec.get("last_modified"), etag=rec.get("etag"))
        if u.scheme != "https":
            rep.add("collection", "request", where, "url", None, url, note="not https (18, 20.2)")
        if u.hostname != host:
            rep.add("collection", "request", where, "host", host, u.hostname, note="the file name's host is not the URL's host")
        src = hosts.get(u.hostname)
        route = routes.get((u.hostname, u.path))
        entry["source"], entry["route"] = (route[0] if route else src), (route[1] if route else None)
        if src is None:
            rep.add("collection", "request", where, "host", None, u.hostname, note="not a registered source host (18: only the registered host); not compared")
            continue
        if route is None:
            rep.add(src, "request", where, "route", None, u.path, note="not a registered endpoint or calendar route; not compared")
            continue
        entry["query"] = parse_qsl(u.query, keep_blank_values=True)
        entry["data"] = data
        rep.sources[route[0]]["requests"].append({k: entry.get(k) for k in ("n", "host", "url", "status", "bytes", "sha256", "route", "requested_at", "content_type", "date", "last_modified", "etag")})
        if len(data) > MAX_RESPONSE_BYTES:
            rep.add(route[0], "format", where, note=f"{len(data)} bytes, over the 64,000,000 of 20.2")
    return out


def body_bytes(rep, source, where, data):
    """The response body as JSON-ready bytes: a gzip body (never requested) is inflated with a
    finding, a UTF-8 byte order mark is reported and dropped."""
    if data[:2] == b"\x1f\x8b":
        rep.add(source, "format", where, note="the body is gzip-compressed although no Accept-Encoding was sent (20.2); inflated to compare")
        data = gunzip_bounded(data)
    if data[:3] == b"\xef\xbb\xbf":
        rep.add(source, "format", where, note="the body starts with a UTF-8 byte order mark; dropped to compare")
        data = data[3:]
    return data


def status_ok(rep, source, e):
    if e["status"] != "200":
        kind = "a redirect, never followed (20.2)" if e["status"][:1] == "3" else "not 200"
        rep.add(source, "request", f"{e['n']}-{e['host']}", "status", None, e["status"], note=f"{kind}; the response is not compared")
        return False
    return True


def compare_effr(rep, live_entries, fixtures):
    src = "nyfed-markets"
    saved_doc = load_json(gunzip_bounded((fixtures / "nyfed-effr-full.json.gz").read_bytes()))
    saved = saved_doc.get("refRates") if isinstance(saved_doc, dict) else None
    live, start, end, top_keys = [], None, None, set()
    for e in live_entries:
        where = f"{e['n']}-{e['host']}"
        if not status_ok(rep, src, e):
            continue
        q = dict(e.get("query") or [])
        start, end = q.get("startDate"), q.get("endDate")
        try:
            doc = load_json(body_bytes(rep, src, where, e["data"]))
        except (JsonRefused, ValueError, UnicodeDecodeError) as exc:
            rep.add(src, "format", where, note=f"not readable JSON ({exc}); not compared")
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("refRates"), list):
            rep.add(src, "format", where, note="the body is not an object with a refRates list; not compared")
            continue
        top_keys |= set(doc)
        live += [r for r in doc["refRates"] if isinstance(r, dict)]
        if len(live) != len(doc["refRates"]):
            rep.add(src, "format", where, note="a refRates entry is not an object")
    if not live and not any(e["status"] == "200" for e in live_entries):
        return None
    for k in sorted(top_keys - set(saved_doc)):
        rep.add(src, "field-set", "response", k, None, "present", note="a top-level member the saved response lacks")
    for k in sorted(set(saved_doc) - top_keys) if top_keys else []:
        rep.add(src, "field-set", "response", k, "present", None, note="a top-level member of the saved response the live one lacks")
    types = sorted({jtext(r.get("type")) for r in live})
    if types and types != ['"EFFR"']:
        rep.add(src, "note", "type", "type", '"EFFR"', ", ".join(types), note="record types other than EFFR in the live response")

    def in_request(k):
        return (start is None or str(k) >= start) and (end is None or str(k) <= end)
    summ = compare_records(rep, src, "EFFR", saved, live, lambda r: r.get("effectiveDate"), in_request, f"startDate {start}, endDate {end}")
    summ["request_range"] = [start, end]
    summ["order"] = record_order([r.get("effectiveDate") for r in live])
    return summ


def record_order(keys):
    ks = [str(k) for k in keys]
    if ks == sorted(ks):
        return "ascending"
    if ks == sorted(ks, reverse=True):
        return "descending"
    return "mixed"


def compare_dtp(rep, live_entries, fixtures):
    src = "fiscaldata"
    saved_doc = load_json(gunzip_bounded((fixtures / "fiscaldata-dtp-full.json.gz").read_bytes()))
    saved = saved_doc.get("data") if isinstance(saved_doc, dict) else None
    pages, start, totals = [], None, set()
    for e in live_entries:
        where = f"{e['n']}-{e['host']}"
        if not status_ok(rep, src, e):
            continue
        q = dict(e.get("query") or [])
        flt = q.get("filter") or ""
        mt = re.fullmatch(r"record_date:gte:(\d{4}-\d{2}-\d{2})", flt)
        start = mt.group(1) if mt else start
        if flt and not mt:
            rep.add(src, "request", where, "filter", None, flt, note="not record_date:gte:<date> (18)")
        try:
            page_no = int(q.get("page[number]", "1"))
        except ValueError:
            page_no = None
        try:
            doc = load_json(body_bytes(rep, src, where, e["data"]))
        except (JsonRefused, ValueError, UnicodeDecodeError) as exc:
            rep.add(src, "format", where, note=f"not readable JSON ({exc}); not compared")
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("data"), list) or not isinstance(doc.get("meta"), dict):
            rep.add(src, "format", where, note="the body is not an object with a data list and a meta object; not compared")
            continue
        pages.append((page_no, where, doc))
        totals.add(jtext(doc["meta"].get("total-count")))
    if not pages:
        return None
    pages.sort(key=lambda x: (x[0] is None, x[0] or 0))
    live = [r for _, _, d in pages for r in d["data"] if isinstance(r, dict)]
    if len(totals) > 1:
        rep.add(src, "format", "meta", "total-count", None, ", ".join(sorted(totals)), note="the pages give different total-count values")
    total = next(iter(totals)) if len(totals) == 1 else None
    after_live = None
    if total is not None and total.isdigit() and int(total) > len(live):
        after_live = max((r.get("record_date") for r in live), default=None, key=str)
        rep.add(src, "note", "meta", "total-count", None, total, note=f"{len(live)} rows received in {len(pages)} page(s), total-count {total}: later pages were not requested")
    elif total is not None and total.isdigit() and int(total) < len(live):
        rep.add(src, "format", "meta", "total-count", None, total, note=f"{len(live)} rows received, more than total-count (5: must be equal)")
    # meta: labels, dataTypes and dataFormats describe the fields; their changes are schema signals
    sm, lm = saved_doc.get("meta") or {}, pages[0][2]["meta"]
    for part in sorted(set(sm) | set(lm)):
        a, b = sm.get(part), lm.get(part)
        if part in ("count", "total-count", "total-pages"):
            if jtext(a) != jtext(b):
                rep.add(src, "header", "meta", part, jtext(a), jtext(b), note="page and count members (informative)")
            continue
        if isinstance(a, dict) and isinstance(b, dict):
            for f in sorted(set(a) | set(b)):
                if jtext(a.get(f)) != jtext(b.get(f)):
                    rep.add(src, "header", f"meta.{part}", f, jtext(a[f]) if f in a else None, jtext(b[f]) if f in b else None, note="a field's label, type or format")
        elif jtext(a) != jtext(b):
            rep.add(src, "header", "meta", part, jtext(a) if a is not None else None, jtext(b) if b is not None else None)
    for k in sorted(set(pages[0][2]) - set(saved_doc)):
        rep.add(src, "field-set", "response", k, None, "present", note="a top-level member the saved response lacks")
    for k in sorted(set(saved_doc) - set(pages[0][2])):
        rep.add(src, "field-set", "response", k, "present", None, note="a top-level member of the saved response the live one lacks")

    def in_request(k):
        return start is None or str(k) >= start
    summ = compare_records(rep, src, "DTP", saved, live, lambda r: jtext(r.get("record_date")).strip('"'), in_request, f"record_date from {start}", after_live)
    summ["request_start"] = start
    summ["pages"] = [p for p, _, _ in pages]
    summ["total_count"] = total
    summ["order"] = record_order([r.get("record_date") for r in live])
    return summ


def h6_side(xml_bytes, names):
    doc = parse_h6_xml(xml_bytes)
    by = {}
    for s in doc["series"]:
        by.setdefault(s["attrs"].get("SERIES_NAME"), []).append(s)
    return doc["header"], by


def compare_h6(rep, zip_entries, date_entries, fixtures, h6_names):
    src = "frb-releases"
    out = {}
    saved_xml, saved_members = read_zip_member((fixtures / "frb-h6-reduced.zip").read_bytes(), "H6_data.xml")
    saved_header, saved_by = h6_side(saved_xml, h6_names)
    live_header, live_by, live_members = None, None, None
    for e in zip_entries:
        where = f"{e['n']}-{e['host']}"
        if not status_ok(rep, src, e):
            continue
        try:
            xml_bytes, live_members = read_zip_member(e["data"], "H6_data.xml")
            live_header, live_by = h6_side(xml_bytes, h6_names)
        except (ValueError, ET.ParseError) as exc:
            rep.add(src, "format", where, note=f"the H.6 zip or XML is refused ({exc}); not compared")
            rep.refused = True
            live_by = None
    if live_by is not None:
        for f in sorted(set(saved_header) | set(live_header)):
            a, b = saved_header.get(f), live_header.get(f)
            if jtext(a) != jtext(b):
                rep.add(src, "header", "H6_data.xml", f, jtext(a) if a is not None else None, jtext(b) if b is not None else None,
                        note="Prepared is recorded only, not a release signal (2.4)" if f == "Prepared" else None)
        for side, by in (("saved", saved_by), ("live", live_by)):
            for name in sorted(n for n in by if n in h6_names):
                copies = by[name]
                for i, c in enumerate(copies[1:], start=2):
                    if c["attrs"] != copies[0]["attrs"] or c["obs"] != copies[0]["obs"]:
                        rep.add(src, "copies-differ", f"{name} copy {i}", note=f"the {side} file's copies of {name} differ in attributes or observations ({copies[0]['dataset']} and {c['dataset']}; 5: copies must be identical, the namespace ignored)")
        series_summ = {}
        # reading: 5 binds only the registered series, and the saved file keeps two unregistered
        # ones cut to eight observations by construction (18); they are counted, not compared.
        unreg_saved = sorted(n for n in saved_by if n is not None and n not in h6_names)
        unreg_live = sorted(n for n in live_by if n is not None and n not in h6_names)
        rep.sources[src]["notes"].append(f"unregistered series names: saved file {len(unreg_saved)} ({', '.join(unreg_saved)}), live file {len(unreg_live)}; not compared (5 binds only the registered series)")
        for name in h6_names:
            label = name
            s_copies, l_copies = saved_by.get(name) or [], live_by.get(name) or []
            if not l_copies:
                rep.add(src, "missing-record", label, note="the series is in the saved file and not in the live one")
                continue
            if not s_copies:
                rep.add(src, "new-record", label, note="a registered series the saved file lacks")
                continue
            sa, la = s_copies[0]["attrs"], l_copies[0]["attrs"]
            for f in sorted(set(sa) | set(la)):
                if sa.get(f) != la.get(f):
                    kind = "changed-field" if f in sa and f in la else ("field-appears" if f in la else "field-disappears")
                    rep.add(src, kind, f"{label} series", f, json.dumps(sa[f]) if f in sa else None, json.dumps(la[f]) if f in la else None)
            if len(s_copies) != len(l_copies):
                rep.add(src, "note", label, "copies", str(len(s_copies)), str(len(l_copies)), note="number of copies in the file")

            def as_records(obs):
                return [dict(o) for o in obs]
            summ = compare_records(rep, src, label, as_records(s_copies[0]["obs"]), as_records(l_copies[0]["obs"]), lambda o: o.get("TIME_PERIOD"))
            series_summ[name] = summ
        out["series"] = series_summ
        out["prepared"] = {"saved": saved_header.get("Prepared"), "live": live_header.get("Prepared")}
        out["unregistered_series"] = {"saved": unreg_saved, "live_count": len(unreg_live)}
        out["zip_members"] = {"saved": saved_members, "live": live_members}
    # releaseDates.json (2.4: the release marker)
    saved_dates, saved_keys = flatten_release_dates(load_json((fixtures / "frb-h6-releaseDates.json").read_bytes()))
    for e in date_entries:
        where = f"{e['n']}-{e['host']}"
        if not status_ok(rep, src, e):
            continue
        try:
            live_dates, live_keys = flatten_release_dates(load_json(body_bytes(rep, src, where, e["data"])))
        except (JsonRefused, ValueError, UnicodeDecodeError) as exc:
            rep.add(src, "format", where, note=f"releaseDates.json is not readable ({exc}); not compared")
            continue
        for level in ("year", "month"):
            for k in sorted(live_keys[level] - saved_keys[level]):
                rep.add(src, "field-set", f"releaseDates {level} entries", k, None, "present")
            for k in sorted(saved_keys[level] - live_keys[level]):
                rep.add(src, "field-set", f"releaseDates {level} entries", k, "present", None)
        recs_s = [{"date": d, "marker": mk} for d, mk, _, _ in saved_dates]
        recs_l = [{"date": d, "marker": mk} for d, mk, _, _ in live_dates]
        summ = compare_records(rep, src, "release date", recs_s, recs_l, lambda r: r["date"])
        out["release_dates"] = summ
        s_latest, l_latest = summ["saved_latest"], summ["live_latest"]
        rep.add(src, "release-dates", "latest release date", None, s_latest, l_latest,
                note="the newest date in releaseDates.json (2.4: latest_release_date)" + ("" if s_latest == l_latest else "; a later release date than the saved one" if str(l_latest) > str(s_latest) else "; the live file's newest date is older"))
    return out


def run(collection, out_path, repo_root, emit=print):
    repo_root = Path(repo_root)
    fixtures = repo_root / "pipeline" / "fixtures" / "raw"
    coll = Path(collection).resolve()
    rep = Report()
    if out_path is not None:
        op = Path(out_path).resolve()
        if op == coll or coll in op.parents:
            emit(f"compare-saved: refused: --compare-out {op} lies inside the collection folder {coll}, which this mode never edits")
            return 2
    reg, routes, hosts, h6_names = read_registry(repo_root / "pipeline" / "registry" / "econ.json")
    entries = read_collection(rep, coll, hosts, routes)
    by_route = {}
    for e in entries:
        if e.get("route") and e.get("integrity") == "ok" and "data" in e:
            by_route.setdefault(e["route"], []).append(e)
    summaries = {}
    for src, route, fn in (("nyfed-markets", "effr", compare_effr), ("fiscaldata", "dtp", compare_dtp)):
        es = by_route.get(route, [])
        if not es:
            rep.add(src, "request", None, note="no response of this source in the collection")
            continue
        try:
            summaries[src] = fn(rep, es, fixtures)
        except (JsonRefused, ValueError, UnicodeDecodeError, OSError) as exc:
            rep.add(src, "format", None, note=f"cannot compare ({type(exc).__name__}: {exc})")
            rep.refused = True
    zips, dates = by_route.get("h6-zip", []), by_route.get("h6-dates", [])
    if not zips and not dates:
        rep.add("frb-releases", "request", None, note="no response of this source in the collection")
    else:
        if not zips:
            rep.add("frb-releases", "request", "H.6 zip", note="no response for the H.6 zip")
        if not dates:
            rep.add("frb-releases", "request", "releaseDates.json", note="no response for releaseDates.json")
        try:
            summaries["frb-releases"] = compare_h6(rep, zips, dates, fixtures, h6_names)
        except (JsonRefused, ValueError, UnicodeDecodeError, OSError, ET.ParseError) as exc:
            rep.add("frb-releases", "format", None, note=f"cannot compare ({type(exc).__name__}: {exc})")
            rep.refused = True
    # one line per finding, then a summary per source
    rank = {k: i for i, k in enumerate(KIND_ORDER)}
    srank = {s: i for i, s in enumerate(("collection",) + SOURCE_ORDER)}
    rep.findings.sort(key=lambda f: (srank.get(f["source"], 9), rank.get(f["kind"], 99), str(f.get("key")), str(f.get("field"))))
    emit(f"compare-saved: collection {coll}; saved histories {fixtures}")
    for e in entries:
        emit(f"RESPONSE {e['n']}-{e['host']}: {e.get('url') or '?'} status {e.get('status')}, {e.get('bytes')} bytes, integrity {e.get('integrity')}, route {e.get('route')}")
    for f in rep.findings:
        line = f"FINDING {f['source']} {f['kind']}"
        if f.get("key") is not None:
            line += f" {f['key']}"
        if f.get("field") is not None:
            line += f" {f['field']}"
        if f.get("saved") is not None or f.get("live") is not None:
            line += f": saved {f['saved'] if f['saved'] is not None else '(absent)'}, live {f['live'] if f['live'] is not None else '(absent)'}"
            if f.get("same_decimal_value"):
                line += " (the same decimal value, written differently)"
        if f.get("note"):
            line += f" ({f['note']})"
        emit(line)
    for src in SOURCE_ORDER:
        s = summaries.get(src)
        reqs = rep.sources[src]["requests"]
        req_text = ", ".join(f"{r['n']} {r['route']} status {r['status']}" for r in reqs) or "none"
        kinds = {}
        for f in rep.findings:
            if f["source"] == src:
                kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
        if s is None:
            emit(f"SUMMARY {src}: requests [{req_text}]; nothing compared; findings {kinds}")
            continue
        if src == "frb-releases":
            parts = []
            for name, ss in (s.get("series") or {}).items():
                parts.append(f"{name}: saved {ss['saved_records']} live {ss['live_records']} both {ss['in_both']} changed {ss['changed_records']} new {ss['new_after_saved']} missing {ss['missing_from_live']} latest {ss['saved_latest']}/{ss['live_latest']}")
            rd = s.get("release_dates") or {}
            emit(f"SUMMARY {src}: requests [{req_text}]; Prepared {((s.get('prepared') or {}).get('saved'))}/{((s.get('prepared') or {}).get('live'))}; "
                 + "; ".join(parts) + (f"; release dates saved {rd.get('saved_records')} live {rd.get('live_records')} new {rd.get('new_after_saved')} missing {rd.get('missing_from_live')} changed {rd.get('changed_records')} latest {rd.get('saved_latest')}/{rd.get('live_latest')}" if rd else "")
                 + f"; findings {kinds}")
        else:
            live_dates = "; ".join(f"HTTP Date {r.get('date')!s}, Last-Modified {r.get('last_modified')!s}" for r in reqs[:1])
            emit(f"SUMMARY {src}: requests [{req_text}]; saved {s['saved_records']} records (latest {s['saved_latest']}), live {s['live_records']} (latest {s['live_latest']}, {s.get('order')}); "
                 f"in both {s['in_both']}, changed {s['changed_records']} records ({s['changed_fields']} fields, {s['fields_appearing']} appearing, {s['fields_disappearing']} disappearing); "
                 f"new after the saved data {s['new_after_saved']}, inserted {s['inserted']}, earlier {s['earlier_than_saved']}, missing from live {s['missing_from_live']}, "
                 f"saved outside the request {s['saved_outside_request']}, not in the received pages {s['saved_not_in_received_pages']}; {live_dates}; findings {kinds}")
    for src in SOURCE_ORDER:
        for note in rep.sources[src]["notes"]:
            emit(f"NOTE {src}: {note}")
    emit(f"COMPARE {len(rep.findings)} finding(s); {'a response was refused or unreadable' if rep.refused else 'every response verified and read'}; nothing preferred, nothing edited")
    if out_path is not None:
        result = {"mode": "compare-saved", "conventions": "v0.6 section 20.4", "collection": str(coll), "saved_histories": str(fixtures),
                  "responses": [{k: v for k, v in e.items() if k not in ("data",)} for e in entries],
                  "sources": {src: {"requests": rep.sources[src]["requests"], "summary": summaries.get(src), "notes": rep.sources[src]["notes"]} for src in SOURCE_ORDER},
                  "findings": rep.findings, "refused": rep.refused,
                  "written_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        Path(out_path).write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n")
        emit(f"compare-saved: wrote {Path(out_path).resolve()}")
    return 1 if rep.refused else 0
