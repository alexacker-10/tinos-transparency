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
- **No payment orders to the municipality before mid-2021, checked in the structured metadata** (2026-09-26,
  in memory only). `/opendata/search` honours `type=` and echoes it (`decisionTypeUid:"Β.2.2"`), and a Region
  payment decision's metadata names its payee's ΑΦΜ (`sponsor[].sponsorAFMName.afm`). Of all 22,529 Β.2.1 and
  Β.2.2 decisions of the Region issued January 2015 to May 2021, every window echo-verified, one carries a Tinos
  body's ΑΦΜ: the 2015 snow-clearing commitment 612Π7ΛΞ-1Ο4 (49,867.41, a Β.2.1). The same scan of June-December
  2021 (3,270 decisions) finds exactly the four payment orders the ΑΦΜ search found. No search term can find the
  Region's earlier payment orders to the municipality: Diavgeia holds none. Its money went through credits.
- **The Region's development fund** (Περιφερειακό Ταμείο Ανάπτυξης Νοτίου Αιγαίου, uid 14763, ΑΦΜ 090355852)
  is the paying agent of its investment programme: a credit «θα μεταβιβαστεί στο Π.Τ.Α.» and the fund pays the
  bill, to the municipality for a project the municipality carries out. Its payment decisions name the payee's
  ΑΦΜ. The municipality's ΑΦΜ as the term finds 27 of them (2015-2023); a scan of all 5,217 of the fund's Β.2.1
  and Β.2.2 decisions of 2015-2025 finds the same 27. Registered as a grantor, counted as the Region (F9).
- `fq=decisionTypeUid:"Β.2.2"` narrows a full-text search to one decision type (ΤΗΝΟΥ at 5011, 2020: 666 →
  142); `fq=decisionType:"Β.2.2"` returns HTTP 200 and 0 hits, so a wrong fq field is not always refused
  (`organizationUidz` is HTTP 400). The ingester sends neither.
- **Other issuers naming ΤΗΝΟΥ, by year 2015-2025** (probe 2026-09-26, counts only), and the Tinos bodies' ΑΦΜ
  found there 2015-2025:
  - Αποκεντρωμένη Διοίκηση Αιγαίου (50203): 268, 541, 320, 302, 220, 195, 299, 216, 188, 213, 225; the
    municipality's ΑΦΜ 4. The municipality's supervisor: legality reviews and ratifications of its decisions.
  - Ιερό Ίδρυμα Ευαγγελιστρίας (99206908): 642, 720, 752, 811, 694, 468, 469, 613, 692, 739, 800 (its
    letterhead names Tinos); the municipality's ΑΦΜ 30, the community enterprise's 1.
  - The Education Ministry: 100010887 (the merged Culture-Education ministry, 2015: 21), 100015990 (2015-2019:
    3, 141, 119, 148, 124), 100054501 (2019-2023: 97, 147, 103, 107, 53), 100081880 (2023-2025: 80, 193, 222);
    uid 8 only before 2015. The school committees' ΑΦΜ 7, the municipality's 4.
  - The Culture Ministry: 17 (2015: 2), 100015966 (2015-2023: 3, 177, 130, 141, 123, 78, 145, 133, 65),
    100081912 (2023-2025: 75, 191, 316). The Panormos cultural centre's ΑΦΜ 3, the Tsoklis museum's 1.
  - Citizen Protection: 19 (2015: 5), 100042756 (2018-2019: 14, 69), 100054489 (2019-2025: 40, 102, 59, 81,
    179, 177, 180), and Climate Crisis and Civil Protection 100068650 (2021-2025: 12, 41, 37, 24, 42). The
    police station's purchases and staff acts; under the ministries' whitelist 8 would be kept, none money for a
    Tinos body (a 2015 state of emergency, a volunteer group's registration, the police's own expenses), and no
    Tinos ΑΦΜ appears. Not registered.

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
- **A national table can hide from both terms.** The state's 2015 payment of its debts to the
  municipalities (article 27 of law 3756/2009, 7ΞΝ4465ΦΘΕ-Α63, 4 December 2015) names neither Tinos
  in indexed text nor ΑΥΤΟΤΕΛΕΙΣ in its title; the term «3756» finds it (four Interior Ministry uids,
  2015-2025: 77 hits, 8 kept, every year through the guard). Digits are valid terms. Where a statement
  line has more than the tables found, search for a word of the law or programme it names.
- **Searched again with a new keep rule, 2026-09-26:** the foundation (99206908), ΤΗΝΟΥ 2015-2025,
  7,400 hits (the same yearly counts), 85 kept, 57 decisions new, no retries.
- **Grantors found from the municipality's own acceptances** (F12, searched 2026-09-26; each probed in memory first:
  yearly counts, its real subjects under each keep rule, a first-name scan of what would be kept). ΤΗΝΟΥ hits and
  records kept, all years through the guard, no retries, the municipality's ΑΦΜ searched too:
  - the Regional Union of Municipalities of the South Aegean (ΠΕΔ, 53992), 2015-2026: 628 hits, 22 kept; ΑΦΜ 10
    (its payment orders of 2021 and 2023-2025 and three board decisions). Keep rule `tinos_body`: its grant words
    return every island's requests.
  - the Green Fund (99201054), 2014-2026: 37 hits, 30 kept (default rules: none about people); ΑΦΜ 2.
  - the Shipping Ministry (100015969, its General Secretariat for the Aegean and Island Policy), 2015-2026: 942
    hits, 52 kept; ΑΦΜ 47, 45 kept (the transfers to the project account the municipality holds); the port
    fund's ΑΦΜ 2, 1 kept.
  - the public-investment ministries: Finance / National Economy and Finance (15, 2015-2026: 342 hits, 7 kept;
    ΑΦΜ 9, 7 kept), Economy, Development and Tourism (100016002, 2015-2016: 107 and ΑΦΜ 9, all 9 kept, the 2016
    ΕΣΠΑ allocations), Economy and Development (100025890, 2016-2019: 102, 1), Development and Investments
    (100054495, 2019-2023: 147, 1), Development (100081597, 2023-2026: 26, 0; ΑΦΜ 2, 1); Infrastructure and
    Transport (100025905, 2016-2026: 289, 10; ΑΦΜ 9, 3) and its 2015-2016 predecessor (100016011: 13, 0); Digital
    Governance (100054486, 2019-2026: 16, 1; ΑΦΜ 2, 2); the tourism organisation ΕΟΤ (99221315, 2015-2026: 91, 2)
    and the Tourism Ministry (100025893, 2016-2026: 139, 0). All but the Green Fund keep `tinos_body` only.
  - ΕΕΤΑΑ (100027722), probed and not registered: 80 ΤΗΝΟΥ hits in 2015-2025, 38 about people (invoices of the
    «Βοήθεια στο Σπίτι» programme), no hit for any Tinos ΑΦΜ; the municipality's home-help line begins in 2023
    and is the Interior Ministry's to the cent.
- **A Tinos project's code anchors a search like a Tinos ΑΦΜ** (entities.yaml `anchor_codes`, 2026-09-26). The
  Economy Ministry's transfers for the municipality's waste-processing project («Επεξεργασία νέων ΑΣΑ Δήμου
  Τήνου - Μεταβατική περίοδος», 2018ΣΕ36700029) name neither Tinos nor its ΑΦΜ in every act. The code as the term
  (four uids, 2016-2026): 18 hits, 15 kept, 3 about people («ορισμός υπολόγων», the designation of account
  holders); among them 6ΦΠΚ46ΝΛΣΞ-27Τ (160,082.90, 2023) and ΨΨΨΛΗ-8ΑΨ (193,992.44, December 2024). Its 2025
  transfers are not in the index under the code. The rule about people still comes first.
- **Title words find national tables the index holds by title only.** Searched for the words of their titles:
  «ΝΑΥΑΓΟΣΩΣΤΙΚΗΣ» (Interior Ministry 100054492, June 2019-September 2026: 17 hits, 11 kept, the lifeguard grants
  of 2021-2026 and their commitments; 100025896 in 2018-2019 returns nothing relevant and was not stored),
  «ΚΟΡΟΝΟΙΟΥ» (100054492, 2020-2022: 49 hits, 42 kept, the COVID grants), «ΗΛΙΚΙΩΜΕΝΩΝ» (100010874, 2015-2016:
  22 hits, 7 kept, the home-help allocations) and «ΘΗΣΕΑΣ» (uid 30, 2014-2015: 230 hits, 227 kept, the programme's
  transfer orders, 43 of them for the Aegean; the one holding Tinos's row is ΩΗ4ΔΝ-52Τ). Kept but text-indexed and
  not found by ΤΗΝΟΥ means no Tinos row (the supplementary lifeguard tables of 2022 and 2024); not text-indexed
  means the index cannot say, so the document is read.
- **Extended to 2026**: every grantor searched through 2026-09-26 for ΤΗΝΟΥ and the Tinos ΑΦΜ (the Interior Ministry
  also for ΑΥΤΟΤΕΛΕΙΣ and «3756»): 2026 adds 35 + 150 Interior Ministry decisions, 23 + 1 of the Region, 3 of the
  foundation, 1 of the Education Ministry, and the new grantors' 2026 acts.
- **Purged, 2026-09-26** (PRIVACY.md Q7): 13 Interior Ministry staff-travel commitments of 2020-2024, found by
  ΑΥΤΟΤΕΛΕΙΣ and kept by the earlier rules, and the 4 search pages holding them whole, after their years were
  searched again; `tinos fulltext-purge --apply` on the owner's word, 17 lines in the ingest log.

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

**Every month read, 2026-09-26** (F11). Layouts: `standard` (July 2015-2024), `apologistika` (February-June
2015: rows at every level of the chart and spending per service; the 4-digit rows are summed per ΚΑΕ and must
equal each side's «ΓΕΝΙΚΟ ΣΥΝΟΛΟ»), `2025`. Refused: December 2014 and January 2015 (a layout with the month's
own figures, not the year to date) and January-August 2026 (the new chart of accounts, codes such as
«010.1310101»). The municipality published no statement for October-November 2016 or January-February 2017.

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

**Claim.** From 2015 to 2025 the Interior Ministry allocated at least **29.02M €** to Δήμος Τήνου (revised
2026-09-26, below; the rest of this claim is the 2026-09-26 morning text)
in decisions whose PDFs we hold and whose amounts are validated against the documents themselves
(1.98M in 2015 rising to 4.05M in 2025; 17.58M of it the monthly general ΚΑΠ; was 28.83M before the
2015 tranche of the state's debts to the municipalities, 228,743.11, was found on 2026-09-26). Where a ministry
allocation and a line of the municipality's year-end revenue statement describe the same money,
they agree to the cent in 52 line-years (with the Region's payments of F9; 48 before them) and differ by
exactly 0.15% in 18 more. The ΚΑΠ investment
share («ΣΑΤΑ») agrees to the cent in all eleven years; school repairs and fire protection agree in
every year, to the cent or by exactly 0.15%. What remains is timing, allocations booked under a line
not identified here, lines other funders also feed, and three allocations not found (listed below).
None is established as money allocated and not received.

**Revised 2026-09-26 (evening): 29.06M → 29.02M.** Read against the monthly statements (F11):
- **The 2020 arrears grants are ceilings, not money received** (−507,722.07). 6ΥΕΓ46ΜΤΛ6-6ΣΑ (127,272.07) and
  ΩΦΙΦ46ΜΤΛ6-6ΞΘ (380,450.00) grant «έως» that much for the municipality's arrears; the Deposits and Loans Fund pays
  each creditor directly on the municipality's payment orders («Εντολές Εξόφλησης»), and the municipality registers
  the grant only as it draws on it. It never did: 1219 of 2020 was budgeted at 127,272.07 and collected nothing,
  and neither grant appears in any statement of 2020-2023. Family `arrears_ceiling`, listed.
- **National tables the index holds by title** (the contract above): the COVID grant of May 2020 (64ΧΒ46ΜΤΛ6-9Υ8,
  75,124.62, June 2020's 1211 receipt 75,011.93 and September's 112.69 to the cent), that of August 2021
  (69ΘΤ46ΜΤΛ6-4ΧΞ, 42,600.00), the lifeguard grants of 2021 (6Γ6Η46ΜΤΛ6-5ΝΨ, 47,114.25, June 2021's 1211 receipt
  47,043.58 after 0.15%) and 2024 (ΨΔΖΣ46ΜΤΛ6-0ΨΤ, 186,771.40); the December 2020 COVID table has no Tinos row.
- **Home help, 2015-2016, is 0619.** The statements of 2015-2016 have no home-help line: September 2015's 0619
  receipt, 50,653.90, is ΩΚΦΘ465ΦΘΕ-Ι56 (50,730.00) less exactly 0.15%, and May-August 2016's 42,093.28 is the
  three 2016 allocations, 17,305.12 (ΩΖΛΣ465ΦΘΕ-ΓΙΔ) + 11,138.52 (ΩΤΤΥ465ΦΘΕ-ΨΕΧ) + 13,649.64 (6ΧΤ2465ΦΘΕ-ΥΦ9), to
  the cent. Two of the three had failed validation: each table's last row is a regional unit numbered in sequence
  but with no ΤΠΔ code (row 48, 53,477.84; row 61, 23,389.82), exactly the shortfalls; the parser now reads such a
  row. With them 0619 closes in 2015 (0.15% of the year) and 2016 (0.15% of the ΚΑΠ parts, 665.79).
- **0619 of November-December 2024.** ΡΟ0946ΜΤΛ6-ΣΚ8 pays two purposes from two accounts, one column each: arrears to
  third parties (121,570.34, account «Κάλυψη των πάσης φύσεως αναγκών», booked in 1215 as 121,387.98, the 0.15%
  refunded in December) and operating costs charged to the ΚΑΠ account (115,031.59, booked in 0619 as 114,859.04,
  family `kap_supplementary`). With a quarter of the schools' ΚΑΠ (23,830.00 → 23,794.26) that is November's
  138,653.30 to the cent; December's 163,610.34 is the desalination instalment, a quarter of the schools' ΚΑΠ and
  the stray-animal grant, each less 0.15%, plus 445.45 of the year's withholdings refunded. The earlier reading of
  the whole 236,601.93 as arrears is corrected.
- **What 1211 holds.** The ministry's operating grants: COVID (2020-2021), stray animals (2020), the school cleaners'
  pay (2020-2022; 0621 exists only from 2023), lifeguards, elections, the 2022-2023 energy grants, each less 0.15%
  on arrival and the 0.15% often refunded months later (June 2020's 75,124.62 arrived as 75,011.93, the 112.69 in
  September). 1211 of 2020 is COVID 258,356.56 + stray animals 1,500.00 + school cleaners 32,960.00 = 292,816.56
  to the cent; 1211 + 1219 of 2021 is school cleaners 80,184.00 + COVID 76,800.00 + lifeguards 47,114.25 + the
  Regional Union's 10,000.00 (F12) = 214,098.25 to the cent. A school-cleaner allocation counts in the year it is
  paid, not the school year its subject names («διδακτικό έτος 2022-2023»); COVID and stray-animal grants of
  2020-2021 and the cleaners' of 2020-2022 are state grants (`CATEGORY_BY_YEAR`).
- **Θησέας**: the 2016 transfer order (6ΙΧ2465ΦΘΕ-Ο2Κ, 36,540.00; the ΕΕΤΑΑ's table sections are now read against
  their own «ΣΥΝΟΛΑ») is March 2016's 1314 receipt 36,485.19 less 0.15%; the order of 29 December 2014
  (ΩΗ4ΔΝ-52Τ, 27,667.90) is February-March 2015's 1314 receipts, 27,626.40 + 41.50, to the cent (dated 2014, it is
  outside the 2015-2025 sum).
- The 1216 line («national part of the ΠΔΕ») joins the investment programmes: its other funders are now read (F12).

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
| ΚΑΠ other purposes, the state's debts, home help 2015-2016 (0619) | ≈ | ≈ | ≈ | +99,018 | +138 | = | = | = | = | −71,440 | = |

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
  their own in those years' statements; 0619 («ΚΑΠ για λοιπούς σκοπούς») holds less than its
  allocations in 2018, 2020 and 2021 (booked elsewhere or the next year; 2015, 2016 and 2024 below). **2018 is one instalment booked under another
  line** (found 2026-09-26): the two desalination instalments of 98,870.00 each were booked 98,721.69 in
  0619 and 98,721.69 in 1219 («Λοιπές επιχορηγήσεις»), together 197,443.38 = 197,740.00 less exactly
  0.15%; with the 1219 half moved back, both lines of 2018 close. 2020: 0619 holds exactly the two
  desalination instalments (92,020.00 + 112,265.00 = 204,285.00); the COVID and stray-animal
  allocations (184,731.94) are not in it.
- **0619 in 2015, 2016 and 2024, from the monthly statements** (F11, 2026-09-26). The state paid off its
  own debts to the municipalities (article 27 of law 3756/2009) in two tranches of 228,743.11 for Tinos,
  7ΞΝ4465ΦΘΕ-Α63 (4 December 2015; found by a search for «3756»: the index holds the table by title
  only) and 7ΡΒ7465ΦΘΕ-19Θ (30 November 2016), booked in 0619 (the 2015 statements name the sub-account,
  «0619.0001 Επιχορήγηση άρθρου 27 του Ν.3756/2009»): December 2015's 0619 receipt is 228,399.99, the
  tranche less exactly 0.15%, and October-December 2016's is 335,801.07, the tranche and the desalination
  instalment of 21 December (107,562.41) each less 0.15%. 2015's desalination instalments were booked in
  1219 instead: 1219 of 2015, 232,262.14, is the two instalments (215,124.82) less 0.15% and the tourism
  organisation ΕΟΤ's 17,460.00 for a conference (sub-account 1219.0006), to one cent. 2024: three
  quarters of the schools' ΚΑΠ (3 × 23,830.00, the +71,490 of the schools' row) were booked in 0619 as
  3 × 23,794.26, the rest of their year in 4311. The remainders this note left unidentified (50,653.90 of
  September 2015, 42,093.28 of May-August 2016, 115,304.49 of November-December 2024) are home help and the
  two-purpose table of November 2024 (revision above).
- **Not found.** The advertising fee of 2015 (17,463.76 booked). 2015's welfare line (4,695.53; five national
  welfare tables of 2015 are read and none has a Tinos row) is the Labour Ministry's: the municipality's own
  acceptance (Ω02ΓΩΗ6-ΕΞ6, May 2015) cites its decision Δ23/11957/840/6-4-2015 for a social-protection programme
  and the same 4,695.53; that ministry's decision is not stored, so it is explained, not counted.
- **The 2015 state grants.** Line 1211 of 2015 (16,043.00) is the Decentralised Administration's four
  election grants to the cent (F10).
- **Not comparable one to one.** The property levy ΤΑΠ is mostly paid through electricity bills;
  the ministry's allocation is 13-15% of line 0441 every year, by construction. Investment
  programmes (1314, 1315, 1322) and state grants (1211, 1215, 1219) also receive money from other
  ministries, the Region and the EU; there the ministry's share is a floor (1322 matched exactly in
  2020: 294,830.16). With the Region's payments (F9) the investment programmes match to the cent in
  2018 (206,488.46) and 2019 (205,756.11 + 13,094.40 = 218,850.51), and the Region's 2015 money is line
  1319 (added to the category) to one cent. 2017's surplus of 59,342.80 is the part of the ministry's
  Θησέας transfer the municipality booked in 1216 («national part of the ΠΔΕ»): 59,970.67 in 1314 +
  59,342.80 in 1216 = 119,313.47, the transfer to the cent. (The first version of this note also held
  the Region's 50,000.00 of 28 December 2017 and its sewage-study credit of 39,709.88: both went to the
  Region's fund, F9.) Line 1216 joined the category on 2026-09-26: its 0.17-0.78M a year of 2023-2025 is
  mostly the Economy Ministry's and the Aegean secretariat's money, read in F12.

**Queries.** `SELECT * FROM v_grant_reconciliation WHERE year BETWEEN 2015 AND 2025 ORDER BY
category, year`; allocations: `SELECT budget_year, family, sum(amount) FROM v_grant_line GROUP BY
1, 2`; every amount's document: `grant_line.source_sha256` (the PDF), `detail` (table, row, columns).

**Consequence.** Revenue lines 0611, 1311/0612, 1312/0615, 1214/0614, 0715 and 0624 can now be
traced to the ministry's decisions euro for euro. The Region of South Aegean, the next grantor, is F9.

## F9. Money given to Tinos by the Region of South Aegean: 0.90M in 2015-2025, most of it through its development fund, and every programme-agreement payment found is booked to the cent.

**Claim.** From 2015 to 2025 the Region of South Aegean gave Δήμος Τήνου at least **901,434.66 €** (revised
2026-09-26 with the 2015 snow-clearing commitment, 49,867.41, below; the rest is the earlier text: 851,567.25 €, 38
decisions, every amount validated in words and figures): 594,583.65 paid by its development fund
(Περιφερειακό Ταμείο Ανάπτυξης Νοτίου Αιγαίου, uid 14763), the paying agent of the Region's investment
programme, of which 419,929.13 under programme agreements and 174,654.52 for projects; 234,681.12 in
credits transferred to the municipality directly (the landfill study); and 22,302.48 by the Region's own
payment orders under programme agreements (from 2021, net of their withholdings). Set against the
municipality's books, every payment found is booked to the cent in the year it was paid: 1319 in 2015
(181,723.86, one cent less than the 181,723.87 paid), 1213 in 2016 (78,780.00), 1326 in 2017 (45,904.93),
1322 in 2018 (206,488.46: the fund's 152,804.88 and the landfill credits' 53,683.58), the investment
programmes in 2019 (with F8), 1213 in 2021 (13,002.48: the order's 13,020.00 less its own 17.52 of
withholdings), 1213 and 1326 in 2022 (12,400.00 and 126,345.32) and 1326 in 2023 (144,098.88). The
Region's other payment orders to the municipality pay its own water bills (305.80 in 2021-2025): a sale,
shown, not counted.

**Corrected from the first version of this finding** (release `0.1.0+curated7`, 298,396.89 €). The
Region's credits were counted as its payments; most are transfers to its fund, which pays the bill. The
sewage study of Τήνος and Εξωμβούργο (2017, 39,709.88) was the Region's own, paid by its fund to the
consultant: never the municipality's money. The 17.52 not explained in 2021 is the payment order's own
withholdings. The credits behind the fund's payments are now listed (`region_credit_via_fund`, 7
decisions, 214,364.40), not counted, and the fund's payments counted once.

**How found and read** (release `0.1.0+curated7`, 2026-09-26).
- `tinos fulltext-backfill`, the Region (5011) for ΤΗΝΟΥ and the Tinos bodies' ΑΦΜ, and its fund (14763)
  for the Tinos bodies' ΑΦΜ: 420 decisions kept (393 and 27), 138 PDFs read. The fund's decisions keep only
  acts naming a Tinos body or found by its ΑΦΜ (PRIVACY.md Q7).
- `read_region`: a credit's recipient is where the credit «θα μεταβιβαστεί»: to Δήμο Τήνου (counted,
  `region_credit`), to the fund (listed), or elsewhere (the Region's own project on the island, listed). The
  fund's payment decisions (`read_fund`: approval in words and figures, or the order's total equal to the
  voucher's) name the payee's ΑΦΜ; those to the municipality are counted: under a programme agreement when
  the sub-project, the subject or a stored Region agreement says so, else for a project. A payment order is
  read from its own lines, net of the withholdings it states («ΕΝΤΕΛΛΟΜΕΝΟ ΠΟΣΟ»).

| Year | Fund, programme agreements € | Fund, projects € | Credits to the municipality € | Region's orders (net) € | Counted € | Booked as |
|---|---:|---:|---:|---:|---:|---|
| 2015 | | 8,755.24 | 172,968.63 | | 181,723.87 | 1319: 181,723.86 |
| 2016 | 78,780.00 | | | | 78,780.00 | 1213: = |
| 2017 | 45,904.93 | | | | 45,904.93 | 1326: = |
| 2018 | | 152,804.88 | 53,683.58 | | 206,488.46 | 1322: = |
| 2019 | | 13,094.40 | | | 13,094.40 | investment programmes: = (F8) |
| 2021 | | | 8,028.91 | 13,002.48 | 21,031.39 | 1213: = (13,002.48) |
| 2022 | 138,745.32 | | | | 138,745.32 | 1213 + 1326: = |
| 2023 | 156,498.88 | | | | 156,498.88 | 1326: =; 1213: 12,400.00 of 14,020.00 |
| 2024 | | | | 9,300.00 | 9,300.00 | 1213: 9,300.00 of 50,718.27 |

- **Programme agreements.** 33 acts with Tinos bodies are stored and read (agreements, amendments, the
  Region's committee decisions; the sums they state run from the electronic application's 13,020.00 of
  2020 and the snow clearing's 49,867.41 of 2015 to budgets of 250,000 and 450,000) and listed, not
  counted: entitlements and budgets, not money sent. What they promise arrives through the fund, whose
  payments are the ones in the table; a fund payment is matched to its agreement by sub-project title.
- **Revised 2026-09-26: 851,567.25 → 901,434.66.** 1213 of 2015, 49,815.74, is the snow-clearing commitment
  (612Π7ΛΞ-1Ο4, 49,867.41) less the 0.10% ΕΑΑΔΗΣΥ withholding and the 3.6% stamp duty on it (51.67). Before
  mid-2021 the Region published no payment orders to the municipality, so its commitment «για την πληρωμή
  ισόποσης δαπάνης» is the last published step of the payment: counted (family
  `region_agreement_commitment`).
- **The rest of 1213 and 1326 is the port fund's own money.** The municipality's port fund (a Tinos body, its
  own acts in `payment`) pays the municipality under their programme agreements: the playground works in the
  port in 2020 (ΩΔΔΧΟΡ07-5ΓΜ 23,975.25 in February, ΨΜ32ΟΡ07-09Τ 115,996.48 less 83.98 of ΕΑΑΔΗΣΥ and 3.02 of
  stamp duty in April, the 87.00 refunded in May, Ψ4ΦΩΟΡ07-Ρ1Β 15,382.57 in August: 1326 of 2020, 155,354.30,
  to the cent) and the removal of the ports' waste in 2024 (Ψ46ΕΟΡ07-ΚΗ9, 41,461.22 less 42.95: December's
  1213 receipt 50,718.27 with the Region's 9,300.00) and 2025 (ΨΦΑΩΟΡ07-Θ92, 35,589.52 less 35.59: September's
  35,553.93). Money between Tinos bodies, not money given to Tinos: explained, not counted. The first payment
  order's metadata transposes two digits (23,795.25; data/manual/amount_review.yaml, F7).
- **Open.** 1213 of 2017 (23,084.00) and of 2023 (1,620.00): no payment found; programme agreements can be with
  other public bodies.
- **Not in Diavgeia.** Payment orders of the Region to the municipality before mid-2021: an echo-verified
  scan of all 22,529 of its payment decisions of 2015-2021 found none naming the municipality's ΑΦΜ before
  then (contract section). The fund's payments cover the years before.

**Queries.** `SELECT * FROM v_grant_line WHERE grantor = 'region'`; `SELECT * FROM v_grant_reconciliation
WHERE category IN ('programme_agreements', 'investment_programmes')`.

## F10. Other public bodies: the Evangelistria foundation's statutory grant, 2.50M in 2015-2025, is line 2119 month by month; the 2015 election grants are line 1211.

**Claim.** From 2015 to 2025 the Evangelistria foundation (Πανελλήνιο Ιερό Ίδρυμα Ευαγγελιστρίας, 99206908)
paid Δήμος Τήνου **2,497,913.91 €** of the statutory grant it owes it, 10% of its gross receipts, in 25
decisions read from their PDFs (1,594,676.80 of it spelled out in words; the rest stated in figures only,
counted and marked). The municipality books it as prior years' revenue, line 2119: the statements of 2014-2015
name the sub-account («2119.0002 Εισφορά (10% επί των ακαθαρίστων) Π.Ι.Ι.Ε.ΤΗΝΟΥ παρελθόντων ετών»), and
the monthly statements date every one of the 25 payments to a jump of 2119 of the same amount: in the
decision's month (18, and one in the October-December 2016 span that two missing statements leave), one or
two months later (4), or in two instalments where the decision says it will be paid in instalments (2). Also counted: the Decentralised Administration's four election grants of 2015,
16,043.00 €, which are line 1211 of 2015 to the cent (F8 had left it open); the Culture Ministry's grants
to the Panormos cultural centre (35,000.00 € in 2018-2021; 2018's 10,000.00 is the centre's own line 1219)
and the Tsoklis museum (3,000.00 € in 2022); and the Education Ministry's money for foreign-language books
and a 2019 transfer for school equipment (10,961.02 € to the school committees; 1,718.35 € to the
municipality in 2024-2025, line 1219 of December 2024 and December 2025 to the cent).

**How found** (release `0.1.0+curated7`, 2026-09-26).
- `tinos fulltext-backfill`, ΤΗΝΟΥ and the Tinos bodies' ΑΦΜ, 2015-2025, each issuer with keep rules of its
  own (PRIVACY.md Q7): the foundation (7,400 ΤΗΝΟΥ hits: every act carries the word in its letterhead; kept
  are acts naming a Tinos body, its statutory grants, and hits of the municipality's ΑΦΜ), the
  Decentralised Administration (50203; subjects with a grant word), the Education Ministry (four uids) and
  the Culture Ministry (three uids; acts naming a Tinos body). Each issuer's real subjects were read in
  memory before anything was stored, and every kept subject was scanned for first names afterwards: places,
  saints, programmes, a museum, the city of Sofia and a wreath («στεφάνου»), no person.
- The foundation's statutory grants were first missed. Titles such as «Έναντι τακτικής επιχορήγησης έτους
  2017» or «Τακτική επιχορήγηση Δήμου - Ι.ΤΗ.Π. - Ι.Μητρόπολη Σύρου» name no Tinos body, and the whitelist
  kept only acts that do. Line 2119's monthly receipts showed payments without a decision (December 2020 and
  2021); an echo-verified scan of the foundation's 7,399 decisions of 2015-2025, in memory, found them. The
  rule `statutory_grant` was added for this issuer only (its grants to public and church bodies; the rules
  about people still come first; a first-name scan of the 62 titles it adds found none), and the foundation
  was searched again (all eleven years passed the guard; 57 decisions added). 29 PDFs were fetched: two pay
  the municipality (60,000.00 in December 2020, 100,652.92 in December 2021), 27 pay other bodies (the Tinian
  Culture Foundation, the foundation's elderly-care unit, the Panormos school of fine arts, a pension fund).
- `read_foundation`: each numbered item of the decision, the recipient it names (the municipality, or the
  school committee: 600.00 € in 2019 and 2022, not counted as the statutory grant), the amount after «ποσού»,
  and its words when it spells them. Five PDFs print Greek in a shifted font (Τ as Η, Σ as Ζ, Ρ as Π, «Δήμο
  Σήνου»); the digits are intact and the number words are read back through the shift, so they check the
  figures too. `read_other`: the other grantors' single amount in words and figures («απόδοση επιχορήγησης
  ύψους πέντε χιλιάδων τετρακοσίων εξήντα ευρώ (5460,00 €) στο Δήμο ΤΗΝΟΥ»), or rows for a Tinos body's ΑΦΜ
  that add up to the stated total (school books: the column of the total, since a per-school subtotal sits
  beside its parts).

| Year | Decisions | Statutory grant paid € | In words € | 2119, all prior-year revenue € | When 2119 received it |
|---|---:|---:|---:|---:|---|
| 2015 | 1 | 121,085.57 | | 302,569.00 | December |
| 2016 | 2 | 223,917.68 | | 267,734.28 | July + September (instalments); October-December |
| 2017 | 3 | 247,580.94 | | 274,636.10 | July + August (instalments), October, December |
| 2018 | 2 | 150,000.00 | | 274,369.81 | July, October |
| 2019 | 2 | 146,474.85 | 146,474.85 | 164,551.99 | September, November |
| 2020 | 2 | 120,000.00 | 60,000.00 | 131,757.47 | August (60,000.00 exactly), December |
| 2021 | 3 | 265,652.92 | 165,000.00 | 295,029.77 | July, October, December |
| 2022 | 3 | 316,449.76 | 316,449.76 | 330,025.71 | July, August, November (3,451.70 short) |
| 2023 | 2 | 277,289.17 | 277,289.17 | 305,427.61 | July, December |
| 2024 | 3 | 305,137.16 | 305,137.16 | 331,840.57 | August, October, December |
| 2025 | 2 | 324,325.86 | 324,325.86 | 403,736.18 | October, December |

- **Not found.** Two jumps of 2119 have no foundation decision: October 2015 (122,146.62) and December 2018
  (105,741.53). Each is where a settlement of the previous year's grant would fall (2014's receipts were
  settled in December 2015 with 121,085.57 «ως ολική εξόφληση», so something came before it; 2017's receipts
  had 150,000.00 by October 2018, against 247,580.94 and 206,474.85 in the years either side). Neither the
  full-text store nor the structured scan holds a decision for them; they are not counted.
- **Water bills.** The foundation pays the municipality for the water of its buildings (20 decisions): a
  sale, listed, not counted, as the Region's.
- **The Culture Ministry's 2021 grant to the Panormos centre** (ΨΑΤ94653Π4-3ΟΜ): its title in Diavgeia says
  6,500 €, its document grants 20,000.00 €, in words and figures («είκοσι χιλιάδων Ευρώ (20.000,00 €)»). The
  document is the act; 20,000.00 is counted. The centre's 2021 statement is not in the store to settle it.
- **Duplicates.** The Education Ministry posted its 2025 school-book decision twice (protocol 13931, two ADAs
  2.5 minutes apart, identical documents, retyped titles): counted once (`duplicate_of`).
- **Listed, not counted.** The Decentralised Administration's legality reviews of the municipality's own
  decisions (27: among them its acceptance of other bodies' money, leads to grantors not yet searched: the
  Green Fund, the Ministry of Economy's public-investment programme), its share-out of the dissolved Cyclades
  port fund (2016: 174.45 € to the port fund «Τήνου-Άνδρου»), the Culture Ministry's commitment behind its
  2018 grant, the Education Ministry's sports-facility programme notices and a 2024 commitment.

**Queries.** `SELECT * FROM v_grant_line WHERE grantor NOT IN ('interior', 'region')`; `SELECT * FROM
v_budget_month WHERE entity = '6296' AND side = 'revenue' AND kae = '2119'`.

## F11. The monthly statements: every month from February 2015 to November 2025, and when each grant arrived.

**Claim.** The municipality's monthly budget statements are now read for every month from February 2015
to November 2025 (126 monthly statements besides the 11 year-end ones), each validated to the cent against
its own totals on both sides. Their cumulative figures give what each revenue line collected in each month
(`v_budget_month`), which dates the grants found by F8-F10: the Evangelistria foundation's 25 payments are 25
jumps of line 2119 of the same amount (F10), the 2016 state-debt tranche and a desalination allocation are
December 2016's 0619 receipt to the cent after 0.15% (F8), and the Education Ministry's school books of 2024
and 2025 are December's 1219 receipts to the cent (F10).

**How** (release `0.1.0+curated7`). All 125 monthly statements of the municipality stored in Diavgeia as
Β.3 were fetched with the owner's approval (2026-09-26); `tinos build` parses 151 statements of all bodies
and refuses 10 (layouts above). The view subtracts each month's cumulative figure from the previous
statement's: `months` > 1 marks a change that spans a missing statement (October-December 2016: 3).

**Limits.** A month's figure is net of corrections booked in it (November 2022: 2119 rose 113,248.25, the
foundation paid 116,699.95). The 2026 statements are read since 2026-09-26 (F13).

**A line a statement stops printing gives its money back** (2026-09-26). When a later statement of the year no
longer prints a line, the money booked to it was moved to another: the view now carries the line at zero there
(`absent`), so the move nets out instead of counting twice. Three cases in 2015-2025: the tourism organisation's
17,460.00 (1329 in February-March 2015, 1219 from April), the advertising fee's 11,113.30 (0462 to October 2015,
0715 from November) and 23,023.41 of school cleaners' pay (1211 in February 2023, 0621 from March). 2023's line
1211 moves 23,023.41 out in March and 95,754.52 in by May, where the view had shown 72,731.11.

**A statement posted under the wrong body.** ΨΣΓΟΟΞΥΒ-ΤΣΘ, posted by the Panormos cultural centre as its December
2021 statement, bears the Tsoklis museum's letterhead and figures: the build now refuses a statement whose
letterhead names another Tinos body (`budget_rows`), so the Panormos centre's 2021 has its November statement
(6Α7ΦΟΞΥΒ-ΝΒΜ) and no year-end.

**Query.** `SELECT * FROM v_budget_month WHERE entity = '6296' AND side = 'revenue' AND kae = '2119'`.

## F12. Who else pays Tinos: the municipality's own acceptances name the grantors, and the Regional Union's, the Green Fund's and the Economy Ministry's money is booked to the cent.

**Claim.** The municipality records every grant it receives in a decision of its own before booking it
(«Αποδοχή χρηματοδότησης / επιχορήγησης / ποσού ... από ...», and from 2023 the budget amendment that follows).
Read by title (table `acceptance`: 178 acts of the municipality of 2015-2026, 126 acceptances and 52 proposals
or amendments), they name its grantors: the Interior Ministry (62), the Shipping Ministry's Secretariat for the
Aegean (14), the Regional Union of Municipalities of the South Aegean (ΠΕΔ, 11), the Region (6), the Green Fund
(6), the Economy (4), Infrastructure (4) and Digital Governance (3) ministries, the Education Ministry (3), EU
programmes (2), the Central Union of Municipalities and the Tourism Ministry (1 each), private donors (4); 5 name
none. The eight grantors not yet searched were searched and their documents read (contract section; 104 PDFs
fetched with the owner's approval). From 2015 to 2025 they gave the municipality **2,201,222.89 €** in
validated amounts, counted once, at the document that moves the money: the Economy Ministry 865,032.12, the
Aegean secretariat 537,704.28 (and 120,000.00 to the port fund, for the port of Korthi on Andros, 2018), the
Infrastructure Ministry 389,015.72, the Green Fund 283,824.00, the ΠΕΔ 82,390.00, the Recovery Fund through the
Digital Governance Ministry 25,256.77 and the tourism organisation ΕΟΤ 18,000.00. With them every money
receipt of 1219 «Λοιπές επιχορηγήσεις» in 2021-2025 is identified, 1329 «Λοιπές επιχορηγήσεις για επενδύσεις»
is identified but for 5,689.12 of February 2020, and 2024's line 1216 is to the cent (2023's but for 2,996.76 of
October).

**The Regional Union (ΠΕΔ).** Its board grants the municipality's requests («Αίτημα Δήμου Τήνου για ...»); from
2021 it pays by payment order («Χρηματικό Ένταλμα Πληρωμής») to the municipality's ΑΦΜ. The payment order is
counted; a board grant is counted only when no payment order pays it (the order cites it, or one of the same
amount follows within a year) and no later decision replaces it (`grant_decision.paid_by`). In 2022-2023 the
Union published no payment orders to Tinos (neither ΤΗΝΟΥ nor the ΑΦΜ finds one), so its grants count there.
Against 1219: July 2021, 10,000.00 = two orders of 5,000.00 (the Exomvourgo castle research, a tourism
leaflet); July 2022, 16,430.00 = the grants of 4,750.00 (volleyball), 8,680.00 (Karagoutis Training Camp, a
fourth of 34,720.00 for four islands) and 3,000.00 (a tourism convention); December 2022, 10,000.00 (a festival
with the National Opera); July 2023, 18,680.00 = 10,000.00 (Food Paths, Running Experience; its two parts in
words and figures) + 8,680.00; August 2024 and August 2025, 8,680.00 each, and November 2024, 9,920.00, by
payment order. The 2023 water-shortage campaign (9Α9ΡΟΚΔΠ-Π4Τ, 9,920.00) was not paid («δεν απορροφήθηκε»,
says the 2024 decision that grants it again) and is not counted; events the Union co-organises or procures
itself (2025's Final Four and dance festival, 2026's workshops and festival) are its own spending, listed.
Not found: the 7,200.00 for lodging ambulance staff that the municipality accepted in April 2022 (93ΓΜΩΗ6-39Κ,
with the grants above); 1211 of 2023 holds 7,200.00 more than the documents read.

**The Green Fund.** 1329 of 2018-2019, 200,000.00, is the kindergarten repair's three accounts to the cent:
9ΨΜΓ46Ψ844-ΑΑΛ 39,347.78 (July 2018), ΩΟΨΠ46Ψ844-Π2Θ 43,286.47 (September 2018) and Ω6Λ246Ψ844-Ι90 117,365.75
(June 2019; it names the municipality as payee with another body's ΑΦΜ, 998292246). Its escrow account at the
Deposits and Loans Fund: 24,800.00 for the urban mobility plan (December 2020, to the cent), 10,200.00 +
19,312.00 for the electric-charging plan (January 2023) and 29,512.00 for the accessibility plan (October 2023),
received as 29,432.00 and 29,462.00, 80.00 and 50.00 less (the Fund's charges, by the look of it). Six payments
of 2014-2018 for the Panormos spatial plan went to the study's contractors, not to the municipality: `absent`,
their payees not recorded.

**The Aegean secretariat (Shipping Ministry).** A grant is a ceiling («μέχρι του ποσού»); each payment is
approved on invoices («Εγκρίνουμε την πληρωμή»); the money moves when an order credits the project account the
municipality holds at the Bank of Greece («Εντολή κατανομής εξουσιοδοτήσεως πληρωμής», ΣΑΕ 330 / ΣΑΝΑ 233). The
transfer is counted, the approval it cites is not; an approval with no published transfer (2025-2026) counts.
The municipality books the money when it draws on the account: the 2018 and 2019 desalination rentals (11,300.00
each) are 1216 of November and December 2019; March 2024's 1322 receipt 24,468.94 is the pumps' transfers of
December 2023 and March 2024 (4,986.46 + 19,482.48) and July's 38,713.24 those of June-July 2024 (7,950.01 +
2,143.19 + 28,620.04), to the cent; October 2025's 1216 receipt 302,312.00 is the two desalination approvals of
June 2025 (117,056.00 + 185,256.00). 2021's valve-house transfer (34,352.10) was drawn as 32,390.77.

**The Economy Ministry: public investment (ΠΔΕ) for the waste-processing transition.** Transfers to the account of
project 2018ΣΕ36700029 («Επεξεργασία νέων ΑΣΑ Δήμου Τήνου - Μεταβατική περίοδος»), found by the project's code
(contract section): November 2023's 1216 receipt 160,082.90 (6ΦΠΚ46ΝΛΣΞ-27Τ; its figures and subject agree, its
words spell another transfer's 523,848.57), April 2024's 148,041.60, August's 147,968.95 and October's and
December's 293,066.22 + 193,992.45 (the Aegean secretariat's 78,120.00, the ministry's 214,946.23 and 193,992.44:
one cent booked a month early), all to the cent. The municipality pays the contractor for the same service. The
2025 transfers are not in the index (1216 of 2025 holds 424,390.45 not found).
The ministry's 2016 ΕΣΠΑ allocations (eight orders, 164,478.54 net for two Tinos projects, one of 1,500.00 reversed)
are read and listed:
the line they feed, 1328, receives other years' ΕΣΠΑ money that no indexed order names, so it is not reconciled.

**Infrastructure, Digital Governance, the tourism organisation.** The Infrastructure Ministry's 2022 transfers for
two road repairs (9,663.33 + 186,836.95 in March, 43,557.44 in October, 148,958.00 in December; the tables' rows,
some sub-rows of another project, add up to their stated totals) are 2022's investment money; the 2025 road works
it included in 2024 (Ψ3Ν1465ΧΘΞ-ΚΕΛ, 480,945.97 accepted by the municipality) have no transfer in the index. The
Recovery Fund paid 25,256.77 in December 2022 for the citizen service centres (Ψ4ΖΚ46ΜΤΛΠ-Τ0Α; category
`recovery_fund`, no line of 2022-2023 shows it) and 26,549.50 in August 2026 (F13). ΕΟΤ's 2015 payment
(7ΗΕΡ469ΗΙΖ-99Μ) is 18,000.00 less 540.00 withheld: 17,460.00, line 1219.0006 of 2015 (F8, F11).

**Fetched as leads** (the owner's approval, 2026-09-26). The school committees' yearly accounts of 2015-2021 (14)
total their grants in one line («Έσοδα από επιχορηγήσεις», mostly the municipality's transfers), so the Education
Ministry's 10,961.02 cannot be told apart in them. The Decentralised Administration's 27 ratifications of the
municipality's acceptances and budget amendments are stored, not read into the tables. The municipality's own
acceptance of 50,000.00 from the Region for clearing the roads in 2015 (7ΠΞΕΩΗ6-6ΚΧ, to 1213.0002) is the snow
clearing of F9.

**Reconciliation after F12** (release `0.1.0+curated8`; `v_grant_reconciliation`, allocated minus assessed). State grants (1211, 1215, 1219):
2019-2021 to the cent, 2022 −54,369.77, 2023 −7,200.00, 2024 −18,379.20, 2025 −11,594.93. Investment programmes
(now 1216, 1314, 1315, 1319, 1322, 1329): 2017 to the cent, 2018/2019 ±11,300.00 (timing), 2020 −5,689.12, 2021
−192,976.32, 2022 −77,068.37, 2023 −22,827.79, 2024 −9,998.90 (two transfers of December 2023 drawn in 2024),
2025 −1,003,158.97 (the Economy Ministry's 2025 transfers and the road works above, not in the index).

**Queries.** `SELECT * FROM v_acceptance_year`; `SELECT * FROM v_grant_line WHERE grantor IN ('ped', 'green_fund',
'shipping', 'economy', 'infrastructure', 'digital', 'eot')`; `SELECT ada, family, paid_by FROM grant_decision WHERE
paid_by IS NOT NULL`.

## F13. The 2026 statements: the new chart of accounts, read to the cent, and 2026 month by month.

**Claim.** The municipality's eight statements of January-August 2026 (Ρ1Α4ΩΗ6-01Ξ, Ψ1Β9ΩΗ6-25Β, ΨΝΟΧΩΗ6-Λ10,
Ψ1Ρ8ΩΗ6-94Γ, Ψ3ΔΟΩΗ6-3Τ8, 6ΝΥ8ΩΗ6-ΘΣ2, 976ΨΩΗ6-Γ4Λ, ΡΥΝΠΩΗ6-ΞΤΟ) are read and each validated to the cent
against its own «ΓΕΝΙΚΟ ΣΥΝΟΛΟ» on both sides. They use the state's economic classification, adopted by the
municipalities on 1 January 2026: every row is a 3-digit service, a dot and a 7-digit code, spending codes with a
3-digit sub-account («010.1310101 ΚΑΠ για την κάλυψη γενικών αναγκών», «010.2120101001 Βασικός μισθός ...»). The
same software printed the 2025 year-end statement, so the page is the one the 2025 layout reads; only the codes
are new. One trap: in four of the eight a wrapped title carries a row's paid figure above its warranted one, so
reading order swapped the two columns in five rows and the spending side missed its totals by equal and opposite
amounts (−54,934.40 / +54,934.40 in March). In the 2026 rows the three amounts are ordered by the column where
each ends; in the 2025 chart, whose wrapped amounts run into the title, reading order stays.

**Mapping** (`tinos.extract.grants`: the ΚΑΠ lines by name, the rest by code; `budget_line.grant_category`):

| New code | Title | Old line | Category |
|---|---|---|---|
| 1310101 | ΚΑΠ για την κάλυψη γενικών αναγκών | 0611 | kap_general |
| 1340107 | ΚΑΠ για επενδυτικές δαπάνες | 1311 / 0612 | kap_investment |
| 1310105 | ΚΑΠ για την κάλυψη των λειτουργικών αναγκών των σχολείων | 0614 / 4311 / 0616 | kap_schools |
| 1310104 | ΚΑΠ για την επισκευή και συντήρηση σχολικών κτιρίων | 1312 / 0615 | school_repairs |
| 1310106 | ΚΑΠ για πυροπροστασία | 1214 / 0614 | fire_protection |
| 1310109 | Κάλυψη δαπανών μισθοδοσίας προσωπικού καθαριότητας ... | 0621 | school_cleaners |
| 1310111 | Επιχορηγήσεις για το πρόγραμμα «Βοήθεια στο σπίτι» | 0624 | home_help |
| 1310108 | ΚΑΠ για λοιπούς σκοπούς | 0619 | kap_other |
| 1310114, 1310189 | Επιχορηγήσεις για δαπάνες διοίκησης και λειτουργίας; ... για λοιπούς σκοπούς | 1211, 1219 | state_grants |
| 1310489 | Λοιπές μεταβιβάσεις από ΟΤΑ | 1213 (in part) | programme_agreements |
| 1340101, 1340102, 1340105, 1340189 | capital grants (κτίρια, εξοπλισμός, μη παραγόμενα, λοιποί σκοποί) | 1314-1329 | investment_programmes |
| 1350109 | Απολήψεις από το Ταμείο Ανάκαμψης και Ανθεκτικότητας | 1324 | recovery_fund |
| 1130106 | Δημοτικό Τέλος Ακίνητης Περιουσίας (ΤΑΠ) | 0441 | property_tax |
| 1140918 | Δημοτικά τέλη διαφήμισης | 0715 | advertising_fee |

Not mapped: 1320389 (EU transfers, like 1217), 1390904 and 5420102 (Deposits and Loans Fund loans and their
repayment grants), 1570101 (employment subsidies). The new chart has no prior-years lines: the foundation's 10%,
booked in 2119 to 2025, is 1190989 «Διάφοροι άλλοι τρέχοντες φόροι» in 2026.

**2026 month by month** (release `0.1.0+curated8`; `v_grant_to_date`, `v_revenue_grant_month`; every grantor searched to 2026-09-26, 39
PDFs fetched). Allocated through August and booked: the Region's programme-agreement payment 12,400.00 is
February's 1310489 to the cent; fire protection 60,000.00, road waste 31,062.45, stray animals 15,900.00, school
repairs 29,100.00, lifeguards 246,387.47 (1310189, June) and desalination 171,839.05 (August) are each booked
0.15% less the month after; the schools' ΚΑΠ, 23,770.00 in January and April, likewise; the ΚΑΠ for investment,
61,402.50 in April and July, to the cent; the school cleaners' 49,392.00 of April is April's and May's
24,658.96, half each less 0.15%; the foundation's statutory grant for 2025 (ΨΓ9Λ469Β79-ΩΞΗ, 150,000.00) is July's
1190989 to the cent; the Recovery Fund's order of 7 August (99ΡΠ46ΜΤΛ6-7Υ3, three payment lines, 26,549.50) is
August's 1350109 to the cent. **Open:** the monthly ΚΑΠ for general needs, 1310101, receives 5,423.01 (January),
5,455.73 (February) and 5,439.37 (March-August) less than each month's allocation (212,674.24; 234,486.98;
223,580.61), 43,514.96 by August, while 0611 matched the allocations to the cent in 2023-2025 and the tables
show no withholding for Tinos; 1310114 «Επιχορηγήσεις για δαπάνες διοίκησης και λειτουργίας» (179,763.13) and
1340102 (96,049.09) have no document; the Aegean secretariat's approvals of 2026 (148,952.06 by August) and the
school cleaners' 7,200.00 of April are not yet booked.

**Query.** `SELECT * FROM v_grant_to_date WHERE year = 2026`; `SELECT * FROM v_revenue_grant_month WHERE year =
2026`.
