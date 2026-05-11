// Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
// Licensed under CC BY-NC 4.0. See LICENSE for details.
import { cookies } from "next/headers";

const ADMIN_COOKIE = "storysmith_admin_session";
const SESSION_SECRET = process.env.ADMIN_SESSION_SECRET || "storysmith-default-secret-change-me";

/**
 * Create a simple HMAC-like token from the secret.
 * In production, use a proper JWT library.
 */
function createToken(): string {
  const payload = `admin:${Date.now()}:${SESSION_SECRET}`;
  // Simple base64 encoding — not cryptographically secure for production,
  // but sufficient for a local/demo admin panel
  return Buffer.from(payload).toString("base64");
}

function validateToken(token: string): boolean {
  try {
    const decoded = Buffer.from(token, "base64").toString("utf-8");
    return decoded.includes(SESSION_SECRET) && decoded.startsWith("admin:");
  } catch {
    return false;
  }
}

export function setAdminSession(): string {
  const token = createToken();
  return token;
}

export function isAdminAuthenticated(): boolean {
  const cookieStore = cookies();
  const session = cookieStore.get(ADMIN_COOKIE);
  if (!session) return false;
  return validateToken(session.value);
}

export const ADMIN_COOKIE_NAME = ADMIN_COOKIE;
