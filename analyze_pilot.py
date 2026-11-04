"""Reproduce all pilot numbers in Parts 2-4 from the transcribed pilot dataset without network access."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd


def main() -> None:
    xlsx_path = Path(__file__).resolve().parent / "18_DAO_pilot_dataset_2025-10_2026-09.xlsx"
    top30 = pd.read_excel(xlsx_path, sheet_name="top30")
    kleros_p = pd.read_excel(xlsx_path, sheet_name="kleros_proposals")
    kleros_v = pd.read_excel(xlsx_path, sheet_name="kleros_voters")

    total_props = int(top30["proposals_with_votes"].sum())
    total_votes = int(top30["votes_cast"].sum())
    arb_votes = int(top30.loc[0, "votes_cast"])
    arb_share = arb_votes / total_votes * 100.0
    med_dao_voters = float(top30["median_voters_per_proposal"].median())
    daos_ge_100 = int((top30["median_voters_per_proposal"] >= 100).sum())
    daos_lt_50 = int((top30["median_voters_per_proposal"] < 50).sum())

    valid_yoy = top30["yoy_pct"].dropna()
    declines_yoy = int((valid_yoy < 0).sum())
    med_yoy = float(valid_yoy.median())

    both_halves = top30.dropna(subset=["h1_median", "h2_median"])
    h2_lower = int((both_halves["h2_median"] < both_halves["h1_median"]).sum())

    print("=== PILOT REPRODUCTION SUMMARY (30 DAOs, 2025-10-01 to 2026-09-30) ===")
    print(f"Total proposals with votes: {total_props}")
    print(f"Total votes cast: {total_votes:,}")
    print(f"Arbitrum DAO votes: {arb_votes:,} ({arb_share:.1f}%)")
    print(f"DAOs with median >= 100: {daos_ge_100}/30; median < 50: {daos_lt_50}/30; median across 30 DAOs: {med_dao_voters:.1f}")
    print(f"YoY declines: {declines_yoy}/{len(valid_yoy)} (median YoY change: {med_yoy:.1f}%)")
    print(f"H2 < H1 declines: {h2_lower}/{len(both_halves)}")

    print("\n=== KLEROS VOTE-LEVEL VALIDATION ===")
    rel_diff = np.abs(kleros_p["vp_cast"] - kleros_p["scores_total_api"]) / kleros_p["scores_total_api"]
    print(f"Max relative difference against API scores_total: {rel_diff.max():.2e}")
    print(f"Active electorate (unique voters): {len(kleros_v)}")
    print(f"One-off voters: {(kleros_v['votes'] == 1).sum()} ({(kleros_v['votes'] == 1).mean()*100:.1f}%)")
    print(f"Core voters (>=3 of 6 proposals): {kleros_v['core'].sum()} ({kleros_v.loc[kleros_v['core'], 'vp_share_pct'].sum():.1f}% of VP)")


if __name__ == "__main__":
    main()
