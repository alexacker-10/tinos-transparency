"""Append-only raw store and ingest log.

Invariants (CLAUDE.md):
- ``data/raw/`` is append-only. This module never overwrites or deletes a
  file there. A document whose content changed since it was first captured
  is written as a *new* file next to the original, never on top of it.
- Every stored document is addressed by the SHA-256 of its canonical JSON
  (PDFs: of their bytes as served), so any derived figure can be traced back
  to an exact stored byte string.
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
# ΚΗΜΔΗΣ reference numbers: two-digit year, type code, digits (24REQ014452842,
# 24PROC..., 24AWRD..., 24SYMV..., 24PAY...). ASCII capitals and digits only.
_KHMDHS_REF_RE = re.compile(r"[0-9A-Z]{6,40}")
_KHMDHS_ENDPOINT_RE = re.compile(r"request|notice|auction|contract|payment")
# A full-text search term: one word in capitals (Greek or Latin) or digits.
_TERM_RE = re.compile(r"[0-9Α-ΩA-Z]{2,40}")


def _path_part(value: Any, pattern: re.Pattern[str], what: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"refusing unsafe {what} {value!r} as a path component")
    return value


def safe_ada(value: Any) -> str:
    """``value`` if it has the shape of an ADA, else ValueError (paths and URLs)."""
    return _path_part(value, _ADA_RE, "ADA")


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
        return self.put_keyed_bytes(path, canonical_json(obj))

    def put_keyed_bytes(self, path: Path, data: bytes) -> StoreResult:
        """``put_keyed`` for bytes stored exactly as fetched (PDFs)."""
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

    # -- the one exception to append-only -----------------------------------

    def purge_fulltext(self, path: Path) -> str:
        """Delete one stored full-text file (a decision record or a search page); return its SHA-256.

        The only deletion the store allows, decided by the project owner on 2026-09-26 (PRIVACY.md
        Q7): full-text records found, after they were stored, to be about a person. Anything outside
        ``diavgeia/fulltext`` is refused.
        """
        base = (self.raw_dir / "diavgeia" / "fulltext").resolve()
        target = path.resolve()
        if base not in target.parents or not target.is_file():
            raise ValueError(f"refusing to delete {path}: not a stored full-text file")
        digest = sha256_hex(target.read_bytes())
        target.unlink()
        return digest

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

    def find_diavgeia_act(self, ada: str) -> Path | None:
        """The stored act file for ``ada`` (first capture), or None."""
        base = self.raw_dir / "diavgeia" / "acts"
        hits = sorted(base.glob(f"*/{safe_ada(ada)}.json")) if base.is_dir() else []
        return hits[0] if hits else None

    def diavgeia_doc_path(self, org_uid: str, ada: str) -> Path:
        org = _path_part(org_uid, _ORG_UID_RE, "org uid")
        return self.raw_dir / "diavgeia" / "docs" / org / f"{safe_ada(ada)}.pdf"

    def put_diavgeia_doc(self, org_uid: str, ada: str, data: bytes) -> StoreResult:
        """The act's signed PDF, byte for byte; a re-issued file becomes a sibling."""
        return self.put_keyed_bytes(self.diavgeia_doc_path(org_uid, ada), data)

    # -- khmdhs layout -----------------------------------------------------

    def _khmdhs_base(self, kind: str, endpoint: str, org_uid: str) -> Path:
        ep = _path_part(endpoint, _KHMDHS_ENDPOINT_RE, "ΚΗΜΔΗΣ endpoint")
        return self.raw_dir / "khmdhs" / kind / ep / _path_part(org_uid, _ORG_UID_RE, "org uid")

    def khmdhs_record_path(self, endpoint: str, org_uid: str, ref: str) -> Path:
        name = _path_part(ref, _KHMDHS_REF_RE, "ΚΗΜΔΗΣ referenceNumber")
        return self._khmdhs_base("records", endpoint, org_uid) / f"{name}.json"

    def khmdhs_page_path(self, endpoint: str, org_uid: str, date_from: str, date_to: str,
                         page: int, digest: str) -> Path:
        name = f"{date_from}_{date_to}_p{page:03d}_{digest[:12]}.json"
        return self._khmdhs_base("search", endpoint, org_uid) / name

    def put_khmdhs_page(self, endpoint: str, org_uid: str, date_from: str, date_to: str,
                        page: int, body: dict) -> StoreResult:
        return self.put_content_addressed(
            lambda d: self.khmdhs_page_path(endpoint, org_uid, date_from, date_to, page, d), body)

    def put_khmdhs_record(self, endpoint: str, org_uid: str, record: dict) -> StoreResult:
        """One record, keyed by referenceNumber; an edited record becomes a sibling."""
        return self.put_keyed(self.khmdhs_record_path(endpoint, org_uid, record.get("referenceNumber")), record)

    def iter_khmdhs_records(self) -> list[Path]:
        base = self.raw_dir / "khmdhs" / "records"
        return sorted(base.glob("*/*/*.json")) if base.is_dir() else []

    # -- diavgeia full-text layout -----------------------------------------
    # search/<issuer>/<term>/<from>_<to>_p<NNN>_<sha12>.json: pages as stored,
    #   i.e. redacted (tinos.sources.fulltext.redact_page, PRIVACY.md Q7).
    # decisions/<issuer>/<ADA>.json: whitelisted records, keyed by ADA, under
    #   the record's own issuer (a co-issued act is filed under its issuer).

    def fulltext_page_path(self, org_uid: str, term: str, date_from: str, date_to: str,
                           page: int, digest: str) -> Path:
        base = self.raw_dir / "diavgeia" / "fulltext" / "search"
        name = f"{date_from}_{date_to}_p{page:03d}_{digest[:12]}.json"
        return base / _path_part(org_uid, _ORG_UID_RE, "org uid") / _path_part(term, _TERM_RE, "search term") / name

    def put_fulltext_page(self, org_uid: str, term: str, date_from: str, date_to: str, page: int,
                          body: dict) -> StoreResult:
        return self.put_content_addressed(
            lambda d: self.fulltext_page_path(org_uid, term, date_from, date_to, page, d), body)

    def fulltext_decision_path(self, org_uid: str, ada: str) -> Path:
        org = _path_part(org_uid, _ORG_UID_RE, "org uid")
        return self.raw_dir / "diavgeia" / "fulltext" / "decisions" / org / f"{safe_ada(ada)}.json"

    def put_fulltext_decision(self, record: dict) -> StoreResult:
        """One whitelisted record, keyed by ADA; a re-indexed record becomes a sibling."""
        org = (record.get("organization") or {}).get("uid")
        return self.put_keyed(self.fulltext_decision_path(str(org) if org is not None else None, record.get("ada")), record)

    def iter_fulltext_decisions(self) -> list[Path]:
        """First capture of every whitelisted record (``<ADA>.<sha12>.json`` siblings excluded)."""
        base = self.raw_dir / "diavgeia" / "fulltext" / "decisions"
        return sorted(p for p in base.glob("*/*.json") if "." not in p.stem) if base.is_dir() else []

    def find_fulltext_decision(self, ada: str) -> Path | None:
        base = self.raw_dir / "diavgeia" / "fulltext" / "decisions"
        hits = sorted(base.glob(f"*/{safe_ada(ada)}.json")) if base.is_dir() else []
        return hits[0] if hits else None


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
