"""State store mode and appendix G scenario mode of the independent checker (DATA_CONVENTIONS v0.8).

    python -I tests/datacheck/check_p22.py --state <store dir>
    python -I tests/datacheck/check_p22.py --state-scenario <dir>

Loaded by check_p22.py by its path; it is given the checker module (`ck`) and uses its readers,
canonical form, schema validator, calendar and root checks. Written from the text of sections 20.1
to 20.3, 21.1 to 21.5 and appendix G, the schemas and the registry only; it shares no code with the
pipeline. Every file of a store is untrusted data: parsed, never executed. A store is read only;
nothing is written.

Two layouts (20.3, 21.2), told apart by state/STATE.json:
  rmf.econ.state/1  the Stage B layout of 20.1 and 20.3: state/ and unpublished/<run id>/ (checks SB1 to SB9)
  rmf.econ.state/2  the v0.7 layout of 21.2 after the baseline promotion (checks ST1 to ST20; v0.8 adds
                    state/deployments.json, the private deployment log of 22.4, checked by ST20)
In both, the root is then verified by the live root mode of 21.3 (the T checks, appendix B excluded).
The scenario mode (checks G0 to G12) reads <dir>/steps.json and <dir>/store against appendix G and
then runs the state mode on the store.

"reading:" in a comment marks a point the text does not state outright; the report lists them.
"""

import datetime as dt
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

TOP_V07 = {".gitattributes", "state", "root", "runs", "responses", "unpublished"}  # 21.2, the table
STATE_FIXED = ("review-queue.json", "publications.json", "pins.json", "alerts.json", "collector.json")  # 17.1
RX_BODY = re.compile(r"responses/([0-9a-f]{2})/([0-9a-f]{64})\.bin", re.ASCII)
RX_STAGE_B_RESPONSE = re.compile(r"(\d+)-([A-Za-z0-9](?:[A-Za-z0-9.-]{0,252}))\.(bin|json)", re.ASCII)
RX_REVIEW_NAME = re.compile(r"[a-z0-9-]+/[0-9a-f]{16}-[a-z]+-(\d{8}T\d{6}Z)\.json", re.ASCII)
RX_ROLLBACK_NAME = re.compile(r"(\d{8}T\d{6}Z)\.json", re.ASCII)
OUTCOMES_QUIET = ("nothing-due", "no-change", "gate-failed", "failed", "refused")  # nothing accepted (21.3); nothing under root/
OP_TRIGGER = {"review": "review", "rollback": "rollback", "restore": "restore"}  # 21.4 operation to the run record's trigger (14.1)
NO_RUN_RECORD_OPS = ("promote", "pin", "unpin")  # 21.4: no pipeline step, no run record (v0.8 I45 adds pin and unpin)


class Store:
    """Read-only view of a state store folder. A top-level .git (a clone) is not part of it."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        self._files = None
        self._bytes, self._json = {}, {}

    def files(self):
        if self._files is None:
            out = []
            if self.path.is_dir():
                for p in self.path.rglob("*"):
                    rel = p.relative_to(self.path).as_posix()
                    if rel == ".git" or rel.startswith(".git/"):
                        continue
                    if p.is_file():
                        out.append(rel)
            self._files = sorted(out)
        return self._files

    def under(self, prefix):
        return [f for f in self.files() if f.startswith(prefix)]

    def _set(self):
        if not hasattr(self, "_fileset"):
            self._fileset = set(self.files())
        return self._fileset

    def read(self, rel):
        if rel not in self._bytes:
            self._bytes[rel] = (self.path / rel).read_bytes() if rel in self._set() else None
        return self._bytes[rel]

    def load(self, ck, rel):
        if rel not in self._json:
            data = self.read(rel)
            if data is None:
                self._json[rel] = (None, "missing")
            else:
                try:
                    self._json[rel] = (ck.load_strict(data), None)
                except Exception as exc:
                    self._json[rel] = (None, f"{type(exc).__name__}: {exc}")
        return self._json[rel]

    def size(self, rel):
        data = self.read(rel)
        return len(data) if data is not None else 0


def _mismatch(ck, data, want_sha, want_bytes=None):
    """'' when data matches, else the problem, with the 21.2 diagnosis when it applies."""
    if data is None:
        return "missing"
    got = ck.sha256_hex(data)
    if got != want_sha or (want_bytes is not None and len(data) != want_bytes):
        return f"{len(data)} bytes, sha256 {got[:16]}; recorded {want_bytes} bytes, sha256 {str(want_sha)[:16]}" + ck.hash_mismatch_note(data, want_sha)
    return ""


def _canonical(ck, data, value):
    return ck.canonical_problem(data, value)


def _schema(ck, st, name, value):
    try:
        return ck.schema_errors(value, st.schemas[name])
    except ck.SchemaKeywordError as exc:
        return [f"validator cannot evaluate: {exc}"]


def _run_item_errors(ck, st, rec):
    """A run record against the run item of rmf.econ.runs/2 (20.3)."""
    sid = st.schemas["runs"].get("properties", {}).get("schema", {}).get("const", "rmf.econ.runs/2")
    return _schema(ck, st, "runs", {"schema": sid, "runs": [rec]})


def _state_file_problems(ck, st, store, rel):
    """20.3, 17.1: a state file: canonical JSON and its schema (alerts, pins, publications, review
    queue; a run record against the run item of runs/2); collector.json has no schema file."""
    v, err = store.load(ck, rel)
    if err:
        return [f"{rel}: {err}"]
    p = []
    why = _canonical(ck, store.read(rel), v)
    if why:
        p.append(f"{rel}: {why} (17.1: state files are canonical JSON)")
    name = rel.split("state/", 1)[1]
    kind = {"alerts.json": "alerts", "pins.json": "pins", "publications.json": "publications", "review-queue.json": "review-queue"}.get(name)
    if kind:
        p += [f"{rel}: {e}" for e in _schema(ck, st, kind, v)[:3]]
        if kind == "review-queue" and isinstance(v, dict) and v.get("schema") != ck.SCHEMA_IDS["review-queue"]:
            p.append(f"{rel}: schema {v.get('schema')!r}, 17.5 gives {ck.SCHEMA_IDS['review-queue']}")
    elif name.startswith("run-records/"):
        if not isinstance(v, dict):
            p.append(f"{rel}: not an object")
        else:
            p += [f"{rel}: {e} (runs/2 run item)" for e in _run_item_errors(ck, st, v)[:3]]
            if name != f"run-records/{v.get('id')}.json":
                p.append(f"{rel}: the record's id is {v.get('id')!r}")
    elif name == "accepted.json":
        p += [f"{rel}: {e}" for e in _schema(ck, st, "accepted", v)[:4]]
    elif name == "deployments.json":
        # 21.2, 22.4 (v0.8): the private deployment log, rmf.econ.deployments/1 (shape built from the text)
        try:
            p += [f"{rel}: {e}" for e in ck.schema_errors(v, st.v08_schemas["deployments"])[:4]]
        except ck.SchemaKeywordError as exc:
            p.append(f"{rel}: validator cannot evaluate: {exc}")
    elif name != "collector.json":
        p.append(f"{rel}: not a state file of 17.1 (review-queue, publications, pins, alerts, collector, run-records/<run id>.json), nor accepted.json, nor deployments.json (v0.8)")
    return p


def _cr_problems(ck, store, files, recorded=None):
    """21.2 (F2): no carriage return and no byte order mark in a file the pipeline writes; the
    'line endings converted' diagnosis when the file would match its recorded hash (or its
    canonical form) after CRLF is turned back into LF."""
    recorded = recorded or {}
    p = []
    for f in files:
        data = store.read(f)
        if data is None:
            continue
        if data.startswith(b"\xef\xbb\xbf"):
            p.append(f"{f}: starts with a byte order mark (21.2)")
        if b"\r" not in data:
            continue
        conv = data.replace(b"\r\n", b"\n")
        named = False
        if b"\r" not in conv:
            if f in recorded:
                named = ck.sha256_hex(conv) == recorded[f]
            elif f == ".gitattributes":
                named = conv == ck.GITATTRIBUTES
            elif f.endswith(".json"):
                try:
                    named = ck.canonical_problem(conv, ck.load_strict(conv)) is None
                except Exception:
                    named = False
            elif f.endswith(".csv"):
                named = True
        if named:
            p.append(f"{f}: line endings converted (a checkout made with conversion; clone with core.autocrlf=false, 21.2)")
        else:
            n_cr = data.count(b"\r")
            p.append(f"{f}: {n_cr} carriage return(s) in a file the pipeline writes (21.2: LF only)")
    return p


def _registry_hosts(st):
    """Source host to its request group (17.3), and group to host. Each source has one group."""
    grp = st_groups(st)
    host_group, group_host = {}, {}
    for s in st.registry.get("series", []):
        host = st.registry["sources"][s["source"]]["host"]
        host_group.setdefault(host, grp[s["id"]])
        group_host.setdefault(grp[s["id"]], host)
    return host_group, group_host


def st_groups(st):
    order = [s["id"] for s in st.registry.get("series", [])]
    out = {}
    for s in st.registry.get("series", []):
        members = {s["id"], *s["fetch"].get("shared_with", [])}
        out[s["id"]] = min(members, key=lambda x: order.index(x) if x in order else len(order))
    return out


def _group_earliest(st, g):
    grp = st_groups(st)
    return min(st.series[s]["earliest"] for s in st.series if grp[s] == g)


def request_start(url):
    """The {start} a request URL carries (18): EFFR startDate (and endDate), Debt to the Penny
    filter=record_date:gte:<start>; None for H.6."""
    q = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
    if "startDate" in q:
        return q["startDate"], q.get("endDate")
    mt = re.fullmatch(r"record_date:gte:(\d{4}-\d{2}-\d{2})", q.get("filter", ""))
    if mt:
        return mt.group(1), None
    return None, None


def _ctx_for(ck, st, rv, legacy_until, legacy_ff=None):
    return ck.root_context(st, rv, legacy_until, live=True, quiet=True, legacy_ff=legacy_ff)


# ---------------------------------------------------------------------------
# The Stage B layout (20.1, 20.3): SB1 to SB9
# ---------------------------------------------------------------------------


def run_stage_b(ck, st, store, desc):
    check = ck.check
    p = []
    data = store.read("state/STATE.json")
    p += [f"state/STATE.json: {e}" for e in _schema(ck, st, "state", desc)[:4]]
    why = _canonical(ck, data, desc)
    if why:
        p.append(f"state/STATE.json: {why} (21.4: canonical JSON)")
    root = desc.get("root")
    run_id = root.split("/", 1)[1] if isinstance(root, str) and root.startswith("unpublished/") else None
    if root is None:
        p.append("root is null; 20.1 commits the whole root of every run, so a Stage B STATE.json names it")
    elif run_id is None or not any(f.startswith(root + "/") for f in store.files()):
        p.append(f"root {root!r} names no folder of the store")
    rrec_path = f"{root}/archive/state/run-records/{run_id}.json" if run_id else None
    rrec, rerr = store.load(ck, rrec_path) if rrec_path else (None, "no root")
    if run_id and desc.get("run") != run_id:
        p.append(f"run {desc.get('run')!r} is not the run of the root it names {run_id!r} (20.3: the run that wrote it, whose root is the newest)")
    if isinstance(rrec, dict) and ck.is_time(rrec.get("ended_at")) and ck.is_time(desc.get("written_at")) and desc["written_at"] < rrec["ended_at"]:
        p.append(f"written_at {desc['written_at']} is before the run's end {rrec['ended_at']} (reading: STATE.json is written after the run)")
    check("SB1 state/STATE.json is rmf.econ.state/1 (canonical JSON) naming the newest root unpublished/<run id> of the run that wrote it (20.1, 20.3)", p,
          f"root {root}, run {desc.get('run')}")

    # SB2: every state file listed with its SHA-256 and bytes, none unlisted (20.3)
    p, listed = [], {}
    files = desc.get("files") if isinstance(desc.get("files"), list) else []
    for e in files:
        if not isinstance(e, dict):
            continue
        path = e.get("path")
        if path in listed:
            p.append(f"{path} listed twice")
        listed[path] = e
        if path == "state/STATE.json":
            p.append("state/STATE.json lists itself (reading: its own hash cannot be in it; 21.2 states it for state/2)")
            continue
        why = _mismatch(ck, store.read(path), e.get("sha256"), e.get("bytes"))
        if why:
            p.append(f"{path}: {why}")
    actual = [f for f in store.under("state/") if f != "state/STATE.json"]
    for f in actual:
        if f not in listed:
            p.append(f"{f} is not listed (20.3: no file unlisted)")
    check("SB2 every file under state/ but STATE.json is listed once in STATE.json files with its SHA-256 and byte count, and matches (line endings diagnosis of 21.2); none is unlisted (20.3)", p,
          f"{len(listed)} listed, {len(actual)} present")

    # SB3: state files against their schemas (20.3)
    p = []
    for f in actual:
        p += _state_file_problems(ck, st, store, f)
    for f in STATE_FIXED:
        if f"state/{f}" not in actual:
            p.append(f"state/{f} missing (17.1)")
    check("SB3 each state file validates: alerts/1, pins/1, publications/1, review-queue/4, each run record against the run item of runs/2, and every one canonical JSON (17.1, 20.3)", p, f"{len(actual)} files")

    # SB4: state/ is the root's archive/state/, byte for byte (20.1)
    p = []
    if run_id:
        ast = {f[len(root) + len("/archive/state/"):] for f in store.under(f"{root}/archive/state/")}
        stf = {f[len("state/"):] for f in actual}
        for f in sorted(stf - ast):
            p.append(f"state/{f} is not in {root}/archive/state/")
        for f in sorted(ast - stf):
            p.append(f"{root}/archive/state/{f} is not in state/")
        for f in sorted(ast & stf):
            if store.read(f"state/{f}") != store.read(f"{root}/archive/state/{f}"):
                p.append(f"state/{f} differs from {root}/archive/state/{f}")
    check("SB4 state/ holds exactly the root's archive/state/ files, byte for byte (20.1)", p)

    # SB5: manifest_sha256
    p = []
    mdata = store.read(f"{root}/live/manifest.json") if run_id else None
    if desc.get("manifest_sha256") is None:
        if mdata is not None:
            p.append("manifest_sha256 is null although the root has live/manifest.json")
    else:
        why = _mismatch(ck, mdata, desc.get("manifest_sha256"))
        if why:
            p.append(f"{root}/live/manifest.json: {why}")
    check("SB5 manifest_sha256 is the SHA-256 of the named root's live/manifest.json, or null when it has none (20.3)", p)

    # SB6: layout (20.1)
    p, extra_notes = [], []
    tops = {f.split("/", 1)[0] for f in store.files()}
    for t in sorted(tops - {"state", "unpublished"}):
        p.append(f"{t} at the top of the store; the Stage B layout has state/ and unpublished/ only (20.1)")
    folders = sorted({f.split("/")[1] for f in store.under("unpublished/") if f.count("/") >= 2})
    for x in folders:
        names = {f.split("/")[2] for f in store.under(f"unpublished/{x}/")}
        for need in ("live", "archive", "responses"):
            if need not in names:
                p.append(f"unpublished/{x}/{need}/ missing (20.1: the whole root plus responses/)")
        other = sorted(names - {"live", "archive", "responses"})
        if other:
            extra_notes.append(f"unpublished/{x}/ also holds {', '.join(other)} (not named by 20.1; reading: allowed)")
        if store.under(f"unpublished/{x}/staging/"):
            p.append(f"unpublished/{x}/staging/ is not empty (17.1)")
    check("SB6 the store holds state/ and unpublished/<run id>/ folders, each with live/, archive/ and responses/ (20.1)", p, "; ".join(extra_notes) or f"{len(folders)} folder(s)")

    # SB7: response records (20.2, v0.7 F1) and the requests of the run
    p, n_resp = [], 0
    host_group, group_host = _registry_hosts(st)
    for x in folders:
        recs = {}
        for f in store.under(f"unpublished/{x}/responses/"):
            name = f.rsplit("/", 1)[1]
            mt = RX_STAGE_B_RESPONSE.fullmatch(name)
            if not mt:
                p.append(f"{f}: not <n>-<host>.bin or <n>-<host>.json (20.2)")
                continue
            recs.setdefault((int(mt.group(1)), mt.group(2)), {})[mt.group(3)] = f[:-len(mt.group(3)) - 1]  # reading: <n> may be zero-padded (Stage B wrote 001)
        rr, _ = store.load(ck, f"unpublished/{x}/archive/state/run-records/{x}.json")
        started = rr.get("started_at") if isinstance(rr, dict) else None
        ns = sorted(n for n, _ in recs)
        if ns != list(range(1, len(ns) + 1)):
            p.append(f"unpublished/{x}/responses: request numbers {ns[:6]} are not 1 to {len(ns)}")
        prev_t = None
        hosts = set()
        for (n, host), kinds in sorted(recs.items()):
            n_resp += 1
            if set(kinds) != {"bin", "json"} or kinds["bin"] != kinds["json"]:
                p.append(f"{next(iter(kinds.values()))}: not a .bin and .json pair of one name (20.2 saves both)")
                continue
            base = kinds["json"]
            rec, err = store.load(ck, base + ".json")
            if err:
                p.append(f"{base}.json: {err}")
                continue
            for why in ck.response_record_problems(rec, store.read(base + ".bin"), n, host):
                p.append(f"{base}.json: {why}")
            hosts.add(host)
            if host not in host_group:
                p.append(f"{base}: {host} is not a registered source host (18)")
            t = rec.get("requested_at") if isinstance(rec, dict) else None
            if ck.is_time(t) and ck.is_time(started) and t < started:
                p.append(f"{base}: requested_at {t} before the run started {started} (reading)")
            if ck.is_time(t) and prev_t and t < prev_t:
                p.append(f"{base}: requested_at {t} before the request before it ({prev_t})")
            prev_t = t if ck.is_time(t) else prev_t
        if isinstance(rr, dict) and rr.get("series"):
            want = {group_host[g] for g in ck.requested_groups(st, rr)}
            if want != hosts:
                p.append(f"unpublished/{x}: requests to {sorted(hosts)}, the run record's outcomes request the groups of {sorted(want)}")
    check("SB7 every saved response has its record with exactly the twelve fields of 20.2 (v0.7, F1), n and host those of its file name, bytes and sha256 those of its body; requests numbered from 1, in time order, to the registered hosts of the groups the run requested (18, 20.2)", p,
          f"{n_resp} response(s)")

    # SB8: line endings (21.2 applies to every text file the pipeline writes; bodies exempt)
    targets = [f for f in store.files() if not (f.startswith("unpublished/") and "/responses/" in f and f.endswith(".bin"))]
    recorded = {e.get("path"): e.get("sha256") for e in files if isinstance(e, dict)}
    p = _cr_problems(ck, store, targets, recorded)
    check("SB8 no file of the store but the response bodies holds a carriage return or a byte order mark; a file that would match its record after CRLF is turned back into LF is named 'line endings converted' (21.2)", p,
          f"{len(targets)} files")

    # SB9: the named root in live mode (21.1, 21.3)
    if run_id:
        print(f"check_state.py: the named root {root} in live mode (21.3)")
        ck.section_root(st, store.path / root, live=True)
    else:
        check("SB9 the named root passes the live root mode (21.1, 21.3)", ["no root named"])
    return {"layout": "stage-b", "root": root, "run": run_id}


# ---------------------------------------------------------------------------
# The v0.7 layout (21.1, 21.2, 21.4): ST1 to ST19
# ---------------------------------------------------------------------------


def _time_of_name(stamp):
    return f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}Z"


def attribute_root(ck, ctx, store):
    """For every file under root/ (as the store holds it now), the time (a run's now) at which it
    was first written, as far as the store tells: an archived manifest at its generated_at, a
    snapshot at its created_at, an object, CSV or log version at the first snapshot or manifest
    that names it, a held or locked candidate when first held, frozen or locked by a rollback, a
    review or rollback record at the time in its name. Live files take the time of their archive
    copy. Returns {store path: time or None}."""
    first = {}

    def note(path, t):
        if ck.is_time(t) and (path not in first or t < first[path]):
            first[path] = t

    for sid_, s in ctx.snaps.items():
        t = s.get("created_at")
        note(f"snapshots/{sid_}.json", t)
        for path in ck.rx_snapshot_files(s):
            note(path, t)
        for h in s.get("holds", []) or []:
            sha = (h.get("candidate") or {}).get("sha256")
            note(f"holds:{h.get('series')}/{str(sha)[:16]}.json", t)
        for e in s.get("frozen", []) or []:
            note(f"holds:{e.get('series')}/{str(e.get('candidate_sha256'))[:16]}.json", t)
    for name, m, err in ctx.arch_manifests:
        if err:
            continue
        t = m.get("generated_at")
        note(f"manifests:{name}", t)
        for path in ck.rx_manifest_files(m):
            note(path, t)
    rv = ctx.rv
    for f in rv.files(rv.rollbacks):
        mt = RX_ROLLBACK_NAME.fullmatch(f)
        if mt:
            t = _time_of_name(mt.group(1))
            note(f"rollbacks:{f}", t)
            v, err = rv.load(rv.rollbacks, f)
            for lk in (v.get("locks") or []) if isinstance(v, dict) else []:
                if isinstance(lk, dict):
                    note(f"holds:{lk.get('series')}/{str(lk.get('candidate_sha256'))[:16]}.json", t)
    out = {}
    for f in store.under("root/"):
        rel = f[len("root/"):]
        if rel.startswith("archive/files/"):
            out[f] = first.get(rel[len("archive/files/"):])
        elif rel.startswith("archive/manifests/"):
            out[f] = first.get("manifests:" + rel[len("archive/manifests/"):])
        elif rel.startswith("archive/holds/"):
            out[f] = first.get("holds:" + rel[len("archive/holds/"):])
        elif rel.startswith("archive/reviews/"):
            mt = RX_REVIEW_NAME.fullmatch(rel[len("archive/reviews/"):])
            out[f] = _time_of_name(mt.group(1)) if mt else None
        elif rel.startswith("archive/rollbacks/"):
            out[f] = first.get("rollbacks:" + rel[len("archive/rollbacks/"):])
        elif rel.startswith("live/"):
            out[f] = first.get(rel[len("live/"):]) if rel not in ("live/manifest.json", "live/status/runs.json", "live/status/publications.json") else None
        else:
            out[f] = None
    return out


def freshness_of(ck, st, manifest, snapshot, now):
    """21.4 (as corrected by the coordinator): per registered series in registry order, the status
    (held, frozen, not-yet-published as the accepted manifest gives them; otherwise stale when now
    is at or after the series' staleness time, the registry staleness rule measured from the 14.2
    deadline of its next unseen period; the FOMC target, which follows the EFFR, exactly when the
    EFFR's staleness time has passed), last_period and deadline (null without one)."""
    out, thr_of, dl_of = [], {}, {}
    sstate = (snapshot or {}).get("series") or {}
    for s in st.registry.get("series", []):
        sid = s["id"]
        summ = (manifest.get("series") or {}).get(sid) or {}
        lp = summ.get("last_period")
        marker = (sstate.get(sid) or {}).get("source_marker")
        dl, _ = ck.deadline_for(st, sid, lp, marker) if lp is not None else (None, "not yet published")
        dl_of[sid] = dl
        thr_of[sid] = ck.stale_threshold(st, sid, dl) if dl is not None else None
    for s in st.registry.get("series", []):
        sid = s["id"]
        summ = (manifest.get("series") or {}).get(sid) or {}
        mstat = summ.get("status")
        if mstat in ("held", "frozen", "not-yet-published"):
            status = mstat
        elif "follows" in s["staleness"]:
            thr = thr_of.get(s["staleness"]["follows"])
            status = "stale" if thr is not None and now >= thr else "fresh"  # reading: "has passed" as "at or after", like the series it follows
        else:
            thr = thr_of.get(sid)
            status = "stale" if thr is not None and now >= thr else "fresh"
        out.append({"series": sid, "status": status, "last_period": summ.get("last_period"),
                    "deadline": ck.fmt_utc(dl_of[sid]) if dl_of[sid] is not None else None})
    return out


def expected_next_of(ck, st, manifest, snapshot):
    """21.4 and 14.2, 17.3: the earliest deadline among published series neither held nor frozen;
    None when there is none (the caller accepts the run's now or the manifest's generated_at)."""
    sstate = (snapshot or {}).get("series") or {}
    best = None
    for s in st.registry.get("series", []):
        sid = s["id"]
        summ = (manifest.get("series") or {}).get(sid) or {}
        if summ.get("status") in ("held", "frozen", "not-yet-published") or "follows" in s["staleness"] or summ.get("last_period") is None:
            continue
        dl, _ = ck.deadline_for(st, sid, summ["last_period"], (sstate.get(sid) or {}).get("source_marker"))
        if dl is not None and (best is None or dl < best):
            best = dl
    return best


def run_v07(ck, st, store, desc):
    check = ck.check
    info = {"layout": "v0.7"}
    files = store.files()
    fileset = set(files)

    # ST1: .gitattributes (21.2)
    ga = store.read(".gitattributes")
    if ga is None:
        p = [".gitattributes is missing (21.2: the read refuses to run)"]
    elif ga != ck.GITATTRIBUTES:
        p = [f".gitattributes is {ga!r}, not exactly the 8 bytes {ck.GITATTRIBUTES!r}" + (" (line endings converted, 21.2)" if ga.replace(b"\r\n", b"\n") == ck.GITATTRIBUTES else "")]
    else:
        p = []
    check("ST1 .gitattributes is exactly the 8 bytes '* -text' and a line feed (21.2)", p)

    # ST2: layout (21.2)
    p, notes = [], []
    tops = {f.split("/", 1)[0] for f in files}
    for t in sorted(tops - TOP_V07):
        p.append(f"{t} at the top of the store; 21.2 lists .gitattributes, state/, root/, runs/, responses/ and unpublished/ only")
    for need in ("state/STATE.json", "state/accepted.json", "root/live/manifest.json"):
        if need not in fileset:
            p.append(f"{need} missing (21.2)")
    if store.under("root/archive/state/"):
        p.append("root/archive/state/ exists; 21.2 keeps the state files in state/ (the root without archive/state/)")
    if store.under("root/staging/"):
        p.append("root/staging/ exists; 21.2 keeps the root without staging/")
    for f in store.under("root/"):
        if f.split("/")[1] not in ("live", "archive"):
            p.append(f"{f}: root/ holds live/ and archive/ only (21.2)")
    for f in store.under("runs/"):
        if not re.fullmatch(r"runs/[A-Za-z0-9._-]{1,80}\.json", f):
            p.append(f"{f}: not runs/<run id>.json (21.2)")
    folders = sorted({f.split("/")[1] for f in store.under("unpublished/") if f.count("/") >= 2})
    notes.append(f"unpublished/: {', '.join(folders) or 'none'}")
    check("ST2 the store holds .gitattributes, state/ (STATE.json, accepted.json, the state files), root/ (live/ and archive/, without archive/state/ or staging/), runs/<run id>.json, responses/ and unpublished/ only (21.2)", p, "; ".join(notes))

    # ST3: STATE.json (21.2)
    p = [f"state/STATE.json: {e}" for e in _schema(ck, st, "state-v2", desc)[:4]]
    why = _canonical(ck, store.read("state/STATE.json"), desc)
    if why:
        p.append(f"state/STATE.json: {why} (21.4: canonical JSON)")
    check("ST3 state/STATE.json validates against rmf.econ.state/2 (root always root) and is canonical JSON (21.2, 21.4)", p)

    # ST4: the files list (21.2)
    p, listed = [], {}
    flist = desc.get("files") if isinstance(desc.get("files"), list) else []
    paths = [e.get("path") for e in flist if isinstance(e, dict)]
    if paths != sorted(paths, key=str):
        p.append("files are not sorted by path (21.2)")
    for e in flist:
        if not isinstance(e, dict):
            continue
        path = e.get("path")
        if path in listed:
            p.append(f"{path} listed twice")
        listed[path] = e
        if path == "state/STATE.json":
            p.append("state/STATE.json lists itself (21.2: it is not listed)")
            continue
        if not (isinstance(path, str) and path.startswith("state/") and path in fileset):
            p.append(f"{path!r} is listed but is not a file under state/")
            continue
        why = _mismatch(ck, store.read(path), e.get("sha256"), e.get("bytes"))
        if why:
            p.append(f"{path}: {why}")
    actual = [f for f in store.under("state/") if f != "state/STATE.json"]
    for f in actual:
        if f not in listed:
            p.append(f"{f} is not listed (21.2: a state file unlisted refuses the read)")
    if "state/accepted.json" not in listed:
        p.append("state/accepted.json is not listed (21.2: it is listed)")
    check("ST4 STATE.json files lists every file under state/ but STATE.json itself, once, sorted by path, accepted.json included, each with the SHA-256 and byte count it has (line endings diagnosis of 21.2); nothing under state/ is unlisted (21.2)", p,
          f"{len(listed)} listed, {len(actual)} present")

    # ST5: manifest_sha256 and accepted (21.1, 21.2)
    p = []
    mdata = store.read("root/live/manifest.json")
    man, merr = store.load(ck, "root/live/manifest.json")
    msha = ck.sha256_hex(mdata) if mdata is not None else None
    if desc.get("manifest_sha256") != msha:
        p.append(f"manifest_sha256 {str(desc.get('manifest_sha256'))[:16]}, root/live/manifest.json has {str(msha)[:16]}"
                 + (ck.hash_mismatch_note(mdata, desc.get("manifest_sha256")) if mdata is not None else ""))
    want_acc = {"snapshot": (man.get("snapshot") or {}).get("id"), "manifest_sha256": msha} if isinstance(man, dict) else None
    if desc.get("accepted") != want_acc:
        p.append(f"accepted {desc.get('accepted')}, the manifest's snapshot id and SHA-256 give {want_acc} (21.1, 21.2)")
    check("ST5 manifest_sha256 is the SHA-256 of root/live/manifest.json and accepted is the pair of its snapshot id and that SHA-256 (null only with no manifest) (21.1, 21.2)", p,
          f"accepted {want_acc}" if want_acc else "")
    info["accepted"] = want_acc

    # ST6: the state files (21.2 as 20.3)
    p = []
    for f in actual:
        p += _state_file_problems(ck, st, store, f)
    for f in STATE_FIXED:
        if f"state/{f}" not in fileset:
            p.append(f"state/{f} missing (17.1)")
    check("ST6 each state file validates: accepted.json against rmf.econ.accepted/1, alerts/1, pins/1, publications/1, review-queue/4, each run record against the run item of runs/2, deployments.json against deployments/1 (v0.8, built from 22.4); every one canonical JSON (17.1, 20.3, 21.2)", p,
          f"{len(actual)} files")

    # Collection records (needed from here on)
    records, rec_errs = [], []
    for f in store.under("runs/"):
        v, err = store.load(ck, f)
        if err or not isinstance(v, dict):
            rec_errs.append(f"{f}: {err or 'not an object'}")
            continue
        records.append((f, v))
    records.sort(key=lambda x: (str(x[1].get("started_at")), str(x[1].get("run"))))
    info["records"] = records

    # ST7: accepted.json (21.1)
    acc, aerr = store.load(ck, "state/accepted.json")
    p = []
    promoted_time = None
    stage_b = None
    if aerr or not isinstance(acc, dict):
        p.append(f"state/accepted.json: {aerr or 'not an object'} (21.2: a store without it is refused)")
        acc = {}
    src = acc.get("source") or {}
    sroot = src.get("root") if isinstance(src.get("root"), str) else None
    x = sroot.split("/", 1)[1] if sroot and sroot.startswith("unpublished/") else None
    if x is None or x not in folders:
        p.append(f"source.root {sroot!r} names no unpublished/ folder of the store (21.1: kept unchanged)")
    else:
        stage_b = sroot
        if src.get("run") != x:
            p.append(f"source.run {src.get('run')!r} is not the run of {sroot} (21.1)")
        sbm = store.read(f"{sroot}/live/manifest.json")
        ds = acc.get("dataset") or {}
        if sbm is None:
            p.append(f"{sroot}/live/manifest.json missing")
        else:
            why = _mismatch(ck, sbm, ds.get("manifest_sha256"))
            if why:
                p.append(f"{sroot}/live/manifest.json is not the promoted dataset: {why} (21.1: the Stage B folder is kept unchanged)")
            sv, _ = store.load(ck, f"{sroot}/live/manifest.json")
            if isinstance(sv, dict):
                if (sv.get("snapshot") or {}).get("id") != ds.get("snapshot"):
                    p.append(f"dataset.snapshot {ds.get('snapshot')} is not the Stage B manifest's snapshot {(sv.get('snapshot') or {}).get('id')}")
                promoted_time = sv.get("generated_at")
        # the promotion copied the Stage B root's live/ and archive/ (without archive/state/): root/archive only grows
        missing, differ = [], []
        for f in store.under(f"{sroot}/archive/"):
            rel = f[len(sroot) + 1:]
            if rel.startswith("archive/state/"):
                continue
            got = store.read("root/" + rel)
            if got is None:
                missing.append(rel)
            elif got != store.read(f):
                differ.append(rel)
        if missing:
            p.append(f"{len(missing)} file(s) of {sroot}/archive/ are not in root/archive/ (21.1, 21.2: copied by the promotion, root/archive only grows), e.g. {missing[:2]}")
        if differ:
            p.append(f"{len(differ)} file(s) of root/archive/ differ from {sroot}/archive/, e.g. {differ[:2]} (append-only)")
        rr_b = store.read(f"{sroot}/archive/state/run-records/{x}.json")
        if rr_b is not None and store.read(f"state/run-records/{x}.json") != rr_b:
            p.append(f"state/run-records/{x}.json is not the Stage B run record of {sroot} (reading: a run record is never rewritten)")
        if not any(sha_ok for sha_ok in [ck.sha256_hex(store.read(f)) == ds.get("manifest_sha256") for f in store.under("root/archive/manifests/")]):
            p.append("root/archive/manifests/ holds no copy of the promoted manifest (21.1: root/archive is a byte copy of the Stage B archive)")
    ver = acc.get("verification") or {}
    if ck.is_time(ver.get("at")) and ck.is_time(acc.get("promoted_at")) and ver["at"] > acc["promoted_at"]:
        p.append(f"verification.at {ver['at']} is after promoted_at {acc['promoted_at']} (21.1: verified before it writes)")
    if ck.rx_automation_login(acc.get("promoted_by")) or not (isinstance(acc.get("promoted_by"), str) and ck.RX_GITHUB_LOGIN.fullmatch(acc["promoted_by"])):
        p.append(f"promoted_by {acc.get('promoted_by')!r} is not a person's GitHub login (21.6: automation accounts are refused)")
    promotes = [(f, v) for f, v in records if v.get("operation") == "promote"]
    if promotes and acc.get("run") != promotes[0][1].get("run"):
        p.append(f"run {acc.get('run')!r} is not the promotion's collection record {promotes[0][1].get('run')!r} (21.1: the operation's run id)")
    if promotes and acc.get("promoted_at") != promotes[0][1].get("started_at"):
        p.append(f"promoted_at {acc.get('promoted_at')} is not the promotion's now {promotes[0][1].get('started_at')} (reading)")
    check("ST7 state/accepted.json names the promoted dataset: its Stage B folder (source.root and source.run) present and unchanged as far as the store tells (its manifest is the dataset, its archive is in root/archive byte for byte, its run record kept), verified before promoted_at, promoted by a person in the promotion run (21.1, 21.6)", p,
          f"dataset {acc.get('dataset')}, from {sroot}")
    info["stage_b"], info["promoted_time"], info["acc"] = stage_b, promoted_time, acc

    # ST8: one promotion (21.1)
    p = []
    if len(promotes) != 1:
        p.append(f"{len(promotes)} collection records of the operation promote; the promotion happens once (21.1: a store with an accepted.json refuses a second)")
    if promotes and records and records[0][1].get("operation") != "promote":
        p.append(f"the first collection record is {records[0][0]}, not the promotion (a Stage C run never starts from an unpromoted store, 21.2)")
    for f, v in promotes:
        if v.get("outcome") != "promoted" or v.get("trigger") != "operation" or v.get("requests") != []:
            p.append(f"{f}: outcome {v.get('outcome')}, trigger {v.get('trigger')}, {len(v.get('requests') or [])} request(s); 21.4 gives promoted, operation, none")
        if v.get("accepted") != acc.get("dataset"):
            p.append(f"{f}: accepted {v.get('accepted')} is not accepted.json's dataset {acc.get('dataset')}")
    for f, v in records:
        if v.get("outcome") == "promoted" and v.get("operation") != "promote":
            p.append(f"{f}: outcome promoted outside the promotion (21.4)")
    check("ST8 exactly one promotion: one collection record with operation promote, outcome promoted, no requests, the first in time, whose accepted is accepted.json's dataset (21.1, 21.4)", p, f"{len(promotes)} promotion record(s)")

    # ST9: collection records (21.4)
    p = list(rec_errs)
    for f, v in records:
        data = store.read(f)
        why = _canonical(ck, data, v)
        if why:
            p.append(f"{f}: {why} (21.4: canonical JSON)")
        p += [f"{f}: {e}" for e in _schema(ck, st, "collection", v)[:3]]
        if f != f"runs/{v.get('run')}.json":
            p.append(f"{f}: run {v.get('run')!r} is not its file name (21.2: runs/<run id>.json)")
        trig, op = v.get("trigger"), v.get("operation")
        if (trig == "operation") != (op is not None):
            p.append(f"{f}: trigger {trig} with operation {op} (21.4: an operation exactly when the trigger is operation)")
        if op is not None and v.get("requests"):
            p.append(f"{f}: an operation with {len(v['requests'])} request(s) (21.4: empty for an operation)")
        if op in ("rollback", "restore") and v.get("outcome") != "published":
            p.append(f"{f}: a {op} with outcome {v.get('outcome')} (17.2: published)")
        if op == "review" and v.get("outcome") not in ("published", "refused"):
            p.append(f"{f}: a review with outcome {v.get('outcome')} (17.5: published or refused)")
        if op in ("pin", "unpin"):
            # 21.4, 21.6 (v0.8, I45): outcome no-change; they change pins.json only, as 17.6 records them
            if v.get("outcome") != "no-change":
                p.append(f"{f}: a {op} with outcome {v.get('outcome')} (21.4: no-change)")
            pins_doc, _ = store.load(ck, "state/pins.json")
            pins_doc = pins_doc if isinstance(pins_doc, dict) else {}
            t = v.get("started_at")
            if op == "pin" and not (any(isinstance(x, dict) and x.get("pinned_at") == t for x in pins_doc.get("pins") or [])
                                    or any(isinstance(x, dict) and str(x.get("unpinned_at")) > str(t) for x in pins_doc.get("unpinned") or [])):
                p.append(f"{f}: a pin at {t}, but pins.json has no pin made then (nor a later unpin) (17.6, 21.6)")
            if op == "unpin" and not any(isinstance(x, dict) and x.get("unpinned_at") == t for x in pins_doc.get("unpinned") or []):
                p.append(f"{f}: an unpin at {t}, but pins.json unpinned records none then (17.6, 21.6)")
        if op is None and v.get("outcome") in ("refused", "promoted"):
            p.append(f"{f}: a collection with outcome {v.get('outcome')}")
        if ck.is_time(v.get("started_at")) and ck.is_time(v.get("ended_at")) and v["ended_at"] < v["started_at"]:
            p.append(f"{f}: ended_at before started_at")
        for i, r in enumerate(v.get("requests") or []):
            for why in ck.response_record_problems(r, None, i + 1):
                p.append(f"{f} requests[{i}]: {why}")
    check("ST9 every runs/<run id>.json is a canonical rmf.econ.collection/1 record named by its run, with exactly the twelve fields of 20.2 in every request (numbered from 1), an operation exactly when the trigger is operation and then no request, outcomes as 14.1 and 21.4 give them (20.2, 21.4)", p,
          f"{len(records)} record(s)")

    # ST10: request bodies and responses/ (21.2)
    p = []
    host_group, group_host = _registry_hosts(st)
    referenced = {}
    for f, v in records:
        prev_t = None
        for i, r in enumerate(v.get("requests") or []):
            if not isinstance(r, dict):
                continue
            sha = r.get("sha256")
            body_path = f"responses/{str(sha)[:2]}/{sha}.bin"
            data = store.read(body_path)
            if data is None:
                p.append(f"{f} requests[{i}]: no body at {body_path} (21.2: content-addressed)")
            else:
                why = _mismatch(ck, data, sha, r.get("bytes"))
                if why:
                    p.append(f"{body_path}: {why}")
            referenced.setdefault(sha, f)
            if r.get("host") not in host_group:
                p.append(f"{f} requests[{i}]: host {r.get('host')!r} is not a registered source host (18)")
            t = r.get("requested_at")
            if ck.is_time(t) and ck.is_time(v.get("started_at")) and t < v["started_at"]:
                p.append(f"{f} requests[{i}]: requested_at {t} before the run's now {v['started_at']} (reading)")
            if ck.is_time(t) and prev_t and t < prev_t:
                p.append(f"{f} requests[{i}]: requested_at {t} before the request before it")
            prev_t = t if ck.is_time(t) else prev_t
    stage_b_bodies = {}
    if stage_b:
        for g in store.under(f"{stage_b}/responses/"):
            if g.endswith(".bin"):
                stage_b_bodies[ck.sha256_hex(store.read(g))] = store.size(g)
    stored = {}
    for g in store.under("responses/"):
        mt = RX_BODY.fullmatch(g)
        if not mt or mt.group(1) != mt.group(2)[:2]:
            p.append(f"{g}: not responses/<first 2 hex>/<sha256>.bin (21.2)")
            continue
        data = store.read(g)
        if ck.sha256_hex(data) != mt.group(2):
            p.append(f"{g}: its bytes have sha256 {ck.sha256_hex(data)[:16]}, not its name{ck.hash_mismatch_note(data, mt.group(2))}")
        stored[mt.group(2)] = len(data)
        if mt.group(2) not in referenced and mt.group(2) not in stage_b_bodies:
            p.append(f"{g}: no collection record received this body (21.2: every response body a run received)")
    present_b = [s for s in stage_b_bodies if s in stored]
    if stage_b and len(present_b) != len(stage_b_bodies):
        p.append(f"{len(stage_b_bodies) - len(present_b)} of the {len(stage_b_bodies)} Stage B response bodies are not at their content addresses (21.1 v0.7, F11: the promotion stores them)")
    info["stage_b_bodies"], info["stored_bodies"], info["referenced_bodies"] = stage_b_bodies, stored, referenced
    info["promotion_copied_bodies"] = True  # 21.1 (v0.7, F11)
    check("ST10 every request's body is at responses/<first 2 hex>/<sha256>.bin with the recorded bytes and SHA-256, and so is every Stage B body (the promotion stores them, 21.1); every stored body is content-addressed and was received by a run or is a Stage B body; requests to registered hosts, in time order (20.2, 21.1, 21.2)", p,
          f"{len(stored)} stored bodies, {len(referenced)} referenced, {len(present_b)} of the {len(stage_b_bodies)} Stage B bodies stored")

    # The composed working root (21.3) and its context
    rv = ck.RootView(store.path / "root", state=store.path / "state", state_exclude=("STATE.json",))
    # 21.1: the boundary comes from the working root's archive/state/accepted.json; whether the runs before it
    # recorded their full fetches is what the Stage B folder's own collector.json shows (v0.6 form: none).
    sb_col, _ = store.load(ck, f"{stage_b}/archive/state/collector.json") if stage_b else (None, None)
    legacy_ff = isinstance(sb_col, dict) and "full_fetches" in sb_col
    info["legacy_ff"] = legacy_ff
    ctx = _ctx_for(ck, st, rv, None, legacy_ff)
    promoted_time = ctx.legacy_until
    info["ctx"] = ctx
    run_recs = ck.rx_run_records(ctx)

    # ST11: run records and requests (14.1, 17.3, 21.3, 21.4)
    p = []
    by_run = {v.get("run"): (f, v) for f, v in records}
    plan = ck.rx_full_plan(ctx)
    for f, v in records:
        op = v.get("operation")
        rid = v.get("run")
        rec = run_recs.get(rid)
        if op in NO_RUN_RECORD_OPS:
            if rec is not None:
                p.append(f"{f}: the {op} operation has a run record state/run-records/{rid}.json (21.4: it runs no pipeline step and has none)")
            continue
        if rec is None:
            p.append(f"{f}: no run record state/run-records/{rid}.json (21.3: the store keeps the run's run record)")
            continue
        want_trig = OP_TRIGGER.get(op) if op else v.get("trigger")
        if rec.get("trigger") != want_trig:
            p.append(f"{f}: the run record's trigger is {rec.get('trigger')}, the collection record gives {want_trig}")
        if rec.get("outcome") != v.get("outcome"):
            p.append(f"{f}: outcome {v.get('outcome')}, the run record says {rec.get('outcome')}")
        if rec.get("started_at") != v.get("started_at"):
            p.append(f"{f}: started_at {v.get('started_at')}, the run record says {rec.get('started_at')} (21.4: the run's now)")
        if ck.is_time(rec.get("ended_at")) and ck.is_time(v.get("ended_at")) and v["ended_at"] < rec["ended_at"]:
            p.append(f"{f}: ended_at {v['ended_at']} before the run record's {rec['ended_at']} (21.4: the time its record was written)")
        if op is None and rec.get("series"):
            want_hosts = {group_host[g] for g in ck.requested_groups(st, rec)}
            got_hosts = {r.get("host") for r in v.get("requests") or [] if isinstance(r, dict)}
            if want_hosts != got_hosts:
                p.append(f"{f}: requests to {sorted(got_hosts)}, the run record's outcomes request the groups of {sorted(want_hosts)}")
            rows = plan["runs"].get(rid, {})
            today = ck.et_date(ck.parse_utc(v["started_at"])) if ck.is_time(v.get("started_at")) else None
            for i, r in enumerate(v.get("requests") or []):
                if not isinstance(r, dict) or not isinstance(r.get("url"), str) or today is None:
                    continue
                g = host_group.get(r.get("host"))
                start, end = request_start(r["url"])
                if g is None or start is None or g not in rows:
                    continue
                want = _group_earliest(st, g) if rows[g]["full"] else (today - dt.timedelta(days=59)).isoformat()
                if start != want:
                    p.append(f"{f} requests[{i}]: start {start}, 17.3 gives {want} ({'full' if rows[g]['full'] else 'a 60-day window'})")
                if end is not None and end != today.isoformat():
                    p.append(f"{f} requests[{i}]: end {end}, the run's ET date is {today} (reading: {{end}} is the last period requested, the run's ET date)")
    for rid, rec in sorted(run_recs.items(), key=lambda kv: str(kv[0])):
        if rid not in by_run and not (promoted_time and str(rec.get("started_at")) <= promoted_time):
            p.append(f"state/run-records/{rid}.json has no collection record runs/{rid}.json (21.4: one per run that wrote the store)")
    check("ST11 every collection record but the promotion's has its run record (same trigger, outcome and now); a collection's requests go to exactly the hosts of the groups its run requested, with the window of 17.3 (full from the group's earliest period for an unpublished group, H.6 and the weekly full fetch once per Sunday; else the 60 days ending on the ET date); every Stage C run record has its collection record (14.1, 17.3, 21.4)", p,
          f"{len(run_recs)} run record(s)")

    # ST12: accepted, against the manifest history (21.1, 21.4)
    p = []
    man_by_sha = {}
    for name, m, err in ctx.arch_manifests:
        data = rv.read(rv.manifests, name)
        if not err and data is not None:
            man_by_sha[ck.sha256_hex(data)] = (name, m)
    timeline = sorted(((m.get("generated_at"), sha, (m.get("snapshot") or {}).get("id")) for sha, (name, m) in man_by_sha.items() if ck.is_time(m.get("generated_at"))))
    prev_acc = None
    for f, v in records:
        a = v.get("accepted") or {}
        if a.get("manifest_sha256") not in man_by_sha:
            p.append(f"{f}: accepted names a manifest {str(a.get('manifest_sha256'))[:16]} that is not in root/archive/manifests/ (21.1: every accepted manifest is archived)")
            prev_acc = a
            continue
        name, m = man_by_sha[a["manifest_sha256"]]
        if (m.get("snapshot") or {}).get("id") != a.get("snapshot"):
            p.append(f"{f}: accepted.snapshot {a.get('snapshot')} is not the snapshot {((m.get('snapshot') or {}).get('id'))} its manifest names")
        if ck.is_time(v.get("ended_at")):
            in_place = [x for x in timeline if x[0] <= v["ended_at"]]
            if in_place and in_place[-1][1] != a["manifest_sha256"]:
                p.append(f"{f}: accepted {name}, but the newest manifest at {v['ended_at']} is {in_place[-1][0]}")
        if v.get("outcome") == "published" and v.get("operation") != "restore" and m.get("generated_at") != v.get("started_at"):
            p.append(f"{f}: outcome published, but its accepted manifest was generated at {m.get('generated_at')}, not at the run's now {v.get('started_at')}")
        if (v.get("outcome") in OUTCOMES_QUIET or v.get("operation") == "restore") and prev_acc is not None and a != prev_acc:
            p.append(f"{f}: outcome {v.get('outcome')} ({v.get('operation') or v.get('trigger')}) changed the accepted dataset (21.3: nothing is accepted then)")
        prev_acc = a
    if records and records[-1][1].get("accepted") != desc.get("accepted"):
        p.append(f"the newest collection record's accepted {records[-1][1].get('accepted')} is not STATE.json's {desc.get('accepted')}")
    check("ST12 every collection record's accepted is an archived manifest's pair (snapshot id, SHA-256): the newest manifest in place when the record was written, new exactly for a published run (at its now) and unchanged by every other outcome and by a restore; the newest record's equals STATE.json's (21.1, 21.3, 21.4)", p,
          f"{len(timeline)} archived manifest(s)")

    # ST13: added and month_added_bytes (21.4)
    p, notes = [], []
    attr = attribute_root(ck, ctx, store)
    seen_bodies = set()
    promote_root = []
    if stage_b:
        promote_root = [f for f in store.under(f"{stage_b}/") if f.split("/")[2] in ("live", "archive") and not f[len(stage_b) + 1:].startswith("archive/state/")]
    month_sum = {}
    for f, v in records:
        add = v.get("added") or {}
        t = v.get("started_at")
        op, oc = v.get("operation"), v.get("outcome")
        new_b = []
        for r in v.get("requests") or []:
            if isinstance(r, dict) and r.get("sha256") not in seen_bodies and r.get("sha256") not in [x[0] for x in new_b]:
                new_b.append((r.get("sha256"), r.get("bytes") if type(r.get("bytes")) is int else 0))
        bf, bb = len(new_b), sum(x[1] for x in new_b)
        if op == "promote":
            rf = len(promote_root)
            rb = sum(store.size(x) for x in promote_root)
            sbf, sbb = len(info["stage_b_bodies"]), sum(info["stage_b_bodies"].values())
            got = (add.get("files"), add.get("bytes"))
            want = (rf + sbf, rb + sbb)  # 21.1 (v0.7, F11): the root's copy and the Stage B bodies at their content addresses
            if got != want:
                p.append(f"{f}: added {got}; the promotion copied {rf} files of {rb} bytes into root/ and stored {sbf} Stage B bodies of {sbb} bytes in responses/, so {want} (21.1)")
            seen_bodies |= set(info["stage_b_bodies"])
        else:
            if oc in OUTCOMES_QUIET:
                lo_f, lo_b, hi_f, hi_b = bf, bb, bf, bb
                stray = [x for x, tt in attr.items() if tt == t]
                if stray:
                    p.append(f"{f}: outcome {oc}, yet {len(stray)} file(s) under root/ date from its now, e.g. {stray[:2]} (21.2: such a run adds its records and state files only)")
            else:
                mine = [x for x, tt in attr.items() if tt == t and x.startswith("root/archive/")]
                mine_files = [x for x in mine if x.startswith("root/archive/files/")]
                lo_f = bf + len(mine) + len(mine_files)
                lo_b = bb + sum(store.size(x) for x in mine) + sum(store.size(x) for x in mine_files)
                earlier = [x for x, tt in attr.items() if tt is not None and tt < t and x.startswith("root/archive/files/")]
                hi_f = lo_f + len(earlier)
                hi_b = lo_b + sum(store.size(x) for x in earlier)
            got_f, got_b = add.get("files"), add.get("bytes")
            if not (isinstance(got_f, int) and isinstance(got_b, int) and lo_f <= got_f <= hi_f and lo_b <= got_b <= hi_b):
                p.append(f"{f} ({oc}): added {got_f} files, {got_b} bytes; the store gives {lo_f}" + (f" to {hi_f}" if hi_f != lo_f else "")
                         + f" files and {lo_b}" + (f" to {hi_b}" if hi_b != lo_b else "") + f" bytes ({bf} new body or bodies of {bb} bytes)")
            seen_bodies |= {x[0] for x in new_b}
        month = ck.et_date(ck.parse_utc(t)).strftime("%Y-%m") if ck.is_time(t) else None
        before = month_sum.get(month, 0)
        month_sum[month] = before + (add.get("bytes") if isinstance(add.get("bytes"), int) else 0)
        if v.get("month_added_bytes") != month_sum[month]:
            p.append(f"{f}: month_added_bytes {v.get('month_added_bytes')}, the records of ET month {month} up to it add {month_sum[month]}")
        v["_earlier_month_bytes"] = before
    check("ST13 added counts the files and bytes the write added under root/ and responses/ (exactly the new bodies for a run that accepts nothing; for a publishing run the new archive files, their live copies and the new bodies, within what the store tells; the promotion's copy of the Stage B root), and month_added_bytes sums added.bytes over the ET month up to the record (21.2, 21.4)", p,
          "; ".join(f"{k}: {v_} bytes" for k, v_ in sorted(month_sum.items(), key=str)))

    # ST14: freshness and expected_next_update_by (21.4, 14.2)
    p = []
    n14 = 0
    for f, v in records:
        a = v.get("accepted") or {}
        hit = man_by_sha.get(a.get("manifest_sha256"))
        if hit is None or not ck.is_time(v.get("started_at")):
            continue
        name, m = hit
        snap = ctx.snaps.get((m.get("snapshot") or {}).get("id"))
        now = ck.parse_utc(v["started_at"])
        want = freshness_of(ck, st, m, snap, now)
        n14 += 1
        if v.get("freshness") != want:
            got = v.get("freshness") if isinstance(v.get("freshness"), list) else []
            diff = [f"{w['series']}: got {g if isinstance(g, dict) else g!r}, want {w}" for w, g in zip(want, got + [None] * (len(want) - len(got))) if g != w]
            p.append(f"{f}: freshness differs from the accepted manifest {name} at {v['started_at']}: " + "; ".join(diff[:2])
                     + (f" (and the list has {len(got)} entries, {len(want)} registered series)" if len(got) != len(want) else ""))
        best = expected_next_of(ck, st, m, snap)
        got_n = v.get("expected_next_update_by")
        if best is not None and got_n != ck.fmt_utc(best):
            p.append(f"{f}: expected_next_update_by {got_n}, the earliest 14.2 deadline among published series neither held nor frozen is {ck.fmt_utc(best)}")
        if best is None and got_n != v.get("started_at"):
            p.append(f"{f}: expected_next_update_by {got_n}; with no series that qualifies it is the run's now {v.get('started_at')} (21.4)")
    check("ST14 every collection record's freshness (per registered series in registry order: held, frozen, not-yet-published as the accepted manifest gives them, else stale exactly when the run's now is at or after the series' staleness time from the 14.2 deadline of its next unseen period, the FOMC target when the EFFR's staleness time has passed; last_period; the deadline or null) and expected_next_update_by are recomputed from the accepted manifest of that time (14.2, 21.4)", p,
          f"{n14} record(s) recomputed")

    # ST15: line endings across the store (21.2)
    targets = [f for f in files if not (f.endswith(".bin") and (f.startswith("responses/") or (f.startswith("unpublished/") and "/responses/" in f)))]
    recorded = {e.get("path"): e.get("sha256") for e in flist if isinstance(e, dict)}
    recorded["root/live/manifest.json"] = desc.get("manifest_sha256")
    p = _cr_problems(ck, store, targets, recorded)
    check("ST15 no file of the store but the response bodies holds a carriage return or a byte order mark (.gitattributes, state/, root/, runs/, the Stage B record); a file that would match its record after CRLF is turned back into LF is named 'line endings converted' (21.2)", p,
          f"{len(targets)} files")

    # ST16: STATE.json is written last, by the newest run (21.2)
    p = []
    if records:
        newest = records[-1][1]
        if desc.get("run") != newest.get("run"):
            p.append(f"STATE.json run {desc.get('run')!r}, the newest collection record is {newest.get('run')!r} (21.2: written last, by every write)")
        if ck.is_time(desc.get("written_at")) and ck.is_time(newest.get("ended_at")) and desc["written_at"] < newest["ended_at"]:
            p.append(f"written_at {desc['written_at']} before the newest record's ended_at {newest['ended_at']} (reading: STATE.json is written last)")
    else:
        p.append("no collection record (21.4: the promotion writes one)")
    check("ST16 STATE.json names the run of the newest collection record and is written at or after that record (21.2: last, by every write)", p)

    # ST17: budget:state-store (21.4)
    p = []
    for f, v in records:
        rec = run_recs.get(v.get("run"))
        if rec is None:
            continue
        earlier = v.get("_earlier_month_bytes", 0)
        has = "budget:state-store" in (rec.get("alerts") or [])
        if (earlier > ck.STATE_BUDGET_WARNING) != has:
            p.append(f"{f}: the earlier records of its ET month added {earlier} bytes, and budget:state-store is {'' if has else 'not '}among its run's alerts (21.4: a warning over 50,000,000)")
    if records:
        newest = records[-1][1]
        earlier = newest.get("_earlier_month_bytes", 0)
        doc, _ = store.load(ck, "state/alerts.json")
        sev = next((a.get("severity") for a in (doc or {}).get("open", []) if isinstance(a, dict) and a.get("key") == "budget:state-store"), None) if isinstance(doc, dict) else None
        want = "critical" if earlier > ck.STATE_BUDGET_CRITICAL else ("warning" if earlier > ck.STATE_BUDGET_WARNING else None)
        if want != sev and run_recs.get(newest.get("run")) is not None:
            p.append(f"the ledger has budget:state-store {sev}; the newest record's earlier ET month records added {earlier} bytes, so {want}")
    check("ST17 budget:state-store is a current alert exactly when the earlier collection records of the run's ET month added more than 50,000,000 bytes (critical over 100,000,000) (21.4; reading: it is in that run's alerts)", p)

    # ST18: scheduled-run-gap against the store's scheduled runs (14.3, 21.3)
    p, n18 = [], 0
    last_ok = None
    for f, v in records:
        rec = run_recs.get(v.get("run"))
        if v.get("trigger") == "schedule" and rec is not None and ck.is_time(v.get("started_at")):
            alerts = rec.get("alerts") or []
            if "self-check-unavailable" not in alerts and last_ok is not None:
                hours = (ck.parse_utc(v["started_at"]) - ck.parse_utc(last_ok)).total_seconds() / 3600
                has = "scheduled-run-gap" in alerts
                n18 += 1
                if hours > ck.RUN_GAP_WARNING_HOURS + 1 and not has:
                    p.append(f"{f}: {hours:.1f} hours after the store's previous successful scheduled run {last_ok}, but no scheduled-run-gap (14.3: over 9 hours)")
                if hours < ck.RUN_GAP_WARNING_HOURS - 1 and has:
                    p.append(f"{f}: scheduled-run-gap although the store's previous successful scheduled run {last_ok} is {hours:.1f} hours before it (14.3: over 9 hours)")
            if v.get("outcome") not in ("gate-failed", "failed"):
                last_ok = v["started_at"]
    check("ST18 a scheduled run that read the self-check facts raises scheduled-run-gap when more than 9 hours passed since the store's previous successful scheduled run, and not when fewer did (one hour of margin for queueing; a successful scheduled run always writes the store, 21.3) (14.3)", p,
          f"{n18} scheduled run(s) compared")

    # ST20 (v0.8): the private deployment log state/deployments.json (21.2, 22.4)
    p = []
    raw = store.read("state/deployments.json")
    live_v4 = isinstance(man, dict) and man.get("schema") == ck.MANIFEST_V4
    if raw is None:
        if live_v4:
            p.append("state/deployments.json is missing although the accepted manifest is manifest/4 (reading: a v0.8 collection run writes it at every run, 22.4)")
        note = "absent: every write so far is a v0.7 run (reading: required once the accepted manifest is manifest/4)"
    else:
        dep, derr = store.load(ck, "state/deployments.json")
        if derr:
            p.append(f"state/deployments.json: {derr}")
        else:
            pairs = set()
            for f in store.under("root/archive/manifests/"):
                data = store.read(f)
                mv, merr2 = store.load(ck, f)
                if not merr2 and isinstance(mv, dict):
                    pairs.add(((mv.get("snapshot") or {}).get("id"), ck.sha256_hex(data)))
            p += ck.deployment_log_problems(dep, "state/deployments.json", True, st, archived_pairs=pairs)
        note = f"{len((dep or {}).get('deployments') or []) if not derr else 0} entr(y/ies)"
    check("ST20 state/deployments.json (v0.8), when present: rmf.econ.deployments/1, canonical, numbered 1, 2, ..., previous the dataset before, each release data-<snapshot>-<run id>-<attempt> once, post set from the verify job, a redeploy only of a verified pair, every dataset an archived manifest's pair; written by the collection run (21.2, 22.4)", p, note)

    # ST19: root/ in live mode (21.2, 21.3)
    print("check_state.py: root/ with state/ (accepted.json included, STATE.json left out) as its archive/state/: the working root of 21.3, in live mode")
    ck.section_root(st, store.path / "root", live=True, rv=ck.RootView(store.path / "root", state=store.path / "state", state_exclude=("STATE.json",)), legacy_ff=legacy_ff)
    info["run_recs"] = run_recs
    info["man_by_sha"] = man_by_sha
    info["attr"] = attr
    return info


def run_state(ck, st, store_dir):
    store = Store(store_dir)
    print(f"check_state.py: state store {store.path}")
    if not store.path.is_dir():
        ck.check("ST0 the state store is a folder", [f"{store.path} is not a folder"])
        return None
    desc, err = store.load(ck, "state/STATE.json")
    sid = desc.get("schema") if isinstance(desc, dict) else None
    if sid == ck.SCHEMA_IDS["state"]:
        print("check_state.py: state/STATE.json is rmf.econ.state/1: the Stage B layout (20.1, 20.3)")
        return run_stage_b(ck, st, store, desc)
    if sid == ck.SCHEMA_IDS["state-v2"]:
        print("check_state.py: state/STATE.json is rmf.econ.state/2: the v0.7 layout (21.1, 21.2, 21.4)")
        return run_v07(ck, st, store, desc)
    ck.check("ST0 state/STATE.json is readable and names rmf.econ.state/1 or rmf.econ.state/2 (20.3, 21.2: a missing or unreadable descriptor refuses the read)",
             [f"state/STATE.json: {err or 'schema ' + repr(sid)}"])
    if store.read(".gitattributes") != ck.GITATTRIBUTES:
        ck.check("ST1 .gitattributes is exactly the 8 bytes '* -text' and a line feed (21.2)", [".gitattributes is missing or not its 8 bytes"])
    return None


# ---------------------------------------------------------------------------
# The appendix G scenario (G0 to G12)
# ---------------------------------------------------------------------------

G_STEPS = [  # appendix G: time, trigger, operation, outcome (None: the outcome the rules give)
    ("2026-11-16T16:17:00Z", "manual", None, "published"),
    ("2026-11-16T16:30:00Z", "operation", "promote", "promoted"),
    ("2026-11-16T20:17:00Z", "schedule", None, "no-change"),
    ("2026-11-17T00:17:00Z", "schedule", None, "published"),
    ("2026-11-22T16:17:00Z", "schedule", None, "published"),
    ("2026-11-22T20:17:00Z", "schedule", None, "no-change"),
    ("2026-11-23T16:17:00Z", "schedule", None, "published"),
    ("2026-11-23T16:30:00Z", "operation", "review", "published"),
    ("2026-11-23T16:45:00Z", "operation", "rollback", "published"),
    ("2026-11-23T17:00:00Z", "operation", "restore", "published"),
    ("2026-11-23T20:17:00Z", "schedule", None, None),
]
G_FIELDS = ("step", "run", "trigger", "operation", "at", "outcome", "record", "plan", "ledger")  # appendix G (v0.7, F13)
LEDGER_FIELDS = ("key", "severity", "title", "body")
rk, pk = "record", "plan"


def run_scenario(ck, st, d):
    check = ck.check
    d = Path(d).resolve()
    print(f"check_state.py: appendix G scenario {d}")
    data = (d / "steps.json").read_bytes() if (d / "steps.json").is_file() else None
    p = []
    steps = None
    if data is None:
        p.append("steps.json missing")
    else:
        try:
            doc = ck.load_strict(data)
            if isinstance(doc, list):
                steps = doc
            else:
                p.append(f"steps.json is a {type(doc).__name__}, not a JSON array (appendix G)")
        except Exception as exc:
            p.append(f"steps.json: {type(exc).__name__}: {exc}")
    if steps is not None:
        if len(steps) != len(G_STEPS):
            p.append(f"{len(steps)} steps, appendix G has {len(G_STEPS)}")
        for i, s in enumerate(steps):
            if not isinstance(s, dict):
                p.append(f"step {i + 1}: not an object")
                continue
            if set(s) != set(G_FIELDS):
                p.append(f"step {i + 1}: fields {sorted(s)}, appendix G gives exactly {list(G_FIELDS)}")
            led = s.get("ledger")
            if not isinstance(led, list) or any(not (isinstance(e, dict) and set(e) == set(LEDGER_FIELDS) and all(isinstance(e.get(k), str) for k in LEDGER_FIELDS)
                                                     and e.get("severity") in ("warning", "critical")) for e in led):
                p.append(f"step {i + 1}: ledger is not a list of {{key, severity, title, body}} (the alert ledger's open entries after the step)")
            elif len({e["key"] for e in led}) != len(led):
                p.append(f"step {i + 1}: a key appears twice in its ledger")
    check("G0 steps.json is a JSON array of one object per step with exactly the fields step, run, trigger, operation, at, outcome, record, plan and ledger; each ledger the open entries {key, severity, title, body} after the step, one per key (appendix G, 17.8)", p,
          f"{len(steps or [])} steps")
    if steps is None:
        return
    steps = [s if isinstance(s, dict) else {} for s in steps] + [{}] * max(0, len(G_STEPS) - len(steps))

    # G1: the rows: step, run id, time, trigger, operation, outcome, record path
    p = []
    for i, (t, trig, op, oc) in enumerate(G_STEPS, start=1):
        s = steps[i - 1]
        want = {"step": i, "run": f"g{i}", "at": t, "trigger": trig, "operation": op}
        for k, w in want.items():
            if s.get(k) != w:
                p.append(f"step {i}: {k} {s.get(k)!r}, appendix G gives {w!r}")
        if oc is not None and s.get("outcome") != oc:
            p.append(f"step {i}: outcome {s.get('outcome')!r}, appendix G gives {oc!r}")
        want_rec = None if i == 1 else f"runs/g{i}.json"
        if s.get(rk) != want_rec:
            p.append(f"step {i}: collection record {s.get(rk)!r}, expected {want_rec!r} (null for step 1)")
        plan = s.get(pk)
        if not isinstance(plan, list) or any(not (isinstance(e, dict) and set(e) == {"action", "key"} and e.get("action") in ("open", "update", "close") and isinstance(e.get("key"), str)) for e in plan):
            p.append(f"step {i}: the issue plan is not a list of {{action, key}} with action open, update or close (17.8)")
    check("G1 every step has the run id g<step>, the time, trigger, operation and outcome of its appendix G row, and its collection record runs/g<step>.json (none for step 1)", p)

    store = Store(d / "store")
    print("check_state.py: the final store in state mode")
    info = run_state(ck, st, d / "store") or {}
    if info.get("layout") != "v0.7":
        check("G2 the final store has the v0.7 layout (appendix G: step 2 promotes it)", ["the final store is not in the v0.7 layout"])
        return
    ctx, records, run_recs = info["ctx"], {v.get("run"): v for _, v in info["records"]}, info["run_recs"]
    host_group, group_host = _registry_hosts(st)
    grp = st_groups(st)

    def rec_of(i):
        return records.get(f"g{i}") or {}

    def reqs(i, g=None):
        return [r for r in rec_of(i).get("requests") or [] if isinstance(r, dict) and (g is None or host_group.get(r.get("host")) == g)]

    def outcomes(i):
        return (run_recs.get(f"g{i}") or {}).get("series") or {}

    def state_after(i):
        return ck.rx_state_at(ctx, G_STEPS[i - 1][0], inclusive=True) or {}

    def locks_after(i):
        return ck.rx_locks_at(ctx, G_STEPS[i - 1][0], True)

    # G2: steps 1 and 2: the Stage B record and the promotion
    p = []
    sb = info.get("stage_b")
    if sb != "unpublished/g1":
        p.append(f"the promoted Stage B folder is {sb!r}, not unpublished/g1 (step 2)")
    rr1, _ = store.load(ck, "unpublished/g1/archive/state/run-records/g1.json")
    if not isinstance(rr1, dict) or rr1.get("started_at") != G_STEPS[0][0] or rr1.get("trigger") != "manual" or rr1.get("outcome") != "published" \
            or (rr1.get("series") or {}) != {s: "appended" for s in st.series}:
        p.append(f"step 1's run record: {str(rr1)[:160]}; appendix G gives a manual run at {G_STEPS[0][0]}, published, all nine series appended")
    b_reqs = [f for f in store.under("unpublished/g1/responses/") if f.endswith(".json")]
    b_hosts = {}
    for f in b_reqs:
        v, _ = store.load(ck, f)
        if isinstance(v, dict):
            b_hosts.setdefault(v.get("host"), []).append(v)
    for g, h in group_host.items():
        for v in b_hosts.get(h, []):
            start, _ = request_start(str(v.get("url")))
            if start is not None and start != _group_earliest(st, g):
                p.append(f"step 1: {h} requested from {start}, not the full history from {_group_earliest(st, g)} (an empty store: every series not yet published)")
        if h not in b_hosts:
            p.append(f"step 1: no request to {h}")
    acc = info.get("acc") or {}
    if rec_of(2).get("accepted") != acc.get("dataset") or acc.get("source", {}).get("run") != "g1" or acc.get("run") != "g2" or acc.get("promoted_at") != G_STEPS[1][0]:
        p.append(f"step 2: accepted.json {acc.get('dataset')}, source run {acc.get('source', {}).get('run')}, run {acc.get('run')}, promoted_at {acc.get('promoted_at')}; appendix G promotes step 1's identifier in run g2 at {G_STEPS[1][0]}")
    m1 = store.read("unpublished/g1/live/manifest.json")
    if m1 is not None and acc.get("dataset", {}).get("manifest_sha256") != ck.sha256_hex(m1):
        p.append("step 2: the promoted dataset is not step 1's manifest SHA-256 (unpublished/g1/ unchanged)")
    check("G2 steps 1 and 2: a manual collection into an empty store in the Stage B layout (all nine series appended, full histories) and its promotion with step 1's identifier, unpublished/g1/ kept unchanged", p)

    # G3: step 3: only EFFR, windowed, no-change, nothing added under root/, the body new and stored
    p = []
    r3 = reqs(3)
    if {host_group.get(r.get("host")) for r in r3} != {"effr"}:
        p.append(f"step 3 requested {sorted({str(r.get('host')) for r in r3})}; appendix G: only the EFFR group")
    today3 = ck.et_date(ck.parse_utc(G_STEPS[2][0]))
    for r in r3:
        start, _ = request_start(str(r.get("url")))
        if start != (today3 - dt.timedelta(days=59)).isoformat():
            p.append(f"step 3: start {start}, a windowed request starts {(today3 - dt.timedelta(days=59)).isoformat()}")
    stray = [x for x, tt in info["attr"].items() if tt == G_STEPS[2][0]]
    if stray:
        p.append(f"step 3 added files under root/: {stray[:3]}")
    shas3 = {r.get("sha256") for r in r3}
    earlier = {r.get("sha256") for i in (2,) for r in reqs(i)} | (set(info.get("stage_b_bodies") or {}) if info.get("promotion_copied_bodies") else set())
    new3 = [r for r in r3 if r.get("sha256") not in earlier]
    added3 = rec_of(3).get("added") or {}
    if not new3:
        p.append("step 3: its response body is not new (appendix G: the response body is new and stored)")
    if (added3.get("files"), added3.get("bytes")) != (len({r.get("sha256") for r in new3}), sum(r.get("bytes") or 0 for r in {r.get("sha256"): r for r in new3}.values())):
        p.append(f"step 3: added {added3}; only its new body is added (nothing under root/)")
    check("G3 step 3: only the EFFR group is due, with a windowed request; no-change; nothing is added under root/ and the new response body is the only addition", p)

    # G4: step 4: effr and the three debt series appended
    p = []
    oc4 = outcomes(4)
    for s in ("effr", "debt-total", "debt-held-public", "debt-intragov"):
        if oc4.get(s) != "appended":
            p.append(f"step 4: {s} {oc4.get(s)}, appendix G: appended")
    s4 = state_after(4)
    for s in ("effr", "debt-total", "debt-held-public", "debt-intragov"):
        if ((s4.get("series") or {}).get(s) or {}).get("last_period") != "2026-11-13":
            p.append(f"step 4: {s} last_period {((s4.get('series') or {}).get(s) or {}).get('last_period')}, appendix G adds 2026-11-13")
    if s4.get("id") != ck.snapshot_id_of(ck.parse_utc(G_STEPS[3][0])):
        p.append(f"step 4 wrote no snapshot at its time (published)")
    check("G4 step 4: a new EFFR day and debt record date 2026-11-13: effr, debt-total, debt-held-public and debt-intragov appended and published", p)

    # G5: step 5: the first Sunday run, every group in full, debt-total held, source-overdue:effr, the zip body not written again
    p = []
    r5 = reqs(5)
    if {host_group.get(r.get("host")) for r in r5} != set(group_host):
        p.append(f"step 5 requested the groups {sorted({str(host_group.get(r.get('host'))) for r in r5})}; appendix G: the weekly full fetch of every group")
    for r in r5:
        g = host_group.get(r.get("host"))
        start, _ = request_start(str(r.get("url")))
        if start is not None and start != _group_earliest(st, g):
            p.append(f"step 5: {r.get('host')} start {start}, not the full history from {_group_earliest(st, g)}")
    s5 = state_after(5)
    if not any(h.get("series") == "debt-total" for h in s5.get("holds", [])) or any(h.get("series") != "debt-total" for h in s5.get("holds", [])):
        p.append(f"step 5: holds {[h.get('series') for h in s5.get('holds', [])]}, appendix G: debt-total held")
    if "source-overdue:effr" not in ((run_recs.get("g5") or {}).get("alerts") or []):
        p.append("step 5: source-overdue:effr is not among its alerts")
    zip_url = st.series["m1-sa"]["fetch"]["endpoint"]
    zips = [r for r in r5 if r.get("url") == zip_url]
    prior = set()
    for i in (2, 3, 4):
        prior |= {r.get("sha256") for r in reqs(i)}
    if info.get("promotion_copied_bodies"):
        prior |= set(info.get("stage_b_bodies") or {})
    if not zips:
        p.append("step 5: no request for the H.6 zip")
    for r in zips:
        if r.get("sha256") not in prior:
            p.append("step 5: the H.6 zip body is not one already stored (appendix G: it is the one already stored and is not written again)")
    check("G5 step 5: the first Sunday run fetches every group in full; debt-total is held (the 2019-12-31 total one dollar higher); source-overdue:effr; the H.6 zip body is one already stored and is not written again", p)

    # G6: step 6: no weekly full fetch again; EFFR and debt windowed; no H.6
    p = []
    r6 = reqs(6)
    today6 = ck.et_date(ck.parse_utc(G_STEPS[5][0]))
    if {host_group.get(r.get("host")) for r in r6} != {"effr", "debt-total"}:
        p.append(f"step 6 requested the groups {sorted({str(host_group.get(r.get('host'))) for r in r6})}; appendix G: EFFR and the held debt group, H.6 not requested")
    for r in r6:
        start, _ = request_start(str(r.get("url")))
        if start != (today6 - dt.timedelta(days=59)).isoformat():
            p.append(f"step 6: {r.get('host')} start {start}; appendix G: windowed ({(today6 - dt.timedelta(days=59)).isoformat()}), no weekly full fetch again")
    if state_after(6).get("holds") != state_after(5).get("holds"):
        p.append("step 6: the hold changed (appendix G: unchanged)")
    check("G6 step 6: a later Sunday run fetches no group in full again: EFFR and the held debt group with windowed requests, H.6 not requested; no-change with the hold unchanged", p)

    # G7: step 7: the debt source answers 500 to every attempt (one request and three retries)
    p = []
    d7 = reqs(7, "debt-total")
    if [r.get("status") for r in d7] != [500, 500, 500, 500]:
        p.append(f"step 7: debt statuses {[r.get('status') for r in d7]}; appendix G: one request and three retries, each 500")
    oc7 = outcomes(7)
    if oc7.get("effr") != "appended" or any(oc7.get(s) != "failed" for s in ("debt-total", "debt-held-public", "debt-intragov")):
        p.append(f"step 7: outcomes {oc7}; appendix G: effr appended, the debt group failed")
    s7 = state_after(7)
    if ((s7.get("series") or {}).get("effr") or {}).get("last_period") != "2026-11-20":
        p.append(f"step 7: effr last_period {((s7.get('series') or {}).get('effr') or {}).get('last_period')}; appendix G adds 2026-11-16 to 2026-11-20")
    check("G7 step 7: the debt source answers 500 to the request and its three retries, the debt group fails and is carried forward; effr appended to 2026-11-20", p)

    # G8 to G10: the locks
    p = []
    l8 = locks_after(8)
    held5 = next(((h.get("candidate") or {}).get("sha256") for h in state_after(7).get("holds", []) if h.get("series") == "debt-total"), None)
    if ("debt-total", "rejected", held5) not in l8:
        p.append(f"step 8: locks {sorted(map(ck._k16, l8))}; appendix G: debt-total locked, origin rejected, on its held candidate")
    if any(h.get("series") == "debt-total" for h in state_after(8).get("holds", [])):
        p.append("step 8: debt-total is still held after its rejection")
    _, m9 = ck.rx_manifest_at(ctx, G_STEPS[8][0], True)
    rb = (m9 or {}).get("rollback") or {}
    if m9 is None or m9.get("generated_at") != G_STEPS[8][0] or rb.get("to") != ck.snapshot_id_of(ck.parse_utc(G_STEPS[3][0])):
        p.append(f"step 9: the manifest in place is not a rollback to step 4's snapshot at {G_STEPS[8][0]} ({rb})")
    l9 = locks_after(9)
    if ("debt-total", "rejected", held5) not in l9:
        p.append("step 9: the rejection lock of debt-total was not kept")
    before9 = ck.rx_state_at(ctx, G_STEPS[8][0], inclusive=False) or {}
    target = ctx.snaps.get(rb.get("to")) or {}
    for sid in st.series:
        a, b = ck.rx_obs(ctx, (before9.get("series") or {}).get(sid)), ck.rx_obs(ctx, (target.get("series") or {}).get(sid))
        if a != b and not any(k[0] == sid and k[1] == "rolled-back" for k in l9):
            p.append(f"step 9: {sid} changes between step 8's data and step 4's but has no rolled-back lock")
        if a == b and any(k[0] == sid and k[1] == "rolled-back" for k in l9):
            p.append(f"step 9: {sid} does not change, yet it has a rolled-back lock")
    if not ctx.rv.read(ctx.rv.rollbacks, f"{ck.snapshot_id_of(ck.parse_utc(G_STEPS[8][0]))}.json"):
        p.append("step 9: no rollback record")
    if locks_after(10) != l9:
        p.append(f"step 10: locks {sorted(map(ck._k16, locks_after(10)))} differ from step 9's {sorted(map(ck._k16, l9))} (the locks still in force)")
    if rec_of(10).get("accepted") != rec_of(9).get("accepted"):
        p.append("step 10: the restore changed the accepted dataset")
    check("G8 steps 8 to 10: the reject locks debt-total (rejected, its held candidate); the rollback to step 4's snapshot writes its record, locks every series it changes (rolled-back) and keeps the rejection lock; the restore keeps every lock and the accepted dataset", p,
          f"locks after step 9: {', '.join(sorted(map(ck._k16, l9)))}")

    # G9: the ledgers and the issue plans (17.8), step 11's property in full
    p = []

    def as_ledger(entries):
        return {e.get("key"): (e.get("severity"), e.get("title"), e.get("body")) for e in entries if isinstance(e, dict)}

    sb_alerts, _ = store.load(ck, "unpublished/g1/archive/state/alerts.json")
    prev = {}
    led = {}
    for i in range(1, len(G_STEPS) + 1):
        s = steps[i - 1]
        cur = as_ledger(s.get("ledger") if isinstance(s.get("ledger"), list) else [])
        led[i] = cur
        if i == 1:
            keys = set(((rr1 or {}).get("alerts")) or []) if isinstance(rr1, dict) else set()
            if isinstance(sb_alerts, dict) and as_ledger(sb_alerts.get("open") or []) != cur:
                p.append("step 1: its ledger is not unpublished/g1/archive/state/alerts.json's open entries")
        elif i == 2:
            keys = set(prev)
            if cur != prev:
                p.append("step 2: the promotion changed the ledger (it runs no pipeline step and raises no alert)")
        else:
            keys = set((run_recs.get(f"g{i}") or {}).get("alerts") or [])
        if set(cur) != keys:
            p.append(f"step {i}: ledger keys {sorted(cur)}, the run's current alerts are {sorted(keys)} (17.8: the ledger after the run holds exactly them)")
        plan = s.get(pk) if isinstance(s.get(pk), list) else []
        got = [(e.get("action"), e.get("key")) for e in plan if isinstance(e, dict)]
        want = {("open", k) for k in set(cur) - set(prev)} | {("close", k) for k in set(prev) - set(cur)} \
            | {("update", k) for k in set(cur) & set(prev) if cur[k] != prev[k]}
        if len({k for _, k in got}) != len(got):
            p.append(f"step {i}: a key appears twice in the plan (never a duplicate issue)")
        if set(got) != want:
            p.append(f"step {i}: plan {sorted(got)}, the ledgers before and after give {sorted(want)} (17.8: open a new key, update a changed severity, title or body, close a gone key, nothing for an unchanged one)")
        if i == len(G_STEPS):
            same = [k for k in set(cur) & set(prev) if cur[k] == prev[k]]
            bad = [x for x in got if x[0] in ("open", "update") and x[1] in same]
            if bad:
                p.append(f"step 11 {bad}: keys open after step 10 with the same severity, title and body (appendix G row 11)")
            doc, _ = store.load(ck, "state/alerts.json")
            final = as_ledger((doc or {}).get("open", [])) if isinstance(doc, dict) else {}
            if final != cur:
                p.append(f"the store's final ledger {sorted(final)} is not step 11's ledger {sorted(cur)} (key, severity, title, body)")
        prev = cur
    check("G9 every step's ledger holds exactly the alerts current after it (step 1's is the Stage B ledger, the promotion changes none, the final one is the store's), and its issue plan is exactly the 17.8 plan of the ledgers before and after: open new keys, update changed severities, titles or bodies, close gone keys; so step 11 opens or updates no key that was open after step 10 with the same severity, title and body (17.8, appendix G)", p,
          f"step 11 ledger {sorted(led.get(len(G_STEPS), {}))}")

    # G10: step 11
    p = []
    oc11 = (run_recs.get("g11") or {}).get("outcome")
    if steps[-1].get("outcome") != oc11 or rec_of(11).get("outcome") != oc11:
        p.append(f"step 11: steps.json says {steps[-1].get('outcome')}, the collection record {rec_of(11).get('outcome')}, the run record {oc11}")
    if not reqs(11, "debt-total") or any(r.get("status") != 200 for r in reqs(11, "debt-total")):
        p.append(f"step 11: the debt source answers again, yet its statuses are {[r.get('status') for r in reqs(11, 'debt-total')]}")
    check("G10 step 11: the outcome the rules give, the same in steps.json, the collection record and the run record; the debt source answers again", p, f"outcome {oc11}")

    # G11: steps.json against the collection records and run records
    p = []
    for i in range(2, len(G_STEPS) + 1):
        s, v = steps[i - 1], rec_of(i)
        if not v:
            p.append(f"step {i}: no collection record runs/g{i}.json")
            continue
        for k in ("trigger", "operation", "outcome"):
            if s.get(k) != v.get(k):
                p.append(f"step {i}: steps.json {k} {s.get(k)!r}, its collection record {v.get(k)!r}")
        if v.get("started_at") != s.get("at"):
            p.append(f"step {i}: at {s.get('at')}, its record started_at {v.get('started_at')}")
    extra = sorted(set(records) - {f"g{i}" for i in range(2, len(G_STEPS) + 1)})
    if extra:
        p.append(f"collection records for runs not in appendix G: {extra}")
    check("G11 steps.json agrees with the collection records (trigger, operation, outcome, at as started_at), one record per step after the first and none other (appendix G, 21.4)", p)
