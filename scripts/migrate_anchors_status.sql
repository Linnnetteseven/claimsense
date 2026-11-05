-- Apply manually after confirming the anchors table is empty.
-- Enables durable pending/confirmed/failed transaction tracking.
ALTER TABLE anchors ADD (
    status VARCHAR2(16) DEFAULT 'confirmed' NOT NULL,
    head_hash CHAR(64)
);

ALTER TABLE anchors MODIFY (tx_hash NULL);
ALTER TABLE anchors ADD CONSTRAINT anchors_status_ck
    CHECK (status IN ('pending', 'confirmed', 'failed'));
ALTER TABLE anchors ADD CONSTRAINT anchors_root_hash_uq UNIQUE (root_hash);
COMMIT;
