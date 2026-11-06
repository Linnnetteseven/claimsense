# Hakiki: insurance officer briefing

## What it does

Hakiki is a claims-preparation workspace for Kerugoya Level 5 Hospital. It helps hospital staff check a claim before submission, see why a rule flagged it, correct the saved version, and record the steps taken. It is a co-pilot for facility staff; it does not replace SHA, the hospital HMIS, or clinical and payment decisions.

## How a claim moves through it

1. A claim enters the relevant department inbox.
2. Hakiki runs ten deterministic checks: seven shared checks plus maternity, renal, and surgical claim-type checks. Rules look for structural or documentation concerns; they do not guarantee payer acceptance.
3. Staff review the flagged items, save any correction as a new version, and the system runs the current checks again.
4. The owning desk completes its checklist and records its sign-off. These checklists are drafts to confirm with Kerugoya desk officers.
5. A claims officer submits the latest validated version through the configured workflow. In this demonstration, a live SHA/openIMIS submission connection is not established.
6. The facility can record a later returned/rejected, accepted, or paid outcome for follow-up and learning.

## What each desk does

- **Outpatient:** handles most routine outpatient claims; there is no outpatient-only automated rule today.
- **Renal:** checks dialysis-related claims. Hakiki flags `sessions_this_week > 3` for review; that is an internal demo heuristic, not a SHA limit.
- **Maternity:** checks delivery/labour claims for a linked `partograph_id` when the relevant indicators are present.
- **Manager:** sees aggregate workflow measures in Management Overview.
- Lab and pharmacy appear as supporting-item status, not independent desk roles.

The demo roles only filter the interface. They are clearly labelled and do not authenticate a person or secure a hospital account. With `DEPARTMENTS_ENABLED=false`, department sign-off is omitted and the available roles are Claims officer and Manager.

## Trust and privacy

Synthetic demo claims use fake `SYN-nnnnnn` patient references and `SYN-CLM-nnnnnn` claim references. A fictional Kenyan-style display name is generated in the browser from the fake reference; it is not saved in the claim, version, evidence pack, or fingerprint input. The validation page carries the persistent label **Demo environment: synthetic data**. Evidence-pack export checks the database `is_synthetic` flag and the `SYN-nnnnnn` reference.

Hakiki links claim events in an audit ledger. It can manually anchor a batch fingerprint on Avalanche Fuji, which gives the facility an external time and integrity reference. The blockchain stores a fingerprint, not the claim or the patient name. This can help show that recorded data changed after anchoring; it cannot prove that care happened or that SHA received or paid a claim.

## What a pilot would need

The facility would need an approved way to receive claim data from its HMIS, agree desk checklists with staff, confirm its SHA/openIMIS submission pathway, and set up real user authentication and access control. This build uses synthetic data and is suitable for workflow demonstration, not live patient processing.
