// Changes between two metamodels in the editor (Layout.diff): the same lines as `modeler diff` in the CLI.
// node --test plugins/modeler/tests/diff.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const Layout = createRequire(import.meta.url)("../kit/metamodel-editor.js");

// both metamodels through the CLI: the canonical form the editor receives and the lines of ecore.diff
const cli = (old, neu) => JSON.parse(execFileSync("python3", ["-c",
  "import json, sys; sys.path.insert(0, sys.argv[1]); from metamodel import ecore as E; " +
  "a, b = json.loads(sys.argv[2]), json.loads(sys.argv[3]); " +
  "print(json.dumps({'old': E.runtime_json(a), 'new': E.runtime_json(b), 'diff': E.diff(a, b)}))",
  path.join(here, "../scripts"), JSON.stringify(old), JSON.stringify(neu)], { encoding: "utf8" }));

const base = {
  package: "t", language: "it",
  classes: {
    Persona: { attributes: { nome: { type: "EString", lower: 1 }, nascita: "Date" },
               references: { account: { type: "Account", opposite: "persona" } } },
    Account: { attributes: { email: "Email" }, references: { persona: { type: "Persona", opposite: "account" } } },
    Gruppo: { attributes: { nome: "EString" } },
  },
  enums: { Ruolo: ["ADMIN", "STAFF"] },
};

const variants = {
  "multiplicity": (m) => { m.classes.Persona.attributes.nascita = { type: "Date", lower: 1 }; },
  "added and removed features": (m) => { m.classes.Gruppo.attributes.codice = "EString"; delete m.classes.Account.attributes.email; },
  "rename": (m) => { m.classes.Persona.attributes.natoIl = { type: "Date", renamed_from: "nascita" }; delete m.classes.Persona.attributes.nascita; },
  "classes and inheritance": (m) => { m.classes.Soggetto = { abstract: true }; m.classes.Persona.supertypes = ["Soggetto"]; delete m.classes.Gruppo; },
  "enums": (m) => { m.enums.Ruolo = ["ADMIN", "OSPITE"]; m.enums.Stato = ["APERTO"]; },
  "unique groups": (m) => { m.classes.Persona.unique = [["nome", "nascita"]]; },
  "type and default": (m) => { m.classes.Persona.attributes.nome = { type: "Text", lower: 1, default: "x" }; },
  "rules added": (m) => { m.rules = [{ id: "a", text: "t" }]; m.classes.Persona.rules = [{ id: "b", text: "u" }];
                          m.classes.Nuova = { attributes: { x: "EString" }, rules: [{ id: "c", text: "v" }] }; },
};

for (const [name, change] of Object.entries(variants)) {
  test(`same lines as the CLI: ${name}`, () => {
    const neu = structuredClone(base);
    change(neu);
    const { old, new: next, diff } = cli(base, neu);
    assert.ok(diff.length > 0);
    assert.deepEqual(Layout.diff(old, next), diff);
  });
}

test("same lines as the CLI: rules changed and removed", () => {
  const old = structuredClone(base);
  old.rules = [{ id: "a", text: "t" }, { id: "z", text: "w" }];
  old.classes.Persona.rules = [{ id: "b", text: "u" }];
  const neu = structuredClone(old);
  neu.rules = [{ id: "a", text: "t2" }];
  delete neu.classes.Persona.rules;
  const { old: o, new: n, diff } = cli(old, neu);
  assert.deepEqual(diff, ["~ rule a changed", "- rule z", "- Persona: rule b"]);
  assert.deepEqual(Layout.diff(o, n), diff);
});

test("no changes, no lines", () => {
  const { old } = cli(base, base);
  assert.deepEqual(Layout.diff(old, structuredClone(old)), []);
});
