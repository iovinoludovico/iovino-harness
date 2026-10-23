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
// "Apply" on a production proposal (requestProposalApply) starts the `modeler-apply` GitHub Actions workflow
// (repository_dispatch): Claude Code applies it on a branch and opens the pull request, whose link comes back on
// the row (`npm run model:track`). "Confirm and release" on the PR (requestProposalRelease) starts `modeler-release`
// the same way (migrations on the production database, merge, deploy, done); proposalPullRequest shows the PR to
// review first.
// One variable in the app's environment: MODELER_APPLY_TOKEN, a fine-grained token on that repository only with
// Contents: write (the dispatches), Pull requests: write (the review, and the merge when it serves as MODELER_GH_TOKEN)
// and Secrets: write (the panel below); it never leaves the server. The repository comes from modeler-apply.json
// (written by `modeler install` from the git remote; MODELER_APPLY_REPO overrides it). The secrets the workflows read
// (ANTHROPIC_API_KEY, MODELER_PROD_DB, MODELER_GH_TOKEN) are set from the «Apply from the web» panel of the page:
// saveApplyWebSecrets seals each value with the repository's Actions public key (libsodium sealed box, as `gh secret
// set` does) and writes it as a repository secret; the app stores nothing, applyWebStatus only reports their dates.
// What the app's environment already holds is never typed again: applyWebStatus writes MODELER_PROD_DB from the
// DATABASE_URL of the web process (the compose passes it to `web` as to the worker) and MODELER_GH_TOKEN from the app's
// own token as soon as they are missing on GitHub, so the admin types only the API key.

import { mkdir, readdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { modelerDb, requireModelerAdmin } from "./access";
import { APPLY_ENVIRONMENTS, APPLY_SECRETS, dsnHasPassword, dsnWithPassword,
         type ApplySecretName, type ApplyWebInput, type ApplyWebSecret, type ApplyWebStatus } from "./apply-web";
import applyConfig from "./modeler-apply.json";

export type ProposalResult = { ok: boolean; message: string };

export type PendingProposal = {
  id: string;              // file name in development, row id in production
  behavior?: unknown;      // the behaviour (behavior.yaml) the proposal carries, when the modeler saved it
  author: string | null;
  note: string | null;
  createdAt: string;
  status: string;          // open | pulled
  metamodel: unknown;
  applyRequestedAt?: string | null;   // "Apply" pressed (production): the workflow is running or has finished
  applyFinishedAt?: string | null;
  prUrl?: string | null;              // the pull request the workflow opened
  applyError?: string | null;         // why the last run failed (link to the run)
  releaseRequestedAt?: string | null; // "Confirm and release" pressed: the modeler-release workflow is running
  releaseError?: string | null;       // why the release stopped (link to the run)
  mergedAt?: string | null;           // the PR is merged (the deploy follows)
  deployedAt?: string | null;         // the deploy of the merge succeeded and the proposal was closed
};

/** What the admin reviews before releasing: the pull request as GitHub describes it (its body is the summary
 * Claude Code wrote: what changes, the TODO lines left commented, the cost). */
export type ProposalPullRequest = {
  number: number; title: string; body: string; state: string; merged: boolean;
  mergeable: boolean | null; mergeableState: string; changedFiles: number; additions: number; deletions: number;
  htmlUrl: string;
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
                       author_email?: string | null; status: unknown; created_at: unknown;
                       apply_requested_at?: string | null; apply_finished_at?: string | null;
                       pr_url?: string | null; apply_error?: string | null;
                       release_requested_at?: string | null; release_error?: string | null;
                       merged_at?: string | null; deployed_at?: string | null };
  type Rows = { data: ProposalRow[] | null; error: { message: string } | null };
  const select = (columns: string) => db
    .from("model_change_requests")
    .select(columns)
    .in("status", ["open", "pulled"])
    .order("created_at", { ascending: true });
  const base = "id, metamodel, note, author_email, status, created_at";
  // columns added over time (behaviour proposals, apply from the web): without them, select the rest
  const apply = "apply_requested_at, apply_finished_at, pr_url, apply_error";
  const release = "release_requested_at, release_error, merged_at, deployed_at";
  let { data, error } = (await select(`${base}, behavior, ${apply}, ${release}`)) as Rows;
  if (error && /release_|merged_at|deployed_at/.test(error.message)) ({ data, error } = (await select(`${base}, behavior, ${apply}`)) as Rows);
  if (error && /apply_|pr_url/.test(error.message)) ({ data, error } = (await select(`${base}, behavior`)) as Rows);
  if (error && /behavior/.test(error.message)) ({ data, error } = (await select(base)) as Rows);
  if (error) throw new Error(error.message);
  return (data ?? []).map((r) => ({ id: String(r.id), author: r.author_email ?? null, note: r.note ?? null,
                                    createdAt: String(r.created_at), status: String(r.status), metamodel: r.metamodel,
                                    behavior: r.behavior ?? undefined,
                                    applyRequestedAt: r.apply_requested_at ?? null, applyFinishedAt: r.apply_finished_at ?? null,
                                    prUrl: r.pr_url ?? null, applyError: r.apply_error ?? null,
                                    releaseRequestedAt: r.release_requested_at ?? null, releaseError: r.release_error ?? null,
                                    mergedAt: r.merged_at ?? null, deployedAt: r.deployed_at ?? null }));
}

const GITHUB_HEADERS = (token: string) => ({ Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" });

// Written by `modeler install`: the repository (from the git remote) and the pooler URL of the production database
// without password (from the linked Supabase project); null when it could not derive them.
const APPLY = applyConfig as { repo?: string | null; pooler?: string | null };

function applyRepo(): string | null {
  return process.env.MODELER_APPLY_REPO || APPLY.repo || null;
}

/** The connection string of the production database the web process already has (the compose passes DATABASE_URL
 * to `web` as to the worker), when it carries the password: the panel reuses it instead of asking for the password. */
function appDatabaseUrl(): string | null {
  return [process.env.MODELER_PROD_DB, process.env.DATABASE_URL].find((v) => v && dsnHasPassword(v)) ?? null;
}

function githubConfig(): { repo: string; token: string } | ProposalResult {
  const repo = applyRepo();
  const token = process.env.MODELER_APPLY_TOKEN;
  if (!token) {
    return { ok: false, message: "Apply from the web is not configured: set MODELER_APPLY_TOKEN in the app's environment (fine-grained token on this repository: Contents write, Pull requests write, Secrets write). The API key, the database password and the merge token are then set from the «Apply from the web» panel of this page (modeler install skill, section 7)." };
  }
  if (!repo) {
    return { ok: false, message: "Apply from the web: the GitHub repository is unknown. Run `modeler install` again with the git remote `origin` set, or set MODELER_APPLY_REPO (owner/repo) in the app's environment." };
  }
  return { repo, token };
}

type GhResponse = { ok: boolean; status: number; text: () => Promise<string>; json: () => Promise<unknown> };

/** One call to the GitHub API on the app's repository; a network failure reads as status 0. */
async function gh(repo: string, token: string, path: string, init: RequestInit = {}): Promise<GhResponse> {
  return fetch(`https://api.github.com/repos/${repo}${path}`, { ...init, headers: GITHUB_HEADERS(token), cache: "no-store" })
    .catch((e: unknown): GhResponse => ({ ok: false, status: 0, text: async () => String(e), json: async () => ({}) }));
}

async function ghDetail(res: GhResponse): Promise<string> {
  return (await res.text().catch(() => "")).slice(0, 200);
}

async function dispatch(repo: string, token: string, eventType: string, payload: Record<string, unknown>): Promise<ProposalResult> {
  const res = await gh(repo, token, "/dispatches", { method: "POST", body: JSON.stringify({ event_type: eventType, client_payload: payload }) });
  if (!res.ok) {
    const detail = await ghDetail(res);
    return { ok: false, message: `GitHub refused the dispatch (${res.status}): ${detail || "check the repository and the token's permissions (Contents: write)"}` };
  }
  return { ok: true, message: "" };
}

/** The pull request opened for a proposal, to review it before the release (needs Pull requests: read on the token). */
export async function proposalPullRequest(id: string): Promise<ProposalPullRequest | ProposalResult> {
  await requireModelerAdmin();
  if (!/^[0-9a-f-]{36}$/i.test(id)) return { ok: false, message: "Invalid proposal" };
  const cfg = githubConfig();
  if ("ok" in cfg) return cfg;
  const db = await modelerDb();
  const { data, error } = (await db.from("model_change_requests").select("pr_url").eq("id", id)) as
    { data: { pr_url?: string | null }[] | null; error: { message: string } | null };
  if (error) return { ok: false, message: error.message };
  const m = /\/pull\/(\d+)$/.exec(data?.[0]?.pr_url ?? "");
  if (!m) return { ok: false, message: "No pull request on this proposal yet" };
  const res = await gh(cfg.repo, cfg.token, `/pulls/${m[1]}`);
  if (!res.ok) {
    const detail = await ghDetail(res);
    return { ok: false, message: `GitHub refused the request (${res.status}): ${detail || "the token needs Pull requests: read"}` };
  }
  const pr = (await res.json()) as { number: number; title: string; body: string | null; state: string; merged: boolean;
    mergeable: boolean | null; mergeable_state: string; changed_files: number; additions: number; deletions: number; html_url: string };
  return { number: pr.number, title: pr.title, body: pr.body ?? "", state: pr.state, merged: pr.merged, mergeable: pr.mergeable,
           mergeableState: pr.mergeable_state, changedFiles: pr.changed_files, additions: pr.additions, deletions: pr.deletions, htmlUrl: pr.html_url };
}

/** "Confirm and release": starts the `modeler-release` workflow on the proposal's pull request (migrations on the
 * production database, merge, deploy, `model:done`); its progress comes back on the row with `npm run model:track`. */
export async function requestProposalRelease(id: string): Promise<ProposalResult> {
  await requireModelerAdmin();
  if (proposalMode() === "file") return { ok: false, message: "In development a proposal is applied with /modeler:apply." };
  if (!/^[0-9a-f-]{36}$/i.test(id)) return { ok: false, message: "Invalid proposal" };
  const cfg = githubConfig();
  if ("ok" in cfg) return cfg;
  const db = await modelerDb();
  const { data, error } = (await db.from("model_change_requests").select("pr_url, merged_at").eq("id", id)) as
    { data: { pr_url?: string | null; merged_at?: string | null }[] | null; error: { message: string } | null };
  if (error) return { ok: false, message: error.message };
  const m = /\/pull\/(\d+)$/.exec(data?.[0]?.pr_url ?? "");
  if (!m) return { ok: false, message: "No pull request on this proposal yet" };
  if (data?.[0]?.merged_at) return { ok: false, message: "Already merged: the rest of the release is followed on GitHub" };
  const sent = await dispatch(cfg.repo, cfg.token, "modeler-release", { proposal_id: id, pr_number: Number(m[1]) });
  if (!sent.ok) return sent;
  const upd = await db.from("model_change_requests")
    .update({ release_requested_at: new Date().toISOString(), release_error: null }).eq("id", id);
  if (upd.error && /release_/.test(upd.error.message)) {
    return { ok: true, message: "Release started. model_change_requests has no release columns yet (migration model_change_requests_apply in the install skill): progress will not show here." };
  }
  if (upd.error) return { ok: false, message: upd.error.message };
  return { ok: true, message: "Release started: migrations on the production database, merge, deploy. The proposal closes when the deploy is done." };
}

/** Starts the `modeler-apply` workflow on a production proposal: a repository_dispatch to the app's GitHub
 * repository, which pulls that proposal, runs Claude Code and opens the pull request (its link comes back on the
 * row with `npm run model:track`). Development proposals are applied with /modeler:apply instead. */
export async function requestProposalApply(id: string): Promise<ProposalResult> {
  await requireModelerAdmin();
  if (proposalMode() === "file") {
    return { ok: false, message: "In development a proposal is applied with /modeler:apply (npm run model:apply)." };
  }
  if (!/^[0-9a-f-]{36}$/i.test(id)) return { ok: false, message: "Invalid proposal" };
  const cfg = githubConfig();
  if ("ok" in cfg) return cfg;
  const sent = await dispatch(cfg.repo, cfg.token, "modeler-apply", { proposal_id: id });
  if (!sent.ok) return sent;
  const db = await modelerDb();
  const { error } = await db.from("model_change_requests")
    .update({ apply_requested_at: new Date().toISOString(), apply_finished_at: null, pr_url: null, apply_error: null })
    .eq("id", id).in("status", ["open", "pulled"]);
  if (error && /apply_|pr_url/.test(error.message)) {
    return { ok: true, message: "Workflow started. model_change_requests has no apply columns yet (migration model_change_requests_apply in the install skill): the pull request link will not show here." };
  }
  if (error) return { ok: false, message: error.message };
  return { ok: true, message: "Workflow started: the pull request will appear here when it is ready (a few minutes)." };
}

/** The state of «Apply from the web»: repository, token, the three Actions secrets with the date they were written
 * and whether an environment secret of the same name would take precedence. Never returns a value. */
export async function applyWebStatus(): Promise<ApplyWebStatus> {
  await requireModelerAdmin();
  if (proposalMode() === "file") return { mode: "file" };
  const cfg = githubConfig();
  // what the app's environment provides: written on GitHub by this very call when missing there
  const fromEnv: Partial<Record<ApplySecretName, string>> = {};
  const own = appDatabaseUrl();
  if (own) fromEnv.MODELER_PROD_DB = own;
  if (!("ok" in cfg)) fromEnv.MODELER_GH_TOKEN = cfg.token;
  const blank = APPLY_SECRETS.map((name): ApplyWebSecret => ({ name, updatedAt: null, envOverride: null, fromEnv: name in fromEnv }));
  const base = { mode: "db" as const, repo: applyRepo(), pooler: APPLY.pooler ?? null, dbFromEnv: own !== null,
                 tokenOk: false, configured: false, envChecked: false, secrets: blank };
  if ("ok" in cfg) return { ...base, error: cfg.message };
  const res = await gh(cfg.repo, cfg.token, "/actions/secrets?per_page=100");
  if (!res.ok) {
    const detail = await ghDetail(res);
    return { ...base, error: `GitHub refused the secrets list (${res.status}): ${detail || `the token needs Secrets: read and write on ${cfg.repo}`}` };
  }
  const list = (await res.json()) as { secrets?: { name: string; updated_at: string }[] };
  const dates = new Map((list.secrets ?? []).map((x) => [x.name, x.updated_at] as const));
  let envChecked = true;
  const overrides = new Map<string, string>();
  for (const env of APPLY_ENVIRONMENTS) {
    const r = await gh(cfg.repo, cfg.token, `/environments/${env}/secrets?per_page=100`);
    if (r.status === 404) continue;                       // not created yet: GitHub creates it on the first run
    if (!r.ok) { envChecked = false; continue; }          // Environments: read missing on the token: not blocking
    const l = (await r.json()) as { secrets?: { name: string }[] };
    for (const x of l.secrets ?? []) if (!overrides.has(x.name)) overrides.set(x.name, env);
  }
  let error: string | null = null;
  const seed: Partial<Record<ApplySecretName, string>> = {};
  for (const name of APPLY_SECRETS) if (fromEnv[name] && !dates.has(name) && !overrides.has(name)) seed[name] = fromEnv[name];
  if (Object.keys(seed).length) {
    const written = await putSecrets(cfg, seed);
    if (written.ok) for (const name of written.names) dates.set(name, new Date().toISOString());
    else error = `Could not write ${Object.keys(seed).join(", ")} from the app's environment: ${written.message}`;
  }
  const secrets = APPLY_SECRETS.map((name): ApplyWebSecret => ({ name, updatedAt: dates.get(name) ?? null, envOverride: overrides.get(name) ?? null, fromEnv: name in fromEnv }));
  return { ...base, tokenOk: true, configured: secrets.every((x) => x.updatedAt || x.envOverride), envChecked, secrets, error };
}

/** Seals each value with the repository's Actions public key (libsodium sealed box, the recipe of `gh secret set`)
 * and writes it as a repository secret. */
async function putSecrets(cfg: { repo: string; token: string }, values: Partial<Record<ApplySecretName, string>>): Promise<ProposalResult & { names: ApplySecretName[] }> {
  const names = Object.keys(values) as ApplySecretName[];
  const pk = await gh(cfg.repo, cfg.token, "/actions/secrets/public-key");
  if (!pk.ok) {
    const detail = await ghDetail(pk);
    return { ok: false, names, message: `GitHub refused the repository's public key (${pk.status}): ${detail || `the token needs Secrets: read and write on ${cfg.repo}`}` };
  }
  const { key_id, key: publicKey } = (await pk.json()) as { key_id: string; key: string };
  const mod = await import("libsodium-wrappers");
  const sodium = ((mod as unknown as { default?: typeof mod }).default ?? mod) as typeof mod;   // CJS under a bundler or Node
  await sodium.ready;
  const recipient = sodium.from_base64(publicKey, sodium.base64_variants.ORIGINAL);
  for (const name of names) {
    const sealed = sodium.crypto_box_seal(sodium.from_string(values[name] ?? ""), recipient);
    const res = await gh(cfg.repo, cfg.token, `/actions/secrets/${name}`, {
      method: "PUT", body: JSON.stringify({ encrypted_value: sodium.to_base64(sealed, sodium.base64_variants.ORIGINAL), key_id }),
    });
    if (!res.ok) {
      const detail = await ghDetail(res);
      return { ok: false, names, message: `GitHub refused to write ${name} (${res.status}): ${detail || `the token needs Secrets: write on ${cfg.repo}`}` };
    }
  }
  return { ok: true, names, message: "" };
}

/** Writes what the admin typed as repository Actions secrets (sealed; see putSecrets). An empty field leaves the
 * existing secret untouched; the app stores nothing and never sends a value back. */
export async function saveApplyWebSecrets(input: ApplyWebInput): Promise<ProposalResult> {
  await requireModelerAdmin();
  if (proposalMode() === "file") return { ok: false, message: "In development the proposals are applied with /modeler:apply: nothing to configure." };
  const cfg = githubConfig();
  if ("ok" in cfg) return cfg;
  const values: Partial<Record<ApplySecretName, string>> = {};
  const key = input.anthropicKey?.trim();
  if (key) values.ANTHROPIC_API_KEY = key;
  const dsn = input.dsn?.trim();
  if (dsn) {
    if (!dsnHasPassword(dsn)) return { ok: false, message: "The connection string must carry the password: postgresql://user:password@host:5432/postgres." };
    values.MODELER_PROD_DB = dsn;
  } else if (input.dbPassword) {
    const full = APPLY.pooler ? dsnWithPassword(APPLY.pooler, input.dbPassword) : null;
    if (!full) return { ok: false, message: "The pooler URL of the production database is unknown: paste the full connection string instead (or `supabase link`, then `modeler install` again)." };
    values.MODELER_PROD_DB = full;
  }
  const merge = input.mergeToken?.trim();
  if (merge) values.MODELER_GH_TOKEN = merge;
  const names = Object.keys(values) as ApplySecretName[];
  if (!names.length) return { ok: false, message: "Nothing to save: the fields are empty." };
  if (names.some((n) => Buffer.byteLength(values[n] ?? "") > 48_000)) return { ok: false, message: "A value exceeds GitHub's limit of 48 KB for a secret." };
  const written = await putSecrets(cfg, values);
  if (!written.ok) return { ok: false, message: written.message };
  return { ok: true, message: `Saved on GitHub as repository secrets of ${cfg.repo}: ${names.join(", ")}. A secret with the same name in the modeler-apply or modeler-release environment still takes precedence.` };
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
