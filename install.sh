#!/usr/bin/env bash
# Installa (o aggiorna) il marketplace iovino-harness e i suoi plugin (core, modeler) su questo computer.
#
#   ./install.sh                     usa questa cartella (clone locale) come marketplace
#   ./install.sh owner/repo          usa il repository GitHub come marketplace
#   ./install.sh --no-settings       non tocca ~/.claude/settings.json
#   PLUGINS=core ./install.sh        installa solo alcuni plugin (default: core modeler)
#
# Idempotente: si può rilanciare dopo ogni git pull.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKETPLACE="iovino-harness"
SOURCE="$HERE"
APPLY_SETTINGS=1

for arg in "$@"; do
  case "$arg" in
    --no-settings) APPLY_SETTINGS=0 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) SOURCE="$arg" ;;
  esac
done

command -v claude >/dev/null || { echo "Claude Code non trovato nel PATH." >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 è richiesto dagli hook del plugin core." >&2; exit 1; }

echo "==> Marketplace $MARKETPLACE da $SOURCE"
if claude plugin marketplace list 2>/dev/null | grep -q "$MARKETPLACE"; then
  claude plugin marketplace update "$MARKETPLACE"
else
  claude plugin marketplace add "$SOURCE"
fi

PLUGINS="${PLUGINS:-core modeler}"
for plugin in $PLUGINS; do
  echo "==> Plugin $plugin"
  CONFIG=()
  if [ "$plugin" = "core" ] && [ "$SOURCE" = "$HERE" ]; then
    # clone locale: le note dell'harness finiscono direttamente in questo repository
    CONFIG=(--config "harness_repo=$HERE")
  fi
  if claude plugin list 2>/dev/null | grep -q "$plugin@$MARKETPLACE"; then
    claude plugin update "$plugin@$MARKETPLACE" || true
  else
    claude plugin install "$plugin@$MARKETPLACE" ${CONFIG[@]+"${CONFIG[@]}"}
  fi
done

if [ "$APPLY_SETTINGS" = 1 ]; then
  echo "==> Permessi consigliati in ~/.claude/settings.json"
  # le note dell'harness si scrivono senza conferma: NOTES.md del clone e cartella dati del plugin
  python3 "$HERE/settings/merge_settings.py" "$HERE/settings/recommended-settings.json" "$HOME/.claude/settings.json" \
    --allow "Edit(/$HERE/NOTES.md)" --allow "Edit(~/.claude/plugins/data/core-$MARKETPLACE/**)" \
    --allow "Read(/$HERE/plugins/**)" \
    --allow "Bash(python3 $HERE/plugins/modeler/scripts/modeler.py validate:*)" \
    --allow "Bash(python3 \"$HERE/plugins/modeler/scripts/modeler.py\" validate:*)" \
    --allow "Bash(python3 $HERE/plugins/modeler/scripts/modeler.py show:*)" \
    --allow "Bash(python3 \"$HERE/plugins/modeler/scripts/modeler.py\" show:*)" \
    --allow "Bash(python3 $HERE/plugins/modeler/scripts/modeler.py diff:*)" \
    --allow "Bash(python3 \"$HERE/plugins/modeler/scripts/modeler.py\" diff:*)" \
    --allow "Bash(python3 tools/modeler/modeler.py validate:*)" --allow "Bash(python3 tools/modeler/modeler.py show:*)" \
    --allow "Bash(python3 tools/modeler/modeler.py proposals:*)" --allow "Bash(python3 tools/modeler/modeler.py diff:*)" \
    --allow "Bash(npm run model:validate:*)" --allow "Bash(npm run model:show:*)" \
    --allow "Bash(npm run model:proposals:*)"
fi

if claude plugin list 2>/dev/null | grep -q "appforge@"; then
  echo
  echo "Attenzione: appforge è ancora installato ed è dismesso. Rimuovilo con:"
  echo "  claude plugin uninstall appforge@appforge-marketplace"
  echo "  claude plugin marketplace remove appforge-marketplace"
fi

echo
echo "Fatto. In una sessione già aperta esegui /reload-plugins."
