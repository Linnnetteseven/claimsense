-- Apply once to an existing Hakiki Oracle schema before deploying lifecycle code.
-- Existing validation rows are retained and marked with unknown rule metadata.
ALTER TABLE validation_runs ADD (
    rules_version VARCHAR2(64) DEFAULT 'unknown' NOT NULL,
    rules_date VARCHAR2(10) DEFAULT 'unknown' NOT NULL,
    informational NUMBER(1) DEFAULT 0 NOT NULL
);

COMMIT;
