"""``tinos`` command line: entities, doctor, backfill, status."""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date, timedelta

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
    from tinos.publish.summary import write_summary

    st = _settings()
    typer.echo(f"summary -> {write_summary(st)}")


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
