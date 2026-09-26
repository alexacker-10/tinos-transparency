"""``tinos`` command line: entities, doctor, backfill, fetch-doc, khmdhs-doctor,
khmdhs-backfill, fulltext-doctor, fulltext-backfill, fulltext-purge, fulltext-status, status."""

from __future__ import annotations

import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import typer

from tinos.config import Settings, load_registry, load_settings
from tinos.sources.diavgeia import (
    CLAMP_DAYS,
    DiavgeiaClient,
    EchoMismatch,
    SearchRequest,
    iter_windows,
)
from tinos.store import IngestLog, RawStore, utc_now_iso

app = typer.Typer(
    help="Tinos Transparency ingester.", no_args_is_help=True, add_completion=False
)


def _settings() -> Settings:
    return load_settings()


# --------------------------------------------------------------------------
@app.command()
def entities(
    verify: bool = typer.Option(
        False, "--verify", help="Cross-check entities.yaml against organizations.json."
    ),
) -> None:
    """List the entity registry; optionally verify it against Diavgeia."""
    st = _settings()
    reg = load_registry(st.entities_file)
    typer.echo(f"entities.yaml v{reg.version}  ({st.entities_file})")
    typer.echo(f"{'uid':<10} {'afm':<10} {'cat':<10} {'years':<10} {'acts':>6}  name")
    for e in reg.in_scope:
        years = f"{e.active_years[0]}-{e.active_years[1]}" if e.active_years else "-"
        typer.echo(
            f"{e.uid:<10} {e.afm or '-':<10} {e.category or '-':<10} {years:<10} "
            f"{e.approx_acts if e.approx_acts is not None else '-':>6}  {e.name}"
        )
    typer.echo(f"in_scope={len(reg.in_scope)}  out_of_scope={len(reg.out_of_scope)}")

    if not verify:
        return
    with DiavgeiaClient(st) as client:
        orgs = {str(o["uid"]): o for o in client.organizations()}
    bad = 0
    for e in reg.entities:
        o = orgs.get(e.uid)
        if o is None:
            typer.echo(f"  MISSING  {e.uid}  {e.name}")
            bad += 1
            continue
        issues = []
        if e.afm and str(o.get("vatNumber")) != e.afm:
            issues.append(f"afm {o.get('vatNumber')}")
        if e.in_scope and e.parent and str(o.get("supervisorId")) != e.parent:
            issues.append(f"parent {o.get('supervisorId')}")
        if e.category and o.get("category") != e.category:
            issues.append(f"category {o.get('category')}")
        if issues:
            bad += 1
            typer.echo(f"  DRIFT    {e.uid}  {e.name}: {', '.join(issues)}")
        else:
            typer.echo(f"  ok       {e.uid}  {o.get('label')}")
    for g in reg.grantors:
        o = orgs.get(g.uid)
        if o is None or o.get("label") != g.name or (g.latin_name and o.get("latinName") != g.latin_name):
            bad += 1
            typer.echo(f"  DRIFT    {g.uid}  grantor {g.name}: diavgeia has "
                       f"{(o or {}).get('label')!r} / {(o or {}).get('latinName')!r}")
        else:
            typer.echo(f"  ok       {g.uid}  grantor {o.get('label')} ({o.get('latinName')})")
    typer.echo("verify: OK" if bad == 0 else f"verify: {bad} problem(s)")
    if bad:
        raise typer.Exit(code=1)


# --------------------------------------------------------------------------
@app.command()
def doctor() -> None:
    """Prove the echo guard works against the live API.

    Sends (1) an in-limit window that must echo back exactly, and (2) a
    deliberately over-wide window that the server is known to clamp. The
    PASS condition for (2) is that _verify_echo raises EchoMismatch.
    """
    st = _settings()
    reg = load_registry(st.entities_file)
    org = "6296"
    ok = True
    typer.echo(f"root={st.root}")
    typer.echo(f"user-agent={st.user_agent}")
    typer.echo(f"delay={st.request_delay}s  window={st.window_days}d  page={st.page_size}")
    typer.echo(f"entities.yaml: {len(reg.in_scope)} in scope")
    typer.echo(f"raw dir: {st.raw_dir}  (exists={st.raw_dir.is_dir()})")

    with DiavgeiaClient(st) as client:
        # (1) in-limit window must echo exactly
        narrow = SearchRequest(org, date(2024, 1, 1), date(2024, 1, 1) + timedelta(days=st.window_days), size=1)
        try:
            page, echo = client.search_page(narrow)
            typer.echo(
                f"[1] narrow {narrow.from_date}..{narrow.to_date} ({narrow.span_days}d): "
                f"echo-check OK  total={page.total}  executed={echo['issue_from']}..{echo['issue_to']}"
            )
        except EchoMismatch as exc:
            ok = False
            typer.echo(f"[1] narrow window: FAIL  {exc}")

        # (2) over-wide window: the server WILL clamp; the guard MUST notice
        wide = SearchRequest(org, date(2024, 1, 1), date(2025, 1, 1), size=1)
        try:
            client.search_page(wide)
        except EchoMismatch as exc:
            typer.echo(
                f"[2] wide {wide.from_date}..{wide.to_date} ({wide.span_days}d): "
                f"echo-check OK (clamp correctly detected)"
            )
            typer.echo(f"    detail: {str(exc).split(' | ')[0]}")
        else:
            ok = False
            typer.echo(
                f"[2] wide window: FAIL  server returned {wide.span_days}d unclamped "
                f"or _verify_echo is broken"
            )

        # (3) wrong-org sanity: a non-numeric org id must not silently match 6296
        typer.echo(f"calls made: {client.calls}")

    typer.echo("doctor: PASS" if ok else "doctor: FAIL")
    if not ok:
        raise typer.Exit(code=1)


# --------------------------------------------------------------------------
def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except ValueError as exc:
        raise typer.BadParameter(f"{s!r} is not YYYY-MM-DD") from exc


@app.command()
def backfill(
    entity: str = typer.Option(..., "--entity", help="Diavgeia organisation uid."),
    start: str = typer.Option(..., "--start", help="First issueDate, YYYY-MM-DD (inclusive)."),
    end: str = typer.Option(..., "--end", help="Last issueDate, YYYY-MM-DD (inclusive)."),
    status_all: bool = typer.Option(
        True, "--status-all/--no-status-all",
        help="Ask for status=all so revoked/withdrawn acts are included (default on).",
    ),
) -> None:
    """Fetch every act for one entity over a date range into data/raw.

    Revoked acts are fetched by default: an authorised-then-withdrawn payment
    is exactly what a transparency dataset should surface. Each act's own
    ``status`` field is stored verbatim and tallied in the ingest log.
    """
    st = _settings()
    reg = load_registry(st.entities_file)
    ent = reg.get(entity)
    if ent is None:
        typer.echo(f"warning: {entity} is not in entities.yaml", err=True)
    elif not ent.in_scope:
        typer.echo(f"refusing: {entity} ({ent.name}) is out of scope: {ent.reason}", err=True)
        raise typer.Exit(code=2)
    d0, d1 = _parse_date(start), _parse_date(end)
    if d1 < d0:
        raise typer.BadParameter("--end is before --start")

    store = RawStore(st.raw_dir)
    log = IngestLog(st.ingest_log)
    run_id = utc_now_iso()
    tally: Counter[str] = Counter()
    seen_adas: set[str] = set()
    status_tally: Counter[str] = Counter()
    typer.echo(
        f"backfill {entity} {ent.name if ent else ''}  {d0}..{d1}  "
        f"status={'all' if status_all else 'published-only'}  run={run_id}"
    )

    with DiavgeiaClient(st) as client:
        for w_from, w_to in iter_windows(d0, d1, st.window_days):
            req = SearchRequest(entity, w_from, w_to, size=st.page_size, status_all=status_all)
            window_tally: Counter[str] = Counter()
            window_status: Counter[str] = Counter()
            pages: list[dict] = []
            total = None
            executed = None
            try:
                for page, echo in client.search_all(req):
                    executed = echo
                    total = page.total
                    # Snapshot is content-addressed on the body WITHOUT info.query
                    # (the echo carries a wall clock). A repeat sighting stores
                    # nothing and is logged against the existing hash.
                    snap = store.put_diavgeia_page(
                        entity, w_from.isoformat(), w_to.isoformat(), page.request.page, page.raw
                    )
                    pages.append({
                        "page": page.request.page, "sha256": snap.sha256,
                        "stored": snap.outcome == "new", "query": page.info.get("query"),
                    })
                    for act in page.decisions:
                        ada = act.get("ada")
                        if not ada:
                            window_tally["no_ada"] += 1
                            continue
                        if ada in seen_adas:
                            window_tally["dup"] += 1
                            continue
                        seen_adas.add(ada)
                        window_status[str(act.get("status"))] += 1
                        res = store.put_diavgeia_act(entity, act)
                        window_tally[res.outcome] += 1
            except EchoMismatch as exc:
                log.append({
                    "source": "diavgeia", "run": run_id, "org": entity,
                    "from": w_from.isoformat(), "to_excl": w_to.isoformat(),
                    "status": "ECHO_MISMATCH", "error": str(exc),
                })
                typer.echo(f"  {w_from}..{w_to}: ECHO MISMATCH, window discarded: {exc}", err=True)
                raise typer.Exit(code=3)
            tally.update(window_tally)
            status_tally.update(window_status)
            stored = sum(1 for p in pages if p["stored"])
            log.append({
                "source": "diavgeia", "run": run_id, "org": entity,
                "from": w_from.isoformat(), "to_excl": w_to.isoformat(),
                "status_all": status_all, "executed": executed,
                "total": total, "pages": pages, "pages_stored": stored,
                "new": window_tally["new"], "changed": window_tally["changed"],
                "unchanged": window_tally["unchanged"], "dup": window_tally["dup"],
                "act_status": dict(window_status),
            })
            typer.echo(
                f"  {w_from}..{w_to} (excl): total={total} pages={len(pages)} "
                f"(stored {stored}, seen {len(pages) - stored}) "
                f"new={window_tally['new']} changed={window_tally['changed']} "
                f"unchanged={window_tally['unchanged']}  status={dict(window_status)}"
            )
        typer.echo(f"calls made: {client.calls}")

    typer.echo(
        f"done: acts={len(seen_adas)} new={tally['new']} changed={tally['changed']} "
        f"unchanged={tally['unchanged']} dup={tally['dup']}  by status={dict(status_tally)}"
    )


# --------------------------------------------------------------------------
@app.command(name="fetch-doc")
def fetch_doc(
    adas: list[str] = typer.Argument(..., help="ADA(s) of acts already in data/raw."),
) -> None:
    """Store the signed PDF of acts we already hold, under data/raw/diavgeia/docs.

    Only acts present in the raw store are fetched (our own acts, or another
    body's decision kept by ``fulltext-backfill``): the stored act names the
    organisation and the document belongs to it. Append-only like the rest of
    data/raw; every call is logged with the hash of the bytes kept.
    """
    import httpx

    st = _settings()
    store = RawStore(st.raw_dir)
    log = IngestLog(st.ingest_log)
    run_id = utc_now_iso()
    failed = 0
    with DiavgeiaClient(st) as client:
        for ada in adas:
            # Our own acts, or another body's decision kept by fulltext-backfill.
            act_path = store.find_diavgeia_act(ada) or store.find_fulltext_decision(ada)
            if act_path is None:
                typer.echo(f"  {ada}: no such act in data/raw, skipped", err=True)
                failed += 1
                continue
            org = act_path.parent.name
            try:
                data, meta = client.document(ada)
            except (httpx.HTTPError, ValueError) as exc:
                log.append({"source": "diavgeia-doc", "run": run_id, "org": org, "ada": ada,
                            "status": "ERROR", "error": str(exc)})
                typer.echo(f"  {ada}: FAILED {exc}", err=True)
                failed += 1
                continue
            res = store.put_diavgeia_doc(org, ada, data)
            rel = res.path.relative_to(st.root)
            log.append({"source": "diavgeia-doc", "run": run_id, "org": org, "ada": ada, **meta,
                        "sha256": res.sha256, "outcome": res.outcome, "path": str(rel)})
            typer.echo(f"  {ada}: {res.outcome}  {meta['bytes']:,} bytes  sha256={res.sha256}  -> {rel}")
        typer.echo(f"calls made: {client.calls}")
    if failed:
        raise typer.Exit(code=1)


# --------------------------------------------------------------------------
@app.command(name="khmdhs-doctor")
def khmdhs_doctor() -> None:
    """Prove the ΚΗΜΔΗΣ guard's premises against the live API (about 8 calls).

    (1) a one-month window passes the guard; (2) a 366-day window comes back
    truncated, with fewer records than its three sub-windows, which is why the
    client refuses windows over 180 days; (3) a misspelled body field is
    rejected with HTTP 400, not silently ignored.
    """
    from tinos.sources.khmdhs import GuardViolation, KhmdhsClient, SearchRequest
    from tinos.sources.khmdhs import iter_windows as khmdhs_windows

    st = _settings()
    ok = True
    typer.echo(f"base={st.khmdhs_base}")
    typer.echo(f"user-agent={st.user_agent}  delay={st.khmdhs_delay}s  window={st.khmdhs_window_days}d")
    with KhmdhsClient(st) as client:
        try:
            pages = list(client.search_all(SearchRequest("contract", "6296", date(2024, 3, 1), date(2024, 3, 31))))
            typer.echo(f"[1] contract 6296 2024-03: guard OK, total={pages[0].total}, pages={len(pages)}")
        except GuardViolation as exc:
            ok = False
            typer.echo(f"[1] FAIL {exc}")

        wide = client.post_raw("request", {"organizations": ["6296"], "dateFrom": "2024-01-01", "dateTo": "2024-12-31"})
        wide_total = wide.json().get("totalElements") if wide.status_code == 200 else None
        parts = [client.search_page(SearchRequest("request", "6296", a, b)).total
                 for a, b in khmdhs_windows(date(2024, 1, 1), date(2024, 12, 31), st.khmdhs_window_days)]
        if wide_total is not None and wide_total < sum(parts):
            typer.echo(f"[2] request 6296 2024 in one window: {wide_total}, in {len(parts)} windows: {sum(parts)} "
                       "-> server truncation confirmed; windows stay under 180 days")
        else:
            ok = False
            typer.echo(f"[2] FAIL one window={wide_total} vs windows={parts}: the clamp premise no longer holds")

        typo = client.post_raw("contract", {"organizationz": ["6296"], "dateFrom": "2024-03-01", "dateTo": "2024-03-31"})
        if typo.status_code == 400:
            typer.echo("[3] misspelled field: HTTP 400 (rejected, not ignored)")
        else:
            ok = False
            typer.echo(f"[3] FAIL misspelled field returned HTTP {typo.status_code}: unknown fields may be ignored")
        typer.echo(f"calls made: {client.calls}  throttled: {client.throttled}")
    typer.echo("khmdhs-doctor: PASS" if ok else "khmdhs-doctor: FAIL")
    if not ok:
        raise typer.Exit(code=1)


@app.command(name="khmdhs-backfill")
def khmdhs_backfill(
    start: str = typer.Option(..., "--start", help="First submissionDate, YYYY-MM-DD (inclusive)."),
    end: str = typer.Option(..., "--end", help="Last submissionDate, YYYY-MM-DD (inclusive)."),
    entity: Optional[list[str]] = typer.Option(None, "--entity", help="Organisation uid; repeatable. Default: all in scope."),
    endpoint: Optional[list[str]] = typer.Option(None, "--endpoint", help="request|notice|auction|contract|payment; repeatable. Default: all."),
) -> None:
    """Fetch ΚΗΜΔΗΣ records into data/raw/khmdhs, window by window.

    A window is stored only after every page of it passed the guard. Every
    window, including empty ones, gets an ingest-log line.
    """
    import httpx

    from tinos.sources.khmdhs import ENDPOINTS, GuardViolation, KhmdhsClient, SearchRequest
    from tinos.sources.khmdhs import iter_windows as khmdhs_windows

    st = _settings()
    reg = load_registry(st.entities_file)
    orgs = entity or [e.uid for e in reg.in_scope]
    for org in orgs:
        ent = reg.get(org)
        if ent is not None and not ent.in_scope:
            typer.echo(f"refusing: {org} ({ent.name}) is out of scope: {ent.reason}", err=True)
            raise typer.Exit(code=2)
    eps = endpoint or list(ENDPOINTS)
    bad = [e for e in eps if e not in ENDPOINTS]
    if bad:
        raise typer.BadParameter(f"unknown endpoint(s) {bad}; choose from {ENDPOINTS}")
    d0, d1 = _parse_date(start), _parse_date(end)
    if d1 < d0:
        raise typer.BadParameter("--end is before --start")

    store = RawStore(st.raw_dir)
    log = IngestLog(st.ingest_log)
    run_id = utc_now_iso()
    grand: Counter[str] = Counter()
    typer.echo(f"khmdhs-backfill {d0}..{d1}  entities={orgs}  endpoints={eps}  run={run_id}")
    with KhmdhsClient(st) as client:
        for org in orgs:
            for ep in eps:
                seen: set[str] = set()
                per: Counter[str] = Counter()
                for a, b in khmdhs_windows(d0, d1, st.khmdhs_window_days):
                    req = SearchRequest(ep, org, a, b)
                    for attempt in (1, 2):
                        try:
                            pages = list(client.search_all(req))
                            break
                        except (GuardViolation, httpx.HTTPError) as exc:
                            kind = "GUARD_VIOLATION" if isinstance(exc, GuardViolation) else "HTTP_ERROR"
                            log.append({"source": "khmdhs", "run": run_id, "endpoint": ep, "org": org,
                                        "from": a.isoformat(), "to": b.isoformat(), "status": kind,
                                        "attempt": attempt, "error": str(exc)})
                            typer.echo(f"  {ep} {org} {a}..{b}: {kind} (attempt {attempt}): {exc}", err=True)
                            if attempt == 2:
                                raise typer.Exit(code=3)
                            time.sleep(st.khmdhs_backoff)
                    tally: Counter[str] = Counter()
                    logged_pages = []
                    for page in pages:
                        if "notFound" not in page.raw:  # a 404 has no body worth keeping
                            snap = store.put_khmdhs_page(ep, org, a.isoformat(), b.isoformat(), page.request.page, page.raw)
                            logged_pages.append({"page": page.request.page, "sha256": snap.sha256,
                                                 "stored": snap.outcome == "new"})
                        for rec in page.records:
                            if rec["referenceNumber"] in seen:
                                tally["dup"] += 1
                                continue
                            seen.add(rec["referenceNumber"])
                            tally[store.put_khmdhs_record(ep, org, rec).outcome] += 1
                    total = pages[0].total
                    log.append({"source": "khmdhs", "run": run_id, "endpoint": ep, "org": org,
                                "from": a.isoformat(), "to": b.isoformat(), "body": req.body(), "total": total,
                                "pages": logged_pages, "new": tally["new"], "changed": tally["changed"],
                                "unchanged": tally["unchanged"], "dup": tally["dup"]})
                    per.update(tally)
                    per["total"] += total
                typer.echo(f"  {ep:9} {org:>10}: total={per['total']:>5} new={per['new']} changed={per['changed']} "
                           f"unchanged={per['unchanged']} dup={per['dup']}  (calls so far {client.calls}, "
                           f"throttled {client.throttled})")
                grand.update(per)
        typer.echo(f"calls made: {client.calls}  throttled: {client.throttled}")
    typer.echo(f"done: records={grand['total']} new={grand['new']} changed={grand['changed']} "
               f"unchanged={grand['unchanged']} dup={grand['dup']}")


# --------------------------------------------------------------------------
@app.command(name="fulltext-doctor")
def fulltext_doctor() -> None:
    """Prove the full-text guard's premises against the live API (about 12 calls).

    (1) a ten-day window passes the guard and the term narrows it against the
    control term; (2) a nonsense term finds nothing; (3) a year equals the sum
    of its halves (no truncation); (4) a misspelt fq field is HTTP 400; (5) an
    unknown top-level parameter is silently ignored (reported, the known
    hazard); (6) size above 100 is capped and says so in info.size; (7) the
    query is still not echoed.
    """
    from tinos.sources.fulltext import (CONTROL_TERM, MAX_PAGE_SIZE, FulltextClient, GuardViolation,
                                        SearchRequest, check_control)

    st = _settings()
    org, term = "100054492", "ΤΗΝΟΥ"
    ok = True
    typer.echo(f"base={st.fulltext_base}")
    typer.echo(f"user-agent={st.user_agent}  delay={st.fulltext_delay}s")
    with FulltextClient(st) as client:
        narrow = SearchRequest(term, org, date(2024, 11, 1), date(2024, 11, 10))
        baseline = None
        try:
            pages = list(client.search_all(narrow))
            baseline = pages[0].total
            control = client.count(narrow, CONTROL_TERM).total
            check_control(narrow, baseline, control)
            typer.echo(f"[1] {term} {org} 2024-11-01..10: guard OK, total={baseline}, control {CONTROL_TERM}={control}")
        except GuardViolation as exc:
            ok = False
            typer.echo(f"[1] FAIL {exc}")

        nonsense = client.count(narrow, "ΖΞΨΚΦΘ").total
        if nonsense == 0:
            typer.echo("[2] nonsense term: 0 hits (q is applied)")
        else:
            ok = False
            typer.echo(f"[2] FAIL nonsense term returned {nonsense}: q may be ignored")

        year = SearchRequest(term, org, date(2024, 1, 1), date(2024, 12, 31))
        whole = client.count(year).total
        halves = [client.count(SearchRequest(term, org, a, b)).total
                  for a, b in ((date(2024, 1, 1), date(2024, 6, 30)), (date(2024, 7, 1), date(2024, 12, 31)))]
        if whole == sum(halves) and whole > 0:
            typer.echo(f"[3] 2024 whole={whole}, halves={halves}: no truncation")
        else:
            ok = False
            typer.echo(f"[3] FAIL 2024 whole={whole}, halves={halves}: long windows are truncated or empty")

        params = narrow.params()
        typo = client.get_raw([("fq", 'organizationUidz:"100054492"') if p[1].startswith("organizationUid") else p
                               for p in params])
        if typo.status_code == 400:
            typer.echo("[4] misspelt fq field: HTTP 400 (rejected, not ignored)")
        else:
            ok = False
            typer.echo(f"[4] FAIL misspelt fq field returned HTTP {typo.status_code}: fq fields may be ignored")

        extra = client.get_raw(params + [("foo", "bar")])
        same = extra.status_code == 200 and extra.json().get("info", {}).get("total") == baseline
        typer.echo(f"[5] unknown top-level parameter: HTTP {extra.status_code}, "
                   + ("silently ignored (the known hazard: send only q, fq, page, size)" if same
                      else "not silently ignored now: re-verify the contract"))

        capped = client.get_raw([(k, "500") if k == "size" else (k, v) for k, v in params])
        size = capped.json().get("info", {}).get("size") if capped.status_code == 200 else None
        if size == MAX_PAGE_SIZE:
            typer.echo(f"[6] size=500 executed as size={size} (capped, echoed)")
        else:
            ok = False
            typer.echo(f"[6] FAIL size=500 came back as size={size}: the page-size premise changed")

        query = capped.json().get("info", {}).get("query") if capped.status_code == 200 else "?"
        typer.echo(f"[7] info.query = {query!r}" + (" (still no echo)" if query is None else " (ECHO NOW PRESENT: re-verify)"))
        ok = ok and query is None
        typer.echo(f"calls made: {client.calls}  retried: {client.retried}")
    typer.echo("fulltext-doctor: PASS" if ok else "fulltext-doctor: FAIL")
    if not ok:
        raise typer.Exit(code=1)


@app.command(name="fulltext-backfill")
def fulltext_backfill(
    start: str = typer.Option(..., "--start", help="First issue date, YYYY-MM-DD (inclusive)."),
    end: str = typer.Option(..., "--end", help="Last issue date, YYYY-MM-DD (inclusive)."),
    issuer: Optional[list[str]] = typer.Option(None, "--issuer", help="Grantor uid (entities.yaml grantors); repeatable. Default: all."),
    term: Optional[list[str]] = typer.Option(None, "--term", help="Search term, one word in capitals; repeatable. Default: ΤΗΝΟΥ."),
) -> None:
    """Find other bodies' decisions naming Tinos, via Diavgeia full-text search.

    Walks each calendar year in two half-year windows. A year is stored only
    after every page passed the guard, each window's hits were fewer than the
    control term's, and the whole year searched at once held exactly what its
    windows held. Pages are stored redacted and only whitelisted decisions are
    kept (PRIVACY.md Q7). One ingest-log line per call.
    """
    import httpx

    from tinos.sources.fulltext import (CONTROL_TERM, FulltextClient, GuardViolation, SearchRequest, check_control,
                                        check_year, redact_page, whitelist_reason, year_windows)

    st = _settings()
    reg = load_registry(st.entities_file)
    grantors = {g.uid: g for g in reg.grantors}
    issuers = issuer or list(grantors)
    unknown = [u for u in issuers if u not in grantors]
    if unknown:
        typer.echo(f"refusing: {unknown} not among the grantors in entities.yaml", err=True)
        raise typer.Exit(code=2)
    terms = term or ["ΤΗΝΟΥ"]
    # A Tinos body's own ΑΦΜ, or one of its projects' codes (entities.yaml ``anchor_codes``), as the term anchors every
    # hit to it: kept unless about a person.
    anchors = reg.anchors
    d0, d1 = _parse_date(start), _parse_date(end)
    if d1 < d0:
        raise typer.BadParameter("--end is before --start")

    store = RawStore(st.raw_dir)
    log = IngestLog(st.ingest_log)
    run_id = utc_now_iso()
    grand: Counter[str] = Counter()
    seen: set[str] = set()
    typer.echo(f"fulltext-backfill {d0}..{d1}  issuers={issuers}  terms={terms}  run={run_id}")
    with FulltextClient(st) as client:
        for org in issuers:
            for t in terms:
                for (y0, y1), windows in year_windows(d0, d1):
                    calls: list[dict] = []  # ingest-log lines for this year, written once it is settled
                    base = {"source": "diavgeia-fulltext", "run": run_id, "issuer": org, "term": t}
                    try:
                        fetched = []  # (window, pages, control total)
                        for a, b in windows:
                            req = SearchRequest(t, org, a, b)
                            pages = []
                            for page in client.search_all(req):
                                pages.append(page)
                                calls.append({**base, "kind": "page", "from": a.isoformat(), "to": b.isoformat(),
                                              "page": page.request.page, "size": page.request.size, "total": page.total,
                                              "returned": len(page.decisions), "received_sha256": page.received_sha256})
                            control = client.count(req, CONTROL_TERM)
                            calls.append({**base, "kind": "control", "control_term": CONTROL_TERM, "from": a.isoformat(),
                                          "to": b.isoformat(), "total": control.total,
                                          "received_sha256": control.received_sha256})
                            check_control(req, pages[0].total, control.total)
                            fetched.append(((a, b), pages))
                        whole = client.count(SearchRequest(t, org, y0, y1))
                        calls.append({**base, "kind": "year", "from": y0.isoformat(), "to": y1.isoformat(),
                                      "total": whole.total, "received_sha256": whole.received_sha256})
                        check_year(org, t, y0, y1, whole.total, [p[0].total for _, p in fetched])
                    except (GuardViolation, httpx.HTTPError) as exc:
                        kind = "GUARD_VIOLATION" if isinstance(exc, GuardViolation) else "HTTP_ERROR"
                        for line in calls:
                            log.append({**line, "stored": None})
                        log.append({**base, "kind": "error", "from": y0.isoformat(), "to": y1.isoformat(),
                                    "status": kind, "error": str(exc)})
                        typer.echo(f"  {org} {t} {y0}..{y1}: {kind}, year discarded: {exc}", err=True)
                        raise typer.Exit(code=3)

                    # Settled: store the year's pages (redacted) and its whitelisted decisions.
                    tally: Counter[str] = Counter()
                    page_lines = iter([c for c in calls if c["kind"] == "page"])
                    for (a, b), pages in fetched:
                        for page in pages:
                            keep, dropped = set(), Counter()
                            for rec in page.decisions:
                                reason = whitelist_reason(rec, anchored=t in anchors, keep=grantors[org].keep)
                                if reason is None:
                                    keep.add(rec["ada"])
                                else:
                                    dropped[reason] += 1
                            snap = store.put_fulltext_page(org, t, a.isoformat(), b.isoformat(), page.request.page,
                                                           redact_page(page.raw, keep))
                            decisions: Counter[str] = Counter()
                            for rec in page.decisions:
                                if rec["ada"] not in keep:
                                    continue
                                if rec["ada"] in seen:
                                    decisions["dup"] += 1
                                    continue
                                seen.add(rec["ada"])
                                decisions[store.put_fulltext_decision(rec).outcome] += 1
                            line = next(page_lines)
                            line.update({"stored": {"path": str(snap.path.relative_to(st.root)), "sha256": snap.sha256,
                                                    "outcome": snap.outcome},
                                         "kept": len(keep), "dropped": dict(dropped), "decisions": dict(decisions)})
                            tally["hits"] += len(page.decisions)
                            tally["kept"] += len(keep)
                            tally.update({f"dropped_{k}": v for k, v in dropped.items()})
                            tally.update({f"decision_{k}": v for k, v in decisions.items()})
                    for line in calls:
                        log.append(line if line["kind"] == "page" else {**line, "stored": None})
                    grand.update(tally)
                    typer.echo(f"  {org:>9} {t} {y0.year}: hits={tally['hits']:>4} kept={tally['kept']:>4} "
                               f"personal={tally['dropped_personal']:>3} other={tally['dropped_not_a_grant']:>4} "
                               f"new={tally['decision_new']} changed={tally['decision_changed']} "
                               f"unchanged={tally['decision_unchanged']} dup={tally['decision_dup']}  "
                               f"(calls {client.calls})")
        typer.echo(f"calls made: {client.calls}  retried: {client.retried}")
    typer.echo(f"done: hits={grand['hits']} kept={grand['kept']} dropped personal={grand['dropped_personal']} "
               f"not a grant={grand['dropped_not_a_grant']}  decisions new={grand['decision_new']} "
               f"changed={grand['decision_changed']} unchanged={grand['decision_unchanged']}")


@app.command(name="fulltext-purge")
def fulltext_purge(
    apply: bool = typer.Option(False, "--apply", help="Delete and log. Without it, only list."),
) -> None:
    """Delete stored full-text records the whitelist now calls personal, with the pages holding them whole.

    data/raw is append-only; this is its one exception, decided by the project owner on 2026-09-26
    (PRIVACY.md Q7). A record kept whole under an earlier, looser whitelist and now judged to be
    about a person is deleted, and so is every stored search page that holds it unredacted. Re-run
    the years listed with ``fulltext-backfill`` first: a page is deleted only when a later capture
    of the same page, holding the record redacted, is stored. One ingest-log line per deletion
    (path, SHA-256, ADAs; never a subject).
    """
    import json
    import re

    from tinos.curated_grants import keep_rules_for, search_index_by_issuer
    from tinos.sources.fulltext import whitelist_reason

    st = _settings()
    reg = load_registry(st.entities_file)
    anchors = reg.anchors
    store = RawStore(st.raw_dir)
    found, _, found_orgs = search_index_by_issuer(st.raw_dir)
    base = st.raw_dir / "diavgeia" / "fulltext"
    personal: dict[str, list[Path]] = {}
    for path in sorted((base / "decisions").glob("*/*.json")):
        rec = json.loads(path.read_bytes())
        if whitelist_reason(rec, anchored=bool(anchors & set(found.get(rec["ada"], []))),
                            keep=keep_rules_for(rec["ada"], path.parent.name, found_orgs, reg)) == "personal":
            personal.setdefault(rec["ada"], []).append(path)
    page_re = re.compile(r"(\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}_p\d{3})_[0-9a-f]{12}\.json")
    pages: dict[Path, list[str]] = {}
    captures: Counter[tuple[str, str, str]] = Counter()
    for page in sorted((base / "search").glob("*/*/*.json")):
        m = page_re.fullmatch(page.name)
        slot = (page.parent.parent.name, page.parent.name, m.group(1) if m else page.name)
        captures[slot] += 1
        whole = [r.get("ada") for r in json.loads(page.read_bytes()).get("decisions") or []
                 if r.get("ada") in personal and not r.get("redacted")]
        if whole:
            pages[page] = whole
    doomed = Counter((p.parent.parent.name, p.parent.name, page_re.fullmatch(p.name).group(1)) for p in pages)
    orphans = sorted(slot for slot, n in doomed.items() if captures[slot] - n < 1)
    typer.echo(f"records about a person: {len(personal)} ({sum(len(v) for v in personal.values())} files); "
               f"pages holding them whole: {len(pages)}")
    if orphans:
        years = sorted({(i, t, w[:4]) for i, t, w in orphans})
        typer.echo("no later capture yet for these pages; re-run first:", err=True)
        for i, t, y in years:
            typer.echo(f"  tinos fulltext-backfill --issuer {i} --term {t} --start {y}-01-01 --end {y}-12-31", err=True)
        raise typer.Exit(code=2 if apply else 0)
    if not apply:
        typer.echo("dry run: nothing deleted (--apply to delete)")
        return
    log = IngestLog(st.ingest_log)
    run_id = utc_now_iso()
    for ada, paths in sorted(personal.items()):
        for path in paths:
            digest = store.purge_fulltext(path)
            log.append({"source": "privacy-deletion", "run": run_id, "kind": "decision", "ada": ada,
                        "path": str(path.relative_to(st.root)), "sha256": digest,
                        "reason": "PRIVACY.md Q7: about a person; owner's decision 2026-09-26"})
    for page, adas in sorted(pages.items()):
        digest = store.purge_fulltext(page)
        log.append({"source": "privacy-deletion", "run": run_id, "kind": "page", "adas": sorted(adas),
                    "path": str(page.relative_to(st.root)), "sha256": digest,
                    "reason": "PRIVACY.md Q7: holds records about a person unredacted; a later capture holds them redacted"})
    typer.echo(f"deleted {sum(len(v) for v in personal.values())} decision files and {len(pages)} pages; logged")


@app.command(name="fulltext-status")
def fulltext_status(
    missing_docs: bool = typer.Option(False, "--missing-docs", help="List kept decisions whose PDF is not stored yet."),
    names: bool = typer.Option(False, "--names", help="List kept decisions whose subject holds a common first name "
                                                      "(a privacy review of what the whitelist keeps)."),
) -> None:
    """Kept full-text decisions by issuer and year, and which PDFs are stored."""
    import json

    from tinos.curated_grants import keep_rules_for, search_index_by_issuer
    from tinos.sources.fulltext import first_name_words, issue_day, whitelist_reason

    st = _settings()
    store = RawStore(st.raw_dir)
    if names:
        # Every stored record the current whitelist would still keep, scanned for first names (PRIVACY.md Q7).
        # Saints and places carry the same words; each hit is for a person to read.
        reg = load_registry(st.entities_file)
        anchors = reg.anchors
        found, _, found_orgs = search_index_by_issuer(st.raw_dir)
        scanned = hits = 0
        for path in store.iter_fulltext_decisions():
            rec = json.loads(path.read_bytes())
            org = path.parent.name
            if whitelist_reason(rec, anchored=bool(anchors & set(found.get(rec["ada"], []))),
                                keep=keep_rules_for(rec["ada"], org, found_orgs, reg)) is not None:
                continue
            scanned += 1
            words = first_name_words(rec.get("subject"))
            if words:
                hits += 1
                typer.echo(f"{org}\t{rec['ada']}\t{issue_day(rec['issueDate'])}\t{','.join(words)}\t"
                           f"{' '.join(str(rec.get('subject')).split())[:160]}")
        typer.echo(f"kept subjects scanned: {scanned}  with a first-name word: {hits}")
        return
    rows = []
    for path in store.iter_fulltext_decisions():
        rec = json.loads(path.read_bytes())
        org = path.parent.name
        doc = store.diavgeia_doc_path(org, rec["ada"])
        rows.append((org, issue_day(rec["issueDate"]), rec, doc.is_file()))
    counts = Counter((org, day.year) for org, day, _, _ in rows)
    have = Counter((org, day.year) for org, day, _, stored in rows if stored)
    typer.echo(f"kept decisions: {len(rows)}  PDFs stored: {sum(1 for r in rows if r[3])}")
    for (org, year), n in sorted(counts.items()):
        typer.echo(f"  {org:>10} {year}: {n:>4} kept, {have[(org, year)]:>4} with PDF")
    if missing_docs:
        for org, day, rec, stored in sorted(rows, key=lambda r: (r[1], r[2]["ada"])):
            if not stored:
                typer.echo(f"{rec['ada']}\t{org}\t{day}\t{(rec.get('decisionType') or {}).get('uid')}\t"
                           f"{rec.get('status')}\t{' '.join(str(rec.get('subject')).split())[:110]}")


# --------------------------------------------------------------------------
@app.command()
def status() -> None:
    """Summarise what is in data/raw and the ingest log."""
    import json
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    st = _settings()
    reg = load_registry(st.entities_file)
    store = RawStore(st.raw_dir)
    files = store.iter_diavgeia_acts()
    typer.echo(f"raw acts on disk: {len(files)}  ({st.raw_dir / 'diavgeia' / 'acts'})")
    if files:
        # Plain per-file scan on purpose: DuckDB schema inference across tens of
        # thousands of nested JSON files needs many GB; this needs none.
        athens = ZoneInfo("Europe/Athens")
        counts: Counter[tuple[str, int, str]] = Counter()
        adas: dict[tuple[str, int, str], set[str]] = {}
        for f in files:
            with open(f, "rb") as fh:
                act = json.load(fh)
            # issueDate is a Greek civil date; older acts store it as local
            # midnight, newer ones as UTC midnight, so attribute the year in
            # Europe/Athens (see FINDINGS.md).
            yr = datetime.fromtimestamp(act["issueDate"] / 1000, timezone.utc).astimezone(athens).year
            key = (str(act.get("organizationId")), yr, str(act.get("status")))
            counts[key] += 1
            adas.setdefault(key, set()).add(act.get("ada"))
        typer.echo(f"{'org':<10} {'year':<6} {'status':<19} {'files':>6} {'adas':>6}  name")
        for (org, yr, status), n in sorted(counts.items()):
            e = reg.get(org)
            typer.echo(f"{org:<10} {yr:<6} {status:<19} {n:>6} {len(adas[(org, yr, status)]):>6}  {e.name if e else '?'}")
    kfiles = store.iter_khmdhs_records()
    if kfiles:
        # records/<endpoint>/<org>/<ref>.json
        kc = Counter((p.parent.parent.name, p.parent.name) for p in kfiles)
        typer.echo(f"khmdhs record files: {len(kfiles)}")
        for (ep, org), n in sorted(kc.items()):
            e = reg.get(org)
            typer.echo(f"  {ep:<9} {org:<10} {n:>6}  {e.name if e else '?'}")
    log = IngestLog(st.ingest_log).read()
    typer.echo(f"ingest log: {len(log)} record(s)  ({st.ingest_log})")
    if log:
        runs = sorted({r.get("run") for r in log if r.get("run")})
        last = log[-1]
        typer.echo(f"runs: {len(runs)}  last record: {last.get('ts')} org={last.get('org')} "
                   f"{last.get('from')}..{last.get('to_excl')} status={last.get('status', 'ok')}")


# --------------------------------------------------------------------------
@app.command()
def build() -> None:
    """Rebuild data/curated/*.parquet from data/raw (pure, no network)."""
    from tinos.curated import build_curated

    st = _settings()
    res = build_curated(st)
    typer.echo(f"curated -> {st.curated_dir}  (derived_at={res.derived_at.isoformat()})")
    for name, n in res.counts.items():
        typer.echo(f"  {name:<13}{n:>10,}")
    typer.echo(f"manifest: {res.manifest_path}")


@app.command()
def release() -> None:
    """Build releases/tinos.duckdb from the curated Parquet files."""
    from tinos.publish.release import build_release

    st = _settings()
    path, counts = build_release(st)
    typer.echo(f"release -> {path}")
    for name, n in counts.items():
        typer.echo(f"  {name:<13}{n:>10,}")


@app.command()
def summary() -> None:
    """Write SUMMARY.md from releases/tinos.duckdb."""
    from tinos.publish.privacy import PrivacyLeak
    from tinos.publish.summary import write_summary

    st = _settings()
    try:
        typer.echo(f"summary -> {write_summary(st)}")
    except PrivacyLeak as exc:
        for leak in exc.leaks:
            typer.echo(f"  {leak}", err=True)
        typer.echo(f"refusing to write SUMMARY.md: {exc}", err=True)
        raise typer.Exit(code=4)


@app.command(name="privacy-check")
def privacy_check(
    paths: Optional[list[Path]] = typer.Argument(None, help="Files to scan. Default: every file git tracks."),
) -> None:
    """Fail if a published file names or identifies a natural person (PRIVACY.md Q1).

    The repository is public, so every tracked file counts as published. Run
    before pushing.
    """
    from tinos.publish.privacy import load_markers, scan_files, tracked_files

    st = _settings()
    db = st.releases_dir / "tinos.duckdb"
    markers = load_markers(db) if db.is_file() else None
    if markers is None:
        typer.echo(f"warning: {db} not found; only the SURNAME,,NAME form is checked", err=True)
    files = [p.resolve() for p in paths] if paths else tracked_files(st.root)
    leaks = scan_files(files, markers, st.root)
    for leak in leaks:
        typer.echo(str(leak))
    typer.echo(f"privacy-check: {len(files)} file(s), {len(leaks)} leak(s)")
    if leaks:
        raise typer.Exit(code=1)


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
