import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from audit.chain import verify_records, _hash_record
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

def test_anchor_uses_owner_and_waits_for_receipt(monkeypatch):
    records=make_records(2)
    monkeypatch.setattr(anchor.chain,"all_records",lambda:records)
    monkeypatch.setattr(anchor.chain,"verify_records",lambda rows:{"verified":True})
    event={"seq":3}
    monkeypatch.setattr(anchor.chain,"append_anchor_event",lambda payload:event)
    monkeypatch.setattr(anchor.config,"ANCHOR_PRIVATE_KEY","private-key-fixture")
    monkeypatch.setattr(anchor.config,"ANCHOR_CONTRACT_ADDRESS","0x"+"1"*40)
    fake_contract=MagicMock(); fake_contract.functions.owner.return_value.call.return_value="0x"+"2"*40
    fake_contract.functions.anchor.return_value.build_transaction.return_value={"tx":"unsigned"}
    fake_account=MagicMock(); fake_account.address="0x"+"2"*40; fake_account.sign_transaction.return_value.raw_transaction=b"signed"
    fake_w3=MagicMock(); fake_w3.eth.chain_id=43113; fake_w3.eth.account.from_key.return_value=fake_account
    fake_w3.eth.get_transaction_count.return_value=4; fake_w3.eth.gas_price=1
    fake_w3.eth.send_raw_transaction.return_value=b"txhash"
    fake_w3.eth.wait_for_transaction_receipt.return_value=MagicMock(status=1,blockNumber=99)
    fake_w3.is_connected.return_value=True
    fake_web3=MagicMock(); fake_web3.HTTPProvider.return_value=None; fake_web3.return_value=fake_w3
    fake_web3.to_checksum_address.side_effect=lambda x:x; fake_web3.to_hex.return_value="0x"+"a"*64
    monkeypatch.setattr(anchor,"_web3",lambda:(fake_web3,fake_w3,fake_contract))
    result=anchor.anchor_latest()
    assert result["status"]=="anchored" and result["block_number"]==99
    fake_w3.eth.wait_for_transaction_receipt.assert_called_once()

def test_already_anchored_head_does_not_send_another_transaction(monkeypatch):
    records=make_records(1)
    payload={"type":"anchor","seq":2,"hash_version":2,"to_seq":1,"from_seq":1}
    digest=_hash_record(records[-1]["hash"],payload)
    records.append({**payload,"prev_hash":records[-1]["hash"],"hash":digest})
    monkeypatch.setattr(anchor.chain,"all_records",lambda:records)
    monkeypatch.setattr(anchor.chain,"verify_records",lambda rows:{"verified":True})
    monkeypatch.setattr(anchor,"_web3",lambda:pytest.fail("Should not make another chain transaction"))
    assert anchor.anchor_latest()["status"]=="already_anchored"
