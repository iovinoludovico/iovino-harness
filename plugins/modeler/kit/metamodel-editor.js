/*
 * <metamodel-editor> — framework-free editor of the domain metamodel of this application (Ecore notation).
 *
 * Installed by the modeler plugin (`modeler install`) and owned by the app: the admin page
 * (src/components/modeler/metamodel-modeler.tsx) renders it; a save becomes a change proposal.
 *
 *   const el = document.querySelector("metamodel-editor");
 *   el.metamodel = json;            // canonical form: src/lib/modeler/metamodel.json (`npm run model:sync`)
 *   el.readonly = false;
 *   el.addEventListener("change", (e) => e.detail.metamodel);
 *   el.addEventListener("save", (e) => { e.detail.metamodel; e.detail.note; });
 *
 * Attributes: lang="it|en", save-label="…", readonly.
 * The diagram positions are kept in metamodel.diagram ({Class: {x, y}}).
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

  const Layout = (() => {
    const rowsOf = (c, allAttrs = false, more = "more") => {
      // attribute lines of a class box: all of them, or the first ones plus "+N more"
      const lines = Object.entries(c.attributes).map(([an, a]) => {
        const m = a.lower === 0 && a.upper === 1 ? "" : ` [${multText(a.lower, a.upper)}]`;
        return `${a.id ? "🔑 " : ""}${an}: ${a.type}${m}`;
      });
      // references to the application users have no box to point to: listed in the class, dimmed
      for (const [rn, r] of Object.entries(c.references)) {
        if (r.type === "User") lines.push(`↗ ${rn}: User${r.lower === 0 && r.upper === 1 ? "" : ` [${multText(r.lower, r.upper)}]`}`);
      }
      if (allAttrs || lines.length <= MAX_ROWS) return lines;
      return [...lines.slice(0, MAX_ROWS - 1), `… +${lines.length - MAX_ROWS + 1} ${more}`];
    };

    const boxSize = (mm, name, opts = {}) => {
      const c = mm.classes[name];
      const width = (texts, min) => Math.round(Math.max(min, Math.min(380, Math.max(...texts.map((x) => x.length)) * CHAR_W + 24)));
      if (c) {
        const rows = rowsOf(c, opts.allAttrs, opts.more);
        return { w: width([name, ...rows], 160), h: HEAD_H + Math.max(1, rows.length) * ROW_H + PAD };
      }
      const e = mm.enums[name];
      return { w: width([name, ...e.literals.map((l) => l.name)], 120), h: HEAD_H + 12 + Math.max(1, e.literals.length) * ROW_H + PAD };
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
        const width = colW.reduce((a, b) => a + b, 0) + GAP_X * (cols - 1);
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
      const ox = used.length ? Math.max(...used.map(([n, p]) => p.x + size(n).w)) + GAP_X : 0;
      const colX = [];
      best.colW.reduce((x, w, i) => { colX[i] = x; return x + w + GAP_X; }, ox);
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

    const route = (p1, sa, p2, sb, lane, self, detour = 0) => {
      const h1 = horizontal(sa), h2 = horizontal(sb);
      const step = 28 + detour * 10;   // connectors going around the boxes get a lane each
      if (self) { const x = p1.x + step; return [p1, { x, y: p1.y }, { x, y: p2.y }, p2]; }
      if (h1 && h2) {
        const facing = out[sa][0] !== out[sb][0] && (out[sa][0] > 0 ? p2.x > p1.x : p2.x < p1.x);
        const x = facing ? (p1.x + p2.x) / 2 + lane : (out[sa][0] > 0 ? Math.max(p1.x, p2.x) + step : Math.min(p1.x, p2.x) - step);
        return Math.abs(p1.y - p2.y) < 1 && facing ? [p1, p2] : [p1, { x, y: p1.y }, { x, y: p2.y }, p2];
      }
      if (!h1 && !h2) {
        const facing = out[sa][1] !== out[sb][1] && (out[sa][1] > 0 ? p2.y > p1.y : p2.y < p1.y);
        const y = facing ? (p1.y + p2.y) / 2 + lane : (out[sa][1] > 0 ? Math.max(p1.y, p2.y) + step : Math.min(p1.y, p2.y) - step);
        return Math.abs(p1.x - p2.x) < 1 && facing ? [p1, p2] : [p1, { x: p1.x, y }, { x: p2.x, y }, p2];
      }
      // one horizontal and one vertical side: an L, or (detour) out of both boxes and around, when the L crosses one
      if (!detour) return h1 ? [p1, { x: p2.x, y: p1.y }, p2] : [p1, { x: p1.x, y: p2.y }, p2];
      const a = { x: p1.x + out[sa][0] * step, y: p1.y + out[sa][1] * step };
      const b = { x: p2.x + out[sb][0] * step, y: p2.y + out[sb][1] * step };
      return h1 ? [p1, a, { x: a.x, y: b.y }, b, p2] : [p1, a, { x: b.x, y: a.y }, b, p2];
    };

    const edgesOf = (mm) => {
      // EMF / Ecore Tools notation: reference = open arrow at the target; containment = filled diamond at the
      // container; a pair of opposite references = one connector with both ends; inheritance = hollow triangle
      // at the supertype.
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
            labelB: `${rn} ${multText(r.lower, r.upper)}`,
            labelA: o ? `${r.opposite} ${multText(o.lower, o.upper)}` : null,
          });
        }
      }
      return list;
    };

    const routeEdges = (mm, size) => {
      // Connectors as orthogonal polylines, with the labels of their ends: { edges: [{key, a, b, cls, start, end,
      // pts, labels: [{text, x, y, w, h}]}], boxes: {name: rect}, ext } (ext: the extent of lines and labels).
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
      const list = edgesOf(mm);
      for (const e of list) {   // the sides the connector leaves and enters
        const A = rects[e.a], B = rects[e.b];
        e.A = A; e.B = B;
        if (e.a === e.b) { e.sa = "right"; e.sb = "right"; continue; }
        let best = Infinity;
        for (const sa of SIDES) for (const sb of SIDES) {
          const pts = route(mid(A, sa), sa, mid(B, sb), sb, 0, false);
          const c = crosses(pts, [e.a, e.b]) * 100000 + length(pts) + (pts.length - 2) * 40;
          if (c < best - 1e-6) { best = c; e.sa = sa; e.sb = sb; }
        }
      }
      // ports: the connectors on the same side of a box are spread along it, ordered by where they go;
      // the incoming ends are staggered by a few px from the outgoing ones
      const ports = {};
      list.forEach((e, i) => {
        for (const [end, n, side, other] of [["a", e.a, e.sa, e.B], ["b", e.b, e.sb, e.A]]) {
          (ports[`${n}|${side}`] ||= []).push({ i, end, key: horizontal(side) ? other.y + other.h / 2 : other.x + other.w / 2 });
        }
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
          list[it.i][it.end === "a" ? "pa" : "pb"] = pt;
          list[it.i][it.end === "a" ? "ja" : "jb"] = j;   // position on the side: labels alternate
        });
      }
      // each connector takes the lane (offset of its middle run, distance of a detour) that crosses no box and
      // shares no run with the connectors already routed; its ports may slide a few px along their sides, so that
      // two connectors leaving boxes of the same row at the same height do not run on the same line
      const slide = (pt, side, d) => (horizontal(side) ? { x: pt.x, y: pt.y + d } : { x: pt.x + d, y: pt.y });
      const routed = [];
      for (const e of list) {
        let best = null;
        for (const jog of [0, 6, -6]) for (const lane of LANES) for (let detour = 0; detour < 5; detour++) {
          const pts = route(slide(e.pa, e.sa, jog), e.sa, slide(e.pb, e.sb, jog), e.sb, lane, e.a === e.b, detour);
          const segs = segments(pts);
          const shared = routed.reduce((n, o) => n + segs.filter((s) => o.segs.some((t) => collinear(s, t))).length, 0);
          const c = crosses(pts, [e.a, e.b]) * 100000 + shared * 10000 + length(pts) + (pts.length - 2) * 40
            + Math.abs(lane) + detour * 6 + Math.abs(jog) * 2;
          if (!best || c < best.c - 1e-6) best = { c, pts, segs };
        }
        e.pts = best.pts;
        routed.push({ segs: best.segs });
      }
      // labels: at the ends, in the first of several candidate places that covers no box, label or line
      const allSegs = list.flatMap((e) => segments(e.pts));
      const placed = [];
      const ext = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
      const grow = (x0, y0, x1, y1) => { ext.x0 = Math.min(ext.x0, x0); ext.y0 = Math.min(ext.y0, y0); ext.x1 = Math.max(ext.x1, x1); ext.y1 = Math.max(ext.y1, y1); };
      const label = (pt, side, text, below) => {
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
        e.labels = [];
        const pa = e.pts[0], pb = e.pts[e.pts.length - 1];   // the ports, after sliding
        if (e.labelB) e.labels.push(label(pb, e.sb, e.labelB, e.labelA ? false : e.jb % 2 === 0));   // first port: label on its left
        if (e.labelA) e.labels.push(label(pa, e.sa, e.labelA, e.ja % 2 === 0));
        for (const q of e.pts) grow(q.x - 14, q.y - 14, q.x + 14, q.y + 14);
      }
      const edges = list.map(({ key, a, b, cls, start, end, pts, labels }) => ({ key, a, b, cls, start, end, pts, labels }));
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

    return { rowsOf, boxSize, normalize, autoLayout, routeEdges, edgesOf, freeSpot };
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

  if (typeof module === "object" && module.exports) module.exports = Layout;
  if (typeof customElements === "undefined" || customElements.get("metamodel-editor")) return;

  const T = {
    it: {
      addClass: "Classe", addEnum: "Enum", layout: "Riordina", fit: "Adatta", save: "Salva", note: "Nota sulla modifica",
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
    },
    en: {
      addClass: "Class", addEnum: "Enum", layout: "Layout", fit: "Fit", save: "Save", note: "Change note",
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
    },
  };

  const css = `
:host { --bg:#fff; --fg:#1f2937; --muted:#6b7280; --line:#d1d5db; --panel:#f9fafb; --accent:#2563eb; --head:#eef2ff;
  --enum:#fef3c7; --err:#dc2626; --ok:#16a34a; display:block; font:13px/1.4 system-ui,sans-serif; color:var(--fg); }
@media (prefers-color-scheme: dark) { :host { --bg:#111827; --fg:#e5e7eb; --muted:#9ca3af; --line:#374151;
  --panel:#1f2937; --head:#1e293b; --enum:#3b2f12; --accent:#60a5fa; } }
:host([theme="light"]) { --bg:#fff; --fg:#1f2937; --muted:#6b7280; --line:#d1d5db; --panel:#f9fafb; --head:#eef2ff; --enum:#fef3c7; --accent:#2563eb; }
:host(:fullscreen) { height:100vh; background:var(--bg); }
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
.main.nopanel { grid-template-columns:1fr; }
.main.nopanel .side { display:none; }
button.on { border-color:var(--accent); color:var(--accent); }
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
.ehit { stroke:transparent; stroke-width:10; fill:none; pointer-events:stroke; cursor:pointer; }
.elabel { cursor:pointer; }
svg.hover .edge:not(.hi), svg.hover .elabel:not(.hi) { opacity:.15; }
.edge.hi { stroke:var(--accent); stroke-width:2.4; }
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
      this.attachShadow({ mode: "open" });
    }

    static get observedAttributes() { return ["lang", "readonly", "save-label"]; }
    attributeChangedCallback() { if (this.isConnected) this._render(); }
    connectedCallback() { this._render(); }

    get t() { return T[(this.getAttribute("lang") || "it").slice(0, 2)] || T.it; }
    get readonly() { return this.hasAttribute("readonly"); }
    set readonly(v) { if (v) this.setAttribute("readonly", ""); else this.removeAttribute("readonly"); }

    set metamodel(mm) {
      const m = Layout.normalize(mm);
      this._mm = m;
      this._orig = clone(m);
      this._sel = null;
      this._panel = false;
      this._autoFit = true;
      this._autoLayout(false);
      this._render();
      requestAnimationFrame(() => this._fit());
    }
    get metamodel() { return clone(this._mm); }
    // the changes from the metamodel the editor was opened with (the running one) to `mm`, as `modeler diff`
    changesTo(mm) { return Layout.diff(this._orig || {}, mm); }
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
      return [...new Set(out)];
    }

    /* ------------------------------------------------------------------ layout */
    _rows(c) { return Layout.rowsOf(c, this._allAttrs, this.t.more); }
    _boxSize(name) { return Layout.boxSize(this._mm, name, { allAttrs: this._allAttrs, more: this.t.more }); }
    _autoLayout(force) {
      const r = this.shadowRoot.querySelector(".canvas")?.getBoundingClientRect();
      const pos = Layout.autoLayout(this._mm, (n) => this._boxSize(n),
        { force, width: r ? r.width - 2 * MARGIN : 0, height: r ? r.height - 2 * MARGIN : 0 });
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
      const k = Math.min(K_MAX, Math.max(K_MIN, Math.min((r.width - 2 * MARGIN) / (x1 - x0), (r.height - 2 * MARGIN) / (y1 - y0))));
      this._view = { k, x: (r.width - (x1 - x0) * k) / 2 - x0 * k, y: (r.height - (y1 - y0) * k) / 2 - y0 * k };
      this._renderDiagram();
    }
    _refit() { this._autoFit = true; this._fit(); }
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
          el("div", { class: "main" }, el("div", { class: "canvas" }), el("div", { class: "side" })));
        root.append(wrap);
        const canvas = root.querySelector(".canvas");
        this._bindCanvas(canvas);
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
          onclick: () => this.dispatchEvent(new CustomEvent("save", { detail: { metamodel: this.metamodel, note: this._note || "" } })),
        }, this.getAttribute("save-label") || t.save),
        VERSION.startsWith("__") ? null : el("span", { class: "hint", title: `${t.modeler} ${VERSION}` }, `v${VERSION}`),
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
      canvas.addEventListener("wheel", (ev) => {
        ev.preventDefault();
        this._autoFit = false;
        const r = canvas.getBoundingClientRect();
        const k = Math.min(K_MAX, Math.max(K_MIN, this._view.k * (ev.deltaY < 0 ? 1.1 : 0.9)));
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
      const routed = Layout.routeEdges(mm, (n) => this._boxSize(n));
      for (const e of routed.edges) {
        const d = rounded(e.pts);
        const attrs = { d, class: e.cls, "data-edge": e.key };
        if (e.start) attrs["marker-start"] = e.start;
        if (e.end) attrs["marker-end"] = e.end;
        edges.append(svg("path", attrs));
        edges.append(svg("path", { d, class: "ehit", "data-edge": e.key }));   // wider, invisible: easier to hover
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
        const hh = HEAD_H;
        const b = svg("g", { class: `box${sel ? " sel" : ""}`, "data-name": cn, transform: `translate(${p.x},${p.y})` },
          svg("rect", { class: "body", width: s.w, height: s.h, rx: 6 }),
          svg("rect", { class: "head", width: s.w - 2, x: 1, y: 1, height: hh - 2, rx: 5 }),
          svg("text", { x: s.w / 2, y: 21, "text-anchor": "middle", class: `title${c.abstract ? " abstract" : ""}` }, cn));
        let y = hh + 14;
        const rows = this._rows(c);
        if (!rows.length) b.append(svg("text", { x: 8, y, class: "muted" }, "—"));
        rows.forEach((line, i) => {
          const muted = line.startsWith("↗ ") || (!this._allAttrs && i === MAX_ROWS - 1 && line.startsWith("…"));
          b.append(svg("text", { x: 8, y, class: muted ? "muted" : null }, line));
          y += ROW_H;
        });
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
    _applyHover() {
      const root = this.shadowRoot.querySelector(".canvas svg");
      if (!root) return;
      const known = this._hover && [...root.querySelectorAll("[data-edge]")].some((n) => n.dataset.edge === this._hover);
      if (!known) this._hover = null;
      root.classList.toggle("hover", !!this._hover);
      for (const n of root.querySelectorAll("[data-edge]")) n.classList.toggle("hi", n.dataset.edge === this._hover);
    }

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
        el("h3", {}, ""),
        ro ? null : el("button", { class: "danger", onclick: () => { if (confirm(`${t.confirmDelete} ${cn}?`)) { this._deleteClass(cn); commit(); } } }, `${t.del} ${cn}`));
    }
  }

  customElements.define("metamodel-editor", MetamodelEditor);
})();
