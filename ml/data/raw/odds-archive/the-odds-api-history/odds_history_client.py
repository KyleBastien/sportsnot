"""Quota-guarded The Odds API client with secret-safe request logging."""

from __future__ import annotations

import gzip
import http.client
import json
import time
from typing import Any
from urllib.parse import urlencode

from odds_history_models import API_HOST, API_ROOT, MIN_REMAINING, ApiRequest, ClientSettings


def _quota_headers(headers: dict[str, str]) -> dict[str, int | None]:
    return {
        "remaining": _optional_int(headers.get("x-requests-remaining")),
        "used": _optional_int(headers.get("x-requests-used")),
        "last": _optional_int(headers.get("x-requests-last")),
    }


def _optional_int(value: str | None) -> int | None:
    return int(value) if value is not None else None


class Client:
    def __init__(self, settings: ClientSettings) -> None:
        self.settings = settings
        self.estimated = 0
        self.actual = 0
        self.network_calls = 0
        self.calls: list[dict[str, Any]] = []

    def _perform(self, request: ApiRequest) -> tuple[int, bytes, dict[str, str]]:
        query = urlencode({"apiKey": self.settings.api_key, **request.params})
        connection = http.client.HTTPSConnection(API_HOST, timeout=180)
        try:
            connection.request(
                "GET",
                f"{API_ROOT}{request.path}?{query}",
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "User-Agent": "sportsnot-odds-archive/1",
                },
            )
            response = connection.getresponse()
            body = response.read()
            headers = {key.lower(): value for key, value in response.getheaders()}
            return response.status, body, headers
        except Exception as exc:
            raise RuntimeError(
                f"{request.label}: request failed ({type(exc).__name__}); URL suppressed"
            ) from None
        finally:
            connection.close()

    def _save_response(self, request: ApiRequest, body: bytes) -> None:
        output = self.settings.scratch / request.output_name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(gzip.compress(body, mtime=0))

    def _record(self, request: ApiRequest, status: int, quota: dict[str, int | None]) -> None:
        record = {
            "label": request.label,
            "status": status,
            "estimated_cost": request.estimated_cost,
            "quota": quota,
            "raw_file": request.output_name,
            "path": request.path,
            "params": request.params,
        }
        self.calls.append(record)
        if self.settings.request_log is None:
            return
        self.settings.request_log.parent.mkdir(parents=True, exist_ok=True)
        with self.settings.request_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _report(self, request: ApiRequest, status: int, quota: dict[str, int | None]) -> None:
        interval = self.settings.progress_every
        if interval != 1 and self.network_calls != 1 and self.network_calls % interval:
            return
        print(
            f"{request.label}: HTTP {status}; "
            f"x-requests-remaining={quota['remaining']}; "
            f"x-requests-used={quota['used']}; x-requests-last={quota['last']}",
            flush=True,
        )

    def _enforce_quota(self, quota: dict[str, int | None]) -> None:
        remaining = quota["remaining"]
        if remaining is not None and remaining < MIN_REMAINING:
            raise RuntimeError(f"quota guard: remaining {remaining} below {MIN_REMAINING}")
        if self.actual > self.settings.max_credits:
            raise RuntimeError(
                f"credit guard: actual {self.actual} exceeds {self.settings.max_credits}"
            )

    def _parse(self, request: ApiRequest, body: bytes) -> dict[str, Any] | list[Any]:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"{request.label}: non-JSON response saved outside repo; URL suppressed"
            ) from None
        if not isinstance(parsed, dict | list):
            raise RuntimeError(f"{request.label}: unexpected JSON root")
        return parsed

    def get(self, request: ApiRequest) -> dict[str, Any] | list[Any]:
        projected = self.estimated + request.estimated_cost
        if projected > self.settings.max_credits:
            raise RuntimeError(f"credit guard: {projected} exceeds {self.settings.max_credits}")
        self.estimated = projected
        if self.settings.delay:
            time.sleep(self.settings.delay)
        status, body, headers = self._perform(request)
        self._save_response(request, body)
        quota = _quota_headers(headers)
        self.actual += quota["last"] or 0
        self.network_calls += 1
        self._record(request, status, quota)
        self._report(request, status, quota)
        self._enforce_quota(quota)
        if status not in request.allowed_statuses:
            raise RuntimeError(
                f"{request.label}: HTTP {status}; response saved outside repo; URL suppressed"
            )
        return self._parse(request, body)
