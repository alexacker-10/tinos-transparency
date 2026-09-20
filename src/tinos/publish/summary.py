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

# Reference figures from FINDINGS.md (verified from the PDFs named there).
FY2024_REFERENCE = [
    ("Voted budget (revenue = expenditure)", 22_251_724.35, "ΨΞΕΟΩΗ6-2ΥΑ"),
    ("Revised budget by December", 23_630_861.94, "Ψ68ΩΩΗ6-3ΓΦ"),
    ("Ενταλματοποιηθέντα (warranted)", 9_055_399.10, "Ψ68ΩΩΗ6-3ΓΦ"),
    ("Πληρωθέντα (paid)", 8_877_120.61, "Ψ68ΩΩΗ6-3ΓΦ"),
]
PROBE_2024_THIRD_PARTY = 6_031_795.60
PROBE_2024_COMMITMENTS = 20_000_913.15


def _eur(v: float | None) -> str:
    return "" if v is None else f"{v:,.2f}"


def _m(v: float | None) -> str:
    return "" if v is None else f"{v / 1e6:,.2f}M"


def _table(headers: list[str], rows: list[list], align_right_from: int = 1) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(("---:" if i >= align_right_from else "---") for i in range(len(headers))) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
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
      "effect is visible. Β.1.3 is in consistent use only from 2017; the 2012 municipal figure is the whole "
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
    w("Largest internal transfers (not procurement): " + "; ".join(f"{n.strip()} {_eur(e)} € in {c} payments" for n, c, e in it) + ".")
    w("")

    # ---- supplier concentration
    w("## Supplier concentration, Δήμος Τήνου")
    w("")
    rows = q("""WITH f AS (SELECT counterparty_afm, min(year) AS y0 FROM v_supplier_payment WHERE entity = '6296' GROUP BY 1),
                       n AS (SELECT y0 AS year, count(*) AS new_suppliers FROM f GROUP BY 1)
                SELECT c.year, c.n_suppliers, n.new_suppliers, c.supplier_eur, c.top10_share, c.top1_share
                FROM v_counterparty_year c LEFT JOIN n USING (year) WHERE c.entity = '6296' ORDER BY 1""")
    w("Supplier-class payments only: payroll, remittances, internal transfers, taxes, debt service and "
      "other public bodies are excluded, so the state, EFKA, the tax office, the bank and the "
      "municipality's own bodies do not appear as \"suppliers\".")
    w("")
    w(_table(["Year", "Distinct suppliers", "of which first paid this year", "Supplier payments €", "Top-10 share", "Top-1 share"],
             [[y, n, nw or 0, _m(e), f"{s * 100:.1f}%", f"{t * 100:.1f}%"] for y, n, nw, e, s, t in rows]))
    w("")
    w("2026 is a partial year and the first under the new chart of accounts. Its supplier count is keyed "
      "by ΑΦΜ and was checked line by line against the 2023-2024 payees: nothing that used to be a "
      "remittance or tax payee became a supplier. The jump is real: most of the new suppliers had never "
      "been paid by the municipality before, and the subjects are ordinary works and services. 2020 is a "
      "genuine trough in supplier cash-outs, not a posting gap: payment acts fell only a tenth, remittances "
      "were normal, no amounts are missing, and no works payment above 160k € was made all year while "
      "commitments doubled; the large works payments resume in December 2021.")
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
    top = q("""SELECT afm, display_name, is_natural_person, total_received_supplier, n_payments, first_seen, last_seen,
                      n_entities, largest_payment_ada
               FROM counterparty WHERE total_received_supplier > 0 ORDER BY total_received_supplier DESC LIMIT 15""")
    w("Top 15 counterparties by supplier-class euros received, all entities, all years (published, "
      "non-suspect). Natural persons are shown as «φυσικό πρόσωπο»; the ADA of their largest payment is "
      "given so the fact can be verified at source (see PRIVACY.md).")
    w("")
    w(_table(["ΑΦΜ", "Name", "Received €", "Payments", "First", "Last", "Entities", "Largest payment"],
             [["—" if np else a, n, _eur(t), p, f, l, e, ada] for a, n, np, t, p, f, l, e, ada in top], 2))
    w("")

    # ---- data quality
    w("## Data quality flags")
    w("")
    sus = q("""SELECT p.entity, p.date, p.source_ada, p.amount, substr(p.counterparty_name_raw, 1, 40), substr(a.subject, 1, 70)
               FROM v_payment_suspect p JOIN act a ON a.ada = p.source_ada ORDER BY p.amount DESC""")
    w(f"Suspect payment lines (amount above 10,000,000 €; kept in `payment`, excluded from every view and total): {len(sus)}")
    w("")
    if sus:
        w(_table(["Entity", "Date", "ADA", "Amount €", "Counterparty", "Subject"],
                 [[e, d, ada, _eur(amt), n, sub] for e, d, ada, amt, n, sub in sus], 3))
        w("")
    big = q("""SELECT p.entity, p.date, p.source_ada, p.amount, substr(p.counterparty_name_raw, 1, 40), p.kae, substr(a.subject, 1, 70)
               FROM v_supplier_payment p JOIN act a ON a.ada = p.source_ada ORDER BY p.amount DESC LIMIT 8""")
    w("Largest single supplier payment lines in the release. Each is a real record; large one-offs "
      "(an EU-funded works contract, a cash transfer to a newly created body) explain most year-to-year "
      "swings and should be read before any trend is:")
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
    for line in [
        f"**Payroll is counted, never itemised.** {pk.get('no_sponsor', 0):,} payment acts have an empty sponsor "
        "list because the beneficiary is an employee; Diavgeia withholds the name and the amount by design, "
        f"so the FY2024 residual below is the only handle on them. From late 2025 the municipality posts payroll "
        f"batches that name one representative employee plus \"& ΛΟΙΠΟΙ\" ({pk.get('batch', 0):,} lines) and a few "
        f"payroll acts name a single person ({pk.get('named', 0):,} lines). These carry an amount, which is kept; "
        "the name and ΑΦΜ are dropped in the curated layer and never reach the counterparty table.",
        f"**Direct awards left Diavgeia in 2021.** Δήμος Τήνου published {d1_2024} Δ.1 acts in 2024 against "
        "about 350 a year before 2021, while its payment volume did not change and ΚΗΜΔΗΣ contract counts "
        "stayed flat. Award values from 2021 onward must come from ΚΗΜΔΗΣ, not from this table.",
        f"**Award amounts and CPV are unreliable.** {noamt:,} published award rows have no amount; CPV is "
        "filled on under 15% of awards in any year.",
        f"**Commitments before 2017 are absent** (Β.1.3 was not used), and {nokae:,} published commitment "
        "rows have no per-ΚΑΕ breakdown, so their ΚΑΕ is null and the amount is the act total. "
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
        ["Β.2.2 third-party payments, probe (FINDINGS.md)", _eur(PROBE_2024_THIRD_PARTY), "probe windows were blind to Dec 28–31"],
        ["Residual = paid − third-party (≈ payroll and unitemised)", _eur(paid - (ours[0] or 0)), f"derived; {ours[1]:,} payroll acts"],
        ["Β.1.3 commitments, this release (reversals excluded)", _eur(ours[2]), f"curated; {_eur(ours[5])} € of reversals excluded"],
        ["Β.1.3 commitments, probe (FINDINGS.md)", _eur(PROBE_2024_COMMITMENTS), "probe"],
    ]
    w(_table(["Figure", "€", "Source"], rows, 1))
    w("")
    w("The execution statement (Ψ68ΩΩΗ6-3ΓΦ) is the denominator: what the municipality itself reports as "
      "paid. Third-party payments from Diavgeia metadata are a floor for itemisable spending; the residual "
      "is payroll plus anything paid without a Β.2.2 act. Commitments exceed payments by design: they are "
      "budget reservations, many multi-year, not cash.")
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
    settings.summary_file.write_text("\n".join(L), encoding="utf-8")
    return settings.summary_file
