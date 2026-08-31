import { NextRequest, NextResponse } from "next/server";

/**
 * RECON OS — Phase 5: route protection (UX layer only).
 *
 * This ONLY checks whether the session cookie is present — it cannot
 * validate it (no DB access at the edge). Every actual authorization
 * decision is made server-side per API call (see apps/api/auth.py); this
 * middleware exists solely so an unauthenticated visitor is redirected to
 * /login instead of seeing a broken, half-loaded page of 401 errors.
 */
const SESSION_COOKIE_NAME = "recon_session";

const PUBLIC_PATHS = [
  "/login",
  "/register",
  "/forgot-password",
  "/reset-password",
  "/session-expired",
];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE_NAME)?.value);

  if (!isPublic && !hasSession) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (isPublic && hasSession && pathname !== "/session-expired") {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|webp|ico)$).*)"],
};
