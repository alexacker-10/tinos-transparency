# Limitations — read before quoting any number

This project rebuilds, from public records, what the municipality of Tinos and
its bodies spend and decide. The records are real but incomplete, and some of
them are misleading if read naively. This page lists what the data cannot tell
you, in plain language. The technical detail behind each point is in
FINDINGS.md and in the docstring of `src/tinos/curated.py`.

## Money is counted three times, on purpose, by the source

Greek public bodies publish a decision when they *reserve* money in the budget
(a commitment), when they *decide who gets a contract* (an award), and when they
*pay* (a payment). The same euro appears in all three. Our tables keep them
apart and never add them together. If you see a "total spending" figure that
adds commitments to payments, it is wrong.

## Salaries are counted but never itemised

About 8,000 payment decisions are payroll. The law withholds the employee's name
and, until late 2025, the amount too. We know the municipality paid roughly
2.2 million euros in 2024 that is not itemised anywhere; most of that is wages.
From late 2025 payroll batches carry an amount and the name of one employee
standing for the group. We keep the amount and drop the name.

## Direct awards vanished from Diavgeia in 2021, not from reality

The municipality published about 350 direct-award decisions a year until 2020
and 13 in 2024. Its payments did not change. The awards continued to be recorded
in ΚΗΜΔΗΣ, the procurement register, which was always the primary venue; what
stopped was the duplicate copy in Diavgeia. Roughly 9.5 million euros of award
value between 2021 and 2024 has no Diavgeia record. Anyone using Diavgeia alone
to study procurement after 2020 will see almost nothing and conclude wrongly.

## Some big numbers are bookkeeping, not spending

- At year end the municipality *reverses* unused commitments, and the reversal is
  published as if it were a new commitment with a positive amount. Around
  50 million euros of such reversals across the corpus would double-count if
  summed. We exclude them and show the excluded amount.
- About half of the municipality's "payments to third parties" in 2023-2024 are
  taxes, social-insurance contributions and other withholdings passed through to
  the state. They are real payments but not purchases. We separate them.
- One 2018 record from a subsidiary shows a payment of 82 million euros, roughly
  four hundred times that body's annual spending. It is a data-entry error at the
  source. We keep it, flag it, and leave it out of every total.
- A 2012 record of 13.8 million euros filed as a "commitment" is in fact the
  whole annual budget summary filed under the wrong type.
- Amounts are sometimes typed wrong at the source. One verified case: a 2015
  payment recorded as 281,880 euros whose document says 2,818.80, entered in
  cents. We have no way to check every record against its document, so a few
  wrong amounts certainly remain. Verified cases are listed in
  `data/manual/amount_review.yaml` and left out of totals.
- About 4.7 million euros of "payments" are the municipality funding its own
  subsidiaries; a further 3.3 million went to other public bodies, 1.6 million
  to taxes and 1.4 million to loan instalments and bank charges. None of that
  is procurement, and our supplier tables exclude it.

## Some records are simply missing or thin

- Commitments were not published in structured form before 2017, and in 2017 the
  published commitments are far smaller than the reversals that refer to them.
- Award decisions rarely say what was bought in a machine-readable way: the
  product classification (CPV) is filled in on fewer than one in seven.
- Council sessions on video: 2021 is entirely absent from the channel and 2022
  has a single video.
- The legacy municipal website (2014-2022) is only reachable over an insecure
  connection and has not yet been archived.
- Three subsidiaries were wound up in 2023; their series end there. The current
  year is partial.

## Thirty "pending revocation" decisions are not withdrawn payments

They are uploads the organisation tried to pull back within minutes of posting
(wrong file, double posting, wrong venue) between March 2018 and January 2020.
The central approval step never ran, so they have sat in limbo for six to eight
years. We leave them out of the money tables and keep them, labelled, in the
list of decisions.

## Concentration among suppliers is not, by itself, a finding

A handful of payees dominate any municipal ledger: the electricity utility, the
waste contractor, the water-treatment supplier, a multi-year construction
contract. The naive figures looked worse than the corrected ones because they
counted the tax office and the pension funds as "suppliers". Our concentration
tables exclude those. Use them to decide where to look, not as a conclusion.

## Dates and years

Diavgeia records the decision's civil date in Greek local time, but stored it two
different ways over the years. All our dates are computed in Athens time. If you
recompute from the raw timestamps in UTC, a few decisions move across a year
boundary and December 31 decisions move into the previous year.

## What we do not do

- We do not guess who a payroll payment went to.
- We do not merge two suppliers into one because their names look similar; only
  an identical tax number merges them.
- We do not correct the source. Every derived row points back to the exact
  stored bytes it came from.
