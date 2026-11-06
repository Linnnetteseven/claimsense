import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from audit.chain import verify_records, _hash_record, _hash_record_v4
from audit import anchor

def make_records(count=3):
    records=[]; prev="0"*16
    for i in range(1,count+1):
        payload={"type":"validation","seq":i,"hash_version":2,"claim_id":f"C{i}","score":90,"timestamp":str(i)}
        digest=_hash_record(prev,payload)
        records.append({**payload,"prev_hash":prev,"hash":digest}); prev=digest
    return records

def test_edited_record_breaks_chain():
    records=make_records(); records[1]["score"]=10
    assert verify_records(records)["verified"] is False

def test_deleted_tail_breaks_anchor_root_range():
    records=make_records(); root,_=anchor._checkpoint_root(records,1,3)
    assert len(root)==32
    with pytest.raises(ValueError): anchor._checkpoint_root(records[:-1],1,3)

def test_reordered_records_break_chain():
    records=make_records(); records[0],records[1]=records[1],records[0]
    assert verify_records(records)["verified"] is False

def test_v4_oracle_records_verify_using_persisted_hash_input():
    header = {
        "seq": 1, "claim_ref": "a" * 32, "event_type": "claim_received",
        "payload_hash": "b" * 64, "timestamp": "2026-11-04T07:04:44Z",
    }
    previous = "0" * 16
    digest = _hash_record_v4(previous, {"hash_input": header, **{
        "seq": 1, "claim_ref": "a" * 32, "type": "claim_received",
        "payload_hash": "b" * 64, "timestamp": header["timestamp"],
    }})
    record = {
        "seq": 1, "claim_ref": "a" * 32, "type": "claim_received",
        "payload_hash": "b" * 64, "timestamp": header["timestamp"],
        "hash_input": header, "prev_hash": previous, "hash": digest, "hash_version": 4,
    }
    assert verify_records([record])["verified"] is True

    changed_input = {**record, "timestamp": "2026-11-04T10:04:44+03:00"}
    assert verify_records([changed_input])["verified"] is False

    changed_header = {**record, "hash_input": {**header, "payload_hash": "c" * 64}}
    assert verify_records([changed_header])["verified"] is False

def test_anchor_uses_owner_and_waits_for_receipt(monkeypatch):
    records=make_records(2)
    from db.testing import MemoryRepository
    repository = MemoryRepository()
    for record in records:
        repository.append_ledger_event({key: value for key, value in record.items() if key not in {"seq", "prev_hash", "hash", "hash_version", "claim_ref", "payload_hash"}})
    repository.save_verification_checkpoint(len(repository.records), repository.records[-1]["hash"])
    monkeypatch.setattr(anchor, "_repository", lambda: repository)
    monkeypatch.setattr(anchor.chain, "all_records", lambda: pytest.fail("Anchor prepare must not load the full ledger"))
    monkeypatch.setattr(anchor.config,"ANCHOR_PRIVATE_KEY","private-key-fixture")
    monkeypatch.setattr(anchor.config,"ANCHOR_CONTRACT_ADDRESS","0x"+"1"*40)
    fake_contract=MagicMock(); fake_contract.functions.owner.return_value.call.return_value="0x"+"2"*40
    fake_contract.functions.anchor.return_value.build_transaction.return_value={"tx":"unsigned"}
    fake_account=MagicMock(); fake_account.address="0x"+"2"*40; fake_account.sign_transaction.return_value.raw_transaction=b"signed"
    fake_w3=MagicMock(); fake_w3.eth.chain_id=43113; fake_w3.eth.account.from_key.return_value=fake_account
    fake_w3.eth.get_transaction_count.return_value=4; fake_w3.eth.gas_price=1
    def submit_only_after_pending(_raw):
        assert repository.anchors and repository.anchors[0]["status"] == "pending"
        return b"txhash"
    fake_w3.eth.send_raw_transaction.side_effect=submit_only_after_pending
    fake_w3.eth.wait_for_transaction_receipt.return_value=MagicMock(status=1,blockNumber=99)
    fake_w3.is_connected.return_value=True
    fake_web3=MagicMock(); fake_web3.HTTPProvider.return_value=None; fake_web3.return_value=fake_w3
    fake_web3.to_checksum_address.side_effect=lambda x:x; fake_web3.to_hex.return_value="0x"+"a"*64
    monkeypatch.setattr(anchor,"_web3",lambda:(fake_web3,fake_w3,fake_contract))
    result=anchor.anchor_latest()
    assert result["status"] == "pending"
    assert result["anchor"]["status"] == "pending"
    assert result["anchor"]["tx_hash"] == "0x" + "a" * 64
    assert repository.anchors[0]["tx_hash"] == "0x" + "a" * 64
    fake_w3.eth.wait_for_transaction_receipt.assert_not_called()
    completed = anchor.confirm_anchor(result["root_hash"])
    assert completed["status"] == "confirmed"
    assert repository.anchors[0]["status"] == "confirmed"
    fake_w3.eth.wait_for_transaction_receipt.assert_called_once()

def test_already_anchored_head_does_not_send_another_transaction(monkeypatch):
    from db.testing import MemoryRepository
    repository = MemoryRepository()
    repository.append_ledger_event({"type": "claim_received", "claim_id": "C1", "version": 1})
    repository.append_ledger_event({"type": "anchor", "root": "0x" + "a" * 64, "from_seq": 1,
                                    "to_seq": 1, "tx_hash": "0x" + "b" * 64})
    repository.save_verification_checkpoint(len(repository.records), repository.records[-1]["hash"])
    repository.anchors.append({"id": 1, "from_seq": 1, "to_seq": 1, "root_hash": "0x" + "a" * 64,
                               "head_hash": repository.records[0]["hash"], "status": "confirmed",
                               "tx_hash": "0x" + "b" * 64, "created_at": "test"})
    monkeypatch.setattr(anchor, "_repository", lambda: repository)
    monkeypatch.setattr(anchor.chain, "all_records", lambda: pytest.fail("Anchor prepare must not load the full ledger"))
    monkeypatch.setattr(anchor,"_web3",lambda:pytest.fail("Should not make another chain transaction"))
    assert anchor.anchor_latest()["status"] == "confirmed"


def test_pending_anchor_is_returned_without_resubmitting(monkeypatch):
    from db.testing import MemoryRepository
    repository = MemoryRepository()
    repository.append_ledger_event({"type": "claim_received", "claim_id": "C1", "version": 1})
    repository.save_verification_checkpoint(1, repository.records[0]["hash"])
    repository.anchors.append({"id": 1, "from_seq": 1, "to_seq": 1, "root_hash": "0x" + "a" * 64,
                               "head_hash": repository.records[0]["hash"], "status": "pending",
                               "tx_hash": "0x" + "b" * 64, "created_at": "test"})
    monkeypatch.setattr(anchor, "_repository", lambda: repository)
    monkeypatch.setattr(anchor.chain, "all_records", lambda: pytest.fail("Anchor prepare must not load the full ledger"))
    monkeypatch.setattr(anchor, "_web3", lambda: pytest.fail("Pending anchor must not send again"))
    result = anchor.anchor_latest()
    assert result["status"] == "pending"
    assert result["submitted"] is False
    assert result["anchor"]["tx_hash"] == "0x" + "b" * 64


def test_receipt_timeout_marks_saved_anchor_failed(monkeypatch):
    from db.testing import MemoryRepository
    repository = MemoryRepository()
    pending = repository.create_pending_anchor(1, 1, "0x" + "a" * 64, "c" * 64)
    repository.update_anchor_submission(pending["root_hash"], "0x" + "b" * 64)
    fake_w3 = MagicMock()
    fake_w3.eth.wait_for_transaction_receipt.side_effect = TimeoutError("receipt timeout")
    fake_web3 = MagicMock()
    fake_web3.to_checksum_address.side_effect = lambda value: value
    monkeypatch.setattr(anchor, "_repository", lambda: repository)
    monkeypatch.setattr(anchor, "_web3", lambda: (fake_web3, fake_w3, MagicMock()))
    result = anchor.confirm_anchor(pending["root_hash"])
    assert result["status"] == "failed"
    assert repository.get_anchor_by_root(pending["root_hash"])["status"] == "failed"
    assert repository.get_anchor_by_root(pending["root_hash"])["tx_hash"] == "0x" + "b" * 64


def test_broken_suffix_blocks_anchor_before_any_transaction(monkeypatch):
    from db.testing import MemoryRepository
    repository = MemoryRepository()
    repository.append_ledger_event({"type": "claim_received", "claim_id": "C1", "version": 1})
    checkpoint_hash = repository.records[0]["hash"]
    repository.save_verification_checkpoint(1, checkpoint_hash)
    repository.append_ledger_event({"type": "validation", "claim_id": "C1", "score": 90})
    repository.records[-1]["payload_hash"] = "tampered"
    monkeypatch.setattr(anchor, "_repository", lambda: repository)
    monkeypatch.setattr(anchor.chain, "all_records", lambda: pytest.fail("Anchor prepare must not load the full ledger"))
    monkeypatch.setattr(anchor, "_web3", lambda: pytest.fail("Broken suffix must be rejected before RPC send"))
    result = anchor.anchor_latest()
    assert result["status"] == "blocked"
    assert result["reason"] == "ledger_suffix_mismatch"
    assert result["message"] == "Ledger verification failed at seq 2."


def test_missing_checkpoint_requires_manual_full_verification(monkeypatch):
    from db.testing import MemoryRepository
    repository = MemoryRepository()
    repository.append_ledger_event({"type": "claim_received", "claim_id": "C1", "version": 1})
    monkeypatch.setattr(anchor, "_repository", lambda: repository)
    monkeypatch.setattr(anchor, "_web3", lambda: pytest.fail("Must require full verification first"))
    result = anchor.anchor_latest()
    assert result["status"] == "blocked"
    assert result["reason"] == "full_ledger_verification_required"


def test_full_verification_saves_checkpoint_without_chain_transaction(monkeypatch):
    from db.testing import MemoryRepository
    repository = MemoryRepository()
    repository.append_ledger_event({"type": "claim_received", "claim_id": "C1", "version": 1})
    monkeypatch.setattr(anchor, "_repository", lambda: repository)
    monkeypatch.setattr(anchor.chain, "all_records", repository.all_ledger_records)
    monkeypatch.setattr(anchor, "_web3", lambda: pytest.fail("Full ledger verification does not send a transaction"))
    result = anchor.verify_full_ledger()
    assert result["verified"] is True
    assert result["checkpoint"]["seq"] == 1
    assert repository.get_verification_checkpoint()["hash"] == repository.records[-1]["hash"]


def test_anchor_route_returns_409_when_checkpoint_verification_fails(monkeypatch):
    import asyncio
    from fastapi import BackgroundTasks, HTTPException
    from main import anchor_audit_ledger
    from config import config

    monkeypatch.setattr(config, "ANCHOR_API_SECRET", "test-secret")
    monkeypatch.setattr(anchor, "anchor_latest", lambda: {
        "status": "blocked", "reason": "ledger_suffix_mismatch",
        "message": "Ledger verification failed at seq 12.",
    })
    with pytest.raises(HTTPException) as error:
        asyncio.run(anchor_audit_ledger(BackgroundTasks(), "test-secret"))
    assert error.value.status_code == 409
    assert error.value.detail == "Ledger verification failed at seq 12."
