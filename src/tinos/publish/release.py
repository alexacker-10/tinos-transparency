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
  the same payments counted by two sources.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from tinos.config import Settings

TABLES = ("act", "payment", "commitment", "award", "counterparty", "entity", "budget_line")

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
