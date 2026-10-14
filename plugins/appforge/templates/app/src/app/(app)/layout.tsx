import { getTranslations } from "next-intl/server";
import { requireUser } from "@/lib/auth";
import { AppHeader } from "@/components/app-header";
import { RealtimeRefresh } from "@/components/realtime-refresh";
import { k, menuEntities } from "@/lib/model-helpers";

export default async function AppLayout({ children }: LayoutProps<"/">) {
  const [user, t] = await Promise.all([requireUser(), getTranslations()]);
  const items = [
    { href: "/", label: t("nav.dashboard") },
    ...menuEntities().map((e) => ({ href: `/e/${e.key}`, label: t(k.plural(e)) })),
    ...(user.isAdmin ? [{ href: "/admin/users", label: t("nav.users") }, { href: "/admin/integrations", label: t("nav.integrations") }, { href: "/admin/model", label: t("nav.model") }] : []),
  ];
  const roles = [...new Set(user.roles.map((r) => t(k.role(r.role))))].join(", ") || t("app.noRoles");
  return (
    <div className="min-h-screen">
      <AppHeader
        appName={t("model.app.name")}
        items={items}
        user={{ name: user.profile.full_name ?? user.profile.email, email: user.profile.email, roles }}
      />
      {/* Refreshes server components when a `broadcast` reaction publishes on the "dashboard" channel. */}
      <RealtimeRefresh channel="dashboard" />
      <main className="mx-auto max-w-7xl px-4 py-8 md:px-8 md:py-10">{children}</main>
    </div>
  );
}
