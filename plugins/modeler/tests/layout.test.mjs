// Layout of the metamodel editor (kit/metamodel-editor.js): node --test plugins/modeler/tests/
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const Layout = createRequire(import.meta.url)("../kit/metamodel-editor.js");

// the fixture in the canonical form the editor receives (src/lib/modeler/metamodel.json in an app)
const fixture = (name) => JSON.parse(execFileSync("python3", ["-c",
  "import json, sys; sys.path.insert(0, sys.argv[1]); from metamodel import ecore as E; " +
  "print(json.dumps(E.runtime_json(E.load(sys.argv[2]))))",
  path.join(here, "../scripts"), path.join(here, "fixtures", name)], { encoding: "utf8" }));

// a larger model: one class referenced from many others, a chain, inheritance and enums
// (sources: how many classes reference Evento; from 4 on the same side the connectors share a bus)
const hub = (sources = 4) => {
  const classes = { Evento: { attributes: { titolo: { type: "EString", lower: 1 }, stato: { type: "Stato" } } } };
  ["Ordine", "Fattura", "Cliente", "Fornitore", "Prodotto", "Magazzino", "Spedizione", "Reso"].forEach((n, i) => {
    classes[n] = { attributes: { codice: { type: "EString", lower: 1 }, note: { type: "Text" } },
      references: i < sources ? { evento: { type: "Evento" } } : {} };
  });
  classes.Ordine.references.righe = { type: "Riga", upper: -1, containment: true, opposite: "ordine" };
  classes.Riga = { attributes: { quantita: { type: "EInt" } }, references: { ordine: { type: "Ordine", lower: 1, opposite: "righe" },
    prodotto: { type: "Prodotto", lower: 1 } } };
  classes.Fattura.references.ordine = { type: "Ordine" };
  classes.Cliente.references.ordini = { type: "Ordine", upper: -1 };
  classes.Soggetto = { abstract: true, attributes: { nome: { type: "EString" } } };
  classes.Cliente.supertypes = ["Soggetto"];
  classes.Fornitore.supertypes = ["Soggetto"];
  return { package: "hub", classes, enums: { Stato: ["APERTO", "CHIUSO", "ANNULLATO"] } };
};

const laidOut = (raw, width, height) => {
  const mm = Layout.normalize(raw);
  const size = (n) => Layout.boxSize(mm, n);
  Object.assign(mm.diagram, Layout.autoLayout(mm, size, { force: true, width, height }));
  return { mm, ...Layout.routeEdges(mm, size) };
};

const segs = (pts) => pts.slice(1).map((q, i) => [pts[i], q]);
// every line of a connector: the polyline, or for a bus the stub, the trunk and the branches (with their own source)
const runs = (e) => [{ pts: e.pts, own: [e.a, e.b] }, ...(e.trunk ? [{ pts: e.trunk, own: [] }, ...e.branches.map((b) => ({ pts: b.pts, own: [b.a] }))] : [])];
const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
const inside = ([p, q], R, m) => Math.min(p.x, q.x) < R.x + R.w - m && Math.max(p.x, q.x) > R.x + m
  && Math.min(p.y, q.y) < R.y + R.h - m && Math.max(p.y, q.y) > R.y + m;
const collinear = ([p, q], [r, s]) => {
  const ov = (a0, a1, b0, b1) => Math.min(Math.max(a0, a1), Math.max(b0, b1)) - Math.max(Math.min(a0, a1), Math.min(b0, b1));
  if (p.y === q.y && r.y === s.y && Math.abs(p.y - r.y) < 2) return ov(p.x, q.x, r.x, s.x) > 2;
  if (p.x === q.x && r.x === s.x && Math.abs(p.x - r.x) < 2) return ov(p.y, q.y, r.y, s.y) > 2;
  return false;
};

for (const [name, raw] of [["anagrafica", () => fixture("anagrafica.ecore.yaml")], ["hub", hub], ["hub8", () => hub(8)]]) {
  // canvas sizes from a phone to a wide screen, as the editor measures them (window minus bar and margins)
  const sizes = [];
  for (let w = 400; w <= 1900; w += 125) for (const h of [480, 630, 900]) sizes.push([w, h]);
  for (const [w, h] of sizes) {
    test(`${name} at ${w}x${h}`, () => {
      const { mm, edges, boxes } = laidOut(raw(), w, h);
      const names = Object.keys(boxes);
      assert.equal(names.length, Object.keys(mm.classes).length + Object.keys(mm.enums).length, "every box is placed");
      assert.ok(edges.length > 0);

      for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++) {
        assert.ok(!overlap(boxes[names[i]], boxes[names[j]]), `boxes ${names[i]} and ${names[j]} overlap`);
      }
      const lines = edges.flatMap((e) => runs(e).map((r) => ({ ...r, key: e.key })));
      for (let i = 0; i < lines.length; i++) for (let j = i + 1; j < lines.length; j++) {
        for (const s of segs(lines[i].pts)) for (const t of segs(lines[j].pts)) {
          assert.ok(!collinear(s, t), `connectors ${lines[i].key} and ${lines[j].key} share a run`);
        }
      }
      for (const l of lines) {
        for (const [n, R] of Object.entries(boxes)) {
          const own = l.own.includes(n);
          for (const s of segs(l.pts)) assert.ok(!inside(s, R, own ? 2 : -1), `connector ${l.key} crosses ${n}`);
        }
      }
      const labels = edges.flatMap((e) => e.labels.map((l) => ({ ...l, key: e.key })));
      for (const l of labels) {
        for (const [n, R] of Object.entries(boxes)) assert.ok(!overlap(l, R), `label "${l.text}" covers ${n}`);
      }
      for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
        assert.ok(!overlap(labels[i], labels[j]), `labels "${labels[i].text}" and "${labels[j].text}" overlap`);
      }
    });
  }
}

test("incoming ports are staggered from the outgoing ones", () => {
  const { edges } = laidOut(hub(), 1280, 720);
  const ends = edges.flatMap((e) => [e.pts[0], e.pts[e.pts.length - 1]]).map((p) => `${p.x},${p.y}`);
  assert.equal(new Set(ends).size, ends.length, "two connectors share an attachment point");
});

test("many classes referencing the same one (hub(8)) share a bus: one trunk, one arrow, one label", () => {
  for (const [w, h] of [[400, 480], [900, 630], [1280, 720], [1900, 900]]) {
    const { edges } = laidOut(hub(8), w, h);
    const into = edges.filter((e) => e.b === "Evento" && e.cls === "edge");
    const buses = into.filter((e) => e.trunk);
    assert.ok(buses.length >= 1, `${w}x${h}: no bus into Evento`);
    assert.equal(into.length, 1, `${w}x${h}: ${into.length} arrows into Evento`);   // one arrow: every reference joins the bus
    assert.equal(into.reduce((n, e) => n + (e.branches?.length ?? 1), 0), 8, "every reference is drawn");
    for (const bus of buses) {
      assert.ok(bus.branches.length >= 4, `${w}x${h}: a bus of ${bus.branches.length}`);
      assert.equal(bus.end, "url(#arrow)");
      assert.equal(bus.labels.length, 1, "the references read the same: one label");
      assert.equal(bus.pts.length, 2, "the stub from the trunk to the port");
      const vertical = bus.trunk[0].x === bus.trunk[1].x;
      for (const b of bus.branches) {   // every branch ends on the trunk
        const end = b.pts[b.pts.length - 1];
        assert.ok(vertical ? end.x === bus.trunk[0].x : end.y === bus.trunk[0].y, `branch ${b.key} misses the trunk`);
      }
    }
  }
  // references that read differently: a label at each source
  const mixed = hub(8);
  mixed.classes.Ordine.references.evento = { type: "Evento", lower: 1 };
  const { edges } = laidOut(mixed, 1280, 720);
  const bus = edges.find((e) => e.trunk && e.branches.some((b) => b.a === "Ordine"));
  if (bus) assert.equal(bus.labels.length, bus.branches.length);
});

// Where "+ Classe" / "+ Enum" put the new box (Layout.freeSpot): never over an existing box, with a margin
test("freeSpot avoids the existing boxes, stays in view, is deterministic", () => {
  const occupied = [{ x: 300, y: 100, w: 320, h: 180 }, { x: 350, y: 300, w: 200, h: 120 }, { x: 0, y: 0, w: 160, h: 90 }];
  const size = { w: 210, h: 80 };
  const view = { x: 0, y: 0, w: 1000, h: 600 };
  const start = { x: 395, y: 200 };                                  // inside the big box: the old code used it
  const p = Layout.freeSpot(occupied, size, start, view);
  for (const o of occupied) assert.ok(!overlap({ x: p.x - 24, y: p.y - 24, w: size.w + 48, h: size.h + 48 }, o), `over ${JSON.stringify(o)}`);
  assert.ok(p.x >= 0 && p.y >= 0 && p.x + size.w <= view.w && p.y + size.h <= view.h, "inside the view");
  assert.deepEqual(Layout.freeSpot(occupied, size, start, view), p);
  assert.deepEqual(Layout.freeSpot([], size, { x: 120, y: 80 }, view), { x: 120, y: 80 });   // empty diagram
  const full = Layout.freeSpot([{ x: 0, y: 0, w: 400, h: 300 }], size, { x: 95, y: 100 }, { x: 0, y: 0, w: 400, h: 300 });
  assert.ok(!overlap({ ...full, ...size }, { x: 0, y: 0, w: 400, h: 300 }), "leaves a full view");
});

for (const [name, raw] of [["anagrafica", () => fixture("anagrafica.ecore.yaml")], ["hub", () => hub(8)]]) {
  test(`freeSpot on the laid out ${name}, with the real box sizes`, () => {
    for (const [w, h] of [[400, 480], [900, 630], [1900, 900]]) {
      const { mm, boxes } = laidOut(raw(), w, h);
      mm.classes.NuovaClasse = { abstract: false, supertypes: [], attributes: { name: { type: "EString", lower: 1, upper: 1 } }, references: {} };
      const size = Layout.boxSize(mm, "NuovaClasse");
      const occupied = Object.entries(boxes).map(([n, b]) => ({ x: mm.diagram[n].x, y: mm.diagram[n].y, w: b.w, h: b.h }));
      for (const start of [{ x: w / 2 - size.w / 2, y: h / 3 }, { x: 0, y: 0 }, occupied[0]]) {
        const p = Layout.freeSpot(occupied, size, start, { x: 0, y: 0, w, h });
        for (const o of occupied) assert.ok(!overlap({ ...p, ...size }, o), `${name} ${w}x${h}: new box over one at ${o.x},${o.y}`);
      }
    }
  });
}

// Behaviour next to the structure: `/` marks a derived attribute (flag of the metamodel), `⟳` the state attribute
// of the workflow (behavior.json: `workflows.<Class>.state`), in the rows the box is sized on
const behaviorFixture = (meta, beh) => JSON.parse(execFileSync("python3", ["-c",
  "import json, sys; sys.path.insert(0, sys.argv[1]); from metamodel import behavior as B, ecore as E; " +
  "print(json.dumps(B.runtime_json(B.load(sys.argv[3]), E.load(sys.argv[2]))))",
  path.join(here, "../scripts"), path.join(here, "fixtures", meta), path.join(here, "fixtures", beh)], { encoding: "utf8" }));

test("derived attributes and the workflow state are marked in the rows of a class", () => {
  const mm = Layout.normalize(fixture("invitations.ecore.yaml"));
  const bh = behaviorFixture("invitations.ecore.yaml", "invitations.behavior.yaml");
  const state = bh.workflows.Invitation.state;
  const rows = Layout.rowItems(mm.classes.Invitation, true, "more", state);
  const derived = rows.filter((r) => r.derived);
  assert.ok(derived.length >= 5, "the fixture has derived attributes");
  for (const r of derived) {
    assert.ok(r.text.includes(`/${r.attr}:`), r.text);
    assert.ok(bh.derivations.Invitation[r.attr]?.text, `formula of ${r.attr} in behavior.json`);
  }
  const st = rows.find((r) => r.state);
  assert.equal(st.attr, state);
  assert.ok(st.text.startsWith("⟳ "), st.text);
  assert.ok(!rows.some((r) => !r.derived && r.text.includes("/")), "only derived attributes carry the slash");
  // the texts of the same items size the box; the marks change the width a little, never the height
  assert.deepEqual(Layout.rowsOf(mm.classes.Invitation, true, "more", state), rows.map((r) => r.text));
  const marked = Layout.boxSize(mm, "Invitation", { allAttrs: true, state });
  const plain = Layout.boxSize(mm, "Invitation", { allAttrs: true });
  assert.equal(marked.h, plain.h);
  assert.ok(marked.w >= plain.w && marked.w <= 380);
  // without a behaviour nothing is marked as state
  assert.ok(!Layout.rowItems(mm.classes.Invitation, true).some((r) => r.state));
});
