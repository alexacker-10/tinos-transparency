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
- **Full-text search exists, on another endpoint**, with its own contract: see "Diavgeia
  full-text search" below. `q=` on `/opendata/search` is still silently dropped.
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
  net + 388.80 VAT) for gym equipment. Exactly x100. Eight more, and one payment order
  posted twice, were found by reconciling Β.2.2 lines against the execution statements and
  verified against their PDFs (FY2024 below; F7). The 10M threshold cannot catch this class
  of error; verified cases go in `data/manual/amount_review.yaml` (the whole act, or one
  `line_no`; duplicates under `duplicate`) and are flagged `document_mismatch` or
  `duplicate_posting`. The execution statements, ΚΑΕ by ΚΑΕ against Β.2.2 lines
  (`v_kae_reconciliation`), are the systematic check; bodies without parsed statements are
  unchecked.
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

## Diavgeia full-text search ("luminapi") — verified by probe 2026-09-25 (`tinos fulltext-doctor`)
The only way to find decisions *about* Tinos issued by other bodies (grants, allocations).
About 130 probe calls and three doctor runs at 1.5 s, project User-Agent; probe output kept in memory
only (PRIVACY Q7).
- Base: `https://opendata.diavgeia.gov.gr/luminapi/api/search`, keyless, JSON keys `decisions`,
  `facets`, `highlighting`, `info`.
  `?q="ΤΗΝΟΥ"&fq=organizationUid:"<uid>"&fq=issueDate:[DT(2024-11-01T00:00:00) TO DT(2024-11-10T23:59:59)]&page=N&size=100`
- **NO ECHO.** `info.query` is always null; `info` echoes only `page`, the executed `size`,
  `actualSize`, `total` (`order` null). Results are treated as unfiltered until counts prove
  otherwise, as for Diavgeia and ΚΗΜΔΗΣ.
- **`q` must be a quoted term**: unquoted (`q=ΤΗΝΟΥ`) or absent is HTTP 400 SEARCH-001. Matching is
  stemmed and ignores accents and case: "Τήνου" returns the same 2 as "ΤΗΝΟΥ", and the highlights
  of 978 hits show ΤΗΝΟΥ 771, ΤΗΝΟ 26, ΤΗΝΟΣ 24 (and oddities ΤΗΝΥ, ΤΗΝΗΣ). A nonsense term returns 0.
- **`fq` fields are validated** (`organizationUidz` is HTTP 400; an unknown uid returns 0), but
  **unknown top-level parameters are silently ignored** (`foo=bar`, `order=asc`: HTTP 200, same
  result). `sort=recent|relative` is honoured; any other sort value is HTTP 500 SEARCH-006 «η
  αναζήτηση πράξεων είναι δυνατή μόνο βάσει του ΑΔΑ», the message of an unavailable index. The
  client retries SEARCH-006 and never sorts.
- **The org filter matches issuer OR co-issuer**: 7 of the Interior Ministry's 978 hits were joint
  decisions issued by other ministries (`cooperatingOrganizations`).
- **Date bounds are Athens wall-clock time, both inclusive.** ΡΟ0946ΜΤΛ6-ΣΚ8 (stored at UTC midnight
  2024-11-04, shown `04/11/2024 02:00:00`) is matched by `[DT(2024-11-04T02:00:00) TO
  DT(2024-11-04T02:00:00)]`, not by the same window at `T00:00:00`, and not by
  `[DT(2024-11-03T22:00:00) TO DT(2024-11-03T23:59:59)]`. Whole-day windows `[a T00:00:00, b
  T23:59:59]` therefore tile the calendar for both issueDate conventions.
- **Page size is silently capped at 100** (`size=101`, `500`, `1000` all come back `info.size`
  100; default 10). The guard compares `info.size` with the request.
- **No truncation of long windows**, unlike `/opendata/search` and ΚΗΜΔΗΣ: Interior Ministry
  (100054492) × ΤΗΝΟΥ, 2024 in one window 64 = halves 25 + 39 = months 4, 5, 4, 6, 2, 4, 7, 3, 4, 6,
  10, 9; 2015-2025 in one window 426 = the sum of the eleven years. Still checked every year.
- **Paging is stable, usually**: 978 hits over 12 pages of 100, distinct ADAs = total in each window.
  Not always (2026-09-26): the Region of South Aegean (5011), ΤΗΝΟΥ, July-December 2022 returned 288
  records over 3 pages for 287 distinct ADAs, one record twice and so one missed (results are
  unsorted). The guard refused the year; the retry minutes later passed. A stored year is complete.
- **A record's `unitIds` depends on the query**: the same decision found by ΤΗΝΟΥ and by an ΑΦΜ
  came back with different `unitIds` (612Π7ΛΞ-1Ο4: 78486, then 78490), so the second capture is
  stored as a sibling. Nothing is read from that field.
- **Revoked acts are included** (the status facet showed 4 «Ανακληθείσα» among 242 hits of
  2015-2016); `status` is on every record.
- **The index is a finding aid, not a register.** Against the echo-verified `/opendata/search`
  count of the same issuer and window, the near-universal word «ΑΠΟΦΑΣΗ» matches 3,918 of 4,045
  acts (97%, 100054492, Jan-May 2024) but 19,893 of 26,215 (76%, 100025896, Jan-May 2017) and 25,365
  of 30,164 (84%, 100010874, Jan-May 2016). Documents without extractable text are probably not
  indexed, so a missing decision is not proof of no decision.
- **Highlights carry the matched text**: 778 of 978 hits have a `documentText` fragment, e.g.
  `230 58216 <pre>ΤΗΝΟΥ</pre> ΚΥΚΛΑΔΩΝ 121.570,34 115.031,59 236.601,93` (the Tinos row of an
  annex); 200 have none, mostly 2015 police acts. Snippets are a finding aid; amounts are read
  from the stored PDF.
- **The Interior Ministry has five Diavgeia uids**: 12 (the 2009-2011 ministry, by its name; not
  searched), 30 (3, 0 and 2 ΤΗΝΟΥ hits in 2012-2014, none from 2015), **100010874** (ΥΠΕΣΔΑ,
  2015-2016), **100025896** (`ypesneo`, 2016-mid 2019),
  **100054492** (`ypes_2019`, mid 2019-). ΤΗΝΟΥ hits by year: 77, 165 (100010874, 2015-2016);
  27, 121, 129, 33 (100025896, 2016-2019); 25, 79, 43, 58, 89, 64, 68 (100054492, 2019-2025). They
  are the `grantors` in `entities.yaml`, verified by `tinos entities --verify`.
- In 2015-2019 the ministry also ran the police and fire service, so most of its ΤΗΝΟΥ hits are
  the Tinos police station's own purchases (fuel, repairs, detainee transport).
- **Acts about private people come back too** (citizenship grants, staff transfers, appointments,
  detainees): the ingester keeps only whitelisted decisions and redacts the rest (PRIVACY.md Q7).
- The municipality's ΑΦΜ as the term (`"800302968"`, 100054492, 2019-2025) finds 18 acts, all
  already found by ΤΗΝΟΥ.
- Decision metadata (`/opendata/decisions/{ADA}.json`) of these allocations carries no amounts,
  recipients or attachments: the per-municipality table is in the act's own PDF.
- **A document's size cannot be known before downloading it**: `HEAD /doc/{ADA}` is HTTP 405, a
  `Range: bytes=0-0` request is ignored (200, whole body) and the body is chunked without
  `Content-Length`.
- Other issuers naming ΤΗΝΟΥ in 2024 (facet, top 10): Δήμος Τήνου 4,208, Ευαγγελίστρια 739,
  Περιφέρεια Νοτίου Αιγαίου (5011) 708, ΤΕΕ 630, Λιμενικό Ταμείο 409, Αποκεντρωμένη Διοίκηση
  Αιγαίου 213, Υπ. Παιδείας 193, Υπ. Πολιτισμού 191, Υπ. Προστασίας του Πολίτη 177, Σχολικές
  Επιτροπές 161. The Region is the next candidate grantor (searched from 2026-09-26: F9).
- **The Region of South Aegean (5011)**, ΤΗΝΟΥ by year 2015-2025: 115, 730, 596, 802, 801, 666, 446,
  557, 845, 708, 625 (7,409; 2026 to September 518). The municipality's ΑΦΜ (800302968) as the term:
  35 in 2015-2025, the other Tinos bodies' ΑΦΜ none but the slaughterhouse's (1). An ΑΦΜ search is
  *anchored*: every hit is about that body (whitelist, PRIVACY.md Q7).

**Guard** (`tinos.sources.fulltext`): every page must echo the page and page size requested and
hold `actualSize` records, each issued or co-issued by the organisation inside the window; the
total must hold across pages and the distinct ADAs add up to it; each half-year window's count
must differ from the control term's (`"ΔΗΜΟΚΡΑΤΙΑ"`, on nearly every letterhead: 9,230 for the
ministry in 2024 against 64 for ΤΗΝΟΥ), since an ignored `q` returns the same unfiltered set for
both; and each year searched whole must hold exactly what its halves held. A year is stored only
after all of that passed; one ingest-log line per call. (The first rule required the control to be
larger; it refused 2015, where only subjects are indexed and ΑΥΤΟΤΕΛΕΙΣ matched 17 acts of uid 30
in January-June against 1 for the letterhead word. Inequality is what proves `q` was applied.)
- **Document text is indexed only from about November 2015.** Of the ministry's ΤΗΝΟΥ hits, none
  issued March-October 2015 carries a text highlight, 2 of 8 in November, 9 of 13 in December,
  and all from January 2016. Earlier acts match by subject alone, so the 2015 ΚΑΠ allocations,
  whose subjects never name Tinos, are found with the term ΑΥΤΟΤΕΛΕΙΣ (uid 30: 17 hits, 15 kept;
  100010874: 161 hits, 118 kept, most about single municipalities).

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
- Award value that has no Diavgeia record, measured: across all bodies, ΚΗΜΔΗΣ holds 10.40M of
  direct awards (excl. VAT) submitted 2021-2024, Diavgeia Δ.1 2.79M, so **~7.6M** has no
  Diavgeia record (municipality 7.68M in ΚΗΜΔΗΣ, port authority 1.68M, the rest under 0.6M
  each). `SELECT * FROM v_direct_award_year` against `v_award`. The first version of this
  bullet extrapolated ~9.5M from the 2017-2020 Diavgeia average (3.08M/yr); the order was
  right. The VAT basis of Δ.1 `awardAmount` is not stated.
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

## F3. Supplier concentration: with ΚΗΜΔΗΣ payments added, the supplier count never fell.

**Claim (revised 2026-09-25).** On Diavgeia alone the municipality's distinct suppliers fell
from 218 (2016) to 77 (2024) and the top payee's share rose to 60%. Both are artefacts:
remittances and transfers inflated the naive series (corrected 2026-09-21), and from 2019
most supplier payments are published in ΚΗΜΔΗΣ rather than in Diavgeia (F6). Adding the
ΚΗΜΔΗΣ payments whose payees Diavgeia never shows, the municipality paid 194-249 distinct
suppliers every year from 2017 to 2025. Concentration rose moderately, not steeply: the
top-10 share is 44-52% in 2017-2019, 57-64% in 2020-2024 and 74% in 2025; the top-1 share
stays at 18-32%.

**Evidence** (municipality, `payee_class = 'supplier'`; left: `v_counterparty_year`, Β.2.2
lines only; right: `v_supplier_year_combined`, Β.2.2 lines plus ΚΗΜΔΗΣ payments, with the
suppliers only ΚΗΜΔΗΣ shows in brackets):

| Year | Suppliers, Β.2.2 | Top-10 | Top-1 | Suppliers, with ΚΗΜΔΗΣ | Supplier € | Top-10 | Top-1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2016 | 218 | 41.6% | 7.6% | 218 (0) | 2.19M | 41.6% | 7.6% |
| 2017 | 224 | 50.2% | 18.6% | 236 (12) | 3.22M | 49.9% | 18.5% |
| 2018 | 188 | 51.9% | 20.2% | 194 (6) | 2.73M | 51.7% | 20.2% |
| 2019 | 180 | 60.8% | 35.6% | 235 (55) | 3.01M | 44.4% | 20.1% |
| 2020 | 107 | 85.9% | 67.1% | 211 (104) | 3.26M | 57.3% | 17.8% |
| 2021 | 131 | 79.6% | 55.1% | 223 (92) | 3.37M | 57.4% | 22.9% |
| 2022 | 102 | 88.2% | 51.7% | 218 (116) | 4.63M | 62.1% | 28.7% |
| 2023 | 103 | 90.3% | 61.1% | 234 (131) | 4.98M | 63.7% | 30.8% |
| 2024 | 77 | 92.0% | 59.6% | 222 (145) | 5.70M | 63.0% | 27.7% |
| 2025 | 91 | 91.7% | 60.9% | 249 (158) | 9.81M | 73.8% | 32.4% |
| 2026 (to Sep) | 210 | 64.8% | 17.2% | 216 (6) | 4.25M | 64.2% | 17.0% |

- The combined series adds a ΚΗΜΔΗΣ payment only when its payee has no Β.2.2 line within 60
  days, so it is a floor; the payee is the ΑΦΜ on the payment's own invoice lines.
- 2016-2018: ΚΗΜΔΗΣ adds 0-12 suppliers; Diavgeia was then the complete record.
- 2026: ΚΗΜΔΗΣ adds 6. With the municipality's new software, supplier payments are back in
  Diavgeia; the 2026 "jump" is the publication returning, not new suppliers.
- 2020: supplier payments were 3.26M, not 0.86M.
- 2025: payments almost doubled (16.6M paid per the statement, against 11.1M in 2024), and
  a few large projects lift the top-10 share to 74%.

**Earlier corrections, still valid for the Diavgeia-only series.**
- Naive series (all counterparties): 260 → 120 distinct, top-10 50% → 88% (92% before
  the cents entries were flagged). About a third of the 2023-2024 "top payee" euros were
  ΚΑΕ-82 remittances to the Ministry of Finance, EFKA and pension funds (1.3M of 4.1M in
  2023, 1.6M of 4.6M in 2024), and a further 4.7M corpus-wide were transfers inside the
  entity family, 1.6M taxes, 1.4M debt service, 3.3M other public bodies.
- 2015's top-1 share looked like 64.7% because of one line: Ω1ΠΠΩΗ6-ΧΗΑ, 6,493,493.00 € to
  ΔΟΜΙΚΗ ΕΦΑΡΜΟΓΗ ΑΕ for the ESPA-funded «Κέντρο σίτισης» works, which its PDF gives as
  64,934.93 (F7). Flagged, 2015 has top-1 17.0% and top-10 65.2% (184 suppliers); the
  contractor's other eight payments 2014-2016 total 322,609.
- The 2026 classification was checked on 2026-09-21: every ΑΦΜ classed remittance or tax in
  2023-2024 keeps its class (the new chart puts remittances in group 59, now a rule), and
  two missed payroll shapes («ΚΑΙ ΛΟΙΠΕΣ ΥΠΑΛΛΗΛΟΙ» batches; individuals under personnel
  group 21/60) moved 169 lines / 268k € out of the supplier column.

**Withdrawn 2026-09-25.** Two readings of the earlier version were wrong, because both are
changes in what Diavgeia publishes (F6), which the year-end statements expose: that "the
concentration trend reversed in 2026", and that "the 2020 trough is real, not a posting
gap". The 2020 payment acts, amounts and remittances looked normal, but the statement shows
4.24M of supplier-type spending that year and ΚΗΜΔΗΣ carries 2.40M of payments to payees
absent from Diavgeia.

**Reading.** Use as a pointer, not a finding. Large recurring payees (electricity, waste,
water, multi-year works) concentrate any municipal ledger legitimately.

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
stay fully published. The missing supplier payments are, for 66-87% of each year's gap, in
ΚΗΜΔΗΣ's payment register (εντολές πληρωμής), to payees that have no Β.2.2 line at all. Staff
pay is withheld by design throughout. The pattern mirrors F1: direct awards stopped being
copied into Diavgeia in 2021, supplier payments in 2019.

**Evidence** (Δήμος Τήνου; coverage = paid with a Β.2.2 line ÷ paid per statement):

| Year | Paid (statement) | With a Β.2.2 line | Coverage | Excl. staff | 66 consumables | 71 equipment | 73 works | 82 remittances |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 6,480,252 | 3,563,301 | 55% | 72% | 81% | 72% | 87% | 31% |
| 2016 | 5,896,518 | 3,998,354 | 68% | 95% | 96% | 101% | 97% | 92% |
| 2017 | 6,787,387 | 4,968,051 | 73% | 97% | 99% | 97% | 99% | 100% |
| 2018 | 6,243,759 | 4,181,994 | 67% | 95% | 96% | 100% | 103% | 98% |
| 2019 | 7,021,315 | 3,179,978 | 45% | 61% | 16% | 28% | 54% | 76% |
| 2020 | 7,603,787 | 2,497,273 | 33% | 44% | 2% | 17% | 8% | 85% |
| 2021 | 8,169,105 | 3,297,208 | 40% | 56% | 19% | 9% | 30% | 84% |
| 2022 | 9,951,139 | 4,188,207 | 42% | 55% | 8% | 6% | 96% | 89% |
| 2023 | 9,876,883 | 4,088,168 | 41% | 56% | 6% | 1% | 57% | 93% |
| 2024 | 11,134,284 | 4,643,985 | 42% | 56% | 2% | 2% | 1% | 100% |
| 2025 | 16,577,097 | 5,581,969 | 34% | 41% | 13% | 2% | 24% | 101% |

`SELECT * FROM v_payment_coverage WHERE entity='6296'` (statements: the December act of each
year, `budget_line.statement_ada`), after the corrections in F7; before them 2015 read 159%,
2017 86% (115% excluding staff) and 2022 44%. No group now exceeds 103%.

| Year | Supplier-type spending, statement* | In Β.2.2* | Gap | ΚΗΜΔΗΣ payments | to payees with no Β.2.2 line ±60 d | Share of gap |
|---|---:|---:|---:|---:|---:|---:|
| 2017 | 3,778,494 | 3,639,712 | 138,782 | 1,499,071 | 18,464 | 13% |
| 2018 | 3,268,855 | 3,057,589 | 211,266 | 2,064,753 | 8,141 | 4% |
| 2019 | 3,896,777 | 2,137,236 | 1,759,541 | 2,512,408 | 1,316,396 | 75% |
| 2020 | 4,238,462 | 1,332,297 | 2,906,165 | 2,595,695 | 2,399,522 | 83% |
| 2021 | 4,321,084 | 1,982,028 | 2,339,056 | 2,603,274 | 1,973,207 | 84% |
| 2022 | 5,927,823 | 2,808,635 | 3,119,188 | 3,339,923 | 2,057,094 | 66% |
| 2023 | 5,806,735 | 2,703,578 | 3,103,157 | 3,377,195 | 2,469,648 | 80% |
| 2024 | 6,565,586 | 2,944,627 | 3,620,959 | 4,148,661 | 3,061,601 | 85% |
| 2025 | 11,467,566 | 3,637,125 | 7,830,441 | 8,954,481 | 6,845,030 | 87% |

\* ΚΑΕ groups other than 60 staff, 82 remittances, 63 taxes and 65 debt. ΚΗΜΔΗΣ payments:
`/payment` records by submission year, `totalCostWithVAT`, not cancelled. The payee is on the
payment itself (`objectDetails[].vatNo`, filled on every line); a payment counts as absent from
Diavgeia when its payee's ΑΦΜ has no Β.2.2 line within 60 days of it. 2024 in detail: 579 ΚΗΜΔΗΣ
payments, 4.15M; 24 match a Β.2.2 line by amount (0.71M); 72 go to payees paid in Diavgeia with
other amounts (0.38M); 483 to payees with no Β.2.2 line at all (3.06M). Before 2019 almost
every ΚΗΜΔΗΣ payment is also in Diavgeia (18k and 8k are not).

- Not timing: January 2025 carries 61,378 of Β.2.2 payments and none name 2024.
- Not lines without amounts: no 2024 municipal Β.2.2 line lacks one.
- Not filed under another Diavgeia type: of 1,193 municipal 2.4.7.1 acts in 2024, 30 subjects
  mention payment and none an invoice; Β.2.1 has 2 acts.
- Not less spending: supplier-type spending per the statements doubled, 3.3M (2018) to 6.6M
  (2024); the commitments for the under-published groups were published (2024 Β.1.3 exceeds
  what was paid in every one of them).
- 2014 is out of reach: its "December" statement reports December alone, and the parser refuses it.

**Consequence.** From 2019 every Diavgeia payment total is a floor, and supplier analyses on
Β.2.2 alone are biased toward large, recurring and public payees. `v_payment_combined` adds the
ΚΗΜΔΗΣ payments whose payees Diavgeia does not show (a floor itself); F3 is rebuilt on it.

## F7. Reconciliation found amounts entered x100 and a double posting; verified and flagged.

Where Diavgeia's Β.2.2 lines exceed what the year-end statement says was paid under a ΚΑΕ,
some line is wrong or posted twice. Each line below explained its own excess almost exactly,
and its stored PDF (`data/raw/diavgeia/docs/6296/`) confirms it. All are in
`data/manual/amount_review.yaml` and excluded from the views since 2026-09-25 (natural
persons unnamed):

| ADA | Date | ΚΑΕ | Metadata | Document | What |
|---|---|---|---:|---:|---|
| Ω1ΠΠΩΗ6-ΧΗΑ | 2015-08-14 | 15.7341.0001 | 6,493,493.00 | 64,934.93 | ΕΣΠΑ works instalment; the metadata exceeded all 2015 payments |
| 6ΩΗ8ΩΗ6-7ΜΦ | 2017-11-28 | 00.6312 | 530,308.00 | 5,303.08 | the municipality's own ΕΝΦΙΑ balance |
| 6ΓΗΝΩΗ6-5Λ1 | 2017-11-14 | 30.6644 | 191,266.00 | 1,912.66 | fuel; 1,542.47 + 24% VAT, lines sum to the order's 7,605.98 |
| 71ΠΔΩΗ6-ΘΑΠ | 2017-07-20 | 30.6662.0006 | 166,712.00 | 1,667.12 | concrete |
| 6ΩΚΤΩΗ6-9ΛΦ | 2015-11-27 | 20.6263 | 151,960.00 | 1,519.60 | refuse-truck repairs |
| 76Λ6ΩΗ6-1ΝΓ | 2015-11-26 | 20.6263 | 84,680.00 | 846.80 | refuse-truck repairs |
| 61ΘΚΩΗ6-4ΤΛ | 2022-12-22 | 63.7312.0001 | 154,224.42 | = ΨΧΥΧΩΗ6-8ΚΖ | payment order 1.835 posted a second time 21 s after the first |

With 6Ξ6ΖΩΗ6-26Β, 6Ω80ΩΗ6-0Ι2 (FY2024 section) and Ω25ΙΩΗ6-ΟΜΘ, nine municipal lines were
entered x100; together they overstated the municipality's published payments by 11.8M
(metadata minus document amounts), and the duplicate by another 0.15M.

Still open, from `SELECT * FROM v_kae_reconciliation WHERE entity='6296' AND
excess_in_diavgeia > 20000` (20 rows left): 2022 ΚΑΕ 8211 is 131,814 over with no line above
34,490 (repeated monthly withholdings postings?); 2017 ΚΑΕ 6423 holds ΩΩ2ΜΩΗ6-ΩΡΖ at 50,952.00
against 9,718 paid; a 2018 payment coded under a revenue ΚΑΕ (0718, 50,000.00); Β.2.2 lines with
no parseable ΚΑΕ (63-81k a year in 2015, 2016 and 2019).

**Subsidiaries' statements (added 2026-09-26).** 24 December statements of five subsidiaries were
fetched with the owner's approval and parse to the cent: the port authority 2016-2025 (its 2016-2017
statements print `∆` and `µ` for Δ and μ, now normalised), the Tsoklis museum 2019-2021 and 2023, the
Panormos cultural centre 2016-2020 and 2023, 53404 2015 and 2022, the Gyrlas foundation 2017 and 2025
(its subjects abbreviate the budget «Π/Υ», which hid them from the statement filter)
(`v_payment_coverage` and `v_kae_reconciliation` cover them unchanged, being keyed by entity). The
port authority's payment decisions carry 88-98% of what it paid in 2016-2021, then 20-22% in 2022,
2023 and 2025 (83% in 2024): the municipality's pattern of F6, three years later. The smaller bodies'
payment lines mostly carry no ΚΑΕ, so only their totals compare. Two port-authority lines explained
their ΚΑΕ's excess over the statement exactly, the x100 signature above, and their PDFs, fetched on
2026-09-26 with the owner's approval, confirm both; flagged since then:

| ADA | Date | ΚΑΕ | Metadata | Document | What |
|---|---|---|---:|---:|---|
| Ψ4ΡΕΟΡ07-ΩΣΝ | 2017-06-29 | 00.8231 | 115,324.00 | 1,153.24 | withholdings order 49 to ΙΚΑ; excess 114,170.76 = 115,324.00 − 1,153.24 |
| Ψ07ΘΟΡ07-ΡΙ8 | 2019-12-12 | 00.6222 | 58,800.00 | 588.00 | OTE bill for 23/9-22/11/2019; excess 58,212.00; the year's 6222 was 3,186.00 |

Each document gives its amount in figures and in words. With them flagged the port authority's
2016-2021 coverage is 88-98% (it read 104% in 2017 and 100% in 2019 before). ΨΜ32ΟΡ07-09Τ (2020,
115,996.48 to the municipality under 6731, which the statement does not use) looks like a coding
difference, not an amount error.

Before the statements were parsed, the port authority's two largest supplier lines stood out, round sums 24-37 times its 99th-percentile line (19,326) that made
its only two spike years, and their PDFs (`data/raw/diavgeia/docs/50256/`) confirm both as
x100: 61ΟΛΟΡ07-ΕΡ4 (2019, 30.7333.0004) 708,102.00 for 7,081.02, and ΩΤΣΜΟΡ07-ΥΛ7 (2016,
20.6117.0010) 466,638.00 for 4,666.38. Flagged; together 1.16M overstated, and 1.33M with the two
above. Thirteen lines entered x100 in all, nine municipal and four of the port authority.

Corpus-wide, 37 groups of payment lines share entity, date, ΚΑΕ, amount and payee under two
or more ADAs (amount ≥ 1,000; 0.49M counted more than once if all are duplicates). Some are
legitimate (equal instalments paid the same day); only the documents can separate them.
`GROUP BY entity, date, kae, amount, counterparty_afm HAVING count(DISTINCT source_ada) > 1`
over published, non-suspect, non-payroll `payment` rows.

## F8. Money given to Tinos: the Interior Ministry's allocations match the municipality's books to the cent where both are complete.

**Claim.** From 2015 to 2025 the Interior Ministry allocated at least **28.83M €** to Δήμος Τήνου
in decisions whose PDFs we hold and whose amounts are validated against the documents themselves
(1.75M in 2015 rising to 4.05M in 2025; 17.58M of it the monthly general ΚΑΠ). Where a ministry
allocation and a line of the municipality's year-end revenue statement describe the same money,
they agree to the cent in 48 line-years (with the Region's credits of F9) and differ by exactly 0.15% in
18 more. The ΚΑΠ investment
share («ΣΑΤΑ») agrees to the cent in all eleven years; school repairs and fire protection agree in
every year, to the cent or by exactly 0.15%. What remains is timing, allocations booked under a line
not identified here, lines other funders also feed, and three allocations not found (listed below).
None is established as money allocated and not received.

**How the decisions were found and read** (release `0.1.0+curated6`, curated 2026-09-26T09:06Z).
- `tinos fulltext-backfill` (contract above): the four Interior Ministry uids, ΤΗΝΟΥ 2015-2025 and,
  for 2015 (annexes not indexed), ΑΥΤΟΤΕΛΕΙΣ. 1,156 hits, 558 decisions kept, 598 dropped by the
  privacy whitelist. 447 PDFs fetched with the owner's approval (275.2 MB, 471 files with the
  subsidiaries' statements below, 0 failures).
- **The index hides some national tables** (added 2026-09-26). It holds some decisions by subject
  only, with no document text, so ΤΗΝΟΥ cannot match them however large Tinos's row. A second pass
  searched the three ministry uids for 2016-2025 for ΑΥΤΟΤΕΛΕΙΣ, the word of every ΚΑΠ subject
  («Κεντρικοί Αυτοτελείς Πόροι»): 4,367 hits, every page and year through the guard, 1,887 kept by the
  whitelist (1,609 new). A stored page highlights a hit's document text when the text is indexed; a
  kept decision that ΤΗΝΟΥ did not find, whose text no page highlights, whose subject is a table over
  the municipalities and whose family has a revenue line, is one the index hid: 22 of 2016-2025. With
  the owner's approval their PDFs were fetched with the 11 monthly instalments this finding had listed
  as missing, the 13 national tables of 2015 that the 2015 subject pass had kept but never fetched (the
  earlier statement that the unfetched decisions were "about single other municipalities or not money"
  was wrong for them) and the two port-authority documents of F7: 48 files, 26.0 MB, 0 failures.
  31 of them give Tinos an amount (2,371,522.80 € in all), 14 are tables without Tinos.
  `grant_decision.found_by` and `text_indexed` record, per decision, which term found it and whether
  its text was indexed.
- **Whitelist corrected** (PRIVACY.md Q7). «ΑΥΤΟΤΕΛ» also matched «Αυτοτελούς Τμήματος», a ministry
  department: the 2015 subject pass had kept six acts about named employees' travel and one acting
  head's designation. The rule now needs «Αυτοτελείς/Αυτοτελών Πόροι», and staff travel («εκτός
  έδρας»), heads of unit and «του κ. ...» are personal. The curated layer applies the whitelist again,
  so those seven and four more that are not grants never enter it; `data/raw` is append-only and
  keeps them, unpublished.
- `tinos.extract.grants.read_decision` reads each PDF (`pdftotext -layout`) three ways. **National
  tables** keyed by the municipalities' ΤΠΔ codes (Δήμος Τήνου is 58216): a column counts only if it
  sums to the document's own total line, within half a cent per row (the ministry rounds each row;
  COVID 2020: 40,000,000.00 printed, rows 39,999,999.97). The column relation is proved on the
  totals and every row: single amount, components then total, or gross, withholdings (signs −, +, or
  0 for a breakdown column) and net. **Transfer letters** state one amount in words and in figures
  («τριάντα τεσσάρων χιλιάδων εκατόν πενήντα επτά ευρώ & τεσσάρων λεπτών (34.157,04€)»); the words
  must equal the figures. **Stated amounts**: a one-row table equal to the amount the letter states.
- Result (double postings aside): of 2,156 kept decisions (424 found by ΤΗΝΟΥ), 493 have their PDF.
  421 give Tinos an amount, 24 have a validated table without Tinos (Tinos was not a recipient:
  citizen-service centres, school meals of music schools, welfare benefits of 2015 and 2017, the
  small-island and «δικαιούμενοι δήμοι» allocations of 2020-2022, municipal police pay, compensatory
  benefits), 46 are not read: 42 approvals, invitations and other acts that send no money, and 4
  money decisions (a 2016 Θησέας transfer, two 2017 «Βοήθεια στο Σπίτι» payments with no Tinos payee,
  the Tempi transfer below). The 1,663 without a PDF are ΑΥΤΟΤΕΛΕΙΣ hits about single other
  municipalities, withholdings for associations, and ministry acts that mention the central funds.
  Of the 398 money amounts, **395 are validated** (355 by column totals, 22 by words and figures, 18
  by stated amounts). Three are not: two 2016 «Βοήθεια στο Σπίτι» tables whose rows fall short of
  their totals (by 53,477.84 and 23,389.82), and the 2025 ΝΑ255 request 91ΤΔ46ΜΤΛ6-ΒΥΦ. Only validated
  amounts enter the views.
- **An error in the earlier version: 29,700.00 counted twice.** Ω40Λ465ΦΘΕ-ΧΝΙ, the order moving the
  2015 fire-protection ΚΑΠ credits, was read as investment-programme money on top of the allocation
  it executes, 6ΖΒΘ465ΦΘΕ-Σ2Σ (same day, same 29,700.00). The school-repairs pair of 2015
  (7ΛΞ9465ΦΘΕ-9Ι1 and its order 615Ζ465ΦΘΕ-ΑΡ0, 17,300.00 each) would have repeated it. Such orders
  are now a family of their own, `kap_transfer_order`, listed and never reconciled. On the same
  decisions the earlier 26.49M was 26.46M.
- Hazards met on the way, each now handled: `∆` (U+2206) printed for Δ (the 2019 ΣΑΤΑ table lost
  15 municipalities to it), a row number 81 between 62 and 63 (ΤΑΠ 2024), «50.0000,00» (August
  2023), blank cells and «- €» for zero, ΤΠΔ codes split over two lines («5840» / «0»), names
  wrapped above and below the code, whole-euro tables («29.700»), total lines that sum only some
  columns, and a breakdown column (art. 115 ν.5225/2025, November 2025) that enters no net amount.

**Double postings.** The same decision posted twice (same protocol, date and subject, two ADAs,
minutes apart): the monthly ΚΑΠ of March 2018, 6ΠΒΟ465ΧΘ7-64Η and 6ΩΥΘ465ΧΘ7-Ω4Η (108,081.58 each),
and the advertising-fee allocation of December 2022, ΨΚΙΧ46ΜΤΛ6-ΣΒΕ and 9Ζ5246ΜΤΛ6-ΠΕΨ (19,090.00
each); the municipality booked each once. 7Σ1Ζ465ΦΘΕ-ΞΟΜ (September 2016) is a first upload with no
readable table, replaced 9 minutes later by ΨΥΓΦ465ΦΘΕ-ΞΧΨ. The later copies carry `duplicate_of`
and are excluded. One source error: 6Ο4Ζ46ΜΤΛ6-Λ49 funds the municipality of Tempi but cites a Tinos
funding request as its basis.

**Reconciliation** (`v_grant_reconciliation`: allocated for the budget year the subject names,
against «Βεβαιωθέντα» of the revenue line with the same purpose in the December statement; lines
matched by name because the chart moved them between codes; «=» to the cent, «≈» exactly 0.15%
less booked; other cells in € allocated minus booked):

| Line (codes) | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ΚΑΠ general (0611) | ≈ | ≈ | +548 | +29,760 | −29,664 | = | +162 | +144 | = | = | +25 |
| ΚΑΠ investment «ΣΑΤΑ» (1311, 0612) | = | = | = | = | = | = | = | = | = | = | = |
| ΚΑΠ schools' running costs (0614, 4311, 0616) | +49 | = | +27 | +3,670 | −3,654 | = | = | = | = | +71,490 | = |
| School repairs (1312, 0615) | ≈ | ≈ | = | ≈ | ≈ | = | = | = | = | = | = |
| Fire protection (1214, 0614) | ≈ | ≈ | ≈ | = | = | = | = | ≈ | = | = | = |
| Advertising fee, cat. Δ (0715) | −17,464 | ≈ | −13 | ≈ | ≈ | ≈ | = | = | = | = | = |
| «Βοήθεια στο Σπίτι» (0624) | | | | | | | | | = | = | ≈ |
| ΚΑΠ other purposes (0619) | −63,929 | −270,171 | ≈ | +99,018 | +138 | +184,732 | +34,200 | = | = | −186,471 | = |

- **The index's gaps are closed.** Every negative general-ΚΑΠ, ΣΑΤΑ, fire and schools cell of the
  earlier version of this table was a decision the index held by subject only; each is now read and
  each closed its cell exactly. General ΚΑΠ: 6724465ΧΘ7-Α9Ξ, 6Σ3Ζ465ΧΘ7-Κ3Ν (2017, Η΄ and Θ΄, 108,081.58
  each); ΨΔΒΦ46ΜΤΛ6-35Ζ, 6ΨΣ246ΜΤΛ6-ΚΛΡ, 68ΠΤ46ΜΤΛ6-Ε2Φ, 63ΕΕ46ΜΤΛ6-ΓΦΔ, ΨΥΖΣ46ΜΤΛ6-723 (2021,
  108,081.58 each); 9ΧΗΦ46ΜΤΛ6-0Λ4, 6ΧΣΥ46ΜΤΛ6-ΤΗ4, 6Τ7Κ46ΜΤΛ6-Σ6Ψ, Ψ0ΘΞ46ΜΤΛ6-1ΒΧ (2022, 115,211.06
  each). ΣΑΤΑ: the seven 2015 allocations (5 × 20,467.50 + 40,935.00 + 102,337.50 = 245,610.00, the
  booked figure), 7Η9Σ465ΧΘ7-Π7Π (2017, 81,870.00), 628Γ46ΜΤΛ6-Τ5Κ (2020, 122,805.00), ΨΚΟΘ46ΜΤΛ6-Ζ6Ξ
  (2021, 61,402.50), 6Υ7Ρ46ΜΤΛ6-ΒΗΝ and 6ΣΨ246ΜΤΛ6-8ΔΛ (2022, 61,402.50 each). Fire 2021 9Γ6Ξ46ΜΤΛ6-Χ2Ι
  (29,700.00); schools 6ΨΡ746ΜΤΛ6-Ε9Ε (2021, 21,810.00) and 9ΕΠΜ46ΜΤΛ6-ΕΗ4 (2023, 22,700.00); school
  repairs 2015 7ΛΞ9465ΦΘΕ-9Ι1 (17,300.00, booked 0.15% less). Desalination, part of 0619: 2017
  69ΤΛ465ΧΘ7-9ΙΡ (99,250.00, the year now 0.15% short), 2021 6Γ9346ΜΤΛ6-2ΦΟ (103,370.00), 2022
  ΨΕΖ946ΜΤΛ6-310 and ΨΣ8Π46ΜΤΛ6-Λ4Χ (100,215.00 + 125,270.00 = 225,485.00, exactly that year's gap).
- **Residuals.** The general ΚΑΠ of 2021 was booked 162.12 short, 0.15% of one instalment of
  108,081.58; 2017 (548.20), 2022 (144.40) and 2025 (24.99) are unexplained and under 0.05% of the line.
- **Timing.** 2018 → 2019: the supplementary general ΚΑΠ of 28 December 2018 (29,762.12,
  7ΥΙ9465ΧΘ7-2ΚΨ) was booked in 2019. The 2019 figure is exact to the cent once that is known:
  1,391,762.69 = twelve instalments of 108,081.58 + 29,762.12 + the 2019 supplementary 65,119.29
  less 0.15%. The schools' ΚΑΠ shifts 3,670/3,654 between the same two years.
- **The 0.15%.** In 18 line-years the municipality booked exactly 0.15% less than allocated
  (29,700.00 → 29,655.45; 1,172,467.43 → 1,170,708.76), mostly 2015-2017 and in single lines later.
  The ministry's tables show no such withholding for Tinos, so it is taken after the allocation;
  which charge it is, the documents read here do not say.
- **Booked elsewhere.** The schools' ΚΑΠ in 2024 (118,730) appears in 4311 only for 47,240; school
  cleaners' pay (2020-2022) and the COVID and «Βοήθεια στο Σπίτι» 2016 allocations have no line of
  their own in those years' statements; 0619 («ΚΑΠ για λοιπούς σκοπούς») holds more than the
  desalination, road-waste and stray-animal allocations in 2015, 2016 and 2024, and less in 2018,
  2020 and 2021 (booked elsewhere or the next year).
- **Not found.** The advertising fee of 2015 (17,463.76 booked), 2015's welfare line (4,695.53;
  five national welfare tables of 2015 are read and none has a Tinos row), and whatever 0619 held
  beyond the identified allocations in 2015, 2016 and 2024.
- **Not comparable one to one.** The property levy ΤΑΠ is mostly paid through electricity bills;
  the ministry's allocation is 13-15% of line 0441 every year, by construction. Investment
  programmes (1314, 1315, 1322) and state grants (1211, 1215, 1219) also receive money from other
  ministries, the Region and the EU; there the ministry's share is a floor (1322 matched exactly in
  2020: 294,830.16). With the Region's credits (F9) the investment programmes match to the cent in
  2019 too (205,756.11 + 13,094.40 = 218,850.51), 2018 is short by exactly the Region's 50,000.00
  of 28 December 2017, booked in 2018, and 2017's surplus of 149,052.68 is that 50,000.00, the
  Region's sewage-study credit of 39,709.88 (not found in the 2017-2018 statements), and 59,342.80 of
  the ministry's Θησέας transfer that the municipality booked in 1216 («national part of the ΠΔΕ»):
  59,970.67 in 1314 + 59,342.80 in 1216 = 119,313.47, the transfer to the cent. Line 1216 is not
  added to the category: in 2023-2025 it holds 0.17-0.78M a year of other funders' money.

**Queries.** `SELECT * FROM v_grant_reconciliation WHERE year BETWEEN 2015 AND 2025 ORDER BY
category, year`; allocations: `SELECT budget_year, family, sum(amount) FROM v_grant_line GROUP BY
1, 2`; every amount's document: `grant_line.source_sha256` (the PDF), `detail` (table, row, columns).

**Consequence.** Revenue lines 0611, 1311/0612, 1312/0615, 1214/0614, 0715 and 0624 can now be
traced to the ministry's decisions euro for euro. The Region of South Aegean, the next grantor, is F9.

## F9. Money given to Tinos by the Region of South Aegean: 0.30M in 2015-2025, and its investment credits close the 2018-2019 gaps to the cent.

**Claim.** From 2015 to 2025 the Region of South Aegean (5011) gave Δήμος Τήνου at least **298,396.89 €**
in decisions validated in words and figures: 276,076.89 in credits of its investment programme for
projects the municipality carried out (the completion of the municipal gym, the landfill and sewage
studies) and 22,320.00 paid under programme agreements. Its credits are the missing piece of F8's
«investment programmes» line: 2019 matches to the cent and 2018 differs by one timed credit. Most of
the Region's other payment orders to the municipality pay its own water bills (305.80 in 2021-2025), a
sale, not a grant. The Region's hand in the programme-agreement lines (1213, 1326; 0.75M booked in
2015-2025) is mostly not visible: 22,320.00 found.

**How the decisions were found and read** (release `0.1.0+curated7`, 2026-09-26).
- `tinos fulltext-backfill --issuer 5011`, ΤΗΝΟΥ 2015-2025 (7,409 hits) and the municipality's and the
  slaughterhouse's ΑΦΜ (36 hits), guard as for the ministry (one year refused for unstable paging,
  retried; contract above). The ministry's whitelist keeps grant words; the Region's money to the
  municipality mostly has none, so two keep rules were added: a subject naming a Tinos body, and any
  hit of a search for a Tinos body's own ΑΦΜ (its payment orders are titled only «ΕΝΤΑΛΜΑ ΠΛΗΡΩΜΗΣ»).
  The Region's hits name people far more often (licences, fishermen, bus operators, litigants, staff);
  the rules about people were widened first and every stored subject re-checked (PRIVACY.md Q7).
  393 Region decisions kept; 68 PDFs fetched with the owner's approval (17 MB, 0 failures).
- Families of their own (`tinos.extract.grants.REGION_FAMILIES`): credits («Έγκριση/Διάθεση πίστωσης»,
  counted) and their «Κατανομή ποσού» companions (the same tranche, listed); payment orders; programme
  agreements, ΕΣΠΑ inclusions, licences and fines (listed). A credit for a project of the Region's own
  on the island (`region_own_credit`, 43) is not money to Tinos: a credit counts only when its subject
  names a Tinos body or the municipality's ΑΦΜ found it.
- `read_region`: a credit's amount is the one its subject states, validated when the text gives the
  same amount in words and figures and names the municipality as recipient («θα μεταβιβαστεί στο Δήμο
  Τήνου ... Α.Φ.Μ. 800302968») or as the project's owner (10 of 10 validated). A payment order is read
  from its own lines: amount between hash marks, amount in words, payee ΑΦΜ, and purpose («Για:»),
  which sorts water bills from agreement payments (18 of 18 validated).

| Year | Investment credits € | Agreement payments € | Counted € | Water bills € (not counted) |
|---|---:|---:|---:|---:|
| 2015 | 8,755.24 | | 8,755.24 | |
| 2017 | 89,709.88 | | 89,709.88 | |
| 2018 | 156,488.46 | | 156,488.46 | |
| 2019 | 13,094.40 | | 13,094.40 | |
| 2021 | 8,028.91 | 13,020.00 | 21,048.91 | 47.72 |
| 2022 | | | | 31.00 |
| 2023 | | | | 115.46 |
| 2024 | | 9,300.00 | 9,300.00 | 67.41 |
| 2025 | | | | 44.21 |

Investment credits: the municipal gym (2011ΕΠ76700012, ΣΑΕΠ 767): 8,755.24 (2015), 50,000.00 (28
December 2017), 70,000.00, 10,082.03, 22,722.85 (2018), 13,094.40 (2019, the sports hall's floor);
the landfill study (2014ΜΠ06700015, ΣΑΜΠ 067), paid to the municipality as the study's manager:
18,000.00, 35,683.58 (2018), 8,028.91 (2021); the sewage study of Τήνος and Εξωμβούργο (2014ΜΠ06700018):
39,709.88 (2017). Agreement payments: 13,020.00 (6ΚΗ17ΛΞ-ΓΔ5, 2021, an electronic application) and
9,300.00 (9ΩΕΧ7ΛΞ-ΡΓ7, December 2024).

- **Against the books.** 2018's credits plus the 50,000.00 of 28 December 2017 are line 1322 of 2018 to
  the cent (206,488.46); 2019's 13,094.40 closes that year's investment programmes exactly (F8). The
  2021 agreement payment was booked in 1213/1326 as 13,002.48 (17.52 less, not explained). The sewage
  study's 39,709.88 is not visible in the 2017-2018 revenue lines.
- **Not found.** Payment orders before 2021: the Region's documents name the municipality's ΑΦΜ in
  indexed text only from 2021, and ΤΗΝΟΥ cannot tell a payment order to the municipality from one to a
  contractor on the island. Of 0.75M booked in the programme-agreement lines in 2015-2025, 22,320.00 is
  found; agreements can also be with other public bodies. 33 programme-agreement acts and 28 ΕΣΠΑ
  inclusions (one more posted twice) with Tinos bodies are stored and listed, not counted (entitlements
  and budgets).

**Queries.** `SELECT * FROM v_grant_line WHERE grantor = 'region'`; `SELECT family, count(*) FROM
grant_decision WHERE grantor = 'region' GROUP BY 1`.
