-- Row level security and validation / correction history.
--
-- RLS is on with no policies on every table: the backend uses the service role key,
-- which bypasses RLS, so the anon key can never read or write claim data.

alter table public.claims enable row level security;

-- Supabase linter 0011: pin the trigger function's search_path.
alter function public.set_claims_updated_at() set search_path = '';

-- One row per full validation (the deterministic score and the rules that ran).
create table if not exists public.validation_runs (
    id uuid primary key default gen_random_uuid(),
    claim_number text not null references public.claims (claim_number) on delete cascade,
    score integer not null,
    rule_version text not null,
    error_count integer not null,
    warning_count integer not null,
    ai_explanations_used boolean not null default false,
    results jsonb not null,
    created_at timestamptz not null default now()
);

-- One row per changed field on each correction. source records whether the officer
-- typed it or applied a suggestion (and which), for audit of AI-assisted edits.
create table if not exists public.corrections (
    id uuid primary key default gen_random_uuid(),
    claim_number text not null references public.claims (claim_number) on delete cascade,
    field text not null,
    old_value jsonb,
    new_value jsonb,
    source text not null default 'manual',
    created_at timestamptz not null default now()
);

create index if not exists validation_runs_claim_number_idx on public.validation_runs (claim_number);
create index if not exists validation_runs_created_at_idx on public.validation_runs (created_at);
create index if not exists corrections_claim_number_idx on public.corrections (claim_number);
create index if not exists corrections_created_at_idx on public.corrections (created_at);

alter table public.validation_runs enable row level security;
alter table public.corrections enable row level security;
