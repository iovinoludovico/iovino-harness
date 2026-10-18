"use server";

// Domain modeler of this app: stores a metamodel change proposal (owned by the modeler, replaced by
// `modeler install`; adapt src/lib/modeler/access.ts instead of this file).
//  - development (or MODELER_PROPOSALS=file): .modeler/proposals/<timestamp>.json in the repository,
//    applied with `/modeler:apply` (Claude Code) or `npm run model:apply -- --write`;
//  - production (or MODELER_PROPOSALS=db): a row of public.model_change_requests (admins only), copied into
//    the repository with `npm run model:pull` (linked Supabase project); the page also offers a download.
// A proposal never alters the running app: the metamodel changes only through the repository
// (domain.ecore.yaml + migration + code, then deploy). The page lists the proposals still waiting
// (listMetamodelProposals) so that nobody wonders where a saved change went, and can reject one.

import { mkdir, readdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { modelerDb, requireModelerAdmin } from "./access";

export type ProposalResult = { ok: boolean; message: string };

export type PendingProposal = {
  id: string;              // file name in development, row id in production
  behavior?: unknown;      // the behaviour (behavior.yaml) the proposal carries, when the modeler saved it
  author: string | null;
  note: string | null;
  createdAt: string;
  status: string;          // open | pulled
  metamodel: unknown;
};

const MAX_BYTES = 1_000_000;
const FILE_ID = /^[\w.-]+\.json$/;

function proposalMode(): "file" | "db" {
  return (process.env.MODELER_PROPOSALS ?? (process.env.NODE_ENV === "development" ? "file" : "db")) === "file" ? "file" : "db";
}

function proposalsDir(): string {
  return path.join(process.cwd(), ".modeler", "proposals");
}

/** Saves a proposal: the metamodel, and the behaviour (behavior.yaml as the editor proposes it) when the app has one. */
export async function saveMetamodelProposal(json: string, note: string, behaviorJson?: string | null): Promise<ProposalResult> {
  const admin = await requireModelerAdmin();
  if (json.length + (behaviorJson?.length ?? 0) > MAX_BYTES) return { ok: false, message: "Proposal too large" };
  let metamodel: unknown;
  let behavior: unknown = null;
  try {
    metamodel = JSON.parse(json);
    if (behaviorJson) behavior = JSON.parse(behaviorJson);
  } catch {
    return { ok: false, message: "Invalid proposal" };
  }
  if (!metamodel || typeof metamodel !== "object" || !("classes" in metamodel)) {
    return { ok: false, message: "Invalid metamodel" };
  }
  if (behavior !== null && (typeof behavior !== "object" || !("workflows" in (behavior as object)))) {
    return { ok: false, message: "Invalid behaviour" };
  }
  if (proposalMode() === "file") {
    const dir = proposalsDir();
    await mkdir(dir, { recursive: true });
    const name = `${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    const body = { author: admin.email, note, created_at: new Date().toISOString(), metamodel, ...(behavior ? { behavior } : {}) };
    await writeFile(path.join(dir, name), JSON.stringify(body, null, 2) + "\n");
    return { ok: true, message: `Proposal saved in .modeler/proposals/${name}: apply it with /modeler:apply` };
  }
  const db = await modelerDb();
  const row = { metamodel, note, author_email: admin.email, ...(behavior ? { behavior } : {}) };
  const { error } = await db.from("model_change_requests").insert(row);
  if (error && behavior && /behavior/.test(error.message)) {
    // the table predates the behaviour proposals: saved without it (add the column: see the install skill)
    const retry = await db.from("model_change_requests").insert({ metamodel, note, author_email: admin.email });
    if (retry.error) return { ok: false, message: retry.error.message };
    return { ok: true, message: "Proposal saved without the behaviour: model_change_requests has no `behavior` column yet (migration in the install skill)." };
  }
  if (error) return { ok: false, message: error.message };
  return { ok: true, message: "Proposal saved: the developer pulls it into the repository. You can also download it." };
}

/** The proposals saved and not yet applied: .modeler/proposals/*.json in development, open or pulled rows of
 * model_change_requests in production. Oldest first. */
export async function listMetamodelProposals(): Promise<PendingProposal[]> {
  await requireModelerAdmin();
  if (proposalMode() === "file") {
    const names = (await readdir(proposalsDir()).catch(() => [] as string[])).filter((n) => FILE_ID.test(n)).sort();
    const out: PendingProposal[] = [];
    for (const name of names) {
      try {
        const doc = JSON.parse(await readFile(path.join(proposalsDir(), name), "utf8"));
        out.push({ id: name, author: doc.author ?? null, note: doc.note ?? null, createdAt: doc.created_at ?? name,
                   status: "open", metamodel: doc.metamodel ?? doc, behavior: doc.behavior ?? undefined });
      } catch {
        // not a proposal: ignored
      }
    }
    return out;
  }
  const db = await modelerDb();
  // `behavior` exists only in tables created or migrated after the behaviour proposals: without it, select the rest.
  // supabase-js infers the row shape from the select string, so the two queries have different types: both are
  // read as `ProposalRow` (the fallback simply has no `behavior`).
  type ProposalRow = { id: unknown; metamodel: unknown; behavior?: unknown; note?: string | null;
                       author_email?: string | null; status: unknown; created_at: unknown };
  const select = (columns: string) => db
    .from("model_change_requests")
    .select(columns)
    .in("status", ["open", "pulled"])
    .order("created_at", { ascending: true });
  let { data, error } = (await select("id, metamodel, behavior, note, author_email, status, created_at")) as
    { data: ProposalRow[] | null; error: { message: string } | null };
  if (error && /behavior/.test(error.message)) {
    ({ data, error } = (await select("id, metamodel, note, author_email, status, created_at")) as
      { data: ProposalRow[] | null; error: { message: string } | null });
  }
  if (error) throw new Error(error.message);
  return (data ?? []).map((r) => ({ id: String(r.id), author: r.author_email ?? null, note: r.note ?? null,
                                    createdAt: String(r.created_at), status: String(r.status), metamodel: r.metamodel,
                                    behavior: r.behavior ?? undefined }));
}

/** Rejects a pending proposal: moved to .modeler/proposals/rejected/ in development, status `rejected` in production. */
export async function rejectMetamodelProposal(id: string): Promise<ProposalResult> {
  await requireModelerAdmin();
  if (proposalMode() === "file") {
    if (!FILE_ID.test(id)) return { ok: false, message: "Invalid proposal" };
    const dir = proposalsDir();
    await mkdir(path.join(dir, "rejected"), { recursive: true });
    try {
      await rename(path.join(dir, id), path.join(dir, "rejected", id));
    } catch {
      return { ok: false, message: "Proposal not found" };
    }
    return { ok: true, message: "Proposal rejected" };
  }
  const db = await modelerDb();
  const { error } = await db.from("model_change_requests").update({ status: "rejected" }).eq("id", id).in("status", ["open", "pulled"]);
  if (error) return { ok: false, message: error.message };
  return { ok: true, message: "Proposal rejected" };
}
