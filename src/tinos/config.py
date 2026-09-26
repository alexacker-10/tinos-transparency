"""Project settings and entity registry.

Nothing here talks to the network. Paths are resolved relative to the
repository root so the CLI behaves the same from any working directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# the full-text whitelist's keep rules an issuer may name (tinos.sources.fulltext.whitelist_reason)
KEEP_RULES = ("grant_words", "investment_acts", "tinos_body", "statutory_grant")

# src/tinos/config.py -> parents[2] is the repository root (editable install).
_DEFAULT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env reader: KEY=VALUE lines, '#' comments, no interpolation."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


@dataclass(frozen=True)
class Settings:
    root: Path
    diavgeia_base: str = "https://diavgeia.gov.gr/opendata"
    diavgeia_doc_base: str = "https://diavgeia.gov.gr/doc"
    contact_url: str = "https://github.com/alexacker-10/tinos-transparency"
    # Seconds to sleep after every request to a public endpoint. Keep it.
    request_delay: float = 0.5
    request_timeout: float = 60.0
    # Diavgeia clamps issueDate ranges to exactly from+180 days (FINDINGS.md).
    # We walk in windows well inside that limit so we never sit on the edge.
    window_days: int = 150
    page_size: int = 500
    # ΚΗΜΔΗΣ: same 180-day clamp (to [dateTo-180d, dateTo]), and it throttles with
    # HTTP 429 without saying how much: slower pace, exponential back-off.
    khmdhs_base: str = "https://cerpp.eprocurement.gov.gr/khmdhs-opendata"
    khmdhs_delay: float = 3.0
    khmdhs_window_days: int = 150
    khmdhs_backoff: float = 60.0
    khmdhs_max_retries: int = 5
    # Diavgeia full-text search ("luminapi"): no echo of the executed query, so
    # every window is checked by counts (FINDINGS.md). No throttling was seen at
    # one call every 1.5 s; keep at least that.
    fulltext_base: str = "https://opendata.diavgeia.gov.gr/luminapi/api/search"
    fulltext_delay: float = 1.5
    fulltext_backoff: float = 30.0
    fulltext_max_retries: int = 3

    @property
    def user_agent(self) -> str:
        return f"tinos-transparency/0.1 (+{self.contact_url})"

    @property
    def raw_dir(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def curated_dir(self) -> Path:
        return self.root / "data" / "curated"

    @property
    def releases_dir(self) -> Path:
        return self.root / "releases"

    @property
    def summary_file(self) -> Path:
        return self.root / "SUMMARY.md"

    @property
    def manifests_dir(self) -> Path:
        return self.root / "manifests"

    @property
    def ingest_log(self) -> Path:
        return self.manifests_dir / "ingest_log.jsonl"

    @property
    def entities_file(self) -> Path:
        return self.root / "entities.yaml"


def load_settings() -> Settings:
    root = Path(os.environ.get("TINOS_ROOT", _DEFAULT_ROOT)).resolve()
    env = _load_dotenv(root / ".env")
    env.update({k: v for k, v in os.environ.items() if k.startswith("TINOS_")})
    kwargs: dict = {"root": root}
    contact = env.get("TINOS_CONTACT_URL", "")
    # The template placeholder is not a reachable contact; fall back to the
    # repository URL rather than advertise "<you>".
    if contact and "<you>" not in contact:
        kwargs["contact_url"] = contact
    if "TINOS_DELAY" in env:
        kwargs["request_delay"] = float(env["TINOS_DELAY"])
    if "TINOS_KHMDHS_DELAY" in env:
        kwargs["khmdhs_delay"] = float(env["TINOS_KHMDHS_DELAY"])
    if "TINOS_FULLTEXT_DELAY" in env:
        kwargs["fulltext_delay"] = float(env["TINOS_FULLTEXT_DELAY"])
    return Settings(**kwargs)


@dataclass(frozen=True)
class Entity:
    uid: str
    name: str
    afm: str | None
    category: str | None
    parent: str | None
    active_years: tuple[int, int] | None
    approx_acts: int | None
    role: str | None = None
    note: str | None = None
    in_scope: bool = True
    reason: str | None = None


@dataclass(frozen=True)
class Grantor:
    """A public body whose decisions give money to Tinos: an issuer we search, never ingest as ours."""
    uid: str
    name: str
    latin_name: str | None
    active_years: tuple[int, int] | None
    note: str | None = None
    # What the full-text whitelist may keep from this issuer besides hits of a Tinos ΑΦΜ (PRIVACY.md Q7):
    # grant_words, investment_acts (Β.1.1), tinos_body, statutory_grant (the foundation's). Default: the first three.
    keep: tuple[str, ...] = ("grant_words", "investment_acts", "tinos_body")
    group: str = "interior"  # the grantor as reported: one ministry under all its uids, the Region with its fund


@dataclass
class Registry:
    version: int
    entities: list[Entity] = field(default_factory=list)
    grantors: list[Grantor] = field(default_factory=list)

    @property
    def in_scope(self) -> list[Entity]:
        return [e for e in self.entities if e.in_scope]

    @property
    def out_of_scope(self) -> list[Entity]:
        return [e for e in self.entities if not e.in_scope]

    def get(self, uid: str) -> Entity | None:
        return next((e for e in self.entities if e.uid == uid), None)

    def keep_rules(self, issuer: str) -> tuple[str, ...]:
        """The whitelist's keep rules for decisions stored under ``issuer`` (a co-issuer that is no grantor of ours
        gets the default)."""
        g = next((g for g in self.grantors if g.uid == issuer), None)
        return g.keep if g else Grantor.keep

    def grantor_group(self, issuer: str) -> str:
        """The grantor a decision stored under ``issuer`` is reported as. A co-issuer that is no grantor of ours
        (a joint decision found by an Interior Ministry search) counts with the ministry."""
        g = next((g for g in self.grantors if g.uid == issuer), None)
        return g.group if g else Grantor.group


def load_registry(path: Path) -> Registry:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    reg = Registry(version=int(doc.get("version", 0)))

    def mk(raw: dict, in_scope: bool) -> Entity:
        years = raw.get("active_years")
        return Entity(
            uid=str(raw["uid"]),
            name=str(raw["name"]),
            afm=str(raw["afm"]) if raw.get("afm") is not None else None,
            category=raw.get("category"),
            parent=str(raw["parent"]) if raw.get("parent") is not None else None,
            active_years=(int(years[0]), int(years[1])) if years else None,
            approx_acts=raw.get("approx_acts"),
            role=raw.get("role"),
            note=raw.get("note"),
            in_scope=in_scope,
            reason=raw.get("reason"),
        )

    reg.entities += [mk(r, True) for r in doc.get("in_scope", [])]
    reg.entities += [mk(r, False) for r in doc.get("out_of_scope", [])]
    for raw in doc.get("grantors", []) or []:
        years = raw.get("active_years")
        keep = tuple(raw["keep"]) if raw.get("keep") else Grantor.keep
        unknown = set(keep) - set(KEEP_RULES)
        if unknown:
            raise ValueError(f"grantor {raw['uid']}: unknown keep rule(s) {sorted(unknown)}")
        reg.grantors.append(Grantor(
            uid=str(raw["uid"]), name=str(raw["name"]), latin_name=raw.get("latin_name"),
            active_years=(int(years[0]), int(years[1])) if years else None, note=raw.get("note"), keep=keep,
            group=str(raw.get("group") or Grantor.group)))
    return reg
