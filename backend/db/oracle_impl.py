"""Oracle Autonomous Database repository using python-oracledb Thin mode."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import secrets

from .connection import get_pool, health_check, is_retryable_read_error
from .analytics import fetch_view_rows, VIEW_QUERIES
from . import response_cache

logger = logging.getLogger(__name__)
GENESIS_HASH = "0" * 16


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _claim_fingerprint(claim: dict) -> str:
    body = {key: value for key, value in claim.items() if not str(key).startswith("_")}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def _timestamp(value: str | None = None) -> tuple[datetime, str]:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if value else datetime.now(timezone.utc)
    parsed = parsed.astimezone(timezone.utc).replace(microsecond=0)
    return parsed, parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_lob(value):
    return value.read() if hasattr(value, "read") else value


def _load_json(value):
    value = _read_lob(value)
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        return json.loads(value)
    raise TypeError(f"Expected JSON text from Oracle; received {type(value).__name__}")


def _clean_claim(claim: dict) -> dict:
    return {key: value for key, value in claim.items() if not str(key).startswith("_")}


def _hash_v3(previous: str, seq: int, claim_ref: str | None, event_type: str, payload_hash: str, timestamp: str) -> str:
    header = {
        "seq": seq,
        "claim_ref": claim_ref,
        "event_type": event_type,
        "payload_hash": payload_hash,
        "timestamp": timestamp,
    }
    return hashlib.sha256((previous + _canonical(header)).encode("utf-8")).hexdigest()


def _hash_v4(previous: str, header: dict) -> str:
    """Hash an explicitly persisted canonical header for Oracle round trips."""
    return hashlib.sha256((previous + _canonical(header)).encode("utf-8")).hexdigest()


def _safe_details(payload: dict) -> dict:
    # These fields make the timeline useful but never contain identifiers,
    # free-text notes, patient data, staff names, or evidence references.
    allowed = {
        "version", "from_version", "score", "status", "error_count", "warning_count",
        "changed_fields", "department", "step_title", "completed_checks", "signed_off",
        "decision", "outcome", "from_seq", "to_seq", "root", "tx_hash", "block_number",
        "head_hash", "review_fingerprint", "version_fingerprint", "previous_version_fingerprint",
        "reason_category",
    }
    return {key: payload[key] for key in allowed if key in payload}


class OracleRepository:
    backend_name = "oracle"

    def health(self) -> bool:
        return health_check()

    def fetch_analytics_view(self, view_name: str) -> list[dict]:
        """Read an aggregate analytics view using a fixed SELECT allowlist."""
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                return fetch_view_rows(cursor, view_name)

    def fetch_analytics_status_signoffs(self) -> dict[str, list[dict]]:
        """Read the two small categorical dashboard datasets in one round trip."""
        query = """
            SELECT 'claims_by_status' AS section_name, status AS item_key,
                   TO_CHAR(claim_count) AS value_one, CAST(NULL AS VARCHAR2(100)) AS value_two
            FROM v_claims_by_status
            UNION ALL
            SELECT 'signoff_progress', department, TO_CHAR(pending), TO_CHAR(signed_off)
            FROM v_signoff_progress
        """
        result = {"claims_by_status": [], "signoff_progress": []}
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
        for section, key, value_one, value_two in rows:
            if section == "claims_by_status":
                result[section].append({"status": key, "claim_count": int(value_one or 0)})
            else:
                result[section].append({"department": key, "pending": int(value_one or 0),
                                        "signed_off": int(value_two or 0)})
        return result

    def fetch_analytics_overview(self) -> dict:
        """Fetch all dashboard datasets in five round trips or fewer."""
        combined_status_signoffs = """
            SELECT 'claims_by_status' AS section_name, status AS item_key,
                   TO_CHAR(claim_count) AS value_one, CAST(NULL AS VARCHAR2(100)) AS value_two
            FROM v_claims_by_status
            UNION ALL
            SELECT 'signoff_progress', department, TO_CHAR(pending), TO_CHAR(signed_off)
            FROM v_signoff_progress
        """
        views = (
            "management_kpis", "score_by_department", "top_failed_rules",
            "rework_trend_weekly",
        )
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(combined_status_signoffs)
                split_rows = cursor.fetchall()
                cursor.execute(VIEW_QUERIES["management_kpis"])
                kpi_columns = [column[0].lower() for column in cursor.description]
                kpi_row = cursor.fetchone()
                kpis = {key: (value.isoformat() if hasattr(value, "isoformat") else value)
                        for key, value in zip(kpi_columns, kpi_row or ())}
                results = {}
                for view_name in views[1:]:
                    cursor.execute(VIEW_QUERIES[view_name])
                    columns = [column[0].lower() for column in cursor.description]
                    results[view_name] = [
                        {key: (value.isoformat() if hasattr(value, "isoformat") else value)
                         for key, value in zip(columns, row)}
                        for row in cursor.fetchall()
                    ]

        by_section = {"claims_by_status": [], "signoff_progress": []}
        for section, key, value_one, value_two in split_rows:
            if section == "claims_by_status":
                by_section[section].append({"status": key, "claim_count": int(value_one or 0)})
            else:
                by_section[section].append({"department": key, "pending": int(value_one or 0),
                                            "signed_off": int(value_two or 0)})
        results.update(by_section)
        results["kpis"] = kpis
        results["ledger_status"] = {
            "entries": kpis.get("ledger_entries", 0), "last_seq": kpis.get("last_seq", 0),
            "last_anchor_at": kpis.get("last_anchor_at"), "last_anchor_tx": kpis.get("last_anchor_tx"),
            "unanchored_entries": kpis.get("unanchored_entries", 0),
        }
        return results

    def list_claim_queue(self, limit: int = 50) -> tuple[int, list[dict]]:
        """Read only queue fields and current-version validation summaries."""
        query = """
            SELECT total_count, id, patient_name, facility_name, department,
                   visit_date, is_synthetic, score, validation_status, error_count,
                   warning_count, validation_payload
            FROM (
                SELECT COUNT(*) OVER() AS total_count,
                       c.id,
                       JSON_VALUE(c.payload, '$.patient_name' RETURNING VARCHAR2(255)) AS patient_name,
                       JSON_VALUE(c.payload, '$.facility_name' RETURNING VARCHAR2(255)) AS facility_name,
                       NVL(c.department, 'unassigned') AS department,
                       JSON_VALUE(c.payload, '$.visit_date' RETURNING VARCHAR2(32)) AS visit_date,
                       CASE WHEN JSON_VALUE(c.payload, '$.is_synthetic') = 'true' THEN 1 ELSE 0 END AS is_synthetic,
                       vr.score,
                       vr.status AS validation_status,
                       NVL(vr.error_count, 0) AS error_count,
                       NVL(vr.warning_count, 0) AS warning_count,
                       CASE WHEN vr.id IS NULL THEN c.payload ELSE NULL END AS validation_payload
                FROM claims c
                LEFT JOIN (
                    SELECT id, claim_id, version, score, status, error_count, warning_count,
                           ROW_NUMBER() OVER (PARTITION BY claim_id ORDER BY created_at DESC, id DESC) AS rn
                    FROM validation_runs
                ) vr ON vr.claim_id = c.id AND vr.rn = 1 AND vr.version = c.current_version
                ORDER BY c.created_at DESC, c.id DESC
            )
            WHERE ROWNUM <= :limit
        """
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"limit": min(50, max(1, int(limit)))}, fetch_lobs=False)
                rows = cursor.fetchall()
        if not rows:
            return 0, []
        total = int(rows[0][0])
        claims = []
        for row in rows:
            (_, claim_id, patient_name, facility_name, department, visit_date,
             synthetic, score, status, errors, warnings, validation_payload) = row
            preview = None
            if score is not None:
                color = "green" if status == "Ready for Submission" else "amber" if status == "Needs Review" else "red"
                preview = {"score": int(score), "status": status, "color": color,
                           "error_count": int(errors), "warning_count": int(warnings)}
            claims.append({
                "id": claim_id, "patient_name": patient_name,
                "facility_name": facility_name, "department": department, "visit_date": visit_date,
                "is_synthetic": bool(synthetic), "_preview": preview,
                "_validation_payload": _load_json(validation_payload) if validation_payload else None,
            })
        return total, claims

    def get_claim_audit(self, claim_id: str, claim: dict | None = None, limit: int = 50) -> dict | None:
        """Fetch one claim's latest 50 events and current version in one SQL call."""
        query = """
            SELECT c.payload, cv.version, cv.version_fingerprint, cv.event_seq,
                   l.seq, l.claim_ref, l.event_type, l.payload_hash, RTRIM(l.prev_hash),
                   RTRIM(l.hash), l.chain_version,
                   TO_CHAR(l.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                   DBMS_LOB.SUBSTR(d.details_json, 4000, 1) AS details_json,
                   DBMS_LOB.GETLENGTH(d.details_json) AS details_length
            FROM claims c
            LEFT JOIN claim_versions cv
              ON cv.claim_id = c.id AND cv.version = c.current_version
            LEFT JOIN (
                SELECT * FROM (
                    SELECT seq, claim_ref, event_type, payload_hash, prev_hash, hash,
                           chain_version, created_at
                    FROM audit_ledger
                    WHERE claim_ref = (SELECT claim_ref FROM claims WHERE id = :claim_id)
                    ORDER BY seq DESC
                ) WHERE ROWNUM <= :limit
            ) l ON 1 = 1
            LEFT JOIN audit_event_details d ON d.event_seq = l.seq
            WHERE c.id = :claim_id
            ORDER BY l.seq DESC
        """
        rows = None
        for attempt in (1, 2):
            connection = None
            try:
                with get_pool().acquire() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(query, {"claim_id": claim_id, "limit": min(50, max(1, int(limit)))}, fetch_lobs=False)
                        rows = cursor.fetchall()
                if attempt == 2:
                    logger.info("Oracle read retry succeeded operation=get_claim_audit claim_id=%s", claim_id)
                break
            except Exception as exc:
                if connection is not None and is_retryable_read_error(exc):
                    try:
                        connection.drop()
                    except Exception:
                        pass
                if attempt == 1 and is_retryable_read_error(exc):
                    logger.info("Oracle connection dropped; retrying safe read operation=get_claim_audit claim_id=%s", claim_id)
                    continue
                raise
        if not rows:
            return None
        stored_claim = _load_json(rows[0][0])
        _, version, fingerprint, event_seq = rows[0][:4]
        history = []
        for row in rows:
            (_, _, _, _, seq, claim_ref, event_type, payload_hash, prev_hash, digest,
             chain_version, timestamp, details_json, details_length) = row
            if seq is None:
                continue
            if details_length and int(details_length) > 4000:
                raise ValueError(f"Audit event {seq} details_json exceeds 4000 characters")
            details = _load_json(details_json) if details_json else {}
            hash_input = details.get("hash_input")
            if int(chain_version) == 4 and isinstance(hash_input, dict):
                timestamp = hash_input.get("timestamp", timestamp)
            history.append({
                **details, "seq": int(seq), "claim_ref": claim_ref, "type": event_type,
                "payload_hash": payload_hash, "prev_hash": prev_hash, "hash": digest,
                "hash_version": int(chain_version), "timestamp": timestamp, "claim_id": claim_id,
            })
        history.reverse()
        current_fingerprint = _claim_fingerprint(claim if claim is not None else stored_claim)
        return {
            "history": history,
            "current_version": ({"status": "not_recorded"} if not fingerprint else {
                "status": "matches" if current_fingerprint == fingerprint else "mismatch",
                "version": int(version), "event_seq": event_seq,
                "version_fingerprint": fingerprint,
            }),
        }

    def get_evidence_pack_data(self, claim_id: str) -> dict | None:
        """Return a synthetic-only, identifier-minimized evidence pack payload."""
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT claim_ref, payload, department FROM claims WHERE id = :claim_id",
                    {"claim_id": claim_id}, fetch_lobs=False,
                )
                claim_row = cursor.fetchone()
                if not claim_row:
                    return None
                claim_ref, claim_payload, department = claim_row
                claim = _load_json(claim_payload)
                synthetic_reference = str(claim.get("patient_id") or "")
                if claim.get("is_synthetic") is not True or not __import__("re").fullmatch(r"SYN-[0-9]{6}", synthetic_reference):
                    raise ValueError("Evidence packs are available only for synthetic-reference claims")

                cursor.execute(
                    """SELECT version, created_at, version_fingerprint, changed_fields_json
                       FROM claim_versions WHERE claim_id = :claim_id ORDER BY version""",
                    {"claim_id": claim_id}, fetch_lobs=False,
                )
                versions = []
                for version, created_at, fingerprint, changed_fields in cursor.fetchall():
                    changes = _load_json(changed_fields) if changed_fields else {}
                    versions.append({"version": int(version), "created_at": created_at.isoformat(),
                                     "fingerprint": fingerprint,
                                     "changed_fields": changes.get("fields", [])})

                cursor.execute(
                    """SELECT version, score, status, error_count, warning_count, counts_json, created_at
                       FROM validation_runs WHERE claim_id = :claim_id ORDER BY created_at, id""",
                    {"claim_id": claim_id}, fetch_lobs=False,
                )
                validations = []
                for version, score, status, errors, warnings, counts, created_at in cursor.fetchall():
                    summary = _load_json(counts) if counts else {}
                    validations.append({"version": int(version or 1), "score": int(score), "status": status,
                                        "error_count": int(errors), "warning_count": int(warnings),
                                        "failed_rules": [item.get("rule_id") for item in summary.get("failed_rules", [])],
                                        "created_at": created_at.isoformat()})

                cursor.execute(
                    """SELECT department, status, signed_at FROM department_signoffs
                       WHERE claim_id = :claim_id ORDER BY department""",
                    {"claim_id": claim_id},
                )
                signoffs = [{"department": row[0], "status": row[1],
                             "signed_at": row[2].isoformat() if row[2] else None}
                            for row in cursor.fetchall()]

                cursor.execute(
                    """SELECT seq, event_type, payload_hash, RTRIM(prev_hash), RTRIM(hash), created_at
                       FROM audit_ledger WHERE claim_ref = :claim_ref ORDER BY seq""",
                    {"claim_ref": claim_ref},
                )
                ledger_entries = [{"seq": int(row[0]), "event_type": row[1], "payload_hash": row[2],
                                   "previous_hash": row[3], "hash": row[4],
                                   "created_at": row[5].isoformat()}
                                  for row in cursor.fetchall()]
                claim_seqs = [entry["seq"] for entry in ledger_entries]
                cursor.execute(
                    "SELECT from_seq, to_seq, root_hash, tx_hash, created_at FROM anchors ORDER BY id"
                )
                anchors = [{"from_seq": int(row[0]), "to_seq": int(row[1]), "root_hash": row[2],
                            "tx_hash": row[3], "created_at": row[4].isoformat()}
                           for row in cursor.fetchall()
                           if any(int(row[0]) <= seq <= int(row[1]) for seq in claim_seqs)]

        if anchors:
            from audit.anchor import verify_anchors
            verification = verify_anchors()
            verified_ranges = {(int(row.get("from_seq", 0)), int(row.get("to_seq", 0))): row.get("status")
                               for row in verification.get("anchors", [])}
            for item in anchors:
                item["verification"] = verified_ranges.get((item["from_seq"], item["to_seq"]), verification.get("status", "unavailable"))
        else:
            verification = {"status": "not_anchored", "anchors": []}
        return {
            "synthetic_reference": synthetic_reference,
            "department": department or "Unassigned",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "claim_version_history": versions,
            "validation_runs": validations,
            "department_signoffs": signoffs,
            "ledger_entries": ledger_entries,
            "anchors": anchors,
            "anchor_verification": {"status": verification.get("status", "unavailable")},
        }

    def _append_cursor(self, connection, cursor, payload: dict) -> dict:
        cursor.execute(
            "SELECT last_seq, RTRIM(last_hash) FROM audit_ledger_head WHERE singleton_id = 1 FOR UPDATE"
        )
        current = cursor.fetchone()
        if not current:
            raise RuntimeError("Oracle audit_ledger_head is not initialized; apply backend/db/schema.sql")
        seq = int(current[0]) + 1
        previous = current[1]
        claim_id = str(payload.get("claim_id") or "")
        claim_ref = None
        if claim_id:
            cursor.execute("SELECT claim_ref FROM claims WHERE id = :claim_id", {"claim_id": claim_id})
            row = cursor.fetchone()
            claim_ref = row[0] if row else None
        event_type = str(payload.get("type") or "event")[:64]
        created_at, timestamp = _timestamp(payload.get("timestamp"))
        payload_hash = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        hash_input = {
            "seq": seq, "claim_ref": claim_ref, "event_type": event_type,
            "payload_hash": payload_hash, "timestamp": timestamp,
        }
        digest = _hash_v4(previous, hash_input)
        anchor_tx = str(payload.get("tx_hash") or "") if event_type == "anchor" else None
        cursor.execute(
            """INSERT INTO audit_ledger
               (seq, claim_ref, event_type, payload_hash, prev_hash, hash, created_at, anchored_tx, chain_version)
               VALUES (:seq, :claim_ref, :event_type, :payload_hash, :prev_hash, :hash,
                       :created_at, :anchored_tx, 4)""",
            {
                "seq": seq, "claim_ref": claim_ref, "event_type": event_type,
                "payload_hash": payload_hash, "prev_hash": previous, "hash": digest,
                "created_at": created_at, "anchored_tx": anchor_tx,
            },
        )
        cursor.execute(
            "UPDATE audit_ledger_head SET last_seq = :seq, last_hash = :hash WHERE singleton_id = 1",
            {"seq": seq, "hash": digest},
        )
        safe_details = _safe_details(payload)
        # Persist the exact hash preimage next to the event. Reconstructing it
        # from Oracle columns can vary with driver/NLS timestamp formatting.
        safe_details["hash_input"] = hash_input
        if event_type == "anchor":
            cursor.execute(
                """INSERT INTO anchors (from_seq, to_seq, root_hash, tx_hash, created_at)
                   VALUES (:from_seq, :to_seq, :root_hash, :tx_hash, :created_at)""",
                {
                    "from_seq": int(payload["from_seq"]), "to_seq": int(payload["to_seq"]),
                    "root_hash": str(payload.get("root", "")), "tx_hash": str(payload["tx_hash"]),
                    "created_at": created_at,
                },
            )
        cursor.execute(
            "INSERT INTO audit_event_details (event_seq, details_json) VALUES (:seq, :details_json)",
            {"seq": seq, "details_json": _canonical(safe_details)},
        )
        return {
            **safe_details, "type": event_type, "seq": seq, "hash_version": 4,
            "claim_ref": claim_ref, "payload_hash": payload_hash,
            "timestamp": timestamp, "hash_input": hash_input,
            "prev_hash": previous, "hash": digest,
        }

    def append_ledger_event(self, payload: dict) -> dict:
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                event = self._append_cursor(connection, cursor, payload)
                connection.commit()
                response_cache.clear()
                return event

    def append_ledger_events(self, payloads: list[dict], existing=None) -> list[dict]:
        if not payloads:
            return []
        with get_pool().acquire() as connection:
            result = []
            with connection.cursor() as cursor:
                for payload in payloads:
                    result.append(self._append_cursor(connection, cursor, payload))
                connection.commit()
                response_cache.clear()
            return result

    def all_ledger_records(self) -> list[dict]:
        import time
        started = time.perf_counter()
        sql_calls = 0
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.arraysize = 500
                sql_calls += 1
                cursor.execute(
                    """SELECT l.seq, l.claim_ref, l.event_type, l.payload_hash, RTRIM(l.prev_hash),
                              RTRIM(l.hash), l.chain_version,
                              TO_CHAR(l.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"'),
                              DBMS_LOB.SUBSTR(d.details_json, 4000, 1) AS details_json,
                              DBMS_LOB.GETLENGTH(d.details_json) AS details_length
                       FROM audit_ledger l LEFT JOIN audit_event_details d ON d.event_seq = l.seq
                       ORDER BY l.seq""",
                    fetch_lobs=False,
                )
                rows = cursor.fetchall()
        records = []
        for seq, claim_ref, event_type, payload_hash, prev_hash, digest, chain_version, timestamp, details, details_length in rows:
            if details_length and int(details_length) > 4000:
                raise ValueError(f"Audit event {seq} details_json exceeds 4000 characters")
            record = _load_json(details) if details else {}
            hash_input = record.get("hash_input")
            record.update({
                "seq": int(seq), "claim_ref": claim_ref, "type": event_type,
                "payload_hash": payload_hash, "prev_hash": prev_hash,
                "hash": digest, "hash_version": int(chain_version), "timestamp": timestamp,
            })
            if int(chain_version) == 4 and isinstance(hash_input, dict):
                record["timestamp"] = hash_input.get("timestamp")
            if event_type == "anchor":
                # Anchor metadata is safe on-chain and needed by the Fuji UI.
                record["anchored_tx"] = record.get("tx_hash")
            records.append(record)
        logger.info("Oracle all_ledger_records rows=%d sql_queries=%d duration_ms=%.1f arraysize=500 fetch_lobs=false",
                    len(records), sql_calls, (time.perf_counter() - started) * 1000)
        return records

    def get_ledger_for_claim(self, claim_id: str) -> list[dict]:
        """Return only this claim's latest 50 events in one indexed query."""
        query = """
            SELECT seq, claim_ref, event_type, payload_hash, RTRIM(prev_hash), RTRIM(hash),
                   chain_version,
                   TO_CHAR(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                   DBMS_LOB.SUBSTR(details_json, 4000, 1) AS details_json,
                   DBMS_LOB.GETLENGTH(details_json) AS details_length
            FROM (
                SELECT l.seq, l.claim_ref, l.event_type, l.payload_hash, l.prev_hash, l.hash,
                       l.chain_version, l.created_at,
                       DBMS_LOB.SUBSTR(d.details_json, 4000, 1) AS details_json,
                       DBMS_LOB.GETLENGTH(d.details_json) AS details_length
                FROM claims c
                JOIN audit_ledger l ON l.claim_ref = c.claim_ref
                LEFT JOIN audit_event_details d ON d.event_seq = l.seq
                WHERE c.id = :claim_id
                ORDER BY l.seq DESC
            )
            WHERE ROWNUM <= 50
            ORDER BY seq
        """
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"claim_id": claim_id}, fetch_lobs=False)
                rows = cursor.fetchall()
        records = []
        for row in rows:
            seq, claim_ref, event_type, payload_hash, prev_hash, digest, version, timestamp, details_json, details_length = row
            if details_length and int(details_length) > 4000:
                raise ValueError(f"Audit event {seq} details_json exceeds 4000 characters")
            details = _load_json(details_json) if details_json else {}
            header = details.get("hash_input")
            if int(version) == 4 and isinstance(header, dict):
                timestamp = header.get("timestamp", timestamp)
            records.append({**details, "seq": int(seq), "claim_ref": claim_ref, "type": event_type,
                            "payload_hash": payload_hash, "prev_hash": prev_hash, "hash": digest,
                            "hash_version": int(version), "timestamp": timestamp, "claim_id": claim_id})
        return records

    def _select_claim(self, cursor, claim_id: str, for_update: bool = False):
        suffix = " FOR UPDATE" if for_update else ""
        cursor.execute(
            "SELECT claim_ref, payload, current_version, status FROM claims WHERE id = :claim_id" + suffix,
            {"claim_id": claim_id},
            fetch_lobs=False,
        )
        row = cursor.fetchone()
        if not row:
            return None
        return row[0], _load_json(row[1]), int(row[2]), row[3]

    def _ensure_claim_cursor(self, connection, cursor, claim: dict, created_by="system") -> tuple[dict, bool]:
        created_at_value = claim.get("_created_at")
        claim = _clean_claim(claim)
        claim_id = str(claim.get("id") or "")
        if not claim_id:
            raise ValueError("Claim id is required")
        existing = self._select_claim(cursor, claim_id, for_update=True)
        if existing:
            return existing[1], False
        claim_ref = secrets.token_hex(16)
        payload_text = _canonical(claim)
        fingerprint = _claim_fingerprint(claim)
        created_at, _ = _timestamp(created_at_value)
        cursor.execute(
            """INSERT INTO claims (id, claim_ref, facility, department, payload, status, current_version, created_at)
               VALUES (:id, :claim_ref, :facility, :department, :payload, :status, 1, :created_at)""",
            {
                "id": claim_id, "claim_ref": claim_ref,
                "facility": claim.get("facility_name"), "department": claim.get("department"),
                "payload": payload_text, "status": claim.get("status"), "created_at": created_at,
            },
        )
        event_payload = {
            "type": "claim_received", "claim_id": claim_id, "version": 1,
            "version_fingerprint": fingerprint,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        event = self._append_cursor(connection, cursor, event_payload)
        cursor.execute(
            """INSERT INTO claim_versions
               (claim_id, version, payload, created_by, version_fingerprint, event_seq)
               VALUES (:claim_id, 1, :payload, :created_by, :fingerprint, :event_seq)""",
            {"claim_id": claim_id, "payload": payload_text, "created_by": created_by,
             "fingerprint": fingerprint, "event_seq": event["seq"]},
        )
        return claim, True

    def record_claim_received(self, claim: dict) -> dict | None:
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cleaned = _clean_claim(claim)
                _, created = self._ensure_claim_cursor(connection, cursor, cleaned)
                if not created:
                    connection.rollback()
                    rows = self.get_ledger_for_claim(str(cleaned.get("id") or ""))
                    return next((item for item in rows if item.get("type") == "claim_received"), None)
                connection.commit()
                response_cache.clear()
                rows = self.get_ledger_for_claim(str(cleaned.get("id") or ""))
                return next((item for item in rows if item.get("type") == "claim_received"), None)

    def record_claims_received(self, claims: list[dict]) -> list[dict]:
        self.sync_claims(claims)
        return []

    def sync_claims(self, claims: list[dict]) -> list[dict]:
        """Insert missing intake claims with three batch round trips, independent of N."""
        incoming = [(_clean_claim(claim), claim.get("_created_at"))
                    for claim in claims if str(claim.get("id") or "")]
        if not incoming:
            return []
        id_binds = {f"id_{index}": claim["id"] for index, (claim, _) in enumerate(incoming)}
        placeholders = ", ".join(f":id_{index}" for index in range(len(incoming)))
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                # Lock the singleton head first so concurrent sync requests cannot
                # both decide the same intake IDs are missing and race to insert.
                cursor.execute(
                    "SELECT last_seq, RTRIM(last_hash) FROM audit_ledger_head WHERE singleton_id = 1 FOR UPDATE"
                )
                head = cursor.fetchone()
                if not head:
                    raise RuntimeError("Oracle audit_ledger_head is not initialized; apply backend/db/schema.sql")
                cursor.execute(f"SELECT id FROM claims WHERE id IN ({placeholders})", id_binds)
                existing_ids = {str(row[0]) for row in cursor.fetchall()}
                missing = [(claim, created_at_value) for claim, created_at_value in incoming
                           if str(claim["id"]) not in existing_ids]
                if not missing:
                    connection.rollback()
                    return [claim for claim, _ in incoming]
                seq = int(head[0])
                previous = head[1]
                batch = {"claims": [], "versions": [], "ledger": [], "details": []}
                now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                for claim, created_at_value in missing:
                    claim_id = str(claim["id"])
                    claim_ref = secrets.token_hex(16)
                    payload_text = _canonical(claim)
                    fingerprint = _claim_fingerprint(claim)
                    created_at, timestamp = _timestamp(created_at_value)
                    seq += 1
                    event_payload = {
                        "type": "claim_received", "claim_id": claim_id, "version": 1,
                        "version_fingerprint": fingerprint, "timestamp": timestamp or now,
                    }
                    payload_hash = hashlib.sha256(_canonical(event_payload).encode("utf-8")).hexdigest()
                    header = {"seq": seq, "claim_ref": claim_ref, "event_type": "claim_received",
                              "payload_hash": payload_hash, "timestamp": timestamp or now}
                    digest = _hash_v4(previous, header)
                    details = _safe_details(event_payload)
                    details["hash_input"] = header
                    batch["claims"].append({
                        "id": claim_id, "claim_ref": claim_ref,
                        "facility": claim.get("facility_name"), "department": claim.get("department"),
                        "payload": payload_text, "status": claim.get("status"),
                        "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    })
                    batch["versions"].append({
                        "claim_id": claim_id, "version": 1, "payload": payload_text,
                        "created_by": "system", "fingerprint": fingerprint, "event_seq": seq,
                    })
                    batch["ledger"].append({
                        "seq": seq, "claim_ref": claim_ref, "event_type": "claim_received",
                        "payload_hash": payload_hash, "prev_hash": previous, "hash": digest,
                        "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    })
                    batch["details"].append({"seq": seq, "details_json": _canonical(details)})
                    previous = digest

                # One bound JSON document lets Oracle perform all array inserts and
                # the head update in one network round trip after the two reads.
                cursor.execute(
                    """BEGIN
                         INSERT INTO claims (id, claim_ref, facility, department, payload, status, current_version, created_at)
                         SELECT id, claim_ref, facility, department, payload, status, 1,
                                TO_TIMESTAMP_TZ(created_at, 'YYYY-MM-DD"T"HH24:MI:SSTZH:TZM')
                         FROM JSON_TABLE(:batch_json, '$.claims[*]' COLUMNS (
                           id VARCHAR2(128) PATH '$.id', claim_ref VARCHAR2(32) PATH '$.claim_ref',
                           facility VARCHAR2(255) PATH '$.facility', department VARCHAR2(64) PATH '$.department',
                           payload CLOB PATH '$.payload', status VARCHAR2(64) PATH '$.status',
                           created_at VARCHAR2(40) PATH '$.created_at'));
                         INSERT INTO claim_versions (claim_id, version, payload, created_by, version_fingerprint, event_seq)
                         SELECT claim_id, version, payload, created_by, fingerprint, event_seq
                         FROM JSON_TABLE(:batch_json, '$.versions[*]' COLUMNS (
                           claim_id VARCHAR2(128) PATH '$.claim_id', version NUMBER PATH '$.version',
                           payload CLOB PATH '$.payload', created_by VARCHAR2(120) PATH '$.created_by',
                           fingerprint CHAR(64) PATH '$.fingerprint', event_seq NUMBER PATH '$.event_seq'));
                         INSERT INTO audit_ledger (seq, claim_ref, event_type, payload_hash, prev_hash, hash, created_at, chain_version)
                         SELECT seq, claim_ref, event_type, payload_hash, prev_hash, hash,
                                TO_TIMESTAMP_TZ(created_at, 'YYYY-MM-DD"T"HH24:MI:SSTZH:TZM'), 4
                         FROM JSON_TABLE(:batch_json, '$.ledger[*]' COLUMNS (
                           seq NUMBER PATH '$.seq', claim_ref VARCHAR2(32) PATH '$.claim_ref',
                           event_type VARCHAR2(64) PATH '$.event_type', payload_hash CHAR(64) PATH '$.payload_hash',
                           prev_hash CHAR(64) PATH '$.prev_hash', hash CHAR(64) PATH '$.hash',
                           created_at VARCHAR2(40) PATH '$.created_at'));
                         INSERT INTO audit_event_details (event_seq, details_json)
                         SELECT seq, details_json FROM JSON_TABLE(:batch_json, '$.details[*]' COLUMNS (
                           seq NUMBER PATH '$.seq', details_json CLOB PATH '$.details_json'));
                         UPDATE audit_ledger_head SET last_seq = :last_seq, last_hash = :last_hash
                         WHERE singleton_id = 1;
                       END;""",
                    {"batch_json": json.dumps(batch, separators=(",", ":"), ensure_ascii=False),
                     "last_seq": seq, "last_hash": previous},
                )
                connection.commit()
        response_cache.clear()
        return [claim for claim, _ in incoming]

    def get_claim(self, claim_id: str) -> dict | None:
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                selected = self._select_claim(cursor, claim_id)
                return selected[1] if selected else None

    def list_claims(self) -> list[dict]:
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT payload FROM claims ORDER BY created_at DESC", fetch_lobs=False)
                return [_load_json(row[0]) for row in cursor.fetchall()]

    def create_claim(self, claim: dict) -> dict:
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cleaned, _ = self._ensure_claim_cursor(connection, cursor, claim, created_by="claims_officer")
                connection.commit()
                response_cache.clear()
                return cleaned

    def record_claim_correction(self, claim_id: str, previous: dict, updated: dict) -> dict | None:
        corrected_at, corrected_timestamp = _timestamp(updated.get("_corrected_at"))
        updated = {**_clean_claim(updated), "id": claim_id}
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                selected = self._select_claim(cursor, claim_id, for_update=True)
                if not selected:
                    self._ensure_claim_cursor(connection, cursor, previous)
                    selected = self._select_claim(cursor, claim_id, for_update=True)
                _claim_ref, current, current_version, _status = selected
                fingerprint = _claim_fingerprint(updated)
                cursor.execute(
                    "SELECT version_fingerprint FROM claim_versions WHERE claim_id = :claim_id ORDER BY version DESC FETCH FIRST 1 ROW ONLY",
                    {"claim_id": claim_id},
                )
                latest = cursor.fetchone()
                if latest and latest[0] == fingerprint:
                    connection.rollback()
                    return None
                changed = sorted(key for key in set(current) | set(updated) if key != "id" and current.get(key) != updated.get(key))
                version = current_version + 1
                event = self._append_cursor(connection, cursor, {
                    "type": "claim_corrected", "claim_id": claim_id,
                    "from_version": current_version, "version": version,
                    "previous_version_fingerprint": _claim_fingerprint(current),
                    "version_fingerprint": fingerprint, "changed_fields": changed,
                    "timestamp": corrected_timestamp,
                })
                cursor.execute(
                    """UPDATE claims SET payload = :payload, department = :department,
                       facility = :facility, current_version = :version, updated_at = SYSTIMESTAMP
                       WHERE id = :claim_id""",
                    {"payload": _canonical(updated), "department": updated.get("department"),
                     "facility": updated.get("facility_name"), "version": version, "claim_id": claim_id},
                )
                cursor.execute(
                    """INSERT INTO claim_versions
                       (claim_id, version, payload, created_by, version_fingerprint, event_seq, changed_fields_json, created_at)
                       VALUES (:claim_id, :version, :payload, :created_by, :fingerprint, :event_seq, :changed, :created_at)""",
                    {"claim_id": claim_id, "version": version, "payload": _canonical(updated),
                     "created_by": "claims_officer", "fingerprint": fingerprint,
                     "event_seq": event["seq"], "changed": _canonical({"fields": changed}),
                     "created_at": corrected_at},
                )
                connection.commit()
                response_cache.clear()
                return event

    def record_validation(self, claim_id: str, claim: dict, result: dict) -> dict | None:
        created_at, timestamp = _timestamp(result.get("recorded_at"))
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                selected = self._select_claim(cursor, claim_id, for_update=True)
                if not selected:
                    self._ensure_claim_cursor(connection, cursor, claim)
                    selected = self._select_claim(cursor, claim_id, for_update=True)
                version = selected[2]
                fingerprint = _claim_fingerprint(claim)
                event = self._append_cursor(connection, cursor, {
                    "type": "validation", "claim_id": claim_id, "version": version,
                    "version_fingerprint": fingerprint, "score": result["score"],
                    "status": result["status"], "error_count": result["error_count"],
                    "warning_count": result["warning_count"],
                    "timestamp": timestamp,
                })
                cursor.execute(
                    """INSERT INTO validation_runs
                       (claim_id, version, score, status, error_count, warning_count, counts_json, ledger_seq, created_at)
                       VALUES (:claim_id, :version, :score, :status, :errors, :warnings, :counts, :ledger_seq, :created_at)""",
                    {"claim_id": claim_id, "version": version, "score": result["score"],
                     "status": result["status"], "errors": result["error_count"],
                     "warnings": result["warning_count"],
                     "counts": _canonical({
                         "errors": result["error_count"], "warnings": result["warning_count"],
                         "failed_rules": [
                             {"rule_id": rule.get("rule_id"), "rule_name": rule.get("rule_id")}
                             for rule in result.get("results", []) if not rule.get("passed")
                         ],
                     }),
                     "ledger_seq": event["seq"], "created_at": created_at},
                )
                connection.commit()
                response_cache.clear()
                return event

    def record_event(self, payload: dict) -> dict:
        return self.append_ledger_event(payload)

    def verify_current_claim_version(self, claim_id: str, claim: dict) -> dict:
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT version, version_fingerprint, event_seq FROM claim_versions
                       WHERE claim_id = :claim_id ORDER BY version DESC FETCH FIRST 1 ROW ONLY""",
                    {"claim_id": claim_id},
                )
                row = cursor.fetchone()
        if not row:
            return {"status": "not_recorded"}
        fingerprint = _claim_fingerprint(claim)
        return {"status": "matches" if fingerprint == row[1] else "mismatch",
                "version": int(row[0]), "event_seq": row[2], "version_fingerprint": row[1]}

    def get_department_review(self, claim_id: str, department: str) -> dict | None:
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT review_json FROM department_signoffs WHERE claim_id = :claim_id AND department = :department",
                    {"claim_id": claim_id, "department": department.lower()},
                    fetch_lobs=False,
                )
                row = cursor.fetchone()
                return _load_json(row[0]) if row else None

    def save_department_review(self, claim_id: str, department: str, review: dict) -> dict:
        department = department.lower()
        signed_at, _ = _timestamp(review.get("signedOffAt")) if review.get("signedOffAt") else (None, None)
        signed = bool(review.get("signedOffAt"))
        state = "signed_off" if signed else "in_progress"
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE department_signoffs SET status = :status, note = :note,
                       signed_by = :signed_by, signed_at = :signed_at, review_json = :review_json,
                       updated_at = SYSTIMESTAMP WHERE claim_id = :claim_id AND department = :department""",
                    {"status": state, "note": str(review.get("note") or "")[:2000] or None,
                     "signed_by": str(review.get("signedOffBy") or review.get("reviewer") or "")[:120] or None,
                     "signed_at": signed_at, "review_json": _canonical(review),
                     "claim_id": claim_id, "department": department},
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        """INSERT INTO department_signoffs
                           (claim_id, department, status, note, signed_by, signed_at, review_json)
                           VALUES (:claim_id, :department, :status, :note, :signed_by, :signed_at, :review_json)""",
                        {"claim_id": claim_id, "department": department, "status": state,
                         "note": str(review.get("note") or "")[:2000] or None,
                         "signed_by": str(review.get("signedOffBy") or review.get("reviewer") or "")[:120] or None,
                         "signed_at": signed_at, "review_json": _canonical(review)},
                    )
                connection.commit()
                response_cache.clear()
        return review

    def list_outcomes(self, claim_id: str | None = None) -> list[dict]:
        query = "SELECT id, claim_id, department, outcome, reason, note, recorded_at FROM claim_outcomes"
        params = {}
        if claim_id:
            query += " WHERE claim_id = :claim_id"
            params["claim_id"] = claim_id
        query += " ORDER BY recorded_at DESC"
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return [{"id": row[0], "claimId": row[1], "department": row[2],
                         "outcome": row[3], "reasonCategory": row[4], "note": row[5],
                         "recordedAt": row[6].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
                        for row in cursor.fetchall()]

    def save_outcome(self, outcome: dict) -> dict:
        recorded_at, _ = _timestamp(outcome["recordedAt"])
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                event = self._append_cursor(connection, cursor, {
                    "type": "claim_outcome_recorded", "claim_id": outcome["claimId"],
                    "department": outcome.get("department"), "outcome": outcome["outcome"],
                    "reason_category": outcome.get("reasonCategory"),
                    "timestamp": outcome["recordedAt"],
                })
                cursor.execute(
                    """INSERT INTO claim_outcomes
                       (id, claim_id, department, outcome, reason, note, recorded_at)
                       VALUES (:id, :claim_id, :department, :outcome, :reason, :note, :recorded_at)""",
                    {"id": outcome["id"], "claim_id": outcome["claimId"],
                     "department": outcome.get("department"), "outcome": outcome["outcome"],
                     "reason": outcome.get("reasonCategory"), "note": outcome.get("note"),
                     "recorded_at": recorded_at},
                )
                connection.commit()
                response_cache.clear()
        return {**outcome, "ledgerSeq": event["seq"]}

    def import_legacy_records(self, records: list[dict], verify_records) -> dict:
        """Verify legacy Redis records, re-chain privacy-safe commitments, verify the Oracle copy."""
        source_check = verify_records(records)
        if not source_check.get("verified"):
            raise ValueError("Source Redis ledger failed verification; migration stopped")
        if self.all_ledger_records():
            raise ValueError("Oracle audit ledger is not empty; refusing to merge ledgers")
        from data.mock_claims import MOCK_CLAIMS
        allowed_claims = {str(claim["id"]): _clean_claim(claim) for claim in MOCK_CLAIMS}
        source_ids = {str(record.get("claim_id")) for record in records if record.get("claim_id")}
        references: dict[str, str] = {claim_id: secrets.token_hex(16) for claim_id in source_ids}
        copied_count = 0
        with get_pool().acquire() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM claims")
                if int(cursor.fetchone()[0]) > 0:
                    raise ValueError("Oracle claims table is not empty; refusing migration")
                for claim_id in sorted(source_ids & set(allowed_claims)):
                    claim = allowed_claims[claim_id]
                    claim_ref = references[claim_id]
                    fingerprint = _claim_fingerprint(claim)
                    cursor.execute(
                        """INSERT INTO claims (id, claim_ref, facility, department, payload, status, current_version)
                           VALUES (:id, :claim_ref, :facility, :department, :payload, :status, 1)""",
                        {"id": claim_id, "claim_ref": claim_ref, "facility": claim.get("facility_name"),
                         "department": claim.get("department"), "payload": _canonical(claim), "status": None},
                    )
                    cursor.execute(
                        """INSERT INTO claim_versions
                           (claim_id, version, payload, created_by, version_fingerprint)
                           VALUES (:claim_id, 1, :payload, 'redis_migration', :fingerprint)""",
                        {"claim_id": claim_id, "payload": _canonical(claim), "fingerprint": fingerprint},
                    )
                previous = GENESIS_HASH
                for source in records:
                    old_payload = {key: value for key, value in source.items() if key not in {"seq", "prev_hash", "hash", "hash_version"}}
                    old_type = str(old_payload.get("type") or "event")
                    event_type = "legacy_anchor" if old_type == "anchor" else old_type
                    claim_id = str(old_payload.get("claim_id") or "")
                    claim_ref = references.get(claim_id)
                    created_at, timestamp = _timestamp(old_payload.get("timestamp"))
                    payload_hash = hashlib.sha256(_canonical(source).encode("utf-8")).hexdigest()
                    seq = copied_count + 1
                    digest = _hash_v3(previous, seq, claim_ref, event_type, payload_hash, timestamp)
                    cursor.execute(
                        """INSERT INTO audit_ledger
                           (seq, claim_ref, event_type, payload_hash, prev_hash, hash, created_at, chain_version)
                           VALUES (:seq, :claim_ref, :event_type, :payload_hash, :prev_hash, :hash, :created_at, 3)""",
                        {"seq": seq, "claim_ref": claim_ref, "event_type": event_type,
                         "payload_hash": payload_hash, "prev_hash": previous, "hash": digest,
                         "created_at": created_at},
                    )
                    safe_details = _safe_details(old_payload)
                    cursor.execute(
                        "INSERT INTO audit_event_details (event_seq, details_json) VALUES (:seq, :details_json)",
                        {"seq": seq, "details_json": _canonical(safe_details)},
                    )
                    if old_type == "anchor":
                        cursor.execute(
                            """INSERT INTO legacy_anchors
                               (source_seq, from_seq, to_seq, root_hash, tx_hash, source_hash, created_at)
                               VALUES (:source_seq, :from_seq, :to_seq, :root_hash, :tx_hash, :source_hash, :created_at)""",
                            {"source_seq": int(source.get("seq", seq)),
                             "from_seq": int(old_payload.get("from_seq", 1)),
                             "to_seq": int(old_payload.get("to_seq", 1)),
                             "root_hash": old_payload.get("root"), "tx_hash": old_payload.get("tx_hash"),
                             "source_hash": source.get("hash", ""), "created_at": created_at},
                        )
                    previous = digest
                    copied_count += 1
                cursor.execute(
                    "UPDATE audit_ledger_head SET last_seq = :seq, last_hash = :hash WHERE singleton_id = 1",
                    {"seq": copied_count, "hash": previous},
                )
            connection.commit()
            response_cache.clear()
        copied = self.all_ledger_records()
        previous = GENESIS_HASH
        copied_check = {"verified": True}
        for index, record in enumerate(copied, start=1):
            if (record.get("seq") != index or record.get("prev_hash") != previous
                    or _hash_v3(previous, index, record.get("claim_ref"), record.get("type"),
                                record.get("payload_hash"), record.get("timestamp")) != record.get("hash")):
                copied_check = {"verified": False, "broken_at": index - 1}
                break
            previous = record["hash"]
        if not copied_check.get("verified") or len(copied) != len(records):
            raise RuntimeError("Oracle ledger copy failed post-migration verification")
        return {"source_count": len(records), "copied_count": len(copied),
                "source_verified": True, "copied_verified": True,
                "legacy_anchors_archived": sum(1 for row in records if row.get("type") == "anchor")}
