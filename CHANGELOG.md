# Changelog

## v2.0.0 (unreleased): SHA eClaims alignment

Branch `feat/v2-sha-alignment`. Merges the `main` and `demo/supabase-gemini` lines and aligns Hakiki with SHA's current claim rules and FHIR format. Ruleset `2026.09-v5`.

### Validation
- Rule registry: every rule has an ID, version, severity, fix fields, source and a plain-language explanation. 25 rules (16 errors, 9 warnings).
- ICD-11 replaces ICD-10 (`INVALID_ICD11`): format and postcoordination checks, offline check against WHO release 2026-01, optional live WHO API lookup. ICD-10 codes get WHO's mapped ICD-11 code as a one-click fix.
- New SHA rules: intervention code format, service periods present and inside the claim period, item sequence, exact total (replaces the 5% tolerance), PHC zero total, bundle integrity, pre-authorization, tariff ceiling.
- Catalogue rules from the MOH OCL SHA benefits catalogue: sex/age eligibility, facility level, active code, diagnosis link, inpatient/outpatient setting, capitation.
- Reference data: `sha_interventions.csv` (1216 codes from MOH OCL), WHO ICD-11 code list and ICD-10 map, with refresh scripts.
- Demo and bulk claims rewritten to follow SHA's catalogue; one deliberately broken claim kept.

### Guided fixes
- Apply fix for computable corrections (totals, sequences, service dates), WHO-mapped ICD-11 codes, and intervention codes from a shortlist valid for the claim (Gemini may pick; picks outside the list are ignored).
- Missing SHA numbers and practitioner numbers are suggested only from real records (earlier claims, facility roster); identifiers are never generated.
- Pick lists for choices only the officer can make (which practitioner; PHC or not).
- Every failing rule is editable inline, including a line-item editor.

### FHIR and SHA
- Kenya eClaims bundle rebuilt to the DHA IG: message Bundle, fullUrls, Practitioner and care team, Coverage, service periods, SHA code system URLs (`SHA_TERMINOLOGY_BASE`).
- All demo bundles pass SHA UAT `$validate` with no errors (`backend/scripts/uat_validate.py`).
- Bundle structure checks before any hand-off; claim-state parsing for SHA ClaimResponses.

### Workflow
- Hand-off to the hospital HIS replaces direct submission: certified bundle stored and delivered (`store`, `webhook`, `openimis`). Hakiki never submits to SHA.
- SHA responses forwarded by the HIS show as a state badge.
- Queue views by lifecycle: To do, Ready, With SHA, Closed (closed claims read-only).
- Demo reset restores seeded claims with dates re-resolved to today.

### Gemini
- Structured output (Pydantic schema), model from `GEMINI_MODEL` with one retry on a fallback model, 10 s timeout, explanation cache.
- No patient identifiers in prompts (enforced by a test). Warnings are explained too, with concrete fix steps.

### Data and security
- Supabase: row level security on every table, validation run and correction history (with the source of each change), hand-off records, SHA responses.
- CORS limited to Hakiki's frontends; USSD reads the database, shows no patient names and can be limited to registered numbers; phone numbers masked in logs.
- Demo seed scripts moved out of `frontend/` to `scripts/` so nothing near the browser bundle touches the service role key.

### Backend structure
- Routers (health, claims, validation, fhir, terminology, ussd), Pydantic models, one error shape, `/health` dependency checks.
- Routes run in a thread pool with a shared Supabase client and short timeouts, so one slow dependency no longer stalls the server.

### Frontend
- Code search for ICD-11 and SHA interventions; "Show in claim"; "Why SHA checks this" explanations; real claim details and items; keyboard shortcuts (`/`, Ctrl/Cmd+Enter, Esc); masked SHA numbers; WCAG AA contrast in both themes.

### Removed
- `USE_SUPABASE` (claims always come from Supabase), the in-memory `MOCK_CLAIMS`, the unused `backend/data/supabase_claim_repository.py`, the frontend's fake fallback data, and `backend/test_upstash.py`.

### Known limitations
- No authentication yet; demo database hosted outside Kenya; SHA submission through AfyaLink not tested; tariffs incomplete. See README.
