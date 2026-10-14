// Allowed email domains. The authoritative check is the Supabase "before user
// created" hook (app_settings.allowed_email_domains); this is the optimistic
// check used by the proxy and the OAuth callback. Empty list = any domain.
export const ALLOWED_EMAIL_DOMAINS = (process.env.NEXT_PUBLIC_ALLOWED_EMAIL_DOMAINS ?? "{{ALLOWED_DOMAINS}}")
  .split(",")
  .map((d) => d.trim().toLowerCase())
  .filter(Boolean);

export function isAllowedEmail(email: string | null | undefined): boolean {
  const domain = email?.toLowerCase().split("@")[1];
  if (!domain) return false;
  return ALLOWED_EMAIL_DOMAINS.length === 0 || ALLOWED_EMAIL_DOMAINS.includes(domain);
}
