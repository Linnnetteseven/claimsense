# Roadmap: from demo-ready to hospital-integrated claims platform

The current app already has the core idea in place: a claim validation workflow, a simple UI, FHIR-oriented output, and an audit trail. To move it from a convincing demo to something that can be deployed in a local hospital HIS environment, the work needs to shift from “prototype” to “production-safe integration layer.”

## 1. Stabilize the backend architecture

### Goal
Make the API robust, testable, and ready for hospital operations.

### Code changes
- Refactor [backend/main.py](backend/main.py) so routes are grouped into routers instead of being defined in one file.
- Introduce Pydantic request/response models for all endpoints.
- Move business logic out of route handlers into service modules.
- Add a clear health-check endpoint with dependency checks for DB, Redis, Gemini, and openIMIS connectivity.

### Why this matters
A hospital deployment needs predictable API contracts, strong validation, and separation between transport, business logic, and integrations.

---

## 2. Replace mock data with real hospital integration adapters

### Goal
Allow the app to ingest claims from an HIS or openIMIS without relying on demo fixtures.

### Code changes
- Extend [backend/fhir/client.py](backend/fhir/client.py) with real adapters for:
  - FHIR Claim retrieval
  - Coverage lookup
  - Encounter/Condition/Organization resources
- Add a new parser module for HIS-to-internal claim transformation.
- Add a fallback strategy for partial data availability so the validator still works when some fields are missing.

### Why this matters
The current app uses mock claims and a simplified data model. A hospital deployment needs a reliable import pipeline from real clinical and administrative data.

---

## 3. Introduce authentication and role-based access

### Goal
Ensure only authorized staff can view or modify claim information.

### Code changes
- Add authentication to the API using OAuth2/OpenID Connect or a hospital SSO integration.
- Define roles such as:
  - claims officer
  - medical reviewer
  - finance auditor
  - administrator
- Protect endpoints in [backend/main.py](backend/main.py) using dependency injection and role checks.
- Pass the authenticated user identity into the audit trail and workflow events.

### Why this matters
Hospital systems must enforce access control, especially for patient and reimbursement data.

---

## 4. Move from ephemeral demo state to persistent storage

### Goal
Store claims, validation results, corrections, and user history in a real database.

### Code changes
- Replace the in-memory correction store in [backend/main.py](backend/main.py) with a database-backed repository.
- Add a relational database layer using PostgreSQL or SQLite for local development.
- Create tables for:
  - claims
  - validation_runs
  - rule_results
  - corrections
  - user_actions
  - audit_events
- Add ORM or repository abstractions so the API no longer depends on the current in-memory session model.

### Why this matters
Demo state disappears on restart. A hospital deployment needs durable records and reproducible workflows.

---

## 5. Make the validation engine configurable and versioned

### Goal
Allow the ruleset to evolve with hospital policy and SHA requirements.

### Code changes
- Refactor [backend/validation/rules.py](backend/validation/rules.py) into a rule registry with version metadata.
- Store the active rule version per hospital or department.
- Allow hospital-specific overrides for thresholds and required fields.
- Add a way to track rule changes over time for audit and policy review.

### Why this matters
Hospitals will not want a fixed static validator forever. They need policy updates without rewriting core logic.

---

## 6. Add workflow state and async processing

### Goal
Support real-world claim workflows, not just single-session validation.

### Code changes
- Introduce claim workflow states such as:
  - draft
  - submitted for review
  - corrected
  - approved
  - rejected
  - sent to payer
- Add background jobs for validation and submission.
- Make claim submission idempotent so retries do not create duplicate records.
- Add webhook or polling support for claim status updates from the HIS or payer.

### Why this matters
A hospital environment needs longitudinal claim tracking, not a one-shot validation screen.

---

## 7. Harden the audit trail for compliance

### Goal
Make the audit trail suitable for operational and regulatory review.

### Code changes
- Expand [backend/audit/chain.py](backend/audit/chain.py) so it writes both immutable hashes and structured audit event records.
- Record who changed what, when, and from which source system.
- Add retention policies and export features.
- Support audit verification from a database-backed ledger rather than only an external Redis service.

### Why this matters
Hospitals need defensible evidence for claim handling and dispute resolution.

---

## 8. Improve frontend for real clinical operations

### Goal
Make the UI suitable for daily use by claims staff and reviewers.

### Code changes
- Replace the current demo-style state handling in [frontend/src/hooks/useClaimValidation.js](frontend/src/hooks/useClaimValidation.js) with real API-driven state management.
- Add loading, error, retry, and offline-safe UX patterns.
- Add a real claim detail view with patient context, item breakdown, and correction history.
- Integrate the UI with authenticated API calls in [frontend/src/api/client.js](frontend/src/api/client.js).

### Why this matters
The front end needs to be fast, dependable, and clear for non-technical hospital staff.

---

## 9. Add observability and reliability

### Goal
Make the system operationally supportable.

### Code changes
- Add structured logging throughout the backend.
- Add request IDs and correlation IDs for tracing.
- Add metrics for validation latency, submission failures, and rule hit rates.
- Add alerting for API failures, external service outages, and high error rates.

### Why this matters
A hospital deployment cannot depend on informal debugging or manual monitoring.

---

## 10. Containerize and deploy for a local hospital environment

### Goal
Make the app deployable in a standard hospital or on-prem environment.

### Code changes
- Add Dockerfiles for backend and frontend.
- Add a docker-compose setup for API, database, and optional Redis.
- Add environment profiles for development, staging, and production.
- Add CI/CD pipelines for automated testing and deployment.

### Why this matters
The system needs repeatable deployment and maintenance processes.

---

## 11. Add security and privacy controls

### Goal
Protect patient data and comply with local healthcare data handling expectations.

### Code changes
- Encrypt sensitive fields at rest and in transit.
- Mask or minimize patient identifiers in logs and UI previews.
- Add consent and data-retention handling if required by local policy.
- Build a data classification strategy for clinical vs. administrative data.

### Why this matters
Healthcare integrations are not just business integrations; they are regulated data environments.

---

## 12. Run pilot deployment and validation

### Goal
Prove the system in a real hospital workflow.

### Code changes
- Create a staging environment that mirrors the hospital HIS.
- Run test claims with real departments and claim scenarios.
- Capture feedback from claims officers and medical reviewers.
- Fix workflow gaps before production rollout.

### Why this matters
The best architecture decisions come from actual end-user usage, not just technical assumptions.

---

## Suggested implementation order

1. Backend architecture hardening
2. Authentication and authorization
3. Persistent storage
4. Real HIS/FHIR adapters
5. Workflow and async processing
6. Audit, security, observability
7. Deployment and pilot rollout

---

## The first 5 concrete steps I would take in this repo

1. Split [backend/main.py](backend/main.py) into routers and service modules.
2. Add typed request/response models and replace the current ad-hoc route logic.
3. Add database-backed persistence for corrections and validation history.
4. Extend [backend/fhir/client.py](backend/fhir/client.py) to support real FHIR claim ingestion and submission.
5. Add authentication and role checks before any patient-sensitive endpoint is used.

If you want, the next step can be to turn this roadmap into a concrete implementation checklist with actual file-by-file changes and starter code for the first phase.
