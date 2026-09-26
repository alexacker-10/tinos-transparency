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
and, until late 2025, the amount too. The municipality's own year-end budget
report shows 2.93 million euros paid on staff (pay, overtime and employer
contributions) in 2024; Diavgeia's payment decisions carry amounts for about
48,000 euros of it. From late 2025 payroll batches carry an amount and the name
of one employee standing for the group. We keep the amount and drop the name.

## Since 2019, Diavgeia's payment decisions show less than half of what was paid

Each year the municipality publishes its own budget report, which says how much
it paid. Until 2018 its payment decisions on Diavgeia carried nearly all of the
non-salary payments in that report. From 2019 they carry about half, and less
since: in 2024, 4.64 of the 11.13 million euros paid, about 42%. Salaries explain
2.9 million of the gap; the rest is ordinary spending on supplies, equipment and
works. Most of those payments did not disappear: they are recorded in ΚΗΜΔΗΣ, the
national procurement register, instead of Diavgeia (66 to 87% of each year's gap
since 2019). Treat any payment total from Diavgeia alone, from 2019 on, as a floor.

## Money given to Tinos: what we can and cannot see

The Interior Ministry sends the municipality most of its outside money: a monthly share of the
central funds for municipalities (ΚΑΠ), a quarterly investment share, money for schools, fire
protection, desalination and other set purposes, and occasional extra grants. We find these
decisions by searching Diavgeia's full text for «ΤΗΝΟΥ», and, because the search index holds some
national tables by their title only, also for a word every such title carries («ΑΥΤΟΤΕΛΕΙΣ»). We read
the amount for Tinos from each decision's PDF, and count it only if the document confirms it: its
table must add up to its own total, or the letter must state the amount, or spell it out in words to
the same figure.

- **What we found.** At least 29.0 million euros from the ministry in 2015-2025, from 2.0 million
  in 2015 to 4.1 million in 2025. Where the municipality's own year-end report has a line for the
  same money, the two agree to the cent in most years; the investment share agrees to the cent in
  every year. In some years the municipality booked exactly 0.15% less than the ministry allocated;
  we do not know which charge that is.
- **What we miss.** A decision whose text was never indexed can only be found by its title.
  Searching titles found 31 such decisions with money for Tinos that had not been read before
  (2.37 million euros, eleven monthly instalments of 2017, 2021 and 2022 among them); they are now
  counted. An allocation whose title uses neither word would still be missed; searching the words of
  particular titles (lifeguards, COVID, home help, the Θησέας programme) found five more. One amount the
  municipality booked has no decision yet (the 2015 advertising fee); a 2015 welfare amount is the Labour
  Ministry's, named in the municipality's own acceptance. «At least» means exactly that.
- **A grant is not always money received.** Two 2020 grants for the municipality's overdue bills (507,722
  euros) were ceilings: the Deposits and Loans Fund would pay the creditors directly as the municipality
  asked, and the municipality never drew on them. They are listed, not counted.
- **The Region of South Aegean.** We also searched the Region's decisions and those of its development
  fund (Περιφερειακό Ταμείο Ανάπτυξης), which pays most of the Region's investment money on its behalf.
  At least 0.90 million euros in 2015-2025, counted once, at the payment that reached the municipality:
  mostly the fund's payments under programme agreements and for projects, and the landfill study's
  credits. Every payment we found is in the municipality's books to the cent, in the year it was paid.
  The 2015 snow-clearing money is counted at the Region's commitment, the last step it published. Most of
  the programme-agreement lines we could not explain before are the municipality's own port fund paying it
  under their agreements (2020, 2024, 2025): money between Tinos bodies, explained but not counted. Two
  small amounts (2017, 2023) remain unexplained. The sewage study of 2017 was the Region's own; our first count wrongly included its 39,709.88
  euros. The Region's water bills paid to the municipality are sales, shown, not counted. Before mid-2021
  the Region published no payment orders to the municipality at all (we checked all 22,529 of its
  payment decisions of 2015-2021); the fund's payments cover those years.
- **The Evangelistria foundation.** It owes the municipality 10% of its gross receipts every year. We
  found 2.50 million euros of it in 2015-2025, in 25 decisions, and every one of them appears in the
  municipality's monthly figures as a receipt of the same amount, in the same month or soon after. Two
  more receipts of about 100,000 euros (October 2015, December 2018) look like payments of the same grant
  whose decisions we cannot find; they are not counted. Eight older decisions state the amount in figures
  only, without words to check them against; they are counted and marked. The foundation's decisions
  mostly concern named people (scholarships, welfare): we keep only those about the municipality and its
  grants to public bodies, and nothing about a person.
- **Other ministries and bodies.** The Decentralised Administration's election grants of 2015 (16,043
  euros, matching the municipality's books to the cent), the Culture Ministry's grants to the Panormos
  cultural centre and the Tsoklis museum (38,000 euros), and the Education Ministry's money for school books
  and equipment (12,679 euros).
- **The grantors the municipality names itself.** The municipality records every grant in a decision
  accepting it, and most of those decisions name who pays. Searching those grantors added 2.2 million
  euros in 2015-2025: the Economy Ministry's public-investment money for the waste-processing transition
  (0.87 million), the Shipping Ministry's Aegean secretariat for desalination and water works (0.54 million,
  and 0.12 million to the port fund), the Infrastructure Ministry's road repairs of 2022 (0.39 million),
  the Green Fund (0.28 million), the Regional Union of Municipalities (82,390 euros), the Recovery Fund
  (25,257 euros) and the tourism organisation (18,000 euros). Each is counted once, at the document that
  moves the money: a transfer, not the approval it pays; a payment order, not the grant it pays; a grant
  only when no payment of it was published. Where the grantor pays into an account the municipality then
  draws on, the municipality books the money when it draws, so a transfer and its receipt can be months
  apart. Not found: the Economy Ministry's 2025 transfers and the Infrastructure Ministry's 2025 road works
  (together about a million euros of 2025's investment receipts), a 2022 grant for lodging ambulance staff
  (7,200 euros), and 5,689 euros of February 2020.
- **One ministry among several.** Money from other ministries, the Region of South Aegean and EU
  programmes reaches the same revenue lines, so for investment money and extra grants our figure is
  the share of the bodies we searched, not the whole. The property levy (ΤΑΠ) is mostly collected through
  electricity bills, so the ministry's allocation is only a small part of what the municipality
  receives from it.
- **Three decisions were published twice** (2018, 2022, 2025). We count each once.
- **Allocated is not the same as received.** An allocation decided in late December is sometimes
  booked the next year (29,762.12 euros decided on 28 December 2018 appear in 2019).

## The subsidiaries' own reports

We now read the year-end reports of five of the municipality's bodies: the port fund (2016-2025),
the Tsoklis museum, the Panormos cultural centre, the Gyrlas foundation and the municipal legal
entity (a few years each). The port fund's payment decisions on Diavgeia show nearly everything it
paid until 2021 and about a fifth since 2022, the same drop the municipality shows from 2019. The
smaller bodies rarely record which budget line a payment belongs to, so only their yearly totals can
be compared. Comparing them exposed two more port-fund payments typed in cents (100 times too
large); their documents confirm it, and they are left out of totals (FINDINGS.md F7).

## The municipality's monthly figures

We now read the municipality's monthly budget statements too, not only the year-end ones: every month
from February 2015 to November 2025, each checked against its own totals to the cent. They show when
money arrived, which is how the foundation's payments were matched. Four months are missing because
the municipality never published them (October and November 2016, January and February 2017); the
statements of December 2014 and January 2015 show one month's figures rather than the year so far, and
are not used. From January 2026 the municipality uses a new chart of accounts, with new line codes; its
eight 2026 statements (January-August) are read and each new code is matched to the old line with the same
purpose. Most 2026 grants appear in them to the cent or 0.15% less; the monthly general ΚΑΠ arrives about
5,440 euros a month short of the allocation, for a reason the documents do not show. When a statement stops
printing a line, the money was moved to another line; the monthly view treats the dropped line as zero so the
move is not counted twice. One statement posted by the Panormos cultural centre is in fact the Tsoklis
museum's, and is not used.

## Direct awards vanished from Diavgeia in 2021, not from reality

The municipality published about 350 direct-award decisions a year until 2020
and 13 in 2024. Its payments did not change. The awards continued to be recorded
in ΚΗΜΔΗΣ, the procurement register, which was always the primary venue; what
stopped was the duplicate copy in Diavgeia. For the municipality alone, ΚΗΜΔΗΣ
records 7.7 million euros of direct awards (before VAT) in 2021-2024, where
Diavgeia carries 1.5 million. Anyone using Diavgeia alone to study procurement
after 2020 will see almost nothing and conclude wrongly.

## Some big numbers are bookkeeping, not spending

- At year end the municipality *reverses* unused commitments, and the reversal is
  published as if it were a new commitment with a positive amount. Around
  50 million euros of such reversals across the corpus would double-count if
  summed. We exclude them and show the excluded amount.
- About a third of the municipality's "payments to third parties" in 2023-2024
  are taxes, social-insurance contributions and other withholdings passed through
  to the state. They are real payments but not purchases. We separate them.
- One 2018 record from a subsidiary shows a payment of 82 million euros, roughly
  four hundred times that body's annual spending. It is a data-entry error at the
  source. We keep it, flag it, and leave it out of every total.
- A 2012 record of 13.8 million euros filed as a "commitment" is in fact the
  whole annual budget summary filed under the wrong type.
- Amounts are sometimes typed wrong at the source. Thirteen verified cases, nine
  for the municipality and four for the port authority, all entered in cents (the
  amount x100), and one payment posted twice. The largest was a 2015 payment recorded as 6.5 million euros, more than
  everything the municipality paid that year; its document says 64,934.93. Two
  monthly withholdings statements (2023, 2024) had made "payments to third
  parties" look 2 million euros larger in each of those years. Together the nine
  had overstated payments by 11.8 million euros. Most were found by comparing
  payments with the municipality's own budget reports, then checked against the
  documents; they are listed in `data/manual/amount_review.yaml` and left out of
  totals. The same comparison shows a few smaller leads, and the other bodies,
  whose reports we have not parsed, have not been checked (FINDINGS.md F7).
- About 4.7 million euros of "payments" are the municipality funding its own
  subsidiaries; a further 3.3 million went to other public bodies, 1.6 million
  to taxes and 1.4 million to loan instalments and bank charges. None of that
  is procurement, and our supplier tables exclude it.

## Some records are simply missing or thin

- The municipality's commitments are complete only from 2020. Before 2017 it
  barely published them; from 2017 it published about a thousand a year, but most
  of those from 2017 and 2018, and a third from 2019, carry no amount. In 2017 the
  recorded commitments are far smaller than the reversals that refer to them.
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

From 2019 Diavgeia alone misses most small suppliers, because their payments
moved from Diavgeia to ΚΗΜΔΗΣ (see above): counted there, the municipality's
suppliers seem to fall from about 200 to under 100. Our supplier tables now add
the ΚΗΜΔΗΣ payments, and with them the count holds at about 200 to 250 a year.
Those tables are still a floor: a ΚΗΜΔΗΣ payment to a supplier that Diavgeia
also shows within two months is assumed to be already counted.

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
