import { NextRequest, NextResponse } from "next/server";
import { updateStory, getStoryById, getStory } from "@/lib/db";
import { syncStoryYaml } from "@/lib/story-yaml";

/** Resolve a story ID or slug to a numeric ID. */
async function resolveStoryId(idOrSlug: string): Promise<number | null> {
  const numeric = parseInt(idOrSlug, 10);
  if (!isNaN(numeric)) return numeric;
  // Treat as slug
  const story = await getStory(idOrSlug);
  return story ? story.id : null;
}

export async function GET(
  _request: NextRequest,
  { params }: { params: { id: string } }
) {
  const id = await resolveStoryId(params.id);
  if (id === null) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  const story = await getStoryById(id);
  if (!story) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
  return NextResponse.json(story);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const id = await resolveStoryId(params.id);
  if (id === null) {
    return NextResponse.json({ error: "Invalid ID or slug" }, { status: 400 });
  }

  const body = await request.json();
  const fields = ["title", "title_zh", "description", "description_zh", "background", "status", "poster_episode_id", "selected_poster_en", "selected_poster_zh"] as const;
  const updates: Record<string, unknown> = {};
  for (const key of fields) {
    if (body[key] !== undefined) updates[key] = body[key];
  }

  await updateStory(id, updates);

  // Sync YAML files with updated story data
  const story = await getStoryById(id);
  if (story) {
    syncStoryYaml({
      title: story.title,
      title_zh: story.title_zh,
      slug: story.slug,
      description: story.description,
      description_zh: story.description_zh,
      background: story.background,
    });
  }

  return NextResponse.json({ success: true });
}
