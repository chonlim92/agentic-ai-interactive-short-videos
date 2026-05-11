import { NextRequest, NextResponse } from "next/server";
import { loadStore } from "@/lib/db";
import fs from "fs";
import path from "path";
import { spawn } from "child_process";
import { StringDecoder } from "string_decoder";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");
const IS_WINDOWS = process.platform === "win32";
const AGENTS_DIR = path.join(PROJECT_ROOT, "agents");

/**
 * Simple YAML parser for the clip review reports.
 * Handles the subset of YAML that Python's yaml.dump produces.
 */
function parseSimpleYaml(text: string): Record<string, unknown> {
  // Use dynamic import to avoid bundling issues; fall back to JSON if the report is JSON
  try {
    return JSON.parse(text);
  } catch {
    // Not JSON — try basic YAML key-value parsing
  }

  // For the review report, the Python agent also saves as JSON sidecar
  // Just return the raw text as a fallback
  const result: Record<string, unknown> = {};
  result._raw = text;
  return result;
}

/**
 * GET /api/admin/clip-review?story_id=1&episode=1&run_ts=20260101_120000
 *
 * Returns the clip review report (clip_review.yaml) for a given clips run.
 * If the report doesn't exist yet, returns { available: false }.
 */
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const storyId = searchParams.get("story_id");
  const episodeNum = searchParams.get("episode");
  const runTs = searchParams.get("run_ts");

  if (!storyId || !episodeNum) {
    return NextResponse.json({ error: "story_id and episode are required" }, { status: 400 });
  }

  // Validate run_ts
  if (runTs && (runTs.includes("..") || runTs.includes("/"))) {
    return NextResponse.json({ error: "Invalid run_ts" }, { status: 400 });
  }

  const store = loadStore();
  const story = store.stories.find((s: { id: number }) => s.id === parseInt(storyId, 10));
  if (!story) {
    return NextResponse.json({ error: "Story not found" }, { status: 404 });
  }

  const epDir = path.join(PROJECT_ROOT, "data", "stories", story.slug, "episodes", episodeNum);
  const qualityDir = path.join(epDir, "quality");
  const clipsDir = path.join(epDir, "clips");

  // Find quality run dir (uses same run_ts as clips)
  let qualityRunDir: string;
  if (runTs) {
    qualityRunDir = path.join(qualityDir, runTs);
  } else {
    // Use latest quality run, or fall back to latest clips run timestamp
    if (fs.existsSync(qualityDir)) {
      const subdirs = fs.readdirSync(qualityDir)
        .filter((d) => fs.statSync(path.join(qualityDir, d)).isDirectory())
        .sort()
        .reverse();
      if (subdirs.length > 0) {
        qualityRunDir = path.join(qualityDir, subdirs[0]);
      } else {
        return NextResponse.json({ available: false, clips: [] });
      }
    } else if (fs.existsSync(clipsDir)) {
      // No quality dir yet — derive from latest clips run
      const subdirs = fs.readdirSync(clipsDir)
        .filter((d) => fs.statSync(path.join(clipsDir, d)).isDirectory())
        .sort()
        .reverse();
      if (subdirs.length > 0) {
        qualityRunDir = path.join(qualityDir, subdirs[0]);
      } else {
        return NextResponse.json({ available: false, clips: [] });
      }
    } else {
      return NextResponse.json({ available: false, clips: [] });
    }
  }

  // Check for existing review report (prefer JSON, fall back to YAML)
  const reviewJsonPath = path.join(qualityRunDir, "clip_review.json");
  const reviewYamlPath = path.join(qualityRunDir, "clip_review.yaml");
  const reviewPath = fs.existsSync(reviewJsonPath) ? reviewJsonPath : reviewYamlPath;
  if (!fs.existsSync(reviewPath)) {
    return NextResponse.json({ available: false, run_ts: runTs || path.basename(qualityRunDir), clips: [] });
  }

  try {
    const content = fs.readFileSync(reviewPath, "utf-8");
    const report = reviewPath.endsWith(".json") ? JSON.parse(content) : parseSimpleYaml(content);
    return NextResponse.json({ available: true, ...report });
  } catch {
    return NextResponse.json({ error: "Failed to parse review report" }, { status: 500 });
  }
}

/**
 * POST /api/admin/clip-review
 *
 * Actions:
 * - { action: "run_review", story_id, episode, run_ts } — Run quality review on clips
 * - { action: "regenerate", story_id, episode, run_ts, clip_name, improvement_prompt? } — Regenerate a clip
 * - { action: "accept_regen", story_id, episode, run_ts, clip_name } — Accept regenerated clip (replace original)
 * - { action: "discard_regen", story_id, episode, run_ts, clip_name } — Discard regenerated clip
 */
export async function POST(req: NextRequest) {
  const body = await req.json();
  const { action, story_id, episode, run_ts } = body;

  if (!action || !story_id || !episode) {
    return NextResponse.json({ error: "action, story_id, and episode are required" }, { status: 400 });
  }

  // Validate run_ts
  if (run_ts && (/\.\./.test(run_ts) || /[\/\\]/.test(String(run_ts).replace(/^\d{8}_\d{6}$/, "")))) {
    if (!/^\d{8}_\d{6}$/.test(run_ts)) {
      return NextResponse.json({ error: "Invalid run_ts format" }, { status: 400 });
    }
  }

  const store = loadStore();
  const story = store.stories.find((s: { id: number }) => s.id === parseInt(story_id, 10));
  if (!story) {
    return NextResponse.json({ error: "Story not found" }, { status: 404 });
  }

  const epDir = path.join(PROJECT_ROOT, "data", "stories", story.slug, "episodes", String(episode));
  const clipsDir = path.join(epDir, "clips");

  // Resolve clips run dir
  let clipsRunDir: string;
  if (run_ts) {
    clipsRunDir = path.join(clipsDir, run_ts);
  } else {
    if (!fs.existsSync(clipsDir)) {
      return NextResponse.json({ error: "No clips directory" }, { status: 404 });
    }
    const subdirs = fs.readdirSync(clipsDir)
      .filter((d) => fs.statSync(path.join(clipsDir, d)).isDirectory())
      .sort()
      .reverse();
    if (subdirs.length === 0) {
      return NextResponse.json({ error: "No clips runs found" }, { status: 404 });
    }
    clipsRunDir = path.join(clipsDir, subdirs[0]);
  }

  switch (action) {
    case "run_review": {
      // Run validate_quality.py --episode X --story slug --review
      return await runReview(story.slug, String(episode), run_ts);
    }

    case "regenerate": {
      const { clip_name, improvement_prompt } = body;
      if (!clip_name) {
        return NextResponse.json({ error: "clip_name is required" }, { status: 400 });
      }
      // Sanitize clip_name
      if (clip_name.includes("..") || clip_name.includes("/") || clip_name.includes("\\")) {
        return NextResponse.json({ error: "Invalid clip_name" }, { status: 400 });
      }
      const clipPath = path.join(clipsRunDir, clip_name);
      if (!fs.existsSync(clipPath)) {
        return NextResponse.json({ error: "Clip not found" }, { status: 404 });
      }
      return await regenerateClip(clipPath, improvement_prompt, story.slug);
    }

    case "accept_regen": {
      const clipName = body.clip_name;
      if (!clipName) {
        return NextResponse.json({ error: "clip_name is required" }, { status: 400 });
      }
      if (clipName.includes("..") || clipName.includes("/") || clipName.includes("\\")) {
        return NextResponse.json({ error: "Invalid clip_name" }, { status: 400 });
      }
      const stem = clipName.replace(/\.mp4$/, "");
      const regenPath = path.join(clipsRunDir, `${stem}.regen.mp4`);
      const originalPath = path.join(clipsRunDir, clipName);

      if (!fs.existsSync(regenPath)) {
        return NextResponse.json({ error: "No regenerated clip found" }, { status: 404 });
      }

      // Backup original, replace with regen
      const backupPath = path.join(clipsRunDir, `${stem}.original.mp4`);
      if (fs.existsSync(originalPath)) {
        fs.copyFileSync(originalPath, backupPath);
      }
      fs.renameSync(regenPath, originalPath);

      // Also replace enhanced prompt YAML if regen prompt exists
      const regenPromptPath = path.join(clipsRunDir, `${stem}.regen_enhanced_prompt.yaml`);
      const originalPromptPath = path.join(clipsRunDir, `${stem}_enhanced_prompt.yaml`);
      if (fs.existsSync(regenPromptPath)) {
        const backupPromptPath = path.join(clipsRunDir, `${stem}.original_enhanced_prompt.yaml`);
        if (fs.existsSync(originalPromptPath)) {
          fs.copyFileSync(originalPromptPath, backupPromptPath);
        }
        fs.renameSync(regenPromptPath, originalPromptPath);
      }

      return NextResponse.json({ success: true, message: "Regenerated clip accepted" });
    }

    case "discard_regen": {
      const clipNameD = body.clip_name;
      if (!clipNameD) {
        return NextResponse.json({ error: "clip_name is required" }, { status: 400 });
      }
      if (clipNameD.includes("..") || clipNameD.includes("/") || clipNameD.includes("\\")) {
        return NextResponse.json({ error: "Invalid clip_name" }, { status: 400 });
      }
      const stemD = clipNameD.replace(/\.mp4$/, "");
      const regenPathD = path.join(clipsRunDir, `${stemD}.regen.mp4`);

      if (fs.existsSync(regenPathD)) {
        fs.unlinkSync(regenPathD);
      }

      // Also clean up regen enhanced prompt YAML
      const regenPromptPathD = path.join(clipsRunDir, `${stemD}.regen_enhanced_prompt.yaml`);
      if (fs.existsSync(regenPromptPathD)) {
        fs.unlinkSync(regenPromptPathD);
      }

      return NextResponse.json({ success: true, message: "Regenerated clip discarded" });
    }

    default:
      return NextResponse.json({ error: `Unknown action: ${action}` }, { status: 400 });
  }
}

/**
 * Run validate_quality.py in review mode and return the report.
 */
async function runReview(storySlug: string, episode: string, runTs?: string): Promise<Response> {
  return new Promise((resolve) => {
    const args = [
      path.join(AGENTS_DIR, "validate_quality.py"),
      "--episode", episode,
      "--story", storySlug,
      "--review",
    ];
    if (runTs) {
      args.push("--clips-run-ts", runTs);
    }

    const proc = spawn("python", args, {
      cwd: PROJECT_ROOT,
      env: { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" },
      detached: !IS_WINDOWS,
    });

    const stdoutDecoder = new StringDecoder("utf8");
    const stderrDecoder = new StringDecoder("utf8");
    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk: Buffer) => { stdout += stdoutDecoder.write(chunk); });
    proc.stderr.on("data", (chunk: Buffer) => { stderr += stderrDecoder.write(chunk); });

    proc.on("close", (code) => {
      // Read the generated report
      const epDir = path.join(PROJECT_ROOT, "data", "stories", storySlug, "episodes", episode);
      const qualityDir = path.join(epDir, "quality");
      const clipsDir = path.join(epDir, "clips");

      // Resolve quality run dir (same run_ts as clips)
      let reviewDir = qualityDir;
      if (runTs) {
        reviewDir = path.join(qualityDir, runTs);
      } else if (fs.existsSync(clipsDir)) {
        const subdirs = fs.readdirSync(clipsDir)
          .filter((d) => fs.statSync(path.join(clipsDir, d)).isDirectory())
          .sort()
          .reverse();
        if (subdirs.length > 0) reviewDir = path.join(qualityDir, subdirs[0]);
      }

      const reviewJsonPath = path.join(reviewDir, "clip_review.json");
      const reviewYamlPath = path.join(reviewDir, "clip_review.yaml");
      const reviewPath = fs.existsSync(reviewJsonPath) ? reviewJsonPath : reviewYamlPath;
      if (fs.existsSync(reviewPath)) {
        try {
          const content = fs.readFileSync(reviewPath, "utf-8");
          const report = reviewPath.endsWith(".json") ? JSON.parse(content) : parseSimpleYaml(content);
          resolve(NextResponse.json({ available: true, exit_code: code, ...report }));
        } catch {
          resolve(NextResponse.json({ available: false, exit_code: code, stdout, stderr }, { status: 500 }));
        }
      } else {
        resolve(NextResponse.json({ available: false, exit_code: code, stdout, stderr }));
      }
    });

    proc.on("error", (err) => {
      resolve(NextResponse.json({ error: `Process error: ${err.message}` }, { status: 500 }));
    });
  });
}

/**
 * Run generate_video.py --regenerate-clip to regenerate a single clip.
 */
async function regenerateClip(clipPath: string, improvementPrompt?: string, storySlug?: string): Promise<Response> {
  return new Promise((resolve) => {
    const args = [
      path.join(AGENTS_DIR, "generate_video.py"),
      "--regenerate-clip", clipPath,
    ];
    if (improvementPrompt) {
      args.push("--improvement-prompt", improvementPrompt);
    }
    if (storySlug) {
      args.push("--story", storySlug);
    }

    // Pass through model/quality env vars
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      PYTHONIOENCODING: "utf-8",
    };

    const proc = spawn("python", args, {
      cwd: PROJECT_ROOT,
      env,
      detached: !IS_WINDOWS,
    });

    const stdoutDecoder = new StringDecoder("utf8");
    const stderrDecoder = new StringDecoder("utf8");
    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk: Buffer) => { stdout += stdoutDecoder.write(chunk); });
    proc.stderr.on("data", (chunk: Buffer) => { stderr += stderrDecoder.write(chunk); });

    proc.on("close", (code) => {
      if (code === 0) {
        // Extract regenerated clip path from stdout
        const match = stdout.match(/Regenerated clip saved:\s+(.+?)(?:\s+\(|$)/m);
        const regenPath = match ? match[1].trim() : null;
        resolve(NextResponse.json({
          success: true,
          regen_clip: regenPath ? path.basename(regenPath) : null,
          stdout,
        }));
      } else {
        resolve(NextResponse.json({
          success: false,
          exit_code: code,
          stdout,
          stderr,
        }, { status: 500 }));
      }
    });

    proc.on("error", (err) => {
      resolve(NextResponse.json({ error: `Process error: ${err.message}` }, { status: 500 }));
    });
  });
}

/**
 * DELETE /api/admin/clip-review?story_id=1&episode=1&run_ts=20260101_120000
 *
 * Deletes the quality review report for a given run.
 * If run_ts is omitted, deletes the entire quality/ folder for the episode.
 */
export async function DELETE(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const storyId = searchParams.get("story_id");
  const episodeNum = searchParams.get("episode");
  const runTs = searchParams.get("run_ts");

  if (!storyId || !episodeNum) {
    return NextResponse.json({ error: "story_id and episode are required" }, { status: 400 });
  }

  if (runTs && !/^\d{8}_\d{6}$/.test(runTs)) {
    return NextResponse.json({ error: "Invalid run_ts format" }, { status: 400 });
  }

  const store = loadStore();
  const story = store.stories.find((s: { id: number }) => s.id === parseInt(storyId, 10));
  if (!story) {
    return NextResponse.json({ error: "Story not found" }, { status: 404 });
  }

  const epDir = path.join(PROJECT_ROOT, "data", "stories", story.slug, "episodes", episodeNum);
  const qualityDir = path.join(epDir, "quality");

  if (runTs) {
    const qualityRunDir = path.join(qualityDir, runTs);
    if (fs.existsSync(qualityRunDir)) {
      fs.rmSync(qualityRunDir, { recursive: true, force: true });
    }
  } else {
    if (fs.existsSync(qualityDir)) {
      fs.rmSync(qualityDir, { recursive: true, force: true });
    }
  }

  return NextResponse.json({ success: true });
}
