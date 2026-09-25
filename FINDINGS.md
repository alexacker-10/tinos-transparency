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

### Metadata hazards found while building the curated layer (2026-09-20)
- **Reversals are positive.** Year-end commitment reversals (`Ανατροπές`, `Ανάκληση`)
  are posted as Β.1.3 with a positive `amountWithVAT`; `recalledExpenseDecision` is
  unreliable (2023: 9.05M of 28.1M "commitments" were reversals). From 2025 some
  reversals carry negative amounts instead. Filter on flag OR subject.
- **One suspect line.** ΨΩΚΙΟΚ6Δ-ΘΟ6 (53404, 2018) carries a withholdings statement of
  82,310,012.00 EUR, ~400x the body's annual payments. Data-entry error at source;
  kept, flagged `amount_suspect`, excluded from views.
- **Amounts can be entered in cents.** Ω25ΙΩΗ6-ΟΜΘ (6296, 2015) carries 281,880.00 EUR in
  the metadata; the PDF (payment order ΧΘ 600, sha256 872acd76…) says 2,818.80 (2,430.00
  net + 388.80 VAT) for gym equipment. Exactly x100. The 10M threshold cannot catch this
  class of error; verified cases go in `data/manual/amount_review.yaml` and are flagged
  `suspect_reason = document_mismatch`. Expect more; a systematic check (metadata
  amount vs. commitment amount vs. PDF) is future work.
- **Remittances dominate naive top-payee lists.** ΚΑΕ group 82 (αποδόσεις κρατήσεων)
  and "Κατάσταση Κρατήσεων" subjects are pass-through withholdings to the state,
  EFKA, IKA and pension funds: 3.6M of 6.7M municipal third-party payments in 2024.
- **New chart of accounts in 2026.** Δήμος Τήνου ΚΑΕ changed from `NN.NNNN[.NNNN]`
  (sometimes `NN-NNNN.NNNN`) to `NNN.NNNNNNN[.NNN]` on 2026-01-01. Groups seen, from
  subject sampling: 21 personnel, 22 supplies, 23 transfers and levies, 24 services,
  27 rents, 31 fixed assets, 45 contributions, **59 αποδόσεις (remittances)**; the old
  chart's 60 personnel / 63 taxes / 65 debt / 67 grants / 82 remittances map onto them
  only partly. Classification rules use both.
- **Payroll batches from late 2025.** Payroll Β.2.2 acts now carry a sponsor line naming
  one representative employee "& ΛΟΙΠΟΙ" with that person's ΑΦΜ (721 lines, 22 people,
  1.87M in 2026 to September). The curated layer keeps the amount and drops the person.
- **Pre-2017 Β.1.3 is not commitments.** Β4Β7ΩΗ6-Μ8Ω (2012) is the whole annual budget
  summary (13.77M) posted under Β.1.3. In 2017 reversals (2.31M) exceed posted
  commitments (0.12M): the record is incomplete, not small.
- `read_json_auto` in DuckDB over the 76k act files exhausts >10 GB; scan with plain
  `json` or pass explicit `columns=`.

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

## Budget reconciliation, FY2024 (Δήμος Τήνου), January to November

**Corrected 2026-09-25.** Ψ68ΩΩΗ6-3ΓΦ is the statement for «Περίοδος: Νοέμβριος 2024»
(signed 2024-12-10): its figures run to 30 November, not to the year end. The December
statement is 6ΝΠΘΩΗ6-Β64 (published 2025-01-10), not yet stored or parsed, so there is no
full-year paid figure. The earlier version of this table labelled the November figures "by
December", set them against Diavgeia figures for the whole year taken from probe3 windows
that were blind to 28-31 Dec (third-party payments 6,031,795.60; commitments 20,000,913.15,
which does not reproduce from the release), and called the difference, 2,845,325.01, payroll.
Like for like:

| Figure | € | Source |
|---|---|---|
| Voted budget (balanced: revenue = expenditure) | 22,251,724.35 | ΨΞΕΟΩΗ6-2ΥΑ |
| Revised budget at 30 Nov | 23,630,861.94 | Ψ68ΩΩΗ6-3ΓΦ |
| Ενταλματοποιηθέντα, Jan-Nov | 9,055,399.10 | Ψ68ΩΩΗ6-3ΓΦ |
| **Πληρωθέντα, Jan-Nov** | **8,877,120.61** | Ψ68ΩΩΗ6-3ΓΦ |
| of which personnel costs, ΚΑΕ 60xx (17 rows) | 2,523,642.33 | Ψ68ΩΩΗ6-3ΓΦ |
| of which remittances, ΚΑΕ 82xx | 1,145,923.76 | Ψ68ΩΩΗ6-3ΓΦ |
| Β.2.2 third-party payments, Jan-Nov | 5,757,765.58 | release: 950 lines, 862 acts |
| of which under ΚΑΕ 60 | 190.00 | release; the 651 payroll acts carry no amount |
| of which under ΚΑΕ 82 | 3,174,526.80 | release; includes 6Ξ6ΖΩΗ6-26Β, below |
| Β.2.2 third-party payments, full year | 6,667,197.72 | release: 1,074 lines, 967 acts |
| Β.1.3 commitments, full year, reversals excluded | 19,824,694.80 | release; 8,486,555.56 of reversals excluded |

`SELECT sum(amount) FROM v_payment WHERE entity='6296' AND date BETWEEN '2024-01-01' AND '2024-11-30'`
(release source digest `d29344da…`). Statement rows are the probe's parse of the PDF
(`probe-out/exec2412.*`, PDF sha256 `78b0de36…`): 149 expenditure rows that sum exactly to
the document's ΣΥΝΟΛΟ ΕΞΟΔΩΝ. The PDF is not yet in `data/raw`.

**Paid minus third-party payments is not a payroll estimate.** Group by group the two
sources disagree in both directions: personnel costs (60) are 2,523,642.33 in the statement
and 190.00 in Β.2.2; the other expenditure groups are under-itemised in Β.2.2 by 2,624,505.74
net (62, 61, 66, 81, 71, 64 and 73 each by 0.15-0.62M); remittances (82) are over-itemised
by 2,028,603.04. The differences net to 3,119,355.03. Read payroll from the statement's
60xx rows, not from a residual.

**Suspected amount error: 6Ξ6ΖΩΗ6-26Β.** The February 2024 withholdings statement («Κατάσταση
Κρατήσεων») carries 2,023,213.00 on its 00.8211 line; that line runs 19,508.71-20,379.14 in
the other eleven monthly statements of 2024, and the act's other lines are ordinary
(13,491.65 · 2,783.97 · 754.66). Read as cents, 20,232.13, the Jan-Nov Β.2.2 00.8211 lines
total 217,858.34: exactly the statement's 8211 Πληρωθέντα. 6Ω80ΩΗ6-0Ι2 (August 2023) has the
same shape: 2,004,276.00 on 00.8211 against 19,448.31-21,070.60 in the other 2023 statements.
Neither is checked against its own PDF yet, so neither is in
`data/manual/amount_review.yaml` or flagged. Until they are, the 2023 and 2024 remittance and
third-party totals (F1, F3) each carry about 2.0M that was not paid.

Expenditure classes (voted budget): 6 ΕΞΟΔΑ ΧΡΗΣΗΣ 11,031,542.99 · 7 ΕΠΕΝΔΥΣΕΙΣ 7,232,281.72 ·
8 ΠΡΟΒΛΕΨΕΙΣ 3,954,381.31 · 9 ΑΠΟΘΕΜΑΤΙΚΟ 33,518.33.
ΠΡΟΒΛΕΨΕΙΣ is notional — that's why execution to 30 November looks like ~37% of budget.

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

---

# Findings — what the data says (distinct from the API contract)

Each finding names its evidence. Queries run against `releases/tinos.duckdb`
(`tinos build && tinos release`). Figures as of the 2026-09-20 corpus.

## F1. Direct awards (Δ.1) stopped being copied into Diavgeia in 2021. Spending did not change.

**Claim.** Δ.1 counts collapse from 2021; payments and commitments hold or rise;
ΚΗΜΔΗΣ contract counts are flat throughout. This was never a migration: ΚΗΜΔΗΣ was
always the primary venue, Diavgeia carried a parallel copy, and the copy stopped.

**Evidence.**
- Δ.1 per year, all entities: 2015-2020 flat at 606-710, then 391 (2021), 187, 132,
  **46 (2024)**, 174, 247 (2026 to Sep). Municipality alone: 391 (2020) → 145 → 100 →
  90 → **13 (2024)** → 133 → 209.
  `SELECT year, count(*) FROM act WHERE type='Δ.1' AND status='PUBLISHED' GROUP BY 1`
- Staggered by entity: municipality 2021; port authority 50256 in 2022 (87 → 3);
  school committees 54500 in 2022 (77 → 0); community enterprise 53952 after 2019
  (117 → 17 → 0) while still publishing 500-600 acts a year.
- Municipality payment acts ~1,700/yr from 2016 to 2026 with no dip; third-party
  payment euros 3.3M (2021) → 6.7M (2024); commitments (reversals excluded) 12.9M
  (2020) → 19.8M (2024). `SELECT * FROM v_yearly WHERE entity='6296'`
- ΚΗΜΔΗΣ, org 6296, POST `/contract` and `/request` with `dateFrom/dateTo` per year,
  first page validated on `contractSignedDate` / `signedDate`:
  contracts 135, 141, 122, 100, 125, 101, 137, 143 (2018-2025); requests 267, 294,
  357, 289, 370, 246, 445, 493. Contracts were already at 135 in 2018 when Diavgeia
  still carried 271 Δ.1 acts for the same body.
- Award value that has no Diavgeia record: against the 2017-2020 average of
  3.08M €/yr, 2021-2024 carry 2.79M in total instead of ~12.3M, i.e. **~9.5M €**.
  `SELECT year, sum(amount) FROM v_award WHERE award_type='Δ.1' GROUP BY 1`
- Partial recovery: 2025 174 acts / 0.83M, 2026 to Sep 247 / 1.19M.
- Independent confirmation: pending-revocation 6ΥΝ1ΟΡ07-0ΨΠ carries the operator note
  "ΔΕΝ ΕΧΕΙ ΑΝΑΡΤΗΘΕΙ ΠΡΩΤΑ ΣΤΟ ΚΗΜΔΗΣ" (not posted to ΚΗΜΔΗΣ first): the rule that
  awards go to ΚΗΜΔΗΣ before Diavgeia was already in force in 2018.
- Join key for the ΚΗΜΔΗΣ side: contract rows carry `diavgeiaADA` and
  `procedureType` (e.g. "Απευθείας ανάθεση (αρ.118/αρ. 328)").

**Caveat.** The port authority's 2022 Δ.1 collapse coincides with a genuine activity
contraction: payment acts 428 → 182, payment euros 0.82M → 0.20M, while commitment
euros held. For 50256 it is not a pure paperwork effect.

## F2. PENDING_REVOCATION acts are mis-uploads the system never processed, not withdrawn spending.

**Claim.** Revocation is a two-party workflow: the organisation requests, a central
Diavgeia operator approves. The 30 PENDING_REVOCATION acts are requests the central
step never completed.

**Evidence.**
- All 30 fall between 2018-03-14 and 2020-01-31; 14 from the port authority, 9 from
  the municipality, 5 from the community enterprise. Pending 6.6-8.5 years.
  `SELECT * FROM act WHERE status='PENDING_REVOCATION' ORDER BY date`
- `/opendata/decisions/{ADA}/versionlog.json`, three pending acts:
  6ΣΕΚΟΡ07-ΙΕΜ published 09:09, flagged 09:14, reason "ΛΑΘΟΣ ΑΡΧΕΙΟ";
  6ΥΝ1ΟΡ07-0ΨΠ published 11:21, flagged 11:22, reason "not posted to ΚΗΜΔΗΣ first";
  ΩΓ6ΖΟΡ07-Υ6Κ published 09:51, flagged 09:55, reason "wrong file uploaded".
  Each log has exactly two versions; no third step.
- Control ΩΝΩ6ΟΞΥΒ-ΟΡΖ (REVOKED, 2016): published 2016-12-09 15:01, flagged 15:10
  "διπλή ανάρτηση", **REVOKED 2016-12-12 07:33 by a central operator account** (not
  an org account). Normal completion takes days.
- Amounts present on 16 of 30, 82,334 € in total, 25,003 € of it one withholdings
  statement to the state.

**Consequence.** Excluded from the measure tables, kept in `act` with their status.
Do not read them as revoked payments.

## F3. Supplier concentration: the corrected series, and why the naive one misled.

**Claim.** Counting every Β.2.2 counterparty as a "supplier" inflated the apparent
2016-2024 concentration trend. Remittances to the state (ΚΑΕ 82, withholdings
statements) and the 2015 ESPA outlier drove most of it. 2026 reverses it.

**Evidence** (municipality, `payee_class = 'supplier'` only: no payroll, remittances, internal
transfers, taxes, debt service or other public bodies; `v_counterparty_year`):

| year | distinct suppliers | first paid this year | supplier € | top-10 | top-1 |
|---|---|---|---|---|---|
| 2016 | 218 | 102 | 2.19M | 41.6% | 7.6% |
| 2018 | 188 | 39 | 2.72M | 51.9% | 20.2% |
| 2020 | 107 | 23 | 0.86M | 85.9% | 67.1% |
| 2022 | 102 | 14 | 2.72M | 88.9% | 48.8% |
| 2024 | 77 | 19 | 2.65M | 92.0% | 59.6% |
| 2025 | 91 | 18 | 2.87M | 91.7% | 60.9% |
| 2026 (to Sep, new chart) | 210 | 95 | 4.21M | 64.8% | 17.2% |

- Naive series (all counterparties): 260 → 120 distinct, top-10 50% → 92%. Roughly
  half of the 2023-2024 "top payee" euros were ΚΑΕ-82 remittances to the Ministry
  of Finance, EFKA and pension funds (3.3M of 6.1M in 2023, 3.6M of 6.7M in 2024),
  and a further 4.7M corpus-wide were transfers inside the entity family (the
  municipality funding its own bodies), 1.6M taxes, 1.4M debt service, 3.3M other
  public bodies. Removing them lowers the supplier count but *raises* the top-1 share
  in 2020-2025 (the electricity bill dominates a smaller denominator); the
  concentration is real, its interpretation is not.
- 2015 top-1 share of 64.7% is one payment: Ω1ΠΠΩΗ6-ΧΗΑ, 6,493,493.00 € to ΔΟΜΙΚΗ
  ΕΦΑΡΜΟΓΗ ΑΕ, 6th instalment of the ESPA-funded «Κέντρο σίτισης» works. Nine
  payments from that contractor total 6.82M over 2014-2016.
- The decline in distinct suppliers 2018-2024 is real but begins before the Δ.1
  collapse and reverses in 2026 (partly because payroll batches and a new chart of
  accounts changed how lines are posted; see hazards above).

**Is the 2026 row trustworthy? Yes, with two caveats.** Tested 2026-09-21 on the
suspicion that the 2026 chart-of-accounts change had broken the remittance rule and
let state payees leak into "suppliers":
- Every ΑΦΜ classed remittance or tax in 2023-2024 keeps that class in 2026; the only
  lines that flipped to supplier total 274 € (ΟΤΕ ΑΚΙΝΗΤΑ). The new chart puts all
  remittances in group 59, 178 lines / 904k €, now an explicit rule.
- The count is keyed by ΑΦΜ, so the 2026 change from `SURNAME,,NAME` to `SURNAME NAME`
  cannot inflate it. 95 suppliers received their first municipal payment in 2026,
  against 14-19 a year in 2022-2025; both companies (39 → 109) and sole traders
  (38 → 101) roughly tripled; monthly distinct suppliers run 43-86 against 19-39 in
  2025; the subjects are ordinary works and services (firefighting, waste collection,
  mosquito control, pump repairs, furniture).
- Two payroll shapes the rules had missed were found and fixed in the same check
  ("ΚΑΙ ΛΟΙΠΕΣ ΥΠΑΛΛΗΛΟΙ" batches; individuals paid under personnel group 21/60), 169
  lines / 268k € moved out of the supplier column.
Caveats: 2026 is nine months, and it is the first year on the new chart, so any rule
that depends on ΚΑΕ semantics is weaker for it. The row is comparable as a count of
distinct paid suppliers; its reading as "the concentration trend reversed" is real so
far but should be re-checked at year end.

**The 2020 trough (0.86M against 1.7M in 2019 and 2.7M in 2022) is real, not a posting
gap and not a classification effect.** Payment acts fell only from 987 to 884; no line
lacks an amount; remittances were normal (0.99M). The extra 250 no-sponsor acts that
year are payroll posted per employee per half-month (subjects checked), not supplier
payments without a payee. Supplier cash-outs were low in every month of 2020, with no
single works payment above 160k €, while the electricity bill alone (580k €) was 67% of
the supplier total. Commitments doubled to 12.9M and awards were normal (391 Δ.1), so
projects were being committed, not paid; the large works payments reappear in December
2021 (452k €) and through 2022 (2.7M). This is the pandemic-year execution-delay
pattern; the data shows the delay, not its cause.

**Reading.** Use as a pointer, not a finding. Large recurring payees (electricity,
waste, water, multi-year works) concentrate any municipal ledger legitimately.

## F4. There was no taxonomy migration.

**Claim.** The numeric (2.4.x) and Greek-letter (Α/Β/Γ/Δ) families run in parallel
for the whole period; neither replaced the other.

**Evidence.** `SELECT year, type, count(*) FROM act GROUP BY 1,2`
- Numeric share of all acts by year: 24%, 24%, 33%, 25%, 21%, 20%, 15%, 17%, 17%,
  20%, 19%, 21%, 27%, 29%, 24%, 25% (2011-2026). No trend, never zero, never dominant.
- Within the numeric family: 2.4.6.1 effectively died in 2019 (222 → 8, then ≤14);
  "100" vanished after 2012; 2.4.7.1 grew from ~16% of all acts (2017) to 29% (2024).
  Since 2019 "numeric" means 2.4.7.1, the miscellaneous-acts drawer.
- Letter families first seen: Β and Δ 2010, Α and Γ 2011, Ζ 2014, Ε 2015.
- `2.4.4` never occurs in the corpus.

## F5. Nothing in the Δ.1 metadata classifies awards.

CPV is filled on ≤13% of Δ.1 acts in any year (0% before 2014). The award amount is
present on 88-100% of acts through 2021 and degrades to 56% in 2023. Classification
of direct awards must come from ΚΗΜΔΗΣ, which carries `cpvItems` and `procedureType`.
