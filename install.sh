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

if [ "$SOURCE" = "$HERE" ] && [ -d "$HERE/.git" ]; then
  # il push di un plugin modificato richiede la versione alzata (scripts/release.py)
  git -C "$HERE" config core.hooksPath .githooks
fi

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

# Un aggiornamento non riceve --config: se l'opzione è vuota (plugin installato da GitHub, o prima che il clone
# esistesse) o indica una cartella che non c'è più, impostala su questo clone. Un altro percorso valido resta.
if [ "$SOURCE" = "$HERE" ] && [[ " $PLUGINS " == *" core "* ]]; then
  CURRENT="$(claude plugin configure "core@$MARKETPLACE" --json 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("inputs", {}).get("harness_repo") or "")' 2>/dev/null || true)"
  if [ -z "$CURRENT" ] || [ ! -d "${CURRENT/#\~/$HOME}" ]; then
    echo "==> Opzione harness_repo del plugin core: $HERE"
    python3 -c 'import json,sys; print(json.dumps({"harness_repo": sys.argv[1]}))' "$HERE" \
      | claude plugin configure "core@$MARKETPLACE" --values-stdin \
      || echo "   non impostata: fallo da /plugin → core → configurazione" >&2
  fi
fi

if [ "$APPLY_SETTINGS" = 1 ]; then
  echo "==> Permessi consigliati in ~/.claude/settings.json"
  # le note dell'harness si scrivono e si committano (solo NOTES.md) senza conferma: clone e cartella dati del plugin
  python3 "$HERE/settings/merge_settings.py" "$HERE/settings/recommended-settings.json" "$HOME/.claude/settings.json" \
    --allow "Edit(/$HERE/NOTES.md)" --allow "Edit(~/.claude/plugins/data/core-$MARKETPLACE/**)" \
    --allow "Read(/$HERE/plugins/**)" \
    --allow "Bash(git -C $HERE branch --show-current)" \
    --allow "Bash(git -C $HERE commit NOTES.md:*)" \
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

echo
echo "Fatto. In una sessione già aperta esegui /reload-plugins."
