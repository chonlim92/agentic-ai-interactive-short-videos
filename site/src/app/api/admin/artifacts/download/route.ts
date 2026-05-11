import { NextRequest, NextResponse } from "next/server";
import { loadStore } from "@/lib/db";
import fs from "fs";
import path from "path";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");

/**
 * GET /api/admin/artifacts/download?story_id=1&episode=1&step=generate_script&file=script.yaml[&run_ts=20260507_004604]
 * Serves the actual file content for download or preview.
 * If run_ts is provided, serve from the timestamped run subfolder instead of top-level.
 */
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const storyId = searchParams.get("story_id");
  const episodeNum = searchParams.get("episode");
  const step = searchParams.get("step");
  const fileName = searchParams.get("file");
  const runTs = searchParams.get("run_ts"); // optional: timestamp subfolder

  if (!storyId || !episodeNum || !step || !fileName) {
    return NextResponse.json({ error: "story_id, episode, step, and file are required" }, { status: 400 });
  }

  // Validate no path traversal
  if (fileName.includes("..") || fileName.includes("~")) {
    return NextResponse.json({ error: "Invalid file name" }, { status: 400 });
  }
  if (runTs && (runTs.includes("..") || runTs.includes("/"))) {
    return NextResponse.json({ error: "Invalid run_ts" }, { status: 400 });
  }

  const store = loadStore();
  const story = store.stories.find((s: { id: number }) => s.id === parseInt(storyId, 10));
  if (!story) {
    return NextResponse.json({ error: "Story not found" }, { status: 404 });
  }

  const epDir = path.join(PROJECT_ROOT, "data", "stories", story.slug, "episodes", episodeNum);
  const storyDir = path.join(PROJECT_ROOT, "data", "stories", story.slug);

  // Map step to subfolder name for run-specific access
  const stepFolders: Record<string, string> = {
    generate_script: "script",
    plan_scenes: "scenes",
    design_characters: "characters",
    generate_clips: "clips",
    add_audio: "audio",
    compose_episode: "compose",
    publish: "publish",
  };

  // Resolve file path based on step
  let filePath: string;
  if (runTs && stepFolders[step]) {
    if (step === "design_characters") {
      // Characters are story-level, not episode run-level
      filePath = path.join(storyDir, "characters", fileName);
    } else if (step === "publish") {
      // Publish assets: gallery/ and poster/ live in final/, story_posters/ at story level
      if (fileName.startsWith("gallery/") || fileName.startsWith("poster/")) {
        filePath = path.join(epDir, "final", fileName);
      } else if (fileName.startsWith("story_posters/")) {
        const relName = fileName.replace("story_posters/", "");
        // Try new 'poster/' directory first, fall back to legacy 'posters/'
        const newPath = path.join(storyDir, "poster", relName);
        filePath = fs.existsSync(newPath) ? newPath : path.join(storyDir, "posters", relName);
      } else {
        filePath = path.join(epDir, fileName);
      }
    } else {
      // Serve from run-specific subfolder
      filePath = path.join(epDir, stepFolders[step], runTs, fileName);
    }
  } else {
    switch (step) {
      case "generate_script":
        filePath = path.join(epDir, fileName);
        break;
      case "plan_scenes":
        filePath = path.join(epDir, "scenes", fileName);
        break;
      case "design_characters":
        filePath = path.join(storyDir, "characters", fileName);
        break;
      case "generate_clips":
        filePath = path.join(epDir, "clips", fileName);
        break;
      case "validate_quality":
        filePath = path.join(epDir, fileName);
        break;
      case "add_audio":
        filePath = path.join(epDir, "audio", fileName);
        break;
      case "compose_episode":
        filePath = path.join(epDir, "final", fileName);
        break;
      case "publish":
        if (fileName.startsWith("gallery/") || fileName.startsWith("poster/")) {
          filePath = path.join(epDir, "final", fileName);
        } else if (fileName.startsWith("story_posters/")) {
          const relName = fileName.replace("story_posters/", "");
          const newPath = path.join(storyDir, "poster", relName);
          filePath = fs.existsSync(newPath) ? newPath : path.join(storyDir, "posters", relName);
        } else {
          filePath = path.join(epDir, fileName);
        }
        break;
      default:
        return NextResponse.json({ error: "Unknown step" }, { status: 400 });
    }
  }

  // Ensure resolved path is within the project data directory
  const resolved = path.resolve(filePath);
  const dataRoot = path.resolve(PROJECT_ROOT, "data");
  if (!resolved.startsWith(dataRoot)) {
    return NextResponse.json({ error: "Access denied" }, { status: 403 });
  }

  if (!fs.existsSync(resolved)) {
    return NextResponse.json({ error: "File not found" }, { status: 404 });
  }

  const stat = fs.statSync(resolved);
  if (!stat.isFile()) {
    return NextResponse.json({ error: "Not a file" }, { status: 400 });
  }

  const ext = path.extname(resolved).toLowerCase();
  const mimeTypes: Record<string, string> = {
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".json": "application/json",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
  };

  const contentType = mimeTypes[ext] || "application/octet-stream";

  // For media files, use inline disposition so they can be played in-browser
  const isMedia = [".mp4", ".webm", ".mp3", ".wav", ".png", ".jpg", ".jpeg"].includes(ext);
  const disposition = isMedia
    ? `inline; filename="${path.basename(resolved)}"`
    : `attachment; filename="${path.basename(resolved)}"`;

  // Support Range requests for media streaming (required by <video>/<audio> elements)
  const rangeHeader = req.headers.get("range");
  if (isMedia && rangeHeader) {
    const fileSize = stat.size;
    const parts = rangeHeader.replace(/bytes=/, "").split("-");
    const start = parseInt(parts[0], 10);
    const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
    const chunkSize = end - start + 1;

    const fileStream = fs.createReadStream(resolved, { start, end });
    const chunks: Buffer[] = [];
    for await (const chunk of fileStream) {
      chunks.push(chunk as Buffer);
    }
    const content = Buffer.concat(chunks);

    return new Response(content, {
      status: 206,
      headers: {
        "Content-Type": contentType,
        "Content-Range": `bytes ${start}-${end}/${fileSize}`,
        "Accept-Ranges": "bytes",
        "Content-Length": String(chunkSize),
        "Content-Disposition": disposition,
      },
    });
  }

  const content = fs.readFileSync(resolved);

  return new Response(content, {
    headers: {
      "Content-Type": contentType,
      "Content-Disposition": disposition,
      "Content-Length": String(stat.size),
      "Accept-Ranges": "bytes",
    },
  });
}
