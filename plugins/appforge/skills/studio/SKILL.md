---
name: studio
description: Starts appforge Studio, the local graphical editor of domain models and manager of the generated applications (entity diagram, workflow editor, events and reactions, YAML, generation preview). This skill should be used when the user wants to "modellare graficamente", "aprire lo studio", "vedere il diagramma delle entità/del workflow", or invokes /appforge:studio.
argument-hint: "[app] [--port N]"
---

# appforge Studio

Arguments: `$ARGUMENTS`

1. Start the server in the background (it runs until stopped):
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/appforge.py" studio --no-browser [--app <slug>] [--port 4321]`
   Use the Bash tool with `run_in_background`, then read its first output line: it contains the URL with a
   per-session token (`http://127.0.0.1:4321/#token=…`).
2. Give the user the URL (if this session runs on the user's computer, also open it with the system
   browser: `open <url>` on macOS, `xdg-open <url>` on Linux). The Studio binds to 127.0.0.1 only.
3. Explain briefly what it offers: the registry of apps on the left; for the open app the tabs *Dominio*
   (entities and references, drag to arrange), *Workflow* (states and transitions; select a state, then
   «Nuova transizione» and click the target), *Eventi e reazioni*, *Ruoli e impostazioni*, *YAML*, *Genera*
   (preview, generate, test migrations on a scratch database). Validation is live, Ctrl+S saves, Ctrl+Z undoes.
4. After the user saved changes in the Studio, run the `generate` skill from here when manual migrations or
   custom handlers are involved (the Studio cannot write SQL by itself).

If the session runs in a cloud container without access to the user's machine, the Studio can still run here,
but the user cannot open 127.0.0.1 of the container: say so, and suggest running the same command on their
computer (`python3 <plugin>/scripts/appforge.py studio`).

The **Metamodello** tab hosts the same web modeler of the admin area on `domain.ecore.yaml` (single-file apps
show it read-only with a button to split them). Saving refuses changes that would break `app.yaml`
(workflow guards, permissions, reactions, UI referring to removed features).
