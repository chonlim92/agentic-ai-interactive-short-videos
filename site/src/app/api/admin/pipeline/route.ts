import { NextResponse } from "next/server";
import { getAllEpisodes, getAllComments } from "@/lib/db";
import fs from "fs";
import path from "path";

/**
 * GET /api/admin/pipeline
 * Returns pipeline status by reading episode state files from disk.
 */
export async function GET() {
  const episodes = await getAllEpisodes();
  const comments = await getAllComments();

  // Try to read pipeline state files
  const statesDir = path.join(process.cwd(), "..", "data", "episodes");
  const pipelineStates: Record<string, unknown> = {};

  if (fs.existsSync(statesDir)) {
    const dirs = fs.readdirSync(statesDir).filter((d) => {
      const full = path.join(statesDir, d);
      return fs.statSync(full).isDirectory();
    });
    for (const dir of dirs) {
      const stateFile = path.join(statesDir, dir, "state.yaml");
      if (fs.existsSync(stateFile)) {
        pipelineStates[dir] = fs.readFileSync(stateFile, "utf-8");
      }
    }
  }

  return NextResponse.json({
    summary: {
      total_episodes: episodes.length,
      published: episodes.filter((e) => e.status === "published").length,
      drafts: episodes.filter((e) => e.status === "draft").length,
      voting_open: episodes.filter((e) => e.voting_open).length,
      total_comments: comments.length,
      pending_moderation: comments.filter((c) => !c.moderated && !c.flagged).length,
      flagged_comments: comments.filter((c) => c.flagged).length,
    },
    pipeline_states: pipelineStates,
  });
}
