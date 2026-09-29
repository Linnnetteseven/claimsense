-- Hand-off of Hakiki-validated claims to the hospital HIS, which submits them to SHA.
-- Each row is the exact bundle Hakiki certified, with the score and rules it passed.

alter table public.claims drop constraint if exists claims_status_check;
alter table public.claims add constraint claims_status_check
    check (status in ('draft', 'handed_off', 'submitted', 'cancelled'));

create table if not exists public.claim_handoffs (
    id uuid primary key default gen_random_uuid(),
    claim_number text not null references public.claims (claim_number) on delete cascade,
    bundle jsonb not null,
    score integer not null,
    ruleset_version text not null,
    warnings jsonb not null default '[]'::jsonb,
    delivery text not null check (delivery in ('store', 'webhook', 'openimis')),
    delivery_status text not null check (delivery_status in ('stored', 'delivered', 'failed')),
    delivery_response jsonb,
    created_at timestamptz not null default now()
);

create index if not exists claim_handoffs_claim_number_idx on public.claim_handoffs (claim_number, created_at desc);

-- Service role only; the anon key can never read hand-offs.
alter table public.claim_handoffs enable row level security;
