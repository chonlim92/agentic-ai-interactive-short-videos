import { NextRequest, NextResponse } from "next/server";
import { changeAdminPassword, verifyAdminPassword } from "@/lib/db";
import { isAdminAuthenticated } from "@/lib/auth";
import fs from "fs";
import path from "path";

export async function POST(req: NextRequest) {
  if (!isAdminAuthenticated()) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { current_password, new_password } = await req.json();

  if (!current_password || !new_password) {
    return NextResponse.json(
      { error: "Both current_password and new_password are required" },
      { status: 400 }
    );
  }

  if (new_password.length < 6) {
    return NextResponse.json(
      { error: "New password must be at least 6 characters" },
      { status: 400 }
    );
  }

  const valid = await verifyAdminPassword(current_password);
  if (!valid) {
    return NextResponse.json(
      { error: "Current password is incorrect" },
      { status: 403 }
    );
  }

  await changeAdminPassword(new_password);

  // Also update config/.env file
  const envPath = path.resolve(process.cwd(), "..", "config", ".env");
  try {
    if (fs.existsSync(envPath)) {
      let envContent = fs.readFileSync(envPath, "utf-8");
      if (envContent.match(/^ADMIN_DEFAULT_PASSWORD=.*/m)) {
        envContent = envContent.replace(
          /^ADMIN_DEFAULT_PASSWORD=.*/m,
          `ADMIN_DEFAULT_PASSWORD=${new_password}`
        );
      } else {
        envContent += `\nADMIN_DEFAULT_PASSWORD=${new_password}\n`;
      }
      fs.writeFileSync(envPath, envContent);
    }
  } catch {
    // Non-fatal: password is already updated in store
  }

  return NextResponse.json({ success: true });
}
