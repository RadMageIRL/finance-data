"""Self-test of the state store mode and the appendix G scenario mode (check_state.py, DATA_CONVENTIONS v0.7).

    python -I tests/datacheck/state_selftest.py <empty or new output dir>

The state store of appendix G and its scenario do not exist yet, so this builds them:

  base       a v0.7 store promoted from a byte copy of the real Stage B store
             (local/research/p26/live/state-store, read only) by this checker's reading of 21.1:
             root/ is the Stage B root's live/ and archive/ without archive/state/, state/ its state
             files, the Stage B response bodies stored content-addressed, .gitattributes,
             accepted.json and STATE.json rmf.econ.state/2; then three scheduled runs that accept
             nothing: nothing-due at 12:17 UTC, a windowed EFFR request at 16:17 (no-change), and at
             22:17 the same EFFR answer (one body stored once) with the debt source answering 500
             to the request and its three retries (no-change, source-overdue:effr). Expected: every
             state and root check passes (the promoted v0.6 files read by the three rules of 21.1).
  faults     copies of base with one fault each, and the checks expected to catch it.
  stage-b    a byte copy of the real Stage B store (the v0.6 layout, .git left out): expected to fail
             only T46, T55 and T116, the v0.6 to v0.7 differences (no accepted.json, so every rule is\n             strict); then copies with one fault each.
  legacy     the T46 reading for a root written before v0.7, with the registry's conventions set
             to v0.7 in memory.
  scenario   a fabricated appendix G folder (steps.json and store/): its collection records, run
             records, response bodies, issue plans and the root facts the G checks read (snapshots,
             manifests, holds, locks, the rollback record) follow the rows; the objects are small
             stand-ins, so the state and root checks of the final store are not asserted here, only
             the G checks. Then copies with one fault each in a row.

Standard library only. Reads the Stage B store and writes only under the output folder. Every
check run is `python -I tests/datacheck/check_p22.py --state <dir>` (or --state-scenario) in a
subprocess; the FAIL lines are compared with the expectation.
"""

import concurrent.futures
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "local" / "research" / "p26" / "live" / "state-store"
X = "live-44452072672-1"
SB = f"unpublished/{X}"


def load(name, file_name):
    spec = importlib.util.spec_from_file_location(name, HERE / file_name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CK = load("rmf_check_p22_for_selftest", "check_p22.py")
CS = load("rmf_check_state_for_selftest", "check_state.py")
ST = CK.load_state()
CK.load_holiday_table(ST)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def canon(v):
    return CK.canon_bytes(v)


class W:
    """Writes one store folder."""

    def __init__(self, base):
        self.base = Path(base)

    def put(self, rel, data):
        p = self.base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return data

    def json(self, rel, v):
        return self.put(rel, canon(v))

    def body(self, data):
        self.put(f"responses/{sha(data)[:2]}/{sha(data)}.bin", data)
        return data


def files_under(base):
    base = Path(base)
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file() and ".git" not in p.relative_to(base).parts)


def record(n, url, t, status, body, ctype="application/json;charset=utf-8", clen=None, date=None):
    host = url.split("/")[2]
    return {"n": n, "host": host, "url": url, "requested_at": t, "status": status, "content_type": ctype, "content_length": clen,
            "etag": None, "last_modified": None, "date": date, "bytes": len(body), "sha256": sha(body)}


class Num(str):
    pass


def numdumps(v):
    if isinstance(v, Num):
        return str(v)
    if isinstance(v, dict):
        return "{" + ",".join(json.dumps(k) + ":" + numdumps(x) for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ",".join(numdumps(x) for x in v) + "]"
    return json.dumps(v)


def freshness(manifest, snapshot, t):
    fr = CS.freshness_of(CK, ST, manifest, snapshot, CK.parse_utc(t))
    best = CS.expected_next_of(CK, ST, manifest, snapshot)
    return fr, CK.fmt_utc(best) if best is not None else t


VALIDATION = {"checker": {"mode": "live", "pass": 161, "fail": 0, "skip": 0}, "state": "ok"}


# ---------------------------------------------------------------------------
# base: the promoted real Stage B store and three quiet scheduled runs
# ---------------------------------------------------------------------------


def build_base(out):
    w = W(out)
    src_files = files_under(SRC)
    for f in src_files:
        if f.startswith(SB + "/"):
            w.put(f, (SRC / f).read_bytes())
    root_files = []
    for f in src_files:
        if f.startswith(SB + "/live/") or (f.startswith(SB + "/archive/") and not f.startswith(SB + "/archive/state/")):
            rel = "root/" + f[len(SB) + 1:]
            w.put(rel, (SRC / f).read_bytes())
            root_files.append(rel)
    for f in src_files:
        if f.startswith(SB + "/archive/state/"):
            w.put("state/" + f[len(SB) + len("/archive/state/"):], (SRC / f).read_bytes())
    sb_bodies = [f for f in src_files if f.startswith(SB + "/responses/") and f.endswith(".bin")]
    for f in sb_bodies:
        w.body((SRC / f).read_bytes())
    w.put(".gitattributes", CK.GITATTRIBUTES)
    mbytes = (SRC / SB / "live" / "manifest.json").read_bytes()
    manifest = json.loads(mbytes)
    snapshot = json.loads((SRC / SB / "archive" / "files" / "snapshots" / f"{manifest['snapshot']['id']}.json").read_bytes())
    ident = {"snapshot": manifest["snapshot"]["id"], "manifest_sha256": sha(mbytes)}
    t_p, t_a, t_b, t_c = "2026-11-19T10:00:00Z", "2026-11-19T12:17:00Z", "2026-11-19T16:17:00Z", "2026-11-19T22:17:00Z"
    w.json("state/accepted.json", {"schema": "rmf.econ.accepted/1", "dataset": ident,
                                   "source": {"store_commit": "0123456789abcdef0123456789abcdef01234567", "root": SB, "run": X},
                                   "verification": {"checker": {"mode": "live", "pass": 161, "fail": 0, "skip": 0}, "state": "ok", "at": "2026-11-19T09:59:30Z"},
                                   "decision": {"brief": "docs/P26_STAGE_B_ACCEPTANCE_STAGE_C.md", "decided_on": "2026-11-19"},
                                   "promoted_at": t_p, "promoted_by": "example-maintainer", "run": "op-500-1"})
    records = []
    month = 0

    def collection(run, trig, op, t0, t1, outcome, reqs, added):
        nonlocal month
        month += added[1]
        fr, nxt = freshness(manifest, snapshot, t0)
        v = {"schema": "rmf.econ.collection/1", "run": run, "trigger": trig, "operation": op, "started_at": t0, "ended_at": t1, "outcome": outcome,
             "requests": reqs, "validation": VALIDATION, "accepted": ident, "freshness": fr, "expected_next_update_by": nxt,
             "added": {"files": added[0], "bytes": added[1]}, "month_added_bytes": month}
        w.json(f"runs/{run}.json", v)
        records.append(v)
        return v

    body_bytes = sum((SRC / f).stat().st_size for f in sb_bodies)
    root_bytes = sum((out / f).stat().st_size for f in root_files)
    collection("op-500-1", "operation", "promote", t_p, "2026-11-19T10:00:05Z", "promoted", [], (len(root_files) + len(sb_bodies), root_bytes + body_bytes))

    def run_record(run, t0, t1, outcome, series, alerts, absences):
        w.json(f"state/run-records/{run}.json", {"id": run, "trigger": "schedule", "started_at": t0, "ended_at": t1, "outcome": outcome, "snapshot": None,
                                                  "series": series, "alerts": alerts, "absences": absences, "pruned": []})

    all_not_due = {s: "not-due" for s in ST.series}
    # A: nothing due (EFFR's 2026-11-18 is expected at 14:00 UTC, the debt record date at 21:15 UTC at the earliest, H.6 on 2026-11-24)
    run_record("sched-501-1", t_a, t_a, "nothing-due", all_not_due, [], [])
    collection("sched-501-1", "schedule", None, t_a, "2026-11-19T12:17:03Z", "nothing-due", [], (0, 0))
    # B: EFFR due, a 60-day window ending on the ET date 2026-11-19; the source has nothing new
    eb = (SRC / SB / "responses" / "001-markets.newyorkfed.org.bin").read_bytes()
    doc = json.loads(eb, parse_float=Num, parse_int=Num)
    doc["refRates"] = [r for r in doc["refRates"] if "2026-09-21" <= r["effectiveDate"] <= "2026-11-19"]
    effr_body = numdumps(doc).encode("utf-8")
    url_b = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2026-09-21&endDate=2026-11-19"
    w.body(effr_body)
    nd = dict(all_not_due, effr="unchanged", **{"fomc-target": "unchanged"})
    ab = [{"series": "effr", "period": p, "kind": "expected-nonpublication", "detail": "not-yet-due"} for p in ("2026-11-18", "2026-11-19")]
    run_record("sched-502-1", t_b, t_b, "no-change", nd, [], ab)
    collection("sched-502-1", "schedule", None, t_b, "2026-11-19T16:17:09Z", "no-change",
               [record(1, url_b, "2026-11-19T16:17:01Z", 200, effr_body, date="Thu, 19 Nov 2026 16:17:01 GMT")], (1, len(effr_body)))
    # C: EFFR and the debt group due; the debt source answers 500 four times; EFFR answers the same bytes
    err = b'{"error":"Internal Server Error"}'
    w.body(err)
    url_d = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?filter=record_date:gte:2026-09-21&sort=record_date&page[size]=10000&page[number]=1"
    reqs = [record(1, url_b.replace("2026-11-19&", "2026-11-19&") , "2026-11-19T22:17:01Z", 200, effr_body, date="Thu, 19 Nov 2026 22:17:01 GMT")]
    for i, ts in enumerate(("22:17:02", "22:17:04", "22:17:08", "22:17:16")):
        reqs.append(record(2 + i, url_d, f"2026-11-19T{ts}Z", 500, err, ctype="application/json", clen=str(len(err)), date=f"Thu, 19 Nov 2026 {ts} GMT"))
    nc = dict(nd, **{s: "failed" for s in ("debt-total", "debt-held-public", "debt-intragov")})
    ac = [{"series": "effr", "period": "2026-11-18", "kind": "source-overdue", "detail": "after-deadline"},
          {"series": "effr", "period": "2026-11-19", "kind": "expected-nonpublication", "detail": "not-yet-due"}]
    for s in ("debt-total", "debt-held-public", "debt-intragov"):
        ac += [{"series": s, "period": p, "kind": "expected-nonpublication", "detail": "not-yet-due"} for p in ("2026-11-18", "2026-11-19")]
    run_record("sched-503-1", t_c, t_c, "no-change", nc, ["source-overdue:effr"], ac)
    collection("sched-503-1", "schedule", None, t_c, "2026-11-19T22:17:30Z", "no-change", reqs, (1, len(err)))
    w.json("state/alerts.json", {"schema": "rmf.econ.alerts/1", "open": [
        {"key": "source-overdue:effr", "severity": "warning", "title": "Source overdue: effr",
         "body": "effr: 1 period past its deadline without a record (2026-11-18); the request succeeded.", "first_seen": t_c, "last_seen": t_c, "runs": 1}]})
    col = json.loads((SRC / "state" / "collector.json").read_bytes())
    col["full_fetches"] = {}  # 21.1: the Stage B full fetches were never recorded, so no group has an entry until a v0.7 full fetch
    col["sources"]["fiscaldata"]["consecutive_failures"] = 1
    w.json("state/collector.json", col)
    write_state(out, "sched-503-1", "2026-11-19T22:17:31Z")
    return out


def write_state(out, run, at, extra=None):
    """STATE.json rmf.econ.state/2 over the store as it is (21.2)."""
    out = Path(out)
    mb = (out / "root" / "live" / "manifest.json").read_bytes()
    m = json.loads(mb)
    files = []
    for f in files_under(out / "state"):
        if f == "STATE.json":
            continue
        b = (out / "state" / f).read_bytes()
        files.append({"path": f"state/{f}", "sha256": sha(b), "bytes": len(b)})
    v = {"schema": "rmf.econ.state/2", "run": run, "written_at": at, "root": "root", "manifest_sha256": sha(mb),
         "accepted": {"snapshot": m["snapshot"]["id"], "manifest_sha256": sha(mb)}, "files": sorted(files, key=lambda e: e["path"])}
    if extra:
        extra(v)
    W(out).json("state/STATE.json", v)


# ---------------------------------------------------------------------------
# faults on base
# ---------------------------------------------------------------------------


def edit_json(path, fn, canonical=True):
    v = json.loads(Path(path).read_bytes())
    fn(v)
    Path(path).write_bytes(canon(v) if canonical else json.dumps(v).encode())


def f_csv_crlf(d):
    for base in ("root/archive/files", "root/live"):
        p = next(q for q in sorted((d / base / "series" / "effr").rglob("*.csv")))
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))


def f_gitattributes_crlf(d):
    (d / ".gitattributes").write_bytes(b"* -text\r\n")


def f_no_gitattributes(d):
    (d / ".gitattributes").unlink()


def f_extra_state_file(d):
    W(d).json("state/notes.json", {"note": "left here by hand"})


def f_body_mismatch(d):
    p = next(q for q in (d / "responses").rglob("*.bin") if q.stat().st_size < 100)
    p.write_bytes(p.read_bytes().replace(b"Internal", b"Internai"))


def f_record_extra_field(d):
    edit_json(d / "runs" / "sched-502-1.json", lambda v: v["requests"][0].update(base="001-markets.newyorkfed.org"))


def f_record_missing_field(d):
    edit_json(d / "runs" / "sched-503-1.json", lambda v: v["requests"][2].pop("etag"))


def f_record_wrong_type(d):
    edit_json(d / "runs" / "sched-503-1.json", lambda v: v["requests"][1].update(status="500"))


def f_second_promotion(d):
    v = json.loads((d / "runs" / "op-500-1.json").read_bytes())
    v.update(run="op-600-1", started_at="2026-11-19T23:00:00Z", ended_at="2026-11-19T23:00:05Z", added={"files": 0, "bytes": 0})
    v["month_added_bytes"] = json.loads((d / "runs" / "sched-503-1.json").read_bytes())["month_added_bytes"]
    W(d).json("runs/op-600-1.json", v)
    write_state(d, "op-600-1", "2026-11-19T23:00:06Z")


def f_mismatched_accepted(d):
    edit_json(d / "state" / "STATE.json", lambda v: v["accepted"].update(manifest_sha256="f" * 64))


def f_month_bytes(d):
    edit_json(d / "runs" / "sched-503-1.json", lambda v: v.update(month_added_bytes=v["month_added_bytes"] + 1))


def f_freshness(d):
    def fn(v):
        v["freshness"][0]["status"] = "stale" if v["freshness"][0]["status"] == "fresh" else "fresh"
    edit_json(d / "runs" / "sched-502-1.json", fn)


def f_state_lists_itself(d):
    write_state(d, "sched-503-1", "2026-11-19T22:17:31Z", lambda v: v["files"].append({"path": "state/STATE.json", "sha256": "0" * 64, "bytes": 1}))


def f_accepted_unlisted(d):
    write_state(d, "sched-503-1", "2026-11-19T22:17:31Z", lambda v: v.update(files=[e for e in v["files"] if e["path"] != "state/accepted.json"]))


def f_state_file_changed(d):
    p = d / "state" / "pins.json"
    v = json.loads(p.read_bytes())
    v["pins"] = []
    v["unpinned"] = []
    v["schema"] = "rmf.econ.pins/1"
    p.write_bytes(canon(v).replace(b"}", b" }", 1))


def f_stage_b_changed(d):
    p = d / SB / "live" / "status" / "runs.json"
    p.write_bytes(p.read_bytes())
    m = d / SB / "live" / "manifest.json"
    m.write_bytes(m.read_bytes().replace(b'"days":35', b'"days":36'))


def f_unreferenced_body(d):
    W(d).body(b"a body no run received")


def f_added_root_file(d):
    edit_json(d / "runs" / "sched-502-1.json", lambda v: v["added"].update(files=v["added"]["files"] + 1, bytes=v["added"]["bytes"] + 100))


def f_root_archive_state(d):
    W(d).json("root/archive/state/alerts.json", {"open": [], "schema": "rmf.econ.alerts/1"})


def f_window_full(d):
    def fn(v):
        v["requests"][0]["url"] = v["requests"][0]["url"].replace("startDate=2026-09-21", "startDate=2000-07-03")
    edit_json(d / "runs" / "sched-502-1.json", fn)


def f_accepted_changed_by_no_change(d):
    edit_json(d / "runs" / "sched-502-1.json", lambda v: v["accepted"].update(snapshot="20261119T163000Z"))


def f_promoted_by_bot(d):
    edit_json(d / "state" / "accepted.json", lambda v: v.update(promoted_by="github-actions[bot]"))
    write_state(d, "sched-503-1", "2026-11-19T22:17:31Z")


def f_run_record_without_collection(d):
    (d / "runs" / "sched-501-1.json").unlink()


def f_collect_failed_in_ledger(d):
    def fn(v):
        v["open"].append({"key": "collect-failed", "severity": "critical", "title": "Collection failed", "body": "run sched-504-1 failed at step 3",
                          "first_seen": "2026-11-19T22:17:00Z", "last_seen": "2026-11-19T22:17:00Z", "runs": 1})
    edit_json(d / "state" / "alerts.json", fn)
    write_state(d, "sched-503-1", "2026-11-19T22:17:31Z")


def f_full_fetches_wrong(d):
    edit_json(d / "state" / "collector.json", lambda v: v["full_fetches"].update(effr="2026-11-19T16:17:00Z"))
    write_state(d, "sched-503-1", "2026-11-19T22:17:31Z")


def f_retry_body_counted_twice(d):
    edit_json(d / "runs" / "sched-503-1.json", lambda v: (v["added"].update(files=4, bytes=4 * v["requests"][1]["bytes"]), v.update(month_added_bytes=v["month_added_bytes"] + 3 * v["requests"][1]["bytes"])))


def f_run_gap_early(d):
    edit_json(d / "state" / "run-records" / "sched-503-1.json", lambda v: v["alerts"].append("scheduled-run-gap"))
    write_state(d, "sched-503-1", "2026-11-19T22:17:31Z")


def f_budget_alert_early(d):
    edit_json(d / "state" / "run-records" / "sched-503-1.json", lambda v: v["alerts"].append("budget:state-store"))
    write_state(d, "sched-503-1", "2026-11-19T22:17:31Z")


def f_promotion_body_not_stored(d):
    """21.1 (F11): the promotion stores every Stage B body; one is missing from responses/."""
    b = (SRC / SB / "responses" / "004-www.federalreserve.gov.bin").read_bytes()
    (d / "responses" / sha(b)[:2] / f"{sha(b)}.bin").unlink()


def f_promotion_added_without_bodies(d):
    """21.1 (F11): the promotion counts the Stage B bodies in its added; this one does not."""
    sb = sum(p.stat().st_size for p in (SRC / SB / "responses").glob("*.bin"))
    n = len(list((SRC / SB / "responses").glob("*.bin")))
    edit_json(d / "runs" / "op-500-1.json", lambda v: (v["added"].update(files=v["added"]["files"] - n, bytes=v["added"]["bytes"] - sb), v.update(month_added_bytes=v["month_added_bytes"] - sb)))
    for run in ("sched-501-1", "sched-502-1", "sched-503-1"):
        edit_json(d / "runs" / f"{run}.json", lambda v: v.update(month_added_bytes=v["month_added_bytes"] - sb))


SB_TIME = "2026-11-19T03:32:14Z"


def v_v07_form(d):
    """21.1: the v0.7 form before the boundary (as appendix G step 1 writes it): the Stage B
    collector.json carries full_fetches, and the runs after the promotion carry them forward."""
    edit_json(d / SB / "archive" / "state" / "collector.json", lambda v: v.update(full_fetches={"effr": SB_TIME, "debt-total": SB_TIME, "m1-sa": SB_TIME}))
    edit_json(d / "state" / "collector.json", lambda v: v.update(full_fetches={"effr": SB_TIME, "debt-total": SB_TIME, "m1-sa": SB_TIME}))
    write_state(d, "sched-503-1", "2026-11-19T22:17:31Z")


def f_carried_dropped(d):
    v_v07_form(d)
    edit_json(d / "state" / "collector.json", lambda v: v.update(full_fetches={}))
    write_state(d, "sched-503-1", "2026-11-19T22:17:31Z")


def f_full_fetches_key_missing(d):
    edit_json(d / "state" / "collector.json", lambda v: v.pop("full_fetches"))
    write_state(d, "sched-503-1", "2026-11-19T22:17:31Z")


VARIANTS = [  # copies of base that must pass every check
    ("v07-form-before-boundary", v_v07_form),
]


def f_state_run_old(d):
    write_state(d, "sched-502-1", "2026-11-19T22:17:31Z")


FAULTS = [  # name, function, checks that must FAIL, checks that may also FAIL
    ("csv-crlf", f_csv_crlf, {"T117", "ST15"}, {"ST7", "T37", "T57", "T88", "T89", "T90", "T91", "T92", "T93", "T47", "T62", "T63", "T66", "T67", "T68", "T64"}),
    ("gitattributes-crlf", f_gitattributes_crlf, {"ST1", "ST15"}, set()),
    ("no-gitattributes", f_no_gitattributes, {"ST1"}, set()),
    ("extra-state-file", f_extra_state_file, {"ST4", "ST6"}, {"T34", "T35"}),
    ("body-mismatch", f_body_mismatch, {"ST10"}, set()),
    ("record-extra-field", f_record_extra_field, {"ST9"}, set()),
    ("record-missing-field", f_record_missing_field, {"ST9"}, set()),
    ("record-wrong-type", f_record_wrong_type, {"ST9"}, set()),
    ("second-promotion", f_second_promotion, {"ST8"}, {"ST13", "ST7", "ST14"}),
    ("mismatched-accepted", f_mismatched_accepted, {"ST5", "ST12"}, set()),
    ("month-added-bytes", f_month_bytes, {"ST13"}, set()),
    ("freshness", f_freshness, {"ST14"}, set()),
    ("state-lists-itself", f_state_lists_itself, {"ST3", "ST4"}, set()),
    ("accepted-unlisted", f_accepted_unlisted, {"ST4"}, set()),
    ("state-file-changed", f_state_file_changed, {"ST4"}, {"ST6", "T34"}),
    ("stage-b-changed", f_stage_b_changed, {"ST7"}, {"ST15"}),
    ("unreferenced-body", f_unreferenced_body, {"ST10"}, {"ST13"}),
    ("added-root-file", f_added_root_file, {"ST13"}, set()),
    ("root-archive-state", f_root_archive_state, {"ST2"}, {"ST13", "T34", "T35"}),
    ("window-full", f_window_full, {"ST11"}, set()),
    ("accepted-changed-by-no-change", f_accepted_changed_by_no_change, {"ST12"}, {"ST14"}),
    ("promoted-by-bot", f_promoted_by_bot, {"ST7"}, set()),
    ("run-record-without-collection", f_run_record_without_collection, {"ST11"}, {"ST13", "ST18"}),
    ("collect-failed-in-ledger", f_collect_failed_in_ledger, {"T118", "T70"}, set()),
    ("full-fetches-wrong", f_full_fetches_wrong, {"T116"}, set()),
    ("retry-body-counted-twice", f_retry_body_counted_twice, {"ST13"}, set()),
    ("run-gap-alert-early", f_run_gap_early, {"ST18"}, {"T70", "T71"}),
    ("budget-alert-early", f_budget_alert_early, {"ST17"}, {"T70", "T71"}),
    ("state-run-old", f_state_run_old, {"ST16"}, set()),
    ("carried-full-fetches-dropped", f_carried_dropped, {"T116"}, set()),
    ("full-fetches-missing-after-boundary", f_full_fetches_key_missing, {"T116"}, set()),
    ("promotion-body-not-stored", f_promotion_body_not_stored, {"ST10"}, set()),
    ("promotion-added-without-bodies", f_promotion_added_without_bodies, {"ST13"}, set()),
]


# ---------------------------------------------------------------------------
# faults on a byte copy of the Stage B store (the v0.6 layout)
# ---------------------------------------------------------------------------


def build_stage_b(out):
    w = W(out)
    for f in files_under(SRC):
        w.put(f, (SRC / f).read_bytes())
    return Path(out)


def write_state_v1(d):
    """Rewrites a Stage B STATE.json files list over state/ as it is (20.3)."""
    p = d / "state" / "STATE.json"
    v = json.loads(p.read_bytes())
    files = []
    for f in files_under(d / "state"):
        if f != "STATE.json":
            b = (d / "state" / f).read_bytes()
            files.append({"path": f"state/{f}", "sha256": sha(b), "bytes": len(b)})
    v["files"] = sorted(files, key=lambda e: e["path"])
    p.write_bytes(canon(v))


def sb_record_extra(d):
    edit_json(d / SB / "responses" / "001-markets.newyorkfed.org.json", lambda v: v.update(base="001-markets.newyorkfed.org"))


def sb_record_ten_fields(d):
    edit_json(d / SB / "responses" / "003-www.federalreserve.gov.json", lambda v: (v.pop("n"), v.pop("host")))


def sb_body_changed(d):
    p = d / SB / "responses" / "004-www.federalreserve.gov.bin"
    p.write_bytes(p.read_bytes() + b" ")


def sb_state_not_root(d):
    """state/pins.json no longer equals the root's archive/state/pins.json; STATE.json relisted."""
    q = d / "state" / "pins.json"
    v = json.loads(q.read_bytes())
    v["pins"] = [{"snapshot": "20261119T033214Z", "site_release": "site-1", "reason": "test", "pinned_at": "2026-11-19T04:00:00Z"}]
    q.write_bytes(canon(v))
    write_state_v1(d)


def sb_unlisted(d):
    W(d).json("state/notes.json", {"note": "x"})


def sb_manifest_sha(d):
    edit_json(d / "state" / "STATE.json", lambda v: v.update(manifest_sha256="e" * 64))


def sb_csv_crlf(d):
    p = next(q for q in sorted((d / SB / "live" / "series" / "m1-sa").rglob("*.csv")))
    p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))


def sb_null_root(d):
    edit_json(d / "state" / "STATE.json", lambda v: v.update(root=None))


STAGE_B_FAULTS = [
    ("record-extra-field", sb_record_extra, {"SB7"}, set()),
    ("record-ten-fields", sb_record_ten_fields, {"SB7"}, set()),
    ("body-changed", sb_body_changed, {"SB7"}, set()),
    ("state-not-root", sb_state_not_root, {"SB4"}, {"SB3"}),
    ("unlisted-state-file", sb_unlisted, {"SB2", "SB3", "SB4"}, set()),
    ("manifest-sha", sb_manifest_sha, {"SB5"}, set()),
    ("csv-crlf", sb_csv_crlf, {"SB8", "T117"}, {"T37", "T62", "T57", "T88", "T89", "T90", "T91", "T92", "T93", "T66", "T67", "T68"}),
    ("null-root", sb_null_root, {"SB1", "SB9"}, {"SB5"}),
]


def legacy_hash_selftest():
    """The legacy reading of T46: with the committed registry's conventions set to v0.7 in memory
    (as the pipeline update will commit it), the Stage B snapshot's registry_sha256 is the hash of
    that registry with conventions v0.6, and not its v0.7 hash."""
    st = CK.load_state()
    st.registry["conventions"] = "v0.7"
    ctx = CK.root_context(st, CK.RootView(SRC / SB), None)
    snap = next(iter(ctx.snaps.values()))
    got = (snap.get("run") or {}).get("registry_sha256")
    return got == CK.rx_legacy_registry_hash(ctx) and got != CK.sha256_hex(CK.canon_bytes(st.registry)), got


# ---------------------------------------------------------------------------
# scenario: a fabricated appendix G folder
# ---------------------------------------------------------------------------

G_TIMES = [t for t, _, _, _ in CS.G_STEPS]
SID = lambda t: CK.snapshot_id_of(CK.parse_utc(t))
EFFR_URL = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate={s}&endDate={e}"
DTP_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?filter=record_date:gte:{s}&sort=record_date&page[size]=10000&page[number]=1"
ZIP_URL = "https://www.federalreserve.gov/releases/h6/data/FRB_h6_xml.zip"
DATES_URL = "https://www.federalreserve.gov/releases/h6/releaseDates.json"


def build_scenario(out):
    out = Path(out)
    w = W(out / "store")
    series = [s["id"] for s in ST.registry["series"]]

    def obj(sid, tag):
        v = {"schema": "rmf.econ.object/1", "series": sid, "segment": "all", "observations": [{"period": tag, "value": "1.00"}]}
        b = canon(v)
        path = f"objects/{sid}/all/{sha(b)[:16]}.json"
        w.put(f"root/archive/files/{path}", b)
        return {"segment": "all", "path": path, "sha256": sha(b), "bytes": len(b)}

    base_obj = {s: obj(s, "2026-11-12") for s in series}
    o4 = dict(base_obj, **{s: obj(s, "2026-11-13") for s in ("effr", "debt-total", "debt-held-public", "debt-intragov")})
    o7 = dict(o4, effr=obj("effr", "2026-11-20"))
    held_sha = "c" * 64
    lp1 = {"effr": "2026-11-12", "fomc-target": "2026-09-17", "debt-total": "2026-11-12", "debt-held-public": "2026-11-12", "debt-intragov": "2026-11-12",
           "m1-sa": "2026-09", "m2-sa": "2026-09", "m1-nsa": "2026-09", "m2-nsa": "2026-09"}
    lp4 = dict(lp1, **{s: "2026-11-13" for s in ("effr", "debt-total", "debt-held-public", "debt-intragov")})
    lp7 = dict(lp4, effr="2026-11-20")

    def snap(t, objs, lps, holds=(), frozen=(), trigger="schedule"):
        v = {"schema": "rmf.econ.snapshot/2", "id": SID(t), "created_at": t, "run": {"trigger": trigger},
             "series": {s: {"objects": [objs[s]], "last_period": lps[s], "status": "held" if any(h["series"] == s for h in holds) else "refreshed"} for s in series},
             "holds": list(holds), "frozen": list(frozen), "revisions": []}
        b = w.json(f"root/archive/files/snapshots/{SID(t)}.json", v)
        return {"id": SID(t), "path": f"snapshots/{SID(t)}.json", "sha256": sha(b)}

    def man(t, ref, rollback=None):
        v = {"schema": "rmf.econ.manifest/3", "generated_at": t, "snapshot": ref, "rollback": rollback, "series": {}}
        b = w.json(f"root/archive/manifests/{SID(t)}.json", v)
        return {"snapshot": ref["id"], "manifest_sha256": sha(b)}, b

    hold = {"series": "debt-total", "candidate": {"archive_asset": "archive-2026-11/hold-debt-total-" + held_sha[:16] + ".json", "sha256": held_sha, "bytes": 10}, "reason": "unexpected", "opened_at": G_TIMES[4]}
    fz_rej = {"series": "debt-total", "candidate_sha256": held_sha, "origin": "rejected", "frozen_at": G_TIMES[7], "reason": "rejected in review"}
    r1 = snap(G_TIMES[0], base_obj, lp1, trigger="manual")
    a1, m1b = man(G_TIMES[0], r1)
    r4 = snap(G_TIMES[3], o4, lp4)
    a4, _ = man(G_TIMES[3], r4)
    r5 = snap(G_TIMES[4], o4, lp4, holds=[hold])
    a5, _ = man(G_TIMES[4], r5)
    r7 = snap(G_TIMES[6], o7, lp7, holds=[hold])
    a7, _ = man(G_TIMES[6], r7)
    r8 = snap(G_TIMES[7], o7, lp7, frozen=[fz_rej], trigger="review")
    a8, _ = man(G_TIMES[7], r8)
    effr7 = [{"period": "2026-11-20", "value": "1.00"}]
    lock_effr = {"series": "effr", "origin": "rolled-back", "candidate_sha256": sha(canon(effr7)), "locked_changes": [{"period": "2026-11-20", "field": "period"}]}
    lock_debt = {"series": "debt-total", "origin": "rejected", "candidate_sha256": held_sha, "locked_changes": [{"period": "2019-12-31", "field": "value"}]}
    a9, m9b = man(G_TIMES[8], r4, rollback={"from": r8["id"], "to": r4["id"], "at": G_TIMES[8], "reason": "rolled back", "locked": ["effr", "debt-total"]})
    w.json(f"root/archive/rollbacks/{SID(G_TIMES[8])}.json", {"schema": "rmf.econ.rollback/1", "from": r8["id"], "to": r4["id"], "at": G_TIMES[8], "run": "g9",
                                                             "reason": "rolled back", "locks": [lock_effr, lock_debt]})
    w.put("root/live/manifest.json", m9b)
    # step 1: the Stage B record
    wb = W(out / "store" / "unpublished" / "g1")
    wb.put("live/manifest.json", m1b)
    wb.json("archive/state/run-records/g1.json", {"id": "g1", "trigger": "manual", "started_at": G_TIMES[0], "ended_at": G_TIMES[0], "outcome": "published",
                                                  "snapshot": SID(G_TIMES[0]), "series": {s: "appended" for s in series}, "alerts": [], "absences": [], "pruned": []})
    zip_body, dates_body = b"PK\x03\x04 the H.6 zip", b'[{"yearValue":"2026"}]\r\n'
    sb_bodies = []
    for n, url, body in ((1, EFFR_URL.format(s="2000-07-03", e="2026-11-16"), b'{"refRates":[1]}'), (2, DTP_URL.format(s="1993-04-01"), b'{"data":[1]}'),
                         (3, ZIP_URL, zip_body), (4, DATES_URL, dates_body)):
        host = url.split("/")[2]
        wb.put(f"responses/{n:03d}-{host}.bin", body)
        wb.json(f"responses/{n:03d}-{host}.json", record(n, url, G_TIMES[0], 200, body))
        w.body(body)
        sb_bodies.append(body)
    # collection and run records
    steps, month = [], 0
    alerts = {1: [], 3: ["source-overdue:effr"], 4: [], 5: ["hold:debt-total", "source-overdue:effr"], 6: ["hold:debt-total", "source-overdue:effr"],
              7: ["hold:debt-total"], 8: ["frozen:debt-total"], 9: ["frozen:debt-total", "frozen:effr"], 10: ["frozen:debt-total", "frozen:effr"], 11: ["frozen:debt-total", "frozen:effr"]}
    plans = {1: [], 2: [], 3: [("open", "source-overdue:effr")], 4: [("close", "source-overdue:effr")], 5: [("open", "hold:debt-total"), ("open", "source-overdue:effr")],
             6: [("update", "source-overdue:effr")], 7: [("close", "source-overdue:effr")], 8: [("close", "hold:debt-total"), ("open", "frozen:debt-total")],
             9: [("open", "frozen:effr")], 10: [], 11: []}
    texts = {"source-overdue:effr": ("warning", "Source overdue: effr"), "hold:debt-total": ("critical", "Hold: debt-total"),
             "frozen:debt-total": ("warning", "Frozen: debt-total"), "frozen:effr": ("warning", "Frozen: effr")}
    bodies = {(3, "source-overdue:effr"): "effr: 2026-11-13 is past its deadline.", (5, "source-overdue:effr"): "effr: 2026-11-16 to 2026-11-20 are past their deadlines.",
              (5, "hold:debt-total"): "debt-total held.", (8, "frozen:debt-total"): "debt-total is locked (rejected).", (9, "frozen:effr"): "effr is locked (rolled-back)."}

    def body_at(i, key):  # the latest body set at or before step i (step 6 updates source-overdue:effr)
        return next(bodies[(j, key)] for j in range(i, 0, -1) if (j, key) in bodies) if i != 6 or key != "source-overdue:effr" else "effr: 2026-11-16 to 2026-11-20 and 2026-11-23 are past their deadlines."

    def ledger_at(i):
        keys = alerts[1] if i in (1, 2) else alerts[i]
        return [{"key": k, "severity": texts[k][0], "title": texts[k][1], "body": body_at(i, k)} for k in sorted(keys)]

    accepted = {2: a1, 3: a1, 4: a4, 5: a5, 6: a5, 7: a7, 8: a8, 9: a9, 10: a9, 11: a9}
    outcome = {2: "promoted", 3: "no-change", 4: "published", 5: "published", 6: "no-change", 7: "published", 8: "published", 9: "published", 10: "published", 11: "no-change"}
    nd = {s: "not-due" for s in series}
    oc = {3: dict(nd, effr="unchanged", **{"fomc-target": "unchanged"}),
          4: dict(nd, effr="appended", **{"fomc-target": "unchanged", "debt-total": "appended", "debt-held-public": "appended", "debt-intragov": "appended"}),
          5: dict({s: "unchanged" for s in series}, **{"debt-total": "revised-unexpected"}),
          6: dict(nd, effr="unchanged", **{"fomc-target": "unchanged", "debt-total": "revised-unexpected", "debt-held-public": "unchanged", "debt-intragov": "unchanged"}),
          7: dict(nd, effr="appended", **{"fomc-target": "unchanged", "debt-total": "failed", "debt-held-public": "failed", "debt-intragov": "failed"}),
          11: dict(nd, effr="revised-unexpected", **{"fomc-target": "unchanged", "debt-total": "revised-unexpected", "debt-held-public": "unchanged", "debt-intragov": "unchanged"})}
    trig = {3: "schedule", 4: "schedule", 5: "schedule", 6: "schedule", 7: "schedule", 8: "review", 9: "rollback", 10: "restore", 11: "schedule"}
    snapid = {4: r4["id"], 5: r5["id"], 7: r7["id"], 8: r8["id"], 9: r4["id"], 10: r4["id"]}

    def win(i):
        d = CK.et_date(CK.parse_utc(G_TIMES[i - 1]))
        return (d - __import__("datetime").timedelta(days=59)).isoformat(), d.isoformat()

    reqs = {}
    s3, e3 = win(3)
    reqs[3] = [(EFFR_URL.format(s=s3, e=e3), 200, b'{"refRates":[3]}')]
    s4, e4 = win(4)
    reqs[4] = [(EFFR_URL.format(s=s4, e=e4), 200, b'{"refRates":[4]}'), (DTP_URL.format(s=s4), 200, b'{"data":[4]}')]
    _, e5 = win(5)
    reqs[5] = [(EFFR_URL.format(s="2000-07-03", e=e5), 200, b'{"refRates":[5]}'), (DTP_URL.format(s="1993-04-01"), 200, b'{"data":[5]}'),
               (ZIP_URL, 200, zip_body), (DATES_URL, 200, dates_body)]
    s6, e6 = win(6)
    reqs[6] = [(EFFR_URL.format(s=s6, e=e6), 200, b'{"refRates":[5]}'), (DTP_URL.format(s=s6), 200, b'{"data":[6]}')]
    s7, e7 = win(7)
    reqs[7] = [(EFFR_URL.format(s=s7, e=e7), 200, b'{"refRates":[7]}')] + [(DTP_URL.format(s=s7), 500, b'{"error":"500"}')] * 4
    s11, e11 = win(11)
    reqs[11] = [(EFFR_URL.format(s=s11, e=e11), 200, b'{"refRates":[7]}'), (DTP_URL.format(s=s11), 200, b'{"data":[11]}')]
    seen = {sha(b) for b in sb_bodies}
    for i in range(1, 12):
        t = G_TIMES[i - 1]
        trigger, op, _ = CS.G_STEPS[i - 1][1], CS.G_STEPS[i - 1][2], CS.G_STEPS[i - 1][3]
        entry = {"step": i, "run": f"g{i}", "trigger": trigger, "operation": op, "at": t, "outcome": "published" if i == 1 else outcome[i],
                 "record": None if i == 1 else f"runs/g{i}.json", "plan": [{"action": a, "key": k} for a, k in plans[i]], "ledger": ledger_at(i)}
        steps.append(entry)
        if i == 1:
            continue
        rl = []
        new = 0
        new_b = 0
        for n, (url, status, body) in enumerate(reqs.get(i, []), start=1):
            w.body(body)
            rl.append(record(n, url, t, status, body))
            if sha(body) not in seen:
                seen.add(sha(body))
                new += 1
                new_b += len(body)
        added = (new, new_b) if i != 2 else (1, len(m1b) + sum(len(b) for b in sb_bodies))
        month += added[1]
        w.json(f"runs/g{i}.json", {"schema": "rmf.econ.collection/1", "run": f"g{i}", "trigger": trigger, "operation": op, "started_at": t, "ended_at": t,
                                   "outcome": outcome[i], "requests": rl, "validation": VALIDATION, "accepted": accepted[i], "freshness": [],
                                   "expected_next_update_by": t, "added": {"files": added[0], "bytes": added[1]}, "month_added_bytes": month})
        if i >= 3:
            w.json(f"state/run-records/g{i}.json", {"id": f"g{i}", "trigger": trig[i], "started_at": t, "ended_at": t, "outcome": outcome[i],
                                                   "snapshot": snapid.get(i), "series": oc.get(i, {}), "alerts": alerts[i], "absences": [], "pruned": []})
    w.json("state/run-records/g1.json", json.loads((out / "store" / "unpublished" / "g1" / "archive" / "state" / "run-records" / "g1.json").read_bytes()))
    first = {"frozen:debt-total": (G_TIMES[7], 4), "frozen:effr": (G_TIMES[8], 3)}
    w.json("state/alerts.json", {"schema": "rmf.econ.alerts/1", "open": [dict(e, first_seen=first[e["key"]][0], last_seen=G_TIMES[10], runs=first[e["key"]][1]) for e in ledger_at(11)]})
    W(out / "store" / "unpublished" / "g1").json("archive/state/alerts.json", {"open": [], "schema": "rmf.econ.alerts/1"})
    w.json("state/accepted.json", {"schema": "rmf.econ.accepted/1", "dataset": a1, "source": {"store_commit": "1" * 40, "root": "unpublished/g1", "run": "g1"},
                                   "verification": {"checker": {"mode": "live", "pass": 100, "fail": 0, "skip": 0}, "state": "ok", "at": G_TIMES[1]},
                                   "decision": {"brief": "docs/P26_STAGE_B_ACCEPTANCE_STAGE_C.md", "decided_on": "2026-11-19"},
                                   "promoted_at": G_TIMES[1], "promoted_by": "example-maintainer", "run": "g2"})
    w.put(".gitattributes", CK.GITATTRIBUTES)
    write_state(out / "store", "g11", G_TIMES[10])
    (out / "steps.json").write_bytes(canon(steps))
    return out


def edit_steps(d, fn):
    p = d / "steps.json"
    v = json.loads(p.read_bytes())
    fn(v)
    p.write_bytes(canon(v))


def sf_time(d):
    edit_steps(d, lambda v: v[3].update(at="2026-11-17T01:17:00Z"))


def sf_step3_adds_root(d):
    edit_json(d / "store" / "runs" / "g3.json", lambda v: v["added"].update(files=v["added"]["files"] + 1))


def sf_zip_new(d):
    def fn(v):
        r = next(x for x in v["requests"] if x["url"].endswith(".zip"))
        body = b"PK\x03\x04 another zip"
        W(d / "store").body(body)
        r.update(bytes=len(body), sha256=sha(body))
    edit_json(d / "store" / "runs" / "g5.json", fn)


def sf_step6_full(d):
    edit_json(d / "store" / "runs" / "g6.json", lambda v: v["requests"][0].update(url=EFFR_URL.format(s="2000-07-03", e="2026-11-22")))


def sf_step6_h6(d):
    def fn(v):
        body = b"PK\x03\x04 the H.6 zip"
        v["requests"].append(record(len(v["requests"]) + 1, ZIP_URL, G_TIMES[5], 200, body))
    edit_json(d / "store" / "runs" / "g6.json", fn)


def sf_three_retries(d):
    edit_json(d / "store" / "runs" / "g7.json", lambda v: v.update(requests=v["requests"][:-1]))


def sf_rollback_drops_rejection(d):
    p = d / "store" / "root" / "archive" / "rollbacks" / f"{SID(G_TIMES[8])}.json"
    edit_json(p, lambda v: v.update(locks=[x for x in v["locks"] if x["series"] != "debt-total"]))


def sf_reopen_at_11(d):
    edit_steps(d, lambda v: v[10].update(plan=[{"action": "open", "key": "frozen:effr"}]))


def sf_restore_changes_accepted(d):
    edit_json(d / "store" / "runs" / "g10.json", lambda v: v.update(accepted={"snapshot": SID(G_TIMES[7]), "manifest_sha256": v["accepted"]["manifest_sha256"]}))


def sf_reject_origin(d):
    p = d / "store" / "root" / "archive" / "files" / "snapshots" / f"{SID(G_TIMES[7])}.json"
    edit_json(p, lambda v: v["frozen"][0].update(origin="rolled-back"))


def sf_duplicate_open(d):
    edit_steps(d, lambda v: v[4].update(plan=v[4]["plan"] + [{"action": "open", "key": "hold:debt-total"}]))


def sf_update_same_text_at_11(d):
    edit_steps(d, lambda v: v[10].update(plan=[{"action": "update", "key": "frozen:effr"}]))


def sf_ledger_not_final(d):
    edit_json(d / "store" / "state" / "alerts.json", lambda v: v["open"][0].update(body="changed after the run"))
    write_state(d / "store", "g11", G_TIMES[10])


def sf_step6_no_update(d):
    edit_steps(d, lambda v: v[5].update(plan=[]))


def sf_steps_extra_field(d):
    edit_steps(d, lambda v: v[0].update(collection_record=None))


def sf_steps_object(d):
    p = d / "steps.json"
    p.write_bytes(canon({"steps": json.loads(p.read_bytes())}))


SCENARIO_FAULTS = [
    ("time", sf_time, {"G1", "G11"}),
    ("step3-adds-root", sf_step3_adds_root, {"G3"}),
    ("zip-new-at-5", sf_zip_new, {"G5"}),
    ("step6-full", sf_step6_full, {"G6"}),
    ("step6-h6", sf_step6_h6, {"G6"}),
    ("three-retries", sf_three_retries, {"G7"}),
    ("rollback-drops-rejection", sf_rollback_drops_rejection, {"G8"}),
    ("reopen-at-11", sf_reopen_at_11, {"G9"}),
    ("restore-changes-accepted", sf_restore_changes_accepted, {"G8"}),
    ("reject-origin", sf_reject_origin, {"G8"}),
    ("duplicate-open", sf_duplicate_open, {"G9"}),
    ("update-same-text-at-11", sf_update_same_text_at_11, {"G9"}),
    ("ledger-not-final", sf_ledger_not_final, {"G9"}),
    ("step6-update-missing", sf_step6_no_update, {"G9"}),
    ("steps-extra-field", sf_steps_extra_field, {"G0"}),
    ("steps-not-array", sf_steps_object, {"G0"}),
]


# ---------------------------------------------------------------------------


def run_check(args, log):
    proc = subprocess.run([sys.executable, "-I", str(HERE / "check_p22.py")] + args, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    Path(log).write_text(proc.stdout + proc.stderr, encoding="utf-8", newline="\n")
    fails = {ln.split(" ", 2)[1] for ln in proc.stdout.splitlines() if ln.startswith("FAIL ")}
    aborted = [ln for ln in proc.stdout.splitlines() if "section aborted" in ln]
    summary = next((ln for ln in proc.stdout.splitlines() if ln.startswith("SUMMARY")), "")
    return proc.returncode, fails, aborted, summary


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    out = Path(argv[0]).resolve()
    if out.exists() and any(out.iterdir()):
        print(f"refused: {out} is not empty")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    print(f"state_selftest.py: building under {out}")
    base = build_base(out / "base")
    jobs = [("base", ["--state", str(base)], out / "base.log")]
    for name, fn in VARIANTS:
        d = out / "variants" / name
        shutil.copytree(base, d)
        fn(d)
        jobs.append(("v:" + name, ["--state", str(d)], out / "variants" / f"{name}.log"))
    # 21.1: the promotion's live check runs on a working copy of the named root holding, in
    # archive/state/, the store's state files and the accepted.json about to be written, whose
    # verification counts are provisional (pass 1, fail 0, skip 0).
    wc = out / "promotion-working-copy"
    shutil.copytree(base / SB, wc, ignore=shutil.ignore_patterns("responses", "comparison.*", "summary.json"))
    acc = json.loads((base / "state" / "accepted.json").read_bytes())
    acc["verification"]["checker"] = {"mode": "live", "pass": 1, "fail": 0, "skip": 0}
    W(wc).json("archive/state/accepted.json", acc)
    jobs.append(("promotion-working-copy", ["--root", str(wc), "--live"], out / "promotion-working-copy.log"))
    bare = out / "promotion-bare-root"
    shutil.copytree(base / SB, bare, ignore=shutil.ignore_patterns("responses", "comparison.*", "summary.json"))
    jobs.append(("promotion-bare-root", ["--root", str(bare), "--live"], out / "promotion-bare-root.log"))
    for name, fn, _, _ in FAULTS:
        d = out / "faults" / name
        shutil.copytree(base, d)
        fn(d)
        jobs.append((name, ["--state", str(d)], out / "faults" / f"{name}.log"))
    sbb = build_stage_b(out / "stage-b")
    jobs.append(("stage-b", ["--state", str(sbb)], out / "stage-b.log"))
    for name, fn, _, _ in STAGE_B_FAULTS:
        d = out / "stage-b-faults" / name
        shutil.copytree(sbb, d)
        fn(d)
        jobs.append(("sb:" + name, ["--state", str(d)], out / "stage-b-faults" / f"{name}.log"))
    sc = build_scenario(out / "scenario")
    jobs.append(("scenario", ["--state-scenario", str(sc)], out / "scenario.log"))
    for name, fn, _ in SCENARIO_FAULTS:
        d = out / "scenario-faults" / name
        shutil.copytree(sc, d)
        fn(d)
        jobs.append(("sf:" + name, ["--state-scenario", str(d)], out / "scenario-faults" / f"{name}.log"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        results = dict(zip([j[0] for j in jobs], ex.map(lambda j: run_check(j[1], j[2]), jobs)))
    passes, fails = 0, []

    def expect(label, cond, detail=""):
        nonlocal passes
        if cond:
            passes += 1
            print(f"PASS {label}")
        else:
            fails.append(label)
            print(f"FAIL {label}: {detail}")

    code, base_fails, aborted, summ = results["base"]
    expect("base: the promoted Stage B store with three quiet runs passes every state and root check (the v0.6 files read by the three rules of 21.1)",
           base_fails == set() and not aborted, f"{summ}; FAIL {sorted(base_fails)}; aborted {aborted[:2]}")
    expect("base: exit code 0", code == 0, code)
    code, got, aborted, summ = results["promotion-working-copy"]
    expect("promotion working copy: the Stage B root with the store's state files and the provisional accepted.json passes the live mode (21.1: the boundary applies)", not got and not aborted and code == 0, f"{summ}; FAIL {sorted(got)}")
    code, got, aborted, summ = results["promotion-bare-root"]
    expect("the bare Stage B root without accepted.json is strict: T46, T55 and T116 fail (21.1)", got == {"T46", "T55", "T116"} and code == 1, f"{summ}; FAIL {sorted(got)}")
    for name, _ in VARIANTS:
        code, got, aborted, summ = results["v:" + name]
        expect(f"variant {name}: passes every check (21.1: either form before the boundary)", not got and not aborted and code == 0, f"{summ}; FAIL {sorted(got)}")
    for name, _, must, may in FAULTS:
        code, got, aborted, summ = results[name]
        new = got - base_fails
        expect(f"fault {name}: caught by {sorted(must)}" + (f" (may also fail {sorted(may)})" if may else ""),
               must <= new and new <= must | may and not aborted and code == 1,
               f"new FAIL {sorted(new)}; expected {sorted(must)}; aborted {aborted[:1]}")
    code, sb_fails, aborted, summ = results["stage-b"]
    expect("stage-b: a byte copy of the real Stage B store (no accepted.json, so strict) fails only the v0.6 to v0.7 differences T46, T55 and T116",
           sb_fails == {"T46", "T55", "T116"} and not aborted, f"{summ}; FAIL {sorted(sb_fails)}")
    for name, _, must, may in STAGE_B_FAULTS:
        code, got, aborted, summ = results["sb:" + name]
        new = got - sb_fails
        expect(f"stage-b fault {name}: caught by {sorted(must)}" + (f" (may also fail {sorted(may)})" if may else ""),
               must <= new and new <= must | may and not aborted and code == 1, f"new FAIL {sorted(new)}; expected {sorted(must)}; aborted {aborted[:1]}")
    ok, got = legacy_hash_selftest()
    expect("legacy reading of T46: with the registry's conventions set to v0.7 in memory, the Stage B snapshot carries the hash of the same registry with conventions v0.6", ok, got)
    code, sc_fails, aborted, summ = results["scenario"]
    g_fails = {x for x in sc_fails if x.startswith("G")}
    expect("scenario: the fabricated appendix G folder passes every G check (its stand-in root is not asserted)", not g_fails and not [a for a in aborted if a.startswith(("FAIL G", "FAIL state"))], f"G FAIL {sorted(g_fails)}; aborted {aborted[:2]}")
    for name, _, must in SCENARIO_FAULTS:
        code, got, aborted, summ = results["sf:" + name]
        new = {x for x in got if x.startswith("G")} - g_fails
        expect(f"scenario fault {name}: caught by {sorted(must)}", new == must and not [a for a in aborted if a.startswith(("FAIL G", "FAIL state"))], f"new G FAIL {sorted(new)}; aborted {aborted[:1]}")
    print(f"SELFTEST {passes} PASS, {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
