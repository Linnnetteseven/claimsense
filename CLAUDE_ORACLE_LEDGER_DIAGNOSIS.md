# Hakiki Oracle Ledger Failure: Context and Request for Review

## Purpose

Please review this repository and the Oracle ledger problem described below. We need a clear explanation of the likely root cause and a safe, practical recovery plan. Please determine whether clearing and restarting the demo database is the best option, or whether there is a better way to preserve the existing history.

**Do not run database writes, delete data, rewrite hashes, change blockchain anchors, or make code changes yet.** First inspect the code and give a recommendation with the trade-offs. Do not ask for or include database passwords, wallet passwords, private keys, API tokens, or patient data.

## Project context

Hakiki is a department-led hospital claims preparation demo. The backend is FastAPI; the frontend is React/Vite. The default backend store remains Redis/in-process. For this demo, the user deliberately selected Oracle Autonomous Database with:

- `DB_BACKEND=oracle`
- `python-oracledb` Thin mode
- an existing Autonomous Database, user/schema `HAKIKI_APP`, and a downloaded wallet
- a synthetic-only workload based on Kerugoya County Referral Hospital (Level 5)
- an optional audit ledger that can be anchored to an Avalanche Fuji `HakikiAnchor` contract

The Oracle schema includes `claims`, `claim_versions`, `validation_runs`, `department_signoffs`, `claim_outcomes`, `audit_ledger`, `audit_event_details`, `anchors`, `legacy_anchors`, and `audit_ledger_head`. The ledger is intended to be append-only and hash chained. The `audit_ledger` table keeps random `claim_ref` values and hash commitments rather than raw identifiers.

Relevant code to inspect:

- `backend/db/oracle_impl.py`: `_hash_v3`, `_append_cursor`, `all_ledger_records`, `create_claim`, `record_validation`, migration and Oracle persistence behavior.
- `backend/audit/chain.py`: `_hash_record_v3`, `verify_records`, and the shared chain verification behavior.
- `backend/db/schema.sql`: Oracle table types, constraints, initial ledger head row, and foreign keys.
- `scripts/seed_synthetic_claims.py`: seed loop, reset behavior, and final verification.
- `scripts/migrate_redis_to_oracle.py`: legacy migration entry point.
- `backend/tests/test_anchor_integrity.py`, `backend/tests/test_repository.py`, and `backend/tests/test_synthetic_seed.py`.

The current branch is `oracle-db`. Recent commits include `5391e68` (local evidence packs), `bab7c4a` (experimental Select AI), and `fa49b4f` (make the standalone seeder load the repo-root `.env`). These are not believed to be changes to the v3 hash formula, but please verify with `git log`/`git blame` rather than assuming.

## What happened

1. The standalone seeder initially failed with `Oracle database configuration is incomplete`. The web application loaded the root `.env`, but the script did not. A code fix now makes the seeder load the repository-root `.env`, while shell environment variables retain precedence.
2. A subsequent run connected to Oracle, then failed during an insert with a network timeout/reset (`WinError 10060`, `WinError 10054`, `DPY-4011`).
3. The user ran `Resolve-DnsName adb.af-johannesburg-1.oraclecloud.com`; it timed out. `Test-NetConnection` to that host on port `1522` succeeded (`TcpTestSucceeded: True`).
4. A later health-check attempt used system Python instead of the virtual environment and returned `ModuleNotFoundError`. The user then ran the seeder inside the virtual environment.
5. The seeder was run with `--count 250 --reset`. It printed:

   ```text
   Removed 157 synthetic claims and their dependent app rows; audit history retained.
   ```

   It then completed its seeding loop but failed at the final chain verification with:

   ```text
   RuntimeError: Audit chain verification failed at record 0
   ```

   In `seed_repository`, this verification is after the claim/version/validation/department writes. The latest run therefore likely inserted the 250 synthetic claims, but the current row count has not been checked. The script's `--reset` deletes synthetic app rows and their dependent rows; it deliberately retains the append-only audit ledger and its history. Repeating `--reset` does not fix this ledger failure.

## Current read-only diagnostic results

The user's current Oracle ledger query through the repository returned:

```text
records: 1106
verification: {'verified': False, 'total': 1106, 'broken_at': 0}
first_record: {'seq': 1, 'type': 'claim_received', 'hash_version': 3,
               'timestamp': '2026-11-03T12:35:23Z'}
last_seq: 1106
```

The first record was then inspected using the current `_hash_v3` function:

```text
seq: 1
type: claim_received
hash_version: 3
timestamp: 2026-11-03T12:35:23Z
prev_hash: 0000000000000000
payload_hash: ea77224581b0a3c27f0fce8bf4cb299bad01f38a2d00a00779384a83afdd5fd1
stored hash: 140a9921d0d5a0cb38362fefd97450da9ed5dd595c811f95f4403f09a90ac43d
current recomputed hash: 03ab834edfe6937ef8c0f13ed1b0b63dc2ab483b8ddfdbc089b77cb3bc170b69
```

The first record's `prev_hash` correctly equals the current genesis constant (`16` zero characters). The first `claim_ref` exists. The following boolean checks all returned `False`:

- recomputation using the current format and current stored fields
- recomputation with `claim_ref` set to null
- recomputation with the `claim_ref` key omitted
- recomputation with the timestamp rendered as an ISO `+00:00` offset
- recomputation using a 64-character zero previous hash

No claim ID, patient details, credential values, wallet files, or private keys are included here. The values above are ledger hashes and safe metadata; do not infer that a digest mismatch by itself proves malicious alteration.

## Key questions to answer

1. Inspect the exact `v3` hash creation and verification code. Are `_hash_v3` and `_hash_record_v3` mathematically identical for a stored Oracle record? Is there a subtle serialization, type, field, Oracle `CHAR` padding, timestamp, time-zone, or `claim_ref` issue?
2. Is the row returned by `all_ledger_records` exactly the same hash input used when sequence 1 was appended? Check the Oracle query and conversions (`RTRIM`, `TO_CHAR`, `TIMESTAMP WITH TIME ZONE`, numeric conversion, `payload_hash` type).
3. Could the first row have been written by another checkout or earlier runtime version? Use Git history to identify any changes to the hashing format. Do not assume an earlier format unless the repository or row evidence supports it.
4. Why does the first record hash fail even though its genesis link is correct? Identify the highest-confidence cause and the evidence for it. If there is not enough information to identify the original input, say so plainly.
5. Could the latest seed itself have altered the first record? The first timestamp predates the latest seed. Explain what the failure location tells us and what it does not prove.
6. What test can reproduce or rule out this failure without using the user's live database credentials? Add/describe a focused fake-cursor repository test covering append → database-style round-trip → verify, including Oracle timestamp and fixed-width `CHAR` behavior.

## Recovery options to assess

Compare these options and recommend one, ranked by safety and effort:

### A. Preserve and repair the existing ledger

Is there a defensible way to recover the original hashes from the stored data? If rehashing is proposed, explain that it changes historical commitments and invalidates any Avalanche roots that cover the changed records. Do not overwrite original hashes without archiving the old ledger, old hashes, details, anchors, and head.

### B. Add an explicit ledger epoch / archive

Could the existing chain be frozen as an unverified legacy chain while a new chain starts at a clean genesis? What schema and code changes would represent chain IDs/epochs, verification scopes, sequence ranges, and separate Avalanche anchors without mixing epochs? How would old anchor transaction hashes remain traceable?

### C. Start a clean demo schema while preserving the existing schema

Creating a second Oracle user/schema (for example `HAKIKI_DEMO`) in the same Autonomous Database was suggested as the safest non-destructive restart. It would leave `HAKIKI_APP` and its 1,106 existing events untouched, use the same database host/DSN/wallet, apply `schema.sql` and `views.sql` under the new schema, then point the app to the new user. Is this actually the best choice? Could the v3 hash defect, if it is in code rather than old data, recur in the new schema? Propose a small preflight that detects such a problem before committing to a 250-row seed.

### D. Clear and reuse `HAKIKI_APP`

The user asks whether the previous schema can simply be cleared. Assess this as a valid demo-only option if the data is synthetic and the user explicitly accepts retiring that local history. List exactly what must be backed up, which tables must be cleared in foreign-key-safe order, how `audit_ledger_head` must be reset to sequence 0 and the genesis hash, and what must happen to `anchors` and `legacy_anchors`. Emphasize that on-chain Avalanche transactions cannot be deleted. If sequence ranges restart at 1, discuss whether a new Fuji contract is advisable to avoid ambiguous old/new ranges.

The existing `--reset` is **not** a complete ledger reset. It only deletes synthetic claim rows and dependent app rows while retaining all audit events and anchors. Do not recommend running it repeatedly as a fix for a broken first hash.

## Safety and output requested

Please return:

1. The likely root cause, separated from hypotheses.
2. A short explanation in plain language that the founder can understand.
3. A comparison table for options A–D: data preserved, effect on old Avalanche anchors, code changes, Oracle steps, risk, and effort.
4. Your recommended path and exact staged steps, including a preflight test that stops before a large seed if hashes do not verify.
5. A precise backup/rollback plan before any destructive Oracle SQL.
6. Any code defects/tests you recommend fixing **before** a restart.

Do not execute the repair or include destructive SQL as something to paste immediately. The founder wants a quick, safe way forward, but must understand the effect on the current 1,106 records and any on-chain history first.
