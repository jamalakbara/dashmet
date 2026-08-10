import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = [
  "/login",
  "/signup",
  "/verify-email",
  "/accept-invite",
  "/forgot-password",
  "/reset-password",
];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get("access_token")?.value;

  const isPublicPath = PUBLIC_PATHS.some((p) => pathname.startsWith(p));

  // Unauthenticated user trying to access a protected route → login
  if (!token && !isPublicPath) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Authenticated user visiting auth pages → dashboard
  if (token && isPublicPath) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return NextResponse.next();
}

export const config = {
  // Exclude API, Next internals, and any path with a file extension (public/
  // static assets like /logo.svg, /meta-logo.svg) — otherwise an unauthenticated
  // <img src="/logo.svg"> gets redirected to /login and renders as a broken image.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
