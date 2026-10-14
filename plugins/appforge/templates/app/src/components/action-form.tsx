"use client";

import { useActionState, useEffect, useRef } from "react";
import { useFormStatus } from "react-dom";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import type { ActionState } from "@/lib/action-state";
import { cn } from "@/lib/utils";

type Props = {
  action: (state: ActionState, formData: FormData) => Promise<ActionState>;
  children: React.ReactNode | ((state: ActionState) => React.ReactNode);
  className?: string;
  resetOnSuccess?: boolean;
  onSuccess?: (state: NonNullable<ActionState>) => void;
};

// Form bound to a server action returning ActionState: shows errors inline and
// success messages as toasts.
export function ActionForm({ action, children, className, resetOnSuccess, onSuccess }: Props) {
  const [state, formAction] = useActionState(action, null);
  const ref = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (state?.ok) {
      if (state.message) toast.success(state.message);
      if (resetOnSuccess) ref.current?.reset();
      onSuccess?.(state);
    } else if (state?.error && !state.fieldErrors) {
      toast.error(state.error);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  return (
    <form ref={ref} action={formAction} className={cn("space-y-4", className)}>
      {state?.error && state.fieldErrors && <p className="text-sm text-destructive">{state.error}</p>}
      {typeof children === "function" ? children(state) : children}
    </form>
  );
}

export function SubmitButton({ children, disabled, ...props }: React.ComponentProps<typeof Button>) {
  const { pending } = useFormStatus();
  const t = useTranslations("common");
  return (
    <Button type="submit" {...props} disabled={pending || disabled}>
      {pending ? t("wait") : children}
    </Button>
  );
}
