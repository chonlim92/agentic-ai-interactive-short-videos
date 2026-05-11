import { getEpisode, getVoteResults, closeVoting } from "@/lib/db";
import { NextRequest, NextResponse } from "next/server";

/**
 * GET /api/episodes/[id]/results
 * Returns vote tallies for an episode. Used by agents/tally_votes.py.
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: { id: string } }
) {
  const episodeNumber = parseInt(params.id, 10);
  if (isNaN(episodeNumber)) {
    return NextResponse.json({ error: "Invalid episode number" }, { status: 400 });
  }

  const episode = await getEpisode(episodeNumber);
  if (!episode) {
    return NextResponse.json({ error: "Episode not found" }, { status: 404 });
  }

  const results = await getVoteResults(episode.id);
  const totalVotes = results.reduce((sum, r) => sum + r.count, 0);

  return NextResponse.json({
    episode_number: episode.episode_number,
    title: episode.title,
    voting_open: episode.voting_open,
    total_votes: totalVotes,
    results: results.map((r) => ({
      option_id: r.option_id,
      label: r.label,
      votes: r.count,
      percentage: totalVotes > 0 ? Math.round((r.count / totalVotes) * 100) : 0,
    })),
    winner:
      totalVotes > 0
        ? results.reduce((max, r) => (r.count > max.count ? r : max)).label
        : null,
  });
}

/**
 * POST /api/episodes/[id]/results
 * Closes voting for an episode. Used by agents after deadline.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  const episodeNumber = parseInt(params.id, 10);
  if (isNaN(episodeNumber)) {
    return NextResponse.json({ error: "Invalid episode number" }, { status: 400 });
  }

  const body = await request.json();
  if (body.action !== "close_voting") {
    return NextResponse.json({ error: "Unknown action" }, { status: 400 });
  }

  const episode = await getEpisode(episodeNumber);
  if (!episode) {
    return NextResponse.json({ error: "Episode not found" }, { status: 404 });
  }

  await closeVoting(episode.id);
  return NextResponse.json({ success: true, message: "Voting closed" });
}
