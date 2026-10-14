"use client";

import * as React from "react";
import { Combobox } from "@base-ui/react/combobox";
import { useTranslations } from "next-intl";
import { Check, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";

export type SelectOption = { value: string; label: string; hint?: string | null };

type Props = {
  options: SelectOption[];
  /** Submitted with the enclosing form (hidden input). */
  name?: string;
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  /** Put on the trigger, so a <label htmlFor> focuses it. */
  id?: string;
  className?: string;
  "aria-label"?: string;
};

const normalize = (s: string) =>
  s
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();

// Select with a search box in its popup. Used instead of native <select> across
// the app: works with Server Actions and GET filter forms through `name`.
export function SearchableSelect({
  options,
  name,
  value,
  defaultValue,
  onValueChange,
  placeholder,
  required,
  disabled,
  id,
  className,
  "aria-label": ariaLabel,
}: Props) {
  const t = useTranslations("select");
  const [inner, setInner] = React.useState(defaultValue ?? "");
  const current = value ?? inner;

  const items = React.useMemo(
    () => Combobox.createItems(options, { getValue: (o) => o.value, getLabel: (o) => o.label }),
    [options]
  );
  const selected = options.find((o) => o.value === current);

  return (
    <Combobox.Root
      items={items}
      name={name}
      required={required}
      disabled={disabled}
      value={selected ? current : null}
      onValueChange={(next) => {
        const v = (next as string | null) ?? "";
        if (value === undefined) setInner(v);
        onValueChange?.(v);
      }}
      filter={(option, query) => {
        const o = option as SelectOption;
        const q = normalize(query.trim());
        return !q || normalize(`${o.label} ${o.hint ?? ""}`).includes(q);
      }}
      autoHighlight
    >
      <Combobox.Trigger
        id={id}
        aria-label={ariaLabel}
        className={cn(
          "flex h-10 w-full min-w-0 items-center justify-between gap-2 rounded-[10px] border border-input bg-card px-3 text-left text-[15px] outline-none select-none",
          "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 data-popup-open:border-ring",
          "disabled:cursor-not-allowed disabled:opacity-50 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-60",
          className
        )}
      >
        <span className={cn("truncate", !selected && "text-muted-foreground")}>
          {selected?.label ?? placeholder ?? t("placeholder")}
        </span>
        <Combobox.Icon className="shrink-0 text-muted-foreground">
          <ChevronsUpDown className="size-4" />
        </Combobox.Icon>
      </Combobox.Trigger>
      <Combobox.Portal>
        <Combobox.Positioner align="start" sideOffset={4} className="z-50 outline-none">
          <Combobox.Popup
            aria-label={ariaLabel ?? placeholder ?? t("placeholder")}
            className="w-[max(var(--anchor-width),18rem)] max-w-[var(--available-width)] origin-(--transform-origin) overflow-hidden rounded-xl bg-popover text-popover-foreground shadow-lg ring-1 ring-foreground/10 transition-[scale,opacity] duration-100 data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0"
          >
            <div className="border-b p-2">
              <Combobox.Input
                placeholder={t("search")}
                className="h-9 w-full rounded-lg border border-input bg-card px-3 text-[15px] outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-3 focus:ring-ring/40"
              />
            </div>
            <Combobox.Empty>
              <p className="px-3 py-4 text-sm text-muted-foreground">{t("empty")}</p>
            </Combobox.Empty>
            <Combobox.List className="max-h-[min(20rem,calc(var(--available-height)-4rem))] overflow-y-auto overscroll-contain p-1 empty:p-0">
              {(option: SelectOption) => (
                <Combobox.Item
                  key={option.value}
                  value={option.value}
                  className="grid cursor-default grid-cols-[1rem_1fr] items-start gap-2 rounded-lg px-2 py-2 text-[15px] outline-none select-none data-highlighted:bg-secondary data-highlighted:text-secondary-foreground"
                >
                  <Combobox.ItemIndicator className="col-start-1 pt-0.5 text-primary">
                    <Check className="size-4" />
                  </Combobox.ItemIndicator>
                  <span className="col-start-2 min-w-0">
                    <span className="block truncate">{option.label}</span>
                    {option.hint && <span className="block truncate text-xs text-muted-foreground">{option.hint}</span>}
                  </span>
                </Combobox.Item>
              )}
            </Combobox.List>
          </Combobox.Popup>
        </Combobox.Positioner>
      </Combobox.Portal>
    </Combobox.Root>
  );
}
