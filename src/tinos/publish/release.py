"""Build ``releases/tinos.duckdb`` from the curated Parquet files.

The database is a self-contained copy (tables, not external references) so
it can be shipped on its own. Views encode the analysis rules so that a
casual reader gets the right numbers by default:

- ``v_*`` views filter to PUBLISHED acts.
- ``v_payment`` excludes payroll rows and suspect amounts; ``v_payroll`` is
  only payroll rows; ``v_supplier_payment`` further drops ΚΑΕ-82 remittances.
- ``v_supplier_payment`` is ``payee_class = 'supplier'`` only; ``v_internal_transfer``
  is money moving inside the entity family; ``v_payee_class_year`` shows the
  euro effect of every class.
- ``v_commitment`` excludes reversals; ``v_commitment_reversal`` is only them.
- ``v_yearly`` reports the three money measures side by side but in
  separate columns. They are different measures of the same spending and
  must never be added together.
- ``v_budget_year`` is the municipality's own year-end execution statement
  per ΚΑΕ group (one statement per entity and year, the latest published);
  ``v_payment_coverage`` sets its paid column against the Β.2.2 lines that
  carry an amount, per year and ΚΑΕ group. Coverage, not a sum: the two are
  the same payments counted by two sources. ``v_kae_reconciliation`` does the
  same per 4-digit ΚΑΕ; a positive ``excess_in_diavgeia`` marks a wrong or
  double-posted line.
- ``v_payment_combined`` is every Β.2.2 line with an amount plus every ΚΗΜΔΗΣ
  payment whose payee has no Β.2.2 line within 60 days (since 2019 most
  supplier payments are published only there, FINDINGS F6). A floor: a ΚΗΜΔΗΣ
  payment to a payee Diavgeia also shows nearby is assumed to be already in.
  ``v_supplier_year_combined`` is the supplier series on it (F3).
- ``v_grant_line`` is every amount another body's decision gives Δήμος Τήνου
  that was validated against the document (column totals, a stated amount, or
  words and figures), published decisions only. ``v_grant_year`` sums it per
  budget year, grantor (the Interior Ministry, the Region), category and
  family; ``v_revenue_grant_year`` is the revenue
  side of the year-end statements in the same categories; and
  ``v_grant_reconciliation`` sets them side by side, every grantor together
  (a revenue line does not say who paid). Allocations decided and revenue
  booked are two views of the same transfers: compare, never add.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from tinos.config import Settings

TABLES = ("act", "payment", "commitment", "award", "counterparty", "entity", "budget_line",
          "procurement", "procurement_party", "grant_decision", "grant_line")

VIEWS = {
    "v_act": "SELECT * FROM act",
    "v_payment": "SELECT * FROM payment WHERE act_status = 'PUBLISHED' AND NOT is_payroll AND NOT amount_suspect",
    "v_supplier_payment": "SELECT * FROM payment WHERE act_status = 'PUBLISHED' AND NOT amount_suspect AND payee_class = 'supplier'",
    "v_internal_transfer": "SELECT * FROM payment WHERE act_status = 'PUBLISHED' AND NOT amount_suspect AND payee_class = 'internal_transfer'",
    "v_payee_class_year": """
        SELECT entity, year, payee_class, count(*) AS n_lines, count(DISTINCT source_ada) AS n_acts, sum(amount) AS eur
        FROM payment WHERE act_status = 'PUBLISHED' AND NOT amount_suspect GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
    """,
    "v_payment_suspect": "SELECT * FROM payment WHERE amount_suspect",
    "v_payroll": "SELECT * FROM payment WHERE act_status = 'PUBLISHED' AND is_payroll",
    "v_commitment": "SELECT * FROM commitment WHERE act_status = 'PUBLISHED' AND NOT is_reversal",
    "v_commitment_reversal": "SELECT * FROM commitment WHERE act_status = 'PUBLISHED' AND is_reversal",
    "v_award": "SELECT * FROM award WHERE act_status = 'PUBLISHED'",
    "v_revoked": "SELECT * FROM act WHERE status IN ('REVOKED', 'PENDING_REVOCATION')",
    # Three separate measures. Do not add the euro columns together.
    "v_yearly": """
        WITH a AS (
            SELECT entity, year, count(*) AS n_acts FROM act GROUP BY 1, 2),
        p AS (
            SELECT entity, year,
                   count(DISTINCT CASE WHEN NOT is_payroll AND NOT amount_suspect THEN source_ada END) AS n_payment_acts,
                   sum(CASE WHEN NOT is_payroll AND NOT amount_suspect THEN amount END) AS payment_eur,
                   sum(CASE WHEN NOT is_payroll AND NOT amount_suspect AND is_remittance THEN amount END) AS remittance_eur,
                   sum(CASE WHEN NOT amount_suspect AND payee_class = 'supplier' THEN amount END) AS supplier_eur,
                   sum(CASE WHEN NOT amount_suspect AND payee_class = 'internal_transfer' THEN amount END) AS internal_transfer_eur,
                   sum(CASE WHEN NOT amount_suspect AND payee_class IN ('tax', 'debt_service', 'other_public_body') THEN amount END) AS other_nonsupplier_eur,
                   count(DISTINCT CASE WHEN is_payroll THEN source_ada END) AS n_payroll_acts,
                   sum(CASE WHEN is_payroll THEN amount END) AS payroll_eur,
                   count(DISTINCT CASE WHEN NOT amount_suspect AND payee_class = 'supplier' THEN counterparty_afm END) AS n_suppliers,
                   sum(CASE WHEN amount_suspect THEN 1 ELSE 0 END) AS n_suspect_lines
            FROM payment WHERE act_status = 'PUBLISHED' GROUP BY 1, 2),
        c AS (
            SELECT entity, year,
                   count(DISTINCT CASE WHEN NOT is_reversal THEN source_ada END) AS n_commitment_acts,
                   sum(CASE WHEN NOT is_reversal THEN amount END) AS commitment_eur,
                   sum(CASE WHEN is_reversal THEN amount END) AS reversal_eur
            FROM commitment WHERE act_status = 'PUBLISHED' GROUP BY 1, 2),
        w AS (
            SELECT entity, year, count(DISTINCT source_ada) AS n_award_acts, sum(amount) AS award_eur
            FROM (SELECT DISTINCT source_ada, entity, year, amount FROM award WHERE act_status = 'PUBLISHED')
            GROUP BY 1, 2)
        SELECT a.entity, e.name AS entity_name, a.year, a.n_acts,
               p.n_payment_acts, p.payment_eur, p.remittance_eur, p.supplier_eur, p.internal_transfer_eur,
               p.other_nonsupplier_eur, p.n_payroll_acts, p.payroll_eur,
               p.n_suppliers, p.n_suspect_lines,
               c.n_commitment_acts, c.commitment_eur, c.reversal_eur, w.n_award_acts, w.award_eur
        FROM a LEFT JOIN p USING (entity, year) LEFT JOIN c USING (entity, year)
               LEFT JOIN w USING (entity, year) LEFT JOIN entity e ON e.uid = a.entity
        ORDER BY 1, 3
    """,
    "v_counterparty_year": """
        WITH t AS (
            SELECT entity, year, counterparty_afm, sum(amount) AS eur
            FROM payment WHERE act_status = 'PUBLISHED' AND NOT amount_suspect
                  AND payee_class = 'supplier' AND counterparty_afm IS NOT NULL
            GROUP BY 1, 2, 3),
        r AS (
            SELECT *, row_number() OVER (PARTITION BY entity, year ORDER BY eur DESC) AS rk,
                   sum(eur) OVER (PARTITION BY entity, year) AS total FROM t)
        SELECT entity, year, count(*) AS n_suppliers, max(total) AS supplier_eur,
               sum(CASE WHEN rk <= 10 THEN eur END) / max(total) AS top10_share,
               max(CASE WHEN rk = 1 THEN eur END) / max(total) AS top1_share
        FROM r GROUP BY 1, 2 ORDER BY 1, 2
    """,
    "v_type_year": "SELECT year, type, status, count(*) AS n FROM act GROUP BY 1, 2, 3 ORDER BY 1, 2, 3",
    "v_budget_year": """
        WITH s AS (
            SELECT DISTINCT entity, statement_ada, period_end, statement_date FROM budget_line WHERE is_year_end),
        pick AS (
            SELECT entity, statement_ada FROM s
            QUALIFY row_number() OVER (PARTITION BY entity, period_end ORDER BY statement_date DESC, statement_ada) = 1)
        SELECT b.entity, b.period_year AS year, b.side, b.kae_group, any_value(b.statement_ada) AS statement_ada,
               sum(b.budgeted) AS budgeted, sum(b.assessed_or_warranted) AS assessed_or_warranted,
               sum(b.collected_or_paid) AS collected_or_paid
        FROM budget_line b JOIN pick USING (entity, statement_ada)
        GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3, 4
    """,
    # Same payments, two sources: the statement (all paid) and Β.2.2 lines with an amount.
    "v_payment_coverage": r"""
        WITH stmt AS (
            SELECT entity, year, kae_group, collected_or_paid AS paid_per_statement, statement_ada
            FROM v_budget_year WHERE side = 'spending'),
        pub AS (
            SELECT entity, year,
                   left(coalesce(nullif(regexp_extract(kae, '^\d{2}[.\-](\d{4})', 1), ''),
                                 regexp_extract(kae, '^(\d{4})', 1)), 2) AS kae_group,
                   sum(amount) AS paid_in_diavgeia
            FROM payment WHERE act_status = 'PUBLISHED' AND NOT amount_suspect AND amount IS NOT NULL
            GROUP BY 1, 2, 3)
        SELECT stmt.entity, stmt.year, stmt.kae_group, stmt.paid_per_statement,
               coalesce(pub.paid_in_diavgeia, 0) AS paid_in_diavgeia,
               coalesce(pub.paid_in_diavgeia, 0) / nullif(stmt.paid_per_statement, 0) AS coverage,
               stmt.statement_ada
        FROM stmt LEFT JOIN pub USING (entity, year, kae_group) ORDER BY 1, 2, 3
    """,
    # The systematic check for wrong amounts: a 4-digit ΚΑΕ where Diavgeia lines exceed what the
    # statement says was paid holds a line entered wrong (often x100) or posted twice (FINDINGS F7).
    "v_kae_reconciliation": r"""
        WITH years AS (SELECT DISTINCT entity, year, statement_ada FROM v_budget_year),
        stmt AS (
            SELECT y.entity, y.year, b.kae, sum(b.collected_or_paid) AS paid_per_statement
            FROM budget_line b JOIN years y ON y.statement_ada = b.statement_ada
            WHERE b.side = 'spending' GROUP BY 1, 2, 3),
        pub AS (
            SELECT p.entity, p.year,
                   coalesce(nullif(regexp_extract(p.kae, '^\d{2}[.\-](\d{4})', 1), ''),
                            regexp_extract(p.kae, '^(\d{4})', 1)) AS kae,
                   sum(p.amount) AS paid_in_diavgeia, arg_max(p.source_ada, p.amount) AS largest_ada,
                   max(p.amount) AS largest_amount
            FROM payment p JOIN (SELECT DISTINCT entity, year FROM years) y USING (entity, year)
            WHERE p.act_status = 'PUBLISHED' AND NOT p.amount_suspect AND p.amount IS NOT NULL
            GROUP BY 1, 2, 3)
        SELECT coalesce(stmt.entity, pub.entity) AS entity, coalesce(stmt.year, pub.year) AS year,
               coalesce(stmt.kae, pub.kae) AS kae, coalesce(stmt.paid_per_statement, 0) AS paid_per_statement,
               coalesce(pub.paid_in_diavgeia, 0) AS paid_in_diavgeia,
               coalesce(pub.paid_in_diavgeia, 0) - coalesce(stmt.paid_per_statement, 0) AS excess_in_diavgeia,
               pub.largest_ada, pub.largest_amount
        FROM stmt FULL JOIN pub ON stmt.entity = pub.entity AND stmt.year = pub.year AND stmt.kae = pub.kae
        ORDER BY 1, 2, 3
    """,
    "v_procurement": "SELECT * FROM procurement WHERE NOT cancelled",
    "v_grant_line": """
        SELECT l.*, d.subject, d.decision_type, d.issuer_label
        FROM grant_line l JOIN grant_decision d USING (ada)
        WHERE l.status = 'PUBLISHED' AND l.validation IS NOT NULL AND l.amount IS NOT NULL AND l.duplicate_of IS NULL
    """,
    "v_grant_year": """
        SELECT budget_year AS year, grantor, recipient_entity, category, family, count(DISTINCT ada) AS n_decisions,
               count(*) AS n_lines, sum(amount) AS allocated, sum(net_paid) AS net_paid
        FROM v_grant_line WHERE category IS NOT NULL GROUP BY 1, 2, 3, 4, 5 ORDER BY 1, 2, 3, 4, 5
    """,
    "v_revenue_grant_year": """
        WITH s AS (
            SELECT DISTINCT entity, statement_ada, period_end, statement_date FROM budget_line WHERE is_year_end),
        pick AS (
            SELECT entity, statement_ada FROM s
            QUALIFY row_number() OVER (PARTITION BY entity, period_end ORDER BY statement_date DESC, statement_ada) = 1)
        SELECT b.entity, b.period_year AS year, b.grant_category AS category, any_value(b.statement_ada) AS statement_ada,
               string_agg(b.kae, ', ' ORDER BY b.kae) AS kae_lines, sum(b.budgeted) AS budgeted,
               sum(b.assessed_or_warranted) AS assessed, sum(b.collected_or_paid) AS collected
        FROM budget_line b JOIN pick USING (entity, statement_ada)
        WHERE b.side = 'revenue' AND b.grant_category IS NOT NULL
        GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
    """,
    # Monthly statements: what each line collected (or paid) in the month, from the cumulative figures. ``months`` > 1
    # when the previous month's statement is missing: the change then spans that many months.
    "v_budget_month": """
        WITH m AS (
            SELECT entity, side, period_year AS year, period_month AS month, kae, any_value(description) AS description,
                   any_value(statement_ada) AS statement_ada, sum(assessed_or_warranted) AS assessed_to_date,
                   sum(collected_or_paid) AS collected_to_date
            FROM budget_line GROUP BY 1, 2, 3, 4, 5)
        SELECT *, collected_to_date - coalesce(lag(collected_to_date) OVER w, 0) AS collected_in_period,
               month - coalesce(lag(month) OVER w, 0) AS months
        FROM m WINDOW w AS (PARTITION BY entity, side, year, kae ORDER BY month)
        ORDER BY entity, side, year, kae, month
    """,
    "v_grant_reconciliation": """
        WITH g AS (
            SELECT year, category, sum(n_decisions) AS n_decisions, sum(allocated) AS allocated, sum(net_paid) AS net_paid
            FROM v_grant_year WHERE recipient_entity = '6296' GROUP BY 1, 2),
        r AS (SELECT year, category, kae_lines, assessed, collected, statement_ada FROM v_revenue_grant_year WHERE entity = '6296')
        SELECT coalesce(g.year, r.year) AS year, coalesce(g.category, r.category) AS category,
               coalesce(g.n_decisions, 0) AS n_decisions, coalesce(g.allocated, 0) AS allocated,
               r.assessed, r.collected, r.kae_lines, r.statement_ada,
               coalesce(g.allocated, 0) - coalesce(r.assessed, 0) AS allocated_minus_assessed,
               -- what was paid after the payer's own withholdings, where the document states it (the Region's payment
               -- orders: the municipality books this net amount)
               g.net_paid, coalesce(g.net_paid, 0) - coalesce(r.assessed, 0) AS net_minus_assessed
        FROM g FULL JOIN r ON g.year = r.year AND g.category = r.category
        ORDER BY 1, 2
    """,
    "v_direct_award_year": """
        SELECT entity, year, count(*) AS n_awards, sum(total_cost_without_vat) AS value_without_vat
        FROM procurement WHERE endpoint = 'auction' AND NOT cancelled AND procedure_type LIKE 'Απευθείας%'
        GROUP BY 1, 2 ORDER BY 1, 2
    """,
    "v_payment_combined": """
        WITH d AS (
            SELECT entity, date, year, counterparty_afm AS afm, counterparty_display AS display_name, payee_class,
                   amount, 'diavgeia' AS source, source_ada AS ref
            FROM payment
            WHERE act_status = 'PUBLISHED' AND NOT amount_suspect AND NOT is_payroll AND amount IS NOT NULL),
        k AS (
            SELECT p.entity, p.submission_date AS date, p.year, p.afm, p.display_name,
                   CASE WHEN p.afm IN (SELECT afm FROM entity WHERE afm IS NOT NULL)
                        THEN 'internal_transfer' ELSE 'supplier' END AS payee_class,
                   p.amount_with_vat AS amount, 'khmdhs' AS source, p.ref
            FROM procurement_party p
            WHERE p.role = 'payee' AND NOT p.cancelled AND p.amount_with_vat IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM d WHERE d.entity = p.entity AND d.afm = p.afm
                    AND d.date BETWEEN p.submission_date - INTERVAL 60 DAY AND p.submission_date + INTERVAL 60 DAY))
        SELECT * FROM d UNION ALL SELECT * FROM k
    """,
    "v_supplier_year_combined": """
        WITH t AS (
            SELECT entity, year, afm, sum(amount) AS eur, bool_and(source = 'khmdhs') AS only_khmdhs
            FROM v_payment_combined WHERE payee_class = 'supplier' AND afm IS NOT NULL GROUP BY 1, 2, 3),
        r AS (
            SELECT *, row_number() OVER (PARTITION BY entity, year ORDER BY eur DESC) AS rk,
                   sum(eur) OVER (PARTITION BY entity, year) AS total FROM t)
        SELECT entity, year, count(*) AS n_suppliers, count(*) FILTER (WHERE only_khmdhs) AS n_only_khmdhs,
               max(total) AS supplier_eur,
               sum(CASE WHEN rk <= 10 THEN eur END) / max(total) AS top10_share,
               max(CASE WHEN rk = 1 THEN eur END) / max(total) AS top1_share
        FROM r GROUP BY 1, 2 ORDER BY 1, 2
    """,
}


def build_release(settings: Settings) -> tuple[Path, dict[str, int]]:
    settings.releases_dir.mkdir(parents=True, exist_ok=True)
    db_path = settings.releases_dir / "tinos.duckdb"
    # Rebuildable output, regenerated from Parquet on every run.
    for p in (db_path, db_path.with_suffix(".duckdb.wal")):
        if p.exists():
            p.unlink()
    manifest = json.loads((settings.curated_dir / "build_manifest.json").read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    con = duckdb.connect(str(db_path))
    try:
        for t in TABLES:
            src = settings.curated_dir / f"{t}.parquet"
            con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_parquet('{src.as_posix()}')")
            counts[t] = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        con.execute("CREATE TABLE meta (key VARCHAR, value VARCHAR)")
        for k, v in manifest.items():
            con.execute("INSERT INTO meta VALUES (?, ?)", [k, json.dumps(v, ensure_ascii=False)])
        for name, sql in VIEWS.items():
            con.execute(f"CREATE VIEW {name} AS {sql}")
        con.execute("CHECKPOINT")
    finally:
        con.close()
    return db_path, counts
