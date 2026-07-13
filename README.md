# 🩺 Hakiki
"Grammarly for hospital claims."

## *An AI-Powered Claims Intelligence Platform for Healthcare Financing*


> **"Helping healthcare providers submit better claims before they become reimbursement delays."**

Hakiki is an AI-powered Claims Intelligence Platform that integrates with existing **Hospital Information Systems (HIS)** and healthcare financing platforms such as **openIMIS** to improve the quality of healthcare claims before submission.

Rather than replacing existing hospital systems, Hakiki acts as an intelligent decision-support layer between claim preparation and claim submission. It validates draft claims against healthcare financing rules, identifies inconsistencies, explains issues in plain language, and provides actionable recommendations that help claims officers submit complete, compliant, and high-quality claims.

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
[ FastAPI Validation Engine ] ──► [ 7 Deterministic SHA Rules ]
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
2. **Rule pass** — Seven deterministic rules run against the claim: required fields, ICD-10 format, visit date sanity, item/service codes, coverage window, amount-vs-items match, and amount-reasonableness thresholds.
3. **Score** — Each failed rule deducts points (errors −20, warnings −10) off a base of 100, producing a color-coded status: 🟢 Ready · 🟡 Needs Review · 🔴 High Risk.
4. **Explain** — Every error is batched into a single Gemini API call that returns a short, non-technical explanation and fix suggestion per rule.
5. **Correct & re-validate** — The clerk edits flagged fields inline; the claim is re-scored instantly, no resubmission needed.
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
│   │   ├── rules.py               ← 7 rule functions
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
git clone https://github.com/Linnnetteseven/openimis-dist_dkr.git
cd openimis-dist_dkr/claimsense
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
pytest tests/ -v              # 24 tests should pass
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

ClaimSense scores claims using **seven transparent, deterministic rules** — no training data, no drift, no model to retrain when SHA policy changes. Just code you can read in five minutes.

| Rule | Checks | Severity |
|---|---|---|
| Required Fields | Patient ID, facility code, visit date, diagnosis code present | 🔴 Error |
| ICD-10 Format | Diagnosis code matches valid ICD-10 structure | 🔴 Error |
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

## 🎯 Hackathon Track Focus

ClaimSense was built for the **openIMIS Hackathon — Track 3 (Claims Management)**. By optimizing point-of-entry accuracy instead of chasing rejections after the fact, it targets the evaluation criteria around interoperability (FHIR R4), administrative cost reduction, and system reliability — with a validation core simple enough to demo, test, and trust on stage.

---

## 🗺️ Roadmap

- [ ] Full FHIR `Bundle` parser for live openIMIS claim ingestion
- [ ] Facility-level analytics on common rejection causes
- [ ] Coverage lookups via the openIMIS `Coverage` FHIR endpoint
- [ ] Responsible AI section documenting Gemini's role (explanation only — never adjudication)
