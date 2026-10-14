"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ActionForm, SubmitButton } from "@/components/action-form";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { ActionState } from "@/lib/action-state";
import { pickLabel } from "@/i18n/config";

export type TransitionView = {
  key: string;
  labels: Record<string, string>;
  to: { key: string; labels: Record<string, string> };
  comment: "optional" | "required" | "none";
  /** Guard clauses not satisfied yet, already described. */
  unmet: string[];
};

// Workflow actions available to the current user. Selecting one opens a small
// confirmation form with an (optionally mandatory) comment.
export function TransitionActions({
  transitions,
  action,
}: {
  transitions: TransitionView[];
  /** Server action (transition key, state, form data). */
  action: (transitionKey: string, state: ActionState, formData: FormData) => Promise<ActionState>;
}) {
  const t = useTranslations("records");
  const tc = useTranslations("common");
  const locale = useLocale();
  const [selected, setSelected] = useState<TransitionView | null>(null);

  if (!transitions.length) return <p className="text-sm text-muted-foreground">{t("noActions")}</p>;

  if (selected) {
    return (
      <ActionForm key={selected.key} action={action.bind(null, selected.key)} onSuccess={() => setSelected(null)} className="space-y-3">
        <p className="text-sm">
          {t("transitionConfirm", { label: pickLabel(selected.labels, locale), state: pickLabel(selected.to.labels, locale) })}
        </p>
        {selected.comment !== "none" && (
          <Textarea
            name="comment"
            rows={3}
            placeholder={selected.comment === "required" ? t("commentRequired") : t("commentOptional")}
            required={selected.comment === "required"}
          />
        )}
        <div className="flex gap-2">
          <SubmitButton>{tc("confirm")}</SubmitButton>
          <Button type="button" variant="ghost" onClick={() => setSelected(null)}>
            {tc("cancel")}
          </Button>
        </div>
      </ActionForm>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap justify-end gap-2">
        {transitions.map((tr) => (
          <Button
            key={tr.key}
            variant={tr.to.key.includes("cancel") || tr.key.includes("reject") ? "outline" : "default"}
            disabled={tr.unmet.length > 0}
            title={tr.unmet.length ? t("blockedAction") : undefined}
            onClick={() => setSelected(tr)}
          >
            {pickLabel(tr.labels, locale)}
          </Button>
        ))}
      </div>
      {transitions
        .filter((tr) => tr.unmet.length > 0)
        .map((tr) => (
          <p key={tr.key} className="text-right text-sm text-destructive">
            {t("unmetRequirements", { action: pickLabel(tr.labels, locale), missing: tr.unmet.join("; ") })}
          </p>
        ))}
    </div>
  );
}
