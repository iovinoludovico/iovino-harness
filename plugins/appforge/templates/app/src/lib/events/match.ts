/** Glob match on event types, same semantics as public.event_type_matches(): '*' = any sequence. */
export function eventTypeMatches(pattern: string, type: string): boolean {
  const re = new RegExp("^" + pattern.split("*").map((p) => p.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*") + "$");
  return re.test(type);
}
