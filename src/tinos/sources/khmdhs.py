"""ΚΗΜΔΗΣ open-data client with a mandatory per-record guard.

ΚΗΜΔΗΣ is the central register of public contracts (Κεντρικό Ηλεκτρονικό
Μητρώο Δημοσίων Συμβάσεων), keyless, CC BY 4.0. Contract (FINDINGS.md,
verified by probe 2026-09-25):

- ``POST {base}/{endpoint}?page=N`` with a JSON body
  ``{"organizations": [uid], "dateFrom": "YYYY-MM-DD", "dateTo": "YYYY-MM-DD"}``.
  The organisation uid is Diavgeia's (6296 is Δήμος Τήνου). Endpoints, with
  the record type in each referenceNumber: ``request`` (REQ, αίτημα),
  ``notice`` (PROC, προκήρυξη), ``auction`` (AWRD, κατακύρωση/ανάθεση),
  ``contract`` (SYMV, σύμβαση), ``payment`` (PAY, εντολή πληρωμής).
- ``dateFrom``/``dateTo`` filter ``submissionDate``; both bounds inclusive.
- Ranges wider than 180 days are SILENTLY truncated to
  ``[dateTo - 180 days, dateTo]``, and a request without dates silently gets a
  recent default window. HTTP 200 both ways, and unlike Diavgeia nothing in
  the response echoes the executed filter. Hence: both dates always, windows
  of at most ``MAX_SPAN_DAYS`` (refused client-side), and every record is
  checked against the request (:func:`check_page`). A violation raises
  :class:`GuardViolation`; do not loosen it.
- Unknown body fields and malformed dates are rejected with HTTP 400.
- No match is HTTP 404 ``{"message": "No ... found for the given criteria"}``,
  not an empty page.
- 50 records per page, unsorted. Paging was stable in tests (445 of 445
  distinct over 9 pages); :meth:`KhmdhsClient.search_all` checks it anyway.
- The service throttles with HTTP 429 and no Retry-After header: we pace at
  ``settings.khmdhs_delay`` and back off exponentially.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterator

import httpx

from tinos.config import Settings

ENDPOINTS = ("request", "notice", "auction", "contract", "payment")
MAX_SPAN_DAYS = 180
_NOT_FOUND_RE = re.compile(r"^No .* found for the given criteria")


class GuardViolation(Exception):
    """A response that does not answer exactly the query we sent."""


@dataclass(frozen=True)
class SearchRequest:
    endpoint: str
    org: str
    date_from: date  # inclusive
    date_to: date  # inclusive
    page: int = 0

    def __post_init__(self) -> None:
        if self.endpoint not in ENDPOINTS:
            raise ValueError(f"unknown ΚΗΜΔΗΣ endpoint {self.endpoint!r}")
        if self.date_to < self.date_from:
            raise ValueError("date_to before date_from")
        if (self.date_to - self.date_from).days > MAX_SPAN_DAYS:
            raise ValueError(f"{self.date_from}..{self.date_to} spans more than {MAX_SPAN_DAYS} days; "
                             "the server would silently truncate it")

    def body(self) -> dict[str, Any]:
        return {"organizations": [self.org], "dateFrom": self.date_from.isoformat(),
                "dateTo": self.date_to.isoformat()}

    def at_page(self, page: int) -> "SearchRequest":
        return SearchRequest(self.endpoint, self.org, self.date_from, self.date_to, page)


@dataclass(frozen=True)
class SearchPage:
    request: SearchRequest
    raw: dict[str, Any]

    @property
    def records(self) -> list[dict[str, Any]]:
        return list(self.raw.get("content") or [])

    @property
    def total(self) -> int:
        return int(self.raw.get("totalElements", 0))

    @property
    def total_pages(self) -> int:
        return int(self.raw.get("totalPages", 0))


def check_page(req: SearchRequest, raw: dict[str, Any]) -> None:
    """Raise GuardViolation unless ``raw`` is a page of exactly ``req``.

    Checked: envelope shape and page number; on every record the
    organisation key, a referenceNumber, and a submissionDate inside the
    requested window (the one field the date filter applies to).
    """
    problems: list[str] = []
    content = raw.get("content")
    if not isinstance(content, list) or not isinstance(raw.get("totalElements"), int):
        raise GuardViolation(f"{req.endpoint} page {req.page}: not a search page: keys={sorted(raw)[:12]}")
    if raw.get("number") != req.page:
        problems.append(f"page requested={req.page} returned={raw.get('number')}")
    lo, hi = req.date_from.isoformat(), req.date_to.isoformat()
    for rec in content:
        ref = rec.get("referenceNumber")
        org = (rec.get("organization") or {}).get("key")
        sub = str(rec.get("submissionDate") or "")[:10]
        if not ref:
            problems.append("record without referenceNumber")
        if str(org) != req.org:
            problems.append(f"{ref}: organization {org!r} != {req.org!r}")
        if not lo <= sub <= hi:
            problems.append(f"{ref}: submissionDate {sub!r} outside {lo}..{hi}")
    if problems:
        shown = "; ".join(problems[:5]) + (f" (+{len(problems) - 5} more)" if len(problems) > 5 else "")
        raise GuardViolation(f"{req.endpoint} {req.org} {lo}..{hi} p{req.page}: {shown}")


def iter_windows(start: date, end: date, window_days: int) -> Iterator[tuple[date, date]]:
    """Consecutive inclusive windows [a, b] covering [start, end], no gaps, no overlap."""
    if window_days > MAX_SPAN_DAYS:
        raise ValueError(f"window_days={window_days} exceeds the {MAX_SPAN_DAYS}-day clamp")
    a = start
    while a <= end:
        b = min(a + timedelta(days=window_days), end)
        yield a, b
        a = b + timedelta(days=1)


class KhmdhsClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._http = httpx.Client(
            base_url=settings.khmdhs_base,
            headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
            timeout=settings.request_timeout,
        )
        self.calls = 0
        self.throttled = 0

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "KhmdhsClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def post_raw(self, endpoint: str, body: dict[str, Any], page: int = 0) -> httpx.Response:
        """One call, paced; HTTP 429 is retried with exponential back-off.

        Unguarded: for diagnostics (``tinos khmdhs-doctor``) only. Ingestion
        goes through :meth:`search_page`.
        """
        if endpoint not in ENDPOINTS:
            raise ValueError(f"unknown ΚΗΜΔΗΣ endpoint {endpoint!r}")
        for attempt in range(self.settings.khmdhs_max_retries + 1):
            resp = self._http.post(f"/{endpoint}", params={"page": page}, json=body)
            self.calls += 1
            time.sleep(self.settings.khmdhs_delay)
            if resp.status_code != 429:
                return resp
            self.throttled += 1
            time.sleep(self.settings.khmdhs_backoff * 2 ** attempt)
        resp.raise_for_status()
        return resp

    def search_page(self, req: SearchRequest) -> SearchPage:
        resp = self.post_raw(req.endpoint, req.body(), req.page)
        if resp.status_code == 404:
            # "Nothing matched" arrives as 404 with a message; any other 404 is an error.
            try:
                msg = str(resp.json().get("message", ""))
            except ValueError:
                msg = ""
            if not _NOT_FOUND_RE.match(msg):
                resp.raise_for_status()
            raw = {"content": [], "totalElements": 0, "totalPages": 0, "number": req.page, "notFound": msg}
        else:
            resp.raise_for_status()
            raw = resp.json()
        check_page(req, raw)
        return SearchPage(req, raw)

    def search_all(self, req: SearchRequest) -> Iterator[SearchPage]:
        """Every page of one window. The total must hold across pages and the
        distinct referenceNumbers must add up to it."""
        first = self.search_page(req.at_page(0))
        yield first
        refs = {r["referenceNumber"] for r in first.records}
        for n in range(1, first.total_pages):
            page = self.search_page(req.at_page(n))
            if page.total != first.total:
                raise GuardViolation(f"{req.endpoint} {req.org} {req.date_from}..{req.date_to}: "
                                     f"total changed while paging ({first.total} -> {page.total})")
            refs.update(r["referenceNumber"] for r in page.records)
            yield page
        if len(refs) != first.total:
            raise GuardViolation(f"{req.endpoint} {req.org} {req.date_from}..{req.date_to}: "
                                 f"{len(refs)} distinct records for totalElements={first.total}")
