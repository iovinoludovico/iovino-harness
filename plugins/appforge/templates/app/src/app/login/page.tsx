import { getTranslations } from "next-intl/server";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { LoginForm } from "./login-form";

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const { next } = await searchParams;
  const t = await getTranslations();
  return (
    <main className="grid min-h-screen md:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <section className="flex flex-col justify-between bg-primary p-8 text-primary-foreground md:p-12">
        <p className="text-2xl font-bold tracking-wide">{t("model.app.name")}</p>
        <div className="my-12 max-w-md md:my-0">
          <h1 className="text-4xl leading-tight font-bold md:text-5xl">{t("login.title")}</h1>
          <p className="mt-4 text-lg text-primary-foreground/80">{t("model.app.description")}</p>
        </div>
        <span />
      </section>
      <section className="flex items-center justify-center bg-background p-6 md:p-12">
        <div className="w-full max-w-sm space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl font-bold">{t("login.signIn")}</h2>
            <LocaleSwitcher />
          </div>
          <LoginForm
            next={typeof next === "string" ? next : null}
            google={{{GOOGLE_ENABLED}}}
            emailLogin={{{EMAIL_ENABLED}} || process.env.NEXT_PUBLIC_DEV_EMAIL_LOGIN === "true"}
          />
        </div>
      </section>
    </main>
  );
}
