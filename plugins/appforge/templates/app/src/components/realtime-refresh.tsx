"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

// Subscribes to a Supabase Realtime broadcast channel fed by `broadcast`
// reactions (public.broadcast) and refreshes the page when a message arrives.
// The payload carries only type and ids: data is re-read through RLS.
export function RealtimeRefresh({ channel, onMessage }: { channel: string; onMessage?: (payload: unknown) => void }) {
  const router = useRouter();
  useEffect(() => {
    const supabase = createClient();
    const sub = supabase
      .channel(channel)
      .on("broadcast", { event: "*" }, (msg) => {
        onMessage?.(msg.payload);
        router.refresh();
      })
      .subscribe();
    return () => {
      void supabase.removeChannel(sub);
    };
  }, [channel, onMessage, router]);
  return null;
}
