/*
 * <metamodel-editor> — framework-free editor of the domain metamodel of this application (Ecore notation).
 *
 * Installed by the modeler plugin (`modeler install`) and owned by the app: the admin page
 * (src/components/modeler/metamodel-modeler.tsx) renders it; a save becomes a change proposal.
 *
 *   const el = document.querySelector("metamodel-editor");
 *   el.metamodel = json;            // canonical form: src/lib/modeler/metamodel.json (`npm run model:sync`)
 *   el.behavior = json;             // optional: src/lib/modeler/behavior.json (behavior.yaml as the app reads it);
 *                                   // the workflow of the selected class is shown and edited in the bottom panel,
 *                                   // derived attributes show their formula, roles and reactions are in the side panel
 *   el.readonly = false;
 *   el.addEventListener("change", (e) => { e.detail.metamodel; e.detail.behavior; });
 *   el.addEventListener("save", (e) => { e.detail.metamodel; e.detail.behavior; e.detail.note; });   // behavior: for behavior.yaml
 *   el.addEventListener("select", (e) => e.detail.name);   // the class or enum selected (null: none)
 *
 * Attributes: lang="it|en", save-label="…", readonly.
 * The diagram positions are kept in metamodel.diagram ({Class: {x, y}}).
 *
 * The same file defines <workflow-view>: the state diagram of one workflow with the state a record is in
 * (src/components/modeler/workflow-view.tsx puts it on the record pages):
 *
 *   const v = document.querySelector("workflow-view");
 *   v.workflow = behavior.workflows.Task;   // one workflow of behavior.json
 *   v.setAttribute("state", "doing");       // the current state: its box filled with its colour (white text, a ring),
 *                                            // the other states and connectors dimmed, the transitions leaving it at
 *                                            // full strength (also the `state` property; an unknown value sets
 *                                            // data-state-missing on the element and draws the diagram neutral)
 * Attributes: lang="it|en", name="Task" (for the accessible label), state="<key>".
 */
(() => {

  // Version of the modeler plugin that installed this file: written by `modeler install`, shown in the toolbar.
  const VERSION = "__MODELER_VERSION__";

  const DATATYPES = ["EString", "Text", "Email", "URL", "EInt", "ELong", "EDouble", "EBigDecimal", "Money",
    "EBoolean", "Date", "EDate", "JSON"];
  const MULTS = [["0..1", 0, 1], ["1", 1, 1], ["0..*", 0, -1], ["1..*", 1, -1]];
  const CLASS_RE = /^[A-Z][A-Za-z0-9]{1,39}$/;
  const FEATURE_RE = /^[a-z][A-Za-z0-9_]{0,39}$/;
  const LITERAL_RE = /^[A-Za-z][A-Za-z0-9_]{0,39}$/;
  const RESERVED = ["id", "createdAt", "updatedAt", "created_at", "updated_at"];
  const HEAD_H = 32, ROW_H = 19, PAD = 8, CHAR_W = 7.4;
  const MAX_ROWS = 12;                     // attributes shown in a box before "+N" (all of them with "Tutti")
  const GAP_X = 110, GAP_Y = 56, MARGIN = 24, K_MIN = 0.25, K_MAX = 2;

  /* ------------------------------------------------------------------ pure layout (no DOM)
   * Box sizes, placement and connector routing are pure functions of the metamodel: the editor draws what they
   * return, and plugins/modeler/tests/layout.test.mjs checks them with `node --test` (no overlapping boxes, no
   * connectors sharing a run or crossing a box, labels clear of boxes and of each other). */
  const multText = (lo, up) => (lo === 1 && up === 1 ? "1" : `${lo}..${up === -1 ? "*" : up}`);
  const LABEL_CHAR_W = 6.6, LABEL_H = 14;
  const PORT_STAGGER = 4;                  // incoming ports sit a few px off the outgoing ones
  const LANES = [0, 8, -8, 16, -16, 24, -24, 32, -32];
  const FRACS = [0.5, 0.3, 0.7, 0.15, 0.85, 0.05, 0.95];   // where the middle run of a Z sits between the two boxes
  const GRID_M = 6, GRID_STUB = 14, GRID_LANES = [0, 8, -8, 16, -16], GRID_BEND = 40, GRID_SHARE = 400, GRID_MAX = 60000;
  const BUS_MIN = 4;                       // references entering the same side of a class that share a bus
  const BUS_GAP = 28;                      // distance of the trunk of a bus from the side of the class
  const STEREO_H = 12;                     // extra head height of a box with a stereotype line («enumeration», «workflow»)
  const WF_PAD = 10, WF_HEAD = 30;         // padding of the workflow panel and height of its heading line
  // the state diagram of the selected workflow, drawn in the panel under the canvas
  const WF = { font: 11, keyFont: 9, labelFont: 10, minBox: 96, maxBox: 200, minGap: 56, maxLabel: 110, margin: 8,
    lane: 8, laneInset: 12, channel: 26, sinkSources: 3, pad: 6, arrow: 8, lOffset: 3.5, color: "#64748b", charW: 0.56 };

  const Layout = (() => {
    // the class as seen from a state: `model` of the state merged with `requires` (its shorthand for lower: 1),
    // per feature {lower, readonly, hidden, in} (behavior.json keeps `model` as written, with requires apart)
    const stateView = (st) => {
      const out = {};
      for (const f of [].concat(st?.requires || [])) out[f] = { ...(out[f] || {}), lower: 1 };
      for (const [f, o] of Object.entries(st?.model || {})) {
        const cur = out[f] || {};
        out[f] = { lower: o?.lower ?? cur.lower ?? null, readonly: !!(cur.readonly || o?.readonly || o?.hidden), hidden: !!(cur.hidden || o?.hidden), in: o?.in ?? cur.in ?? null };
      }
      for (const o of Object.values(out)) { o.lower ??= null; o.readonly = !!o.readonly; o.hidden = !!o.hidden; o.in ??= null; }
      return out;
    };
    // what the states of a workflow say of each feature: {feature: [{state, label, lower, readonly, hidden, in}]}
    const stateOverlay = (w, lang = "it") => {
      const out = {};
      for (const [sn, st] of Object.entries(w?.states || {})) {
        for (const [f, o] of Object.entries(stateView(st))) (out[f] ||= []).push({ state: sn, label: wfLabel(st, sn, lang), ...o });
      }
      return out;
    };
    // the mark of one feature in one state, as BEHAVIOR.md prints it: ● required, 🔒 read only, ○ hidden, {a, b}
    const viewMark = (o) => (o ? [o.lower === 1 ? "●" : "", o.hidden ? "○" : o.readonly ? "🔒" : "", o.in ? `{${o.in.join(", ")}}` : ""].filter(Boolean).join(" ") : "");
    // the multiplicity of a feature with what the states add: `[1 da Bozza]`, `[0..* · 1 da Bozza]`; `from` = "da"/"from"
    const multWithStates = (f, entries, from) => {
      const base = f.lower === 0 && f.upper === 1 ? "" : multText(f.lower, f.upper);
      const req = (entries || []).filter((x) => x.lower === 1).map((x) => x.label);
      if (!req.length) return base ? ` [${base}]` : "";
      return ` [${base ? base + " · " : ""}1 ${from} ${req.join(", ")}]`;
    };
    const rowItems = (c, allAttrs = false, more = "more", state = null, uses = null, opts = {}) => {
      // attribute lines of a class box: all of them, or the first ones plus "+N more". `🔑` marks the id,
      // `/name` a derived attribute (UML), `⟳` the state attribute of the workflow (`state` of behavior.yaml),
      // ` ·ƒ` a feature the behaviour uses (`uses` of behavior.json for this class: formulas, guards, principals…).
      // `opts.overlay` (stateOverlay) adds «1 da <stato>» to the multiplicity; `opts.view` (stateView of one state)
      // draws the class as seen from that state: `[1]`, 🔒 read only, hidden rows flagged, `∈ {a, b}`.
      const { overlay = null, view = null, from = "from" } = opts;
      const seen = (f, spec) => {
        const v = view?.[f];
        if (!v) return { m: multWithStates(spec, overlay?.[f], from), pre: "", post: "", hidden: false };
        const lower = v.lower ?? spec.lower;
        const m = lower === 0 && spec.upper === 1 ? "" : ` [${multText(lower, spec.upper)}]`;
        return { m, pre: v.readonly && !v.hidden ? "🔒 " : "", post: v.in ? ` ∈ {${v.in.join(", ")}}` : "", hidden: v.hidden };
      };
      const items = Object.entries(c.attributes).map(([an, a]) => {
        const v = seen(an, a);
        const mark = a.id ? "🔑 " : an === state ? "⟳ " : "";
        const used = uses?.attributes?.[an] || null;
        return { text: `${v.pre}${mark}${a.derived ? "/" : ""}${an}: ${a.type}${v.m}${v.post}${used ? " ·ƒ" : ""}`, attr: an, derived: !!a.derived, state: an === state, used, hidden: v.hidden };
      });
      // references to the application users have no box to point to: listed in the class, dimmed
      for (const [rn, r] of Object.entries(c.references)) {
        if (r.type !== "User") continue;
        const v = seen(rn, r);
        const used = uses?.references?.[rn] || null;
        items.push({ text: `${v.pre}↗ ${rn}: User${v.m}${used ? " ·ƒ" : ""}`, ref: rn, muted: true, used, hidden: v.hidden });
      }
      if (allAttrs || items.length <= MAX_ROWS) return items;
      return [...items.slice(0, MAX_ROWS - 1), { text: `… +${items.length - MAX_ROWS + 1} ${more}`, muted: true }];
    };
    const rowsOf = (c, allAttrs, more, state, uses, opts) => rowItems(c, allAttrs, more, state, uses, opts).map((r) => r.text);

    const boxSize = (mm, name, opts = {}) => {
      const c = mm.classes[name];
      const width = (texts, min) => Math.round(Math.max(min, Math.min(380, Math.max(...texts.map((x) => x.length)) * CHAR_W + 24)));
      if (c) {
        const rows = rowsOf(c, opts.allAttrs, opts.more, opts.state, opts.uses, opts);
        // a class with a workflow has a «workflow» stereotype line in its head, like an enum has «enumeration»
        return { w: width([name, ...rows], 160), h: HEAD_H + (opts.workflow ? STEREO_H : 0) + Math.max(1, rows.length) * ROW_H + PAD };
      }
      const e = mm.enums[name];
      return { w: width([name, ...e.literals.map((l) => l.name)], 120), h: HEAD_H + STEREO_H + Math.max(1, e.literals.length) * ROW_H + PAD };
    };

    const normalize = (mm) => {
      const m = JSON.parse(JSON.stringify(mm || {}));
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
      return m;
    };

    const autoLayout = (mm, size, opts = {}) => {
      // Positions of the boxes without one (all of them with force). Order: BFS from the most connected class
      // (neighbours stay close), enums after the classes, near the first class that uses them. Placement: masonry
      // columns, with the number of columns chosen to match the canvas aspect ratio, so that the diagram can be
      // shown as large as possible once fitted.
      const { force = false } = opts;
      const W = opts.width > 50 ? opts.width : 960, H = opts.height > 50 ? opts.height : 600;
      const classes = Object.keys(mm.classes);
      const enums = Object.keys(mm.enums);
      // the gap between columns holds the connectors and their labels: at least the widest reference label
      const labelW = Math.max(0, ...edgesOf({ ...mm, diagram: Object.fromEntries([...classes, ...enums].map((n) => [n, { x: 0, y: 0 }])) }, null, opts.overlay, opts.from)
        .flatMap((e) => [e.labelA, e.labelB]).filter(Boolean).map((t) => t.length * LABEL_CHAR_W + 4));
      const gapX = Math.max(GAP_X, Math.ceil(labelW) + 30);
      const missing = [...classes, ...enums].filter((n) => force || !mm.diagram[n]);
      if (!missing.length) return {};
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
      const nodes = [...order];
      for (const n of order) {
        for (const a of Object.values(mm.classes[n].attributes)) {
          if (mm.enums[a.type] && !nodes.includes(a.type)) nodes.push(a.type);
        }
      }
      for (const e of enums) if (!nodes.includes(e)) nodes.push(e);
      const place = force ? nodes : nodes.filter((n) => !mm.diagram[n]);
      const sizes = Object.fromEntries(place.map((n) => [n, size(n)]));
      // neighbours of every node (references, inheritance, enum attributes), to keep connected boxes close
      const near = Object.fromEntries(nodes.map((n) => [n, new Set(adj[n] || [])]));
      for (const [cn, c] of Object.entries(mm.classes)) {
        for (const a of Object.values(c.attributes)) if (near[a.type] && mm.enums[a.type]) { near[cn].add(a.type); near[a.type].add(cn); }
      }
      const avgH = place.reduce((a, n) => a + sizes[n].h, 0) / Math.max(1, place.length);
      const masonry = (cols) => {
        const colH = new Array(cols).fill(0), colW = new Array(cols).fill(0), at = {};
        for (const n of place) {
          // the shortest column, unless a column nearer to the placed neighbours is not much taller
          const placed = [...near[n]].filter((x) => at[x]).map((x) => at[x][0]);
          const target = placed.length ? placed.reduce((a, b) => a + b, 0) / placed.length : null;
          let c = 0, best = Infinity;
          for (let i = 0; i < cols; i++) {
            const score = colH[i] + (target === null ? 0 : Math.abs(i - target) * avgH * 0.9);
            if (score < best - 1e-6) { best = score; c = i; }
          }
          at[n] = [c, colH[c]];
          colH[c] += sizes[n].h + GAP_Y;
          colW[c] = Math.max(colW[c], sizes[n].w);
        }
        const width = colW.reduce((a, b) => a + b, 0) + gapX * (cols - 1);
        const height = Math.max(...colH) - GAP_Y;
        return { at, colW, width, height, k: Math.min(W / width, H / height) };
      };
      let best = null;
      for (let cols = 1; cols <= Math.max(1, place.length); cols++) {
        const m = masonry(cols);
        if (!best || m.k > best.k + 1e-6) best = m;
      }
      if (!best) return {};
      // new nodes next to the existing diagram (on its right), all nodes from the origin when forced
      const used = Object.entries(mm.diagram).filter(([n]) => !place.includes(n) && (mm.classes[n] || mm.enums[n]));
      const ox = used.length ? Math.max(...used.map(([n, p]) => p.x + size(n).w)) + gapX : 0;
      const colX = [];
      best.colW.reduce((x, w, i) => { colX[i] = x; return x + w + gapX; }, ox);
      const pos = {};
      for (const n of place) {
        const [c, y] = best.at[n];
        pos[n] = { x: Math.round(colX[c] + (best.colW[c] - sizes[n].w) / 2), y: Math.round(y) };
      }
      return pos;
    };

    /* geometry helpers */
    const out = { left: [-1, 0], right: [1, 0], top: [0, -1], bottom: [0, 1] };
    const SIDES = ["right", "left", "bottom", "top"];
    const horizontal = (side) => side === "left" || side === "right";
    const mid = (R, side) => side === "left" ? { x: R.x, y: R.y + R.h / 2 } : side === "right" ? { x: R.x + R.w, y: R.y + R.h / 2 }
      : side === "top" ? { x: R.x + R.w / 2, y: R.y } : { x: R.x + R.w / 2, y: R.y + R.h };
    const segments = (pts) => pts.slice(1).map((q, i) => [pts[i], q]);
    const hitsRect = (p, q, R, m) => {
      const x0 = Math.min(p.x, q.x), x1 = Math.max(p.x, q.x), y0 = Math.min(p.y, q.y), y1 = Math.max(p.y, q.y);
      return x0 < R.x + R.w - m && x1 > R.x + m && y0 < R.y + R.h - m && y1 > R.y + m;
    };
    const rectsOverlap = (a, b, m = 0) => a.x < b.x + b.w + m && b.x < a.x + a.w + m && a.y < b.y + b.h + m && b.y < a.y + a.h + m;
    // two axis-parallel segments on the same line sharing more than a couple of px
    const collinear = ([p, q], [r, s]) => {
      const ov = (a0, a1, b0, b1) => Math.min(Math.max(a0, a1), Math.max(b0, b1)) - Math.max(Math.min(a0, a1), Math.min(b0, b1));
      if (Math.abs(p.y - q.y) < 0.5 && Math.abs(r.y - s.y) < 0.5 && Math.abs(p.y - r.y) < 2) return ov(p.x, q.x, r.x, s.x) > 2;
      if (Math.abs(p.x - q.x) < 0.5 && Math.abs(r.x - s.x) < 0.5 && Math.abs(p.x - r.x) < 2) return ov(p.y, q.y, r.y, s.y) > 2;
      return false;
    };

    const route = (p1, sa, p2, sb, lane, self, detour = 0, frac = 0.5) => {
      const h1 = horizontal(sa), h2 = horizontal(sb);
      const step = 28 + detour * 10;   // connectors going around the boxes get a lane each
      if (self) { const x = p1.x + step; return [p1, { x, y: p1.y }, { x, y: p2.y }, p2]; }
      if (h1 && h2) {
        const facing = out[sa][0] !== out[sb][0] && (out[sa][0] > 0 ? p2.x > p1.x : p2.x < p1.x);
        // facing sides: a Z whose middle run sits at `frac` of the way (so it can pass between other boxes)
        const x = facing ? p1.x + (p2.x - p1.x) * frac + lane : (out[sa][0] > 0 ? Math.max(p1.x, p2.x) + step : Math.min(p1.x, p2.x) - step);
        return Math.abs(p1.y - p2.y) < 1 && facing ? [p1, p2] : [p1, { x, y: p1.y }, { x, y: p2.y }, p2];
      }
      if (!h1 && !h2) {
        const facing = out[sa][1] !== out[sb][1] && (out[sa][1] > 0 ? p2.y > p1.y : p2.y < p1.y);
        const y = facing ? p1.y + (p2.y - p1.y) * frac + lane : (out[sa][1] > 0 ? Math.max(p1.y, p2.y) + step : Math.min(p1.y, p2.y) - step);
        return Math.abs(p1.x - p2.x) < 1 && facing ? [p1, p2] : [p1, { x: p1.x, y }, { x: p2.x, y }, p2];
      }
      // one horizontal and one vertical side: an L, or (detour) out of both boxes and around, when the L crosses one
      if (!detour) return h1 ? [p1, { x: p2.x, y: p1.y }, p2] : [p1, { x: p1.x, y: p2.y }, p2];
      const a = { x: p1.x + out[sa][0] * step, y: p1.y + out[sa][1] * step };
      const b = { x: p2.x + out[sb][0] * step, y: p2.y + out[sb][1] * step };
      return h1 ? [p1, a, { x: a.x, y: b.y }, b, p2] : [p1, a, { x: b.x, y: a.y }, b, p2];
    };

    const branchRoute = (pa, sa, A, J, sb, detour = 0) => {
      // from a source port (side `sa` of the box A) to the trunk of a bus: the line through the junction J parallel
      // to the side `sb` of the target. Arrives square on the trunk; a port on the far side goes around its box.
      const step = 28 + detour * 10;
      const v = horizontal(sb);                       // vertical trunk (x = J.x) when the bus enters a left/right side
      const [ax, ay] = out[sa];
      if (horizontal(sa) === v) {
        const facing = v ? (J.x - pa.x) * ax > 0 : (J.y - pa.y) * ay > 0;
        if (facing) return [pa, v ? { x: J.x, y: pa.y } : { x: pa.x, y: J.y }];
        const o = { x: pa.x + ax * step, y: pa.y + ay * step };
        if (v) { const y = J.y < A.y + A.h / 2 ? A.y - step : A.y + A.h + step; return [pa, o, { x: o.x, y }, { x: J.x, y }]; }
        const x = J.x < A.x + A.w / 2 ? A.x - step : A.x + A.w + step;
        return [pa, o, { x, y: o.y }, { x, y: J.y }];
      }
      const o = { x: pa.x + ax * step, y: pa.y + ay * step };   // a side parallel to the trunk: out, then straight to it
      return [pa, o, v ? { x: J.x, y: o.y } : { x: o.x, y: J.y }];
    };

    /* ------------------------------------------------------------------ workflow (state diagram) layout
     * Port of src/lib/workflow-layout.ts and state-path.ts (mainPath) of guest-invitations-af, the reference of the
     * skill core:diagrams: states in columns by distance from the initial one (the main path on the first row),
     * final states reached from many states on a bottom row with their transitions as a bus, orthogonal connectors
     * each in its own lane (between columns) and channel (between rows), labels where they cover the least. */
    // text widths: an estimate by default (tests, no DOM); the editor measures the real font (opts.measure)
    const wfCharW = (font, bold = false) => font * (bold ? WF.charW + 0.04 : WF.charW);
    const wfTextWidth = (s, font, bold = false) => s.length * wfCharW(font, bold);
    // word wrap to at most `maxLines` lines no wider than `maxWidth`, by measure; the last line is cut with an ellipsis
    const wfWrap = (text, maxWidth, font, maxLines, bold = false, measure = wfTextWidth) => {
      const fits = (l) => measure(l, font, bold) <= maxWidth;
      const cut = (l) => { let c = l; while (c.length > 1 && !fits(`${c}…`)) c = c.slice(0, -1); return `${c}…`; };
      const lines = [];
      let cur = "";
      for (const word of String(text).split(/\s+/).filter(Boolean)) {
        const next = cur ? `${cur} ${word}` : word;
        if (fits(next)) cur = next;
        else { if (cur) lines.push(cur); cur = word; }
      }
      if (cur) lines.push(cur);
      const out = lines.slice(0, maxLines).map((l) => (fits(l) ? l : cut(l)));
      if (lines.length > maxLines) {
        const last = out[maxLines - 1];
        out[maxLines - 1] = fits(`${last}…`) ? `${last}…` : cut(last);
      }
      return out.length ? out : [""];
    };
    // the longest simple path from the initial state to a final one: the "normal" flow of the workflow
    const mainPath = (states, out) => {
      const initial = (states.find((s) => s.kind === "initial") || states[0]).key;
      const final = new Set(states.filter((s) => s.kind === "final").map((s) => s.key));
      let best = [initial], bestEndsFinal = final.has(initial), visits = 0;
      const walk = (path) => {
        if (++visits > 20000) return;
        const last = path[path.length - 1], endsFinal = final.has(last);
        if ((endsFinal && (!bestEndsFinal || path.length > best.length)) || (!bestEndsFinal && !endsFinal && path.length > best.length)) {
          best = [...path]; bestEndsFinal = endsFinal;
        }
        if (endsFinal) return;
        for (const next of out.get(last) || []) if (!path.includes(next)) walk([...path, next]);
      };
      walk([initial]);
      return best;
    };
    const wfLabel = (spec, key, lang) => (typeof spec?.label === "string" ? spec.label : spec?.label?.[lang]) || key;
    // a workflow of behavior.json as the layout reads it
    const workflowModel = (w, lang = "it") => ({
      states: Object.entries(w?.states || {}).map(([key, s]) => ({ key, label: wfLabel(s, key, lang), color: s.color || WF.color, kind: s.initial ? "initial" : s.final ? "final" : "state" })),
      transitions: Object.entries(w?.transitions || {}).map(([key, t]) => ({ key, label: wfLabel(t, key, lang), from: t.from || [], to: t.to, timed: t.at != null })),
    });
    const wfArrowAt = (pts) => {
      const b = pts[pts.length - 1];
      let i = pts.length - 2;
      while (i > 0 && pts[i].x === b.x && pts[i].y === b.y) i--;
      const a = pts[i];
      const len = Math.hypot(b.x - a.x, b.y - a.y) || 1;
      const ux = (b.x - a.x) / len, uy = (b.y - a.y) / len;
      const base = { x: b.x - ux * WF.arrow, y: b.y - uy * WF.arrow };
      return [b, base, { x: base.x - uy * 4, y: base.y + ux * 4 }, { x: base.x + uy * 4, y: base.y - ux * 4 }];
    };
    const wfSimplify = (pts) => {
      const out = [];
      for (const p of pts) {
        if (out.length && Math.abs(out[out.length - 1].x - p.x) < 0.01 && Math.abs(out[out.length - 1].y - p.y) < 0.01) continue;
        if (out.length >= 2) {
          const a = out[out.length - 2], b = out[out.length - 1];
          if ((Math.abs(a.x - b.x) < 0.01 && Math.abs(b.x - p.x) < 0.01) || (Math.abs(a.y - b.y) < 0.01 && Math.abs(b.y - p.y) < 0.01)) { out[out.length - 1] = p; continue; }
        }
        out.push(p);
      }
      return out;
    };
    const wfEmptyLabel = (tr, width, measure) => {
      const lines = wfWrap(`${tr.timed ? "⏱ " : ""}${tr.label}`, width - 10, WF.labelFont, 3, false, measure);
      const w = Math.ceil(Math.max(...lines.map((l) => measure(l, WF.labelFont)))) + 10;
      return { x: 0, y: 0, w, h: lines.length * (WF.labelFont + 3) + 6, lines };
    };
    const wfOverlapArea = (a, b) => Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
    // each label on its own connector, where it covers the fewest boxes, labels and other connectors
    const wfPlaceLabels = (edges, boxes, bounds) => {
      const placed = [];
      const segs = edges.flatMap((e) => e.paths.flatMap((p) => p.slice(1).map((b, i) => ({ id: e.id, a: p[i], b }))));
      const crosses = (r, id) => segs.filter((s) => s.id !== id
        && Math.max(s.a.x, s.b.x) >= r.x && Math.min(s.a.x, s.b.x) <= r.x + r.w
        && Math.max(s.a.y, s.b.y) >= r.y && Math.min(s.a.y, s.b.y) <= r.y + r.h).length;
      const order = [...edges].sort((a, b) => a.paths.flat().length - b.paths.flat().length);
      for (const e of order) {
        const { w, h } = e.label;
        let best = null, bestScore = Infinity;
        for (const p of e.paths) for (let i = 1; i < p.length; i++) {
          const a = p[i - 1], b = p[i];
          const len = Math.hypot(b.x - a.x, b.y - a.y);
          if (len < 6) continue;
          const horizontal = Math.abs(a.y - b.y) < 0.01;
          const shifts = [0, -w / 2 + 3, w / 2 - 3];
          if (horizontal) shifts.push(Math.min(a.x, b.x) + w / 2 - (a.x + b.x) / 2, Math.max(a.x, b.x) - w / 2 - (a.x + b.x) / 2);
          for (const t of [0.5, 0.3, 0.7, 0.15, 0.85]) for (const dx of t === 0.5 ? shifts : shifts.slice(0, 3)) for (const dy of [0, -h / 2 - 2, h / 2 + 2]) {
            const cx = a.x + (b.x - a.x) * t + dx, cy = a.y + (b.y - a.y) * t + dy;
            const r = { x: Math.min(Math.max(cx - w / 2, bounds.x), bounds.x + bounds.w - w), y: Math.min(Math.max(cy - h / 2, bounds.y), bounds.y + bounds.h - h), w, h };
            const score = boxes.reduce((sum, bx) => sum + wfOverlapArea(r, bx) * 40, 0) + placed.reduce((sum, l) => sum + wfOverlapArea(r, l) * 8, 0)
              + crosses(r, e.id) * 60 + (horizontal ? (len >= w + 8 ? 0 : 20) : 35) + Math.abs(t - 0.5) * 10 + (dx ? 6 : 0) + (dy ? 6 : 0);
            if (score < bestScore) { bestScore = score; best = r; }
          }
        }
        if (best) { Object.assign(e.label, best); placed.push(best); }
      }
    };
    // { width, height, boxes: [{key,label,color,kind,x,y,w,h,lines}], edges: [{id,key,from,color,timed,paths,arrow,dots,label}]
    // (from: the source states of the edge; a bus has all of them)
    // opts.measure(text, font, bold) -> px: the real text widths (default: the estimate wfTextWidth)
    const workflowLayout = (states, transitions, width, opts = {}) => {
      const measure = opts.measure || wfTextWidth;
      if (!states.length) return { width, height: 0, boxes: [], edges: [] };
      const byKey = new Map(states.map((s) => [s.key, s]));
      const pairs = transitions.flatMap((tr) => tr.from.filter((f) => f !== tr.to && byKey.has(f) && byKey.has(tr.to)).map((f) => ({ tr, f })));
      const out = new Map(), sources = new Map();
      for (const { tr, f } of pairs) {
        out.set(f, [...new Set([...(out.get(f) || []), tr.to])]);
        sources.set(tr.to, new Set([...(sources.get(tr.to) || []), f]));
      }
      // columns: breadth-first distance from the initial state; unreachable states last
      const initial = states.find((s) => s.kind === "initial") || states[0];
      const level = new Map([[initial.key, 0]]);
      const queue = [initial.key];
      while (queue.length) {
        const cur = queue.shift();
        for (const next of out.get(cur) || []) if (!level.has(next)) { level.set(next, level.get(cur) + 1); queue.push(next); }
      }
      const lastLevel = Math.max(0, ...level.values()) + 1;
      for (const s of states) if (!level.has(s.key)) level.set(s.key, lastLevel);
      // sinks: final states reached from many states, drawn on a bottom row
      const sinks = new Set(states.filter((s) => s.kind === "final" && s.key !== initial.key && (sources.get(s.key)?.size || 0) >= WF.sinkSources).map((s) => s.key));
      const regular = states.filter((s) => !sinks.has(s.key));
      const levels = [...new Set(regular.map((s) => level.get(s.key)))].sort((a, b) => a - b);
      const col = new Map(regular.map((s) => [s.key, levels.indexOf(level.get(s.key))]));
      const nCols = Math.max(1, levels.length);
      // rows: the main path first, then the others by the mean row of their neighbours in earlier columns
      const main = mainPath(states, out);
      const neighbours = new Map();
      for (const { tr, f } of pairs) {
        neighbours.set(f, [...(neighbours.get(f) || []), tr.to]);
        neighbours.set(tr.to, [...(neighbours.get(tr.to) || []), f]);
      }
      const row = new Map();
      for (let c = 0; c < nCols; c++) {
        const inCol = regular.filter((s) => col.get(s.key) === c);
        const onMain = inCol.filter((s) => main.includes(s.key)).sort((a, b) => main.indexOf(a.key) - main.indexOf(b.key));
        const bary = (key) => {
          const rs = (neighbours.get(key) || []).filter((n) => row.has(n)).map((n) => row.get(n));
          return rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : Infinity;
        };
        const others = inCol.filter((s) => !main.includes(s.key)).sort((a, b) => bary(a.key) - bary(b.key));
        [...onMain, ...others].forEach((s, i) => row.set(s.key, i));
      }
      const nRegRows = Math.max(1, ...regular.map((s) => row.get(s.key) + 1));
      const sinkRow = nRegRows;
      const taken = new Set();
      for (const key of sinks) {   // each sink under the mean column of its sources, on a free column
        const cs = [...(sources.get(key) || [])].filter((f) => col.has(f)).map((f) => col.get(f));
        const base = Math.round(cs.length ? cs.reduce((a, b) => a + b, 0) / cs.length : 0);
        const free = Array.from({ length: nCols }, (_, c) => c).filter((c) => !taken.has(c)).sort((a, b) => Math.abs(a - base) - Math.abs(b - base) || b - a);
        const c = free.length ? free[0] : base;
        taken.add(c); col.set(key, c); row.set(key, sinkRow);
      }
      const nRows = nRegRows + (sinks.size ? 1 : 0);
      // routing requests: ports on box sides, lanes in the gaps between columns, segments in the channels between rows
      const ports = [], lanes = [], hsegs = [];
      const port = (owner, side, order) => { const p = { owner, side, order }; ports.push(p); return p; };
      const lane = (gap, order, kind) => { const l = { gap, order, kind }; lanes.push(l); return l; };   // kind: 0 left stub, 1 both, 2 right
      const hseg = (ch) => { const h = { ch, x1: 0, x2: 0 }; hsegs.push(h); return h; };
      const ord = (key) => row.get(key) * 100 + col.get(key);
      const normals = [], buses = [];
      for (const tr of transitions) {
        const fs = tr.from.filter((f) => f !== tr.to && byKey.has(f) && byKey.has(tr.to));
        if (!fs.length) continue;
        if (sinks.has(tr.to)) {
          const srcs = fs.map((f) => ({ f, p: port(f, "R", 1e6 + ord(tr.to)) }));
          const colLanes = new Map();
          for (const { f } of srcs) if (!colLanes.has(col.get(f))) colLanes.set(col.get(f), lane(col.get(f) + 1, 1e6, 0));
          buses.push({ tr, srcs, colLanes, tp: port(tr.to, "T", Math.min(...fs.map((f) => col.get(f)))), h: hseg(sinkRow) });
          continue;
        }
        for (const f of fs) {
          const cs = col.get(f), ct = col.get(tr.to), rs = row.get(f), rt = row.get(tr.to);
          const forward = ct > cs;
          const sp = port(f, forward || ct === cs ? "R" : "L", ord(tr.to));
          const tp = port(tr.to, forward ? "L" : "R", ord(f));
          const e = { tr, f, sp, tp };
          const g1 = forward || ct === cs ? cs + 1 : cs, g2 = forward ? ct : ct + 1;
          if (g1 === g2) e.l1 = lane(g1, rs * 10 + rt, forward ? 1 : ct === cs ? 0 : 1);
          else {
            e.l1 = lane(g1, rs, forward || ct === cs ? 0 : 2);
            e.l2 = lane(g2, rt, forward ? 2 : 0);
            const lo = Math.min(rs, rt), hi = Math.max(rs, rt) + 1;   // channel: above for backward edges, below for forward ones
            let best = lo, bestCost = Infinity;
            for (let ch = lo; ch <= hi; ch++) {
              const cost = Math.abs(ch - rs - 0.5) + Math.abs(ch - rt - 0.5) + (forward ? (ch <= Math.min(rs, rt) ? 0.01 : 0) : (ch > Math.max(rs, rt) ? 0.01 : 0));
              if (cost < bestCost) { bestCost = cost; best = ch; }
            }
            e.h = hseg(best);
          }
          normals.push(e);
        }
      }
      // port positions along each side, ordered by where the other end is
      const sideGroups = new Map();
      for (const p of ports) sideGroups.set(`${p.owner}:${p.side}`, [...(sideGroups.get(`${p.owner}:${p.side}`) || []), p]);
      for (const group of sideGroups.values()) {
        group.sort((a, b) => a.order - b.order);
        group.forEach((p, i) => { p.frac = (i + 1) / (group.length + 1); });
      }
      for (const e of normals) {   // adjacent boxes on the same row with ports at the same height: a straight line
        if (e.l1 && !e.l2 && e.sp.side === "R" && e.tp.side === "L" && row.get(e.f) === row.get(e.tr.to) && e.sp.frac === e.tp.frac) {
          lanes.splice(lanes.indexOf(e.l1), 1); e.l1 = undefined; e.tp.straight = true;
        }
      }
      // widths: gaps sized by their lanes and by the longest word of a label, boxes fill the rest
      const word = Math.max(0, ...transitions.flatMap((t) => t.label.split(/\s+/)).map((w) => measure(w, WF.labelFont)));
      const labelW = Math.min(WF.maxLabel, Math.max(WF.minGap - 4, word + 14));   // the longest word always fits a label
      const minGap = Math.max(WF.minGap, labelW + 4);
      const gapLanes = Array.from({ length: nCols + 1 }, (_, g) => lanes.filter((l) => l.gap === g));
      const gapNeed = gapLanes.map((ls, g) => {
        const need = ls.length ? 2 * WF.laneInset + (ls.length - 1) * WF.lane : 0;
        return g > 0 && g < nCols ? Math.max(minGap, need) : Math.max(WF.margin, need);
      });
      let box = (width - gapNeed.reduce((a, b) => a + b, 0)) / nCols;
      const gaps = [...gapNeed];
      if (box > WF.maxBox) {
        const extra = (box - WF.maxBox) * nCols;
        box = WF.maxBox;
        if (nCols > 1) for (let g = 1; g < nCols; g++) gaps[g] += extra / (nCols - 1);
        else { gaps[0] += extra / 2; gaps[1] += extra / 2; }
      }
      const stateWord = Math.max(0, ...states.flatMap((s) => s.label.split(/\s+/)).map((w) => measure(w, WF.font, true)));
      box = Math.max(Math.min(WF.maxBox, Math.max(WF.minBox, Math.ceil(stateWord + 2 * WF.pad))), Math.floor(box));
      const colX = [];
      let x = 0;
      for (let c = 0; c < nCols; c++) { x += gaps[c]; colX.push(x); x += box; }
      const totalW = Math.max(width, x + gaps[nCols]);
      const gapX = (g) => (g === 0 ? 0 : colX[g - 1] + box);
      gapLanes.forEach((ls, g) => {   // stubs towards the left column first, crossing lanes, then towards the right one
        ls.sort((a, b) => a.kind - b.kind || a.order - b.order);
        const span = (ls.length - 1) * WF.lane;
        const x0 = g === 0 ? gaps[0] - WF.laneInset - span : g === nCols ? gapX(g) + WF.laneInset : gapX(g) + (gaps[g] - span) / 2;
        ls.forEach((l, i) => { l.x = x0 + i * WF.lane; });
      });
      // box heights: the longest label decides, all boxes the same height
      const lineH = WF.font + 3;
      const boxLines = new Map(states.map((s) => [s.key, wfWrap(`${s.kind === "initial" ? "▶ " : ""}${s.label}`, box - 2 * WF.pad, WF.font, 3, true, measure)]));
      const maxLines = Math.max(...[...boxLines.values()].map((l) => l.length));
      const boxH = 12 + maxLines * lineH + WF.keyFont + 10;
      // channels: horizontal segments get their own height where their x ranges overlap
      const portX = (p, key) => colX[col.get(key)] + box * (p.frac ?? 0.5);
      for (const e of normals) if (e.h) { e.h.x1 = Math.min(e.l1.x, e.l2.x); e.h.x2 = Math.max(e.l1.x, e.l2.x); }
      for (const b of buses) {
        const xs = [...b.colLanes.values()].map((l) => l.x).concat(portX(b.tp, b.tr.to));
        b.h.x1 = Math.min(...xs); b.h.x2 = Math.max(...xs);
      }
      const chLanes = new Array(nRows + 1).fill(0);
      for (let ch = 0; ch <= nRows; ch++) {
        const segs = hsegs.filter((h) => h.ch === ch).sort((a, b) => a.x1 - b.x1);
        const ends = [];
        for (const h of segs) {
          let k = ends.findIndex((end) => end < h.x1 - 4);
          if (k < 0) { k = ends.length; ends.push(0); }
          ends[k] = h.x2;
          h.y = k;
        }
        chLanes[ch] = ends.length;
      }
      const chH = chLanes.map((n, ch) => {
        const need = n ? 2 * 8 + (n - 1) * WF.lane : 0;
        return ch === 0 || ch === nRows ? Math.max(WF.margin, need) : Math.max(WF.channel, need + 6);
      });
      const rowY = [], chY = [];
      let y = 0;
      for (let r = 0; r <= nRows; r++) {
        chY.push(y); y += chH[r];
        if (r < nRows) { rowY.push(y); y += boxH; }
      }
      const height = y;
      for (const h of hsegs) h.y = chY[h.ch] + (chH[h.ch] - (chLanes[h.ch] - 1) * WF.lane) / 2 + h.y * WF.lane;
      const rectOf = (key) => ({ x: colX[col.get(key)], y: rowY[row.get(key)], w: box, h: boxH });
      const boxes = states.map((s) => ({ ...s, ...rectOf(s.key), lines: boxLines.get(s.key) }));
      const at = (p, key) => {   // ports entering from the left sit a little lower than those leaving to the right
        const r = rectOf(key);
        if (p.side === "T") return { x: r.x + r.w * p.frac, y: r.y };
        return { x: p.side === "L" ? r.x : r.x + r.w, y: r.y + r.h * p.frac + (p.side === "L" && !p.straight ? WF.lOffset : 0) };
      };
      const color = (key) => byKey.get(key).color;
      const edges = [];
      for (const e of normals) {
        const a = at(e.sp, e.f), b = at(e.tp, e.tr.to);
        let pts;
        if (!e.l1) pts = [a, b];
        else if (!e.l2) pts = [a, { x: e.l1.x, y: a.y }, { x: e.l1.x, y: b.y }, b];
        else pts = [a, { x: e.l1.x, y: a.y }, { x: e.l1.x, y: e.h.y }, { x: e.l2.x, y: e.h.y }, { x: e.l2.x, y: b.y }, b];
        edges.push({ id: `${e.tr.key}:${e.f}`, key: e.tr.key, from: [e.f], color: color(e.tr.to), timed: e.tr.timed, paths: [wfSimplify(pts)], arrow: wfArrowAt(pts), dots: [], label: wfEmptyLabel(e.tr, labelW, measure) });
      }
      for (const b of buses) {
        const paths = [], dots = [];
        for (const [c, l] of b.colLanes) {
          const here = b.srcs.filter((s) => col.get(s.f) === c).map((s) => at(s.p, s.f));
          for (const p of here) { paths.push([p, { x: l.x, y: p.y }]); dots.push({ x: l.x, y: p.y }); }
          paths.push([{ x: l.x, y: Math.min(...here.map((p) => p.y)) }, { x: l.x, y: b.h.y }]);
          dots.push({ x: l.x, y: b.h.y });
        }
        const t = at(b.tp, b.tr.to);
        paths.push([{ x: b.h.x1, y: b.h.y }, { x: b.h.x2, y: b.h.y }]);
        const drop = [{ x: t.x, y: b.h.y }, t];
        paths.push(drop);
        const keep = dots.filter((d) => d.y !== b.h.y || (d.x > b.h.x1 + 0.5 && d.x < b.h.x2 - 0.5));
        if (t.x > b.h.x1 + 0.5 && t.x < b.h.x2 - 0.5) keep.push({ x: t.x, y: b.h.y });
        edges.push({ id: `${b.tr.key}:bus`, key: b.tr.key, from: b.srcs.map((s) => s.f), color: color(b.tr.to), timed: b.tr.timed, paths, arrow: wfArrowAt(drop), dots: keep, label: wfEmptyLabel(b.tr, labelW, measure) });
      }
      for (const e of edges) {   // the arrow head replaces the last few pixels of each connector
        const last = e.paths[e.paths.length - 1];
        last[last.length - 1] = e.arrow[1];
      }
      wfPlaceLabels(edges, boxes, { x: 0, y: 0, w: totalW, h: height });
      return { width: totalW, height, boxes, edges };
    };
    /* ------------------------------------------------------------------ grid router
     * When no Z or L route is clean, an orthogonal route is searched on a grid of free corridors: the sides of
     * every box (GRID_M away from it) and lanes in the gaps between them. Shortest path by length, with a cost per
     * bend and per run shared with a connector already routed; never through a box (the two it joins only through
     * their ports). Returns the points port→port, or null when the grid is too large or there is no way. */
    const gridRoute = (pa, sa, pb, sb, rects, own, routedSegs) => {
      const half = (v) => Math.round(v * 2) / 2;
      const [ax, ay] = out[sa], [bx, by] = out[sb];
      const start = { x: half(pa.x + ax * GRID_STUB), y: half(pa.y + ay * GRID_STUB) };
      const end = { x: half(pb.x + bx * GRID_STUB), y: half(pb.y + by * GRID_STUB) };
      const obs = Object.entries(rects).map(([n, R]) => {
        const m = own.includes(n) ? 2 : GRID_M;
        return { x: R.x - m, y: R.y - m, w: R.w + 2 * m, h: R.h + 2 * m };
      });
      const inObs = (p) => obs.some((o) => p.x > o.x && p.x < o.x + o.w && p.y > o.y && p.y < o.y + o.h);
      if (inObs(start) || inObs(end)) return null;
      const lines = (a, b, vals) => {
        const base = [...new Set([a, b, ...vals.map(half)])].sort((p, q) => p - q);
        const all = [...base];
        for (let i = 1; i < base.length; i++) {
          const mid = (base[i - 1] + base[i]) / 2;
          for (const l of GRID_LANES) { const v = half(mid + l); if (v > base[i - 1] + 3 && v < base[i] - 3) all.push(v); }
        }
        return [...new Set(all)].sort((p, q) => p - q);
      };
      const xs = lines(start.x, end.x, obs.flatMap((o) => [o.x, o.x + o.w]));
      const ys = lines(start.y, end.y, obs.flatMap((o) => [o.y, o.y + o.h]));
      const nx = xs.length, ny = ys.length;
      if (nx * ny * 4 > GRID_MAX) return null;
      const si = xs.indexOf(start.x), sj = ys.indexOf(start.y), ei = xs.indexOf(end.x), ej = ys.indexOf(end.y);
      // a grid step is free when it crosses no obstacle (running along an obstacle's side is fine)
      const blockedH = (i, j) => { const y = ys[j], x0 = xs[i], x1 = xs[i + 1]; return obs.some((o) => o.y < y && y < o.y + o.h && x1 > o.x && x0 < o.x + o.w); };
      const blockedV = (i, j) => { const x = xs[i], y0 = ys[j], y1 = ys[j + 1]; return obs.some((o) => o.x < x && x < o.x + o.w && y1 > o.y && y0 < o.y + o.h); };
      const sharedStep = (p, q) => routedSegs.some((t) => collinear([p, q], t));
      // Dijkstra over (column, row, direction): 0 right, 1 left, 2 down, 3 up
      const DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1]];
      const dirOf = (dx, dy) => (dx > 0 ? 0 : dx < 0 ? 1 : dy > 0 ? 2 : 3);
      const N = nx * ny * 4;
      const key = (i, j, d) => (i * ny + j) * 4 + d;
      const dist = new Float64Array(N).fill(Infinity), prev = new Int32Array(N).fill(-1);
      const heap = [];
      const push = (c, k) => { heap.push([c, k]); let n = heap.length - 1; while (n > 0) { const m = (n - 1) >> 1; if (heap[m][0] <= heap[n][0]) break; [heap[m], heap[n]] = [heap[n], heap[m]]; n = m; } };
      const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let n = 0; for (;;) { const l = 2 * n + 1, r = l + 1; let m = n; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === n) break; [heap[m], heap[n]] = [heap[n], heap[m]]; n = m; } } return top; };
      const d0 = dirOf(ax, ay), dIn = dirOf(-bx, -by);
      dist[key(si, sj, d0)] = 0;
      push(0, key(si, sj, d0));
      let found = -1;
      while (heap.length) {
        const [c, k] = pop();
        if (c > dist[k]) continue;
        const d = k % 4, j = ((k - d) / 4) % ny, i = ((k - d) / 4 - j) / ny;
        if (i === ei && j === ej) { found = k; break; }
        for (let nd = 0; nd < 4; nd++) {
          const [dx, dy] = DIRS[nd];
          const ni = i + dx, nj = j + dy;
          if (ni < 0 || ni >= nx || nj < 0 || nj >= ny) continue;
          if (dx ? blockedH(Math.min(i, ni), j) : blockedV(i, Math.min(j, nj))) continue;
          const p = { x: xs[i], y: ys[j] }, q = { x: xs[ni], y: ys[nj] };
          let cost = c + Math.abs(q.x - p.x) + Math.abs(q.y - p.y) + (nd !== d ? GRID_BEND : 0) + (sharedStep(p, q) ? GRID_SHARE : 0);
          if (ni === ei && nj === ej && nd !== dIn) cost += GRID_BEND;   // arriving sideways to the port bends once more
          const nk = key(ni, nj, nd);
          if (cost < dist[nk] - 1e-9) { dist[nk] = cost; prev[nk] = k; push(cost, nk); }
        }
      }
      if (found < 0) return null;
      const pts = [];
      for (let k = found; k >= 0; k = prev[k]) { const d = k % 4, j = ((k - d) / 4) % ny, i = ((k - d) / 4 - j) / ny; pts.push({ x: xs[i], y: ys[j] }); }
      pts.reverse();
      return wfSimplify([pa, ...pts, pb]);
    };

    const edgesOf = (mm, uses = null, overlay = null, from = "from") => {
      // EMF / Ecore Tools notation: reference = open arrow at the target; containment = filled diamond at the
      // container; a pair of opposite references = one connector with both ends; inheritance = hollow triangle
      // at the supertype. A reference the behaviour uses gets ` ·ƒ` after its label; `overlay` ({class: stateOverlay})
      // adds «1 da <stato>» when a state requires it.
      const used = (cn, rn) => (uses?.[cn]?.references?.[rn] ? " ·ƒ" : "");
      const mult = (cn, rn, r) => {
        const req = (overlay?.[cn]?.[rn] || []).filter((x) => x.lower === 1).map((x) => x.label);
        return multText(r.lower, r.upper) + (req.length ? ` · 1 ${from} ${req.join(", ")}` : "");
      };
      const list = [];
      const drawn = new Set();
      for (const [cn, c] of Object.entries(mm.classes)) {
        if (!mm.diagram[cn]) continue;
        for (const s of c.supertypes) {
          if (mm.diagram[s] && mm.classes[s]) list.push({ key: `${cn}^${s}`, a: cn, b: s, end: "url(#tri)", cls: "edge inherit" });
        }
        for (const [rn, r] of Object.entries(c.references)) {
          if (drawn.has(`${cn}.${rn}`)) continue;
          if (r.type === "User" || !mm.diagram[r.type] || !mm.classes[r.type]) continue;   // User: a row in the box
          const o = r.opposite ? mm.classes[r.type]?.references?.[r.opposite] : null;
          if (o) drawn.add(`${r.type}.${r.opposite}`);
          list.push({
            key: `${cn}.${rn}`, a: cn, b: r.type, cls: "edge",
            start: r.containment ? "url(#diamond)" : (o ? "url(#arrow)" : null),
            end: o?.containment ? "url(#diamond)" : "url(#arrow)",
            labelB: `${rn} ${mult(cn, rn, r)}${used(cn, rn)}`,
            labelA: o ? `${r.opposite} ${mult(r.type, r.opposite, o)}${used(r.type, r.opposite)}` : null,
          });
        }
      }
      return list;
    };

    const routeEdges = (mm, size, opts = {}) => {
      // Connectors as orthogonal polylines, with the labels of their ends: { edges: [{key, a, b, cls, start, end,
      // pts, labels: [{text, x, y, w, h}]}], boxes: {name: rect}, ext } (ext: the extent of lines and labels).
      // A bus (BUS_MIN or more references entering the same side of a class, core:diagrams) is one edge: `pts` the
      // stub with the arrow, `trunk` the line parallel to the side, `branches` [{key, a, start, pts}] one per source,
      // one label when the references read the same, else one at each source.
      // opts.uses: the `uses` map of behavior.json (marks the labels of the references the behaviour uses).
      const rects = {};
      for (const n of [...Object.keys(mm.classes), ...Object.keys(mm.enums)]) {
        const p = mm.diagram[n];
        if (p) { const s = size(n); rects[n] = { x: p.x, y: p.y, w: s.w, h: s.h }; }
      }
      const boxes = Object.entries(rects);
      const crosses = (pts, skip) => {
        let n = 0;
        for (const [name, R] of boxes) {
          const m = skip.includes(name) ? 2 : -4;   // the own boxes only count when the line runs inside them
          for (const [p, q] of segments(pts)) if (hitsRect(p, q, R, m)) n++;
        }
        return n;
      };
      const length = (pts) => segments(pts).reduce((a, [p, q]) => a + Math.abs(q.x - p.x) + Math.abs(q.y - p.y), 0);
      const list = edgesOf(mm, opts.uses, opts.overlay, opts.from);
      for (const e of list) {   // the sides the connector leaves and enters
        const A = rects[e.a], B = rects[e.b];
        e.A = A; e.B = B;
        if (e.a === e.b) { e.sa = "right"; e.sb = "right"; continue; }
        let best = Infinity;
        for (const sa of SIDES) for (const sb of SIDES) for (const frac of FRACS) {
          const pts = route(mid(A, sa), sa, mid(B, sb), sb, 0, false, 0, frac);
          // a Z off the middle only when it avoids a crossing: the sides are chosen on the box centres, the
          // ports move along the sides afterwards, and a path that squeezes through on the centres may not then
          const c = crosses(pts, [e.a, e.b]) * 100000 + length(pts) + (pts.length - 2) * 40 + Math.abs(frac - 0.5) * 2000;
          if (c < best - 1e-6) { best = c; e.sa = sa; e.sb = sb; }
        }
      }
      // many plain references (no opposite) entering the same side of a class share a bus: one port and one arrow
      const groups = {};
      for (const e of list) if (e.cls === "edge" && !e.labelA && e.a !== e.b) (groups[`${e.b}|${e.sb}`] ||= []).push(e);
      const buses = Object.entries(groups).filter(([, g]) => g.length >= BUS_MIN).map(([k, g]) => {
        const bus = { key: `bus:${k}`, a: g[0].a, b: g[0].b, sb: g[0].sb, cls: "edge", end: g[0].end, members: g };
        for (const e of g) e.bus = bus;
        return bus;
      });
      // the other plain references into a class with a bus join it when a branch reaches the trunk without
      // crossing a box: one arrow on the class instead of one per side
      for (const bus of buses) {
        const J0 = mid(rects[bus.b], bus.sb);
        const J = { x: J0.x + out[bus.sb][0] * BUS_GAP, y: J0.y + out[bus.sb][1] * BUS_GAP };
        for (const e of list) {
          if (e.bus || e.b !== bus.b || e.cls !== "edge" || e.labelA || e.a === e.b) continue;
          let best = null;
          for (const sa of SIDES) {
            const pts = branchRoute(mid(e.A, sa), sa, e.A, J, bus.sb);
            const c = crosses(pts, [e.a]) * 100000 + length(pts) + (pts.length - 2) * 40;
            if (!best || c < best.c - 1e-6) best = { c, sa };
          }
          if (best.c < 100000) { e.sa = best.sa; e.sb = bus.sb; e.bus = bus; bus.members.push(e); }
        }
      }
      const centre = (R, side) => (horizontal(side) ? R.y + R.h / 2 : R.x + R.w / 2);
      // ports: the connectors on the same side of a box are spread along it, ordered by where they go;
      // the incoming ends are staggered by a few px from the outgoing ones; a bus takes one port, at the middle
      // of its sources
      const ports = {};
      list.forEach((e, i) => {
        (ports[`${e.a}|${e.sa}`] ||= []).push({ at: e, i, end: "a", key: centre(e.B, e.sa) });
        if (!e.bus) (ports[`${e.b}|${e.sb}`] ||= []).push({ at: e, i, end: "b", key: centre(e.A, e.sb) });
      });
      buses.forEach((bus, i) => {
        const keys = bus.members.map((e) => centre(e.A, bus.sb));
        (ports[`${bus.b}|${bus.sb}`] ||= []).push({ at: bus, i: list.length + i, end: "b", key: keys.reduce((s, v) => s + v, 0) / keys.length });
      });
      for (const [k, items] of Object.entries(ports)) {
        const [n, side] = k.split("|");
        const R = rects[n];
        items.sort((u, v) => u.key - v.key || (u.end === v.end ? u.i - v.i : u.end === "a" ? -1 : 1));
        items.forEach((it, j) => {
          const t = (j + 1) / (items.length + 1);
          const shift = it.end === "b" ? PORT_STAGGER : 0;
          const pt = side === "left" ? { x: R.x, y: R.y + HEAD_H / 2 + (R.h - HEAD_H / 2) * t + shift }
            : side === "right" ? { x: R.x + R.w, y: R.y + HEAD_H / 2 + (R.h - HEAD_H / 2) * t + shift }
              : side === "top" ? { x: R.x + R.w * t + shift, y: R.y } : { x: R.x + R.w * t + shift, y: R.y + R.h };
          it.at[it.end === "a" ? "pa" : "pb"] = pt;
          it.at[it.end === "a" ? "ja" : "jb"] = j;   // position on the side: labels alternate
        });
      }
      // each connector takes the lane (offset of its middle run, distance of a detour) that crosses no box and
      // shares no run with the connectors already routed; its ports may slide a few px along their sides, so that
      // two connectors leaving boxes of the same row at the same height do not run on the same line
      const slide = (pt, side, d) => (horizontal(side) ? { x: pt.x, y: pt.y + d } : { x: pt.x + d, y: pt.y });
      const routed = [];
      const shared = (segs) => routed.reduce((n, o) => n + segs.filter((s) => o.segs.some((t) => collinear(s, t))).length, 0);
      // the buses first (one place for the trunk, a branch per source), then the single connectors avoid them
      for (const bus of buses) {
        const [ox, oy] = out[bus.sb];
        const J = { x: bus.pb.x + ox * BUS_GAP, y: bus.pb.y + oy * BUS_GAP };
        bus.pts = [J, bus.pb];
        bus.branches = [];
        let lo = horizontal(bus.sb) ? J.y : J.x, hi = lo;
        for (const e of bus.members) {
          let best = null;
          for (const jog of [0, 6, -6, 12, -12]) for (let detour = 0; detour < 5; detour++) {
            const pts = branchRoute(slide(e.pa, e.sa, jog), e.sa, e.A, J, bus.sb, detour);
            const segs = segments(pts);
            const c = crosses(pts, [e.a]) * 100000 + shared(segs) * 10000 + length(pts) + (pts.length - 2) * 40 + detour * 6 + Math.abs(jog) * 2;
            if (!best || c < best.c - 1e-6) best = { c, pts, segs };
          }
          e.pts = best.pts;
          routed.push({ segs: best.segs });
          const end = best.pts[best.pts.length - 1];
          const v = horizontal(bus.sb) ? end.y : end.x;
          lo = Math.min(lo, v); hi = Math.max(hi, v);
          bus.branches.push({ key: e.key, a: e.a, start: e.start, pts: best.pts });
        }
        bus.trunk = horizontal(bus.sb) ? [{ x: J.x, y: lo }, { x: J.x, y: hi }] : [{ x: lo, y: J.y }, { x: hi, y: J.y }];
        routed.push({ segs: segments(bus.pts) }, { segs: [bus.trunk] });
      }
      for (const e of list) {
        if (e.bus) continue;
        let best = null;
        for (const frac of FRACS) for (const jog of [0, 6, -6]) for (const lane of LANES) for (let detour = 0; detour < 5; detour++) {
          const pts = route(slide(e.pa, e.sa, jog), e.sa, slide(e.pb, e.sb, jog), e.sb, lane, e.a === e.b, detour, frac);
          const segs = segments(pts);
          const c = crosses(pts, [e.a, e.b]) * 100000 + shared(segs) * 10000 + length(pts) + (pts.length - 2) * 40
            + Math.abs(lane) + detour * 6 + Math.abs(jog) * 2 + Math.abs(frac - 0.5) * 20;
          if (!best || c < best.c - 1e-6) best = { c, pts, segs };
        }
        // no clean Z or L: a route on the grid of free corridors, kept when it crosses nothing and shares no more
        if (e.a !== e.b && (crosses(best.pts, [e.a, e.b]) > 0 || shared(best.segs) > 0)) {
          const g = gridRoute(e.pa, e.sa, e.pb, e.sb, rects, [e.a, e.b], routed.flatMap((o) => o.segs));
          if (g) {
            const gs = segments(g);
            if (crosses(g, [e.a, e.b]) === 0 && shared(gs) <= shared(best.segs)) best = { c: 0, pts: g, segs: gs };
          }
        }
        e.pts = best.pts;
        routed.push({ segs: best.segs });
      }
      // labels: at the ends, in the first of several candidate places that covers no box, label or line
      const allSegs = [...list.flatMap((e) => segments(e.pts)), ...buses.flatMap((b) => [...segments(b.pts), b.trunk])];
      const placed = [];
      const ext = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
      const grow = (x0, y0, x1, y1) => { ext.x0 = Math.min(ext.x0, x0); ext.y0 = Math.min(ext.y0, y0); ext.x1 = Math.max(ext.x1, x1); ext.y1 = Math.max(ext.y1, y1); };
      const label = (pt, side, text, below, pts = []) => {
        const w = text.length * LABEL_CHAR_W + 4, h = LABEL_H;
        const [ox, oy] = out[side];
        // candidates: along the connector (d) and away from it (s), on the preferred side of the line first
        const cands = [];
        for (const d of [8, 24, 42, 62, 84, 108]) for (const s of [4, 18, 32, 46]) for (const flip of [0, 1]) {
          const first = below ? !flip : !!flip;   // below the line (horizontal side) / left of it (vertical side)
          const r = ox
            ? { x: ox > 0 ? pt.x + d : pt.x - d - w, y: first ? pt.y + s : pt.y - s - h, w, h }
            : { x: first ? pt.x - s - 2 - w : pt.x + s + 2, y: oy > 0 ? pt.y + d - 2 : pt.y - d + 2 - h, w, h };
          cands.push({ r, near: d + s + flip * 6 });
        }
        // then, farther from the port, beside every run of the connector (used when the places near the port are taken)
        segments(pts).forEach(([p, q], k) => {
          const horiz = Math.abs(p.y - q.y) < 0.5, len = Math.abs(horiz ? q.x - p.x : q.y - p.y);
          if (len < 12) return;
          for (const t of [0.5, 0.25, 0.75]) for (const s of [4, 18]) for (const sign of [1, -1]) {
            const cx = p.x + (q.x - p.x) * t, cy = p.y + (q.y - p.y) * t;
            const r = horiz ? { x: cx - w / 2, y: sign > 0 ? cy + s : cy - s - h, w, h } : { x: sign > 0 ? cx + s + 2 : cx - s - 2 - w, y: cy - h / 2, w, h };
            cands.push({ r, near: 160 + k * 20 + Math.abs(t - 0.5) * 40 + s });
          }
        });
        let best = null;
        for (const { r, near } of cands) {
          const c = boxes.filter(([, R]) => rectsOverlap(r, R, 1)).length * 1000
            + placed.filter((q) => rectsOverlap(r, q, 1)).length * 1000
            + allSegs.filter(([p, q]) => hitsRect(p, q, r, 0)).length * 50 + near;
          if (!best || c < best.c) best = { c, r };
        }
        placed.push(best.r);
        grow(best.r.x, best.r.y, best.r.x + w, best.r.y + h);
        return { text, ...best.r };
      };
      for (const e of list) {
        if (e.bus) continue;
        e.labels = [];
        const pa = e.pts[0], pb = e.pts[e.pts.length - 1];   // the ports, after sliding
        if (e.labelB) e.labels.push(label(pb, e.sb, e.labelB, e.labelA ? false : e.jb % 2 === 0, [...e.pts].reverse()));   // first port: label on its left
        if (e.labelA) e.labels.push(label(pa, e.sa, e.labelA, e.ja % 2 === 0, e.pts));
        for (const q of e.pts) grow(q.x - 14, q.y - 14, q.x + 14, q.y + 14);
      }
      for (const bus of buses) {   // one label at the arrow when every reference reads the same, else one per source
        bus.labels = [];
        if (new Set(bus.members.map((e) => e.labelB)).size === 1) bus.labels.push(label(bus.pb, bus.sb, bus.members[0].labelB, bus.jb % 2 === 0, [bus.pb, ...bus.trunk]));
        else for (const e of bus.members) bus.labels.push(label(e.pts[0], e.sa, e.labelB, e.ja % 2 === 0, e.pts));
        for (const q of [...bus.pts, ...bus.trunk, ...bus.members.flatMap((e) => e.pts)]) grow(q.x - 14, q.y - 14, q.x + 14, q.y + 14);
      }
      const edges = [
        ...list.filter((e) => !e.bus).map(({ key, a, b, cls, start, end, pts, labels }) => ({ key, a, b, cls, start, end, pts, labels })),
        ...buses.map(({ key, a, b, cls, end, pts, trunk, branches, labels }) => ({ key, a, b, cls, start: null, end, pts, trunk, branches, labels })),
      ];
      return { edges, boxes: rects, ext: edges.length ? ext : null };
    };

    const freeSpot = (occupied, size, start, view, step = 30, margin = MARGIN) => {
      // Where a new box of `size` goes: the first place near `start` (candidates on a `step` grid, nearest first)
      // whose rectangle crosses no existing box, with a margin; inside the view when possible, beyond it otherwise.
      // Pure and deterministic: the same input gives the same place.
      const clear = (x, y) => !occupied.some((o) => x < o.x + o.w + margin && o.x < x + size.w + margin
        && y < o.y + o.h + margin && o.y < y + size.h + margin);
      const inView = (x, y) => !view || (x >= view.x && y >= view.y && x + size.w <= view.x + view.w && y + size.h <= view.y + view.h);
      const far = Math.max(view ? Math.max(view.w, view.h) : 0,
        ...occupied.map((o) => Math.max(Math.abs(o.x - start.x) + o.w, Math.abs(o.y - start.y) + o.h))) + size.w + size.h + margin;
      const ring = (r) => {
        if (r === 0) return [[0, 0]];
        const d = r * step, out = [];
        for (let i = -r; i <= r; i++) out.push([i * step, -d], [i * step, d]);
        for (let i = -r + 1; i < r; i++) out.push([-d, i * step], [d, i * step]);
        return out.sort((a, b) => (a[0] ** 2 + a[1] ** 2) - (b[0] ** 2 + b[1] ** 2) || a[1] - b[1] || a[0] - b[0]);
      };
      for (const needView of view ? [true, false] : [false]) {
        for (let r = 0; r * step <= far; r++) {
          for (const [dx, dy] of ring(r)) {
            const x = start.x + dx, y = start.y + dy;
            if ((!needView || inView(x, y)) && clear(x, y)) return { x: Math.round(x), y: Math.round(y) };
          }
        }
      }
      const bottom = Math.max(start.y, ...occupied.map((o) => o.y + o.h + margin));   // nothing around: below everything
      return { x: Math.round(start.x), y: Math.round(bottom) };
    };

    // the ids of the edges leaving a state (the transitions a record in that state can take; a bus counts when the
    // state is one of its sources): what <workflow-view> draws at full strength
    const workflowFocus = (edges, stateKey) => (stateKey == null ? [] : edges.filter((e) => e.from.includes(stateKey)).map((e) => e.id));
    // The view of the canvas: {k, x, y} (scale and translation). fitView fills the canvas with the bounds of the
    // diagram (centred, a margin around, the scale between K_MIN and K_MAX); zoomView scales around a point of the
    // canvas (the centre for the toolbar buttons) so that point stays where it is.
    const fitView = (bounds, size, margin = MARGIN, kMin = K_MIN, kMax = K_MAX) => {
      const w = Math.max(1, bounds.x1 - bounds.x0), h = Math.max(1, bounds.y1 - bounds.y0);
      const k = Math.min(kMax, Math.max(kMin, Math.min((size.w - 2 * margin) / w, (size.h - 2 * margin) / h)));
      return { k, x: (size.w - w * k) / 2 - bounds.x0 * k, y: (size.h - h * k) / 2 - bounds.y0 * k };
    };
    const zoomView = (view, factor, at, kMin = K_MIN, kMax = K_MAX) => {
      const k = Math.min(kMax, Math.max(kMin, view.k * factor));
      return { k, x: at.x - ((at.x - view.x) * k) / view.k, y: at.y - ((at.y - view.y) * k) / view.k };
    };
    return { rowItems, rowsOf, boxSize, normalize, autoLayout, routeEdges, edgesOf, freeSpot, fitView, zoomView, workflowModel, workflowLayout, workflowFocus,
             stateView, stateOverlay, viewMark, wfLabel, WF, STEREO_H };
  })();

  /* ------------------------------------------------------------------ changes between two metamodels
   * The same lines as `modeler diff` (ecore.diff in the CLI), on the canonical form: the admin page shows them
   * for the proposals waiting to be applied. Values are printed as the CLI prints them (None, True, ['A']). */
  const pyRepr = (v) => v === undefined || v === null ? "None" : v === true ? "True" : v === false ? "False"
    : Array.isArray(v) ? `[${v.map((x) => (typeof x === "string" ? `'${x}'` : pyRepr(x))).join(", ")}]` : String(v);
  const multSuffix = (lo, up) => lo === 0 && up === 1 ? "" : lo === 0 && up === -1 ? "[*]" : lo === 1 && up === -1 ? "[+]"
    : lo === up ? `[${lo}]` : `[${lo}..${up === -1 ? "*" : up}]`;
  const sameGroup = (g, h) => JSON.stringify(g) === JSON.stringify(h);
  // domain rules ({id, text} on the package or a class): the same lines as ecore.diff
  const ruleLines = (prefix, old, neu) => {
    const o = Object.fromEntries((old || []).map((r) => [r.id, r.text])), n = Object.fromEntries((neu || []).map((r) => [r.id, r.text]));
    const out = [];
    for (const k of Object.keys(n)) if (!(k in o)) out.push(`+ ${prefix}rule ${k}`);
    for (const k of Object.keys(n)) if (k in o && o[k] !== n[k]) out.push(`~ ${prefix}rule ${k} changed`);
    for (const k of Object.keys(o)) if (!(k in n)) out.push(`- ${prefix}rule ${k}`);
    return out;
  };
  const diff = (oldMm, newMm) => {
    const a = Layout.normalize(oldMm), b = Layout.normalize(newMm);
    const out = [];
    const lits = (e) => e.literals.map((l) => l.name);
    for (const en of Object.keys(b.enums)) {
      if (!a.enums[en]) { out.push(`+ enum ${en}: ${lits(b.enums[en]).join(", ")}`); continue; }
      for (const n of lits(b.enums[en])) if (!lits(a.enums[en]).includes(n)) out.push(`+ literal ${en}.${n}`);
      for (const n of lits(a.enums[en])) if (!lits(b.enums[en]).includes(n)) out.push(`- literal ${en}.${n}`);
    }
    for (const en of Object.keys(a.enums)) if (!b.enums[en]) out.push(`- enum ${en}`);
    out.push(...ruleLines("", a.rules, b.rules));
    for (const [cn, c] of Object.entries(b.classes)) {
      const oc = a.classes[cn];
      if (!oc) {
        out.push(`+ class ${cn}${c.abstract ? " (abstract)" : ""}${c.supertypes.length ? ` extends ${c.supertypes.join(", ")}` : ""}`);
        for (const g of c.unique || []) out.push(`  + ${cn}: unique (${g.join(", ")})`);
        for (const [an, at] of Object.entries(c.attributes)) out.push(`  + ${cn}.${an}: ${at.type}${multSuffix(at.lower, at.upper)}`);
        for (const [rn, r] of Object.entries(c.references)) {
          out.push(`  + ${cn}.${rn} -> ${r.type}${multSuffix(r.lower, r.upper)}${r.containment ? " containment" : ""}${r.opposite ? ` opposite ${r.opposite}` : ""}`);
        }
        for (const r of c.rules || []) out.push(`  + ${cn}: rule ${r.id}`);
        continue;
      }
      if (oc.abstract !== c.abstract) out.push(`~ class ${cn}: abstract ${pyRepr(oc.abstract)} -> ${pyRepr(c.abstract)}`);
      if (!sameGroup(oc.supertypes, c.supertypes)) out.push(`~ class ${cn}: supertypes ${pyRepr(oc.supertypes)} -> ${pyRepr(c.supertypes)}`);
      for (const g of c.unique || []) if (!(oc.unique || []).some((h) => sameGroup(g, h))) out.push(`+ ${cn}: unique (${g.join(", ")})`);
      for (const g of oc.unique || []) if (!(c.unique || []).some((h) => sameGroup(g, h))) out.push(`- ${cn}: unique (${g.join(", ")})`);
      out.push(...ruleLines(`${cn}: `, oc.rules, c.rules));
      for (const kind of ["attributes", "references"]) {
        for (const [fn, f] of Object.entries(c[kind])) {
          const renamed = f.renamed_from;
          const of = oc[kind][fn] || (renamed ? oc[kind][renamed] : null);
          if (!of) { out.push(`+ ${cn}.${fn}: ${f.type}${multSuffix(f.lower, f.upper)}`); continue; }
          if (renamed && !oc[kind][fn]) out.push(`~ ${cn}.${renamed} renamed to ${fn}`);
          for (const k of ["type", "lower", "upper", "containment", "opposite", "default", "id", "changeable", "derived"]) {
            if (JSON.stringify(of[k] ?? null) !== JSON.stringify(f[k] ?? null)) out.push(`~ ${cn}.${fn}: ${k} ${pyRepr(of[k])} -> ${pyRepr(f[k])}`);
          }
        }
        for (const fn of Object.keys(oc[kind])) {
          if (!c[kind][fn] && !Object.values(c[kind]).some((x) => x.renamed_from === fn)) out.push(`- ${cn}.${fn}`);
        }
      }
    }
    for (const cn of Object.keys(a.classes)) if (!b.classes[cn]) out.push(`- class ${cn}`);
    return out;
  };
  Layout.diff = diff;

  /* ------------------------------------------------------------------ the behaviour as a proposal
   * The editor holds behavior.json (typed expressions {text, type, ast, sql}, runtime keys). A proposal carries the
   * behaviour as behavior.yaml is written: expressions as their text, no `entities`/`uses` (the CLI normalises the
   * rest: `behavior.from_editor`). behaviorDiff lists the changes as the CLI's `behavior.diff`, for the pending list. */
  const exprText = (x) => (x && typeof x === "object" && "text" in x ? x.text : x);
  const behaviorSource = (bh) => {
    if (!bh || typeof bh !== "object") return null;
    const b = JSON.parse(JSON.stringify(bh));   // (clone is defined after this module's early return for Node)
    delete b.entities; delete b.uses;
    for (const ders of Object.values(b.derivations || {})) for (const an of Object.keys(ders)) ders[an] = exprText(ders[an]);
    for (const w of Object.values(b.workflows || {})) {
      for (const t of Object.values(w.transitions || {})) { t.when = exprText(t.when); t.guard = exprText(t.guard); }
      for (const st of Object.values(w.states || {})) {
        for (const [f, o] of Object.entries(st.model || {})) {
          const c = {};
          if (o?.lower != null) c.lower = o.lower;
          if (o?.readonly && !o?.hidden) c.readonly = true;
          if (o?.hidden) c.hidden = true;
          if (o?.in) c.in = o.in;
          if (Object.keys(c).length) st.model[f] = c; else delete st.model[f];
        }
        if (st.model && !Object.keys(st.model).length) delete st.model;
      }
    }
    for (const r of b.reactions || []) r.when = exprText(r.when);
    return b;
  };
  const behaviorDiff = (oldBh, newBh) => {
    const a = behaviorSource(oldBh) || {}, b = behaviorSource(newBh) || {};
    const out = [];
    const same = (x, y) => JSON.stringify(x ?? null) === JSON.stringify(y ?? null);
    const norm = (x) => (typeof x === "string" ? x.split(/\s+/).join(" ") : x);
    const keysChanged = (x, y, keys) => keys.filter((k) => !same(norm(x?.[k]), norm(y?.[k])));
    const ar = a.roles || {}, br = b.roles || {};
    for (const rn of Object.keys(br)) {
      if (!ar[rn]) out.push(`+ role ${rn}`);
      else { const ks = keysChanged(ar[rn], br[rn], ["scope", "label"]); if (ks.length) out.push(`~ role ${rn}: ${ks.join(", ")}`); }
    }
    for (const rn of Object.keys(ar)) if (!br[rn]) out.push(`- role ${rn}`);
    const ad = a.derivations || {}, bd = b.derivations || {};
    for (const [cn, ders] of Object.entries(bd)) for (const [an, ex] of Object.entries(ders)) {
      if (ad[cn]?.[an] === undefined) out.push(`+ derivation ${cn}.${an} = ${ex}`);
      else if (norm(ad[cn][an]) !== norm(ex)) out.push(`~ derivation ${cn}.${an} = ${ex}`);
    }
    for (const [cn, ders] of Object.entries(ad)) for (const an of Object.keys(ders)) if (bd[cn]?.[an] === undefined) out.push(`- derivation ${cn}.${an}`);
    const aw = a.workflows || {}, bw = b.workflows || {};
    for (const [cn, w] of Object.entries(bw)) {
      const ow = aw[cn];
      if (!ow) { out.push(`+ workflow ${cn} on ${w.state}: ${Object.keys(w.states || {}).length} states, ${Object.keys(w.transitions || {}).length} transitions`); continue; }
      if (ow.state !== w.state) out.push(`~ workflow ${cn}: state attribute ${ow.state} -> ${w.state}`);
      for (const [sn, st] of Object.entries(w.states || {})) {
        if (!ow.states?.[sn]) out.push(`+ state ${cn}.${sn}`);
        else { const ks = keysChanged(ow.states[sn], st, ["initial", "final", "label", "color", "owner", "editable_by", "reminder", "requires", "model"]); if (ks.length) out.push(`~ state ${cn}.${sn}: ${ks.join(", ")}`); }
      }
      for (const sn of Object.keys(ow.states || {})) if (!w.states?.[sn]) out.push(`- state ${cn}.${sn}`);
      for (const [tn, tr] of Object.entries(w.transitions || {})) {
        if (!ow.transitions?.[tn]) out.push(`+ transition ${cn}.${tn}: ${[].concat(tr.from || []).join(", ")} -> ${tr.to}`);
        else { const ks = keysChanged(ow.transitions[tn], tr, ["from", "to", "by", "when", "guard", "comment", "at", "emits", "label"]); if (ks.length) out.push(`~ transition ${cn}.${tn}: ${ks.join(", ")}`); }
      }
      for (const tn of Object.keys(ow.transitions || {})) if (!w.transitions?.[tn]) out.push(`- transition ${cn}.${tn}`);
      if (!same(ow.revert, w.revert)) out.push(`~ workflow ${cn}: revert`);
    }
    for (const cn of Object.keys(aw)) if (!bw[cn]) out.push(`- workflow ${cn}`);
    const ae = a.events || {}, be = b.events || {};
    for (const [cn, evs] of Object.entries(be)) for (const en of Object.keys(evs || {})) if (!ae[cn]?.[en]) out.push(`+ event ${cn}.${en}`);
    for (const [cn, evs] of Object.entries(ae)) for (const en of Object.keys(evs || {})) if (!be[cn]?.[en]) out.push(`- event ${cn}.${en}`);
    const byName = (lst) => Object.fromEntries((lst || []).map((r, i) => [String(r.name || i), r]));
    const arx = byName(a.reactions), brx = byName(b.reactions);
    for (const [n, r] of Object.entries(brx)) {
      if (!arx[n]) out.push(`+ reaction ${n} on ${r.event}`);
      else { const ks = keysChanged(arx[n], r, ["event", "when", "notify", "template"]); if (ks.length) out.push(`~ reaction ${n}: ${ks.join(", ")}`); }
    }
    for (const n of Object.keys(arx)) if (!brx[n]) out.push(`- reaction ${n}`);
    const at = a.templates || {}, bt = b.templates || {};
    for (const [k, langs] of Object.entries(bt)) {
      if (!at[k]) out.push(`+ template ${k} (${Object.keys(langs).join(", ")})`);
      else { const ks = [...new Set([...Object.keys(langs), ...Object.keys(at[k])])].sort().filter((l) => !same(at[k][l], langs[l])); if (ks.length) out.push(`~ template ${k}: ${ks.join(", ")}`); }
    }
    for (const k of Object.keys(at)) if (!bt[k]) out.push(`- template ${k}`);
    return out;
  };
  Layout.behaviorSource = behaviorSource;
  Layout.behaviorDiff = behaviorDiff;

  if (typeof module === "object" && module.exports) module.exports = Layout;
  if (typeof customElements === "undefined" || customElements.get("metamodel-editor")) return;

  const T = {
    it: {
      addClass: "Classe", addEnum: "Enum", layout: "Riordina", fit: "Adatta", zoomIn: "Ingrandisci", zoomOut: "Riduci", save: "Salva", note: "Nota sulla modifica",
      panel: "Pannello", fullscreen: "Schermo intero", exitFullscreen: "Esci", allAttrs: "Tutti gli attributi",
      compact: "Compatto", more: "altri",
      issues: "problemi", ok: "Metamodello valido", name: "Nome", abstract: "Astratta", supertypes: "Supertipi",
      doc: "Descrizione", label: "Etichetta", attributes: "Attributi", references: "Riferimenti", literals: "Letterali",
      add: "Aggiungi", del: "Elimina", type: "Tipo", mult: "Molt.", id: "ID", target: "Classe", containment: "Contiene",
      opposite: "Opposto", none: "—", select: "Seleziona una classe o un'enum nel diagramma, oppure aggiungine una.",
      confirmDelete: "Eliminare", package: "Package", modeler: "Modellatore", readonly: "Sola lettura", users: "User = utenti dell'applicazione",
      dupName: "nome già usato", badName: "nome non valido", reserved: "colonna standard", noTarget: "classe di destinazione mancante",
      oppBroken: "opposto non coerente", bothCont: "entrambi i lati sono contenimenti", noLiterals: "nessun letterale",
      cycle: "ciclo di ereditarietà", newClass: "NuovaClasse", newEnum: "NuovaEnum", warnings: "avvisi",
      dropClass: "classe rimossa: la tabella e i suoi dati andranno eliminati",
      dropFeature: "rimosso: la colonna e i suoi dati andranno eliminati",
      dropLiteral: "letterale rimosso: i record con questo valore vanno migrati",
      behavior: "Comportamento", workflow: "Workflow", states: "stati", transitions: "transizioni",
      derived: "calcolato", inCode: "calcolato nel codice", formula: "formula",
      legendWf: "classe con workflow", legendInvolved: "coinvolta nel comportamento", legendStruct: "solo struttura",
      usedBy: "usato da", derivation: "derivazione", guard: "requisito", when: "condizione", at: "scadenza", by: "chi",
      owner: "in attesa di", editable_by: "modificabile da", requires: "richiede", allowed: "valori ammessi nello stato", readonly: "sola lettura nello stato",
      hidden: "assente nello stato", notify: "destinatario", revert: "ritorno", scope: "ambito del ruolo", fromState: "da", model: "Modello",
      modelHint: "la classe come appare nello stato (model in behavior.yaml): ● richiesto, 🔒 sola lettura, ○ assente, {a, b} valori ammessi",
      stateViewHint: "passa il mouse su uno stato: il riquadro della classe mostra come appare in quello stato",
      addWorkflow: "Workflow", removeWorkflow: "Rimuovi workflow", stateAttr: "attributo di stato", stateAttrHint: "serve un attributo EString o enum",
      state: "Stato", kind: "Tipo", initial: "iniziale", final: "finale", color: "Colore", reminder: "Sollecito",
      transition: "Transizione", from: "Da", to: "A", who: "Chi", comment: "Commento", required: "obbligatorio", optional: "facoltativo",
      emits: "Eventi", events: "Eventi dichiarati", roles: "Ruoli", reactions: "Reazioni", event: "Evento", template: "Template",
      derivedFlag: "calcolato (ƒ)", derivedHint: "formula in behavior.yaml", listHint: "separati da virgola", editHint: "modifica il comportamento: le modifiche entrano nella proposta",
      resize: "Trascina per ridimensionare, doppio click per tornare all'altezza automatica",
      wfNoInitial: "nessuno stato iniziale", wfManyInitial: "più stati iniziali", wfNoFinal: "nessuno stato finale",
      wfBadState: "stato sconosciuto", wfNoActor: "senza chi né scadenza", wfBadKey: "chiave non valida", wfStateAttr: "attributo di stato mancante",
      wfBadRequires: "richiede una feature che la classe non ha:", requiresHint: "attributi o riferimenti da valorizzare per entrare nello stato",
      wfEnumStates: "gli stati devono essere i letterali dell'enum", rxBadEvent: "evento Classe.evento",
    },
    en: {
      addClass: "Class", addEnum: "Enum", layout: "Layout", fit: "Fit", zoomIn: "Zoom in", zoomOut: "Zoom out", save: "Save", note: "Change note",
      panel: "Panel", fullscreen: "Full screen", exitFullscreen: "Exit", allAttrs: "All attributes",
      compact: "Compact", more: "more",
      issues: "issues", ok: "Valid metamodel", name: "Name", abstract: "Abstract", supertypes: "Supertypes",
      doc: "Description", label: "Label", attributes: "Attributes", references: "References", literals: "Literals",
      add: "Add", del: "Delete", type: "Type", mult: "Mult.", id: "ID", target: "Class", containment: "Contains",
      opposite: "Opposite", none: "—", select: "Select a class or an enum in the diagram, or add one.",
      confirmDelete: "Delete", package: "Package", modeler: "Modeler", readonly: "Read only", users: "User = the application users",
      dupName: "name already used", badName: "invalid name", reserved: "standard column", noTarget: "missing target class",
      oppBroken: "inconsistent opposite", bothCont: "both ends are containments", noLiterals: "no literals",
      cycle: "inheritance cycle", newClass: "NewClass", newEnum: "NewEnum", warnings: "warnings",
      dropClass: "class removed: its table and data will be dropped",
      dropFeature: "removed: the column and its data will be dropped",
      dropLiteral: "literal removed: records with this value must be migrated",
      behavior: "Behaviour", workflow: "Workflow", states: "states", transitions: "transitions",
      derived: "derived", inCode: "computed in code", formula: "formula",
      legendWf: "class with a workflow", legendInvolved: "involved in the behaviour", legendStruct: "structure only",
      usedBy: "used by", derivation: "derivation", guard: "requirement", when: "condition", at: "due", by: "who",
      owner: "waiting for", editable_by: "editable by", requires: "requires", allowed: "allowed in state", readonly: "read only in state",
      hidden: "hidden in state", notify: "recipient", revert: "revert", scope: "role scope", fromState: "from", model: "Model",
      modelHint: "the class as seen from the state (model in behavior.yaml): ● required, 🔒 read only, ○ hidden, {a, b} the allowed literals",
      stateViewHint: "hover a state: the class box shows how the class looks in that state",
      addWorkflow: "Workflow", removeWorkflow: "Remove workflow", stateAttr: "state attribute", stateAttrHint: "needs an EString or enum attribute",
      state: "State", kind: "Kind", initial: "initial", final: "final", color: "Colour", reminder: "Reminder",
      transition: "Transition", from: "From", to: "To", who: "Who", comment: "Comment", required: "required", optional: "optional",
      emits: "Events", events: "Declared events", roles: "Roles", reactions: "Reactions", event: "Event", template: "Template",
      derivedFlag: "derived (ƒ)", derivedHint: "formula in behavior.yaml", listHint: "comma separated", editHint: "edit the behaviour: the changes go into the proposal",
      resize: "Drag to resize, double click for the automatic height",
      wfNoInitial: "no initial state", wfManyInitial: "several initial states", wfNoFinal: "no final state",
      wfBadState: "unknown state", wfNoActor: "neither who nor due", wfBadKey: "invalid key", wfStateAttr: "state attribute missing",
      wfBadRequires: "requires a feature the class does not have:", requiresHint: "attributes or references that must be set to enter the state",
      wfEnumStates: "the states must be the literals of the enum", rxBadEvent: "event as Class.event",
    },
  };

  // colours of both elements (light, dark by the system or by the `theme` attribute)
  const hostCss = `
:host { --bg:#fff; --fg:#1f2937; --muted:#6b7280; --line:#d1d5db; --panel:#f9fafb; --accent:#2563eb; --head:#eef2ff;
  --enum:#fef3c7; --wf:#dcfce7; --inv:#b45309; --err:#dc2626; --ok:#16a34a; display:block; font:13px/1.4 system-ui,sans-serif; color:var(--fg); }
@media (prefers-color-scheme: dark) { :host { --bg:#111827; --fg:#e5e7eb; --muted:#9ca3af; --line:#374151;
  --panel:#1f2937; --head:#1e293b; --enum:#3b2f12; --wf:#064e3b; --inv:#f59e0b; --accent:#60a5fa; } }
:host([theme="light"]) { --bg:#fff; --fg:#1f2937; --muted:#6b7280; --line:#d1d5db; --panel:#f9fafb; --head:#eef2ff; --enum:#fef3c7; --wf:#dcfce7; --inv:#b45309; --accent:#2563eb; }
:host([theme="dark"]) { --bg:#111827; --fg:#e5e7eb; --muted:#9ca3af; --line:#374151; --panel:#1f2937; --head:#1e293b; --enum:#3b2f12; --wf:#064e3b; --inv:#f59e0b; --accent:#60a5fa; }
`;
  // the state diagram (the panel of the editor and <workflow-view>): states, connectors, labels, hover, and the
  // emphasis of <workflow-view> (`out`: leaving the current state, `far`: the other connectors)
  const wfCss = `
.wfe { fill:none; stroke-width:1.75; }
.wfs { fill:var(--bg); }
.wfst { font-size:11px; font-weight:600; }
.wfkey { font-size:9px; fill:var(--muted); font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
.wfl-bg { fill:var(--bg); fill-opacity:.95; stroke-width:1; stroke-opacity:.55; }
.wfl { font-size:10px; fill:var(--fg); }
.wfa { stroke:none; }
.wfe.far, .wfa.far, .wfdot.far, .wfl.far, .wfl-bg.far { opacity:.3; }
.wfe.out { stroke-width:2.6; }
.wfs.far, .wfst.far, .wfkey.far { opacity:.55; }
.wfring { fill:none; stroke-width:6; stroke-opacity:.25; pointer-events:none; }
.wfkey.cur { fill:#fff; fill-opacity:.85; }
.ehit { stroke:transparent; stroke-width:10; fill:none; pointer-events:stroke; cursor:pointer; }
svg.hover .wfe:not(.hi), svg.hover .wfa:not(.hi), svg.hover .wfdot:not(.hi), svg.hover .wfl:not(.hi), svg.hover .wfl-bg:not(.hi) { opacity:.15; }
.wfe.hi { stroke-width:2.6; }
`;
  // contain:inline-size — the host takes the width of its container (a grid cell, a column) instead of the
  // diagram's; the diagram is laid out at that width and scrolls horizontally below its minimum
  const viewCss = `${hostCss}
:host { contain:inline-size; overflow-x:auto; overflow-y:hidden; }
svg { display:block; font:11px system-ui,sans-serif; }
${wfCss}`;
  const css = `${hostCss}
:host(:fullscreen) { height:100vh; background:var(--bg); }
* { box-sizing:border-box; }
.wrap { display:grid; grid-template-rows:auto 1fr auto; height:100%; min-height:520px; border:1px solid var(--line); border-radius:8px; overflow:hidden; background:var(--bg); }
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
.main.nopanel { grid-template-columns:1fr; }
.main.nopanel .side { display:none; }
button.on { border-color:var(--accent); color:var(--accent); }
.canvas { position:relative; overflow:hidden; min-height:0; cursor:grab; }
.canvas svg { width:100%; height:100%; display:block; user-select:none; }
.side { border-left:1px solid var(--line); background:var(--panel); overflow:auto; padding:10px; }
.side h3 { margin:12px 0 6px; font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
.side h3:first-child { margin-top:0; }
.row { display:grid; gap:4px; align-items:center; margin-bottom:4px; }
.attr { grid-template-columns:1fr 92px 58px 22px 22px 22px; }
.ref { grid-template-columns:1fr 92px 58px; }
.ref2 { grid-template-columns:auto 1fr 22px; margin:-2px 0 8px 8px; font-size:12px; color:var(--muted); }
.lit { grid-template-columns:1fr 1fr 22px; }
.field { display:grid; grid-template-columns:90px 1fr; gap:6px; align-items:center; margin-bottom:6px; }
.x { padding:0 4px; border:none; background:none; color:var(--muted); }
.x:hover { color:var(--err); }
.hint { color:var(--muted); font-size:12px; }
.formula { margin:-2px 0 8px 8px; font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; color:var(--muted); white-space:pre-wrap; word-break:break-word; }
.wf { margin:0 0 4px; font-size:12px; }
.wf .hint { display:block; margin-left:8px; }
.box text.state { fill:var(--accent); }
.box.workflow rect.head { fill:var(--wf); }
.box text.inv { fill:var(--inv); }
.box text.hidden { fill:var(--muted); text-decoration:line-through; opacity:.55; }
.box.viewed rect.head { stroke:var(--accent); stroke-width:1.5; }
.box text.mark { fill:var(--inv); font-weight:700; font-size:12px; }
.wfpanel { display:none; border-top:1px solid var(--line); background:var(--panel); grid-template-rows:auto 1fr; min-height:0; }
.wfpanel.on { display:grid; }
.wfgrip { height:7px; cursor:row-resize; background:var(--panel); position:relative; touch-action:none; }
.wfgrip::after { content:""; position:absolute; left:50%; top:2px; width:36px; height:3px; margin-left:-18px; border-radius:2px; background:var(--line); }
.wfgrip:hover::after { background:var(--accent); }
.wfbody { overflow:auto; min-height:0; }
.wfhead { display:flex; gap:8px; align-items:baseline; padding:6px 10px 0; font-size:12px; color:var(--muted); white-space:nowrap; }
.wfhead strong { color:var(--fg); font-size:13px; }
.wfpanel svg { display:block; font:11px system-ui,sans-serif; }
.wfedit { padding:4px 10px 10px; display:grid; gap:8px; }
.wfedit h4 { margin:6px 0 2px; font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
.wfedit table { border-collapse:collapse; font-size:12px; }
.wfedit th { text-align:left; font-weight:500; color:var(--muted); font-size:11px; padding:0 4px 2px; white-space:nowrap; }
.wfedit td { padding:1px 3px; vertical-align:middle; }
.wfedit input, .wfedit select { font-size:12px; padding:2px 4px; width:100%; min-width:60px; }
.wfedit input.k { width:96px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
.wfedit input.w { width:118px; }
.wfedit input.n { width:52px; }
.wfedit input[type=color] { width:28px; padding:0; height:22px; border:none; background:none; }
.wfedit .hint { padding:0 2px; }
.side input.formula { width:100%; font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; margin:-2px 0 8px 0; }
.side table.beh { border-collapse:collapse; width:100%; font-size:12px; }
.side table.beh th { text-align:left; font-weight:500; color:var(--muted); font-size:11px; padding:0 3px 2px; }
.side table.beh td { padding:1px 2px; }
.side table.beh input, .side table.beh select { width:100%; font-size:12px; padding:2px 4px; }
${wfCss}
.legend { position:absolute; left:8px; bottom:8px; display:flex; gap:10px; align-items:center; font-size:11px; color:var(--muted); background:var(--bg); border:1px solid var(--line); border-radius:6px; padding:4px 8px; pointer-events:none; }
.legend .sw { display:inline-block; width:12px; height:12px; border-radius:3px; background:var(--head); border:1px solid var(--line); margin-right:-5px; }
.legend .sw.wf { background:var(--wf); }
.legend .sw.inv { color:var(--inv); font-weight:700; font-size:10px; line-height:11px; text-align:center; }
.issues { position:absolute; right:8px; top:8px; max-width:420px; background:var(--bg); border:1px solid var(--line); border-radius:6px; padding:8px 10px; font-size:12px; box-shadow:0 4px 16px rgba(0,0,0,.12); z-index:2; }
.issues div { color:var(--err); }
.box rect.body { fill:var(--bg); stroke:var(--line); }
.box.sel rect.body { stroke:var(--accent); stroke-width:2; }
.box rect.head { fill:var(--head); }
.box.enum rect.head { fill:var(--enum); }
.box text { fill:var(--fg); font-size:13px; }
.box text.title { font-weight:600; font-size:14px; }
.box text.abstract { font-style:italic; }
.box text.stereo, .box text.muted { fill:var(--muted); font-size:11.5px; }
.box { cursor:move; }
.edge { stroke:var(--muted); fill:none; stroke-width:1.6; }
.edge.inherit { stroke-dasharray:none; }
.elabel { fill:var(--muted); font-size:12px; paint-order:stroke; stroke:var(--bg); stroke-width:4px; stroke-linejoin:round; }
.mk-open { fill:var(--bg); stroke:var(--muted); stroke-width:1.2; }
.mk-line { fill:none; stroke:var(--muted); stroke-width:1.6; stroke-linejoin:round; }
.status.warn { color:#d97706; }
.issues div.w { color:#b45309; }
.mk-fill { fill:var(--muted); }
.elabel { cursor:pointer; }
.junction { fill:var(--muted); }
svg.hover .edge:not(.hi), svg.hover .elabel:not(.hi), svg.hover .junction:not(.hi) { opacity:.15; }
.edge.hi { stroke:var(--accent); stroke-width:2.4; }
.junction.hi { fill:var(--accent); }
.elabel.hi { fill:var(--accent); font-weight:600; }
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
  const multKey = (lo, up) => MULTS.find((m) => m[1] === lo && m[2] === up)?.[0] ?? "0..1";
  const snake = (s) => s.replace(/(?<=[a-z0-9])([A-Z])/g, "_$1").toLowerCase();

  // real text widths for the state diagram (one canvas 2D context and cache shared by the editor and the viewers);
  // undefined when there is no 2D context: the layout falls back to its estimate
  let mctx, mcache;
  const textMeasure = () => {
    if (mctx === undefined) {
      mctx = document.createElement("canvas").getContext?.("2d") || null;
      mcache = new Map();
    }
    if (!mctx) return undefined;
    return (text, font, bold = false) => {
      const k = `${bold ? 1 : 0}|${font}|${text}`;
      let w = mcache.get(k);
      if (w === undefined) {
        mctx.font = `${bold ? 600 : 400} ${font}px system-ui, sans-serif`;
        w = mctx.measureText(text).width;
        mcache.set(k, w);
      }
      return w;
    };
  };
  // the state diagram as SVG: states in their colour (thick border when final), connectors in the colour of the
  // target state (dashed when timed) with a filled arrow head, dots at bus junctions, labels on a background.
  // Every part carries data-edge="wf:<class>:<transition>" for the hover highlight.
  // opts.current: the key of the state a record is in (its box filled with its colour, thick border);
  // opts.focus: a Set of the ids of the edges leaving it (class `out`; the other edges `far`, dimmed).
  const workflowSvg = (cn, L, opts = {}) => {
    const current = opts.current != null && L.boxes.some((b) => b.key === opts.current) ? opts.current : null;
    const root = svg("svg", { width: L.width + 2 * WF_PAD, height: L.height + WF_PAD, role: "img", "aria-label": current ? `workflow ${cn} · ${current}` : `workflow ${cn}` });
    const inner = svg("g", { transform: `translate(${WF_PAD},${WF_PAD / 2})` });
    const pathD = (pts) => pts.map((q, i) => `${i ? "L" : "M"}${q.x},${q.y}`).join(" ");
    const mark = (e) => (opts.focus ? (opts.focus.has(e.id) ? " out" : " far") : "");
    for (const e of L.edges) {
      const key = `wf:${cn}:${e.key}`, m = mark(e);
      for (const p of e.paths) {
        inner.append(svg("path", { d: pathD(p), class: "ehit", "data-edge": key }));
        inner.append(svg("path", { d: pathD(p), class: `wfe${m}`, stroke: e.color, "stroke-dasharray": e.timed ? "5 4" : null, "data-edge": key }));
      }
      for (const q of e.dots) inner.append(svg("circle", { cx: q.x, cy: q.y, r: 2.4, class: `wfdot${m}`, fill: e.color, "data-edge": key }));
      inner.append(svg("polygon", { points: [e.arrow[0], e.arrow[2], e.arrow[3]].map((q) => `${q.x},${q.y}`).join(" "), class: `wfa${m}`, fill: e.color, "data-edge": key }));
    }
    for (const b of L.boxes) {
      // the current state (a record's): box filled with its colour, white text, a ring around it, as the state path
      // of an app marks its current step; the other boxes dim. The class rule .wfs sets the fill: inline style wins.
      const cur = current !== null && b.key === current, bm = cur ? " cur" : current !== null ? " far" : "";
      if (cur) inner.append(svg("rect", { x: b.x - 4, y: b.y - 4, width: b.w + 8, height: b.h + 8, rx: 11, class: "wfring", stroke: b.color }));
      inner.append(svg("rect", { x: b.x, y: b.y, width: b.w, height: b.h, rx: 7, class: `wfs${bm}`, stroke: b.color, "data-state": b.key,
        "stroke-width": cur || b.kind === "final" ? 3 : 1.5, style: cur ? `fill:${b.color}` : null }));
      const text = svg("text", { x: b.x + b.w / 2, y: b.y + 9 + WF.font, "text-anchor": "middle", class: `wfst${bm}`, fill: cur ? "#fff" : b.color });
      b.lines.forEach((line, i) => text.append(svg("tspan", { x: b.x + b.w / 2, dy: i ? WF.font + 3 : 0 }, line)));
      inner.append(text, svg("text", { x: b.x + b.w / 2, y: b.y + b.h - 6, "text-anchor": "middle", class: `wfkey${bm}` }, b.key));
    }
    for (const e of L.edges) {   // labels on top of the lines
      const key = `wf:${cn}:${e.key}`, l = e.label, m = mark(e);
      inner.append(svg("rect", { x: l.x, y: l.y, width: l.w, height: l.h, rx: 3, class: `wfl-bg${m}`, stroke: e.color, "data-edge": key }));
      const text = svg("text", { x: l.x + l.w / 2, y: l.y + WF.labelFont + 3, "text-anchor": "middle", class: `wfl${m}`, "data-edge": key });
      l.lines.forEach((line, i) => text.append(svg("tspan", { x: l.x + l.w / 2, dy: i ? WF.labelFont + 3 : 0 }, line)));
      inner.append(text);
    }
    root.append(inner);
    return root;
  };
  // the hover highlight of the connectors in the given SVG roots: the parts whose data-edge is `key` get `hi` and the
  // roots `hover` (the other parts dim). Returns the key still drawn somewhere, else null (no roots: unchanged).
  const applyHover = (roots, key) => {
    if (!roots.length) return key;
    const all = roots.flatMap((r) => [...r.querySelectorAll("[data-edge]")]);
    const cur = key && all.some((n) => n.dataset.edge === key) ? key : null;
    for (const r of roots) r.classList.toggle("hover", !!cur);
    for (const n of all) n.classList.toggle("hi", n.dataset.edge === cur);
    return cur;
  };

  class MetamodelEditor extends HTMLElement {
    constructor() {
      super();
      this._mm = { package: "domain", classes: {}, enums: {}, diagram: {} };
      this._orig = null;
      this._sel = null;
      this._view = { x: 0, y: 0, k: 1 };
      this._autoFit = true;        // refit when the canvas is resized, until the user zooms or pans
      this._panel = false;         // side panel open (it opens on selection)
      this._allAttrs = false;      // boxes show every attribute instead of the first MAX_ROWS
      this._showIssues = false;
      this._hover = null;          // key of the connector under the mouse: highlighted, the others dimmed
      this._bh = null;             // behavior.json (optional): formulas of the derived attributes, workflows, uses
      this._wfCache = new Map();   // state-diagram layouts of the panel, per class, language and width
      this._bhOrig = null;         // the behaviour the editor was opened with (changesTo compares with it)
      this._wfUserH = null;        // height of the workflow panel chosen by dragging its grip (null: automatic)
      this._lastSel = undefined;   // the selection last announced with the `select` event
      this.attachShadow({ mode: "open" });
    }

    static get observedAttributes() { return ["lang", "readonly", "save-label"]; }
    attributeChangedCallback() { this._wfCache.clear(); if (this.isConnected) this._render(); }
    connectedCallback() { this._render(); }

    get t() { return T[(this.getAttribute("lang") || "it").slice(0, 2)] || T.it; }
    get readonly() { return this.hasAttribute("readonly"); }
    set readonly(v) { if (v) this.setAttribute("readonly", ""); else this.removeAttribute("readonly"); }

    set metamodel(mm) {
      const m = Layout.normalize(mm);
      this._mm = m;
      this._wfCache.clear();
      this._orig = clone(m);
      this._sel = null;
      this._panel = false;
      this._autoFit = true;
      this._autoLayout(false);
      this._render();
      requestAnimationFrame(() => this._fit());
    }
    get metamodel() { return clone(this._mm); }
    // the behaviour model (src/lib/modeler/behavior.json): read only, shown next to the structure it refers to
    set behavior(b) {
      this._bh = b && typeof b === "object" ? clone(b) : null;
      this._bhOrig = this._bh ? clone(this._bh) : null;
      this._wfCache.clear();
      if (this.isConnected) this._render();
    }
    get behavior() { return this._bh ? clone(this._bh) : null; }
    // the behaviour as a proposal carries it (behavior.yaml structure, expressions as text), or null
    behaviorProposal() { return Layout.behaviorSource(this._bh); }
    // a change of the behaviour from the panel or the side panel: the diagram and the proposal follow
    _bhChanged() { this._wfCache.clear(); this._changed(); }
    // comma separated list <-> array of names
    _list(text) { return String(text || "").split(",").map((x) => x.trim()).filter(Boolean); }
    _workflow(cn) { return this._bh?.workflows?.[cn] || null; }
    _formula(cn, an) { return this._bh?.derivations?.[cn]?.[an]?.text ?? null; }
    _uses(cn) { return this._bh?.uses?.[cn] || null; }
    _lang() { return (this.getAttribute("lang") || "it").slice(0, 2); }
    // "used by: Project.plannedHours (derivation), …" for a feature or a whole class
    _usedText(used) { return `${this.t.usedBy}: ${used.map((u) => `${u.of} (${this.t[u.kind] || u.kind})`).join(", ")}`; }
    _usesText(cn) {
      const u = this._uses(cn);
      if (!u) return "";
      const lines = [...Object.entries(u.attributes || {}), ...Object.entries(u.references || {})].map(([n, used]) => `${n} — ${this._usedText(used)}`);
      if (u.class?.length) lines.push(this._usedText(u.class));
      return lines.join("\n");
    }
    // the changes from the metamodel the editor was opened with (the running one) to `mm`, as `modeler diff`
    changesTo(mm, bh) {
      const lines = Layout.diff(this._orig || {}, mm);
      return bh === undefined ? lines : [...lines, ...Layout.behaviorDiff(this._bhOrig, bh).map((l) => `behaviour: ${l}`)];
    }
    getMetamodel() { return this.metamodel; }

    /* ------------------------------------------------------------------ model edits */
    _schedule() {
      if (this._pending) return;
      this._pending = true;
      setTimeout(() => { this._pending = false; this._render(); }, 0);
    }
    _changed() {
      this._schedule();
      this.dispatchEvent(new CustomEvent("change", { detail: { metamodel: this.metamodel, behavior: this.behaviorProposal(), issues: this._issues() } }));
    }

    _uniqueName(base, taken) { let n = base, i = 2; while (taken.includes(n)) n = base + i++; return n; }
    _allNames() { return [...Object.keys(this._mm.classes), ...Object.keys(this._mm.enums), "User"]; }

    _addClass() {
      const name = this._uniqueName(this.t.newClass, this._allNames());
      this._mm.classes[name] = { abstract: false, supertypes: [], attributes: { name: { type: "EString", lower: 1, upper: 1 } }, references: {} };
      this._mm.diagram[name] = this._freeSpot(name);
      this._sel = { kind: "class", name };
      this._panel = true;
      this._changed();
    }
    _addEnum() {
      const name = this._uniqueName(this.t.newEnum, this._allNames());
      this._mm.enums[name] = { literals: [{ name: "first" }, { name: "second" }] };
      this._mm.diagram[name] = this._freeSpot(name);
      this._sel = { kind: "enum", name };
      this._panel = true;
      this._changed();
    }
    _freeSpot(name) {
      // the place of the box of `name` (just added to the model, not yet to the diagram): see Layout.freeSpot
      const mm = this._mm;
      const occupied = Object.keys(mm.diagram).filter((n) => n !== name && (mm.classes[n] || mm.enums[n]))
        .map((n) => ({ ...mm.diagram[n], ...this._boxSize(n) }));
      const size = this._boxSize(name);
      const r = this.shadowRoot.querySelector(".canvas")?.getBoundingClientRect();
      const v = this._view;
      const view = { x: -v.x / v.k, y: -v.y / v.k, w: (r?.width || 800) / v.k, h: (r?.height || 500) / v.k };
      return Layout.freeSpot(occupied, size, { x: view.x + view.w / 2 - size.w / 2, y: view.y + view.h / 3 }, view);
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
      if (origClass?.[kind]?.[old] && !f.renamed_from) f.renamed_from = old;   // the migration renames the column, keeping the data
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

    /* ------------------------------------------------------------------ destructive changes */
    _warnings() {
      // compared with the metamodel the page was opened with: what the migration would have to drop
      const t = this.t, out = [], orig = this._orig;
      if (!orig) return out;
      for (const [cn, oc] of Object.entries(orig.classes || {})) {
        const c = this._mm.classes[cn];
        if (!c) { if (!oc.abstract) out.push(`${cn}: ${t.dropClass}`); continue; }
        for (const kind of ["attributes", "references"]) {
          const renamed = Object.values(c[kind]).map((f) => f.renamed_from).filter(Boolean);
          for (const fn of Object.keys(oc[kind] || {})) if (!c[kind][fn] && !renamed.includes(fn)) out.push(`${cn}.${fn}: ${t.dropFeature}`);
        }
      }
      for (const [en, oe] of Object.entries(orig.enums || {})) {
        const names = (this._mm.enums[en]?.literals || []).map((l) => l.name);
        for (const l of oe.literals || []) if (this._mm.enums[en] && !names.includes(l.name)) out.push(`${en}.${l.name}: ${t.dropLiteral}`);
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
      out.push(...this._behaviorIssues());
      return [...new Set(out)];
    }
    // what the CLI's validate would refuse at once (the full check against the metamodel runs at apply time)
    _behaviorIssues() {
      const t = this.t, mm = this._mm, out = [], bh = this._bh;
      if (!bh) return out;
      const KEY = /^[a-z][a-z0-9_]*$/;
      for (const [cn, w] of Object.entries(bh.workflows || {})) {
        const c = mm.classes[cn];
        if (!c) { out.push(`${cn}: ${t.noTarget}`); continue; }
        const states = Object.keys(w.states || {});
        const attr = c.attributes[w.state];
        if (!attr) out.push(`${cn}.${w.state}: ${t.wfStateAttr}`);
        else if (mm.enums[attr.type]) {
          const lits = mm.enums[attr.type].literals.map((l) => l.name).sort().join(",");
          if (lits !== [...states].sort().join(",")) out.push(`${cn}.${w.state}: ${t.wfEnumStates} ${attr.type}`);
        }
        const initial = states.filter((sn) => w.states[sn].initial);
        if (!initial.length) out.push(`${cn}: ${t.wfNoInitial}`);
        if (initial.length > 1) out.push(`${cn}: ${t.wfManyInitial}`);
        if (!states.some((sn) => w.states[sn].final)) out.push(`${cn}: ${t.wfNoFinal}`);
        for (const sn of states) if (!KEY.test(sn)) out.push(`${cn}.${sn}: ${t.wfBadKey}`);
        for (const sn of states) for (const f of [...[].concat(w.states[sn].requires || []), ...Object.keys(w.states[sn].model || {})]) if (!c.attributes[f] && !c.references[f]) out.push(`${cn}.${sn}: ${t.wfBadRequires} ${f}`);
        for (const [tn, tr] of Object.entries(w.transitions || {})) {
          if (!KEY.test(tn)) out.push(`${cn}.${tn}: ${t.wfBadKey}`);
          for (const f of [].concat(tr.from || [])) if (!w.states?.[f]) out.push(`${cn}.${tn}: ${t.wfBadState} ${f}`);
          if (!w.states?.[tr.to]) out.push(`${cn}.${tn}: ${t.wfBadState} ${tr.to ?? "—"}`);
          if (!(tr.by || []).length && (tr.at == null || tr.at === "")) out.push(`${cn}.${tn}: ${t.wfNoActor}`);
        }
      }
      for (const r of bh.reactions || []) {
        const [cn, ev] = String(r.event || "").split(".");
        if (!cn || !ev || !mm.classes[cn]) out.push(`${r.name || "?"}: ${t.rxBadEvent}`);
      }
      return out;
    }

    /* ------------------------------------------------------------------ layout */
    // what the states of the class's workflow say of its features, and the state whose view is shown (hover in the panel)
    _overlay(cn) { const w = this._workflow(cn); return w ? Layout.stateOverlay(w, this._lang()) : null; }
    _overlays() { const out = {}; for (const cn of Object.keys(this._bh?.workflows || {})) if (this._mm.classes[cn]) out[cn] = this._overlay(cn); return out; }
    _stateViewOf(cn) { return this._wfView?.cn === cn ? Layout.stateView(this._workflow(cn)?.states?.[this._wfView.state]) : null; }
    _rowOpts(cn) { return { overlay: this._overlay(cn), view: this._stateViewOf(cn), from: this.t.fromState }; }
    _sizeOpts(cn) { return { allAttrs: this._allAttrs, more: this.t.more, state: this._workflow(cn)?.state || null, uses: this._uses(cn), workflow: !!this._workflow(cn), ...this._rowOpts(cn) }; }
    _rows(cn) { return Layout.rowItems(this._mm.classes[cn], this._allAttrs, this.t.more, this._workflow(cn)?.state || null, this._uses(cn), this._rowOpts(cn)); }
    _boxSize(name) { return Layout.boxSize(this._mm, name, this._sizeOpts(name)); }
    _workflowText(cn) {
      const w = this._workflow(cn), t = this.t;
      return w ? `${t.workflow}: ${Object.keys(w.states || {}).length} ${t.states}, ${Object.keys(w.transitions || {}).length} ${t.transitions}` : "";
    }
    _autoLayout(force) {
      const r = this.shadowRoot.querySelector(".canvas")?.getBoundingClientRect();
      const pos = Layout.autoLayout(this._mm, (n) => this._boxSize(n),
        { force, width: r ? r.width - 2 * MARGIN : 0, height: r ? r.height - 2 * MARGIN : 0, overlay: this._overlays(), from: this.t.fromState });
      Object.assign(this._mm.diagram, pos);
    }
    _fit() {
      const r = this.shadowRoot.querySelector(".canvas")?.getBoundingClientRect();
      const pos = Object.entries(this._mm.diagram).filter(([n]) => this._mm.classes[n] || this._mm.enums[n]);
      if (!r || r.width < 50 || r.height < 50 || !pos.length) return;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const [n, p] of pos) {
        const s = this._boxSize(n);
        x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x + s.w); y1 = Math.max(y1, p.y + s.h);
      }
      if (this._ext) {   // connectors that run around the boxes stay in view
        x0 = Math.min(x0, this._ext.x0); y0 = Math.min(y0, this._ext.y0); x1 = Math.max(x1, this._ext.x1); y1 = Math.max(y1, this._ext.y1);
      }
      this._view = Layout.fitView({ x0, y0, x1, y1 }, { w: r.width, h: r.height });
      this._renderDiagram();
    }
    _refit() { this._autoFit = true; this._fit(); }
    _zoom(factor) {
      // zoom buttons only: the wheel scrolls the page, as everywhere else (no accidental zoom), and the diagram
      // fills the canvas by default (fit on open and on resize until the user zooms or pans)
      const r = this.shadowRoot.querySelector(".canvas")?.getBoundingClientRect();
      if (!r) return;
      this._autoFit = false;
      this._view = Layout.zoomView(this._view, factor, { x: r.width / 2, y: r.height / 2 });
      this._renderDiagram();
    }
    _separate() {
      // boxes grew (all attributes shown): push down the ones that now overlap, keeping columns and order
      const mm = this._mm;
      const names = Object.keys(mm.diagram).filter((n) => mm.classes[n] || mm.enums[n]).sort((a, b) => mm.diagram[a].y - mm.diagram[b].y);
      const done = [];
      for (const n of names) {
        const p = mm.diagram[n], s = this._boxSize(n);
        let moved = true;
        while (moved) {
          moved = false;
          for (const o of done) {
            const q = mm.diagram[o], t = this._boxSize(o);
            if (p.x < q.x + t.w && q.x < p.x + s.w && p.y < q.y + t.h + GAP_Y / 2 && q.y < p.y + s.h) {
              p.y = q.y + t.h + GAP_Y;
              moved = true;
            }
          }
        }
        done.push(n);
      }
    }
    _toggleFullscreen() {
      if (document.fullscreenElement === this) document.exitFullscreen?.();
      else this.requestFullscreen?.().catch(() => {});
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
          el("div", { class: "main" }, el("div", { class: "canvas" }), el("div", { class: "side" })),
          el("div", { class: "wfpanel" }));
        root.append(wrap);
        const canvas = root.querySelector(".canvas");
        this._bindCanvas(canvas);
        // the workflow panel: re-laid out at its width, hover like the canvas
        const panel = root.querySelector(".wfpanel");
        const grip = el("div", { class: "wfgrip", title: t.resize });
        panel.append(grip, el("div", { class: "wfbody" }));
        let panelPending = false;
        new ResizeObserver(() => {   // the width changed: a new layout (not while the grip is dragged: only the height moves)
          if (panelPending || this._wfDrag) return;
          panelPending = true;
          requestAnimationFrame(() => { panelPending = false; this._renderWorkflowPanel(); });
        }).observe(panel);
        // the grip: drag to set the panel's height (the canvas keeps at least 160px), double click for the automatic one
        grip.addEventListener("pointerdown", (ev) => {
          this._wfDrag = { y: ev.clientY, h: panel.getBoundingClientRect().height };
          grip.setPointerCapture(ev.pointerId);
          ev.preventDefault();
        });
        grip.addEventListener("pointermove", (ev) => {
          if (!this._wfDrag) return;
          const bar = root.querySelector(".bar")?.getBoundingClientRect().height || 0;
          const max = Math.max(120, (root.querySelector(".wrap")?.clientHeight || 600) - bar - 160);
          this._wfUserH = Math.round(Math.min(max, Math.max(120, this._wfDrag.h - (ev.clientY - this._wfDrag.y))));
          panel.style.height = `${this._wfUserH}px`;
        });
        const endDrag = () => { this._wfDrag = null; };
        grip.addEventListener("pointerup", endDrag);
        grip.addEventListener("pointercancel", endDrag);
        grip.addEventListener("dblclick", () => { this._wfUserH = null; this._renderWorkflowPanel(); });
        panel.addEventListener("pointerover", (ev) => {
          const key = ev.target.closest?.("[data-edge]")?.dataset.edge || null;
          if (key !== this._hover) { this._hover = key; this._applyHover(); }
        });
        panel.addEventListener("pointerleave", () => { if (this._hover) { this._hover = null; this._applyHover(); } });
        // keep the diagram fitted to the canvas (window resized, panel opened, full screen) until the user zooms
        let pending = false;
        new ResizeObserver(() => {
          if (!this._autoFit || pending) return;
          pending = true;
          requestAnimationFrame(() => { pending = false; this._fit(); });
        }).observe(canvas);
        document.addEventListener("fullscreenchange", () => { this._render(); this._refit(); });
        requestAnimationFrame(() => this._fit());
      }
      root.querySelector(".main").classList.toggle("nopanel", !this._panel);
      const bar = root.querySelector(".bar");
      const issues = this._issues();
      const warns = this._warnings();
      bar.replaceChildren(...[
        el("strong", {}, `${t.package} ${this._mm.package || ""}`),
        this.readonly ? el("span", { class: "hint" }, `· ${t.readonly}`) : null,
        this.readonly ? null : el("button", { onclick: () => this._addClass(), title: t.addClass }, `+ ${t.addClass}`),
        this.readonly ? null : el("button", { onclick: () => this._addEnum(), title: t.addEnum }, `+ ${t.addEnum}`),
        el("button", { onclick: () => { this._autoLayout(true); this._refit(); this._changed(); }, disabled: this.readonly }, t.layout),
        el("button", { onclick: () => this._refit() }, t.fit),
        el("button", { onclick: () => this._zoom(1.25), title: t.zoomIn, "aria-label": t.zoomIn }, "+"),
        el("button", { onclick: () => this._zoom(0.8), title: t.zoomOut, "aria-label": t.zoomOut }, "−"),
        el("button", { class: this._allAttrs ? "on" : "", onclick: () => { this._allAttrs = !this._allAttrs; this._separate(); this._render(); this._refit(); } },
          this._allAttrs ? t.compact : t.allAttrs),
        el("button", { class: this._panel ? "on" : "", onclick: () => { this._panel = !this._panel; this._render(); } }, t.panel),
        el("button", { onclick: () => this._toggleFullscreen() }, document.fullscreenElement === this ? t.exitFullscreen : t.fullscreen),
        el("span", {
          class: `status ${issues.length ? "bad" : "good"}`,
          onclick: () => { this._showIssues = !this._showIssues; this._schedule(); },
        }, issues.length ? `⚠ ${issues.length} ${t.issues}` : `✓ ${t.ok}`),
        warns.length ? el("span", { class: "status warn", onclick: () => { this._showIssues = !this._showIssues; this._schedule(); } }, `△ ${warns.length} ${t.warnings}`) : null,
        el("span", { class: "grow" }),
        this.readonly ? null : el("input", { class: "note", placeholder: t.note, size: 24, value: this._note || "", oninput: (e) => { this._note = e.target.value; } }),
        this.readonly ? null : el("button", {
          class: "primary", disabled: issues.length > 0,
          onclick: () => this.dispatchEvent(new CustomEvent("save", { detail: { metamodel: this.metamodel, behavior: this.behaviorProposal(), note: this._note || "" } })),
        }, this.getAttribute("save-label") || t.save),
        VERSION.startsWith("__") ? null : el("span", { class: "hint", title: `${t.modeler} ${VERSION}` }, `v${VERSION}`),
      ].filter(Boolean));
      this._renderDiagram();
      this._renderSide();
      this._renderWorkflowPanel();
      const selName = this._sel?.name ?? null;
      if (selName !== this._lastSel) {   // the page follows the selection (e.g. the behaviour of the class)
        this._lastSel = selName;
        this.dispatchEvent(new CustomEvent("select", { detail: { kind: this._sel?.kind ?? null, name: selName } }));
      }
      const canvas = root.querySelector(".canvas");
      canvas.querySelector(".issues")?.remove();
      if (this._showIssues && (issues.length || warns.length)) {
        canvas.append(el("div", { class: "issues" }, issues.map((i) => el("div", {}, i)), warns.map((w) => el("div", { class: "w" }, `△ ${w}`))));
      }
      canvas.querySelector(".legend")?.remove();
      if (this._bh) {   // the three levels of involvement in the behaviour
        canvas.append(el("div", { class: "legend" },
          el("span", { class: "sw wf" }), t.legendWf, el("span", { class: "sw inv" }, "ƒ"), t.legendInvolved, el("span", { class: "sw" }), t.legendStruct));
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
          this._panel = true;
          const start = { ...(this._mm.diagram[name] || { x: 0, y: 0 }) };
          drag = { kind: "box", name, p, start, moved: false };
          this._schedule();
        } else {
          drag = { kind: "pan", p, start: { ...this._view }, moved: false };
        }
        canvas.setPointerCapture(ev.pointerId);
      });
      canvas.addEventListener("pointermove", (ev) => {
        if (!drag) return;
        const dx = ev.clientX - drag.p.x, dy = ev.clientY - drag.p.y;
        if (drag.kind === "pan") {
          drag.moved = drag.moved || Math.abs(dx) + Math.abs(dy) > 2;
          if (drag.moved) this._autoFit = false;
          this._view = { ...drag.start, x: drag.start.x + dx, y: drag.start.y + dy };
        } else if (!this.readonly) {
          drag.moved = drag.moved || Math.abs(dx) + Math.abs(dy) > 2;
          this._mm.diagram[drag.name] = { x: Math.round(drag.start.x + dx / this._view.k), y: Math.round(drag.start.y + dy / this._view.k) };
        }
        this._renderDiagram();
      });
      const end = () => {
        if (drag?.kind === "box" && drag.moved) this._changed();
        if (drag?.kind === "pan" && !drag.moved && this._sel) {   // a click on the background: deselect
          this._sel = null;
          this._panel = false;
          this._schedule();
        }
        drag = null;
      };
      canvas.addEventListener("pointerover", (ev) => {
        const key = drag ? null : ev.target.closest?.("[data-edge]")?.dataset.edge || null;
        if (key !== this._hover) { this._hover = key; this._applyHover(); }
      });
      canvas.addEventListener("pointerleave", () => { if (this._hover) { this._hover = null; this._applyHover(); } });
      canvas.addEventListener("dblclick", (ev) => { if (!ev.target.closest?.(".box")) this._refit(); });
      canvas.addEventListener("pointerup", end);
      canvas.addEventListener("pointercancel", end);
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
        svg("marker", { id: "tri", viewBox: "0 0 12 12", refX: "11", refY: "6", markerWidth: "16", markerHeight: "16", orient: "auto-start-reverse", markerUnits: "userSpaceOnUse" },
          svg("path", { d: "M1,1 L11,6 L1,11 z", class: "mk-open" })),
        svg("marker", { id: "arrow", viewBox: "0 0 12 12", refX: "11", refY: "6", markerWidth: "11", markerHeight: "11", orient: "auto-start-reverse", markerUnits: "userSpaceOnUse" },
          svg("path", { d: "M1,1 L11,6 L1,11", class: "mk-line" })),
        svg("marker", { id: "diamond", viewBox: "0 0 16 10", refX: "15", refY: "5", markerWidth: "20", markerHeight: "12", orient: "auto-start-reverse", markerUnits: "userSpaceOnUse" },
          svg("path", { d: "M1,5 L8,1 L15,5 L8,9 z", class: "mk-fill" })));
      const g = svg("g", { transform: `translate(${this._view.x},${this._view.y}) scale(${this._view.k})` });
      const edges = svg("g", {});
      const labels = svg("g", {});
      // EMF / Ecore Tools notation (see Layout.edgesOf), orthogonal connectors with rounded corners
      const rounded = (pts, radius = 10) => {
        let d = `M${pts[0].x},${pts[0].y}`;
        for (let i = 1; i < pts.length - 1; i++) {
          const p0 = pts[i - 1], p1 = pts[i], p2 = pts[i + 1];
          const l1 = Math.hypot(p1.x - p0.x, p1.y - p0.y), l2 = Math.hypot(p2.x - p1.x, p2.y - p1.y);
          const r = Math.min(radius, l1 / 2, l2 / 2);
          if (r < 0.5) { d += ` L${p1.x},${p1.y}`; continue; }
          const a = { x: p1.x + ((p0.x - p1.x) / l1) * r, y: p1.y + ((p0.y - p1.y) / l1) * r };
          const b = { x: p1.x + ((p2.x - p1.x) / l2) * r, y: p1.y + ((p2.y - p1.y) / l2) * r };
          d += ` L${a.x},${a.y} Q${p1.x},${p1.y} ${b.x},${b.y}`;
        }
        const last = pts[pts.length - 1];
        return d + ` L${last.x},${last.y}`;
      };
      const routed = Layout.routeEdges(mm, (n) => this._boxSize(n), { uses: this._bh?.uses || null, overlay: this._overlays(), from: this.t.fromState });
      for (const e of routed.edges) {
        // a bus: the stub with the arrow, the trunk and a branch per source, with a dot where each joins the trunk
        const runs = [{ pts: e.pts, start: e.start, end: e.end }];
        if (e.trunk) runs.push({ pts: e.trunk }, ...e.branches.map((b) => ({ pts: b.pts, start: b.start })));
        for (const r of runs) {
          const d = rounded(r.pts);
          const attrs = { d, class: e.cls, "data-edge": e.key };
          if (r.start) attrs["marker-start"] = r.start;
          if (r.end) attrs["marker-end"] = r.end;
          edges.append(svg("path", attrs));
          edges.append(svg("path", { d, class: "ehit", "data-edge": e.key }));   // wider, invisible: easier to hover
        }
        if (e.trunk) {
          for (const q of [e.pts[0], ...e.branches.map((b) => b.pts[b.pts.length - 1])]) {
            edges.append(svg("circle", { cx: q.x, cy: q.y, r: 2.6, class: "junction", "data-edge": e.key }));
          }
        }
        for (const l of e.labels) {
          labels.append(svg("text", { x: l.x + 2, y: l.y + l.h - 3, class: "elabel", "data-edge": e.key }, l.text));
        }
      }
      const boxes = svg("g", {});
      for (const [cn, c] of Object.entries(mm.classes)) {
        const p = mm.diagram[cn];
        if (!p) continue;
        const s = this._boxSize(cn);
        const sel = this._sel?.name === cn;
        // «workflow» stereotype in the head of a class with a workflow; ƒ in the corner of a class the behaviour uses
        const wf = this._workflow(cn), involved = !wf && this._uses(cn);
        const hh = HEAD_H + (wf ? STEREO_H : 0);
        const viewed = this._wfView?.cn === cn && wf?.states?.[this._wfView.state] ? Layout.wfLabel(wf.states[this._wfView.state], this._wfView.state, this._lang()) : null;
        const b = svg("g", { class: `box${sel ? " sel" : ""}${wf ? " workflow" : ""}${viewed ? " viewed" : ""}`, "data-name": cn, transform: `translate(${p.x},${p.y})` },
          svg("rect", { class: "body", width: s.w, height: s.h, rx: 6 }),
          svg("rect", { class: "head", width: s.w - 2, x: 1, y: 1, height: hh - 2, rx: 5 }),
          wf ? svg("text", { x: s.w / 2, y: 14, "text-anchor": "middle", class: "stereo" }, viewed ? `«workflow · ${viewed}»` : "«workflow»") : null,
          svg("text", { x: s.w / 2, y: wf ? 30 : 21, "text-anchor": "middle", class: `title${c.abstract ? " abstract" : ""}` }, cn),
          involved ? svg("text", { x: s.w - 6, y: 13, "text-anchor": "end", class: "stereo mark" }, "ƒ", svg("title", {}, this._usesText(cn))) : null);
        let y = hh + 14;
        const rows = this._rows(cn);
        if (!rows.length) b.append(svg("text", { x: 8, y, class: "muted" }, "—"));
        for (const r of rows) {
          const tips = [];
          if (r.derived) tips.push(`/${r.attr} = ${this._formula(cn, r.attr) ?? this.t.inCode}`);
          if (r.state) tips.push(this._workflowText(cn));
          if (r.used) tips.push(this._usedText(r.used));
          const cls = [r.muted ? "muted" : r.state ? "state" : r.used ? "inv" : null, r.hidden ? "hidden" : null].filter(Boolean).join(" ") || null;
          b.append(svg("text", { x: 8, y, class: cls }, r.text, tips.length ? svg("title", {}, tips.join("\n")) : null));
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
      this._ext = routed.ext;
      g.append(edges, boxes, labels);   // lines under the boxes, labels on top
      const root = svg("svg", { role: "img", "aria-label": "metamodel diagram" }, defs, g);
      const old = canvas.querySelector("svg");
      if (old) old.replaceWith(root); else canvas.prepend(root);
      this._applyHover();
    }
    // the panel under the canvas: the state diagram of the selected class with a workflow (Layout.workflowLayout at
    // the panel's width, measured text), hidden when the selection is anything else. The diagram fills the width;
    // below the width of the longest state name it scrolls (core:diagrams).
    _renderWorkflowPanel() {
      const panel = this.shadowRoot.querySelector(".wfpanel"), body = panel?.querySelector(".wfbody");
      if (!panel || !body) return;
      const cn = this._sel?.kind === "class" ? this._sel.name : null;
      const wf = cn ? this._workflow(cn) : null;
      if (!wf) {
        if (panel.classList.contains("on")) { panel.classList.remove("on"); body.replaceChildren(); panel.style.height = ""; }
        return;
      }
      panel.classList.add("on");
      const width = Math.max(240, Math.floor(panel.clientWidth) - 2 * WF_PAD);
      const key = `${cn}|${this._lang()}|${width}`;
      let L = this._wfCache.get(key);
      if (!L) {
        const model = Layout.workflowModel(wf, this._lang());
        L = Layout.workflowLayout(model.states, model.transitions, width, { measure: textMeasure() });
        this._wfCache.set(key, L);
      }
      const t = this.t;
      const head = el("div", { class: "wfhead" }, el("strong", {}, cn),
        el("span", {}, `«workflow» ⟳ ${wf.state} · ${L.boxes.length} ${t.states}, ${Object.keys(wf.transitions || {}).length} ${t.transitions}`),
        Object.values(wf.states || {}).some((st) => Object.keys(Layout.stateView(st)).length) ? el("span", { class: "hint" }, t.stateViewHint) : null);
      const edit = this.readonly ? null : this._workflowEditor(cn, wf);
      const scroll = { top: body.scrollTop, left: body.scrollLeft };   // an edit re-renders the panel: keep where the user was
      const diagram = workflowSvg(cn, L);
      // hovering a state redraws the class box as seen from that state (the diagram only: the panel stays put)
      for (const node of diagram.querySelectorAll("[data-state]")) {
        node.addEventListener("mouseenter", () => { this._wfView = { cn, state: node.dataset.state }; this._renderDiagram(); });
        node.addEventListener("mouseleave", () => { if (this._wfView?.state === node.dataset.state) { this._wfView = null; this._renderDiagram(); } });
      }
      body.replaceChildren(head, diagram, ...(edit ? [edit] : []));
      body.scrollTop = scroll.top; body.scrollLeft = scroll.left;
      // the height the user dragged, else what the diagram (and the editing tables) need, up to half of the editor
      const wrapH = this.shadowRoot.querySelector(".wrap")?.clientHeight || 600;
      const h = this._wfUserH ?? Math.round(Math.min(Math.max(220, wrapH * 0.5), Math.max(160, L.height + WF_HEAD + (edit ? edit.scrollHeight || 220 : 0))));
      if (panel.style.height !== `${h}px`) panel.style.height = `${h}px`;
      this._applyHover();
    }
    // the states, transitions and revert of a workflow as tables of inputs; every change goes into the proposal
    _workflowEditor(cn, w) {
      const t = this.t, lang = this._lang();
      const states = w.states || (w.states = {}), trs = w.transitions || (w.transitions = {});
      const rename = (obj, oldKey, newKey) => { const rebuilt = {}; for (const [k, v] of Object.entries(obj)) rebuilt[k === oldKey ? newKey : k] = v; return rebuilt; };
      const lbl = (spec) => (typeof spec.label === "string" ? spec.label : spec.label?.[lang] || "");
      const setLbl = (spec, v) => { if (v) spec.label = typeof spec.label === "object" && spec.label ? { ...spec.label, [lang]: v } : { [lang]: v }; else delete spec.label; };
      const stateRows = Object.entries(states).map(([sn, st]) => el("tr", {},
        el("td", {}, el("input", { class: "k", value: sn, onchange: (ev) => { const n = ev.target.value.trim(); if (!n || n === sn) return; w.states = rename(states, sn, n); for (const tr of Object.values(trs)) { tr.from = [].concat(tr.from || []).map((f) => (f === sn ? n : f)); if (tr.to === sn) tr.to = n; } this._bhChanged(); } })),
        el("td", {}, el("input", { class: "w", value: lbl(st), onchange: (ev) => { setLbl(st, ev.target.value.trim()); this._bhChanged(); } })),
        el("td", {}, el("input", { type: "color", value: st.color || "#64748b", onchange: (ev) => { st.color = ev.target.value; this._bhChanged(); } })),
        el("td", {}, el("select", { onchange: (ev) => { st.initial = ev.target.value === "initial"; st.final = ev.target.value === "final"; if (!st.initial) delete st.initial; if (!st.final) delete st.final; this._bhChanged(); } },
          el("option", { value: "", selected: !st.initial && !st.final }, "—"), el("option", { value: "initial", selected: !!st.initial }, t.initial), el("option", { value: "final", selected: !!st.final }, t.final))),
        el("td", {}, el("input", { class: "w", value: (st.owner || []).join(", "), title: t.listHint, onchange: (ev) => { st.owner = this._list(ev.target.value); this._bhChanged(); } })),
        el("td", {}, el("input", { class: "w", value: (st.editable_by || []).join(", "), title: t.listHint, onchange: (ev) => { st.editable_by = this._list(ev.target.value); this._bhChanged(); } })),
        el("td", {}, el("input", { class: "w", value: (st.requires || []).join(", "), title: t.requiresHint, onchange: (ev) => { const v = this._list(ev.target.value); if (v.length) st.requires = v; else delete st.requires; this._bhChanged(); } })),
        el("td", { class: "hint", title: t.modelHint }, Object.entries(st.model || {}).map(([f, o]) => `${f}: ${Layout.viewMark(Layout.stateView({ model: { [f]: o } })[f])}`).join(" · ")),
        el("td", {}, el("input", { class: "n", value: st.reminder?.after || "", placeholder: "7d", onchange: (ev) => { const v = ev.target.value.trim(); st.reminder = v ? { ...(st.reminder || {}), after: v } : null; this._bhChanged(); } })),
        el("td", {}, el("button", { class: "x", title: t.del, onclick: () => { delete states[sn]; this._bhChanged(); } }, "×"))));
      const stateOptions = (cur) => Object.keys(states).map((sn) => el("option", { value: sn, selected: sn === cur }, sn));
      const trRows = Object.entries(trs).map(([tn, tr]) => el("tr", {},
        el("td", {}, el("input", { class: "k", value: tn, onchange: (ev) => { const n = ev.target.value.trim(); if (n && n !== tn) { w.transitions = rename(trs, tn, n); this._bhChanged(); } } })),
        el("td", {}, el("input", { class: "w", value: lbl(tr), onchange: (ev) => { setLbl(tr, ev.target.value.trim()); this._bhChanged(); } })),
        el("td", {}, el("input", { class: "w", value: [].concat(tr.from || []).join(", "), title: t.listHint, onchange: (ev) => { tr.from = this._list(ev.target.value); this._bhChanged(); } })),
        el("td", {}, el("select", { onchange: (ev) => { tr.to = ev.target.value; this._bhChanged(); } }, stateOptions(tr.to))),
        el("td", {}, el("input", { class: "w", value: (tr.by || []).join(", "), title: t.listHint, placeholder: "self.ref, role", onchange: (ev) => { tr.by = this._list(ev.target.value); this._bhChanged(); } })),
        el("td", {}, el("input", { class: "w", value: exprText(tr.when) || "", onchange: (ev) => { const v = ev.target.value.trim(); tr.when = v ? { text: v } : null; this._bhChanged(); } })),
        el("td", {}, el("input", { class: "w", value: exprText(tr.guard) || "", onchange: (ev) => { const v = ev.target.value.trim(); tr.guard = v ? { text: v } : null; this._bhChanged(); } })),
        el("td", {}, el("select", { onchange: (ev) => { tr.comment = ev.target.value || null; this._bhChanged(); } },
          el("option", { value: "", selected: !tr.comment }, "—"), el("option", { value: "optional", selected: tr.comment === "optional" }, t.optional), el("option", { value: "required", selected: tr.comment === "required" }, t.required))),
        el("td", {}, el("input", { class: "w", value: tr.at ?? "", placeholder: "dueDate + 30d", onchange: (ev) => { tr.at = ev.target.value.trim() || null; this._bhChanged(); } })),
        el("td", {}, el("input", { class: "w", value: (tr.emits || []).join(", "), title: t.listHint, onchange: (ev) => { tr.emits = this._list(ev.target.value); this._bhChanged(); } })),
        el("td", {}, el("button", { class: "x", title: t.del, onclick: () => { delete trs[tn]; this._bhChanged(); } }, "×"))));
      const rv = w.revert;
      return el("div", { class: "wfedit" },
        el("div", {},
          el("h4", {}, `${t.states} · ⟳ ${w.state}`),
          el("table", {}, el("tr", {}, ...[t.name, t.label, t.color, t.kind, t.owner, t.editable_by, t.requires, t.model, t.reminder, ""].map((h) => el("th", {}, h))), ...stateRows),
          el("button", { onclick: () => { states[this._uniqueName("state", Object.keys(states))] = {}; this._bhChanged(); } }, `+ ${t.state}`)),
        el("div", {},
          el("h4", {}, t.transitions),
          el("table", {}, el("tr", {}, ...[t.name, t.label, t.from, t.to, t.who, t.when, t.guard, t.comment, t.at, t.emits, ""].map((h) => el("th", {}, h))), ...trRows),
          el("button", { onclick: () => { const keys = Object.keys(states); trs[this._uniqueName("transition", Object.keys(trs))] = { from: [keys[0]].filter(Boolean), to: keys[1] || keys[0] || "", by: [], when: null, guard: null, comment: null, at: null, emits: [] }; this._bhChanged(); } }, `+ ${t.transition}`)),
        el("div", { class: "wf" }, el("h4", {}, t.revert),
          el("label", { style: "display:inline-flex;gap:4px;align-items:center;margin-right:10px" }, t.who, el("input", { class: "w", value: (rv?.by || []).join(", "), title: t.listHint, onchange: (ev) => { const by = this._list(ev.target.value); w.revert = by.length || rv?.final_by?.length ? { ...(rv || {}), by, final_by: rv?.final_by || [], comment: rv?.comment || null } : null; this._bhChanged(); } })),
          el("label", { style: "display:inline-flex;gap:4px;align-items:center;margin-right:10px" }, `${t.final}:`, el("input", { class: "w", value: (rv?.final_by || []).join(", "), title: t.listHint, onchange: (ev) => { const fb = this._list(ev.target.value); w.revert = { ...(rv || { by: [] }), final_by: fb, comment: rv?.comment || null }; this._bhChanged(); } })),
          el("label", { style: "display:inline-flex;gap:4px;align-items:center" }, t.comment, el("select", { onchange: (ev) => { w.revert = { ...(rv || { by: [], final_by: [] }), comment: ev.target.value || null }; this._bhChanged(); } },
            el("option", { value: "", selected: !rv?.comment }, "—"), el("option", { value: "optional", selected: rv?.comment === "optional" }, t.optional), el("option", { value: "required", selected: rv?.comment === "required" }, t.required)))),
        el("p", { class: "hint" }, `${cn} · ${t.editHint}`));
    }
    _applyHover() { this._hover = applyHover([...this.shadowRoot.querySelectorAll(".canvas svg, .wfpanel svg")], this._hover); }

    _multSelect(f, onchange, disabled) {
      return el("select", {
        disabled, onchange: (e) => { const m = MULTS.find((x) => x[0] === e.target.value); f.lower = m[1]; f.upper = m[2]; onchange(); },
      }, MULTS.map(([k]) => el("option", { value: k, selected: k === multKey(f.lower, f.upper) }, k)));
    }

    _renderSide() {
      const side = this.shadowRoot.querySelector(".side");
      const t = this.t, mm = this._mm, ro = this.readonly;
      side.replaceChildren();
      const sel = this._sel;
      if (!sel || (sel.kind === "class" && !mm.classes[sel.name]) || (sel.kind === "enum" && !mm.enums[sel.name])) {
        add(side, el("p", { class: "hint" }, t.select), el("p", { class: "hint" }, t.users), ...this._globalBehaviorPanel());
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
        el("div", { class: "row attr hint" }, el("span", {}, t.name), el("span", {}, t.type), el("span", {}, t.mult), el("span", { title: "iD" }, t.id), el("span", { title: t.derivedFlag }, "ƒ"), el("span")),
        ...Object.entries(c.attributes).flatMap(([an, a]) => [el("div", { class: "row attr" },
          el("input", { value: an, disabled: ro, title: a.derived ? `${t.derived} (/${an})` : null, onchange: (ev) => { this._renameFeature(cn, "attributes", an, ev.target.value.trim()); commit(); } }),
          el("select", { disabled: ro, onchange: (ev) => { a.type = ev.target.value; delete a.default; commit(); } }, typeOptions(a.type)),
          this._multSelect(a, commit, ro),
          el("input", { type: "checkbox", checked: !!a.id, disabled: ro, title: "iD (unique key)", onchange: (ev) => { if (ev.target.checked) a.id = true; else delete a.id; commit(); } }),
          ro ? el("span") : el("button", { class: `x${a.derived ? " on" : ""}`, title: t.derivedFlag, style: a.derived ? "color:var(--inv)" : null, onclick: () => { if (a.derived) delete a.derived; else a.derived = true; commit(); } }, "ƒ"),
          ro ? el("span") : el("button", { class: "x", title: t.del, onclick: () => { delete c.attributes[an]; commit(); } }, "×")),
          // a derived attribute: its formula from behavior.yaml, editable when the behaviour is loaded
          a.derived ? (this._bh && !ro
            ? el("input", { class: "formula", value: this._formula(cn, an) ?? "", placeholder: t.inCode, title: t.derivedHint, onchange: (ev) => {
                const v = ev.target.value.trim();
                const ders = (this._bh.derivations ||= {});
                if (v) (ders[cn] ||= {})[an] = { text: v }; else if (ders[cn]) { delete ders[cn][an]; if (!Object.keys(ders[cn]).length) delete ders[cn]; }
                this._bhChanged();
              } })
            : el("div", { class: "formula", title: t.formula }, `= ${this._formula(cn, an) ?? t.inCode}`)) : null]),
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
        ...this._behaviorPanel(cn),
        el("h3", {}, ""),
        ro ? null : el("button", { class: "danger", onclick: () => { if (confirm(`${t.confirmDelete} ${cn}?`)) { this._deleteClass(cn); commit(); } } }, `${t.del} ${cn}`));
    }

    // the behaviour of the selected class in the side panel: the workflow summary (edited in the bottom panel),
    // a button to give the class a workflow or take it away, the events it declares
    _behaviorPanel(cn) {
      const w = this._workflow(cn), t = this.t, bh = this._bh, ro = this.readonly, c = this._mm.classes[cn];
      if (!bh) return w ? [el("h3", {}, t.behavior), el("div", { class: "wf" }, `⟳ ${w.state} · ${this._workflowText(cn).replace(`${t.workflow}: `, "")}`)] : [];
      const lang = this._lang();
      const label = (spec, key) => (typeof spec?.label === "string" ? spec.label : spec?.label?.[lang]) || key;
      const out = [el("h3", {}, t.behavior)];
      if (w) {
        out.push(el("div", { class: "wf" }, `⟳ ${w.state} · ${this._workflowText(cn).replace(`${t.workflow}: `, "")}`));
        out.push(...Object.entries(w.transitions || {}).map(([tn, tr]) => el("div", { class: "wf" },
          label(tr, tn), el("span", { class: "hint" }, `${[].concat(tr.from || []).join(", ")} → ${tr.to}${tr.at != null && tr.at !== "" ? ` · ${tr.at}` : ""}`))));
        if (!ro) out.push(el("button", { class: "danger", onclick: () => { if (confirm(`${t.removeWorkflow} ${cn}?`)) { delete bh.workflows[cn]; this._bhChanged(); } } }, t.removeWorkflow));
      } else if (!ro) {
        // candidates for the state attribute: EString, or an enum whose literals become the states
        const cands = Object.entries(c.attributes).filter(([, a]) => a.type === "EString" || this._mm.enums[a.type]).map(([an]) => an);
        out.push(el("div", { class: "wf" }, el("button", { disabled: !cands.length, title: cands.length ? "" : t.stateAttrHint, onclick: () => {
          const an = cands[0];
          const enumName = c.attributes[an].type;
          const lits = this._mm.enums[enumName]?.literals.map((l) => l.name);
          const states = lits
            ? Object.fromEntries(lits.map((k, i) => [k, { ...(i === 0 ? { initial: true } : {}), ...(i === lits.length - 1 ? { final: true } : {}) }]))
            : { draft: { initial: true }, done: { final: true } };
          (bh.workflows ||= {})[cn] = { state: an, states, transitions: {}, revert: null };
          (bh.entities ||= {})[cn] = snake(cn);
          this._bhChanged();
        } }, `+ ${t.addWorkflow}`), cands.length ? el("span", { class: "hint" }, ` ${t.stateAttr}: ${cands[0]}`) : el("span", { class: "hint" }, ` ${t.stateAttrHint}`)));
      }
      // events the class declares (besides the built-in ones), comma separated
      const evs = bh.events?.[cn] || {};
      out.push(el("div", { class: "field" }, el("label", { title: t.listHint }, t.events),
        el("input", { value: Object.keys(evs).join(", "), disabled: ro, placeholder: t.listHint, onchange: (ev) => {
          const names = this._list(ev.target.value);
          const next = Object.fromEntries(names.map((n) => [n, evs[n] || {}]));
          if (names.length) (bh.events ||= {})[cn] = next; else if (bh.events) delete bh.events[cn];
          this._bhChanged();
        } })));
      return out;
    }
    // roles and reactions (global to the behaviour), when nothing is selected
    _globalBehaviorPanel() {
      const bh = this._bh, t = this.t, ro = this.readonly;
      if (!bh) return [];
      const lang = this._lang();
      const classes = Object.keys(this._mm.classes);
      const roles = bh.roles || {};
      const roleRows = Object.entries(roles).map(([rn, r]) => el("tr", {},
        el("td", {}, el("input", { value: rn, disabled: ro, onchange: (ev) => { const n = ev.target.value.trim(); if (n && n !== rn) { const rebuilt = {}; for (const [k, v] of Object.entries(roles)) rebuilt[k === rn ? n : k] = v; bh.roles = rebuilt; this._bhChanged(); } } })),
        el("td", {}, el("input", { value: typeof r.label === "string" ? r.label : (r.label?.[lang] || ""), disabled: ro, onchange: (ev) => { const v = ev.target.value.trim(); if (v) r.label = typeof r.label === "object" && r.label ? { ...r.label, [lang]: v } : v; else delete r.label; this._bhChanged(); } })),
        el("td", {}, el("select", { disabled: ro, onchange: (ev) => { if (ev.target.value) r.scope = ev.target.value; else r.scope = null; this._bhChanged(); } },
          el("option", { value: "" }, t.none), classes.map((cn) => el("option", { value: cn, selected: r.scope === cn }, cn)))),
        el("td", {}, ro ? null : el("button", { class: "x", title: t.del, onclick: () => { delete roles[rn]; this._bhChanged(); } }, "×"))));
      const reactions = bh.reactions || [];
      const rxRows = reactions.map((r, i) => el("tr", {},
        el("td", {}, el("input", { value: r.name || "", disabled: ro, onchange: (ev) => { r.name = ev.target.value.trim(); this._bhChanged(); } })),
        el("td", {}, el("input", { value: r.event || "", disabled: ro, placeholder: "Class.event", onchange: (ev) => { r.event = ev.target.value.trim(); this._bhChanged(); } })),
        el("td", {}, el("input", { value: exprText(r.when) || "", disabled: ro, onchange: (ev) => { const v = ev.target.value.trim(); r.when = v ? { text: v } : null; this._bhChanged(); } })),
        el("td", {}, el("input", { value: (r.notify || []).join(", "), disabled: ro, title: t.listHint, onchange: (ev) => { r.notify = this._list(ev.target.value); this._bhChanged(); } })),
        el("td", {}, el("input", { value: r.template || "", disabled: ro, onchange: (ev) => { r.template = ev.target.value.trim() || undefined; this._bhChanged(); } })),
        el("td", {}, ro ? null : el("button", { class: "x", title: t.del, onclick: () => { reactions.splice(i, 1); this._bhChanged(); } }, "×"))));
      return [
        el("h3", {}, t.roles),
        el("table", { class: "beh" }, el("tr", {}, el("th", {}, t.name), el("th", {}, t.label), el("th", {}, t.scope), el("th")), ...roleRows),
        ro ? null : el("button", { onclick: () => { (bh.roles ||= {})[this._uniqueName("role", Object.keys(bh.roles || {}))] = {}; this._bhChanged(); } }, `+ ${t.add}`),
        el("h3", {}, t.reactions),
        el("table", { class: "beh" }, el("tr", {}, el("th", {}, t.name), el("th", {}, t.event), el("th", {}, t.when), el("th", {}, t.notify), el("th", {}, t.template), el("th")), ...rxRows),
        ro ? null : el("button", { onclick: () => { const cn = Object.keys(bh.workflows || {})[0] || classes[0] || "Class"; (bh.reactions ||= []).push({ name: this._uniqueName("notify", reactions.map((r) => r.name)), event: `${cn}.transitioned`, when: null, notify: [], template: "" }); this._bhChanged(); } }, `+ ${t.add}`),
        el("p", { class: "hint" }, t.editHint),
      ];
    }
  }

  customElements.define("metamodel-editor", MetamodelEditor);

  /* <workflow-view> — the state diagram of one workflow of behavior.json with the state a record is in: the box
   * of the current state filled with its colour (white text, a ring), the other states dimmed, the transitions
   * leaving it at full strength, the others dimmed.
   * Laid out at the element's width (again when it changes); below the width of the longest state name it scrolls
   * horizontally (core:diagrams). No editing: the record pages of the app use it through
   * src/components/modeler/workflow-view.tsx. */
  class WorkflowView extends HTMLElement {
    constructor() {
      super();
      this._wf = null;             // one workflow of behavior.json ({state, states, transitions, …})
      this._cache = new Map();     // layouts per language and width
      this._last = null;           // "<lang>|<width>|<state>" of the diagram drawn (no redraw when unchanged)
      this._hover = null;
      this._ro = null;
      this.attachShadow({ mode: "open" });
    }
    static get observedAttributes() { return ["lang", "name", "state"]; }
    attributeChangedCallback() { if (this.isConnected) this._render(); }
    connectedCallback() {
      const root = this.shadowRoot;
      if (!root.querySelector(".wfview")) {
        root.append(el("style", {}, viewCss), el("div", { class: "wfview" }));
        root.addEventListener("pointerover", (ev) => {
          const key = ev.target.closest?.("[data-edge]")?.dataset.edge || null;
          if (key !== this._hover) { this._hover = key; this._applyHover(); }
        });
        this.addEventListener("pointerleave", () => { if (this._hover) { this._hover = null; this._applyHover(); } });
      }
      let pending = false;   // the width changed: a new layout (the height follows the diagram, so no loop)
      this._ro = new ResizeObserver(() => {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => { pending = false; this._render(); });
      });
      this._ro.observe(this);
      this._render();
    }
    disconnectedCallback() { this._ro?.disconnect(); this._ro = null; }
    get workflow() { return this._wf ? clone(this._wf) : null; }
    set workflow(w) {
      this._wf = w && typeof w === "object" ? clone(w) : null;
      this._cache.clear();
      this._last = null;
      if (this.isConnected) this._render();
    }
    // the current state as a property too: React sets the property once the element is upgraded, the attribute before
    get state() { return this.getAttribute("state"); }
    set state(v) { if (v == null || v === "") this.removeAttribute("state"); else this.setAttribute("state", String(v)); }
    _applyHover() { this._hover = applyHover([...this.shadowRoot.querySelectorAll("svg")], this._hover); }
    _render() {
      const body = this.shadowRoot.querySelector(".wfview");
      if (!body) return;
      if (!this._wf || !Object.keys(this._wf.states || {}).length) { body.replaceChildren(); this._last = null; return; }
      const lang = (this.getAttribute("lang") || "it").slice(0, 2);
      const width = Math.max(240, Math.floor(this.clientWidth) - 2 * WF_PAD);
      const key = `${lang}|${width}`, state = this.getAttribute("state") || null, drawn = `${key}|${state}`;
      if (drawn === this._last) return;
      let L = this._cache.get(key);
      if (!L) {
        const model = Layout.workflowModel(this._wf, lang);
        L = Layout.workflowLayout(model.states, model.transitions, width, { measure: textMeasure() });
        this._cache.set(key, L);
      }
      const known = state === null || L.boxes.some((b) => b.key === state);   // an unknown value: neutral diagram, flagged
      if (known) this.removeAttribute("data-state-missing"); else this.setAttribute("data-state-missing", state);
      body.replaceChildren(workflowSvg(this.getAttribute("name") || "", L, known ? { current: state, focus: new Set(Layout.workflowFocus(L.edges, state)) } : {}));
      this._last = drawn;
      this._applyHover();
    }
  }
  if (!customElements.get("workflow-view")) customElements.define("workflow-view", WorkflowView);
})();
