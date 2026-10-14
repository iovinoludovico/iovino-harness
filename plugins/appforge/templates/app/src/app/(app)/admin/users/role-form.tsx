"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ActionForm, SubmitButton } from "@/components/action-form";
import { SearchableSelect, type SelectOption } from "@/components/searchable-select";
import type { ActionState } from "@/lib/action-state";
import { MODEL } from "@/lib/model";

// Role (+ scope for scoped roles) picker used to approve users and add roles.
export function RoleForm({
  action,
  scopes,
  submitLabel,
  optionalRole,
}: {
  action: (state: ActionState, formData: FormData) => Promise<ActionState>;
  scopes: SelectOption[];
  submitLabel: string;
  optionalRole?: boolean;
}) {
  const t = useTranslations();
  const [role, setRole] = useState("");
  const scoped = !!role && MODEL.roles[role]?.scoped;
  return (
    <ActionForm action={action} className="flex flex-wrap items-center gap-2 space-y-0" resetOnSuccess>
      <SearchableSelect
        name="role"
        className="w-52"
        value={role}
        onValueChange={setRole}
        required={!optionalRole}
        options={[...(optionalRole ? [{ value: "", label: t("admin.noRole") }] : []),
                  ...Object.keys(MODEL.roles).map((r) => ({ value: r, label: t(`model.roles.${r}`) }))]}
      />
      {scoped && <SearchableSelect name="scope_id" className="w-52" required options={scopes} placeholder={t("admin.scope")} />}
      <SubmitButton variant="outline">{submitLabel}</SubmitButton>
    </ActionForm>
  );
}
