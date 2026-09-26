# Tinos Transparency — project brief

Reconstructed 2026-09-25 from CLAUDE.md, FINDINGS.md, SOURCES.md, LIMITATIONS.md, PRIVACY.md and the `curated.py` docstring. The original PROMPT.md was never committed. Edit where this misstates the intent.

## Goal

Rebuild, from public records only, what the municipality of Tinos (Δήμος Τήνου, Diavgeia org 6296) and its ten subsidiary bodies spend and decide, 2010 to today, in a form that is searchable, reproducible and traceable to the source document byte for byte. Publish figures with their definitions. Publish no inference about anyone's conduct.

Audience: residents, local journalists, councillors. Everything published must be defensible in a complaint to the Hellenic DPA and checkable at the source register by anyone.

## Sources

- Diavgeia (`diavgeia.gov.gr/opendata`): decisions of all 11 entities in `entities.yaml`. Primary source for payments (Β.2.2), commitments (Β.1.3), awards to 2020 (Δ.1/Δ.2.2), budgets (Β.1.1) and monthly execution statements (Β.3).
- ΚΗΜΔΗΣ (`cerpp.eprocurement.gov.gr/khmdhs-opendata`): procurement register, same org uid, CC BY 4.0. Primary source for awards from 2021; contract rows carry `diavgeiaADA`.
- Diavgeia full-text search (`opendata.diavgeia.gov.gr/luminapi`): other bodies' decisions about Tinos, i.e. money given to it (grants and allocations), read from the decisions' PDFs. No query echo: proved by counts. Hits about private people are redacted at ingestion (PRIVACY.md Q7).
- Council video: YouTube `@dimostinouwebtv`, 205 sessions / 472 h.
- Municipal sites: `dimostinou.gr` (WordPress, wp-json open), `dimostinou.eu` (legacy Blogger, HTTP only).
- Local media (tinosnews.gr, tinostoday.gr): link and cite only.

## Data model

Layers, each derived from the one below and never hand-edited:

1. `data/raw/` — exact bytes fetched, append-only, content-hashed, with `manifests/ingest_log.jsonl` recording every call and its echoed query.
2. `data/curated/*.parquet` — pure functions of raw. Tables: `act`, `payment` (one row per Β.2.2 sponsor line), `commitment` (per ΚΑΕ line), `award` (per awardee), `counterparty` (per ΑΦΜ), `entity`, `budget_line` (execution statements), `procurement`, `procurement_party` (ΚΗΜΔΗΣ), `grant_decision`, `grant_line` (money given to Tinos, validated against each PDF). Every row carries `source_ada`, `source_sha256`, `derived_at`, `pipeline_version`.
3. `releases/tinos.duckdb` — the curated tables plus `v_*` views that apply status, suspect and reversal filters.
4. `SUMMARY.md` and the site — generated only; nothing typed by hand except reference rows that cite an ADA.
5. `data/manual/` — the only human input: documented corrections (`amount_review.yaml`), each citing the document and its hash.

Payments, commitments and awards are three measures of the same euro and are shown side by side, never added.

## Invariants

- Every Diavgeia response is accepted only if `info.query` echoes the requested organisation, both date bounds, status clause and page. The API drops unknown parameters and clamps date ranges silently, always HTTP 200.
- `data/raw` is append-only. Re-fetches that differ are stored as new versions, never overwritten.
- Every published figure traces to a stored document hash.
- Never sum across the three measure tables.
- Payroll beneficiaries are absent by design; do not attempt recovery.
- Counterparties merge on identical ΑΦΜ only; never on name similarity.
- The source is never corrected. Errors are flagged and excluded, and the flag's reason is recorded.
- Dates are Greek civil dates in Europe/Athens.
- Be polite to public endpoints: fixed delay, identifying User-Agent.
- Classification rules are deterministic, documented in the `curated.py` docstring, and applied by code only.

## Privacy rules (see PRIVACY.md for reasoning and open questions)

- Legal entities receiving public money: named.
- Public office holders acting in office: named.
- Natural persons, including sole traders: never in ranked or aggregated tables; shown as «φυσικό πρόσωπο» with the ADA of a source decision. Raw name and ΑΦΜ stay in the curated layer only.
- Employees: never itemised, even where the source leaks a name.
- Welfare/hardship beneficiaries and private citizens in council video: undecided; do not publish until decided.
- Never enrich a person with data from outside the public record.

## Working method

- Claude Code builds; the claude.ai session reviews numbers and design.
- Findings go in FINDINGS.md with the query that produced them and the release digest. Limitations go in LIMITATIONS.md in plain language.
- Every phase ends with `tinos build && tinos release && tinos summary` and a commit whose message names what changed in the numbers.
