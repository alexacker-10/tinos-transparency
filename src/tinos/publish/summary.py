"""Write ``SUMMARY.md`` from the release database.

Everything printed here is a query over ``releases/tinos.duckdb``; nothing
is typed in by hand except the FY2024 reference figures, which are quoted
from FINDINGS.md with their source ADAs.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from tinos.config import Settings
from tinos.publish.privacy import PrivacyLeak, find_leaks, load_markers

# Reference figures from FINDINGS.md (verified from the PDFs named there). 6ΝΠΘΩΗ6-Β64 is the
# December 2024 execution statement, i.e. the whole year; stored in data/raw/diavgeia/docs.
FY2024_REFERENCE = [
    ("Voted budget (revenue = expenditure)", 22_251_724.35, "ΨΞΕΟΩΗ6-2ΥΑ"),
    ("Revised budget at 31 Dec", 23_669_482.09, "6ΝΠΘΩΗ6-Β64"),
    ("Ενταλματοποιηθέντα (warranted)", 11_153_794.10, "6ΝΠΘΩΗ6-Β64"),
    ("Πληρωθέντα (paid)", 11_134_283.87, "6ΝΠΘΩΗ6-Β64"),
    ("  of which personnel costs (ΚΑΕ 60xx)", 2_925_750.54, "6ΝΠΘΩΗ6-Β64"),
    ("  of which remittances (ΚΑΕ 82xx)", 1_597_701.22, "6ΝΠΘΩΗ6-Β64"),
]


def _eur(v: float | None) -> str:
    return "" if v is None else f"{v:,.2f}"


def _m(v: float | None) -> str:
    return "" if v is None else f"{v / 1e6:,.2f}M"


def _cell(v: object) -> str:
    """Source text is third-party: keep pipes, line breaks and tags from breaking or injecting Markdown."""
    return "" if v is None else " ".join(str(v).split()).replace("|", "\\|").replace("<", "&lt;")


def _table(headers: list[str], rows: list[list], align_right_from: int = 1) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(("---:" if i >= align_right_from else "---") for i in range(len(headers))) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_cell(v) for v in r) + " |")
    return "\n".join(out)


def write_summary(settings: Settings) -> Path:
    db = settings.releases_dir / "tinos.duckdb"
    con = duckdb.connect(str(db), read_only=True)
    q = lambda sql, *args: con.execute(sql, list(args)).fetchall()  # noqa: E731
    meta = {k: json.loads(v) for k, v in q("SELECT key, value FROM meta")}
    names = dict(q("SELECT uid, name FROM entity"))
    L: list[str] = []
    w = L.append

    w("# Tinos Transparency — summary")
    w("")
    w(f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} by `tinos summary` "
      f"from `releases/tinos.duckdb` (pipeline `{meta['pipeline_version']}`, curated at "
      f"{meta['derived_at']}, {meta['source_acts']:,} source acts, source digest "
      f"`{meta['source_digest'][:16]}…`). Every figure below is a query over the release; "
      "nothing is hand-typed except the FY2024 reference row, which cites its ADA.")
    w("")
    w("**Read this first.** Payments, commitments and awards are three different measures of the "
      "same spending. The same euro is reserved (Β.1.3), then awarded (Δ.1), then paid (Β.2.2). "
      "They are shown side by side but must never be added together. Payroll payments have no "
      "counterparty by design and are counted, never itemised.")
    w("")

    # ---- corpus
    w("## Corpus")
    w("")
    rows = q("SELECT entity, count(*), min(year), max(year) FROM act GROUP BY 1 ORDER BY 2 DESC")
    w(_table(["Entity", "Name", "Acts", "First", "Last"],
             [[e, names.get(e, "?"), f"{n:,}", a, b] for e, n, a, b in rows], 2))
    w("")
    st = q("SELECT status, count(*) FROM act GROUP BY 1 ORDER BY 2 DESC")
    w("Status: " + " · ".join(f"{s} {n:,}" for s, n in st) + ".")
    w("")

    # ---- acts by year and type
    w("## Acts by year and type")
    w("")
    top_types = [t for (t,) in q("SELECT type FROM act GROUP BY 1 ORDER BY count(*) DESC LIMIT 6")]
    years = [y for (y,) in q("SELECT DISTINCT year FROM act ORDER BY 1")]
    counts = {(y, t): n for y, t, n in q("SELECT year, type, count(*) FROM act GROUP BY 1, 2")}
    totals = dict(q("SELECT year, count(*) FROM act GROUP BY 1"))
    rows = []
    for y in years:
        known = sum(counts.get((y, t), 0) for t in top_types)
        rows.append([y, f"{totals[y]:,}"] + [f"{counts.get((y, t), 0):,}" for t in top_types] + [f"{totals[y] - known:,}"])
    w(_table(["Year", "All"] + top_types + ["Other"], rows))
    w("")
    w("Β.2.2 = payment finalisation · Β.1.3 = commitment · Δ.1 = direct award · 2.4.7.1 = "
      "miscellaneous individual acts · Α.2 = regulatory acts. Two taxonomies (numeric and Greek-letter) "
      "coexist for the whole period; neither replaced the other.")
    w("")

    # ---- money by year, all entities and municipality
    for title, where in (("all entities", "1=1"), ("Δήμος Τήνου (6296) only", "entity = '6296'")):
        w(f"## Money by year, {title}")
        w("")
        rows = q(f"""
            SELECT year, sum(n_acts), sum(n_payment_acts), sum(payment_eur), sum(supplier_eur), sum(remittance_eur),
                   sum(internal_transfer_eur), sum(other_nonsupplier_eur),
                   sum(n_payroll_acts), sum(payroll_eur), sum(n_commitment_acts), sum(commitment_eur), sum(reversal_eur),
                   sum(n_award_acts), sum(award_eur)
            FROM v_yearly WHERE {where} GROUP BY 1 ORDER BY 1""")
        w(_table(["Year", "Acts", "Payment acts", "Third-party payments €", "Suppliers €", "Remittances €",
                  "Internal transfers €", "Tax, debt, other public €", "Payroll acts", "Payroll € (where posted)",
                  "Commitment acts", "Commitments €", "Reversals € (excluded)", "Award acts", "Awards €"],
                 [[y, f"{a:,}", f"{p or 0:,}", _m(pe), _m(se), _m(re_), _m(it), _m(ot), f"{pr or 0:,}", _m(pl),
                   f"{c or 0:,}", _m(ce), _m(rv), f"{aw or 0:,}", _m(ae)]
                  for y, a, p, pe, se, re_, it, ot, pr, pl, c, ce, rv, aw, ae in rows]))
        w("")
    w("Third-party payments are every Β.2.2 sponsor line with a counterparty, split by payee class. "
      "*Suppliers* are the residual after removing *remittances* (withholdings passed to the state), "
      "*internal transfers* (the municipality funding its own bodies), and *tax, debt service and other "
      "public bodies* (ΕΝΦΙΑ and fees, loan instalments, payments to other municipalities, regions, "
      "ministries and insurance funds). Only the supplier column is procurement. Payroll euros "
      "are visible only from late 2025, when the municipality began posting payroll batches with an "
      "amount; before that payroll acts carry no amount at all. In 2026 the municipality adopted a new "
      "chart of accounts, so ΚΑΕ-based classification is weaker for that year. Commitments exclude year-end reversals "
      "(Ανατροπές), which Diavgeia posts as positive Β.1.3 amounts; the excluded euros are shown so the "
      "effect is visible. Β.1.3 is in consistent use from 2017 and carries amounts reliably from 2020; the 2012 municipal figure is the whole "
      "annual budget summary posted under that type, not a commitment. Awards (Δ.1) collapse from 2021 "
      "while payments hold steady: the money did not move, the award record stopped being duplicated "
      "into Diavgeia (see coverage gaps).")
    w("")

    # ---- payee classes
    w("## Payee classes, all entities")
    w("")
    rows = q("""SELECT payee_class, sum(n_lines), sum(n_acts), sum(eur) FROM v_payee_class_year
                GROUP BY 1 ORDER BY 4 DESC NULLS LAST""")
    w(_table(["Class", "Lines", "Acts", "€"], [[c, f"{l:,}", f"{a:,}", _eur(e)] for c, l, a, e in rows]))
    w("")
    w("Classes are assigned by deterministic rules (see the `curated.py` docstring): payroll → internal "
      "transfer (payee ΑΦΜ belongs to an entity in `entities.yaml`) → remittance (ΚΑΕ 82 or a withholdings "
      "subject) → tax (ΚΑΕ 63, tax-authority payee, ΕΝΦΙΑ/ΦΠΑ subject) → debt service (ΚΑΕ 65, bank or "
      "Ταμείο Παρακαταθηκών payee) → other public body (name marks a state, regional, municipal, insurance "
      "or regulatory body) → supplier, then a second pass reclassifies supplier lines of any ΑΦΜ whose euros are at least 80% "
      "non-supplier across all years (`payee_class_rule = afm_propagation`). Utilities such as ΔΕΗ and ΕΛΤΑ stay suppliers; grants to clubs and "
      "churches (ΚΑΕ 67) are not yet separated and remain in the supplier column.")
    w("")
    it = q("""SELECT p.counterparty_display, count(*), sum(p.amount) FROM v_internal_transfer p
              GROUP BY 1 ORDER BY 3 DESC LIMIT 6""")
    w("Largest internal transfers (not procurement): " + "; ".join(f"{_cell(n)} {_eur(e)} € in {c} payments" for n, c, e in it) + ".")
    w("")

    # ---- supplier concentration
    w("## Supplier concentration, Δήμος Τήνου")
    w("")
    rows = q("""SELECT c.year, d.n_suppliers, c.n_suppliers, c.n_only_khmdhs, c.supplier_eur, c.top10_share, c.top1_share
                FROM v_supplier_year_combined c LEFT JOIN v_counterparty_year d USING (entity, year)
                WHERE c.entity = '6296' ORDER BY 1""")
    w("Supplier-class payments only: payroll, remittances, internal transfers, taxes, debt service and "
      "other public bodies are excluded, so the state, EFKA, the tax office, the bank and the "
      "municipality's own bodies do not appear as \"suppliers\". From 2019 most supplier payments are "
      "published in ΚΗΜΔΗΣ rather than Diavgeia, so the series adds every ΚΗΜΔΗΣ payment whose payee has "
      "no Diavgeia payment line within 60 days (`v_supplier_year_combined`; a floor).")
    w("")
    w(_table(["Year", "Suppliers in Diavgeia alone", "Suppliers, with ΚΗΜΔΗΣ", "of which only in ΚΗΜΔΗΣ",
              "Supplier payments €", "Top-10 share", "Top-1 share"],
             [[y, d or 0, n, k, _m(e), f"{s * 100:.1f}%", f"{t * 100:.1f}%"] for y, d, n, k, e, s, t in rows]))
    w("")
    w("Diavgeia alone suggests the municipality's suppliers fell from about 200 to under 100 after 2018 and "
      "that one payee took 50-67% of the money. Neither is true: from 2019 small suppliers are paid through "
      "ΚΗΜΔΗΣ-published payment orders instead (FINDINGS.md F6), and with them the count holds at about "
      "200-250 a year. In 2026 the municipality's new software puts supplier payments back in Diavgeia, "
      "which is why the Diavgeia-alone count jumps. 2020 was not a trough in supplier payments; its "
      "payments were simply not in Diavgeia.")
    w("")
    w("**Concentration has innocent explanations and is not, by itself, evidence of anything improper.** "
      "A few large payees dominate any municipal ledger: the electricity utility, waste-management and "
      "water contractors, and multi-year public-works contracts each concentrate spending in one ΑΦΜ. "
      "A single EU-funded project can put most of a year's euros with one contractor. Fewer, larger "
      "contracts (a policy choice, or a shift of small purchases to framework agreements) reduce the "
      "count of small suppliers without anyone doing anything wrong. Use this table to decide where to "
      "look, not as a finding.")
    w("")
    cp = q("SELECT count(*), sum(CASE WHEN needs_review THEN 1 ELSE 0 END), sum(total_received) FROM counterparty")[0]
    w(f"Counterparty registry: {cp[0]:,} distinct ΑΦΜ, {cp[1]:,} flagged for review (non-standard ΑΦΜ "
      f"format or materially different name spellings under one ΑΦΜ). Resolution is exact-ΑΦΜ only; "
      "name variants are collected, never merged.")
    w("")
    top = q("""SELECT afm, display_name, total_received_supplier, n_payments, first_seen, last_seen,
                      n_entities, largest_payment_ada
               FROM counterparty WHERE total_received_supplier > 0 AND NOT is_natural_person
               ORDER BY total_received_supplier DESC LIMIT 15""")
    people = q("""SELECT count(DISTINCT p.counterparty_afm), count(*), sum(p.amount) FROM v_supplier_payment p
                  JOIN counterparty c ON c.afm = p.counterparty_afm WHERE c.is_natural_person""")[0]
    supplier_eur = q("SELECT sum(amount) FROM v_supplier_payment")[0][0]
    w("Top 15 counterparties by supplier-class euros received, all entities, all years (published, "
      "non-suspect). Natural persons, sole traders included, are not ranked: a masked row would still "
      "give one person's all-years total, and the ADA printed beside it names them at source. Together, "
      f"{people[0]:,} natural persons received {_eur(people[2])} € ({people[2] / supplier_eur * 100:.1f}% of "
      f"supplier-class euros) in {people[1]:,} payments (see PRIVACY.md).")
    w("")
    w(_table(["ΑΦΜ", "Name", "Received €", "Payments", "First", "Last", "Entities", "Largest payment"],
             [[a, n, _eur(t), p, f, l, e, ada] for a, n, t, p, f, l, e, ada in top], 2))
    w("")

    # ---- data quality
    w("## Data quality flags")
    w("")
    # Names come from counterparty_display, never counterparty_name_raw: natural persons are masked there.
    sus = q("""SELECT p.entity, p.date, p.source_ada, p.amount, p.suspect_reason, substr(p.counterparty_display, 1, 40), substr(a.subject, 1, 70)
               FROM v_payment_suspect p JOIN act a ON a.ada = p.source_ada ORDER BY p.amount DESC""")
    w("Suspect payment lines (above 10,000,000 € = `threshold`, or checked against the decision's PDF and "
      "found wrong = `document_mismatch`, see `data/manual/amount_review.yaml`; kept in `payment`, excluded "
      f"from every view and total): {len(sus)}")
    w("")
    if sus:
        w(_table(["Entity", "Date", "ADA", "Amount €", "Reason", "Counterparty", "Subject"],
                 [[e, d, ada, _eur(amt), why, n, sub] for e, d, ada, amt, why, n, sub in sus], 3))
        w("")
    big = q("""SELECT p.entity, p.date, p.source_ada, p.amount, substr(p.counterparty_display, 1, 40), p.kae, substr(a.subject, 1, 70)
               FROM v_supplier_payment p JOIN act a ON a.ada = p.source_ada ORDER BY p.amount DESC LIMIT 8""")
    w("Largest single supplier payment lines in the release. Large one-offs explain most year-to-year "
      "swings and should be read before any trend is. Each row is one published decision, checkable at "
      "source by its ADA, but a published amount is not always right: the municipality's own year-end "
      "statements exposed nine lines entered x100 (FINDINGS.md F7), and bodies whose statements are not "
      "parsed yet are unchecked. A natural person appears as «φυσικό πρόσωπο»:")
    w("")
    w(_table(["Entity", "Date", "ADA", "Amount €", "Counterparty", "ΚΑΕ", "Subject"],
             [[e, d, ada, _eur(amt), n, k, sub] for e, d, ada, amt, n, k, sub in big], 3))
    w("")
    rv = q("SELECT count(DISTINCT source_ada), sum(amount) FROM v_commitment_reversal")[0]
    w(f"Commitment reversals excluded from commitment totals: {rv[0]:,} acts, {_eur(rv[1])} €. "
      "Identified by the `recalledExpenseDecision` flag or a subject containing Ανατροπή/Ανάκληση.")
    w("")

    # ---- coverage gaps
    w("## Coverage gaps")
    w("")
    pend = q("SELECT count(*) FROM act WHERE status = 'PENDING_REVOCATION'")[0][0]
    rev = q("SELECT count(*) FROM act WHERE status = 'REVOKED'")[0][0]
    payroll = q("SELECT count(*) FROM v_payroll")[0][0]
    d1_2024 = q("SELECT count(*) FROM act WHERE type = 'Δ.1' AND year = 2024 AND entity = '6296'")[0][0]
    noamt = q("SELECT count(*) FROM v_award WHERE amount IS NULL")[0][0]
    nokae = q("SELECT count(*) FROM v_commitment WHERE NOT has_kae_lines")[0][0]
    weak = [str(y) for (y,) in q("""SELECT year FROM v_yearly WHERE entity = '6296' AND year >= 2017
                                     AND coalesce(reversal_eur, 0) > coalesce(commitment_eur, 0) ORDER BY 1""")]
    pk = dict(q("SELECT payroll_kind, count(*) FROM payment WHERE is_payroll GROUP BY 1"))
    # Municipal Β.1.3 acts per year, and how many carry no usable amount (null or zero on every line).
    b13 = q("""WITH a AS (SELECT year, source_ada, max(coalesce(amount, 0)) AS m FROM commitment
                          WHERE entity = '6296' AND act_status = 'PUBLISHED' GROUP BY 1, 2)
               SELECT year, count(*) FILTER (WHERE m = 0), count(*) FROM a GROUP BY 1 ORDER BY 1""")
    pre = (min(t for y, _, t in b13 if y < 2017), max(t for y, _, t in b13 if y < 2017))
    thin = [(y, n, t) for y, n, t in b13 if y >= 2017 and n > 0.05 * t]
    for line in [
        f"**Payroll is counted, never itemised.** {pk.get('no_sponsor', 0):,} payment acts have an empty sponsor "
        "list because the beneficiary is an employee; Diavgeia withholds the name and the amount by design, "
        "so the personnel lines (ΚΑΕ 60xx) of the municipality's monthly execution statements are the only "
        f"handle on them (FY2024 below). From late 2025 the municipality posts payroll "
        f"batches that name one representative employee plus \"& ΛΟΙΠΟΙ\" ({pk.get('batch', 0):,} lines); a few "
        f"payroll acts name a single person ({pk.get('named', 0):,} lines) and some pay a natural person under "
        f"the personnel ΚΑΕ ({pk.get('personnel_kae', 0):,} lines). These carry an amount, which is kept; "
        "the name and ΑΦΜ are dropped in the curated layer and never reach the counterparty table.",
        f"**Direct awards left Diavgeia in 2021.** Δήμος Τήνου published {d1_2024} Δ.1 acts in 2024 against "
        "about 350 a year before 2021, while its payment volume did not change and ΚΗΜΔΗΣ contract counts "
        "stayed flat. Award values from 2021 onward must come from ΚΗΜΔΗΣ, not from this table.",
        f"**Award amounts and CPV are unreliable.** {noamt:,} published award rows have no amount; CPV is "
        "filled on under 15% of awards in any year.",
        f"**Commitment euros are complete only from {thin[-1][0] + 1 if thin else 2017}.** Before 2017 "
        f"Δήμος Τήνου barely used Β.1.3 ({pre[0]}–{pre[1]} acts a year); from 2017 it posts about a thousand a "
        "year, but many carry no amount: "
        + ", ".join(f"{n:,} of {tot:,} in {y}" for y, n, tot in thin)
        + f". {nokae:,} published commitment rows have no per-ΚΑΕ breakdown, so their ΚΑΕ is null and the "
        "amount is the act total. "
        + (f"In {', '.join(weak)} the municipality's year-end reversals exceed its posted commitments, so the "
           "commitment record for those years is incomplete, not small." if weak else ""),
        f"**Revocations.** {rev:,} acts are REVOKED and are excluded from every total. {pend:,} acts are "
        "PENDING_REVOCATION: version logs show these are mis-uploads flagged within minutes of publication "
        "(wrong file, double posting, wrong venue) that the central operator never processed, all between "
        "March 2018 and January 2020. They are excluded from the measure tables and are not withdrawn spending.",
        "**Time span.** Diavgeia starts in late 2010; three subsidiaries stopped publishing after 2023 (local "
        "government reform); the current year is partial.",
        "**Dates** are Greek civil dates attributed in Europe/Athens. Diavgeia stored them as local midnight "
        "until 2014 and UTC midnight after; naive UTC attribution moves acts across year boundaries.",
    ]:
        w(f"- {line}")
    w("")

    # ---- reconciliation
    w("## Reconciliation, FY2024, Δήμος Τήνου")
    w("")
    ours = q("""SELECT sum(payment_eur), sum(n_payroll_acts), sum(commitment_eur), sum(n_payment_acts), sum(remittance_eur), sum(reversal_eur)
                FROM v_yearly WHERE entity = '6296' AND year = 2024""")[0]
    paid = FY2024_REFERENCE[3][1]
    rows = [[label, _eur(v), ada] for label, v, ada in FY2024_REFERENCE]
    rows += [
        ["Β.2.2 third-party payments, this release", _eur(ours[0]), f"{ours[3]:,} payment acts, curated"],
        ["  of which remittances to the state (ΚΑΕ 82 or withholdings subject)", _eur(ours[4]), "curated"],
        ["Β.1.3 commitments, this release (reversals excluded)", _eur(ours[2]), f"curated; {_eur(ours[5])} € of reversals excluded"],
    ]
    w(_table(["Figure", "€", "Source"], rows, 1))
    w("")
    w("The December execution statement (6ΝΠΘΩΗ6-Β64) is the denominator: what the municipality itself "
      f"reports as paid in the year. Diavgeia's payment decisions carry amounts for {(ours[0] or 0) / paid:.0%} "
      "of it. Personnel costs are almost entirely missing there, and so are whole spending groups such as "
      "consumables, equipment and works (FINDINGS.md). Paid minus third-party payments is therefore not a "
      "payroll estimate; payroll is read from the statement's personnel lines. Two withholdings lines, "
      "6Ω80ΩΗ6-0Ι2 (2023) and 6Ξ6ΖΩΗ6-26Β (2024), were entered in cents (about 2.0 million € each where the "
      "document says about 20,000 €); they are verified against their PDFs, flagged and excluded. Commitments "
      "exceed payments by design: they are budget reservations, many multi-year, not cash.")
    w("")

    # ---- coverage: Diavgeia payments against the municipality's own year-end statements
    cov = q("""SELECT year, sum(paid_per_statement), sum(paid_in_diavgeia),
                      sum(paid_in_diavgeia) FILTER (WHERE kae_group <> '60')
                        / sum(paid_per_statement) FILTER (WHERE kae_group <> '60'),
                      any_value(statement_ada)
               FROM v_payment_coverage WHERE entity = '6296' GROUP BY 1 ORDER BY 1""")
    if cov:
        w("## How much of what was paid Diavgeia shows, Δήμος Τήνου")
        w("")
        w(_table(["Year", "Paid, per the year-end statement €", "With a Diavgeia payment line €", "Share",
                  "Share excl. staff", "Statement"],
                 [[y, _eur(s), _eur(d), f"{d / s:.0%}" if s else "", "" if x is None else f"{x:.0%}", ada]
                  for y, s, d, x, ada in cov], 1))
        w("")
        w("The year-end execution statement is the municipality's own account of what it paid, parsed from its PDF "
          "with every column equal to the document's totals. Until 2018 Diavgeia's payment decisions carried nearly "
          "all non-staff payments; from 2019 most supplier payments are recorded in ΚΗΜΔΗΣ instead (FINDINGS.md F6). "
          "A share above 100% means some Diavgeia amount cannot be right (FINDINGS.md F7). Staff pay is withheld "
          "from Diavgeia by design.")
        w("")

    # ---- money given to Tinos: Interior Ministry allocations, against the revenue side
    grants = q("""SELECT year, sum(n_decisions),
                         sum(allocated) FILTER (WHERE category = 'kap_general'),
                         sum(allocated) FILTER (WHERE category = 'kap_investment'),
                         sum(allocated) FILTER (WHERE category IN ('kap_schools', 'school_rents', 'school_repairs', 'school_cleaners')),
                         sum(allocated) FILTER (WHERE category IN ('fire_protection', 'home_help', 'kap_other', 'welfare')),
                         sum(allocated) FILTER (WHERE category = 'state_grants'),
                         sum(allocated) FILTER (WHERE category = 'investment_programmes'),
                         sum(allocated) FILTER (WHERE category IN ('advertising_fee', 'property_tax')),
                         sum(allocated)
                  FROM v_grant_year WHERE year BETWEEN 2015 AND 2025 GROUP BY 1 ORDER BY 1""")
    if grants:
        counts = dict(q("SELECT read_status, count(*) FROM grant_decision GROUP BY 1"))
        n_lines = q("""SELECT count(*), count(*) FILTER (WHERE validation IS NOT NULL) FROM grant_line
                       WHERE category IS NOT NULL AND status = 'PUBLISHED' AND duplicate_of IS NULL""")[0]
        w("## Money given to Tinos by the Interior Ministry, 2015-2025")
        w("")
        w(f"Found by full-text search of the ministry's decisions for «ΤΗΝΟΥ» (and, for 2015, whose annexes are not "
          f"indexed, for «ΑΥΤΟΤΕΛΕΙΣ»): {sum(counts.values()):,} decisions kept, {counts.get('read', 0):,} with an "
          f"amount for Δήμος Τήνου read from their PDF, {counts.get('absent', 0):,} whose validated table shows Tinos "
          f"was not a recipient. {n_lines[1]:,} of {n_lines[0]:,} amounts are validated against the document itself: "
          "the table's column sums its own total line, or the letter states the amount, or spells it in words. "
          "Only validated amounts are counted below, each once (two decisions posted twice are counted once). "
          "Year = the year the allocation is for.")
        w("")
        w(_table(["Year", "Decisions", "ΚΑΠ general €", "ΚΑΠ investment €", "Schools €", "Other targeted €",
                  "State grants €", "Investment programmes €", "Fees collected centrally €", "Total €"],
                 [[y, n, _eur(a), _eur(b), _eur(c), _eur(d), _eur(e), _eur(f), _eur(g), _eur(t)]
                  for y, n, a, b, c, d, e, f, g, t in grants], 1))
        w("")
        labels = {
            "kap_general": "ΚΑΠ, general needs (0611)",
            "kap_investment": "ΚΑΠ, investment «ΣΑΤΑ» (1311, 0612 from 2023)",
            "kap_schools": "ΚΑΠ, schools' running costs (0614, 4311, 0616)",
            "school_rents": "ΚΑΠ, school rents (0612 to 2021)",
            "school_repairs": "School repairs (1312, 0615 from 2023)",
            "fire_protection": "Fire protection (1214, 0614 from 2023)",
            "home_help": "«Βοήθεια στο Σπίτι» (0624)",
            "advertising_fee": "Advertising fee, category Δ (0715)",
            "kap_other": "ΚΑΠ, other purposes (0619)",
            "school_cleaners": "School cleaners' pay (0621 from 2023)",
            "state_grants": "State grants (1211, 1215, 1219)",
            "investment_programmes": "Investment programmes (1314, 1315, 1322)",
            "property_tax": "Property levy ΤΑΠ, the ministry's share (0441)",
            "welfare": "Welfare benefits (0621 in 2015)",
        }
        rec = q("""SELECT category, year, allocated, assessed FROM v_grant_reconciliation
                   WHERE year BETWEEN 2015 AND 2025 AND category IS NOT NULL""")
        cells: dict[str, dict[int, str]] = {}
        for cat, year, alloc, booked in rec:
            if not alloc and not booked:
                continue
            diff = (alloc or 0) - (booked or 0)
            if abs(diff) < 0.005:
                cell = "="
            elif alloc and booked and abs(diff / alloc - 0.0015) < 0.00002:
                cell = "≈ 0.15%"
            else:
                cell = f"{diff:+,.0f}"
            cells.setdefault(cat, {})[year] = cell
        years = list(range(2015, 2026))
        w("**Against the municipality's own books.** Each cell is allocated minus booked for that revenue line in the "
          "year-end statement (`v_grant_reconciliation`): «=» to the cent, «≈ 0.15%» booked exactly 0.15% less than "
          "allocated, otherwise the difference in euros (positive: allocated but not booked there).")
        w("")
        w(_table(["Revenue line"] + [str(y) for y in years],
                 [[labels.get(cat, cat)] + [cells[cat].get(y, "") for y in years]
                  for cat in labels if cat in cells], 1))
        w("")
        w("Where the two sources meet line for line they agree to the cent, or differ by exactly 0.15%: school "
          "repairs and fire protection in every year whose decision was found, the advertising fee in 2016 and "
          "2018-2025, «Βοήθεια στο Σπίτι» 2023-2025, the general ΚΑΠ in 2015-2016, 2020 and 2023-2024 (2025 within "
          "25 €). The general ΚΑΠ gaps of 2017, 2021 and 2022 are monthly instalments that the search index holds by "
          "subject only, so a search for ΤΗΝΟΥ cannot find them (11 decisions, FINDINGS.md F8). 2018 and 2019 are one "
          "supplementary allocation, 29,762.12 € decided on 28 December 2018 and booked in 2019. The property levy "
          "(ΤΑΠ) is mostly collected through electricity bills, so the ministry's share is a small part of line 0441 "
          "by construction; the investment-programme and state-grant lines also receive money from other ministries "
          "and the EU. Allocations and booked revenue are two views of the same transfers: compare them, never add "
          "them.")
        w("")

    # ---- the subsidiaries' own statements
    # Totals, not per ΚΑΕ group: the smaller bodies' payment lines mostly carry no ΚΑΕ.
    sub = q("""WITH s AS (SELECT entity, year, sum(paid_per_statement) AS paid FROM v_payment_coverage
                          WHERE entity <> '6296' GROUP BY 1, 2),
                    p AS (SELECT entity, year, sum(amount) AS pub FROM payment
                          WHERE act_status = 'PUBLISHED' AND NOT amount_suspect AND amount IS NOT NULL GROUP BY 1, 2)
               SELECT s.entity, s.year, s.paid, coalesce(p.pub, 0) FROM s LEFT JOIN p USING (entity, year)
               ORDER BY 1, 2""")
    if sub:
        w("## How much of what the subsidiaries paid Diavgeia shows")
        w("")
        w(_table(["Entity", "Name", "Year", "Paid, per the year-end statement €", "With a Diavgeia payment line €", "Share"],
                 [[e, names.get(e, ""), y, _eur(s), _eur(d), f"{d / s:.0%}" if s else ""] for e, y, s, d in sub], 3))
        w("")
        w("Only the December statements that parse to the cent are used, one per body and year where one was "
          "found. Every payment line with an amount counts, with or without a ΚΑΕ, so a share above 100% can also "
          "be a payment of the previous year's bills; the ΚΑΕ-by-ΚΑΕ check is `v_kae_reconciliation` "
          "(FINDINGS.md F7, where two port-authority lines stand out as probable x100 entries).")
        w("")

    # ---- method
    w("## Method")
    w("")
    w("- Source: `data/raw/diavgeia/acts/<entity>/<ADA>.json`, append-only, content-hashed. Every curated "
      "row carries `source_ada`, `source_sha256`, `derived_at`, `pipeline_version`.")
    w("- Every Diavgeia response was accepted only after its echoed query matched the request "
      "(organisation, both date bounds, status clause, page). See FINDINGS.md.")
    w("- Rebuild: `tinos build && tinos release && tinos summary`.")
    w("")
    con.close()
    text = "\n".join(L)
    # Fail closed: a summary that names a natural person is never written (PRIVACY.md Q1).
    leaks = find_leaks(text, load_markers(db), settings.summary_file.name)
    if leaks:
        raise PrivacyLeak(leaks)
    settings.summary_file.write_text(text, encoding="utf-8")
    return settings.summary_file
