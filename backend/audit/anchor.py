"""Manual Avalanche C-Chain anchoring and ledger verification."""
from __future__ import annotations

import hashlib
import json
import logging
import time

from config import config
from audit import chain

logger = logging.getLogger(__name__)
GENESIS_HASH = "0" * 16
ABI = [
    {"inputs": [{"internalType": "bytes32", "name": "root", "type": "bytes32"},
                {"internalType": "uint64", "name": "fromSeq", "type": "uint64"},
                {"internalType": "uint64", "name": "toSeq", "type": "uint64"}],
     "name": "anchor", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
     "name": "anchoredAt", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "owner", "outputs": [{"internalType": "address", "name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"},
    {"anonymous": False, "inputs": [
        {"indexed": True, "internalType": "bytes32", "name": "root", "type": "bytes32"},
        {"indexed": False, "internalType": "uint64", "name": "fromSeq", "type": "uint64"},
        {"indexed": False, "internalType": "uint64", "name": "toSeq", "type": "uint64"},
        {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"}],
     "name": "Anchored", "type": "event"},
]


def _repository():
    from db.factory import get_repository
    return get_repository()


def _oracle_active(repository) -> bool:
    return repository.backend_name == "oracle" or (
        repository.backend_name == "oracle_with_fallback" and repository.active_backend == "oracle"
    )


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
    contract = w3.eth.contract(address=Web3.to_checksum_address(config.ANCHOR_CONTRACT_ADDRESS), abi=ABI)
    return Web3, w3, contract


def _checkpoint_root(records: list[dict], from_seq: int, to_seq: int) -> tuple[bytes, str]:
    selected = records[from_seq - 1:to_seq]
    if not selected or selected[-1].get("seq", to_seq) != to_seq:
        raise ValueError("Requested sequence range is not present in the ledger")
    return _root_for_head(from_seq, to_seq, selected[-1]["hash"])


def _root_for_head(from_seq: int, to_seq: int, head_hash: str) -> tuple[bytes, str]:
    body = {"schema": "hakiki-anchor-v1", "from_seq": int(from_seq),
            "to_seq": int(to_seq), "head_hash": head_hash}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).digest()
    return digest, head_hash


def _explorer_url(tx_hash: str | None) -> str | None:
    return f"https://subnets-test.avax.network/c-chain/tx/{tx_hash}" if tx_hash else None


def _public_anchor(row: dict) -> dict:
    result = {key: row.get(key) for key in ("id", "from_seq", "to_seq", "root_hash", "head_hash", "tx_hash", "status", "created_at")}
    result["explorer_url"] = _explorer_url(row.get("tx_hash"))
    return result


def _verify_suffix(repository) -> tuple[dict | None, list[dict], dict | None]:
    """Verify the checkpoint link and only the records appended after it."""
    checkpoint_started = time.perf_counter()
    checkpoint = repository.get_verification_checkpoint()
    checkpoint_ms = (time.perf_counter() - checkpoint_started) * 1000
    if not checkpoint:
        return None, [], {"verified": False, "reason": "full_ledger_verification_required",
                          "message": "Run Verify full ledger before anchoring."}

    seq = int(checkpoint["seq"])
    digest = str(checkpoint["hash"]).strip()
    head = repository.get_ledger_head()
    if seq > int(head["seq"]):
        return checkpoint, [], {"verified": False, "reason": "checkpoint_ahead_of_ledger",
                                 "message": f"Verified checkpoint seq {seq} is ahead of ledger head {head['seq']}."}
    if seq == 0:
        if digest != GENESIS_HASH:
            return checkpoint, [], {"verified": False, "reason": "checkpoint_genesis_mismatch",
                                     "message": "The stored checkpoint does not match the ledger genesis hash."}
    else:
        linked = repository.get_ledger_record_hash(seq)
        if not linked or linked["hash"] != digest:
            return checkpoint, [], {"verified": False, "reason": "checkpoint_link_mismatch",
                                     "message": f"Ledger checkpoint link failed at seq {seq}."}

    read_started = time.perf_counter()
    suffix = repository.get_ledger_records_after(seq)
    read_ms = (time.perf_counter() - read_started) * 1000
    verify_started = time.perf_counter()
    integrity = chain.verify_records_from_checkpoint(suffix, seq, digest)
    verify_ms = (time.perf_counter() - verify_started) * 1000
    logger.info("anchor_prepare checkpoint_ms=%.1f suffix_read_ms=%.1f suffix_verify_ms=%.1f suffix_records=%d",
                checkpoint_ms, read_ms, verify_ms, len(suffix))
    if not integrity.get("verified"):
        broken = integrity.get("broken_at")
        return checkpoint, suffix, {**integrity, "reason": "ledger_suffix_mismatch",
                                    "message": f"Ledger verification failed at seq {broken}."}
    if suffix:
        if int(suffix[-1]["seq"]) != int(head["seq"]) or suffix[-1]["hash"] != head["hash"]:
            return checkpoint, suffix, {"verified": False, "reason": "ledger_head_mismatch",
                                        "message": "The verified ledger suffix does not match the stored ledger head."}
    elif int(head["seq"]) != seq or head["hash"] != digest:
        return checkpoint, suffix, {"verified": False, "reason": "ledger_head_mismatch",
                                    "message": "The stored ledger head does not match the verified checkpoint."}
    return {**checkpoint, "_verified_head": head}, suffix, None


def _oracle_anchor_latest() -> dict:
    started = time.perf_counter()
    repository = _repository()
    try:
        checkpoint, suffix, failure = _verify_suffix(repository)
    except Exception as exc:
        logger.warning("Anchor checkpoint verification unavailable type=%s", type(exc).__name__)
        return {"status": "blocked", "reason": "verification_checkpoint_unavailable",
                "message": "Could not read the verified checkpoint. Apply the checkpoint migration, then run Verify full ledger."}
    if failure:
        return {"status": "blocked", **failure}

    anchors = repository.list_anchor_records()
    pending = next((row for row in reversed(anchors) if row.get("status") == "pending"), None)
    if pending:
        return {"status": "pending", "anchor": _public_anchor(pending), "submitted": False,
                "reason": "An anchor transaction is already pending; check its status before retrying."}

    head = checkpoint["_verified_head"]
    confirmed_to = max((int(row["to_seq"]) for row in anchors if row.get("status") == "confirmed"), default=0)
    latest_confirmed = next((row for row in reversed(anchors) if row.get("status") == "confirmed"), None)
    if confirmed_to and not repository.has_non_anchor_events_after(confirmed_to, int(head["seq"])):
        return {"status": "confirmed", "anchor": _public_anchor(latest_confirmed),
                "reason": "No new non-anchor ledger events need anchoring."}
    from_seq, to_seq = confirmed_to + 1, int(head["seq"])
    if from_seq > to_seq:
        latest = next((row for row in reversed(anchors) if row.get("status") == "confirmed"), None)
        return {"status": "confirmed" if latest else "not_anchored",
                "anchor": _public_anchor(latest) if latest else None,
                "reason": "No new ledger records need anchoring."}

    root, head_hash = _root_for_head(from_seq, to_seq, head["hash"])
    from web3 import Web3
    root_hash = Web3.to_hex(root)
    row = repository.create_pending_anchor(from_seq, to_seq, root_hash, head_hash)
    created = bool(row.pop("_created", False))
    if not created:
        return {"status": row["status"], "anchor": _public_anchor(row), "submitted": False,
                "reason": "This ledger head already has an anchor record; no duplicate transaction was sent."}

    prepare_ms = (time.perf_counter() - started) * 1000
    logger.info("anchor_prepare duration_ms=%.1f suffix_records=%d from_seq=%d to_seq=%d",
                prepare_ms, len(suffix), from_seq, to_seq)
    submit_started = time.perf_counter()
    try:
        Web3, w3, contract = _web3()
        account = w3.eth.account.from_key(config.ANCHOR_PRIVATE_KEY)
        if Web3.to_checksum_address(contract.functions.owner().call()) != Web3.to_checksum_address(account.address):
            raise PermissionError("Configured signing account is not the contract owner")
        call = contract.functions.anchor(root, from_seq, to_seq)
        gas_limit = int(call.estimate_gas({"from": account.address}) * 1.2)
        tx = call.build_transaction({
            "from": account.address, "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": config.CHAIN_ID, "gas": gas_limit, "gasPrice": w3.eth.gas_price,
        })
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hex = Web3.to_hex(tx_hash)
        row = repository.update_anchor_submission(root_hash, tx_hex) or row
        logger.info("Avalanche transaction submitted root=%s tx_hash=%s", root_hash, tx_hex)
        return {"status": "pending", "anchor": _public_anchor(row), "submitted": True,
                "root_hash": root_hash, "explorer_url": _explorer_url(tx_hex)}
    except Exception as exc:
        repository.update_anchor_status(root_hash, "failed")
        logger.warning("Avalanche anchor submission failed type=%s", type(exc).__name__)
        reason = {"ConnectionError": "rpc_unavailable", "PermissionError": "signer_not_contract_owner",
                  "RuntimeError": "chain_or_contract_configuration_error", "ValueError": "invalid_anchor_configuration_or_range"}.get(
                      type(exc).__name__, "anchor_transaction_failed")
        failed = repository.get_anchor_by_root(root_hash) or row
        return {"status": "failed", "anchor": _public_anchor(failed), "reason": reason,
                "explorer_url": _explorer_url(failed.get("tx_hash"))}
    finally:
        logger.info("anchor_submit_and_persist duration_ms=%.1f", (time.perf_counter() - submit_started) * 1000)


def _legacy_anchor_latest() -> dict:
    """Keep the pre-existing Redis anchoring path unchanged."""
    records = chain.all_records()
    if not records:
        return {"status": "not_anchored", "reason": "ledger_empty"}
    integrity = chain.verify_records(records)
    if not integrity.get("verified"):
        return {"status": "mismatch", "integrity": integrity}
    anchors = [record for record in records if record.get("type") == "anchor"]
    from_seq = int(anchors[-1]["to_seq"]) + 1 if anchors else 1
    to_seq = len(records)
    new_events = [record for record in records if record.get("type") != "anchor"]
    if anchors and not any(int(record.get("seq", 0)) > int(anchors[-1].get("seq", 0)) for record in new_events):
        return {"status": "already_anchored", "head_hash": records[-1]["hash"]}
    try:
        Web3, w3, contract = _web3()
        account = w3.eth.account.from_key(config.ANCHOR_PRIVATE_KEY)
        if Web3.to_checksum_address(contract.functions.owner().call()) != Web3.to_checksum_address(account.address):
            raise PermissionError("Configured signing account is not the contract owner")
        root, head_hash = _checkpoint_root(records, from_seq, to_seq)
        call = contract.functions.anchor(root, from_seq, to_seq)
        tx = call.build_transaction({"from": account.address,
             "nonce": w3.eth.get_transaction_count(account.address), "chainId": config.CHAIN_ID,
             "gas": int(call.estimate_gas({"from": account.address}) * 1.2), "gasPrice": w3.eth.gas_price})
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        tx_hex = Web3.to_hex(tx_hash)
        if receipt.status != 1:
            raise RuntimeError("Anchor transaction reverted")
        event = chain.append_anchor_event({"tx_hash": tx_hex, "block_number": receipt.blockNumber,
                 "root": Web3.to_hex(root), "head_hash": head_hash, "from_seq": from_seq, "to_seq": to_seq})
        return {"status": "anchored", "tx_hash": tx_hex, "block_number": receipt.blockNumber,
                "head_hash": head_hash, "root": Web3.to_hex(root), "from_seq": from_seq,
                "to_seq": to_seq, "event_seq": event.get("seq") if event else None,
                "explorer_url": _explorer_url(tx_hex)}
    except Exception as exc:
        logger.warning("Avalanche legacy anchor failed type=%s", type(exc).__name__)
        reason = {"ConnectionError": "rpc_unavailable", "PermissionError": "signer_not_contract_owner",
                  "RuntimeError": "chain_or_contract_configuration_error", "ValueError": "invalid_anchor_configuration_or_range"}.get(
                      type(exc).__name__, "anchor_transaction_failed")
        return {"status": "unavailable", "reason": reason}


def anchor_latest() -> dict:
    try:
        repository = _repository()
        return _oracle_anchor_latest() if _oracle_active(repository) else _legacy_anchor_latest()
    except Exception as exc:
        logger.warning("Audit ledger unavailable for anchoring: %s", type(exc).__name__)
        return {"status": "failed", "reason": "audit_ledger_unavailable"}


def confirm_anchor(root_hash: str) -> dict:
    """Wait for the receipt in a background task and finalize the saved row."""
    repository = _repository()
    row = repository.get_anchor_by_root(root_hash)
    if not row or not row.get("tx_hash"):
        return {"status": row.get("status", "not_found") if row else "not_found"}
    try:
        Web3, w3, _contract = _web3()
        receipt = w3.eth.wait_for_transaction_receipt(row["tx_hash"], timeout=60)
        if receipt.status != 1:
            repository.update_anchor_status(root_hash, "failed")
            return {"status": "failed", "anchor": _public_anchor(repository.get_anchor_by_root(root_hash))}
        payload = {"tx_hash": row["tx_hash"], "block_number": int(receipt.blockNumber),
                   "root": root_hash, "head_hash": row["head_hash"],
                   "from_seq": row["from_seq"], "to_seq": row["to_seq"]}
        result = repository.finalize_anchor(root_hash, {"type": "anchor", **payload})
        return {"status": "confirmed", "anchor": _public_anchor(result["anchor"]),
                "block_number": int(receipt.blockNumber), "explorer_url": _explorer_url(row["tx_hash"])}
    except Exception as exc:
        repository.update_anchor_status(root_hash, "failed")
        logger.warning("Avalanche receipt wait failed root=%s type=%s", root_hash, type(exc).__name__)
        failed = repository.get_anchor_by_root(root_hash)
        return {"status": "failed", "anchor": _public_anchor(failed) if failed else None,
                "reason": "receipt_timeout_or_rpc_error", "explorer_url": _explorer_url(row.get("tx_hash"))}


def anchor_status(root_hash: str | None = None, check_chain: bool = False) -> dict:
    repository = _repository()
    if not _oracle_active(repository):
        return verify_anchors() if check_chain else {"status": "not_checked", "anchors": []}
    anchors = repository.list_anchor_records()
    selected = next((row for row in reversed(anchors) if root_hash is None or row["root_hash"].lower() == root_hash.lower()), None)
    if not selected:
        return {"status": "not_anchored", "anchors": []}
    status = selected["status"]
    block_number = None
    if check_chain and selected.get("tx_hash"):
        try:
            Web3, w3, contract = _web3()
            receipt = w3.eth.get_transaction_receipt(selected["tx_hash"])
            if receipt and receipt.status == 1:
                root_bytes = bytes.fromhex(selected["root_hash"].removeprefix("0x"))
                anchored_at = contract.functions.anchoredAt(root_bytes).call()
                if not anchored_at:
                    status = "mismatch"
                else:
                    if status != "confirmed":
                        finalized = repository.finalize_anchor(selected["root_hash"], {
                            "type": "anchor", "tx_hash": selected["tx_hash"], "block_number": int(receipt.blockNumber),
                            "root": selected["root_hash"], "head_hash": selected["head_hash"],
                            "from_seq": selected["from_seq"], "to_seq": selected["to_seq"],
                        })
                        selected = finalized["anchor"]
                    status = "confirmed"
                    block_number = int(receipt.blockNumber)
            elif receipt and receipt.status != 1:
                selected = repository.update_anchor_status(selected["root_hash"], "failed") or selected
                status = "failed"
        except Exception:
            # Not found or RPC unavailable: preserve the database's pending/failed state.
            pass
    anchor_view = _public_anchor(selected)
    anchor_view["status"] = status
    anchor_view["block_number"] = block_number
    return {"status": status, "anchors": [anchor_view], "anchor": anchor_view,
            "explorer_url": _explorer_url(selected.get("tx_hash"))}


def verify_full_ledger() -> dict:
    """Explicit deep verification; only this action loads the complete ledger."""
    started = time.perf_counter()
    read_started = time.perf_counter()
    records = chain.all_records()
    read_ms = (time.perf_counter() - read_started) * 1000
    verify_started = time.perf_counter()
    integrity = chain.verify_records(records)
    verify_ms = (time.perf_counter() - verify_started) * 1000
    result = {**integrity, "read_ms": round(read_ms, 1), "verify_ms": round(verify_ms, 1)}
    repository = _repository()
    if integrity.get("verified") and _oracle_active(repository):
        last_seq = int(records[-1]["seq"]) if records else 0
        last_hash = records[-1]["hash"] if records else GENESIS_HASH
        repository.save_verification_checkpoint(last_seq, last_hash)
        from web3 import Web3
        for row in repository.list_anchor_records():
            try:
                root, head_hash = _checkpoint_root(records, int(row["from_seq"]), int(row["to_seq"]))
                if Web3.to_hex(root).lower() == row["root_hash"].lower() and not row.get("head_hash"):
                    repository.backfill_anchor_head_hash(row["root_hash"], head_hash)
            except (ValueError, IndexError):
                continue
        result["checkpoint"] = {"seq": last_seq, "hash": last_hash}
    logger.info("manual_full_ledger_verification records=%d read_ms=%.1f verification_ms=%.1f total_ms=%.1f verified=%s",
                len(records), read_ms, verify_ms, (time.perf_counter() - started) * 1000, integrity.get("verified"))
    return result


def _verify_oracle_anchors() -> dict:
    repository = _repository()
    rows = repository.list_anchor_records()
    if not rows:
        return {"status": "not_anchored", "anchors": []}
    try:
        Web3, w3, contract = _web3()
        results = []
        overall = "verified"
        for row in rows:
            status = row.get("status") or "confirmed"
            item = _public_anchor(row)
            if status != "confirmed" or not row.get("tx_hash"):
                item["status"] = status
                results.append(item)
                if status == "pending":
                    overall = "pending"
                elif overall != "pending":
                    overall = "unavailable"
                continue
            expected_root, _ = _root_for_head(row["from_seq"], row["to_seq"], row.get("head_hash") or "")
            root = Web3.to_hex(expected_root)
            anchored_at = contract.functions.anchoredAt(bytes.fromhex(row["root_hash"].removeprefix("0x"))).call()
            receipt = w3.eth.get_transaction_receipt(row["tx_hash"])
            events = contract.events.Anchored().process_receipt(receipt)
            event_match = any(
                Web3.to_hex(event["args"]["root"]).lower() == root.lower()
                and int(event["args"]["fromSeq"]) == row["from_seq"]
                and int(event["args"]["toSeq"]) == row["to_seq"] for event in events
            )
            good = bool(anchored_at and receipt.status == 1 and event_match and root.lower() == row["root_hash"].lower())
            item.update(status="verified" if good else "mismatch", block_number=int(receipt.blockNumber) if receipt else None)
            results.append(item)
            if not good:
                overall = "mismatch"
                break
        return {"status": overall, "anchors": results}
    except Exception as exc:
        logger.warning("Avalanche anchor verification unavailable: %s", type(exc).__name__)
        return {"status": "unavailable", "reason": "rpc_or_contract_verification_failed", "anchors": []}


def _legacy_verify_anchors() -> dict:
    """Preserve the existing Redis ledger verification path and response shape."""
    records = chain.all_records()
    integrity = chain.verify_records(records)
    if not integrity.get("verified"):
        return {"status": "mismatch", "integrity": integrity, "anchors": []}
    local_anchors = [record for record in records if record.get("type") == "anchor"]
    try:
        Web3, w3, contract = _web3()
        if not local_anchors:
            return {"status": "not_anchored", "anchors": []}
        verified = []
        for item in local_anchors:
            seq, start = int(item["to_seq"]), int(item["from_seq"])
            root, head = _checkpoint_root(records, start, seq)
            timestamp = contract.functions.anchoredAt(root).call()
            receipt = w3.eth.get_transaction_receipt(item["tx_hash"])
            events = contract.events.Anchored().process_receipt(receipt)
            matches = any(
                Web3.to_hex(event["args"]["root"]).lower() == Web3.to_hex(root).lower()
                and int(event["args"]["fromSeq"]) == start
                and int(event["args"]["toSeq"]) == seq for event in events
            )
            if (receipt.status != 1 or not timestamp or not matches or head != item.get("head_hash")
                    or Web3.to_hex(root).lower() != item.get("root", "").lower()):
                return {"status": "mismatch", "anchors": verified + [{"seq": seq, "status": "mismatch"}]}
            verified.append({"seq": seq, "from_seq": start, "to_seq": seq,
                             "block_number": item.get("block_number"), "timestamp": timestamp,
                             "head_hash": head, "tx_hash": item.get("tx_hash"), "status": "verified"})
        return {"status": "verified", "anchors": verified}
    except Exception as exc:
        logger.warning("Avalanche anchor verification unavailable: %s", type(exc).__name__)
        return {"status": "unavailable", "reason": "rpc_or_contract_verification_failed", "anchors": []}


def verify_anchors() -> dict:
    try:
        repository = _repository()
        if _oracle_active(repository):
            return _verify_oracle_anchors()
        return _legacy_verify_anchors()
    except Exception as exc:
        logger.warning("Anchor verification unavailable: %s", type(exc).__name__)
        return {"status": "unavailable", "reason": "audit_ledger_unavailable", "anchors": []}
