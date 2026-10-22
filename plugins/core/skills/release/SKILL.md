---
name: release
description: Nel repository harness alza la versione dei plugin modificati e crea il commit chore(release) con scripts/release.py - prima la prova a vuoto, poi --write - così il push passa l'hook pre-push e `claude plugin update` arriva sugli altri computer. Usala quando l'utente dice "fai il rilascio", "alza la versione", "release --write", o invoca /core:release. Non fa push: per pubblicare c'è /core:ship, che include questo passo.
argument-hint: "[--level patch|minor|major]"
disable-model-invocation: true
---

# Release dei plugin dell'harness

Argomenti: `$ARGUMENTS` (`--level patch|minor|major` forza il livello invece di dedurlo dai commit).

Invocare `/core:release` vale come richiesta esplicita di **alzare le versioni e creare il commit di rilascio**, non di
push, tag o PR: per quelli `/core:ship`, che esegue anche questo passo prima del push.

## 1. Precondizioni (fermati se una manca e spiega cosa fare)
- Repository harness: la cartella corrente ha `scripts/release.py`, `.claude-plugin/marketplace.json` e `plugins/core`.
- Albero pulito (`git status --porcelain`): il commit di rilascio contiene solo le versioni, e lo script si rifiuta
  con modifiche in sospeso in un plugin («Commit the changes of the plugins first»). Proponi `/core:commit`.
- Branch diverso da `main`: il rilascio accompagna i commit del branch nella stessa PR. Su `main` proponi un branch
  (`fix/…`, `feat/…`), salvo richiesta esplicita.

## 2. Prova a vuoto
- `python3 scripts/release.py` (con `--level` se dato) e mostra l'output: per ogni plugin versione attuale → nuova,
  livello e numero di commit dall'ultima versione.
- «Nothing to release»: nessun plugin cambiato dall'ultima versione. Dillo e fermati: niente commit vuoto.
- Se il livello dedotto non corrisponde al contenuto del branch (una `feat` registrata come `fix`, o il contrario),
  segnalalo: si corregge con `--level`, non riscrivendo i commit.

## 3. Scrittura
- `python3 scripts/release.py --write` (con `--level` se dato): alza `version` in `plugin.json` e nelle copie
  (`__version__` del modeler) e crea `chore(release): …`. Mostra `git log --oneline -1` e `git show --stat HEAD`.
- Niente versioni a mano: se lo script fallisce, riporta l'errore e fermati.

## 4. Chiudi
- Riepilogo: versioni nuove e commit, in due righe.
- Il push resta su richiesta: `/core:ship` (push, PR, merge solo dopo conferma). Dopo il merge: `/reload-plugins` qui
  e, se è cambiato `modeler`, `/modeler:install` nelle app che lo usano.

## Non fare
- Push, tag, `--no-verify`; versioni modificate a mano; rilascio con albero sporco o test rossi (i test del
  `CLAUDE.md` si eseguono prima, con `/core:commit` o `/core:ship`).
