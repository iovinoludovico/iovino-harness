---
name: harness-review
description: Valuta in modo strutturato le note aperte di NOTES.md nel repository harness - raggruppa le simili, propone per ciascuna la modifica concreta (conventions.md, regola di guard, skill, hook) con pro e contro, applica su un branch solo quelle approvate con test e commit, e segna ogni nota come applicata, scartata o rinviata. Usala quando l'inizio sessione segnala note da valutare, quando l'utente chiede "valutiamo le note", "rivediamo NOTES.md", "applica le note dell'harness", o invoca /core:harness-review.
argument-hint: "[titolo o data di una nota, per valutare solo quella]"
---

# Revisione delle note dell'harness

Filtro dell'utente: $ARGUMENTS (vuoto: tutte le note aperte).

Si lavora dentro il repository harness (`${user_config.harness_repo}`, o la cartella corrente se contiene
`.claude-plugin/marketplace.json` e `plugins/core`). Se non ci sei, dillo e fermati: le note si applicano lì.
Leggi prima `CLAUDE.md` del repository (rilascio, verifica) e `HANDOFF.md` se esiste.

## Stati di una nota

Ogni voce di `NOTES.md` ha una riga `- **Stato**: …` (le voci senza valgono "da valutare"):

| Stato | Significato | Aperta? |
| :- | :- | :- |
| `da valutare` | appena annotata | sì |
| `in parte applicata il <data>: <fatto>. Da fare: <resto>` | applicata solo una parte | sì |
| `applicata il <data>: <cosa, dove, commit o test>` | chiusa | no |
| `scartata il <data>: <motivo>` | chiusa, con la ragione | no |
| `rinviata il <data>: <motivo e condizione per riprenderla>` | in attesa | no, ma si ricorda |

Le voci restano nel file: `NOTES.md` è anche lo storico delle decisioni. Non cancellarle e non riscriverne
il contenuto, cambia solo la riga **Stato** (e aggiungi un caso nuovo se emerge). Una nota con più righe Stato (una
parte applicata prima, poi `- **Stato (parte rimasta)**: …`) vale per l'ultima riga: è quella che l'hook di avvio conta.

## 1. Leggi e raggruppa

- Elenca le note aperte (e, in una riga, le rinviate: la loro condizione per riprenderle si è avverata?).
- Raggruppa quelle che toccano lo stesso punto (stessa skill, stessa sezione di `conventions.md`, stesso hook) o
  che dicono la stessa cosa da progetti diversi: si valutano e si applicano insieme.
- Per ogni gruppo guarda lo stato attuale del codice: la nota può essere già superata da un commit successivo
  (`git log --oneline -- <file>`), e allora si propone di chiuderla come applicata indicando il commit.

## 2. Proponi

Per ogni gruppo mostra all'utente, in modo compatto:

- **Nota/e**: titolo e data.
- **Modifica concreta**: dove (`plugins/core/context/conventions.md` sezione X, regola in `ASK_RULES`/`DENY_RULES` di
  `plugins/core/scripts/hook.py`, skill nuova o esistente, hook, script del modeler) e il testo o il codice
  proposto, abbastanza preciso da essere applicato così com'è.
- **Pro** e **contro** (costo per ogni sessione: le convenzioni entrano nel contesto di tutti i progetti; rischio
  di falsi positivi per una regola di guard; manutenzione di una skill nuova rispetto a estenderne una esistente).
- **Raccomandazione**: applicare, applicare in parte, scartare o rinviare, con una frase di motivo.

Preferisci la modifica più piccola che risolve il caso: una riga in una skill esistente prima di una skill nuova,
una skill prima di una convenzione globale. Poi chiedi la decisione con AskUserQuestion, un gruppo per domanda
(fino a 4 per volta), opzioni: applica (raccomandazione per prima se è questa), scarta, rinvia. Non applicare nulla
che l'utente non abbia approvato.

## 3. Applica quelle approvate

- Branch dedicato da `main` aggiornato: `fix/…` o `feat/…` secondo la modifica (es. `feat/core-harness-review-<tema>`).
  Più gruppi approvati nella stessa revisione possono stare nello stesso branch, ma un commit per gruppo.
- Implementa seguendo i pattern del repository; per un hook o una regola di guard aggiungi il test in
  `tests/test_core_hooks.py`, per il modeler in `plugins/modeler/tests/`.
- Verifica come chiede `CLAUDE.md` (test core, test modeler, `claude plugin validate .`). Se fallisce, correggi o
  riporta il problema: non committare con i test rossi.
- Aggiorna la documentazione toccata (README dei plugin, elenco delle skill).
- Commit in Conventional Commits (in inglese), mostrato prima in un blocco ```text; il corpo cita la nota
  ("Applies the harness note of <data>: <titolo>").

## 4. Segna le decisioni

Per ogni nota valutata aggiorna la riga **Stato** con la data di oggi:

- applicata: cosa è cambiato e dove (file, skill, test), così si ritrova;
- scartata: il motivo dato dall'utente o concordato;
- rinviata: il motivo e la condizione per riprenderla (es. "quando `gh` è installato");
- in parte applicata: cosa è fatto e cosa resta.

Committa l'aggiornamento di `NOTES.md` come `docs: record harness note decisions` (o nello stesso commit della
modifica se riguarda una sola nota).

## 5. Chiudi

- Riepilogo in poche righe: applicate, scartate, rinviate, ancora aperte.
- Ricorda il rilascio: prima di un push `python3 scripts/release.py`, poi `--write` (`/core:release`). Push, PR e merge solo su
  richiesta esplicita.
- Se la revisione cambia lo stato del lavoro sull'harness, proponi di aggiornare `HANDOFF.md` con `core:handoff`.
