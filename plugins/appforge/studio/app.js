/* appforge Studio — graphical editor of app.yaml and manager of the generated applications.
 * The page edits the *raw* model (as written in app.yaml); the server normalises and
 * validates it with the same code used by the CLI, so the two can never disagree. */
"use strict";

const FIELD_TYPES = ["string", "text", "email", "url", "int", "number", "money", "bool", "date", "datetime", "enum", "ref", "json"];
const OPS = ["eq", "neq", "in", "not_in", "gt", "gte", "lt", "lte", "is_true", "is_false", "is_set", "is_empty"];
const UNARY = ["is_true", "is_false", "is_set", "is_empty"];
const REACTIONS = { notify: "Notifica", set: "Imposta campi", transition: "Esegui transizione", schedule: "Pianifica evento", broadcast: "Broadcast in tempo reale", custom: "Codice personalizzato" };
const STATE_KINDS = { initial: "iniziale", normal: "intermedio", final: "finale" };

const S = {
  token: "", apps: [], app: null, data: null, raw: null, layout: { entities: {}, workflows: {} },
  analysis: { errors: [], warnings: [], events: [], normalized: null },
  view: "metamodel", sel: null, wfEntity: null, dirty: false, undo: [], yamlDraft: null, connectFrom: null, genResult: null,
};

/* ------------------------------------------------------------------ utils */
const $ = (sel, root = document) => root.querySelector(sel);
const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
};
const svg = (tag, attrs = {}, ...children) => {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v); else el.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
};
const clone = (x) => JSON.parse(JSON.stringify(x));
const snake = (s) => s.replace(/([a-z0-9])([A-Z])/g, "$1_$2").replace(/[^A-Za-z0-9]+/g, "_").toLowerCase().replace(/^_+|_+$/g, "");
const pascal = (s) => s.replace(/(^|[^A-Za-z0-9]+)([A-Za-z0-9])/g, (_, __, c) => c.toUpperCase()).replace(/[^A-Za-z0-9]/g, "");
const asList = (v) => (v === undefined || v === null ? [] : Array.isArray(v) ? v : [v]);
function toast(msg, error = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast show" + (error ? " error" : "");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.className = "toast"), error ? 5000 : 2500);
}

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json", "X-Studio-Token": S.token },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

/* ------------------------------------------------------------- model access */
const locales = () => asList(S.raw?.app?.locales).length ? asList(S.raw.app.locales) : ["it", "en"];
const norm = () => S.analysis.normalized;
const entities = () => (S.raw.entities ||= {});
const ent = (name) => entities()[name];
const fieldsOf = (name) => (ent(name).fields ||= {});
const fieldSpec = (name, key) => {
  const f = fieldsOf(name)[key];
  if (typeof f === "string") return (fieldsOf(name)[key] = { type: f });
  return (fieldsOf(name)[key] ||= {});
};
const isProcess = (name) => (ent(name).kind || (ent(name).workflow ? "process" : "registry")) === "process";
const workflow = (name) => (ent(name).workflow ||= { states: {}, transitions: {} });
const labelOf = (spec, key, loc = locales()[0]) => {
  const l = spec && spec.label;
  if (typeof l === "string") return l;
  if (l && typeof l === "object") return l[loc] || Object.values(l)[0] || key;
  return key;
};
function principals(entityName, forNotify = false) {
  const out = ["all", "creator", "admin", ...Object.keys(S.raw.roles || {}).filter((r) => r !== "admin")];
  if (entityName && ent(entityName)) {
    for (const [k, f] of Object.entries(fieldsOf(entityName))) {
      const spec = typeof f === "string" ? { type: f } : f || {};
      if (spec.type === "ref" && !spec.many && (spec.to === "User" || forNotify)) out.push(`field:${k}`);
    }
  }
  return out;
}

/* ---------------------------------------------------------------- mutation */
function mutate(fn, { rerender = true } = {}) {
  S.undo.push(JSON.stringify({ raw: S.raw, layout: S.layout }));
  if (S.undo.length > 100) S.undo.shift();
  fn(S.raw);
  setDirty(true);
  if (rerender) render();
  scheduleValidate();
}
function setDirty(v) {
  S.dirty = v;
  $("#dirty").hidden = !v;
  $("#btn-save").disabled = !v || !S.app;
  $("#btn-undo").disabled = S.undo.length === 0;
}
function undo() {
  const last = S.undo.pop();
  if (!last) return;
  const st = JSON.parse(last);
  S.raw = st.raw;
  S.layout = st.layout;
  setDirty(true);
  render();
  scheduleValidate();
}
let validateTimer;
function scheduleValidate() {
  clearTimeout(validateTimer);
  validateTimer = setTimeout(validate, 350);
}
async function validate() {
  if (!S.raw) return;
  try {
    const r = await api("POST", "/api/validate", { raw: S.raw });
    S.analysis = r;
    renderProblems();
    if (["events", "generate"].includes(S.view)) renderView();
  } catch (e) {
    S.analysis = { errors: [e.message], warnings: [], events: S.analysis.events, normalized: S.analysis.normalized };
    renderProblems();
  }
}

/* ------------------------------------------------------------------- apps */
async function loadApps() {
  const r = await api("GET", "/api/apps");
  S.apps = r.apps;
  $("#registry-path").textContent = `Registro: ${r.registry}`;
  renderApps();
}
function renderApps() {
  const ul = $("#apps");
  ul.replaceChildren(
    ...(S.apps.length ? S.apps.map((a) =>
      h("li", {}, h("button", { "aria-current": S.app === a.slug ? "true" : "false", onclick: () => openApp(a.slug), title: a.path },
        h("span", { class: "name" }, a.name || a.slug),
        h("span", { class: "meta" }, h("span", { class: `state-dot ${a.state}` }), stateText(a)))))
      : [h("li", { class: "rail-foot" }, "Nessuna applicazione registrata.")])
  );
}
const stateText = (a) => ({ ok: "aggiornata", changed: "modello da rigenerare", new: "mai generata", problems: "da sistemare", missing: "cartella mancante" }[a.state] || a.state)
  + (a.evolution !== undefined && a.evolution !== null ? ` · evo ${a.evolution}` : "");

async function openApp(slug) {
  if (S.dirty && !confirm("Ci sono modifiche non salvate. Aprire un'altra applicazione e perderle?")) return;
  try {
    const d = await api("GET", `/api/model?app=${encodeURIComponent(slug)}`);
    S.app = slug;
    S.data = d;
    S.raw = d.raw;
    S.layout = { entities: {}, workflows: {}, ...(d.layout || {}) };
    S.analysis = { errors: d.errors, warnings: d.warnings, events: d.events, normalized: d.normalized };
    S.undo = [];
    S.sel = null;
    S.yamlDraft = null;
    S.genResult = null;
    S.wfEntity = Object.keys(entities()).find(isProcess) || null;
    setDirty(false);
    history.replaceState(null, "", `#token=${S.token}&app=${slug}`);
    $("#app-name").textContent = d.raw.app?.name || slug;
    $("#app-path").textContent = d.root;
    renderApps();
    render();
  } catch (e) {
    toast(e.message, true);
  }
}

async function save() {
  if (!S.app) return;
  try {
    const body = S.view === "yaml" && S.yamlDraft !== null
      ? { mode: "yaml", yaml: S.yamlDraft, layout: S.layout }
      : { raw: S.raw, layout: S.layout };
    const d = await api("PUT", `/api/model?app=${encodeURIComponent(S.app)}`, body);
    S.raw = d.raw;
    S.data = d;
    S.yamlDraft = null;
    S.analysis = { errors: d.errors, warnings: d.warnings, events: d.events, normalized: d.normalized };
    setDirty(false);
    toast(d.errors.length ? `Salvato, con ${d.errors.length} errori da correggere prima di generare` : "Modello salvato");
    await loadApps();
    render();
  } catch (e) {
    toast(e.message, true);
  }
}

/* ---------------------------------------------------------------- render */
function render() {
  document.querySelectorAll(".tabs [role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === S.view)));
  renderView();
  renderInspector();
  renderProblems();
}
function renderView() {
  const v = $("#view");
  if (!S.raw) {
    v.replaceChildren(h("div", { class: "pane" }, h("div", { class: "empty" },
      "Apri un'applicazione dal registro, oppure creane una nuova. Ogni applicazione resta un repository indipendente: lo Studio ne modifica solo il modello (app.yaml).")));
    return;
  }
  const views = { metamodel: viewMetamodel, domain: viewDomain, workflow: viewWorkflow, events: viewEvents, settings: viewSettings, yaml: viewYaml, generate: viewGenerate };
  v.replaceChildren(views[S.view]());
  if (S.view === "domain" || S.view === "workflow") requestAnimationFrame(drawEdges);
}
function renderProblems() {
  const { errors = [], warnings = [] } = S.analysis;
  const btn = $("#btn-problems");
  btn.className = "problems-btn " + (errors.length ? "has-errors" : warnings.length ? "has-warnings" : "clean");
  $("#problems-count").textContent = errors.length ? `${errors.length} errori` + (warnings.length ? `, ${warnings.length} avvisi` : "")
    : warnings.length ? `${warnings.length} avvisi` : "Modello valido";
  const p = $("#problems");
  p.replaceChildren(h("ul", {}, ...errors.map((e) => h("li", { class: "err" }, e)), ...warnings.map((w) => h("li", { class: "warn" }, w))));
}

/* ------------------------------------------------------------ metamodel */
function viewMetamodel() {
  const pane = h("div", { class: "pane" });
  if (!S.data?.split) {
    pane.append(h("p", { class: "hint", style: "margin:0 0 10px" },
      "Il modello di questa applicazione è ancora in un solo file (app.yaml): il metamodello qui sotto ne è ricavato, in sola lettura. ",
      h("button", { class: "primary", onclick: extractMetamodel }, "Separa in domain.ecore.yaml + app.yaml")));
  }
  const ed = document.createElement("metamodel-editor");
  ed.setAttribute("lang", "it");
  ed.setAttribute("save-label", "Salva metamodello");
  if (!S.data?.split) ed.setAttribute("readonly", "");
  ed.style.display = "block";
  ed.style.height = "calc(100vh - 190px)";
  pane.append(ed);
  customElements.whenDefined("metamodel-editor").then(() => { ed.metamodel = S.data.metamodel; });
  ed.addEventListener("save", async (ev) => {
    if (S.dirty) { toast("Salva prima le modifiche ad app.yaml", true); return; }
    try {
      await api("PUT", `/api/metamodel?app=${encodeURIComponent(S.app)}`, { metamodel: ev.detail.metamodel, note: ev.detail.note });
      await openApp(S.app);
      toast("Metamodello salvato: rigenera dalla scheda Genera");
    } catch (e) {
      toast(e.message, true);
    }
  });
  return pane;
}
async function extractMetamodel() {
  try {
    await api("POST", `/api/extract?app=${encodeURIComponent(S.app)}`, {});
    await openApp(S.app);
    toast("Separato: struttura in domain.ecore.yaml, comportamento in app.yaml");
  } catch (e) {
    toast(e.message, true);
  }
}

/* ------------------------------------------------------------ domain (ER) */
function defaultPos(i) {
  return { x: 40 + (i % 4) * 300, y: 80 + Math.floor(i / 4) * 300 };
}
function viewDomain() {
  if (S.data?.split) {
    return h("div", { class: "pane" }, h("div", { class: "empty" },
      "La struttura del dominio di questa applicazione è in domain.ecore.yaml: modificala nella scheda Metamodello. "
      + "Permessi, workflow, eventi e reazioni restano in app.yaml (schede Workflow, Eventi e reazioni, YAML)."));
  }
  const names = Object.keys(entities());
  const canvas = h("div", { class: "canvas domain", id: "canvas" });
  canvas.append(h("div", { class: "canvas-tools" },
    h("button", { class: "ghost", onclick: addEntity }, "Nuova entità"),
    h("button", { class: "ghost", onclick: addEnum }, "Nuova enumerazione"),
    h("button", { class: "ghost", onclick: autoLayout }, "Disponi"),
    ...Object.keys(S.raw.enums || {}).map((n) => h("button", { class: `small${S.sel?.type === "enum" && S.sel.name === n ? " chip-sel" : ""}`, title: "Enumerazione", onclick: () => select({ type: "enum", name: n }) }, n)),
    h("span", { class: "note" }, "Trascina i riquadri. Le frecce sono riferimenti (tratteggio = multipli).")));
  canvas.append(svg("svg", { class: "edges", id: "edges" }));
  const scope = S.raw.scope && (typeof S.raw.scope === "string" ? S.raw.scope : S.raw.scope.entity);
  names.forEach((name, i) => {
    const pos = (S.layout.entities[name] ||= defaultPos(i));
    const proc = isProcess(name);
    const box = h("div", {
      class: `box ${proc ? "process" : "registry"}${scope === name ? " scope" : ""}${S.sel?.type === "entity" && S.sel.name === name ? " sel" : ""}`,
      style: `left:${pos.x}px;top:${pos.y}px`, "data-entity": name,
    },
      h("header", { onclick: () => select({ type: "entity", name }) },
        h("strong", {}, name), h("span", { class: "kind" }, proc ? "processo" : "anagrafica")),
      h("ul", {},
        ...(ent(name).code_prefix ? [h("li", { class: "sys" }, h("span", { class: "key" }, "code"), h("span", { class: "t" }, ent(name).code_prefix + "-AAAA-NNNN"))] : []),
        ...Object.entries(fieldsOf(name)).map(([k, f]) => {
          const spec = typeof f === "string" ? { type: f } : f || {};
          const t = spec.type === "ref" ? `→ ${spec.to}${spec.many ? "[]" : ""}` : spec.type === "enum" ? spec.enum : spec.type || "string";
          return h("li", {
            class: `${spec.required ? "req" : ""}${S.sel?.type === "field" && S.sel.entity === name && S.sel.key === k ? " sel" : ""}`,
            onclick: (ev) => { ev.stopPropagation(); select({ type: "field", entity: name, key: k }); },
          }, h("span", { class: "key" }, k), h("span", { class: "t" }, t));
        }),
        ...(proc ? [h("li", { onclick: () => { S.wfEntity = name; S.view = "workflow"; render(); } },
          h("span", { class: "key" }, "state"), h("span", { class: "t" }, `${Object.keys(workflow(name).states || {}).length} stati`))] : [])),
      h("button", { class: "add", onclick: () => addField(name) }, "+ campo"));
    makeDraggable(box, (x, y) => { S.layout.entities[name] = { x, y }; setDirty(true); drawEdges(); });
    canvas.append(box);
  });
  return canvas;
}
function autoLayout() {
  Object.keys(entities()).forEach((n, i) => (S.layout.entities[n] = defaultPos(i)));
  setDirty(true);
  render();
}
function makeDraggable(el, onMove) {
  el.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0 || ev.target.closest("li, button, .add")) return;
    const start = { x: ev.clientX, y: ev.clientY, left: el.offsetLeft, top: el.offsetTop };
    el.setPointerCapture(ev.pointerId);
    el.style.cursor = "grabbing";
    const move = (e) => {
      const x = Math.max(0, Math.round((start.left + e.clientX - start.x) / 10) * 10);
      const y = Math.max(50, Math.round((start.top + e.clientY - start.y) / 10) * 10);
      el.style.left = `${x}px`;
      el.style.top = `${y}px`;
      onMove(x, y, false);
    };
    const up = () => {
      el.style.cursor = "";
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
  });
}
function drawEdges() {
  const g = $("#edges");
  if (!g) return;
  const canvas = $("#canvas");
  g.replaceChildren(svg("defs", {}, svg("marker", { id: "arrow", viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "7", markerHeight: "7", orient: "auto-start-reverse" },
    svg("path", { d: "M 0 0 L 10 5 L 0 10 z", style: "fill: var(--graphite); stroke: none" }))));
  let maxX = 0, maxY = 0;
  canvas.querySelectorAll(".box, .node").forEach((b) => { maxX = Math.max(maxX, b.offsetLeft + b.offsetWidth); maxY = Math.max(maxY, b.offsetTop + b.offsetHeight); });
  canvas.style.width = `${maxX + 200}px`;
  canvas.style.height = `${maxY + 200}px`;
  g.setAttribute("width", maxX + 200);
  g.setAttribute("height", maxY + 200);
  if (S.view === "domain") drawRefEdges(g, canvas); else drawTransitionEdges(g, canvas);
}
function rectOf(el) {
  return { x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight, cx: el.offsetLeft + el.offsetWidth / 2, cy: el.offsetTop + el.offsetHeight / 2 };
}
function anchor(r, toward) {
  const dx = toward.cx - r.cx, dy = toward.cy - r.cy;
  if (Math.abs(dx) * r.h > Math.abs(dy) * r.w) return { x: dx > 0 ? r.x + r.w : r.x, y: r.cy, side: "h" };
  return { x: r.cx, y: dy > 0 ? r.y + r.h : r.y, side: "v" };
}
function curve(a, b, bend = 0) {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
  const nx = -(b.y - a.y), ny = b.x - a.x, len = Math.hypot(nx, ny) || 1;
  const cx = mx + (nx / len) * bend, cy = my + (ny / len) * bend;
  return { d: `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`, lx: (a.x + 2 * cx + b.x) / 4, ly: (a.y + 2 * cy + b.y) / 4 };
}
function drawRefEdges(g, canvas) {
  for (const [name, e] of Object.entries(entities())) {
    const src = canvas.querySelector(`.box[data-entity="${CSS.escape(name)}"]`);
    if (!src) continue;
    for (const [k, f] of Object.entries(e.fields || {})) {
      const spec = typeof f === "string" ? { type: f } : f || {};
      if (spec.type !== "ref" || spec.to === "User") continue;
      const dst = canvas.querySelector(`.box[data-entity="${CSS.escape(spec.to)}"]`);
      if (!dst) continue;
      const rs = rectOf(src), rd = rectOf(dst);
      const a = anchor(rs, rd), b = anchor(rd, rs);
      const c = curve(a, b, src === dst ? 60 : 18);
      const sel = S.sel?.type === "field" && S.sel.entity === name && S.sel.key === k;
      g.append(svg("path", { d: c.d, class: `${spec.many ? "many" : ""}${sel ? " sel" : ""}`, "marker-end": "url(#arrow)" }));
      g.append(svg("text", { x: c.lx + 4, y: c.ly - 4 }, k));
    }
  }
}

/* --------------------------------------------------------------- workflow */
function viewWorkflow() {
  const procs = Object.keys(entities()).filter(isProcess);
  const wrap = h("div", { class: "canvas", id: "canvas" });
  const tools = h("div", { class: "canvas-tools" },
    h("select", { onchange: (e) => { S.wfEntity = e.target.value; S.sel = null; render(); }, "aria-label": "Entità" },
      ...procs.map((p) => h("option", { value: p, selected: p === S.wfEntity }, p))),
    h("button", { class: "ghost", onclick: addState, disabled: !S.wfEntity }, "Nuovo stato"),
    h("button", { class: S.connectFrom ? "primary" : "ghost", onclick: toggleConnect, disabled: !S.wfEntity },
      S.connectFrom ? "Clicca lo stato di arrivo…" : "Nuova transizione"),
    h("button", { class: "ghost", onclick: () => { if (S.wfEntity) { S.layout.workflows[S.wfEntity] = {}; setDirty(true); render(); } } }, "Disponi"),
    h("span", { class: "note" }, "Arancione = transizione automatica a tempo. Bordo doppio = stato finale."));
  wrap.append(tools);
  if (!procs.length) {
    wrap.append(h("div", { class: "pane" }, h("div", { class: "empty" },
      "Nessun processo. Un'entità diventa un processo con un workflow: selezionala nel Dominio e scegli «processo».")));
    return wrap;
  }
  if (!S.wfEntity || !procs.includes(S.wfEntity)) S.wfEntity = procs[0];
  const name = S.wfEntity;
  const wf = workflow(name);
  wf.states ||= {};
  wf.transitions ||= {};
  if (Array.isArray(wf.states)) wf.states = Object.fromEntries(wf.states.map((s) => [s, {}]));
  wrap.append(svg("svg", { class: "edges", id: "edges" }));
  const lay = (S.layout.workflows[name] ||= {});
  const auto = layeredLayout(wf);
  Object.entries(wf.states).forEach(([k, st], i) => {
    st = st || {};
    const pos = (lay[k] ||= auto[k]);
    const kind = st.kind || (i === 0 ? "initial" : "normal");
    const node = h("div", {
      class: `node ${kind}${S.sel?.type === "state" && S.sel.entity === name && S.sel.key === k ? " sel" : ""}${S.connectFrom === k ? " connect-from" : ""}`,
      style: `left:${pos.x}px;top:${pos.y}px`, "data-state": k,
      onclick: () => onStateClick(k),
    }, h("span", { class: "lab" }, labelOf(st, k)), h("span", { class: "k key" }, k),
      st.reminder ? h("span", { class: "bell", title: "Sollecito" }, `${typeof st.reminder === "object" ? st.reminder.after_days ?? 7 : st.reminder}g`) : null);
    makeDraggable(node, (x, y) => { lay[k] = { x, y }; setDirty(true); drawEdges(); });
    wrap.append(node);
  });
  return wrap;
}
// Columns by distance from the initial state (final states last), rows in order of appearance.
function layeredLayout(wf) {
  const keys = Object.keys(wf.states || {});
  const kind = (k, i) => (wf.states[k] && wf.states[k].kind) || (i === 0 ? "initial" : "normal");
  const initial = keys.find((k, i) => kind(k, i) === "initial") || keys[0];
  const depth = { [initial]: 0 };
  const queue = [initial];
  while (queue.length) {
    const cur = queue.shift();
    for (const t of Object.values(wf.transitions || {})) {
      const froms = t.from === "*" || t.from === undefined ? keys : asList(t.from);
      if (froms.includes(cur) && t.to in wf.states && !(t.to in depth)) { depth[t.to] = depth[cur] + 1; queue.push(t.to); }
    }
  }
  const maxD = Math.max(0, ...Object.values(depth));
  const cols = {};
  keys.forEach((k, i) => {
    const d = kind(k, i) === "final" ? maxD + 1 : depth[k] ?? maxD + 1;
    (cols[d] ||= []).push(k);
  });
  const out = {};
  for (const [d, list] of Object.entries(cols)) list.forEach((k, r) => (out[k] = { x: 50 + Number(d) * 225, y: 80 + r * 130 + (Number(d) % 2) * 40 }));
  return out;
}
function onStateClick(k) {
  if (S.connectFrom) {
    const from = S.connectFrom;
    S.connectFrom = null;
    const name = S.wfEntity;
    let key = `to_${k}`;
    let n = 2;
    while (workflow(name).transitions[key]) key = `to_${k}_${n++}`;
    mutate(() => {
      workflow(name).transitions[key] = { label: { [locales()[0]]: key }, from, to: k, by: ["admin"] };
    }, { rerender: false });
    select({ type: "transition", entity: name, key });
    return;
  }
  select({ type: "state", entity: S.wfEntity, key: k });
}
function toggleConnect() {
  if (S.connectFrom) { S.connectFrom = null; render(); return; }
  if (S.sel?.type === "state" && S.sel.entity === S.wfEntity) { S.connectFrom = S.sel.key; render(); toast("Ora clicca lo stato di arrivo"); return; }
  toast("Seleziona prima lo stato di partenza, poi «Nuova transizione»");
}
function drawTransitionEdges(g, canvas) {
  const name = S.wfEntity;
  if (!name) return;
  const wf = workflow(name);
  const pairCount = {};
  for (const [k, t] of Object.entries(wf.transitions || {})) {
    const froms = t.from === "*" || t.from === undefined ? Object.keys(wf.states).filter((s) => (wf.states[s]?.kind) !== "final" && s !== t.to) : asList(t.from);
    for (const f of froms) {
      const a = canvas.querySelector(`.node[data-state="${CSS.escape(f)}"]`);
      const b = canvas.querySelector(`.node[data-state="${CSS.escape(t.to)}"]`);
      if (!a || !b) continue;
      const pair = [f, t.to].sort().join("|");
      const idx = (pairCount[pair] = (pairCount[pair] || 0) + 1);
      const ra = rectOf(a), rb = rectOf(b);
      let c;
      if (a === b) {
        c = { d: `M ${ra.x + ra.w - 20} ${ra.y} C ${ra.x + ra.w + 40} ${ra.y - 60}, ${ra.x + ra.w + 60} ${ra.y + 20}, ${ra.x + ra.w} ${ra.cy}`, lx: ra.x + ra.w + 40, ly: ra.y - 24 };
      } else {
        const bend = (f < t.to ? 1 : -1) * (14 + (idx - 1) * 26);
        c = curve(anchor(ra, rb), anchor(rb, ra), bend);
      }
      const timed = t.trigger && typeof t.trigger === "object";
      const sel = S.sel?.type === "transition" && S.sel.entity === name && S.sel.key === k;
      g.append(svg("path", { d: c.d, class: sel ? "sel" : "", "marker-end": "url(#arrow)", style: timed ? "stroke: var(--amber); stroke-dasharray: 4 3" : null }));
      const text = labelOf(t, k);
      const w = Math.min(180, 12 + text.length * 6.6);
      const lab = svg("g", { class: `tlabel${sel ? " sel" : ""}${timed ? " timed" : ""}`, transform: `translate(${c.lx - w / 2}, ${c.ly - 10})`, onclick: () => select({ type: "transition", entity: name, key: k }) },
        svg("rect", { width: w, height: 20, rx: 4 }), svg("text", { x: 6, y: 14 }, text.length > 26 ? text.slice(0, 25) + "…" : text));
      g.append(lab);
    }
  }
}

/* ------------------------------------------------------- events/reactions */
function viewEvents() {
  const pane = h("div", { class: "pane" });
  const reactions = (S.raw.reactions ||= []);
  pane.append(h("div", { class: "row" }, h("h2", {}, "Reazioni"), h("span", { class: "spacer" }),
    h("button", { class: "ghost", onclick: addReaction }, "Nuova reazione")));
  if (!reactions.length) pane.append(h("div", { class: "empty" }, "Nessuna reazione. Una reazione collega un evento a un effetto: una notifica, un campo aggiornato, una transizione, un evento futuro."));
  else pane.append(h("table", { class: "grid" },
    h("thead", {}, h("tr", {}, h("th", {}, "Nome"), h("th", {}, "Quando"), h("th", {}, "Fa"))),
    h("tbody", {}, ...reactions.map((r, i) => h("tr", { class: S.sel?.type === "reaction" && S.sel.index === i ? "sel" : "", onclick: () => select({ type: "reaction", index: i }) },
      h("td", {}, h("span", { class: "key" }, r.name || `reaction_${i + 1}`)),
      h("td", {}, h("code", {}, r.on || "?"), describeWhen(r.when)),
      h("td", {}, describeReaction(r)))))));

  const custom = (S.raw.events ||= {});
  pane.append(h("div", { class: "row" }, h("h2", {}, "Eventi di dominio dichiarati"), h("span", { class: "spacer" }),
    h("button", { class: "ghost", onclick: addEvent }, "Nuovo evento")));
  const entries = Object.entries(custom);
  if (!entries.length) pane.append(h("div", { class: "empty" }, "Ogni entità emette già created, updated, deleted (e transitioned, completed, reminder se è un processo). Dichiara qui solo gli eventi in più, ad esempio quelli emessi da una transizione o pianificati."));
  else pane.append(h("table", { class: "grid" }, h("tbody", {}, ...entries.map(([k, ev]) =>
    h("tr", { class: S.sel?.type === "event" && S.sel.key === k ? "sel" : "", onclick: () => select({ type: "event", key: k }) },
      h("td", {}, h("code", {}, k)), h("td", {}, typeof ev === "string" ? ev : ev?.description || ""))))));

  pane.append(h("h2", {}, "Tutti gli eventi pubblicati"));
  pane.append(h("p", {}, ...(S.analysis.events || []).map((e) => h("code", { style: "margin-right:10px;display:inline-block" }, e))));
  return pane;
}
function describeWhen(w) {
  if (!w || !Object.keys(w).length) return "";
  const parts = [];
  if (w.transition) parts.push(`transizione ${asList(w.transition).join("/")}`);
  if (w.to) parts.push(`verso ${asList(w.to).join("/")}`);
  if (w.from) parts.push(`da ${asList(w.from).join("/")}`);
  if (w.clauses) parts.push(`${asList(w.clauses).length} condizioni`);
  return ` (${parts.join(", ")})`;
}
function describeReaction(r) {
  switch (r.do) {
    case "notify": return `Notifica ${asList(r.to).join(", ")} · template ${r.template || "?"}`;
    case "set": return `Imposta ${Object.entries(r.set || {}).map(([k, v]) => `${k}: ${v}`).join(", ")}`;
    case "transition": return `Transizione ${r.transition}`;
    case "schedule": return `Pianifica ${r.event} a ${r.at}`;
    case "broadcast": return `Broadcast su ${r.channel}`;
    case "custom": return `Handler custom_${r.handler}`;
    default: return "—";
  }
}

/* ------------------------------------------------------------- settings */
function viewSettings() {
  const app = (S.raw.app ||= {});
  const pane = h("div", { class: "pane" });
  pane.append(h("h2", {}, "Applicazione"));
  const auth = (app.auth ||= {});
  pane.append(h("div", { style: "max-width:640px" },
    textField("Nome", app.name || "", (v) => mutate((r) => (r.app.name = v), { rerender: false })),
    textField("Descrizione", app.description || "", (v) => mutate((r) => (r.app.description = v), { rerender: false })),
    textField("Lingue (separate da virgola, la prima è la predefinita)", locales().join(", "), (v) => mutate((r) => (r.app.locales = v.split(",").map((s) => s.trim()).filter(Boolean)), { rerender: false })),
    textField("Domini email ammessi", asList(auth.allowed_domains).join(", "), (v) => mutate((r) => (r.app.auth.allowed_domains = v.split(",").map((s) => s.trim()).filter(Boolean)), { rerender: false })),
    textField("Amministratori iniziali (email)", asList(auth.admins).join(", "), (v) => mutate((r) => (r.app.auth.admins = v.split(",").map((s) => s.trim()).filter(Boolean)), { rerender: false })),
    selectField("Abilitazione nuovi utenti", auth.approval || "manual", { manual: "un amministratore li abilita", auto: "abilitati subito" }, (v) => mutate((r) => (r.app.auth.approval = v), { rerender: false })),
    chipsField("Accesso con", ["google", "email"], asList(auth.providers).length ? asList(auth.providers) : ["google"], (v) => mutate((r) => (r.app.auth.providers = v), { rerender: false })),
    textField("Immagine Docker", app.deploy?.image || "", (v) => mutate((r) => ((r.app.deploy ||= {}).image = v), { rerender: false })),
    textField("URL pubblico", app.deploy?.base_url || "", (v) => mutate((r) => ((r.app.deploy ||= {}).base_url = v), { rerender: false })),
  ));
  pane.append(h("div", { class: "row" }, h("h2", {}, "Ruoli"), h("span", { class: "spacer" }), h("button", { class: "ghost", onclick: addRole }, "Nuovo ruolo")));
  const roles = (S.raw.roles ||= {});
  pane.append(h("table", { class: "grid" }, h("tbody", {},
    h("tr", {}, h("td", {}, h("span", { class: "key" }, "admin")), h("td", {}, "Amministratore (implicito: può tutto)"), h("td", {}, "")),
    ...Object.entries(roles).filter(([k]) => k !== "admin").map(([k, r]) => h("tr", { class: S.sel?.type === "role" && S.sel.key === k ? "sel" : "", onclick: () => select({ type: "role", key: k }) },
      h("td", {}, h("span", { class: "key" }, k)), h("td", {}, labelOf(typeof r === "object" ? r : { label: r }, k)), h("td", {}, r?.scoped ? "con ambito" : "globale"))))));
  const scope = typeof S.raw.scope === "string" ? S.raw.scope : S.raw.scope?.entity || "";
  pane.append(h("h2", {}, "Ambito dei ruoli"));
  pane.append(h("div", { style: "max-width:640px" }, selectField("Entità che fa da ambito (es. Dipartimento, Ufficio)", scope,
    { "": "nessuno", ...Object.fromEntries(Object.keys(entities()).filter((n) => !isProcess(n)).map((n) => [n, n])) },
    (v) => mutate((r) => { if (v) r.scope = { entity: v }; else delete r.scope; }))));
  return pane;
}

/* ------------------------------------------------------------------ yaml */
function viewYaml() {
  const pane = h("div", { class: "pane", style: "max-width:none" });
  const ta = h("textarea", { class: "yaml", spellcheck: "false", "aria-label": "app.yaml" });
  if (S.yamlDraft !== null) ta.value = S.yamlDraft;
  else if (!S.dirty) ta.value = S.data?.yaml ?? "";
  else {
    ta.value = "# …";
    api("POST", "/api/yaml", { raw: S.raw }).then((r) => { if (S.yamlDraft === null) ta.value = r.yaml; });
  }
  ta.addEventListener("input", () => {
    S.yamlDraft = ta.value;
    setDirty(true);
    clearTimeout(viewYaml.t);
    viewYaml.t = setTimeout(async () => {
      try {
        const r = await api("POST", "/api/validate", { yaml: ta.value });
        S.raw = r.raw;
        S.analysis = r;
        renderProblems();
      } catch (e) {
        S.analysis = { ...S.analysis, errors: [e.message], warnings: [] };
        renderProblems();
      }
    }, 500);
  });
  pane.append(h("p", { class: "hint" }, "Il testo scritto qui viene salvato così com'è, commenti compresi. Le modifiche fatte nelle viste grafiche riscrivono il file senza commenti."), ta);
  return pane;
}

/* -------------------------------------------------------------- generate */
function viewGenerate() {
  const pane = h("div", { class: "pane" });
  const ok = !S.analysis.errors?.length;
  pane.append(h("h2", {}, "Generazione"),
    h("p", {}, "Il generatore confronta il modello con l'ultima generazione e produce le migrazioni (additive in automatico, quelle distruttive come migrazione manuale da completare), il catalogo eventi, i tipi TypeScript, le traduzioni e la documentazione."),
    h("div", { class: "row" },
      h("button", { class: "ghost", disabled: !ok, onclick: () => runGenerate(true) }, "Anteprima"),
      h("button", { class: "primary", disabled: !ok || S.dirty, title: S.dirty ? "Salva prima il modello" : "", onclick: () => runGenerate(false) }, "Genera"),
      h("button", { class: "ghost", onclick: runCheckDb }, "Prova le migrazioni su un database temporaneo"),
      !ok ? h("span", { class: "dirty" }, "Correggi gli errori del modello per generare.") : S.dirty ? h("span", { class: "dirty" }, "Salva il modello per generare.") : null));
  const r = S.genResult;
  if (r) {
    pane.append(h("h2", {}, r.title));
    if (r.ops) pane.append(h("ul", { class: "ops" }, ...r.ops.map((o) => h("li", { class: o.startsWith("MANUAL") ? "manual" : "" }, o))));
    if (r.manual?.length) pane.append(h("p", { class: "dirty" }, "Alcune modifiche richiedono una migrazione scritta a mano: in Claude Code esegui /appforge:generate e l'agente la completerà."));
    if (r.migrations) for (const mg of r.migrations) {
      if (typeof mg === "string") pane.append(h("p", {}, h("code", {}, mg)));
      else pane.append(h("details", {}, h("summary", {}, h("code", {}, mg.path)), h("pre", { class: "out" }, mg.text)));
    }
    if (r.files?.length) pane.append(h("p", {}, "File aggiornati: ", ...r.files.map((f) => h("code", { style: "margin-right:8px" }, f))));
    if (r.log) pane.append(h("pre", { class: "out" }, r.log));
  }
  return pane;
}
async function runGenerate(dry) {
  try {
    const r = await api("POST", `/api/generate?app=${encodeURIComponent(S.app)}`, { dry_run: dry });
    S.genResult = { title: dry ? "Anteprima" : "Generato", ...r };
    if (!dry) { toast("Generazione completata"); await loadApps(); }
    renderView();
  } catch (e) {
    toast(e.message, true);
  }
}
async function runCheckDb() {
  try {
    S.genResult = { title: "Verifica in corso…" };
    renderView();
    const r = await api("POST", `/api/check-db?app=${encodeURIComponent(S.app)}`, {});
    S.genResult = { title: r.ok ? "Le migrazioni si applicano correttamente" : "Errore nelle migrazioni", log: r.log };
    renderView();
  } catch (e) {
    toast(e.message, true);
  }
}

/* -------------------------------------------------------------- inspector */
function select(sel) {
  S.sel = sel;
  if (S.view === "domain" || S.view === "workflow") {
    document.querySelectorAll(".box.sel, .node.sel, li.sel").forEach((x) => x.classList.remove("sel"));
    renderView();
  } else renderView();
  renderInspector();
}
function renderInspector() {
  const box = $("#inspector");
  if (!S.raw || !S.sel) {
    box.replaceChildren(h("p", { class: "hint" }, S.raw ? "Seleziona un elemento per modificarne le proprietà." : ""));
    return;
  }
  const s = S.sel;
  try {
    const panels = { entity: inspEntity, field: inspField, state: inspState, transition: inspTransition, reaction: inspReaction, enum: inspEnum, role: inspRole, event: inspEvent };
    box.replaceChildren(...[panels[s.type](s)].flat());
  } catch {
    S.sel = null;
    box.replaceChildren(h("p", { class: "hint" }, "Elemento non più presente."));
  }
}
function textField(label, value, onchange, opts = {}) {
  const input = h(opts.multiline ? "textarea" : "input", { type: opts.number ? "number" : "text", value: opts.multiline ? undefined : value, placeholder: opts.placeholder || "" });
  if (opts.multiline) input.value = value;
  input.addEventListener("change", () => onchange(opts.number ? (input.value === "" ? null : Number(input.value)) : input.value));
  return h("label", { class: "f" }, h("span", {}, label), input);
}
function selectField(label, value, options, onchange) {
  const sel = h("select", { onchange: (e) => onchange(e.target.value) },
    ...Object.entries(options).map(([v, l]) => h("option", { value: v, selected: v === value }, l)));
  return h("label", { class: "f" }, h("span", {}, label), sel);
}
function checkField(label, value, onchange) {
  return h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!value, onchange: (e) => onchange(e.target.checked) }), label);
}
function chipsField(label, options, selected, onchange) {
  const cur = new Set(selected);
  return h("div", { class: "f" }, h("span", {}, label), h("div", { class: "chips" }, ...options.map((o) => h("button", {
    type: "button", class: "chip", "aria-pressed": String(cur.has(o)),
    onclick: (e) => { cur.has(o) ? cur.delete(o) : cur.add(o); e.target.setAttribute("aria-pressed", String(cur.has(o))); onchange([...cur]); },
  }, o))));
}
function labelsFields(spec, key, onchange) {
  const cur = typeof spec.label === "string" ? { [locales()[0]]: spec.label } : { ...(spec.label || {}) };
  return h("div", { class: "pair" }, ...locales().map((loc) => textField(`Etichetta (${loc})`, cur[loc] || "", (v) => {
    cur[loc] = v;
    onchange(Object.fromEntries(Object.entries(cur).filter(([, x]) => x)));
  })));
}
function rename(obj, oldKey, newKey) {
  const out = {};
  for (const [k, v] of Object.entries(obj)) out[k === oldKey ? newKey : k] = v;
  return out;
}

function inspEntity({ name }) {
  const e = ent(name);
  const fieldKeys = Object.keys(fieldsOf(name));
  const perms = (e.permissions ||= {});
  const princ = principals(name).filter((p) => p !== "admin");
  return [
    h("h2", {}, name), h("p", { class: "sub" }, isProcess(name) ? "Processo con workflow" : "Anagrafica"),
    textField("Nome (PascalCase)", name, (v) => {
      const nn = pascal(v);
      if (!nn || nn === name || entities()[nn]) return;
      mutate((r) => {
        r.entities = rename(r.entities, name, nn);
        for (const x of Object.values(r.entities)) for (const f of Object.values(x.fields || {})) if (f && f.to === name) f.to = nn;
        if (r.scope && (r.scope.entity === name || r.scope === name)) r.scope = { entity: nn };
        S.layout.entities[nn] = S.layout.entities[name];
        S.layout.workflows[nn] = S.layout.workflows[name];
        S.sel = { type: "entity", name: nn };
      });
    }),
    labelsFields(e, name, (v) => mutate(() => (e.label = v), { rerender: false })),
    selectField("Tipo", isProcess(name) ? "process" : "registry", { registry: "anagrafica (senza workflow)", process: "processo (con workflow)" }, (v) => mutate(() => {
      e.kind = v;
      if (v === "process" && !e.workflow) e.workflow = { states: { draft: { kind: "initial", label: { it: "Bozza", en: "Draft" } }, done: { kind: "final", label: { it: "Concluso", en: "Done" } } },
        transitions: { complete: { label: { it: "Concludi", en: "Complete" }, from: "draft", to: "done", by: ["creator"] } } };
      if (v === "registry") delete e.workflow;
    })),
    textField("Prefisso del codice (es. INV)", e.code_prefix || "", (v) => mutate(() => { if (v) e.code_prefix = v.toUpperCase(); else delete e.code_prefix; })),
    selectField("Campo mostrato come titolo", e.display || "", { "": "automatico", ...(e.code_prefix ? { code: "code" } : {}), ...Object.fromEntries(fieldKeys.map((k) => [k, k])) }, (v) => mutate(() => { if (v) e.display = v; else delete e.display; }, { rerender: false })),
    selectField("Campo di ambito (per i ruoli con ambito)", e.scope_field || "", { "": "nessuno", ...Object.fromEntries(fieldKeys.filter((k) => fieldSpec(name, k).type === "ref").map((k) => [k, k])) }, (v) => mutate(() => { if (v) e.scope_field = v; else delete e.scope_field; }, { rerender: false })),
    h("fieldset", {}, h("legend", {}, "Permessi (admin può sempre tutto)"),
      ...["read", "create", "update", "delete"].map((a) => chipsField({ read: "Lettura", create: "Creazione", update: "Modifica", delete: "Eliminazione" }[a], princ,
        asList(perms[a] ?? (a === "read" ? ["all"] : [])), (v) => mutate(() => (perms[a] = v), { rerender: false })))),
    isProcess(name) ? h("button", { class: "ghost", onclick: () => { S.wfEntity = name; S.view = "workflow"; render(); } }, "Apri il workflow") : null,
    h("div", { class: "danger-zone" }, h("button", { class: "small danger", onclick: () => {
      if (!confirm(`Eliminare l'entità ${name} dal modello? I dati esistenti richiederanno una migrazione manuale.`)) return;
      mutate((r) => { delete r.entities[name]; S.sel = null; });
    } }, "Elimina entità")),
  ];
}

function inspField({ entity, key }) {
  const f = fieldSpec(entity, key);
  const type = f.type || "string";
  const targets = ["User", ...Object.keys(entities())];
  return [
    h("h2", {}, `${entity}.${key}`), h("p", { class: "sub" }, "Campo"),
    textField("Chiave (snake_case)", key, (v) => {
      const nk = snake(v);
      if (!nk || nk === key || fieldsOf(entity)[nk]) return;
      mutate(() => {
        const spec = fieldSpec(entity, key);
        if (!spec.renamed_from) spec.renamed_from = key; // keeps the data at the next generation
        ent(entity).fields = rename(fieldsOf(entity), key, nk);
        S.sel = { type: "field", entity, key: nk };
      });
    }),
    labelsFields(f, key, (v) => mutate(() => (f.label = v), { rerender: false })),
    selectField("Tipo", type, Object.fromEntries(FIELD_TYPES.map((t) => [t, t])), (v) => mutate(() => {
      f.type = v;
      if (v !== "ref") { delete f.to; delete f.many; delete f.on_delete; }
      if (v !== "enum") delete f.enum;
      if (v === "ref" && !f.to) f.to = "User";
      if (v === "enum" && !f.enum) f.enum = Object.keys(S.raw.enums || {})[0];
    })),
    type === "ref" ? selectField("Riferimento a", f.to || "User", Object.fromEntries(targets.map((t) => [t, t])), (v) => mutate(() => (f.to = v))) : null,
    type === "ref" ? checkField("Riferimento multiplo (tabella di collegamento)", f.many, (v) => mutate(() => { if (v) f.many = true; else delete f.many; })) : null,
    type === "ref" && !f.many ? selectField("Se il riferito viene eliminato", f.on_delete || "", { "": "automatico", restrict: "impedisci", set_null: "svuota il campo", cascade: "elimina anche questo" }, (v) => mutate(() => { if (v) f.on_delete = v; else delete f.on_delete; }, { rerender: false })) : null,
    type === "enum" ? selectField("Enumerazione", f.enum || "", Object.fromEntries(Object.keys(S.raw.enums || {}).map((n) => [n, n])), (v) => mutate(() => (f.enum = v))) : null,
    checkField("Obbligatorio", f.required, (v) => mutate(() => { if (v) f.required = true; else delete f.required; })),
    checkField("Unico", f.unique, (v) => mutate(() => { if (v) f.unique = true; else delete f.unique; }, { rerender: false })),
    checkField("Mostra nell'elenco", f.list ?? null, (v) => mutate(() => (f.list = v), { rerender: false })),
    checkField("Sola lettura (impostato da reazioni o codice)", f.readonly, (v) => mutate(() => { if (v) f.readonly = true; else delete f.readonly; }, { rerender: false })),
    textField("Valore predefinito", f.default ?? "", (v) => mutate(() => { if (v === "" || v === null) delete f.default; else f.default = ["int", "number", "money"].includes(type) ? Number(v) : type === "bool" ? v === "true" : v; }, { rerender: false })),
    ["int", "number", "money"].includes(type) ? h("div", { class: "pair" },
      textField("Minimo", f.min ?? "", (v) => mutate(() => { if (v === null) delete f.min; else f.min = v; }, { rerender: false }), { number: true }),
      textField("Massimo", f.max ?? "", (v) => mutate(() => { if (v === null) delete f.max; else f.max = v; }, { rerender: false }), { number: true })) : null,
    h("div", { class: "danger-zone" }, h("button", { class: "small danger", onclick: () => mutate(() => { delete fieldsOf(entity)[key]; S.sel = { type: "entity", name: entity }; }) }, "Elimina campo")),
  ];
}

function stateNames(entity) { return Object.keys(workflow(entity).states || {}); }
function inspState({ entity, key }) {
  const wf = workflow(entity);
  const st = (wf.states[key] ||= {});
  const princ = principals(entity).filter((p) => !["admin", "all"].includes(p));
  const rem = st.reminder;
  const remDays = rem === undefined || rem === null ? "" : typeof rem === "object" ? rem.after_days ?? 7 : rem;
  return [
    h("h2", {}, labelOf(st, key)), h("p", { class: "sub" }, `Stato di ${entity}`),
    textField("Chiave", key, (v) => {
      const nk = snake(v);
      if (!nk || nk === key || wf.states[nk]) return;
      mutate(() => {
        if (!st.renamed_from) st.renamed_from = key; // records are moved at the next generation
        wf.states = rename(wf.states, key, nk);
        for (const t of Object.values(wf.transitions || {})) {
          if (t.to === key) t.to = nk;
          if (Array.isArray(t.from)) t.from = t.from.map((x) => (x === key ? nk : x)); else if (t.from === key) t.from = nk;
        }
        const lay = S.layout.workflows[entity] || {};
        lay[nk] = lay[key];
        S.sel = { type: "state", entity, key: nk };
      });
    }),
    labelsFields(st, key, (v) => mutate(() => (st.label = v))),
    selectField("Tipo", st.kind || (stateNames(entity)[0] === key ? "initial" : "normal"), STATE_KINDS, (v) => mutate(() => {
      if (v === "initial") for (const s of Object.values(wf.states)) if (s && s.kind === "initial") s.kind = "normal";
      st.kind = v;
    })),
    chipsField("In carico a (compare nella loro scrivania)", princ, asList(st.owner), (v) => mutate(() => (st.owner = v), { rerender: false })),
    chipsField("Chi può modificare i dati in questo stato", princ, asList(st.editable_by), (v) => mutate(() => (st.editable_by = v), { rerender: false })),
    textField("Sollecito dopo N giorni (vuoto = nessuno)", remDays, (v) => mutate(() => { if (v === null) delete st.reminder; else st.reminder = { after_days: v, template: (typeof rem === "object" && rem?.template) || `${key}_reminder` }; }), { number: true }),
    textField("Colore", st.color || "", (v) => mutate(() => { if (v) st.color = v; else delete st.color; }), { placeholder: "#2563eb" }),
    h("div", { class: "row" }, h("button", { class: "ghost", onclick: () => { S.connectFrom = key; render(); toast("Ora clicca lo stato di arrivo"); } }, "Nuova transizione da qui")),
    h("div", { class: "danger-zone" }, h("button", { class: "small danger", onclick: () => mutate(() => {
      delete wf.states[key];
      for (const [tk, t] of Object.entries(wf.transitions || {})) {
        if (t.to === key) delete wf.transitions[tk];
        else if (Array.isArray(t.from)) t.from = t.from.filter((x) => x !== key);
        else if (t.from === key) delete wf.transitions[tk];
      }
      S.sel = null;
    }) }, "Elimina stato")),
  ];
}

function clausesEditor(entity, clauses, onchange) {
  const list = asList(clauses).map((c) => ({ ...c }));
  const fieldKeys = ["state", ...Object.keys(fieldsOf(entity))];
  const wrap = h("div", {});
  const draw = () => {
    wrap.replaceChildren(
      ...list.map((c, i) => h("div", { class: "clause" },
        h("select", { onchange: (e) => { c.field = e.target.value; onchange(list); } }, ...fieldKeys.map((k) => h("option", { value: k, selected: c.field === k }, k))),
        h("select", { onchange: (e) => { c.op = e.target.value; if (UNARY.includes(c.op)) delete c.value; onchange(list); draw(); } }, ...OPS.map((o) => h("option", { value: o, selected: c.op === o }, o))),
        UNARY.includes(c.op) ? h("span", {}) : (() => {
          const inp = h("input", { type: "text", value: Array.isArray(c.value) ? c.value.join(", ") : c.value ?? "" });
          inp.addEventListener("change", () => {
            const raw = inp.value.trim();
            c.value = ["in", "not_in"].includes(c.op) ? raw.split(",").map((s) => s.trim()).filter(Boolean) : /^-?\d+(\.\d+)?$/.test(raw) ? Number(raw) : raw === "true" ? true : raw === "false" ? false : raw;
            onchange(list);
          });
          return inp;
        })(),
        h("button", { type: "button", title: "Rimuovi", onclick: () => { list.splice(i, 1); onchange(list); draw(); } }, "×"))),
      h("button", { type: "button", class: "small", onclick: () => { list.push({ field: fieldKeys[1] || "state", op: "is_set" }); onchange(list); draw(); } }, "+ condizione"));
  };
  draw();
  return wrap;
}

function inspTransition({ entity, key }) {
  const wf = workflow(entity);
  const t = (wf.transitions[key] ||= {});
  const timed = t.trigger && typeof t.trigger === "object";
  const dateFields = Object.keys(fieldsOf(entity)).filter((k) => ["date", "datetime"].includes(fieldSpec(entity, k).type));
  const princ = principals(entity).filter((p) => p !== "admin");
  const declared = Object.keys(S.raw.events || {});
  return [
    h("h2", {}, labelOf(t, key)), h("p", { class: "sub" }, `Transizione di ${entity}`),
    textField("Chiave", key, (v) => {
      const nk = snake(v);
      if (!nk || nk === key || wf.transitions[nk]) return;
      mutate(() => { wf.transitions = rename(wf.transitions, key, nk); S.sel = { type: "transition", entity, key: nk }; });
    }),
    labelsFields(t, key, (v) => mutate(() => (t.label = v))),
    chipsField("Da", stateNames(entity), t.from === "*" ? stateNames(entity) : asList(t.from), (v) => mutate(() => (t.from = v.length === 1 ? v[0] : v))),
    selectField("A", t.to || "", Object.fromEntries(stateNames(entity).map((s) => [s, s])), (v) => mutate(() => (t.to = v))),
    selectField("Esecuzione", timed ? "timed" : "manual", { manual: "manuale (un utente)", timed: "automatica a una data" }, (v) => mutate(() => {
      if (v === "timed") { t.trigger = { at: dateFields[0] || "", offset: "+1d" }; delete t.by; } else { delete t.trigger; t.by = t.by || ["admin"]; }
    })),
    timed ? h("div", { class: "pair" },
      selectField("Alla data del campo", t.trigger.at || "", Object.fromEntries(dateFields.map((k) => [k, k])), (v) => mutate(() => (t.trigger.at = v), { rerender: false })),
      textField("Scostamento", t.trigger.offset || "", (v) => mutate(() => (t.trigger.offset = v), { rerender: false }), { placeholder: "+1d" }))
      : chipsField("Chi può eseguirla", princ, asList(t.by), (v) => mutate(() => (t.by = v), { rerender: false })),
    selectField("Commento", t.comment === true ? "required" : t.comment || "optional", { optional: "facoltativo", required: "obbligatorio", none: "nessuno" }, (v) => mutate(() => { if (v === "optional") delete t.comment; else t.comment = v; }, { rerender: false })),
    h("fieldset", {}, h("legend", {}, "Condizioni (se false l'azione non compare)"), clausesEditor(entity, t.condition, (v) => mutate(() => { if (v.length) t.condition = v; else delete t.condition; }, { rerender: false }))),
    h("fieldset", {}, h("legend", {}, "Requisiti (se non soddisfatti l'azione è bloccata e spiega cosa manca)"), clausesEditor(entity, t.guard, (v) => mutate(() => { if (v.length) t.guard = v; else delete t.guard; }, { rerender: false }))),
    declared.length ? chipsField("Emette anche gli eventi", declared, asList(t.emits), (v) => mutate(() => { if (v.length) t.emits = v; else delete t.emits; }, { rerender: false })) : null,
    h("div", { class: "danger-zone" }, h("button", { class: "small danger", onclick: () => mutate(() => { delete wf.transitions[key]; S.sel = null; }) }, "Elimina transizione")),
  ];
}

function inspReaction({ index }) {
  const r = S.raw.reactions[index];
  if (!r) throw new Error("gone");
  const events = S.analysis.events || [];
  const entSnake = (r.on || "").split(".")[0];
  const entityName = Object.keys(entities()).find((n) => snake(n) === entSnake || (ent(n).table || "") === entSnake);
  const isWf = /\.(transitioned|completed|reminder)$/.test(r.on || "") && entityName && isProcess(entityName);
  const when = (r.when ||= {});
  const hasEmail = (target) => target === "User" || Object.values((ent(target) || {}).fields || {}).some((f) => f && f.type === "email");
  const princ = entityName
    ? principals(entityName, true).filter((p) => !["all", "admin"].includes(p))
        .filter((p) => !p.startsWith("field:") || hasEmail(fieldSpec(entityName, p.slice(6)).to)).concat(["admin"])
    : ["admin", ...Object.keys(S.raw.roles || {})];
  const out = [
    h("h2", {}, r.name || `reaction_${index + 1}`), h("p", { class: "sub" }, "Reazione"),
    textField("Nome", r.name || "", (v) => mutate(() => (r.name = snake(v)))),
    selectField("Quando avviene l'evento", r.on || "", Object.fromEntries(["", ...events].map((e) => [e, e || "scegli…"])), (v) => mutate(() => { r.on = v; r.when = {}; })),
    isWf ? chipsField("Solo per le transizioni", Object.keys(workflow(entityName).transitions || {}), asList(when.transition), (v) => mutate(() => { if (v.length) when.transition = v; else delete when.transition; }, { rerender: false })) : null,
    isWf ? chipsField("Solo verso gli stati", stateNames(entityName), asList(when.to), (v) => mutate(() => { if (v.length) when.to = v; else delete when.to; }, { rerender: false })) : null,
    entityName ? h("fieldset", {}, h("legend", {}, "Solo se"), clausesEditor(entityName, when.clauses, (v) => mutate(() => { if (v.length) when.clauses = v; else delete when.clauses; }, { rerender: false }))) : null,
    selectField("Cosa fa", r.do || "", { "": "scegli…", ...REACTIONS }, (v) => mutate(() => { for (const k of ["to", "template", "set", "transition", "event", "at", "channel", "handler"]) delete r[k]; r.do = v; })),
  ];
  if (r.do === "notify") out.push(
    chipsField("Destinatari", princ, asList(r.to), (v) => mutate(() => (r.to = v), { rerender: false })),
    textField("Altre email (separate da virgola)", asList(r.to).filter((x) => x.startsWith("email:")).map((x) => x.slice(6)).join(", "), (v) => mutate(() => {
      r.to = asList(r.to).filter((x) => !x.startsWith("email:")).concat(v.split(",").map((s) => s.trim()).filter(Boolean).map((s) => `email:${s}`));
    }, { rerender: false })),
    textField("Template (chiave usata da chi invia, es. n8n)", r.template || "", (v) => mutate(() => (r.template = v), { rerender: false })));
  if (r.do === "set" && entityName) out.push(textField("Valori, uno per riga: campo: valore (speciali: =now, =today, =actor, =null)",
    Object.entries(r.set || {}).map(([k, v]) => `${k}: ${v}`).join("\n"), (v) => mutate(() => {
      r.set = Object.fromEntries(v.split("\n").map((l) => l.split(/:(.*)/s)).filter((p) => p[0]?.trim() && p.length > 1).map(([k, val]) => {
        const x = val.trim();
        return [k.trim(), /^-?\d+(\.\d+)?$/.test(x) ? Number(x) : x === "true" ? true : x === "false" ? false : x];
      }));
    }, { rerender: false }), { multiline: true }));
  if (r.do === "transition" && entityName && isProcess(entityName)) out.push(selectField("Transizione", r.transition || "", Object.fromEntries(["", ...Object.keys(workflow(entityName).transitions || {})].map((k) => [k, k || "scegli…"])), (v) => mutate(() => (r.transition = v), { rerender: false })));
  if (r.do === "schedule") out.push(
    selectField("Evento da pianificare", r.event || "", Object.fromEntries(["", ...Object.keys(S.raw.events || {})].map((k) => [k, k || "scegli…"])), (v) => mutate(() => (r.event = v), { rerender: false })),
    textField("Quando (campo data ± scostamento)", r.at || "", (v) => mutate(() => (r.at = v), { rerender: false }), { placeholder: "start_date - 3d" }));
  if (r.do === "broadcast") out.push(textField("Canale", r.channel || "", (v) => mutate(() => (r.channel = v), { rerender: false }), { placeholder: "dashboard" }));
  if (r.do === "custom") out.push(textField("Handler (funzione SQL custom_<nome>)", r.handler || "", (v) => mutate(() => (r.handler = snake(v)), { rerender: false })),
    h("p", { class: "hint" }, "Il generatore crea uno stub; il codice si scrive in Claude Code con /appforge:custom."));
  out.push(h("div", { class: "danger-zone" }, h("button", { class: "small danger", onclick: () => mutate(() => { S.raw.reactions.splice(index, 1); S.sel = null; }) }, "Elimina reazione")));
  return out;
}

function inspEnum({ name }) {
  const en = S.raw.enums[name];
  const values = asList(Array.isArray(en) ? en : en.values).map((v) => (typeof v === "object" ? v.key ?? Object.keys(v)[0] : v));
  return [
    h("h2", {}, name), h("p", { class: "sub" }, "Enumerazione"),
    textField("Valori (uno per riga, snake_case)", values.join("\n"), (v) => mutate(() => {
      const old = Array.isArray(en) ? {} : Object.fromEntries(asList(en.values).filter((x) => typeof x === "object").map((x) => [x.key ?? Object.keys(x)[0], x]));
      S.raw.enums[name] = { ...(Array.isArray(en) ? {} : en), values: v.split("\n").map((s) => snake(s)).filter(Boolean).map((k) => old[k] && old[k].key ? old[k] : { key: k, label: { [locales()[0]]: k } }) };
    }), { multiline: true }),
    h("p", { class: "hint" }, "Le etichette tradotte dei valori si modificano nella vista YAML."),
    h("div", { class: "danger-zone" }, h("button", { class: "small danger", onclick: () => mutate(() => { delete S.raw.enums[name]; S.sel = null; }) }, "Elimina enumerazione")),
  ];
}
function inspRole({ key }) {
  const r = (S.raw.roles[key] = typeof S.raw.roles[key] === "object" && S.raw.roles[key] ? S.raw.roles[key] : { label: S.raw.roles[key] });
  return [
    h("h2", {}, key), h("p", { class: "sub" }, "Ruolo"),
    labelsFields(r, key, (v) => mutate(() => (r.label = v))),
    checkField("Con ambito (assegnato per singolo elemento dell'ambito)", r.scoped, (v) => mutate(() => { if (v) r.scoped = true; else delete r.scoped; })),
    h("div", { class: "danger-zone" }, h("button", { class: "small danger", onclick: () => mutate(() => { delete S.raw.roles[key]; S.sel = null; }) }, "Elimina ruolo")),
  ];
}
function inspEvent({ key }) {
  const ev = S.raw.events[key];
  const spec = typeof ev === "object" && ev ? ev : { description: ev || "" };
  return [
    h("h2", {}, key), h("p", { class: "sub" }, "Evento di dominio"),
    textField("Descrizione", spec.description || "", (v) => mutate(() => (S.raw.events[key] = { ...spec, description: v }), { rerender: false })),
    selectField("Categoria", spec.category || "domain", { domain: "dominio", workflow: "workflow" }, (v) => mutate(() => (S.raw.events[key] = { ...spec, category: v }), { rerender: false })),
    h("div", { class: "danger-zone" }, h("button", { class: "small danger", onclick: () => mutate(() => { delete S.raw.events[key]; S.sel = null; }) }, "Elimina evento")),
  ];
}

/* ----------------------------------------------------------------- adders */
function ask(title, fields) {
  return new Promise((resolve) => {
    const dlg = $("#dlg");
    $("#dlg-title").textContent = title;
    const inputs = fields.map((f) => {
      const el = f.options
        ? h("select", {}, ...Object.entries(f.options).map(([v, l]) => h("option", { value: v }, l)))
        : h("input", { type: "text", placeholder: f.placeholder || "", value: f.value || "" });
      return { f, el };
    });
    $("#dlg-body").replaceChildren(...inputs.map(({ f, el }) => h("label", { class: "f" }, h("span", {}, f.label), el)));
    dlg.returnValue = "";
    dlg.onclose = () => resolve(dlg.returnValue === "ok" ? Object.fromEntries(inputs.map(({ f, el }) => [f.name, el.value.trim()])) : null);
    dlg.showModal();
    inputs[0]?.el.focus();
  });
}
async function addEntity() {
  const r = await ask("Nuova entità", [{ name: "name", label: "Nome (es. Ordine, PurchaseOrder)" }, { name: "kind", label: "Tipo", options: { registry: "anagrafica", process: "processo con workflow" } }]);
  if (!r || !r.name) return;
  const name = pascal(r.name);
  if (entities()[name]) return toast("Esiste già un'entità con questo nome", true);
  mutate(() => {
    entities()[name] = { label: { [locales()[0]]: r.name }, ...(r.kind === "process" ? { kind: "process" } : {}),
      fields: { name: { type: "string", required: true, label: { it: "Nome", en: "Name" } } } };
    if (r.kind === "process") {
      ent(name).workflow = { states: { draft: { kind: "initial", label: { it: "Bozza", en: "Draft" }, owner: ["creator"], editable_by: ["creator"] }, done: { kind: "final", label: { it: "Concluso", en: "Done" } } },
        transitions: { complete: { label: { it: "Concludi", en: "Complete" }, from: "draft", to: "done", by: ["creator"] } } };
      ent(name).permissions = { create: ["all"] };
    }
    S.layout.entities[name] = defaultPos(Object.keys(entities()).length - 1);
    S.sel = { type: "entity", name };
  });
}
async function addField(entity) {
  const r = await ask(`Nuovo campo di ${entity}`, [{ name: "key", label: "Chiave (es. start_date)" }, { name: "type", label: "Tipo", options: Object.fromEntries(FIELD_TYPES.map((t) => [t, t])) }]);
  if (!r || !r.key) return;
  const key = snake(r.key);
  if (fieldsOf(entity)[key]) return toast("Il campo esiste già", true);
  mutate(() => {
    fieldsOf(entity)[key] = { type: r.type, label: { [locales()[0]]: r.key }, ...(r.type === "ref" ? { to: "User" } : {}), ...(r.type === "enum" ? { enum: Object.keys(S.raw.enums || {})[0] } : {}) };
    S.sel = { type: "field", entity, key };
  });
}
async function addEnum() {
  const r = await ask("Nuova enumerazione", [{ name: "name", label: "Nome (es. Priority)" }, { name: "values", label: "Valori separati da virgola", placeholder: "low, medium, high" }]);
  if (!r || !r.name) return;
  const name = pascal(r.name);
  mutate(() => {
    (S.raw.enums ||= {})[name] = { values: r.values.split(",").map((s) => snake(s)).filter(Boolean).map((k) => ({ key: k, label: { [locales()[0]]: k } })) };
    S.sel = { type: "enum", name };
  });
}
async function addState() {
  const r = await ask(`Nuovo stato di ${S.wfEntity}`, [{ name: "key", label: "Chiave (es. approved)" }, { name: "label", label: `Etichetta (${locales()[0]})` }]);
  if (!r || !r.key) return;
  const key = snake(r.key);
  mutate(() => {
    workflow(S.wfEntity).states[key] = { label: { [locales()[0]]: r.label || r.key } };
    S.sel = { type: "state", entity: S.wfEntity, key };
  });
}
async function addReaction() {
  mutate(() => {
    (S.raw.reactions ||= []).push({ name: `reaction_${S.raw.reactions.length + 1}`, on: "", do: "notify", to: [], template: "" });
    S.sel = { type: "reaction", index: S.raw.reactions.length - 1 };
  });
}
async function addEvent() {
  const r = await ask("Nuovo evento di dominio", [{ name: "key", label: "Tipo (entità.nome, es. invitation.visit_ended)" }, { name: "description", label: "Descrizione" }]);
  if (!r || !r.key) return;
  mutate(() => { (S.raw.events ||= {})[r.key] = { description: r.description || r.key }; S.sel = { type: "event", key: r.key }; });
}
async function addRole() {
  const r = await ask("Nuovo ruolo", [{ name: "key", label: "Chiave (es. reviewer)" }, { name: "label", label: `Etichetta (${locales()[0]})` },
    { name: "scoped", label: "Ambito", options: { no: "globale", yes: "con ambito" } }]);
  if (!r || !r.key) return;
  const key = snake(r.key);
  mutate(() => { (S.raw.roles ||= {})[key] = { label: { [locales()[0]]: r.label || r.key }, ...(r.scoped === "yes" ? { scoped: true } : {}) }; S.sel = { type: "role", key }; });
}
async function newApp() {
  const r = await ask("Nuova applicazione", [
    { name: "dir", label: "Cartella (verrà creata)", placeholder: "~/Progetti/nuova-app" },
    { name: "name", label: "Nome dell'applicazione" },
    { name: "domain", label: "Dominio email ammesso (facoltativo)", placeholder: "gssi.it" },
    { name: "admin", label: "Email dell'amministratore iniziale" },
  ]);
  if (!r || !r.dir) return;
  try {
    const slug = r.dir.split(/[\\/]/).filter(Boolean).pop().toLowerCase().replace(/[^a-z0-9-]+/g, "-");
    const res = await api("POST", "/api/new", { ...r, slug });
    toast(`Creata in ${res.path}`);
    await loadApps();
    await openApp(res.slug);
  } catch (e) {
    toast(e.message, true);
  }
}
async function registerExisting() {
  const r = await ask("Aggiungi un'applicazione esistente", [{ name: "path", label: "Cartella che contiene app.yaml" }]);
  if (!r || !r.path) return;
  try {
    await api("POST", "/api/register", r);
    await loadApps();
  } catch (e) {
    toast(e.message, true);
  }
}

/* ------------------------------------------------------------------- boot */
function boot() {
  const params = new URLSearchParams(location.hash.slice(1));
  S.token = params.get("token") || "";
  document.querySelectorAll(".tabs [role=tab]").forEach((b) => b.addEventListener("click", () => {
    if (S.view === "yaml" && S.yamlDraft !== null) S.yamlDraft = null; // the parsed draft is already in S.raw
    S.view = b.dataset.view;
    S.connectFrom = null;
    render();
  }));
  $("#btn-save").addEventListener("click", save);
  $("#btn-undo").addEventListener("click", undo);
  $("#btn-new-app").addEventListener("click", newApp);
  $("#btn-register").addEventListener("click", registerExisting);
  $("#btn-problems").addEventListener("click", () => {
    const p = $("#problems");
    p.hidden = !p.hidden;
    $("#btn-problems").setAttribute("aria-expanded", String(!p.hidden));
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); if (S.dirty) save(); }
    if ((e.ctrlKey || e.metaKey) && e.key === "z" && !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) { e.preventDefault(); undo(); }
    if (e.key === "Escape" && S.connectFrom) { S.connectFrom = null; render(); }
  });
  window.addEventListener("beforeunload", (e) => { if (S.dirty) e.preventDefault(); });
  window.addEventListener("resize", () => requestAnimationFrame(drawEdges));
  loadApps().then(() => {
    const app = params.get("app") || (S.apps.length === 1 ? S.apps[0].slug : null);
    if (app) openApp(app);
    else render();
  }).catch((e) => toast(e.message, true));
}
boot();
