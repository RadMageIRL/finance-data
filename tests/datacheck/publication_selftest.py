"""Self-test of the v0.8 modes of the independent checker (DATA_CONVENTIONS v0.8).

    python -I tests/datacheck/publication_selftest.py <empty or new output dir>

Nothing of Stage D exists yet, so this builds it from the text, on a byte copy of the accepted
state store (local/research/p27/observe/state, read only; its .git is left out):

  reg8       the committed registry with the three v0.8 substitutions of 22.9 applied, used with
             --registry, so that the I7 derivation is exercised (the committed registry is v0.7)
  v08        the store with two v0.8 runs that each write a snapshot with the current registry and a
             manifest/4 (9): deadline and stale_at, revision_csvs, rules, the registry versions of the
             window, the holiday copy, the notice file and NOTICE.txt, the New York Fed CSVs at new
             paths (22.9); STATE.json restated; the private deployment log, a copy of release A's
             log with its post fixed (22.4). The snapshots copy the accepted one, so checks that
             follow a real run (T45, T82, ST12 and the like) fail by construction; only the v0.8
             checks are asserted in the state mode.
  releases   A (dataset a, entry 1) and B (dataset b, entry 2, extending A's log): the chain of 22.4.
  artifact   econ/ and artifact.tar.gz of dataset b with A as the newest earlier release: the
             publication mode with no FAIL; then faults, each caught by the expected P checks.
  redeploy   a redeploy of a (entry 1, a verified pair) with B as the newest earlier release.
  release    the release mode on B, with and without A; faults. The release history (22.7) on A and B.
  scenario   a fabricated appendix J folder (19 steps: steps.json, releases/, production/, store/)
             following the rows, with datasets made by cloning the accepted snapshot; then faults.

Standard library only. Writes only under the output folder. Every check run is a subprocess of
`python -I tests/datacheck/check_p22.py --registry <reg8> ...`; the FAIL ids are compared with the
expectation.
"""

import concurrent.futures
import hashlib
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "local" / "research" / "p27" / "observe" / "state"


def load(name, file_name):
    spec = importlib.util.spec_from_file_location(name, HERE / file_name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CK = load("rmf_check_p22_for_pubtest", "check_p22.py")
CP = load("rmf_check_publication_for_pubtest", "check_publication.py")
RESULTS = []
GEN_A, GEN_B = "2026-11-21T04:17:00Z", "2026-11-21T08:17:00Z"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def canon(doc):
    return CK.canon_bytes(doc)


def load_json(path):
    return CK.load_strict(Path(path).read_bytes())


def copy_store(src, dst):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git"))


def make_reg8(out):
    reg = json.loads(CK.REGISTRY.read_text(encoding="utf-8"))
    reg["conventions"] = "v0.8"
    for k, s in reg["sources"].items():
        s["terms_checked"] = CK.TERMS_CHECKED_V08
        if k == CK.NYFED:
            s["terms_url"] = CK.NYFED_TERMS_V08
    write(out / "econ.json", (json.dumps(reg, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    shutil.copyfile(CK.REGISTRY.parent / "fed-holidays.json", out / "fed-holidays.json")
    return out / "econ.json"


def restate(store):
    """STATE.json after a change under state/ or root/live/manifest.json (21.2)."""
    desc = load_json(store / "state" / "STATE.json")
    files = []
    for x in sorted((store / "state").rglob("*")):
        rel = x.relative_to(store).as_posix()
        if x.is_file() and rel != "state/STATE.json":
            data = x.read_bytes()
            files.append({"path": rel, "sha256": sha(data), "bytes": len(data)})
    files.sort(key=lambda e: e["path"])
    m = (store / "root" / "live" / "manifest.json").read_bytes()
    desc["files"] = files
    desc["manifest_sha256"] = sha(m)
    desc["accepted"] = {"snapshot": CK.load_strict(m)["snapshot"]["id"], "manifest_sha256": sha(m)}
    write(store / "state" / "STATE.json", canon(desc))


def v08_run(store, st8, base, gen, mutate=None, rewrite_nyfed=True, write_notice_txt=True, new_snapshot=True, snap_registry=None, run_reg=None):
    """A v0.8 run by the checker's reading of 8, 9, 10 and 22.9: a snapshot with the current registry
    (a copy of the base manifest's) and a manifest/4, into root/live and root/archive."""
    live, arch = store / "root" / "live", store / "root" / "archive" / "files"
    reg = run_reg or st8.registry  # 22.9 (I44): the registry this run uses, possibly edited within v0.8
    m = json.loads(json.dumps(base))
    snap = load_json(live / m["snapshot"]["path"])
    if new_snapshot:
        sid = CK.snapshot_id_of(CK.parse_utc(gen))
        snap = json.loads(json.dumps(snap))
        newest = sorted(x.stem for x in (arch / "snapshots").glob("*.json"))[-1]
        snap.update(id=sid, created_at=gen, previous=newest)
        snap["run"] = dict(snap["run"], id=f"sched-v08-{sid}", attempt=1, trigger="schedule", registry_sha256=snap_registry or sha(canon(reg)))
        for state in snap["series"].values():
            state["attempt"] = dict(state.get("attempt") or {}, at=gen)
        snap["notices"] = {k: {f: reg["sources"][k].get(f) for f in ("attribution", "notice", "terms_url")} for k in snap["notices"]}
        sb = canon(snap)
        write(live / f"snapshots/{sid}.json", sb)
        write(arch / f"snapshots/{sid}.json", sb)
        m["snapshot"] = {"id": sid, "path": f"snapshots/{sid}.json", "sha256": sha(sb)}
    m["schema"] = CK.MANIFEST_V4
    m["generated_at"] = gen
    m["previous_snapshot"] = base["snapshot"]["id"]
    m["rollback"] = None
    dl = CK.v08_expect_deadlines(st8, snap)
    for sid_, summ in m["series"].items():
        summ["deadline"], summ["stale_at"] = dl[sid_]
        summ["revision_csvs"] = []
        for r in summ.get("revisions", []):
            log = load_json(arch / r["path"])
            data = CK.revision_csv_bytes(st8.registry, st8.series[sid_], log["year"], log["records"])
            path = r["path"].rsplit("/", 1)[0] + f"/{sha(data)[:16]}.csv"
            write(live / path, data)
            write(arch / path, data)
            summ["revision_csvs"].append({"path": path, "sha256": sha(data)})
        if rewrite_nyfed and st8.series[sid_]["source"] == CK.NYFED:
            objs = {o["segment"]: o for o in snap["series"][sid_]["objects"]}
            new = []
            for c in summ["csvs"]:
                obj = load_json(arch / objs[c["segment"]]["path"])
                data = CK.csv_segment_bytes(st8, st8.series[sid_], obj["observations"], c["segment"], c["retrieved_at"])
                path = f"series/{sid_}/{c['segment']}/{sha(data)[:16]}.csv"
                write(live / path, data)
                write(arch / path, data)
                new.append(dict(c, path=path, sha256=sha(data)))
            summ["csvs"] = new
    regb, holb, noteb = canon(reg), canon(st8.holiday_doc), CK.notice_file_bytes(reg, gen)
    rules = {"registry": {"path": f"registry/econ-{sha(regb)[:16]}.json", "sha256": sha(regb)},
             "holidays": {"path": f"registry/holidays-{sha(holb)[:16]}.json", "sha256": sha(holb)},
             "notice": {"path": f"notices/{sha(noteb)[:16]}.txt", "sha256": sha(noteb)}, "registry_versions": []}
    for data, ref in ((regb, rules["registry"]), (holb, rules["holidays"]), (noteb, rules["notice"])):
        write(live / ref["path"], data)
        write(arch / ref["path"], data)
    if write_notice_txt:
        write(live / "NOTICE.txt", noteb)
    by_hash = CK.registry_by_hash(st8)
    hashes = {load_json(x)["run"]["registry_sha256"] for x in (arch / "snapshots").glob("*.json")}
    for h in sorted(hashes - {sha(regb)}):
        path = f"registry/econ-{h[:16]}.json"
        data = by_hash[h][1] if h in by_hash else (arch / path).read_bytes()  # 22.9 (I44): the archived copy of an earlier v0.8 run
        write(live / path, data)
        write(arch / path, data)
        rules["registry_versions"].append({"path": path, "sha256": h})
    rules["registry_versions"].sort(key=lambda r: r["path"])
    m["rules"] = rules
    if mutate:
        mutate(m)
    data = canon(m)
    write(live / "manifest.json", data)
    write(store / "root" / "archive" / "manifests" / (CK.snapshot_id_of(CK.parse_utc(gen)) + ".json"), data)
    return m, data


def entry(n, ds, prev, at, run, trig="manual", post=None, commit=CP.ZERO_COMMIT, art=None, checker=None):
    x, a = run[4:].rsplit("-", 1)
    return {"number": n, "published_at": at, "run": run, "trigger": trig, "dataset": ds, "release": f"data-{ds['snapshot']}-{x}-{a}",
            "site_commit": commit, "artifact": art or {"files": 1, "bytes": 1, "sha256": "e" * 64}, "previous": prev,
            "verification": {"checker": checker or {"pass": 200, "fail": 0, "skip": 0}, "post": post}}


def fixed(log, post):
    """22.4: the log with its last entry's post fixed."""
    x = json.loads(json.dumps(log))
    if x["deployments"]:
        x["deployments"][-1]["verification"]["post"] = post
    return x


def live_tree(store):
    return {x.relative_to(store / "root" / "live").as_posix(): x.read_bytes() for x in sorted((store / "root" / "live").rglob("*")) if x.is_file()}


def build_artifact(tree, prev_log, ds, at, run, trig="manual", commit=CP.ZERO_COMMIT, prev_post="passed", log_override=None, checker=None):
    """The artifact of 22.3 and its log (22.4): the newest earlier release's log with its last post fixed, plus one entry."""
    files = dict(tree)
    files.pop(CP.DEPLOY_LOG, None)
    base = fixed(prev_log, prev_post) if prev_log else {"schema": CK.DEPLOYMENTS_ID, "deployments": []}
    deps = base["deployments"]
    a_sha, a_n, a_b = CP.artifact_sha(files)
    new = entry(len(deps) + 1, ds, deps[-1]["dataset"] if deps else None, at, run, trig=trig, commit=commit, art={"files": a_n, "bytes": a_b, "sha256": a_sha}, checker=checker)
    log = log_override(deps, new) if log_override else {"schema": CK.DEPLOYMENTS_ID, "deployments": deps + [new]}
    files[CP.DEPLOY_LOG] = canon(log)
    return files, log


def write_release(folder, files, tgz=None, sums=None, extra=None):
    if folder.exists():
        shutil.rmtree(folder)
    assets = {"artifact.tar.gz": tgz if tgz is not None else CP.build_targz(files), "manifest.json": files["manifest.json"], "deployments.json": files[CP.DEPLOY_LOG]}
    assets["SHA256SUMS"] = sums if sums is not None else "".join(f"{sha(assets[n])}  {n}\n" for n in sorted(assets)).encode()
    assets.update(extra or {})
    for n, data in assets.items():
        write(folder / n, data)
    return folder


def write_tree(files, out):
    if out.exists():
        shutil.rmtree(out)
    for f, data in files.items():
        write(out / "econ" / f, data)
    return out


def run_checker(args):
    r = subprocess.run([sys.executable, "-I", str(HERE / "check_p22.py")] + [str(a) for a in args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    fails = {line.split()[1].rstrip(":") for line in r.stdout.splitlines() if line.startswith("FAIL ")}
    summary = [x for x in r.stdout.splitlines() if x.startswith("SUMMARY")]
    return r.returncode, fails, summary[-1] if summary else r.stdout[-400:] + r.stderr[-400:], r.stdout


def expect(label, args, want, only=None, log=None):
    code, fails, summary, out = run_checker(args)
    got = fails if only is None else {f for f in fails if f in only}
    ok = got == set(want)
    RESULTS.append((ok, label, sorted(got), sorted(want), summary))
    if log is not None:
        write(log, out.encode("utf-8"))
    return ok


def mutate_store(src, dst, fn):
    copy_store(src, dst)
    fn(dst)
    return dst


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    reg8 = make_reg8(out / "reg8")
    CK.REGISTRY = reg8
    st8 = CK.load_state()
    CK.load_holiday_table(st8)
    R = ["--registry", reg8]
    jobs = []

    # --- the v0.8 store, releases A and B ---
    store = out / "v08" / "store"
    copy_store(SRC, store)
    m3 = load_json(store / "root" / "live" / "manifest.json")
    ma, ba = v08_run(store, st8, m3, GEN_A)
    dsa = {"snapshot": ma["snapshot"]["id"], "manifest_sha256": sha(ba)}
    tree_a = live_tree(store)
    files_a, log_a = build_artifact(tree_a, None, dsa, "2026-11-21T05:00:00Z", "pub-800-1")
    rel_a = write_release(out / "releases" / f"data-{dsa['snapshot']}-800-1", files_a)
    mb, bb = v08_run(store, st8, ma, GEN_B)
    dsb = {"snapshot": mb["snapshot"]["id"], "manifest_sha256": sha(bb)}
    write(store / "state" / "deployments.json", canon(fixed(log_a, "passed")))  # 22.4: the collection run's copy
    restate(store)
    tree_b = live_tree(store)
    files_b, log_b = build_artifact(tree_b, log_a, dsb, "2026-11-21T09:00:00Z", "pub-900-1")
    rel_b = write_release(out / "releases" / f"data-{dsb['snapshot']}-900-1", files_b)

    # --- the state mode on the v0.8 store: the v0.8 checks are asserted ---
    V08 = {"T33", "T35", "T37", "T40", "T46", "T62", "T63", "T66", "T67", "T68", "T117", "T119", "T120", "T121", "T122", "T123", "T124", "T125",
           "ST4", "ST6", "ST20", "R2", "R31", "S7", "C10", "C11", "C12", "C13", "C14", "C15", "C16", "C17", "C18", "T57", "T87", "T88", "T89", "T90", "T91", "T92", "T93"}
    jobs.append(("state mode, v0.8 store (the v0.8 checks asserted)", R + ["--state", store], set(), V08, out / "logs" / "state-v08.log"))
    jobs.append(("plain mode with the v0.8 registry", R, set(), None, out / "logs" / "plain-reg8.log"))

    def fs(name, fn, want):
        d = mutate_store(store, out / "state-faults" / name, fn)
        jobs.append((f"state fault: {name}", R + ["--state", d], want, V08, None))

    def rerun(mutate=None, rewrite=True, base_gen=GEN_A, gen="2026-11-21T12:17:00Z", new_snapshot=True):
        def go(d):
            base = load_json(d / "root" / "archive" / "manifests" / (CK.snapshot_id_of(CK.parse_utc(base_gen)) + ".json"))
            v08_run(d, st8, base, gen, mutate=mutate, rewrite_nyfed=rewrite, new_snapshot=new_snapshot)
            restate(d)
        return go

    fs("control-third-run", rerun(base_gen=GEN_B), set())
    fs("deadline-wrong", rerun(lambda m: m["series"]["effr"].update(deadline="2026-11-30T20:00:00Z"), base_gen=GEN_B), {"T120"})
    fs("stale-at-wrong", rerun(lambda m: m["series"]["debt-total"].update(stale_at="2026-11-30T20:00:00Z"), base_gen=GEN_B), {"T120"})
    fs("registry-version-missing", rerun(lambda m: m["rules"]["registry_versions"].pop(), base_gen=GEN_B), {"T122"})
    fs("own-registry-not-the-snapshot's", rerun(lambda m: m["rules"].update(registry=m["rules"]["registry_versions"][0]), base_gen=GEN_B), {"T122"})

    def pending(d):
        rerun(base_gen=GEN_B)(d)
        m = load_json(d / "root" / "live" / "manifest.json")
        bad = (d / "root" / "live" / m["rules"]["notice"]["path"]).read_bytes().replace(CK.NOTICE_STATEMENT.encode(), b"RadMage Finance terms for its own compilation: pending.")
        newp = f"notices/{sha(bad)[:16]}.txt"
        for b in ("live", "archive/files"):
            write(d / "root" / b / newp, bad)
        m["rules"]["notice"] = {"path": newp, "sha256": sha(bad)}
        data = canon(m)
        write(d / "root" / "live" / "manifest.json", data)
        write(d / "root" / "archive" / "manifests" / "20261121T121700Z.json", data)
        write(d / "root" / "live" / "NOTICE.txt", bad)
        restate(d)
    fs("notice-file-old-placeholder", pending, {"T122"})
    fs("notice-txt-differs", lambda d: write(d / "root" / "live" / "NOTICE.txt", b"other\n"), {"T123", "T66"})
    fs("notice-txt-archived", lambda d: write(d / "root" / "archive" / "files" / "NOTICE.txt", (d / "root" / "live" / "NOTICE.txt").read_bytes()), {"T123", "T63"})

    def not_rewritten(d):
        v08_run(d, st8, m3, "2026-11-21T12:17:00Z", rewrite_nyfed=False)
        restate(d)
    fs("nyfed-csv-old-terms-in-a-manifest-4", not_rewritten, {"T57", "T40"})

    def v3_after_v4(d):
        m = json.loads(json.dumps(m3))
        m["generated_at"] = "2026-11-21T12:17:00Z"
        m["previous_snapshot"] = dsb["snapshot"]
        m["snapshot"] = load_json(d / "root" / "live" / "manifest.json")["snapshot"]
        data = canon(m)
        write(d / "root" / "live" / "manifest.json", data)
        write(d / "root" / "archive" / "manifests" / "20261121T121700Z.json", data)
        (d / "root" / "live" / "NOTICE.txt").unlink()
        restate(d)
    fs("manifest-3-after-4", v3_after_v4, {"T119", "T33", "T40"})

    def bad_log(d, fn):
        doc = load_json(d / "state" / "deployments.json")
        fn(doc)
        write(d / "state" / "deployments.json", canon(doc))
        restate(d)
    fs("private-log-numbering", lambda d: bad_log(d, lambda doc: doc["deployments"][0].update(number=2)), {"ST20"})
    fs("private-log-newest-post-null (its run in progress, 22.4)", lambda d: bad_log(d, lambda doc: doc["deployments"][0]["verification"].update(post=None)), set())

    def earlier_null(doc):
        two = fixed(log_b, "passed")
        two["deployments"][0]["verification"]["post"] = None
        doc.update(two)
    fs("private-log-earlier-post-null", lambda d: bad_log(d, earlier_null), {"ST20"})

    def no_log(d):
        (d / "state" / "deployments.json").unlink()
        restate(d)
    fs("private-log-missing", no_log, {"ST20"})

    def bad_pin(d):
        doc = load_json(d / "state" / "pins.json")
        doc["pins"].append({"snapshot": dsa["snapshot"], "site_release": "0.2.0", "reason": "asked by radmageirl@radmagelabs.com", "pinned_at": "2026-11-21T09:00:00Z"})
        write(d / "state" / "pins.json", canon(doc))
        restate(d)
    fs("pin-reason-email", bad_pin, {"T124"})

    CS = load("rmf_check_state_for_pubtest", "check_state.py")
    ST_OPS = V08 | {"ST8", "ST9", "ST11", "ST13", "ST14", "ST16"}

    def pin_op(op="pin", outcome="no-change", run_record=False, record_pin=True):
        def go(d):
            t = "2026-11-21T09:30:00Z"
            rid = f"op-{op}-1"
            pins = load_json(d / "state" / "pins.json")
            if record_pin:
                pins["pins"].append({"snapshot": dsb["snapshot"], "site_release": "0.2.0", "reason": "Pinned for site release 0.2.0.", "pinned_at": t})
                if op == "unpin":
                    pins["pins"].pop()
                    pins["unpinned"].append({"snapshot": dsb["snapshot"], "reason": "Released after site release 0.2.1.", "unpinned_at": t})
            write(d / "state" / "pins.json", canon(pins))
            recs = sorted((load_json(x) for x in (d / "runs").glob("*.json")), key=lambda v: v["started_at"])
            m = load_json(d / "root" / "live" / "manifest.json")
            snap = load_json(d / "root" / "live" / m["snapshot"]["path"])
            now = CK.parse_utc(t)
            fresh = CS.freshness_of(CK, st8, m, snap, now)
            nxt = CS.expected_next_of(CK, st8, m, snap)
            month = sum(v["added"]["bytes"] for v in recs if CK.et_date(CK.parse_utc(v["started_at"])).strftime("%Y-%m") == CK.et_date(now).strftime("%Y-%m"))
            rec = dict(recs[-1], run=rid, trigger="operation", operation=op, started_at=t, ended_at=t, outcome=outcome, requests=[],
                       accepted={"snapshot": m["snapshot"]["id"], "manifest_sha256": sha((d / "root" / "live" / "manifest.json").read_bytes())},
                       freshness=fresh, expected_next_update_by=CK.fmt_utc(nxt) if nxt else t, added={"files": 0, "bytes": 0}, month_added_bytes=month)
            write(d / "runs" / f"{rid}.json", canon(rec))
            if run_record:
                rr = load_json(sorted((d / "state" / "run-records").glob("*.json"))[-1])
                write(d / "state" / "run-records" / f"{rid}.json", canon(dict(rr, id=rid, started_at=t, ended_at=t, outcome="no-change")))
            restate(d)
            desc = load_json(d / "state" / "STATE.json")
            desc.update(run=rid, written_at=t)
            write(d / "state" / "STATE.json", canon(desc))
        return go

    def fso(name, fn, want):
        dd = mutate_store(store, out / "state-faults" / name, fn)
        jobs.append((f"state operation: {name}", R + ["--state", dd], want, ST_OPS, None))
    fso("pin-no-change-no-run-record", pin_op(), set())
    fso("unpin-no-change", pin_op("unpin"), set())
    fso("pin-with-a-run-record", pin_op(run_record=True), {"ST11"})
    fso("pin-outcome-published", pin_op(outcome="published"), {"ST9"})
    fso("pin-not-in-pins-json", pin_op(record_pin=False), {"ST9"})

    def old_snapshot(d):
        base = load_json(d / "root" / "archive" / "manifests" / "20261121T081700Z.json")
        v08_run(d, st8, base, "2026-11-21T12:17:00Z", snap_registry=CK.registry_versions(st8)["v0.7"][0])
        restate(d)
    fs("v0.7-snapshot-after-a-v0.8-one", old_snapshot, {"T46", "T122"})

    edited = json.loads(json.dumps(st8.registry))  # 22.9 (I44): an edit within v0.8 that I7 cannot derive
    edited["sources"]["frb-releases"]["route_notices"][0]["milestone"] += " (rechecked)"
    h_edit = sha(canon(edited))

    def edited_runs(d):
        mc, _ = v08_run(d, st8, load_json(d / "root" / "archive" / "manifests" / "20261121T081700Z.json"), "2026-11-21T12:17:00Z", run_reg=edited)
        v08_run(d, st8, mc, "2026-11-21T16:17:00Z")
        restate(d)
    fs("I44-registry-edited-within-v0.8", edited_runs, set())

    def edited_copy_missing(d):
        edited_runs(d)
        for b in ("live", "archive/files"):
            (d / "root" / b / f"registry/econ-{h_edit[:16]}.json").unlink()
    fs("I44-edited-registry-copy-missing", edited_copy_missing, {"T46", "T122", "T66"})

    def ledger_key(key):
        def go(d):
            doc = load_json(d / "state" / "alerts.json")
            doc["open"].append({"key": key, "severity": "critical" if key != "manifest-overdue" else "warning", "title": "t", "body": "x",
                                "first_seen": GEN_B, "last_seen": GEN_B, "runs": 1})
            write(d / "state" / "alerts.json", canon(doc))
            restate(d)
        return go
    fs("publish-failed-in-ledger", ledger_key("publish-failed"), {"T125"})
    fs("manifest-overdue-in-ledger", ledger_key("manifest-overdue"), {"T125"})
    fs("series-stale-in-ledger", ledger_key("series-stale"), {"T125"})

    # --- the publication mode (dataset b, newest earlier release A) ---
    tgz = out / "artifact" / "artifact.tar.gz"
    write(tgz, CP.build_targz(files_b))
    tree = write_tree(files_b, out / "artifact" / "tree")
    PR = ["--previous-release", rel_a]
    jobs.append(("publication mode, econ/ tree", R + ["--publication", tree, "--state", store] + PR, set(), None, out / "logs" / "publication-tree.log"))
    jobs.append(("publication mode, artifact.tar.gz", R + ["--publication", tgz, "--state", store] + PR, set(), None, out / "logs" / "publication-targz.log"))
    jobs.append(("publication fault: no earlier release given for a second entry", R + ["--publication", tgz, "--state", store], {"P8"}, None, None))
    raw = tgz.read_bytes()
    write(out / "artifact" / "os3.tar.gz", raw[:9] + b"\x03" + raw[10:])
    jobs.append(("publication fault: gzip OS byte 3", R + ["--publication", out / "artifact" / "os3.tar.gz", "--state", store] + PR, {"P0"}, None, None))
    write(out / "artifact" / "noprefix.tar.gz", CP.build_targz(files_b, ""))
    jobs.append(("publication fault: entry names without econ/", R + ["--publication", out / "artifact" / "noprefix.tar.gz", "--state", store] + PR, {"P0"}, None, None))

    def pf(name, want, store_fn=None, extra=None, **kw):
        s = mutate_store(store, out / "pub-faults" / name / "store", store_fn) if store_fn else store
        t = live_tree(s)
        t.update(extra or {})
        ds = {"snapshot": dsb["snapshot"], "manifest_sha256": sha((s / "root" / "live" / "manifest.json").read_bytes())}
        f_, _ = build_artifact(t, log_a, ds, "2026-11-21T09:00:00Z", "pub-900-1", **kw)
        jobs.append((f"publication fault: {name}", R + ["--publication", write_tree(f_, out / "pub-faults" / name / "artifact"), "--state", s] + PR, want, None, None))

    pf("planted-state-file", {"P1", "P2", "P5", "P9"}, extra={"state/alerts.json": (store / "state" / "alerts.json").read_bytes()})
    pf("file-without-extension", {"P1", "P2", "P5"}, extra={"objects/README": b"x"})
    obj = next(f for f in files_b if f.startswith("objects/"))
    pf("object-changed", {"P2", "P4", "P9"}, extra={obj: files_b[obj] + b" "})

    def wrong_accepted(d):
        desc = load_json(d / "state" / "STATE.json")
        desc["accepted"] = dsa
        write(d / "state" / "STATE.json", canon(desc))
    pf("identifier-not-accepted", {"P3"}, store_fn=wrong_accepted)
    csv = next(f for f in files_b if f.startswith("series/"))
    pf("named-file-missing", {"P4", "P5"}, store_fn=lambda d: (d / "root" / "live" / csv).unlink())
    orphan = canon({"schema": "rmf.econ.object/1", "series": "effr", "segment": "2026", "observations": []})
    pf("file-outside-window", {"P5"}, store_fn=lambda d: write(d / "root" / "live" / f"objects/effr/2026/{sha(orphan)[:16]}.json", orphan))

    def edit_pubs(fn):
        def go(d):
            doc = load_json(d / "root" / "live" / "status" / "publications.json")
            fn(doc)
            write(d / "root" / "live" / "status" / "publications.json", canon(doc))
        return go
    pf("reason-with-email", {"P6"}, store_fn=edit_pubs(lambda doc: doc["publications"][0]["events"][0].update(reason="requested by radmageirl@radmagelabs.com")))
    pf("reason-with-header-word", {"P6"}, store_fn=edit_pubs(lambda doc: doc["publications"][0]["events"][0].update(reason="owner authorization P56")))

    def noncanon(d):
        doc = load_json(d / "root" / "live" / "status" / "runs.json")
        write(d / "root" / "live" / "status" / "runs.json", json.dumps(doc, indent=1).encode())
    pf("non-canonical-json", {"P9"}, store_fn=noncanon)
    pf("notice-txt-differs", {"P8"}, store_fn=lambda d: write(d / "root" / "live" / "NOTICE.txt", b"other\n"))

    def drop_regver(d):
        for r in load_json(d / "root" / "live" / "manifest.json")["rules"]["registry_versions"]:
            (d / "root" / "live" / r["path"]).unlink()
    pf("registry-copy-missing", {"P4", "P5", "P8"}, store_fn=drop_regver)
    pf("log-does-not-extend-A", {"P8"}, log_override=lambda deps, new: {"schema": CK.DEPLOYMENTS_ID, "deployments": [dict(new, number=1, previous=None)]})
    pf("log-A-post-left-null", {"P8"}, prev_post=None)
    pf("log-new-entry-post-set", {"P8"}, log_override=lambda deps, new: {"schema": CK.DEPLOYMENTS_ID, "deployments": deps + [dict(new, verification=dict(new["verification"], post="passed"))]})
    pf("log-artifact-wrong", {"P8"}, log_override=lambda deps, new: {"schema": CK.DEPLOYMENTS_ID, "deployments": deps + [dict(new, artifact=dict(new["artifact"], files=new["artifact"]["files"] + 1))]})
    pf("log-tag-run-mismatch", {"P8"}, log_override=lambda deps, new: {"schema": CK.DEPLOYMENTS_ID, "deployments": deps + [dict(new, release=new["release"].replace("-900-", "-901-"))]})

    def withdraw(sid):
        def fn(doc):
            for pub in doc["publications"]:
                if pub["snapshot"] == sid:
                    pub["events"].append({"at": "2026-11-21T08:30:00Z", "run": "rollback-x", "status": "withdrawn", "reason": "rolled back"})
                    return
            doc["publications"].append({"snapshot": sid, "events": [{"at": GEN_B, "run": "sched-x", "status": "active", "reason": None},
                                                                    {"at": "2026-11-21T08:30:00Z", "run": "rollback-x", "status": "withdrawn", "reason": "rolled back"}]})
        return fn
    pf("withdrawn-never-public", {"P11"}, store_fn=edit_pubs(withdraw(dsb["snapshot"])))
    pf("withdrawn-after-public (in deployed release A)", set(), store_fn=edit_pubs(withdraw(dsa["snapshot"])))
    pf("withdrawn-in-a-not-deployed-release", {"P11"}, store_fn=edit_pubs(withdraw(dsa["snapshot"])), prev_post="not-deployed")

    # the redeploy of a (entry 1, verified) with B as the newest earlier release
    s2 = mutate_store(store, out / "redeploy" / "store", lambda d: None)
    write(s2 / "state" / "deployments.json", canon(fixed(log_b, "failed")))
    restate(s2)
    ctx = CP.store_context(CK, st8, CP.Store(s2))
    _, wfiles = CP.window_of(CK, ctx, ma)
    rtree = {}
    for path in wfiles:
        src = ma["rules"]["notice"]["path"] if path == "NOTICE.txt" else path
        rtree[path] = (s2 / "root" / "archive" / "files" / src).read_bytes()
    rtree["manifest.json"] = ba
    for f in ("status/runs.json", "status/publications.json"):
        rtree[f] = (s2 / "root" / "live" / f).read_bytes()
    rf, _ = build_artifact(rtree, log_b, dsa, "2026-11-21T09:30:00Z", "pub-901-1", trig="redeploy", prev_post="failed")
    jobs.append(("publication mode, a redeploy of a verified pair", R + ["--publication", write_tree(rf, out / "redeploy" / "artifact"), "--state", s2, "--previous-release", rel_b], set(), None, out / "logs" / "publication-redeploy.log"))
    rf2, _ = build_artifact(rtree, log_b, dsa, "2026-11-21T09:30:00Z", "pub-901-1", trig="redeploy", prev_post="failed", commit="1" * 40)
    jobs.append(("publication fault: a redeploy of a pair that is not verified (other site commit)", R + ["--publication", write_tree(rf2, out / "redeploy" / "artifact-unverified"), "--state", s2, "--previous-release", rel_b], {"P3", "P8"}, None, None))
    rf3, _ = build_artifact(rtree, log_b, dsb, "2026-11-21T09:30:00Z", "pub-901-1", trig="redeploy", prev_post="failed")
    jobs.append(("publication fault: a redeploy whose window is not its target's", R + ["--publication", write_tree(rf3, out / "redeploy" / "artifact-wrong-window"), "--state", s2, "--previous-release", rel_b], {"P2", "P3", "P8"}, None, None))

    # --- the release mode and the release history ---
    jobs.append(("release mode, B", R + ["--release", rel_b], set(), None, out / "logs" / "release.log"))
    jobs.append(("release mode, B against A", R + ["--release", rel_b, "--previous-release", rel_a, "--expect", f"{dsb['snapshot']}:{dsb['manifest_sha256']}"], set(), None, None))
    jobs.append(("release fault: --expect another dataset", R + ["--release", rel_b, "--expect", f"{dsa['snapshot']}:{dsa['manifest_sha256']}"], {"RL3"}, None, None))
    tag_b = rel_b.name
    jobs.append(("release fault: SHA256SUMS wrong", R + ["--release", write_release(out / "release-faults" / "sums" / tag_b, files_b, sums=b"x  artifact.tar.gz\n")], {"RL2"}, None, None))
    jobs.append(("release fault: a fifth asset", R + ["--release", write_release(out / "release-faults" / "extra" / tag_b, files_b, extra={"notes.txt": b"x"})], {"RL1"}, None, None))
    jobs.append(("release fault: a tag with letters", R + ["--release", write_release(out / "release-faults" / "letters" / f"data-{dsb['snapshot']}-j1-1", files_b)], {"RL1", "RL3"}, None, None))
    t = CP.build_targz(files_b)
    raw = bytearray(CP.gzip.decompress(t))
    raw[156:157] = b"2"
    raw[148:156] = b" " * 8
    raw[148:156] = b"%06o\0 " % sum(raw[0:512])
    co = CP.zlib.compressobj(9, CP.zlib.DEFLATED, -15)
    linked = t[:10] + co.compress(bytes(raw)) + co.flush() + struct.pack("<II", CP.zlib.crc32(bytes(raw)) & 0xFFFFFFFF, len(raw))
    jobs.append(("release fault: a link entry", R + ["--release", write_release(out / "release-faults" / "link" / tag_b, files_b, tgz=linked)], {"RL4", "RL5"}, None, None))
    f2 = dict(files_b)
    f2[obj] = files_b[obj] + b" "
    jobs.append(("release fault: an object altered in the archive", R + ["--release", write_release(out / "release-faults" / "altered" / tag_b, files_b, tgz=CP.build_targz(f2))], {"RL5", "P4", "P9"}, None, None))
    jobs.append(("release fault: B against B (not extending)", R + ["--release", rel_b, "--previous-release", rel_b], {"RL5"}, None, None))
    jobs.append(("release history, A and B", R + ["--release-history", out / "releases"], set(), None, out / "logs" / "release-history.log"))
    hist2 = out / "history-faults" / "a-deleted"
    if hist2.exists():
        shutil.rmtree(hist2)
    shutil.copytree(rel_b, hist2 / rel_b.name)
    jobs.append(("release history fault: release A deleted", R + ["--release-history", hist2], {"RH1"}, None, None))
    hist3 = out / "history-faults" / "a-rewritten"
    if hist3.exists():
        shutil.rmtree(hist3)
    shutil.copytree(rel_b, hist3 / rel_b.name)
    write_release(hist3 / rel_a.name, dict(files_a, **{CP.DEPLOY_LOG: canon(fixed(log_a, "passed"))}))
    jobs.append(("release history fault: release A's log rewritten", R + ["--release-history", hist3], {"RH1"}, None, None))
    hist4 = out / "history-faults" / "b-deleted"
    if hist4.exists():
        shutil.rmtree(hist4)
    shutil.copytree(rel_a, hist4 / rel_a.name)
    write(out / "history-faults" / "deployed-b.json", files_b[CP.DEPLOY_LOG])
    jobs.append(("release history: the newest release B deleted, releases alone (they cannot show it)", R + ["--release-history", hist4], set(), None, None))
    jobs.append(("release history fault: B deleted, the deployed log names it", R + ["--release-history", hist4, "--deployed", out / "history-faults" / "deployed-b.json"], {"RH1"}, None, None))
    jobs.append(("release history, A and B with the deployed log of B", R + ["--release-history", out / "releases", "--deployed", out / "history-faults" / "deployed-b.json"], set(), None, None))

    # --- function probes the modes rest on ---
    probes = []
    lp, _ = CP.limit_problems(CK, {"manifest.json": b"x" * 256_001, "objects/effr/2026/" + "a" * 16 + ".json": b"x" * 2_000_001, "series/x/2026/" + "b" * 16 + ".csv": b"x" * 5_000_001})
    probes.append(("P7 limits: manifest over 256 KB, object over 2 MB, file over 5 MB", len(lp) == 3, lp))
    snapdoc = {"id": "20261124T120000Z", "holds": [{"series": "effr", "candidate": {"archive_asset": "archive-2026-11/hold-effr-" + "c" * 16 + ".json", "sha256": sha(b"cand"), "bytes": 4}}], "frozen": []}
    leaks = CP.hold_leaks(CK, {"snapshots/20261124T120000Z.json": canon(snapdoc), "objects/hold-effr-" + "c" * 16 + ".json": b"cand"})
    probes.append(("P10 a hold whose archive asset and candidate are in the artifact", len(leaks) == 2, leaks))
    probes.append(("P10 no leak without them", CP.hold_leaks(CK, {"snapshots/20261124T120000Z.json": canon(snapdoc)}) == [], []))

    # --- appendix J ---
    jdir = out / "scenario"
    build_j(jdir, store, st8, tree_b)
    jobs.append(("appendix J scenario", R + ["--publication-scenario", jdir], set(), None, out / "logs" / "scenario-j.log"))

    def jf(name, fn, want):
        d = out / "scenario-faults" / name
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(jdir, d)
        fn(d)
        jobs.append((f"appendix J fault: {name}", R + ["--publication-scenario", d], want, None, None))

    def edit_steps(fn):
        def go(d):
            steps = load_json(d / "steps.json")
            fn(steps)
            write(d / "steps.json", canon(steps))
        return go
    jf("wrong-time", edit_steps(lambda s: s[3].update(at="2026-11-24T16:18:00Z")), {"J1"})
    jf("deployed-after-unpublish", edit_steps(lambda s: s[17].update(deployed=s[16]["deployed"])), {"J1"})
    jf("alert-closed-by-collection", edit_steps(lambda s: s[14].update(alerts=[])), {"J1"})
    jf("outcome-not-in-list", edit_steps(lambda s: s[7].update(outcome="ended")), {"J0", "J1"})
    jf("alerts-unsorted", edit_steps(lambda s: s[13].update(alerts=sorted(s[13]["alerts"], reverse=True))), {"J0", "J1"})
    jf("extra-field", edit_steps(lambda s: s[0].update(note="x")), {"J0"})
    jf("not-an-array", lambda d: write(d / "steps.json", canon({"steps": []})), {"J0", "J1"})

    def entry4_passed(d):
        x = d / "releases" / sorted(p.name for p in (d / "releases").iterdir() if p.name.endswith("-1001-1"))[0]
        doc = load_json(x / "deployments.json")
        doc["deployments"][3]["verification"]["post"] = "passed"
        rebuild_release(x, doc)
    jf("entry-4-post-passed", entry4_passed, {"J3", "J5"})

    def counts_not_fixed(d):
        x = d / "releases" / sorted(q.name for q in (d / "releases").iterdir() if q.name.endswith("-6-1"))[0]
        doc = load_json(x / "deployments.json")
        doc["deployments"][-1]["verification"]["checker"] = {"pass": 92, "fail": 0, "skip": 0}
        rebuild_release(x, doc)
    jf("checker-counts-not-fixed (I47)", counts_not_fixed, {"J2", "J3"})

    def drop_release(d):
        shutil.rmtree(d / "releases" / sorted(p.name for p in (d / "releases").iterdir() if p.name.endswith("-5-1"))[0])
    jf("release-of-step-5-deleted", drop_release, {"J2", "J3"})

    def prod(fn):
        def go(d):
            doc = load_json(d / "production" / "runs.json")
            fn(doc)
            write(d / "production" / "runs.json", canon(doc))
        return go
    jf("step-7-deployed", prod(lambda doc: doc[4].update(conclusion="success", deployed=True)), {"J4"})
    jf("production-left", lambda d: write(d / "production" / "econ" / "manifest.json", b"{}"), {"J4"})

    def priv_edit(fn):
        def go(d):
            doc = load_json(d / "store" / "state" / "deployments.json")
            fn(doc)
            write(d / "store" / "state" / "deployments.json", canon(doc))
        return go
    jf("private-log-short", priv_edit(lambda doc: doc.update(deployments=doc["deployments"][:4])), {"J5"})
    jf("refused-rollback-wrote", lambda d: write(d / "store" / "runs" / "13.json", canon({"run": "13", "started_at": CP.J_TABLE[13][1]})), {"J5"})

    def unwithdraw(d):
        p_ = d / "store" / "root" / "live" / "status" / "publications.json"
        doc = load_json(p_)
        for pub in doc["publications"]:
            pub["events"] = [e for e in pub["events"] if e["status"] != "withdrawn"]
        write(p_, canon(doc))
    jf("n4-not-withdrawn", unwithdraw, {"J6"})
    jf("release-sums", lambda d: write(sorted((d / "releases").iterdir())[0] / "SHA256SUMS", b"x\n"), {"J2"})

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(lambda j: expect(*j), jobs))
    for label, ok, detail in probes:
        RESULTS.append((ok, label, detail, [], ""))
    n_ok = 0
    for ok, label, got, want, summary in sorted(RESULTS, key=lambda r: r[1]):
        n_ok += ok
        print(f"{'PASS' if ok else 'FAIL'} {label}: FAIL ids {got}" + ("" if ok else f", expected {want}") + (f" [{summary}]" if summary else ""))
    print(f"SUMMARY {n_ok} PASS, {len(RESULTS) - n_ok} FAIL")
    return 0 if n_ok == len(RESULTS) else 1


def rebuild_release(folder, log_doc):
    """Replace a release's log (in its archive and as its asset) and restate its assets."""
    files, _, _ = CP.parse_targz((folder / "artifact.tar.gz").read_bytes())
    files[CP.DEPLOY_LOG] = canon(log_doc)
    write_release(folder, files)


def build_j(d, store, st8, tree):
    """A fabricated appendix J folder following the 19 rows (see the module text)."""
    if d.exists():
        shutil.rmtree(d)
    cur = CK.load_strict(tree["manifest.json"])
    snap = CK.load_strict(tree[cur["snapshot"]["path"]])
    tree0 = {k: v for k, v in tree.items() if k != CP.DEPLOY_LOG}

    def window(sid_):
        s = dict(snap, id=sid_, created_at=CK.fmt_utc(CK.snapshot_time(sid_)))
        sb = canon(s)
        m = dict(cur, snapshot={"id": sid_, "path": f"snapshots/{sid_}.json", "sha256": sha(sb)}, generated_at=s["created_at"])
        mb = canon(m)
        t = dict(tree0)
        t[f"snapshots/{sid_}.json"] = sb
        t["manifest.json"] = mb
        return t, {"snapshot": sid_, "manifest_sha256": sha(mb)}, sb

    t1, N1, _ = window("20261124T120000Z")
    t2, N2, _ = window("20261124T161700Z")
    t3, N3, _ = window("20261124T172000Z")
    _, N4, sb4 = window(CK.snapshot_id_of(CK.parse_utc(CP.J_TABLE[15][1])))
    T = CP.J_TABLE
    trees = {"N1": (t1, N1), "N2": (t2, N2), "N3": (t3, N3)}
    logs, tags = {}, {}
    prev = None
    for step, (num, trig, post) in CP.J_RELEASES.items():
        run, at = T[step][0], T[step][1]
        t, ds = trees[T[step][5]]
        files, lg = build_artifact(t, prev, ds, at, f"pub-{run}-1", trig=trig, checker=dict(CP.J_CHECKER), prev_post=(CP.J_RELEASES[[k for k, v in CP.J_RELEASES.items() if v[0] == num - 1][0]][2] if num > 1 else None))
        tag = lg["deployments"][-1]["release"]
        write_release(d / "releases" / tag, files)
        logs[step], tags[step], prev = lg, tag, lg
    steps = []
    for step, (run, at, kind, mode, outcome, rel_lab, dep, alerts) in T.items():
        steps.append({"step": step, "run": run, "at": at, "kind": kind, "mode": mode, "outcome": outcome, "release": tags[step] if rel_lab else None,
                      "deployed": trees[dep][1] if dep else None, "alerts": alerts})
    write(d / "steps.json", canon(steps))
    runs = []
    for step, run, mode, lab, rstep, concl, dep in CP.J_SITE_RUNS:
        runs.append({"run": run if run is not None else T[step][0], "mode": mode, "dataset": trees[lab][1] if lab else None,
                     "release": tags[rstep] if rstep else None, "conclusion": concl, "deployed": dep})
    write(d / "production" / "runs.json", canon(runs))
    copy_store(store, d / "store")
    sd = d / "store"
    write(sd / "state" / "deployments.json", canon(fixed(logs[11], "passed")))
    write(sd / "root" / "live" / "snapshots" / f"{N4['snapshot']}.json", sb4)
    write(sd / "root" / "archive" / "files" / "snapshots" / f"{N4['snapshot']}.json", sb4)
    pubs = load_json(sd / "root" / "live" / "status" / "publications.json")
    pubs["publications"].append({"snapshot": N4["snapshot"], "events": [{"at": CP.J_TABLE[15][1], "run": "15", "status": "active", "reason": None},
                                                                       {"at": CP.J_TABLE[16][1], "run": "16", "status": "withdrawn", "reason": "Rolled back to snapshot 20261124T172000Z."}]})
    write(sd / "root" / "live" / "status" / "publications.json", canon(pubs))
    write(sd / "root" / "archive" / "rollbacks" / (CK.snapshot_id_of(CK.parse_utc(CP.J_TABLE[16][1])) + ".json"),
          canon({"at": CP.J_TABLE[16][1], "from": N4["snapshot"], "to": N3["snapshot"], "run": "16", "reason": "Rolled back to snapshot 20261124T172000Z: the new EFFR day is not reviewed.", "locks": []}))
    restate(sd)


if __name__ == "__main__":
    sys.exit(main())
