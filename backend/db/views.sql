-- Shared analytics definitions for Hakiki's synthetic demo workload.
-- Apply as HAKIKI_APP after schema.sql. API routes SELECT from these views;
-- keep metric logic here so each client sees the same definitions.

CREATE OR REPLACE VIEW v_claims_by_status AS
WITH latest_run AS (
    SELECT claim_id, status,
           ROW_NUMBER() OVER (PARTITION BY claim_id ORDER BY created_at DESC, id DESC) rn
    FROM validation_runs
)
SELECT NVL(lr.status, NVL(c.status, 'Not validated')) AS status,
       COUNT(*) AS claim_count
FROM claims c
LEFT JOIN latest_run lr ON lr.claim_id = c.id AND lr.rn = 1
WHERE JSON_VALUE(c.payload, '$.is_synthetic') = 'true'
GROUP BY NVL(lr.status, NVL(c.status, 'Not validated'));

CREATE OR REPLACE VIEW v_score_by_department AS
WITH latest_run AS (
    SELECT claim_id, score,
           ROW_NUMBER() OVER (PARTITION BY claim_id ORDER BY created_at DESC, id DESC) rn
    FROM validation_runs
)
SELECT NVL(c.department, 'Unassigned') AS department,
       ROUND(AVG(lr.score), 1) AS avg_score,
       COUNT(*) AS claims
FROM claims c
JOIN latest_run lr ON lr.claim_id = c.id AND lr.rn = 1
WHERE JSON_VALUE(c.payload, '$.is_synthetic') = 'true'
GROUP BY NVL(c.department, 'Unassigned');

CREATE OR REPLACE VIEW v_top_failed_rules AS
SELECT jt.rule_id AS rule_id,
       MAX(jt.rule_name) AS rule_name,
       COUNT(*) AS failures
FROM validation_runs vr
JOIN claims c ON c.id = vr.claim_id
CROSS APPLY JSON_TABLE(
    vr.counts_json, '$.failed_rules[*]'
    COLUMNS (
        rule_id VARCHAR2(64) PATH '$.rule_id',
        rule_name VARCHAR2(128) PATH '$.rule_name'
    )
) jt
WHERE JSON_VALUE(c.payload, '$.is_synthetic') = 'true'
GROUP BY jt.rule_id;

CREATE OR REPLACE VIEW v_rework_trend_weekly AS
SELECT TRUNC(c.created_at, 'IW') AS week_start,
       COUNT(*) AS claims,
       SUM(CASE WHEN EXISTS (
           SELECT 1 FROM claim_versions cv
           WHERE cv.claim_id = c.id AND cv.version > 1
       ) THEN 1 ELSE 0 END) AS reworked,
       ROUND(
           100 * SUM(CASE WHEN EXISTS (
               SELECT 1 FROM claim_versions cv
               WHERE cv.claim_id = c.id AND cv.version > 1
           ) THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1
       ) AS rework_rate
FROM claims c
WHERE JSON_VALUE(c.payload, '$.is_synthetic') = 'true'
GROUP BY TRUNC(c.created_at, 'IW');

CREATE OR REPLACE VIEW v_ledger_status AS
SELECT (SELECT COUNT(*) FROM audit_ledger) AS entries,
       (SELECT NVL(MAX(seq), 0) FROM audit_ledger) AS last_seq,
       (SELECT MAX(created_at) FROM anchors) AS last_anchor_at,
       (SELECT MAX(tx_hash) KEEP (DENSE_RANK LAST ORDER BY created_at, id) FROM anchors) AS last_anchor_tx,
       (SELECT COUNT(*) FROM audit_ledger l
        WHERE l.seq > NVL((SELECT MAX(a.to_seq) FROM anchors a), 0)) AS unanchored_entries
FROM dual;

CREATE OR REPLACE VIEW v_signoff_progress AS
SELECT NVL(c.department, 'Unassigned') AS department,
       SUM(CASE WHEN NVL(ds.status, 'pending') <> 'signed_off' THEN 1 ELSE 0 END) AS pending,
       SUM(CASE WHEN ds.status = 'signed_off' THEN 1 ELSE 0 END) AS signed_off
FROM claims c
LEFT JOIN department_signoffs ds ON ds.claim_id = c.id AND ds.department = c.department
WHERE JSON_VALUE(c.payload, '$.is_synthetic') = 'true'
GROUP BY NVL(c.department, 'Unassigned');

CREATE OR REPLACE VIEW v_management_kpis AS
SELECT (SELECT NVL(SUM(claim_count), 0) FROM v_claims_by_status) AS total_claims,
       (SELECT ROUND(100 * NVL(SUM(CASE WHEN status = 'Ready for Submission' THEN claim_count END), 0)
                       / NULLIF(SUM(claim_count), 0), 1)
        FROM v_claims_by_status) AS ready_percent,
       (SELECT ROUND(100 * NVL(SUM(reworked), 0) / NULLIF(SUM(claims), 0), 1)
        FROM v_rework_trend_weekly) AS rework_rate,
       ls.entries AS ledger_entries,
       ls.last_seq,
       ls.last_anchor_at,
       ls.last_anchor_tx,
       ls.unanchored_entries
FROM v_ledger_status ls;
