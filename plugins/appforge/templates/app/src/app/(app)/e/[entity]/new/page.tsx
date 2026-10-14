import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { requireUser } from "@/lib/auth";
import { refOptionsFor } from "@/lib/records";
import { entityByKey, k } from "@/lib/model-helpers";
import { PageHeader } from "@/components/page-header";
import { EntityForm } from "@/components/entity-form";
import { Card, CardContent } from "@/components/ui/card";
import { saveRow } from "../../actions";

export default async function NewEntityPage({ params, searchParams }: PageProps<"/e/[entity]/new">) {
  await requireUser();
  const { entity: key } = await params;
  const e = entityByKey(key);
  if (!e) notFound();
  const [t, options, sp] = await Promise.all([getTranslations(), refOptionsFor(e), searchParams]);
  // ?f_<field>=<value> pre-fills single fields (used by the related panels of a parent record).
  const prefill = Object.fromEntries(
    e.fields
      .filter((f) => !f.many && typeof sp[`f_${f.key}`] === "string")
      .map((f) => [f.key, sp[`f_${f.key}`] as string]),
  );
  return (
    <>
      <PageHeader title={t("records.newTitle", { entity: t(k.entity(e)) })} />
      <Card>
        <CardContent>
          <EntityForm entity={e} row={Object.keys(prefill).length ? prefill : null} options={options} action={saveRow.bind(null, e.key, null)} submitLabel={t("records.create")} />
        </CardContent>
      </Card>
    </>
  );
}
