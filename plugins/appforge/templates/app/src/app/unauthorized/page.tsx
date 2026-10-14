import { getTranslations } from "next-intl/server";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { LinkButton } from "@/components/link-button";

export default async function UnauthorizedPage({ searchParams }: PageProps<"/unauthorized">) {
  const { reason } = await searchParams;
  const t = await getTranslations();
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{t("unauthorized.title")}</CardTitle>
          <CardDescription>
            {reason === "inactive" ? t("unauthorized.inactive") : t("unauthorized.domain")}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          <form action="/auth/signout" method="post">
            <Button type="submit" variant="outline">
              {t("common.signOut")}
            </Button>
          </form>
          <LinkButton href="/login">{t("unauthorized.backToLogin")}</LinkButton>
        </CardContent>
      </Card>
    </main>
  );
}
