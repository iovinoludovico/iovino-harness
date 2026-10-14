---
name: upgrade
description: Brings an existing appforge application up to the current version of the generator and of the reference template (regenerates the behaviour layer and merges template improvements into the app's own files). This skill should be used when status reports a different generator version, when the user asks "aggiorna l'app all'ultima versione del framework", or invokes /appforge:upgrade.
argument-hint: "[app]"
---

# Upgrade an app to the current appforge

1. `appforge status <app>` — note the generator version recorded in the lock.
2. Regenerate: `appforge generate <app>`. When the generator version differs from the lock (or with
   `--rebuild-behavior`), an evolve migration with the full new behaviour layer is produced even if the model
   did not change; the lock records the new version.
3. Template files (owned by the app after scaffolding: pages, components, worker, Dockerfile, CI) are not
   overwritten. Compare them with `${CLAUDE_PLUGIN_ROOT}/templates/app/` (placeholders `{{…}}` aside) and
   propose the relevant differences file by file; apply only what the user accepts, preserving local
   customisations.
4. Verify with the `check` skill and summarise what changed.
