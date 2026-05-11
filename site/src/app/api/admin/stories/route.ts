import { NextResponse } from "next/server";
import { getAllStories, createStory } from "@/lib/db";
import { syncStoryYaml } from "@/lib/story-yaml";

export async function GET() {
  const stories = await getAllStories();
  return NextResponse.json({ stories });
}

export async function POST(request: Request) {
  const body = await request.json();
  const { title, title_zh, slug, description, description_zh, background } = body;

  if (!title || !slug) {
    return NextResponse.json({ error: "title and slug required" }, { status: 400 });
  }

  const storyData = {
    title,
    title_zh: title_zh || title,
    slug,
    description: description || "",
    description_zh: description_zh || description || "",
    background: background || "",
  };

  const id = await createStory(storyData);

  // Create story data folder structure and populate YAML files
  syncStoryYaml(storyData);

  return NextResponse.json({ success: true, id }, { status: 201 });
}
