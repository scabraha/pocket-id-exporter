"""HTTP client for the Pocket-ID admin API."""

from __future__ import annotations

import logging
import time
from typing import Any, Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)


class PocketIDClient:
    """Thin wrapper over the Pocket-ID REST API.

    Uses a single requests.Session with retry/backoff for transient failures
    so callers don't need to care about flaky networking.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: int = 30,
        page_size: int = 100,
        session: requests.Session | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._page_size = page_size
        self._session = session or self._build_session(api_key)

    @staticmethod
    def _build_session(api_key: str) -> requests.Session:
        session = requests.Session()
        session.headers.update({"X-API-Key": api_key})
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET an API path and return the parsed JSON body.

        Raises a ``requests.HTTPError`` with a message that includes the
        status code, target path, and a short body excerpt — which is far
        more useful in operator logs than the default Requests output.
        """
        url = f"{self._base_url}{path}"
        started = time.monotonic()
        resp = self._session.get(url, params=params, timeout=self._timeout)
        duration_ms = (time.monotonic() - started) * 1000

        log.debug(
            "HTTP GET %s -> %d in %.0fms",
            path, resp.status_code, duration_ms,
        )

        if not resp.ok:
            snippet = (resp.text or "")[:200].replace("\n", " ")
            hint = ""
            if resp.status_code in (401, 403):
                hint = " (check POCKET_ID_API_KEY and that the key has admin scope)"
            raise requests.HTTPError(
                f"{resp.status_code} {resp.reason} from {path}{hint}: {snippet}",
                response=resp,
            )

        return resp.json()

    def total_items(self, path: str) -> int:
        """Return ``pagination.totalItems`` from a paginated endpoint."""
        data = self.get(path, {"pagination[page]": 1, "pagination[limit]": 1})
        return int(data.get("pagination", {}).get("totalItems", 0))

    def iter_audit_logs(self, *, ascending: bool = True) -> Iterator[dict[str, Any]]:
        """Yield audit-log entries page by page in the requested order."""
        direction = "asc" if ascending else "desc"
        page = 1
        while True:
            data = self.get(
                "/api/audit-logs/all",
                {
                    "pagination[page]": page,
                    "pagination[limit]": self._page_size,
                    "sort[column]": "createdAt",
                    "sort[direction]": direction,
                },
            )
            entries = data.get("data", []) or []
            for entry in entries:
                yield entry

            pagination = data.get("pagination", {})
            total_pages = int(pagination.get("totalPages", 1) or 1)
            if page >= total_pages or not entries:
                return
            page += 1

    def fetch_audit_logs_since(self, since_iso: str) -> list[dict[str, Any]]:
        """Return audit-log entries created strictly after ``since_iso``."""
        return [e for e in self.iter_audit_logs(ascending=True)
                if e.get("createdAt", "") > since_iso]

    def version(self) -> str:
        """Return the running Pocket-ID version, or ``"unknown"``."""
        data = self.get("/api/version/current")
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            return str(data.get("version", "unknown"))
        return "unknown"

