-- EXPERIMENTAL Oracle Select AI setup for Hakiki aggregate analytics.
-- Do not use the HAKIKI_APP account for this endpoint: it owns the base tables.
-- Apply backend/db/views.sql first, as HAKIKI_APP.

-- Step 1: connect as the Autonomous Database ADMIN user and create a separate
-- reader account. Replace the password placeholder in your SQL worksheet only;
-- do not save the real password in this file or Git.
CREATE USER HAKIKI_ANALYTICS IDENTIFIED BY "REPLACE_WITH_STRONG_PASSWORD";
GRANT CREATE SESSION TO HAKIKI_ANALYTICS;
GRANT SELECT ON HAKIKI_APP.v_claims_by_status TO HAKIKI_ANALYTICS;
GRANT SELECT ON HAKIKI_APP.v_score_by_department TO HAKIKI_ANALYTICS;
GRANT SELECT ON HAKIKI_APP.v_top_failed_rules TO HAKIKI_ANALYTICS;
GRANT SELECT ON HAKIKI_APP.v_rework_trend_weekly TO HAKIKI_ANALYTICS;
GRANT SELECT ON HAKIKI_APP.v_ledger_status TO HAKIKI_ANALYTICS;
GRANT SELECT ON HAKIKI_APP.v_signoff_progress TO HAKIKI_ANALYTICS;
GRANT SELECT ON HAKIKI_APP.v_management_kpis TO HAKIKI_ANALYTICS;
GRANT EXECUTE ON DBMS_CLOUD_AI TO HAKIKI_ANALYTICS;

-- Step 2: configure an Oracle Select AI provider credential according to the
-- provider you choose, then connect as HAKIKI_ANALYTICS and create this profile.
-- Replace the provider, credential, model, and compartment placeholders.
-- object_list + enforce_object_list limit generated SQL metadata to these views;
-- the HAKIKI_ANALYTICS account has SELECT grants on those views only.
BEGIN
  DBMS_CLOUD_AI.CREATE_PROFILE(
    profile_name => 'HAKIKI_ANALYTICS_READONLY',
    attributes => '{
      "provider": "oci",
      "credential_name": "REPLACE_WITH_SELECT_AI_CREDENTIAL",
      "oci_compartment_id": "REPLACE_WITH_COMPARTMENT_OCID",
      "model": "REPLACE_WITH_SUPPORTED_MODEL",
      "object_list": [
        {"owner": "HAKIKI_APP", "name": "V_CLAIMS_BY_STATUS"},
        {"owner": "HAKIKI_APP", "name": "V_SCORE_BY_DEPARTMENT"},
        {"owner": "HAKIKI_APP", "name": "V_TOP_FAILED_RULES"},
        {"owner": "HAKIKI_APP", "name": "V_REWORK_TREND_WEEKLY"},
        {"owner": "HAKIKI_APP", "name": "V_LEDGER_STATUS"},
        {"owner": "HAKIKI_APP", "name": "V_SIGNOFF_PROGRESS"},
        {"owner": "HAKIKI_APP", "name": "V_MANAGEMENT_KPIS"}
      ],
      "enforce_object_list": true,
      "additional_instructions": "Use aggregate analytics views only. Never request patient-level rows or identifiers."
    }',
    status => 'enabled',
    description => 'Experimental Hakiki aggregate analytics only'
  );
END;
/

-- Test this profile as HAKIKI_ANALYTICS before setting ENABLE_SELECT_AI=true:
-- SELECT DBMS_CLOUD_AI.GENERATE(
--   prompt => 'Show average score by department',
--   profile_name => 'HAKIKI_ANALYTICS_READONLY',
--   action => 'showsql') FROM dual;
