import { NextRequest, NextResponse } from "next/server";
import { getComments, addComment } from "@/lib/db";

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const episodeId = parseInt(params.id, 10);
  if (isNaN(episodeId)) {
    return NextResponse.json({ error: "Invalid episode ID" }, { status: 400 });
  }

  const comments = await getComments(episodeId);
  return NextResponse.json({ comments });
}

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const episodeId = parseInt(params.id, 10);
  if (isNaN(episodeId)) {
    return NextResponse.json({ error: "Invalid episode ID" }, { status: 400 });
  }

  const body = await request.json();
  const { author, content } = body;

  if (!author || !content) {
    return NextResponse.json(
      { error: "Author and content are required" },
      { status: 400 }
    );
  }

  const result = await addComment(episodeId, author, content);

  if (!result.success) {
    return NextResponse.json({ error: result.error }, { status: 400 });
  }

  return NextResponse.json({ success: true, id: result.id }, { status: 201 });
}
