#!/usr/bin/env bash
# Installa (o aggiorna) il marketplace iovino-harness e il plugin core su questo computer.
#
#   ./install.sh                     usa questa cartella (clone locale) come marketplace
#   ./install.sh owner/repo          usa il repository GitHub come marketplace
#   ./install.sh --no-settings       non tocca ~/.claude/settings.json
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

echo "==> Plugin core"
CONFIG=()
if [ "$SOURCE" = "$HERE" ]; then
  # clone locale: le note dell'harness finiscono direttamente in questo repository
  CONFIG=(--config "harness_repo=$HERE")
fi
if claude plugin list 2>/dev/null | grep -q "core@$MARKETPLACE"; then
  claude plugin update "core@$MARKETPLACE" || true
else
  claude plugin install "core@$MARKETPLACE" ${CONFIG[@]+"${CONFIG[@]}"}
fi

if [ "$APPLY_SETTINGS" = 1 ]; then
  echo "==> Permessi consigliati in ~/.claude/settings.json"
  # le note dell'harness si scrivono senza conferma: NOTES.md del clone e cartella dati del plugin
  python3 "$HERE/settings/merge_settings.py" "$HERE/settings/recommended-settings.json" "$HOME/.claude/settings.json" \
    --allow "Edit(/$HERE/NOTES.md)" --allow "Edit(~/.claude/plugins/data/core-$MARKETPLACE/**)"
fi

echo
echo "Fatto. In una sessione già aperta esegui /reload-plugins."
