"""Grants and allocations to Tinos: which decision is which, and where it lands in the budget.

The Interior Ministry's decisions found by ``tinos fulltext-backfill`` are
classified by subject into *families* (:data:`FAMILIES`, first match wins).
A family says what the money is for and which *category* of the
municipality's revenue it should arrive in (:data:`CATEGORY_OF_FAMILY`). The
revenue side of the year-end execution statements (``budget_line``, side
``revenue``) is sorted into the same categories by line description
(:data:`REVENUE_CATEGORIES`), not by ΚΑΕ code: the chart moved grant lines
between codes over the years (ΚΑΠ investment is 1311 to 2023 and 0612 from
2024, when 0612 had meant school rents in 2015-2017; fire protection moved from
1214 to 0614; the schools' ΚΑΠ from 0614 to 4311 to 0616).

Families that are approvals or ceilings rather than money sent
(programme inclusion, invitations) map to no category: they are listed, not
reconciled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tinos.sources.fulltext import fold

# (family, pattern on the folded subject). Order matters: specific before general.
_W = r"(?<![^\W\d_])"   # word start
_E = r"(?![^\W\d_])"    # word end
FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = tuple((name, re.compile(p)) for name, p in (
    # Not money to the municipality: grants to the Regions, masks bought through the Central Union
    # of Municipalities for them (in kind).
    ("to_regions", r"ΕΠΙΧΟΡΗΓΗΣΗ ΤΩΝ ΠΕΡΙΦΕΡΕΙΩΝ|ΣΤΙΣ ΠΕΡΙΦΕΡΕΙΕΣ"),
    ("in_kind", r"ΚΕΝΤΡΙΚΗΣ ΕΝΩΣΗΣ ΔΗΜΩΝ"),
    # The order moving an allocation's ΚΑΠ credits, issued with the allocation itself (2015: school
    # repairs 615Ζ465ΦΘΕ-ΑΡ0 with 7ΛΞ9465ΦΘΕ-9Ι1, fire protection Ω40Λ465ΦΘΕ-ΧΝΙ with 6ΖΒΘ465ΦΘΕ-Σ2Σ,
    # same day, same amounts): the same money again, listed, never reconciled.
    ("kap_transfer_order", r"ΕΝΤΟΛΗ ΜΕΤΑΦΟΡΑΣ ΠΙΣΤΩΣΕΩΝ.*ΑΥΤΟΤΕΛ(?:ΕΙΣ|ΩΝ) ΠΟΡ"),
    # Approvals of financing (and their amendments), paid out later by transfer letters.
    ("pde_approval", r"^ΧΡΗΜΑΤΟΔΟΤΗΣΗ ΤΟΥ ΔΗΜΟΥ|ΑΠΟΦΑΣΗΣ? ΧΡΗΜΑΤΟΔΟΤΗΣΗΣ|ΑΠΟΦΑΣΗΣ ΕΠΙΧΟΡΗΓΗΣΗΣ|ΑΠΟΡΡΙΜΜΑΤΟΦΟΡ"),
    # Public-investment cash: ΣΑΕ/ΣΑΝΑ allocations and transfer orders, whatever the programme.
    ("pde_financing", r"ΜΕΤΑΦΟΡΑΣ ΠΙΣΤΩΣΕΩΝ|ΚΑΤΑΝΟΜΗ ΧΡΗΜΑΤΟΔΟΤΗΣΗΣ|ΕΝΤΟΛΗ ΧΡΗΜΑΤΟΔΟΤΗΣΗΣ|ΑΙΤΗΜΑ ΧΡΗΜΑΤΟΔΟΤΗΣΗΣ|"
                      r"ΧΡΗΜΑΤΟΔΟΤΗΣΗΣ? ΤΟΥ ΔΗΜΟΥ|" + _W + r"(ΣΑΕ|ΣΑΝΑ|ΝΑ ?255)" + _E),
    # Approvals, inclusions, invitations and their amendments: entitlements, not money sent.
    ("programme", r"ΦΙΛΟΔΗΜ|ΤΡΙΤΣΗ|ΕΝΤΑΞ|ΠΡΟΣΚΛΗΣ|ΠΡΟΘΕΣΗΣ ΧΡΗΜΑΤΟΔΟΤΗΣΗΣ|ΕΝΤΑΓΜΕΝΩΝ"),
    ("school_cleaners", r"ΠΡΟΣΩΠΙΚΟΥ ΚΑΘΑΡΙΟΤΗΤΑΣ"),
    ("welfare_benefits", r"ΠΡΟΝΟΙΑΚ"),
    ("citizen_centres", r"ΚΕΝΤΡΩΝ ΕΞΥΠΗΡΕΤΗΣΗΣ ΠΟΛΙΤΩΝ|" + _W + r"ΚΕΠ" + _E),
    ("school_meals", r"ΣΙΤΙΣΗ"),
    ("shore_rents", r"ΜΙΣΘΩΜΑΤΑ .*ΚΑΤΕΒΛΗΘΗΣΑΝ|ΑΙΓΙΑΛ"),
    ("school_rents", r"ΚΑΤΑΒΟΛΗ ΜΙΣΘΩΜΑΤΩΝ|ΜΙΣΘΩΜΑΤΩΝ ΤΩΝ ΣΧΟΛΙΚ"),
    ("school_repairs", r"ΣΥΝΤΗΡΗΣΗ\w* ΣΧΟΛΙΚ"),
    ("school_operating", r"ΣΧΟΛΙΚ|ΣΧΟΛΕΙ"),
    ("home_help", r"ΒΟΗΘΕΙΑ ΣΤΟ ΣΠΙΤΙ|ΣΤΗΡΙΞΗΣ ΗΛΙΚΙΩΜΕΝΩΝ"),
    ("fire_protection", r"ΠΥΡΟΠΡΟΣΤΑΣ|ΠΥΡΚΑΓΙ"),
    ("desalination", r"ΑΦΑΛΑΤΩΣ"),
    ("lifeguards", r"ΝΑΥΑΓΟΣΩΣΤ"),
    ("stray_animals", r"ΑΔΕΣΠΟΤ"),
    ("road_waste", r"ΑΠΟΚΟΜΙΔΗΣ ΑΠΟΡΡΙΜΜΑΤΩΝ ΤΟΥ ΟΔΙΚΟΥ"),
    ("covid", r"ΚΟΡΟΝΟΙ|COVID"),
    ("property_tax", r"ΤΕΛΟΣ ΑΚΙΝΗΤΗΣ ΠΕΡΙΟΥΣΙΑΣ|" + _W + r"ΤΑΠ" + _E),
    ("advertising_fee", r"ΤΕΛΟΣ ΔΙΑΦΗΜΙΣΗΣ"),
    ("beer_tax", r"ΖΥΘΟΥ"),
    ("cruise_levy", r"ΚΡΟΥΑΖΙΕΡ"),
    ("election_costs", r"ΕΚΛΟΓΙΚ"),
    ("arrears", r"ΛΗΞΙΠΡΟΘΕΣΜ|ΔΙΑΤΑΓΕΣ ΠΛΗΡΩΜΗΣ|ΔΙΚΑΣΤΙΚ|ΠΑΣΗΣ ΦΥΣΕΩΣ ΟΦΕΙΛΩΝ"),
    # The monthly general ΚΑΠ first: some of its subjects go on to mention investment spending.
    ("kap_general_monthly", r"ΑΥΤΟΤΕΛ.*ΛΕΙΤΟΥΡΓΙΚΩΝ ΚΑΙ ΛΟΙΠΩΝ ΓΕΝΙΚΩΝ ΔΑΠΑΝΩΝ"),
    ("kap_investment", r"ΕΠΕΝΔΥΤΙΚ|ΕΚΤΕΛΕΣΗΣ ΕΡΓΩΝ|" + _W + r"ΣΑΤΑ" + _E),
    ("kap_general", r"ΑΥΤΟΤΕΛΕΙΣ ΠΟΡΟΥΣ|ΑΥΤΟΤΕΛΩΝ ΠΟΡΩΝ|" + _W + r"ΚΑΠ" + _E),
    ("extraordinary", r"ΕΠΙΧΟΡΗΓ"),
))

# The Region of South Aegean (5011) gives Tinos money two ways (probe and backfill 2026-09-26): credits
# of its investment programme (ΣΑΕΠ/ΣΑΜΠ) for a project a Tinos body carries out, each tranche decided
# twice, «Κατανομή ποσού X» then «Έγκριση πίστωσης X» («Διάθεση πίστωσης» from 2021), the second
# counted; and payment orders titled only «ΕΝΤΑΛΜΑ ΠΛΗΡΩΜΗΣ», found by the municipality's ΑΦΜ. A credit
# for a project of the Region's own (its roads, its buildings) is not money to Tinos: `region_credit`
# needs a subject naming a Tinos body or a decision found by the ΑΦΜ (curated_grants).
REGION_UIDS = frozenset({"5011"})
REGION_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = tuple((name, re.compile(p)) for name, p in (
    ("region_payment", r"^ΕΝΤΑΛΜΑ ΠΛΗΡΩΜΗΣ"),
    ("region_credit", r"^(?:ΕΓΚΡΙΣΗ|ΔΙΑΘΕΣΗ) ΠΙΣΤΩΣΗΣ [\d.,]+ ?€ ΣΕ ΒΑΡΟΣ"),
    ("region_allocation", r"^ΚΑΤΑΝΟΜΗ ΠΟΣΟΥ [\d.,]+ ?€ (?:ΓΙΑ|ΣΕ ΒΑΡΟΣ)"),
    ("region_fine", r"ΠΡΟΣΤΙΜ|ΚΥΡΩΣΕ"),
    ("region_agreement", r"ΠΡΟΓΡΑΜΜΑΤΙΚ|ΔΙΑΒΑΘΜΙΔΙΚ|" + _W + r"ΠΣ (?:ΠΝΑ|ΜΕΤΑΞΥ)" + _E),
    ("programme", r"ΕΝΤΑΞ|ΕΝΤΑΓΜΕΝ|ΠΡΑΞΗΣ|ΠΡΟΣΚΛΗΣ|ΑΠΟΡΡΙΨ"),
    ("region_licence", r"ΑΔΕΙ|ΥΠΑΓΩΓΗ|ΓΝΩΜΟΔΟΤ|ΠΕΡΙΒΑΛΛΟΝΤΙΚ|ΧΩΡΟΘΕΤΗΣ"),
))

# The revenue line (by name) where each family's money should arrive. None: listed, not
# reconciled (approvals and ceilings, money to others, in kind). The chart moved several of these
# lines between codes over the years, hence names, not codes (module docstring).
CATEGORY_OF_FAMILY: dict[str, str | None] = {
    "kap_general": "kap_general",
    "kap_investment": "kap_investment",
    "school_operating": "kap_schools",
    "school_rents": "school_rents",
    "school_repairs": "school_repairs",
    "fire_protection": "fire_protection",
    "school_cleaners": "school_cleaners",
    "home_help": "home_help",
    "desalination": "kap_other",
    "road_waste": "kap_other",
    "covid": "kap_other",
    "citizen_centres": "kap_other",
    "school_meals": "kap_other",
    "welfare_benefits": "welfare",
    "extraordinary": "state_grants",
    "arrears": "state_grants",
    "lifeguards": "state_grants",
    "stray_animals": "kap_other",  # booked under 0619 (2023, 2025: 5,300.00 each)
    "election_costs": "state_grants",
    "cruise_levy": "state_grants",
    "pde_financing": "investment_programmes",
    "advertising_fee": "advertising_fee",
    "property_tax": "property_tax",
    "beer_tax": None,
    "shore_rents": None,
    "pde_approval": None,
    "kap_transfer_order": None,
    "programme": None,
    "to_regions": None,
    "in_kind": None,
    "other": None,
    # the Region: its investment credits land where the ministry's investment programmes do (1322 in
    # 2018-2019, matched to the cent); the rest is listed, not reconciled
    "region_credit": "investment_programmes",
    "region_agreement_payment": "programme_agreements",  # 1213, 1326
    "region_utility_payment": None,  # the Region's water bill: a sale by the municipality, not a grant
    "region_payment": None,
    "region_allocation": None,
    "region_own_credit": None,
    "region_fine": None,
    "region_agreement": None,
    "region_licence": None,
}

# Revenue lines of the year-end statement, by folded name (first match wins); ``kae`` narrows
# the few names shared by a current-year line and a prior-year receivable (group 32).
REVENUE_CATEGORIES: tuple[tuple[str, re.Pattern[str]], ...] = tuple((name, re.compile(p)) for name, p in (
    ("kap_general", r"ΚΑΠ ΓΙΑ ΚΑΛΥΨΗ ΓΕΝΙΚΩΝ"),
    ("kap_investment", r"ΚΑΠ ΕΠΕΝΔΥΤΙΚΩΝ"),
    ("kap_schools", r"ΚΑΠ ΓΙΑ ΤΗΝ ΚΑΛΥΨΗ ΤΩΝ ΛΕΙΤΟΥΡΓΙΚΩΝ"),
    ("school_rents", r"ΚΑΠ ΓΙΑ ΤΗΝ ΚΑΤΑΒΟΛΗ ΜΙΣΘΩΜΑΤΩΝ"),
    ("school_repairs", r"ΕΠΙΣΚΕΥΗ ΚΑΙ ΣΥΝΤΗΡΗΣΗ ΣΧΟΛΙΚΩΝ"),
    ("fire_protection", r"ΠΥΡΟΠΡΟΣΤΑΣΙΑ"),
    ("school_cleaners", r"ΜΙΣΘΟΔΟΣΙΑΣ ΠΡΟΣΩΠΙΚΟΥ ΚΑΘΑΡΙΟΤΗΤΑΣ"),
    ("home_help", r"ΒΟΗΘΕΙΑ ΣΤΟ ΣΠΙΤΙ"),
    ("kap_other", r"ΚΑΠ ΓΙΑ ΛΟΙΠΟΥΣ ΣΚΟΠΟΥΣ"),
    ("welfare", r"ΠΡΟΝΟΙΑΚ"),
    ("investment_programmes", r"ΘΗΣΕΑΣ|ΦΙΛΟΔΗΜΟΣ|ΕΙΔΙΚΑ ΠΡΟΓΡΑΜΜΑΤΑ ΠΡΟΓΡΑΜΜΑ|ΚΕΝΤΡΙΚΟΥΣ ΦΟΡΕΙΣ"),
    ("advertising_fee", r"^ΤΕΛΟΣ ΔΙΑΦΗΜΙΣΗΣ.*ΚΑΤΗΓΟΡΙΑΣ Δ"),  # 0715; 0462 is the municipality's own fee
    ("property_tax", r"^ΤΕΛΟΣ ΑΚΙΝΗΤΗΣ ΠΕΡΙΟΥΣΙΑΣ"),
    ("programme_agreements", r"ΠΡΟΓΡΑΜΜΑΤΙΚΕΣ ΣΥΜΒΑΣΕΙΣ"),  # 1213 operating, 1326 investment
))
# The state's operating grants to municipalities, by code: their names changed more than their codes.
STATE_GRANT_KAE = ("1211", "1215", "1219")


def family_of(subject: str | None, issuer: str | None = None) -> str:
    s = fold(subject)
    if issuer in REGION_UIDS:
        return next((name for name, pattern in REGION_FAMILIES if pattern.search(s)), "other")
    for name, pattern in FAMILIES:
        if pattern.search(s):
            return "kap_general" if name == "kap_general_monthly" else name
    return "other"


def revenue_category(kae: str, description: str | None) -> str | None:
    """The reconciliation line of a revenue line, or None for revenue that is not such a transfer."""
    if not kae.startswith(("0", "1", "43")):
        return None  # prior-year receivables (2x/3x), loans (31), withholdings (41, 42), balances (5x)
    # 43xx is revenue collected for others: the schools' ΚΑΠ sat there (4311) in 2019-2024.
    if kae in STATE_GRANT_KAE:
        return "state_grants"
    d = fold(description)
    for name, pattern in REVENUE_CATEGORIES:
        if pattern.search(d):
            return name
    return None


# ---------------------------------------------------------------------------
# Allocation tables in the decision's PDF (``pdftotext -layout``)
# ---------------------------------------------------------------------------
# The Interior Ministry's tables list municipalities by their code at the Ταμείο
# Παρακαταθηκών και Δανείων (ΤΠΔ): Δήμος Τήνου is 58216. A row is an optional
# serial number (Α/Α), the code, the name and prefecture, and one or more
# columns. Only currency amounts («1.234,56», «- €» for zero) are columns here;
# counts, hours and kilometres («79», «42,0», «41.150») are skipped. A token
# shaped like an amount but malformed («50.0000,00», a typo in one 2023 table)
# keeps its column as unreadable, so the other columns still line up.
TINOS_TPD_CODE = "58216"
_AMT = r"-?\d{1,3}(?:\.\d{3})*,\d{2}"
AMOUNT = re.compile(rf"(?<![\d.,]){_AMT}(?![\d%])")
_TOKEN = re.compile(rf"(?<![\d.,])(?:(?P<amt>{_AMT})(?![\d%])|(?P<bad>\d[\d.]*,\d{{2}})(?![\d%])|(?P<dash>-)(?=\s*€))")
_ROW = re.compile(r"^\s*(?:(\d{1,4})\s+)?(\d{1,5})(?:\s+((?:[-–]\s*)?[^\W\d_].*))?\s*$")
_TOTAL = re.compile(r"ΣΥΝΟΛ")
# «... με το ποσό # 3.087,60 € # ...»: the amount a transfer order states, between hash marks.
_STATED = re.compile(rf"#\s*({_AMT})\s*€?\s*#")


def cents(s: str) -> int:
    """«1.234,56» -> 123456."""
    neg = s.startswith("-")
    whole, frac = s.lstrip("-").replace(".", "").split(",")
    v = int(whole) * 100 + int(frac)
    return -v if neg else v


def amounts_in(text: str) -> tuple[int | None, ...]:
    """Currency columns of a line, in cents; None for a malformed amount."""
    return tuple(v for v, _ in amounts_at(text))


def amounts_at(text: str) -> list[tuple[int | None, int]]:
    """(cents, end offset) of each currency column of a line."""
    return [(cents(m.group("amt")) if m.group("amt") else 0 if m.group("dash") else None, m.end())
            for m in _TOKEN.finditer(text)]


@dataclass(frozen=True)
class Row:
    number: int | None  # Α/Α, when the table numbers its rows
    code: str  # ΤΠΔ code (5 digits; a code split across two lines leaves a stub)
    text: str  # name, prefecture and any non-currency columns
    amounts: tuple[int | None, ...]  # cents, currency columns in order; None = unreadable
    ends: tuple[int, ...] = ()  # where each amount ends on its line (to place blank cells)
    filled: bool = False  # blank cells were read as zero, placed by the neighbouring rows' columns


@dataclass(frozen=True)
class Table:
    rows: tuple[Row, ...]
    totals: tuple[int, ...] | None  # the document's own total line, cents
    valid_columns: tuple[bool, ...]  # column j sums to its total, every cell readable
    layout: str  # single | sum | net | columns
    signs: tuple[int, ...]  # net layout: +1/-1 per middle column (gross + Σ sign·col = net)
    validation: str | None  # column_totals | stated_amount | None
    note: str = ""


@dataclass(frozen=True)
class TinosLine:
    table: int
    row: Row
    amount: int | None  # cents: what the table allocates to Tinos (None: not established)
    net: int | None  # cents: what is paid after withholdings (``net`` layout), else = amount
    layout: str
    validation: str | None  # how the column ``amount`` comes from was validated; None if not
    n_rows: int
    table_total: int | None  # cents, total of the column ``amount`` comes from


def _signs(totals: tuple[int, ...], rows: tuple[Row, ...]) -> tuple[int, ...] | None:
    """Signs s in {-1, 0, +1} so that col[-1] == col[0] + Σ s·col[1:-1] on the totals and on every
    complete row: withholdings subtract, returns add, a breakdown column (0) enters no row's net.
    Fewest zeros first."""
    import itertools
    middle = len(totals) - 2
    if middle < 1 or middle > 7:
        return None
    candidates = sorted(itertools.product((-1, 1, 0), repeat=middle), key=lambda sg: sg.count(0))
    for signs in candidates:
        def gap(v: tuple[int | None, ...]) -> int:
            return abs(v[-1] - v[0] - sum(sg * x for sg, x in zip(signs, v[1:-1])))
        if gap(totals) <= ROUNDING_CENTS and all(gap(r.amounts) <= 2 for r in rows if None not in r.amounts):
            return signs
    return None


# Symbols some PDFs use for Greek capitals (the 2019 ΣΑΤΑ table writes every Δ as ∆, U+2206).
_SYMBOLS = str.maketrans({"\u2206": "Δ", "\u2126": "Ω", "\u00b5": "μ"})
# The source's own total lines can miss the sum of the printed rows by rounding: each row is
# rounded to the cent (at most half a cent of drift per row) and withholdings are computed by
# percentage. A column is accepted within max(10 cents, half a cent per row) and the difference
# is recorded; a row left out would be hundreds of euros, not cents.
ROUNDING_CENTS = 10


def _tolerance(n_rows: int) -> int:
    return max(ROUNDING_CENTS, (n_rows + 1) // 2)


def parse_allocation(text: str, subject: str | None = None) -> tuple[list[Table], list[int]]:
    """The allocation tables of a decision, each checked against its own totals.

    Tables keyed by ΤΠΔ code are read first (:func:`parse_coded`). When none
    gives Tinos a row with amounts, the table is read by name instead
    (:func:`parse_named`): older tables carry no code, and some print whole
    euros («29.700»).
    """
    tables, stated = parse_coded(text, subject)
    if any(r.code == TINOS_TPD_CODE and r.amounts for t in tables for r in t.rows):
        return tables, stated
    named = parse_named(text, stated)
    return (named, stated) if named else (tables, stated)


def parse_coded(text: str, subject: str | None = None) -> tuple[list[Table], list[int]]:
    """Every ΤΠΔ-coded table in ``text``, each checked against its own totals.

    Rows are lines that start with an optional Α/Α and a code. A row whose line
    holds no amounts takes them from the next or previous line when that line
    is not a row itself (multi-line cells put the figures above or below the
    code). A table ends at a line containing «ΣΥΝΟΛ» with amounts (its rightmost
    amounts are the column totals) or at a row numbered 1 after higher numbers.

    A column is valid when every cell is readable and they sum to the total
    line to the cent. The table is ``column_totals``-validated when all its
    columns are; with no total line, a one-column table is ``stated_amount``-
    validated when its sum equals an amount the text states between hash marks
    (``# 3.087,60 € #``) or the subject states («συνολικού ποσού 1.018.800,00€»).
    Row numbering is recorded, not required: one 2024 table numbers a row 81
    between 62 and 63, and the column totals already catch a missing row.
    Returns the tables and the stated amounts.
    """
    text = text.translate(_SYMBOLS)
    stated = [cents(m) for m in _STATED.findall(text)] + [cents(a) for a in AMOUNT.findall(subject or "")]
    tables: list[Table] = []
    rows: list[Row] = []
    lines = text.splitlines()
    kinds: list[tuple[str, object]] = []  # per line: ('row', match) | ('total', amounts) | ('amounts', amounts) | ('', None)
    for raw in lines:
        m = _ROW.match(raw)
        # A row has a 5-digit code or an Α/Α; with no name beside them (a name wrapped
        # above and below the code) it needs both.
        if m and (m.group(3) and (len(m.group(2)) == 5 or m.group(1)) or m.group(1) and len(m.group(2)) == 5):
            kinds.append(("row", m))
        elif _TOTAL.search(raw) and amounts_in(raw):
            kinds.append(("total", amounts_in(raw)))
        elif amounts_in(raw):
            kinds.append(("amounts", amounts_in(raw)))
        else:
            kinds.append(("", None))
    claimed: set[int] = set()

    def neighbour(i: int, step: int) -> int | None:
        j = i + step
        while 0 <= j < len(lines) and abs(j - i) <= 2:
            kind = kinds[j][0]
            if kind == "row" or kind == "total":
                return None
            if kind == "amounts" and j not in claimed:
                return j
            if lines[j].strip() and kind == "":
                j += step
                continue
            j += step
        return None

    def close(totals: tuple[int | None, ...] | None) -> None:
        if rows:
            tables.append(_check(tuple(rows), totals, stated))
            rows.clear()

    for i, (kind, obj) in enumerate(kinds):
        if kind == "row":
            m = obj
            number = int(m.group(1)) if m.group(1) else None
            if number == 1 and rows and (rows[-1].number or 0) > 1:
                close(None)
            found = amounts_at(lines[i]) if m.group(3) else []
            if not found:
                j = neighbour(i, 1)
                j = j if j is not None else neighbour(i, -1)
                if j is not None:
                    claimed.add(j)
                    found = amounts_at(lines[j])
            if not found:
                continue  # a line that only looks like a row (a wrapped name, a code stub alone)
            rows.append(Row(number, m.group(2), " ".join(_TOKEN.sub(" ", m.group(3) or "").split()),
                            tuple(v for v, _ in found), tuple(e for _, e in found)))
        elif kind == "total" and rows:
            close(obj)
    close(None)
    return tables, stated


# Name-keyed tables: any number is a column (whole euros «29.700», counts «1.190», amounts «8,50»).
_NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?"
_NAMED_ROW = re.compile(rf"^\s*(?:(\d{{1,4}})\s+)?(?:(\d{{4,5}})\s+)?([^\W\d_][^\d€]*?)\s+((?:(?:{_NUM})\s*€?\s*)+)$")
_NUM_TOKEN = re.compile(rf"(?<![\d.,])(?:{_NUM})(?![\d.,%])")
_TINOS_NAME = re.compile(r"(?<![^\W\d_])ΤΗΝΟΥ(?![^\W\d_])")


def number_cents(tok: str) -> int:
    """«29.700» -> 2970000, «8,5» -> 850, «1.234,56» -> 123456: every column in cents."""
    whole, _, frac = tok.partition(",")
    return int(whole.replace(".", "")) * 100 + int((frac + "00")[:2])


def parse_named(text: str, stated: list[int]) -> list[Table]:
    """The table holding a row named ΤΗΝΟΥ, read by name.

    Rows are lines ending in as many numbers as the Tinos line, numbered when
    the Tinos line is numbered, with a name in capitals otherwise, up to the
    next «ΣΥΝΟΛ» line, whose numbers are the column totals. Validation is the
    same as for coded tables.
    """
    text = text.translate(_SYMBOLS)
    lines = text.splitlines()
    parsed = [_NAMED_ROW.match(l) for l in lines]
    tinos = [i for i, m in enumerate(parsed) if m and _TINOS_NAME.search(fold(m.group(3)))]
    tables = []
    for i in tinos[:1]:
        m = parsed[i]
        k = len(_NUM_TOKEN.findall(m.group(4)))
        numbered = m.group(1) is not None
        ends = [j for j in range(i + 1, len(lines)) if _TOTAL.search(lines[j]) and _NUM_TOKEN.search(lines[j])]
        start = max((j for j in range(0, i) if _TOTAL.search(lines[j]) and _NUM_TOKEN.search(lines[j])), default=-1) + 1
        best = None
        for end in ends[:3] or [None]:  # the first total line whose numbers the rows add up to
            table = _named_table(lines, parsed, i, start, end, k, numbered, stated)
            if table is not None and (best is None or table.validation):
                best = table
            if best is not None and best.validation:
                break
        if best is not None:
            tables.append(best)
    return tables


def _named_table(lines, parsed, i, start, end, k, numbered, stated) -> Table | None:
        rows = []
        for j in range(start, end if end is not None else len(lines)):
            mj = parsed[j]
            if not mj or _TOTAL.search(lines[j]):
                continue
            toks = _NUM_TOKEN.findall(mj.group(4))
            name = mj.group(3).strip()
            if len(toks) != k or (numbered and mj.group(1) is None) or (not numbered and name != name.upper()):
                continue
            code = mj.group(2) or ""
            rows.append(Row(int(mj.group(1)) if mj.group(1) else None,
                            TINOS_TPD_CODE if j == i else code, name, tuple(number_cents(t) for t in toks)))
        totals = None
        if end is not None:
            totals = tuple(number_cents(t) for t in _NUM_TOKEN.findall(lines[end].split("ΣΥΝΟΛ", 1)[-1]))
        return _check(tuple(rows), totals, stated) if rows else None


def _fill_blanks(rows: tuple[Row, ...]) -> tuple[Row, ...]:
    """Rows with fewer amounts than the table's usual width get their amounts placed by the right
    edges of the nearest complete row's columns (within 4 characters), blank cells read as zero."""
    from collections import Counter
    if not rows or not all(r.ends for r in rows):
        return rows
    k = Counter(len(r.amounts) for r in rows).most_common(1)[0][0]
    full = [i for i, r in enumerate(rows) if len(r.amounts) == k]
    out = list(rows)
    for i, r in enumerate(rows):
        if len(r.amounts) >= k or not full:
            continue
        ref = rows[min(full, key=lambda j: abs(j - i))].ends
        cells: list[int | None] = [0] * k
        taken: set[int] = set()
        for v, e in zip(r.amounts, r.ends):
            col = min(range(k), key=lambda c: abs(ref[c] - e))
            if abs(ref[col] - e) > 4 or col in taken:
                break
            taken.add(col)
            cells[col] = v
        else:
            out[i] = Row(r.number, r.code, r.text, tuple(cells), ref, True)
    return tuple(out)


def _check(rows: tuple[Row, ...], totals: tuple[int | None, ...] | None, stated: list[int]) -> Table:
    rows = _fill_blanks(rows)
    widths = {len(r.amounts) for r in rows}
    numbers = [r.number for r in rows]
    numbered = "" if all(n is None for n in numbers) or numbers == list(range(1, len(rows) + 1)) \
        else "rows not numbered 1..N"
    if len(widths) != 1:
        return Table(rows, None, (), "columns", (), None, f"rows carry {sorted(widths)} amounts; {numbered}".strip("; "))
    k = widths.pop()
    readable = [all(r.amounts[j] is not None for r in rows) for j in range(k)]
    sums = tuple(sum(r.amounts[j] for r in rows) if readable[j] else None for j in range(k))
    filled = [r.number for r in rows if r.filled]
    numbered = "; ".join(x for x in (numbered, f"blank cells read as zero in rows {filled}" if filled else "") if x)
    if totals is not None and None not in totals and len(totals) < k:
        # The total line sums only the rightmost columns (a rate per person is not summed):
        # validate those, and read the amount from the last.
        n = len(totals)
        valid = tuple(False for _ in range(k - n)) + tuple(
            sums[j] is not None and abs(sums[j] - totals[j - (k - n)]) <= _tolerance(len(rows)) for j in range(k - n, k))
        padded = tuple(0 for _ in range(k - n)) + tuple(totals)
        note = "; ".join(x for x in (numbered, f"total line covers the last {n} of {k} columns") if x)
        return Table(rows, padded, valid, "last", (), "column_totals" if valid[-1] else None, note)
    if totals is not None:
        if None in totals:
            return Table(rows, None, (), "columns", (), None, "unreadable total line")
        totals = tuple(totals[-k:])
        valid = tuple(sums[j] is not None and abs(sums[j] - totals[j]) <= _tolerance(len(rows)) for j in range(k))
        off = [sums[j] - totals[j] for j in range(k) if valid[j] and sums[j] != totals[j]]
        layout, signs = "columns", ()
        if k == 1:
            layout = "single"
        elif abs(totals[-1] - sum(totals[:-1])) <= ROUNDING_CENTS and all(
                abs(r.amounts[-1] - sum(r.amounts[:-1])) <= 2 for r in rows if None not in r.amounts):
            layout = "sum"
        elif (sg := _signs(totals, rows)) is not None:
            layout, signs = "net", sg
        note = "; ".join(x for x in (
            numbered, f"rounding in the source: columns off by {off} cents" if off else "",
            "" if all(valid) else f"columns {[j for j, v in enumerate(valid) if not v]} do not sum to the total line") if x)
        return Table(rows, totals, valid, layout, signs, "column_totals" if all(valid) else None, note)
    if k == 1 and sums[0] is not None and sums[0] in stated:
        return Table(rows, sums, (True,), "single", (), "stated_amount", numbered)
    return Table(rows, None, tuple(False for _ in range(k)), "single" if k == 1 else "columns", (), None,
                 "; ".join(x for x in ("no total line", numbered) if x))


def tinos_lines(tables: list[Table]) -> list[TinosLine]:
    """The Tinos row of every table, with the amount its layout implies.

    The amount comes from one column: the only one (``single``), the last
    (``sum``: components then their total) or the first (``net``: gross, then
    withholdings and additions, then what is paid). It counts as validated only
    if that column summed to the document's total (or its stated amount).
    """
    out = []
    for i, t in enumerate(tables):
        col = {"single": 0, "sum": -1, "net": 0, "last": -1}.get(t.layout)
        for r in t.rows:
            if r.code != TINOS_TPD_CODE:
                continue
            amount = net = total = None
            validation = None
            if col is not None and r.amounts[col] is not None:
                amount = r.amounts[col]
                net = r.amounts[-1] if t.layout == "net" else amount
                total = t.totals[col] if t.totals else None
                if t.valid_columns and t.valid_columns[col]:
                    validation = t.validation or "column_totals"
            out.append(TinosLine(i, r, amount, net, t.layout, validation, len(t.rows), total))
    return out


# ---------------------------------------------------------------------------
# Transfer letters: one amount, written in words and in figures
# ---------------------------------------------------------------------------
# «... με το ποσό των τριάντα τεσσάρων χιλιάδων εκατόν πενήντα επτά ευρώ & τεσσάρων λεπτών
# (34.157,04€) ... Διαχειριστής του πιο πάνω ποσού είναι ο Δήμος Τήνου». The words are the
# letter's own check on the figures.
_UNITS = {
    "ΜΗΔΕΝ": 0, "ΕΝΑ": 1, "ΕΝΑΣ": 1, "ΕΝΟΣ": 1, "ΜΙΑ": 1, "ΜΙΑΣ": 1, "ΜΙΑΝ": 1, "ΔΥΟ": 2,
    "ΤΡΙΑ": 3, "ΤΡΕΙΣ": 3, "ΤΡΙΩΝ": 3, "ΤΕΣΣΕΡΑ": 4, "ΤΕΣΣΕΡΙΣ": 4, "ΤΕΣΣΑΡΩΝ": 4, "ΠΕΝΤΕ": 5,
    "ΕΞΙ": 6, "ΕΞ": 6, "ΕΠΤΑ": 7, "ΕΦΤΑ": 7, "ΟΚΤΩ": 8, "ΟΧΤΩ": 8, "ΕΝΝΕΑ": 9, "ΕΝΝΙΑ": 9,
    "ΔΕΚΑ": 10, "ΕΝΤΕΚΑ": 11, "ΔΩΔΕΚΑ": 12, "ΔΕΚΑΤΡΙΑ": 13, "ΔΕΚΑΤΡΙΩΝ": 13, "ΔΕΚΑΤΡΕΙΣ": 13,
    "ΔΕΚΑΤΕΣΣΕΡΑ": 14, "ΔΕΚΑΤΕΣΣΑΡΩΝ": 14, "ΔΕΚΑΤΕΣΣΕΡΙΣ": 14, "ΔΕΚΑΠΕΝΤΕ": 15, "ΔΕΚΑΕΞΙ": 16,
    "ΔΕΚΑΕΞ": 16, "ΔΕΚΑΞΙ": 16, "ΔΕΚΑΕΠΤΑ": 17, "ΔΕΚΑΕΦΤΑ": 17, "ΔΕΚΑΟΚΤΩ": 18, "ΔΕΚΑΟΧΤΩ": 18,
    "ΔΕΚΑΕΝΝΕΑ": 19, "ΔΕΚΑΕΝΝΙΑ": 19, "ΕΙΚΟΣΙ": 20, "ΤΡΙΑΝΤΑ": 30, "ΣΑΡΑΝΤΑ": 40, "ΠΕΝΗΝΤΑ": 50,
    "ΕΞΗΝΤΑ": 60, "ΕΒΔΟΜΗΝΤΑ": 70, "ΟΓΔΟΝΤΑ": 80, "ΕΝΕΝΗΝΤΑ": 90, "ΕΚΑΤΟ": 100, "ΕΚΑΤΟΝ": 100,
}
_HUNDREDS = {"ΔΙΑΚΟΣΙ": 200, "ΤΡΙΑΚΟΣΙ": 300, "ΤΕΤΡΑΚΟΣΙ": 400, "ΠΕΝΤΑΚΟΣΙ": 500, "ΕΞΑΚΟΣΙ": 600,
             "ΕΠΤΑΚΟΣΙ": 700, "ΕΦΤΑΚΟΣΙ": 700, "ΟΚΤΑΚΟΣΙ": 800, "ΟΧΤΑΚΟΣΙ": 800, "ΕΝΝΙΑΚΟΣΙ": 900,
             "ΕΝΝΕΑΚΟΣΙ": 900}
_LETTER_AMOUNT = re.compile(rf"ΠΟΣΟ\w*\s+(?:ΤΩΝ\s+|ΤΟΥ\s+)?(?P<words>[^()]{{3,300}}?)\s*\(\s*(?P<fig>{_AMT})\s*€?\s*\)")


def words_to_cents(words: str) -> int | None:
    """«τριάντα τεσσάρων χιλιάδων εκατόν πενήντα επτά ευρώ & τεσσάρων λεπτών» -> 3415704.

    None when a word is not a number word (the phrase is not an amount in words)."""
    euros = total = current = 0
    cents_part: int | None = None
    in_cents = False
    for w in re.findall(r"[^\W_]+|&", fold(words)):
        if w in ("&", "ΚΑΙ"):
            continue
        if w.isdigit():
            current += int(w)
        elif w in _UNITS:
            current += _UNITS[w]
        elif (h := next((v for k, v in _HUNDREDS.items() if w.startswith(k)), None)) is not None:
            current += h
        elif w.startswith("ΧΙΛΙ"):
            total += (current or 1) * 1000
            current = 0
        elif w.startswith("ΕΚΑΤΟΜΜΥΡΙ"):
            total += (current or 1) * 1_000_000
            current = 0
        elif w == "ΕΥΡΩ":
            euros, total, current, in_cents = total + current, 0, 0, True
        elif w.startswith("ΛΕΠΤ") and in_cents:
            cents_part = total + current
        else:
            return None
    if not in_cents:
        return None
    return euros * 100 + (cents_part or 0)


@dataclass(frozen=True)
class LetterAmount:
    amount: int  # cents, the figures
    words: int | None  # cents, the words (None: not an amount in words)
    tinos: bool  # the letter names Δήμος Τήνου as the account manager or beneficiary


_TINOS_MANAGER = re.compile(r"(ΔΙΑΧΕΙΡΙΣΤ|ΔΙΚΑΙΟΥΧ)[^.]{0,80}ΤΗΝΟΥ|800302968")


def parse_letter(text: str) -> list[LetterAmount]:
    """Amounts a transfer letter states as «ποσό ‹words› (‹figures›)»."""
    flat = " ".join(text.translate(_SYMBOLS).split())
    tinos = bool(_TINOS_MANAGER.search(fold(flat)))
    return [LetterAmount(cents(m.group("fig")), words_to_cents(m.group("words")), tinos)
            for m in _LETTER_AMOUNT.finditer(fold(flat))]


# ---------------------------------------------------------------------------
# One decision: every amount it gives a Tinos body, and how it was checked
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GrantAmount:
    amount: int | None  # cents; None when the document names Tinos but the amount is not established
    net: int | None  # cents paid after withholdings (monthly ΚΑΠ), else = amount
    method: str  # table | letter
    validation: str | None  # column_totals | stated_amount | words_and_figures | None
    detail: str  # layout, rows, columns: enough to find the figure in the PDF again


def read_decision(text: str, subject: str | None) -> tuple[list[GrantAmount], str]:
    """The amounts a decision gives Tinos, and a status.

    Status: ``read`` (at least one amount), ``absent`` (a validated table without
    a Tinos row: Tinos was not a recipient), ``not_found`` (no table or letter
    naming Tinos could be read).
    """
    tables, _ = parse_allocation(text, subject)
    lines = tinos_lines(tables)
    all_letters = parse_letter(text)
    spelled = {x.amount for x in all_letters if x.words == x.amount}
    if lines:
        out = []
        for x in lines:
            validation = x.validation
            # A one-row transfer table: the covering letter spells the same amount in words.
            if validation is None and x.amount is not None and x.n_rows == 1 and x.amount in spelled:
                validation = "words_and_figures"
            out.append(GrantAmount(x.amount, x.net, "table", validation,
                                   f"table {x.table}, row {x.row.number or '-'} of {x.n_rows}, layout {x.layout}, "
                                   f"columns {[a / 100 if a is not None else None for a in x.row.amounts]}"))
        return out, "read"
    letters = [x for x in all_letters if x.tinos]
    if letters:
        return [GrantAmount(x.amount, x.amount, "letter", "words_and_figures" if x.words == x.amount else None,
                            f"figures {x.amount / 100:.2f}, words {x.words / 100 if x.words is not None else None}")
                for x in letters], "read"
    found = _stated_lines(text)
    if found:
        return found, "read"
    if tables and all(t.validation for t in tables):
        return [], "absent"
    return [], "not_found"


_AFM_ROW = re.compile(rf"(?<!\d)(\d{{9}})(?!\d).*?({_AMT})\s*€?\s*(?:\S.*)?$")
_STATED_POSO = re.compile(rf"ΠΟΣΟ\w*\s+(?:ΤΩΝ\s+|ΤΟΥ\s+)?({_AMT})")


def _stated_lines(text: str) -> list[GrantAmount]:
    """Lines naming Tinos whose amount the text states as «ποσό X», or ΑΦΜ-keyed rows (800302968
    for Tinos) that add up to the stated amount (the 2025 ΝΑ255 funding requests)."""
    lines = text.translate(_SYMBOLS).splitlines()
    flat = fold(" ".join(" ".join(lines).split()))
    stated = {cents(m) for m in _STATED_POSO.findall(flat)}
    afm_rows = [(m.group(1), cents(m.group(2))) for m in (_AFM_ROW.search(fold(l)) for l in lines) if m]
    tinos_afm = [a for afm, a in afm_rows if afm == "800302968"]
    if tinos_afm:
        total = sum(a for _, a in afm_rows)
        ok = "stated_amount" if total in stated else None
        return [GrantAmount(a, a, "afm_rows", ok, f"ΑΦΜ rows {len(afm_rows)}, sum {total / 100:.2f}, "
                                                    f"stated {sorted(x / 100 for x in stated)}") for a in tinos_afm]
    out = []
    for l in lines:
        if _TINOS_NAME.search(fold(l)):
            for a in AMOUNT.findall(l):
                if cents(a) in stated:
                    out.append(GrantAmount(cents(a), cents(a), "stated_line", "stated_amount",
                                           f"line naming Tinos, amount {a} stated in the text"))
    return out


_BUDGET_YEAR = re.compile(r"(?:ΕΤΟΥΣ|ΕΤΟΣ|ΚΑΠ)\s+(20[12]\d)")


# ---------------------------------------------------------------------------
# The Region of South Aegean's documents
# ---------------------------------------------------------------------------
TINOS_AFMS = frozenset({"800302968"})  # the only Tinos body the Region's documents name by ΑΦΜ (2015-2025)
# A payment order: «Δίνεται εντολή πληρωμής ευρώ: #15,50# ... (δέκα πέντε Ευρώ και πενήντα Λεπτά) ... στο
# δικαιούχο ΔΗΜΟΣ ΤΗΝΟΥ ... ΑΦΜ: 800302968 ... Για: Υδρευση - άρδευση ... ΕΝΤΕΛΛΟΜΕΝΟ ΠΟΣΟ». Printed twice
# (original and copy); the first print is read.
_ORDER_AMOUNT = re.compile(rf"ΕΝΤΟΛΗ ΠΛΗΡΩΜΗΣ ΕΥΡΩ:\s*#\s*(?P<fig>{_AMT})\s*#.{{0,160}}?\((?P<words>[^()]{{3,200}})\)")
_ORDER_PAYEE = re.compile(r"ΣΤΟ ΔΙΚΑΙΟΥΧΟ\s+(?P<name>.{3,120}?)\s+ΔΙΕΥΘΥΝΣΗ:.{0,240}?ΑΦΜ:\s*(?P<afm>\d{9})")
_ORDER_PURPOSE = re.compile(r"ΓΙΑ:\s*(?P<purpose>.{3,240}?)\s+ΕΝΤΕΛΛΟΜΕΝΟ ΠΟΣΟ")
_UTILITY = re.compile(r"ΥΔΡΕΥΣ|ΑΡΔΕΥΣ|ΑΔΡΕΥΣ|ΑΠΟΧΕΤΕΥΣ|ΥΔΡΟΜΕΤΡ|ΚΑΤΑΝΑΛΩΣΗ ΝΕΡΟΥ")
# A credit: «Εγκρίνουμε (την ανάληψη) πίστωση(ς) ύψους ‹words› (‹figures› €) ... θα μεταβιβαστεί στο Δήμο
# Τήνου, υπόλογο διαχειριστή ..., με Α.Φ.Μ. 800302968» (or to the regional development fund, the ΠΤΑ,
# for a project of Δήμος Τήνου).
# Tried at every anchor (a lookahead, so matches may overlap): «πίστωσης ύψους ‹words›», «την πίστωση των
# ‹words›»; the words hold no digits, so a figure quoted earlier in the preamble cannot start a match.
_CREDIT_AMOUNT = re.compile(rf"(?=(?:ΥΨΟΥΣ|ΠΟΣΟ\w*|ΠΙΣΤΩΣΗ\w*)\s+(?:ΤΩΝ\s+)?(?P<words>[^()#\d]{{3,300}}?)\s*\(\s*"
                            rf"(?P<fig>{_AMT})\s*€?\s*\))")
_TO_TINOS = re.compile(r"ΜΕΤΑΒΙΒΑΣΤΕΙ ΣΤΟ ΔΗΜΟ ΤΗΝΟΥ|ΑΦΜ\W*800302968|800302968")
_TINOS_PROJECT = re.compile(r"ΔΗΜΟΥ ΤΗΝΟΥ|ΔΗΜΟ ΤΗΝΟΥ|ΔΗΜΟΣ ΤΗΝΟΥ")


def read_region(text: str, subject: str | None, family: str) -> tuple[list[GrantAmount], str, str]:
    """The amount a Region of South Aegean document gives a Tinos body: (amounts, status, family).

    ``region_payment``: the payment order's amount, validated when its words equal its figures,
    for a Tinos payee (by ΑΦΜ); its purpose line refines the family: a water bill the Region pays
    the municipality is ``region_utility_payment`` (a sale, not a grant), a payment under a
    programme agreement ``region_agreement_payment``. ``region_credit``: the amount the subject
    states, validated when the text gives it in words and figures and names the municipality as
    recipient or project owner. Other families are listed, not read.
    """
    flat = fold(" ".join(text.translate(_SYMBOLS).split()))
    if family == "region_payment":
        order = _ORDER_AMOUNT.search(flat)
        payee = _ORDER_PAYEE.search(flat)
        if not order or not payee:
            return [], "not_found", family
        if payee.group("afm") not in TINOS_AFMS:
            return [], "absent", family
        purpose = (_ORDER_PURPOSE.search(flat) or {"purpose": ""})["purpose"] if _ORDER_PURPOSE.search(flat) else ""
        refined = ("region_utility_payment" if _UTILITY.search(purpose)
                   else "region_agreement_payment" if "ΠΡΟΓΡΑΜΜΑΤΙΚ" in purpose else family)
        fig, words = cents(order.group("fig")), words_to_cents(order.group("words"))
        return [GrantAmount(fig, fig, "payment_order", "words_and_figures" if words == fig else None,
                            f"payee ΑΦΜ {payee.group('afm')}, figures {fig / 100:.2f}, words "
                            f"{words / 100 if words is not None else None}, for: {purpose[:120]}")], "read", refined
    if family == "region_credit":
        stated = [cents(a) for a in AMOUNT.findall(subject or "")]
        if not stated:
            return [], "not_found", family
        target = stated[0]
        spelled = [m for m in _CREDIT_AMOUNT.finditer(flat) if cents(m.group("fig")) == target]
        to_tinos = bool(_TO_TINOS.search(flat))
        if not (to_tinos or _TINOS_PROJECT.search(flat)):
            return [], "absent", family
        ok = any(words_to_cents(m.group("words")) == target for m in spelled)
        return [GrantAmount(target, target, "credit", "words_and_figures" if ok else None,
                            f"stated {target / 100:.2f} in the subject; words and figures "
                            f"{'agree' if ok else 'not found'}; transferred to "
                            f"{'Δήμος Τήνου (ΑΦΜ 800302968)' if to_tinos else 'the project account, a Δήμος Τήνου project'}")], \
            "read", family
    return [], "listed", family


def budget_year(subject: str | None, issued: int) -> int:
    """The year the allocation is for: «ΚΑΠ έτους 2016» may be issued on 30 December 2015."""
    m = _BUDGET_YEAR.search(fold(subject))
    return int(m.group(1)) if m else issued
