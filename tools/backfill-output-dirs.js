/**
 * One-time script: backfill output_dir from run logs, delete orphan folders.
 * Run with: node tools/backfill-output-dirs.js
 */
const fs = require("fs");
const path = require("path");

const PROJECT_ROOT = path.resolve(__dirname, "..");
const STORE_PATH = path.join(PROJECT_ROOT, "site", "data", "store.json");

const STEP_TO_FOLDER = {
  generate_script: "script",
  plan_scenes: "scenes",
  design_characters: "characters",
  add_audio: "audio",
  compose_episode: "final",
  publish: "publish",
};

// Pattern: "saved to <full_path>"
const SAVED_TO_REGEX = /saved to\s+(.+?)[\r\n]/i;

function extractOutputDir(output, stepFolder) {
  const match = output.match(SAVED_TO_REGEX);
  if (!match) return null;
  const savedPath = match[1].trim().replace(/\\/g, "/");
  const parts = savedPath.split("/");
  const folderIdx = parts.findIndex((p) => p === stepFolder);
  if (folderIdx >= 0 && folderIdx + 1 < parts.length) {
    const tsFolder = parts[folderIdx + 1];
    if (/^\d{8}_\d{6}$/.test(tsFolder)) return tsFolder;
  }
  return null;
}

// Load store
const store = JSON.parse(fs.readFileSync(STORE_PATH, "utf-8"));

const backfilled = [];
const knownDirs = new Map(); // key: "slug/epNum/stepFolder" → Set of ts dirs

// Step 1: Backfill output_dir from run logs
for (const run of store.generation_runs) {
  const story = store.stories.find((s) => s.id === run.story_id);
  const episode = store.episodes.find((e) => e.id === run.episode_id);
  if (!story || !episode) continue;

  for (const step of run.steps) {
    const stepFolder = STEP_TO_FOLDER[step.step_id];
    if (!stepFolder) continue;

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
      knownDirs.get(key).add(step.output_dir);
    }
  }
}

// Save updated store
fs.writeFileSync(STORE_PATH, JSON.stringify(store, null, 2));
console.log(`\nBackfilled ${backfilled.length} output_dirs:`);
for (const b of backfilled) {
  console.log(`  Run ${b.run_id} / ${b.step_id} → ${b.output_dir}`);
}

// Step 2: Delete orphan folders
const deleted = [];
for (const [key, validDirs] of knownDirs.entries()) {
  const [slug, epNum, stepFolder] = key.split("/");
  const stepDir = path.join(PROJECT_ROOT, "data", "stories", slug, "episodes", epNum, stepFolder);
  if (!fs.existsSync(stepDir)) continue;

  for (const entry of fs.readdirSync(stepDir)) {
    const entryPath = path.join(stepDir, entry);
    if (!fs.statSync(entryPath).isDirectory()) continue;
    if (!/^\d{8}_\d{6}$/.test(entry)) continue;
    if (!validDirs.has(entry)) {
      fs.rmSync(entryPath, { recursive: true, force: true });
      deleted.push(`${key}/${entry}`);
    }
  }
}

console.log(`\nDeleted ${deleted.length} orphan folders:`);
for (const d of deleted) {
  console.log(`  ${d}`);
}

console.log("\nDone.");
