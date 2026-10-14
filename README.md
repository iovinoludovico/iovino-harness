# iovino-harness

Harness personale per Claude Code: un marketplace di plugin da installare su ogni computer, così ogni sessione parte con le stesse convenzioni, gli stessi guardrail e le stesse skill.

## Contenuto

| Plugin | Cosa fa |
| :- | :- |
| `core` | Convenzioni iniettate a inizio sessione, guardrail su segreti e comandi distruttivi, autoformattazione, agenti `code-reviewer` e `debugger`, skill `project-init`, `handoff`, `commit`, `harness-note` |

In arrivo: `appforge`, `research`, `mde`.

## Installazione su un nuovo computer

Requisiti: Claude Code, `git`, `python3` (≥ 3.9).

```bash
git clone git@github.com:<tuo-utente>/iovino-harness.git ~/code/iovino-harness
cd ~/code/iovino-harness
./install.sh
```

Lo script:

1. registra la cartella come marketplace `iovino-harness` (caricato in place: un `git pull` aggiorna subito i plugin);
2. installa `core` impostando `harness_repo` su questa cartella;
3. aggiunge i permessi di `settings/recommended-settings.json` a `~/.claude/settings.json` (unione delle liste, backup automatico). Usa `--no-settings` per saltare questo passo.

Senza clone locale si può usare direttamente GitHub: `claude plugin marketplace add <tuo-utente>/iovino-harness` e poi `claude plugin install core@iovino-harness`; in questo caso `harness_repo` va impostato a mano con `/config`.

In una sessione già aperta: `/reload-plugins`.

## Uso quotidiano

| Comando | Quando |
| :- | :- |
| `/core:project-init` | Primo lavoro serio su un repository senza CLAUDE.md |
| `/core:commit` | Commit con Conventional Commits, test e lint prima, mai push |
| `/core:handoff` | Fine sessione o cambio computer: aggiorna HANDOFF.md |
| `/core:harness-note <lezione>` | Qualcosa da migliorare nell'harness: finisce in `NOTES.md` |

Gli agenti `core:code-reviewer` e `core:debugger` vengono usati da Claude quando servono, o su richiesta ("fai rivedere il diff al code-reviewer").

## Cosa fanno gli hook

- **SessionStart**: inietta `plugins/core/context/conventions.md` e lo stato del progetto (branch, file modificati, stack, presenza di CLAUDE.md e HANDOFF.md).
- **PreToolUse su Edit/Write**: blocca la scrittura di `.env*` (tranne `*.example`), chiavi e certificati, interni di `.git/`, e contenuti che sembrano chiavi o token.
- **PreToolUse su Bash**: blocca `rm -rf /` e simili e il force push su main/master; chiede conferma per `git push`, `reset --hard`, `clean`, `rm -r`, `sudo`, `curl | sh`, lettura di `.env`, `supabase db reset/push`, DDL distruttivo, `--no-verify`.
- **PostToolUse su Edit/Write**: formatta il file con il formatter già configurato nel progetto (prettier locale, ruff o black). Disattivabile con l'opzione `autoformat`.

Gli hook sono Python solo libreria standard: nessuna dipendenza da installare.

## Ciclo di miglioramento

1. Durante il lavoro, quando Claude sbaglia qualcosa di ricorrente: `/core:harness-note …`.
2. Ogni tanto, apri una sessione in questo repository, rivedi `NOTES.md` e trasforma le note in modifiche a `conventions.md`, agli hook o alle skill.
3. `python3 -m unittest discover -s tests` e `claude plugin validate plugins/core`, poi commit e push.
4. Sugli altri computer: `git pull` (marketplace locale) oppure `claude plugin marketplace update iovino-harness`.

## Struttura

```
.claude-plugin/marketplace.json
plugins/core/
  .claude-plugin/plugin.json
  context/conventions.md        ← le tue convenzioni: modificale qui
  hooks/hooks.json
  scripts/hook.py
  agents/{code-reviewer,debugger}.md
  skills/{project-init,handoff,commit,harness-note}/SKILL.md
settings/recommended-settings.json, merge_settings.py
tests/
install.sh
NOTES.md                         ← lezioni annotate da /core:harness-note
```
