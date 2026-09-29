-- SHA's answer to a handed-off claim, forwarded by the hospital HIS.
-- claims.sha_state: the latest parsed claim state, shown as a badge; cleared when the
--   claim is edited (a new cycle starts).
-- claim_handoffs.sha_response: the full ClaimResponse, kept with the hand-off it answers.

alter table public.claims add column if not exists sha_state jsonb;
alter table public.claim_handoffs add column if not exists sha_response jsonb;
alter table public.claim_handoffs add column if not exists sha_response_at timestamptz;
