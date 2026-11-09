"""End-to-end execution pipeline for DAO Governance Observatory."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from .collector import SnapshotCollector
from .holders import HolderCollector
from .indicators import (
    compute_core_retention,
    compute_proposal_metrics,
    compute_voter_table,
    get_or_create_salt,
)
from .instruments import code_instrument_class
from .reports import plot_lorenz_and_top10, write_dissertation_markdown_tables


def run_observatory(
    config_path: Path,
    fetch_holders: bool = False,
    fetch_prior_votes: bool = False,
    out_dir: Path = Path("results"),
    cache_dir: Path = Path("data/raw/cache"),
    salt_file: Path = Path("data/raw/PRIVATE_pseudonym_salt.txt"),
    collector: Optional[SnapshotCollector] = None,
    holder_collector: Optional[HolderCollector] = None,
) -> Dict[str, Any]:
    """
    Execute the full DAO Governance Observatory pipeline for all configured spaces.
    Outputs:
      - results/summary_by_dao.csv
      - results/voters/voters_<space>.csv (pseudonymised)
      - results/proposals/proposals_<space>.csv
      - results/dao_observatory_results.xlsx
      - results/dissertation_table_3_13_full.md
      - results/appendix_M4_top10_all30.md
      - results/figures/lorenz_<space>.png
      - data/raw/PRIVATE_address_mapping_<space>.csv (never published)
    """
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    endpoint = cfg.get("endpoint", "https://hub.snapshot.org/graphql")
    sleep_sec = float(cfg.get("rate_limit_sleep_sec", 1.0))

    if collector is None:
        collector = SnapshotCollector(endpoint=endpoint, cache_dir=cache_dir, sleep_sec=sleep_sec)
    if holder_collector is None:
        holder_collector = HolderCollector(cache_dir=cache_dir, sleep_sec=0.5)

    salt = get_or_create_salt(salt_file)

    win_start = int(cfg["window_start_ts"])
    win_end = int(cfg["window_end_ts"])
    h1_end = int(cfg.get("h1_end_ts", (win_start + win_end) // 2))
    prior_start = int(cfg["prior_start_ts"])
    prior_end = int(cfg["prior_end_ts"])

    out_dir = Path(out_dir)
    (out_dir / "voters").mkdir(parents=True, exist_ok=True)
    (out_dir / "proposals").mkdir(parents=True, exist_ok=True)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    private_dir = salt_file.parent
    private_dir.mkdir(parents=True, exist_ok=True)

    summary_rows: List[Dict[str, Any]] = []
    top10_by_dao: Dict[str, List[Dict[str, Any]]] = {}
    all_proposals_rows: List[Dict[str, Any]] = []

    for item in cfg["spaces"]:
        space_id = str(item["space"])
        dao_name = str(item.get("name") or space_id)
        rank = int(item.get("rank", 0))

        space_info = collector.fetch_space_info(space_id)
        strategies = space_info.get("strategies") or []
        vp_class = item.get("instrument_class") or (code_instrument_class(strategies) if strategies else "C")

        # 1. Fetch proposals in observation window and comparison year
        win_props_all = collector.fetch_proposals(space_id, win_start, win_end)
        win_props = [p for p in win_props_all if int(p.get("votes", 0) or 0) > 0]

        prior_props_all = collector.fetch_proposals(space_id, prior_start, prior_end)
        prior_props = [p for p in prior_props_all if int(p.get("votes", 0) or 0) > 0]

        # 2. Fetch votes for each proposal in observation window
        votes_by_prop: Dict[str, List[Dict[str, Any]]] = {}
        for p in win_props:
            pid = str(p["id"])
            votes_by_prop[pid] = collector.fetch_votes_for_proposal(p)

        # 3. Compute voter-level table & proposal-level table
        voter_rows, voter_summary = compute_voter_table(win_props, votes_by_prop, salt)
        prop_rows = compute_proposal_metrics(win_props, votes_by_prop, voter_summary["unique_voters"])

        for pr in prop_rows:
            pr_with_space = {"space": space_id, "dao": dao_name, **pr}
            all_proposals_rows.append(pr_with_space)

        # Save per-proposal CSV
        pd.DataFrame(prop_rows).to_csv(out_dir / "proposals" / f"proposals_{space_id}.csv", index=False)

        # Save public pseudonymised per-voter CSV (strip raw_address)
        public_voter_rows = [{k: v for k, v in r.items() if k != "raw_address"} for r in voter_rows]
        pd.DataFrame(public_voter_rows).to_csv(out_dir / "voters" / f"voters_{space_id}.csv", index=False)

        # Save private raw address mapping (strictly excluded from Git via .gitignore)
        private_voter_rows = [{"voter_id": r["voter_id"], "raw_address": r["raw_address"]} for r in voter_rows]
        pd.DataFrame(private_voter_rows).to_csv(private_dir / f"PRIVATE_addresses_{space_id}.csv", index=False)

        # Top-10 + remainder summary for Appendix M.4
        if len(public_voter_rows) > 10:
            rem = public_voter_rows[10:]
            rem_row = {
                "rank": f"11–{len(public_voter_rows)}",
                "voter_id": f"{len(rem)} other addresses",
                "votes": sum(r["votes"] for r in rem),
                "proposals_total": len(win_props),
                "vp_share_pct": round(sum(r["vp_share_pct"] for r in rem), 2),
                "cum_share_pct": 100.0,
                "core": f"{sum(1 for r in rem if r['core'])} core",
            }
            top10_by_dao[space_id] = public_voter_rows[:10] + [rem_row]
        else:
            top10_by_dao[space_id] = public_voter_rows

        # Plot Lorenz curve and Top-10 voters
        if voter_rows and not np.isnan(voter_summary["window_gini"]):
            plot_lorenz_and_top10(
                dao_name=dao_name,
                space_id=space_id,
                voter_rows=public_voter_rows,
                window_gini=voter_summary["window_gini"],
                out_path=out_dir / "figures" / f"lorenz_{space_id}.png",
            )

        # 4. Prior-year votes for core retention (if --prior-votes enabled)
        core_retention_pct: Optional[float] = None
        if fetch_prior_votes and prior_props:
            prior_votes_by_prop: Dict[str, List[Dict[str, Any]]] = {}
            for pp in prior_props:
                prior_votes_by_prop[str(pp["id"])] = collector.fetch_votes_for_proposal(pp)
            prior_voter_rows, _ = compute_voter_table(prior_props, prior_votes_by_prop, salt)
            core_retention_pct = compute_core_retention(prior_voter_rows, voter_rows)

        # 5. Token holder count (if --holders enabled)
        holders_count: Optional[int] = None
        holders_minus_voters: Optional[int] = None
        holder_participation_pct: Optional[float] = None
        holder_token_used: Optional[str] = None
        if fetch_holders:
            # Primary token first; fall back to the documented governance token when the primary
            # address is missing or is not indexed as a token (e.g. a locker/staking contract).
            candidates = []
            chain_id = item.get("holder_token_chain")
            token_addr = item.get("holder_token_address")
            if chain_id and token_addr and str(token_addr) != "None":
                candidates.append((chain_id, token_addr, item.get("holder_token_label") or str(token_addr)))
            doc = item.get("documented_holder_token") or {}
            if doc.get("chain") and doc.get("address"):
                candidates.append((doc["chain"], doc["address"], doc.get("label") or str(doc["address"])))
            for c_chain, c_addr, c_label in candidates:
                holders_count = holder_collector.fetch_holder_count(c_chain, c_addr)
                if holders_count is not None and holders_count > 0:
                    holder_token_used = f"{c_label} @ {c_chain}"
                    break
            if holders_count is not None and holders_count > 0:
                holders_minus_voters = max(0, int(holders_count) - int(voter_summary["unique_voters"]))
                holder_participation_pct = round(voter_summary["unique_voters"] / holders_count * 100.0, 4)

        # 6. Compute medians (window, H1, H2, prior year, YoY %)
        win_counts = [int(p.get("votes", 0) or len(votes_by_prop.get(str(p["id"]), []))) for p in win_props]
        h1_counts = [
            int(p.get("votes", 0) or len(votes_by_prop.get(str(p["id"]), [])))
            for p in win_props if int(p["created"]) < h1_end
        ]
        h2_counts = [
            int(p.get("votes", 0) or len(votes_by_prop.get(str(p["id"]), [])))
            for p in win_props if int(p["created"]) >= h1_end
        ]
        prior_counts = [int(p.get("votes", 0) or 0) for p in prior_props]

        med_win = float(np.median(win_counts)) if win_counts else 0.0
        med_h1 = float(np.median(h1_counts)) if h1_counts else None
        med_h2 = float(np.median(h2_counts)) if h2_counts else None
        med_prior = float(np.median(prior_counts)) if prior_counts else None
        yoy_pct = round((med_win - med_prior) / med_prior * 100.0, 1) if (med_prior and med_prior > 0) else None

        prop_ginis = [r["gini"] for r in prop_rows if r.get("gini") is not None and not np.isnan(r["gini"])]
        prop_naks = [r["nakamoto50"] for r in prop_rows if r.get("nakamoto50") is not None and r["nakamoto50"] > 0]

        summary_rows.append({
            "rank": rank,
            "space": space_id,
            "name": dao_name,
            "instrument_class": vp_class,
            "proposals_with_votes": len(win_props),
            "votes_cast": int(sum(win_counts)),
            "unique_voters": voter_summary["unique_voters"],
            "median_voters_per_proposal": round(med_win, 1),
            "mean_voters": round(float(np.mean(win_counts)), 1) if win_counts else 0.0,
            "max_voters": int(max(win_counts)) if win_counts else 0,
            "h1_median": round(med_h1, 1) if med_h1 is not None else None,
            "h2_median": round(med_h2, 1) if med_h2 is not None else None,
            "prior_median": round(med_prior, 1) if med_prior is not None else None,
            "yoy_pct": yoy_pct,
            "median_gini": round(float(np.median(prop_ginis)), 4) if prop_ginis else None,
            "window_gini": voter_summary["window_gini"],
            "median_nakamoto50": round(float(np.median(prop_naks)), 1) if prop_naks else None,
            "window_nakamoto50": voter_summary["window_nakamoto50"],
            "core_count": voter_summary["core_count"],
            "core_vp_share_pct": voter_summary["core_vp_share_pct"],
            "core_retention_pct": core_retention_pct,
            "reason_share_pct": voter_summary["reason_share_pct"],
            "token_holders": holders_count,
            "holders_minus_voters": holders_minus_voters,
            "holder_participation_pct": holder_participation_pct,
            "holder_token_used": holder_token_used,
        })

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(out_dir / "summary_by_dao.csv", index=False)

    # Write Excel workbook
    xlsx_path = out_dir / "dao_observatory_results.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="summary_by_dao", index=False)
        pd.DataFrame(all_proposals_rows).to_excel(writer, sheet_name="proposals_all", index=False)

    # Write ready-to-insert Markdown tables for the dissertation
    write_dissertation_markdown_tables(summary_rows, top10_by_dao, out_dir)

    return {
        "summary": summary_rows,
        "proposals": all_proposals_rows,
        "top10_by_dao": top10_by_dao,
        "xlsx_path": str(xlsx_path),
    }


def select_top_spaces(
    candidates: List[Dict[str, Any]],
    min_proposals: int = 3,
    top_n: int = 30
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Apply the reproducible selection rule:
      (i) verified Snapshot space;
      (ii) at least `min_proposals` (3) proposals with >=1 vote in the window;
      (iii) rank descending by median voting addresses per proposal;
      (iv) tie-break descending by total votes cast in the window;
      (v) select top_n (30).
    """
    eligible = []
    excluded = []
    for c in candidates:
        if not c.get("verified", True):
            excluded.append({**c, "reason": "unverified space"})
            continue
        props = int(c.get("proposals_with_votes", 0))
        if props == 0:
            excluded.append({**c, "reason": "no Snapshot proposal in window"})
            continue
        if props < min_proposals:
            excluded.append({**c, "reason": f"fewer than {min_proposals} proposals with votes in window"})
            continue
        eligible.append(c)

    eligible_sorted = sorted(
        eligible,
        key=lambda x: (-float(x["median_voters_per_proposal"]), -int(x["votes_cast"]), str(x["space"]))
    )
    selected = []
    for idx, item in enumerate(eligible_sorted, start=1):
        if idx <= top_n:
            selected.append({**item, "rank": idx})
        else:
            excluded.append({**item, "reason": f"below cut-off (rank {idx})"})
    return selected, excluded
