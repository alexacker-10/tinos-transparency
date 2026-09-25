"""Append-only raw store and ingest log.

Invariants (CLAUDE.md):
- ``data/raw/`` is append-only. This module never overwrites or deletes a
  file there. A document whose content changed since it was first captured
  is written as a *new* file next to the original, never on top of it.
- Every stored document is addressed by the SHA-256 of its canonical JSON,
  so any derived figure can be traced back to an exact stored byte string.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

Outcome = Literal["new", "unchanged", "changed"]

# An ADA arrives in API responses and becomes a file name. All 76,785 in the
# corpus are Greek capitals and digits around one hyphen (Ω25ΙΩΗ6-ΟΜΘ); anything
# else is refused rather than allowed to steer a path out of data/raw.
_ADA_RE = re.compile(r"[0-9Α-Ω]+-[0-9Α-Ω]+")
_ORG_UID_RE = re.compile(r"\d+")


def _path_part(value: Any, pattern: re.Pattern[str], what: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"refusing unsafe {what} {value!r} as a path component")
    return value


def canonical_json(obj: Any) -> bytes:
    """Deterministic serialisation: sorted keys, no whitespace, UTF-8."""
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class StoreResult:
    outcome: Outcome
    path: Path
    sha256: str


class RawStore:
    """Content-addressed, append-only writer under ``data/raw``."""

    def __init__(self, raw_dir: Path) -> None:
        self.raw_dir = raw_dir

    # -- generic -----------------------------------------------------------

    def _write_new(self, path: Path, data: bytes) -> None:
        """Create ``path``; refuse to touch an existing file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        # 'x' mode: fail loudly rather than overwrite. Append-only by construction.
        with open(path, "xb") as fh:
            fh.write(data)

    def put_keyed(self, path: Path, obj: Any) -> StoreResult:
        """Store ``obj`` at a stable path keyed by identity (e.g. an ADA).

        - No file yet          -> write it, ``new``.
        - Same bytes on disk   -> touch nothing, ``unchanged``.
        - Different bytes      -> keep the old file, write a sibling
          ``<stem>.<sha12>.json`` holding the new version, ``changed``.
        """
        data = canonical_json(obj)
        digest = sha256_hex(data)
        if not path.exists():
            self._write_new(path, data)
            return StoreResult("new", path, digest)
        if sha256_hex(path.read_bytes()) == digest:
            return StoreResult("unchanged", path, digest)
        # Content differs from the first capture. Look for an earlier sibling
        # with the same digest before adding another one.
        sibling = path.with_name(f"{path.stem}.{digest[:12]}{path.suffix}")
        if sibling.exists() and sha256_hex(sibling.read_bytes()) == digest:
            return StoreResult("unchanged", sibling, digest)
        self._write_new(sibling, data)
        return StoreResult("changed", sibling, digest)

    def put_content_addressed(self, path_for: "Callable[[str], Path]", obj: Any) -> StoreResult:
        """Store ``obj`` at a path derived from its own digest.

        ``new`` on first sighting, ``unchanged`` when the identical body is
        already on disk. Nothing is ever rewritten.
        """
        data = canonical_json(obj)
        digest = sha256_hex(data)
        path = path_for(digest)
        if path.exists():
            return StoreResult("unchanged", path, digest)
        self._write_new(path, data)
        return StoreResult("new", path, digest)

    # -- diavgeia layout ---------------------------------------------------

    def diavgeia_act_path(self, org_uid: str, ada: str) -> Path:
        org = _path_part(org_uid, _ORG_UID_RE, "org uid")
        return self.raw_dir / "diavgeia" / "acts" / org / f"{_path_part(ada, _ADA_RE, 'ADA')}.json"

    def diavgeia_page_path(
        self, org_uid: str, from_date: str, to_date: str, page: int, digest: str
    ) -> Path:
        name = f"{from_date}_{to_date}_p{page:03d}_{digest[:12]}.json"
        return self.raw_dir / "diavgeia" / "search" / _path_part(org_uid, _ORG_UID_RE, "org uid") / name

    def put_diavgeia_page(
        self, org_uid: str, from_date: str, to_date: str, page: int, envelope: dict
    ) -> StoreResult:
        """Store a search page with ``info.query`` stripped.

        The echoed query embeds the server's wall clock, so two identical
        result sets never hash the same with it present. The executed echo
        belongs in the ingest log line, not in a duplicate copy of the bytes.
        """
        body = dict(envelope)
        info = dict(body.get("info", {}))
        info.pop("query", None)
        body["info"] = info
        return self.put_content_addressed(
            lambda d: self.diavgeia_page_path(org_uid, from_date, to_date, page, d), body
        )

    def put_diavgeia_act(self, org_uid: str, act: dict) -> StoreResult:
        return self.put_keyed(self.diavgeia_act_path(org_uid, act["ada"]), act)

    def iter_diavgeia_acts(self) -> list[Path]:
        base = self.raw_dir / "diavgeia" / "acts"
        return sorted(base.glob("*/*.json")) if base.is_dir() else []


class IngestLog:
    """One JSON object per line, appended, never rewritten."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"ts": utc_now_iso(), **record}, ensure_ascii=False)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def read(self) -> list[dict]:
        if not self.path.is_file():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out
