# iovino-harness

Marketplace personale di plugin per Claude Code (`core`, `modeler`), installato in place da questo clone con
`./install.sh` e da GitHub (`iovinoludovico/iovino-harness`) sugli altri computer.

## Rilascio (ogni push che tocca un plugin)
- Prima di proporre o fare un push: `python3 scripts/release.py` per vedere cosa cambia, poi
  `python3 scripts/release.py --write` (alza `version` dei plugin modificati, livello dedotto dai Conventional
  Commits, e crea il commit `chore(release): …`); `/core:release` fa i due passi. Senza versione nuova
  `claude plugin update` non arriva sugli altri computer e le app non vedono il modellatore da aggiornare.
- L'hook `.githooks/pre-push` (attivato da `install.sh`) blocca il push di un plugin modificato con la versione
  vecchia. Non aggirarlo con `--no-verify`.
- `plugins/modeler/scripts/metamodel/__init__.py` ripete la versione del modeler: la aggiorna `release.py`, mai a mano.
- Push e tag solo su richiesta esplicita.

## Verifica prima del commit
```bash
python3 -m unittest discover -s tests
python3 -m unittest discover -s plugins/modeler/tests      # MODELER_PG=<dsn> per reverse/drift
claude plugin validate .
```

## Regole
- Le note raccolte da `/core:harness-note` in `NOTES.md` si valutano qui con `/core:harness-review` (l'inizio
  sessione segnala quante sono aperte); ogni nota resta nel file con lo stato applicata, scartata o rinviata.
- Le convenzioni personali sono in `plugins/core/context/conventions.md`: si modificano lì, non in questo file.
