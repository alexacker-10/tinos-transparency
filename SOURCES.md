# Sources — reconnaissance record

What exists, where, how to reach it, and what it costs. Verified by probe on
2026-09-20 (`scripts/probe*.sh`, logs in `probe-out/`, not committed). Diavgeia
and ΚΗΜΔΗΣ are documented in FINDINGS.md; this file covers everything else.

## Council video — YouTube

- Channel `UCDY6BWFDvNgUg9YeYkmhS7g` (`@dimostinouwebtv`), the municipality's own.
- 330 videos on the videos tab + 109 on the streams tab = **439 unique** after
  dedup by video id. **205 are council sessions** (title matches συνεδρίαση).
- Duration: 662 hours in total, **472 hours of council sessions**.
- Coverage by year (all / sessions): 2015 88/17 · 2016 83/27 · 2017 82/31 ·
  2018 30/20 · 2019 17/14 · 2020 16/15 · **2021 absent** · **2022 1/0** ·
  2023 17/17 · 2024 26/18 · 2025 48/29 · 2026 31/17 (to September).
  Two years of sessions are simply not on the channel.
- Enumerable keylessly with `yt-dlp --flat-playlist` (upload dates are approximate
  from the tab; exact dates need a per-video call). RSS for the latest 15:
  `https://www.youtube.com/feeds/videos.xml?channel_id=UCDY6BWFDvNgUg9YeYkmhS7g`.
- No Greek captions on the sample session checked; transcription is on us.
- The municipal site's category 166 («Βίντεο Συνεδριάσεων», 46 posts) embeds the
  same video ids for sessions from 2023-12-20 onward, giving a second index.

## Local media — private, copyrighted

Link and cite. Never republish text or video. Both sites run WordPress with the
REST API open (`/wp-json/wp/v2/posts`), which makes indexing by date and category
cheap.

- **tinosnews.gr**: 8,391 posts; 844 in «Τοπική Αυτοδιοίκηση»; 46 posts in a
  «Podcast» category (feed at `/category/podcast/feed`, redirects). YouTube channel
  `UCikCfcrFBIbwhh68yrcP5KQ`.
- **tinostoday.gr**: 23,078 posts. YouTube channel `UCP6pHhVmLU1fjECEk-IDGxA`.

## Municipality web presence

- **dimostinou.gr** — current site, WordPress, `wp-json` fully open. 1,319 posts
  from 2022-08-22, 44 pages, 3,439 media items, 8 `lsvr_document`, 5 `lsvr_notice`.
  Category 166 = «Βίντεο Συνεδριάσεων».
- **dimostinou.eu** — legacy Blogger site, **4,635 posts**, roughly December 2014
  to November 2022 (the probe's oldest sample; FINDINGS.md says ~2011, to be
  reconciled by a full feed walk). **HTTP only, TLS is broken.** Feed:
  `http://dimostinou.eu/feeds/posts/default?alt=json&max-results=N&start-index=M`.
- Internet Archive was offline on probe day; the Wayback CDX sweep of both
  domains is still to do.

## ΚΗΜΔΗΣ (public procurement register)

- Base `https://cerpp.eprocurement.gov.gr/khmdhs-opendata`, keyless, CC BY 4.0,
  OpenAPI at `/v3/api-docs`. POST JSON to `/request`, `/notice`, `/contract`,
  `/auction`, `/payment`, `/pde`; `?page=N`; Spring page envelope
  (`totalElements`, `totalPages`, `content[]`, 50 per page). **It silently truncates
  any date window over 180 days and echoes nothing**: ingest only with
  `tinos khmdhs-backfill` (the verified contract is in FINDINGS.md).
- Same organisation uid as Diavgeia (`6296`); records carry `organization.key`.
- **Contract rows carry `procedureType`** (e.g. «Απευθείας ανάθεση (αρ.118/αρ. 328)»),
  amounts, CPV, the contractor (`contractingDataDetails.contractingMembersDataList[]`
  with `vatNumber`) and Diavgeia ADAs (`diavgeiaADA`, `contractRelatedADA`), the ADAs
  systematically only from 2023. Payment rows (`/payment`) name no payee; reach it
  through `contractRefNo`.
- Volume for 6296 (full backfill 2026-09-25, by submission year, 2018-2025): requests
  427-930, notices 9-454 (the jump comes in 2021), awards 240-468, contracts 153-274,
  payments 429-840 a year; 17,502 records from 2017 to September 2026, none before
  2017. (This line used to say contracts 100-143 and requests 246-493: one-year
  windows the API had truncated to their last 180 days.)
- `/adamChain/{referenceNumber}` returns the pre-built request → notice →
  contract → payment chain.

## Candidate sources, desk research 2026-09-25 (not ingested)

Read-only checks by a research pass; **re-checked** marks what was confirmed again before
writing it here. Ranked by what they would add.

- **Diavgeia full-text search ("luminapi")** — `https://opendata.diavgeia.gov.gr/luminapi/api/search`
  with `q="ΤΗΝΟΥ"` and `fq=organizationUid:"<issuer>"`, `fq=issueDate:[DT(..) TO DT(..)]`. No key,
  JSON, 100 results a page. **Re-checked**: Interior Ministry (uid 100054492) acts naming ΤΗΝΟΥ,
  1-10 Nov 2024, returns exactly 2 (ΡΟ0946ΜΤΛ6-ΣΚ8, 9ΩΖΥ46ΜΤΛ6-ΡΩΗ); no `info.query` echo, so
  any use must be checked by counts. The route to money *given to* Tinos (ΚΑΠ, «Φιλόδημος ΙΙ»,
  grants): decisions of other issuers whose annexes list the municipality (the pass found 64
  Interior Ministry acts naming Tinos in 2024; ΡΟ0946ΜΤΛ6-ΣΚ8's annex gives ΤΗΝΟΥ 236,601.93).
  Amounts sit in PDF annexes; results also hit acts about private persons, so whitelist issuers
  and subjects. The revenue side of the execution statements (`budget_line`, side `revenue`)
  already gives the totals by category to reconcile against.
- **Local-government indicators, Interior Ministry** — `https://deiktesota.gov.gr/reports/1008/view/`,
  Power BI, no export, reuse with attribution. 2024 row for Tinos (reported): financial
  independence 28.33%, direct awards 98.54% of contracts (consistent with ΚΗΜΔΗΣ: 358 of 364
  awards in 2024). Its "53.15% executed" is not our paid ÷ revised budget (47%).
- **Quarterly cash and debts bulletins** (a.107 ν.4714/2020) —
  `ypes.gr/.../oikonomika-stoicheia-ota/deltia-oikonomikon-stoicheion-ota`, PDF, every municipality
  and municipal legal person, Dec 2020 onward: cash, unpaid and overdue bills.
- **anaptyxi.gov.gr (ΕΣΠΑ projects)** — `GetData.ashx?queryType=projects_v2&...&outputFormat=json`, no
  key. **Re-checked**: the endpoint answers JSON, but the query tried returned a map aggregate, not
  projects; the pass reports 3 projects (1.92M) for 2014-20 and 6 for 2007-13. Projects run by
  other bodies (the 6.0M sewage plant, Εγνατία Οδός) are not under Tinos as beneficiary.
- **HRMS staff positions** — `hrms.gov.gr/api/public/positions?organizationCode=86551`, current
  snapshot, positions not people (reported: 120, 86 filled). No pay, no history.
- **ELSTAT 2021 census** (population, per-resident figures); **TED** (21 EU-level notices,
  2019-2026, a cross-check of ΚΗΜΔΗΣ); **Kohesio** (EU cohesion projects, bulk CSV); **ΓΕΜΗ**
  open data (key on request; companies only, never for sole traders).
- **Wayback Machine** is back: 4,667 archived dimostinou.eu post pages, 2014-2022 (reported).
- Ruled out by the pass: the Interior Ministry's internal submission systems (not public),
  EETAA's finance app (closed 2022), apografi.gov.gr (replaced by HRMS), data.gov.gr (no money
  data for Tinos), the ΜΕΦ grants registry, Greece 2.0 (only the out-of-scope art school), Court
  of Audit and Transparency Authority (nothing on Tinos), ΕΣΗΔΗΣ (no API), other Cyclades
  statements as a benchmark (Tinos is the only one publishing them regularly), and other
  transparency projects (none covers Tinos's money).

## Transcription costing (472 h of sessions)

Whisper-class models on a modern GPU run roughly 8× real time, so **~60 GPU-hours**.
- GitHub-hosted GPU runners: need a Team or Enterprise plan; about **$185** for the
  job at list price.
- Kaggle: free, 30 GPU-hours per week, so two weeks of quota; fiddly for a batch job.
- RunPod / Vast.ai spot instances: **$12-18** in total at 2026 spot prices.
- Recommendation: RunPod or Vast, audio only (`yt-dlp -f bestaudio`, ~40-60 MB per
  session), chunked, outputs committed as text with the video id and offset.

## Not used, by decision

- `data.gov.gr` token (in `.env.example`): nothing needed so far is behind it.
- YouTube Data API key: `yt-dlp` and RSS cover enumeration; the key is only needed
  if we want comments or exact publish timestamps at scale.
