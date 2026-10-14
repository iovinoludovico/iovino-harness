---
name: custom
description: Implements the hand-written body of a `custom` reaction (public.custom_<handler>) or another piece of domain logic that the appforge model cannot express, as a new migration with tests. This skill should be used when generation lists custom handlers to implement, when the user asks "implementa l'handler X", "serve una regola che il modello non esprime", or invokes /appforge:custom.
argument-hint: "<handler o descrizione della logica> [app]"
---

# Hand-written domain logic

Request: `$ARGUMENTS`

1. Load the `architecture` skill and read `references/where-code-goes.md` (template and checklist).
2. Find the reaction in `app.yaml` (`do: custom`, `handler: …`): which event triggers it and with which filters.
   Read the payload shape in `docs/domain.md` / `src/lib/events/catalog.ts`.
3. Clarify the intended behaviour with the user if the description is not precise (it runs inside the same
   transaction as the change: an exception aborts the user's action).
4. Create the migration with `supabase migration new custom_<handler>` (or a timestamped file after the
   latest one) containing `create or replace function public.custom_<handler>(p_event public.events)`.
   Follow the checklist: security definer, empty search_path, qualified names, revoke execute, map new error
   messages in `src/lib/db-errors.ts` + `messages/*.json` (`errors.*`).
5. Add a pgTAP test in `supabase/tests/database/custom_<handler>.test.sql` that performs the triggering change
   and asserts the effect.
6. Verify with the `check` skill. Delegate to the `sql-engineer` agent for larger pieces of logic.

If the logic is an external effect (email, HTTP API, files), do not write it in SQL: propose a webhook
subscriber (n8n workflow) on the event instead, and if useful remove the `custom` reaction from the model.
