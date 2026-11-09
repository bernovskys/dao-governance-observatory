"""Report generation: CSVs, Excel workbook, Lorenz curves, and dissertation Markdown tables (Table 3.13 & M.4)."""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .indicators import lorenz_curve_points


def plot_lorenz_and_top10(
    dao_name: str,
    space_id: str,
    voter_rows: List[Dict],
    window_gini: float,
    out_path: Path
) -> None:
    """Save two-panel Lorenz curve + Top-10 voters bar chart (matching Figure 3.2 in dissertation)."""
    vps = [float(r["vp_total"]) for r in voter_rows if float(r["vp_total"]) > 0]
    if not vps:
        return
    x, y = lorenz_curve_points(vps)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.4), dpi=200)

    ax1.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1.0)
    ax1.plot(x, y, color="#154c79", linewidth=2.4)
    ax1.set_title(f"{dao_name}: Lorenz curve, Gini = {window_gini:.2f}", fontsize=10.5)
    ax1.set_xlabel("Share of voters (ascending)")
    ax1.set_ylabel("Share of VP cast")
    ax1.set_xlim(0, 1)
    ax1.set_ylim(0, 1)

    top10 = voter_rows[:10][::-1]
    labels = [r["voter_id"][:7] for r in top10]
    shares = [float(r["vp_share_pct"]) for r in top10]
    ax2.barh(labels, shares, color="#154c79")
    ax2.set_title("Ten largest voters (pseudonymised)", fontsize=10.5)
    ax2.set_xlabel("Share of all VP cast in window (%)")

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def write_dissertation_markdown_tables(
    summary_rows: List[Dict],
    top10_by_dao: Dict[str, List[Dict]],
    out_dir: Path
) -> None:
    """Generate ready-to-paste Markdown tables for Dissertation Table 3.13 (full Mode B) and Appendix M.4."""
    out_dir.mkdir(parents=True, exist_ok=True)
    md_lines = [
        "# Disertācijas Table 3.13 (Pilnais Režīms B: 30 DAO uzvedības telemetrija)",
        "",
        "| # | DAO | VP class | Props | Votes cast | Unique voters | Median voters | H1 | H2 | Prior year | YoY, % | Median Gini (VP) | Median Nakamoto | Core VP share, % | Reason share, % | Token holders | Holders minus voters |",
        "|---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    ]
    for r in summary_rows:
        md_lines.append(
            f"| {r['rank']} | {r['name']} | {r['instrument_class']} | {r['proposals_with_votes']} | "
            f"{r['votes_cast']:,} | {r.get('unique_voters', '–')} | {r['median_voters_per_proposal']} | "
            f"{r.get('h1_median') if pd.notna(r.get('h1_median')) else '–'} | "
            f"{r.get('h2_median') if pd.notna(r.get('h2_median')) else '–'} | "
            f"{r.get('prior_median') if pd.notna(r.get('prior_median')) else 'n/c'} | "
            f"{r.get('yoy_pct') if pd.notna(r.get('yoy_pct')) else 'n/c'} | "
            f"{r.get('median_gini') if pd.notna(r.get('median_gini')) else '–'} | "
            f"{r.get('median_nakamoto50') if pd.notna(r.get('median_nakamoto50')) else '–'} | "
            f"{r.get('core_vp_share_pct') if pd.notna(r.get('core_vp_share_pct')) else '–'} | "
            f"{r.get('reason_share_pct') if pd.notna(r.get('reason_share_pct')) else '–'} | "
            f"{r.get('token_holders') if pd.notna(r.get('token_holders')) else '–'} | "
            f"{r.get('holders_minus_voters') if pd.notna(r.get('holders_minus_voters')) else '–'} |"
        )

    # P1 and P2 empirical correlation notes
    df = pd.DataFrame(summary_rows)
    md_lines.append("")
    md_lines.append("## Empīriskais kopsavilkums P1 un P2 testēšanai (visos 30 DAO)")
    if "reason_share_pct" in df.columns and df["reason_share_pct"].notna().any():
        med_reason = df["reason_share_pct"].median()
        mean_reason = df["reason_share_pct"].mean()
        md_lines.append(f"- **P1 (Deliberative reason share)**: Mediānā pamatojumu daļa 30 DAO = **{med_reason:.2f}%** (vidējā = **{mean_reason:.2f}%**).")
    if "median_gini" in df.columns and df["median_gini"].notna().any():
        med_gini = df["median_gini"].median()
        med_nak = df["median_nakamoto50"].median()
        corr_p2 = df["median_gini"].corr(np.log10(df["median_voters_per_proposal"].astype(float))) if df["median_gini"].notna().sum() >= 2 else float("nan")
        md_lines.append(rf"- **P2 (Concentration vs. breadth)**: Mediānais Gini = **{med_gini:.3f}**, mediānais Nakamoto (50%) = **{med_nak:.1f}**, korelācija starp Gini un $\log_{{10}}(\text{{mediānie balsotāji}})$ = **{corr_p2:.3f}**.")

    (out_dir / "dissertation_table_3_13_full.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    # Write Appendix M.4 summary (Top-10 + remainder for all 30 DAOs)
    m4_lines = [
        "# Appendix M.4: Top-10 Voters and Remainder Across All 30 DAOs (Pseudonymised)",
        ""
    ]
    for space_id, rows in top10_by_dao.items():
        m4_lines.append(f"## Space: `{space_id}`")
        m4_lines.append("| Rank | Voter (pseudonym) | Proposals voted | Share of all VP cast (%) | Cumulative (%) | Core |")
        m4_lines.append("|---:|---|---:|---:|---:|:---:|")
        for vr in rows:
            # The remainder row carries a "<n> core" string; plain voter rows carry a bool.
            core_label = vr["core"] if isinstance(vr["core"], str) else ("yes" if vr["core"] else "no")
            m4_lines.append(
                f"| {vr['rank']} | {vr['voter_id']} | {vr['votes']} of {vr['proposals_total']} | "
                f"{vr['vp_share_pct']:.2f} | {vr['cum_share_pct']:.1f} | {core_label} |"
            )
        m4_lines.append("")
    (out_dir / "appendix_M4_top10_all30.md").write_text("\n".join(m4_lines) + "\n", encoding="utf-8")
