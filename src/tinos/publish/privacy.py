"""Privacy guard for everything this project publishes (PRIVACY.md Q1).

The repository is public, so every tracked file is a publication. Natural
persons, sole traders included, must never be named in one. The curated layer
keeps their raw names because the source publishes them, which leaves any
published file one wrong column away from a leak. This module turns the rule
into a check that fails closed: ``tinos summary`` refuses to write a
SUMMARY.md that fails it, and ``tinos privacy-check`` runs it over every
tracked file.

What counts as a leak:
- ``person_form``: Diavgeia's way of writing an individual, a word, two commas,
  a word (``SURNAME,,NAME``). Needs no database, so it also catches people the
  release no longer holds (payroll batches drop the name at the curated layer).
  The literal placeholder ``SURNAME,,NAME`` used in the docs is exempt.
- ``name``: a natural person's surname and first name as adjacent words, in
  either order, compared after folding case, accents, punctuation and the
  Latin look-alike capitals Diavgeia mixes into Greek names. Not when the two
  words sit inside a legal entity's name: Q1 publishes company names, and a
  partnership is often named after its partner (ΧΧΧ ΚΑΙ ΣΙΑ ΟΕ). At least three
  words of the entity's name must match from its start, so a table that cuts
  long names still counts and a bare two-word name never does.
- ``afm``: a natural person's 9-digit ΑΦΜ standing alone.

Names and ΑΦΜ come from the release database: payees flagged
``is_natural_person``, plus awardees and commitment counterparties that the same
rule (``curated.is_natural_person``) classifies as individuals.

Known gap: inflected forms. A subject naming someone in the genitive
(ΠΑΠΑΔΑΚΗ for ΠΑΠΑΔΑΚΗΣ) is not caught.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import duckdb

from tinos.curated import is_natural_person, normalise_name

# Latin capitals that look like Greek ones; Diavgeia names mix both alphabets.
_LATIN_TO_GREEK = str.maketrans("ABEZHIKMNOPTYX", "ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ")
# Words in a payee name that are not part of the person's name.
_NOT_A_NAME = frozenset({"ΥΠΟΛΟΓΟΣ", "ΕΝΤΑΛΜΑΤΟΣ", "ΠΡΟΠΛΗΡΩΜΗΣ", "ΚΑΙ", "ΛΟΙΠΟΙ", "ΛΟΙΠΕΣ", "ΤΟΥ", "ΤΗΣ"})
_PERSON_FORM_RE = re.compile(r"([^\W\d_]+)\s*,,\s*[^\W\d_]")
_AFM_RE = re.compile(r"(?<![0-9A-Za-z])\d{9}(?![0-9A-Za-z])")


@dataclass(frozen=True)
class Leak:
    path: str
    line: int
    kind: str  # person_form | name | afm
    match: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.kind}: {self.match}"


class PrivacyLeak(Exception):
    """Text meant for publication names or identifies a natural person."""

    def __init__(self, leaks: list[Leak]) -> None:
        super().__init__(f"{len(leaks)} natural-person identifier(s) in text meant for publication")
        self.leaks = leaks


@dataclass(frozen=True)
class Markers:
    """What identifies the natural persons in the release, and the legal-entity
    names that may contain a person's name without being about them."""

    name_keys: frozenset[str]
    afms: frozenset[str]
    entity_names: frozenset[tuple[str, ...]] = frozenset()


def _fold(text: str) -> list[str]:
    return normalise_name(text).translate(_LATIN_TO_GREEK).split()


def name_keys(name: str) -> set[str]:
    """``SURNAME,,NAME,FATHER`` -> {"SURNAME NAME", "NAME SURNAME"}, folded."""
    tokens = [t for t in _fold(name) if len(t) >= 3 and t not in _NOT_A_NAME]
    if len(tokens) < 2:
        return set()
    return {f"{tokens[0]} {tokens[1]}", f"{tokens[1]} {tokens[0]}"}


def load_markers(db_path: Path) -> Markers:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        people: list[tuple[str | None, str]] = []
        entities: set[str] = set()
        for afm, canonical, variants, natural in con.execute(
                "SELECT afm, canonical_name, name_variants, is_natural_person FROM counterparty").fetchall():
            names = {n for n in {canonical, *(variants or [])} if n}
            if natural:
                people += [(afm, n) for n in names]
            else:
                entities |= names
        for afm, afm_type, name in con.execute(
                "SELECT DISTINCT person_afm, person_afm_type, person_name_raw FROM award").fetchall():
            if is_natural_person(name, afm, afm_type):
                people.append((afm, name))
            elif name:
                entities.add(name)
        for afm, name in con.execute(
                "SELECT DISTINCT counterparty_afm, counterparty_name_raw FROM commitment").fetchall():
            if is_natural_person(name, afm, None):
                people.append((afm, name))
            elif name:
                entities.add(name)
    finally:
        con.close()
    keys: set[str] = set()
    for _, name in people:
        keys |= name_keys(name)
    return Markers(frozenset(keys), frozenset(a for a, _ in people if a and _AFM_RE.fullmatch(a)),
                   frozenset(t for t in (tuple(_fold(n)) for n in entities) if len(t) >= 3))


def _inside_entity_names(tokens: list[str], by_first: dict[str, list[tuple[str, ...]]]) -> set[int]:
    """Positions covered by at least three leading words of a legal entity's name."""
    covered: set[int] = set()
    for i, t in enumerate(tokens):
        for name in by_first.get(t, ()):
            k = 0
            while k < len(name) and i + k < len(tokens) and tokens[i + k] == name[k]:
                k += 1
            if k >= 3:
                covered.update(range(i, i + k))
    return covered


def find_leaks(text: str, markers: Markers | None, path: str = "<text>") -> list[Leak]:
    """Every line of ``text`` that names or identifies a natural person.

    With ``markers=None`` only the ``person_form`` check runs.
    """
    leaks: list[Leak] = []
    by_first: dict[str, list[tuple[str, ...]]] = {}
    for name in markers.entity_names if markers else ():
        by_first.setdefault(name[0], []).append(name)
    for no, line in enumerate(text.splitlines(), 1):
        for m in _PERSON_FORM_RE.finditer(line):
            if m.group(1) != "SURNAME":
                leaks.append(Leak(path, no, "person_form", m.group(0)))
        if markers is None:
            continue
        tokens = _fold(line)
        covered = _inside_entity_names(tokens, by_first)
        for j, (a, b) in enumerate(zip(tokens, tokens[1:])):
            if f"{a} {b}" in markers.name_keys and not {j, j + 1} <= covered:
                leaks.append(Leak(path, no, "name", f"{a} {b}"))
        for m in _AFM_RE.finditer(line):
            if m.group(0) in markers.afms:
                leaks.append(Leak(path, no, "afm", m.group(0)))
    return leaks


def tracked_files(root: Path) -> list[Path]:
    """Every file git tracks under ``root``: the repository is public."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True).stdout
    return [root / p for p in out.decode("utf-8").split("\0") if p]


def scan_files(paths: list[Path], markers: Markers | None, root: Path) -> list[Leak]:
    leaks: list[Leak] = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue  # binary or gone; nothing a reader could see as text
        rel = p.relative_to(root).as_posix() if p.is_relative_to(root) else str(p)
        leaks += find_leaks(text, markers, rel)
    return leaks
