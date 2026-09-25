"""Curated layer: pure functions from ``data/raw`` to Parquet in ``data/curated``.

Nothing here is hand-edited and nothing here touches the network. Every
output row carries ``source_ada``, ``source_sha256`` (the SHA-256 of the
exact stored file it was derived from), ``derived_at`` and
``pipeline_version``, so any figure can be traced back to bytes on disk.

Tables
------
act          one row per stored act (every status).
payment      one row per Β.2.2 sponsor line, or one payroll row when the
             sponsor list is empty.
commitment   one row per Β.1.3 ΚΑΕ line, or one row from the act-level
             amount when there are no ΚΑΕ lines.
award        one row per Δ.1 / Δ.2.2 awardee, or one row with no awardee.
counterparty one row per distinct ΑΦΜ seen on payment lines.
entity       the registry in ``entities.yaml``.
budget_line  one row per ΚΑΕ line of every stored budget execution statement
             (Β.3 PDF in ``data/raw/diavgeia/docs``), parsed by
             ``tinos.extract.statements`` and kept only if every column sums
             to the document's own totals to the cent. The municipality's own
             account of what was paid: the denominator for Diavgeia payments.

DO NOT SUM ACROSS TABLES. ``payment`` (money that left the account),
``commitment`` (budget reserved) and ``award`` (contract value decided)
are three different measures of the same spending; the same euro appears in
all three. Each table's total is meaningful on its own only.

Status handling. ``act`` keeps every status. The three measure tables carry
PUBLISHED and REVOKED rows, tagged with ``act_status``; consumers should
filter to PUBLISHED for totals and look at REVOKED separately. Acts in
PENDING_REVOCATION are excluded from the measure tables altogether: the
version logs show they are mis-uploads (wrong file, double posting, wrong
venue) that the organisation tried to pull within minutes and the central
operator never processed. They are not withdrawn spending.

Payroll. Three shapes, all ``is_payroll = true`` with NO counterparty:
- ``payroll_kind = 'no_sponsor'``: empty or null sponsor list, the historical
  form. Diavgeia withholds the employee by design; the amount is absent too.
- ``payroll_kind = 'batch'``: from late 2025 the municipality posts payroll
  batches with a sponsor line naming one representative employee plus
  "& ΛΟΙΠΟΙ" (and others) and that person's ΑΦΜ. The amount is kept, the
  name and ΑΦΜ are dropped here: they identify an employee, not a supplier.
- ``payroll_kind = 'named'``: a payroll-worded subject (μισθοδοσία, αποδοχές,
  υπερωρίες) whose sponsor is a natural person. Same treatment.
- ``payroll_kind = 'personnel_kae'``: a natural person paid under the
  personnel-cost group of the chart (old major 60, new major 21): school
  crossing guards, trainees, compensation of staff. Same treatment.
Do not try to attribute payroll rows to anyone.

Dates. ``issueDate`` is a Greek civil date stored as local midnight up to
2014 and UTC midnight afterwards (FINDINGS.md). All dates and years here are
computed in Europe/Athens.

Flags (deterministic, documented, never applied by hand):
- ``payment.kae_scheme`` / ``kae_major``: ``old`` is the classic municipal
  chart (``00.8231.0004`` -> major ``82``), ``bare`` the same code without a
  service prefix (``8211``), ``new`` the chart adopted by Δήμος Τήνου in 2026
  (``055.2120102001`` -> major ``21``, the first two digits of the 7-digit code).
  New-chart groups seen so far, from subject sampling: 21 personnel, 22
  supplies, 23 transfers and levies, 24 services, 27 rents, 31 fixed assets,
  45 contributions, 59 αποδόσεις (remittances).
  ``is_remittance`` marks old-chart major 82 or new-chart major 59, OR a
  subject naming withholdings (κρατήσεις), which catches the same payees on
  lines posted without a ΚΑΕ. Real payments, not supplier spending; they dominate
  any naive "top counterparties" list.
- ``payment.amount_suspect`` marks a single line above 10,000,000 EUR. No
  Tinos body has a budget that size; the one hit is a withholdings statement
  four hundred times its entity's annual payments, i.e. a data-entry error at
  source. Kept, flagged, excluded from the ``v_*`` views.
- ``commitment.is_reversal`` marks year-end reversals (``Ανατροπές``,
  ``Ανάκληση``) and the ``recalledExpenseDecision`` flag. Diavgeia posts
  reversals as Β.1.3 with a POSITIVE amount and the flag is unreliable, so an
  unfiltered sum counts the same money twice. Before 2017 Β.1.3 is used
  inconsistently (budget summaries appear under it); treat early years as
  unreliable.

- ``payment.payee_class`` classifies every non-payroll line, first match wins:
  ``internal_transfer`` (ΑΦΜ of an entity in entities.yaml: the municipality
  funding its own bodies, not procurement) → ``remittance`` (above) → ``tax``
  (old-chart ΚΑΕ major 63, taxes and fees, or a tax-authority payee: Ministry
  of Finance, ΔΟΥ, ΑΑΔΕ, or an ΕΝΦΙΑ / interest-tax subject; ΚΑΕ 63 also catches
  interest-withholding tax settled through banks and regulator levies) →
  ``debt_service`` (ΚΑΕ major 65: loan instalments, bank and card-processing
  charges; or a bank / Ταμείο Παρακαταθηκών payee) → ``other_public_body`` (a payee
  whose name marks it as state, region, another municipality or its bodies,
  a social-insurance fund, regulator, chamber or hospital) → ``supplier``.
  Utilities (ΔΕΗ, ΕΛΤΑ, ΔΕΔΔΗΕ) stay suppliers: they sell a service. Grants to
  clubs and churches (ΚΑΕ 67) also stay ``supplier`` for now.
- ``payment.suspect_reason``: ``threshold`` (above) or ``document_mismatch``,
  applied from ``data/manual/amount_review.yaml`` where a human compared the
  metadata amount with the PDF and found it wrong (Ω25ΙΩΗ6-ΟΜΘ: 281,880.00 in
  the metadata, 2,818.80 in the document; entered in cents). An entry with
  ``line_no`` flags that sponsor line only, and the build fails if the line no
  longer carries the recorded ``metadata_amount``; without it, every line of
  the act is flagged. ``duplicate_posting``: every line of an act listed under
  ``duplicate`` there, a second posting of a payment order another act already
  records (``duplicate_of``); the build fails unless both acts are held.

Counterparties. Resolution is exact-ΑΦΜ only. Name variants are collected,
never fuzzy-merged. ``needs_review`` flags an ΑΦΜ whose format is not a
9-digit Greek number or whose names differ beyond whitespace, case and
punctuation. ``is_natural_person`` is set from Diavgeia's ``SURNAME,,NAME,FATHER``
form, or, because 2026 records drop that form, from a Greek 9-digit ΑΦΜ in
the individual range (first digit 0-3, not 08x partnerships or 09x public
bodies) on a name with at most four words and no legal-form token (ΟΕ, ΕΕ,
ΑΕ, ΙΚΕ, ΕΠΕ, ΚΑΙ ΣΙΑ, ΑΦΟΙ, ΕΤΑΙΡΕΙΑ, ...), or on an imprest-account holder
(ΥΠΟΛΟΓΟΣ). Sole traders are natural persons. The raw name stays in the Parquet (it is public at source) but
``display_name`` / ``counterparty_display`` is "φυσικό πρόσωπο" for natural persons
and is the only name anything published may print, with an ADA so the fact can be
verified at source. ``tinos privacy-check`` enforces it. See PRIVACY.md Q1.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq

from tinos import __version__
from tinos.config import Settings, load_registry

CURATED_SCHEMA_VERSION = 2  # 2: budget_line
PIPELINE_VERSION = f"{__version__}+curated{CURATED_SCHEMA_VERSION}"
ATHENS = ZoneInfo("Europe/Athens")
UTC = timezone.utc

PAYMENT_TYPES = {"Β.2.2"}
COMMITMENT_TYPES = {"Β.1.3"}
AWARD_TYPES = {"Δ.1", "Δ.2.2"}
MEASURE_STATUSES = {"PUBLISHED", "REVOKED"}  # PENDING_REVOCATION excluded by design

_AFM_RE = re.compile(r"^\d{9}$")
_KAE_OLD_RE = re.compile(r"^(\d{2})[.\-](\d{4})")
_KAE_BARE_RE = re.compile(r"^(\d{4})(\.\d+)?$")
_KAE_NEW_RE = re.compile(r"^\d{3}\.\d{7}")
_REVERSAL_RE = re.compile(r"ανατροπ|ανακλησ", re.IGNORECASE)
_WITHHOLDING_RE = re.compile(r"κρατησ", re.IGNORECASE)
_PAYROLL_SUBJECT_RE = re.compile(r"μισθοδοσ|αποδοχ|υπερωρι", re.IGNORECASE)
_BATCH_NAME_RE = re.compile(r"(&|\bΚΑΙ)\s*ΛΟΙΠ(ΟΙ|ΕΣ|ΩΝ)", re.IGNORECASE)
_LEGAL_FORM_RE = re.compile(
    r"(?<![^\W\d_])(ΟΕ|Ο\.Ε\.?|ΕΕ|Ε\.Ε\.?|ΑΕ|Α\.Ε\.?|ΑΕΒΕ|ΑΒΕΕ|ΑΤΕ|ΟΕΕ|ΕΠΕ|Ε\.Π\.Ε\.?|ΙΚΕ|Ι\.Κ\.Ε\.?|ΜΕΠΕ|ΝΕ|ΝΕΠΑ|"
    r"LTD|LIMITED|INC|GMBH|SA|S\.A\.?|A\.E\.?|PLC|LLC|ΑΦΟΙ|ΣΙΑ|ΜΟΝΗ|ΝΑΟΣ|ΔΗΜΟΣ|ΤΑΜΕΙΟ|ΕΝΩΣΗ|ΚΕΝΤΡΟ|ΟΜΙΛΟΣ)(?![^\W\d_])|"
    r"ΜΟΝΟΠΡΟΣΩΠ|ΕΤΑΙΡ|ΣΥΝΕΤΑΙΡ|ΕΠΙΧΕΙΡΗΣ|ΟΡΓΑΝΙΣΜ|ΙΔΡΥΜΑ|ΣΩΜΑΤΕΙ|ΣΥΛΛΟΓ|ΥΠΟΥΡΓΕΙ|ΚΟΙΝΟΠΡΑΞ|ΚΟΙΝΩΝΙΑ|ΑΣΤΙΚΗ|"
    r"ΕΚΚΛΗΣ|ΣΥΝΔΕΣΜ|ΙΝΣΤΙΤΟΥΤ|ΣΥΝΔΙΚ|ΕΠΙΜΕΛΗΤ|ΤΡΑΠΕΖ|BANK|ΤΕΧΝΙΚ|ΚΑΤΑΣΚΕΥ|ΕΜΠΟΡ|ΒΙΟΤΕΧΝ|ΒΙΟΜΗΧΑΝ|SOLUTIONS|"
    r"SERVICES?|CONSULT|SYSTEMS?|GROUP|ΠΑΝΕΠΙΣΤΗΜ|UNIVERSIT|ΕΠΙΤΡΟΠ|ΣΧΟΛ|ΔΙΚΤΥΟ|ΕΡΓΑΣΤΗΡ|ΞΕΝΟΔΟΧ|ΓΡΑΦΕΙ|ΦΑΡΜΑΚΕΙ",
    re.IGNORECASE)
_IMPREST_RE = re.compile(r"ΥΠΟΛΟΓΟΣ", re.IGNORECASE)
PERSONNEL_KAE_MAJOR = {"old": "60", "bare": "60", "new": "21"}
NEW_REMITTANCE_KAE_MAJOR = "59"
_PERSON_NAME_RE = re.compile(r",,")
_TAX_PAYEE_RE = re.compile(
    r"ΥΠΟΥΡΓΕΙΟ ΟΙΚΟΝΟΜ|ΑΑΔΕ|ΑΝΕΞΑΡΤΗΤΗ ΑΡΧΗ ΔΗΜΟΣΙΩΝ ΕΣΟΔΩΝ|ΦΟΡΟΛΟΓ|ΤΕΛΩΝΕΙ|(?<![^\W\d_])Δ\.?Ο\.?Υ(?![^\W\d_])",
    re.IGNORECASE)
# ΦΠΑ deliberately absent: ordinary invoices mention VAT in the subject.
_TAX_SUBJECT_RE = re.compile(r"ΕΝΦΙΑ|ΦΟΡΟΣ ΕΙΣΟΔ|ΦΟΡΟΥ? ΤΟΚΩΝ", re.IGNORECASE)
_DEBT_PAYEE_RE = re.compile(r"ΤΡΑΠΕΖ|(?<![^\W\d_])BANK(?![^\W\d_])|ΠΑΡΑΚΑΤΑΘΗΚ|(?<![^\W\d_])ALPHA(?![^\W\d_])|EUROBANK", re.IGNORECASE)
_PUBLIC_BODY_RE = re.compile(
    r"ΔΗΜΟΣ |ΔΗΜΟΤΙΚ|ΠΕΡΙΦΕΡΕΙ|ΥΠΟΥΡΓΕΙ|ΦΟΔΣΑ|ΦΟ\.Δ\.Σ\.Α|ΛΙΜΕΝΙΚΟ ΤΑΜΕΙΟ|ΟΡΓΑΝΙΣΜΟΣ ΛΙΜΕΝ|ΡΥΘΜΙΣΤΙΚΗ ΑΡΧΗ|"
    r"ΕΦΚΑ|ΕΘΝΙΚΟΣ ΦΟΡΕΑΣ ΚΟΙΝ|(?<![^\W\d_])ΙΚΑ(?![^\W\d_])|ΤΑΜΕΙΟ ΠΡΟΝΟΙΑΣ|ΟΠΑΔ|ΤΕΑΔΥ|ΤΑΔΚΥ|ΤΥΔΚΥ|ΤΠΔΥ|ΤΠΔΚΥ|ΜΤΠΥ|"
    r"ΕΤΑΑ|ΤΜΕΔΕ|ΤΣΜΕΔΕ|ΕΑΔΗΣΥ|Ε\.Α\.ΔΗ\.ΣΥ|ΕΝΙΑΙΑ ΑΡΧΗ ΔΗΜΟΣΙΩΝ ΣΥΜΒΑΣΕΩΝ|ΟΑΕΔ|ΔΥΠΑ|ΕΟΠΥΥ|"
    r"ΚΕΔΕ|ΕΕΤΑΑ|ΑΠΟΚΕΝΤΡΩΜΕΝ|ΕΛΛΗΝΙΚΟ ΔΗΜΟΣΙΟ|ΟΡΓΑΝΙΣΜΟΣ ΠΕΡΙΘΑΛΨ|ΝΟΣΟΚΟΜΕΙ|ΚΕΝΤΡΟ ΥΓΕΙΑΣ|ΠΑΝΕΠΙΣΤΗΜΙ|"
    r"ΣΧΟΛΙΚΗ ΕΠΙΤΡΟΠ|ΚΟΙΝΩΦΕΛΗΣ ΕΠΙΧΕΙΡΗΣΗ|ΑΝΑΠΤΥΞΙΑΚ\w* ΟΡΓΑΝΙΣΜ|ΠΟΛΕΜΙΚΟΥ ΝΑΥΤΙΚΟΥ|ΕΠΙΜΕΛΗΤΗΡΙ|ΕΝΩΣΗ ΛΙΜΕΝΩΝ|"
    r"ΚΤΗΜΑΤΟΛΟΓ|ΕΛ\.?Γ\.?Α(?![^\W\d_])|ΑΣΦΑΛΙΣΤΙΚ\w* ΤΑΜΕΙ|ΤΑΜΕΙΟ \w*ΑΣΦΑΛ|ΕΘΝΙΚΟ ΚΕΝΤΡΟ|ΓΕΝΙΚΟ ΛΟΓΙΣΤΗΡΙΟ|"
    r"ΕΛΛΗΝΙΚΗ ΑΣΤΥΝΟΜ|ΠΥΡΟΣΒΕΣΤΙΚ|ΛΙΜΕΝΑΡΧΕΙ|ΕΙΡΗΝΟΔΙΚΕΙ|ΠΡΩΤΟΔΙΚΕΙ|ΔΙΚΑΣΤΗΡΙ",
    re.IGNORECASE)
PAYEE_CLASSES = ("payroll", "internal_transfer", "remittance", "tax", "debt_service", "other_public_body", "supplier")
SUSPECT_PAYMENT_EUR = 10_000_000.0
REMITTANCE_KAE_MAJOR = "82"


# ---------------------------------------------------------------------------
# raw access
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RawAct:
    path: Path
    sha256: str
    doc: dict[str, Any]

    @property
    def ada(self) -> str:
        return self.doc["ada"]

    @property
    def ev(self) -> dict[str, Any]:
        return self.doc.get("extraFieldValues") or {}


def iter_raw_acts(raw_dir: Path) -> Iterable[RawAct]:
    """Yield every stored act with the hash of its exact bytes."""
    base = raw_dir / "diavgeia" / "acts"
    for path in sorted(base.glob("*/*.json")):
        data = path.read_bytes()
        yield RawAct(path, hashlib.sha256(data).hexdigest(), json.loads(data))


# ---------------------------------------------------------------------------
# small pure helpers
# ---------------------------------------------------------------------------
def athens_date(ms: int | None) -> date | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, UTC).astimezone(ATHENS).date()


def utc_ts(ms: int | None) -> datetime | None:
    return None if ms is None else datetime.fromtimestamp(ms / 1000, UTC)


def as_list(v: Any) -> list:
    """Diavgeia emits some list fields as null or as a bare dict."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def amount_of(v: Any) -> float | None:
    """``{"amount": 12.3, "currency": "EUR"}`` -> 12.3; missing amount -> None."""
    if isinstance(v, dict):
        a = v.get("amount")
        return float(a) if a is not None else None
    return None


def currency_of(v: Any) -> str | None:
    return v.get("currency") if isinstance(v, dict) else None


def afm_name(v: Any) -> tuple[str | None, str | None, str | None]:
    """sponsorAFMName / person -> (afm, afm_type, raw name)."""
    if not isinstance(v, dict):
        return None, None, None
    afm = v.get("afm")
    return (str(afm) if afm is not None else None, v.get("afmType"), v.get("name"))


def related_adas(ev: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for item in as_list(ev.get("relatedEkgrisiDapanis")):
        if isinstance(item, dict) and item.get("textRelatedADA"):
            out.append(item["textRelatedADA"])
    for item in as_list(ev.get("relatedDecisions")):
        if isinstance(item, dict) and item.get("relatedDecisionsADA"):
            out.append(item["relatedDecisionsADA"])
    if ev.get("textRelatedADA"):
        out.append(ev["textRelatedADA"])
    return sorted(set(out))


def parse_kae(kae: str | None) -> tuple[str | None, str | None]:
    """-> (scheme, major). ``00.8231.0004`` -> ('old','82'); ``8211`` -> ('bare','82');
    ``055.2120102001`` -> ('new','21'); anything else -> ('unknown', None)."""
    if not kae or not kae.strip():
        return None, None
    k = kae.strip()
    if m := _KAE_OLD_RE.match(k):
        return "old", m.group(2)[:2]
    if m := _KAE_BARE_RE.match(k):
        return "bare", m.group(1)[:2]
    if _KAE_NEW_RE.match(k):
        return "new", k.split(".", 1)[1][:2]
    return "unknown", None


def kae_major(kae: str | None) -> str | None:
    return parse_kae(kae)[1]


def strip_accents(s: str | None) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def is_reversal_subject(subject: str | None) -> bool:
    return bool(_REVERSAL_RE.search(strip_accents(subject)))


def is_withholding_subject(subject: str | None) -> bool:
    return bool(_WITHHOLDING_RE.search(strip_accents(subject)))


def is_natural_person_name(name: str | None) -> bool:
    return bool(name and _PERSON_NAME_RE.search(name))


def is_natural_person(name: str | None, afm: str | None, afm_type: str | None) -> bool:
    """Diavgeia's ``,,`` form, an imprest-account holder, or an individual-range
    Greek ΑΦΜ on a short name without a legal-form token (see docstring)."""
    if not name:
        return False
    if _PERSON_NAME_RE.search(name) or _IMPREST_RE.search(strip_accents(name)):
        return True
    if not afm or not _AFM_RE.match(afm) or (afm_type and afm_type != "EL"):
        return False
    if afm[0] not in "0123" or afm[:2] in ("08", "09"):
        return False
    n = strip_accents(name).upper()
    if len(n.split()) > 4 or _LEGAL_FORM_RE.search(n):
        return False
    return True


def classify_payee(*, afm: str | None, name: str | None, subject: str | None, kae_major: str | None,
                   is_remittance: bool, family_afms: frozenset[str]) -> str:
    """First matching rule wins; see module docstring for the rationale of each."""
    n = strip_accents(name).upper()
    subj = strip_accents(subject)
    if afm and afm in family_afms:
        return "internal_transfer"
    if is_remittance:
        return "remittance"
    if kae_major == "63" or _TAX_PAYEE_RE.search(n) or _TAX_SUBJECT_RE.search(subj):
        return "tax"
    if kae_major == "65" or _DEBT_PAYEE_RE.search(n):
        return "debt_service"
    if _PUBLIC_BODY_RE.search(n):
        return "other_public_body"
    return "supplier"


def load_amount_review(path: Path) -> dict[str, dict[str, Any]]:
    """data/manual/amount_review.yaml -> {ada: entry} for documented mismatches."""
    return _review_section(path, "mismatch")


def load_duplicate_postings(path: Path) -> dict[str, dict[str, Any]]:
    """data/manual/amount_review.yaml -> {ada: entry} for acts that re-post another act's payment."""
    return _review_section(path, "duplicate")


def _review_section(path: Path, key: str) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    import yaml
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(e["ada"]): e for e in doc.get(key) or []}


def review_flags_line(entry: dict[str, Any] | None, i: int, kae: Any, amount: float | None) -> bool:
    """True when a review entry flags sponsor line ``i`` of its act.

    An entry without ``line_no`` flags every line of the act. With ``line_no``
    it flags that line only, and the line must still carry the recorded
    ``metadata_amount`` (and ``kae``, if given): a re-published act whose lines
    moved must fail the build, not silently flag the wrong euro.
    """
    if entry is None:
        return False
    if entry.get("line_no") is None:
        return True
    if int(entry["line_no"]) != i:
        return False
    want_kae = entry.get("kae")
    if amount is None or round(amount, 2) != round(float(entry["metadata_amount"]), 2) or (
            want_kae is not None and str(kae) != str(want_kae)):
        raise ValueError(f"amount_review: {entry['ada']} line {i} is now kae={kae} amount={amount}; "
                         f"the entry expects kae={want_kae} amount={entry['metadata_amount']}")
    return True


def payroll_kind_of(name: str | None, subject: str | None) -> str | None:
    """'batch' for "X & ΛΟΙΠΟΙ" sponsors, 'named' for a payroll-worded act paid
    to a natural person, else None."""
    if name and _BATCH_NAME_RE.search(strip_accents(name)):
        return "batch"
    if name and _PERSON_NAME_RE.search(name) and _PAYROLL_SUBJECT_RE.search(strip_accents(subject)):
        return "named"
    return None


def normalise_name(name: str) -> str:
    """Whitespace, case, punctuation and accent-insensitive key for variant grouping."""
    s = unicodedata.normalize("NFD", name)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^\w]+", " ", s, flags=re.UNICODE)
    return " ".join(s.upper().split())


def digest_of_hashes(hashes: Iterable[str]) -> str:
    """One hash standing for a set of source files (sorted, newline-joined)."""
    return hashlib.sha256("\n".join(sorted(set(hashes))).encode()).hexdigest()


# ---------------------------------------------------------------------------
# row builders (pure: RawAct -> list[dict])
# ---------------------------------------------------------------------------
def act_row(a: RawAct, stamp: dict[str, Any]) -> dict[str, Any]:
    d = a.doc
    return {
        "ada": a.ada,
        "entity": str(d.get("organizationId")),
        "type": d.get("decisionTypeId"),
        "date": athens_date(d.get("issueDate")),
        "year": athens_date(d.get("issueDate")).year if d.get("issueDate") is not None else None,
        "subject": d.get("subject"),
        "status": d.get("status"),
        "signer_ids": [str(s) for s in as_list(d.get("signerIds"))],
        "unit_ids": [str(u) for u in as_list(d.get("unitIds"))],
        "thematic_ids": [str(t) for t in as_list(d.get("thematicCategoryIds"))],
        "protocol_number": d.get("protocolNumber"),
        "document_type": a.ev.get("documentType"),
        "version_id": d.get("versionId"),
        "corrected_version_id": d.get("correctedVersionId"),
        "submission_ts": utc_ts(d.get("submissionTimestamp")),
        "publish_ts": utc_ts(d.get("publishTimestamp")),
        "document_url": d.get("documentUrl"),
        "source_ada": a.ada,
        "source_path": str(a.path),
        "source_sha256": a.sha256,
        **stamp,
    }


def payment_rows(a: RawAct, stamp: dict[str, Any], family_afms: frozenset[str] = frozenset(),
                 review: dict[str, dict[str, Any]] | None = None,
                 duplicates: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Β.2.2 -> one row per sponsor line; empty/null sponsor -> one payroll row."""
    d, ev = a.doc, a.ev
    entry = review.get(a.ada) if review else None
    duplicate = bool(duplicates and a.ada in duplicates)
    base = {
        "entity": str(d.get("organizationId")),
        "date": athens_date(d.get("issueDate")),
        "year": athens_date(d.get("issueDate")).year,
        "act_status": d.get("status"),
        "related_ada": related_adas(ev),
        "skip_vat_reason": ev.get("skipVatReason"),
        "source_ada": a.ada,
        "source_sha256": a.sha256,
        **stamp,
    }
    sponsors = as_list(ev.get("sponsor"))
    if entry is not None and entry.get("line_no") is not None and not 0 <= int(entry["line_no"]) < len(sponsors):
        raise ValueError(f"amount_review: {a.ada} has {len(sponsors)} sponsor line(s); "
                         f"no line_no {entry['line_no']}")
    if not sponsors:
        return [{
            "payment_id": f"{a.ada}:payroll", "line_no": 0, "is_payroll": True, "payroll_kind": "no_sponsor",
            "payee_class": "payroll", "payee_class_rule": "line", "is_internal_transfer": False,
            "counterparty_display": None,
            "amount": None, "currency": None, "kae": None, "kae_scheme": None, "kae_major": None, "cpv": [],
            "is_remittance": False, "amount_suspect": False, "suspect_reason": None,
            "counterparty_afm": None, "counterparty_afm_type": None, "counterparty_name_raw": None,
            **base,
        }]
    rows = []
    for i, s in enumerate(sponsors):
        afm, afm_type, name = afm_name(s.get("sponsorAFMName"))
        amt = amount_of(s.get("expenseAmount"))
        scheme, major = parse_kae(s.get("kae"))
        kind = payroll_kind_of(name, d.get("subject"))
        natural = is_natural_person(name, afm, afm_type)
        if kind is None and natural and major is not None and major == PERSONNEL_KAE_MAJOR.get(scheme or ""):
            kind = "personnel_kae"
        if kind:
            # An employee, not a supplier: keep the euros, drop the person.
            afm = afm_type = name = None
        remit = kind is None and (
            (scheme in ("old", "bare") and major == REMITTANCE_KAE_MAJOR)
            or (scheme == "new" and major == NEW_REMITTANCE_KAE_MAJOR)
            or is_withholding_subject(d.get("subject")))
        klass = "payroll" if kind else classify_payee(
            afm=afm, name=name, subject=d.get("subject"), kae_major=major,
            is_remittance=remit, family_afms=family_afms)
        over = amt is not None and amt > SUSPECT_PAYMENT_EUR
        doc_mismatch = review_flags_line(entry, i, s.get("kae"), amt)
        flagged = over or doc_mismatch or duplicate
        rows.append({
            "payment_id": f"{a.ada}:{i}", "line_no": i, "is_payroll": kind is not None, "payroll_kind": kind,
            "payee_class": klass, "payee_class_rule": "line", "is_internal_transfer": klass == "internal_transfer",
            "counterparty_display": None if kind else ("φυσικό πρόσωπο" if natural else name),
            "amount": amt, "currency": currency_of(s.get("expenseAmount")),
            "kae": s.get("kae"), "kae_scheme": scheme, "kae_major": major, "cpv": [str(c) for c in as_list(s.get("cpv"))],
            "is_remittance": remit,
            "amount_suspect": flagged,
            "suspect_reason": ("threshold" if over else "document_mismatch" if doc_mismatch
                               else "duplicate_posting" if duplicate else None),
            "counterparty_afm": afm, "counterparty_afm_type": afm_type, "counterparty_name_raw": name,
            **base,
        })
    return rows


def commitment_rows(a: RawAct, stamp: dict[str, Any]) -> list[dict[str, Any]]:
    """Β.1.3 -> one row per ΚΑΕ line; no lines -> one row from the act-level amount."""
    d, ev = a.doc, a.ev
    act_total = amount_of(ev.get("amountWithVAT"))
    base = {
        "entity": str(d.get("organizationId")),
        "date": athens_date(d.get("issueDate")),
        "year": athens_date(d.get("issueDate")).year,
        "act_status": d.get("status"),
        "act_amount_total": act_total,
        "currency": currency_of(ev.get("amountWithVAT")),
        "financial_year": ev.get("financialYear"),
        "budget_type": ev.get("budgettype"),
        "is_partial": bool(ev.get("partialead")),
        "is_recall": bool(ev.get("recalledExpenseDecision")),
        "is_reversal": bool(ev.get("recalledExpenseDecision")) or is_reversal_subject(d.get("subject")),
        "related_partial_ada": ev.get("relatedPartialADA"),
        "entry_number": ev.get("entryNumber"),
        "source_ada": a.ada,
        "source_sha256": a.sha256,
        **stamp,
    }
    lines = as_list(ev.get("amountWithKae"))
    if not lines:
        return [{
            "commitment_id": f"{a.ada}:act", "line_no": 0, "has_kae_lines": False,
            "kae": None, "kae_scheme": None, "kae_major": None, "amount": act_total, "budget_remainder": None, "credit_remainder": None,
            "counterparty_afm": None, "counterparty_name_raw": None, **base,
        }]
    rows = []
    for i, ln in enumerate(lines):
        afm, _, name = afm_name(ln.get("sponsorAFMName"))
        amt = ln.get("amountWithVAT")
        rows.append({
            "commitment_id": f"{a.ada}:{i}", "line_no": i, "has_kae_lines": True,
            "kae": ln.get("kae"), "kae_scheme": parse_kae(ln.get("kae"))[0], "kae_major": kae_major(ln.get("kae")),
            "amount": float(amt) if amt is not None else None,
            "budget_remainder": ln.get("kaeBudgetRemainder"), "credit_remainder": ln.get("kaeCreditRemainder"),
            "counterparty_afm": afm, "counterparty_name_raw": name, **base,
        })
    return rows


def award_rows(a: RawAct, stamp: dict[str, Any]) -> list[dict[str, Any]]:
    """Δ.1 / Δ.2.2 -> one row per awardee; no awardee -> one row with nulls."""
    d, ev = a.doc, a.ev
    base = {
        "entity": str(d.get("organizationId")),
        "date": athens_date(d.get("issueDate")),
        "year": athens_date(d.get("issueDate")).year,
        "act_status": d.get("status"),
        "award_type": d.get("decisionTypeId"),
        "amount": amount_of(ev.get("awardAmount")),
        "currency": currency_of(ev.get("awardAmount")),
        "cpv": [str(c) for c in as_list(ev.get("cpv"))],
        "assignment_type": ev.get("assignmentType"),
        "related_ada": related_adas(ev),
        "source_ada": a.ada,
        "source_sha256": a.sha256,
        **stamp,
    }
    people = [p for p in as_list(ev.get("person")) if isinstance(p, dict)]
    if not people:
        return [{"award_id": f"{a.ada}:0", "line_no": 0, "person_afm": None,
                 "person_afm_type": None, "person_name_raw": None, **base}]
    rows = []
    for i, p in enumerate(people):
        afm, afm_type, name = afm_name(p)
        rows.append({"award_id": f"{a.ada}:{i}", "line_no": i, "person_afm": afm,
                     "person_afm_type": afm_type, "person_name_raw": name, **base})
    return rows


NON_SUPPLIER = ("remittance", "tax", "debt_service", "other_public_body")


def propagate_payee_class(payments: list[dict[str, Any]], share: float = 0.8) -> Counter:
    """Second pass: an ΑΦΜ whose euros are >= ``share`` non-supplier has its
    ``supplier`` lines reclassified to its dominant non-supplier class."""
    eur: dict[str, Counter] = defaultdict(Counter)
    for p in payments:
        if p["counterparty_afm"] and p["act_status"] == "PUBLISHED" and not p["amount_suspect"] and p["amount"]:
            eur[p["counterparty_afm"]][p["payee_class"]] += p["amount"]
    target: dict[str, str] = {}
    for afm, c in eur.items():
        total = sum(c.values())
        ns = sum(c[k] for k in NON_SUPPLIER)
        if total > 0 and ns / total >= share and c["supplier"] > 0:
            target[afm] = max(NON_SUPPLIER, key=lambda k: c[k])
    changed: Counter = Counter()
    for p in payments:
        if p["payee_class"] == "supplier" and p["counterparty_afm"] in target:
            p["payee_class"] = target[p["counterparty_afm"]]
            p["payee_class_rule"] = "afm_propagation"
            changed[p["payee_class"]] += 1
    return changed


def counterparty_rows(payments: list[dict[str, Any]], stamp: dict[str, Any]) -> list[dict[str, Any]]:
    """Exact-ΑΦΜ aggregation over non-payroll payment lines. No fuzzy merging."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in payments:
        if p["is_payroll"] or not p["counterparty_afm"]:
            continue
        groups[p["counterparty_afm"]].append(p)
    rows = []
    for afm, ps in groups.items():
        names = Counter(p["counterparty_name_raw"] for p in ps if p["counterparty_name_raw"])
        variants = sorted(names)
        norm_keys = {normalise_name(n) for n in variants}
        published = [p for p in ps if p["act_status"] == "PUBLISHED" and not p["amount_suspect"]]
        reasons = []
        if not _AFM_RE.match(afm):
            reasons.append("afm_format")
        if len(norm_keys) > 1:
            reasons.append("name_variants")
        afm_types = {p["counterparty_afm_type"] for p in ps if p["counterparty_afm_type"]}
        natural = any(is_natural_person(v, afm, p["counterparty_afm_type"]) for v in variants for p in ps[:1])
        canonical = names.most_common(1)[0][0] if names else None
        largest = max(published, key=lambda p: p["amount"] or 0.0, default=None)
        rows.append({
            "afm": afm,
            "afm_type": sorted(afm_types)[0] if afm_types else None,
            "canonical_name": canonical,
            "is_natural_person": natural,
            "display_name": "φυσικό πρόσωπο" if natural else canonical,
            "payee_class": Counter(p["payee_class"] for p in ps).most_common(1)[0][0],
            "largest_payment_ada": largest["source_ada"] if largest else None,
            "name_variants": variants,
            "n_name_variants": len(variants),
            "n_name_variants_normalised": len(norm_keys),
            "first_seen": min(p["date"] for p in ps),
            "last_seen": max(p["date"] for p in ps),
            "total_received": round(sum(p["amount"] or 0.0 for p in published), 2),
            "total_received_supplier": round(sum(p["amount"] or 0.0 for p in published if p["payee_class"] == "supplier"), 2),
            "n_payments": len(published),
            "n_payments_revoked": sum(1 for p in ps if p["act_status"] != "PUBLISHED"),
            "n_payments_suspect": sum(1 for p in ps if p["amount_suspect"]),
            "is_remittance_payee": all(p["is_remittance"] for p in ps),
            "entities": sorted({p["entity"] for p in ps}),
            "n_entities": len({p["entity"] for p in ps}),
            "needs_review": bool(reasons),
            "review_reason": ",".join(reasons) if reasons else None,
            "source_adas": sorted({p["source_ada"] for p in ps}),
            "source_ada": None,
            "source_sha256": digest_of_hashes(p["source_sha256"] for p in ps),
            **stamp,
        })
    return rows


def entity_rows(settings: Settings, stamp: dict[str, Any]) -> list[dict[str, Any]]:
    path = settings.entities_file
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    reg = load_registry(path)
    return [{
        "uid": e.uid, "name": e.name, "afm": e.afm, "category": e.category, "parent": e.parent,
        "active_from": e.active_years[0] if e.active_years else None,
        "active_to": e.active_years[1] if e.active_years else None,
        "approx_acts": e.approx_acts, "role": e.role, "note": e.note,
        "in_scope": e.in_scope, "reason": e.reason,
        "source_ada": None, "source_path": str(path), "source_sha256": sha, **stamp,
    } for e in reg.entities]


_LOOKALIKE = str.maketrans("ABEHIKMNOPTXYZ", "ΑΒΕΗΙΚΜΝΟΡΤΧΥΖ")


def is_execution_statement(type_id: str | None, subject: str | None) -> bool:
    """Β.3 «ΔΗΜΟΣΙΕΥΣΗ ΣΤΟΙΧΕΙΩΝ ΕΚΤΕΛΕΣΗΣ ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ ...», Latin look-alikes folded."""
    s = strip_accents(subject).upper().translate(_LOOKALIKE)
    return type_id == "Β.3" and "ΕΚΤΕΛΕΣ" in s and "ΠΡΟΥΠΟΛΟΓΙΣΜ" in s


def pdftotext_version() -> str | None:
    exe = shutil.which("pdftotext")
    if exe is None:
        return None
    out = subprocess.run([exe, "-v"], capture_output=True, text=True)
    first = (out.stderr or out.stdout).strip().splitlines()
    return first[0] if first else "pdftotext"


def budget_rows(raw_dir: Path, statements: dict[str, tuple[str, date | None]],
                stamp: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """One row per ΚΑΕ line of every stored execution statement that parses exactly.

    ``statements`` maps ADA -> (entity, act date) for published Β.3 execution
    statements. Only the first capture of each PDF is read; other documents are
    ignored. Returns the rows and {ADA: reason} for statements refused by the
    parser (unsupported layout, or columns that do not sum to the document).
    """
    from tinos.extract.statements import StatementError, parse_statement

    rows: list[dict[str, Any]] = []
    refused: dict[str, str] = {}
    base = raw_dir / "diavgeia" / "docs"
    for pdf in sorted(base.glob("*/*.pdf")) if base.is_dir() else []:
        ada = pdf.stem
        if ada not in statements:
            continue
        entity, act_date = statements[ada]
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                              capture_output=True, text=True, check=True).stdout
        try:
            st = parse_statement(text)
        except StatementError as exc:
            refused[ada] = str(exc)
            continue
        year_end = (st.period_end.month, st.period_end.day) == (12, 31)
        for ln in st.lines:
            rows.append({
                "statement_ada": ada, "entity": entity, "statement_date": act_date,
                "period_end": st.period_end, "period_year": st.period_end.year,
                "period_month": st.period_end.month, "is_year_end": year_end, "layout": st.layout,
                "side": ln.side, "service": ln.service, "kae": ln.kae, "kae_group": ln.kae[:2],
                "budgeted": ln.budgeted / 100, "assessed_or_warranted": ln.assessed_or_warranted / 100,
                "collected_or_paid": ln.collected_or_paid / 100,
                "source_ada": ada, "source_sha256": sha, **stamp,
            })
    return rows, refused


# ---------------------------------------------------------------------------
# schemas
# ---------------------------------------------------------------------------
def _stamp_fields() -> list[pa.Field]:
    return [pa.field("derived_at", pa.timestamp("ms", tz="UTC")), pa.field("pipeline_version", pa.string())]


S = pa.string
L = lambda t: pa.list_(t)  # noqa: E731
SCHEMAS: dict[str, pa.Schema] = {
    "act": pa.schema([
        pa.field("ada", S()), pa.field("entity", S()), pa.field("type", S()),
        pa.field("date", pa.date32()), pa.field("year", pa.int32()), pa.field("subject", S()),
        pa.field("status", S()), pa.field("signer_ids", L(S())), pa.field("unit_ids", L(S())),
        pa.field("thematic_ids", L(S())), pa.field("protocol_number", S()), pa.field("document_type", S()),
        pa.field("version_id", S()), pa.field("corrected_version_id", S()),
        pa.field("submission_ts", pa.timestamp("ms", tz="UTC")), pa.field("publish_ts", pa.timestamp("ms", tz="UTC")),
        pa.field("document_url", S()), pa.field("source_ada", S()), pa.field("source_path", S()),
        pa.field("source_sha256", S()), *_stamp_fields(),
    ]),
    "payment": pa.schema([
        pa.field("payment_id", S()), pa.field("line_no", pa.int32()), pa.field("is_payroll", pa.bool_()),
        pa.field("payroll_kind", S()), pa.field("payee_class", S()), pa.field("payee_class_rule", S()),
        pa.field("is_internal_transfer", pa.bool_()), pa.field("counterparty_display", S()),
        pa.field("amount", pa.float64()), pa.field("currency", S()), pa.field("kae", S()), pa.field("kae_scheme", S()),
        pa.field("kae_major", S()),
        pa.field("cpv", L(S())), pa.field("is_remittance", pa.bool_()), pa.field("amount_suspect", pa.bool_()),
        pa.field("suspect_reason", S()), pa.field("counterparty_afm", S()), pa.field("counterparty_afm_type", S()), pa.field("counterparty_name_raw", S()),
        pa.field("entity", S()), pa.field("date", pa.date32()), pa.field("year", pa.int32()), pa.field("act_status", S()),
        pa.field("related_ada", L(S())), pa.field("skip_vat_reason", S()),
        pa.field("source_ada", S()), pa.field("source_sha256", S()), *_stamp_fields(),
    ]),
    "commitment": pa.schema([
        pa.field("commitment_id", S()), pa.field("line_no", pa.int32()), pa.field("has_kae_lines", pa.bool_()),
        pa.field("kae", S()), pa.field("kae_scheme", S()), pa.field("kae_major", S()), pa.field("amount", pa.float64()),
        pa.field("budget_remainder", pa.float64()),
        pa.field("credit_remainder", pa.float64()), pa.field("counterparty_afm", S()), pa.field("counterparty_name_raw", S()),
        pa.field("entity", S()), pa.field("date", pa.date32()), pa.field("year", pa.int32()), pa.field("act_status", S()),
        pa.field("act_amount_total", pa.float64()), pa.field("currency", S()), pa.field("financial_year", pa.int32()),
        pa.field("budget_type", S()), pa.field("is_partial", pa.bool_()), pa.field("is_recall", pa.bool_()),
        pa.field("is_reversal", pa.bool_()),
        pa.field("related_partial_ada", S()), pa.field("entry_number", S()),
        pa.field("source_ada", S()), pa.field("source_sha256", S()), *_stamp_fields(),
    ]),
    "award": pa.schema([
        pa.field("award_id", S()), pa.field("line_no", pa.int32()), pa.field("person_afm", S()),
        pa.field("person_afm_type", S()), pa.field("person_name_raw", S()),
        pa.field("entity", S()), pa.field("date", pa.date32()), pa.field("year", pa.int32()), pa.field("act_status", S()),
        pa.field("award_type", S()), pa.field("amount", pa.float64()), pa.field("currency", S()), pa.field("cpv", L(S())),
        pa.field("assignment_type", S()), pa.field("related_ada", L(S())),
        pa.field("source_ada", S()), pa.field("source_sha256", S()), *_stamp_fields(),
    ]),
    "counterparty": pa.schema([
        pa.field("afm", S()), pa.field("afm_type", S()), pa.field("canonical_name", S()),
        pa.field("is_natural_person", pa.bool_()), pa.field("display_name", S()), pa.field("payee_class", S()),
        pa.field("largest_payment_ada", S()), pa.field("name_variants", L(S())), pa.field("n_name_variants", pa.int32()),
        pa.field("n_name_variants_normalised", pa.int32()), pa.field("first_seen", pa.date32()),
        pa.field("last_seen", pa.date32()), pa.field("total_received", pa.float64()),
        pa.field("total_received_supplier", pa.float64()), pa.field("n_payments", pa.int32()),
        pa.field("n_payments_revoked", pa.int32()), pa.field("n_payments_suspect", pa.int32()),
        pa.field("is_remittance_payee", pa.bool_()), pa.field("entities", L(S())), pa.field("n_entities", pa.int32()),
        pa.field("needs_review", pa.bool_()), pa.field("review_reason", S()), pa.field("source_adas", L(S())),
        pa.field("source_ada", S()), pa.field("source_sha256", S()), *_stamp_fields(),
    ]),
    "entity": pa.schema([
        pa.field("uid", S()), pa.field("name", S()), pa.field("afm", S()), pa.field("category", S()),
        pa.field("parent", S()), pa.field("active_from", pa.int32()), pa.field("active_to", pa.int32()),
        pa.field("approx_acts", pa.int64()), pa.field("role", S()), pa.field("note", S()),
        pa.field("in_scope", pa.bool_()), pa.field("reason", S()),
        pa.field("source_ada", S()), pa.field("source_path", S()), pa.field("source_sha256", S()), *_stamp_fields(),
    ]),
    "budget_line": pa.schema([
        pa.field("statement_ada", S()), pa.field("entity", S()), pa.field("statement_date", pa.date32()),
        pa.field("period_end", pa.date32()), pa.field("period_year", pa.int32()), pa.field("period_month", pa.int32()),
        pa.field("is_year_end", pa.bool_()), pa.field("layout", S()), pa.field("side", S()), pa.field("service", S()),
        pa.field("kae", S()), pa.field("kae_group", S()), pa.field("budgeted", pa.float64()),
        pa.field("assessed_or_warranted", pa.float64()), pa.field("collected_or_paid", pa.float64()),
        pa.field("source_ada", S()), pa.field("source_sha256", S()), *_stamp_fields(),
    ]),
}

SORT_KEYS = {
    "act": ("entity", "date", "ada"), "payment": ("entity", "date", "payment_id"),
    "commitment": ("entity", "date", "commitment_id"), "award": ("entity", "date", "award_id"),
    "counterparty": ("afm",), "entity": ("uid",),
    "budget_line": ("entity", "period_end", "side", "service", "kae"),
}


def to_table(name: str, rows: list[dict[str, Any]]) -> pa.Table:
    rows = sorted(rows, key=lambda r: tuple(str(r[k]) for k in SORT_KEYS[name]))
    return pa.Table.from_pylist(rows, schema=SCHEMAS[name])


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
@dataclass
class BuildResult:
    counts: dict[str, int]
    manifest_path: Path
    derived_at: datetime


def build_curated(settings: Settings) -> BuildResult:
    derived_at = datetime.now(UTC).replace(microsecond=0)
    stamp = {"derived_at": derived_at, "pipeline_version": PIPELINE_VERSION}
    acts: list[dict] = []
    payments: list[dict] = []
    commitments: list[dict] = []
    awards: list[dict] = []
    source_hashes: list[str] = []
    excluded_pending = Counter()
    family_afms = frozenset(e.afm for e in load_registry(settings.entities_file).entities if e.afm)
    review_path = settings.root / "data" / "manual" / "amount_review.yaml"
    review = load_amount_review(review_path)
    duplicates = load_duplicate_postings(review_path)
    statements: dict[str, tuple[str, date | None]] = {}

    for a in iter_raw_acts(settings.raw_dir):
        source_hashes.append(a.sha256)
        acts.append(act_row(a, stamp))
        t, status = a.doc.get("decisionTypeId"), a.doc.get("status")
        if status == "PUBLISHED" and is_execution_statement(t, a.doc.get("subject")):
            statements[a.ada] = (str(a.doc.get("organizationId")), athens_date(a.doc.get("issueDate")))
        if status not in MEASURE_STATUSES:
            if t in PAYMENT_TYPES | COMMITMENT_TYPES | AWARD_TYPES:
                excluded_pending[t] += 1
            continue
        if t in PAYMENT_TYPES:
            payments.extend(payment_rows(a, stamp, family_afms, review, duplicates))
        elif t in COMMITMENT_TYPES:
            commitments.extend(commitment_rows(a, stamp))
        elif t in AWARD_TYPES:
            awards.extend(award_rows(a, stamp))

    # A duplicate must point at a payment act we hold that is not itself a duplicate.
    payment_adas = {r["source_ada"] for r in payments}
    for ada, e in duplicates.items():
        kept = str(e.get("duplicate_of"))
        if ada not in payment_adas or kept not in payment_adas or kept in duplicates:
            raise ValueError(f"amount_review duplicate {ada} -> {kept}: both must be payment acts, "
                             "and the kept one must not itself be a duplicate")
    propagated = propagate_payee_class(payments)
    pdftotext = pdftotext_version()
    if pdftotext:
        budget, refused = budget_rows(settings.raw_dir, statements, stamp)
    else:
        budget, refused = [], {}
        print("warning: pdftotext not installed; budget_line is empty", file=sys.stderr)
    tables = {
        "act": to_table("act", acts),
        "payment": to_table("payment", payments),
        "commitment": to_table("commitment", commitments),
        "award": to_table("award", awards),
        "counterparty": to_table("counterparty", counterparty_rows(payments, stamp)),
        "entity": to_table("entity", entity_rows(settings, stamp)),
        "budget_line": to_table("budget_line", budget),
    }
    out = settings.curated_dir
    out.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        pq.write_table(table, out / f"{name}.parquet", compression="zstd")

    manifest = {
        "derived_at": derived_at.isoformat(),
        "pipeline_version": PIPELINE_VERSION,
        "source_acts": len(source_hashes),
        "source_digest": digest_of_hashes(source_hashes),
        "rows": {k: v.num_rows for k, v in tables.items()},
        "excluded_pending_revocation_measure_acts": dict(excluded_pending),
        "budget_statements": {
            "parsed": len({r["statement_ada"] for r in budget}),
            "refused": refused,
            "pdftotext": pdftotext or "not installed",
            "validation": "every amount column sums to the document's own total line, to the cent",
        },
        "rules": {
            "measure_statuses": sorted(MEASURE_STATUSES),
            "dates": "Europe/Athens",
            "counterparty_resolution": "exact AFM, no fuzzy merge",
            "payment_amount_suspect_above_eur": SUSPECT_PAYMENT_EUR,
            "remittance_kae_major": f"{REMITTANCE_KAE_MAJOR} (old chart) | {NEW_REMITTANCE_KAE_MAJOR} (new chart, 2026)",
            "remittance_subject": "κρατησ (accent-insensitive)",
            "payroll_kinds": "no_sponsor | batch ('& ΛΟΙΠΟΙ' / 'ΚΑΙ ΛΟΙΠΕΣ' sponsor) | named (payroll subject + natural person)"
                             " | personnel_kae (natural person under personnel ΚΑΕ: old 60, new 21); name and AFM dropped",
            "payee_classes": list(PAYEE_CLASSES),
            "amount_review_entries": len(review),
            "duplicate_posting_entries": len(duplicates),
            "payee_class_afm_propagation_lines": dict(propagated),
            "commitment_reversal": "recalledExpenseDecision OR subject matches ανατροπ/ανακλησ",
            "never_sum_across_tables": True,
        },
    }
    mpath = out / "build_manifest.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return BuildResult(manifest["rows"], mpath, derived_at)
