/*
 * <metamodel-editor> — framework-free editor of an appforge domain metamodel (Ecore notation).
 *
 * Used by the admin area of every app (Next.js wrapper in modeler/next/) and by the appforge Studio.
 *
 *   const el = document.querySelector("metamodel-editor");
 *   el.metamodel = json;            // canonical form: `appforge metamodel show --format json`
 *   el.readonly = false;
 *   el.addEventListener("change", (e) => e.detail.metamodel);
 *   el.addEventListener("save", (e) => { e.detail.metamodel; e.detail.note; });
 *
 * Attributes: lang="it|en", save-label="…", readonly.
 * The diagram positions are kept in metamodel.diagram ({Class: {x, y}}).
 */
(() => {
  if (customElements.get("metamodel-editor")) return;

  const DATATYPES = ["EString", "Text", "Email", "URL", "EInt", "ELong", "EDouble", "EBigDecimal", "Money",
    "EBoolean", "Date", "EDate", "JSON"];
  const MULTS = [["0..1", 0, 1], ["1", 1, 1], ["0..*", 0, -1], ["1..*", 1, -1]];
  const CLASS_RE = /^[A-Z][A-Za-z0-9]{1,39}$/;
  const FEATURE_RE = /^[a-z][A-Za-z0-9_]{0,39}$/;
  const LITERAL_RE = /^[A-Za-z][A-Za-z0-9_]{0,39}$/;
  const RESERVED = ["id", "state", "createdBy", "createdAt", "updatedAt", "created_by", "created_at", "updated_at", "data", "entity", "type"];
  const BOX_W = 210, HEAD_H = 30, ROW_H = 18, PAD = 8;

  const T = {
    it: {
      addClass: "Classe", addEnum: "Enum", layout: "Riordina", fit: "Adatta", save: "Salva", note: "Nota sulla modifica",
      issues: "problemi", ok: "Metamodello valido", name: "Nome", abstract: "Astratta", supertypes: "Supertipi",
      doc: "Descrizione", label: "Etichetta", attributes: "Attributi", references: "Riferimenti", literals: "Letterali",
      add: "Aggiungi", del: "Elimina", type: "Tipo", mult: "Molt.", id: "ID", target: "Classe", containment: "Contiene",
      opposite: "Opposto", none: "—", select: "Seleziona una classe o un'enum nel diagramma, oppure aggiungine una.",
      confirmDelete: "Eliminare", package: "Package", readonly: "Sola lettura", users: "User = utenti dell'applicazione",
      dupName: "nome già usato", badName: "nome non valido", reserved: "colonna standard", noTarget: "classe di destinazione mancante",
      oppBroken: "opposto non coerente", bothCont: "entrambi i lati sono contenimenti", noLiterals: "nessun letterale",
      cycle: "ciclo di ereditarietà", newClass: "NuovaClasse", newEnum: "NuovaEnum",
      workflow: "Workflow", states: "Stati", transitions: "Transizioni", events: "Eventi", reactions: "Reazioni",
      webhooks: "Webhook (n8n)", views: "Viste UI", usedBy: "usato da", warnings: "avvisi", by: "da", timed: "a tempo",
      behaviourHint: "Il comportamento è definito in app.yaml: qui è mostrato collegato alla classe.",
    },
    en: {
      addClass: "Class", addEnum: "Enum", layout: "Layout", fit: "Fit", save: "Save", note: "Change note",
      issues: "issues", ok: "Valid metamodel", name: "Name", abstract: "Abstract", supertypes: "Supertypes",
      doc: "Description", label: "Label", attributes: "Attributes", references: "References", literals: "Literals",
      add: "Add", del: "Delete", type: "Type", mult: "Mult.", id: "ID", target: "Class", containment: "Contains",
      opposite: "Opposite", none: "—", select: "Select a class or an enum in the diagram, or add one.",
      confirmDelete: "Delete", package: "Package", readonly: "Read only", users: "User = the application users",
      dupName: "name already used", badName: "invalid name", reserved: "standard column", noTarget: "missing target class",
      oppBroken: "inconsistent opposite", bothCont: "both ends are containments", noLiterals: "no literals",
      cycle: "inheritance cycle", newClass: "NewClass", newEnum: "NewEnum",
      workflow: "Workflow", states: "States", transitions: "Transitions", events: "Events", reactions: "Reactions",
      webhooks: "Webhooks (n8n)", views: "UI views", usedBy: "used by", warnings: "warnings", by: "by", timed: "timed",
      behaviourHint: "Behaviour is defined in app.yaml: shown here linked to the class.",
    },
  };

  const css = `
:host { --bg:#fff; --fg:#1f2937; --muted:#6b7280; --line:#d1d5db; --panel:#f9fafb; --accent:#2563eb; --head:#eef2ff;
  --enum:#fef3c7; --err:#dc2626; --ok:#16a34a; display:block; font:13px/1.4 system-ui,sans-serif; color:var(--fg); }
@media (prefers-color-scheme: dark) { :host { --bg:#111827; --fg:#e5e7eb; --muted:#9ca3af; --line:#374151;
  --panel:#1f2937; --head:#1e293b; --enum:#3b2f12; --accent:#60a5fa; } }
:host([theme="light"]) { --bg:#fff; --fg:#1f2937; --muted:#6b7280; --line:#d1d5db; --panel:#f9fafb; --head:#eef2ff; --enum:#fef3c7; --accent:#2563eb; }
:host([theme="dark"]) { --bg:#111827; --fg:#e5e7eb; --muted:#9ca3af; --line:#374151; --panel:#1f2937; --head:#1e293b; --enum:#3b2f12; --accent:#60a5fa; }
* { box-sizing:border-box; }
.wrap { display:grid; grid-template-rows:auto 1fr; height:100%; min-height:520px; border:1px solid var(--line); border-radius:8px; overflow:hidden; background:var(--bg); }
.bar { display:flex; gap:6px; align-items:center; padding:6px 8px; border-bottom:1px solid var(--line); background:var(--panel); flex-wrap:wrap; }
.bar .grow { flex:1; }
button { font:inherit; border:1px solid var(--line); background:var(--bg); color:var(--fg); border-radius:6px; padding:4px 10px; cursor:pointer; }
button:hover { border-color:var(--accent); }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
button.danger { color:var(--err); }
button:disabled { opacity:.5; cursor:default; }
input, select, textarea { font:inherit; color:var(--fg); background:var(--bg); border:1px solid var(--line); border-radius:4px; padding:3px 5px; min-width:0; }
input[type=checkbox] { padding:0; }
.status { font-size:12px; color:var(--muted); cursor:pointer; }
.status.bad { color:var(--err); } .status.good { color:var(--ok); }
.main { display:grid; grid-template-columns:1fr 340px; min-height:0; }
.canvas { position:relative; overflow:hidden; min-height:0; cursor:grab; }
.canvas svg { width:100%; height:100%; display:block; user-select:none; }
.side { border-left:1px solid var(--line); background:var(--panel); overflow:auto; padding:10px; }
.side h3 { margin:12px 0 6px; font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
.side h3:first-child { margin-top:0; }
.row { display:grid; gap:4px; align-items:center; margin-bottom:4px; }
.attr { grid-template-columns:1fr 92px 58px 22px 22px; }
.ref { grid-template-columns:1fr 92px 58px; }
.ref2 { grid-template-columns:auto 1fr 22px; margin:-2px 0 8px 8px; font-size:12px; color:var(--muted); }
.lit { grid-template-columns:1fr 1fr 22px; }
.field { display:grid; grid-template-columns:90px 1fr; gap:6px; align-items:center; margin-bottom:6px; }
.x { padding:0 4px; border:none; background:none; color:var(--muted); }
.x:hover { color:var(--err); }
.hint { color:var(--muted); font-size:12px; }
.issues { position:absolute; right:8px; top:8px; max-width:420px; background:var(--bg); border:1px solid var(--line); border-radius:6px; padding:8px 10px; font-size:12px; box-shadow:0 4px 16px rgba(0,0,0,.12); z-index:2; }
.issues div { color:var(--err); }
.box rect.body { fill:var(--bg); stroke:var(--line); }
.box.sel rect.body { stroke:var(--accent); stroke-width:2; }
.box rect.head { fill:var(--head); }
.box.enum rect.head { fill:var(--enum); }
.box text { fill:var(--fg); font-size:12px; }
.box text.title { font-weight:600; }
.box text.abstract { font-style:italic; }
.box text.stereo, .box text.muted { fill:var(--muted); font-size:11px; }
.box { cursor:move; }
.edge { stroke:var(--muted); fill:none; stroke-width:1.3; }
.edge.inherit { stroke-dasharray:none; }
.elabel { fill:var(--muted); font-size:11px; }
.mk-open { fill:var(--bg); stroke:var(--muted); }
.chips { display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px; }
.chip { border-radius:999px; padding:1px 8px; font-size:11px; color:#fff; }
.chip.plain { background:var(--bg); color:var(--fg); border:1px solid var(--line); }
.tr { font-size:12px; margin:0 0 4px; }
.tr b { font-weight:600; }
.status.warn { color:#d97706; }
.issues div.w { color:#b45309; }
.mk-fill { fill:var(--muted); }
@media (max-width: 760px) { .main { grid-template-columns:1fr; grid-template-rows:1fr auto; } .side { border-left:none; border-top:1px solid var(--line); max-height:50%; } }
`;

  const clone = (o) => JSON.parse(JSON.stringify(o));
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else if (k === "checked" || k === "disabled" || k === "value") n[k] = v;
      else if (v !== undefined && v !== null && v !== false) n.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined) n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return n;
  };
  const svg = (tag, attrs = {}, ...kids) => {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) n.setAttribute(k, v);
    for (const kid of kids.flat()) if (kid) n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return n;
  };
  const add = (parent, ...kids) => parent.append(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false));
  const multText = (lo, up) => (lo === 1 && up === 1 ? "1" : `${lo}..${up === -1 ? "*" : up}`);
  const multKey = (lo, up) => MULTS.find((m) => m[1] === lo && m[2] === up)?.[0] ?? "0..1";
  const snake = (s) => s.replace(/(?<=[a-z0-9])([A-Z])/g, "_$1").toLowerCase();

  class MetamodelEditor extends HTMLElement {
    constructor() {
      super();
      this._mm = { package: "domain", classes: {}, enums: {}, diagram: {} };
      this._orig = null;
      this._sel = null;
      this._view = { x: 0, y: 0, k: 1 };
      this._showIssues = false;
      this.attachShadow({ mode: "open" });
    }

    static get observedAttributes() { return ["lang", "readonly", "save-label"]; }
    attributeChangedCallback() { if (this.isConnected) this._render(); }
    connectedCallback() { this._render(); }

    get t() { return T[(this.getAttribute("lang") || "it").slice(0, 2)] || T.it; }
    get readonly() { return this.hasAttribute("readonly"); }
    set readonly(v) { if (v) this.setAttribute("readonly", ""); else this.removeAttribute("readonly"); }

    set metamodel(mm) {
      const m = clone(mm || {});
      m.classes = m.classes || {};
      m.enums = m.enums || {};
      m.diagram = m.diagram || {};
      for (const c of Object.values(m.classes)) {
        c.attributes = c.attributes || {};
        c.references = c.references || {};
        c.supertypes = c.supertypes || [];
        c.abstract = !!c.abstract;
        for (const a of Object.values(c.attributes)) { a.lower = a.lower ?? 0; a.upper = a.upper ?? 1; }
        for (const r of Object.values(c.references)) { r.lower = r.lower ?? 0; r.upper = r.upper ?? 1; r.containment = !!r.containment; }
      }
      for (const [n, e] of Object.entries(m.enums)) {
        if (Array.isArray(e)) m.enums[n] = { literals: e.map((x) => (typeof x === "string" ? { name: x } : x)) };
        else e.literals = (e.literals || []).map((x) => (typeof x === "string" ? { name: x } : x));
      }
      this._mm = m;
      this._orig = clone(m);
      this._sel = null;
      this._autoLayout(false);
      this._render();
      requestAnimationFrame(() => this._fit());
    }
    get metamodel() { return clone(this._mm); }
    getMetamodel() { return this.metamodel; }

    /* ------------------------------------------------------------------ model edits */
    _schedule() {
      if (this._pending) return;
      this._pending = true;
      setTimeout(() => { this._pending = false; this._render(); }, 0);
    }
    _changed() {
      this._schedule();
      this.dispatchEvent(new CustomEvent("change", { detail: { metamodel: this.metamodel, issues: this._issues() } }));
    }

    _uniqueName(base, taken) { let n = base, i = 2; while (taken.includes(n)) n = base + i++; return n; }
    _allNames() { return [...Object.keys(this._mm.classes), ...Object.keys(this._mm.enums), "User"]; }

    _addClass() {
      const name = this._uniqueName(this.t.newClass, this._allNames());
      this._mm.classes[name] = { abstract: false, supertypes: [], attributes: { name: { type: "EString", lower: 1, upper: 1 } }, references: {} };
      this._mm.diagram[name] = this._freeSpot();
      this._sel = { kind: "class", name };
      this._changed();
    }
    _addEnum() {
      const name = this._uniqueName(this.t.newEnum, this._allNames());
      this._mm.enums[name] = { literals: [{ name: "first" }, { name: "second" }] };
      this._mm.diagram[name] = this._freeSpot();
      this._sel = { kind: "enum", name };
      this._changed();
    }
    _freeSpot() {
      const used = Object.values(this._mm.diagram);
      const r = this.shadowRoot.querySelector(".canvas")?.getBoundingClientRect();
      const cx = ((r?.width || 800) / 2 - this._view.x) / this._view.k - BOX_W / 2;
      const cy = ((r?.height || 500) / 3 - this._view.y) / this._view.k;
      let x = cx, y = cy;
      while (used.some((p) => Math.abs(p.x - x) < 40 && Math.abs(p.y - y) < 40)) { x += 30; y += 30; }
      return { x: Math.round(x), y: Math.round(y) };
    }

    _renameClass(old, name) {
      if (old === name || !name) return;
      const mm = this._mm;
      const rebuilt = {};
      for (const [k, v] of Object.entries(mm.classes)) rebuilt[k === old ? name : k] = v;
      mm.classes = rebuilt;
      for (const c of Object.values(mm.classes)) {
        c.supertypes = c.supertypes.map((s) => (s === old ? name : s));
        for (const r of Object.values(c.references)) if (r.type === old) r.type = name;
      }
      if (mm.diagram[old]) { mm.diagram[name] = mm.diagram[old]; delete mm.diagram[old]; }
      this._sel = { kind: "class", name };
    }
    _renameEnum(old, name) {
      if (old === name || !name) return;
      const mm = this._mm;
      const rebuilt = {};
      for (const [k, v] of Object.entries(mm.enums)) rebuilt[k === old ? name : k] = v;
      mm.enums = rebuilt;
      for (const c of Object.values(mm.classes)) for (const a of Object.values(c.attributes)) if (a.type === old) a.type = name;
      if (mm.diagram[old]) { mm.diagram[name] = mm.diagram[old]; delete mm.diagram[old]; }
      this._sel = { kind: "enum", name };
    }
    _renameFeature(cname, kind, old, name) {
      if (old === name || !name) return;
      const c = this._mm.classes[cname];
      const rebuilt = {};
      for (const [k, v] of Object.entries(c[kind])) rebuilt[k === old ? name : k] = v;
      c[kind] = rebuilt;
      const f = c[kind][name];
      const origClass = this._orig?.classes?.[cname];
      if (origClass?.[kind]?.[old] && !f.renamed_from) f.renamed_from = old;   // keeps the data in generated apps
      if (f.renamed_from === name) delete f.renamed_from;
      if (kind === "references" && f.opposite) {
        const o = this._mm.classes[f.type]?.references?.[f.opposite];
        if (o) o.opposite = name;
      }
    }
    _setOpposite(cname, rname, opp) {
      const c = this._mm.classes[cname];
      const r = c.references[rname];
      const target = this._mm.classes[r.type];
      if (r.opposite && target?.references?.[r.opposite]) delete target.references[r.opposite].opposite;
      if (!opp) { delete r.opposite; return; }
      const o = target.references[opp];
      if (o.opposite && this._mm.classes[o.type]?.references?.[o.opposite]) delete this._mm.classes[o.type].references[o.opposite].opposite;
      r.opposite = opp;
      o.opposite = rname;
      if (r.containment && o.containment) o.containment = false;
    }
    _deleteClass(name) {
      const mm = this._mm;
      delete mm.classes[name];
      delete mm.diagram[name];
      for (const c of Object.values(mm.classes)) {
        c.supertypes = c.supertypes.filter((s) => s !== name);
        for (const [rn, r] of Object.entries(c.references)) if (r.type === name) delete c.references[rn];
      }
      this._sel = null;
    }
    _deleteEnum(name) {
      const mm = this._mm;
      delete mm.enums[name];
      delete mm.diagram[name];
      for (const c of Object.values(mm.classes)) for (const a of Object.values(c.attributes)) if (a.type === name) { a.type = "EString"; delete a.default; }
      this._sel = null;
    }

    _ancestors(name, seen = []) {
      const c = this._mm.classes[name];
      if (!c) return seen;
      for (const s of c.supertypes) {
        if (seen.includes(s)) continue;
        seen.push(s);
        this._ancestors(s, seen);
      }
      return seen;
    }

    /* ------------------------------------------------------------------ behaviour links */
    _columns(cn) {
      const cols = new Set();
      const visit = (n, seen = []) => {
        const c = this._mm.classes[n];
        if (!c || seen.includes(n)) return;
        for (const [fn, f] of [...Object.entries(c.attributes), ...Object.entries(c.references)]) cols.add(f.column || snake(fn));
        c.supertypes.forEach((s2) => visit(s2, [...seen, n]));
      };
      visit(cn);
      for (const [on, oc] of Object.entries(this._mm.classes)) {
        for (const r of Object.values(oc.references)) if (r.containment && r.type === cn && !r.opposite) cols.add(snake(on));
      }
      return cols;
    }
    _warnings() {
      const t = this.t, out = [];
      const beh = this._mm.behaviour?.classes || {};
      for (const [cn, b] of Object.entries(beh)) {
        if (!this._mm.classes[cn]) { if (b.workflow || b.reactions?.length) out.push(`${cn}: ${t.usedBy} app.yaml (${t.workflow})`); continue; }
        const cols = this._columns(cn);
        for (const [f, where] of Object.entries(b.uses || {})) if (!cols.has(f)) out.push(`${cn}.${f}: ${t.usedBy} ${where.join(", ")}`);
      }
      return out;
    }

    /* ------------------------------------------------------------------ validation */
    _issues() {
      const t = this.t, mm = this._mm, out = [];
      const names = [...Object.keys(mm.classes), ...Object.keys(mm.enums)];
      for (const n of names) {
        if (!CLASS_RE.test(n)) out.push(`${n}: ${t.badName}`);
        if (names.filter((x) => x === n).length > 1 || n === "User") out.push(`${n}: ${t.dupName}`);
      }
      for (const [en, e] of Object.entries(mm.enums)) {
        if (!e.literals.length) out.push(`${en}: ${t.noLiterals}`);
        const ln = e.literals.map((l) => l.name);
        for (const l of ln) {
          if (!LITERAL_RE.test(l)) out.push(`${en}.${l}: ${t.badName}`);
          if (ln.filter((x) => x === l).length > 1) out.push(`${en}.${l}: ${t.dupName}`);
        }
      }
      for (const [cn, c] of Object.entries(mm.classes)) {
        if (this._ancestors(cn).includes(cn)) out.push(`${cn}: ${t.cycle}`);
        const feats = [...Object.keys(c.attributes), ...Object.keys(c.references)];
        for (const f of feats) {
          if (!FEATURE_RE.test(f)) out.push(`${cn}.${f}: ${t.badName}`);
          if (RESERVED.includes(f) || RESERVED.includes(snake(f))) out.push(`${cn}.${f}: ${t.reserved}`);
          if (feats.filter((x) => x === f).length > 1) out.push(`${cn}.${f}: ${t.dupName}`);
        }
        for (const [rn, r] of Object.entries(c.references)) {
          if (r.type !== "User" && !mm.classes[r.type]) { out.push(`${cn}.${rn}: ${t.noTarget}`); continue; }
          if (r.opposite) {
            const o = mm.classes[r.type]?.references?.[r.opposite];
            if (!o || o.opposite !== rn || (o.type !== cn && !this._ancestors(cn).includes(o.type))) out.push(`${cn}.${rn}: ${t.oppBroken}`);
            else if (o.containment && r.containment) out.push(`${cn}.${rn}: ${t.bothCont}`);
          }
        }
      }
      return [...new Set(out)];
    }

    /* ------------------------------------------------------------------ layout */
    _isProcess(name) { return this._mm.behaviour?.classes?.[name]?.kind === "process"; }
    _boxSize(name) {
      const c = this._mm.classes[name];
      const width = (texts, min) => Math.round(Math.max(min, Math.min(340, Math.max(...texts.map((x) => x.length)) * 6.9 + 22)));
      if (c) {
        const lines = [name, ...Object.entries(c.attributes).map(([an, a]) => `${a.id ? "🔑 " : ""}${an}: ${a.type} [${multText(a.lower, a.upper)}]`)];
        return { w: width(lines, 150), h: HEAD_H + (this._isProcess(name) ? 12 : 0) + Math.max(1, Object.keys(c.attributes).length) * ROW_H + PAD };
      }
      const e = this._mm.enums[name];
      return { w: width([name, ...e.literals.map((l) => l.name)], 120), h: HEAD_H + 12 + Math.max(1, e.literals.length) * ROW_H + PAD };
    }
    _autoLayout(force) {
      // Hub layout: the most connected class in the middle, its neighbours around it (BFS on
      // references and inheritance), subclasses below their supertype; enums on the top row.
      const mm = this._mm;
      const classes = Object.keys(mm.classes);
      const enums = Object.keys(mm.enums);
      const missing = [...classes, ...enums].filter((n) => force || !mm.diagram[n]);
      if (!missing.length) return;
      const adj = Object.fromEntries(classes.map((n) => [n, new Set()]));
      for (const [cn, c] of Object.entries(mm.classes)) {
        for (const r of Object.values(c.references)) if (adj[r.type] && r.type !== cn) { adj[cn].add(r.type); adj[r.type].add(cn); }
        for (const st of c.supertypes) if (adj[st]) { adj[cn].add(st); adj[st].add(cn); }
      }
      const byDegree = [...classes].sort((x, y) => adj[y].size - adj[x].size);
      const order = [];
      for (const start of byDegree) {
        if (order.includes(start)) continue;
        const queue = [start];
        while (queue.length) {
          const n = queue.shift();
          if (order.includes(n)) continue;
          order.push(n);
          [...adj[n]].sort((x, y) => adj[y].size - adj[x].size).forEach((x) => { if (!order.includes(x)) queue.push(x); });
        }
      }
      const ring = [[0, 0]];
      for (let r = 1; ring.length < order.length + 8 * r; r++) {
        for (let dx = -r; dx <= r; dx++) for (let dy = -r; dy <= r; dy++) if (Math.max(Math.abs(dx), Math.abs(dy)) === r) ring.push([dx, dy]);
        ring.sort((p1, p2) => Math.hypot(p1[0] * 1.6, p1[1]) - Math.hypot(p2[0] * 1.6, p2[1]));
      }
      const taken = new Map();
      const cellOf = {};
      for (const n of order) {
        const sup = mm.classes[n].supertypes.find((st) => cellOf[st]);
        let cell = null;
        if (sup) {
          const [sx, sy] = cellOf[sup];
          cell = [[sx, sy + 1], [sx + 1, sy + 1], [sx - 1, sy + 1]].find(([x, y]) => !taken.has(`${x},${y}`)) || null;
        }
        if (!cell) {
          const near = [...adj[n]].filter((x) => cellOf[x]).map((x) => cellOf[x]);
          const free = ring.filter(([x, y]) => !taken.has(`${x},${y}`));
          const score = ([x, y]) => near.reduce((acc, [nx, ny]) => acc + Math.hypot((x - nx) * 1.6, y - ny), 0) + Math.hypot(x * 1.6, y) * 0.3;
          cell = near.length ? free.sort((p1, p2) => score(p1) - score(p2))[0] : free[0];
        }
        taken.set(`${cell[0]},${cell[1]}`, n);
        cellOf[n] = cell;
      }
      const sizes = Object.fromEntries([...classes, ...enums].map((n) => [n, this._boxSize(n)]));
      const cw = Math.max(200, ...classes.map((n) => sizes[n].w)) + 90;
      const xs = Object.values(cellOf).map((c) => c[0]);
      const ys = Object.values(cellOf).map((c) => c[1]);
      const minX = Math.min(0, ...xs), minY = Math.min(0, ...ys);
      const enumH = enums.length ? Math.max(...enums.map((n) => sizes[n].h)) + 60 : 0;
      const rowTop = {};
      let acc = 20 + enumH;
      for (let y = minY; y <= Math.max(0, ...ys); y++) {
        rowTop[y] = acc;
        const hs = order.filter((n) => cellOf[n][1] === y).map((n) => sizes[n].h);
        acc += (hs.length ? Math.max(...hs) : 0) + 70;
      }
      for (const n of order) {
        if (!force && mm.diagram[n]) continue;
        const [x, y] = cellOf[n];
        mm.diagram[n] = { x: 20 + (x - minX) * cw, y: rowTop[y] };
      }
      let ex = 20;
      for (const n of enums) {
        if (force || !mm.diagram[n]) mm.diagram[n] = { x: ex, y: 20 };
        ex += sizes[n].w + 40;
      }
    }
    _fit() {
      const r = this.shadowRoot.querySelector(".canvas")?.getBoundingClientRect();
      const pos = Object.entries(this._mm.diagram).filter(([n]) => this._mm.classes[n] || this._mm.enums[n]);
      if (!r || !pos.length) return;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const [n, p] of pos) {
        const s = this._boxSize(n);
        x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x + s.w); y1 = Math.max(y1, p.y + s.h);
      }
      const k = Math.min(1.2, Math.max(0.3, Math.min((r.width - 40) / (x1 - x0), (r.height - 40) / (y1 - y0))));
      this._view = { k, x: (r.width - (x1 - x0) * k) / 2 - x0 * k, y: 20 - y0 * k };
      this._renderDiagram();
    }

    /* ------------------------------------------------------------------ rendering */
    _render() {
      const root = this.shadowRoot;
      const t = this.t;
      if (!root.querySelector(".wrap")) {
        root.innerHTML = "";
        root.append(el("style", {}, css));
        const wrap = el("div", { class: "wrap" },
          el("div", { class: "bar" }),
          el("div", { class: "main" }, el("div", { class: "canvas" }), el("div", { class: "side" })));
        root.append(wrap);
        this._bindCanvas(root.querySelector(".canvas"));
        requestAnimationFrame(() => this._fit());
      }
      const bar = root.querySelector(".bar");
      const issues = this._issues();
      const warns = this._warnings();
      bar.replaceChildren(...[
        el("strong", {}, `${t.package} ${this._mm.package || ""}`),
        this.readonly ? el("span", { class: "hint" }, `· ${t.readonly}`) : null,
        this.readonly ? null : el("button", { onclick: () => this._addClass(), title: t.addClass }, `+ ${t.addClass}`),
        this.readonly ? null : el("button", { onclick: () => this._addEnum(), title: t.addEnum }, `+ ${t.addEnum}`),
        el("button", { onclick: () => { this._autoLayout(true); this._fit(); this._changed(); }, disabled: this.readonly }, t.layout),
        el("button", { onclick: () => this._fit() }, t.fit),
        el("span", {
          class: `status ${issues.length ? "bad" : "good"}`,
          onclick: () => { this._showIssues = !this._showIssues; this._schedule(); },
        }, issues.length ? `⚠ ${issues.length} ${t.issues}` : `✓ ${t.ok}`),
        warns.length ? el("span", { class: "status warn", onclick: () => { this._showIssues = !this._showIssues; this._schedule(); } }, `△ ${warns.length} ${t.warnings}`) : null,
        el("span", { class: "grow" }),
        this.readonly ? null : el("input", { class: "note", placeholder: t.note, size: 24, value: this._note || "", oninput: (e) => { this._note = e.target.value; } }),
        this.readonly ? null : el("button", {
          class: "primary", disabled: issues.length > 0,
          onclick: () => this.dispatchEvent(new CustomEvent("save", { detail: { metamodel: this.metamodel, note: this._note || "" } })),
        }, this.getAttribute("save-label") || t.save),
      ].filter(Boolean));
      this._renderDiagram();
      this._renderSide();
      const canvas = root.querySelector(".canvas");
      canvas.querySelector(".issues")?.remove();
      if (this._showIssues && (issues.length || warns.length)) {
        canvas.append(el("div", { class: "issues" }, issues.map((i) => el("div", {}, i)), warns.map((w) => el("div", { class: "w" }, `△ ${w}`))));
      }
    }

    _bindCanvas(canvas) {
      let drag = null;
      canvas.addEventListener("pointerdown", (ev) => {
        const box = ev.target.closest?.(".box");
        const p = { x: ev.clientX, y: ev.clientY };
        if (box) {
          const name = box.dataset.name;
          this._sel = { kind: this._mm.classes[name] ? "class" : "enum", name };
          const start = { ...(this._mm.diagram[name] || { x: 0, y: 0 }) };
          drag = { kind: "box", name, p, start, moved: false };
          this._schedule();
        } else {
          drag = { kind: "pan", p, start: { ...this._view } };
        }
        canvas.setPointerCapture(ev.pointerId);
      });
      canvas.addEventListener("pointermove", (ev) => {
        if (!drag) return;
        const dx = ev.clientX - drag.p.x, dy = ev.clientY - drag.p.y;
        if (drag.kind === "pan") {
          this._view = { ...drag.start, x: drag.start.x + dx, y: drag.start.y + dy };
        } else if (!this.readonly) {
          drag.moved = drag.moved || Math.abs(dx) + Math.abs(dy) > 2;
          this._mm.diagram[drag.name] = { x: Math.round(drag.start.x + dx / this._view.k), y: Math.round(drag.start.y + dy / this._view.k) };
        }
        this._renderDiagram();
      });
      const end = () => {
        if (drag?.kind === "box" && drag.moved) this._changed();
        drag = null;
      };
      canvas.addEventListener("pointerup", end);
      canvas.addEventListener("pointercancel", end);
      canvas.addEventListener("wheel", (ev) => {
        ev.preventDefault();
        const r = canvas.getBoundingClientRect();
        const k = Math.min(2, Math.max(0.25, this._view.k * (ev.deltaY < 0 ? 1.1 : 0.9)));
        const mx = ev.clientX - r.left, my = ev.clientY - r.top;
        this._view = { k, x: mx - ((mx - this._view.x) * k) / this._view.k, y: my - ((my - this._view.y) * k) / this._view.k };
        this._renderDiagram();
      }, { passive: false });
    }

    _anchor(name, toward) {
      const p = this._mm.diagram[name] || { x: 0, y: 0 };
      const s = this._boxSize(name);
      const cx = p.x + s.w / 2, cy = p.y + s.h / 2;
      const dx = toward.x - cx, dy = toward.y - cy;
      if (!dx && !dy) return { x: cx, y: cy };
      const sx = (s.w / 2) / Math.abs(dx || 1e-9), sy = (s.h / 2) / Math.abs(dy || 1e-9);
      const f = Math.min(sx, sy);
      return { x: cx + dx * f, y: cy + dy * f };
    }
    _center(name) {
      if (name === "User") return null;
      const p = this._mm.diagram[name];
      if (!p) return null;
      const s = this._boxSize(name);
      return { x: p.x + s.w / 2, y: p.y + s.h / 2 };
    }

    _renderDiagram() {
      const canvas = this.shadowRoot.querySelector(".canvas");
      if (!canvas) return;
      const mm = this._mm;
      const defs = svg("defs", {},
        svg("marker", { id: "tri", viewBox: "0 0 12 12", refX: "11", refY: "6", markerWidth: "14", markerHeight: "14", orient: "auto-start-reverse" },
          svg("path", { d: "M1,1 L11,6 L1,11 z", class: "mk-open" })),
        svg("marker", { id: "arrow", viewBox: "0 0 12 12", refX: "11", refY: "6", markerWidth: "10", markerHeight: "10", orient: "auto-start-reverse" },
          svg("path", { d: "M1,1 L11,6 L1,11", class: "edge" })),
        svg("marker", { id: "diamond", viewBox: "0 0 16 10", refX: "1", refY: "5", markerWidth: "16", markerHeight: "10", orient: "auto-start-reverse" },
          svg("path", { d: "M1,5 L8,1 L15,5 L8,9 z", class: "mk-fill" })));
      const g = svg("g", { transform: `translate(${this._view.x},${this._view.y}) scale(${this._view.k})` });
      const edges = svg("g", {});
      const labels = svg("g", {});
      const drawn = new Set();
      for (const [cn, c] of Object.entries(mm.classes)) {
        const a = this._center(cn);
        if (!a) continue;
        for (const s of c.supertypes) {
          const b = this._center(s);
          if (!b) continue;
          const p1 = this._anchor(cn, b), p2 = this._anchor(s, a);
          edges.append(svg("path", { d: `M${p1.x},${p1.y} L${p2.x},${p2.y}`, class: "edge inherit", "marker-end": "url(#tri)" }));
        }
        for (const [rn, r] of Object.entries(c.references)) {
          if (drawn.has(`${cn}.${rn}`)) continue;
          const b = r.type === "User" ? null : this._center(r.type);
          if (!b) {
            const p = mm.diagram[cn];
            labels.append(svg("text", { x: p.x + 4, y: p.y + this._boxSize(cn).h + 14, class: "elabel" }, `${rn} → User`));
            continue;
          }
          const o = r.opposite ? mm.classes[r.type]?.references?.[r.opposite] : null;
          if (o) drawn.add(`${r.type}.${r.opposite}`);
          let p1, p2, d;
          if (r.type === cn) {   // self reference: a loop on the right side
            const p = mm.diagram[cn];
            const s = this._boxSize(cn);
            p1 = { x: p.x + s.w, y: p.y + 10 };
            p2 = { x: p.x + s.w, y: p.y + 26 };
            d = `M${p1.x},${p1.y} C${p1.x + 50},${p1.y - 30} ${p2.x + 50},${p2.y + 30} ${p2.x},${p2.y}`;
          } else {
            p1 = this._anchor(cn, b);
            p2 = this._anchor(r.type, a);
            d = `M${p1.x},${p1.y} L${p2.x},${p2.y}`;
          }
          const attrs = { d, class: "edge" };
          if (r.containment) attrs["marker-start"] = "url(#diamond)";
          if (o?.containment) attrs["marker-end"] = "url(#diamond)";
          else if (!o) attrs["marker-end"] = "url(#arrow)";
          edges.append(svg("path", attrs));
          const lab = (pt, from, text) => {
            const ux = from.x - pt.x, uy = from.y - pt.y, len = Math.hypot(ux, uy) || 1;
            labels.append(svg("text", { x: pt.x + (ux / len) * 18 + 4, y: pt.y + (uy / len) * 18 - 4, class: "elabel" }, text));
          };
          lab(p2, p1, `${rn} ${multText(r.lower, r.upper)}`);
          if (o) lab(p1, p2, `${r.opposite} ${multText(o.lower, o.upper)}`);
        }
      }
      const boxes = svg("g", {});
      for (const [cn, c] of Object.entries(mm.classes)) {
        const p = mm.diagram[cn];
        if (!p) continue;
        const s = this._boxSize(cn);
        const sel = this._sel?.name === cn;
        const proc = this._isProcess(cn);
        const hh = HEAD_H + (proc ? 12 : 0);
        const b = svg("g", { class: `box${sel ? " sel" : ""}`, "data-name": cn, transform: `translate(${p.x},${p.y})` },
          svg("rect", { class: "body", width: s.w, height: s.h, rx: 6 }),
          svg("rect", { class: "head", width: s.w - 2, x: 1, y: 1, height: hh - 2, rx: 5 }),
          proc ? svg("text", { x: s.w / 2, y: 13, "text-anchor": "middle", class: "stereo" }, "«process»") : null,
          svg("text", { x: s.w / 2, y: proc ? 30 : 19, "text-anchor": "middle", class: `title${c.abstract ? " abstract" : ""}` }, cn));
        let y = hh + 14;
        const attrs = Object.entries(c.attributes);
        if (!attrs.length) b.append(svg("text", { x: 8, y, class: "muted" }, "—"));
        for (const [an, a] of attrs) {
          const m = a.lower === 0 && a.upper === 1 ? "" : ` [${multText(a.lower, a.upper)}]`;
          b.append(svg("text", { x: 8, y }, `${a.id ? "🔑 " : ""}${an}: ${a.type}${m}`));
          y += ROW_H;
        }
        boxes.append(b);
      }
      for (const [en, e] of Object.entries(mm.enums)) {
        const p = mm.diagram[en];
        if (!p) continue;
        const s = this._boxSize(en);
        const sel = this._sel?.name === en;
        const b = svg("g", { class: `box enum${sel ? " sel" : ""}`, "data-name": en, transform: `translate(${p.x},${p.y})` },
          svg("rect", { class: "body", width: s.w, height: s.h, rx: 6 }),
          svg("rect", { class: "head", width: s.w - 2, x: 1, y: 1, height: HEAD_H + 10, rx: 5 }),
          svg("text", { x: s.w / 2, y: 14, "text-anchor": "middle", class: "stereo" }, "«enumeration»"),
          svg("text", { x: s.w / 2, y: 30, "text-anchor": "middle", class: "title" }, en));
        let y = HEAD_H + 28;
        for (const l of e.literals) { b.append(svg("text", { x: 8, y }, l.name)); y += ROW_H; }
        boxes.append(b);
      }
      g.append(boxes, edges, labels);
      const root = svg("svg", { role: "img", "aria-label": "metamodel diagram" }, defs, g);
      const old = canvas.querySelector("svg");
      if (old) old.replaceWith(root); else canvas.prepend(root);
    }

    _multSelect(f, onchange, disabled) {
      return el("select", {
        disabled, onchange: (e) => { const m = MULTS.find((x) => x[0] === e.target.value); f.lower = m[1]; f.upper = m[2]; onchange(); },
      }, MULTS.map(([k]) => el("option", { value: k, selected: k === multKey(f.lower, f.upper) }, k)));
    }

    _behaviourPanel(cn) {
      const b = this._mm.behaviour?.classes?.[cn];
      if (!b) return null;
      const t = this.t;
      const label = (k) => b.workflow?.states.find((s2) => s2.key === k)?.label ?? k;
      const parts = [el("p", { class: "hint" }, t.behaviourHint)];
      if (b.workflow) {
        parts.push(el("h3", {}, `${t.workflow} · ${t.states}`),
          el("div", { class: "chips" }, b.workflow.states.map((s2) => el("span", { class: "chip", style: `background:${s2.color}`, title: s2.kind }, `${s2.kind === "initial" ? "▶ " : s2.kind === "final" ? "■ " : ""}${s2.label}`))),
          el("h3", {}, t.transitions),
          ...b.workflow.transitions.map((tr) => el("p", { class: "tr" },
            el("b", {}, tr.label), ` ${tr.from.map(label).join(", ")} → ${label(tr.to)}`,
            el("span", { class: "hint" }, tr.trigger === "timed" ? ` · ${t.timed}` : tr.by.length ? ` · ${t.by} ${tr.by.join(", ")}` : ""),
            tr.guard.length ? el("span", { class: "hint" }, ` · [${tr.guard.join("; ")}]`) : null)));
      }
      if (b.events?.length) {
        parts.push(el("h3", {}, t.events), el("div", { class: "chips" }, b.events.map((e2) => el("span", { class: "chip plain" }, e2))));
      }
      if (b.reactions?.length) {
        parts.push(el("h3", {}, t.reactions), ...b.reactions.map((r) => el("p", { class: "tr" }, el("b", {}, r.name), ` ${r.on} → ${r.do}`)));
      }
      if (b.webhooks?.length) {
        parts.push(el("h3", {}, t.webhooks), el("div", { class: "chips" }, b.webhooks.map((w) => el("span", { class: "chip plain" }, w))));
      }
      if (b.views?.length) {
        parts.push(el("h3", {}, t.views), el("div", { class: "chips" }, b.views.map((v) => el("span", { class: "chip plain" }, v))));
      }
      return el("div", {}, parts);
    }

    _renderSide() {
      const side = this.shadowRoot.querySelector(".side");
      const t = this.t, mm = this._mm, ro = this.readonly;
      side.replaceChildren();
      const sel = this._sel;
      if (!sel || (sel.kind === "class" && !mm.classes[sel.name]) || (sel.kind === "enum" && !mm.enums[sel.name])) {
        add(side, el("p", { class: "hint" }, t.select), el("p", { class: "hint" }, t.users));
        return;
      }
      const commit = () => this._changed();
      if (sel.kind === "enum") {
        const e = mm.enums[sel.name];
        add(side, 
          el("h3", {}, "Enum"),
          el("div", { class: "field" }, el("label", {}, t.name), el("input", { value: sel.name, disabled: ro, onchange: (ev) => { this._renameEnum(sel.name, ev.target.value.trim()); commit(); } })),
          el("h3", {}, t.literals),
          ...e.literals.map((l, i) => el("div", { class: "row lit" },
            el("input", { value: l.name, disabled: ro, onchange: (ev) => { l.name = ev.target.value.trim(); commit(); } }),
            el("input", { value: typeof l.label === "string" ? l.label : (l.label?.[this.getAttribute("lang") || "it"] || ""), placeholder: t.label, disabled: ro, onchange: (ev) => { const v = ev.target.value.trim(); if (v) l.label = v; else delete l.label; commit(); } }),
            ro ? el("span") : el("button", { class: "x", title: t.del, onclick: () => { e.literals.splice(i, 1); commit(); } }, "×"))),
          ro ? null : el("button", { onclick: () => { e.literals.push({ name: this._uniqueName("value", e.literals.map((l) => l.name)) }); commit(); } }, `+ ${t.add}`),
          el("h3", {}, ""),
          ro ? null : el("button", { class: "danger", onclick: () => { if (confirm(`${t.confirmDelete} ${sel.name}?`)) { this._deleteEnum(sel.name); commit(); } } }, `${t.del} ${sel.name}`));
        return;
      }
      const cn = sel.name, c = mm.classes[cn];
      const typeOptions = (cur) => [...DATATYPES, ...Object.keys(mm.enums)].map((d) => el("option", { value: d, selected: d === cur }, d));
      const classOptions = (cur) => [...Object.keys(mm.classes), "User"].map((d) => el("option", { value: d, selected: d === cur }, d));
      const others = Object.keys(mm.classes).filter((n) => n !== cn && !this._ancestors(n).includes(cn));
      add(side, 
        el("h3", {}, "Class"),
        el("div", { class: "field" }, el("label", {}, t.name), el("input", { value: cn, disabled: ro, onchange: (ev) => { this._renameClass(cn, ev.target.value.trim()); commit(); } })),
        el("div", { class: "field" }, el("label", {}, t.abstract), el("input", { type: "checkbox", checked: c.abstract, disabled: ro, onchange: (ev) => { c.abstract = ev.target.checked; commit(); } })),
        el("div", { class: "field" }, el("label", {}, t.supertypes), el("div", {}, others.length ? others.map((o) => el("label", { style: "display:inline-flex;gap:3px;margin-right:8px" },
          el("input", { type: "checkbox", checked: c.supertypes.includes(o), disabled: ro, onchange: (ev) => { c.supertypes = ev.target.checked ? [...c.supertypes, o] : c.supertypes.filter((s) => s !== o); commit(); } }), o)) : t.none)),
        el("div", { class: "field" }, el("label", {}, t.label), el("input", { value: typeof c.label === "string" ? c.label : (c.label?.[this.getAttribute("lang") || "it"] || ""), disabled: ro, onchange: (ev) => { const v = ev.target.value.trim(); if (v) c.label = v; else delete c.label; commit(); } })),
        el("div", { class: "field" }, el("label", {}, t.doc), el("textarea", { rows: 2, disabled: ro, onchange: (ev) => { const v = ev.target.value.trim(); if (v) c.doc = v; else delete c.doc; commit(); } }, c.doc || "")),
        el("h3", {}, t.attributes),
        el("div", { class: "row attr hint" }, el("span", {}, t.name), el("span", {}, t.type), el("span", {}, t.mult), el("span", { title: "iD" }, t.id), el("span")),
        ...Object.entries(c.attributes).map(([an, a]) => el("div", { class: "row attr" },
          el("input", { value: an, disabled: ro, onchange: (ev) => { this._renameFeature(cn, "attributes", an, ev.target.value.trim()); commit(); } }),
          el("select", { disabled: ro, onchange: (ev) => { a.type = ev.target.value; delete a.default; commit(); } }, typeOptions(a.type)),
          this._multSelect(a, commit, ro),
          el("input", { type: "checkbox", checked: !!a.id, disabled: ro, title: "iD (unique key)", onchange: (ev) => { if (ev.target.checked) a.id = true; else delete a.id; commit(); } }),
          ro ? el("span") : el("button", { class: "x", title: t.del, onclick: () => { delete c.attributes[an]; commit(); } }, "×"))),
        ro ? null : el("button", { onclick: () => { c.attributes[this._uniqueName("attribute", Object.keys(c.attributes))] = { type: "EString", lower: 0, upper: 1 }; commit(); } }, `+ ${t.add}`),
        el("h3", {}, t.references),
        ...Object.entries(c.references).flatMap(([rn, r]) => {
          const target = mm.classes[r.type];
          const candidates = target ? Object.entries(target.references).filter(([, o]) => o.type === cn || this._ancestors(cn).includes(o.type)).map(([on]) => on) : [];
          return [
            el("div", { class: "row ref" },
              el("input", { value: rn, disabled: ro, onchange: (ev) => { this._renameFeature(cn, "references", rn, ev.target.value.trim()); commit(); } }),
              el("select", { disabled: ro, onchange: (ev) => { this._setOpposite(cn, rn, null); r.type = ev.target.value; commit(); } }, classOptions(r.type)),
              this._multSelect(r, commit, ro)),
            el("div", { class: "row ref2" },
              el("label", { style: "display:inline-flex;gap:3px" }, el("input", { type: "checkbox", checked: r.containment, disabled: ro || r.type === "User", onchange: (ev) => { r.containment = ev.target.checked; if (r.containment && r.opposite) { const o = mm.classes[r.type]?.references?.[r.opposite]; if (o) o.containment = false; } commit(); } }), t.containment),
              el("label", { style: "display:inline-flex;gap:4px;align-items:center" }, t.opposite,
                el("select", { disabled: ro || !candidates.length, onchange: (ev) => { this._setOpposite(cn, rn, ev.target.value || null); commit(); } },
                  el("option", { value: "" }, t.none), candidates.map((on) => el("option", { value: on, selected: on === r.opposite }, on)))),
              ro ? el("span") : el("button", { class: "x", title: t.del, onclick: () => { this._setOpposite(cn, rn, null); delete c.references[rn]; commit(); } }, "×")),
          ];
        }),
        ro ? null : el("button", { onclick: () => {
          const target = Object.keys(mm.classes).find((n) => n !== cn) || cn;
          c.references[this._uniqueName(target[0].toLowerCase() + target.slice(1), [...Object.keys(c.references), ...Object.keys(c.attributes)])] = { type: target, lower: 0, upper: 1, containment: false };
          commit();
        } }, `+ ${t.add}`),
        this._behaviourPanel(cn),
        el("h3", {}, ""),
        ro ? null : el("button", { class: "danger", onclick: () => { if (confirm(`${t.confirmDelete} ${cn}?`)) { this._deleteClass(cn); commit(); } } }, `${t.del} ${cn}`));
    }
  }

  customElements.define("metamodel-editor", MetamodelEditor);
})();
