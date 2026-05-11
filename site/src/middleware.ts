import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Middleware to prevent browser caching of HTML pages.
 * Ensures fresh content is always fetched on navigation and refresh.
 */
export function middleware(request: NextRequest) {
  const response = NextResponse.next();

  // Prevent browser from caching HTML pages and RSC payloads
  response.headers.set("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0");
  response.headers.set("Pragma", "no-cache");
  response.headers.set("Expires", "0");

  return response;
}

export const config = {
  // Match page routes only, not API routes or static assets
  matcher: [
    "/((?!api|_next/static|_next/image|favicon|logo|apple-touch-icon|manifest).*)",
  ],
};
