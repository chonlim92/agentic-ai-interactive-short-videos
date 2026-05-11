import { NextRequest, NextResponse } from "next/server";
import { getCommentSummaryData } from "@/lib/db";

/**
 * GET /api/episodes/[id]/comments/summary
 * Returns moderated comment data for the community-manager agent to summarize.
 * Used before generating a new episode to understand audience sentiment.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const episodeId = parseInt(params.id, 10);
  if (isNaN(episodeId)) {
    return NextResponse.json({ error: "Invalid episode ID" }, { status: 400 });
  }

  const data = await getCommentSummaryData(episodeId);

  return NextResponse.json({
    episode_id: episodeId,
    stats: {
      total: data.total,
      moderated: data.moderated,
      flagged: data.flagged,
    },
    moderated_comments: data.comments.map((c) => ({
      author: c.author,
      content: c.content,
      created_at: c.created_at,
    })),
  });
}
