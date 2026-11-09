"""VP instrument class coding (T, D, L, N, W, C) from Snapshot strategy names and labels."""
from __future__ import annotations
import re
from typing import Dict, Iterable, List, Set

CLASS_ORDER = ["T", "D", "L", "N", "W", "C"]

# Wrapper strategies whose own name says nothing about the instrument; their inner
# strategies (params.strategies / params.strategy) are coded instead.
_WRAPPERS = {"multichain", "pagination", "math", "with-delegation"}


def _tokens(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def _code_one(name: str, label: str, found: Set[str]) -> None:
    combined = f"{name} {label}"
    toks = _tokens(combined)
    tokset = set(toks)

    if "whitelist" in combined or "csv" in tokset:
        found.add("W")
    if any(k in combined for k in ["erc721", "erc1155", "nft"]) or tokset & {"estate", "land"}:
        found.add("N")
    if "delegat" in combined or "erc20-votes" in name or "comp-like-votes" in name or name in {"uni", "comp-vote"} or "votes" in tokset and "erc20" in tokset:
        found.add("D")
    # Locked/staked/vesting: whole-word matches or ve*/vl* token prefixes (veYFI, veCRV, vlCVX, vlSDT).
    # Substring matching here used to tag e.g. "curve", "average" or "block" as L.
    lock_words = {"stake", "staked", "staking", "lock", "locked", "locker", "vest", "vesting", "vested", "masterchef"}
    if tokset & lock_words or any(re.fullmatch(r"(ve|vl)[a-z]{2,6}", t) for t in toks if t not in {"vest", "velo", "very"}):
        found.add("L")
    if "contract-call" in name:
        found.add("C")
    if "balance-of" in name or "erc20-with-balance" in name:
        found.add("T")


def code_instrument_class(strategies: Iterable[Dict]) -> str:
    """
    Code voting-power instrument class from strategy names and params.
    Classes:
      T = plain token balance (erc20-balance-of, etc.)
      D = delegated votes (erc20-votes, delegation, etc.)
      L = locked / staked / vesting positions (ve, staked, lock, vest, vl)
      N = NFT-based (erc721, erc1155, nft)
      W = allocation / whitelist (whitelist, csv, multichain-whitelist)
      C = contract-defined (contract-call, custom contract method)
    """
    found: Set[str] = set()
    stack = list(strategies or [])
    while stack:
        s = stack.pop()
        if not isinstance(s, dict):
            continue
        name = str(s.get("name") or "").lower()
        params = s.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        label = str(params.get("symbol") or params.get("name") or "").lower()

        inner = params.get("strategies")
        if isinstance(params.get("strategy"), dict):
            inner = [params["strategy"]]
        if isinstance(inner, list) and inner:
            stack.extend(inner)
            if name == "with-delegation":
                found.add("D")
            if name in _WRAPPERS:
                continue
        _code_one(name, label, found)

    if not found:
        return "C"
    return "+".join(c for c in CLASS_ORDER if c in found)
