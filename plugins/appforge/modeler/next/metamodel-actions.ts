"use server";

// appforge web modeler: stores a metamodel change proposal.
//  - development (or APPFORGE_PROPOSALS=file): .appforge/proposals/<timestamp>.json in the repository,
//    applied with `/appforge:metamodel apply` (Claude Code) or `appforge metamodel apply --write`;
//  - production: a row of public.model_change_requests (admins only), pulled with
//    `appforge metamodel pull --db <DSN>`; the page also offers the proposal as a download.
// The metamodel changes only through the repository: a proposal never alters the running app.

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { requireRole } from "@/lib/auth"; // adopted apps: replace with the app's own admin check
import { createClient } from "@/lib/supabase/server";

export type ProposalResult = { ok: boolean; message: string };

const MAX_BYTES = 1_000_000;

export async function saveMetamodelProposal(json: string, note: string): Promise<ProposalResult> {
  const user = await requireRole("admin");
  if (json.length > MAX_BYTES) return { ok: false, message: "Proposal too large" };
  let metamodel: unknown;
  try {
    metamodel = JSON.parse(json);
  } catch {
    return { ok: false, message: "Invalid metamodel" };
  }
  if (!metamodel || typeof metamodel !== "object" || !("classes" in metamodel)) {
    return { ok: false, message: "Invalid metamodel" };
  }
  const author = user.profile.email;
  const toFile = process.env.APPFORGE_PROPOSALS === "file" || (process.env.NODE_ENV === "development" && process.env.APPFORGE_PROPOSALS !== "db");
  if (toFile) {
    const dir = path.join(process.cwd(), ".appforge", "proposals");
    await mkdir(dir, { recursive: true });
    const name = `${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    await writeFile(path.join(dir, name), JSON.stringify({ author, note, created_at: new Date().toISOString(), metamodel }, null, 2) + "\n");
    return { ok: true, message: `Proposal saved in .appforge/proposals/${name}: apply it with /appforge:metamodel apply` };
  }
  const supabase = await createClient();
  const { error } = await supabase.from("model_change_requests").insert({ metamodel, note, author_email: author });
  if (error) return { ok: false, message: error.message };
  return { ok: true, message: "Proposal saved: the developer pulls it with `appforge metamodel pull`. You can also download it." };
}
