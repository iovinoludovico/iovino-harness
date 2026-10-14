import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { MODEL } from "@/lib/model";
import { EVENT_TYPES } from "@/lib/events/catalog";

const messages = JSON.parse(readFileSync(path.resolve(import.meta.dirname, `../messages/${MODEL.app.locales[0]}.json`), "utf8"));

// Guards the generated artefacts against drift (they are rewritten together by /appforge:generate).
describe("generated model", () => {
  it("every entity, field and state has a label", () => {
    for (const e of Object.values(MODEL.entities)) {
      const m = messages.model.entities[e.key];
      expect(m, e.key).toBeDefined();
      for (const f of e.fields) expect(m.fields[f.key], `${e.key}.${f.key}`).toBeDefined();
      for (const s of e.workflow?.states ?? []) expect(m.states[s.key], `${e.key}.${s.key}`).toBeDefined();
    }
  });

  it("every entity has its lifecycle events in the catalogue", () => {
    for (const e of Object.values(MODEL.entities)) {
      expect(EVENT_TYPES).toHaveProperty(`${e.key}.created`);
      if (e.workflow) expect(EVENT_TYPES).toHaveProperty(`${e.key}.transitioned`);
    }
  });
});
