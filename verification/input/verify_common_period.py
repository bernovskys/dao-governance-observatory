"""Re-collect the common-period telemetry from the Snapshot Hub API and compare it
with the reconciled data set (DAO_apvienota_datu_kopa_A_B_kopigais_periods.xlsx).

Common window : proposals CREATED 2025-10-01 00:00 UTC <= t < 2026-07-01 00:00 UTC
Prior window  : proposals CREATED 2024-10-01 00:00 UTC <= t < 2025-07-01 00:00 UTC
Exception     : aavegotchi.eth (strand B only) - proposals ENDING in the common window
Excluded      : proposals listed in excluded_test_proposals.csv; proposals with 0 votes

Outputs (in --out):
  collected_by_dao.csv      values collected now
  collected_proposals.csv   every proposal used (id, created, end, votes, top1, top5)
  comparison.csv            expected vs collected, status per indicator
  report.md                 human-readable summary (also written to the job summary)

Usage:  python verification/verify_common_period.py --out verification_results [--with-votes]
"""
from __future__ import annotations

import argparse, csv, datetime as dt, json, os, statistics as st, sys, time
import urllib.request, urllib.error

API = "https://hub.snapshot.org/graphql"
C0, C1 = 1759276800, 1782864000          # 2025-10-01, 2026-07-01
Q0, Q1 = 1727740800, 1751328000          # 2024-10-01, 2025-07-01
HERE = os.path.dirname(os.path.abspath(__file__))


def gql(query: str, variables: dict, api_key: str | None, tries: int = 6) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "dao-governance-observatory-verify"}
    if api_key:
        headers["x-api-key"] = api_key
    for i in range(tries):
        try:
            req = urllib.request.Request(API, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.loads(r.read())
            if "errors" in out:
                raise RuntimeError(out["errors"])
            return out["data"]
        except (urllib.error.URLError, RuntimeError, TimeoutError) as e:
            if i == tries - 1:
                raise
            time.sleep(2 ** i)
    return {}


Q_PROPS = """query($space:String!,$skip:Int!,$gte:Int!,$lt:Int!){
 proposals(first:1000,skip:$skip,orderBy:"created",orderDirection:asc,
  where:{space:$space,created_gte:$gte,created_lt:$lt}){id title created end state votes}}"""
Q_VOTES = """query($p:String!,$gte:Int!){
 votes(first:1000,orderBy:"created",orderDirection:asc,where:{proposal:$p,created_gte:$gte}){id voter vp created}}"""


def proposals(space, t0, t1, key):
    out, skip = [], 0
    while True:
        page = gql(Q_PROPS, {"space": space, "skip": skip, "gte": t0, "lt": t1}, key)["proposals"]
        out += page
        if len(page) < 1000:
            return out
        skip += 1000


def votes(pid, key):
    seen, out, cur = set(), [], 0
    while True:
        page = gql(Q_VOTES, {"p": pid, "gte": cur}, key)["votes"]
        new = [v for v in page if v["id"] not in seen]
        for v in new:
            seen.add(v["id"]); out.append(v)
        if len(page) < 1000:
            return out
        nxt = page[-1]["created"]
        if nxt == cur and not new:   # 1000 votes with one timestamp: cannot page further
            raise RuntimeError(f"pagination stuck on {pid}")
        cur = nxt


def top_shares(vs):
    vp = sorted((float(v["vp"] or 0) for v in vs), reverse=True)
    tot = sum(vp)
    if tot <= 0:
        return None, None
    return vp[0] / tot, sum(vp[:5]) / tot


def med(x):
    return st.median(x) if x else None


def num(s):
    return None if s in ("", None) else float(s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="verification_results")
    ap.add_argument("--expected", default=os.path.join(HERE, "expected_common_period.csv"))
    ap.add_argument("--tests", default=os.path.join(HERE, "excluded_test_proposals.csv"))
    ap.add_argument("--with-votes", action="store_true", help="also re-compute top-1/top-5 (strand-B DAOs)")
    ap.add_argument("--only", default="", help="comma-separated spaces (debug)")
    a = ap.parse_args()
    key = os.environ.get("SNAPSHOT_API_KEY") or None
    os.makedirs(a.out, exist_ok=True)
    exp = list(csv.DictReader(open(a.expected, encoding="utf-8")))
    if a.only:
        exp = [e for e in exp if e["space"] in a.only.split(",")]
    tests = {r["proposal_id"] for r in csv.DictReader(open(a.tests, encoding="utf-8"))}

    got, prow = [], []
    for e in exp:
        sp, by_end = e["space"], e["window_rule"] == "end"
        print(f"[{sp}] proposals ...", flush=True)
        if by_end:   # created up to 90 days before the window, filtered by end time in code
            ps = [p for p in proposals(sp, C0 - 90 * 86400, C1, key)
                  if C0 <= p["end"] < C1 and p["state"] == "closed"]
        else:
            ps = proposals(sp, C0, C1, key)
        use = [p for p in ps if (p["votes"] or 0) > 0 and p["id"] not in tests]
        pr = [p for p in proposals(sp, Q0, Q1, key) if (p["votes"] or 0) > 0]
        t1s, t5s = [], []
        for p in use:
            t1 = t5 = None
            if a.with_votes and e["top5_median"] != "":
                vs = votes(p["id"], key)
                if len(vs) != p["votes"]:
                    print(f"  ! {p['id']}: {len(vs)} votes retrieved vs {p['votes']} reported", flush=True)
                t1, t5 = top_shares(vs)
                if t5 is not None:
                    t1s.append(t1); t5s.append(t5)
            prow.append([sp, p["id"], p["title"], p["created"], p["end"], p["state"], p["votes"], t1, t5])
        v = [p["votes"] for p in use]; pv = [p["votes"] for p in pr]
        m, pm = med(v), med(pv)
        got.append(dict(space=sp, proposals=len(v), votes=sum(v), median_voters=m, prior_median=pm,
                        yoy_pct=round(100 * (m / pm - 1), 1) if m and pm else None,
                        top5_median=med(t5s), top1_median=med(t1s),
                        open_proposals=sum(1 for p in use if p["state"] != "closed")))

    with open(os.path.join(a.out, "collected_by_dao.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(got[0])); w.writeheader(); w.writerows(got)
    with open(os.path.join(a.out, "collected_proposals.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["space", "id", "title", "created", "end", "state", "votes", "top1", "top5"]); w.writerows(prow)

    # ---- compare
    G = {g["space"]: g for g in got}
    rows, bad = [], 0
    checks = [("proposals", 0), ("votes", 0), ("median_voters", 0), ("prior_median", 0), ("yoy_pct", 0.15)]
    if a.with_votes:
        checks += [("top5_median", 0.005), ("top1_median", 0.005)]
    for e in exp:
        g = G[e["space"]]
        for k, tol in checks:
            x, y = num(e[k]), g[k]
            if k in ("prior_median", "yoy_pct") and x is None and y is not None:
                status = "NEW (not in data set: prior period was incomplete in the pilot)"
            elif x is None and y is None:
                status = "OK"
            elif x is None or y is None:
                status = "DIFFERS"
            else:
                status = "OK" if abs(x - float(y)) <= tol + 1e-9 else "DIFFERS"
            if status == "DIFFERS":
                bad += 1
            rows.append([e["dao"], e["space"], k, e[k], y, status, g["open_proposals"]])
    with open(os.path.join(a.out, "comparison.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["dao", "space", "indicator", "expected", "collected", "status", "open_proposals_now"]); w.writerows(rows)

    tot_p = sum(g["proposals"] for g in got); tot_v = sum(g["votes"] for g in got)
    meds = [g["median_voters"] for g in got if g["median_voters"] is not None]
    yo = [g["yoy_pct"] for g in got if g["yoy_pct"] is not None]
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rep = [f"# Common-period verification ({now})", "",
           f"- DAOs checked: {len(got)}; proposals {tot_p}; votes {tot_v}",
           f"- Median of DAO medians: {med(meds)}; below 50: {sum(1 for m in meds if m < 50)}; 100 or more: {sum(1 for m in meds if m >= 100)}",
           f"- YoY: {sum(1 for y in yo if y < 0)} of {len(yo)} lower; median {med(yo)} %",
           f"- Expected (data set): 43 DAOs; 948 proposals; 86011 votes; median 31; 26 below 50; 9 >= 100; 32 of 37 lower; median -33.3 %",
           f"- Indicator mismatches: **{bad}**", ""]
    diffs = [r for r in rows if r[5] == "DIFFERS"]
    if diffs:
        rep += ["| DAO | indicator | expected | collected |", "|---|---|---|---|"] + [f"| {r[0]} | {r[2]} | {r[3]} | {r[4]} |" for r in diffs]
    open(os.path.join(a.out, "report.md"), "w", encoding="utf-8").write("\n".join(rep) + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8").write("\n".join(rep) + "\n")
    print("\n".join(rep))
    return 0   # mismatches are reported, not treated as a failed run


if __name__ == "__main__":
    sys.exit(main())
