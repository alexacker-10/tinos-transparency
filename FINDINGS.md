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
  net + 388.80 VAT) for gym equipment. Exactly x100. Two more were found by reconciling
  Β.2.2 lines against the execution statements (FY2024 below): one withholdings line each
  in 6Ω80ΩΗ6-0Ι2 (2023) and 6Ξ6ΖΩΗ6-26Β (2024), ~2.0M where the document says ~20k. The 10M
  threshold cannot catch this class of error; verified cases go in
  `data/manual/amount_review.yaml` (the whole act, or one `line_no`) and are flagged
  `suspect_reason = document_mismatch`. Expect more; the execution statements, ΚΑΕ by ΚΑΕ
  against Β.2.2 lines, are the systematic check.
- **Remittances dominate naive top-payee lists.** ΚΑΕ group 82 (αποδόσεις κρατήσεων)
  and "Κατάσταση Κρατήσεων" subjects are pass-through withholdings to the state,
  EFKA, IKA and pension funds: 1.6M of 4.6M municipal third-party payments in 2024
  (3.6M of 6.7M before the two cents entries above were flagged).
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
  commitments (0.12M): the record is incomplete, not small. Municipal Β.1.3 runs at 8-40
  acts a year to 2016 and ~1,000 from 2017, but acts with no amount on any line are 657 of
  963 (2017), 913 of 1,121 (2018), 400 of 1,137 (2019), 0 of 1,173 (2020); ΚΑΕ lines become
  routine in 2019-2020. Count commitment acts from 2017; sum commitment euros from 2020.
- `read_json_auto` in DuckDB over the 76k act files exhausts >10 GB; scan with plain
  `json` or pass explicit `columns=`.

## ΚΗΜΔΗΣ — keyless, CC BY 4.0 (re-verified by probe 2026-09-25; `tinos khmdhs-doctor`)
- Base: `https://cerpp.eprocurement.gov.gr/khmdhs-opendata`
- OpenAPI: `/v3/api-docs` · Swagger UI: `/swagger-ui/index.html`
- **POST** `/{request|notice|auction|contract|payment}?page=N` with JSON
  `{"organizations": ["<uid>"], "dateFrom": "YYYY-MM-DD", "dateTo": "YYYY-MM-DD"}` (GET times
  out). Response: `{totalElements, totalPages, number, size, content[]}`, 50 a page, unsorted.
- **Uses the SAME org uid as Diavgeia: `6296`.** Records carry `organization.key`.
- Record type by referenceNumber: `REQ` request (αίτημα), `PROC` notice (προκήρυξη), `AWRD`
  auction (κατακύρωση/ανάθεση), `SYMV` contract (σύμβαση), `PAY` payment (εντολή πληρωμής).
- **The date filter applies to `submissionDate`, both bounds inclusive.** One month, all five
  endpoints: every record's submissionDate inside the window; signedDate not always.
- **CRITICAL: ranges wider than 180 days are silently truncated to `[dateTo − 180 d, dateTo]`**,
  the same clamp as Diavgeia's but with no echo to catch it. 2024-07-01..2024-12-31 returns
  what 2024-07-04..2024-12-31 returns (445 requests) although 29 were submitted on 1-3 July;
  2024-01-01..2024-12-31 also returns 445, three 150-day windows return 727. A body without
  dates is not "all time" either: 124 municipal contracts, a default window. The client
  refuses windows over 180 days, walks 150-day windows and checks every record's
  organisation and submissionDate against the request.
- **Unlike Diavgeia, unknown fields and malformed dates are rejected**: HTTP 400 for
  `organizationz`, and "Invalid date format. Expected format: yyyy-MM-dd".
- **No match is HTTP 404** `{"message": "No auctions found for the given criteria"}` (that
  wording on every endpoint), not an empty page. An unknown uid or an ΑΦΜ gets the same 404.
- **Throttled**: HTTP 429 at about one call a second sustained, with no Retry-After or
  rate-limit headers; none at one call every 3 s. The client paces at 3 s and backs off
  exponentially.
- Paging was stable in tests (445 of 445 distinct over 9 pages); the client checks every window.
- **`/adamChain/{referenceNumber}` returns the pre-built act chain**; attachments at
  `/{type}/attachment/{referenceNumber}`.
- Join keys to Diavgeia: contract `diavgeiaADA`, `contractRelatedADA`, `decisionRelatedAda`;
  request `approvalADA`, `commitmentNo`; payment `paymentRelatedAda`, `paymentCommitmentCode`.
- Other body fields (OpenAPI): `cpvItems[]`, `signer`, `contractType`, `totalCostFrom`/`To`,
  `title`, `referenceNumber`, `procedureType`, `vatNumber`, `contractorName`, `isModified`.
- **Every one-year count taken before 2026-09-25 was truncated** (probe7, F1, SOURCES.md): it
  covered roughly July-December. Corrected counts are in F1.

## Budget reconciliation, FY2024 (Δήμος Τήνου)

**Corrected 2026-09-25.** The earlier version of this table took its paid figures from
Ψ68ΩΩΗ6-3ΓΦ, the statement for «Περίοδος: Νοέμβριος 2024», labelled them "by December", set
them against Diavgeia figures for the whole year from probe3 windows blind to 28-31 Dec
(third-party payments 6,031,795.60; commitments 20,000,913.15, which does not reproduce from
the release) and called the difference, 2,845,325.01, payroll. Full-year figures now come
from the December statement, 6ΝΠΘΩΗ6-Β64 (published 2025-01-10, «Περίοδος: Δεκέμβριος 2024»).

| Figure | Jan-Nov € | Full year € | Source |
|---|---:|---:|---|
| Voted budget (balanced: revenue = expenditure) | | 22,251,724.35 | ΨΞΕΟΩΗ6-2ΥΑ |
| Revised budget at period end | 23,630,861.94 | 23,669,482.09 | statements |
| Ενταλματοποιηθέντα | 9,055,399.10 | 11,153,794.10 | statements |
| **Πληρωθέντα** | **8,877,120.61** | **11,134,283.87** | statements |
| of which personnel costs, ΚΑΕ 60xx | 2,523,642.33 | 2,925,750.54 | statements |
| of which remittances, ΚΑΕ 82xx | 1,145,923.76 | 1,597,701.22 | statements |
| Β.2.2 third-party payments | 3,734,552.58 | 4,643,984.72 | release: 949 / 1,073 lines |
| of which under ΚΑΕ 60 | 190.00 | 47,507.39 | release |
| of which under ΚΑΕ 82 | 1,151,313.80 | 1,604,947.25 | release |
| Β.1.3 commitments, reversals excluded | | 19,824,694.80 | release; 8,486,555.56 of reversals excluded |

Statements: Ψ68ΩΩΗ6-3ΓΦ for Jan-Nov (probe copy `probe-out/exec2412.pdf`, sha256 `78b0de36…`,
not in `data/raw`) and 6ΝΠΘΩΗ6-Β64 for the year (`data/raw/diavgeia/docs/6296/`, sha256
`808e051a…`). Both parsed from `pdftotext -layout`: 98 revenue and 149 expenditure rows each,
every column summing exactly to the document's own ΣΥΝΟΛΟ ΕΣΟΔΩΝ and ΣΥΝΟΛΟ ΕΞΟΔΩΝ. Release:
`SELECT sum(amount) FROM v_payment WHERE entity='6296' AND year=2024` (and `date <= '2024-11-30'`),
source digest `d29344da…`, with the two cents entries below flagged.

**Diavgeia's payment metadata itemises 42% of what the municipality paid in 2024**
(4,643,984.72 of 11,134,283.87). Personnel costs are almost entirely absent: 47,507.39 of
2,925,750.54, and the 725 payroll acts of 2024 carry no amount. The rest of the gap is not
timing: January 2025 carries 61,378 of Β.2.2 payments and none name 2024. Whole ΚΑΕ groups
are thin in Β.2.2 (itemised of paid, thousands €): 61 third-party fees 670 of 1,615;
62 services 1,744 of 2,527; 64 other general expenses 37 of 285; 66 consumables 17 of 681;
71 equipment 7 of 418; 73 works 2 of 149; 81 prior-year bills 169 of 548. Where these
payments are published, if at all, is open; payment orders filed under 2.4.7.1 without
structured amounts is the first hypothesis to test. So paid minus Β.2.2 is not a payroll
estimate: read payroll from the statements' 60xx rows.

**Two metadata amounts entered in cents, verified 2026-09-25.** Both are monthly
withholdings statements («Κατάσταση Κρατήσεων») whose 00.8211 line carries the document
amount x100; the other three lines of each act match the PDF.

| ADA | Month | 00.8211 metadata | 00.8211 PDF | Same line, other months |
|---|---|---:|---:|---:|
| 6Ω80ΩΗ6-0Ι2 | Aug 2023 | 2,004,276.00 | 20,042.76 | 19,448.31-21,070.60 |
| 6Ξ6ΖΩΗ6-26Β | Feb 2024 | 2,023,213.00 | 20,232.13 | 19,508.71-20,379.14 |

With the document amount, the 2024 Β.2.2 lines on 00.8211 total 238,237.48: exactly ΚΑΕ 8211
Πληρωθέντα in 6ΝΠΘΩΗ6-Β64 (Jan-Nov: 217,858.34, exactly Ψ68ΩΩΗ6-3ΓΦ). Both lines are listed by
`line_no` in `data/manual/amount_review.yaml`, flagged `document_mismatch` and excluded from
the views: third-party payments fall from 6.11M to 4.11M (2023) and 6.67M to 4.64M (2024),
remittances from 3.30M to 1.29M and 3.63M to 1.61M. Supplier figures are unchanged.

Expenditure classes (voted budget): 6 ΕΞΟΔΑ ΧΡΗΣΗΣ 11,031,542.99 · 7 ΕΠΕΝΔΥΣΕΙΣ 7,232,281.72 ·
8 ΠΡΟΒΛΕΨΕΙΣ 3,954,381.31 · 9 ΑΠΟΘΕΜΑΤΙΚΟ 33,518.33.
ΠΡΟΒΛΕΨΕΙΣ is notional — that's why the year's payments are ~47% of the revised budget.

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
  payment euros 3.3M (2021) → 4.6M (2024; 6.7M before two cents entries were flagged,
  see the FY2024 reconciliation); commitments (reversals excluded) 12.9M
  (2020) → 19.8M (2024). `SELECT * FROM v_yearly WHERE entity='6296'`
- ΚΗΜΔΗΣ, org 6296, full backfill 2026-09-25 (`tinos khmdhs-backfill`, 150-day windows,
  every record checked), counted by submission year, 2018-2025: contracts 183, 212, 189,
  153, 191, 176, 215, 274; requests 427, 502, 543, 509, 602, 594, 727, 930. (The counts
  first quoted here, contracts 100-143 and requests 246-493, came from one-year windows the
  API had silently truncated to their last 180 days.) Contracts were already at 183 in
  2018 when Diavgeia still carried 271 Δ.1 acts for the same body.
- Measured in ΚΗΜΔΗΣ, not extrapolated: award records (`/auction`, AWRD) with procedure type
  «Απευθείας ανάθεση», municipality, count / value excl. VAT: 252 / 1.41M (2020), 232 / 1.82M,
  283 / 2.18M, 299 / 1.59M, 358 / 2.09M (2024), 433 / 2.60M (2025). Diavgeia Δ.1, same body
  and years: 391 / 1.65M, 145 / 0.36M, 100 / 0.59M, 90 / 0.41M, 13 / 0.14M, 133 / 0.59M.
  2021-2024: 7.68M of municipal direct awards in ΚΗΜΔΗΣ against 1.50M in Diavgeia. ΚΗΜΔΗΣ
  fills `procedureType` only from 2019, so earlier direct awards cannot be picked out there.
- Award value that has no Diavgeia record: against the 2017-2020 average of
  3.08M €/yr, 2021-2024 carry 2.79M in total instead of ~12.3M, i.e. **~9.5M €** (all
  entities, extrapolated; for the municipality the ΚΗΜΔΗΣ measurement above gives 6.2M excl.
  VAT, and the VAT basis of Δ.1 `awardAmount` is not stated).
  `SELECT year, sum(amount) FROM v_award WHERE award_type='Δ.1' GROUP BY 1`
- Partial recovery: 2025 174 acts / 0.83M, 2026 to Sep 247 / 1.19M.
- Independent confirmation: pending-revocation 6ΥΝ1ΟΡ07-0ΨΠ carries the operator note
  "ΔΕΝ ΕΧΕΙ ΑΝΑΡΤΗΘΕΙ ΠΡΩΤΑ ΣΤΟ ΚΗΜΔΗΣ" (not posted to ΚΗΜΔΗΣ first): the rule that
  awards go to ΚΗΜΔΗΣ before Diavgeia was already in force in 2018.
- Join keys on the ΚΗΜΔΗΣ side: contract rows carry `procedureType` (e.g. "Απευθείας
  ανάθεση (αρ.118/αρ. 328)") and Diavgeia ADAs (`diavgeiaADA`, `contractRelatedADA`,
  `decisionRelatedAda`), but the ADAs are filled systematically only from 2023: municipal
  contracts with any ADA 0-4 a year to 2021, 43 of 191 in 2022, 144 of 176 in 2023, all
  since. 707 of the links point to Β.1.3 commitments.

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

- Naive series (all counterparties): 260 → 120 distinct, top-10 50% → 88% (92% before
  the cents entries below were flagged). About a
  third of the 2023-2024 "top payee" euros were ΚΑΕ-82 remittances to the Ministry
  of Finance, EFKA and pension funds (1.3M of 4.1M in 2023, 1.6M of 4.6M in 2024; this
  read "roughly half" until two lines entered in cents, ~2.0M each, were flagged),
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

**Correction 2026-09-25: from 2019 the series measures publication, not suppliers (F6).**
The series counts suppliers in Β.2.2 lines. Until 2018 those lines carried the supplier
spending in the municipality's execution statements almost in full; from 2019 most supplier
payments appear in ΚΗΜΔΗΣ's payment register and not in Diavgeia. The fall from 188
distinct suppliers (2018) to 77 (2024) and the rise in concentration are largely that shift:
small suppliers are exactly who stopped appearing. The 2026 jump to 210 coincides with the
municipality's new financial software and chart of accounts and is probably publication
again (no 2026 statement parsed yet). The 2015 top-1 share rests on Ω1ΠΠΩΗ6-ΧΗΑ, which
cannot be a real 6.49M payment (F7). Do not read 2019-2025 as a market trend until the
series combines Β.2.2 lines with ΚΗΜΔΗΣ payments (payee through the contract's contractor
ΑΦΜ).

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

## F6. Since 2019 most supplier payments are published in ΚΗΜΔΗΣ, not in Diavgeia's payment decisions.

**Claim.** The municipality's year-end execution statements are the denominator (2015-2025,
parsed into `budget_line`; every column equals the document's own totals to the cent). Until
2018, Diavgeia's Β.2.2 lines carried the supplier spending in them almost in full. From 2019
they carry about half and then less, while payments to the state (withholdings, taxes, debt)
stay fully published. The missing supplier payments are, for 65-84% of each year's gap, in
ΚΗΜΔΗΣ's payment register (εντολές πληρωμής), to payees that have no Β.2.2 line at all. Staff
pay is withheld by design throughout. The pattern mirrors F1: direct awards stopped being
copied into Diavgeia in 2021, supplier payments in 2019.

**Evidence** (Δήμος Τήνου; coverage = paid with a Β.2.2 line ÷ paid per statement):

| Year | Paid (statement) | With a Β.2.2 line | Coverage | Excl. staff | 66 consumables | 71 equipment | 73 works | 82 remittances |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 6,480,252 | 10,293,434 | 159% | 211% | 81% | 72% | 476% | 31% |
| 2016 | 5,896,518 | 3,998,354 | 68% | 95% | 96% | 101% | 97% | 92% |
| 2017 | 6,787,387 | 5,856,337 | 86% | 115% | 181% | 97% | 99% | 100% |
| 2018 | 6,243,759 | 4,181,994 | 67% | 95% | 96% | 100% | 103% | 98% |
| 2019 | 7,021,315 | 3,179,978 | 45% | 61% | 16% | 28% | 54% | 76% |
| 2020 | 7,603,787 | 2,497,273 | 33% | 44% | 2% | 17% | 8% | 85% |
| 2021 | 8,169,105 | 3,297,208 | 40% | 56% | 19% | 9% | 30% | 84% |
| 2022 | 9,951,139 | 4,342,431 | 44% | 57% | 8% | 6% | 124% | 89% |
| 2023 | 9,876,883 | 4,088,168 | 41% | 56% | 6% | 1% | 57% | 93% |
| 2024 | 11,134,284 | 4,643,985 | 42% | 56% | 2% | 2% | 1% | 100% |
| 2025 | 16,577,097 | 5,581,969 | 34% | 41% | 13% | 2% | 24% | 101% |

`SELECT * FROM v_payment_coverage WHERE entity='6296'` (statements: the December act of each
year, `budget_line.statement_ada`). Above 100% means Diavgeia lines exceed what was paid: F7.

| Year | Supplier-type spending, statement* | In Β.2.2* | Gap | ΚΗΜΔΗΣ payments | of which to payees with no Β.2.2 line ±60 d |
|---|---:|---:|---:|---:|---:|
| 2017 | 3,778,494 | 3,997,690 | −219,196 | 1,499,071 | 3,550 |
| 2018 | 3,268,855 | 3,057,589 | 211,266 | 2,064,753 | 5,000 |
| 2019 | 3,896,777 | 2,137,236 | 1,759,541 | 2,512,408 | 1,231,866 |
| 2020 | 4,238,462 | 1,332,297 | 2,906,165 | 2,595,695 | 2,231,247 |
| 2021 | 4,321,084 | 1,982,028 | 2,339,056 | 2,603,274 | 1,845,790 |
| 2022 | 5,927,823 | 2,962,860 | 2,964,964 | 3,339,923 | 1,932,147 |
| 2023 | 5,806,735 | 2,703,578 | 3,103,157 | 3,377,195 | 2,260,305 |
| 2024 | 6,565,586 | 2,944,627 | 3,620,959 | 4,148,661 | 2,863,151 |
| 2025 | 11,467,566 | 3,637,125 | 7,830,441 | 8,954,481 | 6,588,226 |

\* ΚΑΕ groups other than 60 staff, 82 remittances, 63 taxes and 65 debt. ΚΗΜΔΗΣ payments:
`/payment` records by submission year, `totalCostWithVAT`, not cancelled. The payee comes from
the contract (`contractRefNo` → `contractingDataDetails.contractingMembersDataList[].vatNumber`);
a payment counts as absent from Diavgeia when that ΑΦΜ has no Β.2.2 line within 60 days of it.
2024 in detail: 579 ΚΗΜΔΗΣ payments, 4.15M; 20 match a Β.2.2 line by amount (0.73M); 48 go to
payees paid in Diavgeia with other amounts (0.32M); 315 to payees with no Β.2.2 line (2.86M);
196 have no contract record to name the payee (0.23M).

- Not timing: January 2025 carries 61,378 of Β.2.2 payments and none name 2024.
- Not lines without amounts: no 2024 municipal Β.2.2 line lacks one.
- Not filed under another Diavgeia type: of 1,193 municipal 2.4.7.1 acts in 2024, 30 subjects
  mention payment and none an invoice; Β.2.1 has 2 acts.
- Not less spending: supplier-type spending per the statements doubled, 3.3M (2018) to 6.6M
  (2024); the commitments for the under-published groups were published (2024 Β.1.3 exceeds
  what was paid in every one of them).
- 2014 is out of reach: its "December" statement reports December alone, and the parser refuses it.

**Consequence.** From 2019 every Diavgeia payment total is a floor, and supplier analyses on
Β.2.2 alone are biased toward large, recurring and public payees (F3). A complete payment
series needs Β.2.2 lines plus ΚΗΜΔΗΣ payments, the overlap removed by payee and amount.

## F7. Reconciliation flags amounts that cannot be right. Unverified; not flagged yet.

Where Diavgeia's Β.2.2 lines exceed what the statement says was paid in a ΚΑΕ group and year,
some line is wrong or posted twice. The lines behind each excess (none yet checked against
its own PDF, so none is in `data/manual/amount_review.yaml`; natural persons unnamed):

| ADA | Date | ΚΑΕ | Amount | Why it cannot be right |
|---|---|---|---:|---|
| Ω1ΠΠΩΗ6-ΧΗΑ | 2015-08-14 | 15.7341.0001 | 6,493,493.00 | More than the municipality paid in all of 2015 (6.48M); group 73 paid 1.67M that year; the project's 2014 commitment was 431,964 (ΒΙΥΗΩΗ6-Ν29). As cents: 64,934.93. |
| 6ΩΗ8ΩΗ6-7ΜΦ | 2017-11-28 | 00.6312 | 530,308.00 | Balance of the municipality's own ΕΝΦΙΑ; the first instalment was 2,192.10 and group 63 paid 13,243.18 in 2017. |
| 6ΓΗΝΩΗ6-5Λ1 | 2017-11-14 | 30.6644 | 191,266.00 | Fuel for a forklift. |
| 71ΠΔΩΗ6-ΘΑΠ | 2017-07-20 | 30.6662.0006 | 166,712.00 | Concrete for one district. As cents, with the line above, it removes 354,398 against group 66's 2017 excess of 353,196. |
| 6ΩΚΤΩΗ6-9ΛΦ | 2015-11-27 | 20.6263 | 151,960.00 | Repairs to a refuse truck (payee a natural person). |
| 76Λ6ΩΗ6-1ΝΓ | 2015-11-26 | 20.6263 | 84,680.00 | Repairs to a refuse truck (payee a natural person); with the line above, group 62's 2015 excess is 198,915. |
| ΨΧΥΧΩΗ6-8ΚΖ, 61ΘΚΩΗ6-4ΤΛ | 2022-12-22 | 63.7312.0001 | 154,224.42 twice | Same day, contractor, ΚΑΕ and amount under two ADAs: a double posting; group 73's 2022 excess is 132,218. |

Corpus-wide, 37 groups of payment lines share entity, date, ΚΑΕ, amount and payee under two
or more ADAs (amount ≥ 1,000; 0.49M counted more than once if all are duplicates). Some are
legitimate (equal instalments paid the same day); only the documents can separate them.
`GROUP BY entity, date, kae, amount, counterparty_afm HAVING count(DISTINCT source_ada) > 1`
over published, non-suspect, non-payroll `payment` rows.
