"""Diavgeia open-data client with a mandatory echo check.

Contract (FINDINGS.md, verified 2026-09-20):

- Diavgeia returns HTTP 200 and silently DROPS parameters it does not know.
- ``issueDate`` ranges are silently CLAMPED to exactly ``from + 180 days``.
- Therefore no response is trusted until ``info.query`` is parsed and shown
  to name the organisation and the exact issueDate bounds we asked for.
  A mismatch raises :class:`EchoMismatch`. That guard is the whole point of
  this module; do not loosen it.

Verified request shape::

    /opendata/search.json?org=<uid>&from_issue_date=YYYY-MM-DD
        &to_issue_date=YYYY-MM-DD&size=<=500&page=N[&status=all]

Verified echo shape (``info.query``)::

    submissionTimestamp:[DT(...) TO DT(...)] AND
    issueDate:[DT(2011-01-01T00:00:00+02:00) TO DT(2011-06-30T00:00:00+03:00)] AND
    organizationUid:"6296" AND status:"Αναρτημένη"

With ``status=all`` the trailing ``status:"..."`` clause is absent and revoked
acts are included. The default here is ``status=all``: an authorised-then-
withdrawn act is exactly what a transparency dataset must surface. The
guard also checks that clause, so a silently dropped ``status=all`` is
caught like any other drift.

The ``to_issue_date`` bound is echoed as local midnight at the start of that
day, while stored ``issueDate`` values are UTC midnight (later than local
midnight in Greece). We therefore treat the upper bound as EXCLUSIVE and
request ``end + 1 day`` to include the last day of a range.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterator

import httpx

from tinos.config import Settings

MAX_PAGE_SIZE = 500
CLAMP_DAYS = 180

_ISSUE_RE = re.compile(r"issueDate:\[DT\(([^)]*)\) TO DT\(([^)]*)\)\]")
_ORG_RE = re.compile(r'organizationUid:"([^"]*)"')
_STATUS_RE = re.compile(r'status:"([^"]*)"')
PUBLISHED_ONLY = "Αναρτημένη"


class EchoMismatch(Exception):
    """The server executed a different query than the one we sent."""


@dataclass(frozen=True)
class SearchRequest:
    org: str
    from_date: date  # inclusive
    to_date: date  # EXCLUSIVE (see module docstring)
    page: int = 0
    size: int = MAX_PAGE_SIZE
    status_all: bool = True

    @property
    def span_days(self) -> int:
        return (self.to_date - self.from_date).days

    def params(self) -> dict[str, str]:
        p = {
            "org": self.org,
            "from_issue_date": self.from_date.isoformat(),
            "to_issue_date": self.to_date.isoformat(),
            "size": str(self.size),
            "page": str(self.page),
        }
        if self.status_all:
            p["status"] = "all"
        return p


@dataclass(frozen=True)
class SearchPage:
    request: SearchRequest
    raw: dict[str, Any]

    @property
    def info(self) -> dict[str, Any]:
        return self.raw.get("info", {})

    @property
    def decisions(self) -> list[dict[str, Any]]:
        return list(self.raw.get("decisions", []))

    @property
    def total(self) -> int:
        return int(self.info.get("total", 0))

    @property
    def actual_size(self) -> int:
        return int(self.info.get("actualSize", len(self.decisions)))


def parse_echo(query: str) -> dict[str, str | None]:
    """Pull the executed org and issueDate bounds out of ``info.query``."""
    m_issue = _ISSUE_RE.search(query or "")
    m_org = _ORG_RE.search(query or "")
    m_status = _STATUS_RE.search(query or "")
    return {
        "org": m_org.group(1) if m_org else None,
        "issue_from": m_issue.group(1)[:10] if m_issue else None,
        "issue_to": m_issue.group(2)[:10] if m_issue else None,
        "status": m_status.group(1) if m_status else None,
    }


def _verify_echo(req: SearchRequest, info: dict[str, Any]) -> dict[str, str | None]:
    """Raise EchoMismatch unless the server echoed exactly what we asked.

    Checked: organisation uid, issueDate lower bound, issueDate upper bound,
    status clause (absent for status=all, "Αναρτημένη" otherwise) and page
    number. Anything else the server adds (submissionTimestamp) is allowed;
    anything we asked for that is missing or altered is not.
    """
    query = info.get("query")
    if not isinstance(query, str) or not query:
        raise EchoMismatch("response carries no info.query; refusing to trust it")
    echo = parse_echo(query)
    problems: list[str] = []
    if echo["org"] != req.org:
        problems.append(f"org requested={req.org!r} executed={echo['org']!r}")
    if echo["issue_from"] != req.from_date.isoformat():
        problems.append(
            f"issueDate.from requested={req.from_date} executed={echo['issue_from']}"
        )
    if echo["issue_to"] != req.to_date.isoformat():
        problems.append(
            f"issueDate.to requested={req.to_date} executed={echo['issue_to']}"
            + (f" (span {req.span_days}d > {CLAMP_DAYS}d clamp)" if req.span_days > CLAMP_DAYS else "")
        )
    want_status = None if req.status_all else PUBLISHED_ONLY
    if echo["status"] != want_status:
        problems.append(
            f"status requested={'all' if req.status_all else want_status!r} "
            f"executed={echo['status']!r}"
        )
    if "page" in info and int(info["page"]) != req.page:
        problems.append(f"page requested={req.page} executed={info['page']}")
    if problems:
        raise EchoMismatch("; ".join(problems) + f" | query={query}")
    return echo


def iter_windows(start: date, end: date, window_days: int) -> Iterator[tuple[date, date]]:
    """Half-open [from, to) windows covering [start, end] inclusive.

    Each window spans at most ``window_days`` (must be <= CLAMP_DAYS).
    """
    if window_days > CLAMP_DAYS:
        raise ValueError(f"window_days={window_days} exceeds the {CLAMP_DAYS}-day clamp")
    if end < start:
        raise ValueError("end before start")
    stop = end + timedelta(days=1)
    a = start
    while a < stop:
        b = min(a + timedelta(days=window_days), stop)
        yield a, b
        a = b


class DiavgeiaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._http = httpx.Client(
            base_url=settings.diavgeia_base,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "application/json",
            },
            timeout=settings.request_timeout,
            follow_redirects=True,
        )
        self.calls = 0

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "DiavgeiaClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get_json(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        resp = self._http.get(path, params=params)
        self.calls += 1
        # Be polite: a fixed pause after every call, success or not.
        time.sleep(self.settings.request_delay)
        resp.raise_for_status()
        return resp.json()

    # -- endpoints ---------------------------------------------------------

    def organizations(self) -> list[dict[str, Any]]:
        doc = self._get_json("/organizations.json")
        return list(doc.get("organizations", []))

    def search_page(self, req: SearchRequest) -> tuple[SearchPage, dict[str, str | None]]:
        """One page of ``search.json``; raises EchoMismatch on any drift."""
        if req.size > MAX_PAGE_SIZE:
            raise ValueError(f"size={req.size} exceeds server maximum {MAX_PAGE_SIZE}")
        raw = self._get_json("/search.json", req.params())
        page = SearchPage(req, raw)
        echo = _verify_echo(req, page.info)
        return page, echo

    def search_all(self, req: SearchRequest) -> Iterator[tuple[SearchPage, dict[str, str | None]]]:
        """Every page for one window. Stops when the page count is exhausted."""
        page_no = req.page
        seen = 0
        while True:
            this = SearchRequest(
                req.org, req.from_date, req.to_date, page_no, req.size, req.status_all
            )
            page, echo = self.search_page(this)
            yield page, echo
            seen += page.actual_size
            if page.actual_size < req.size or seen >= page.total or page.actual_size == 0:
                return
            page_no += 1

    def versionlog(self, ada: str) -> dict[str, Any]:
        return self._get_json(f"/decisions/{ada}/versionlog.json")
