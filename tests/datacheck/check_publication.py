"""Publication, release and appendix J modes of the independent checker (DATA_CONVENTIONS v0.8).

    python -I tests/datacheck/check_p22.py --publication <econ dir or artifact.tar.gz> --state <store dir> [--previous-release <release dir>]
    python -I tests/datacheck/check_p22.py --release <release dir> [--expect <snapshot>:<sha256>] [--previous-release <release dir>]
    python -I tests/datacheck/check_p22.py --release-history <folder of release folders>
    python -I tests/datacheck/check_p22.py --publication-scenario <dir>

Loaded by check_p22.py by its path and given the checker module (`ck`). Written from the text of
sections 13, 17.6 to 17.8, 21.6 and 22 and appendix J only; it shares no code with the pipeline.
Every artifact, release and store is untrusted data: parsed, never executed, never extracted to
disk (a tar archive is read in memory). Nothing is written.

Checks:
  P0 to P11   the publication mode: V2c checks 1 to 11 of 22.5 (P1 to P11) and the archive format
              of 22.3 (P0), on the artifact, the store at C and the newest earlier release
  RL1 to RL5  the release mode: the four assets of 22.4 and the data build steps of 22.8, then
              checks 3, 4 and 9 on the extracted tree
  RH1         the release history the watcher checks from public data (22.7)
  J0 to J6    appendix J: steps.json, the releases, the production record and the store
  C10 to C18  self-tests of the v0.8 rules (run with the plain checks): the compare-and-swap and
              monotonic decision of 22.8, D5.5, the archive format, I7, the reason check, the
              revision CSV and notice file formats, the deployment log, its chain and the release
              history, the deployed state and the pages run name

"reading:" in a comment marks a point the text does not state outright; the report lists them.
"""

import gzip
import io
import json
import re
import struct
import zlib
from pathlib import Path

ALLOW_FILES = ("manifest.json", "status/runs.json", "status/publications.json", "status/deployments.json", "NOTICE.txt")  # 22.3
ALLOW_DIRS = ("objects/", "series/", "snapshots/", "revisions/", "registry/", "notices/")  # 22.3
DEPLOY_LOG = "status/deployments.json"
ASSETS = ("artifact.tar.gz", "manifest.json", "deployments.json", "SHA256SUMS")  # 22.4
RX_TAG_SITE = re.compile(r"data-\d{8}T\d{6}Z-\d+-\d+", re.ASCII)  # 22.8 input pattern
RX_EXPECTED = re.compile(r"none|(\d{8}T\d{6}Z):([0-9a-f]{64})", re.ASCII)  # 22.8
LIMIT_PUBLISHED = 250_000_000  # 17.7
ZERO_COMMIT = "0" * 40  # appendix J
# 22.2 amendment 1 (owner authorization P107, appendix I row I49): the one manifest/3 dataset that passes
# the rule-file part of 22.5 check 8 without rule files, identified by both values together
COMPAT_SNAPSHOT = "20261121T001752Z"
COMPAT_MANIFEST_SHA256 = "180a1991a56582e8a03813efa556d2695b3f28f7e415b763b06e499e57c1188d"
COMPAT_SCHEMA = "rmf.econ.manifest/3"  # 22.2: its manifest stays rmf.econ.manifest/3


# ---------------------------------------------------------------------------
# The artifact (22.3): its tree, its SHA-256 and its deterministic archive
# ---------------------------------------------------------------------------


def artifact_sha(files):
    """22.3: the SHA-256 of the lines '<sha256>  <path>' (two spaces, LF-terminated, in path order)
    over every file except status/deployments.json; also the file count and bytes (22.4 artifact).
    reading: paths are relative to econ/ and 'path order' is the byte order of their UTF-8 form."""
    import hashlib
    paths = sorted((p for p in files if p != DEPLOY_LOG), key=lambda x: x.encode("utf-8"))
    text = "".join(f"{hashlib.sha256(files[p]).hexdigest()}  {p}\n" for p in paths)
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), len(paths), sum(len(files[p]) for p in paths)


def _octal(value, width):
    return (b"%0*o" % (width - 1, value)) + b"\0"


def build_tar(files, prefix="econ/"):
    """The checker's own deterministic writer (self-tests only): POSIX ustar, entries in byte order
    of their paths, regular files only, mode 0644, uid and gid 0 with empty names, mtime 0."""
    out = io.BytesIO()
    for path in sorted(files, key=lambda x: x.encode("utf-8")):
        name = (prefix + path).encode("utf-8")
        pre = b""
        if len(name) > 100:
            cut = name.rfind(b"/", 0, 156)
            pre, name = name[:cut], name[cut + 1:]
        data = files[path]
        h = bytearray(512)
        h[0:len(name)] = name
        h[100:108] = _octal(0o644, 8)
        h[108:116] = _octal(0, 8)
        h[116:124] = _octal(0, 8)
        h[124:136] = _octal(len(data), 12)
        h[136:148] = _octal(0, 12)
        h[148:156] = b" " * 8
        h[156:157] = b"0"
        h[257:263] = b"ustar\0"
        h[263:265] = b"00"
        h[329:337] = _octal(0, 8)
        h[337:345] = _octal(0, 8)
        h[345:345 + len(pre)] = pre
        h[148:156] = b"%06o\0 " % sum(h)
        out.write(bytes(h))
        out.write(data)
        out.write(b"\0" * (-len(data) % 512))
    out.write(b"\0" * 1024)
    return out.getvalue()


def build_targz(files, prefix="econ/"):
    """gzip level 9, no file name, modification time 0 and OS byte 255 (22.3)."""
    raw = build_tar(files, prefix)
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = co.compress(raw) + co.flush()
    head = b"\x1f\x8b\x08\x00" + struct.pack("<I", 0) + b"\x02\xff"
    return head + body + struct.pack("<II", zlib.crc32(raw) & 0xFFFFFFFF, len(raw) & 0xFFFFFFFF)


def _num(field):
    """A ustar numeric field: octal digits, ended by NUL or space (POSIX); None when malformed."""
    t = field.rstrip(b"\0 ").lstrip(b" ")
    if t == b"":
        return 0
    if not re.fullmatch(rb"[0-7]+", t):
        return None
    return int(t, 8)


def safe_rel(path):
    """22.8: refuse any path outside the target folder: absolute, a drive, a backslash, an empty, '.' or '..' part."""
    return (isinstance(path, str) and path != "" and not path.startswith("/") and "\\" not in path and ":" not in path
            and "\0" not in path and all(part not in ("", ".", "..") for part in path.split("/")))


def parse_targz(data):
    """Read artifact.tar.gz in memory against 22.3 and the extraction rules of 22.8.
    Returns (files {path relative to econ/: bytes} or None, problems, info)."""
    p, info = [], {}
    if len(data) < 18 or data[:3] != b"\x1f\x8b\x08":
        return None, ["not a gzip file with the deflate method"], info
    flg, mtime, xfl, osb = data[3], struct.unpack("<I", data[4:8])[0], data[8], data[9]
    info["os"] = osb
    if osb != 255:
        p.append(f"the gzip OS byte is {osb} (22.3: 255)")
    if flg & 0x08:
        p.append("the gzip header carries a file name (22.3: no file name)")
    if flg & ~0x08 & 0xFF:
        p.append(f"gzip flags {flg:#04x}: extra field, comment or header CRC present (reading: the header is the bare 10 bytes)")
    if mtime != 0:
        p.append(f"the gzip modification time is {mtime} (22.3: 0)")
    if xfl != 2:
        p.append(f"the gzip XFL byte is {xfl} (reading: level 9 writes 2, maximum compression)")
    d = zlib.decompressobj(-15)
    pos = 10
    if flg & 0x04:
        pos += 2 + struct.unpack("<H", data[10:12])[0]
    for bit in (0x08, 0x10):
        if flg & bit:
            end = data.find(b"\0", pos)
            pos = end + 1 if end >= 0 else len(data)
    if flg & 0x02:
        pos += 2
    try:
        raw = d.decompress(data[pos:]) + d.flush()
    except zlib.error as exc:
        return None, p + [f"the deflate stream is damaged: {exc}"], info
    tail = d.unused_data
    if len(tail) < 8:
        return None, p + ["the gzip trailer is missing"], info
    crc, isize = struct.unpack("<II", tail[:8])
    if crc != zlib.crc32(raw) & 0xFFFFFFFF or isize != len(raw) & 0xFFFFFFFF:
        p.append("the gzip CRC-32 or size does not match the data")
    if tail[8:]:
        p.append(f"{len(tail) - 8} byte(s) after the gzip member (a second member or trailing data)")
    files, order = {}, []
    off, ended = 0, False
    while off + 512 <= len(raw):
        h = raw[off:off + 512]
        if h == b"\0" * 512:
            ended = True
            rest = raw[off:]
            if rest.strip(b"\0"):
                p.append("data after the end-of-archive blocks")
            break
        name = h[0:100].split(b"\0", 1)[0]
        pre = h[345:500].split(b"\0", 1)[0]
        full = (pre + b"/" + name) if pre else name
        try:
            path = full.decode("utf-8")
        except UnicodeDecodeError:
            p.append(f"an entry name is not UTF-8: {full!r}")
            path = full.decode("utf-8", "replace")
        size, mode, uid, gid, mt = _num(h[124:136]), _num(h[100:108]), _num(h[108:116]), _num(h[116:124]), _num(h[136:148])
        chk = _num(h[148:156])
        typ = h[156:157]
        want_chk = sum(h[:148]) + 8 * 32 + sum(h[156:])
        where = f"entry {path!r}"
        if chk != want_chk:
            p.append(f"{where}: header checksum {chk} is not {want_chk}")
        if h[257:263] != b"ustar\0" or h[263:265] != b"00":
            p.append(f"{where}: magic {h[257:265]!r} is not POSIX ustar ('ustar' NUL '00') (22.3)")
        if typ not in (b"0", b"\0"):
            p.append(f"{where}: type {typ!r} is not a regular file (22.3: regular files only; 22.8: refuse any link and any non-regular file)")
        if mode is None or mode & 0o7777 != 0o644:
            p.append(f"{where}: mode {mode if mode is None else oct(mode)} (22.3: 0644)")
        if uid != 0 or gid != 0:
            p.append(f"{where}: owner {uid} and group {gid} (22.3: 0)")
        if h[265:297].strip(b"\0") or h[297:329].strip(b"\0"):
            p.append(f"{where}: owner or group name {h[265:297].strip(chr(0).encode())!r} {h[297:329].strip(chr(0).encode())!r} (22.3: empty)")
        if mt != 0:
            p.append(f"{where}: modification time {mt} (22.3: 0)")
        if h[157:257].strip(b"\0"):
            p.append(f"{where}: a link name is set (22.8: refuse any link)")
        if size is None:
            p.append(f"{where}: malformed size")
            break
        rel = path[5:] if path.startswith("econ/") else path
        if not path.startswith("econ/"):
            p.append(f"{where}: the name is not econ/<path> (22.3; 22.8: any name outside econ/ is refused)")
        if not safe_rel(path) or not safe_rel(rel):
            p.append(f"{where}: a path outside the target folder (22.8: refused)")
        data_ = raw[off + 512: off + 512 + size]
        if len(data_) != size:
            p.append(f"{where}: truncated")
            break
        if typ in (b"0", b"\0"):
            if rel in files:
                p.append(f"{where}: the path appears twice")
            files[rel] = data_
            order.append(path)
        off += 512 + size + (-size % 512)
    if not ended:
        p.append("no end-of-archive blocks (two 512-byte zero blocks)")
    if order != sorted(order, key=lambda x: x.encode("utf-8")):
        p.append("entries are not in byte order of their paths (22.3)")
    info["entries"] = len(order)
    return files, p, info


def read_tree(path):
    """A folder holding the artifact tree: econ/ itself, or a folder with econ/ inside."""
    base = Path(path)
    if (base / "econ").is_dir() and not (base / "manifest.json").is_file():
        base = base / "econ"
    files, links = {}, []
    for x in sorted(base.rglob("*")):
        rel = x.relative_to(base).as_posix()
        if x.is_symlink():
            links.append(rel)
        elif x.is_file():
            files[rel] = x.read_bytes()
    return files, links, base


def read_artifact(target):
    """(files, problems of the archive format or None for a tree, info)."""
    t = Path(target)
    if t.is_file():
        files, p, info = parse_targz(t.read_bytes())
        info["kind"] = "archive"
        return files, p, info
    files, links, base = read_tree(t)
    return files, ([f"{x}: a link (22.8: refused)" for x in links] or None), {"kind": "tree", "base": str(base)}


# ---------------------------------------------------------------------------
# The rules of 22.3, 22.4 and 22.8 as functions (used by the modes and probed by C10 to C16)
# ---------------------------------------------------------------------------


def allow_list_problems(files):
    """22.3: the allow-list, and every file name has an extension."""
    p = []
    for f in sorted(files):
        if not (f in ALLOW_FILES or f.startswith(ALLOW_DIRS)):
            p.append(f"econ/{f} is outside the allow-list of 22.3")
        last = f.rsplit("/", 1)[-1]
        if "." not in last.lstrip("."):
            p.append(f"econ/{f} has no extension (22.3: every file name has one)")
    return p


def parse_expected(text):
    mt = RX_EXPECTED.fullmatch(text) if isinstance(text, str) else None
    if not mt:
        return "bad"
    return None if text == "none" else {"snapshot": mt.group(1), "manifest_sha256": mt.group(2)}


def site_deploy_decision(mode, input_ds, expected_current, deployed, release_log=None):
    """22.8 deploy: (allowed, rule). mode: data, site or unpublish. deployed: the dataset of the
    newest successful deployment (None when it carried none, or there is none). expected_current:
    'none' or '<snapshot>:<sha256>' (the data input); reading: in site and unpublish modes, which
    have no such input, it is the dataset the build read at its start. release_log: the release's
    deployments (data mode). Snapshot ids compare in time order."""
    exp = parse_expected(expected_current) if isinstance(expected_current, str) else expected_current
    if exp == "bad":
        return False, "input"
    if deployed != exp:
        return False, "compare-and-swap"
    if mode != "data":
        return True, "deploy"
    if not isinstance(input_ds, dict):
        return False, "input"
    if deployed is None or str(input_ds.get("snapshot")) > str(deployed.get("snapshot")):
        return True, "deploy"
    log = [e for e in (release_log or []) if isinstance(e, dict)]
    newest = log[-1] if log else None
    if newest is not None and newest.get("trigger") == "redeploy" and newest.get("dataset") == input_ds:
        if any(e.get("dataset") == newest.get("dataset") and e.get("site_commit") == newest.get("site_commit")
               and (e.get("verification") or {}).get("post") == "passed" for e in log[:-1]):
            return True, "deploy (rollback to a known-good pair)"
    return False, "monotonic"


def d55_refused(window_snapshots, publications, public_snapshots):
    """22.3 (D5.5, PROVISIONAL): the snapshots in the window whose publication record shows
    withdrawn and that have not been public: no earlier release whose entry has post passed or
    failed (it was deployed) contains snapshots/<S>.json. `public_snapshots` is the set those
    releases contain."""
    withdrawn = set()
    for pub in (publications or {}).get("publications", []) if isinstance(publications, dict) else []:
        if isinstance(pub, dict) and any(isinstance(ev, dict) and ev.get("status") == "withdrawn" for ev in pub.get("events") or []):
            withdrawn.add(pub.get("snapshot"))
    return sorted(x for x in withdrawn if x in window_snapshots and x not in public_snapshots)


def hold_leaks(ck, files):
    """22.5 check 10: no hold's archive_asset names a file of the artifact. reading: by path (with and
    without its archive-YYYY-MM/ folder) and by content (no artifact file has a held or locked
    candidate's SHA-256)."""
    p = []
    shas = {}
    for f, data in files.items():
        shas.setdefault(ck.sha256_hex(data), f)
    names = set(files) | {f.rsplit("/", 1)[-1] for f in files}
    for f in sorted(files):
        if not ck.RX_SNAPSHOT_PATH.fullmatch(f):
            continue
        try:
            snap = ck.load_strict(files[f])
        except Exception:
            continue
        for h in snap.get("holds") or [] if isinstance(snap, dict) else []:
            cand = (h or {}).get("candidate") or {}
            asset = cand.get("archive_asset")
            if isinstance(asset, str) and (asset in names or asset.split("/", 1)[-1] in names):
                p.append(f"{f}: hold {h.get('series')} archive_asset {asset} names a file of the artifact")
            if cand.get("sha256") in shas:
                p.append(f"{f}: the held candidate of {h.get('series')} is in the artifact as {shas[cand['sha256']]}")
        for fr in snap.get("frozen") or [] if isinstance(snap, dict) else []:
            if isinstance(fr, dict) and fr.get("candidate_sha256") in shas:
                p.append(f"{f}: the locked candidate of {fr.get('series')} is in the artifact as {shas[fr['candidate_sha256']]}")
    return sorted(set(p))


def reasons_in(ck, files):
    """22.3 (D6): the reasons in the artifact: snapshot holds[].reason and frozen[].reason, manifest
    rollback.reason, publication-record reason. Pin reasons are in no artifact file (pins.json is a
    state file), so none is read."""
    out = []
    for f in sorted(files):
        if not (f == "manifest.json" or f == "status/publications.json" or ck.RX_SNAPSHOT_PATH.fullmatch(f)):
            continue
        try:
            doc = ck.load_strict(files[f])
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        if f == "manifest.json" and isinstance(doc.get("rollback"), dict):
            out.append((f"{f} rollback.reason", doc["rollback"].get("reason")))
        elif f == "status/publications.json":
            for pub in doc.get("publications") or []:
                for ev in (pub or {}).get("events") or []:
                    if isinstance(ev, dict) and ev.get("reason") is not None:
                        out.append((f"{f} {pub.get('snapshot')} {ev.get('status')} at {ev.get('at')}", ev.get("reason")))
        else:
            for key in ("holds", "frozen"):
                for x in doc.get(key) or []:
                    if isinstance(x, dict):
                        out.append((f"{f} {key} {x.get('series')}", x.get("reason")))
    return out


def json_kind(ck, path, doc):
    """22.5 check 9: the schema of each JSON file of the artifact."""
    if path == "manifest.json":
        return "manifest"
    if path == DEPLOY_LOG:
        return "deployments"
    if path == "status/runs.json":
        return "runs"
    if path == "status/publications.json":
        return "publications"
    return ck.rx_kind(path)


def json_problems(ck, st, files):
    """22.5 check 9: every JSON file canonical and valid against its schema."""
    p, n = [], 0
    for f in sorted(files):
        if not f.endswith(".json"):
            continue
        n += 1
        try:
            doc = ck.load_strict(files[f])
        except Exception as exc:
            p.append(f"econ/{f}: {type(exc).__name__}: {exc}")
            continue
        why = ck.canonical_problem(files[f], doc)
        if why:
            p.append(f"econ/{f}: {why} (7)")
        kind = json_kind(ck, f, doc)
        if kind is None:
            p.append(f"econ/{f}: no schema covers this path (12.8)")
            continue
        if kind == "manifest":
            schema = ck.manifest_schema_for(st, doc)
            if not isinstance(doc, dict) or doc.get("schema") not in (ck.SCHEMA_IDS["manifest"], ck.MANIFEST_V4):
                p.append(f"econ/{f}: schema {doc.get('schema') if isinstance(doc, dict) else None!r} is not a manifest id")
        elif kind == "deployments":
            schema = st.v08_schemas["deployments"]
        elif kind == "publications":
            schema = (ck.rx_schema_by_id(st, "rmf.econ.publications/1") or (None, None))[1]
        else:
            schema = st.schemas.get(kind)
        if schema is None:
            p.append(f"econ/{f}: no schema file for {kind}")
            continue
        if kind in ck.SCHEMA_IDS and kind != "manifest" and isinstance(doc, dict) and doc.get("schema") != ck.SCHEMA_IDS[kind]:
            p.append(f"econ/{f}: schema {doc.get('schema')!r}, the text gives {ck.SCHEMA_IDS[kind]}")
        try:
            p += [f"econ/{f}: {e}" for e in ck.schema_errors(doc, schema)[:3]]
        except ck.SchemaKeywordError as exc:
            p.append(f"econ/{f}: validator cannot evaluate: {exc}")
    return p, n


CONTENT_RX = None


def closure_problems(ck, files):
    """22.5 check 4 (12.3) over the artifact alone: every file the manifest and its snapshot name is
    present with its SHA-256 (and bytes where the snapshot gives them); every content-addressed path
    equals its address; a CSV segment's path names its series and segment."""
    p = []
    try:
        m = ck.load_strict(files["manifest.json"])
    except Exception as exc:
        return [f"econ/manifest.json: {type(exc).__name__}: {exc}" if "manifest.json" in files else "econ/manifest.json is missing"]
    ref = (m.get("snapshot") or {}) if isinstance(m, dict) else {}
    named = dict(ck.rx_manifest_files(m)) if isinstance(m, dict) else {}
    if ref.get("path") != f"snapshots/{ref.get('id')}.json":
        p.append(f"the manifest's snapshot path {ref.get('path')} is not snapshots/{ref.get('id')}.json")
    named[ref.get("path")] = (ref.get("sha256"), None)
    snap = None
    if ref.get("path") in files:
        try:
            snap = ck.load_strict(files[ref["path"]])
            named.update({k: v for k, v in ck.rx_snapshot_files(snap).items() if k not in named or v[1] is not None})
        except Exception as exc:
            p.append(f"econ/{ref.get('path')}: {type(exc).__name__}: {exc}")
    for path, (sha, nbytes) in sorted(named.items(), key=lambda x: str(x[0])):
        data = files.get(path) if isinstance(path, str) else None
        if data is None:
            p.append(f"econ/{path} is named but missing")
        elif ck.sha256_hex(data) != sha:
            p.append(f"econ/{path} has sha256 {ck.sha256_hex(data)[:16]}, named with {str(sha)[:16]}")
        elif nbytes is not None and len(data) != nbytes:
            p.append(f"econ/{path} is {len(data)} bytes, named with {nbytes}")
    for sid, summ in sorted((m.get("series") or {}).items()) if isinstance(m, dict) else []:
        for r in ck.rx_csv_refs(summ):
            mt = ck.RX_CSV_PATH.fullmatch(str(r.get("path")))
            if not mt or mt.group(1) != sid or mt.group(2) != r.get("segment"):
                p.append(f"{sid}: CSV path {r.get('path')} does not name its series and segment {r.get('segment')} (12.3)")
    for f, data in sorted(files.items()):
        for rx in (ck.RX_OBJECT_PATH, ck.RX_CSV_PATH, ck.RX_LOG_PATH, ck.RX_REVCSV_PATH, ck.RX_REGCOPY_PATH, ck.RX_HOLCOPY_PATH, ck.RX_NOTICE_PATH):
            mt = rx.fullmatch(f)
            if mt:
                if mt.group(mt.lastindex) != ck.sha256_hex(data)[:16]:
                    p.append(f"econ/{f} is not named by its own SHA-256 ({ck.sha256_hex(data)[:16]})")
                break
        else:
            mt = ck.RX_SNAPSHOT_PATH.fullmatch(f)
            if mt:
                try:
                    if ck.load_strict(data).get("id") != mt.group(1):
                        p.append(f"econ/{f}: its id is not {mt.group(1)}")
                except Exception:
                    pass
    return p


def limit_problems(ck, files):
    """22.5 check 7: the hard limits of 17.7 on the tree."""
    p = []
    total = sum(len(v) for v in files.values())
    if total > LIMIT_PUBLISHED:
        p.append(f"the tree is {total} bytes, over 250 MB")
    for f, data in sorted(files.items()):
        if len(data) > ck.LIMIT_FILE:
            p.append(f"econ/{f} is {len(data)} bytes, over 5 MB")
        if ck.RX_OBJECT_PATH.fullmatch(f) and len(data) > ck.LIMIT_OBJECT:
            p.append(f"econ/{f} is {len(data)} bytes, over 2 MB for an object")
    if len(files.get("manifest.json", b"")) > ck.LIMIT_MANIFEST:
        p.append(f"econ/manifest.json is {len(files['manifest.json'])} bytes, over 256 KB")
    return p, total


def compat_exception(manifest_bytes, pinned=(COMPAT_SNAPSHOT, COMPAT_MANIFEST_SHA256)):
    """22.2 amendment 1, 22.5 check 8: whether econ/manifest.json is the dataset of the exception: its
    bytes hash to the pinned SHA-256 and the snapshot id it names is the pinned one, both together, and
    it is a manifest/3 (a manifest/4 is never the exception). reading: the SHA-256 is that of the bytes
    of manifest.json as the artifact holds them (the manifest_sha256 of 21.1), never of a parsed
    re-serialization. `pinned` is given by the self-tests only; the modes use the constants."""
    import hashlib
    if not isinstance(manifest_bytes, bytes) or hashlib.sha256(manifest_bytes).hexdigest() != pinned[1]:
        return False
    try:
        m = json.loads(manifest_bytes)
    except Exception:
        return False
    return isinstance(m, dict) and m.get("schema") == COMPAT_SCHEMA and isinstance(m.get("snapshot"), dict) and m["snapshot"].get("id") == pinned[0]


def rule_file_problems(ck, st, files, store=None, pinned=(COMPAT_SNAPSHOT, COMPAT_MANIFEST_SHA256)):
    """22.5 check 8 (second part): every registry copy hashes to the registry hash a window snapshot
    names (and each such hash has its copy), the holiday copy and the notice file as 22.9 gives them,
    NOTICE.txt equal to the named notice. For a manifest/3 the rule files are required, except for the
    dataset of the 22.2 exception (amendment 1): for it this part passes when the artifact holds no
    registry/ or notices/ file and no NOTICE.txt. `pinned` is given by the self-tests only."""
    p = []
    try:
        m = ck.load_strict(files["manifest.json"])
    except Exception:
        return ["econ/manifest.json unreadable"]
    if m.get("schema") != ck.MANIFEST_V4:
        if compat_exception(files["manifest.json"], pinned):
            # 22.2 amendment 1: published as it stands; nothing is added to make up for the rule files
            return [f"econ/{f} is in the artifact of the 22.2 exception dataset {pinned[0]} (amendment 1: its manifest/3 is published without rule files, so it holds no registry/ or notices/ file and no NOTICE.txt; 22.5 check 8)"
                    for f in sorted(files) if f == "NOTICE.txt" or f.startswith(("registry/", "notices/"))]
        return [f"the manifest is {m.get('schema')}: no rule files (22.9: written with every manifest from the first v0.8 run on; a publication needs them, reading)"]
    rules = m.get("rules") or {}
    by_hash = ck.registry_by_hash(st)
    named_hashes = set()
    for f in files:
        if ck.RX_SNAPSHOT_PATH.fullmatch(f):
            try:
                named_hashes.add((ck.load_strict(files[f]).get("run") or {}).get("registry_sha256"))
            except Exception:
                pass
    copies = {f: ck.sha256_hex(d) for f, d in files.items() if ck.RX_REGCOPY_PATH.fullmatch(f)}
    for f, h in sorted(copies.items()):
        if h not in named_hashes and h != (rules.get("registry") or {}).get("sha256"):
            p.append(f"econ/{f} hashes to {h[:16]}, which no window snapshot names")
        _, cprob = ck.registry_copy_problems(st, files[f], h)
        if cprob:
            p.append(f"econ/{f} is not a valid canonical registry: {cprob[0]} (22.9)")
        if h in by_hash and files[f] != by_hash[h][1]:
            p.append(f"econ/{f} is not the canonical JSON of registry version {by_hash[h][0]}")
        if h not in by_hash and (store is None or store.read(f"root/archive/files/{f}") != files[f]):
            p.append(f"econ/{f} ({h[:16]}) is neither the current registry, a version derived by I7, nor the archived copy of a v0.8 run in root/archive/files/ (22.9, I44)")
    for h in sorted(x for x in named_hashes if x):
        if h not in copies.values():
            p.append(f"a window snapshot names registry {h[:16]} but the artifact has no copy registry/econ-{h[:16]}.json")
    hol = rules.get("holidays") or {}
    if getattr(st, "holiday_doc", None) is not None and files.get(hol.get("path")) != ck.canon_bytes(st.holiday_doc):
        p.append(f"the holiday copy {hol.get('path')} is not the canonical JSON of the holiday table in use")
    nref = rules.get("notice") or {}
    notice = files.get(nref.get("path"))
    rsha = (rules.get("registry") or {}).get("sha256")
    own = by_hash.get(rsha)
    if own is None and files.get((rules.get("registry") or {}).get("path")) is not None:
        try:
            own = ("archived", None, ck.load_strict(files[rules["registry"]["path"]]))  # 22.9 (I44): this run's own archived copy
        except Exception:
            own = None
    if notice is None:
        p.append(f"the notice file {nref.get('path')} is missing")
    elif own is not None and ck.is_time(m.get("generated_at")):
        want = ck.notice_file_bytes(own[2], m["generated_at"])
        if notice != want:
            p.append(f"the notice file differs from 22.9 at {ck.first_line_difference(notice, want)}")
    if files.get("NOTICE.txt") != notice:
        p.append("NOTICE.txt is missing or differs from the named notice file (22.9)")
    return p


# ---------------------------------------------------------------------------
# The store at C
# ---------------------------------------------------------------------------


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()

    def read(self, rel):
        x = self.path / rel
        return x.read_bytes() if x.is_file() else None

    def files(self, rel):
        base = self.path / rel
        return {x.relative_to(base).as_posix(): x.read_bytes() for x in sorted(base.rglob("*")) if x.is_file()} if base.is_dir() else {}


def store_context(ck, st, store):
    rv = ck.RootView(store.path / "root", state=store.path / "state", state_exclude=("STATE.json",))
    return ck.root_context(st, rv, quiet=True)


def window_of(ck, ctx, manifest):
    """13, 17.6: the window of a manifest as of its generated_at, from the root's archive: the files it
    and its window snapshots name, the manifest, status/ and NOTICE.txt (22.9). For a manifest older
    than the live one (a redeploy, or an earlier release's contents), only the snapshots and manifests
    up to its generated_at count, and the pins are that manifest's own pages_window.pinned (22.3)."""
    gen = manifest.get("generated_at")
    if manifest is not ctx.manifest:
        ctx.snaps = {k: v for k, v in ctx.snaps.items() if str(v.get("created_at")) <= str(gen)}
        ctx.order = sorted(ctx.snaps)
        ctx.arch_manifests = [x for x in ctx.arch_manifests if x[2] or str(x[1].get("generated_at")) <= str(gen)]
        ctx.manifest = manifest
        ctx.cur_id = (manifest.get("snapshot") or {}).get("id")
        ctx.cur = ctx.snaps.get(ctx.cur_id)
        ctx.pins_override = list((manifest.get("pages_window") or {}).get("pinned") or [])
        ctx.window, ctx.significant, ctx.named_cache = None, None, {}
    snaps, files = ck.rx_window(ctx)
    return snaps, files


# ---------------------------------------------------------------------------
# The publication mode (22.5 V2c)
# ---------------------------------------------------------------------------


def read_release(path):
    d = Path(path)
    return d.name, ({x.name: x.read_bytes() for x in sorted(d.iterdir()) if x.is_file()} if d.is_dir() else {})


def release_log(ck, assets):
    try:
        doc = ck.load_strict(assets.get("deployments.json") or b"")
    except Exception:
        return None
    return doc if isinstance(doc, dict) and isinstance(doc.get("deployments"), list) else None


def entries_of(doc):
    return [e for e in (doc or {}).get("deployments", []) if isinstance(e, dict)]


def archived_manifest(ctx, ck, sha):
    for name in sorted(ctx.rv.files(ctx.rv.manifests)):
        data = ctx.rv.read(ctx.rv.manifests, name)
        if ck.sha256_hex(data) == sha:
            return ck.load_strict(data), data
    return None, None


def deployed_snapshots(ck, st, store, entries):
    """22.3 (D5.5): the snapshots the earlier deployed releases (post passed or failed) contain:
    each one's window is that of its dataset's archived manifest as of its generated_at (22.3:
    a manual or timer window is root/live at its C, a redeploy's the target's rebuilt window), with
    that manifest's own generated_at and pages_window (22.3)."""
    out, problems = set(), []
    for e in entries:
        if (e.get("verification") or {}).get("post") not in ("passed", "failed"):
            continue
        ctx = store_context(ck, st, store)
        man, _ = archived_manifest(ctx, ck, (e.get("dataset") or {}).get("manifest_sha256"))
        if man is None:
            problems.append(f"release {e.get('release')} (entry {e.get('number')}) names a dataset with no archived manifest: what it contained cannot be told")
            continue
        snaps, _ = window_of(ck, ctx, man)
        out |= set(snaps)
    return out, problems


def run_publication(ck, st, target, store_dir, prev_dir=None):
    check = ck.check
    print(f"check_publication.py: artifact {target}; store {store_dir}; newest earlier release {prev_dir or 'none given'}")
    files, fmt, info = read_artifact(target)
    if fmt is not None or info.get("kind") == "archive":
        check("P0 artifact.tar.gz is the deterministic archive of 22.3 (POSIX ustar, names econ/<path> in byte order, regular files only, mode 0644, owner and group 0 with empty names, mtime 0; gzip with no file name, mtime 0 and OS byte 255) and extracts safely (22.8)", fmt or [],
              f"{info.get('entries', len(files or {}))} entries" if info.get("kind") == "archive" else "a tree")
    if files is None:
        check("P1 the allow-list (22.3)", ["the artifact could not be read"])
        return
    store = Store(store_dir) if store_dir else None
    if store is None or not (store.path / "state" / "STATE.json").is_file():
        check("P2 the store at C is readable (22.5 V2c runs on the artifact and the store)", [f"{store_dir}: no state/STATE.json"])
        return
    desc = ck.load_strict(store.read("state/STATE.json"))
    accepted = desc.get("accepted") if isinstance(desc, dict) else None
    live = store.files("root/live")
    try:
        art_log_doc = ck.load_strict(files[DEPLOY_LOG]) if DEPLOY_LOG in files else None
    except Exception:
        art_log_doc = None
    art_log = entries_of(art_log_doc)
    newest = art_log[-1] if art_log else {}
    redeploy = newest.get("trigger") == "redeploy"
    prev_tag, prev_assets = read_release(prev_dir) if prev_dir else (None, None)
    prev_doc = release_log(ck, prev_assets) if prev_assets is not None else None

    check("P1 the allow-list: manifest.json, objects/, series/, snapshots/, revisions/, status/runs.json, status/publications.json, status/deployments.json, registry/, notices/, NOTICE.txt and nothing else; every file name has an extension (22.3, 22.5 check 1)",
          allow_list_problems(files), f"{len(files)} files")

    # P2 (22.3, 22.5 check 2)
    ctx = store_context(ck, st, store)
    want_tree = {}
    tman = None
    if redeploy:
        tman, tbytes = archived_manifest(ctx, ck, (newest.get("dataset") or {}).get("manifest_sha256"))
        if tman is not None:
            _, wfiles = window_of(ck, ctx, tman)
            for path in wfiles:
                if path == "NOTICE.txt":
                    nref = ((tman.get("rules") or {}).get("notice") or {}).get("path")
                    if nref and ctx.rv.read(ctx.rv.arch, nref) is not None:
                        want_tree["NOTICE.txt"] = ctx.rv.read(ctx.rv.arch, nref)  # 22.3: a byte copy of the notice file that manifest names
                    continue
                data = ctx.rv.read(ctx.rv.arch, path)
                if data is not None:
                    want_tree[path] = data
            want_tree["manifest.json"] = tbytes
            for f in ("status/runs.json", "status/publications.json"):
                if f in live:
                    want_tree[f] = live[f]
    else:
        want_tree = live
    p = [] if not redeploy or tman is not None else [f"no archived manifest has the redeploy target's SHA-256 {str((newest.get('dataset') or {}).get('manifest_sha256'))[:16]}"]
    for f in sorted(set(want_tree) | (set(files) - {DEPLOY_LOG})):
        if f not in files:
            p.append(f"root/live/{f} is not in the artifact" if not redeploy else f"econ/{f} of the target's window is missing")
        elif f not in want_tree:
            p.append(f"econ/{f} is not in root/live/ at C" if not redeploy else f"econ/{f} is not in the target's window")
        elif files[f] != want_tree[f]:
            p.append(f"econ/{f} differs from the store's copy")
    if DEPLOY_LOG in live:
        p.append("root/live/ holds status/deployments.json (22.3: only the publication adds it)")
    if DEPLOY_LOG not in files:
        p.append("econ/status/deployments.json is missing (22.3: the only file a publication adds)")
    check("P2 manual and timer: every window file equals root/live/ at C byte for byte and every root/live/ file is present; redeploy: the window equals the target's, rebuilt from root/archive/ at C with the status files as at C and NOTICE.txt a copy of its named notice; status/deployments.json is the only file added (22.3, 22.5 check 2)", p,
          f"{len(want_tree)} window files" + (" (redeploy)" if redeploy else ""))

    # P3
    p = []
    mdata = files.get("manifest.json")
    msha = ck.sha256_hex(mdata) if mdata is not None else None
    try:
        man = ck.load_strict(mdata) if mdata is not None else {}
    except Exception:
        man = {}
    got = {"snapshot": (man.get("snapshot") or {}).get("id"), "manifest_sha256": msha}
    want = newest.get("dataset") if redeploy else accepted
    if got != want:
        p.append(f"the manifest gives {got}, " + ("the redeploy's target dataset is" if redeploy else "the accepted identifier at C is") + f" {want} (21.1)")
    if redeploy and not any(e.get("dataset") == want and e.get("site_commit") == newest.get("site_commit") and (e.get("verification") or {}).get("post") == "passed" for e in art_log[:-1]):
        p.append("the redeploy's dataset and site commit are not a verified pair (an earlier entry with post passed, 22.4, D13)")
    if newest and newest.get("dataset") != got:
        p.append(f"the new log entry's dataset {newest.get('dataset')} is not the artifact's {got}")
    check("P3 manual and timer: the manifest's SHA-256 and snapshot id equal the accepted identifier at C; redeploy: the target dataset, a verified pair's (22.5 check 3)", p, str(got.get("snapshot")))

    check("P4 closure and hashes over the artifact alone: every file the manifest and its snapshot name is present with its SHA-256, every content-addressed path is its address (12.3, 22.5 check 4)", closure_problems(ck, files))

    # P5
    p, snaps_w = [], {}
    if isinstance(man, dict) and ck.is_time(man.get("generated_at")):
        ctx2 = store_context(ck, st, store)
        snaps_w, wfiles = window_of(ck, ctx2, man if redeploy else ctx2.manifest)
        need = set(wfiles) | {"manifest.json", "status/runs.json", "status/publications.json"}
        have = set(files) - {DEPLOY_LOG}
        p += [f"econ/{f} is in the window ({wfiles[f][2][0] if f in wfiles else 'manifest or status'}) but not in the artifact" for f in sorted(need - have)]
        p += [f"econ/{f} is outside the window as of {man.get('generated_at')}" for f in sorted(have - need)]
    else:
        p.append("no readable manifest")
    check("P5 the artifact holds exactly the window of 13 and 17.6 as of the manifest's generated_at, the rule files and NOTICE.txt included (22.5 check 5)", p, f"{len(snaps_w)} window snapshots")

    p, n = [], 0
    for where, text in reasons_in(ck, files):
        n += 1
        bad = ck.d6_problems(text)
        if bad:
            p.append(f"{where}: {', '.join(bad)}")
    check("P6 every reason in the artifact passes the reason check of 22.3 items 1 to 9 (snapshot holds and frozen reasons, rollback.reason, publication-record reasons) (22.5 check 6; PROVISIONAL)", p, f"{n} reason(s)")

    lp, total = limit_problems(ck, files)
    check("P7 the hard limits of 17.7 on the tree: 250 MB in all, 5 MB a file, 2 MB an object, 256 KB the manifest (22.5 check 7)", lp, f"{total} bytes")

    # P8: the chain of releases, the new entry and the rule files
    p = []
    if art_log_doc is None:
        p.append("econ/status/deployments.json is missing or unreadable")
    else:
        p += ck.deployment_log_problems(art_log_doc, "econ/status/deployments.json", False, st)
        if prev_assets is not None and prev_doc is None:
            p.append(f"the newest earlier release {prev_tag}: its deployments.json is unreadable")
        if prev_doc is not None:
            own = entries_of(prev_doc)[-1] if entries_of(prev_doc) else {}
            if own.get("release") != prev_tag:
                p.append(f"the earlier release {prev_tag}: its own entry names release {own.get('release')}")
        p += ck.log_chain_problems(art_log_doc, prev_doc, "econ/status/deployments.json")
        a_sha, a_n, a_b = artifact_sha(files)
        if newest.get("artifact") != {"files": a_n, "bytes": a_b, "sha256": a_sha}:
            p.append(f"the new entry's artifact {newest.get('artifact')} is not {{files {a_n}, bytes {a_b}, sha256 {a_sha[:16]}}} over the tree without status/deployments.json (22.3)")
    p += rule_file_problems(ck, st, files, store)
    compat = compat_exception(files.get("manifest.json"))  # 22.5 check 8: the report says that the 22.2 exception was applied
    check("P8 the deployment log extends the newest earlier release's log (its last post fixed, one new entry with post null and its artifact recomputed); every registry copy hashes to a registry a window snapshot names, the holiday copy and the notice file are as 22.9 gives them, NOTICE.txt equals the named notice (22.4, 22.5 check 8, 22.9)", p,
          f"{len(art_log)} log entries; newest earlier release {prev_tag or 'none'}"
          + (f"; compatibility exception applied (22.2 amendment 1): manifest/3 dataset {COMPAT_SNAPSHOT} without rule files" if compat else ""))

    jp, nj = json_problems(ck, st, files)
    check("P9 every JSON file of the artifact is canonical and valid against its schema (manifest/3 or manifest/4 and deployments/1 as built from the text) (22.5 check 9)", jp, f"{nj} JSON files")
    check("P10 no hold's archive_asset names a file of the artifact, and no held or locked candidate is in it (22.5 check 10; reading: by path and by content)", hold_leaks(ck, files))

    # P11: D5.5
    try:
        pubs = ck.load_strict(files["status/publications.json"])
    except Exception:
        pubs = None
    in_window = {ck.RX_SNAPSHOT_PATH.fullmatch(f).group(1) for f in files if ck.RX_SNAPSHOT_PATH.fullmatch(f)}
    public, p = deployed_snapshots(ck, st, store, art_log[:-1])
    refused = d55_refused(in_window, pubs, public)
    p += [f"snapshot {x} is withdrawn and has not been public: no earlier deployed release contains snapshots/{x}.json (a publication refuses)" for x in refused]
    check("P11 D5.5: the window holds no snapshot whose publication record shows withdrawn and that has not been public, that is, contained in an earlier release whose entry has post passed or failed (22.3, 22.5 check 11; PROVISIONAL)", p,
          f"{len(in_window)} window snapshot(s), {len(public)} in deployed releases")


def sums_problems(ck, folder):
    """22.4: SHA256SUMS: one line per other asset, in name order, '<sha256>  <name>' and a line feed."""
    data = folder.get("SHA256SUMS")
    if data is None:
        return ["SHA256SUMS is missing"]
    want = "".join(f"{ck.sha256_hex(folder[n])}  {n}\n" for n in sorted(("artifact.tar.gz", "manifest.json", "deployments.json")) if n in folder).encode()
    if data != want:
        lines = data.decode("utf-8", "replace").split("\n")
        return [f"SHA256SUMS is not the three lines '<sha256>  <name>' of the assets in name order (first line {lines[0]!r})"]
    return []


def run_release(ck, st, release_dir, expect, prev_dir=None):
    check = ck.check
    tag, folder = read_release(release_dir)
    print(f"check_publication.py: release {release_dir}")
    p = [f"{n} is missing" for n in ASSETS if n not in folder] + [f"{n} is not an asset of 22.4" for n in sorted(set(folder) - set(ASSETS))]
    if not RX_TAG_SITE.fullmatch(tag):
        p.append(f"the tag {tag!r} does not match ^data-\\d{{8}}T\\d{{6}}Z-\\d+-\\d+$ (22.8: inputs are validated before any use)")
    check("RL1 the release holds exactly the four assets artifact.tar.gz, manifest.json, deployments.json and SHA256SUMS, and its tag passes the 22.8 pattern (22.4, 22.8)", p, tag)
    check("RL2 SHA256SUMS lists the SHA-256 and name of the three other assets in name order and each matches (22.4, 22.8)", sums_problems(ck, folder))
    log_doc = release_log(ck, folder) or {}
    log = entries_of(log_doc)
    newest = log[-1] if log else {}
    ds = newest.get("dataset") or {}
    p = []
    if expect is not None:
        ex = parse_expected(expect)
        if ex in ("bad", None):
            p.append(f"--expect {expect!r} is not <snapshot>:<sha256>")
        elif ex != ds:
            p.append(f"the input dataset {ex} is not the release's newest log entry's {ds}")
        else:
            ds = ex
    man = folder.get("manifest.json")
    if man is None or ck.sha256_hex(man) != ds.get("manifest_sha256"):
        p.append(f"manifest.json does not hash to the input manifest_sha256 {str(ds.get('manifest_sha256'))[:16]}")
    else:
        try:
            if (ck.load_strict(man).get("snapshot") or {}).get("id") != ds.get("snapshot"):
                p.append(f"manifest.json does not name the input snapshot {ds.get('snapshot')}")
        except Exception as exc:
            p.append(f"manifest.json: {exc}")
    if newest.get("release") != tag:
        p.append(f"the newest log entry names release {newest.get('release')}, not this tag")
    check("RL3 manifest.json hashes to the input manifest_sha256 and names the input snapshot (22.8; reading: by default the input is the release's newest log entry, whose release is this tag)", p, str(ds.get("snapshot")))
    files, fmt, info = parse_targz(folder.get("artifact.tar.gz") or b"")
    check("RL4 artifact.tar.gz extracts safely (names inside econ/, no link, no non-regular file) and is the deterministic archive of 22.3 (22.8)", fmt + ([] if files is not None else ["unreadable"]), f"{info.get('entries')} entries")
    if files is None:
        return
    p = []
    a_sha, a_n, a_b = artifact_sha(files)
    if newest.get("artifact") != {"files": a_n, "bytes": a_b, "sha256": a_sha}:
        p.append(f"the recomputed artifact {{files {a_n}, bytes {a_b}, sha256 {a_sha[:16]}}} is not the newest log entry's {newest.get('artifact')} (22.8)")
    if files.get("manifest.json") != man:
        p.append("the manifest.json asset is not econ/manifest.json of the archive (22.4)")
    if files.get(DEPLOY_LOG) != folder.get("deployments.json"):
        p.append("the deployments.json asset is not econ/status/deployments.json of the archive (22.4)")
    p += ck.deployment_log_problems(log_doc, "deployments.json", False, st)
    if prev_dir:
        ptag, pass_ = read_release(prev_dir)
        p += ck.log_chain_problems(log_doc, release_log(ck, pass_), f"deployments.json against {ptag}")
    check("RL5 the recomputed artifact SHA-256 equals the release's newest log entry's; the manifest and deployments assets equal their copies in the archive; the log follows 22.4 (and extends the given earlier release's) (22.4, 22.8)", p, a_sha[:16])
    got = {"snapshot": None, "manifest_sha256": ck.sha256_hex(files["manifest.json"]) if "manifest.json" in files else None}
    try:
        got["snapshot"] = (ck.load_strict(files["manifest.json"]).get("snapshot") or {}).get("id")
    except Exception:
        pass
    check("P3 (release) the manifest's SHA-256 and snapshot id equal the dataset (22.5 check 3 from the release alone)", [] if got == ds else [f"{got} is not {ds}"])
    check("P4 (release) closure and hashes over the tree (22.5 check 4)", closure_problems(ck, files))
    jp, nj = json_problems(ck, st, files)
    check("P9 (release) every JSON file canonical and valid against its schema (22.5 check 9)", jp, f"{nj} JSON files")


def release_history_problems(ck, releases, deployed=None):
    """22.7 (the watcher, from public data only): every release the newest log names exists and has
    exactly its four assets; every existing data-* release is named by the log; the newest
    release's SHA256SUMS matches its other three assets; each release's own deployments.json equals
    the newest log's entries up to its own, except that its last entry's post is null.
    `releases`: {tag: {asset name: bytes}}. The newest is the one whose own entry has the highest number.
    `deployed`: the deployed status/deployments.json fetched from the public address (bytes), which
    names only releases that exist and whose newest entry's number is not higher than the newest
    release's: this catches a deleted newest release."""
    p, logs = [], {}
    if deployed is not None:
        try:
            dep = entries_of(ck.load_strict(deployed))
        except Exception as exc:
            dep = []
            p.append(f"the deployed status/deployments.json is unreadable: {exc}")
        p += [f"the deployed status/deployments.json names {e.get('release')}, which does not exist" for e in dep if e.get("release") not in releases]
        top = max((lg[-1].get("number") for lg in (entries_of(release_log(ck, a)) for a in releases.values()) if lg and isinstance(lg[-1].get("number"), int)), default=0)
        if dep and isinstance(dep[-1].get("number"), int) and dep[-1]["number"] > top:
            p.append(f"the deployed log's newest entry is number {dep[-1]['number']}, higher than the newest release's {top} (a deleted newest release)")
    for tag, assets in sorted(releases.items()):
        if set(assets) != set(ASSETS):
            p.append(f"{tag}: assets {sorted(assets)}; a release has exactly the four of 22.4")
        doc = release_log(ck, assets)
        if doc is None or not entries_of(doc):
            p.append(f"{tag}: deployments.json is missing or unreadable")
            continue
        logs[tag] = entries_of(doc)
        if logs[tag][-1].get("release") != tag:
            p.append(f"{tag}: its own entry names release {logs[tag][-1].get('release')}")
    if not logs:
        return p
    newest_tag = max(logs, key=lambda t: (logs[t][-1].get("number") if isinstance(logs[t][-1].get("number"), int) else -1, t))
    newest = logs[newest_tag]
    named = [e.get("release") for e in newest]
    p += [f"the newest log ({newest_tag}) names {t}, which does not exist" for t in named if t not in releases]
    p += [f"{t} exists but the newest log ({newest_tag}) does not name it" for t in sorted(releases) if t.startswith("data-") and t not in named]
    p += [f"{newest_tag}: {e}" for e in sums_problems(ck, releases[newest_tag])]
    for tag, lg in sorted(logs.items()):
        n = lg[-1].get("number")
        if not isinstance(n, int) or n < 1:
            continue
        want = json.loads(json.dumps(newest[:n]))
        if want and isinstance(want[-1].get("verification"), dict):
            want[-1]["verification"]["post"] = None
        if lg != want:
            p.append(f"{tag}: its deployments.json is not the newest log's entries 1 to {n} with its own post null")
    return p


def run_release_history(ck, st, folder, deployed_path=None):
    d = Path(folder)
    releases = dict(read_release(x) for x in sorted(d.iterdir()) if x.is_dir()) if d.is_dir() else {}
    deployed = Path(deployed_path).read_bytes() if deployed_path else None
    ck.check("RH1 the release history from public data: every release the newest log names exists with exactly its four assets, every data-* release is named, the newest SHA256SUMS matches, each release's log is the newest log up to its own entry with its post null, and the deployed status/deployments.json names only existing releases and no number above the newest release's (22.7, 21.9: a difference raises publication-history-changed)",
             release_history_problems(ck, releases, deployed), f"{len(releases)} release(s), deployed log {'given' if deployed is not None else 'not given'}")


# ---------------------------------------------------------------------------
# The site build's deployed state (22.8)
# ---------------------------------------------------------------------------


RX_RUN_NAME = re.compile(r"pages (site|data|unpublish) (\d{8}T\d{6}Z|none) ([0-9a-f]{64}|none) (data-\d{8}T\d{6}Z-\d+-\d+|none)", re.ASCII)


def parse_run_name(name):
    """22.8: 'pages <mode> <snapshot or none> <manifest_sha256 or none> <release or none>' to
    (mode, dataset or None, release or None); None when malformed or half a dataset."""
    mt = RX_RUN_NAME.fullmatch(name) if isinstance(name, str) else None
    if not mt:
        return None
    mode, snap, sha, rel = mt.groups()
    if (snap == "none") != (sha == "none"):
        return None
    return mode, (None if snap == "none" else {"snapshot": snap, "manifest_sha256": sha}), (None if rel == "none" else rel)


def deployed_state(runs):
    """22.8: the deployed state is the dataset of the newest run that concluded success and did not
    skip its deploy (None: none, after an unpublish or when no run ever carried data)."""
    for r in reversed([x for x in runs if isinstance(x, dict)]):
        if r.get("conclusion") == "success" and r.get("deployed") is True:
            return r.get("dataset")
    return None


# ---------------------------------------------------------------------------
# Appendix J
# ---------------------------------------------------------------------------

J_FIELDS = ("step", "run", "at", "kind", "mode", "outcome", "release", "deployed", "alerts")
J_OUTCOMES = ("released-deployed", "refused-gate", "site-carried", "published", "refused-cas", "refused-older", "no-op", "verify-failed", "redeployed",
              "refused-paused", "refused-reason", "refused-v2", "rollback", "refused-d5", "unpublished", "site-no-data")
PVF, PF = "publication-verify-failed", "publish-failed"
J_CHECKER = {"pass": 1, "fail": 0, "skip": 0}  # appendix J (I47): V2b's counts, fixed
# step: (run, time, kind, mode, outcome, release (dataset label) or None, deployed after (label) or None, alerts after)
J_TABLE = {
    1: (1, "2026-11-24T15:00:00Z", "publish", "manual", "released-deployed", "N1", "N1", []),
    2: (2, "2026-11-24T15:10:00Z", "publish", "manual", "refused-gate", None, "N1", []),
    3: (3, "2026-11-24T15:20:00Z", "site", "site", "site-carried", None, "N1", []),
    4: (4, "2026-11-24T16:17:00Z", "collect", "timer", "published", None, "N1", []),
    5: (5, "2026-11-24T16:40:00Z", "publish", "manual", "refused-cas", "N2", "N1", [PF]),
    6: (6, "2026-11-24T16:50:00Z", "publish", "manual", "released-deployed", "N2", "N2", []),
    7: (7, "2026-11-24T17:00:00Z", "site", "data", "refused-older", None, "N2", []),
    8: (8, "2026-11-24T17:10:00Z", "publish", "manual", "no-op", None, "N2", []),
    9: (9, "2026-11-24T17:20:00Z", "collect", "manual", "published", None, "N2", []),
    10: (10, "2026-11-24T17:25:00Z", "publish", "manual", "verify-failed", "N3", "N3", [PVF]),
    11: (1001, "2026-11-24T17:25:00Z", "publish", "redeploy", "redeployed", "N2", "N2", [PVF]),
    12: (12, "2026-11-24T17:40:00Z", "publish", "timer", "refused-paused", None, "N2", [PVF]),
    13: (13, "2026-11-24T17:50:00Z", "operate", "rollback", "refused-reason", None, "N2", [PVF]),
    14: (14, "2026-11-24T18:00:00Z", "publish", "manual", "refused-v2", None, "N2", sorted([PVF, PF])),
    15: (15, "2026-11-25T16:17:00Z", "collect", "timer", "published", None, "N2", sorted([PVF, PF])),
    16: (16, "2026-11-25T16:30:00Z", "operate", "rollback", "rollback", None, "N2", sorted([PVF, PF])),
    17: (17, "2026-11-25T16:40:00Z", "publish", "manual", "refused-d5", None, "N2", sorted([PVF, PF])),
    18: (18, "2026-11-25T16:50:00Z", "site", "unpublish", "unpublished", None, None, sorted([PVF, PF])),
    19: (19, "2026-11-25T17:00:00Z", "site", "site", "site-no-data", None, None, sorted([PVF, PF])),
}
# The releases (step: entry number, trigger, the post its entry gets in later logs)
J_RELEASES = {1: (1, "manual", "passed"), 5: (2, "manual", "not-deployed"), 6: (3, "manual", "passed"), 10: (4, "manual", "failed"), 11: (5, "redeploy", "passed")}
# The site runs (step, run (a dispatched one carries the publication run's id), mode, dataset label, release step, conclusion, deployed)
J_SITE_RUNS = [(1, 1, "data", "N1", 1, "success", True), (3, 3, "site", "N1", 1, "success", True), (5, 5, "data", "N2", 5, "failure", False),
               (6, 6, "data", "N2", 6, "success", True), (7, 7, "data", "N1", 1, "failure", False), (10, 10, "data", "N3", 10, "success", True),
               (11, 1001, "data", "N2", 11, "success", True), (18, 18, "unpublish", None, None, "success", True), (19, 19, "site", None, None, "success", True)]


def run_pub_scenario(ck, st, d):
    check = ck.check
    d = Path(d)
    print(f"check_publication.py: appendix J folder {d}")
    try:
        steps = ck.load_strict((d / "steps.json").read_bytes())
    except Exception as exc:
        check("J0 steps.json is readable", [f"{exc}"])
        return
    p = []
    if not isinstance(steps, list) or len(steps) != len(J_TABLE):
        p.append(f"steps.json is not a JSON array of {len(J_TABLE)} objects: {type(steps).__name__} of {len(steps) if isinstance(steps, list) else '-'}")
        steps = steps if isinstance(steps, list) else []
    for i, row in enumerate(steps):
        if not isinstance(row, dict):
            p.append(f"row {i + 1} is not an object")
            continue
        if set(row) != set(J_FIELDS):
            p.append(f"row {i + 1} has fields {sorted(row)}; appendix J gives exactly {list(J_FIELDS)}")
        if row.get("outcome") not in J_OUTCOMES:
            p.append(f"row {i + 1}: outcome {row.get('outcome')!r} is not in the list of appendix J")
        if not isinstance(row.get("alerts"), list) or row["alerts"] != sorted(row["alerts"], key=str):
            p.append(f"row {i + 1}: alerts is not a sorted list")
    check("J0 steps.json is a JSON array of one object per step with exactly the fields step, run, at, kind, mode, outcome, release, deployed and alerts; outcomes from appendix J's list; alerts sorted", p, f"{len(steps)} rows")
    rows = {r.get("step"): r for r in steps if isinstance(r, dict)}

    rel_dir = d / "releases"
    releases = dict(read_release(x) for x in sorted(rel_dir.iterdir()) if x.is_dir()) if rel_dir.is_dir() else {}
    logs = {t: entries_of(release_log(ck, a)) for t, a in releases.items()}
    by_number = {lg[-1].get("number"): (t, lg) for t, lg in logs.items() if lg}
    labels = {}
    for step, lab in ((1, "N1"), (6, "N2"), (10, "N3")):
        n = J_RELEASES[step][0]
        if n in by_number:
            labels[lab] = by_number[n][1][-1].get("dataset")

    def tag_of(step):
        lab = J_TABLE[step][5]
        ds = labels.get(lab) or {}
        return f"data-{ds.get('snapshot')}-{J_TABLE[step][0]}-1"

    # J1: the rows
    p = []
    for step, (run, at, kind, mode, outcome, rel_lab, dep, alerts) in J_TABLE.items():
        r = rows.get(step)
        if r is None:
            p.append(f"step {step} is missing")
            continue
        w = f"step {step}"
        if r.get("run") != run or isinstance(r.get("run"), bool):
            p.append(f"{w}: run {r.get('run')!r}, appendix J gives the integer {run}")
        for f, want in (("at", at), ("kind", kind), ("mode", mode), ("outcome", outcome)):
            if r.get(f) != want:
                p.append(f"{w}: {f} {r.get(f)!r}, appendix J gives {want!r}")
        want_rel = tag_of(step) if rel_lab else None
        if r.get("release") != want_rel:
            p.append(f"{w}: release {r.get('release')!r}, appendix J gives {want_rel}")
        want_dep = labels.get(dep) if dep else None
        if dep and want_dep is None:
            p.append(f"{w}: the dataset {dep} cannot be read from the releases")
        elif r.get("deployed") != want_dep:
            p.append(f"{w}: deployed {r.get('deployed')}, appendix J gives {dep or 'null'}")
        if r.get("alerts") != alerts:
            p.append(f"{w}: alerts {r.get('alerts')}, appendix J gives {alerts}")
    check("J1 every row has the run, time, kind, mode and outcome of its appendix J row, the tag data-<snapshot>-<run>-1 exactly where the row releases, the production dataset after it and the publication alerts open after it (appendix J)", p)

    # J2: each release, the chain and the release history
    p = []
    for tag, assets in releases.items():
        if not RX_TAG_SITE.fullmatch(tag):
            p.append(f"{tag}: the tag does not pass the 22.8 pattern")
        p += [f"{tag}: {e}" for e in sums_problems(ck, assets)]
        files, fmt, _ = parse_targz(assets.get("artifact.tar.gz") or b"")
        p += [f"{tag}: {e}" for e in fmt]
        doc = release_log(ck, assets)
        if doc is not None:
            p += [f"{tag}: {e}" for e in ck.deployment_log_problems(doc, "deployments.json", False, st)]
        if files is not None and doc is not None:
            nw = entries_of(doc)[-1]
            a_sha, a_n, a_b = artifact_sha(files)
            if nw.get("artifact") != {"files": a_n, "bytes": a_b, "sha256": a_sha}:
                p.append(f"{tag}: the artifact SHA-256 is not its newest entry's")
            if files.get("manifest.json") != assets.get("manifest.json") or files.get(DEPLOY_LOG) != assets.get("deployments.json"):
                p.append(f"{tag}: the manifest or deployments asset differs from its copy in the archive")
            p += [f"{tag}: {e}" for e in closure_problems(ck, files)]
            p += [f"{tag}: {e}" for e in json_problems(ck, st, files)[0]]
    for n in sorted(x for x in by_number if isinstance(x, int)):
        if n > 1 and n - 1 in by_number:
            p += ck.log_chain_problems({"deployments": by_number[n][1]}, {"deployments": by_number[n - 1][1]}, by_number[n][0])
    p += release_history_problems(ck, releases)
    check("J2 every release has the four assets, a tag that passes 22.8, SHA256SUMS, the deterministic archive with econ/ names, its artifact SHA-256, checks 4 and 9; each release's log extends the one before (22.4) and the release history holds (22.7)", p, f"{len(releases)} release(s)")

    # J3: the entries the table gives
    p = []
    for step, (num, trig, post) in J_RELEASES.items():
        if num not in by_number:
            p.append(f"step {step}: no release with entry {num}")
            continue
        tag, lg = by_number[num]
        e = lg[-1]
        if tag != tag_of(step):
            p.append(f"step {step}: entry {num} is release {tag}, appendix J gives {tag_of(step)}")
        if e.get("trigger") != trig or e.get("dataset") != labels.get(J_TABLE[step][5]):
            p.append(f"step {step}: entry {num} trigger {e.get('trigger')} dataset {e.get('dataset')}; appendix J gives {trig} {J_TABLE[step][5]}")
        if e.get("run") != f"pub-{J_TABLE[step][0]}-1" or e.get("published_at") != J_TABLE[step][1] or e.get("site_commit") != ZERO_COMMIT:
            p.append(f"step {step}: entry {num} run {e.get('run')}, published_at {e.get('published_at')}, site_commit {e.get('site_commit')}")
        for ltag, llg in logs.items():
            for x in llg:
                if x.get("number") == num and (x.get("verification") or {}).get("checker") != J_CHECKER:
                    p.append(f"{ltag}: entry {num}'s checker counts are {(x.get('verification') or {}).get('checker')}; appendix J fixes {J_CHECKER} (22.4, I47)")
        for later_n, (ltag, llg) in by_number.items():
            if isinstance(later_n, int) and later_n > num and len(llg) >= num and (llg[num - 1].get("verification") or {}).get("post") != post:
                p.append(f"{ltag}: entry {num}'s post is {(llg[num - 1].get('verification') or {}).get('post')}, appendix J gives {post}")
    if 5 in by_number and 3 in by_number and (by_number[5][1][-1].get("site_commit"), by_number[5][1][-1].get("dataset")) != (by_number[3][1][-1].get("site_commit"), by_number[3][1][-1].get("dataset")):
        p.append("entry 5 (the redeploy) is not entry 3's verified pair (the newest at step 11)")
    extra = sorted(set(by_number) - {v[0] for v in J_RELEASES.values()}, key=str)
    if extra:
        p.append(f"releases with entries {extra}; appendix J makes entries 1 to 5 only")
    check("J3 the entries: 1 (step 1, N1), 2 (step 5, N2, later not-deployed), 3 (step 6, N2, passed), 4 (step 10, N3, failed), 5 (run 1001, a redeploy of entry 3's pair, passed); run pub-<run>-1, published_at the step's time, site commit 40 zeros, checker counts fixed {pass 1, fail 0, skip 0} in every log (appendix J, 22.4, I47)", p, f"{len(by_number)} release(s)")

    # J4: production
    p = []
    try:
        runs = ck.load_strict((d / "production" / "runs.json").read_bytes())
    except Exception as exc:
        runs = []
        p.append(f"production/runs.json: {exc}")
    if not isinstance(runs, list):
        p.append("production/runs.json is not a list")
        runs = []
    for i, r in enumerate(runs):
        if not isinstance(r, dict) or set(r) != {"run", "mode", "dataset", "release", "conclusion", "deployed"}:
            p.append(f"run {i + 1}: not an object with exactly run, mode, dataset, release, conclusion and deployed (appendix J)")
    if len(runs) != len(J_SITE_RUNS):
        p.append(f"{len(runs)} site runs; appendix J's steps give {len(J_SITE_RUNS)} (steps 1, 3, 5, 6, 7, 10, 11, 18 and 19)")
    for r, (step, run, mode, lab, rstep, concl, dep) in zip(runs, J_SITE_RUNS):
        if not isinstance(r, dict):
            continue
        want = {"mode": mode, "dataset": labels.get(lab) if lab else None, "release": tag_of(rstep) if rstep else None, "conclusion": concl, "deployed": dep}
        for f, v in want.items():
            if r.get(f) != v:
                p.append(f"the site run of step {step}: {f} {r.get(f)!r}, appendix J gives {v!r}")
        if r.get("run") != run or isinstance(r.get("run"), bool):
            p.append(f"the site run of step {step}: run {r.get('run')!r}, appendix J gives the integer {run}")
    for i, r in enumerate(runs):
        if not isinstance(r, dict) or r.get("mode") != "data":
            continue
        before = deployed_state(runs[:i])
        lg = logs.get(r.get("release")) or []
        ok, rule = site_deploy_decision("data", r.get("dataset"), before, before, lg)
        if r.get("deployed") is True and not ok:
            p.append(f"site run {i + 1} deployed {r.get('dataset')} over {before}, but 22.8 refuses it ({rule})")
        if i < len(J_SITE_RUNS) and J_SITE_RUNS[i][0] == 7 and ok:
            p.append(f"site run {i + 1} (step 7): 22.8's monotonic rule does not refuse it, appendix J says refused-older")
    if deployed_state(runs) is not None:
        p.append(f"the deployed state after the last run is {deployed_state(runs)}; appendix J's step 19 leaves none")
    if (d / "production" / "econ").exists():
        p.append("production/econ/ exists after steps 18 and 19")
    check("J4 production/runs.json lists the nine site runs of appendix J oldest first, each {run, mode, dataset, release, conclusion, deployed}; every deployed data run passes 22.8's monotonic rule over the deployed state before it and step 7's is refused by it; the deployed state ends none and production/econ/ is absent (appendix J, 22.8)", p, f"{len(runs)} site run(s)")

    # J5: the store's private log and the refused reason
    p = []
    store = Store(d / "store")
    raw = store.read("state/deployments.json")
    priv = []
    if raw is None:
        p.append("store/state/deployments.json is missing (22.4: written by every v0.8 collection run)")
    else:
        doc = ck.load_strict(raw)
        priv = entries_of(doc)
        p += ck.deployment_log_problems(doc, "state/deployments.json", True, st)
        if 5 in by_number:
            want = json.loads(json.dumps(by_number[5][1]))
            want[-1]["verification"]["post"] = "passed"
            if priv != want:
                p.append("the private log is not the newest release's log with its last post fixed passed (22.4; appendix J step 15)")
    for f, data in sorted(store.files("runs").items()):
        try:
            rec = ck.load_strict(data)
        except Exception:
            continue
        if isinstance(rec, dict) and rec.get("started_at") == J_TABLE[13][1]:
            p.append(f"runs/{f} was written at step 13's time: a reason refused by the check writes nothing (21.6)")
    rbs = {}
    for name, data in store.files("root/archive/rollbacks").items():
        try:
            rbs[name] = ck.load_strict(data)
        except Exception:
            pass
    step16 = [r for r in rbs.values() if isinstance(r, dict) and r.get("at") == J_TABLE[16][1]]
    if not step16:
        p.append("no rollback record at step 16's time")
    for r in step16:
        if ck.d6_problems(r.get("reason")):
            p.append(f"step 16's rollback reason fails {ck.d6_problems(r.get('reason'))}")
    check("J5 the store's private log is the newest release's log with its last post fixed (entries 1 passed, 2 not-deployed, 3 passed, 4 failed, 5 passed); step 13 wrote nothing; step 16's rollback record has a reason that passes the check (appendix J, 21.6, 22.4)", p, f"{len(priv)} private entr(y/ies)")

    # J6: D5.5 at step 17
    p = []
    pubs = ck.load_strict(store.read("root/live/status/publications.json") or b"{}") if store.read("root/live/status/publications.json") else {}
    public = set()
    for t, lg in logs.items():
        n = lg[-1].get("number") if lg else None
        post = (priv[n - 1].get("verification") or {}).get("post") if isinstance(n, int) and 0 < n <= len(priv) else None
        if post in ("passed", "failed"):
            files, _, _ = parse_targz(releases[t].get("artifact.tar.gz") or b"")
            public |= {ck.RX_SNAPSHOT_PATH.fullmatch(f).group(1) for f in files or {} if ck.RX_SNAPSHOT_PATH.fullmatch(f)}
    window = {f[:-5] for f in store.files("root/live/snapshots")}
    refused = d55_refused(window, pubs, public)
    n4 = ck.snapshot_id_of(ck.parse_utc(J_TABLE[15][1]))
    if refused != [n4]:
        p.append(f"D5.5 refuses {refused}; appendix J gives exactly step 15's snapshot {n4} (N4): the store starts from appendix G after its step 4, with no withdrawn snapshot in the window (I46)")
    check("J6 D5.5 at step 17: the window's only withdrawn snapshot that has not been public is step 15's (N4), withdrawn by step 16 and in no deployed release, so a publication refuses; the store starts as appendix G after its step 4 (22.3, appendix J, I46)", p, f"refused {refused}")


# ---------------------------------------------------------------------------
# Self-tests of the v0.8 rules (C10 to C18), run with the plain checks
# ---------------------------------------------------------------------------


def section_selftests_v08(ck, st):
    check = ck.check
    sha = lambda c: c * 64  # noqa: E731
    N1 = {"snapshot": "20261124T120000Z", "manifest_sha256": sha("1")}
    N2 = {"snapshot": "20261124T161700Z", "manifest_sha256": sha("2")}
    N3 = {"snapshot": "20261124T172000Z", "manifest_sha256": sha("3")}

    def ent(n, ds, trig, commit, post):
        return {"number": n, "dataset": ds, "trigger": trig, "site_commit": commit, "verification": {"checker": {"pass": 1, "fail": 0, "skip": 0}, "post": post}}

    good = [ent(1, N1, "manual", ZERO_COMMIT, "passed"), ent(2, N2, "manual", ZERO_COMMIT, "not-deployed"), ent(3, N2, "manual", ZERO_COMMIT, "passed"), ent(4, N3, "manual", ZERO_COMMIT, "failed")]
    red = good + [ent(5, N2, "redeploy", ZERO_COMMIT, None)]
    ec = lambda ds: f"{ds['snapshot']}:{ds['manifest_sha256']}"  # noqa: E731
    cases = [
        ("J step 1: the first data deployment, expected none", ("data", N1, "none", None, good[:1]), True),
        ("J step 5: expected_current forced to none while N1 is deployed", ("data", N2, "none", N1, good[:2]), False),
        ("J step 6: expected N1, newer N2", ("data", N2, ec(N1), N1, good[:3]), True),
        ("J step 7: an older release (N1) over N2, a manual entry", ("data", N1, ec(N2), N2, good[:1]), False),
        ("J step 11: the redeploy of entry 3's verified pair over N3", ("data", N2, ec(N3), N3, red), True),
        ("a redeploy of the not-deployed entry 2's pair only", ("data", N2, ec(N3), N3, [good[0], good[1], ent(3, N3, "manual", ZERO_COMMIT, "failed"), ent(4, N2, "redeploy", ZERO_COMMIT, None)]), False),
        ("a redeploy with another site commit", ("data", N2, ec(N3), N3, good + [ent(5, N2, "redeploy", "1" * 40, None)]), False),
        ("a redeploy whose input is not its entry's dataset", ("data", N1, ec(N3), N3, red), False),
        ("the same snapshot again, a manual entry (not newer)", ("data", N2, ec(N2), N2, good[:3]), False),
        ("expected_current with the right snapshot and another SHA-256", ("data", N2, f"{N1['snapshot']}:{sha('9')}", N1, good[:2]), False),
        ("a malformed expected_current", ("data", N2, "N1", N1, good[:2]), False),
        ("J step 3: site carries the deployed dataset (no monotonic rule outside data mode)", ("site", N1, N1, N1, None), True),
        ("site: another deployment between build start and deploy", ("site", N1, N1, N2, None), False),
        ("J step 18: unpublish over N2", ("unpublish", None, N2, N2, None), True),
        ("J step 19: site after an unpublish, the deployed state none", ("site", None, None, None, None), True),
        ("data after an unpublish, expected none", ("data", N1, "none", None, good[:1]), True),
    ]
    p = []
    for label, args, want in cases:
        got, rule = site_deploy_decision(*args)
        if got != want:
            p.append(f"{label}: {'allowed' if got else 'refused'} ({rule}); 22.8 {'allows' if want else 'refuses'} it")
    check("C10 the compare-and-swap and monotonic decision of 22.8: refuse unless the deployed state equals expected_current (in site and unpublish the state read at build start); in data mode refuse unless the input snapshot is newer (the same is not), except a redeploy entry whose dataset and site commit are an earlier entry's with post passed", p, f"{len(cases)} cases")

    S = "20261124T201700Z"
    pubs = {"publications": [{"snapshot": S, "events": [{"at": "2026-11-24T20:17:00Z", "status": "active"}, {"at": "2026-11-24T20:20:00Z", "status": "withdrawn"}]},
                             {"snapshot": N2["snapshot"], "events": [{"at": "2026-11-24T16:17:00Z", "status": "active"}, {"at": "2026-11-24T20:20:00Z", "status": "withdrawn"}]}]}
    cases = [
        ("J step 17: N4 withdrawn, in no deployed release", {S}, set(), [S]),
        ("withdrawn after it was in a deployed release", {S}, {S}, []),
        ("withdrawn, in a deployed release, and another never public", {S, N2["snapshot"]}, {N2["snapshot"]}, [S]),
        ("withdrawn but no longer in the window", set(), set(), []),
        ("in the window, never withdrawn", {"20261124T120000Z"}, set(), []),
    ]
    p = []
    for label, win, public, want in cases:
        got = d55_refused(win, pubs, public)
        if got != want:
            p.append(f"{label}: refuses {got}, D5.5 gives {want}")
    check("C11 D5.5: a publication refuses while its window holds a snapshot whose publication record shows withdrawn and that has not been public (in no earlier release whose entry has post passed or failed) (22.3; PROVISIONAL)", p, f"{len(cases)} cases")

    files = {"manifest.json": b"{}", "objects/effr/2026/" + "a" * 16 + ".json": b"x" * 700, "status/deployments.json": b"{}",
             "series/" + "s" * 95 + "/2026/" + "b" * 16 + ".csv": b"long path\n", "NOTICE.txt": b"n\n"}
    t1, t2 = build_targz(files), build_targz(dict(reversed(list(files.items()))))
    p = []
    if t1 != t2:
        p.append("the checker's writer gives different bytes for the same tree")
    got, prob, info = parse_targz(t1)
    if prob or got != files:
        p.append(f"the deterministic archive is refused: {prob}")

    def mutate(data, fn):
        raw = gzip.decompress(data)
        raw = bytearray(fn(bytearray(raw)))
        co = zlib.compressobj(9, zlib.DEFLATED, -15)
        return data[:10] + co.compress(bytes(raw)) + co.flush() + struct.pack("<II", zlib.crc32(raw) & 0xFFFFFFFF, len(raw) & 0xFFFFFFFF)

    def hdr(fn):
        def go(raw):
            h = raw[0:512]
            fn(h)
            h[148:156] = b" " * 8
            h[148:156] = b"%06o\0 " % sum(h)
            raw[0:512] = h
            return raw
        return go

    faults = [
        ("names without econ/", build_targz(files, ""), "not econ/<path>"),
        ("OS byte 3", t1[:9] + b"\x03" + t1[10:], "OS byte"),
        ("a modification time", mutate(t1, hdr(lambda h: h.__setitem__(slice(136, 148), _octal(1, 12)))), "modification time"),
        ("mode 0755", mutate(t1, hdr(lambda h: h.__setitem__(slice(100, 108), _octal(0o755, 8)))), "mode"),
        ("owner 1000", mutate(t1, hdr(lambda h: h.__setitem__(slice(108, 116), _octal(1000, 8)))), "owner"),
        ("an owner name", mutate(t1, hdr(lambda h: h.__setitem__(slice(265, 269), b"root"))), "owner or group name"),
        ("a symbolic link entry", mutate(t1, hdr(lambda h: h.__setitem__(slice(156, 157), b"2"))), "not a regular file"),
        ("a directory entry", mutate(t1, hdr(lambda h: h.__setitem__(slice(156, 157), b"5"))), "not a regular file"),
        ("a path with ..", mutate(t1, hdr(lambda h: h.__setitem__(slice(0, 18), b"econ/../manifest.j"))), "outside the target"),
        ("GNU magic", mutate(t1, hdr(lambda h: h.__setitem__(slice(257, 265), b"ustar  \0"))), "POSIX ustar"),
        ("a gzip file name", t1[:3] + b"\x08" + t1[4:10] + b"a.tar\0" + t1[10:], "file name"),
        ("a gzip modification time", t1[:4] + struct.pack("<I", 1) + t1[8:], "gzip modification time"),
        ("gzip XFL 0", t1[:8] + b"\x00" + t1[9:], "XFL"),
        ("trailing bytes", t1 + b"\0", "after the gzip member"),
        ("entries out of order", build_targz_unsorted(files), "byte order"),
    ]
    for label, data, want in faults:
        _, prob, _ = parse_targz(data)
        if not any(want in x for x in prob):
            p.append(f"{label}: not refused as '{want}' ({prob})")
    import hashlib
    a1 = artifact_sha(files)
    if a1 != artifact_sha(dict(files, **{"status/deployments.json": b"[1]"})):
        p.append("the artifact SHA-256 changes with status/deployments.json (22.3: it depends on the window alone)")
    if a1[0] == artifact_sha(dict(files, **{"NOTICE.txt": b"m\n"}))[0]:
        p.append("the artifact SHA-256 does not change with a window file")
    want_sha = hashlib.sha256("".join(f"{hashlib.sha256(files[k]).hexdigest()}  {k}\n" for k in sorted(k for k in files if k != DEPLOY_LOG)).encode()).hexdigest()
    if a1 != (want_sha, len(files) - 1, sum(len(v) for k, v in files.items() if k != DEPLOY_LOG)):
        p.append("the artifact SHA-256, count or bytes is not that of the sorted '<sha256>  <path>' lines without the log")
    check("C12 the archive of 22.3: names econ/<path> in byte order, regular files only, mode 0644, owner and group 0 with empty names, mtime 0, gzip with no name, mtime 0, OS byte 255 and XFL 2; each departure is refused; the artifact SHA-256 covers the window alone (22.3, 22.8)", p,
          f"{len(faults)} faults")

    reg = ck.registry_as_of(st.registry, "current")
    v08 = json.loads(json.dumps(reg))
    v08["conventions"] = "v0.8"
    for k, s in v08["sources"].items():
        s["terms_checked"] = ck.TERMS_CHECKED_V08
        if k == ck.NYFED:
            s["terms_url"] = ck.NYFED_TERMS_V08
    p = []
    v07 = ck.registry_as_of(v08, "v0.7")
    v06 = ck.registry_as_of(v08, "v0.6")
    if v07["conventions"] != "v0.7" or v07["sources"][ck.NYFED]["terms_url"] != ck.NYFED_TERMS_V07 or any(s["terms_checked"] != ck.TERMS_CHECKED_V07 for s in v07["sources"].values()):
        p.append("the v0.7 registry is not the v0.8 one with the three substitutions reversed")
    if {k: v for k, v in v06.items() if k != "conventions"} != {k: v for k, v in v07.items() if k != "conventions"} or v06["conventions"] != "v0.6":
        p.append("the v0.6 registry is not the v0.7 one with conventions v0.6")
    if ck.canon_bytes(ck.registry_as_of(v07, "v0.7")) != ck.canon_bytes(v07):
        p.append("deriving v0.7 from the v0.7 registry does not give it back")
    if any(v07[k] != v08[k] for k in v08 if k not in ("conventions", "sources")):
        p.append("the derivation changed a field I7 does not name")
    committed_v07 = ck.registry_versions(st)["v0.7"][0]
    if ck.sha256_hex(ck.canon_bytes(v07)) != committed_v07:
        p.append("the v0.7 registry derived from the v0.8 one differs from the one derived from the committed registry")
    obs = ck.ROOT / "local" / "research" / "p27" / "observe" / "state" / "root" / "archive" / "files" / "snapshots"
    note = ""
    if obs.is_dir():
        hashes = {}
        for x in sorted(obs.glob("*.json")):
            try:
                hashes[x.stem] = (ck.load_strict(x.read_bytes()).get("run") or {}).get("registry_sha256")
            except Exception:
                pass
        known = {ck.registry_versions(st)["v0.7"][0]: "v0.7", ck.registry_versions(st)["v0.6"][0]: "v0.6"}
        bad = [f"{k} {str(h)[:16]}" for k, h in hashes.items() if h not in known]
        if bad:
            p.append(f"accepted snapshots record registries that I7 does not derive: {bad}")
        note = "; accepted snapshots: " + ", ".join(f"{sum(1 for h in hashes.values() if known.get(h) == v)} {v}" for v in ("v0.6", "v0.7"))
    check("C13 I7: the v0.7 registry is the v0.8 one with conventions, the New York Fed terms_url and the three terms_checked reversed, the v0.6 one the v0.7 one with conventions v0.6; idempotent, nothing else touched; the accepted snapshots record derived versions (22.9, I7, 21.1)", p,
          f"v0.7 {committed_v07[:16]}, v0.6 {ck.registry_versions(st)['v0.6'][0][:16]}" + note)

    ok = ["Reviewed the 2019-12-31 debt total against the Treasury page; the source corrected it.", "Rolled back: snapshot 20261124T201700Z carried an unreviewed change.",
          "sha256:" + "a" * 64 + " is the withdrawn candidate", "Q&A follow-up, see ticket 12", "https://radmagelabs.com is the site", "https://radmagelabs.com/ ends here",
          ("word " * 400)[:2000], "x" * 2000, "authorized by the owner on 2026-11-24", "a cookies policy", "bearer of bad news", "version 1.2.3.4a", "the aghp_ prefix",
          "Pin for site release 0.2.0", "e" * 30 + "1"]
    bad = [("", "length"), (("word " * 401)[:2001], "length"), ("Ask radmageirl@radmagelabs.com", "email"), ("See https://github.com/x/y/issues/1", "url-with-path"),
           ("See HTTP://x.org/a", "url-with-path"), ("form ?id=3", "query-string"), ("and &a[b]=1", "query-string"), ("host 192.168.1.10 timed out", "ipv4"),
           ("host 999.1.1.1", "ipv4"), ("owner authorization P56 for the rollback", "header-name"), ("the Set-Cookie value", "header-name"), ("a Cookie", "header-name"),
           ("x-api-key leaked", "header-name"), ("Bearer abc", "bearer"), ("token ghp_abc", "token-shape"), ("(github_pat_x)", "token-shape"),
           ("commit " + "c" * 39 + "1", "long-run"), ("debt-total-2019-12-31-correction-approved", "long-run"), ("key QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo0NTY3", "long-run"),
           ("sha256:" + "a" * 64 + "b1" + "c" * 30, "long-run")]
    p = []
    for text in ok:
        if ck.d6_problems(text):
            p.append(f"{text[:40]!r} refused ({ck.d6_problems(text)})")
    for text, rule in bad:
        got = ck.d6_problems(text)
        if rule not in got:
            p.append(f"{text[:40]!r}: not refused by {rule} ({got})")
    if ck.alert_text_problems("Bearer x") == [] or ck.alert_text_problems("ok text") != []:
        p.append("the 17.8 alert check is not the same check")
    check("C14 the reason check of 22.3 items 1 to 9, which is also the alert check of 17.8: code points; empty or over 2,000 refused; a query string, a URL with a path (any case), an email, an IPv4 address as a whole word, the five header names as whole words in any case, 'Bearer ', a token prefix at a word start, a run of 32 or more of A-Za-z0-9+/=_- holding a digit and a letter after sha256: hashes are replaced", p,
          f"{len(ok)} accepted, {len(bad)} refused")

    p = []
    ser = st.series["debt-total"]
    recs = [{"detected_at": "2027-01-01T03:00:00Z", "snapshot": "20270101T030000Z", "period": "2019-12-31", "field": "value", "before": "1.00", "after": "2.00",
             "kind": "approved-hold", "basis": "approved in review run r8 on 2026-12-31", "release_date": None},
            {"detected_at": "2026-12-30T15:00:00Z", "snapshot": "20261230T150000Z", "period": "2026-11-10", "field": "period", "before": None,
             "after": '{"period":"2026-11-10","value":"1.00"}', "kind": "rollback", "basis": "rolled back to snapshot x in run r9 on 2026-12-30", "release_date": "2026-12-01"}]
    text = ck.revision_csv_bytes(st.registry, ser, 2026, recs).decode("utf-8")
    lines = text.split("\n")
    if not text.endswith("\n") or "\r" in text:
        p.append("the revision CSV does not end with a newline or holds a carriage return")
    if lines[0] != f"# {ser['title']} ({ser['unit_label']}): changes we observed between our collections, 2026":
        p.append(f"first line {lines[0]!r}")
    h = next((i for i, x in enumerate(lines) if x.startswith("# Terms: ")), 0) + 1
    if lines[h] != ",".join(ck.REVISION_CSV_COLUMNS):
        p.append(f"the header is {lines[h]!r}")
    if lines[h + 1] != "2027-01-01T03:00:00Z,20270101T030000Z,2019-12-31,value,1.00,2.00,approved-hold,approved in review run r8 on 2026-12-31,":
        p.append(f"row 1 is {lines[h + 1]!r} (null is an empty field)")
    if lines[h + 2] != '2026-12-30T15:00:00Z,20261230T150000Z,2026-11-10,period,,"{""period"":""2026-11-10"",""value"":""1.00""}",rollback,rolled back to snapshot x in run r9 on 2026-12-30,2026-12-01':
        p.append(f"row 2 is {lines[h + 2]!r} (quoted, inner quotes doubled)")
    nyf = ck.revision_csv_bytes(st.registry, st.series["effr"], 2026, recs[:1]).decode("utf-8").split("\n")
    if "2026" not in nyf[1] or "2027" in nyf[1]:
        p.append(f"{{year}} is not the ET year of the newest detected_at: {nyf[1]!r}")
    reg = st.registry
    nf = ck.notice_file_bytes(reg, "2027-01-01T03:00:00Z").decode("utf-8")
    want = []
    for sid in sorted(reg["sources"]):
        src = reg["sources"][sid]
        want.append(src["publisher"])
        block = []
        for f in ("attribution", "notice"):
            if src.get(f) is None:
                continue
            lines = [src[f].replace("{data_name}", s["data_name"]).replace("{year}", "2026") for s in reg["series"] if s["source"] == sid] if "{data_name}" in src[f] else [src[f].replace("{year}", "2026")]
            for line in lines:
                if line not in block:
                    block.append(line)
        want += block + [src["license"], f"Terms: {src['terms_url']}", ""]
    want.append(ck.NOTICE_STATEMENT)
    if nf != "\n".join(want) + "\n":
        p.append(f"the notice file differs from 22.9's layout at {ck.first_line_difference(nf.encode(), (chr(10).join(want) + chr(10)).encode())}")
    if nf.split("\n")[0] != reg["sources"][sorted(reg["sources"])[0]]["publisher"] or "pending" in nf.lower() or "{" in nf:
        p.append("the notice file does not start with the first source by id, still carries a placeholder, or the pending line")
    if nf.count(reg["sources"]["nyfed-markets"]["notice"].replace("{data_name}", st.series["effr"]["data_name"])) != 1:
        p.append("the New York Fed notice, identical for its two series, is not written once (22.9, I43)")
    check("C15 the revision CSV of 10 and the notice file of 22.9: sources in byte order of their ids, each publisher, attribution, notice (if any), license, Terms: and a blank line, a {data_name} line once per series of the source but an identical filled line once, {year} the ET year of generated_at, then the CC0 statement", p)

    def log(*entries):
        return {"schema": ck.DEPLOYMENTS_ID, "deployments": [json.loads(json.dumps(e)) for e in entries]}

    def full(n, ds, prev, trig="manual", post="passed", commit=ZERO_COMMIT, run=None, at=None):
        run = run or f"pub-{100 + n}-1"
        x, a = run[4:].rsplit("-", 1)
        return {"number": n, "published_at": at or f"2026-11-24T1{n}:00:00Z", "run": run, "trigger": trig, "dataset": ds, "release": f"data-{ds['snapshot']}-{x}-{a}",
                "site_commit": commit, "artifact": {"files": 3, "bytes": 30, "sha256": sha("a")}, "previous": prev,
                "verification": {"checker": {"pass": 9, "fail": 0, "skip": 0}, "post": post}}

    def post(e, v):
        x = json.loads(json.dumps(e))
        x["verification"]["post"] = v
        return x

    e1, e2, e3 = full(1, N1, None), full(2, N2, N1, post="not-deployed"), full(3, N2, N2)
    e4, e5 = full(4, N3, N2, post="failed"), full(5, N2, N3, trig="redeploy", post="passed", at=full(4, N3, N2)["published_at"])
    cases = [
        ("a private log of five entries with not-deployed and a redeploy sharing its starter's time", log(e1, e2, e3, e4, e5), True, True),
        ("a release log, its own entry post null", log(e1, e2, post(e3, None)), False, True),
        ("a release log whose own entry has post set", log(e1, e2), False, False),
        ("a release log with an earlier post null", log(e1, post(e2, None), post(e3, None)), False, False),
        ("a private log whose newest post is null (its run still in progress, 22.4)", log(e1, post(e2, None)), True, True),
        ("a private log with an earlier post null", log(post(e1, None), e2), True, False),
        ("an empty private log (no release yet)", log(), True, True),
        ("an empty release log", log(), False, False),
        ("a number repeated", log(e1, dict(e2, number=1)), True, False),
        ("previous not the dataset before", log(e1, dict(e2, previous=None)), True, False),
        ("a tag that is not data-<snapshot>-<run id>-<attempt>", log(e1, dict(e2, release=f"data-{N1['snapshot']}-102-1")), True, False),
        ("a release used twice", log(e1, dict(e1, number=2, previous=N1)), True, False),
        ("a redeploy of the not-deployed pair", log(e1, e2, dict(e3, trigger="redeploy")), True, False),
        ("a redeploy with another site commit", log(e1, e2, e3, e4, dict(e5, site_commit="1" * 40)), True, False),
        ("a release whose V2b counts hold a FAIL (I47)", log(dict(e1, verification={"checker": {"pass": 9, "fail": 1, "skip": 0}, "post": "passed"})), True, False),
        ("published_at going back", log(e1, dict(e2, published_at="2026-11-24T10:00:00Z")), True, False),
        ("post 'success'", log(e1, post(e2, "success")), True, False),
    ]
    p = []
    for label, doc, private, want in cases:
        got = ck.deployment_log_problems(doc, "log", private, st)
        if (not got) != want:
            p.append(f"{label}: {'accepted' if not got else 'refused: ' + got[0]}; 22.4 {'accepts' if want else 'refuses'} it")
    check("C16 the deployment log of 22.4: numbered 1, 2, ... (never repeated), published_at oldest first, previous the dataset before, release data-<snapshot>-<run id>-<attempt> with run pub-<run id>-<attempt>, a release once, none after a V2b FAIL (the counts are V2b's, I47), post passed, failed or not-deployed once fixed and null only on a release's own entry (never in the private log), a redeploy only of a verified pair", p, f"{len(cases)} cases")

    p = []
    r1, r2, r3 = log(post(e1, None)), log(e1, post(e2, None)), log(e1, e2, post(e3, None))
    chain = [("the first release", r1, None, True), ("the second extends the first, its post fixed passed", r2, r1, True), ("the third", r3, r2, True),
             ("a first release with two entries", r2, None, False), ("an entry dropped", log(e1, post(e3, None)), r2, False),
             ("the earlier release's post left null", log(post(e1, None), post(e2, None)), r1, False), ("an earlier entry changed", log(dict(e1, site_commit="1" * 40), post(e2, None)), r1, False),
             ("two entries added", log(e1, e2, post(e3, None)), r1, False), ("an earlier fixed post changed", log(e1, post(e2, "passed"), e3, post(e4, None)), r3, False)]
    for label, new, old, want in chain:
        got = ck.log_chain_problems(new, old)
        if (not got) != want:
            p.append(f"chain, {label}: {'accepted' if not got else 'refused: ' + got[0]}; 22.4 {'accepts' if want else 'refuses'} it")

    def rel(doc):
        assets = {"artifact.tar.gz": b"a", "manifest.json": b"m", "deployments.json": ck.canon_bytes(doc)}
        assets["SHA256SUMS"] = "".join(f"{ck.sha256_hex(assets[k])}  {k}\n" for k in sorted(assets)).encode()
        return assets

    hist = {e1["release"]: rel(r1), e2["release"]: rel(r2), e3["release"]: rel(r3)}
    hcases = [("three releases", hist, True), ("a release deleted", {k: v for k, v in hist.items() if k != e2["release"]}, False),
              ("an unnamed release", dict(hist, **{"data-20261124T000000Z-9-1": rel(log(full(1, {"snapshot": "20261124T000000Z", "manifest_sha256": sha("0")}, None, run="pub-9-1", post=None)))}), False),
              ("an asset missing", dict(hist, **{e1["release"]: {k: v for k, v in rel(r1).items() if k != "manifest.json"}}), False),
              ("a release's log rewritten", dict(hist, **{e1["release"]: rel(log(post(e1, "passed")))}), False),
              ("the newest SHA256SUMS wrong", dict(hist, **{e3["release"]: dict(rel(r3), SHA256SUMS=b"x\n")}), False)]
    no3 = {k: v for k, v in hist.items() if k != e3["release"]}
    hcases += [("the newest release deleted, releases alone (22.7: they cannot show it)", no3, True, None),
               ("the newest release deleted, with the deployed log naming it", no3, False, rel(r3)["deployments.json"]),
               ("the deployed log of the newest release", hist, True, rel(r3)["deployments.json"])]
    for label, rels, want, *dep in hcases:
        got = release_history_problems(ck, rels, dep[0] if dep else None)
        if (not got) != want:
            p.append(f"history, {label}: {'accepted' if not got else 'refused: ' + got[0]}; 22.7 {'accepts' if want else 'refuses'} it")
    check("C17 the chain of releases (22.4: the newest earlier release's log, its own last post fixed, plus one entry numbered one higher) and the release history the watcher checks from public data (22.7: every named release exists with its four assets, every release is named, the newest SHA256SUMS, each log the newest up to its own entry with its post null)", p,
          f"{len(chain)} chain and {len(hcases)} history cases")

    p = []
    names = [("pages data 20261124T120000Z " + sha("1") + " data-20261124T120000Z-1-1", ("data", N1, "data-20261124T120000Z-1-1")),
             ("pages unpublish none none none", ("unpublish", None, None)), ("pages site none none none", ("site", None, None)),
             ("pages data 20261124T120000Z none data-20261124T120000Z-1-1", None), ("pages data 20261124T120000Z data-20261124T120000Z-1-1", None),
             ("pages deploy none none none", None)]
    for name, want in names:
        if parse_run_name(name) != want:
            p.append(f"run name {name!r}: read as {parse_run_name(name)}, 22.8 gives {want}")
    runs = [{"conclusion": "success", "deployed": True, "dataset": N1}, {"conclusion": "failure", "deployed": False, "dataset": N2},
            {"conclusion": "success", "deployed": False, "dataset": N3}]
    if deployed_state(runs) != N1:
        p.append("a refused run or a dry run (deploy skipped) changed the deployed state")
    if deployed_state(runs + [{"conclusion": "success", "deployed": True, "dataset": None}]) is not None:
        p.append("after an unpublish the deployed state is not none")
    if deployed_state([]) is not None:
        p.append("with no run the deployed state is not none")
    check("C18 the site build's deployed state (22.8): the newest run that concluded success and did not skip its deploy, named 'pages <mode> <snapshot or none> <manifest_sha256 or none> <release or none>'; none after an unpublish or when no run carried data", p, f"{len(names)} names")


def build_targz_unsorted(files):
    """A fault for C12: the entries in reverse byte order."""
    raw = b"".join(build_tar({k: files[k]})[:-1024] for k in sorted(files, key=lambda x: x.encode("utf-8"), reverse=True)) + b"\0" * 1024
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    return b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff" + co.compress(raw) + co.flush() + struct.pack("<II", zlib.crc32(raw) & 0xFFFFFFFF, len(raw))
