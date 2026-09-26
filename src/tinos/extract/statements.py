"""Budget execution statements of Δήμος Τήνου: parse and validate.

Diavgeia carries the monthly statement (type Β.3, «ΔΗΜΟΣΙΕΥΣΗ ΣΤΟΙΧΕΙΩΝ ΕΚΤΕΛΕΣΗΣ
ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ») as a born-digital PDF: the municipality's own account, per
ΚΑΕ and cumulative from 1 January, of what was budgeted, warranted and paid
(spending) and budgeted, assessed and collected (revenue). It is the
denominator for every Diavgeia payment figure (FINDINGS.md F6).

Input is the text ``pdftotext -layout`` makes of the stored PDF. Layouts seen:

- ``standard`` (statements for 2015-2024): «Στοιχεία Εκτέλεσης Προϋπολογισμού»,
  «Περίοδος: <μήνας> <έτος>», one row per 4-digit ΚΑΕ with its three amounts,
  totals «ΣΥΝΟΛΟ ΕΣΟΔΩΝ» and «ΣΥΝΟΛΟ ΕΞΟΔΩΝ».
- ``2025`` (from the 2025 year-end statement, new software): «ΚΑΤΑΣΤΑΣΗ ΕΚΤΕΛΕΣΗΣ
  ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ ΕΣΟΔΩΝ|ΔΑΠΑΝΩΝ ΕΩΣ dd/mm/yyyy»; spending keyed by service and
  ΚΑΕ (``00-6031``; the reserve 9111 has no service); a row's amounts may
  continue on its description line;
  one «ΓΕΝΙΚΟ ΣΥΝΟΛΟ:» per side.
- The 2014 year-end statement has a third layout, with subtotal rows and the
  figures of December alone rather than the year. It is refused, not guessed.

Validation is mandatory: every amount column must sum to the document's own
total line, to the cent, on both sides, or :class:`StatementError` is raised.

Amounts are «1.234,56» not glued to other digits: no digit before, no digit or
«%» after. «άρθρα 230,242» and «0,50%» in a description are not amounts; «από
τους118.970,00» and «άρ.4.329.159,47», where the 2025 layout ran a wrapped amount
into the description, are.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

_AMT = r"-?\d{1,3}(?:\.\d{3})*,\d{2}"
AMOUNT = re.compile(rf"(?<!\d){_AMT}(?![\d%])")
MONTHS = {"Ιανουάριος": 1, "Φεβρουάριος": 2, "Μάρτιος": 3, "Απρίλιος": 4, "Μάιος": 5, "Ιούνιος": 6,
          "Ιούλιος": 7, "Αύγουστος": 8, "Σεπτέμβριος": 9, "Οκτώβριος": 10, "Νοέμβριος": 11, "Δεκέμβριος": 12}
SIDES = ("revenue", "spending")

_STD_ROW = re.compile(rf"^\s*(\d{{4}})\s+(.*?)\s+({_AMT})\s+({_AMT})\s+({_AMT})\s*$")
_STD_TOTAL = re.compile(rf"ΣΥΝΟΛΟ (ΕΣΟΔΩΝ|ΕΞΟΔΩΝ)\s+({_AMT})\s+({_AMT})\s+({_AMT})")
_STD_PERIOD = re.compile(r"Περίοδος:\s*(\S+)\s+(\d{4})")
_NEW_SECTION = re.compile(r"ΚΑΤΑΣΤΑΣΗ ΕΚΤΕΛΕΣΗΣ ΠΡΟΫΠΟΛΟΓΙΣΜΟΥ (ΕΣΟΔΩΝ|ΔΑΠΑΝΩΝ) ΕΩΣ (\d{1,2})/(\d{1,2})/(\d{4})")
# Rows start at column 0; wrapped descriptions and amounts are indented. The
# reserve (9111) has no service prefix.
_NEW_REVENUE = re.compile(r"^(\d{4})\s")
_NEW_SPENDING = re.compile(r"^(?:(\d{2})-)?(\d{4})\s")


class StatementError(Exception):
    """Not a statement we can read exactly; nothing from it may be used."""


@dataclass(frozen=True)
class Line:
    side: str  # 'revenue' | 'spending'
    service: str | None  # service prefix where the layout has one ('00' ...)
    kae: str  # 4-digit ΚΑΕ
    budgeted: int  # cents: Προϋπολογισθέντα / τελικός προϋπολογισμός
    assessed_or_warranted: int  # cents: Βεβαιωθέντα (revenue) / Ενταλματοποιηθέντα (spending)
    collected_or_paid: int  # cents: Εισπραχθέντα (revenue) / Πληρωθέντα (spending)
    description: str = ""  # the line's name as printed (may be cut short by the layout)


@dataclass(frozen=True)
class Statement:
    layout: str
    period_end: date
    lines: tuple[Line, ...]
    totals: dict[str, tuple[int, int, int]]  # side -> the document's own totals, cents


def cents(s: str) -> int:
    """«1.234,56» -> 123456."""
    neg = s.startswith("-")
    whole, frac = s.lstrip("-").replace(".", "").split(",")
    v = int(whole) * 100 + int(frac)
    return -v if neg else v


# Symbols some PDFs print for Greek letters: ∆ (U+2206) for Δ, µ (micro, U+00B5) for μ, Ω (ohm,
# U+2126) for Ω. The port authority's 2016-2017 statements write «Περίοδος: ∆εκέµβριος 2017».
_SYMBOLS = str.maketrans({"\u2206": "Δ", "\u00b5": "μ", "\u2126": "Ω"})


def parse_statement(text: str) -> Statement:
    text = text.translate(_SYMBOLS)
    if "Στοιχεία Εκτέλεσης Προϋπολογισμού" in text and _STD_PERIOD.search(text):
        st = _parse_standard(text)
    elif _NEW_SECTION.search(text):
        st = _parse_2025(text)
    else:
        raise StatementError("unknown or unsupported statement layout")
    validate(st)
    return st


def validate(st: Statement) -> None:
    for side in SIDES:
        if side not in st.totals:
            raise StatementError(f"no {side} total line found")
        rows = [ln for ln in st.lines if ln.side == side]
        sums = (sum(r.budgeted for r in rows), sum(r.assessed_or_warranted for r in rows),
                sum(r.collected_or_paid for r in rows))
        if sums != st.totals[side]:
            raise StatementError(f"{side}: {len(rows)} rows sum to {sums}, the document says {st.totals[side]}")


def _parse_standard(text: str) -> Statement:
    m = _STD_PERIOD.search(text)
    month = MONTHS.get(m.group(1))
    if month is None:
        raise StatementError(f"unknown month {m.group(1)!r}")
    year = int(m.group(2))
    lines: list[Line] = []
    totals: dict[str, tuple[int, int, int]] = {}
    seen: set[tuple[str, str]] = set()
    for raw in text.splitlines():
        if t := _STD_TOTAL.search(raw):
            totals["revenue" if t.group(1) == "ΕΣΟΔΩΝ" else "spending"] = (
                cents(t.group(2)), cents(t.group(3)), cents(t.group(4)))
            continue
        if r := _STD_ROW.match(raw):
            kae = r.group(1)
            side = "revenue" if kae[0] in "012345" else "spending"
            if (side, kae) in seen:
                raise StatementError(f"ΚΑΕ {kae} appears twice")
            seen.add((side, kae))
            lines.append(Line(side, None, kae, cents(r.group(3)), cents(r.group(4)), cents(r.group(5)),
                              " ".join(r.group(2).split())))
    end = date(year, month, calendar.monthrange(year, month)[1])
    return Statement("standard", end, tuple(lines), totals)


def _parse_2025(text: str) -> Statement:
    side: str | None = None
    period_end: date | None = None
    records: list[tuple[str, str | None, str, list[int], list[str]]] = []
    current: list[int] | None = None
    names: list[str] = []
    totals: dict[str, tuple[int, int, int]] = {}
    for raw in text.splitlines():
        if s := _NEW_SECTION.search(raw):
            side = "revenue" if s.group(1) == "ΕΣΟΔΩΝ" else "spending"
            end = date(int(s.group(4)), int(s.group(3)), int(s.group(2)))
            if period_end not in (None, end):
                raise StatementError(f"sections end on different dates: {period_end} and {end}")
            period_end, current = end, None
            continue
        if side is None:
            continue
        if "ΓΕΝΙΚΟ ΣΥΝΟΛΟ" in raw:
            amounts = [cents(a) for a in AMOUNT.findall(raw)]
            if len(amounts) != 3:
                raise StatementError(f"{side} total line has {len(amounts)} amounts: {raw.strip()!r}")
            totals[side] = tuple(amounts)
            current = None
            continue
        start = (_NEW_REVENUE if side == "revenue" else _NEW_SPENDING).match(raw)
        if start:
            service, kae = (None, start.group(1)) if side == "revenue" else (start.group(1), start.group(2))
            current, names = [], []
            records.append((side, service, kae, current, names))
            raw = raw[start.end():]
        if current is not None:
            # The name is the first text on the row, or on the next line when the row has none;
            # text after all three amounts (page footers, headers) is not part of it.
            text = " ".join(AMOUNT.sub(" ", raw).split())
            if text and not names and len(current) < 3:
                names.append(text)
            current.extend(cents(a) for a in AMOUNT.findall(raw))
    lines = []
    for rside, service, kae, amounts, name in records:
        if len(amounts) != 3:
            raise StatementError(f"{rside} {service or ''}-{kae}: {len(amounts)} amounts, expected 3")
        lines.append(Line(rside, service, kae, *amounts, name[0] if name else ""))
    if period_end is None:
        raise StatementError("no section header with a period end")
    return Statement("2025", period_end, tuple(lines), totals)
