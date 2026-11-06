# Hakiki product direction and Kerugoya pilot steps

## Product direction

Hakiki should complement facility systems by coordinating the work that happens inside a provider before and after a claim is handled by SHA. The national architecture already covers patient/facility registries, eligibility and benefit checks, pre-authorisation, HIE claim exchange, status, remittance, and national analytics. Hakiki's strongest opportunity is the facility team's operating layer: department-specific evidence review, clear ownership and sign-off, and learning from query/correction/payment outcomes.

Keep the OpenIMIS/FHIR workflow. It is part of Hakiki's winning hackathon origin and remains a useful interoperability path and presentation workflow. For a Kerugoya pilot, confirm with DHA and the hospital how that work maps to the facility's actual HMIS and the national HIE. OpenIMIS is not a substitute for that approval or connection.

## First feature increment now in the frontend

### Departmental claim review

- The department checklist is attached to a specific claim.
- Staff can check required and optional items, record an evidence reference, add a handover note, and sign off under a reviewer name.
- Removing or changing a completed item clears the previous sign-off so the review must be completed again.
- Current persistence is in the browser for the presentation workflow. It is not yet shared between staff or devices, role-authenticated, or stored in the backend.

### Claim-outcome feedback

- Staff can log submitted, queried, rejected, resubmitted, paid, or other updates for a claim.
- Query/rejection themes can be summarized across the outcome records available in that browser, with a claim-specific history.
- This is a foundation for facility-level learning. It does not yet ingest SHA/HIE responses or provide cross-user facility analytics.

## Step-by-step from presentation feature to safe pilot

1. **Choose a workflow with Kerugoya.** Meet the insurance head and one or two department leads. Walk through a real claim type from clinical documentation to internal review, preauthorization where needed, claim submission, query/correction, and payment follow-up. Choose the first department based on staff pain and available examples.
2. **Validate the checklist.** Replace assumptions in the maternity, renal, surgical, or outpatient guides with the facility's actual SOP and current authoritative requirements. Each check should explain what evidence is expected, who checks it, and what happens when it is missing.
3. **Make departmental ownership visible.** Add a team queue showing claims awaiting a department check, missing evidence, reviewer, handover note, and sign-off state. Use facility-agreed roles such as department reviewer and insurance reviewer; do not treat a typed name as authenticated identity.
4. **Move workflow state out of browser storage.** Add backend persistence, authenticated accounts, role permissions, timestamps, event history, backup, and access controls before multiple staff use it. Make changes traceable and preserve previous review versions.
5. **Connect outcome feedback to actual claim outcomes.** First agree with Kerugoya and DHA which approved OpenIMIS/HMIS/HIE source can provide status and payer-response information. Map actual query/rejection reasons into a controlled list, retain source references, and let staff correct category mapping.
6. **Measure the pilot.** Establish a baseline and track internal review turnaround, completeness at departmental sign-off, repeat query themes, correction time, claims with unresolved follow-up, and staff effort. Segment by department and claim type. Do not infer payment probability from Hakiki's readiness score.
7. **Confirm the DHA integration and certification scope.** Ask whether Hakiki must be part of the facility's certified HMIS, what sandbox workflows and security controls apply, whether the proposed component is allowed, and what go-live approval requires. Keep OpenIMIS work as an interoperability option, while making the Kerugoya deployment follow the route DHA and the hospital approve.
8. **Consider ML after the feedback dataset is trustworthy.** Start with descriptive reports. If there are enough consistently labelled outcomes, evaluate whether ML helps prioritize claims for human review or spot repeated workflow issues. Do not use it to decide eligibility, clinical appropriateness, SHA adjudication, or payment.
9. **Revisit Avalanche only if there is a defined audit need.** Identify what the hospital wants to prove, why existing HMIS/HIE logs are insufficient, and what DHA/privacy reviewers permit. Prototype with synthetic data first; only a digest of a canonical claim version should ever be considered for anchoring, with personal and clinical data kept off-chain.

## Measures that would show Hakiki is useful

- Time from claim entering department review to sign-off.
- Share of claims with all required evidence before insurance review.
- Repeated query/rejection themes by department and claim type.
- Time staff spend correcting and following up claims.
- Share of Hakiki checklist findings accepted or corrected by reviewers.
- Changes in the above versus a pre-pilot baseline.

The strongest pitch is a facility workflow assistant that helps teams complete, review, hand off, and learn from claims inside the systems they already use.