"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ALLOWED_EMAIL_DOMAINS } from "@/lib/domain";

function callbackUrl(next: string | null) {
  const url = new URL("/auth/callback", window.location.origin);
  if (next) url.searchParams.set("next", next);
  return url.toString();
}

export function LoginForm({ next, google, emailLogin }: { next: string | null; google: boolean; emailLogin: boolean }) {
  const t = useTranslations("login");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function signInWithGoogle() {
    setPending(true);
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: callbackUrl(next),
        // Hint for Google to show only institutional accounts (enforced server-side).
        queryParams: { ...(ALLOWED_EMAIL_DOMAINS[0] ? { hd: ALLOWED_EMAIL_DOMAINS[0] } : {}), prompt: "select_account" },
      },
    });
    if (error) {
      setMessage(error.message);
      setPending(false);
    }
  }

  async function signInWithEmail(formData: FormData) {
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithOtp({
      email: String(formData.get("email")),
      options: { emailRedirectTo: callbackUrl(next) },
    });
    setMessage(error ? error.message : t("linkSent"));
  }

  return (
    <div className="space-y-4">
      {google && (
        <Button className="w-full" size="lg" onClick={signInWithGoogle} disabled={pending}>
          {t("google")}
        </Button>
      )}
      {emailLogin && (
        <form action={signInWithEmail} className="space-y-2 border-t pt-4">
          <p className="text-xs text-muted-foreground">{t("emailHint")}</p>
          <div className="flex gap-2">
            <Input name="email" type="email" placeholder={t("emailPlaceholder")} required />
            <Button type="submit" variant="outline">
              {t("sendLink")}
            </Button>
          </div>
        </form>
      )}
      {message && <p className="text-sm text-muted-foreground">{message}</p>}
    </div>
  );
}
