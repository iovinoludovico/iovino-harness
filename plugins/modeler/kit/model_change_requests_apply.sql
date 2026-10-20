-- Domain modeler of this app: outcome of an apply started from the admin page ("Apply" on a production proposal).
-- The button sends a repository_dispatch to GitHub; the `modeler-apply` workflow pulls that proposal, runs Claude
-- Code on it and opens a pull request, then writes the link (or the error) here with `npm run model:track`.
-- The status stays `pulled` until `npm run model:done -- --write` closes it after the deploy. Idempotent.
alter table public.model_change_requests add column if not exists apply_requested_at timestamptz;
alter table public.model_change_requests add column if not exists apply_finished_at timestamptz;
alter table public.model_change_requests add column if not exists pr_url text;
alter table public.model_change_requests add column if not exists apply_error text;
-- "Confirm and release" on the PR: the `modeler-release` workflow (migrations on the production database, merge,
-- deploy, `model:done`) records its progress here.
alter table public.model_change_requests add column if not exists release_requested_at timestamptz;
alter table public.model_change_requests add column if not exists release_error text;
alter table public.model_change_requests add column if not exists merged_at timestamptz;
alter table public.model_change_requests add column if not exists deployed_at timestamptz;
