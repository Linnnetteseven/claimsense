"""Create synthetic-only JSON/PDF evidence packs in local storage."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import secrets

logger = logging.getLogger(__name__)


def evidence_pack_safety_error(claim: dict) -> str | None:
    """Eligibility uses the persisted synthetic flag and fake reference only."""
    reference = str(claim.get("patient_id") or "")
    if claim.get("is_synthetic") is not True or not re.fullmatch(r"SYN-[0-9]{6}", reference):
        return "Evidence packs are available only for synthetic-reference claims"
    return None


def _pdf_escape(text: str) -> str:
    safe = text.encode("ascii", "replace").decode("ascii")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf_summary(pack: dict) -> bytes:
    """Build a small dependency-free PDF from non-identifying summary fields."""
    versions = pack.get("claim_version_history", [])
    runs = pack.get("validation_runs", [])
    anchors = pack.get("anchors", [])
    signoffs = pack.get("department_signoffs", [])
    ledger = pack.get("ledger_entries", [])
    lines = [
        "HAKIKI - SYNTHETIC DEMO EVIDENCE PACK",
        f"Synthetic reference: {pack.get('synthetic_reference', 'not available')}",
        f"Department: {pack.get('department', 'not available')}",
        f"Generated: {pack.get('generated_at', '')}",
        "",
        f"Claim versions: {len(versions)} | Validation runs: {len(runs)}",
        f"Department sign-off records: {len(signoffs)}",
        f"Ledger events: {len(ledger)} | Anchor records: {len(anchors)}",
        f"Anchor verification: {pack.get('anchor_verification', {}).get('status', 'unknown')}",
        "",
        "Validation history (version / score / status):",
    ]
    lines.extend(f"v{run.get('version')} / {run.get('score')} / {run.get('status')}" for run in runs)
    lines.extend(["", "Ledger commitments are fingerprints; claim contents are not included.",
                  "Demo environment: synthetic data"])
    commands = ["BT", "/F1 10 Tf", "50 780 Td", "14 TL"]
    commands.extend(f"({_pdf_escape(str(line))}) Tj T*" for line in lines[:48])
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n%HakikiSynthetic\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    return bytes(output)


def store_evidence_pack(pack: dict, storage: str | None = None) -> dict:
    """Write a sanitized pack locally; OCI upload stays disabled pending review."""
    allowed = {"synthetic_reference", "department", "generated_at", "claim_version_history",
               "validation_runs", "department_signoffs", "ledger_entries", "anchors", "anchor_verification"}
    if set(pack) - allowed or not re.fullmatch(r"SYN-[0-9]{6}", str(pack.get("synthetic_reference", ""))):
        raise ValueError("Evidence packs accept only minimized synthetic-reference data")
    pack_id = secrets.token_hex(12)
    json_bytes = json.dumps(pack, ensure_ascii=True, indent=2).encode("utf-8")
    pdf_bytes = build_pdf_summary(pack)
    directory = Path(os.getenv("EVIDENCE_DIR", "./evidence_packs")).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{pack_id}.json"
    pdf_path = directory / f"{pack_id}.pdf"
    json_path.write_bytes(json_bytes)
    pdf_path.write_bytes(pdf_bytes)
    result = {"pack_id": pack_id, "storage": "local", "json_path": str(json_path), "pdf_path": str(pdf_path)}
    requested_storage = (storage or os.getenv("EVIDENCE_STORAGE", "local")).strip().lower()
    if requested_storage == "oci":
        logger.warning("OCI evidence storage is disabled; keeping evidence pack local")
        result["message"] = "OCI storage is not enabled; this synthetic pack was saved locally."
    elif requested_storage != "local":
        result["message"] = "Unknown EVIDENCE_STORAGE value; this pack was saved locally."
    return result
