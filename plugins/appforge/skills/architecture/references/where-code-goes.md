# Where code goes in an appforge app

| Need | Put it in | Never |
|---|---|---|
| A new field, entity, role, permission, state, transition, event, notification | `app.yaml` → `/appforge:generate` | hand-written DDL for something the model expresses |
| Body of a `custom` reaction | new migration: `create or replace function public.custom_<handler>(p_event public.events)` | editing the generated stub inside a generated migration |
| Data migration for a model change | the `*_manual_evolve_N.sql` (pre) / `*_manual_evolve_N_post.sql` file created by generate | editing generated evolve migrations |
| Domain rule too complex for guard/condition (aggregates, cross-entity checks) | SQL function + `before insert/update` trigger in a new migration; raise exceptions with an Italian message mapped in `src/lib/db-errors.ts` | checks only in the UI |
| Computed values | SQL (generated column in a manual migration, or a view) | computing in React and saving |
| A specialised page for an entity | `src/app/(app)/x/<entity>/…` or override the link in `src/lib/model-helpers.ts` | editing `src/lib/model.ts` |
| External effects (email, PDF, third-party APIs) | a webhook subscriber (n8n) reacting to the event; for emails use `data.recipients` | HTTP calls from Postgres or from Server Actions after the commit |
| Realtime UI updates | a `broadcast` reaction + `<RealtimeRefresh channel=…>` | polling |
| Hardware / edge devices | a separate process that calls RPCs with its own credentials and subscribes to events | direct table writes with the service key outside RPCs |
| Translations | every `messages/<locale>.json` with the same keys (the `model` namespace is generated) | hard-coded strings |

## Hand-written migration checklist
1. `supabase migration new <name>` (timestamped after the generated ones).
2. `security definer` + `set search_path = ''` + fully qualified names (`public.x`).
3. Permissions checked inside the function (`public.<entity>_can`, `public.is_admin()`), grants explicit:
   `revoke execute … from public, anon, authenticated; grant execute … to authenticated;` only for RPCs.
4. Every new `raise exception '<testo>'` mapped in `src/lib/db-errors.ts` and translated in `errors.*`.
5. A pgTAP test in `supabase/tests/database/` for the new behaviour.
6. `supabase db reset && npm test && npm run typecheck` (or `/appforge:check`).

## Custom handler template
```sql
-- supabase/migrations/<timestamp>_custom_<handler>.sql
create or replace function public.custom_<handler>(p_event public.events)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  r public.<table>;
begin
  select * into r from public.<table> where id = p_event.entity_id;
  if not found then
    return;
  end if;
  -- … domain logic; it runs in the producer's transaction: raising aborts the whole change.
  -- To publish a follow-up event (declared in app.yaml):
  -- perform public.emit_entity_event('<entity>', r.id, '<entity>.<event>', jsonb_build_object('reason', '…'));
end;
$$;
revoke execute on function public.custom_<handler>(public.events) from public, anon, authenticated;
```
