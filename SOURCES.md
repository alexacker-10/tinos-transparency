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
