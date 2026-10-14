import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

// Server-side client bound to the request cookies: queries run as the signed-in
// user, so every authorization rule of the database (RLS, RPC checks) applies.
// Untyped on purpose: the generic pages address tables by name from the model.
// Hand-written code can use the generated types: `npm run db:types`, then
// `createServerClient<Database>(...)` from "@/lib/database.types".
export async function createClient() {
  const cookieStore = await cookies();
  return createServerClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
        } catch {
          // Called from a Server Component: safe to ignore, the proxy refreshes the session.
        }
      },
    },
  });
}
