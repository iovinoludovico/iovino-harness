import { format } from "date-fns";
import { getTranslations } from "next-intl/server";
import { requireRole } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";
import { EVENT_TYPES } from "@/lib/events/catalog";
import { PageHeader, Panel } from "@/components/page-header";
import { ActionForm, SubmitButton } from "@/components/action-form";
import { FormField } from "@/components/form-field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { createEndpoint, deleteEndpoint, redeliver, rotateSecret, sendTest, toggleEndpoint } from "./actions";

type Endpoint = {
  id: string; name: string; url: string; secret: string; previous_secret: string | null; event_filters: string[];
  basic_auth_username: string | null; active: boolean; created_at: string;
};
type Delivery = {
  id: string; status: string; attempts: number; last_status_code: number | null; last_error: string | null; created_at: string;
  endpoint: { name: string } | null; event: { type: string; subject: string | null } | null;
};

// Subscribers of the outbox (n8n and others): signed CloudEvents, at-least-once delivery.
export default async function IntegrationsPage() {
  await requireRole("admin");
  const t = await getTranslations();
  const supabase = await createClient();
  const [{ data: endpoints }, { data: deliveries }] = await Promise.all([
    supabase.from("webhook_endpoints")
      .select("id, name, url, secret, previous_secret, event_filters, basic_auth_username, active, created_at")
      .order("created_at"),
    supabase.from("webhook_deliveries")
      .select("id, status, attempts, last_status_code, last_error, created_at, endpoint:webhook_endpoints(name), event:events(type, subject)")
      .order("created_at", { ascending: false })
      .limit(50),
  ]);

  return (
    <>
      <PageHeader title={t("integrations.title")} description={t("integrations.description")} />
      <Panel className="mb-6 py-5">
        <ActionForm action={createEndpoint} className="grid gap-3 sm:grid-cols-2" resetOnSuccess>
          <FormField label={t("integrations.name")} htmlFor="name"><Input id="name" name="name" required /></FormField>
          <FormField label="URL" htmlFor="url"><Input id="url" name="url" type="url" required placeholder="https://n8n.example.org/webhook/..." /></FormField>
          <FormField label={t("integrations.filters")} htmlFor="event_filters" hint={t("integrations.filtersHint")}>
            <Input id="event_filters" name="event_filters" defaultValue="*" />
          </FormField>
          <div className="grid grid-cols-2 gap-2">
            <FormField label={t("integrations.basicUser")} htmlFor="bu"><Input id="bu" name="basic_auth_username" /></FormField>
            <FormField label={t("integrations.basicPassword")} htmlFor="bp"><Input id="bp" name="basic_auth_password" type="password" /></FormField>
          </div>
          <div className="sm:col-span-2"><SubmitButton>{t("integrations.add")}</SubmitButton></div>
        </ActionForm>
      </Panel>

      <h2 className="mb-3 text-xl font-semibold">{t("integrations.endpoints")}</h2>
      <Panel className="mb-8">
        {(endpoints as Endpoint[] | null)?.length ? (
          <ul className="divide-y">
            {(endpoints as Endpoint[]).map((ep) => (
              <li key={ep.id} className="space-y-1 py-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium">{ep.name} {!ep.active && <span className="text-muted-foreground">({t("integrations.inactive")})</span>}</p>
                  <div className="flex flex-wrap gap-1">
                    <form action={sendTest.bind(null, ep.id)}><Button size="sm" variant="outline" type="submit">{t("integrations.test")}</Button></form>
                    <form action={toggleEndpoint.bind(null, ep.id, !ep.active)}><Button size="sm" variant="ghost" type="submit">{ep.active ? t("integrations.disable") : t("integrations.enable")}</Button></form>
                    <form action={rotateSecret.bind(null, ep.id)}><Button size="sm" variant="ghost" type="submit">{t("integrations.rotate")}</Button></form>
                    <form action={deleteEndpoint.bind(null, ep.id)}><Button size="sm" variant="ghost" type="submit">{t("common.delete")}</Button></form>
                  </div>
                </div>
                <p className="text-sm break-all text-muted-foreground">{ep.url} · {ep.event_filters.join(", ")}{ep.basic_auth_username && ` · Basic ${ep.basic_auth_username}`}</p>
                <p className="font-mono text-xs break-all text-muted-foreground">{ep.secret}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="py-4 text-sm text-muted-foreground">{t("integrations.none")}</p>
        )}
      </Panel>

      <h2 className="mb-3 text-xl font-semibold">{t("integrations.deliveries")}</h2>
      <Panel className="mb-8">
        <ul className="divide-y text-sm">
          {((deliveries ?? []) as unknown as Delivery[]).map((d) => (
            <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span>
                <strong>{d.event?.type}</strong> {d.event?.subject} → {d.endpoint?.name}
                <span className="text-muted-foreground"> · {format(new Date(d.created_at), "dd/MM HH:mm")}</span>
              </span>
              <span className="flex items-center gap-2">
                <span className={d.status === "succeeded" ? "text-green-700" : d.status === "dead" ? "text-destructive" : ""}>
                  {d.status} ({d.attempts}){d.last_status_code ? ` HTTP ${d.last_status_code}` : ""}{d.last_error ? ` ${d.last_error}` : ""}
                </span>
                {d.status !== "succeeded" && (
                  <form action={redeliver.bind(null, d.id)}><Button size="xs" variant="outline" type="submit">{t("integrations.redeliver")}</Button></form>
                )}
              </span>
            </li>
          ))}
        </ul>
      </Panel>

      <h2 className="mb-3 text-xl font-semibold">{t("integrations.catalog")}</h2>
      <Panel>
        <ul className="divide-y text-sm">
          {Object.entries(EVENT_TYPES).map(([type, ev]) => (
            <li key={type} className="flex flex-wrap justify-between gap-2 py-2">
              <code>{type}</code>
              <span className="text-muted-foreground">{ev.description}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </>
  );
}
