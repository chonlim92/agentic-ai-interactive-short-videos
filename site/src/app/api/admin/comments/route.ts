import { NextRequest, NextResponse } from "next/server";
import { getAllComments, moderateComment } from "@/lib/db";

export async function GET() {
  const comments = await getAllComments();
  return NextResponse.json({ comments });
}

export async function PATCH(request: NextRequest) {
  const body = await request.json();
  const { id, action } = body;

  if (!id || !["approve", "flag", "delete"].includes(action)) {
    return NextResponse.json(
      { error: "id and action (approve|flag|delete) required" },
      { status: 400 }
    );
  }

  await moderateComment(id, action);
  return NextResponse.json({ success: true });
}
