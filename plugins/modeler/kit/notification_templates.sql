-- Notification texts of this app: overrides of the templates of behavior.yaml (`templates:`), one row per
-- template key and language. The engine (<entity>_recipients) renders subject and body for every recipient from
-- these rows when they exist, else from the texts of the model; the admin page (matrix template x language) edits
-- them. Written once by `modeler install` when behavior.yaml has templates.
create table if not exists public.notification_templates (
  key        text not null,
  locale     text not null check (locale ~ '^[a-z]{2}$'),
  subject    text not null,
  body       text not null default '',
  updated_at timestamptz not null default now(),
  updated_by uuid,
  primary key (key, locale)
);

alter table public.notification_templates enable row level security;

-- Admins only: replace public.is_admin() with the app's own admin predicate if it has another name.
drop policy if exists notification_templates_admin on public.notification_templates;
create policy notification_templates_admin on public.notification_templates
  for all to authenticated using (public.is_admin()) with check (public.is_admin());
