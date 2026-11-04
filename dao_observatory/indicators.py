"""Indicator functions for DAO Governance Observatory (Breadth, Concentration, Continuity, Deliberation, Trend)."""
from __future__ import annotations
import hashlib
import os
import secrets
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import numpy as np


def get_or_create_salt(salt_file: Path = Path("data/raw/PRIVATE_pseudonym_salt.txt")) -> str:
    """Return DAOOBS_SALT env var or read/create private salt file."""
    env_salt = os.environ.get("DAOOBS_SALT", "").strip()
    if env_salt:
        return env_salt
    salt_file.parent.mkdir(parents=True, exist_ok=True)
    if salt_file.exists():
        return salt_file.read_text(encoding="utf-8").strip()
    new_salt = secrets.token_hex(32)
    salt_file.write_text(new_salt + "\n", encoding="utf-8")
    return new_salt


def pseudonymise_address(address: str, salt: str) -> str:
    """Return salted SHA-256 pseudonym V<10 hex chars> for a blockchain address."""
    norm = (address or "").strip().lower()
    digest = hashlib.sha256(f"{salt}:{norm}".encode("utf-8")).hexdigest()
    return f"V{digest[:10]}"


def gini_coefficient(values: Sequence[float]) -> float:
    """Compute Gini coefficient on positive voting power values (VP > 0)."""
    arr = np.asarray([float(v) for v in values if float(v) > 0.0], dtype=np.float64)
    n = arr.size
    if n == 0:
        return float("nan")
    if n == 1:
        return 0.0
    total = arr.sum()
    if total <= 0.0:
        return float("nan")
    arr_sorted = np.sort(arr)
    index = np.arange(1, n + 1, dtype=np.float64)
    return float((2.0 * np.sum(index * arr_sorted)) / (n * total) - (n + 1.0) / n)


def nakamoto_coefficient(values: Sequence[float], threshold: float = 0.50) -> int:
    """Smallest number of addresses holding strictly more than `threshold` (50%) of total VP cast."""
    arr = np.asarray([float(v) for v in values if float(v) > 0.0], dtype=np.float64)
    if arr.size == 0 or arr.sum() <= 0.0:
        return 0
    arr_desc = np.sort(arr)[::-1]
    cum_shares = np.cumsum(arr_desc) / arr_desc.sum()
    exceeding = np.where(cum_shares > threshold)[0]
    if exceeding.size == 0:
        return int(arr.size)
    return int(exceeding[0]) + 1


def top_k_share(values: Sequence[float], k: int = 1) -> float:
    """Share (0..100 %) of total VP cast held by top k addresses."""
    arr = np.asarray([float(v) for v in values if float(v) > 0.0], dtype=np.float64)
    if arr.size == 0 or arr.sum() <= 0.0:
        return float("nan")
    arr_desc = np.sort(arr)[::-1]
    return float(arr_desc[:k].sum() / arr_desc.sum() * 100.0)


def hhi_index(values: Sequence[float]) -> float:
    """Herfindahl-Hirschman Index (sum of squared shares in 0..1) on VP cast."""
    arr = np.asarray([float(v) for v in values if float(v) > 0.0], dtype=np.float64)
    if arr.size == 0 or arr.sum() <= 0.0:
        return float("nan")
    shares = arr / arr.sum()
    return float(np.sum(shares ** 2))


def lorenz_curve_points(values: Sequence[float]) -> Tuple[np.ndarray, np.ndarray]:
    """Return (x_pop_share, y_vp_share) arrays starting at (0,0) and ending at (1,1)."""
    arr = np.asarray([float(v) for v in values if float(v) > 0.0], dtype=np.float64)
    if arr.size == 0 or arr.sum() <= 0.0:
        return np.array([0.0, 1.0]), np.array([0.0, 1.0])
    arr_sorted = np.sort(arr)
    x = np.concatenate([[0.0], np.arange(1, arr_sorted.size + 1) / arr_sorted.size])
    y = np.concatenate([[0.0], np.cumsum(arr_sorted) / arr_sorted.sum()])
    return x, y


def compute_proposal_metrics(
    proposals: List[Dict],
    votes_by_proposal: Dict[str, List[Dict]],
    active_electorate_size: int
) -> List[Dict]:
    """Compute per-proposal participation, concentration, and reason share metrics."""
    rows = []
    for prop in sorted(proposals, key=lambda p: int(p.get("created", 0))):
        pid = str(prop["id"])
        p_votes = votes_by_proposal.get(pid, [])
        vps = [float(v.get("vp", 0.0) or 0.0) for v in p_votes]
        voters_count = len(p_votes) if p_votes else int(prop.get("votes", 0) or 0)
        reasons_count = sum(1 for v in p_votes if str(v.get("reason") or "").strip())
        reason_share_pct = (reasons_count / len(p_votes) * 100.0) if p_votes else float("nan")
        turnout_pct = (voters_count / active_electorate_size * 100.0) if active_electorate_size > 0 else float("nan")
        rows.append({
            "proposal_id": pid,
            "title": prop.get("title", ""),
            "created": int(prop.get("created", 0)),
            "voters": voters_count,
            "non_voting_active_addresses": max(0, active_electorate_size - voters_count) if active_electorate_size > 0 else None,
            "turnout_active_electorate_pct": round(turnout_pct, 2) if not np.isnan(turnout_pct) else None,
            "vp_cast": float(sum(vps)),
            "scores_total_api": float(prop.get("scores_total", 0.0) or 0.0),
            "gini": round(gini_coefficient(vps), 4) if vps else None,
            "nakamoto50": nakamoto_coefficient(vps, 0.50) if vps else None,
            "top1_pct": round(top_k_share(vps, 1), 2) if vps else None,
            "top5_pct": round(top_k_share(vps, 5), 2) if vps else None,
            "top10_pct": round(top_k_share(vps, 10), 2) if vps else None,
            "hhi": round(hhi_index(vps), 4) if vps else None,
            "reason_share_pct": round(reason_share_pct, 2) if not np.isnan(reason_share_pct) else None,
        })
    return rows


def compute_voter_table(
    proposals: List[Dict],
    votes_by_proposal: Dict[str, List[Dict]],
    salt: str
) -> Tuple[List[Dict], Dict[str, float]]:
    """
    Compute per-voter table across all proposals with votes in the window.
    Core proxy = addresses voting on at least half (>= n_props / 2) of proposals with votes.
    """
    props_with_votes = [p for p in proposals if int(p.get("votes", 0) or len(votes_by_proposal.get(str(p["id"]), []))) > 0]
    n_props = len(props_with_votes)
    if n_props == 0:
        return [], {"unique_voters": 0, "core_count": 0, "core_vp_share_pct": float("nan"), "window_gini": float("nan"), "window_nakamoto50": 0, "reason_share_pct": float("nan")}

    voter_stats: Dict[str, Dict] = {}
    total_window_vp = 0.0
    total_votes_cast = 0
    total_reasons = 0

    for p in props_with_votes:
        pid = str(p["id"])
        p_votes = votes_by_proposal.get(pid, [])
        prop_vp_sum = sum(float(v.get("vp", 0.0) or 0.0) for v in p_votes)
        for v in p_votes:
            addr = str(v["voter"]).strip().lower()
            vp = float(v.get("vp", 0.0) or 0.0)
            created = int(v.get("created", 0) or 0)
            has_reason = 1 if str(v.get("reason") or "").strip() else 0
            prop_share = (vp / prop_vp_sum * 100.0) if prop_vp_sum > 0 else 0.0

            total_window_vp += vp
            total_votes_cast += 1
            total_reasons += has_reason

            if addr not in voter_stats:
                voter_stats[addr] = {
                    "raw_address": addr,
                    "voter_id": pseudonymise_address(addr, salt),
                    "votes": 0,
                    "vp_total": 0.0,
                    "prop_shares": [],
                    "reasons": 0,
                    "first_vote": created,
                    "last_vote": created,
                }
            rec = voter_stats[addr]
            rec["votes"] += 1
            rec["vp_total"] += vp
            rec["prop_shares"].append(prop_share)
            rec["reasons"] += has_reason
            if created < rec["first_vote"] or rec["first_vote"] == 0:
                rec["first_vote"] = created
            if created > rec["last_vote"]:
                rec["last_vote"] = created

    # Sort descending by vp_total, then by votes, then by voter_id
    sorted_voters = sorted(
        voter_stats.values(),
        key=lambda r: (-r["vp_total"], -r["votes"], r["voter_id"])
    )

    cum_pct = 0.0
    voter_rows = []
    core_vp = 0.0
    core_count = 0
    for rank, rec in enumerate(sorted_voters, start=1):
        share_pct = (rec["vp_total"] / total_window_vp * 100.0) if total_window_vp > 0 else 0.0
        cum_pct += share_pct
        is_core = (rec["votes"] * 2) >= n_props  # at least half of window's proposals with votes
        if is_core:
            core_count += 1
            core_vp += rec["vp_total"]
        voter_rows.append({
            "rank": rank,
            "voter_id": rec["voter_id"],
            "raw_address": rec["raw_address"],
            "votes": rec["votes"],
            "proposals_total": n_props,
            "participation": round(rec["votes"] / n_props, 6),
            "vp_total": rec["vp_total"],
            "vp_share_pct": round(share_pct, 4),
            "cum_share_pct": round(cum_pct, 4),
            "mean_prop_share_pct": round(float(np.mean(rec["prop_shares"])), 4) if rec["prop_shares"] else 0.0,
            "reasons": rec["reasons"],
            "first_vote": rec["first_vote"],
            "last_vote": rec["last_vote"],
            "core": is_core,
        })

    all_vps = [r["vp_total"] for r in sorted_voters]
    summary = {
        "unique_voters": len(voter_rows),
        "core_count": core_count,
        "core_vp_share_pct": round(core_vp / total_window_vp * 100.0, 2) if total_window_vp > 0 else float("nan"),
        "window_gini": round(gini_coefficient(all_vps), 4) if all_vps else float("nan"),
        "window_nakamoto50": nakamoto_coefficient(all_vps, 0.50) if all_vps else 0,
        "reason_share_pct": round(total_reasons / total_votes_cast * 100.0, 2) if total_votes_cast > 0 else float("nan"),
    }
    return voter_rows, summary


def compute_core_retention(
    prior_voter_rows: List[Dict],
    current_voter_rows: List[Dict]
) -> Optional[float]:
    """Share (0..100 %) of prior window's core addresses that remain in the current window's core."""
    prior_core = {r["voter_id"] for r in prior_voter_rows if r.get("core")}
    if not prior_core:
        return None
    current_core = {r["voter_id"] for r in current_voter_rows if r.get("core")}
    retained = len(prior_core.intersection(current_core))
    return round(retained / len(prior_core) * 100.0, 2)
