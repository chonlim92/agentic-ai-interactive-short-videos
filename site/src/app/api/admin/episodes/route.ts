import { NextResponse } from "next/server";
import { getAllEpisodes, createEpisode } from "@/lib/db";

export async function GET() {
  const episodes = await getAllEpisodes();
  return NextResponse.json({ episodes });
}

export async function POST(request: Request) {
  const body = await request.json();
  const { story_id, episode_number, title, title_zh, video_url, thumbnail_url, voting_options, admin_prompt, admin_prompt_weight } = body;

  if (!story_id || !episode_number || !title) {
    return NextResponse.json(
      { error: "story_id, episode_number, and title are required" },
      { status: 400 }
    );
  }

  const id = await createEpisode({
    story_id: Number(story_id),
    episode_number: Number(episode_number),
    title,
    title_zh,
    video_url,
    thumbnail_url,
    voting_options,
    admin_prompt,
    admin_prompt_weight,
  });

  return NextResponse.json({ success: true, id }, { status: 201 });
}
