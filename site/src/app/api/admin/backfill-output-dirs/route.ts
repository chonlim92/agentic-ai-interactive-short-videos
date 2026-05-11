import { NextResponse } from "next/server";
import { loadStore, saveStore } from "@/lib/db";
import fs from "fs";
import path from "path";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");

const STEP_TO_FOLDER: Record<string, string> = {
  generate_script: "script",
  plan_scenes: "scenes",
  design_characters: "characters",
  add_audio: "audio",
  compose_episode: "compose",
  publish: "publish",
};

// Pattern to extract the saved file path from run output logs
// e.g. "Script saved to C:\...\script\20260507_001903\script.yaml"
// or more generically: "saved to <path>"
const SAVED_TO_REGEX = /saved to\s+(.+?)[\r\n]/i;

function extractOutputDir(output: string, stepFolder: string): string | null {
  const match = output.match(SAVED_TO_REGEX);
  if (!match) return null;

  const savedPath = match[1].trim();
  // Extract the timestamp folder from the path
  // The path contains: .../episodes/<num>/<stepFolder>/<YYYYMMDD_HHMMSS>/filename
  const parts = savedPath.replace(/\\/g, "/").split("/");
  const folderIdx = parts.findIndex((p) => p === stepFolder);
  if (folderIdx >= 0 && folderIdx + 1 < parts.length) {
    const tsFolder = parts[folderIdx + 1];
    // Validate it looks like a timestamp folder (YYYYMMDD_HHMMSS)
    if (/^\d{8}_\d{6}$/.test(tsFolder)) {
      return tsFolder;
    }
  }
  return null;
}

/**
 * POST /api/admin/backfill-output-dirs
 * One-time backfill: reads run logs, extracts actual output folder names,
 * stores them in DB, then deletes orphan folders.
 */
export async function POST() {
  const store = loadStore();
  const backfilled: { run_id: number; step_id: string; output_dir: string }[] = [];
  const knownDirs: Map<string, Set<string>> = new Map(); // key: "storySlug/epNum/stepFolder" → set of ts folders

  // Step 1: Backfill output_dir from logs
  for (const run of store.generation_runs) {
    const story = store.stories.find((s: { id: number }) => s.id === run.story_id);
    const episode = store.episodes.find((e: { id: number }) => e.id === run.episode_id);
    if (!story || !episode) continue;

    for (const step of run.steps) {
      const stepFolder = STEP_TO_FOLDER[step.step_id];
      if (!stepFolder) continue;

      // Try to extract from output log
      if (step.output && !step.output_dir) {
        const dir = extractOutputDir(step.output, stepFolder);
        if (dir) {
          step.output_dir = dir;
          backfilled.push({ run_id: run.id, step_id: step.step_id, output_dir: dir });
        }
      }

      // Track known dirs
      if (step.output_dir) {
        const key = `${story.slug}/${episode.episode_number}/${stepFolder}`;
        if (!knownDirs.has(key)) knownDirs.set(key, new Set());
        knownDirs.get(key)!.add(step.output_dir);
      }
    }
  }

  saveStore(store);

  // Step 2: Delete orphan folders
  const deleted: string[] = [];
  for (const [key, validDirs] of Array.from(knownDirs.entries())) {
    const [slug, epNum, stepFolder] = key.split("/");
    const stepDir = path.join(PROJECT_ROOT, "data", "stories", slug, "episodes", epNum, stepFolder);
    if (!fs.existsSync(stepDir)) continue;

    for (const entry of fs.readdirSync(stepDir)) {
      const entryPath = path.join(stepDir, entry);
      if (!fs.statSync(entryPath).isDirectory()) continue;
      // Only consider timestamp-shaped folders
      if (!/^\d{8}_\d{6}$/.test(entry)) continue;
      if (!validDirs.has(entry)) {
        fs.rmSync(entryPath, { recursive: true, force: true });
        deleted.push(`${key}/${entry}`);
      }
    }
  }

  // Also check step folders that have runs but no output_dir found (scan anyway)
  for (const story of store.stories) {
    for (const episode of store.episodes) {
      if (episode.story_id !== story.id) continue;
      for (const [stepId, stepFolder] of Object.entries(STEP_TO_FOLDER)) {
        const key = `${story.slug}/${episode.episode_number}/${stepFolder}`;
        if (knownDirs.has(key)) continue; // already handled above
        
        // No runs have output_dir for this step - check if folder exists with subfolders
        const stepDir = path.join(PROJECT_ROOT, "data", "stories", story.slug, "episodes", String(episode.episode_number), stepFolder);
        if (!fs.existsSync(stepDir)) continue;
        
        // Check if there are any runs at all for this step
        const hasRuns = store.generation_runs.some(
          (r) => r.story_id === story.id && r.episode_id === episode.id && r.steps.some((s) => s.step_id === stepId)
        );
        if (!hasRuns) {
          // No runs at all for this step - delete all timestamp folders
          for (const entry of fs.readdirSync(stepDir)) {
            const entryPath = path.join(stepDir, entry);
            if (!fs.statSync(entryPath).isDirectory()) continue;
            if (/^\d{8}_\d{6}$/.test(entry)) {
              fs.rmSync(entryPath, { recursive: true, force: true });
              deleted.push(`${key}/${entry}`);
            }
          }
        }
      }
    }
  }

  return NextResponse.json({
    backfilled,
    deleted,
    message: `Backfilled ${backfilled.length} output_dirs, deleted ${deleted.length} orphan folders`,
  });
}
