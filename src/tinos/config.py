"""Project settings and entity registry.

Nothing here talks to the network. Paths are resolved relative to the
repository root so the CLI behaves the same from any working directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

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

    @property
    def user_agent(self) -> str:
        return f"tinos-transparency/0.1 (+{self.contact_url})"

    @property
    def raw_dir(self) -> Path:
        return self.root / "data" / "raw"

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


@dataclass
class Registry:
    version: int
    entities: list[Entity] = field(default_factory=list)

    @property
    def in_scope(self) -> list[Entity]:
        return [e for e in self.entities if e.in_scope]

    @property
    def out_of_scope(self) -> list[Entity]:
        return [e for e in self.entities if not e.in_scope]

    def get(self, uid: str) -> Entity | None:
        return next((e for e in self.entities if e.uid == uid), None)


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
    return reg
