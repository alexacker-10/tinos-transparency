"""ΚΗΜΔΗΣ records in the curated layer (PRIVACY.md Q6).

Reads the first capture of every record under ``data/raw/khmdhs/records``
(``<endpoint>/<org>/<referenceNumber>.json``; a later edit of a record is a
``<ref>.<sha12>.json`` sibling and is not read yet) and yields two tables:

procurement        one row per record of every endpoint: request (REQ),
                   notice (PROC), auction = award (AWRD), contract (SYMV),
                   payment (PAY). Dates, title, procedure, amounts, links to
                   the other ΚΗΜΔΗΣ records of the same purchase and to
                   Diavgeia ADAs.
procurement_party  one row per record and party ΑΦΜ: the contractors named on
                   an award or a contract (``role = 'contractor'``), the payees
                   on a payment's invoice lines (``role = 'payee'``, with the
                   payment's gross amount split by line value when a payment
                   has more than one payee, 17 of 5,251 municipal payments).

Never carried (PRIVACY.md Q6): ``authorEmail``, signers and every other
official's name, and the street address and postcode on payment lines.
Natural persons, sole traders included, are found with the same rule as
Diavgeia counterparties (``curated.is_natural_person``) and shown as
«φυσικό πρόσωπο»; their raw name and ΑΦΜ stay here for joins only.

``submissionDate`` is the date ΚΗΜΔΗΣ filters on and the one used for
``year``. Cancelled records are kept, flagged ``cancelled``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from tinos.curated import is_natural_person

ENDPOINTS = ("request", "notice", "auction", "contract", "payment")
MASK = "φυσικό πρόσωπο"


def iter_records(raw_dir: Path) -> Iterable[tuple[str, str, Path, str, dict[str, Any]]]:
    """(endpoint, org, path, sha256, record) for the first capture of every record."""
    base = raw_dir / "khmdhs" / "records"
    for endpoint in ENDPOINTS:
        for path in sorted((base / endpoint).glob("*/*.json")) if (base / endpoint).is_dir() else []:
            if "." in path.stem:  # <ref>.<sha12>.json: a later capture
                continue
            data = path.read_bytes()
            yield endpoint, path.parent.name, path, hashlib.sha256(data).hexdigest(), json.loads(data)


def _value(v: Any) -> str | None:
    """ΚΗΜΔΗΣ code lists arrive as {"key": .., "value": ..}."""
    return v.get("value") if isinstance(v, dict) else None


def _day(v: Any) -> date | None:
    return date.fromisoformat(str(v)[:10]) if v else None


def _objects(rec: dict[str, Any]) -> list[dict[str, Any]]:
    return list(rec.get("objectDetails") or rec.get("objectDetailsList") or [])


def _adas(rec: dict[str, Any]) -> list[str]:
    out = [rec.get(k) for k in ("diavgeiaADA", "decisionRelatedAda", "paymentRelatedAda", "approvalADA")]
    related = rec.get("contractRelatedADA")
    if isinstance(related, dict):
        out += list(related.values())
    return sorted({a.strip() for a in out if isinstance(a, str) and a.strip()})


def _refs(*values: Any) -> list[str]:
    """Links to other ΚΗΜΔΗΣ records arrive as a string or a list of strings."""
    out: set[str] = set()
    for v in values:
        for x in v if isinstance(v, list) else [v]:
            if isinstance(x, str) and x.strip():
                out.add(x.strip())
    return sorted(out)


def _contract_type(rec: dict[str, Any]) -> str | None:
    if rec.get("contractType"):
        return _value(rec["contractType"])
    types = rec.get("contractTypes") or []
    return _value(types[0].get("contractType")) if types and isinstance(types[0], dict) else None


def procurement_rows(raw_dir: Path, stamp: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    parties: list[dict[str, Any]] = []
    for endpoint, org, path, sha, rec in iter_records(raw_dir):
        ref = rec["referenceNumber"]
        sub = _day(rec.get("submissionDate"))
        base = {"ref": ref, "endpoint": endpoint, "entity": org, "submission_date": sub,
                "year": sub.year if sub else None, "cancelled": bool(rec.get("cancelled")),
                "source_path": str(path), "source_sha256": sha, **stamp}
        objs = _objects(rec)
        cpv = sorted({c.get("key") for o in objs for c in (o.get("cpvs") or []) if isinstance(c, dict) and c.get("key")})
        records.append({
            **base, "record_type": ref[2:].rstrip("0123456789"),
            "organization_key": str((rec.get("organization") or {}).get("key")),
            "signed_date": _day(rec.get("contractSignedDate") or rec.get("signedDate")),
            "title": rec.get("title"), "procedure_type": _value(rec.get("procedureType")),
            "contract_type": _contract_type(rec),
            "total_cost_without_vat": rec.get("totalCostWithoutVAT"), "total_cost_with_vat": rec.get("totalCostWithVAT"),
            "contract_refs": _refs(ref) if endpoint == "contract" else _refs(rec.get("contractRefNo")),
            "auction_refs": _refs(rec.get("auctionRefNo"), rec.get("auctionReferenceNumber")),
            "notice_refs": _refs(rec.get("noticeRefNo"), rec.get("noticeReferenceNumber")),
            "request_refs": _refs(rec.get("requestRefNo")), "payment_refs": _refs(rec.get("paymentRefNo")),
            "diavgeia_adas": _adas(rec), "cpv": cpv,
        })
        if endpoint in ("auction", "contract"):
            members = (rec.get("contractingDataDetails") or {}).get("contractingMembersDataList") or []
            for m in members:
                parties.append(_party(base, "contractor", m.get("vatNumber"), m.get("greekVatNumber"), m.get("name"), None))
        elif endpoint == "payment":
            by_afm: dict[str, dict[str, Any]] = {}
            for o in objs:
                afm = str(o.get("vatNo") or "").strip()
                if not afm:
                    continue
                p = by_afm.setdefault(afm, {"greek": o.get("greekVatNo"), "name": o.get("name"), "net": 0.0})
                p["net"] += float(o.get("costWithoutVAT") or 0)
            total_net = sum(p["net"] for p in by_afm.values())
            gross = rec.get("totalCostWithVAT")
            for afm, p in by_afm.items():
                share = p["net"] / total_net if total_net else 1 / len(by_afm)
                amount = None if gross is None else round(gross * share, 2)
                parties.append(_party(base, "payee", afm, p["greek"], p["name"], amount))
    return records, parties


def _party(base: dict[str, Any], role: str, afm: Any, greek: Any, name: Any, amount: float | None) -> dict[str, Any]:
    afm = str(afm).strip() if afm else None
    name = str(name).strip() if name else None
    natural = is_natural_person(name, afm, "EL" if greek else None)
    return {
        "ref": base["ref"], "endpoint": base["endpoint"], "entity": base["entity"],
        "submission_date": base["submission_date"], "year": base["year"], "cancelled": base["cancelled"],
        "role": role, "afm": afm, "is_greek_afm": bool(greek), "name_raw": name,
        "is_natural_person": natural, "display_name": MASK if natural else name,
        "amount_with_vat": amount,
        "source_path": base["source_path"], "source_sha256": base["source_sha256"],
        "derived_at": base["derived_at"], "pipeline_version": base["pipeline_version"],
    }
