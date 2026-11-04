"""VP instrument class coding (T, D, L, N, W, C) from Snapshot strategy names and labels."""
from __future__ import annotations
from typing import Dict, Iterable, List, Set

CLASS_ORDER = ["T", "D", "L", "N", "W", "C"]


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
    for s in strategies:
        name = str(s.get("name") or "").lower()
        params = s.get("params") or {}
        label = str(params.get("symbol") or params.get("name") or "").lower()
        combined = f"{name} {label}"

        if any(k in combined for k in ["whitelist", "csv"]):
            found.add("W")
        if any(k in combined for k in ["erc721", "erc1155", "nft", "estate", "land"]):
            found.add("N")
        if any(k in combined for k in ["delegat", "erc20-votes", "comp-vote", "uni", "with-delegated"]):
            found.add("D")
        if any(k in combined for k in ["stake", "staked", "lock", "locked", "vest", "ve", "vlsdt", "veyfi", " masterchef"]):
            found.add("L")
        if any(k in combined for k in ["contract-call", "multichain"]):
            found.add("C")
        if any(k in combined for k in ["erc20-balance-of", "balance-of", "erc20-with-balance"]):
            found.add("T")

    if not found:
        return "C"
    return "+".join(c for c in CLASS_ORDER if c in found)
