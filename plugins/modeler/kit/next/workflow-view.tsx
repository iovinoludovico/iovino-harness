"use client";

// The workflow of a record (installed by the modeler plugin, upgraded by re-running `modeler install`): the state
// diagram of the entity's workflow (behavior.json) with the state the record is in, drawn by the framework-free
// <workflow-view> of public/modeler/metamodel-editor.js (the same layout as the modeler's panel): the current state
// filled with its colour, the transitions leaving it at full strength, the others dimmed. Laid out at the width of
// the container, scrolls horizontally below the width of the longest state name. Renders nothing when the entity
// has no workflow. The record pages of the app use it:
//
//   import behavior from "@/lib/modeler/behavior.json";
//   <WorkflowView behavior={behavior} entity="Task" state={row.state} lang="it" />

import Script from "next/script";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type DetailedHTMLProps, type HTMLAttributes } from "react";
import type { Behavior } from "./behavior-view";

type Props = {
  behavior: unknown;          // src/lib/modeler/behavior.json
  entity: string;             // the class name (key of behavior.workflows)
  state: string | null;       // the current value of the state attribute of the record
  lang?: string;
  theme?: "light" | "dark";   // omitted: the element follows the page (html.dark / data-theme / the body's background)
  className?: string;
  style?: CSSProperties;
};

type ViewElement = HTMLElement & { workflow: unknown; roles: unknown; state: string | null };

declare module "react" {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "workflow-view": DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
        lang?: string;
        name?: string;
        state?: string;
        theme?: string;
      };
    }
  }
}

export function WorkflowView({ behavior, entity, state, lang = "it", theme, className, style }: Props) {
  const ref = useRef<ViewElement | null>(null);
  const [ready, setReady] = useState(false);
  const workflow = useMemo(() => (behavior as Behavior | null)?.workflows?.[entity] ?? null, [behavior, entity]);
  const roles = useMemo(() => (behavior as Behavior | null)?.roles ?? null, [behavior]);

  useEffect(() => {
    let alive = true;
    customElements.whenDefined("workflow-view").then(() => alive && setReady(true));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (ready && ref.current) {
      ref.current.roles = roles;         // the recipients of the notifications with the labels of the roles
      ref.current.workflow = workflow;
    }
  }, [ready, workflow, roles]);

  if (!workflow) return null;
  return (
    <>
      <Script src="/modeler/metamodel-editor.js" strategy="afterInteractive" />
      <workflow-view
        ref={ref}
        lang={lang}
        name={entity}
        state={state ?? undefined}
        theme={theme}
        className={className}
        style={{ display: "block", minHeight: 120, ...style }}
      />
    </>
  );
}
