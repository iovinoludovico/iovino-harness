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
