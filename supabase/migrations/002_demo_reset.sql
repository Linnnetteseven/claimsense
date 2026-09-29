-- Demo reset support.
-- seed_template: the claim as originally seeded or created. Seeded claims keep
--   relative date tokens such as "{{today-3d}}" so a reset re-resolves dates and
--   deliberately broken claims (e.g. a future visit date) stay broken.
-- is_seed: true for rows written by the seed scripts. A full demo reset restores
--   these and deletes everything else (claims added through the UI).
alter table public.claims add column if not exists seed_template jsonb;
alter table public.claims add column if not exists is_seed boolean not null default false;

create index if not exists claims_is_seed_idx on public.claims (is_seed);
