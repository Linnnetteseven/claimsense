# 🩺 Hakiki
"Grammarly for hospital claims."

## *Department-led claim readiness for healthcare facilities*

### Demo roles and department workflow

`DEPARTMENTS_ENABLED` defaults to `true`. With department mode enabled, the demo role selector offers Outpatient, Renal, and Maternity claims desks plus Manager. Desk views filter the queue to their own department; the Manager view contains the aggregate Management Overview only. These are presentation controls, not authentication or production access control. With `DEPARTMENTS_ENABLED=false`, the Department Workspace and department-review API are disabled, and the demo roles become Claims officer and Manager. Core checks and claim-type checks continue to run.

The current validation-to-desk mapping is:

| Rule | Desk / claim type | Trigger |
| --- | --- | --- |
| `MISSING_PARTOGRAPH` | Maternity claims desk | Maternity department or diagnosis O80/O82, with delivery/labour indicators; checks `partograph_id`. |
| `IMPLAUSIBLE_FREQUENCY` | Renal claims desk | Renal department and `sessions_this_week > 3`; warning only, an internal review flag rather than a SHA limit. |
| `MISSING_POSTOP_NOTES` | Surgical claim type | Surgical department, `overnight_stay=true`, and empty `postop_notes_attached`; there is no Surgical demo desk role. |

Outpatient has no department-specific automated rule. Lab and pharmacy are shown as read-only supporting-item status in the desk workspace, not as separate roles. Every checklist is a **draft to be confirmed with the desk officers** before a facility pilot.


> **"Helping healthcare providers submit better claims before they become reimbursement delays."**

Hakiki is a claims-preparation prototype for hospital departments. It demonstrates deterministic pre-submission checks, Gemini-assisted explanations, department-owned claim workspaces, and FHIR response generation. It includes a mock mode; a live HIS/openIMIS connection requires configuration and an approved integration path.

Hakiki is intended to complement hospital systems rather than replace them. It helps staff identify inconsistencies, explain flagged items, and prepare a claim for the facility's submission workflow. It does not guarantee acceptance or payment.

The name **Hakiki**, meaning **"verify"** or **"confirm"** in Swahili, reflects our mission: ensuring that every claim is as accurate, complete, and reimbursement-ready as possible before entering the payer review process.

---

# 🌍 Why Hakiki?

Healthcare financing is one of the most critical components of modern healthcare systems. Hospitals rely on timely reimbursement to sustain clinical services, procure supplies, maintain infrastructure, and continue delivering quality patient care. Yet the healthcare claims lifecycle remains highly administrative, requiring extensive verification and multiple levels of review before reimbursement can be approved.

Through discussions with claims officers at **Kerugoya Level 5 Hospital**, our team observed that a healthcare claim is far more than filling out a form and clicking **Submit**. Every claim progresses through multiple stages of review—including **Manual Review**, **Medical Review**, and **Payer Review**—before reimbursement.

Initially, we believed that claim rejection was the primary challenge. However, conversations with healthcare financing professionals and further research revealed that rejection is only one symptom of a broader operational problem.

Healthcare facilities face:

- ⏳ Lengthy claims adjudication workflows
- 🔍 Extensive manual verification
- 📄 Inconsistent documentation quality
- 💰 Reimbursement delays affecting operational cash flow
- 🧾 High administrative workload for claims teams
- 📊 Limited feedback mechanisms that help facilities improve future claims

These challenges increase operational costs, consume valuable staff time, delay reimbursements, and ultimately reduce the efficiency of healthcare financing systems.

Hakiki was built to address these challenges **before they occur**.

---

# 💡 Our Solution

Hakiki introduces an intelligent **pre-submission validation layer** that supports healthcare workers during claim preparation.

Instead of discovering issues after a claim has entered the reimbursement workflow, Hakiki helps identify and resolve them **before submission**.

The platform combines **deterministic healthcare validation rules** with **Large Language Models (LLMs)** to provide explainable, human-centered decision support.

Hakiki enables healthcare providers to:

- ✅ Validate healthcare claims against predefined financing and compliance rules.
- 🔎 Detect missing or inconsistent information before submission.
- 💬 Explain validation findings in clear, non-technical language.
- 🛠️ Recommend practical corrective actions for claims officers.
- 📈 Generate a transparent **Claim Readiness Score** that reflects overall submission quality.
- 📊 Produce operational insights that help healthcare facilities continuously improve claim quality over time.

Importantly, Hakiki **does not replace healthcare professionals or existing health information systems.**

It augments them.

Final decisions always remain with the claims officer.

---

# 🎯 Our Vision

Our long-term vision is to make Hakiki the intelligence layer connecting **clinical operations** with **healthcare financing**.

Starting with intelligent claims validation, Hakiki is designed to evolve into a proactive assistant capable of supporting healthcare providers throughout the entire claims lifecycle by improving documentation quality, reducing administrative burden, identifying recurring workflow challenges, and providing continuous operational insights.

Built with **interoperability** in mind, Hakiki is designed to integrate with **Hospital Information Systems (HIS)** and healthcare financing platforms through secure APIs and healthcare interoperability standards such as **FHIR (Fast Healthcare Interoperability Resources)**, enabling adoption across diverse healthcare environments.

As healthcare systems continue to digitize, Hakiki aims to become a trusted AI companion that helps hospitals submit higher-quality claims, accelerate reimbursement, and strengthen healthcare financing across Kenya and beyond.

---

# 🤝 Our Philosophy

Healthcare professionals should spend their time delivering care—not navigating avoidable administrative complexity.

We believe Artificial Intelligence should **enhance human expertise, not replace it**.

Hakiki exists to make healthcare financing more accurate, transparent, efficient, and sustainable by empowering the healthcare professionals responsible for it.

---

## 🛠️ Architecture & System Flow

Hakiki here is a **rule-based engine**, not a black-box classifier. Every score is traceable to a specific, named rule — auditable by design, and with no confusion matrix to defend to a room full of clinicians.

```
[ React Dashboard ]
        │
        ▼ (Select / edit a claim)
[ FastAPI Validation Engine ] ──► [ 10 Deterministic Rules ]
        │                                   │
        │                                   ▼ (score + pass/fail per rule)
        │                         [ Gemini API — Plain-English Explainer ]
        ▼                                   │
[ Score Gauge · Error Cards · Corrections ] ◄┘
        │
        ▼ (All errors resolved)
[ FHIR R4 ClaimResponse ] ──► [ openIMIS Core ]
```

### The step-by-step flow

1. **Draft / fetch** — The dashboard loads a claim, either from mock data or a live openIMIS FHIR `Claim` bundle.
2. **Rule pass** — Ten deterministic rules run: seven core checks (required fields, diagnosis-code format, visit date, items/service codes, coverage window, amount-vs-items match, and amount reasonableness) plus three department-specific checks (maternity partograph, renal session frequency, and surgical post-op notes).
3. **Score** — Each failed rule deducts points (errors −20, warnings −10) off a base of 100, producing a color-coded status: 🟢 Ready · 🟡 Needs Review · 🔴 High Risk.
4. **Explain** — Every error is batched into a single Gemini API call that returns a short, non-technical explanation and fix suggestion per rule.
5. **Correct & re-validate** — The clerk saves edits as a new claim version; Hakiki fingerprints that version and reruns checks against the saved data.
6. **Submit** — Once all *errors* (not warnings) clear, a FHIR R4 `ClaimResponse` is built and POSTed to openIMIS — or held in mock mode until credentials are live.

---

## 📁 Project Structure

```
claimsense/
├── .env
├── .gitignore
├── backend/
│   ├── main.py                   ← FastAPI app, all routes
│   ├── config.py                 ← env var loader (mock vs. live mode)
│   ├── requirements.txt
│   ├── data/
│   │   └── mock_claims.py        ← 5 realistic SHA claims
│   ├── validation/
│   │   ├── rules.py               ← 10 rule functions (7 core + 3 department-specific)
│   │   └── engine.py              ← runs rules, computes score
│   ├── fhir/
│   │   ├── client.py              ← openIMIS FHIR HTTP client
│   │   └── builder.py             ← builds ClaimResponse resource
│   ├── llm/
│   │   └── explainer.py           ← Gemini plain-English explanations
│   └── tests/
│       └── test_validation.py
└── frontend/
    ├── package.json
    └── src/
        ├── App.jsx
        ├── api/client.js
        └── components/
            ├── ClaimList.jsx
            ├── ValidationPanel.jsx
            ├── ScoreGauge.jsx
            ├── ErrorCard.jsx
            └── StatusBadge.jsx
```

---

## ⚡ Getting Started

### Prerequisites

- Python 3.10+
- Node.js v18+
- An Gemini API key (for plain-English explanations — optional, falls back gracefully)
- Access to a local openIMIS Docker stack (optional — the app runs entirely on mock data without it)

### Installation & Local Setup

**1. Clone and enter the project**

```bash
git clone https://github.com/Linnnetteseven/claimsense.git
cd claimsense
```

**2. Configure environment variables**

Create a `.env` file at the project root:

```env
OPENIMIS_URL=https://localhost
OPENIMIS_TOKEN=            # leave blank to run on mock data
GEMINI_API_KEY=your_key_here
DEBUG=true
```

**3. Set up the backend**

```bash
cd backend
python3 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest tests/ -v    # 34 tests should pass
uvicorn main:app --reload --port 8001
```

**4. Set up the frontend**

```bash
cd frontend
npm install
npm run dev
```

**5. Verify the services**

| Service | URL |
|---|---|
| Validation API | `http://localhost:8001` |
| Dashboard UI | `http://localhost:5173` |

```bash
curl http://localhost:8001/
# {"service": "ClaimSense", "status": "running", "mode": "mock", ...}
```

---

## 🧠 The Validation Engine

Hakiki scores claims using **ten transparent, deterministic rules** (seven core checks plus three department-specific checks) — no training data, no drift, no model to retrain when SHA policy changes. Just code you can read in five minutes.

| Rule | Checks | Severity |
|---|---|---|
| Required Fields | Patient ID, facility code, visit date, diagnosis code present | 🔴 Error |
| Diagnosis Format | Diagnosis code matches configured ICD-10/ICD-11 shape; this is not a code-set lookup | 🔴 Error |
| Visit Date | Not malformed, not in the future | 🔴 Error |
| Items Present | At least one item with a valid service code and quantity | 🔴 Error |
| Coverage Active | Patient's SHA coverage hadn't expired on the visit date | 🔴 Error |
| Amount Match | Claimed total within 5% of the line-item sum | 🟡 Warning |
| Amount Reasonable | Claimed total under facility/maternity thresholds | 🟡 Warning |

Scores translate into three tiers:

- 🟢 **85–100 — Ready for Submission**
- 🟡 **60–84 — Needs Review**
- 🔴 **0–59 — High Risk, Errors Found**

---

## 🏥 Department-owned claim processing

The demo assigns each claim to an owning department, where that department's staff process it:

- Department checklists support required/optional steps, evidence references, progress, and processing sign-off.
- The department selector filters the queue in the frontend. It is not login security or permission enforcement.
- Claims staff can record submitted, queried, rejected, resubmitted, paid, or other outcomes and categorize query/rejection themes.
- Outcome summaries show recurring themes across records available in the current browser.

With the default `DB_BACKEND=redis` mode, checklist and outcome details continue to use browser local storage, preserving the current demo workflow. In `DB_BACKEND=oracle` mode, they are loaded from and saved to Oracle; local storage remains an offline fallback and a cache. Department login and server-enforced access rules are not implemented. Department actions send a fingerprint and limited action metadata to the backend audit ledger; the typed reviewer name is not a verified login identity. See [PILOT_ROADMAP.md](PILOT_ROADMAP.md) for the phased plan.

### Claim lifecycle fingerprints

On first intake, Hakiki fingerprints the claim version and records a `claim_received` event. A saved correction records a new version fingerprint and changed field names, then reruns validation against the corrected data. Automated validations, an explicit claims officer review, department checklist actions/sign-off changes, and submission attempts are also hash-linked ledger events. The Audit Trail compares the current server-side claim with its latest version fingerprint and shows whether that version falls inside a batch verified on Avalanche Fuji. In Redis mode, older claim bodies are not retained as version snapshots; Oracle mode retains append-only snapshots in `claim_versions`.

Claim data and department evidence are never written to the blockchain. With the default Redis mode, the legacy Upstash ledger stores claim IDs and workflow metadata; without Upstash it is process-local. Oracle mode stores claim bodies and append-only versions in `claims` and `claim_versions`, and stores only random claim references, event types, payload hashes, and chain hashes in `audit_ledger`. Oracle mode is synthetic-demo-only in this build; live openIMIS ingestion is rejected. Do not connect real patient data. Historical anchors from the old Redis chain are preserved as legacy references during migration, but the Oracle chain is privacy-safe and must be anchored again to create Oracle-chain checkpoints. New Oracle ledger entries use hash version 4: the exact canonical hash input is saved in `audit_event_details` with the event so verification does not have to reconstruct it from Oracle-formatted columns. Older v2/v3 records remain verifiable with their original algorithms.

### Oracle Autonomous Database (optional)

The default remains Redis/in-process behavior. Set `DB_BACKEND=oracle` only when you deliberately want claims, claim versions, validation runs, department checklist/sign-off state, outcomes, and the privacy-safe audit ledger in Oracle Autonomous Database. `DB_BACKEND=oracle_with_fallback` uses Oracle while available and switches to the existing Redis behavior after an Oracle failure; fallback writes can split across stores, so use it for demos rather than as a consistency guarantee.

1. Create an application database user in Autonomous Database. Choose either walletless TLS or wallet-based mTLS. Walletless TLS avoids wallet download, but TLS must be enabled on the database and your client IP must be permitted by its network access rules. Oracle documents both Python connection options [here](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/connecting-python.html).
2. Apply [backend/db/schema.sql](backend/db/schema.sql) once in APEX SQL Workshop or SQL Developer using the application schema user.
3. Set `DB_BACKEND=oracle` and fill `ORACLE_USER`, `ORACLE_PASSWORD`, and `ORACLE_DSN` in the repo-root `.env`. For **walletless TLS**, enable TLS for the Autonomous Database, then copy the TLS connection string from its Database Connection page into `ORACLE_DSN`; leave `ORACLE_WALLET_DIR` and `ORACLE_WALLET_PASSWORD` blank. For **wallet mTLS**, use the wallet's TNS alias for `ORACLE_DSN`, set `ORACLE_WALLET_DIR` to its extracted folder, and set `ORACLE_WALLET_PASSWORD`. Never commit `.env` or wallet files.
4. Install the backend requirements and start FastAPI as usual. Check `GET /health/db`; it reports `connection_mode` as `walletless_tls`, `wallet_mtls`, or `redis`, alongside connectivity, and never returns credentials.

For an existing Oracle schema that already has the anchors status migration, apply [`scripts/migrate_audit_verification_checkpoint.sql`](scripts/migrate_audit_verification_checkpoint.sql) once. Then open a claim's Audit tab and run **Verify full ledger**. That stores the verified sequence and hash; later anchor requests verify only the suffix after that checkpoint. The full verification is manual and may take time on a remote database. The app never sends an Avalanche transaction during that verification.

Example from PowerShell at the repository root:

```powershell
.\backend\venv\Scripts\Activate.ps1
cd backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8001
```

The app seeds the existing synthetic mock claims into an empty Oracle claims table on the first `GET /claims`. Corrections are saved as new versions in the same transaction as their audit event. Department checklist state and outcome records use the Oracle endpoints; if the API is unavailable, the frontend keeps the existing local browser copy.

#### Migrate the Upstash ledger once

With a verified, non-empty Upstash ledger and a clean Oracle schema, set the Redis and Oracle variables from `.env`, set `DB_BACKEND=oracle`, and run from the repository root:

```powershell
python scripts/migrate_redis_to_oracle.py
```

The script verifies Redis before writing, refuses a non-empty Oracle target, re-chains entries using payload digests and random references, then verifies the copied chain. It does not delete or modify Redis. Since the old chain hashed full event payloads (including claim IDs), the Oracle chain has different hashes; old Avalanche anchors are retained in `legacy_anchors` for reference and do not verify the new chain. After migration, manually anchor the Oracle chain again. Only seeded synthetic claims are migrated into the claims tables; old in-memory corrections and claims cannot be recovered after their backend process has exited.

The Oracle feature has no authentication or departmental authorization yet and is not suitable for real patient data or a live hospital pilot. Keep demo inputs synthetic, restrict database network access, and use a least-privilege application user rather than the Autonomous Database ADMIN account. Walletless TLS still uses encrypted TLS and database username/password credentials, but requires TLS to be enabled and the caller's IP to be allowed by the database ACL.

#### Synthetic workload and Management Overview

The optional seeder creates 250 deterministic, visibly synthetic claim records for **Kerugoya County Referral Hospital (SYNTHETIC DEMO)**, dated across the prior 12 weeks. Its final validation groups target 55% Ready, 30% Needs Review, and 15% High Risk; about one-third have an earlier, lower-scoring validation followed by a correction and improved revalidation. These are workflow examples, not SHA rules or real facility data. It writes through the normal repository and ledger functions and verifies the audit chain at the end. It refuses Redis mode.

Apply `backend/db/schema.sql` and then `backend/db/views.sql` as `HAKIKI_APP`. The views in `views.sql` are the shared source for the Management Overview metrics. To seed or reset synthetic rows, use the backend virtual environment from the repo root:

```powershell
$env:DB_BACKEND = "oracle"
backend\venv\Scripts\python.exe scripts/seed_synthetic_claims.py --count 250
backend\venv\Scripts\python.exe scripts/seed_synthetic_claims.py --count 250 --reset
```

Run these from the repository root; if your shell is already there, use `backend\venv\Scripts\python.exe` instead. `--reset` removes synthetic claim/version/run/sign-off/outcome rows only. Append-only ledger events and anchors are retained, so seeding again adds a new history rather than erasing the audit record. Do not run the seeder against a database containing real claims. The Management Overview tab is read-only and shows a Redis-mode explanation when Oracle is not selected.

#### Evidence packs

The Audit Trail can export a minimized JSON pack and PDF summary for synthetic-reference claims only. `EVIDENCE_STORAGE=local` is the default; files go under `EVIDENCE_DIR` (default `./evidence_packs/`), which is ignored by Git. The pack contains versions/fingerprints, validation summaries, department sign-off status, hash-chain entries, and any related anchor transaction references; it excludes the claim body and staff note text. OCI object upload is not enabled in this build, so `EVIDENCE_STORAGE=oci` safely falls back to local storage with a response message. Do not publish generated packs unless you have reviewed their contents and destination.

#### Experimental Oracle Select AI

`POST /analytics/ask` is disabled unless `ENABLE_SELECT_AI=true`. It requires an Autonomous Database Select AI provider credential/profile and a separate `HAKIKI_ANALYTICS` database account. Apply `backend/db/views.sql` first, then follow the ordered steps/comments in `scripts/select_ai_setup.sql`: an administrator creates the reader and grants SELECT only on the aggregate views; the reader configures the Select AI profile with an explicit view `object_list`. Set `ORACLE_SELECT_AI_USER`, `ORACLE_SELECT_AI_PASSWORD`, and the regular Oracle DSN/wallet settings for the service. The endpoint asks Oracle for SQL, rejects non-SELECT or unapproved relations, and executes as the view-only reader; it does not run as `HAKIKI_APP`. Keep it disabled if the provider/profile is unavailable. Provider credentials and supported models depend on the OCI setup, and Select AI may not be available on the Autonomous Database Free tier. No live provider call is part of local tests.

### Showcase deployment

The frontend and FastAPI backend should be deployed as separate Vercel projects for a quick preview. The frontend project uses `frontend` as its root, `npm run build` as its build command, and `dist` as its output directory. Set `VITE_API_URL` to the public backend URL. The backend project uses `backend` as its root (the existing `backend/vercel.json` routes requests to FastAPI); set `DEPLOYED_FRONTEND_URL` or include the frontend URL in `ALLOWED_ORIGINS`.

If the original GitHub owner has not granted repository access, deploy the local checkout with Vercel CLI from each project directory after signing in to your own Vercel account; this uploads the local source without pushing to the owner's repository. Use Vercel's Secret environment-variable type for `GEMINI_API_KEY`, `UPSTASH_REDIS_REST_TOKEN`, `ANCHOR_PRIVATE_KEY`, and `ANCHOR_API_SECRET`. Keep `VITE_API_URL` public because it is embedded in the frontend build. Add backend environment values in Vercel's project settings and redeploy after changing them.

For a public preview, keep openIMIS credentials unset so the app stays in mock mode, use only synthetic claims, and use a Fuji-only wallet if enabling anchoring. Redis mode still keeps new claims/corrections in process memory; Oracle mode persists them but must be configured with the Oracle variables above. Vercel CLI supports deploying from source without connecting the owner&apos;s Git repo; see [Vercel FastAPI deployment](https://vercel.com/docs/frameworks/backend/fastapi), [Vercel CLI deployment](https://vercel.com/docs/cli/deploying-from-cli), and [Vercel environment variables](https://vercel.com/docs/environment-variables).

OpenIMIS/FHIR remains part of the project's winning hackathon interoperability path. A Kerugoya deployment still needs a facility/HMIS integration plan and the DHA-approved route into the national HIE.
## 🎯 Hackathon Track Focus

ClaimSense was built for the **openIMIS Hackathon — Track 3 (Claims Management)**. By optimizing point-of-entry accuracy instead of chasing rejections after the fact, it targets the evaluation criteria around interoperability (FHIR R4), administrative cost reduction, and system reliability — with a validation core simple enough to demo, test, and trust on stage.

---

## 🗺️ Roadmap

- [ ] Full FHIR `Bundle` parser for live openIMIS claim ingestion
- [ ] Facility-level analytics on common rejection causes
- [ ] Coverage lookups via the openIMIS `Coverage` FHIR endpoint
- [ ] Responsible AI section documenting Gemini's role (explanation only — never adjudication)


### OCR status

Paper claim upload is simulated in the frontend with fixed sample extracted fields; no OCR engine processes the document.


### Optional Avalanche Fuji audit anchoring

Anchoring is a separate manual action from claim validation. Configure `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` for the ledger, then set `AVAX_RPC_URL` (defaults to Fuji C-Chain), `ANCHOR_CONTRACT_ADDRESS`, `ANCHOR_PRIVATE_KEY`, `CHAIN_ID=43113`, and `ANCHOR_API_SECRET`. The signing key must belong to the deployed contract owner; use a dedicated Fuji-only wallet and never commit or share its private key. The UI requests the API secret when manually anchoring. If RPC or signer setup is unavailable, normal mock and validation flows continue. Only a SHA-256 digest of the sequence range and ledger head is sent on-chain; claim contents stay in the ledger.
