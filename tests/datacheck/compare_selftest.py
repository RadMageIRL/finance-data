"""Self-test of the comparison mode (compare_saved.py, DATA_CONVENTIONS v0.6 section 20.4).

    python -I tests/datacheck/compare_selftest.py <empty or new output dir>

Builds synthetic collection folders (responses/<n>-<host>.bin and .json, as 20.2 defines them)
from the saved fixtures of pipeline/fixtures/raw/ with known edits, runs the comparison on each,
and checks that it reports exactly those edits and nothing else:

  identity  the saved histories served unchanged: no difference at all
  main      EFFR with one value changed, one number written differently, one record removed, one
            added, a field appearing and one disappearing; a Debt to the Penny page with one
            amount changed, one record removed, one added; the reduced H.6 zip with a changed
            value, a new month, a changed status, differing copies and a new Prepared time;
            releaseDates.json with a new release date
  paged     a Debt to the Penny page 1 of 2: the saved records after it are not reported missing
  tampered  a response whose bytes no longer match its recorded SHA-256: refused, not compared
  doctype   an H.6 XML with a document type and an entity declaration: refused
  status    a Debt to the Penny page answered 404 and an EFFR answer 301: reported, not compared

Standard library only. Writes only under the output folder.
"""

import gzip
import hashlib
import importlib.util
import io
import json
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIX = ROOT / "pipeline" / "fixtures" / "raw"
EFFR_URL = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate=2000-07-03&endDate=2026-11-19"
DTP_URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
           "?filter=record_date:gte:1993-04-01&sort=record_date&page%5Bsize%5D=10000&page%5Bnumber%5D={page}")
H6_URL = "https://www.federalreserve.gov/releases/h6/data/FRB_h6_xml.zip"
DATES_URL = "https://www.federalreserve.gov/releases/h6/releaseDates.json"


def load_module():
    spec = importlib.util.spec_from_file_location("rmf_check_compare_saved", HERE / "compare_saved.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CS = load_module()


def dumps(v):
    """JSON with number texts kept (compare_saved.Num)."""
    if isinstance(v, CS.Num):
        return str(v)
    if isinstance(v, dict):
        return "{" + ",".join(json.dumps(k) + ":" + dumps(x) for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ",".join(dumps(x) for x in v) + "]"
    return json.dumps(v, ensure_ascii=False)


def write_response(folder, n, url, body, status=200, content_type="application/json"):
    host = re.match(r"https://([^/]+)/", url).group(1)
    rdir = folder / "responses"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / f"{n}-{host}.bin").write_bytes(body)
    rec = {"url": url, "requested_at": f"2026-11-19T15:00:0{n}Z", "status": status, "content_type": content_type, "content_length": str(len(body)),
           "etag": None, "last_modified": "Thu, 19 Nov 2026 14:00:00 GMT", "date": f"Thu, 19 Nov 2026 15:00:0{n} GMT", "bytes": len(body),
           "sha256": hashlib.sha256(body).hexdigest()}
    (rdir / f"{n}-{host}.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8", newline="\n")


def saved_effr():
    return CS.load_json(gzip.decompress((FIX / "nyfed-effr-full.json.gz").read_bytes()))


def saved_dtp():
    return CS.load_json(gzip.decompress((FIX / "fiscaldata-dtp-full.json.gz").read_bytes()))


def saved_h6_xml():
    return zipfile.ZipFile(FIX / "frb-h6-reduced.zip").read("H6_data.xml").decode("utf-8")


def zip_xml(xml_text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("H6_data.xml", xml_text.encode("utf-8"))
    return buf.getvalue()


def series_span(xml, name, copy=1):
    """(start, end) of the copy-th <kf:Series ... SERIES_NAME="name"> element."""
    pos = -1
    for _ in range(copy):
        pos = xml.index(f'SERIES_NAME="{name}"', pos + 1)
    start = xml.rindex("<kf:Series", 0, pos)
    return start, xml.index("</kf:Series>", pos)


def edit_obs(xml, name, period, attr, old, new, copy=1):
    s, e = series_span(xml, name, copy)
    seg = xml[s:e]
    pat = f'{attr}="{old}"'
    obs = re.search(r'<frb:Obs [^>]*TIME_PERIOD="%s" />' % re.escape(period), seg)
    assert obs and pat in obs.group(0), (name, period, attr, old)
    seg = seg[:obs.start()] + obs.group(0).replace(pat, f'{attr}="{new}"') + seg[obs.end():]
    return xml[:s] + seg + xml[e:]


def add_obs(xml, name, line, copy=1):
    s, e = series_span(xml, name, copy)
    return xml[:e] + "  " + line + "\n    " + xml[e:]


def build(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    dates_bytes = (FIX / "frb-h6-releaseDates.json").read_bytes()
    effr = saved_effr()
    dtp = saved_dtp()
    xml = saved_h6_xml()
    # identity: the saved histories served unchanged
    f = out / "identity"
    write_response(f, 1, EFFR_URL, gzip.decompress((FIX / "nyfed-effr-full.json.gz").read_bytes()))
    write_response(f, 2, DTP_URL.format(page=1), gzip.decompress((FIX / "fiscaldata-dtp-full.json.gz").read_bytes()))
    write_response(f, 3, H6_URL, (FIX / "frb-h6-reduced.zip").read_bytes(), content_type="application/zip")
    write_response(f, 4, DATES_URL, dates_bytes)
    # main
    f = out / "main"
    rr = effr["refRates"]
    by = {r["effectiveDate"]: r for r in rr}
    assert str(by["2026-11-10"]["percentRate"]) == "3.88" and str(by["2026-11-12"]["percentPercentile99"]) == "3.90"
    by["2026-11-10"]["percentRate"] = CS.Num("3.89")
    by["2026-11-12"]["percentPercentile99"] = CS.Num("3.9")
    by["2026-11-09"]["footnoteId"] = "2"
    del by["2026-11-05"]["volumeInBillions"]
    rr[:] = [r for r in rr if r["effectiveDate"] != "2026-11-06"]
    rr.insert(0, {"effectiveDate": "2026-11-13", "type": "EFFR", "percentRate": CS.Num("3.87"), "percentPercentile1": CS.Num("3.85"),
                  "percentPercentile25": CS.Num("3.86"), "percentPercentile75": CS.Num("3.88"), "percentPercentile99": CS.Num("3.91"),
                  "targetRateFrom": CS.Num("3.75"), "targetRateTo": CS.Num("4.00"), "volumeInBillions": CS.Num("101"), "revisionIndicator": ""})
    write_response(f, 1, EFFR_URL, dumps(effr).encode("utf-8"))
    d = json.loads(json.dumps(dtp, default=str))  # DTP fields are all strings except meta counts
    d = CS.load_json(dumps(dtp).encode("utf-8"))
    rows = d["data"]
    bd = {r["record_date"]: r for r in rows}
    assert bd["2026-11-10"]["tot_pub_debt_out_amt"] == "40584130080272.89"
    bd["2026-11-10"]["tot_pub_debt_out_amt"] = "40584130080273.89"
    rows[:] = [r for r in rows if r["record_date"] != "2026-11-06"]
    new = dict(bd["2026-11-12"], record_date="2026-11-13", record_calendar_day="13", tot_pub_debt_out_amt="40610000000000.00",
               debt_held_public_amt="32825000000000.00", intragov_hold_amt="7785000000000.00")
    rows.append(new)
    write_response(f, 2, DTP_URL.format(page=1), dumps(d).encode("utf-8"))
    x = xml.replace("<message:Prepared>2026-10-19T15:17:34</message:Prepared>", "<message:Prepared>2026-11-23T15:00:00</message:Prepared>")
    assert x != xml
    x = edit_obs(x, "M1.M", "2026-09-30", "OBS_VALUE", "20061.2", "20070.0", copy=1)
    x = edit_obs(x, "M1.M", "2026-09-30", "OBS_VALUE", "20061.2", "20070.0", copy=2)
    x = add_obs(x, "M2_N.M", '<frb:Obs OBS_STATUS="A" OBS_VALUE="23400.1" TIME_PERIOD="2026-10-31" />')
    x = edit_obs(x, "M2.M", "2026-08-31", "OBS_STATUS", "A", "NA")
    second = series_span(x, "M1_N.M", 2)
    seg = x[second[0]:second[1]]
    last = re.findall(r'<frb:Obs [^>]*TIME_PERIOD="2026-09-30" />', seg)[0]
    old_val = re.search(r'OBS_VALUE="([^"]+)"', last).group(1)
    x = edit_obs(x, "M1_N.M", "2026-09-30", "OBS_VALUE", old_val, "1.0", copy=2)
    write_response(f, 3, H6_URL, zip_xml(x), content_type="application/zip")
    dates = json.loads(dates_bytes)
    assert dates[0]["yearValue"] == "2026"
    dates[0]["Months"].insert(0, {"MonthName": "November", "MonthValue": "202611", "Dates": ["20261124"]})
    write_response(f, 4, DATES_URL, (json.dumps(dates, indent=2) + "\n").encode("utf-8"))
    # paged: page 1 of 2 (5,000 of 8,433 rows)
    f = out / "paged"
    p1 = CS.load_json(dumps(dtp).encode("utf-8"))
    p1["data"] = p1["data"][:5000]
    p1["meta"]["count"] = CS.Num("5000")
    p1["meta"]["total-pages"] = CS.Num("2")
    write_response(f, 2, DTP_URL.format(page=1).replace("page%5Bsize%5D=10000", "page%5Bsize%5D=5000"), dumps(p1).encode("utf-8"))
    # tampered: the EFFR bytes changed after the record was written
    f = out / "tampered"
    write_response(f, 1, EFFR_URL, gzip.decompress((FIX / "nyfed-effr-full.json.gz").read_bytes()))
    b = (f / "responses" / "1-markets.newyorkfed.org.bin").read_bytes()
    (f / "responses" / "1-markets.newyorkfed.org.bin").write_bytes(b.replace(b'"percentRate": 3.88', b'"percentRate": 3.99', 1))
    # doctype: an XML with a document type and an internal entity
    f = out / "doctype"
    bad = xml.replace('<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
                      '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n<!DOCTYPE m [<!ENTITY x "xxxxxxxxxx">]>', 1)
    assert bad != xml
    write_response(f, 3, H6_URL, zip_xml(bad), content_type="application/zip")
    write_response(f, 4, DATES_URL, dates_bytes)
    # status: a 404 page and a redirect
    f = out / "status"
    write_response(f, 1, EFFR_URL, b"", status=301, content_type="text/html")
    write_response(f, 2, DTP_URL.format(page=1), b'{"error":"not found"}', status=404)
    return out


def run_variant(out, name):
    lines = []
    code = CS.run(out / name, out / f"{name}.result.json", ROOT, emit=lines.append)
    (out / f"{name}.log").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    result = json.loads((out / f"{name}.result.json").read_text(encoding="utf-8"))
    return code, result, lines


DIFF_KINDS = {"changed-field", "field-appears", "field-disappears", "missing-record", "new-record", "earlier-record", "inserted-record",
              "copies-differ", "duplicate", "field-set"}


def diffs(result):
    return sorted((f["source"], f["kind"], f.get("key"), f.get("field"), f.get("saved"), f.get("live")) for f in result["findings"] if f["kind"] in DIFF_KINDS)


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    out = build(argv[0])
    fails, passes = [], 0

    def expect(label, cond, detail=""):
        nonlocal passes
        if cond:
            passes += 1
            print(f"PASS {label}")
        else:
            fails.append(label)
            print(f"FAIL {label}: {detail}")

    code, res, _ = run_variant(out, "identity")
    expect("identity: exit 0, every response verified", code == 0 and all(r["integrity"] == "ok" for r in res["responses"]), f"code {code}")
    expect("identity: no difference in any source", diffs(res) == [], diffs(res)[:5])
    s = res["sources"]
    expect("identity: EFFR 6,625 records in both, latest 2026-11-12", (s["nyfed-markets"]["summary"]["in_both"], s["nyfed-markets"]["summary"]["live_latest"]) == (6625, "2026-11-12"), s["nyfed-markets"]["summary"])
    expect("identity: Debt to the Penny 8,433 records in both", s["fiscaldata"]["summary"]["in_both"] == 8433, s["fiscaldata"]["summary"]["in_both"])
    expect("identity: H.6 four registered series of 813 months each, latest release date 2026-10-27",
           all(s["frb-releases"]["summary"]["series"][n]["in_both"] == 813 for n in ("M1.M", "M2.M", "M1_N.M", "M2_N.M")) and s["frb-releases"]["summary"]["release_dates"]["live_latest"] == "2026-10-27",
           s["frb-releases"]["summary"].get("release_dates"))

    code, res, lines = run_variant(out, "main")
    got = diffs(res)
    want = sorted([
        ("nyfed-markets", "changed-field", "EFFR 2026-11-10", "percentRate", "3.88", "3.89"),
        ("nyfed-markets", "changed-field", "EFFR 2026-11-12", "percentPercentile99", "3.90", "3.9"),
        ("nyfed-markets", "field-appears", "EFFR 2026-11-09", "footnoteId", None, '"2"'),
        ("nyfed-markets", "field-disappears", "EFFR 2026-11-05", "volumeInBillions", "111", None),
        ("nyfed-markets", "missing-record", "EFFR 2026-11-06", None,
         '{"effectiveDate":"2026-11-06","percentPercentile1":3.86,"percentPercentile25":3.87,"percentPercentile75":3.89,"percentPercentile99":3.90,"percentRate":3.88,"revisionIndicator":"","targetRateFrom":3.75,"targetRateTo":4.00,"type":"EFFR","volumeInBillions":105}', None),
        ("nyfed-markets", "new-record", "EFFR 2026-11-13", None, None,
         '{"effectiveDate":"2026-11-13","percentPercentile1":3.85,"percentPercentile25":3.86,"percentPercentile75":3.88,"percentPercentile99":3.91,"percentRate":3.87,"revisionIndicator":"","targetRateFrom":3.75,"targetRateTo":4.00,"type":"EFFR","volumeInBillions":101}'),
        ("fiscaldata", "changed-field", "DTP 2026-11-10", "tot_pub_debt_out_amt", '"40584130080272.89"', '"40584130080273.89"'),
        ("fiscaldata", "missing-record", "DTP 2026-11-06", None, None, None),
        ("fiscaldata", "new-record", "DTP 2026-11-13", None, None, None),
        ("frb-releases", "changed-field", "M1.M 2026-09-30", "OBS_VALUE", '"20061.2"', '"20070.0"'),
        ("frb-releases", "changed-field", "M2.M 2026-08-31", "OBS_STATUS", '"A"', '"NA"'),
        ("frb-releases", "new-record", "M2_N.M 2026-10-31", None, None, '{"OBS_STATUS":"A","OBS_VALUE":"23400.1","TIME_PERIOD":"2026-10-31"}'),
        ("frb-releases", "copies-differ", "M1_N.M copy 2", None, None, None),
        ("frb-releases", "new-record", "release date 2026-11-24", None, None, '{"date":"2026-11-24","marker":""}'),
    ])
    # The Debt to the Penny record texts are long; compare their keys only for those two.
    norm = [g if not (g[0] == "fiscaldata" and g[1] in ("missing-record", "new-record")) else g[:4] + (None, None) for g in got]
    expect("main: exactly the edits made, each field with both values as the provider's text", norm == want,
           f"missing {sorted(set(want) - set(norm))[:4]}; unexpected {sorted(set(norm) - set(want))[:4]}")
    same = [f for f in res["findings"] if f["kind"] == "changed-field" and f.get("field") == "percentPercentile99"]
    expect("main: 3.90 against 3.9 is a text difference, annotated as the same decimal value (never compared as floating point)",
           len(same) == 1 and same[0].get("same_decimal_value") is True and any("the same decimal value" in ln for ln in lines), same)
    hdr = [(f["field"], f["saved"], f["live"]) for f in res["findings"] if f["kind"] == "header" and f["source"] == "frb-releases"]
    expect("main: the H.6 Prepared time is listed with both values", hdr == [("Prepared", '"2026-10-19T15:17:34"', '"2026-11-23T15:00:00"')], hdr)
    rd = [(f["saved"], f["live"]) for f in res["findings"] if f["kind"] == "release-dates"]
    expect("main: the latest release dates, saved and live", rd == [("2026-10-27", "2026-11-24")], rd)
    s = res["sources"]
    expect("main: EFFR summary 6,624 in both, 4 changed records, latest 2026-11-12 and 2026-11-13",
           (s["nyfed-markets"]["summary"]["in_both"], s["nyfed-markets"]["summary"]["changed_records"], s["nyfed-markets"]["summary"]["saved_latest"], s["nyfed-markets"]["summary"]["live_latest"]) == (6624, 4, "2026-11-12", "2026-11-13"),
           s["nyfed-markets"]["summary"])
    expect("main: the requests with their status are listed per source", [(r["n"], r["status"]) for r in s["nyfed-markets"]["requests"]] == [(1, "200")] and len(s["frb-releases"]["requests"]) == 2, s["nyfed-markets"]["requests"])
    expect("main: one line per finding and a summary per source", sum(ln.startswith("FINDING ") for ln in lines) == len(res["findings"]) and sum(ln.startswith("SUMMARY ") for ln in lines) == 3, len(lines))
    expect("main: exit 0", code == 0, code)

    code, res, _ = run_variant(out, "paged")
    nr = [f for f in res["findings"] if f["kind"] == "not-in-received-pages"]
    expect("paged: saved records after page 1 are not reported missing (3,433 not in the received pages)",
           not [f for f in res["findings"] if f["kind"] == "missing-record"] and len(nr) == 1 and res["sources"]["fiscaldata"]["summary"]["saved_not_in_received_pages"] == 3433,
           res["sources"]["fiscaldata"]["summary"])

    code, res, _ = run_variant(out, "tampered")
    expect("tampered: the response whose bytes do not match its SHA-256 is refused and not compared, exit 1",
           code == 1 and [r["integrity"] for r in res["responses"]] == ["mismatch"] and res["sources"]["nyfed-markets"]["summary"] is None
           and any(f["kind"] == "integrity" and f.get("field") == "sha256" for f in res["findings"]), [r["integrity"] for r in res["responses"]])

    code, res, _ = run_variant(out, "doctype")
    expect("doctype: an H.6 XML with a document type and an entity declaration is refused, exit 1",
           code == 1 and any(f["kind"] == "format" and "DOCTYPE" in str(f.get("note")) for f in res["findings"]) and not (res["sources"]["frb-releases"]["summary"] or {}).get("series"),
           [f.get("note") for f in res["findings"] if f["kind"] == "format"])

    code, res, _ = run_variant(out, "status")
    st = sorted((f["source"], f.get("live")) for f in res["findings"] if f["kind"] == "request" and f.get("field") == "status")
    expect("status: a 404 page and a 301 redirect are reported with their status and not compared", st == [("fiscaldata", "404"), ("nyfed-markets", "301")]
           and res["sources"]["fiscaldata"]["summary"] is None, st)

    lines = []
    code = CS.run(out / "main", out / "main" / "inside.json", ROOT, emit=lines.append)
    expect("an output file inside the collection folder is refused (the comparison never edits the collection), exit 2", code == 2 and not (out / "main" / "inside.json").exists(), lines[:1])
    print(f"SELFTEST {passes} PASS, {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
