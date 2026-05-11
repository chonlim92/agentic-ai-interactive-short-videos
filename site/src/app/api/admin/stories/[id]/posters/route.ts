import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import { getStoryById, getEpisodesByStory, getStory } from "@/lib/db";

const DATA_ROOT = path.resolve(process.cwd(), "..", "data", "stories");

/** Resolve a story ID or slug to a numeric ID. */
async function resolveStoryId(idOrSlug: string): Promise<number | null> {
  const numeric = parseInt(idOrSlug, 10);
  if (!isNaN(numeric)) return numeric;
  const story = await getStory(idOrSlug);
  return story ? story.id : null;
}

/** Scan a directory for poster image files and return a map of variant name → API URL. */
function scanPosterDir(dirPath: string, urlPrefix: string): Record<string, string> {
  if (!fs.existsSync(dirPath)) return {};
  const files = fs
    .readdirSync(dirPath)
    .filter((f) => /^poster_.+\.(jpg|png)$/.test(f));
  const posters: Record<string, string> = {};
  for (const file of files) {
    const variantName = file.replace(/^poster_/, "").replace(/\.(jpg|png)$/, "");
    posters[variantName] = `${urlPrefix}/${file}`;
  }
  return posters;
}

/**
 * GET /api/admin/stories/[id]/posters
 * Returns available poster sets for a story:
 * - Story-level posters from `{slug}/poster/`
 * - Episode-level posters from `{slug}/episodes/{N}/final/poster/`
 * - Legacy episode posters from `{slug}/posters/ep{N}/`
 */
export async function GET(
  _request: Request,
  { params }: { params: { id: string } }
) {
  const id = await resolveStoryId(params.id);
  if (id === null) {
    return NextResponse.json({ error: "Invalid ID or slug" }, { status: 400 });
  }

  const story = await getStoryById(id);
  if (!story) {
    return NextResponse.json({ error: "Story not found" }, { status: 404 });
  }

  const episodes = await getEpisodesByStory(id);
  const posterSets: {
    episode_id: number;
    episode_number: number;
    episode_title: string;
    posters: Record<string, string>;
  }[] = [];

  for (const ep of episodes) {
    // New path: episodes/{N}/final/poster/
    const newDir = path.join(
      DATA_ROOT, story.slug, "episodes", String(ep.episode_number), "final", "poster"
    );
    // Legacy path: posters/ep{N}/
    const legacyDir = path.join(DATA_ROOT, story.slug, "posters", `ep${ep.episode_number}`);

    const posters = {
      ...scanPosterDir(
        legacyDir,
        `/api/assets/${story.slug}/posters/ep${ep.episode_number}`
      ),
      // New path takes precedence over legacy
      ...scanPosterDir(
        newDir,
        `/api/assets/${story.slug}/episodes/${ep.episode_number}/final/poster`
      ),
    };

    if (Object.keys(posters).length === 0) continue;

    posterSets.push({
      episode_id: ep.id,
      episode_number: ep.episode_number,
      episode_title: ep.title,
      posters,
    });
  }

  // Story-level posters from {slug}/poster/
  const storyPosterDir = path.join(DATA_ROOT, story.slug, "poster");
  const storyPosters = scanPosterDir(
    storyPosterDir,
    `/api/assets/${story.slug}/poster`
  );

  return NextResponse.json({
    story_id: id,
    poster_episode_id: story.poster_episode_id,
    poster_sets: posterSets,
    story_posters: storyPosters,
  });
}
