# Privacy — open questions

Everything this project uses is already public: Diavgeia and ΚΗΜΔΗΣ are
statutory transparency registers, the council videos are published by the
municipality, the news sites are public. Publishing it *again*, organised,
searchable and ranked, is nonetheless a different act from the source
publication, and Greek and EU data-protection law treats it as one. This file
records the questions we have not answered. Each is marked UNDECIDED until it
is not. Decisions, when taken, are recorded here with their reasoning.

## Q1. Natural persons in ranked tables — DECIDED (2026-09-21)

**Position.** Natural persons are never shown by name in ranked or aggregated
tables. They appear as «φυσικό πρόσωπο» with the ADA of a source decision, so
the underlying fact remains verifiable at the source. Their raw name and tax
number stay in the curated Parquet, because they are public in the source
registers and the layer is a faithful transform, but nothing this project
publishes prints them in a league table.

**How.** `counterparty.is_natural_person` is set from Diavgeia's own
`SURNAME,,NAME,FATHER` formatting of individuals, and, because 2026 records
dropped that form, from a second rule: a Greek 9-digit ΑΦΜ in the individual
range (first digit 0-3, excluding 08x partnerships and 09x public bodies) on a
name of at most four words with no legal-form token, or an imprest-account
holder (ΥΠΟΛΟΓΟΣ). Calibrated 2026-09-21: every `,,` name has an ΑΦΜ in that
range and no company with a legal-form token starts with 09; 764 of 1,315
counterparties are masked. `counterparty.display_name` and
`payment.counterparty_display` carry the mask and are the only names
SUMMARY.md prints. The second rule is a heuristic: a company with an
individual-range ΑΦΜ and no legal-form word in its name would be masked
(harmless), and a person whose name contains such a word would not (a gap).

**Reasoning.** A searchable, ranked list of named individuals by euros received
is materially different from the same facts scattered across separate decisions
on Diavgeia. The source publishes each decision so that a specific act can be
checked; it does not publish, and its legal basis does not obviously cover, a
profile of a person's total dealings with the municipality over twelve years.
Building that profile is our act, not the source's, and it is the kind of
aggregation the GDPR treats as a new processing purpose. Sole traders are
still people. Nothing is lost for accountability: every masked row carries an
ADA, and anyone with a legitimate question can follow it to the named source.

**Amended 2026-09-25: no per-person totals, even masked.** A masked row that
ranks one person by all-years total is still a profile of that person: the ADA
printed beside it names them at source. Natural persons are therefore left out
of every per-payee ranking and reported as one aggregate line (how many, how
much). They stay inside share calculations such as the top-10 share. A row that
is a single decision (largest single payments, suspect amounts) keeps
«φυσικό πρόσωπο» and its ADA: that is the source's own publication, not a
profile. The rule is enforced in code. `tinos summary` refuses to write a
SUMMARY.md that contains Diavgeia's person form (`SURNAME,,NAME`), a natural
person's surname and first name in either order, or their ΑΦΜ. `tinos
privacy-check` runs the same check over every file git tracks, because the
repository is public; run it before pushing. It does not catch names in
inflected forms (a genitive in a subject line).

**Not covered by this decision.** Company names, even one-person companies
(ΟΕ, ΕΕ, ΙΚΕ, ΑΕ), are shown. Public office holders acting in office are shown.
Whether to publish per-person totals above some high euro threshold is left
open. Imprest-account holders («ΥΠΟΛΟΓΟΣ ΕΝΤΑΛΜΑΤΟΣ ΠΡΟΠΛΗΡΩΜΗΣ») are masked
as natural persons since they are employees.

## Q2. Welfare and hardship decisions — UNDECIDED

Some decisions grant emergency financial aid («χορήγηση χρηματικού βοηθήματος»)
or relate to employment-support schemes, and name the beneficiaries. These
reveal a person's financial distress or employment status. The source publishes
them; whether we should index, display or even keep them in derived tables is
open. Current handling: rows whose payee is a group of named individuals are
classed as payroll and the names dropped; single named beneficiaries of welfare
decisions are not yet specially handled.

## Q3. Private citizens in council video — UNDECIDED

Council sessions include members of the public speaking, being named, or being
discussed (planning objections, disputes, personal circumstances). Transcribing
472 hours and making the text searchable changes who can find what about whom.
Open questions: whether to transcribe public-comment segments at all; whether to
publish full transcripts or only summaries and timestamps; whether to redact
names of non-officials.

## Q4. Employee names that leak through the source — DECIDED, partially

From late 2025 payroll batches name one representative employee. We drop the name
and tax number at the curated layer and keep the amount. Reasoning: the person is
an employee, not a counterparty, and the invariant "payroll beneficiaries are
absent by design" applies regardless of the source's formatting choice.
Still open: single-person payroll acts with a payroll-worded subject are handled
the same way, but the rule is a text heuristic and may miss cases.

## Q5. Council members and signatories — UNDECIDED

Signer ids are kept in `act.signer_ids`. Resolving them to names (public office
holders acting in office) is almost certainly fine; publishing per-signer
statistics ("who signed the most direct awards") is a judgement we have not made.

## Q6. ΚΗΜΔΗΣ records — DECIDED (2026-09-25)

ΚΗΜΔΗΣ records name more people than Diavgeia metadata does: the email of the
civil servant who entered each record (`authorEmail`), the signers, and the
contractor's name and ΑΦΜ, sole traders included. They are stored in
`data/raw/khmdhs` (not tracked in git).

**Position**, proposed and approved by the project owner on 2026-09-25: the
curated layer never carries `authorEmail`, signers or any other official's
name (Q5 still governs signers); contractors are treated exactly as Diavgeia
counterparties under Q1: legal entities named, natural persons (sole traders
included) shown as «φυσικό πρόσωπο», never ranked or totalled per person, with
the raw name and ΑΦΜ kept in the curated layer only for joins and checks.
The same `is_natural_person` rule applies, and `tinos privacy-check` guards
what is published. Payment records also carry each supplier's street address
and postcode (a home address for a sole trader): never carried into the curated
layer.

## Q7. Full-text search hits about private people — DECIDED (2026-09-25)

Diavgeia's full-text search is how we find other bodies' decisions giving
money to Tinos (FINDINGS.md, "Diavgeia full-text search"). A search for ΤΗΝΟΥ
at the Interior Ministry also returns decisions about private people: grants
of Greek citizenship naming the person, staff allocations, appointments and
transfers, detainee transport by the Tinos police station, day-care vouchers
naming the owners of private nurseries (a street called Τήνου in Attica).

**Position**, set by the project owner in the brief for this phase: keep
nothing about them beyond what the guard needs. `tinos fulltext-backfill`
applies a whitelist before anything is written
(`tinos.sources.fulltext.whitelist_reason`): a decision is kept only if its
subject is about allocations, grants, financing or programme inclusion, or it
is a Β.1.1 public-investment act, and never if the subject is about people
(citizenship, staff, posts, imprest holders, committees, election teams,
detainees, donors, day-care vouchers; that rule is checked first). Every other
hit is cut, in the stored page, to its ADA, issuer, co-issuers, issue date and
status, the fields the guard checks; its subject and text snippet are dropped
in memory and the response body is not kept (its SHA-256 is in the ingest
log). The ingest log records only counts of what was dropped and why.

**Reasoning.** The raw layer normally keeps bytes as fetched. Here that would
mean building, as a side effect of a search about municipal money, a local
index of people who were naturalised or detained with a Tinos connection:
data we have no purpose for. The ADA of a dropped hit is kept because the
guard needs it (paging, dedup) and it only points to the public source.

**Not covered.** A whitelisted allocation table can still name a person in
a row we do not parse; the stored PDFs are raw data, never published.

## Principles we are working from, pending decisions

- Public office holders acting in office: name them.
- Legal entities receiving public money: name them.
- Natural persons: default to not ranking or aggregating; always link to the
  source decision so the fact remains verifiable at the source.
- Never enrich a person with data from outside the public record.
- Anything we would not want to defend in a complaint to the Hellenic DPA, do
  not publish.
