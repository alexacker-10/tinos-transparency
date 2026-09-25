"""Diavgeia full-text search ("luminapi") with a count guard and a privacy whitelist.

Diavgeia's open-data search (``tinos.sources.diavgeia``) filters by the
issuing organisation, so it cannot find decisions *about* Tinos issued by
someone else, such as the Interior Ministry's allocations to every
municipality. The full-text search behind diavgeia.gov.gr can. Contract
(FINDINGS.md, verified by probe 2026-09-25):

- ``GET {base}?q="<term>"&fq=organizationUid:"<uid>"
  &fq=issueDate:[DT(<from>T00:00:00) TO DT(<to>T23:59:59)]&page=N&size=100``,
  keyless, JSON ``{decisions, facets, highlighting, info}``.
- NO ECHO: ``info.query`` is always null. ``info`` does echo ``page``, the
  executed page ``size`` and ``total``; nothing else says what ran, so every
  window is proved by counts (below).
- ``q`` must be a quoted term (unquoted or absent: HTTP 400). Matching is
  stemmed and ignores accents and case: "ΤΗΝΟΥ" also finds Τήνος and Τήνο.
- ``fq`` fields are validated (a misspelt field is HTTP 400), but unknown
  top-level parameters are silently ignored (HTTP 200, same result; ``foo``,
  ``order``). ``sort=recent|relative`` is honoured; any other sort value is
  HTTP 500 SEARCH-006, the message a genuinely unavailable index also gives
  ("search by ADA only, try later"). We never sort; paging is checked instead.
- ``fq=organizationUid`` matches the issuer OR a co-issuer
  (``cooperatingOrganizations``: joint ministerial decisions).
- ``DT(...)`` bounds are Athens wall-clock time, both inclusive. A record's
  ``issueDate`` comes back as Athens wall clock, ``dd/mm/yyyy HH:MM:SS`` (a
  UTC-midnight act shows 02:00 or 03:00), so whole-day windows
  ``[a T00:00:00, b T23:59:59]`` tile the calendar with no gap or overlap.
- ``size`` above 100 is silently capped at 100; ``info.size`` says so.
- Long windows were NOT truncated: a year equals the sum of its halves and
  of its months, eleven years the sum of the years. The backfill checks it
  again for every year it walks.
- Results include revoked acts (``status``).
- The index is a finding aid, not a register: the control term matches 97%
  of the Interior Ministry's 2024 acts but 76-84% of its 2016-2017 acts, so
  documents without extractable text are probably not indexed.

Guard, raised as :class:`GuardViolation`:
- :func:`check_page`: the page echoes the page number and page size asked
  for; ``actualSize`` equals the records returned; every record names the
  organisation as issuer or co-issuer and was issued inside the window; every
  highlight belongs to a returned record; ``info.query`` is still null (if the
  service starts echoing, the contract has changed: re-verify it first).
- :meth:`FulltextClient.search_all`: ``total`` holds across pages and the
  distinct ADAs add up to it.
- :func:`check_control`: the term changed the count. The same window
  searched for :data:`CONTROL_TERM` (on the letterhead of nearly every act)
  must return a different count, unless neither matched anything: an
  ignored ``q`` returns the same unfiltered set for both. (Not "more": before
  about November 2015 only subjects are indexed, and a subject-level term can
  match more acts than the letterhead word.)
- :func:`check_year`: a year's count equals the sum of its windows' counts.

Privacy (PRIVACY.md Q7). A search for ΤΗΝΟΥ also finds acts about private
people: citizenship grants, appointments and transfers, detainee transport,
day-care vouchers naming their owners. Pages are stored *redacted*
(:func:`redact_page`): a record outside the whitelist (:func:`whitelist_reason`)
keeps only the fields the guard checks (ADA, issuer and co-issuers, issue
date, status); its subject, text snippet and everything else are dropped
before anything is written. The SHA-256 of the body as received is in the
ingest log; the body itself is not kept.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterator

import httpx

from tinos.config import Settings
from tinos.store import safe_ada

MAX_PAGE_SIZE = 100
CONTROL_TERM = "ΔΗΜΟΚΡΑΤΙΑ"
# One word in capitals (Greek or Latin) or digits: it becomes a path component.
_TERM_RE = re.compile(r"[0-9Α-ΩA-Z]{2,40}")
_ORG_RE = re.compile(r"\d{1,12}")
_ISSUE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2}):(\d{2})")
_RETRY_STATUSES = {429, 502, 503, 504}
# HTTP 500 with this code says the index is unavailable ("search by ADA only for now"). The
# same answer comes back for an invalid sort value, which we never send, so it is retried.
_INDEX_UNAVAILABLE = "SEARCH-006"


class GuardViolation(Exception):
    """A response we cannot tie to the query we sent."""


# ---------------------------------------------------------------------------
# requests and pages
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SearchRequest:
    term: str
    org: str
    date_from: date  # inclusive, Athens civil date
    date_to: date  # inclusive, Athens civil date
    page: int = 0
    size: int = MAX_PAGE_SIZE

    def __post_init__(self) -> None:
        if not _TERM_RE.fullmatch(self.term or ""):
            raise ValueError(f"term {self.term!r}: one word in capitals or digits, 2-40 characters")
        if not _ORG_RE.fullmatch(self.org or ""):
            raise ValueError(f"organisation uid {self.org!r} is not numeric")
        if self.date_to < self.date_from:
            raise ValueError("date_to before date_from")
        if not 1 <= self.size <= MAX_PAGE_SIZE:
            raise ValueError(f"size={self.size}: the server caps pages at {MAX_PAGE_SIZE}")

    def params(self) -> list[tuple[str, str]]:
        return [
            ("q", f'"{self.term}"'),
            ("fq", f'organizationUid:"{self.org}"'),
            ("fq", f"issueDate:[DT({self.date_from.isoformat()}T00:00:00) TO DT({self.date_to.isoformat()}T23:59:59)]"),
            ("page", str(self.page)),
            ("size", str(self.size)),
        ]

    def at_page(self, page: int) -> "SearchRequest":
        return SearchRequest(self.term, self.org, self.date_from, self.date_to, page, self.size)

    def counting(self, term: str | None = None) -> "SearchRequest":
        """The same window as a one-record count, optionally for another term."""
        return SearchRequest(term or self.term, self.org, self.date_from, self.date_to, 0, 1)


@dataclass(frozen=True)
class SearchPage:
    request: SearchRequest
    raw: dict[str, Any]
    received_sha256: str  # of the response body as received, before redaction

    @property
    def total(self) -> int:
        return int(self.raw["info"]["total"])

    @property
    def decisions(self) -> list[dict[str, Any]]:
        return list(self.raw.get("decisions") or [])


def issue_day(value: Any) -> date:
    """``'04/11/2024 02:00:00'`` (Athens wall clock) -> 2024-11-04."""
    m = _ISSUE_RE.fullmatch(str(value or "").strip())
    if not m:
        raise ValueError(f"unreadable issueDate {value!r}")
    d, mo, y = (int(g) for g in m.groups()[:3])
    return date(y, mo, d)


def issuers_of(rec: dict[str, Any]) -> set[str]:
    """The issuing organisation and every co-issuer, as uid strings."""
    out = set()
    org = rec.get("organization")
    if isinstance(org, dict) and org.get("uid") is not None:
        out.add(str(org["uid"]))
    for co in rec.get("cooperatingOrganizations") or []:
        if isinstance(co, dict) and co.get("uid") is not None:
            out.add(str(co["uid"]))
    return out


def check_page(req: SearchRequest, raw: Any) -> None:
    """Raise GuardViolation unless ``raw`` is page ``req.page`` of exactly ``req``."""
    info = raw.get("info") if isinstance(raw, dict) else None
    decisions = raw.get("decisions") if isinstance(raw, dict) else None
    if not isinstance(info, dict) or not isinstance(decisions, list) or not isinstance(info.get("total"), int):
        keys = sorted(raw)[:8] if isinstance(raw, dict) else type(raw).__name__
        raise GuardViolation(f"{req.term} {req.org} p{req.page}: not a search page: {keys}")
    problems: list[str] = []
    if info.get("query") is not None:
        problems.append(f"info.query is no longer null ({str(info['query'])[:80]!r}): "
                        "the service echoes now; re-verify the contract before trusting either")
    if info.get("page") != req.page:
        problems.append(f"page requested={req.page} returned={info.get('page')}")
    if info.get("size") != req.size:
        problems.append(f"page size requested={req.size} executed={info.get('size')}")
    if info.get("actualSize") != len(decisions) or len(decisions) > req.size:
        problems.append(f"actualSize={info.get('actualSize')} for {len(decisions)} records (size {req.size})")
    adas: list[str] = []
    for rec in decisions:
        ada = rec.get("ada") if isinstance(rec, dict) else None
        try:
            safe_ada(ada)
        except ValueError:
            problems.append(f"record with unusable ADA {ada!r}")
            continue
        adas.append(ada)
        if req.org not in issuers_of(rec):
            problems.append(f"{ada}: issued by {sorted(issuers_of(rec))}, not {req.org}")
        try:
            day = issue_day(rec.get("issueDate"))
        except ValueError as exc:
            problems.append(f"{ada}: {exc}")
            continue
        if not req.date_from <= day <= req.date_to:
            problems.append(f"{ada}: issued {day}, outside {req.date_from}..{req.date_to}")
    if len(set(adas)) != len(adas):
        problems.append("the same ADA twice on one page")
    stray = set(raw.get("highlighting") or {}) - set(adas)
    if stray:
        problems.append(f"highlights for {len(stray)} ADA(s) not on the page")
    if problems:
        shown = "; ".join(problems[:5]) + (f" (+{len(problems) - 5} more)" if len(problems) > 5 else "")
        raise GuardViolation(f"{req.term} {req.org} {req.date_from}..{req.date_to} p{req.page}: {shown}")


def check_control(req: SearchRequest, total: int, control_total: int) -> None:
    """The term must have changed the count against the control term, unless neither matched anything."""
    if total == 0 and control_total == 0:
        return
    if control_total == total:
        raise GuardViolation(f"{req.term} {req.org} {req.date_from}..{req.date_to}: {total} hits, control "
                             f"{CONTROL_TERM!r} {control_total}: the term did not change the result (q ignored?)")


def check_year(org: str, term: str, year_from: date, year_to: date, year_total: int, window_totals: list[int]) -> None:
    """A year searched whole must hold exactly what its windows held (no truncation, no gap)."""
    if year_total != sum(window_totals):
        raise GuardViolation(f"{term} {org} {year_from}..{year_to}: the whole span returns {year_total}, "
                             f"its windows {window_totals} = {sum(window_totals)}")


def year_windows(start: date, end: date) -> Iterator[tuple[tuple[date, date], list[tuple[date, date]]]]:
    """Per calendar year inside [start, end]: (the year's span, its half-year windows), all inclusive."""
    if end < start:
        raise ValueError("end before start")
    for y in range(start.year, end.year + 1):
        span = (max(start, date(y, 1, 1)), min(end, date(y, 12, 31)))
        halves = [(max(span[0], a), min(span[1], b))
                  for a, b in ((date(y, 1, 1), date(y, 6, 30)), (date(y, 7, 1), date(y, 12, 31)))]
        yield span, [(a, b) for a, b in halves if a <= b]


# ---------------------------------------------------------------------------
# privacy whitelist
# ---------------------------------------------------------------------------
_LOOKALIKE = str.maketrans("ABEHIKMNOPTXYZ", "ΑΒΕΗΙΚΜΝΟΡΤΧΥΖ")


def fold(text: Any) -> str:
    """Uppercase, accents stripped, Latin look-alike capitals made Greek, spaces collapsed."""
    s = unicodedata.normalize("NFD", str(text or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").upper().translate(_LOOKALIKE)
    return " ".join(s.split())


def _word(pattern: str) -> str:
    return rf"(?<![^\W\d_])(?:{pattern})(?![^\W\d_])"


# Acts about a person, or naming people, not money given to a municipality. Checked first.
PERSONAL_RE = re.compile("|".join([
    r"ΙΘΑΓΕΝ", r"ΠΟΛΙΤΟΓΡΑΦ",                                     # citizenship
    r"ΚΑΤΑΝΟΜΗ ΠΡΟΣΩΠΙΚΟΥ", r"ΠΡΟΣΛΗΨ", r"ΔΙΟΡΙΣ", r"ΜΕΤΑΤΑΞ",   # staff: allocation, hiring,
    r"ΑΠΟΣΠΑΣ", r"ΑΠΟΛΥΣ", r"ΛΥΣΗ ΣΥΜΒΑΣΗΣ", r"ΠΕΙΘΑΡΧ",        # appointment, transfer, dismissal
    _word(r"ΘΕΣ(?:Η|ΗΣ|ΕΙΣ|ΕΩΝ)"),                              # posts to fill
    _word(r"ΥΠΟΛΟΓ(?:ΟΣ|ΟΥ|Ο|ΟΙ|ΩΝ|ΟΥΣ)"),                       # imprest-account holders (not ΥΠΟΛΟΓΙΣΜΟΣ)
    r"ΣΥΓΚΡΟΤΗΣ", r"ΣΥΝΕΡΓΕΙ", r"ΑΝΤΙΔΗΜΑΡΧ",                   # committees, election teams, office holders
    r"ΚΡΑΤΟΥΜΕΝ", r"ΑΛΛΟΔΑΠ", r"ΔΩΡΕΑ",                          # detainees, donors
    r"ΕΝΑΡΜΟΝΙΣ",                                               # day-care vouchers: private structures and owners
]))
# Money given to municipalities: allocations, grants, financing, programme inclusion.
GRANT_RE = re.compile("|".join([
    r"ΚΑΤΑΝΟΜ", r"ΑΠΟΔΟΣ[ΗΕ]", r"ΕΠΙΧΟΡΗΓ", r"ΧΡΗΜΑΤΟΔΟΤ", r"ΑΥΤΟΤΕΛ", _word(r"ΚΑΠ|ΣΑΤΑ"),
    r"ΦΙΛΟΔΗΜ", r"ΤΡΙΤΣΗ", r"ΕΝΤΑΞ", r"ΠΙΣΤΩΣ", r"ΒΟΗΘΕΙΑ ΣΤΟ ΣΠΙΤΙ",
]))
# Β.1.1 from a ministry is public-investment financing and budget acts.
GRANT_TYPES = frozenset({"Β.1.1"})


def whitelist_reason(rec: dict[str, Any]) -> str | None:
    """None when the record is kept; otherwise ``'personal'`` or ``'not_a_grant'``.

    Kept: a subject about allocations, grants, financing or programme
    inclusion (:data:`GRANT_RE`) or a Β.1.1 act, unless the subject is about
    people (:data:`PERSONAL_RE`, checked first). Everything else found by a
    search for ΤΗΝΟΥ at a ministry (its own police and fire stations' purchases,
    traffic orders, circulars) is ``not_a_grant``. See PRIVACY.md Q7.
    """
    subject = fold(rec.get("subject"))
    if PERSONAL_RE.search(subject):
        return "personal"
    dtype = (rec.get("decisionType") or {}).get("uid")
    if GRANT_RE.search(subject) or dtype in GRANT_TYPES:
        return None
    return "not_a_grant"


def redact_page(raw: dict[str, Any], keep: set[str]) -> dict[str, Any]:
    """The page as stored: whitelisted records whole, the rest cut to what the guard checks."""
    decisions = []
    for rec in raw.get("decisions") or []:
        if rec.get("ada") in keep:
            decisions.append(rec)
            continue
        org = rec.get("organization") if isinstance(rec.get("organization"), dict) else {}
        decisions.append({
            "ada": rec.get("ada"),
            "issueDate": rec.get("issueDate"),
            "status": rec.get("status"),
            "organization": {"uid": org.get("uid")},
            "cooperatingOrganizations": [{"uid": c.get("uid")} for c in rec.get("cooperatingOrganizations") or []
                                         if isinstance(c, dict)],
            "redacted": True,
        })
    return {
        "info": raw.get("info"),
        "decisions": decisions,
        "highlighting": {a: h for a, h in (raw.get("highlighting") or {}).items() if a in keep},
    }


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------
class FulltextClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._http = httpx.Client(
            headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
            timeout=settings.request_timeout,
        )
        self.calls = 0
        self.retried = 0

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "FulltextClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_raw(self, params: list[tuple[str, str]]) -> httpx.Response:
        """One paced call; 429 and 5xx gateway errors are retried with back-off.

        Unguarded: for diagnostics (``tinos fulltext-doctor``). Ingestion goes
        through :meth:`search_page`.
        """
        resp = None
        for attempt in range(self.settings.fulltext_max_retries + 1):
            resp = self._http.get(self.settings.fulltext_base, params=params)
            self.calls += 1
            time.sleep(self.settings.fulltext_delay)
            unavailable = resp.status_code == 500 and _INDEX_UNAVAILABLE in resp.text
            if resp.status_code not in _RETRY_STATUSES and not unavailable:
                return resp
            self.retried += 1
            time.sleep(self.settings.fulltext_backoff * 2 ** attempt)
        return resp

    def search_page(self, req: SearchRequest) -> SearchPage:
        resp = self.get_raw(req.params())
        resp.raise_for_status()
        raw = resp.json()
        check_page(req, raw)
        return SearchPage(req, raw, hashlib.sha256(resp.content).hexdigest())

    def search_all(self, req: SearchRequest) -> Iterator[SearchPage]:
        """Every page of one window: the total must hold and the distinct ADAs add up to it."""
        first = self.search_page(req.at_page(0))
        yield first
        adas = [d["ada"] for d in first.decisions]
        for n in range(1, math.ceil(first.total / req.size)):
            page = self.search_page(req.at_page(n))
            if page.total != first.total:
                raise GuardViolation(f"{req.term} {req.org} {req.date_from}..{req.date_to}: "
                                     f"total changed while paging ({first.total} -> {page.total})")
            adas += [d["ada"] for d in page.decisions]
            yield page
        if len(adas) != first.total or len(set(adas)) != first.total:
            raise GuardViolation(f"{req.term} {req.org} {req.date_from}..{req.date_to}: {len(set(adas))} distinct "
                                 f"of {len(adas)} records for total={first.total}")

    def count(self, req: SearchRequest, term: str | None = None) -> SearchPage:
        """The window's total for ``term`` (default: the request's), one guarded record."""
        return self.search_page(req.counting(term))
