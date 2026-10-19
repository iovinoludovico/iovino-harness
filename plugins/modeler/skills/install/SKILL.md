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
Rilanciare questa skill aggiorna i file del modellatore (editor, wrapper, vista del comportamento, azione, CLI) e
non tocca quelli adattati all'app (`src/lib/modeler/access.ts`, la pagina admin): se `install` segnala
"behavior.yaml found", aggiorna la pagina come dice il punto 4.

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
- tabelle tecniche dell'app da escludere (`--exclude`, e `MODELER_EXCLUDE` per `model:drift`); una singola
  colonna tecnica (es. FK verso una tabella esclusa) si esclude con `tabella.colonna`.
`validate` e `drift` devono dare "OK" e "aligned".

## 3. Installazione
`install <app>` copia o aggiorna:
- `public/modeler/metamodel-editor.js` (editor senza dipendenze),
- `src/components/modeler/metamodel-modeler.tsx` (wrapper React),
- `src/components/modeler/behavior-view.tsx` (il comportamento in sola lettura sotto l'editor: ruoli, workflow con
  stati e transizioni, attributi calcolati con la formula, eventi, reazioni; compare solo se la pagina passa
  `behavior.json`),
- `src/components/modeler/workflow-view.tsx` (`<WorkflowView>`: il diagramma degli stati del workflow di un'entità con
  lo stato corrente del record evidenziato, per le pagine di dettaglio dell'app; disegnato dall'elemento
  `<workflow-view>` di `metamodel-editor.js`),
- `src/lib/modeler/metamodel-actions.ts` (salva, elenca e scarta le proposte: file in sviluppo, tabella in produzione),
- `src/lib/modeler/access.ts` (solo se manca: chi è admin e quale client Supabase usare),
- `src/lib/modeler/metamodel.json` (il metamodello letto dalla pagina),
- `docs/DOMAIN.md` (la descrizione del dominio generata dal metamodello; si rigenera con `npm run model:sync`).
  Se in `docs/` c'è già un `domain.md` con altre maiuscole (le app nate con appforge), `install` non scrive
  `DOMAIN.md` e lo dice: rinominalo (es. `docs/behavior.md`) aggiornando i riferimenti in `CLAUDE.md` e README, o
  cancellalo se `DOMAIN.md` lo sostituisce, poi `npm run model:sync`,
- `tools/modeler/` (la CLI, con `VERSION`) e gli script `model:*` in `package.json`,
- `supabase/migrations/<ts>_model_change_requests.sql` (solo la prima volta; ha la colonna `behavior jsonb` per le
  proposte che portano il comportamento). In un'app installata prima di questa colonna aggiungi una migrazione con
  `alter table public.model_change_requests add column if not exists behavior jsonb;` (il modellatore in
  produzione lo segnala salvando "senza il comportamento" finché manca).

## 4. Adattamento all'app (solo alla prima installazione)
- `access.ts`: usa il controllo admin e il client Supabase server dell'app (l'import di default è
  `@/lib/supabase/server`, il controllo di default la RPC `is_admin`).
- Nella migrazione `model_change_requests`, sostituisci `public.is_admin()` con il predicato admin dell'app se
  si chiama diversamente (la migrazione non è ancora applicata: si può modificare).
- Pagina admin: parti da `${CLAUDE_PLUGIN_ROOT}/kit/next/page.tsx` e mettila nell'area admin dell'app (es.
  `src/app/(admin)/admin/model/page.tsx`), con layout, titolo e traduzioni dell'app; aggiungi il link nella
  navigazione admin. `lang` segue la lingua dell'utente.
- Se l'app ha `behavior.yaml`: nella pagina togli il commento a `import behavior from "@/lib/modeler/behavior.json"`
  e passa `behavior={behavior}` a `<MetamodelModeler>`: nel diagramma la classe con workflow ha la testata «workflow»
  e, quando è selezionata, il diagramma degli stati in un pannello sotto la tela, gli attributi calcolati
  hanno il prefisso `/` (formula nel tooltip e nel pannello), l'attributo di stato il segno `⟳`, le feature usate dal
  comportamento ` ·ƒ` (tooltip «usato da»), le classi coinvolte senza workflow `ƒ` in testata, con una legenda dei tre
  livelli; sotto l'editor compare il comportamento e la classe selezionata evidenzia il suo workflow. `install` lo segnala ("behavior.yaml found: …") finché la
  pagina non lo passa, anche nelle reinstallazioni. Nel pannello del workflow e nella barra laterale si modificano
  stati, transizioni, ritorno, formule dei derivati, eventi, ruoli e reazioni: «Salva» produce una proposta con
  metamodello e comportamento, che `/modeler:apply` porta in `domain.ecore.yaml` e `behavior.yaml`.
- Se l'app ha `behavior.yaml`, nella pagina di dettaglio di un record di una classe con workflow aggiungi il diagramma
  degli stati con lo stato corrente: `import behavior from "@/lib/modeler/behavior.json"` e
  `<WorkflowView behavior={behavior} entity="<Classe>" state={record.<attributo di stato>} lang="…" />`
  (`@/components/modeler/workflow-view`), sopra le azioni di transizione; non compare se la classe non ha workflow.
  Lo stato corrente è riempito del suo colore, le transizioni che ne partono sono a piena forza, le altre attenuate;
  il diagramma si adatta alla larghezza del contenitore e sotto la larghezza minima scorre in orizzontale: con
  workflow lunghi (10+ stati) mettilo a tutta larghezza.
  Se la pagina ha già una vista del workflow scritta a mano (un percorso degli stati, `StatePath` o simile), non
  metterle una sotto l'altra: due schede con il componente a schede dell'app (es. `Tabs` di shadcn), quella esistente
  predefinita («Percorso») e `<WorkflowView>` nella seconda («Diagramma»); la scheda scelta si ricorda per utente in
  `localStorage` come comodità, mai come stato condiviso; sostituire la vista esistente è una decisione dell'utente.
  ```tsx
  "use client";
  // Workflow of the record: the app's own path first, the full diagram in the second tab
  const KEY = "workflow-tab";
  export function WorkflowTabs({ path, diagram }: { path: ReactNode; diagram: ReactNode }) {
    const [tab, setTab] = useState("path");
    useEffect(() => { try { const t = localStorage.getItem(KEY); if (t === "diagram") setTab(t); } catch {} }, []);
    const pick = (t: string) => { setTab(t); try { localStorage.setItem(KEY, t); } catch {} };
    return (
      <Tabs value={tab} onValueChange={pick}>
        <TabsList><TabsTrigger value="path">Percorso</TabsTrigger><TabsTrigger value="diagram">Diagramma</TabsTrigger></TabsList>
        <TabsContent value="path">{path}</TabsContent>
        <TabsContent value="diagram">{diagram}</TabsContent>
      </Tabs>
    );
  }
  // nella pagina: <WorkflowTabs path={<StatePath … />} diagram={<WorkflowView behavior={behavior} entity="Order" state={row.status} lang="it" />} />
  ```
- `tsconfig.json` deve avere `resolveJsonModule` (la pagina importa `metamodel.json`, e `behavior.json` se c'è).
- `.gitignore`: `install` aggiunge `__pycache__/` (il bytecode della CLI in `tools/modeler/`); non ignorare
  `.modeler/proposals/` (le proposte si rivedono nel repository).
- In `CLAUDE.md` dell'app: "Il metamodello del dominio è `domain.ecore.yaml`: ogni modifica di schema parte da
  lì (/modeler:metamodel) insieme alla migrazione; `npm run model:sync` aggiorna il modellatore,
  `npm run model:drift` deve dare 'aligned'. Le proposte del modellatore si applicano con /modeler:apply.
  `docs/DOMAIN.md` è generato dal metamodello: lì si annotano a mano dettagli e regole da portare nel metamodello
  (/modeler:metamodel), mai la struttura." Se l'app formatta `docs/` con Prettier, aggiungi `docs/DOMAIN.md` a
  `.prettierignore`.
- Proponi uno step di CI che applica le migrazioni a un database temporaneo ed esegue
  `npm run model:validate` e `MODELER_DB=<dsn> npm run model:drift`.
- Logica scritta a mano che il metamodello non esprime (workflow, regole, pagine speciali): elencala in
  `docs/customizations.md` (id, perché il modello non basta, elementi coinvolti, file, verifica) e marca il
  codice con `CUSTOM(<id>)`; conferma l'elenco con l'utente.

## 5. Verifica
`npm run model:validate`, `npm run model:drift` (con il database locale avviato e la migrazione applicata),
typecheck, lint, test e build dell'app; poi apri `/admin/model` in sviluppo, fai una modifica e salva:
deve comparire un file in `.modeler/proposals/`; se c'è un workflow, apri il dettaglio di un record a due larghezze
(desktop e telefono) e controlla che il diagramma mostri lo stato corrente e scorra invece di stringersi. Prima del deploy, la migrazione `model_change_requests` va
applicata al cloud con `/core:db-push`.
