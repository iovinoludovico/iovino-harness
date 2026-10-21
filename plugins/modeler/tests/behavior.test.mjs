// The behaviour as the editor proposes it (Layout.behaviorSource) and the lines of its changes (Layout.behaviorDiff),
// the same as the CLI's behavior.from_editor / behavior.diff. node --test plugins/modeler/tests/behavior.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const Layout = createRequire(import.meta.url)("../kit/metamodel-editor.js");

const py = (code, ...args) => JSON.parse(execFileSync("python3", ["-c",
  "import json, sys; sys.path.insert(0, sys.argv[1]); from metamodel import behavior as B, ecore as E; " + code,
  path.join(here, "../scripts"), ...args], { encoding: "utf8" }));
const runtime = () => py("print(json.dumps(B.runtime_json(B.load(sys.argv[3]), E.load(sys.argv[2]))))",
  path.join(here, "fixtures/invitations.ecore.yaml"), path.join(here, "fixtures/invitations.behavior.yaml"));

test("behaviorSource: expressions as text, runtime keys gone, accepted by the CLI as the same model", () => {
  const bh = runtime();
  const src = Layout.behaviorSource(bh);
  assert.ok(!("entities" in src) && !("uses" in src));
  assert.equal(src.derivations.Invitation.fundsTotal, "invitationFunds.amount.sum()");
  assert.equal(src.workflows.Invitation.transitions.submit.guard, "dataComplete");
  assert.equal(src.workflows.Invitation.transitions.approve.when, "not agencyBookingRequired");
  assert.equal(src.reactions[0].when, "transition in [submit, resubmit]");
  assert.equal(Layout.behaviorSource(null), null);
  // the CLI reads it back (from_editor) with no error against the metamodel and no difference from the file
  const check = py("doc = json.loads(sys.argv[3]); raw = B.from_editor(doc); meta = E.load(sys.argv[2]); "
    + "print(json.dumps({'errors': B.validate(raw, meta).errors, 'diff': B.diff(B.load(sys.argv[4]), raw)}))",
    path.join(here, "fixtures/invitations.ecore.yaml"), JSON.stringify(src), path.join(here, "fixtures/invitations.behavior.yaml"));
  assert.deepEqual(check, { errors: [], diff: [] });
});

test("behaviorDiff: the lines a reviewer reads, as the CLI prints them", () => {
  const a = runtime();
  const b = structuredClone(a);
  const w = b.workflows.Invitation;
  w.states.paused = { label: { it: "Sospeso" }, owner: ["office"] };
  w.states.payment.requires = ["hours"];
  w.states.rejected.model = { flatAmount: { lower: null, readonly: true, hidden: false, in: null }, notes: { lower: null, readonly: true, hidden: true, in: null } };
  w.transitions.pause = { from: ["in_management"], to: "paused", by: ["office"], when: null, guard: null, comment: null, at: null, emits: [] };
  w.transitions.submit.guard = { text: "dataComplete and hours > 0" };
  b.reactions.splice(0, 1);
  b.roles.boss = {};
  b.derivations.Invitation.fundsTotal = { text: "invitationFunds.amount.sum() + 1" };
  assert.deepEqual(Layout.behaviorDiff(a, b), [
    "+ role boss", "~ derivation Invitation.fundsTotal = invitationFunds.amount.sum() + 1",
    "~ state Invitation.rejected: model", "~ state Invitation.payment: requires", "+ state Invitation.paused", "~ transition Invitation.submit: guard",
    "+ transition Invitation.pause: in_management -> paused", "- reaction notify_submitted",
  ]);
  // the proposal writes `model` as the notation does: only what the state changes
  assert.deepEqual(Layout.behaviorSource(b).workflows.Invitation.states.rejected.model, { flatAmount: { readonly: true }, notes: { hidden: true } });
  assert.ok(!("model" in Layout.behaviorSource(b).workflows.Invitation.states.draft));
  assert.deepEqual(Layout.behaviorDiff(a, a), []);
  assert.deepEqual(Layout.behaviorDiff(a, structuredClone(a)), []);
  assert.ok(Layout.behaviorDiff(null, b).includes("+ workflow Invitation on state: 12 states, 16 transitions"));
  const cli = py("a, b = json.loads(sys.argv[2]), json.loads(sys.argv[3]); print(json.dumps(B.diff(B.from_editor(a), B.from_editor(b))))",
    JSON.stringify(Layout.behaviorSource(a)), JSON.stringify(Layout.behaviorSource(b)));
  assert.deepEqual(Layout.behaviorDiff(a, b), cli);
});
