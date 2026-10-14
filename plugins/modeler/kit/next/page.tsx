// Domain modeler of this app: the admin page (template copied by the install skill to the app's admin
// area, e.g. src/app/(admin)/admin/model/page.tsx, and adapted to its layout and translations).

import metamodel from "@/lib/modeler/metamodel.json";
import { MetamodelModeler } from "@/components/modeler/metamodel-modeler";
import { requireModelerAdmin } from "@/lib/modeler/access";
import { saveMetamodelProposal } from "@/lib/modeler/metamodel-actions";

export default async function ModelPage() {
  await requireModelerAdmin();
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Domain model</h1>
      <MetamodelModeler metamodel={metamodel} canEdit lang="it" onSave={saveMetamodelProposal} />
    </div>
  );
}
