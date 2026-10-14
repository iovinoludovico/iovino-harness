import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { getCurrentUser } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

// Shown to users who signed in but have not been enabled by an admin yet.
export default async function PendingPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  if (user.profile.approved_at) redirect("/");
  const t = await getTranslations();

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <CardTitle>{t("pending.title")}</CardTitle>
            <LocaleSwitcher />
          </div>
          <CardDescription>
            {t("pending.body", { name: user.profile.full_name ?? user.profile.email })}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          <form action="/auth/signout" method="post">
            <Button type="submit" variant="outline">
              {t("common.signOut")}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
