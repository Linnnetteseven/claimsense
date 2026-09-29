-- ClaimSense demo HIS store. The full existing ClaimSense claim shape lives in
-- claim_data so the validation engine can continue consuming it unchanged.
create table if not exists public.claims (
    id uuid primary key default gen_random_uuid(),
    claim_number text not null unique,
    status text not null default 'draft' check (status in ('draft', 'submitted', 'cancelled')),
    claim_data jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint claims_claim_data_is_object check (jsonb_typeof(claim_data) = 'object'),
    constraint claims_claim_data_id_matches_number check (claim_data ->> 'id' = claim_number)
);

create index if not exists claims_status_idx on public.claims (status);
create index if not exists claims_claim_data_gin_idx on public.claims using gin (claim_data);

create or replace function public.set_claims_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists claims_set_updated_at on public.claims;
create trigger claims_set_updated_at
before update on public.claims
for each row execute function public.set_claims_updated_at();
