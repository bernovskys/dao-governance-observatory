"""Command-line interface for DAO Governance Observatory."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .pipeline import run_observatory, select_top_spaces


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dao_observatory",
        description="DAO Governance Observatory: Reproducible behavioural telemetry pipeline (Snapshot Hub GraphQL)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run full telemetry collection and indicator computation.")
    run_p.add_argument("--config", required=True, help="Path to JSON configuration file (e.g. config/top30_2025-10_2026-09.json)")
    run_p.add_argument("--holders", action="store_true", help="Fetch token-holder counts from Blockscout APIs")
    run_p.add_argument("--prior-votes", action="store_true", help="Fetch prior-window votes to compute year-on-year core retention")
    run_p.add_argument("--out-dir", default="results", help="Output directory for CSV/XLSX/Markdown/figures")
    run_p.add_argument("--cache-dir", default="data/raw/cache", help="Directory for cached API responses")

    sel_p = sub.add_parser("select", help="Apply the selection rule to a candidate space summary JSON.")
    sel_p.add_argument("--candidates", required=True, help="Path to candidate spaces JSON list")
    sel_p.add_argument("--out", default="results/selected_top30.json", help="Output JSON path")
    sel_p.add_argument("--min-proposals", type=int, default=3)
    sel_p.add_argument("--top-n", type=int, default=30)

    args = parser.parse_args(argv)
    if args.command == "run":
        res = run_observatory(
            config_path=Path(args.config),
            fetch_holders=bool(args.holders),
            fetch_prior_votes=bool(args.prior_votes),
            out_dir=Path(args.out_dir),
            cache_dir=Path(args.cache_dir),
        )
        print(f"[DAO Observatory] Completed for {len(res['summary'])} DAOs.")
        print(f"[DAO Observatory] Summary CSV: {Path(args.out_dir) / 'summary_by_dao.csv'}")
        print(f"[DAO Observatory] Dissertation Table 3.13 Markdown: {Path(args.out_dir) / 'dissertation_table_3_13_full.md'}")
        print(f"[DAO Observatory] Excel Workbook: {res['xlsx_path']}")
        return 0

    if args.command == "select":
        cands = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
        selected, excluded = select_top_spaces(cands, min_proposals=args.min_proposals, top_n=args.top_n)
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"selected": selected, "excluded": excluded}, indent=2), encoding="utf-8")
        print(f"[DAO Observatory] Selected {len(selected)} DAOs, excluded {len(excluded)}.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
