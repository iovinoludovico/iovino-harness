import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { isAllowedEmail } from "@/lib/domain";
import { LOCALE_COOKIE, isLocale } from "@/i18n/config";
import { publicUrl, safeRedirectPath } from "@/lib/public-url";

// OAuth / magic-link callback: exchanges the code for a session, then re-checks the domain.
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const code = searchParams.get("code");
  const safeNext = safeRedirectPath(searchParams.get("next"));

  // Errors returned by Supabase Auth (e.g. the domain hook rejecting the sign-up).
  if (searchParams.get("error")) {
    return NextResponse.redirect(publicUrl(request, "/unauthorized?reason=domain"));
  }
  if (!code) {
    return NextResponse.redirect(publicUrl(request, "/login"));
  }

  const supabase = await createClient();
  const { data, error } = await supabase.auth.exchangeCodeForSession(code);
  if (error || !isAllowedEmail(data.user?.email)) {
    await supabase.auth.signOut();
    return NextResponse.redirect(publicUrl(request, "/unauthorized?reason=domain"));
  }

  // Language: a choice made before signing in (cookie) wins and is stored on the
  // profile; otherwise the profile's language becomes the cookie.
  const response = NextResponse.redirect(publicUrl(request, safeNext));
  const cookieLocale = request.cookies.get(LOCALE_COOKIE)?.value;
  if (isLocale(cookieLocale)) {
    await supabase.rpc("set_my_locale", { p_locale: cookieLocale });
  } else {
    const { data: profile } = await supabase
      .from("profiles")
      .select("locale")
      .eq("auth_user_id", data.user!.id)
      .maybeSingle();
    if (isLocale(profile?.locale)) {
      response.cookies.set(LOCALE_COOKIE, profile.locale, { path: "/", maxAge: 60 * 60 * 24 * 365, sameSite: "lax" });
    }
  }
  return response;
}
