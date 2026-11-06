-- Optional rollback for scripts/migrate_anchors_status.sql.
-- Run only if no pending/failed anchor rows need to be retained.
-- This removes anchor lifecycle metadata; it does not delete anchor rows
-- or undo any Avalanche transaction.

DECLARE
    null_tx_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO null_tx_count FROM anchors WHERE tx_hash IS NULL;
    IF null_tx_count > 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Rollback refused: anchors contain rows with NULL TX_HASH.'
        );
    END IF;
END;
/

ALTER TABLE anchors DROP CONSTRAINT anchors_status_ck;
ALTER TABLE anchors DROP CONSTRAINT anchors_root_hash_uq;
ALTER TABLE anchors MODIFY (tx_hash NOT NULL);
ALTER TABLE anchors DROP COLUMN status;
ALTER TABLE anchors DROP COLUMN head_hash;
COMMIT;
