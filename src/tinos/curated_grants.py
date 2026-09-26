"""Grants and allocations to Tinos in the curated layer.

grant_decision  one row per decision kept by ``tinos fulltext-backfill`` (the
                whitelist, PRIVACY.md Q7): another body's act naming Tinos
                that allocates, grants or finances. Classified by subject into
                a family and a revenue category (``tinos.extract.grants``);
                ``pdf_sha256`` is set once the act's PDF is stored. The
                whitelist is applied again here, so a record kept under an
                earlier, looser version of it (2015: six staff-travel acts
                naming employees) never reaches the curated layer; data/raw
                is append-only.
                ``found_by`` lists the search terms that found it (ΤΗΝΟΥ, or
                ΑΥΤΟΤΕΛΕΙΣ, the subject of every ΚΑΠ decision); ``text_indexed``
                is true when a stored page highlights its document text. A
                decision found only by subject, whose text was never indexed,
                is one a search for ΤΗΝΟΥ could not have found.
grant_line      one row per amount for a Tinos body read from a stored PDF
                (``tinos.extract.grants.read_decision``; the Region's with
                ``read_region``), with how it was validated against the
                document. ``grantor`` is ``interior`` (the four Interior
                Ministry uids) or ``region`` (the Region of South Aegean).

Double postings. The same decision is sometimes posted twice (same issuer,
protocol number, issue date and subject, minutes apart, two ADAs): the
monthly ΚΑΠ of March 2018 (108,081.58 for Tinos both times) and the
advertising-fee allocation of December 2022 (19,090.00 both times). One copy
is kept (the one with a Tinos amount, then the earliest submitted); the others
carry ``duplicate_of`` and are left out of every view.

Read from ``data/raw/diavgeia/fulltext/decisions`` (first capture of each
record) and ``data/raw/diavgeia/docs/<issuer>/<ADA>.pdf``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from tinos.config import KEEP_RULES, Registry
from tinos.extract.grants import (CATEGORY_OF_FAMILY, FOUNDATION_UID, ISSUER_FAMILIES, REGION_UIDS, TINOS_TPD_CODE,
                                  budget_year, family_of, read_decision, read_foundation, read_other, read_region,
                                  recipient_of)
from tinos.sources.fulltext import KEEP_ALL, TINOS_BODY_RE, fold, issue_day, whitelist_reason


def _iso(ts: Any) -> str:
    """«30/03/2018 10:44:26» (Athens wall clock) -> «2018-03-30T10:44:26», sortable."""
    t = str(ts or "")
    return f"{t[6:10]}-{t[3:5]}-{t[0:2]}T{t[11:19]}" if len(t) >= 19 else t


def iter_grant_decisions(raw_dir: Path) -> list[tuple[Path, str, dict[str, Any]]]:
    """(path, sha256, record) for the first capture of every kept decision."""
    base = raw_dir / "diavgeia" / "fulltext" / "decisions"
    out = []
    for path in sorted(base.glob("*/*.json")) if base.is_dir() else []:
        if "." in path.stem:  # <ADA>.<sha12>.json: a later capture
            continue
        data = path.read_bytes()
        out.append((path, hashlib.sha256(data).hexdigest(), json.loads(data)))
    return out


def search_index(raw_dir: Path) -> tuple[dict[str, list[str]], set[str]]:
    """From the stored search pages: ADA -> the terms whose pages list it kept, and the ADAs whose
    document text some page highlights (the text was indexed, so a ΤΗΝΟΥ search could see it)."""
    found, indexed, _ = search_index_by_issuer(raw_dir)
    return found, indexed


def search_index_by_issuer(raw_dir: Path) -> tuple[dict[str, list[str]], set[str], dict[str, set[str]]]:
    """:func:`search_index`, plus ADA -> the grantors whose searches kept it (the page's directory)."""
    base = raw_dir / "diavgeia" / "fulltext" / "search"
    found: dict[str, set[str]] = {}
    orgs: dict[str, set[str]] = {}
    indexed: set[str] = set()
    for page in sorted(base.glob("*/*/*.json")) if base.is_dir() else []:
        body = json.loads(page.read_bytes())
        for rec in body.get("decisions") or []:
            if not rec.get("redacted"):
                found.setdefault(rec["ada"], set()).add(page.parent.name)
                orgs.setdefault(rec["ada"], set()).add(page.parent.parent.name)
        indexed.update(a for a, h in (body.get("highlighting") or {}).items() if (h or {}).get("documentText"))
    return {a: sorted(t) for a, t in found.items()}, indexed, orgs


def keep_rules_for(ada: str, issuer: str, orgs: dict[str, set[str]], registry: Registry | None) -> tuple[str, ...]:
    """The whitelist's keep rules for a stored record: the union of the rules of every grantor whose search kept it
    (a joint decision a ministry search found is judged by that ministry's rules), else its issuer's."""
    if registry is None:
        return KEEP_ALL
    rules = {r for org in orgs.get(ada) or {issuer} for r in registry.keep_rules(org)}
    return tuple(r for r in KEEP_RULES if r in rules)


# The other grantors' families whose documents state money for a Tinos body; the rest (legality reviews, commitments,
# programme notices) are listed, not read for an amount.
OTHER_READ = frozenset({"election_costs", "school_books", "pde_financing", "culture_grant"})


def grant_rows(raw_dir: Path, stamp: dict[str, Any], anchors: frozenset[str] = frozenset(),
               registry: Registry | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(grant_decision rows, grant_line rows). Reads each stored PDF with ``pdftotext -layout``.

    ``anchors``: the Tinos bodies' ΑΦΜ; a decision found by one of them is kept whatever its subject,
    as ``tinos fulltext-backfill`` kept it. ``registry``: each issuer's whitelist keep rules and the
    grantor it is reported as (``entities.yaml``); without it every rule applies and an issuer is the
    Region or the Interior Ministry.
    """
    decisions, lines = [], []
    afm_uid = {e.afm: e.uid for e in registry.in_scope if e.afm} if registry else {"800302968": "6296"}
    found_by, indexed, found_orgs = search_index_by_issuer(raw_dir)
    records = iter_grant_decisions(raw_dir)
    # the Region's programme agreements (their subjects): a fund payment for a sub-project one of them names is paid
    # under that agreement
    agreements = frozenset(fold(rec.get("subject")) for path, _, rec in records
                           if path.parent.name in REGION_UIDS and family_of(rec.get("subject"), path.parent.name)
                           == "region_agreement")
    for path, sha, rec in records:
        anchored = bool(anchors & set(found_by.get(rec["ada"], [])))
        issuer = path.parent.name
        keep = keep_rules_for(rec["ada"], issuer, found_orgs, registry)
        if whitelist_reason(rec, anchored, keep) is not None:  # kept by an earlier whitelist; not carried (PRIVACY.md Q7)
            continue
        day = issue_day(rec["issueDate"])
        subject = " ".join(str(rec.get("subject") or "").split())
        region = issuer in REGION_UIDS
        family = family_of(subject, issuer)
        # A credit whose subject names no Tinos body, not found by a Tinos ΑΦΜ: a project of the Region's own on the
        # island, unless its document says the credit is transferred to the municipality.
        own = family == "region_credit" and not (anchored or TINOS_BODY_RE.search(fold(subject)))
        pdf = raw_dir / "diavgeia" / "docs" / issuer / f"{rec['ada']}.pdf"
        pdf_sha = hashlib.sha256(pdf.read_bytes()).hexdigest() if pdf.is_file() else None
        status = "no_pdf"
        amounts = []
        if pdf_sha:
            text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
            if region:  # the payment order's purpose line and the credit's recipient refine the family
                amounts, status, family = read_region(text, subject, family, agreements)
            elif issuer == FOUNDATION_UID:  # its items name their recipients; the statutory grant's refine the family
                if family in ("foundation_statutory_grant", "foundation_grant"):
                    amounts, status, family = read_foundation(text, family)
                else:
                    amounts, status = [], "listed"
            elif issuer in ISSUER_FAMILIES:  # the Decentralised Administration, the Education and Culture ministries
                amounts, status = read_other(text, subject, afm_uid) if family in OTHER_READ else ([], "listed")
            else:
                amounts, status = read_decision(text, subject)
        if own and (not pdf_sha or family != "region_credit"):
            # the Region's own project, paid through its fund or to another body (or not read): not money to Tinos
            family, amounts, status = "region_own_credit", [], "absent" if pdf_sha else status
        category = CATEGORY_OF_FAMILY.get(family)
        grantor = registry.grantor_group(issuer) if registry else "region" if region else "interior"
        # the year the money is for; the foundation's statutory grant names the year of the receipts it is 10% of, but
        # is booked when paid, so its payment year counts
        year_for = day.year if family.startswith("foundation_") else budget_year(subject, day.year)
        decisions.append({
            "ada": rec["ada"], "issuer": issuer, "grantor": grantor,
            "issuer_label": (rec.get("organization") or {}).get("label"),
            "co_issuers": sorted(str(c.get("uid")) for c in rec.get("cooperatingOrganizations") or [] if isinstance(c, dict)),
            "date": day, "year": day.year, "budget_year": year_for, "decision_type": (rec.get("decisionType") or {}).get("uid"),
            "status": rec.get("status"), "subject": subject, "family": family, "category": category,
            "protocol_number": (rec.get("protocolNumber") or "").strip() or None,
            "submission_ts": _iso(rec.get("submissionTimestamp")),
            "found_by": found_by.get(rec["ada"], []), "text_indexed": rec["ada"] in indexed,
            "read_status": status, "n_amounts": len(amounts),
            "n_validated": sum(1 for a in amounts if a.validation and a.amount is not None),
            "pdf_sha256": pdf_sha, "source_ada": rec["ada"], "source_path": str(path), "source_sha256": sha, **stamp,
        })
        for i, a in enumerate(amounts):
            lines.append({
                "grant_line_id": f"{rec['ada']}:{i}", "line_no": i, "ada": rec["ada"], "issuer": issuer, "grantor": grantor,
                "recipient_tpd_code": TINOS_TPD_CODE, "recipient_entity": a.recipient or recipient_of(subject),
                "date": day, "year": day.year, "budget_year": year_for, "status": rec.get("status"),
                "family": family, "category": category,
                "amount": a.amount / 100 if a.amount is not None else None,
                "net_paid": a.net / 100 if a.net is not None else None,
                "method": a.method, "validation": a.validation, "detail": a.detail,
                "source_ada": rec["ada"], "source_path": str(pdf), "source_sha256": pdf_sha, **stamp,
            })
    _mark_duplicates(decisions, lines)
    return decisions, lines


def _mark_duplicates(decisions: list[dict[str, Any]], lines: list[dict[str, Any]]) -> None:
    from collections import defaultdict
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for d in decisions:
        d["duplicate_of"] = None
        if d["protocol_number"]:
            groups[(d["issuer"], d["protocol_number"], d["date"], fold(d["subject"]))].append(d)
    dup_of: dict[str, str] = {}
    # the same act posted twice with a retyped subject (Education 2025: protocol 13931, two ADAs 2.5 minutes apart,
    # identical documents): same issuer, protocol number, date and amounts
    amounts_of: dict[str, tuple] = defaultdict(tuple)
    for line in lines:
        amounts_of[line["ada"]] += ((line.get("recipient_entity"), line.get("amount")),)
    retyped: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for d in decisions:
        if d["protocol_number"] and amounts_of.get(d["ada"]):
            retyped[(d["issuer"], d["protocol_number"], d["date"], amounts_of[d["ada"]])].append(d)
    for key, members in retyped.items():
        if len({fold(d["subject"]) for d in members}) > 1:
            groups[key] = members
    for members in groups.values():
        if len(members) < 2:
            continue
        keep = min(members, key=lambda d: (d["n_amounts"] == 0, d["submission_ts"], d["ada"]))
        for d in members:
            if d is not keep:
                d["duplicate_of"] = dup_of[d["ada"]] = keep["ada"]
    for line in lines:
        line["duplicate_of"] = dup_of.get(line["ada"])
