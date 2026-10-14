"use client";

// Domain modeler of this app (installed by the modeler plugin, upgraded by re-running `modeler install`):
// wraps the framework-free <metamodel-editor> (public/modeler/metamodel-editor.js).
// The page passes the metamodel (src/lib/modeler/metamodel.json) and a server action that stores the proposal.

import Script from "next/script";
import { useEffect, useRef, useState, type DetailedHTMLProps, type HTMLAttributes, type Ref } from "react";

export type ProposalResult = { ok: boolean; message: string };

type Props = {
  metamodel: unknown;
  canEdit: boolean;
  lang?: string;
  saveLabel?: string;
  downloadLabel?: string;
  onSave: (json: string, note: string) => Promise<ProposalResult>;
};

type EditorElement = HTMLElement & { metamodel: unknown };
type SaveDetail = { metamodel: unknown; note: string };

declare module "react" {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "metamodel-editor": DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
        lang?: string;
        "save-label"?: string;
        readonly?: string;
      };
    }
  }
}

export function MetamodelModeler({ metamodel, canEdit, lang = "it", saveLabel, downloadLabel = "Download", onSave }: Props) {
  const ref = useRef<EditorElement | null>(null);
  const [ready, setReady] = useState(false);
  const [result, setResult] = useState<ProposalResult | null>(null);
  const [last, setLast] = useState<SaveDetail | null>(null);

  useEffect(() => {
    let alive = true;
    customElements.whenDefined("metamodel-editor").then(() => alive && setReady(true));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (ready && ref.current) ref.current.metamodel = metamodel;
  }, [ready, metamodel]);

  useEffect(() => {
    const el = ref.current;
    if (!ready || !el) return;
    const handler = async (ev: Event) => {
      const detail = (ev as CustomEvent<SaveDetail>).detail;
      setLast(detail);
      setResult(null);
      try {
        setResult(await onSave(JSON.stringify(detail.metamodel), detail.note));
      } catch (err) {
        setResult({ ok: false, message: err instanceof Error ? err.message : String(err) });
      }
    };
    el.addEventListener("save", handler);
    return () => el.removeEventListener("save", handler);
  }, [ready, onSave]);

  const download = () => {
    if (!last) return;
    const blob = new Blob([JSON.stringify({ note: last.note, created_at: new Date().toISOString(), metamodel: last.metamodel }, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `metamodel-proposal-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="space-y-3">
      <Script src="/modeler/metamodel-editor.js" strategy="afterInteractive" />
      <metamodel-editor
        ref={ref as Ref<HTMLElement>}
        lang={lang}
        save-label={saveLabel}
        readonly={canEdit ? undefined : ""}
        style={{ display: "block", height: "calc(100dvh - 12rem)", minHeight: 560 }}
      />
      {result && (
        <div className={`flex flex-wrap items-center gap-3 text-sm ${result.ok ? "text-green-700 dark:text-green-400" : "text-destructive"}`}>
          <span>{result.message}</span>
          {last && (
            <button type="button" className="underline" onClick={download}>
              {downloadLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
