import { NextRequest, NextResponse } from "next/server";
import { updateEpisode, deleteEpisode, closeVoting, getEpisodeById, getVoteOptions } from "@/lib/db";

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const id = parseInt(params.id, 10);
  if (isNaN(id)) {
    return NextResponse.json({ error: "Invalid ID" }, { status: 400 });
  }

  const episode = await getEpisodeById(id);
  if (!episode) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const vote_options = await getVoteOptions(id);
  return NextResponse.json({ episode, vote_options });
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const id = parseInt(params.id, 10);
  if (isNaN(id)) {
    return NextResponse.json({ error: "Invalid ID" }, { status: 400 });
  }

  const body = await request.json();
  const fields = ["title", "title_zh", "status", "video_url", "thumbnail_url", "voting_open", "admin_prompt", "admin_prompt_weight"] as const;
  const updates: Record<string, unknown> = {};
  for (const key of fields) {
    if (body[key] !== undefined) updates[key] = body[key];
  }

  await updateEpisode(id, updates);

  if (voting_open === false) {
    await closeVoting(id);
  }

  return NextResponse.json({ success: true });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const id = parseInt(params.id, 10);
  if (isNaN(id)) {
    return NextResponse.json({ error: "Invalid ID" }, { status: 400 });
  }

  await deleteEpisode(id);
  return NextResponse.json({ success: true });
}
