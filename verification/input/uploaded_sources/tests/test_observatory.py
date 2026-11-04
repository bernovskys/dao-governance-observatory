"""Eleven automated tests for DAO Governance Observatory (runs with both `pytest` and `unittest`)."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
import numpy as np

# Ensure package root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dao_observatory.indicators import (
    compute_core_retention,
    compute_proposal_metrics,
    compute_voter_table,
    gini_coefficient,
    hhi_index,
    lorenz_curve_points,
    nakamoto_coefficient,
    pseudonymise_address,
    top_k_share,
)
from dao_observatory.instruments import code_instrument_class
from dao_observatory.collector import SnapshotCollector
from dao_observatory.holders import HolderCollector
from dao_observatory.pipeline import run_observatory, select_top_spaces


class InMemorySnapshotDouble:
    """In-memory double of Snapshot Hub GraphQL API enforcing `first <= 1000` page limits."""

    def __init__(self, spaces: Dict[str, Dict], proposals: Dict[str, List[Dict]], votes: Dict[str, List[Dict]]) -> None:
        self.spaces = spaces
        self.proposals = proposals
        self.votes = votes

    def __call__(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        if "SpaceInfo" in query:
            return {"space": self.spaces.get(variables["id"], {})}
        if "ProposalsWindow" in query:
            space_id = variables["space"]
            gte = int(variables["gte"])
            lt = int(variables["lt"])
            first = min(1000, int(variables["first"]))
            skip = int(variables["skip"])
            filtered = [
                p for p in self.proposals.get(space_id, [])
                if gte <= int(p["created"]) < lt
            ]
            filtered.sort(key=lambda p: (int(p["created"]), str(p["id"])))
            return {"proposals": filtered[skip : skip + first]}
        if "ProposalVotes" in query:
            pid = variables["proposal"]
            gte = int(variables["gte"])
            first = min(1000, int(variables["first"]))
            skip = int(variables["skip"])
            filtered = [
                v for v in self.votes.get(pid, [])
                if int(v["created"]) >= gte
            ]
            filtered.sort(key=lambda v: (int(v["created"]), str(v["voter"])))
            return {"votes": filtered[skip : skip + first]}
        return {}


class TestDAOObservatory(unittest.TestCase):
    """Suite of 11 automated tests (9 unit tests + 2 end-to-end API double tests)."""

    def test_01_gini_equality_and_extremes(self) -> None:
        self.assertAlmostEqual(gini_coefficient([10.0, 10.0, 10.0, 10.0]), 0.0, places=9)
        self.assertAlmostEqual(gini_coefficient([100.0]), 0.0, places=9)
        self.assertTrue(np.isnan(gini_coefficient([0.0, 0.0])))
        self.assertAlmostEqual(gini_coefficient([1.0, 3.0]), 0.25, places=9)

    def test_02_nakamoto_50_percent_strict(self) -> None:
        self.assertEqual(nakamoto_coefficient([50.0, 50.0], 0.50), 2)
        self.assertEqual(nakamoto_coefficient([50.1, 49.9], 0.50), 1)
        self.assertEqual(nakamoto_coefficient([25.0, 20.0, 15.0, 40.0], 0.50), 2)

    def test_03_top_k_share_and_hhi(self) -> None:
        vps = [50.0, 30.0, 20.0, 0.0]
        self.assertAlmostEqual(top_k_share(vps, 1), 50.0, places=6)
        self.assertAlmostEqual(top_k_share(vps, 2), 80.0, places=6)
        self.assertAlmostEqual(hhi_index(vps), 0.5**2 + 0.3**2 + 0.2**2, places=6)

    def test_04_lorenz_curve_endpoints_and_monotonicity(self) -> None:
        x, y = lorenz_curve_points([1.0, 2.0, 7.0])
        self.assertEqual(x[0], 0.0)
        self.assertEqual(y[0], 0.0)
        self.assertEqual(x[-1], 1.0)
        self.assertEqual(y[-1], 1.0)
        self.assertTrue(np.all(np.diff(y) >= 0.0))

    def test_05_pseudonym_determinism_and_case_insensitivity(self) -> None:
        p1 = pseudonymise_address("0xAbCdEf0123456789", "test-salt-1")
        p2 = pseudonymise_address("0xabcdef0123456789  ", "test-salt-1")
        p3 = pseudonymise_address("0xabcdef0123456789", "different-salt")
        self.assertEqual(p1, p2)
        self.assertTrue(p1.startswith("V") and len(p1) == 11)
        self.assertNotEqual(p1, p3)

    def test_06_instrument_class_coding(self) -> None:
        strats = [
            {"name": "erc20-balance-of", "params": {"symbol": "TKN"}},
            {"name": "erc20-votes", "params": {"symbol": "vTKN"}},
            {"name": "strk-staked-balance", "params": {}},
            {"name": "whitelist-weighted", "params": {}},
        ]
        self.assertEqual(code_instrument_class(strats), "T+D+L+W")
        self.assertEqual(code_instrument_class([{"name": "erc721", "params": {}}]), "N")
        self.assertEqual(code_instrument_class([{"name": "contract-call", "params": {}}]), "C")

    def test_07_voter_table_and_identified_core_proxy(self) -> None:
        proposals = [{"id": f"p{i}", "created": 1000 + i, "votes": 2} for i in range(4)]
        votes_by_prop = {
            "p0": [{"voter": "0xA", "vp": 60, "reason": "ok", "created": 1001}, {"voter": "0xB", "vp": 40, "reason": "", "created": 1002}],
            "p1": [{"voter": "0xA", "vp": 60, "reason": "", "created": 1003}, {"voter": "0xC", "vp": 40, "reason": "yes", "created": 1004}],
            "p2": [{"voter": "0xB", "vp": 50, "reason": "", "created": 1005}, {"voter": "0xD", "vp": 50, "reason": "", "created": 1006}],
            "p3": [{"voter": "0xA", "vp": 80, "reason": "good", "created": 1007}, {"voter": "0xE", "vp": 20, "reason": "", "created": 1008}],
        }
        rows, summary = compute_voter_table(proposals, votes_by_prop, salt="s1")
        self.assertEqual(summary["unique_voters"], 5)
        self.assertEqual(summary["core_count"], 2)
        self.assertAlmostEqual(summary["core_vp_share_pct"], (200.0 + 90.0) / 400.0 * 100.0, places=2)
        self.assertAlmostEqual(summary["reason_share_pct"], 3 / 8 * 100.0, places=2)

    def test_08_proposal_metrics_and_turnout(self) -> None:
        proposals = [{"id": "p1", "title": "Test", "created": 100, "votes": 2, "scores_total": 100.0}]
        votes_by_prop = {
            "p1": [
                {"voter": "0x1", "vp": 80.0, "reason": "r1", "created": 101},
                {"voter": "0x2", "vp": 20.0, "reason": "", "created": 102},
            ]
        }
        pm = compute_proposal_metrics(proposals, votes_by_prop, active_electorate_size=10)
        self.assertEqual(len(pm), 1)
        self.assertAlmostEqual(pm[0]["turnout_active_electorate_pct"], 20.0, places=2)
        self.assertEqual(pm[0]["non_voting_active_addresses"], 8)
        self.assertEqual(pm[0]["nakamoto50"], 1)
        self.assertAlmostEqual(pm[0]["top1_pct"], 80.0, places=2)
        self.assertAlmostEqual(pm[0]["reason_share_pct"], 50.0, places=2)

    def test_09_selection_rule_tie_breaking_and_exclusions(self) -> None:
        candidates = [
            {"space": "frax.eth", "verified": True, "proposals_with_votes": 16, "median_voters_per_proposal": 7.5, "votes_cast": 128},
            {"space": "olympusdao.eth", "verified": True, "proposals_with_votes": 10, "median_voters_per_proposal": 7.5, "votes_cast": 86},
            {"space": "walletconnect.eth", "verified": True, "proposals_with_votes": 2, "median_voters_per_proposal": 1907.0, "votes_cast": 3814},
            {"space": "apecoin.eth", "verified": True, "proposals_with_votes": 0, "median_voters_per_proposal": 0.0, "votes_cast": 0},
        ]
        selected, excluded = select_top_spaces(candidates, min_proposals=3, top_n=1)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["space"], "frax.eth")
        self.assertEqual(len(excluded), 3)

    def test_10_e2e_pagination_3x2500_votes_with_1200_shared_timestamp_and_caching(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            space_id = "testdao.eth"
            proposals = []
            votes_map: Dict[str, List[Dict]] = {}

            for p_idx in range(3):
                pid = f"prop_{p_idx}"
                base_ts = 1760000000 + p_idx * 100000
                p_votes = []
                for i in range(600):
                    p_votes.append({
                        "id": f"{pid}_v_{i}",
                        "voter": f"0xvoter_{p_idx}_{i:04d}",
                        "vp": 10.0,
                        "choice": 1,
                        "reason": "reason" if i % 10 == 0 else "",
                        "created": base_ts + i,
                    })
                shared_ts = base_ts + 1000
                for i in range(600, 1800):
                    p_votes.append({
                        "id": f"{pid}_v_{i}",
                        "voter": f"0xvoter_{p_idx}_{i:04d}",
                        "vp": 10.0,
                        "choice": 1,
                        "reason": "",
                        "created": shared_ts,
                    })
                for i in range(1800, 2500):
                    p_votes.append({
                        "id": f"{pid}_v_{i}",
                        "voter": f"0xvoter_{p_idx}_{i:04d}",
                        "vp": 10.0,
                        "choice": 1,
                        "reason": "",
                        "created": shared_ts + 1 + (i - 1800),
                    })
                self.assertEqual(len(p_votes), 2500)
                votes_map[pid] = p_votes
                proposals.append({
                    "id": pid,
                    "title": f"Proposal {p_idx}",
                    "created": base_ts,
                    "end": base_ts + 50000,
                    "state": "closed",
                    "votes": 2500,
                    "scores_total": 25000.0,
                    "quorum": 0.0,
                })

            api_double = InMemorySnapshotDouble(
                spaces={space_id: {"id": space_id, "name": "Test DAO", "verified": True, "strategies": [{"name": "erc20-votes", "params": {}}]}},
                proposals={space_id: proposals},
                votes=votes_map,
            )

            cache_dir = tmp_path / "cache"
            collector = SnapshotCollector(cache_dir=cache_dir, sleep_sec=0.0, transport=api_double)

            for p in proposals:
                retrieved = collector.fetch_votes_for_proposal(p)
                self.assertEqual(len(retrieved), 2500)
                self.assertEqual(len({v["voter"] for v in retrieved}), 2500)
                self.assertAlmostEqual(sum(v["vp"] for v in retrieved), 25000.0, places=5)

            calls_after_first_download = collector.network_calls
            self.assertGreater(calls_after_first_download, 0)

            for p in proposals:
                retrieved_cached = collector.fetch_votes_for_proposal(p)
                self.assertEqual(len(retrieved_cached), 2500)
            self.assertEqual(collector.network_calls, calls_after_first_download)

    def test_11_e2e_half_year_medians_yoy_core_retention_and_pseudonym_stability(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            space_id = "retentiondao.eth"
            win_start = 1759276800
            h1_end = 1774915200
            win_end = 1790812800
            prior_start = 1727740800
            prior_end = 1759276800

            prior_props = [
                {"id": "prior_1", "title": "Prior 1", "created": prior_start + 1000, "end": prior_start + 2000, "state": "closed", "votes": 4, "scores_total": 400.0, "quorum": 0},
                {"id": "prior_2", "title": "Prior 2", "created": prior_start + 5000, "end": prior_start + 6000, "state": "closed", "votes": 4, "scores_total": 400.0, "quorum": 0},
            ]
            win_props = [
                {"id": "win_h1_1", "title": "H1 1", "created": win_start + 1000, "end": win_start + 2000, "state": "closed", "votes": 4, "scores_total": 400.0, "quorum": 0},
                {"id": "win_h1_2", "title": "H1 2", "created": win_start + 5000, "end": win_start + 6000, "state": "closed", "votes": 2, "scores_total": 200.0, "quorum": 0},
                {"id": "win_h2_1", "title": "H2 1", "created": h1_end + 1000, "end": h1_end + 2000, "state": "closed", "votes": 2, "scores_total": 200.0, "quorum": 0},
            ]

            votes_map = {
                "prior_1": [
                    {"id": "pv1", "voter": "0xCore1", "vp": 100.0, "choice": 1, "reason": "r", "created": prior_start + 1010},
                    {"id": "pv2", "voter": "0xCore2", "vp": 100.0, "choice": 1, "reason": "", "created": prior_start + 1020},
                    {"id": "pv3", "voter": "0xCore3", "vp": 100.0, "choice": 1, "reason": "", "created": prior_start + 1030},
                    {"id": "pv4", "voter": "0xOld4", "vp": 100.0, "choice": 1, "reason": "", "created": prior_start + 1040},
                ],
                "prior_2": [
                    {"id": "pv5", "voter": "0xCore1", "vp": 100.0, "choice": 1, "reason": "", "created": prior_start + 5010},
                    {"id": "pv6", "voter": "0xCore2", "vp": 100.0, "choice": 1, "reason": "", "created": prior_start + 5020},
                    {"id": "pv7", "voter": "0xCore3", "vp": 100.0, "choice": 1, "reason": "", "created": prior_start + 5030},
                    {"id": "pv8", "voter": "0xOld4", "vp": 100.0, "choice": 1, "reason": "", "created": prior_start + 5040},
                ],
                "win_h1_1": [
                    {"id": "wv1", "voter": "0xCore1", "vp": 100.0, "choice": 1, "reason": "yes", "created": win_start + 1010},
                    {"id": "wv2", "voter": "0xCore2", "vp": 100.0, "choice": 1, "reason": "", "created": win_start + 1020},
                    {"id": "wv3", "voter": "0xNew1", "vp": 100.0, "choice": 1, "reason": "", "created": win_start + 1030},
                    {"id": "wv4", "voter": "0xNew2", "vp": 100.0, "choice": 1, "reason": "", "created": win_start + 1040},
                ],
                "win_h1_2": [
                    {"id": "wv5", "voter": "0xCore1", "vp": 100.0, "choice": 1, "reason": "ok", "created": win_start + 5010},
                    {"id": "wv6", "voter": "0xCore2", "vp": 100.0, "choice": 1, "reason": "", "created": win_start + 5020},
                ],
                "win_h2_1": [
                    {"id": "wv7", "voter": "0xCore1", "vp": 100.0, "choice": 1, "reason": "", "created": h1_end + 1010},
                    {"id": "wv8", "voter": "0xCore2", "vp": 100.0, "choice": 1, "reason": "", "created": h1_end + 1020},
                ],
            }

            api_double = InMemorySnapshotDouble(
                spaces={space_id: {"id": space_id, "name": "Retention DAO", "verified": True, "strategies": [{"name": "erc20-votes", "params": {}}]}},
                proposals={space_id: prior_props + win_props},
                votes=votes_map,
            )

            cfg_path = tmp_path / "test_config.json"
            cfg_path.write_text(json.dumps({
                "endpoint": "https://hub.snapshot.org/graphql",
                "window_start_ts": win_start,
                "window_end_ts": win_end,
                "h1_end_ts": h1_end,
                "prior_start_ts": prior_start,
                "prior_end_ts": prior_end,
                "rate_limit_sleep_sec": 0.0,
                "spaces": [{
                    "rank": 1,
                    "space": space_id,
                    "name": "Retention DAO",
                    "symbol": "RDAO",
                    "network": "1",
                    "instrument_class": "D",
                    "holder_token_chain": 1,
                    "holder_token_address": "0x1111111111111111111111111111111111111111"
                }]
            }), encoding="utf-8")

            salt_file = tmp_path / "PRIVATE_salt.txt"
            collector = SnapshotCollector(cache_dir=tmp_path / "cache", sleep_sec=0.0, transport=api_double)
            holder_collector = HolderCollector(cache_dir=tmp_path / "cache", sleep_sec=0.0, transport=lambda c, a: 1000)

            res1 = run_observatory(
                config_path=cfg_path,
                fetch_holders=True,
                fetch_prior_votes=True,
                out_dir=tmp_path / "out1",
                cache_dir=tmp_path / "cache",
                salt_file=salt_file,
                collector=collector,
                holder_collector=holder_collector,
            )
            row = res1["summary"][0]
            self.assertAlmostEqual(row["median_voters_per_proposal"], 2.0)
            self.assertAlmostEqual(row["h1_median"], 3.0)
            self.assertAlmostEqual(row["h2_median"], 2.0)
            self.assertAlmostEqual(row["prior_median"], 4.0)
            self.assertAlmostEqual(row["yoy_pct"], -50.0)
            self.assertAlmostEqual(row["core_retention_pct"], 50.0)
            self.assertEqual(row["token_holders"], 1000)
            self.assertEqual(row["holders_minus_voters"], 996)

            res2 = run_observatory(
                config_path=cfg_path,
                fetch_holders=True,
                fetch_prior_votes=True,
                out_dir=tmp_path / "out2",
                cache_dir=tmp_path / "cache",
                salt_file=salt_file,
                collector=collector,
                holder_collector=holder_collector,
            )
            v1 = [r["voter_id"] for r in res1["top10_by_dao"][space_id]]
            v2 = [r["voter_id"] for r in res2["top10_by_dao"][space_id]]
            self.assertEqual(v1, v2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
