-- Rollback only after pending anchor rows have been resolved and tx_hash is
-- populated for every row. This restores the original non-null tx_hash rule.
ALTER TABLE anchors DROP CONSTRAINT anchors_root_hash_uq;
ALTER TABLE anchors DROP CONSTRAINT anchors_status_ck;
ALTER TABLE anchors MODIFY (tx_hash NOT NULL);
ALTER TABLE anchors DROP COLUMN head_hash;
ALTER TABLE anchors DROP COLUMN status;
COMMIT;
