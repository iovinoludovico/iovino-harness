"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { cn } from "@/lib/utils";

export type NavItem = { href: string; label: string };

// Top bar: application name, navigation built from the model, user and language.
export function AppHeader({
  appName,
  items,
  user,
}: {
  appName: string;
  items: NavItem[];
  user: { name: string; email: string; roles: string };
}) {
  const pathname = usePathname();
  const t = useTranslations("nav");
  const active = (href: string) => (href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`));
  return (
    <header className="border-b bg-card">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 md:px-8">
        <Link href="/" className="text-lg font-bold">
          {appName}
        </Link>
        <nav className="flex flex-1 flex-wrap gap-1" aria-label={t("main")}>
          {items.map((it) => (
            <Link
              key={it.href}
              href={it.href}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium",
                active(it.href) ? "bg-primary text-primary-foreground" : "text-foreground/80 hover:bg-muted"
              )}
            >
              {it.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <div className="text-right text-xs leading-tight">
            <p className="font-medium">{user.name}</p>
            <p className="text-muted-foreground">{user.roles}</p>
          </div>
          <LocaleSwitcher />
          <form action="/auth/signout" method="post">
            <button type="submit" className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted">
              {t("signOut")}
            </button>
          </form>
        </div>
      </div>
    </header>
  );
}
