# API Findings — verified by probe, 2026-09-20

## CRITICAL: silently ignored parameters
Diavgeia returns HTTP 200 and **drops parameters it does not understand**.
Three confirmed: `q=` (free text), `giverAFM=`/`afm=`/`receiverAFM=`, and any
Lucene syntax in `q`. All return the unfiltered corpus (~2.96M acts).

**RULE: every call must compare `info.query` against what was requested.**
A result that doesn't name your filter in the echoed query is not filtered.

## Diavgeia
- Base: `https://diavgeia.gov.gr/opendata` — keyless, `.json` suffix or Accept header.
- `org=<uid>` works. It is the ONLY reliable filter besides dates and `type=`.
- **`issueDate` range is clamped to exactly `from + 180 days`.** Wider requests are
  silently truncated. Verified: 2011-01-01 → 2011-06-30; 2024-01-01 → 2024-06-29
  (leap year). It is 180 calendar days, not "six months". Backfill walks 150-day
  windows and the echo guard (`tinos doctor`) proves the clamp is detected.
- **Date bounds are INCLUSIVE at Greek local midnight, and `issueDate` storage
  changed convention in 2014.** The echo shows `TO DT(<to>T00:00:00+03:00)`.
  Acts up to early 2014 store `issueDate` as local midnight (21:00/22:00 UTC of
  the previous day); from mid-2014 onward it is UTC midnight. So an act dated ON
  the `to` day is included only under the old convention. Consequences, verified
  on the full 76,785-act corpus (2026-09-20):
  - Attribute year/date in `Europe/Athens`, never UTC (6 acts change year).
  - The ingester requests `end + 1 day` and walks 150-day windows whose next
    `from` equals the previous `to`. Pre-2014 acts on a seam day appear in both
    windows; they are byte-identical and deduped by ADA (`dup` in the ingest log,
    8 windows, 154 acts, all 2011-2014). Every window reconciled exactly:
    `total == new + unchanged + dup` in all 291 windows.
  - Probe3 section E (the ~71,650 expectation) UNDERCOUNTS by 4,916 acts (6.9%)
    because its H2 window Jul 1..Dec 31 was clamped to Dec 28 and its H1 window
    lost Jun 30 (Jun 29 in leap years). Removing exactly those blind days from
    our counts reproduces the probe table cell-for-cell with zero residual.
    Dec 28-31 alone holds 4,584 acts, 3,171 of them Β.1.3 year-end commitments.
- `from_date`/`to_date` filter `submissionTimestamp` (works), but `issueDate` still
  defaults to last 6 months alongside it. Incremental sync = walk all issue windows
  with a submission filter (~32 calls/entity/run).
- Max `size` = 500. Paging via `page=`.
- `status=all` reveals withdrawn acts. Three values seen in the corpus: `PUBLISHED`
  76,564 · `REVOKED` 191 · `PENDING_REVOCATION` 30. The echoed query drops its
  `status:"Αναρτημένη"` clause when `status=all` is honoured; the guard checks that.
  Ingester default is `status=all`. Revocations skew early (2011-2015 for 6296,
  2013-2014 for the school committees) and by type: 2.4.7.1 53, Δ.1 46, Β.2.2 23.
- Version log: `/opendata/decisions/{ADA}/versionlog.json`. Retroactive edits are real.
- Documents: `https://diavgeia.gov.gr/doc/{ADA}`. **Born-digital text, 2011-2025, no scans found.**

### Where the money is (structured, no OCR needed)
| Type | Meaning | Money field |
|---|---|---|
| Β.1.3 | ΑΝΑΛΗΨΗ ΥΠΟΧΡΕΩΣΗΣ | `amountWithVAT`, `amountWithKae[]` (per-ΚΑΕ + remaining credit) |
| Β.2.1 | ΕΓΚΡΙΣΗ ΔΑΠΑΝΗΣ | `sponsor[].expenseAmount`, `sponsor[].sponsorAFMName` |
| Β.2.2 | ΟΡΙΣΤΙΚΟΠΟΙΗΣΗ ΠΛΗΡΩΜΗΣ | `sponsor[].expenseAmount` + `.kae`, `relatedEkgrisiDapanis` |
| Δ.1 / Δ.2.2 | ΑΝΑΘΕΣΗ / ΚΑΤΑΚΥΡΩΣΗ | `awardAmount`, `person[].afm`, `cpv` |
| Β.1.1 | ΕΓΚΡΙΣΗ ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ | no amount; the figures are in the PDF |
| Β.3 | ΙΣΟΛΟΓΙΣΜΟΣ/ΑΠΟΛΟΓΙΣΜΟΣ | includes MONTHLY EXECUTION STATEMENTS |

### Known gaps
- **Payroll has `sponsor: []` by design** (beneficiary is an employee = personal data).
  693 of 1,644 Β.2.2 acts in 2024. Do not attempt to itemise. Not a bug.
- **Direct awards are NOT in Diavgeia.** Δ.1 = 13 acts in all of 2024. Use ΚΗΜΔΗΣ.
- `2.4.7.1 ΛΟΙΠΕΣ ΑΤΟΜΙΚΕΣ ΠΡΑΞΕΙΣ` is a junk drawer (1,193 acts in 2024).
  Two taxonomies (`2.4.x` and `Α/Β/Γ/Δ`) run simultaneously. Type alone cannot classify.

### Corpus snapshot, full backfill 2026-09-20
76,785 acts, 11 entities, 2010-2026, 304 MB raw JSON + 85 MB page snapshots,
291 windows / 379 calls, 0 echo mismatches. Type mix: Β.2.2 39.6% · 2.4.7.1 20.2% ·
Β.1.3 19.6% · Δ.1 10.6% · Α.2 3.0% · Β.3 1.2% · everything else < 1.2% each.
DuckDB `read_json_auto` over the act files exhausts memory (schema inference across
76k nested files); pass explicit `columns=` or scan with plain `json`.

## ΚΗΜΔΗΣ — keyless, CC BY 4.0
- Base: `https://cerpp.eprocurement.gov.gr/khmdhs-opendata`
- OpenAPI: `/v3/api-docs` · Swagger UI: `/swagger-ui/index.html`
- **POST** with JSON body (GET times out). `?page=N`. Response: `{total, pages, content[]}`.
- **Uses the SAME org uid as Diavgeia: `6296`.** ΑΦΜ 404s.
- Endpoints: `/request` `/notice` `/auction` `/contract` `/payment` `/pde`
  `/adamChain/{referenceNumber}` + `/{type}/attachment/{referenceNumber}`
- **`/adamChain/` returns the pre-built act chain** — use instead of reconstructing.
- Body fields: `organizations[]`, `cpvItems[]`, `signer`, `contractType`,
  `dateFrom`/`dateTo`, `totalCostFrom`/`totalCostTo`, `title`, `isInitial`, `isApproved`.
- Volume: 445 `/request` records for org 6296 in 2024.

## Budget reconciliation, FY2024 (Δήμος Τήνου)
| Figure | € | Source |
|---|---|---|
| Voted budget (balanced: revenue = expenditure) | 22,251,724.35 | ΨΞΕΟΩΗ6-2ΥΑ |
| Revised budget by December | 23,630,861.94 | Ψ68ΩΩΗ6-3ΓΦ |
| Ενταλματοποιηθέντα | 9,055,399.10 | Ψ68ΩΩΗ6-3ΓΦ |
| **Πληρωθέντα** | **8,877,120.61** | Ψ68ΩΩΗ6-3ΓΦ |
| Β.2.2 third-party payments (API) | 6,031,795.60 | Diavgeia metadata |
| Residual = payroll | 2,845,325.01 | derived |
| Β.1.3 commitments | 20,000,913.15 | Diavgeia metadata |

Expenditure classes: 6 ΕΞΟΔΑ ΧΡΗΣΗΣ 11,031,542.99 · 7 ΕΠΕΝΔΥΣΕΙΣ 7,232,281.72 ·
8 ΠΡΟΒΛΕΨΕΙΣ 3,954,381.31 · 9 ΑΠΟΘΕΜΑΤΙΚΟ 33,518.33.
ΠΡΟΒΛΕΨΕΙΣ is notional — that's why execution looks like ~37% of budget.

## Monthly execution statements — the denominator
Published in Diavgeia as type `Β.3`, subject `ΔΗΜΟΣΙΕΥΣΗ ΣΤΟΙΧΕΙΩΝ ΕΚΤΕΛΕΣΗΣ ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ`.
`pdftotext -layout` gives a clean fixed-width table:
- ΕΣΟΔΑ: ΚΑΕ | name | Προϋπολογισθέντα | Βεβαιωθέντα | Εισπραχθέντα
- ΕΞΟΔΑ: ΚΑΕ | name | Προϋπολογισθέντα | Ενταλματοποιηθέντα | Πληρωθέντα
Parser validated: 247 rows, expenditure sum == document's own ΣΥΝΟΛΟ ΕΞΟΔΩΝ exactly.

**`issueDate` != reporting period.** May and June 2025 were both published 2025-07-07.
Always parse `Περίοδος:` from the PDF.

## Municipality web presence
- `dimostinou.gr` — WordPress, **wp-json fully open**.
  posts=1319 (from 2022-08-22), pages=44, media=3439, lsvr_document=8, lsvr_notice=5.
  Category 166 = «Βίντεο Συνεδριάσεων» (46 posts, all with YouTube embeds).
- `dimostinou.eu` — legacy Blogger, **4,635 posts**, covers ~2011-2022.
  **HTTP only** (TLS broken). Feed: `/feeds/posts/default?alt=json&max-results=N&start-index=M`
- YouTube: **@dimostinouwebtv** — resolved via oEmbed from embed IDs.
  46 sessions from 2023-12-20 onward.

## Tooling notes
- `mawk` (Ubuntu default) lacks `{n}` interval regex — **use `gawk`**.
- Internet Archive was offline on probe day; retry the Wayback CDX sweep.
