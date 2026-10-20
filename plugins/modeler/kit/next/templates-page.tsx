// Notification texts of this app: the admin page (template copied by the install skill to the app's admin
// area, e.g. src/app/(admin)/admin/notifications/page.tsx, and adapted to its layout and translations).

import behavior from "@/lib/modeler/behavior.json";
import { NotificationTemplates } from "@/components/modeler/notification-templates";
import { requireModelerAdmin } from "@/lib/modeler/access";
import { listNotificationTemplates } from "@/lib/modeler/notification-actions";

export default async function NotificationTemplatesPage() {
  await requireModelerAdmin();
  const overrides = await listNotificationTemplates();
  return (
    <div className="space-y-4">
      <NotificationTemplates behavior={behavior} overrides={overrides} lang="it" />
    </div>
  );
}
