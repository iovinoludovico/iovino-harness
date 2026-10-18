-- Domain modeler of this app: proposals of metamodel changes made from the admin area in production.
-- They never change the running application: the developer copies them into the repository
-- (`npm run model:pull`, from the Supabase project linked with `supabase link`), reviews them and implements them
-- (domain.ecore.yaml + migration + code).
create table if not exists public.model_change_requests (
  id           uuid primary key default gen_random_uuid(),
  metamodel    jsonb not null,
  behavior     jsonb,            -- the behaviour (behavior.yaml) the proposal carries, when the app has one
  note         text,
  author_email text,
  status       text not null default 'open' check (status in ('open', 'pulled', 'applied', 'rejected')),
  created_at   timestamptz not null default now()
);

-- tables created before the behaviour proposals: the column is added (idempotent)
alter table public.model_change_requests add column if not exists behavior jsonb;

alter table public.model_change_requests enable row level security;

-- Admins only: replace public.is_admin() with the app's own admin predicate if it has another name.
drop policy if exists model_change_requests_admin on public.model_change_requests;
create policy model_change_requests_admin on public.model_change_requests
  for all to authenticated using (public.is_admin()) with check (public.is_admin());
