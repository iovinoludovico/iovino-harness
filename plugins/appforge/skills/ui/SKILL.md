---
name: ui
description: Shows and changes how the concepts of the model map to UI components in an appforge app (widget of each field; table, cards, kanban or calendar views; related panels on detail pages) and proposes components that fit the model. This skill should be used when the user asks how the app shows the data, wants a calendar, board, cards or a different input for a field ("mostra gli inviti in un calendario", "voglio una bacheca per stato", "il campo X come radio"), or invokes /appforge:ui.
argument-hint: "[suggest | richiesta] [app]"
---

# UI mapping of the model

Request: `$ARGUMENTS`. CLI: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/appforge.py" ui show|suggest <app>`.

## How the mapping works
The generic pages render what `src/lib/model.ts` says; the generator fills it from a **default mapping** that
`app.yaml` can override per entity (`entities.<Entity>.ui`):

| concept in the model | default component |
|---|---|
| EString / Text / Email / URL | text / textarea / email / url input; URL named photo, image, foto, logo → image |
| EInt, EDouble with `min` and `max` close (≤ 20) | slider; otherwise number |
| Money | currency input |
| EBoolean | switch |
| Date / EDate | date / date-time picker |
| enum with ≤ 4 literals | radio buttons; more → searchable select |
| reference `[0..1]`/`[1]` | searchable select of the target |
| reference `[*]` | checklist (alternative: `ref-select`, multi-select) |
| multi-valued attribute | JSON (alternative: `tags`) |
| class with a workflow | views table + kanban by state |
| containment | the parts listed on the owner's detail page, with "New" pre-filled |

```yaml
entities:
  Invitation:
    ui:
      view: kanban                    # default view of the list page
      views: [kanban, table, calendar]
      kanban: {group_by: state}       # or an enum field
      calendar: {start: start_date, end: end_date}
      widgets: {notes: textarea, accommodation: radio}
  Guest:
    ui:
      views: [table, cards]
      cards: {title: last_name, subtitle: email, image: photo_url}
      related: [Invitation.guest]     # records of other classes referencing this one (false = none)
```
Widgets: `text textarea email url image number slider currency checkbox switch date datetime select radio
ref-select ref-checklist json tags`. Fields are named by their stored key (snake_case).

## Steps
1. `ui show <app>`: the effective mapping. `ui suggest <app>`: alternatives the model supports (calendar for
   date ranges, kanban for workflows and status enums, cards for images or contact-like records, related
   panels for inverse references, textarea for free text, radio for short enums, slider for bounded numbers).
2. Present the suggestions that fit the user's goal (not all of them), with the reason; apply the chosen ones by
   merging the `ui` snippet into `app.yaml`. The validator checks widgets against field types and views
   against the model.
3. `generate`: a UI-only change regenerates `model.ts` without any migration.
4. Components the mapping does not cover (a chart, a map, a custom dashboard) are hand-written pages:
   see the `architecture` skill ("Where code goes").
