import { castVote, getVoteResults } from "@/lib/db";
import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { episodeId, optionId } = body;

    if (!episodeId || !optionId) {
      return NextResponse.json(
        { error: "Missing episodeId or optionId" },
        { status: 400 }
      );
    }

    // Generate voter ID from IP + user-agent for basic deduplication
    const forwarded = request.headers.get("x-forwarded-for");
    const ip = forwarded?.split(",")[0]?.trim() || "unknown";
    const ua = request.headers.get("user-agent") || "unknown";
    const voterId = crypto
      .createHash("sha256")
      .update(`${ip}:${ua}`)
      .digest("hex")
      .slice(0, 16);

    const result = await castVote(episodeId, optionId, voterId);

    if (!result.success) {
      return NextResponse.json({ error: result.error }, { status: 409 });
    }

    // Return updated results
    const results = await getVoteResults(episodeId);
    return NextResponse.json({ success: true, results });
  } catch {
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const episodeId = searchParams.get("episodeId");

  if (!episodeId) {
    return NextResponse.json(
      { error: "Missing episodeId" },
      { status: 400 }
    );
  }

  const results = await getVoteResults(parseInt(episodeId, 10));
  return NextResponse.json({ results });
}
