// The editor kit is copied into every app (public/modeler/), where the app's eslint runs on it: an unused
// identifier there becomes a lint warning in every app. node --test plugins/modeler/tests/lint.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(here, "../kit/metamodel-editor.js"), "utf8");

// every UPPER_CASE constant declared with `const`, also in `const A = 1, B = 2;` lists
const declared = [...src.matchAll(/^\s*const\s+([A-Z][A-Z0-9_]*\s*=[^;]*);/gm)]
  .flatMap((m) => [...m[1].matchAll(/(?:^|,)\s*([A-Z][A-Z0-9_]*)\s*=/g)].map((d) => d[1]));

test("every constant of the kit is used (declared once, referenced at least once more)", () => {
  assert.ok(declared.length > 10, `found only ${declared.length} constants`);
  const unused = declared.filter((name) => (src.match(new RegExp(`\\b${name}\\b`, "g")) || []).length < 2);
  assert.deepEqual(unused, []);
});

// the app decides which rules are active: a directive for a rule the app does not run is itself a warning
// ("Unused eslint-disable directive"), so the kit silences nothing and fixes the code instead. The two TSX files
// keep the one exception their `declare module "react"` needs (@typescript-eslint/no-namespace fires in every Next app).
test("the kit silences no lint rule (no eslint-disable), except no-namespace for the JSX declarations", () => {
  assert.deepEqual([...src.matchAll(/eslint-disable[^\n]*/g)].map((m) => m[0]), []);
  for (const file of ["workflow-view.tsx", "metamodel-modeler.tsx", "behavior-view.tsx", "view-as.tsx", "notification-templates.tsx"]) {
    const tsx = readFileSync(path.join(here, "../kit/next", file), "utf8");
    const directives = [...tsx.matchAll(/eslint-disable[^\n]*/g)].map((m) => m[0].trim());
    assert.ok(directives.every((d) => d === "eslint-disable-next-line @typescript-eslint/no-namespace"), `${file}: ${directives.join(" | ")}`);
  }
});
