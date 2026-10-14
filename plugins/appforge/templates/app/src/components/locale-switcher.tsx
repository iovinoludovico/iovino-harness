"use client";

import { useTransition } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { LOCALES, LOCALE_NAMES } from "@/i18n/config";
import { setLocale } from "@/app/preferences-actions";
import { cn } from "@/lib/utils";

export function LocaleSwitcher({ className, tone = "light" }: { className?: string; tone?: "light" | "dark" }) {
  const t = useTranslations("language");
  const locale = useLocale();
  const router = useRouter();
  const [pending, start] = useTransition();
  return (
    <div className={cn("flex items-center gap-1 text-xs", className)} aria-label={t("label")} role="group">
      {LOCALES.map((l) => (
        <button
          key={l}
          type="button"
          disabled={pending || l === locale}
          title={LOCALE_NAMES[l]}
          onClick={() =>
            start(async () => {
              await setLocale(l);
              router.refresh();
            })
          }
          className={cn(
            "rounded px-2 py-1 font-medium uppercase",
            tone === "dark"
              ? l === locale
                ? "bg-white text-ink"
                : "text-sidebar-foreground/70 hover:bg-sidebar-accent"
              : l === locale
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted"
          )}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
