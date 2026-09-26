"""The municipality's own decisions accepting other bodies' money: who pays it, read from their titles.

Δήμος Τήνου records every grant it receives in a decision of its own before it books it: «Αποδοχή
χρηματοδότησης / επιχορήγησης / ποσού ... από ...», and from 2023 also the budget amendment that follows,
«Έγκριση Νης αναμόρφωσης ... για αποδοχή χρηματοδότησης ...». The titles usually name the grantor and the
amount, so the act metadata alone says who pays the municipality (FINDINGS F12). Nothing is downloaded.

Classified by the folded title, first match wins:

- an acceptance of money: «ΑΠΟΔΟΧΗ» with a money word (χρηματοδότηση, επιχορήγηση, ποσό, πίστωση, κατανομή),
  or a donation of money («δωρεάς ποσού», «χρηματικής δωρεάς»); not the terms of a loan or of a call, a
  resignation, an inheritance, or an inclusion in a programme («αποδοχή ένταξης»), which moves no money;
- ``kind``: ``acceptance`` (the committee's or council's decision), ``proposal`` («Εισήγηση ...», the same
  money again) or ``amendment`` (the budget amendment approving it, the same money again);
- ``grantor``: the body the title names (:data:`GRANTORS`), ``unknown`` when it names none;
- ``amount``: the first amount the title states, in cents, when it states one.

A title can name a private donor; the table carries no subject (join ``act`` for it) and anything published
counts private donors together (PRIVACY.md Q1).
"""

from __future__ import annotations

import re
from typing import Any

from tinos.sources.fulltext import fold

_ACCEPT = re.compile(r"ΑΠΟΔΟΧ(?:Η|ΗΣ)(?![Α-Ω])")
_MONEY = re.compile(r"ΧΡΗΜΑΤΟΔΟΤ|ΕΠΙΧΟΡΗΓ|ΠΟΣΟΥ|ΠΙΣΤΩΣ|ΚΑΤΑΝΟΜ|ΧΡΗΜΑΤΙΚ")
_DONATION = re.compile(r"ΔΩΡΕΑ\w* (?:ΠΟΣΟΥ|ΧΡΗΜΑΤ)|ΧΡΗΜΑΤΙΚΗΣ ΔΩΡΕΑΣ")
_NOT_MONEY = re.compile(r"ΟΡΩΝ ΣΥΜΜΕΤΟΧΗΣ|ΟΡΟΥ 10|ΔΑΝΕΙ|ΠΑΡΑΙΤΗΣ|ΚΛΗΡΟΝΟΜ|ΤΜΗΜΑΤΙΚΗΣ ΚΑΤΑΒΟΛΗΣ|"
                        r"ΑΠΟΔΟΧΗ (?:ΤΗΣ )?(?:ΑΠΟΦΑΣΗΣ |1ΗΣ ΤΡΟΠΟΙΗΣΗΣ ΤΗΣ ΠΡΑΞΗΣ )?ΕΝΤΑΞΗΣ")
_AMOUNT = re.compile(r"(?<![\d.,])\d{1,3}(?:\.\d{3})*,\d{2}(?!\d)")

# The grantor a title names. Order matters: the Regional Union of Municipalities before the Region, the named
# ministries before the Interior Ministry's programmes, which the other ministries' titles never name.
GRANTORS: tuple[tuple[str, re.Pattern[str]], ...] = tuple((g, re.compile(p)) for g, p in (
    ("ped", r"ΠΕΡΙΦΕΡΕΙΑΚΗ ΕΝΩΣΗ ΔΗΜΩΝ|ΠΕΡΙΦΕΡΕΙΑ ΕΝΩΣΗΣ ΔΗΜΩΝ|(?<![Α-Ω])ΠΕΔ(?![Α-Ω])"),
    ("green_fund", r"ΠΡΑΣΙΝΟ ΤΑΜΕΙΟ|ΠΡΑΣΙΝΟΥ ΤΑΜΕΙΟΥ|ΠΕΡΙΒΑΛΛΟΝΤΙΚΟΥ ΙΣΟΖΥΓΙΟΥ|ΑΣΤΙΚΗ ΑΝΑΖΩΟΓΟΝΗΣΗ"),
    ("shipping", r"ΝΑΥΤΙΛΙΑΣ|ΝΗΣΙΩΤΙΚΗΣ ΠΟΛΙΤΙΚΗΣ"),
    ("infrastructure", r"ΥΠΟΔΟΜΩΝ ΚΑΙ ΜΕΤΑΦΟΡΩΝ"),
    ("digital", r"ΨΗΦΙΑΚΗΣ ΔΙΑΚΥΒΕΡΝΗΣΗΣ"),
    ("tourism", r"ΥΠΟΥΡΓΕΙΟ ΤΟΥΡΙΣΜΟΥ"),
    ("economy", r"ΟΙΚΟΝΟΜΙΑΣ|ΑΝΑΠΤΥΞΙΑΚΟ ΠΡΟΓΡΑΜΜΑ ΕΙΔΙΚΟΥ ΣΚΟΠΟΥ|ΕΥΡΩΠΑΙΚΟ ΤΑΜΕΙΟ ΠΕΡΙΦΕΡΕΙΑΚΗΣ"),
    ("education", r"ΠΑΙΔΕΙΑΣ"),
    ("culture", r"ΥΠΟΥΡΓΕΙΟ ΠΟΛΙΤΙΣΜΟΥ"),
    ("region", r"ΠΕΡΙΦΕΡΕΙΑΣ ΝΟΤΙΟΥ ΑΙΓΑΙΟΥ|ΠΕΡΙΦΕΡΕΙΑ Ν\.? ?ΑΙΓΑΙΟΥ|ΠΕΡΙΦΕΡΕΙΑ ΝΟΤΙΟΥ|ΝΟΤΙΟ ΑΙΓΑΙΟ"),
    ("interior", r"ΥΠΕΣ|ΥΠΟΥΡΓΕΙΟ ΕΣΩΤΕΡΙΚΩΝ|(?<![Α-Ω])Κ\.?Α\.?Π(?![Α-Ω])|ΦΙΛΟΔΗΜΟΣ|ΤΡΙΤΣΗΣ|ΕΚΛΟΓΙΚ|ΝΑΥΑΓΟΣΩΣΤ|"
                 r"ΒΟΗΘΕΙΑ ΣΤΟ ΣΠΙΤΙ|ΣΑΕ ?055|ΘΕΟΜΗΝΙ|ΚΟΡΟΝΟΙ|ΑΔΕΣΠΟΤ|ΣΤΗΡΙΞΗΣ ΗΛΙΚΙΩΜΕΝΩΝ|ΙΔΟΧ|ΞΕΝΟΓΛΩΣΣ"),
    ("eu", r"HORIZON|ΟΡΙΖΟΝΤΑΣ 2020|(?<![Α-Ω])LIFE(?![Α-Ω])|WIFI4EU|ΣΥΝΔΕΟΝΤΑΣ ΤΗΝ ΕΥΡ"),
    ("kede", r"(?<![Α-Ω])ΚΕΔΕ(?![Α-Ω])"),
    ("private", r"ΟΜΙΛΟ ΕΤΑΙΡΕΙΩΝ|ΣΩΜΑΤΕΙ|ΚΛΗΡΟΔΟΤΗΜ|(?<![Α-Ω])Κ\.Κ\.|ΣΥΛΛΟΓΟΥ"),
))
_AMENDMENT = re.compile(r"^(?:ΕΓΚΡΙΣΗ|ΕΙΣΗΓΗΣΗ ΣΧΕΔΙΟΥ) (?:ΤΗΣ )?\d+\w* ΑΝΑΜΟΡΦΩΣ|^ΕΓΚΡΙΣΗ ΤΗΣ ΜΕ ΑΡΙΘΜΟ|^ΤΡΟΠΟΠΟΙΗΣΗ")


def classify(subject: str | None) -> dict[str, Any] | None:
    """The acceptance an act's title records, or None when it records none."""
    s = fold(subject)
    if not _ACCEPT.search(s) or _NOT_MONEY.search(s) or not (_MONEY.search(s) or _DONATION.search(s)):
        return None
    kind = "amendment" if _AMENDMENT.search(s) else "proposal" if s.startswith("ΕΙΣΗΓΗΣΗ") else "acceptance"
    amounts = _AMOUNT.findall(s)
    amount = None
    if amounts:
        whole, frac = amounts[0].replace(".", "").split(",")
        amount = int(whole) * 100 + int(frac)
    grantor = next((g for g, p in GRANTORS if p.search(s)), "unknown")
    return {"grantor": grantor, "kind": kind, "amount_stated": amount}
