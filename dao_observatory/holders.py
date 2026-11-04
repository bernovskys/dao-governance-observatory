"""Token holder count retrieval from public Blockscout v2 APIs (Ethereum Mainnet & Arbitrum One)."""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Callable, Dict, Optional

BLOCKSCOUT_BASE = {
    1: "https://eth.blockscout.com/api/v2/tokens",
    42161: "https://arbitrum.blockscout.com/api/v2/tokens",
}


class HolderCollector:
    """Fetches indicative token holder counts from Blockscout v2 REST API with caching."""

    def __init__(
        self,
        cache_dir: Path = Path("data/raw/cache"),
        sleep_sec: float = 0.5,
        transport: Optional[Callable[[int, str], Optional[int]]] = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sleep_sec = sleep_sec
        self.transport = transport

    def fetch_holder_count(self, chain_id: Optional[int], token_address: Optional[str]) -> Optional[int]:
        if not chain_id or not token_address or str(token_address).lower() == "nan":
            return None
        addr = str(token_address).strip()
        cache_file = self.cache_dir / f"holders_{chain_id}_{addr.lower()}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return data.get("holders_count")

        if self.transport is not None:
            cnt = self.transport(int(chain_id), addr)
            cache_file.write_text(json.dumps({"holders_count": cnt}), encoding="utf-8")
            return cnt

        base_url = BLOCKSCOUT_BASE.get(int(chain_id))
        if not base_url:
            return None

        url = f"{base_url}/{addr}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "DAO-Governance-Observatory/1.0 (Academic Research; RTU)",
        }
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            raw_holders = payload.get("holders") or payload.get("holders_count")
            holders_count = int(raw_holders) if raw_holders is not None else None
            cache_file.write_text(json.dumps({"holders_count": holders_count, "source": url}), encoding="utf-8")
            if self.sleep_sec > 0:
                time.sleep(self.sleep_sec)
            return holders_count
        except Exception:
            return None
