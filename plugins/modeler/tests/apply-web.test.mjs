// The pure helpers of the «Apply from the web» panel (kit/next/apply-web.ts). The file is erasable TypeScript, so
// Node imports it directly where type stripping is on (Node 22.6+ with the flag, default from 23); elsewhere skipped.
import { test } from "node:test";
import assert from "node:assert/strict";

const stripping = Boolean(process.features?.typescript);
const mod = stripping ? await import("../kit/next/apply-web.ts") : null;
const skip = !stripping && "node without type stripping";

test("dsnWithPassword: the encoded password goes after the user of the pooler URL", { skip }, () => {
  const pooler = "postgresql://postgres.abcref@aws-0-eu-west-1.pooler.supabase.com:5432/postgres";
  assert.equal(mod.dsnWithPassword(pooler, "secret"), "postgresql://postgres.abcref:secret@aws-0-eu-west-1.pooler.supabase.com:5432/postgres");
  assert.equal(mod.dsnWithPassword(pooler, "p@ss:w/rd#1%"), "postgresql://postgres.abcref:p%40ss%3Aw%2Frd%231%25@aws-0-eu-west-1.pooler.supabase.com:5432/postgres");
  assert.equal(mod.dsnWithPassword("postgres://postgres.abcref:[YOUR-PASSWORD]@host:6543/postgres\n", "x"), "postgres://postgres.abcref:x@host:6543/postgres");
  assert.equal(mod.dsnWithPassword("mysql://u@h/db", "x"), null);
  assert.equal(mod.dsnWithPassword("", "x"), null);
});

test("dsnHasPassword and envOverrideCommand", { skip }, () => {
  assert.equal(mod.dsnHasPassword("postgresql://u:secret@h:5432/db"), true);
  assert.equal(mod.dsnHasPassword("postgresql://u@h:5432/db"), false);
  assert.equal(mod.dsnHasPassword("postgresql://u:@h/db"), false);
  assert.equal(mod.envOverrideCommand("MODELER_PROD_DB", "modeler-apply", "o/r"), "gh secret delete MODELER_PROD_DB --env modeler-apply --repo o/r");
  assert.deepEqual([...mod.APPLY_SECRETS], ["ANTHROPIC_API_KEY", "MODELER_PROD_DB", "MODELER_GH_TOKEN"]);
  assert.deepEqual([...mod.APPLY_ENVIRONMENTS], ["modeler-apply", "modeler-release"]);
});
