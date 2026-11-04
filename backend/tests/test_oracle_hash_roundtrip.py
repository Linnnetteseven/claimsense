import json
from types import SimpleNamespace
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from audit import chain
from db.oracle_impl import GENESIS_HASH, OracleRepository


class FakeCursor:
    def __init__(self):
        self.next_row = None
        self.ledger_values = None
        self.details_json = None

    def execute(self, sql, params=None):
        if "SELECT last_seq" in sql:
            self.next_row = (0, GENESIS_HASH)
        elif "SELECT claim_ref FROM claims" in sql:
            self.next_row = ("a" * 32,)
        elif "INSERT INTO audit_ledger" in sql:
            self.ledger_values = params
        elif "INSERT INTO audit_event_details" in sql:
            self.details_json = params["details_json"]

    def fetchone(self):
        return self.next_row


def test_oracle_append_persists_hash_input_and_round_trips(monkeypatch):
    cursor = FakeCursor()
    payload = {
        "type": "claim_received", "claim_id": "SYN-CLM-000001", "version": 1,
        "timestamp": "2026-11-04T07:04:44Z",
    }

    appended = OracleRepository()._append_cursor(None, cursor, payload)
    details = json.loads(cursor.details_json)
    ledger = cursor.ledger_values

    # Simulate Oracle returning a different display format for its timestamp.
    # The persisted input is what chain verification must use for v4.
    persisted = {
        **details,
        "seq": ledger["seq"], "claim_ref": ledger["claim_ref"],
        "type": ledger["event_type"], "payload_hash": ledger["payload_hash"],
        "prev_hash": ledger["prev_hash"], "hash": ledger["hash"],
        "hash_version": 4,
        "timestamp": "2026-11-04T10:04:44+03:00",
    }
    persisted["timestamp"] = persisted["hash_input"]["timestamp"]
    monkeypatch.setattr(chain, "_repository", lambda: SimpleNamespace(backend_name="oracle"))

    assert appended["hash_version"] == 4
    assert details["hash_input"] == appended["hash_input"]
    assert chain.verify_records([persisted])["verified"] is True

    tampered = {**persisted, "hash_input": {**persisted["hash_input"], "payload_hash": "f" * 64}}
    assert chain.verify_records([tampered])["verified"] is False
