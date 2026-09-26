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

import itertools
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
    # A Recovery Fund payment order to its beneficiaries («Εκκαθάριση-εντολή πληρωμής της ΣΑ ΤΑ015 ...»): its payment
    # lines, read like the Digital Governance Ministry's (``tinos.extract.grantors.read_pde``)
    ("rrf_payment", r"ΕΚΚΑΘΑΡΙΣΗ\s*-\s*ΕΝΤΟΛΗ ΠΛΗΡΩΜΗΣ"),
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
    ("election_costs", r"ΕΚΛΟΓΙΚ|ΕΚΛΟΓΕΣ|ΕΚΛΟΓΩΝ|ΔΗΜΟΨΗΦΙΣΜ"),
    # the state paying off its own debts to the municipalities (article 27 of law 3756/2009): 228,743.11 for Tinos in
    # 2015 and 2016, booked in 0619 («Επιχορήγηση άρθρου 27 του Ν.3756/2009», the 2015 statements' 0619.0001)
    ("state_debts", r"ΠΑΣΗΣ ΦΥΣΕΩΣ ΟΦΕΙΛΩΝ|3756/2009"),
    # offsetting orders that settle advances already paid (bookkeeping of money counted when it was advanced)
    ("advance_settlement", r"ΣΥΜΨΗΦΙΣΤΙΚ|ΤΑΚΤΟΠΟΙΗΣΗ ΠΡΟΚΑΤΑΒΟΛ"),
    ("arrears", r"ΛΗΞΙΠΡΟΘΕΣΜ|ΔΙΑΤΑΓΕΣ ΠΛΗΡΩΜΗΣ|ΔΙΚΑΣΤΙΚ"),
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
#
# Most credits go not to the municipality but to the Region's development fund (Περιφερειακό Ταμείο Ανάπτυξης Νοτίου
# Αιγαίου, uid 14763, ΑΦΜ 090355852), the paying agent of the Region's investment programme, which then pays the bill
# (scan and search 2026-09-26): its payment decisions name the payee's ΑΦΜ, and those to the municipality close the
# programme-agreement lines to the cent (2016, 2017, 2022, 2023). What reaches the municipality is counted once, at
# the last step: the fund's payment, or the credit itself when it is transferred to the municipality directly.
REGION_FUND_UID = "14763"
REGION_UIDS = frozenset({"5011", REGION_FUND_UID})
FUND_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = tuple((name, re.compile(p)) for name, p in (
    # «Απόφαση έγκρισης δαπάνης ποσού 7.880,00 € για τη χρηματοδότηση του 1ου λογαριασμού του υποέργου «ΠΣ μεταξύ του Δ.
    # Τήνου και της ΠΝΑ» ...» (2015-2019), «ΕΝΤΟΛΗ ΠΛΗΡΩΜΗΣ 152-24/01/2022» (from 2022)
    ("region_fund_payment", r"^ΕΝΤΟΛΗ ΠΛΗΡΩΜΗΣ|ΕΓΚΡΙΣΗΣ ΔΑΠΑΝΗΣ.*ΧΡΗΜΑΤΟΔΟΤΗΣΗ|^ΧΡΗΜΑΤΟΔΟΤΗΣΗ ΤΟΥ ΔΗΜΟΥ"),
))
# Other grantors searched from 2026-09-26, by issuer; checked before the ministry's families (first match wins).
_P = lambda *pairs: tuple((name, re.compile(p)) for name, p in pairs)  # noqa: E731
FOUNDATION_UID = "99206908"
ISSUER_FAMILIES: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    # The Evangelistria foundation: the statutory grant it owes the municipality (10% of its gross receipts, «τακτική
    # / θεσμοθετημένη / νομοθετημένη επιχορήγηση»), the water bills of its buildings it pays the municipality (a sale,
    # as the Region's), a building lent for a school (in kind).
    FOUNDATION_UID: _P(
        ("foundation_water_bill", r"ΥΔΡΕΥΣ|ΝΕΡΟΥ|ΑΠΟΧΕΤΕΥΣ|ΚΟΙΝΟΧΡΗΣΤ|ΤΕΛ(?:Η|ΩΝ) ΑΚΙΝΗΤΟΥ"),
        # its statutory grants to other bodies (the Tinian Culture Foundation, its elderly-care unit, the Metropolis of
        # Syros, the Panormos school of fine arts, the Church's Apostoliki Diakonia, a pension fund): listed
        ("foundation_to_others", r"^(?!.*ΔΗΜΟ)(?=.*(?:ΙΤΗΠ|Ι\.ΤΗ\.Π|ΙΔΡΥΜΑ\w* ΤΗΝΙΑΚΟΥ|ΜΗΤΡΟΠΟΛ|Μ\.Φ\.Η|ΜΦΗ|"
                                 r"ΜΟΝΑΔΑ ΦΡΟΝΤΙΔΑΣ|ΜΕΓΑΛΟΧΑΡΗ|ΚΑΛΩΝ ΤΕΧΝΩΝ|ΑΠΟΣΤΟΛΙΚΗ|ΤΠΟΕΚΕ))"),
        ("foundation_statutory_grant", r"ΤΑΚΤΙΚ\w* (?:ΕΤΗΣΙΑΣ )?ΕΠΙΧΟΡΗΓ|ΘΕΣΜΟΘΕΤΗΜΕΝ|ΝΟΜΟΘΕΤΗΜΕΝ|ΕΤΗΣΙΑΣ ΕΠΙΧΟΡΗΓ|"
                                       r"10% ΕΠΙ|ΕΠΙΧΟΡΗΓΗΣ\w* ΔΗΜΟΥ ΤΗΝΟΥ ΓΙΑ ΕΤΟΣ"),
        ("foundation_grant", r"ΕΠΙΧΟΡΗΓ|ΚΑΤΑΒΟΛΗΣ? ΠΟΣ|ΕΙΣΦΟΡ"),
        ("in_kind", r"ΧΡΗΣΙΔΑΝΕΙ"),
    ),
    # The Decentralised Administration: election grants (the ministry's family), and its reviews of the municipality's
    # own decisions, among them the municipality accepting other bodies' money: leads, not its money.
    "50203": _P(
        ("supervision", r"ΑΠΟΔΟΧΗ (?:ΤΗΣ )?(?:ΧΡΗΜΑΤΟΔΟΤ|ΕΠΙΧΟΡΗΓ)|ΕΠΙΚΥΡΩΣ|ΕΛΕΓΧΟΣ ΝΟΜΙΜΟΤΗΤΑΣ|ΔΙΑΠΙΣΤΩΤΙΚΗ|ΑΝΑΜΟΡΦΩΣΗ|"
                        r"ΚΑΘΙΕΡΩΣΗ"),
        ("own_spending", r"ΔΕΣΜΕΥΣΗΣ ΠΙΣΤΩΣΗΣ|ΔΕΣΜΕΥΣΗ ΠΙΣΤΩΣΗΣ"),
        # the dissolved Cyclades port fund's balances shared among its successors (2016): the Tinos port fund's share?
        ("port_fund_balance", r"ΛΙΜΕΝΙΚ\w* ΤΑΜΕΙ\w* ΚΥΚΛΑΔΩΝ"),
    ),
}
_EDUCATION = _P(
    ("school_books", r"ΞΕΝΟΓΛΩΣΣ"),  # the school committees' (from 2024 the municipality's) foreign-language books
    ("pde_financing", r"ΧΡΗΜΑΤΟΔΟΤΗΣΗ ΕΡΓΟΥ|" + _W + r"ΣΑΕ \d"),
    ("commitment", r"ΑΝΑΛΗΨΗ"),  # a commitment to pay: listed
    ("programme", r"ΠΡΟΘΕΣΗΣ|ΕΝΤΑΞ"),
)
_CULTURE = _P(("commitment", r"^ΑΑΥ|ΑΝΑΛΗΨΗ|ΔΕΣΜΕΥΣΗ"), ("culture_grant", r"ΕΠΙΧΟΡΗΓ"), ("programme", r"ΕΝΤΑΞ"))
ISSUER_FAMILIES.update({u: _EDUCATION for u in ("100010887", "100015990", "100054501", "100081880")})
ISSUER_FAMILIES.update({u: _CULTURE for u in ("17", "100015966", "100081912")})
# Grantors found from the municipality's own acceptances (2026-09-26; FINDINGS F12).
ISSUER_FAMILIES.update({
    # The Regional Union of Municipalities of the South Aegean: its board grants a request («Αίτημα Δήμου Τήνου για
    # χρηματοδότηση ...»), from 2021 it pays by payment order («Χρηματικό Ένταλμα Πληρωμής Α-142 για: ΧΡΗΜΑΤΟΔΟΤΗΣΗ ΤΟΥ
    # ΔΗΜΟΥ ...»; 2021: «ΠΟΛΙΤΙΣΤΙΚΗ ΧΟΡΗΓΙΑ ΤΗΣ ΠΕΔ ... ΣΤΟ ΔΗΜΟ ΤΗΝΟΥ»); a co-organised event it pays its suppliers for
    "53992": _P(
        ("ped_payment", r"ΕΝΤΑΛΜΑ ΠΛΗΡΩΜΗΣ|^ΠΟΛΙΤΙΣΤΙΚΗ ΧΟΡΗΓΙΑ|^ΧΡΗΜΑΤΟΔΟΤΗΣΗ ΤΟΥ ΔΗΜΟΥ"),
        ("ped_grant", r"ΑΙΤΗΜΑ|ΣΥΝΔΙΟΡΓΑΝΩΣΗ|ΧΟΡΗΓΙΑ"),
    ),
    # The Green Fund: payments by account of a project («Έγκριση δαπάνης για τη χρηματοδότηση του 2ου λογαριασμού»),
    # escrow released to the municipality («οριστικός δικαιούχος ... μέσω παρακαταθήκης»); programmes and calls listed
    "99201054": _P(
        ("green_fund_payment", r"ΕΓΚΡΙΣΗ ΔΑΠΑΝΗΣ|ΟΡΙΣΤΙΚΟΥ ΔΙΚΑΙΟΥΧΟΥ|ΑΠΟΔΕΣΜΕΥΣΗΣ ΠΟΣΟΥ"),
        ("programme", r"ΕΝΤΑΞ|ΠΡΟΣΚΛΗΣ|ΧΡΗΜΑΤΟΔΟΤΙΚΟΥ ΠΡΟΓΡΑΜΜΑΤΟΣ|ΠΡΑΚΤΙΚΟΥ"),
    ),
    # The Shipping Ministry's General Secretariat for the Aegean: a grant («Επιχορήγηση του Δήμου Τήνου για ...»), each
    # payment of it («Έγκριση της 1ης πληρωμής των δαπανών ...»), public-investment payment authority (ΣΑΕ 330, ΣΑΝΑ 233)
    "100015969": _P(
        ("shipping_payment", r"^ΕΓΚΡΙΣΗ\b.{0,40}ΠΛΗΡΩΜ"),
        ("pde_authorisation", r"ΕΞΟΥΣΙΟΔΟΤΗΣ\w* ΠΛΗΡΩΜΗΣ|ΕΝΤΟΛΗ ΚΑΤΑΝΟΜΗΣ ΣΑΕ"),
        ("shipping_grant", r"ΕΠΙΧΟΡΗΓΗΣ"),
        ("programme", r"ΠΡΟΓΡΑΜΜΑΤΙΚ|ΚΛΕΙΣΙΜΟ|ΑΔΕΙΑ|ΣΧΕΔΙΟ ΠΑΡΑΛΑΒΗΣ|ΠΡΑΚΤΙΚΟ|ΜΙΣΘΩΣΗΣ|ΧΑΡΑΚΤΗΡΙΣΜΟΣ"),
    ),
    # The Ministry of National Economy and Finance (the ΠΔΕ and ΕΣΠΑ from 2023) and its predecessors for public
    # investment: financing of a Tinos project («Κατανομή Χρηματοδότησης σε βάρος της ΣΑ Ε367 ... (έργο Τήνου)»)
    **{u: _P(("espa_financing", r"ΕΡΓΩΝ ΕΣΠΑ$"),  # «Χρηματοδότηση και κατανομή έργων ΕΣΠΑ» (2016)
             ("pde_financing", r"ΚΑΤΑΝΟΜΗ ΧΡΗΜΑΤΟΔΟΤΗΣΗΣ|ΧΡΗΜΑΤΟΔΟΤΗΣΗ (?:KAI|ΚΑΙ) (?:KATANOMH|ΚΑΤΑΝΟΜΗ)|^ΚΑΤΑΝΟΜΗ ΣΕ ΒΑΡΟΣ"),
             ("water_bill", r"ΛΟΓΑΡΙΑΣΜ\w* ΥΔΡΕΥΣΗΣ"),  # the customs office's water bill: a sale, not a grant
             ("commitment", r"ΔΕΣΜΕΥΣΗ"),
             ("programme", r"ΕΝΤΑΞ|ΤΡΟΠΟΠΟΙΗΣΗ|ΟΛΟΚΛΗΡΩΣΗ|ΚΑΤΑΝΟΜΗ ΕΡΓΩΝ|ΠΡΑΓΜΑΤΟΓΝΩΜΟΣΥΝ"))
       for u in ("15", "100016002", "100025890", "100054495", "100081597")},
    # The Infrastructure Ministry: public-investment payment authority (Σ.Α. Ε071, Μ070), commitments and inclusions
    **{u: _P(("pde_authorisation", r"ΕΞΟΥΣΙΟΔΟΤΗΣ\w* ΠΛΗΡΩΜΗΣ|ΑΝΑΚΑΤΑΝΟΜΗ ΠΙΣΤΩΣΕΩΝ"),
             ("commitment", r"ΔΕΣΜΕΥΣΗΣ"),
             ("programme", r"ΕΝΤΑΞ|ΠΡΟΓΡΑΜΜΑΤΙΚ|ΠΡΟΣΚΛΗΣ|ΠΡΟΘΕΣΗΣ"))
       for u in ("100025905", "100016011")},
    # The Digital Governance Ministry: payment orders of Recovery Fund projects («Εκκαθάριση-εντολή πληρωμής της ΣΑ
    # ΤΑ063 ...»)
    "100054486": _P(("rrf_payment", r"ΕΚΚΑΘΑΡΙΣΗ|ΕΝΤΟΛΗ ΠΛΗΡΩΜΗΣ")),
    # The tourism organisation: its 2015 payment of a 2009 debt to the municipality, and the commitment behind it
    "99221315": _P(("eot_payment", r"ΕΞΟΦΛΗΣΗ|ΟΦΕΙΛΕΣ ΠΡΟΗΓΟΥΜΕΝΩΝ ΕΤΩΝ"), ("commitment", r"ΟΦΕΙΛΗ|ΔΕΣΜΕΥΣΗ")),
    "100025893": _P(("tourism_grant", r"ΧΡΗΜΑΤΟΔΟΤΗΣ|ΕΠΙΧΟΡΗΓ|ΕΝΤΑΞ")),
})

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
    # a ceiling («έως») for arrears the Deposits and Loans Fund pays to the creditors themselves, on the municipality's
    # payment orders («Εντολές Εξόφλησης»): the municipality registers the grant (1219, 1215) only as it draws on it.
    # Tinos's 2020 ceilings (127,272.07 and 380,450.00) appear in no statement: listed, not counted
    "arrears_ceiling": None,
    "state_debts": "kap_other",
    # the operating-cost column of a two-purpose table charged to the ΚΑΠ account (ΡΟ0946ΜΤΛ6-ΣΚ8, November 2024): 0619
    "kap_supplementary": "kap_other",
    "advance_settlement": None,
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
    "region_agreement_commitment": "programme_agreements",  # 1213 of 2015: the snow clearing, less its withholdings
    # the development fund's payments: under a programme agreement (1213, 1326) or for a project (1322)
    "region_fund_agreement_payment": "programme_agreements",
    "region_fund_payment": "investment_programmes",
    "region_credit_via_fund": None,  # the same money as the fund's payment: listed, counted there
    "region_utility_payment": None,  # the Region's water bill: a sale by the municipality, not a grant
    "region_payment": None,
    "region_allocation": None,
    "region_own_credit": None,
    "region_fine": None,
    "region_agreement": None,
    "region_licence": None,
    # other grantors (2026-09-26): counted where the recipient's revenue line is identified, listed otherwise
    # the foundation's 10%: prior years' revenue, 2119 («Εισφορά (10% επί των ακαθαρίστων) Π.Ι.Ι.Ε.ΤΗΝΟΥ παρελθόντων
    # ετών», sub-account 2119.0002 in the statements of 2014-2015)
    "foundation_statutory_grant": "foundation_contribution",
    "foundation_grant": None,
    "foundation_to_others": None,
    "foundation_water_bill": None,  # a sale by the municipality, not a grant
    "supervision": None,
    "own_spending": None,
    "school_books": "state_grants",  # the municipality's from 2024: 1219 (990.15, December 2024; 728.20, December 2025)
    "commitment": None,
    "culture_grant": None,
    "port_fund_balance": None,
    # the grantors found from the municipality's own acceptances (FINDINGS F12)
    # the Regional Union of Municipalities: 1219 «Λοιπές επιχορηγήσεις» (1211 for 2022-2023's lodging of ambulance staff).
    # A board grant is counted only when no payment order of the Union pays it and no later decision replaces it
    # (``tinos.curated_grants``): the Union published no payment orders to Tinos in 2022-2023
    "ped_payment": "state_grants",
    "ped_grant": "state_grants",
    "ped_own_spending": None,  # an event it co-organises or procures itself: its own spending
    "green_fund_payment": "investment_programmes",  # 1329 «Λοιπές επιχορηγήσεις για επενδύσεις και έργα»
    # the Shipping Ministry's Aegean secretariat: a grant is a ceiling; a payment approved on invoices is counted unless
    # the transfer order that pays it is published, the transfer is counted (1216 for rentals, 1322 for works)
    "shipping_grant": None,
    "shipping_payment": "investment_programmes",
    "pde_authorisation": "investment_programmes",
    "espa_financing": None,  # ΕΣΠΑ allocations (1328): only 2016's are indexed, so the line is not reconciled
    # the Recovery Fund's payment orders to the municipality: 1324 «Χρηματοδοτήσεις από το Ταμείο Ανάκαμψης», from 2026
    # 1350109 «Απολήψεις από το Ταμείο Ανάκαμψης» (August 2026: 26,549.50 to the cent)
    "rrf_payment": "recovery_fund",
    "water_bill": None,
    "eot_payment": "state_grants",  # 1219.0006 of 2015
    "tourism_grant": None,
}

# Where a family's money was booked differently in some years. The statements of 2015-2016 have no line of their own
# for «Βοήθεια στο Σπίτι»: its ΚΑΠ money arrived in 0619 «ΚΑΠ για λοιπούς σκοπούς» (May-August 2016: 42,093.28, the three
# 2016 allocations to the cent; FINDINGS F8). From 2023 it has its own line, 0624.
# Likewise, from the monthly statements: 2015's two desalination instalments arrived in 1219 (F8); the COVID grants of
# 2020-2021, 2020's stray-animal grant and the school cleaners' pay of 2020-2022 in 1211, before 0621 existed (each
# less 0.15%, the 0.15% often refunded months later: 1211 of 2020 and of 2021 close to the cent).
CATEGORY_BY_YEAR: dict[tuple[str, int], str] = {
    ("home_help", 2015): "kap_other", ("home_help", 2016): "kap_other",
    ("desalination", 2015): "state_grants",
    ("covid", 2020): "state_grants", ("covid", 2021): "state_grants", ("stray_animals", 2020): "state_grants",
    ("school_cleaners", 2020): "state_grants", ("school_cleaners", 2021): "state_grants",
    ("school_cleaners", 2022): "state_grants",
}
# A national arrears grant paid to the creditors through the Deposits and Loans Fund, not to the municipality.
_ARREARS_CEILING = re.compile(r"ΕΝΤΟΛ\w* ΕΞΟΦΛΗΣΗΣ|ΚΑΘΑΡΟΥ ΠΟΣΟΥ ΠΡΟΣ ΤΟΥΣ ΤΕΛΙΚΟΥΣ ΔΙΚΑΙΟΥΧΟΥΣ")


def refine_family(family: str, text: str) -> str:
    """A family the document itself refines: an arrears grant paid to the creditors is a ceiling (``arrears_ceiling``)."""
    if family == "arrears" and _ARREARS_CEILING.search(fold(" ".join(text.split()))):
        return "arrears_ceiling"
    return family


def category_of(family: str | None, budget_year: int) -> str | None:
    """The revenue category a family's money is reconciled against in a budget year."""
    return CATEGORY_BY_YEAR.get((family, budget_year)) or CATEGORY_OF_FAMILY.get(family)


# Revenue lines of the year-end statement, by folded name (first match wins); ``kae`` narrows
# the few names shared by a current-year line and a prior-year receivable (group 32).
REVENUE_CATEGORIES: tuple[tuple[str, re.Pattern[str]], ...] = tuple((name, re.compile(p)) for name, p in (
    ("kap_general", r"ΚΑΠ ΓΙΑ (?:ΤΗΝ )?ΚΑΛΥΨΗ ΓΕΝΙΚΩΝ"),  # «ΚΑΠ για την κάλυψη γενικών αναγκών» from 2026
    ("kap_investment", r"ΚΑΠ ΕΠΕΝΔΥΤΙΚΩΝ|ΚΑΠ ΓΙΑ ΕΠΕΝΔΥΤΙΚΕΣ"),
    ("kap_schools", r"ΚΑΠ ΓΙΑ ΤΗΝ ΚΑΛΥΨΗ ΤΩΝ ΛΕΙΤΟΥΡΓΙΚΩΝ"),
    ("school_rents", r"ΚΑΠ ΓΙΑ ΤΗΝ ΚΑΤΑΒΟΛΗ ΜΙΣΘΩΜΑΤΩΝ"),
    ("school_repairs", r"ΕΠΙΣΚΕΥΗ ΚΑΙ ΣΥΝΤΗΡΗΣΗ ΣΧΟΛΙΚΩΝ"),
    ("fire_protection", r"ΠΥΡΟΠΡΟΣΤΑΣΙΑ"),
    ("school_cleaners", r"ΜΙΣΘΟΔΟΣΙΑΣ ΠΡΟΣΩΠΙΚΟΥ ΚΑΘΑΡΙΟΤΗΤΑΣ"),
    ("home_help", r"ΒΟΗΘΕΙΑ ΣΤΟ ΣΠΙΤΙ"),
    ("kap_other", r"ΚΑΠ ΓΙΑ ΛΟΙΠΟΥΣ ΣΚΟΠΟΥΣ"),
    ("welfare", r"ΠΡΟΝΟΙΑΚ"),
    # 1319 «Λοιπά ειδικά προγράμματα» (2015 only): the Region's 2015 credits and its fund's payment, to the cent
    # 1329 «Λοιπές επιχορηγήσεις για επενδύσεις και έργα»: the Green Fund's payments (2018-2023), to the cent
    # 1216 «Από εθνικούς πόρους (μέσω του εθνικού τμήματος του ΠΔΕ)»: public-investment money the municipality books as an
    # operating grant (the Economy Ministry's Ε367 transfers for waste processing, 2024 to the cent; the Aegean
    # secretariat's desalination rentals)
    ("investment_programmes", r"ΘΗΣΕΑΣ|ΦΙΛΟΔΗΜΟΣ|ΕΙΔΙΚΑ ΠΡΟΓΡΑΜΜΑΤΑ|ΚΕΝΤΡΙΚΟΥΣ ΦΟΡΕΙΣ|ΛΟΙΠΕΣ ΕΠΙΧΟΡΗΓΗΣΕΙΣ ΓΙΑ ΕΠΕΝΔΥΣΕΙΣ|"
                              r"ΕΘΝΙΚΟΥ ΤΜΗΜΑΤΟΣ ΤΟΥ ΠΔΕ"),
    # 0715; 0462 is the municipality's own fee. From 2026 one line, «Δημοτικά τέλη διαφήμισης» (1140918), budgeted at
    # exactly the ministry's allocation of the category Δ fee (28,129.88)
    ("advertising_fee", r"^ΤΕΛΟΣ ΔΙΑΦΗΜΙΣΗΣ.*ΚΑΤΗΓΟΡΙΑΣ Δ|^ΔΗΜΟΤΙΚΑ ΤΕΛΗ ΔΙΑΦΗΜΙΣΗΣ"),
    ("property_tax", r"^(?:ΔΗΜΟΤΙΚΟ )?ΤΕΛΟΣ ΑΚΙΝΗΤΗΣ ΠΕΡΙΟΥΣΙΑΣ"),
    ("programme_agreements", r"ΠΡΟΓΡΑΜΜΑΤΙΚΕΣ ΣΥΜΒΑΣΕΙΣ"),  # 1213 operating, 1326 investment
    ("recovery_fund", r"ΤΑΜΕΙΟ ΑΝΑΚΑΜΨΗΣ"),  # 1324; 1350109 from 2026
))
# The state's operating grants to municipalities, by code: their names changed more than their codes.
STATE_GRANT_KAE = ("1211", "1215", "1219")
# The chart of accounts of 2026 names its grant lines for what they finance, not for who pays («Επιχορηγήσεις για
# λοιπούς σκοπούς», «... για κτίρια και συναφείς υποδομές»). Its ΚΑΠ lines keep the old names and match the patterns
# above; the codes whose purpose matches an old line are mapped here (FINDINGS F13).
NEW_CHART_CATEGORIES = {
    "1310114": "state_grants",  # Επιχορηγήσεις για δαπάνες διοίκησης και λειτουργίας (old 1211, 1219)
    "1310189": "state_grants",  # Επιχορηγήσεις για λοιπούς σκοπούς (current)
    "1310489": "programme_agreements",  # Λοιπές μεταβιβάσεις από ΟΤΑ: the Region's programme agreements (old 1213)
    "1340101": "investment_programmes",  # capital grants: για κτίρια και συναφείς υποδομές
    "1340102": "investment_programmes",  # για μηχανήματα και εξοπλισμό
    "1340105": "investment_programmes",  # για μη παραγόμενα περιουσιακά στοιχεία
    "1340189": "investment_programmes",  # για λοιπούς σκοπούς (capital)
}


# The Tinos body a grant goes to, when its subject names one other than the municipality (the school committees
# until 2023, the Panormos cultural centre, the Tsoklis museum, the port fund, the community enterprise).
RECIPIENTS: tuple[tuple[str, re.Pattern[str]], ...] = tuple((uid, re.compile(p)) for uid, p in (
    ("54500", r"ΣΧΟΛΙΚ\w* ΕΠΙΤΡΟΠ"),
    ("55049", r"ΠΝΕΥΜΑΤΙΚ\w* (?:ΕΚΠΟΛΙΤΙΣΤΙΚ\w* )?ΚΕΝΤΡ\w* ΠΑΝΟΡΜΟΥ|ΓΙΑΝΝΟΥΛΗΣ ΧΑΛΕΠΑΣ"),
    ("100032995", r"ΜΟΥΣΕΙ\w* ΚΩΣΤΑ ΤΣΟΚΛΗ"),
    ("50256", r"ΛΙΜΕΝΙΚ\w* ΤΑΜΕΙ\w* ΤΗΝΟΥ"),
    ("53952", r"ΚΟΙΝΩΦΕΛ\w* ΕΠΙΧΕΙΡΗΣ"),
))


def recipient_of(subject: str | None) -> str:
    """The recipient's entity uid: a Tinos body the subject names, else the municipality (6296)."""
    s = fold(subject)
    return next((uid for uid, pattern in RECIPIENTS if pattern.search(s)), "6296")


def family_of(subject: str | None, issuer: str | None = None) -> str:
    s = fold(subject)
    if issuer == REGION_FUND_UID:
        return next((name for name, pattern in FUND_FAMILIES if pattern.search(s)), "other")
    if issuer in REGION_UIDS:
        return next((name for name, pattern in REGION_FAMILIES if pattern.search(s)), "other")
    own = next((name for name, pattern in ISSUER_FAMILIES.get(issuer or "", ()) if pattern.search(s)), None)
    if own:
        return own
    if issuer in ISSUER_FAMILIES and issuer != "50203":
        return "other"  # a foundation's or another ministry's act: the Interior Ministry's families do not apply
    for name, pattern in FAMILIES:
        if pattern.search(s):
            return "kap_general" if name == "kap_general_monthly" else name
    return "other"


# The foundation's statutory grant is booked as prior years' revenue: 2119 («Τακτικά έσοδα από λοιπά έσοδα»), which also
# holds other prior-year revenue (rents, interest): compare, it is not all the foundation's.
FOUNDATION_KAE = "2119"


def revenue_category(kae: str, description: str | None) -> str | None:
    """The reconciliation line of a revenue line, or None for revenue that is not such a transfer."""
    if kae == FOUNDATION_KAE:
        return "foundation_contribution"
    if kae in NEW_CHART_CATEGORIES:
        return NEW_CHART_CATEGORIES[kae]
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
        elif kind == "amounts" and i not in claimed and rows and rows[-1].number is not None \
                and (m := _UNCODED_ROW.match(lines[i])) and int(m.group(1)) == rows[-1].number + 1 \
                and not any(kinds[j][0] == "row" and not amounts_at(lines[j])
                            for j in range(i + 1, min(i + 3, len(lines)))):
            # a numbered row with no ΤΠΔ code (a regional unit among the municipalities: the 2016 «Βοήθεια στο
            # Σπίτι» tables' row 48 «ΠΕΡΙΦΕΡΕΙΑ ΚΕΝΤΡΙΚΗΣ ΜΑΚΕΔΟΝΙΑΣ», 53.477,84): it counts in the columns' sums.
            # Not when a code line without amounts follows: that row's code wrapped below its name and figures
            # («112 ΜΑΝΤΟΥΔΙΟΥ-ΛΙΜΝΗΣ-ΑΓΙΑΣ 73.000,00» over «50409 ΕΥΒΟΙΑΣ») and it claims this line.
            claimed.add(i)
            found = amounts_at(lines[i])
            rows.append(Row(int(m.group(1)), "", " ".join(_TOKEN.sub(" ", m.group(2)).split()),
                            tuple(v for v, _ in found), tuple(e for _, e in found)))
        elif kind == "total" and rows:
            close(obj)
    close(None)
    return tables, stated


# A numbered row with a name and amounts but no ΤΠΔ code: «48   ΚΕΝΤΡΙΚΗΣ   Π.Ε. ΚΙΛΚΙΣ ... 53.477,84».
_UNCODED_ROW = re.compile(r"^\s*(\d{1,4})\s+([^\W\d_].*)$")


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
    validation: str | None  # column_totals | stated_amount | words_and_figures | figures_only | None
    detail: str  # layout, rows, columns: enough to find the figure in the PDF again
    recipient: str | None = None  # the Tinos body's uid when the document names it; else the subject's (recipient_of)
    family: str | None = None  # this amount's own family when it differs from the decision's (a table paying two purposes)


# A national table can pay two purposes from two accounts, one column each: ΡΟ0946ΜΤΛ6-ΣΚ8 (November 2024) pays arrears
# to third parties from the account «Κάλυψη των πάσης φύσεως αναγκών» (90M) and operating costs «σε χρέωση του
# λογαριασμού με τίτλο «Κεντρικοί Αυτοτελείς Πόροι των Δήμων»» (130M). The municipality books the ΚΑΠ column in 0619
# «ΚΑΠ για λοιπούς σκοπούς», the other in 1215: the column whose total the text charges to the ΚΑΠ account is an amount
# of its own, family ``kap_supplementary`` (category ``kap_other``).
_KAP_CHARGE = re.compile(rf"({_AMT})\s*€?\s*(?:ΣΕ ΧΡΕΩΣΗ|ΝΑ ΒΑΡΥΝΕΙ|ΒΑΡΥΝΕΙ)\s+(?:ΤΟΝ\s+|ΤΟΥ\s+)?ΛΟΓΑΡΙΑΣΜΟ\w*\s+"
                         r"(?:ΜΕ\s+(?:ΤΟΝ\s+)?ΤΙΤΛΟ\s+)?«?\s*ΚΕΝΤΡΙΚΟΙ\s+ΑΥΤΟΤΕΛΕΙΣ")


def _kap_split(x: TinosLine, table: Table, kap_totals: set[int]) -> list[GrantAmount] | None:
    """A ``sum`` table of two components whose one column the text charges to the ΚΑΠ: the Tinos row as two amounts."""
    if x.layout != "sum" or len(x.row.amounts) != 3 or not table.totals or len(table.totals) != 3 or None in x.row.amounts:
        return None
    kap = [j for j in (0, 1) if table.totals[j] in kap_totals]
    if len(kap) != 1:
        return None
    j = kap[0]
    out = []
    for col, fam in ((1 - j, None), (j, "kap_supplementary")):
        ok = "column_totals" if table.valid_columns and table.valid_columns[col] else None
        out.append(GrantAmount(x.row.amounts[col], x.row.amounts[col], "table", ok,
                               f"table {x.table}, row {x.row.number or '-'} of {x.n_rows}, layout sum, column {col} of "
                               f"{[a / 100 for a in x.row.amounts]}; column total {table.totals[col] / 100:.2f}"
                               f"{' charged to the ΚΑΠ account' if fam else ''}", family=fam))
    return out


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
        kap_totals = {cents(m.group(1)) for m in _KAP_CHARGE.finditer(fold(" ".join(text.translate(_SYMBOLS).split())))}
        out = []
        for x in lines:
            split = _kap_split(x, tables[x.table], kap_totals)
            if split:
                out.extend(split)
                continue
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
    found = _stated_lines(text) or _section_rows(text)
    if found:
        return found, "read"
    if tables and all(t.validation for t in tables):
        return [], "absent"
    return [], "not_found"


# The ΕΕΤΑΑ's «ΠΙΝΑΚΑΣ ΧΡΗΜΑΤΟΔΟΤΗΣΗΣ ΕΡΓΩΝ» of the Θησέας programme's transfer orders: one section per prefecture,
# rows «6  Δήμος Τήνου  37544  <project>  36.540,00  ΤΗΝΟΥ» (Α/Α, body, project code, title, amount, tax office), the
# title wrapping onto the next lines, each section closed by «ΣΥΝΟΛΑ  Αριθμός φορέων: 4 ... 175.202,15».
_SECTION_ROW = re.compile(rf"^\s*\d{{1,4}}\s+(ΔΗΜΟΣ|ΣΥΝΔΕΣΜΟΣ|ΝΟΜΙΚΟ|ΔΗΜΟΤΙΚ|ΚΟΙΝΟΤΗΤΑ|ΠΕΡΙΦΕΡΕΙΑ)\S*\s.*?\s(\d{{2,6}})\s{{2,}}"
                          rf"\S.*?\s({_AMT})\s{{2,}}\S+(?:\s\S+)?\s*$")
_SECTION_TOTAL = re.compile(rf"^ΣΥΝΟΛΑ\s.*ΑΡΙΘΜΟΣ ΦΟΡΕΩΝ.*?\s({_AMT})\s*$")


def _section_rows(text: str) -> list[GrantAmount]:
    """The Tinos rows of a Θησέας financing table, each section's rows adding up to its «ΣΥΝΟΛΑ»."""
    out, rows = [], []
    for line in text.translate(_SYMBOLS).splitlines():
        up = re.sub(r"\S+", lambda w: fold(w.group()), line)  # folded, columns kept
        if m := _SECTION_ROW.match(up):
            rows.append((cents(m.group(3)), bool(_TINOS_NAME.search(fold(line)))))
        elif (t := _SECTION_TOTAL.match(up.strip())) and rows:
            total = cents(t.group(1))
            ok = sum(a for a, _ in rows) == total
            out.extend(GrantAmount(a, a, "section_rows", "stated_amount" if ok else None,
                                   f"{len(rows)} rows of the section adding up to {sum(a for a, _ in rows) / 100:.2f}; "
                                   f"section total {total / 100:.2f}") for a, tinos in rows if tinos)
            rows = []
    return out


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


# «ΚΑΠ έτους 2016»; not a school year («διδακτικό έτος 2022-2023»: the allocation is booked when it is paid)
_BUDGET_YEAR = re.compile(r"(?:ΕΤΟΥΣ|ΕΤΟΣ|ΚΑΠ)\s+(20[12]\d)(?!\s*[-–/]\s*(?:20)?\d\d)")


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
# What the payee receives after the order's own withholdings (0.06% ΑΕΠΠ, 0.07% ΕΑΑΔΗΣΥ and stamp duty on them:
# 17.52 of the 13,020.00 paid in October 2021). The municipality books this net amount.
_ORDER_NET = re.compile(rf"ΕΝΤΕΛΛΟΜΕΝΟ ΠΟΣΟ ΣΤΟ ΔΙΚΑΙΟΥΧΟ:\s*(?P<net>{_AMT})")
_ORDER_WITHHELD = re.compile(rf"ΣΥΝΟΛΟ ΚΡΑΤΗΣΕΩΝ:\s*(?P<w>{_AMT})")
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
_AGREEMENT_COMMITMENT = re.compile(r"ΕΓΚΡΙΝΟΥΜΕ ΤΗ ΔΕΣΜΕΥΣΗ ΠΙΣΤΩΣΗΣ .{0,200}?ΓΙΑ ΤΗΝ ΠΛΗΡΩΜΗ ΙΣΟΠΟΣΗΣ ΔΑΠΑΝΗΣ .{0,200}?"
                                   r"(?:ΠΣ|ΠΡΟΓΡΑΜΜΑΤΙΚ\w* ΣΥΜΒΑΣ\w*) ΠΝΑ & ΔΗΜΟΣ ΤΗΝΟΥ")
# Where a credit goes: «Η πίστωση αυτή ... θα μεταβιβαστεί στο Δήμο Τήνου, υπόλογο διαχειριστή ... Α.Φ.Μ. 800302968»,
# or «... στο Π.Τ.Α. Νοτίου Αιγαίου, υπόλογο του έργου ... Α.Φ.Μ. 090355852», the Region's development fund, which
# then pays the bill: to the municipality for a project it carries out (its own payment decisions, uid 14763), to a
# contractor for the Region's own (the sewage study of 2017, whose bill the Region's technical service sent).
_TRANSFER = re.compile(r"ΜΕΤΑΒΙΒΑΣΤΕΙ ΣΤΟ[ΝΙ]? (?P<to>.{0,200})")
_FUND = re.compile(r"^(?:Π\.? ?Τ\.? ?Α\.?|ΠΕΡΙΦΕΡΕΙΑΚΟ ΤΑΜΕΙΟ ΑΝΑΠΤΥΞΗΣ)|090355852")
REGION_FUND_AFM = "090355852"


# The development fund's documents. 2015-2019, an approval: «Την έγκριση δαπάνης ποσού επτά χιλιάδων οκτακοσίων
# ογδόντα ευρώ (7.880,00 €). Η δαπάνη αφορά τη χρηματοδότηση του 1ου λογαριασμού του υποέργου «ΠΣ μεταξύ του Δ. Τήνου
# και της ΠΝΑ» ... Το ποσό θα καταβληθεί στο δήμο Τήνου (ΑΦΜ:800302968 ...)». From 2022, a payment order: «ΘΕΜΑ:
# Εκκαθάριση-εντολή πληρωμής της ΣΑ ΕΠ567 ... συνολικού ποσού 58.645,14 ευρώ για το έργο/α: 2015ΕΠ56700002», the
# voucher's «ΣΥΝΟΛΙΚΗ ΑΞΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ 58.645,14» and the payee line «ΔΗΜΟΣ ΤΗΝΟΥ 58.645,14», with «ΤΙΤΛΟΣ ΥΠΟΕΡΓΟΥ:».
_FUND_APPROVAL = re.compile(rf"ΕΓΚΡΙΣΗ ΔΑΠΑΝΗΣ (?:ΤΟΥ )?ΠΟΣΟΥ (?:ΤΩΝ )?(?P<words>[^()#\d]{{3,300}}?)\s*\(\s*"
                            rf"(?P<fig>{_AMT})\s*€?\s*\)")
_FUND_PAYEE = re.compile(r"(?:ΚΑΤΑΒΛΗΘΕΙ|ΑΠΟΔΟΘΕΙ) ΣΤΟ[ΝΙ]? ΔΗΜΟ ΤΗΝΟΥ[^.]{0,40}?800302968|"
                         r"ΔΙΚΑΙΟΥΧΟΥ/ΩΝ: ΔΗΜΟΣ ΤΗΝΟΥ \(ΑΦΜ: 800302968")
_FUND_ORDER_TOTAL = re.compile(rf"ΣΥΝΟΛΙΚΟΥ ΠΟΣΟΥ\s+(?P<fig>{_AMT})\s*ΕΥΡΩ")
_FUND_VOUCHER = re.compile(rf"ΣΥΝΟΛΙΚΗ ΑΞΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ\s+(?P<fig>{_AMT})")
# the sub-project: «ΤΙΤΛΟΣ ΥΠΟΕΡΓΟΥ: ‹title› ΚΩΔΙΚΟΣ ΝΟΜΙΚΗΣ ...» (orders), «... του υποέργου «‹title›» ...» (approvals)
_FUND_SUBPROJECT = re.compile(r"ΤΙΤΛΟΣ ΥΠΟΕΡΓΟΥ:\s*(?P<a>.{3,200}?)\s*ΚΩΔΙΚΟΣ ΝΟΜΙΚΗΣ|ΥΠΟΕΡΓΟ[ΥΝ]? [«\"](?P<b>[^»\"]{3,200})[»\"]")
_AGREEMENT = re.compile(r"ΠΡΟΓΡΑΜΜΑΤΙΚ|" + _W + r"Π\.?Σ\.? (?:ΜΕΤΑΞΥ|ΠΝΑ)")
_ORDINAL_SUFFIX = re.compile(_W + r"ΟΥ" + _E)  # a superscript «ου» (2ου, 4ου) pdftotext moves into the words above


def _subproject(flat: str) -> str:
    m = _FUND_SUBPROJECT.search(flat)
    return " ".join((m.group("a") or m.group("b") or "").replace("'", " ").replace('"', " ").split()) if m else ""


def read_fund(text: str, subject: str | None,
              agreements: frozenset[str] = frozenset()) -> tuple[list[GrantAmount], str, str]:
    """The development fund's payment to a Tinos body: (amounts, status, family).

    Validated in words and figures (an approval) or by the order's total agreeing with its voucher (a payment order);
    the payee must be the municipality by its ΑΦΜ. A payment under a programme agreement is
    ``region_fund_agreement_payment`` (lines 1213, 1326), any other ``region_fund_payment`` (1322): under an agreement
    when its sub-project says so («ΠΣ μεταξύ ΠΝΑ και Δήμου Τήνου ...») or when a stored programme agreement of the
    Region names that sub-project (``agreements``: their folded subjects; the slaughterhouse's orders say only
    «Εκσυγχρονισμός Δημοτικού Σφαγείου Τήνου»).
    """
    flat = fold(" ".join(text.translate(_SYMBOLS).split()))
    if not _FUND_PAYEE.search(flat):
        return [], ("absent" if "800302968" not in flat else "not_found"), "region_fund_payment"
    sub = _subproject(flat)
    named = len(sub.split()) >= 3 and any(sub in " ".join(a.replace("'", " ").replace('"', " ").split())
                                          for a in agreements)
    family = ("region_fund_agreement_payment" if _AGREEMENT.search(sub + " " + fold(subject)) or named
              else "region_fund_payment")
    approval = _FUND_APPROVAL.search(flat)
    if approval:
        fig = cents(approval.group("fig"))
        words = words_to_cents(_ORDINAL_SUFFIX.sub(" ", approval.group("words")))
        return [GrantAmount(fig, fig, "fund_approval", "words_and_figures" if words == fig else None,
                            f"approval: figures {fig / 100:.2f}, words {words / 100 if words is not None else None}, "
                            f"payee Δήμος Τήνου (ΑΦΜ 800302968), sub-project: {sub[:120]}")], "read", family
    total, voucher = _FUND_ORDER_TOTAL.search(flat), _FUND_VOUCHER.search(flat)
    if total:
        fig = cents(total.group("fig"))
        ok = voucher is not None and cents(voucher.group("fig")) == fig
        return [GrantAmount(fig, fig, "fund_payment_order", "stated_amount" if ok else None,
                            f"payment order: total {fig / 100:.2f}, voucher "
                            f"{cents(voucher.group('fig')) / 100 if voucher else None}, payee Δήμος Τήνου (ΑΦΜ 800302968), "
                            f"sub-project: {sub[:120]}")], "read", family
    return [], "not_found", family


# The Evangelistria foundation's decisions approve payments: «αποφασίζει ... εγκρίνει την (αρχική) καταβολή ποσού
# ενενήντα έξι χιλιάδων τετρακοσίων εβδομήντα τεσσάρων €υρώ & ογδόντα πέντε λεπτών (96.474,85 €) ... στον Δήμο Τήνου»,
# sometimes several numbered items for several recipients, often in figures alone («ποσού 100.000,00 έναντι ...»).
# Some PDFs carry a font whose Greek comes out shifted («καηαβολή ... ποζό» for «καταβολή ... ποσό», «Δήμο Σήνος» for
# «Δήμο Τήνου», number words «ηεζζάπων» for «τεσσάρων»); the digits are intact.
_FOUND_MARK = re.compile(r"ΑΠΟΦΑΣΙΖ|ΑΠΝΘΑΖΙΔ")
_FOUND_ITEM = re.compile(r"ΚΑΤΑΒΟΛΗ|ΚΑΗΑΒΟΛΗ|ΘΑΗΑΒΝΙΗ")
_FOUND_POSO = re.compile(r"(?:ΠΟΣΟ|ΠΟΖΟ|ΠΝΖΝ)[^\W\d_]*\s+(?:(?:ΤΩΝ|ΤΟΥ|ΗΩΝ|ΗΝΤ|ΣΩΝ|ΣΟΥ)\s+)?")
_FOUND_AMOUNT = re.compile(r"\(?\s*(\d{1,3}(?:\.\d{3})+(?:,\d{2})?|\d+,\d{2}|\d{3,6})(?![\d%.,/])\s*\)?")
_FOUND_TO_MUNICIPALITY = re.compile(r"ΔΗΜΟ\w? [ΤΣ]ΗΝΟ")
# the shifted font's number words: each Η may stand for Τ, Ζ for Σ, Π for Ρ, Ρ for Σ
_SHIFT = {"Η": "ΗΤ", "Ζ": "ΖΣ", "Π": "ΠΡ", "Ρ": "ΡΣ"}
_NUMBER_WORDS = set(_UNITS) | {"ΧΙΛΙΑΔΕΣ", "ΧΙΛΙΑΔΩΝ", "ΧΙΛΙΑ", "ΧΙΛΙΩΝ", "ΕΥΡΩ", "ΛΕΠΤΑ", "ΛΕΠΤΩΝ", "ΛΕΠΤΟ", "ΚΑΙ",
                                "ΕΚΑΤΟΜΜΥΡΙΟ", "ΕΚΑΤΟΜΜΥΡΙΑ", "ΕΚΑΤΟΜΜΥΡΙΩΝ"}


def _is_number_word(w: str) -> bool:
    return w in _NUMBER_WORDS or any(w.startswith(h) for h in _HUNDREDS)


def _unshift(words: str) -> str:
    """Number words as the shifted font printed them, restored where exactly one reading is a number word."""
    out = []
    for w in re.findall(r"[^\W_]+|&", words):
        if w == "&" or _is_number_word(w):
            out.append(w)
            continue
        slots = [_SHIFT.get(ch, ch) for ch in w]
        readings = {"".join(c) for c in itertools.product(*slots)} if len(w) <= 14 else set()
        hits = [r for r in readings if _is_number_word(r)]
        out.append(hits[0] if len(hits) == 1 else w)
    return " ".join(out)


def _words_cents(words: str) -> int | None:
    return words_to_cents(words + ("" if "ΕΥΡΩ" in words else " ΕΥΡΩ")) if words else None


_FOUND_STATUTORY = re.compile(r"ΤΑΚΤΙΚ|ΘΕΣΜΟΘΕΤ|ΝΟΜΟΘΕΤ|10%|ΕΙΣΦΟΡ|ΗΑΚΗΙΚ|ΘΕΖΜΟΘΕΗ")


def read_foundation(text: str, family: str = "foundation_grant") -> tuple[list[GrantAmount], str, str]:
    """Every item of a foundation decision paying a Tinos body (the municipality or its school committee), a status,
    and the family: ``foundation_statutory_grant`` when every item for the municipality pays the statutory grant.

    The words, when the item spells the amount, check the figures (``words_and_figures``); an item in figures
    alone is ``figures_only``, counted and marked as such."""
    flat = fold(" ".join(text.translate(_SYMBOLS).split())).replace("€ΥΡΩ", "ΕΥΡΩ").replace("€ΥΠΩ", "ΕΥΡΩ")
    mark = _FOUND_MARK.search(flat)
    body = flat[mark.end():] if mark else flat
    starts = [m.start() for m in _FOUND_ITEM.finditer(body)] or [0]
    out, statutory, paid_others = [], [], 0
    for i, st in enumerate(starts):
        item = body[st: starts[i + 1] if i + 1 < len(starts) else len(body)]
        recipient = next((uid for uid, pattern in RECIPIENTS if pattern.search(item)), None)
        if recipient is None and _FOUND_TO_MUNICIPALITY.search(item):
            recipient = "6296"
        poso = _FOUND_POSO.search(item)
        if poso is None:
            continue
        if recipient is None:  # an item paying another body (the Tinian Culture Foundation, its elderly-care unit ...)
            paid_others += 1
            continue
        amt = _FOUND_AMOUNT.search(item, poso.end())
        if amt is None or amt.start() - poso.end() > 400:
            continue
        figures = amt.group(1)
        fig = cents(figures) if "," in figures else int(figures.replace(".", "")) * 100
        words_text = item[poso.end():amt.start()].strip(" (")
        words = _words_cents(words_text)
        if words != fig and words_text:
            words = _words_cents(_unshift(words_text))
        out.append(GrantAmount(fig, fig, "foundation_decision", "words_and_figures" if words == fig else "figures_only",
                               f"item {i + 1} of {len(starts)}: figures {fig / 100:.2f}, words "
                               f"{words / 100 if words is not None else None}", recipient))
        if recipient == "6296":
            statutory.append(bool(_FOUND_STATUTORY.search(item)))
    if statutory and all(statutory):
        family = "foundation_statutory_grant"
    return out, "read" if out else "absent" if paid_others else "not_found", family


# The other grantors (the Decentralised Administration, the Education and Culture ministries) state one amount, in words
# and figures («απόδοση επιχορήγησης ύψους πέντε χιλιάδων τετρακοσίων εξήντα ευρώ (5460,00 €) στο Δήμο ΤΗΝΟΥ», «με το
# ποσό των τριών χιλιάδων ευρώ (3.000,00 €)»), or list rows for a Tinos body's ΑΦΜ whose amounts add up to a stated
# total (school books: «ΣΥΝΟΛΟ 990,15»; a ΣΑΕ 047 transfer: «μεταφορά ποσού € 8.947,91» for four invoices).
_OTHER_MARK = re.compile(r"ΑΠΟΦΑΣΙ[ΖΗ]|ΚΑΤΑΝΕΜΟΥΜΕ|ΣΑΣ ΠΑΡΑΚΑΛΟΥΜΕ")
_OTHER_FIG = r"\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}"
_OTHER_WORDS = re.compile(rf"(?:ΠΟΣΟ\w*|ΥΨΟΥΣ)\s+(?:ΤΩΝ\s+|ΤΟΥ\s+)?(?P<words>[^()\d]{{3,300}}?)\s*\(\s*"
                          rf"(?P<fig>{_OTHER_FIG})\s*€?\s*\)")
_OTHER_STATED = re.compile(rf"(?:ΠΟΣΟΥ|ΠΟΣΟ)\s+€?\s*(?P<fig>{_OTHER_FIG})|(?:ΣΥΝΟΛΟ|ΣΥΝΟΛΙΚΟΥ ΠΟΣΟΥ)[\s(€):]{{0,80}}(?P<tot>{_OTHER_FIG})")
_OTHER_AMT = re.compile(rf"(?<![\d.,])(?:{_OTHER_FIG})(?![\d,])")
_OTHER_TOTAL_LINE = re.compile(r"ΣΥΝΟΛΟ|ΥΠΟΛΟΙΠΟ")
_TINOS_TO = re.compile(r"ΔΗΜΟ\w? ΤΗΝΟΥ")
# a font that prints Σ as ΢ (U+03A2) and shifts letters («΢ΤΝΟΛΟ» for «ΣΥΝΟΛΟ»): enough of it for totals
_SHIFTED_TOTAL = str.maketrans({"\u03a2": "Σ"})


def read_other(text: str, subject: str | None, afm_uid: dict[str, str]) -> tuple[list[GrantAmount], str]:
    """The amount another grantor's decision gives a Tinos body, and a status.

    ``afm_uid``: each Tinos body's ΑΦΜ -> its uid. The recipient is the Tinos body the operative part or the subject
    names (``RECIPIENTS``), else the body whose ΑΦΜ it quotes, else the municipality when it names Δήμο Τήνου."""
    raw = text.translate(_SYMBOLS).translate(_SHIFTED_TOTAL).splitlines()  # columns: fold() collapses spaces
    lines = [fold(l).replace("ΣΤΝΟΛΟ", "ΣΥΝΟΛΟ") for l in raw]
    flat = " ".join(" ".join(lines).split())
    mark = None
    for mark in _OTHER_MARK.finditer(flat):
        pass
    body = flat[mark.end():] if mark else flat
    afms = [a for a in re.findall(r"(?<!\d)(\d{9})(?!\d)", body) if a in afm_uid]
    recipient = (next((uid for uid, pattern in RECIPIENTS if pattern.search(body[:600])), None)
                 or next((uid for uid, pattern in RECIPIENTS if pattern.search(fold(subject))), None)
                 or (afm_uid[afms[0]] if afms else None)
                 or ("6296" if _TINOS_TO.search(body) else None))
    if recipient is None:
        return [], "not_found"
    m = _OTHER_WORDS.search(body)
    if m:
        fig = cents(m.group("fig"))
        words = words_to_cents(m.group("words"))
        return [GrantAmount(fig, fig, "letter", "words_and_figures" if words == fig else None,
                            f"figures {fig / 100:.2f}, words {words / 100 if words is not None else None}", recipient)], "read"
    # rows for a Tinos body, checked against a stated total: the amounts in the total's column, every amount of the
    # table, or the longest run of rows from its start
    start = max((i for i, l in enumerate(lines) if _OTHER_MARK.search(l)), default=0)
    stated_hits = [(i, x) for i, l in enumerate(lines) for x in _OTHER_STATED.finditer(l)]
    stated = {cents(x.group("fig") or x.group("tot")) for _, x in stated_hits}
    stated |= {cents(x.group("fig") or x.group("tot")) for x in _OTHER_STATED.finditer(fold(subject))}
    stated_lines = {i for i, _ in stated_hits}
    cells = [(i, a.end(), cents(a.group())) for i, l in enumerate(raw) if i > start and i not in stated_lines
             and not _OTHER_TOTAL_LINE.search(lines[i]) for a in _OTHER_AMT.finditer(l)]
    ends = {i: max(c[1] for c in cells if c[0] == i) for i in {c[0] for c in cells}}
    total_cols = {raw[i].rfind(x.group("tot")) + len(x.group("tot")) for i, x in stated_hits if x.group("tot") and i > start}
    candidates = [("column", [v for i, e, v in cells if any(abs(e - c) <= 2 for c in total_cols)]),
                  ("table", [v for _, _, v in cells]),
                  ("rows", [v for i, e, v in cells if e == ends[i]])]
    for how, amounts in candidates:
        runs = [amounts] if how != "rows" else [amounts[:n] for n in range(len(amounts), 0, -1)]
        for run in runs:
            if run and sum(run) in stated:
                total = sum(run)
                return [GrantAmount(total, total, "table", "stated_amount",
                                    f"{len(run)} amounts ({how}) adding up to the stated {total / 100:.2f}",
                                    recipient)], "read"
    return [], "not_found"


def read_region(text: str, subject: str | None, family: str,
                agreements: frozenset[str] = frozenset()) -> tuple[list[GrantAmount], str, str]:
    """The amount a Region of South Aegean document gives a Tinos body: (amounts, status, family).

    ``region_payment``: the payment order's amount, validated when its words equal its figures,
    for a Tinos payee (by ΑΦΜ); its purpose line refines the family: a water bill the Region pays
    the municipality is ``region_utility_payment`` (a sale, not a grant), a payment under a
    programme agreement ``region_agreement_payment``. ``region_credit``: the amount the subject
    states, validated when the text gives it in words and figures and names the municipality as
    recipient or project owner. Other families are listed, not read.
    """
    if family == "region_fund_payment":
        return read_fund(text, subject, agreements)
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
        # the net the payee receives: figures less the order's own withholdings, when both are printed and agree
        net_m, withheld_m = _ORDER_NET.search(flat), _ORDER_WITHHELD.search(flat)
        withheld = cents(withheld_m.group("w")) if withheld_m else 0
        net = cents(net_m.group("net")) if net_m else None
        net_ok = net is not None and fig - withheld == net
        return [GrantAmount(fig, net if net_ok else None, "payment_order", "words_and_figures" if words == fig else None,
                            f"payee ΑΦΜ {payee.group('afm')}, figures {fig / 100:.2f}, words "
                            f"{words / 100 if words is not None else None}, withholdings {withheld / 100:.2f}, net "
                            f"{net / 100 if net is not None else None}{'' if net_ok else ' (does not add up)'}, "
                            f"for: {purpose[:120]}")], "read", refined
    if family == "region_credit":
        stated = [cents(a) for a in AMOUNT.findall(subject or "")]
        if not stated:
            return [], "not_found", family
        target = stated[0]
        spelled = [m for m in _CREDIT_AMOUNT.finditer(flat) if cents(m.group("fig")) == target]
        ok = any(words_to_cents(m.group("words")) == target for m in spelled)
        transfer = _TRANSFER.search(flat)
        to = transfer.group("to") if transfer else ""
        if _FUND.search(to):
            # through the development fund: its own payment to the municipality, if any, is what counts
            recipient, refined = f"the Region's development fund (ΑΦΜ {REGION_FUND_AFM}), not the municipality", \
                "region_credit_via_fund"
        elif to.startswith("ΔΗΜΟ ΤΗΝΟΥ") or (not transfer and _TO_TINOS.search(flat)):
            recipient, refined = "Δήμος Τήνου (ΑΦΜ 800302968)", family
        elif transfer or not _TINOS_PROJECT.search(flat):
            return [], "absent", family
        else:
            return [], "not_found", family  # a Tinos project, the recipient not stated
        return [GrantAmount(target, target, "credit", "words_and_figures" if ok else None,
                            f"stated {target / 100:.2f} in the subject; words and figures "
                            f"{'agree' if ok else 'not found'}; transferred to {recipient}")], "read", refined
    if family == "region_agreement" and _AGREEMENT_COMMITMENT.search(flat) and _TINOS_PROJECT.search(flat):
        # The Region's commitment of credit «για την πληρωμή ισόποσης δαπάνης» of a programme agreement with the
        # municipality: before mid-2021 the Region published no payment orders (FINDINGS F9), so this is the last
        # published step of the payment. One case, the 2015 snow clearing (612Π7ΛΞ-1Ο4, 49,867.41): the municipality's
        # 1213 received it in December 2015 less the 0.10% ΕΑΑΔΗΣΥ withholding and 3.6% stamp duty on it (51.67).
        stated = [cents(a) for a in AMOUNT.findall(subject or "")]
        spelled = [(cents(m.group("fig")), words_to_cents(m.group("words"))) for m in _CREDIT_AMOUNT.finditer(flat)]
        amounts = sorted({fig for fig, words in spelled if fig == words})
        if len(amounts) == 1 and (not stated or stated[0] == amounts[0]):
            return [GrantAmount(amounts[0], None, "commitment", "words_and_figures",
                                f"commitment of credit for the payment, {amounts[0] / 100:.2f} in words and figures; "
                                "the payment order is not published")], "read", "region_agreement_commitment"
    return [], "listed", family


def budget_year(subject: str | None, issued: int) -> int:
    """The year the allocation is for: «ΚΑΠ έτους 2016» may be issued on 30 December 2015."""
    m = _BUDGET_YEAR.search(fold(subject))
    return int(m.group(1)) if m else issued
