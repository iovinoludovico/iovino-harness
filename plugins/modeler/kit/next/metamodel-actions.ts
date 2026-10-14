"use server";

// Domain modeler of this app: stores a metamodel change proposal (owned by the modeler, replaced by
// `modeler install`; adapt src/lib/modeler/access.ts instead of this file).
//  - development (or MODELER_PROPOSALS=file): .modeler/proposals/<timestamp>.json in the repository,
//    applied with `/modeler:apply` (Claude Code) or `npm run model:apply -- --write`;
//  - production (or MODELER_PROPOSALS=db): a row of public.model_change_requests (admins only), copied into
//    the repository with `python3 tools/modeler/modeler.py pull --db <DSN>`; the page also offers a download.
// A proposal never alters the running app: the metamodel changes only through the repository
// (domain.ecore.yaml + migration + code, then deploy).

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { modelerDb, requireModelerAdmin } from "./access";

export type ProposalResult = { ok: boolean; message: string };

const MAX_BYTES = 1_000_000;

export async function saveMetamodelProposal(json: string, note: string): Promise<ProposalResult> {
  const admin = await requireModelerAdmin();
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
  const mode = process.env.MODELER_PROPOSALS ?? (process.env.NODE_ENV === "development" ? "file" : "db");
  if (mode === "file") {
    const dir = path.join(process.cwd(), ".modeler", "proposals");
    await mkdir(dir, { recursive: true });
    const name = `${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    const body = { author: admin.email, note, created_at: new Date().toISOString(), metamodel };
    await writeFile(path.join(dir, name), JSON.stringify(body, null, 2) + "\n");
    return { ok: true, message: `Proposal saved in .modeler/proposals/${name}: apply it with /modeler:apply` };
  }
  const db = await modelerDb();
  const { error } = await db.from("model_change_requests").insert({ metamodel, note, author_email: admin.email });
  if (error) return { ok: false, message: error.message };
  return { ok: true, message: "Proposal saved: the developer pulls it into the repository. You can also download it." };
}
