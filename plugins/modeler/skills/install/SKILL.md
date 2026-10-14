---
name: install
description: Rende il modellatore web del dominio parte integrante di un'app Next.js + Supabase (nuova o esistente) - ricava domain.ecore.yaml dal database se manca, installa nel repository editor, pagina /admin/model, salvataggio delle proposte, tabella model_change_requests e la CLI con gli script npm model:*, e imposta il controllo di allineamento tra metamodello e database. Va usata quando l'utente vuole il modellatore o il metamodello in un'app ("aggiungi il modellatore", "ricava il metamodello dal database", "non vedo il modellatore"), quando la sessione segnala un modellatore da aggiornare, o invoca /modeler:install.
argument-hint: "[cartella dell'app] [DSN del database locale]"
---

# Installare (o aggiornare) il modellatore in un'app

Argomenti: `$ARGUMENTS`. CLI del plugin: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/modeler.py" …`.
Lavora su un branch (`feat/modeler`), non toccare mai i file `.env*`. Leggi prima `CLAUDE.md` dell'app e le
pagine della sua area admin.

Dopo l'installazione il modellatore appartiene all'app: editor, wrapper React, azione server e CLI
(`tools/modeler/`, con gli script `npm run model:*`) sono nel repository e funzionano senza il plugin.
Rilanciare questa skill aggiorna i file del modellatore (editor, wrapper, azione, CLI) e non tocca quelli
adattati all'app (`src/lib/modeler/access.ts`, la pagina admin).

## 1. Database da leggere (solo se manca `domain.ecore.yaml`)
Di solito il Supabase locale dell'app: `supabase start`, poi il DSN con la porta di `[db]` in
`supabase/config.toml` (la CLI la ricava da sola se ometti `--db`). Se non è avviato chiedi all'utente di
avviarlo; mai un database di produzione senza permesso esplicito.

## 2. Metamodello dal database (solo se manca)
`reverse --package <nome> -o domain.ecore.yaml [--db <DSN>] [--exclude <tabelle infrastrutturali>]`, poi
rivedilo **con l'utente**:
- nomi di classi e feature (rinomina liberamente: `column:` mantiene il legame con la colonna);
- containment dedotti da `on delete cascade`, molti-a-molti dalle join table, enum dai `check (… in …)`;
- `language: it` se i nomi sono italiani; `doc`/`label` per le classi principali;
- tabelle tecniche dell'app da escludere (`--exclude`, e `MODELER_EXCLUDE` per `model:drift`).
`validate` e `drift` devono dare "OK" e "aligned".

## 3. Installazione
`install <app>` copia o aggiorna:
- `public/modeler/metamodel-editor.js` (editor senza dipendenze),
- `src/components/modeler/metamodel-modeler.tsx` (wrapper React),
- `src/lib/modeler/metamodel-actions.ts` (salva le proposte: file in sviluppo, tabella in produzione),
- `src/lib/modeler/access.ts` (solo se manca: chi è admin e quale client Supabase usare),
- `src/lib/modeler/metamodel.json` (il metamodello letto dalla pagina),
- `tools/modeler/` (la CLI, con `VERSION`) e gli script `model:*` in `package.json`,
- `supabase/migrations/<ts>_model_change_requests.sql` (solo la prima volta).

## 4. Adattamento all'app (solo alla prima installazione)
- `access.ts`: usa il controllo admin e il client Supabase server dell'app (l'import di default è
  `@/lib/supabase/server`, il controllo di default la RPC `is_admin`).
- Nella migrazione `model_change_requests`, sostituisci `public.is_admin()` con il predicato admin dell'app se
  si chiama diversamente (la migrazione non è ancora applicata: si può modificare).
- Pagina admin: parti da `${CLAUDE_PLUGIN_ROOT}/kit/next/page.tsx` e mettila nell'area admin dell'app (es.
  `src/app/(admin)/admin/model/page.tsx`), con layout, titolo e traduzioni dell'app; aggiungi il link nella
  navigazione admin. `lang` segue la lingua dell'utente.
- `tsconfig.json` deve avere `resolveJsonModule` (la pagina importa `metamodel.json`).
- `.gitignore`: non ignorare `.modeler/proposals/` (le proposte si rivedono nel repository).
- In `CLAUDE.md` dell'app: "Il metamodello del dominio è `domain.ecore.yaml`: ogni modifica di schema parte da
  lì (/modeler:metamodel) insieme alla migrazione; `npm run model:sync` aggiorna il modellatore,
  `npm run model:drift` deve dare 'aligned'. Le proposte del modellatore si applicano con /modeler:apply."
- Proponi uno step di CI che applica le migrazioni a un database temporaneo ed esegue
  `npm run model:validate` e `MODELER_DB=<dsn> npm run model:drift`.
- Logica scritta a mano che il metamodello non esprime (workflow, regole, pagine speciali): elencala in
  `docs/customizations.md` (id, perché il modello non basta, elementi coinvolti, file, verifica) e marca il
  codice con `CUSTOM(<id>)`; conferma l'elenco con l'utente.

## 5. Verifica
`npm run model:validate`, `npm run model:drift` (con il database locale avviato e la migrazione applicata),
typecheck, lint, test e build dell'app; poi apri `/admin/model` in sviluppo, fai una modifica e salva:
deve comparire un file in `.modeler/proposals/`.
