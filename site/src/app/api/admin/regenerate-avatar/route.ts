import { NextRequest, NextResponse } from "next/server";
import { loadStore } from "@/lib/db";
import { spawn } from "child_process";
import path from "path";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");

/**
 * POST /api/admin/regenerate-avatar
 * Body: { story_id: number, episode: number, slug: string, prompt?: string }
 * Regenerates the avatar for a single character by slug.
 * If prompt is provided, uses LLM to edit the character YAML first.
 */
export async function POST(req: NextRequest) {
  const body = await req.json();
  const { story_id, episode, slug, prompt: editPrompt } = body;

  if (!story_id || !episode || !slug) {
    return NextResponse.json({ error: "story_id, episode, and slug are required" }, { status: 400 });
  }

  // Validate slug (no path traversal)
  if (/[^a-z0-9_\-]/.test(slug)) {
    return NextResponse.json({ error: "Invalid slug" }, { status: 400 });
  }

  const store = loadStore();
  const story = store.stories.find((s: { id: number }) => s.id === parseInt(story_id, 10));
  if (!story) {
    return NextResponse.json({ error: "Story not found" }, { status: 404 });
  }

  const agentScript = path.join(PROJECT_ROOT, "agents", "generate_episode.py");

  return new Promise<NextResponse>((resolve) => {
    const args = [
      agentScript,
      "--episode", String(episode),
      "--story", story.slug,
      "--regenerate-avatar", slug,
    ];
    // Add optional edit prompt
    if (editPrompt && typeof editPrompt === "string" && editPrompt.trim()) {
      args.push("--avatar-prompt", editPrompt.trim());
    }
    const proc = spawn("python", args, {
      cwd: PROJECT_ROOT,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8",
      } as NodeJS.ProcessEnv,
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk: Buffer) => { stdout += chunk.toString(); });
    proc.stderr.on("data", (chunk: Buffer) => { stderr += chunk.toString(); });

    proc.on("close", (code) => {
      if (code === 0) {
        resolve(NextResponse.json({ success: true, output: stdout.trim() }));
      } else {
        resolve(NextResponse.json(
          { error: "Avatar regeneration failed", output: stderr.trim() || stdout.trim() },
          { status: 500 }
        ));
      }
    });
  });
}
