-- appforge web modeler: proposals of metamodel changes made from the admin area in production.
-- They never change the running application: the developer pulls them into the repository
-- (`appforge metamodel pull --db <DSN>`), reviews them and regenerates / implements them.
create table if not exists public.model_change_requests (
  id           uuid primary key default gen_random_uuid(),
  metamodel    jsonb not null,
  note         text,
  author_email text,
  status       text not null default 'open' check (status in ('open', 'pulled', 'applied', 'rejected')),
  created_at   timestamptz not null default now()
);

alter table public.model_change_requests enable row level security;

-- Admins only. appforge apps have public.is_admin(); in an adopted app replace it with the app's own check.
drop policy if exists model_change_requests_admin on public.model_change_requests;
create policy model_change_requests_admin on public.model_change_requests
  for all to authenticated using (public.is_admin()) with check (public.is_admin());
