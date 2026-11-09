"""Snapshot Hub GraphQL collector with caching, timestamp cursor pagination, and count verification."""
from __future__ import annotations
import hashlib
import http.client
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import urllib.request
import urllib.error


class SnapshotCollector:
    """
    Retrieves proposals, votes, and space metadata from Snapshot Hub GraphQL API.
    Supports an injectable transport function for offline unit/end-to-end testing.
    """

    def __init__(
        self,
        endpoint: str = "https://hub.snapshot.org/graphql",
        cache_dir: Path = Path("data/raw/cache"),
        sleep_sec: float = 1.0,
        max_retries: int = 5,
        transport: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        self.endpoint = endpoint
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sleep_sec = sleep_sec
        self.max_retries = max_retries
        self.transport = transport
        self.network_calls = 0

    def _post_graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {"query": query, "variables": variables or {}}
        if self.transport is not None:
            self.network_calls += 1
            return self.transport(query, variables or {})

        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "DAO-Governance-Observatory/1.0 (Academic Research; RTU)",
        }
        api_key = os.environ.get("SNAPSHOT_API_KEY", "").strip()
        if api_key:
            headers["x-api-key"] = api_key
        for attempt in range(self.max_retries):
            try:
                self.network_calls += 1
                req = urllib.request.Request(self.endpoint, data=data_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = resp.read().decode("utf-8")
                    parsed = json.loads(body)
                # Any GraphQL error (even with partial `data`) would silently truncate results.
                if parsed.get("errors"):
                    raise RuntimeError(f"GraphQL error: {parsed['errors']}")
                if self.sleep_sec > 0:
                    time.sleep(self.sleep_sec)
                return parsed.get("data") or {}
            except (OSError, ValueError, RuntimeError, http.client.HTTPException) as exc:
                # OSError covers URLError/HTTPError, timeouts and connection resets;
                # ValueError covers non-JSON (e.g. HTML error/challenge) responses.
                if attempt + 1 >= self.max_retries:
                    raise
                backoff = (2 ** attempt) * max(1.0, self.sleep_sec)
                print(f"[collector] retry {attempt + 1}/{self.max_retries - 1} after {exc!r}", file=sys.stderr)
                time.sleep(backoff)
        return {}

    def fetch_space_info(self, space_id: str) -> Dict[str, Any]:
        cache_file = self.cache_dir / f"space_{space_id}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
        query = """
        query SpaceInfo($id: String!) {
          space(id: $id) {
            id
            name
            verified
            strategies {
              name
              network
              params
            }
          }
        }
        """
        data = self._post_graphql(query, {"id": space_id})
        space_obj = data.get("space") or {}
        cache_file.write_text(json.dumps(space_obj, indent=2), encoding="utf-8")
        return space_obj

    def fetch_proposals(self, space_id: str, created_gte: int, created_lt: int) -> List[Dict[str, Any]]:
        """
        Fetch all proposals for `space_id` in [created_gte, created_lt) using window splitting / cursor pagination.
        """
        cache_file = self.cache_dir / f"proposals_{space_id}_{created_gte}_{created_lt}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))

        all_props: Dict[str, Dict[str, Any]] = {}
        cursor_gte = int(created_gte)
        page_size = 1000

        query = """
        query ProposalsWindow($space: String!, $gte: Int!, $lt: Int!, $first: Int!, $skip: Int!) {
          proposals(
            first: $first,
            skip: $skip,
            orderBy: "created",
            orderDirection: asc,
            where: { space: $space, created_gte: $gte, created_lt: $lt }
          ) {
            id
            title
            created
            end
            state
            votes
            scores_total
            quorum
          }
        }
        """

        while cursor_gte < created_lt:
            batch = self._post_graphql(
                query,
                {"space": space_id, "gte": cursor_gte, "lt": int(created_lt), "first": page_size, "skip": 0},
            ).get("proposals") or []
            if not batch:
                break
            for p in batch:
                all_props[str(p["id"])] = p
            if len(batch) < page_size:
                break
            max_created = max(int(p["created"]) for p in batch)
            if max_created == cursor_gte:
                # Multiple proposals at same timestamp: paginate via skip
                skip = page_size
                while True:
                    sub = self._post_graphql(
                        query,
                        {"space": space_id, "gte": cursor_gte, "lt": cursor_gte + 1, "first": page_size, "skip": skip},
                    ).get("proposals") or []
                    for p in sub:
                        all_props[str(p["id"])] = p
                    if len(sub) < page_size:
                        break
                    skip += page_size
                cursor_gte = max_created + 1
            else:
                cursor_gte = max_created

        result = sorted(all_props.values(), key=lambda x: (int(x["created"]), str(x["id"])))
        # Only cache windows that are already over; otherwise new proposals would be missed on re-runs.
        if int(created_lt) <= int(time.time()):
            cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    def fetch_votes_for_proposal(self, proposal: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Fetch every vote for a proposal using timestamp cursor + skip tie-breaking when >1000 votes share one timestamp.
        Verifies retrieved count against proposal['votes'] and VP sum against proposal['scores_total'].
        """
        pid = str(proposal["id"])
        pid_hash = hashlib.md5(pid.encode("utf-8")).hexdigest()[:16]
        cache_file = self.cache_dir / f"votes_{pid_hash}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))

        expected_votes = int(proposal.get("votes", 0) or 0)
        if expected_votes == 0:
            return []

        page_size = 1000
        query = """
        query ProposalVotes($proposal: String!, $gte: Int!, $first: Int!, $skip: Int!) {
          votes(
            first: $first,
            skip: $skip,
            orderBy: "created",
            orderDirection: asc,
            where: { proposal: $proposal, created_gte: $gte }
          ) {
            id
            voter
            vp
            choice
            reason
            created
          }
        }
        """

        votes_by_voter: Dict[str, Dict[str, Any]] = {}
        cursor_gte = 0

        while True:
            batch = self._post_graphql(
                query,
                {"proposal": pid, "gte": cursor_gte, "first": page_size, "skip": 0},
            ).get("votes") or []
            if not batch:
                break
            for v in batch:
                voter_key = str(v["voter"]).strip().lower()
                votes_by_voter[voter_key] = v

            if len(batch) < page_size:
                break

            min_ts = min(int(v["created"]) for v in batch)
            max_ts = max(int(v["created"]) for v in batch)

            if min_ts == max_ts:
                # More than `page_size` votes share the exact same timestamp `max_ts`
                skip = page_size
                while True:
                    sub = self._post_graphql(
                        query,
                        {"proposal": pid, "gte": max_ts, "first": page_size, "skip": skip},
                    ).get("votes") or []
                    if not sub:
                        break
                    same_ts_count = 0
                    for v in sub:
                        voter_key = str(v["voter"]).strip().lower()
                        votes_by_voter[voter_key] = v
                        if int(v["created"]) == max_ts:
                            same_ts_count += 1
                    if len(sub) < page_size or same_ts_count == 0:
                        break
                    skip += page_size
                cursor_gte = max_ts + 1
            else:
                cursor_gte = max_ts

        result = sorted(votes_by_voter.values(), key=lambda v: (int(v.get("created", 0)), str(v["voter"]).lower()))

        # Verification against the proposal's own counters (as promised in the docstring).
        if len(result) != expected_votes:
            print(
                f"[collector] WARNING proposal {pid}: retrieved {len(result)} votes, API reports {expected_votes}",
                file=sys.stderr,
            )
        scores_total = float(proposal.get("scores_total", 0.0) or 0.0)
        vp_sum = sum(float(v.get("vp", 0.0) or 0.0) for v in result)
        if scores_total > 0 and abs(vp_sum - scores_total) > max(1e-6, 1e-2 * scores_total):
            print(
                f"[collector] WARNING proposal {pid}: VP sum {vp_sum:.4f} differs from scores_total {scores_total:.4f}",
                file=sys.stderr,
            )

        # Do not cache votes of proposals that are still open: the vote set can still change.
        end_ts = int(proposal.get("end", 0) or 0)
        is_final = str(proposal.get("state") or "closed") == "closed" or (end_ts and end_ts <= int(time.time()))
        if is_final:
            cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
