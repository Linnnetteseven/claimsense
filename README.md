# Hakiki

Hakiki ("verify" in Swahili) is a pre-submission checker for claims that Kenyan hospitals send to the Social Health Authority (SHA). A claims officer opens a draft claim, Hakiki scores it 0 to 100 with fixed rules, Gemini explains each failure in plain language, the officer fixes it in place, and once no errors remain Hakiki hands a validated SHA eClaims bundle back to the hospital's HIS for submission.

**The score is always deterministic. Gemini only explains; it never decides.**

Hakiki is a layer, not a replacement: the hospital's HIS stays the system of record and the hospital submits to SHA with its own credentials. Hakiki never contacts SHA on a hospital's behalf.

- Live: frontend <https://claimsense-frontend.vercel.app>, backend <https://claimsense-zeta.vercel.app>
- Repository name: `claimsense` (the product was renamed Hakiki)

## Why

Talking to claims officers at Kerugoya Level 5 Hospital showed that a claim goes through several reviews (manual, medical, payer) before payment, and that most delays come from avoidable data problems: wrong code sets, missing fields, totals that do not add up, services outside the claim period. Hakiki catches those before the claim leaves the hospital.

## How it works

```
Hospital HIS ──draft claim──► Hakiki ──certified bundle──► HIS "Ready for SHA" ──► SHA (AfyaLink)
                               │  1. rules score the claim                          │
                               │  2. Gemini explains, suggests fixes                │
                               │  3. officer fixes, re-validates                    │
                               └──────────◄── SHA's answer, forwarded by the HIS ◄──┘
```

1. **Check.** 25 rules from a versioned registry (`backend/validation/rules.py`) run against the claim. Each failed error costs 20 points, each warning 10.
2. **Explain and suggest.** Gemini writes plain-language explanations and fix steps. Where a fix can be found from real data, the card offers **Apply fix**: WHO's ICD-10 to ICD-11 map, SHA's intervention catalogue, earlier claims (patient SHA number, facility practitioner roster). Gemini can only choose from a validated shortlist; identifiers are never generated.
3. **Fix.** The officer edits fields inline or applies a suggestion; the claim is saved and every rule runs again.
4. **Hand off.** With no errors left (warnings reviewed), Hakiki builds the SHA eClaims FHIR bundle, checks its structure, stores it and delivers it to the HIS.
5. **Follow up.** The HIS forwards SHA's ClaimResponse; Hakiki shows SHA's state (approved, sent back, ...) and moves the claim between queue views: **To do**, **Ready**, **With SHA**, **Closed**.

### Components

| Part | Technology | Notes |
|---|---|---|
| Backend | FastAPI (Python 3.12), Vercel serverless | Entry point `backend/main.py`; routers in `backend/api/routers` |
| Frontend | React, Vite, Tailwind | Deployed on Vercel |
| Database | Supabase Postgres | Claims, validation runs, corrections, hand-offs; row level security on every table |
| AI | Gemini (`google-genai`) | Explanations and picks from validated shortlists only |
| Reference data | MOH OCL, WHO ICD-11 | Stored in `backend/data`, refreshed by scripts |
| Audit chain | Upstash Redis (optional) | Hash-chained log of validations |
| USSD / SMS | Africa's Talking | Claim status check by phone |

## Repository layout

```
backend/
  main.py                 FastAPI app (Vercel entry): middleware, error handlers, routers
  api/                    routers (claims, validation, fhir, terminology, health, ussd), models, errors
  services/               validation pipeline, claim lifecycle stages
  validation/             rule registry and scoring engine
  suggest/                fix suggestions (interventions, ICD-11, identifiers)
  llm/                    Gemini explainer and explanation cache
  fhir/                   SHA bundle builder, bundle checks, claim-state parser, SHA client
  terminology/            ICD-11 checks (offline WHO data, optional WHO API)
  his/                    hand-off to the hospital HIS
  repositories/           Supabase data access
  ussd/                   USSD session handler and SMS reports
  data/                   demo claims, SHA intervention catalogue, WHO ICD-11 files
  scripts/                reference data refresh, UAT validation, HL7 validator
  tests/                  pytest suite
frontend/src/             React app (components, hooks, constants, api client)
scripts/                  demo seed/reset scripts (Node; use the service role key)
supabase/migrations/      database migrations 001-005
```

## Local setup (Linux and macOS)

Prerequisites: Python 3.12, Node.js 20.6+, a Supabase project, optionally a Gemini API key.

```bash
git clone https://github.com/Linnnetteseven/claimsense.git
cd claimsense
```

**Database.** In the Supabase dashboard, open **SQL Editor** and run the files in `supabase/migrations/` in order, 001 to 005.

**Backend.**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest
cp .env.example .env          # fill in SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY at least
python -m pytest -q
uvicorn main:app --reload --port 8001
```

**Demo data** (from the repository root; reads `backend/.env`):

```bash
npm install
npm run demo:reset            # the 8 canonical demo claims
npm run demo:seed:bulk        # 200 generated claims (DEMO_COUNT to change)
```

**Frontend.**

```bash
cd frontend
npm install
cp .env.example .env          # VITE_API_URL=http://localhost:8001
npm run dev                   # http://localhost:5173
npm run lint && npm run build
```

Check the backend: `curl -s localhost:8001/health | python3 -m json.tool`.

**Windows.** Use `py -3.12 -m venv .venv` and `.venv\Scripts\Activate.ps1` instead of `source .venv/bin/activate`. The demo scripts use `node --env-file`, which works on Windows with Node 20.6+.

## Configuration

### Backend (`backend/.env`, Vercel project `claimsense`)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SUPABASE_URL` | yes | | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | | Service role (secret) key; backend only |
| `GEMINI_API_KEY` | no | | Enables AI explanations; without it rule advice is shown |
| `GEMINI_MODEL` | no | `gemini-3.5-flash-lite` | Explanation model |
| `GEMINI_FALLBACK_MODEL` | no | `gemini-3.1-flash-lite` | Tried once if the first model fails |
| `GEMINI_TIMEOUT_SECONDS` | no | `10` | Per call; the API minimum is 10 |
| `UPSTASH_REDIS_REST_URL` | no | | Audit chain and shared explanation cache |
| `UPSTASH_REDIS_REST_TOKEN` | no | | |
| `ICD_API_CLIENT_ID` | no | | WHO ICD API for live lookups (offline data is always used) |
| `ICD_API_CLIENT_SECRET` | no | | |
| `ICD_API_RELEASE` | no | `2026-01` | WHO release for live lookups |
| `SHA_FHIR_URL` | no | SHA UAT | SHA FHIR server (UAT validation, status stub) |
| `SHA_FHIR_TOKEN` | no | | |
| `SHA_FHIR_VERIFY_SSL` | no | `true` | |
| `SHA_FHIR_TIMEOUT` | no | `20` | Seconds |
| `SHA_TERMINOLOGY_BASE` | no | SHA UAT | Base for code system, identifier and profile URLs in bundles |
| `SHA_DIAGNOSIS_SYSTEM` | no | `icd11-codes-cs` | Diagnosis code system name |
| `SHA_BUNDLE_MESSAGE_HEADER` | no | `true` | `false` omits the MessageHeader, as in SHA's mediator example |
| `AFYALINK_URL`, `AFYALINK_USERNAME`, `AFYALINK_PASSWORD`, `AFYALINK_CONSUMER_KEY` | no | UAT URL | Reserved for registry lookups with a facility's credentials |
| `HIS_DELIVERY` | no | `store` | `store` (HIS pulls), `webhook`, or `openimis` |
| `HIS_WEBHOOK_URL`, `HIS_WEBHOOK_TOKEN` | for `webhook` | | Where hand-offs are posted, bearer token |
| `OPENIMIS_URL`, `OPENIMIS_TOKEN` | for `openimis` | | |
| `CORS_ORIGINS` | no | production frontend + localhost | Exact browser origins allowed |
| `CORS_ORIGIN_REGEX` | no | this team's Vercel previews | Pattern for preview frontends |
| `FRONTEND_URL` | no | `claimsense-frontend.vercel.app` | Shown in USSD screens and SMS |
| `USSD_ALLOWED_PHONES` | no | empty (open) | Registered officers' numbers, comma-separated E.164 |
| `AT_USERNAME`, `AT_API_KEY` | for SMS | `sandbox` | Africa's Talking |
| `DEMO_RESET_ENABLED` | no | `true` | Allows demo reset endpoints; set `false` outside demos |
| `DEBUG` | no | `true` | Debug logging |

`USE_SUPABASE` from earlier versions is gone: claims always come from Supabase.

### Frontend (`frontend/.env`, Vercel project `claimsense-frontend`)

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8001` | Backend URL. Built into the browser bundle, so it must never hold a secret; in Vercel use the Config (non-secret) type |

Vercel previews need `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` on the backend project, and a branch-specific `VITE_API_URL` on the frontend pointing at the backend preview.

## API

Errors always look like `{"error": {"code", "message", "details"}}`. Interactive docs: `/docs`.

| Method and path | Purpose |
|---|---|
| `GET /` | Liveness, no dependencies |
| `GET /health` | Supabase (required), Upstash, Gemini key, SHA UAT, openIMIS; 503 if the database is down |
| `GET /claims` | Claims with score preview and stage; `q`, `stage` (`todo`, `ready`, `with_sha`, `closed`), paging; stage counts |
| `POST /claims` | Create a claim (ID generated if missing) |
| `GET /claims/{id}` | One claim |
| `POST /claims/{id}/validate` | Rules, suggestions, explanations, FHIR ClaimResponse |
| `POST /validate` | Validate an unsaved claim |
| `POST /claims/{id}/correct?source=` | Save corrections, re-validate; `source` records typed vs applied suggestion |
| `GET /claims/{id}/history` | Validation runs and corrections |
| `GET /claims/{id}/bundle` | The SHA eClaims bundle and its structural checks |
| `POST /claims/{id}/handoff` | Certify and deliver to the HIS (`/submit` kept as alias) |
| `GET /claims/{id}/handoff` | Latest certified bundle (the HIS pulls from here) |
| `POST /claims/{id}/sha-response` | The HIS forwards SHA's ClaimResponse |
| `GET /terminology/icd11?q=` | ICD-11 search (ICD-10 codes return their WHO mapping) |
| `GET /terminology/interventions?q=&level=` | SHA intervention search by facility level |
| `GET /claims/{id}/audit`, `GET /audit/verify` | Upstash audit chain |
| `POST /claims/{id}/reset`, `POST /demo/reset` | Demo only (`DEMO_RESET_ENABLED`) |
| `POST /ussd` | Africa's Talking USSD callback |

## Validation rules

Every rule has an ID, version, severity, the fields that fix it, a source and a plain-language explanation (shown in the app as "Why SHA checks this"). Ruleset version `2026.09-v5`.

| Rule | Checks | Severity | Source |
|---|---|---|---|
| `MISSING_FIELDS` | SHA number, facility code, visit date, diagnosis present | Error | AfyaLink claim integration guide |
| `INVALID_ICD11` | Diagnosis is a real ICD-11 MMS code (format, WHO 2026-01 release, postcoordination); ICD-10 codes get the WHO mapping as a fix | Error | AfyaLink guide; [WHO ICD-11](https://icd.who.int/browse/2026-01/mms/en) |
| `VISIT_DATE` | Visit date valid and not in the future | Error | Hakiki |
| `EMPTY_ITEMS` | At least one item; every item has an intervention code | Error | AfyaLink guide |
| `SHA_SERVICE_CODE_FORMAT` | Codes are billable interventions (`SHA-12-001`), not chapters | Error | [DHA eClaims FHIR guide](https://build.fhir.org/ig/IntelliSOFT-Consulting/Kenya-eClaims-FHIR-IG/CodeSystem-KenyaSocialHealthAuthorityInterventionCS.html) |
| `SERVICED_PERIOD_PRESENT` | Every item has service start and end dates | Error | AfyaLink guide |
| `SERVICED_PERIOD_IN_BILLABLE` | Service dates inside the claim period (dates only) | Error | AfyaLink guide |
| `ITEM_SEQUENCE_VALID` | Sequences 1..n, no gaps or repeats (repeated codes allowed) | Error | AfyaLink guide |
| `TOTAL_EQUALS_NET_SUM` | Claim total equals the sum of item amounts exactly | Error | AfyaLink guide |
| `PHC_ZERO_TOTAL` | PHC fund claims total zero | Error | AfyaLink guide |
| `FHIR_BUNDLE_VALID` | Bundle references resolve; care team names a practitioner | Error | AfyaLink guide; [DHA eClaims FHIR guide](https://build.fhir.org/ig/IntelliSOFT-Consulting/Kenya-eClaims-FHIR-IG/StructureDefinition-ke-eclaims-claimsubmission.html) |
| `INTERVENTION_ELIGIBILITY` | Patient sex and age within the intervention's limits | Error | SHA benefits catalogue (MOH OCL) |
| `INTERVENTION_FACILITY_LEVEL` | Intervention billable at the facility's level | Error | SHA benefits catalogue |
| `COVERAGE_EXPIRED` | Cover active on the visit date | Error | Hakiki |
| `MISSING_PARTOGRAPH` | Deliveries link a partograph record | Error | Facility SOP |
| `MISSING_POSTOP_NOTES` | Overnight surgery has post-op notes | Error | Facility SOP |
| `ITEM_QUANTITY_VALID` | Quantities positive | Warning | Hakiki |
| `INTERVENTION_KNOWN` | Code active in SHA's catalogue | Warning | SHA benefits catalogue |
| `INTERVENTION_DIAGNOSIS_MATCH` | Diagnosis on SHA's list for the intervention | Warning | SHA benefits catalogue |
| `INTERVENTION_ACCESS_POINT` | Outpatient-only / inpatient-only codes match the setting | Warning | SHA benefits catalogue |
| `CAPITATION_PAYMENT` | Capitated codes not priced outside PHC | Warning | SHA benefits catalogue |
| `PREAUTH_REQUIRED` | Pre-authorization reference where SHA requires one | Warning | SHA benefits catalogue |
| `TARIFF_CEILING` | Unit price within the tariff for the code and level | Warning | SHA benefits catalogue |
| `AMOUNT_HIGH` | Large totals flagged for supporting documents | Warning | Hakiki |
| `IMPLAUSIBLE_FREQUENCY` | Dialysis sessions per week plausible | Warning | Facility SOP |

Scores: 85-100 Ready for submission, 60-84 Needs review, 0-59 High risk. A claim can be handed off only with no errors; warnings must be marked reviewed.

The AfyaLink guide (`afyalink.dha.go.ke/claim-integration`) and the MOH OCL catalogue do not open as readable public pages, so they are named rather than linked.

### Reference data

| File | Source | Refresh |
|---|---|---|
| `backend/data/sha_interventions.csv` | MOH-Kenya OCL `BenefitsAndInterventions` (1216 active billable codes, pre-auth flags, level tariffs, diagnosis links, sex/age limits) | `python backend/scripts/fetch_sha_interventions.py` |
| `backend/data/icd11_mms.tsv` | WHO ICD-11 MMS release 2026-01 (17,255 codes) | `python backend/scripts/fetch_icd_mappings.py` |
| `backend/data/icd10_to_icd11.tsv` | WHO one-category ICD-10 to ICD-11 map | same script |

OCL records tariffs for only a few interventions; where it has none, one labelled sample value (haemodialysis, secondary source) is used. OCL's diagnosis lists contain typos (letter O for zero); Hakiki reads them tolerantly and treats diagnosis matching as a warning.

## SHA alignment

- **Bundle** (`backend/fhir/kenya_bundle_builder.py`): message Bundle with MessageHeader, `fullUrl` on every entry and references to them; Claim, Patient, Coverage, provider and SHA Organization, Practitioner; items with sequence, service period, category, net and SHA codes (display = SHA's name); ICD-11 diagnosis; patient-invoice extension. System URLs follow the DHA eClaims IG under `SHA_TERMINOLOGY_BASE`.
- **Checked against SHA UAT:** all 8 demo bundles pass `$validate` on `nshr-uat.sha.go.ke` with no errors (`python backend/scripts/uat_validate.py`). UAT does not host the eClaims profiles, so profile validation needs the HL7 validator (`backend/scripts/validate_bundle.sh`, Java 11+).
- **Claim states:** SHA's ClaimResponse states from the AfyaLink guide and the eClaims IG are both mapped to Hakiki's workflow (`backend/fhir/claim_state.py`).

## Hand-off to the hospital HIS

Hakiki stores every certified bundle with its score, ruleset version and reviewed warnings (`claim_handoffs`), marks the claim handed off, and delivers per `HIS_DELIVERY`: `store` (the HIS pulls `GET /claims/{id}/handoff`), `webhook` (POST to the HIS with a bearer token) or `openimis`. Any later edit returns the claim to draft. The HIS forwards SHA's answer to `POST /claims/{id}/sha-response`.

## Responsible AI

- **Gemini explains; it never scores.** Scores come only from the rule registry. Applying a suggestion re-runs the rules, so a suggestion cannot raise a score by itself.
- **Grounded suggestions.** Gemini picks codes only from shortlists Hakiki has validated (SHA catalogue, WHO ICD-11); anything else is discarded. ICD-10 mappings come from WHO's table, not the model.
- **No invented identifiers.** SHA numbers and practitioner numbers are suggested only from real records (earlier claims, facility roster); otherwise the officer is told where to find them.
- **No patient identifiers sent to Gemini.** Prompts carry rule results and non-identifying clinical context: no names, SHA numbers, practitioner numbers, dates of birth or claim IDs. A test fails if any appear.
- **Visible provenance.** Every suggestion shows its source; AI picks say "check before applying". `ai_explanations_used` reports whether Gemini answered.
- **Fallback.** If Gemini is unavailable (timeout 10 s, one retry on a second model), the rule's own advice is shown and the flag is false. Explanations are cached by rule and message.

## Data protection

Hakiki processes patient health data for the hospital (Kenya Data Protection Act 2019, Digital Health Act 2023). In place:

- Row level security on every table; only the backend's service role reads or writes. The public key is refused.
- Service role and API keys stay on the server; the frontend holds only the API URL.
- The queue masks SHA numbers (last 4 characters); USSD screens and SMS carry no patient names; phone numbers are masked in logs; USSD can be limited to registered numbers.
- An audit record of every validation, every changed field (typed or from which suggestion) and every hand-off.
- CORS allows only Hakiki's own frontends.

Not yet in place (see Known limitations): user authentication, and hosting in Kenya.

## Known limitations

- **No authentication or roles.** The API is open to anyone with its URL. This must be built before real patient data.
- **Data location.** The demo database is in Supabase eu-west-1 (Ireland); health data may need to stay in Kenya.
- **SHA submission is not tested.** Bundles pass SHA UAT `$validate`, but no bundle has been submitted through AfyaLink (it needs facility credentials). The MessageHeader choice and claim subtype codes (`outpatient` vs `op`) need confirming there.
- **Tariffs are incomplete.** OCL has tariffs for few codes; one sample tariff is used.
- **Registry lookups use earlier claims only.** AfyaLink client and health worker registries are not connected.
- **Demo features.** The document scan panel is a simulation; demo reset endpoints are on by default.
- `claim_status()` in `backend/fhir/sha_client.py` is a stub; the SHA status endpoint is unconfirmed.

## Roadmap

- Authentication (SSO) and roles for officers, reviewers and administrators
- Real SHA production submission through the hospital's AfyaLink access
- Registry lookups (client registry, health worker registry, facility registry)
- Background job queue for bulk validation and delivery retries
- Docker / on-premise packaging for hospitals that host locally
- Facility analytics on recurring errors and SHA outcomes

See `CHANGELOG.md` for what changed in v2.

## Origin

Hakiki started at the openIMIS Hackathon, Track 3 (Claims Management).
