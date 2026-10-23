// Apply from the web: the names of the GitHub Actions secrets the workflows modeler-apply and modeler-release read,
// and the pure helpers of the «Apply from the web» panel of /admin/model and of its server actions (owned by the
// modeler, replaced by `modeler install`). No "use server" here: a server-action file exports only async functions,
// and these are imported by the client component and by the tests too. Only erasable TypeScript (types, `as const`):
// the tests import this file directly with Node's type stripping.

export const APPLY_SECRETS = ["ANTHROPIC_API_KEY", "MODELER_PROD_DB", "MODELER_GH_TOKEN"] as const;
export type ApplySecretName = (typeof APPLY_SECRETS)[number];

/** The environments the two workflows run in: a secret set there overrides the repository secret of the same name. */
export const APPLY_ENVIRONMENTS = ["modeler-apply", "modeler-release"] as const;

export type ApplyWebSecret = {
  name: ApplySecretName;
  updatedAt: string | null;      // when the repository secret was last written (GitHub's updated_at); null when missing
  envOverride: string | null;    // the environment holding a secret of the same name, which takes precedence
};

export type ApplyWebStatus =
  | { mode: "file" }             // development: the proposals are applied with /modeler:apply, nothing to configure
  | {
      mode: "db";
      repo: string | null;       // owner/repo (MODELER_APPLY_REPO, else modeler-apply.json written by `modeler install`)
      pooler: string | null;     // the pooler URL of the production database without password, from modeler-apply.json
      dbFromEnv: boolean;        // the web process has DATABASE_URL (or MODELER_PROD_DB) with the password: no need to type it
      tokenOk: boolean;          // MODELER_APPLY_TOKEN is set and lists the repository secrets
      configured: boolean;      // the three secrets exist
      envChecked: boolean;       // the environment secrets could be listed (Environments: read on the token)
      secrets: ApplyWebSecret[];
      error: string | null;
    };

export type ApplyWebInput = {
  anthropicKey?: string;         // ANTHROPIC_API_KEY
  dbPassword?: string;           // MODELER_PROD_DB = pooler URL + this password (when the pooler is known)
  dsn?: string;                  // MODELER_PROD_DB as a full connection string (when the pooler is unknown)
  useAppDatabaseUrl?: boolean;   // MODELER_PROD_DB = the DATABASE_URL of the web process (when it has one)
  mergeToken?: string;           // MODELER_GH_TOKEN; empty + useAppTokenForMerge: the app's own token
  useAppTokenForMerge?: boolean;
};

const POSTGRES_USER = /^(postgres(?:ql)?:\/\/[^:@/]+)(?::[^@/]*)?@/;

/** The pooler URL with the password percent-encoded after the user (an existing `:[YOUR-PASSWORD]` segment is
 * replaced); null when it is not a postgres URL. libpq and `supabase db push --db-url` decode the userinfo, so a
 * password with `@`, `:`, `/`, `#` or `%` travels safely. */
export function dsnWithPassword(pooler: string, password: string): string | null {
  const url = pooler.trim();
  if (!POSTGRES_USER.test(url)) return null;
  return url.replace(POSTGRES_USER, (_m, user: string) => `${user}:${encodeURIComponent(password)}@`);
}

/** Whether a connection string carries a password (`user:password@`). */
export function dsnHasPassword(dsn: string): boolean {
  return /^postgres(?:ql)?:\/\/[^:@/]+:[^@/]+@/.test(dsn.trim());
}

/** The command that removes the environment secret overriding the repository one. */
export function envOverrideCommand(name: string, env: string, repo: string): string {
  return `gh secret delete ${name} --env ${env} --repo ${repo}`;
}
