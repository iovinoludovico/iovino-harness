import { getLocale, getTranslations } from "next-intl/server";
import { requireRole } from "@/lib/auth";
import { PageHeader } from "@/components/page-header";
import { MetamodelModeler } from "@/components/appforge/metamodel-modeler";
import { saveMetamodelProposal } from "@/lib/appforge/metamodel-actions";
import metamodel from "@/lib/appforge/metamodel.json";

// Web modeler of the domain metamodel (domain.ecore.yaml). Saving creates a proposal: the
// application changes only when the developer applies it and regenerates (/appforge:metamodel apply).
export default async function ModelPage() {
  await requireRole("admin");
  const [t, locale] = await Promise.all([getTranslations(), getLocale()]);
  return (
    <>
      <PageHeader title={t("admin.modelTitle")} description={t("admin.modelDescription")} />
      <MetamodelModeler
        metamodel={metamodel}
        canEdit
        lang={locale}
        saveLabel={t("admin.modelPropose")}
        downloadLabel={t("admin.modelDownload")}
        onSave={saveMetamodelProposal}
      />
    </>
  );
}
