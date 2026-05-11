import { NextRequest, NextResponse } from "next/server";
import { getGenerationRuns, getGenerationRun, clearGenerationRuns, loadStore } from "@/lib/db";
import fs from "fs";
import path from "path";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const episodeId = searchParams.get("episode_id");
  const runId = searchParams.get("id");

  if (runId) {
    const run = await getGenerationRun(parseInt(runId, 10));
    if (!run) return NextResponse.json({ error: "Not found" }, { status: 404 });
    return NextResponse.json({ run });
  }

  const runs = await getGenerationRuns(
    episodeId ? parseInt(episodeId, 10) : undefined
  );
  return NextResponse.json({ runs });
}

export async function DELETE(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const episodeId = searchParams.get("episode_id");

  // Delete raw output files and step subfolders for this episode
  if (episodeId) {
    const store = loadStore();
    const episode = store.episodes.find((e) => e.id === parseInt(episodeId, 10));
    if (episode) {
      const story = store.stories.find((s) => s.id === episode.story_id);
      if (story) {
        const epDir = path.join(PROJECT_ROOT, "data", "stories", story.slug, "episodes", String(episode.episode_number));
        if (fs.existsSync(epDir)) {
          // Delete legacy *_raw_*.txt files
          const files = fs.readdirSync(epDir);
          for (const file of files) {
            if (/_raw_\d{8}_\d{6}\.txt$/.test(file)) {
              fs.unlinkSync(path.join(epDir, file));
            }
          }
          // Delete step subfolders
          const stepFolders = ["script", "scenes", "characters", "clips", "quality", "audio", "final", "publish"];
          for (const folder of stepFolders) {
            const stepDir = path.join(epDir, folder);
            if (fs.existsSync(stepDir)) {
              fs.rmSync(stepDir, { recursive: true, force: true });
            }
          }
          // Delete root-level YAML files produced by pipeline steps
          const rootFiles = ["script.yaml", "scenes_breakdown.yaml", "characters.yaml", "audio_plan.yaml", "edit_plan.yaml", "publish.yaml"];
          for (const file of rootFiles) {
            const filePath = path.join(epDir, file);
            if (fs.existsSync(filePath)) {
              fs.unlinkSync(filePath);
            }
          }
        }
      }
    }
  }

  await clearGenerationRuns(episodeId ? parseInt(episodeId, 10) : undefined);
  return NextResponse.json({ success: true });
}
