import { NextRequest, NextResponse } from "next/server";
import { getEpisode, getVoteOptions, updateEpisode, deleteEpisode, closeVoting, getStory } from "@/lib/db";

/** Resolve a story ID or slug to a numeric ID. */
async function resolveStoryId(idOrSlug: string): Promise<number | null> {
  const numeric = parseInt(idOrSlug, 10);
  if (!isNaN(numeric)) return numeric;
  const story = await getStory(idOrSlug);
  return story ? story.id : null;
}

export async function GET(
  request: NextRequest,
  { params }: { params: { id: string; episodeNumber: string } }
) {
  const storyId = await resolveStoryId(params.id);
  const episodeNumber = parseInt(params.episodeNumber, 10);
  if (storyId === null || isNaN(episodeNumber)) {
    return NextResponse.json({ error: "Invalid parameters" }, { status: 400 });
  }

  const episode = await getEpisode(episodeNumber, storyId);
  if (!episode) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const vote_options = await getVoteOptions(episode.id);
  return NextResponse.json({ episode, vote_options });
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string; episodeNumber: string } }
) {
  const storyId = await resolveStoryId(params.id);
  const episodeNumber = parseInt(params.episodeNumber, 10);
  if (storyId === null || isNaN(episodeNumber)) {
    return NextResponse.json({ error: "Invalid parameters" }, { status: 400 });
  }

  const episode = await getEpisode(episodeNumber, storyId);
  if (!episode) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const body = await request.json();
  const fields = ["title", "title_zh", "status", "video_url", "thumbnail_url", "voting_open", "admin_prompt", "admin_prompt_weight"] as const;
  const updates: Record<string, unknown> = {};
  for (const key of fields) {
    if (body[key] !== undefined) updates[key] = body[key];
  }

  await updateEpisode(episode.id, updates);

  if (voting_open === false) {
    await closeVoting(episode.id);
  }

  return NextResponse.json({ success: true });
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { id: string; episodeNumber: string } }
) {
  const storyId = await resolveStoryId(params.id);
  const episodeNumber = parseInt(params.episodeNumber, 10);
  if (storyId === null || isNaN(episodeNumber)) {
    return NextResponse.json({ error: "Invalid parameters" }, { status: 400 });
  }

  const episode = await getEpisode(episodeNumber, storyId);
  if (!episode) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  await deleteEpisode(episode.id);
  return NextResponse.json({ success: true });
}
