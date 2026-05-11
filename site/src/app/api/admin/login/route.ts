import { NextResponse } from "next/server";
import { verifyAdminPassword } from "@/lib/db";
import { setAdminSession, ADMIN_COOKIE_NAME } from "@/lib/auth";

export async function POST(request: Request) {
  const body = await request.json();
  const { password } = body;

  if (!password) {
    return NextResponse.json({ error: "Password required" }, { status: 400 });
  }

  const valid = await verifyAdminPassword(password);
  if (!valid) {
    return NextResponse.json({ error: "Invalid password" }, { status: 401 });
  }

  const token = setAdminSession();
  const response = NextResponse.json({ success: true });
  const timeoutHours = parseInt(process.env.ADMIN_SESSION_TIMEOUT_HOURS || "24", 10);
  response.cookies.set(ADMIN_COOKIE_NAME, token, {
    httpOnly: true,
    sameSite: "strict",
    maxAge: 60 * 60 * timeoutHours,
    path: "/",
  });

  return response;
}
