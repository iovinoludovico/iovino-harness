import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { isAllowedEmail } from "@/lib/domain";
import { publicUrl } from "@/lib/public-url";

const PUBLIC_PATHS = ["/login", "/auth/callback", "/unauthorized"];

// Refreshes the Supabase session cookie and performs the optimistic auth checks:
// signed in + institutional email. Authorization (roles) is enforced by RLS and
// by the server-side helpers in lib/auth.ts.
export async function updateSession(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        },
      },
    }
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  if (!user && !isPublic) {
    const search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname)}`;
    return NextResponse.redirect(publicUrl(request, `/login${search}`));
  }

  if (user && !isAllowedEmail(user.email) && pathname !== "/unauthorized") {
    await supabase.auth.signOut();
    return NextResponse.redirect(publicUrl(request, "/unauthorized"));
  }

  if (user && pathname === "/login") {
    return NextResponse.redirect(publicUrl(request, "/"));
  }

  return response;
}
