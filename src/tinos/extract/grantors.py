"""The grantors found from the municipality's own acceptances (FINDINGS F12): their documents, read.

Each reader takes a stored PDF's text (``pdftotext -layout``) and the decision's family and returns
``(amounts, status, family)`` like :func:`tinos.extract.grants.read_region`. Only an amount the document
itself checks is validated (``v_grant_line`` counts nothing else): its words against its figures, a total
it states, or the same amount stated twice. Every reader requires the payee to be a Tinos body, by its
ΑΦΜ where the document prints one; a payment to anyone else is ``absent``, and no payee's name is kept.

- The Regional Union of Municipalities of the South Aegean (ΠΕΔ, 53992): its payment orders («Χρηματικό
  Ένταλμα Πληρωμής», from 2021) and its board's grants on the municipality's requests. A grant is counted
  only while no payment order pays it (``tinos.curated_grants``); an event it co-organises
  («συνδιοργάνωση») or procures itself («πρωτογενές αίτημα») is its own spending, listed.
- The Green Fund (99201054): approvals of an expense «με δικαιούχο» a payee by ΑΦΜ (the Panormos plan's
  study was paid to its contractors, not to the municipality), and releases from its escrow account at
  the Deposits and Loans Fund in the municipality's favour.
- The Shipping Ministry's Secretariat for the Aegean (100015969): a grant is a ceiling («μέχρι του
  ποσού»), each payment of it is approved on invoices («Εγκρίνουμε την πληρωμή»), and the money moves when
  an order credits the project account the municipality holds at the Bank of Greece («Εντολή κατανομής
  εξουσιοδοτήσεως πληρωμής», ΣΑΕ 330 / ΣΑΝΑ 233). The order is counted, the approval it cites is not.
- The public-investment ministries (Economy and Finance, Infrastructure, Digital Governance): transfers
  to a project account, one letter or a table of projects whose rows add up to its stated total.
- The tourism organisation ΕΟΤ (99221315): one payment order, gross, withholdings and net.
"""

from __future__ import annotations

import re

from tinos.extract.grants import _AMT, _SYMBOLS, GrantAmount, cents, words_to_cents
from tinos.sources.fulltext import fold

TINOS_AFM = "800302968"
# the municipality's ΑΦΜ before the 2011 merger, still on the tourism organisation's 2015 payment order
OLD_TINOS_AFM = "090188990"

# «ποσού των ‹words› (‹figures›)», «ποσού (‹words›) «‹figures›»», «ποσού ‹words› «‹figures›»»
_WORDS_FIG = re.compile(rf"ΠΟΣΟ\w*\s+(?:ΤΩΝ\s+|ΤΟΥ\s+)?\(?\s*(?P<words>[^()«»\d€]{{3,300}}?)\s*\)?\s*[(«]?\s*€?\s*"
                        rf"(?P<fig>{_AMT})(?:\s*€)*\s*[)»]")  # «(160.082,90€ €)»
_ADA = re.compile(r"(?<![0-9Α-Ω])[0-9Α-Ω]{4,10}-[0-9Α-Ω]{3}(?![0-9Α-Ω])")


def _flat(text: str) -> str:
    return fold(" ".join(text.translate(_SYMBOLS).split()))


def cited_adas(text: str) -> set[str]:
    """The ADAs a document cites (its own included; the caller drops it)."""
    return set(_ADA.findall(_flat(text)))


def _words_fig(flat: str) -> list[tuple[int, int | None]]:
    """(figures, words) of every amount the text states in both."""
    return [(cents(m.group("fig")), words_to_cents(m.group("words") + ("" if "ΕΥΡΩ" in m.group("words") else " ΕΥΡΩ")))
            for m in _WORDS_FIG.finditer(flat)]


def _figure(c: int) -> str:
    """123456 -> «1.234,56»."""
    return f"{c // 100:,}".replace(",", ".") + f",{c % 100:02d}"


def _letter(flat: str, detail: str, subject: str | None = None) -> list[GrantAmount]:
    """The first amount the text states in words and figures, validated when they agree, or, when the words spell
    another amount, when the subject states the same figures (6ΦΠΚ46ΝΛΣΞ-27Τ: 160.082,90 in its subject and figures,
    the words of another transfer's 523.848,57)."""
    found = _words_fig(flat)
    if not found:
        return []
    fig, words = found[0]
    validation = "words_and_figures" if words == fig else "stated_amount" if _figure(fig) in fold(subject) else None
    note = "" if words == fig or validation is None else "; the words spell another amount, the subject states these figures"
    return [GrantAmount(fig, fig, "letter", validation,
                        f"{detail}; figures {fig / 100:.2f}, words {words / 100 if words is not None else None}{note}")]


# ---------------------------------------------------------------------------
# The Regional Union of Municipalities (ΠΕΔ Νοτίου Αιγαίου)
# ---------------------------------------------------------------------------
_PED_PAYEE = re.compile(r"ΔΙΚΑΙΟΥΧΟΣ\W*.{0,80}?Α\.?Φ\.?Μ\.?\s*:?\s*(?P<afm>\d{9})")
_PED_AMOUNT = re.compile(rf"###\s*(?P<words>[^()#]{{3,200}}?)\s*\(\s*(?P<fig>{_AMT})\s*\)\s*ΕΥΡΩ\s*###")
_PED_TOTAL = re.compile(rf"ΣΥΝΟΛΟ\s*:\s*(?P<fig>{_AMT})")
_PED_NET = re.compile(rf"ΚΑΘΑΡ\.?\s*ΔΙΚΑΙΟΥΧΟ\w*\s*:\s*(?P<fig>{_AMT})")
_PED_OPERATIVE = re.compile(r"Α ?Π ?Ο ?Φ ?Α ?Σ ?Ι ?Ζ ?Ε ?Ι")
_PED_OWN_SPENDING = re.compile(r"ΣΥΝΔΙΟΡΓΑΝΩΣ|ΠΡΩΤΟΓΕΝ\w* ΑΙΤΗΜΑ")
# «34.720,00 ευρώ (8.680,00 ευρώ χ 4 Δήμοι ...)»: one municipality's share of a joint grant
_PED_SHARE = re.compile(rf"(?P<total>{_AMT})\s*(?:€|ΕΥΡΩ)?\s*\(\s*(?P<share>{_AMT})\s*(?:€|ΕΥΡΩ)?\s*[ΧX×]\s*(?P<n>\d+)")
_PED_AMOUNT_IN_ITEM = re.compile(rf"ΠΟΣΟ\w*\s+(?:ΤΩΝ\s+|ΤΟΥ\s+)?(?P<fig>{_AMT})")
_PED_PART = re.compile(rf"(?:^|\s)[Α-Ω]\.\s+(?P<w>[^()]{{3,120}}?)\s*ΕΥΡΩ\s*\((?P<fig>{_AMT})")
_PED_BUDGET_YEAR = re.compile(r"(?:ΟΙΚ\.?|ΟΙΚΟΝΟΜΙΚΟΥ)\s*ΕΤΟΥΣ\s+(?P<y>20\d\d)")


def _ped_words(words: str) -> int | None:
    """«Οκτώ Χιλ. Εξακόσια Ογδόντα» (the payment order abbreviates) -> cents."""
    return words_to_cents(re.sub(r"ΧΙΛ\.", "ΧΙΛΙΑΔΕΣ", words) + " ΕΥΡΩ")


def ped_budget_year(text: str) -> int | None:
    """The ΠΕΔ's budget year a board grant is charged to («προϋπολογισμού ... οικ. έτους 2022»)."""
    flat = _flat(text)
    m = None
    for m in _PED_OPERATIVE.finditer(flat):
        pass
    years = [int(y.group("y")) for y in _PED_BUDGET_YEAR.finditer(flat[m.end():] if m else flat)]
    return years[0] if years else None


def read_ped(text: str, family: str, subject: str | None = None,
             codes: dict[str, str] | None = None) -> tuple[list[GrantAmount], str, str]:
    flat = _flat(text)
    if family == "ped_payment":
        payee, amount = _PED_PAYEE.search(flat), _PED_AMOUNT.search(flat)
        if not payee or not amount:
            return [], "not_found", family
        if payee.group("afm") != TINOS_AFM:
            return [], "absent", family
        fig = cents(amount.group("fig"))
        total, net = _PED_TOTAL.search(flat), _PED_NET.search(flat)
        words = _ped_words(amount.group("words"))
        validation = ("words_and_figures" if words == fig
                      else "stated_amount" if total and cents(total.group("fig")) == fig else None)
        net_c = cents(net.group("fig")) if net else fig
        return [GrantAmount(fig, net_c, "payment_order", validation,
                            f"payee ΑΦΜ {TINOS_AFM}; figures {fig / 100:.2f}, words "
                            f"{words / 100 if words is not None else None}, total "
                            f"{cents(total.group('fig')) / 100 if total else None}, net {net_c / 100:.2f}")], "read", family
    if family != "ped_grant":
        return [], "listed", family
    if _PED_OWN_SPENDING.search(fold(subject)):
        return [], "listed", "ped_own_spending"
    m = None
    for m in _PED_OPERATIVE.finditer(flat):
        pass
    if m is None:
        return [], "not_found", family
    operative = flat[m.end():]
    item1 = re.split(r"\s2\.\s", operative, maxsplit=1)[0][:900]
    if _PED_OWN_SPENDING.search(item1):
        return [], "listed", "ped_own_spending"
    if share := _PED_SHARE.search(item1):
        total, part, n = cents(share.group("total")), cents(share.group("share")), int(share.group("n"))
        return [GrantAmount(part, part, "letter", "stated_amount" if part * n == total else None,
                            f"one of {n} municipalities' equal shares, {n} x {part / 100:.2f} = {total / 100:.2f}")], \
            "read", family
    amounts = [cents(x.group("fig")) for x in _PED_AMOUNT_IN_ITEM.finditer(item1)]
    if not amounts:
        return [], "not_found", family
    fig = amounts[0]
    # the grant stated again (the item that commits it, or the request it grants), or its parts in words and figures
    stated = len(re.findall(re.escape(f"{fig // 100:,}".replace(",", ".") + f",{fig % 100:02d}"), flat))
    # «Α. Πέντε χιλιάδες ευρώ (5.000,00€) για ... Β. Πέντε χιλιάδες ευρώ (5.000,00€) για ...»
    parts = [cents(x.group("fig")) for x in _PED_PART.finditer(item1)
             if words_to_cents(x.group("w") + " ΕΥΡΩ") == cents(x.group("fig"))]
    validation = ("words_and_figures" if len(parts) > 1 and sum(parts) == fig
                  else "stated_amount" if stated >= 2 else None)
    return [GrantAmount(fig, fig, "letter", validation,
                        f"the board grants {fig / 100:.2f}; stated {stated} times in the document"
                        + (f", its {len(parts)} parts in words and figures add up to it" if validation ==
                           "words_and_figures" else ""))], "read", family


# ---------------------------------------------------------------------------
# The Green Fund (Πράσινο Ταμείο)
# ---------------------------------------------------------------------------
_GF_PAYEE = re.compile(r"ΔΙΚΑΙΟΥΧ\w*.{0,160}?Α\.?Φ\.?Μ\.?\s*:?\s*(?P<afm>\d{9})")
_GF_ESCROW_RELEASE = re.compile(rf"ΝΑ ΕΚΤΑΜΙΕΥΣΕΙ .{{0,160}}?ΤΟ ΠΟΣΟ ΤΩΝ €?\s*(?P<fig>{_AMT})")
_GF_TINOS_PAYEE = re.compile(r"ΔΙΚΑΙΟΥΧΟ\w*\s+(?:ΤΟ[ΝΥ]?\s+|ΤΗΝ\s+)?ΔΗΜΟ\w? ΤΗΝΟΥ\b")
_GF_BUDGET = re.compile(rf"ΠΡΟΥΠΟΛΟΓΙΣΜΟΥ\s+(?P<fig>{_AMT})")
_GF_DEPOSIT = re.compile(rf"ΠΑΡΑΚΑΤΑΘΗΚΗΣ ΥΠΕΡ (?:ΤΟΥ )?ΔΗΜΟΥ ΤΗΝΟΥ ΠΟΣΟΥ (?:ΥΨΟΥΣ )?(?P<fig>{_AMT})")


def read_green_fund(text: str, family: str, subject: str | None = None,
                    codes: dict[str, str] | None = None) -> tuple[list[GrantAmount], str, str]:
    if family != "green_fund_payment":
        return [], "listed", family
    flat = _flat(text)
    if "ΕΓΚΡΙΝΟΥΜΕ ΤΗ ΔΑΠΑΝΗ" in flat or "ΕΓΚΡΙΝΟΥΜΕ ΤΗΝ ΔΑΠΑΝΗ" in flat:
        operative = flat[flat.find("ΕΓΚΡΙΝΟΥΜΕ"):]
        payee = _GF_PAYEE.search(operative)
        if not payee:
            return [], "not_found", family
        by_name = _GF_TINOS_PAYEE.search(operative)
        if payee.group("afm") != TINOS_AFM and not by_name:
            return [], "absent", family  # paid to the study's contractors, not to the municipality
        how = (f"payee ΑΦΜ {TINOS_AFM}" if payee.group("afm") == TINOS_AFM
               else f"payee Δήμος Τήνου by name (the ΑΦΜ printed, {payee.group('afm')}, is not the municipality's)")
        return _letter(operative, how), "read", family
    # releases from the escrow account and deposits in the municipality's favour, each stated in the operative part
    start = flat.rfind("ΑΠΟΦΑΣΙΖΟΥΝ")
    operative = flat[start:] if start >= 0 else flat
    releases = [(cents(m.group("fig")), flat.count(m.group("fig"))) for m in _GF_ESCROW_RELEASE.finditer(operative)]
    deposits = [cents(m.group("fig")) for m in _GF_DEPOSIT.finditer(operative)]
    deposits = [(fig, deposits.count(fig)) for fig in dict.fromkeys(deposits)]
    # a release and a deposit paying one service: together the service's budget the text states
    budgets = {cents(m.group("fig")) for m in _GF_BUDGET.finditer(flat)}
    whole = sum(f for f, _ in releases + deposits) in budgets
    out = [GrantAmount(fig, fig, "escrow_release", "stated_amount" if n >= 2 or whole else None,
                       f"released from the escrow account for the municipality's service, stated {n} times"
                       + ("; with the deposit, the service's stated budget" if whole else ""))
           for fig, n in releases]
    out += [GrantAmount(fig, fig, "escrow_deposit", "stated_amount" if n >= 2 or whole else None,
                        f"deposit in the municipality's favour at the Deposits and Loans Fund and the order to pay it, "
                        f"stated {n} times" + ("; with the release, the service's stated budget" if whole else ""))
            for fig, n in deposits]
    return out, ("read" if out else "not_found"), family


# ---------------------------------------------------------------------------
# The Shipping Ministry's General Secretariat for the Aegean and Island Policy
# ---------------------------------------------------------------------------
_SHIP_MANAGER = re.compile(rf"(?:ΥΠΟΛΟΓΟ\w* ΔΙΑΧΕΙΡΙΣΤ\w*|ΦΟΡΕΑΣ ΥΛΟΠΟΙΗΣΗΣ).{{0,60}}?ΔΗΜΟ\w* ΤΗΝΟΥ.{{0,40}}?{TINOS_AFM}")


def read_shipping(text: str, family: str, subject: str | None = None,
                  codes: dict[str, str] | None = None) -> tuple[list[GrantAmount], str, str]:
    flat = _flat(text)
    if family not in ("pde_authorisation", "shipping_payment", "shipping_grant"):
        return [], "listed", family
    if not _SHIP_MANAGER.search(flat) and TINOS_AFM not in flat:
        rows = read_rows(text) if family == "pde_authorisation" else []
        return (rows, "read", family) if rows else ([], "absent", family)
    anchor = {"pde_authorisation": "ΠΑΡΑΚΑΛΟΥΜΕ", "shipping_payment": "ΑΠΟΦΑΣΙΖΟΥΜΕ", "shipping_grant": "ΑΠΟΦΑΣΙΖΟΥΜΕ"}[family]
    i = flat.rfind(anchor)
    amounts = _letter(flat[i:] if i >= 0 else flat, {"pde_authorisation": "credited to the project account the "
                                                     "municipality holds at the Bank of Greece",
                                                     "shipping_payment": "payment approved on invoices",
                                                     "shipping_grant": "a ceiling («μέχρι του ποσού»)"}[family])
    return amounts, ("read" if amounts else "not_found"), family


# ---------------------------------------------------------------------------
# Public-investment transfers: a letter, or a table of projects adding up to its stated total
# ---------------------------------------------------------------------------
_EN_AMT = r"-?(?:\d{1,3}(?:,\d{3})*)?\.\d{2}"  # «8,000.00», «-21.46», «-.54»
# a font that prints Σ as ΢ (U+03A2) and shifts letters: «΢ΤΝΟΛΟ» for ΣΥΝΟΛΟ, «ΣΗΝΟΤ» for ΤΗΝΟΥ
_SHIFTED = str.maketrans({"\u03a2": "Σ"})
_TOTAL_LINE = re.compile(r"ΣΥΝΟΛ|ΣΤΝΟΛ")
_STATED_TOTAL = re.compile(rf"ΣΥΝΟΛΙΚΟΥ ΠΟΣΟΥ\s+(?P<fig>{_AMT})")
_PROJECT_CODE = re.compile(r"20\d\d[Α-Ω]{2}\d{8}")
_PAYMENT_ROW = re.compile(r"^\s*\d{8,9}\s")
_NUMBERED_ROW = re.compile(r"^\s*\d{1,3}(?:\.\d{1,2})?\s")  # «  7.1   >>   ...   9.663,33»
# the Tinos bodies these tables pay, by ΑΦΜ or name (the port fund: «ΔΛΤ ΤΗΝΟΥ-ΑΝΔΡΟΥ», shifted «ΔΛΣ ΣΗΝΟΤ-»)
_TINOS_PAYEES = ((re.compile(r"800300858|Δ\.?Λ\.?[ΤΣ]\.? (?:ΤΗΝΟΥ|ΣΗΝΟΤ)|ΛΙΜΕΝΙΚ\w* ΤΑΜΕΙ\w* ΤΗΝΟΥ"), "50256"),
                 (re.compile(rf"{TINOS_AFM}|ΔΗΜΟ[ΣΥ]? (?:ΤΗΝΟΥ|ΣΗΝΟΤ)"), "6296"))
_TINOS_AFMS = ((re.compile(r"(?<!\d)800300858(?!\d)"), "50256"), (re.compile(rf"(?<!\d){TINOS_AFM}(?!\d)"), "6296"))


def _row_amounts(line: str, english: bool) -> list[tuple[int, int]]:
    """(cents, end column) of each amount on a raw line."""
    pat = _EN_AMT if english else _AMT
    out = []
    for m in re.finditer(rf"(?<![\d.,]){pat}(?![\d%])", line):
        s = m.group()
        if english:
            s = re.sub(r"^(-?)\.", r"\g<1>0.", s.replace(",", "")).replace(".", ",")
        out.append((cents(s), m.end()))
    return out


def _payee(lines: list[str], codes: dict[str, str] | None = None) -> str | None:
    for pattern, uid in _TINOS_PAYEES:
        if any(pattern.search(l) for l in lines):
            return uid
    for code, uid in (codes or {}).items():  # a Tinos body's project code (entities.yaml ``anchor_codes``)
        if any(code in l for l in lines):
            return uid
    return None


def _row_payee(folded: list[str], j: int, hi: int, codes: dict[str, str] | None = None) -> str | None:
    """The Tinos body a table row pays: its ΑΦΜ on the row or the three lines after it (a wrapped cell), up to the next
    row's amount, else its name on the row itself."""
    for pattern, uid in _TINOS_AFMS:
        if any(pattern.search(l) for l in folded[j:hi]):
            return uid
    return _payee([folded[j]], codes)


def read_rows(text: str, codes: dict[str, str] | None = None) -> list[GrantAmount]:
    """Rows of a transfer table paying a Tinos body (named, or its ΑΦΜ, on the row or the three lines after it). Each
    section is checked against its own total: the amounts in the total's column since the previous total, or on the
    lines carrying a project code, or on the payment lines, must add up to it."""
    raw = text.translate(_SYMBOLS).translate(_SHIFTED).splitlines()
    # «8,000.00» tables (the 2016 ΕΣΠΑ orders): counted by their thousands, since dates («14.10.2024») look like «14.10»
    english = sum(len(re.findall(r"(?<![\d.,])\d{1,3}(?:,\d{3})+\.\d{2}(?![\d%])", l)) for l in raw) > \
        sum(len(re.findall(r"(?<![\d.,])\d{1,3}(?:\.\d{3})+,\d{2}(?![\d%])", l)) for l in raw)
    folded = [" ".join(fold(l).split()) for l in raw]
    amounts = [_row_amounts(l, english) for l in raw]
    totals, total_lines = [], set()  # (line, total, end column); the lines holding a total's amount
    for i, f in enumerate(folded):
        if _TOTAL_LINE.search(f):
            if amounts[i]:
                totals.append((i, *amounts[i][-1]))
                total_lines.add(i)
            elif i and len(amounts[i - 1]) == 1 and not re.search(r"[^\W\d_]", raw[i - 1]):
                totals.append((i, *amounts[i - 1][0]))  # «762.039,00» alone on the line above «΢ΤΝΟΛΟ :»
                total_lines.add(i - 1)
    stated = {cents(m.group("fig")) for m in _STATED_TOTAL.finditer(" ".join(folded))}
    out = []
    # a payment order's lines («79262223  ΔΗΜΟΣ ΤΗΝΟΥ  4.538,40»), against the total amount the text states
    pay = [(j, amounts[j][-1][0]) for j in range(len(raw)) if _PAYMENT_ROW.match(raw[j]) and amounts[j]]
    if pay and sum(v for _, v in pay) in stated:
        for j, v in pay:
            if uid := _payee([folded[j]], codes):
                out.append(GrantAmount(v, v, "table", "stated_amount",
                                       f"payment line; {len(pay)} lines adding up to the stated {sum(x for _, x in pay) / 100:.2f}",
                                       uid))
        return out
    sections = [(start_i, i, total, col) for (i, total, col), start_i in
                zip(totals, [0] + [t[0] + 1 for t in totals[:-1]])]
    for lo, hi, total, col in sections:
        body = [j for j in range(lo, hi) if j not in total_lines and not _TOTAL_LINE.search(folded[j]) and amounts[j]]
        candidates = []
        if col is not None:
            candidates += [(f"the total's column (±{d})", [(j, v) for j in body for v, e in amounts[j] if abs(e - col) <= d])
                           for d in (3, 8)]
        candidates += [("the lines with a project code", [(j, amounts[j][-1][0]) for j in body
                                                          if _PROJECT_CODE.search(folded[j])]),
                       ("the numbered rows", [(j, amounts[j][-1][0]) for j in body if _NUMBERED_ROW.match(raw[j])])]
        # every amount from the table's first row on (a row's cells wrap: its amount can sit a line or two above its
        # number)
        first = next((j for j in range(lo, hi) if _NUMBERED_ROW.match(raw[j]) or _PROJECT_CODE.search(folded[j])), None)
        if first is not None:
            candidates.append(("every amount of the table", [(j, v) for j in body if j >= first - 3
                                                             for v, _ in amounts[j]]))
        chosen = next(((how, cells) for how, cells in candidates if cells and sum(v for _, v in cells) == total), None)
        how, cells = chosen or candidates[0]
        rows = sorted({j for j, _ in cells})
        for j, v in cells:
            nxt = next((k for k in rows if k > j), hi)
            uid = _row_payee(folded, j, min(j + 4, nxt, hi), codes)
            if uid:
                out.append(GrantAmount(v, v, "table", "stated_amount" if chosen else None,
                                       f"row in {how}: {len(cells)} amounts adding up to "
                                       f"{sum(x for _, x in cells) / 100:.2f}; section total {total / 100:.2f}", uid))
    return out


def read_pde(text: str, family: str, subject: str | None = None,
             codes: dict[str, str] | None = None) -> tuple[list[GrantAmount], str, str]:
    if family not in ("pde_financing", "espa_financing", "pde_authorisation", "rrf_payment"):
        return [], "listed", family
    flat = _flat(text.translate(_SHIFTED))
    uid = _payee([flat, fold(subject)], codes)
    if not uid:
        return [], "absent", family
    rows = read_rows(text, codes)
    if rows:
        return rows, "read", family
    manager = re.search(r"(?:ΥΠΟΛΟΓΟ\w*.{0,3}ΔΙΑΧΕΙΡΙΣΤ\w*).{0,80}?ΔΗΜΟ\w* ΤΗΝΟΥ", flat)
    project = next((c for c, u in (codes or {}).items() if (c in flat or c in fold(subject)) and u == uid), None)
    if manager or project:
        amounts = _letter(flat, "credited to the project account the municipality manages" if manager else
                          f"credited to the account of project {project}, the municipality's", subject)
        return amounts, ("read" if amounts else "not_found"), family
    return [], "not_found", family


# ---------------------------------------------------------------------------
# The tourism organisation (ΕΟΤ)
# ---------------------------------------------------------------------------
_EOT_PAYEE = re.compile(r"ΔΙΚΑΙΟΥΧΟΣ\s*:\s*ΔΗΜΟΣ ΤΗΝΟΥ\s*\(\s*ΑΦΜ\s*:\s*(?P<afm>\d{9})")
_EOT_AMOUNTS = re.compile(rf"ΕΝΤΕΛΛΟΜΕΝΟ\s+ΣΥΝΟΛΟ\s+ΠΛΗΡΩΤΕΟ\s+(?P<gross>{_AMT})\s+(?P<withheld>{_AMT})\s+(?P<net>{_AMT})")
_EOT_WORDS = re.compile(r"ΣΥΝΟΛΟ ΕΝΤΑΛΜΑΤΟΣ\s*:\s*(?P<words>[^\d]{3,120}?ΕΥΡΩ)")


def read_eot(text: str, family: str, subject: str | None = None,
             codes: dict[str, str] | None = None) -> tuple[list[GrantAmount], str, str]:
    if family != "eot_payment":
        return [], "listed", family
    flat = _flat(text)
    payee, amounts = _EOT_PAYEE.search(flat), _EOT_AMOUNTS.search(flat)
    if not payee or not amounts:
        return [], "not_found", family
    if payee.group("afm") not in (TINOS_AFM, OLD_TINOS_AFM):
        return [], "absent", family
    gross, withheld, net = (cents(amounts.group(k)) for k in ("gross", "withheld", "net"))
    words = _EOT_WORDS.search(flat)
    w = words_to_cents(words.group("words")) if words else None
    ok = "words_and_figures" if w == gross and gross - withheld == net else None
    return [GrantAmount(gross, net, "payment_order", ok,
                        f"payee Δήμος Τήνου (ΑΦΜ {payee.group('afm')}, before the 2011 merger); gross {gross / 100:.2f}, "
                        f"withheld {withheld / 100:.2f}, net {net / 100:.2f}, words {w / 100 if w is not None else None}")], \
        "read", family


READERS = {
    "53992": read_ped,
    "99201054": read_green_fund,
    "100015969": read_shipping,
    "99221315": read_eot,
    **{u: read_pde for u in ("15", "100016002", "100025890", "100054495", "100081597", "100025905", "100016011",
                            "100054486")},
}
