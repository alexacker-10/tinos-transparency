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
`SURNAME,,NAME,FATHER` formatting of individuals; `counterparty.display_name`
is the masked name and is the only name SUMMARY.md prints. Payment-level
tables in SUMMARY.md apply the same mask on the fly.

**Reasoning.** A searchable, ranked list of named individuals by euros received
is materially different from the same facts scattered across separate decisions
on Diavgeia. The source publishes each decision so that a specific act can be
checked; it does not publish, and its legal basis does not obviously cover, a
profile of a person's total dealings with the municipality over twelve years.
Building that profile is our act, not the source's, and it is the kind of
aggregation the GDPR treats as a new processing purpose. Sole traders are
still people. Nothing is lost for accountability: every masked row carries an
ADA, and anyone with a legitimate question can follow it to the named source.

**Not covered by this decision.** Company names, even one-person companies
(ΟΕ, ΕΕ, ΙΚΕ, ΑΕ), are shown. Public office holders acting in office are shown.
Whether to publish per-person totals above some high euro threshold, or to
treat imprest-account holders (employees receiving advances, «ΥΠΟΛΟΓΟΣ
ΕΝΤΑΛΜΑΤΟΣ ΠΡΟΠΛΗΡΩΜΗΣ») differently, is left open.

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

## Principles we are working from, pending decisions

- Public office holders acting in office: name them.
- Legal entities receiving public money: name them.
- Natural persons: default to not ranking or aggregating; always link to the
  source decision so the fact remains verifiable at the source.
- Never enrich a person with data from outside the public record.
- Anything we would not want to defend in a complaint to the Hellenic DPA, do
  not publish.
