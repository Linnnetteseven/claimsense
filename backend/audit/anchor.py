"""Manual Avalanche C-Chain checkpointing for the optional audit ledger."""
import hashlib
import json
import logging
from config import config
from audit import chain

logger = logging.getLogger(__name__)
ABI = [
 {"inputs":[{"internalType":"bytes32","name":"root","type":"bytes32"},{"internalType":"uint64","name":"fromSeq","type":"uint64"},{"internalType":"uint64","name":"toSeq","type":"uint64"}],"name":"anchor","outputs":[],"stateMutability":"nonpayable","type":"function"},
 {"inputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"name":"anchoredAt","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
 {"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},
 {"anonymous":False,"inputs":[{"indexed":True,"internalType":"bytes32","name":"root","type":"bytes32"},{"indexed":False,"internalType":"uint64","name":"fromSeq","type":"uint64"},{"indexed":False,"internalType":"uint64","name":"toSeq","type":"uint64"},{"indexed":False,"internalType":"uint256","name":"timestamp","type":"uint256"}],"name":"Anchored","type":"event"},
]

def _web3():
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(config.AVAX_RPC_URL, request_kwargs={"timeout": 12}))
    if not w3.is_connected():
        raise ConnectionError("Avalanche RPC unavailable")
    if w3.eth.chain_id != config.CHAIN_ID:
        raise RuntimeError(f"Connected chain id {w3.eth.chain_id} does not match configured CHAIN_ID")
    if config.CHAIN_ID != 43113:
        raise RuntimeError("Only Fuji testnet (CHAIN_ID=43113) is enabled by this integration")
    if not config.ANCHOR_CONTRACT_ADDRESS or not config.ANCHOR_PRIVATE_KEY:
        raise RuntimeError("Avalanche anchor is not configured")
    return Web3, w3, w3.eth.contract(address=Web3.to_checksum_address(config.ANCHOR_CONTRACT_ADDRESS), abi=ABI)

def _checkpoint_root(records: list[dict], from_seq: int, to_seq: int) -> tuple[bytes, str]:
    selected = records[from_seq - 1:to_seq]
    if not selected or selected[-1].get("seq", to_seq) != to_seq:
        raise ValueError("Requested sequence range is not present in the ledger")
    head_hash = selected[-1]["hash"]
    body = {"schema": "hakiki-anchor-v1", "from_seq": from_seq, "to_seq": to_seq, "head_hash": head_hash}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).digest()
    return digest, head_hash

def _anchor_latest() -> dict:
    records = chain.all_records()
    if not records:
        return {"status": "not_anchored", "reason": "ledger_empty"}
    integrity = chain.verify_records(records)
    if not integrity.get("verified"):
        return {"status": "mismatch", "integrity": integrity}
    anchors = [r for r in records if r.get("type") == "anchor"]
    from_seq = int(anchors[-1]["to_seq"]) + 1 if anchors else 1
    to_seq = len(records)
    # Do not create another transaction when only the previous anchor event
    # has been appended since the last checkpoint.
    if anchors:
        last_anchor_seq = int(anchors[-1].get("seq", 0))
        new_non_anchor_records = [
            record for record in records
            if int(record.get("seq", 0)) > last_anchor_seq and record.get("type") != "anchor"
        ]
    else:
        new_non_anchor_records = records
    if anchors and not new_non_anchor_records:
        return {"status": "already_anchored", "head_hash": records[-1]["hash"]}
    try:
        Web3, w3, contract = _web3()
        account = w3.eth.account.from_key(config.ANCHOR_PRIVATE_KEY)
        if Web3.to_checksum_address(contract.functions.owner().call()) != Web3.to_checksum_address(account.address):
            raise PermissionError("Configured signing account is not the contract owner")
        root, head_hash = _checkpoint_root(records, from_seq, to_seq)
        nonce = w3.eth.get_transaction_count(account.address)
        call = contract.functions.anchor(root, from_seq, to_seq)
        gas_limit = int(call.estimate_gas({"from": account.address}) * 1.2)
        tx = call.build_transaction({"from": account.address, "nonce": nonce, "chainId": config.CHAIN_ID, "gas": gas_limit, "gasPrice": w3.eth.gas_price})
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt.status != 1:
            raise RuntimeError("Anchor transaction reverted")
        tx_hex = Web3.to_hex(tx_hash)
        event = chain.append_anchor_event({"tx_hash": tx_hex, "block_number": receipt.blockNumber, "root": Web3.to_hex(root), "head_hash": head_hash, "from_seq": from_seq, "to_seq": to_seq})
        return {"status": "anchored", "tx_hash": tx_hex, "block_number": receipt.blockNumber, "head_hash": head_hash, "root": Web3.to_hex(root), "from_seq": from_seq, "to_seq": to_seq, "event_seq": event.get("seq") if event else None, "explorer_url": f"https://subnets-test.avax.network/c-chain/tx/{tx_hex}"}
    except Exception as exc:
        # Do not serialize arbitrary provider/signing exceptions: they can
        # include transaction details. The private key is never logged or returned.
        logger.warning("Avalanche anchor unavailable: %s", type(exc).__name__)
        reason = {
            "ConnectionError": "rpc_unavailable",
            "PermissionError": "signer_not_contract_owner",
            "RuntimeError": "chain_or_contract_configuration_error",
            "ValueError": "invalid_anchor_configuration_or_range",
        }.get(type(exc).__name__, "anchor_transaction_failed")
        return {"status": "unavailable", "reason": reason}

def _verify_anchors() -> dict:
    records = chain.all_records()
    integrity = chain.verify_records(records)
    if not integrity.get("verified"):
        return {"status": "mismatch", "integrity": integrity, "anchors": []}
    local_anchors = [r for r in records if r.get("type") == "anchor"]
    try:
        Web3, w3, contract = _web3()
        if not local_anchors:
            return {"status": "not_anchored", "anchors": []}
        verified=[]
        for anchor in local_anchors:
            seq=int(anchor["to_seq"]); start=int(anchor["from_seq"])
            root, head = _checkpoint_root(records, start, seq)
            timestamp=contract.functions.anchoredAt(root).call()
            receipt = w3.eth.get_transaction_receipt(anchor["tx_hash"])
            receipt_events = contract.events.Anchored().process_receipt(receipt)
            matching_event = any(
                Web3.to_hex(event["args"]["root"]).lower() == Web3.to_hex(root).lower()
                and int(event["args"]["fromSeq"]) == start
                and int(event["args"]["toSeq"]) == seq
                for event in receipt_events
            )
            if receipt.status != 1 or not timestamp or not matching_event or head != anchor.get("head_hash") or Web3.to_hex(root).lower() != anchor.get("root", "").lower():
                return {"status":"mismatch","anchors":verified+[{"seq":seq,"status":"mismatch"}]}
            verified.append({"seq":seq,"from_seq":start,"to_seq":int(anchor["to_seq"]),"block_number":anchor.get("block_number"),"timestamp":timestamp,"head_hash":head,"tx_hash":anchor.get("tx_hash"),"status":"verified"})
        return {"status":"verified","anchors":verified}
    except Exception as exc:
        logger.warning("Avalanche anchor verification unavailable: %s", type(exc).__name__)
        return {"status":"unavailable","reason":"rpc_or_contract_verification_failed","anchors":[]}

def anchor_latest() -> dict:
    try:
        return _anchor_latest()
    except Exception as exc:
        logger.warning("Audit ledger unavailable for anchoring: %s", type(exc).__name__)
        return {"status": "unavailable", "reason": "audit_ledger_unavailable"}

def verify_anchors() -> dict:
    try:
        return _verify_anchors()
    except Exception as exc:
        logger.warning("Audit ledger unavailable for anchor verification: %s", type(exc).__name__)
        return {"status": "unavailable", "reason": "audit_ledger_unavailable", "anchors": []}
