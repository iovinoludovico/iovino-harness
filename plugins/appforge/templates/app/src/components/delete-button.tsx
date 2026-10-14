"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ActionForm, SubmitButton } from "@/components/action-form";
import { Button } from "@/components/ui/button";
import type { ActionState } from "@/lib/action-state";

export function DeleteButton({ action }: { action: () => Promise<ActionState> }) {
  const t = useTranslations("common");
  const [confirming, setConfirming] = useState(false);
  if (!confirming) {
    return (
      <Button variant="outline" onClick={() => setConfirming(true)}>
        {t("delete")}
      </Button>
    );
  }
  return (
    <ActionForm action={() => action()} className="flex items-center gap-2 space-y-0">
      <span className="text-sm">{t("deleteConfirm")}</span>
      <SubmitButton variant="destructive">{t("delete")}</SubmitButton>
      <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
        {t("cancel")}
      </Button>
    </ActionForm>
  );
}
