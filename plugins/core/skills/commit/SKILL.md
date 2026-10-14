---
name: commit
description: Prepara e crea un commit secondo le convenzioni (Conventional Commits, test e lint verdi, niente segreti, niente push). Usala quando l'utente chiede di committare o di "salvare il lavoro" in git.
argument-hint: "[messaggio o ambito]"
disable-model-invocation: true
---

# Commit

Indicazioni dell'utente: $ARGUMENTS

## 1. Guarda cosa c'è

- `git status --short` e `git diff` (più `git diff --cached` se c'è già roba in stage).
- Se sei su `main`/`master` e la modifica non è banale, proponi di creare prima un branch `feat/…` o `fix/…`.
- Se le modifiche riguardano argomenti diversi, proponi di dividerle in più commit e mettili in stage per gruppi (`git add <file>`; mai `git add -A` alla cieca).

## 2. Controlla prima di committare

- Nessun segreto nel diff: file `.env*` (tranne gli `.example`), chiavi, token, password. Se ne trovi, fermati e avvisa.
- Nessun file spurio: build, `node_modules`, log, dump, file di editor. Se servono, suggerisci di aggiungerli a `.gitignore`.
- Esegui i controlli che il progetto prevede (vedi CLAUDE.md o gli script): lint, type-check, test pertinenti. Se falliscono, non committare: riporta l'errore e proponi la correzione.

## 3. Messaggio

Formato Conventional Commits, in inglese:

```
<type>(<scope opzionale>): <imperative summary, max ~72 chars>

<body: why the change, not what; wrap at 72>
```

Tipi: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`. Usa `!` e `BREAKING CHANGE:` solo per rotture reali. Se il repository ha istruzioni proprie sulle righe finali del messaggio (attribuzione, ticket), seguile.

Mostra all'utente il messaggio in un blocco ```text copiabile (stesso formato, un blocco per commit). Crea il commit
con `git commit -F -` passando esattamente quel messaggio via heredoc, così le virgolette non creano problemi; se
l'utente lo ha modificato, usa il suo.

## 4. Non fare

- Niente `git push`, `--amend` su commit già pubblicati, `--no-verify`, tag o rebase, a meno che l'utente non lo chieda esplicitamente in questa richiesta.

Alla fine mostra `git log --oneline -3` e una riga su cosa è stato committato.
