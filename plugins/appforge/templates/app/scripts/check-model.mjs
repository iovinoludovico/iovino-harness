// Keeps the application aligned with its model (run in CI: `npm run check:model`).
// Fails when the model (app.yaml, domain.ecore.yaml) changed after the last generation,
// or when a generated file or migration was edited by hand. Fix: `/appforge:generate`.
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";

const read = (p) => readFileSync(p, "utf8").replace(/\r\n/g, "\n");
const sha = (text) => createHash("sha256").update(text, "utf8").digest("hex");
const problems = [];

if (!existsSync(".appforge/lock.json")) {
  console.error("check:model: .appforge/lock.json missing: the app was never generated (appforge generate)");
  process.exit(1);
}
const lock = JSON.parse(read(".appforge/lock.json"));
const model = read("app.yaml") + (existsSync("domain.ecore.yaml") ? read("domain.ecore.yaml") : "");
if (lock.model_sha && sha(model) !== lock.model_sha) {
  problems.push("the model (app.yaml / domain.ecore.yaml) changed after the last generation: run /appforge:generate");
}
for (const [path, hash] of Object.entries({ ...(lock.generated ?? {}), ...(lock.migrations ?? {}) })) {
  if (!existsSync(path)) problems.push(`generated file missing: ${path}`);
  else if (sha(read(path)) !== hash) problems.push(`generated file edited by hand: ${path} (change the model and regenerate)`);
}
for (const p of problems) console.error(`✗ ${p}`);
if (problems.length) process.exit(1);
console.log(`✓ model and application aligned (evolution #${lock.evolution ?? 0}, generator ${lock.generator_version})`);
