-- Apply once to an existing Hakiki Oracle schema before using checkpointed anchoring.
-- No checkpoint is inserted here: run Verify full ledger in Hakiki after applying this.
CREATE TABLE audit_verification_checkpoint (
    singleton_id       NUMBER(1) PRIMARY KEY CHECK (singleton_id = 1),
    last_verified_seq  NUMBER(20) NOT NULL,
    last_verified_hash CHAR(64) NOT NULL,
    verified_at        TIMESTAMP WITH TIME ZONE NOT NULL
);
COMMIT;
