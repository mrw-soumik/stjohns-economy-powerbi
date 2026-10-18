"""Minimal client for the Statistics Canada Web Data Service (WDS).

Documentation: https://www.statcan.gc.ca/en/developers/wds/user-guide
The client sends a descriptive User-Agent, waits at least one second between
requests and retries transient errors with exponential backoff.
"""

from __future__ import annotations

import time
from typing import Iterable

import requests

WDS_BASE = "https://www150.statcan.gc.ca/t1/wds/rest"
USER_AGENT = (
    "stjohns-economy-powerbi/0.1 (portfolio research; contact mostafa.wasib73@gmail.com)"
)


class WdsError(RuntimeError):
    """Raised when the WDS returns an error or an unexpected payload."""


class WdsClient:
    def __init__(self, min_interval: float = 1.0, timeout: float = 90.0, retries: int = 4):
        self.min_interval = min_interval
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        self._last_request = 0.0
        self.request_log: list[dict] = []

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _call(self, method: str, url: str, json_body=None):
        for attempt in range(1, self.retries + 1):
            self._throttle()
            try:
                resp = self.session.request(method, url, json=json_body, timeout=self.timeout)
            except requests.RequestException as exc:  # network hiccup
                if attempt == self.retries:
                    raise WdsError(f"{method} {url} failed: {exc}") from exc
                time.sleep(2 ** attempt)
                continue
            self.request_log.append({"method": method, "url": url, "status": resp.status_code})
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                time.sleep(2 ** attempt)
                continue
            if resp.status_code != 200:
                raise WdsError(f"{method} {url} returned HTTP {resp.status_code}: {resp.text[:300]}")
            try:
                return resp.json()
            except ValueError as exc:
                raise WdsError(f"{method} {url} did not return JSON") from exc
        raise WdsError(f"{method} {url} failed after {self.retries} attempts")

    @staticmethod
    def _objects(payload, what: str) -> list[dict]:
        if not isinstance(payload, list):
            raise WdsError(f"{what}: expected a list, got {type(payload).__name__}")
        failed = [p for p in payload if p.get("status") != "SUCCESS"]
        if failed:
            raise WdsError(f"{what}: {len(failed)} item(s) failed, first: {failed[0]}")
        return [p["object"] for p in payload]

    def series_info(self, vector_ids: Iterable[int]) -> list[dict]:
        body = [{"vectorId": int(v)} for v in vector_ids]
        return self._objects(self._call("POST", f"{WDS_BASE}/getSeriesInfoFromVector", body), "getSeriesInfoFromVector")

    def cube_metadata(self, product_ids: Iterable[int]) -> list[dict]:
        body = [{"productId": int(p)} for p in product_ids]
        return self._objects(self._call("POST", f"{WDS_BASE}/getCubeMetadata", body), "getCubeMetadata")

    def code_sets(self) -> dict:
        payload = self._call("GET", f"{WDS_BASE}/getCodeSets")
        if not isinstance(payload, dict) or payload.get("status") != "SUCCESS":
            raise WdsError("getCodeSets: unexpected payload")
        return payload["object"]

    def data_by_reference_period(self, vector_ids: Iterable[int], start: str, end: str) -> list[dict]:
        # The WDS expects quoted IDs; quotes must be percent-encoded, commas kept literal.
        ids = ",".join(f"%22{int(v)}%22" for v in vector_ids)
        url = (
            f"{WDS_BASE}/getDataFromVectorByReferencePeriodRange?vectorIds={ids}"
            f"&startRefPeriod={start}&endReferencePeriod={end}"
        )
        return self._objects(self._call("GET", url), "getDataFromVectorByReferencePeriodRange")
