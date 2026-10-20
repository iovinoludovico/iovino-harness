# iovino-harness

Harness personale per Claude Code: un marketplace di plugin da installare su ogni computer, così ogni sessione parte con le stesse convenzioni, gli stessi guardrail e le stesse skill.

## Contenuto

| Plugin | Cosa fa |
| :- | :- |
| `core` | Convenzioni iniettate a inizio sessione, guardrail su segreti e comandi distruttivi, autoformattazione, agenti `code-reviewer` e `debugger`, skill `project-init`, `handoff`, `commit`, `ship`, `db-push`, `deploy`, `security-audit`, `harness-note`, `harness-review` |
| `modeler` | Sviluppo model-based delle app Next.js + Supabase: metamodello di dominio `domain.ecore.yaml` (notazione Ecore) dal prompt o ricavato dal database, modello di comportamento `behavior.yaml` (workflow, guardie, derivazioni, eventi, reazioni) verificato sul metamodello e da cui si generano documentazione, SQL e il motore (funzioni e trigger), modellatore web che diventa parte dell'app (`/admin/model`, proposte, CLI `tools/modeler/` con gli script `npm run model:*`), controllo di allineamento metamodello ↔ database, export Ecore/Emfatic/Mermaid. Dettagli in `plugins/modeler/README.md` |

In arrivo: `research`, `mde`.

## Installazione su un nuovo computer

Requisiti: Claude Code, `git`, `python3` (≥ 3.10 per `modeler`). Il repository è
`iovinoludovico/iovino-harness`. Due strade:

### A. Clone + `install.sh` (consigliata)

```bash
git clone https://github.com/iovinoludovico/iovino-harness.git ~/Documents/GitHub/iovino-harness
cd ~/Documents/GitHub/iovino-harness
./install.sh
```

Lo script (si può rilanciare quando vuoi):

1. registra la cartella come marketplace `iovino-harness`, caricato in place: i plugin si leggono da qui;
2. installa `core` (con `harness_repo` su questa cartella, così `/core:harness-note` scrive in `NOTES.md`) e
   `modeler` (`PLUGINS=core ./install.sh` per sceglierne alcuni);
3. aggiunge i permessi di `settings/recommended-settings.json` a `~/.claude/settings.json` (unione delle liste,
   backup automatico; `--no-settings` per saltare questo passo);
4. attiva l'hook git di push (`core.hooksPath .githooks`) che impedisce di pubblicare un plugin modificato senza
   alzarne la versione.

**Aggiornare**: `git pull`, poi `/reload-plugins` nelle sessioni aperte (rilancia `./install.sh` se è cambiato).

### B. Dal marketplace GitHub, senza clone

```bash
claude plugin marketplace add iovinoludovico/iovino-harness
claude plugin install core@iovino-harness
claude plugin install modeler@iovino-harness
```
(dentro Claude Code: `/plugin marketplace add iovinoludovico/iovino-harness`, poi `/plugin`).

**Aggiornare**:
```bash
claude plugin marketplace update iovino-harness
claude plugin update core@iovino-harness
claude plugin update modeler@iovino-harness
```
poi `/reload-plugins`. Un plugin si aggiorna solo se la sua `version` è cambiata: per questo ogni rilascio la
alza (vedi "Rilasciare una modifica").

Differenze rispetto alla strada A:
- le note di `/core:harness-note` vanno in `~/.claude/plugins/data/core-iovino-harness/NOTES.md`; se su quel
  computer cloni il repository, imposta `harness_repo` con `/config` per scriverle direttamente in `NOTES.md`;
- i permessi consigliati non vengono aggiunti (li applica solo `install.sh`);
- repository privato: l'installazione usa le credenziali git del computer (`git clone` deve funzionare); per gli
  aggiornamenti automatici in background serve `GITHUB_TOKEN` nell'ambiente, altrimenti aggiorna con i comandi sopra.

### Dopo l'installazione
- In una sessione già aperta: `/reload-plugins`.

## Uso quotidiano

| Comando | Quando |
| :- | :- |
| `/core:project-init` | Primo lavoro serio su un repository senza CLAUDE.md |
| `/core:commit` | Commit con Conventional Commits, test e lint prima, mai push |
| `/core:ship` | Push del branch, PR, attesa della CI, merge su `main` solo dopo conferma |
| `/core:handoff` | Fine sessione o cambio computer: aggiorna HANDOFF.md |
| `/core:db-push` | Porta in produzione (Supabase cloud) le migrazioni nuove: controlli, anteprima, conferma, verifica |
| `/core:deploy` | Passi di produzione (Supabase cloud, GHCR, Docker Manager di Hostinger, Nginx Proxy Manager, rollback, diagnosi): per scrivere `docs/deploy.md` o rispondere su server e proxy |
| `/core:security-audit` | Dopo il primo deploy o cambi di Auth, dominio, infrastruttura: audit in sola lettura (login e dominio, RLS, piattaforma, header, segreti, GitHub, configurazione di deploy), correzioni solo dopo conferma |
| `/core:harness-note <lezione>` | Qualcosa da migliorare nell'harness: finisce in `NOTES.md` |
| `/core:harness-review` | Nel repository harness: valuta le note aperte, applica quelle approvate, segna applicata/scartata/rinviata |
| `/modeler:install` | Mette il modellatore in un'app (o lo aggiorna): metamodello dal database se manca, `/admin/model`, `npm run model:*` |
| `/modeler:metamodel <descrizione>` | Metamodello dal prompt, poi migrazione, codice e `model:drift` |
| `/modeler:behavior <descrizione>` | Comportamento dal prompt o dal codice (workflow, guardie, notifiche, testi), poi `sync`, motore e test |
| `/modeler:apply` | Applica le proposte salvate dal modellatore web (sviluppo o produzione) |

Gli agenti `core:code-reviewer` e `core:debugger` vengono usati da Claude quando servono, o su richiesta ("fai rivedere il diff al code-reviewer").

## Cosa fanno gli hook

- **SessionStart**: inietta `plugins/core/context/conventions.md` e lo stato del progetto (branch, file modificati, stack, presenza di CLAUDE.md e HANDOFF.md).
- **PreToolUse su Edit/Write**: blocca la scrittura di `.env*` (tranne `*.example`), chiavi e certificati, interni di `.git/`, e contenuti che sembrano chiavi o token. Chiede conferma se una sessione aperta su un'altra
  cartella modifica file del clone dell'harness (tranne `NOTES.md`, scritto da `/core:harness-note`).
- **PreToolUse su Bash**: blocca `rm -rf /` e simili e il force push su main/master; chiede conferma per `git push`, `reset --hard`, `clean`, `rm -r`, `sudo`, `curl | sh`, lettura di `.env`, `supabase db reset/push`, DDL distruttivo, `--no-verify`.
- **PostToolUse su Edit/Write**: formatta il file con il formatter già configurato nel progetto (prettier locale, ruff o black). Disattivabile con l'opzione `autoformat`.

Gli hook sono Python solo libreria standard: nessuna dipendenza da installare.

## Ciclo di miglioramento

1. Durante il lavoro in qualunque progetto, quando Claude sbaglia qualcosa di ricorrente o manca una regola: `/core:harness-note …`. La nota finisce nel `NOTES.md` di questo clone (opzione `harness_repo` del plugin core, impostata da `install.sh`; senza clone va in `~/.claude/plugins/data/core-iovino-harness/NOTES.md`).
2. Ogni tanto, apri una sessione in questo repository, rivedi `NOTES.md` e trasforma le note in modifiche a `conventions.md`, agli hook o alle skill.
3. `python3 -m unittest discover -s tests`, `python3 -m unittest discover -s plugins/modeler/tests` e `claude plugin validate .`, poi commit.
4. Rilascio e push (sezione seguente).
5. Sugli altri computer: `git pull` (strada A) oppure `claude plugin marketplace update` + `claude plugin update` (strada B).

## Rilasciare una modifica

Ogni push che tocca un plugin ne alza la versione: senza versione nuova `claude plugin update` non scarica nulla
sugli altri computer e le app non vedono che il loro modellatore va aggiornato.

```bash
python3 scripts/release.py           # cosa è cambiato e quale sarebbe la versione nuova
python3 scripts/release.py --write   # alza le versioni e crea il commit chore(release): …
git push
```

- Il livello si deduce dai Conventional Commits che toccano il plugin dall'ultima versione: `feat` → minor,
  `!`/`BREAKING CHANGE` → major (minor finché la versione è 0.x), il resto → patch. `--level patch|minor|major`
  lo forza.
- `release.py` aggiorna anche le copie della versione (`__version__` del modeler).
- L'hook `.githooks/pre-push` blocca il push se un plugin modificato ha ancora la versione vecchia.
- Claude lo fa da solo prima di ogni push (regola nel `CLAUDE.md` di questo repository).
- Dopo un rilascio di `modeler`, nelle app che lo usano lancia `/modeler:install` per aggiornare il modellatore
  copiato nel repository (a inizio sessione l'hook lo ricorda quando le versioni differiscono).

## Struttura

```
.claude-plugin/marketplace.json
plugins/core/
  .claude-plugin/plugin.json
  context/conventions.md        ← le tue convenzioni: modificale qui
  hooks/hooks.json
  scripts/hook.py
  agents/{code-reviewer,debugger}.md
  skills/{project-init,handoff,commit,ship,db-push,deploy,security-audit,harness-note,harness-review}/SKILL.md
plugins/modeler/                ← metamodello e modellatore web delle app (README proprio)
settings/recommended-settings.json, merge_settings.py
scripts/release.py              ← versioni dei plugin a ogni rilascio
.githooks/pre-push              ← blocca il push di un plugin non rilasciato
tests/
install.sh
CLAUDE.md                       ← regole per lavorare su questo repository
NOTES.md                         ← lezioni annotate da /core:harness-note
```
