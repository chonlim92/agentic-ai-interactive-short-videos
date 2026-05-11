import { NextResponse } from "next/server";
import { loadStore, computeVotingDeadline } from "@/lib/db";

/**
 * GET /api/admin/dashboard
 * Returns rich statistics for the admin dashboard charts.
 */
export async function GET() {
  const store = loadStore();

  // --- Per-story statistics ---
  const stories = store.stories.map((s) => {
    const episodes = store.episodes.filter((e) => e.story_id === s.id);
    const episodeIds = episodes.map((e) => e.id);
    const comments = store.comments.filter((c) => episodeIds.includes(c.episode_id));
    const votes = store.votes.filter((v) => episodeIds.includes(v.episode_id));

    return {
      id: s.id,
      slug: s.slug,
      title: s.title,
      title_zh: s.title_zh,
      total_episodes: episodes.length,
      published: episodes.filter((e) => e.status === "published").length,
      drafts: episodes.filter((e) => e.status === "draft").length,
      voting_open: episodes.filter((e) => e.voting_open).length,
      total_votes: votes.length,
      total_comments: comments.length,
      moderated_comments: comments.filter((c) => c.moderated).length,
      flagged_comments: comments.filter((c) => c.flagged).length,
    };
  });

  // --- Per-episode breakdown ---
  const episodes = store.episodes.map((ep) => {
    const story = store.stories.find((s) => s.id === ep.story_id);
    const options = store.vote_options
      .filter((o) => o.episode_id === ep.id)
      .sort((a, b) => a.sort_order - b.sort_order);
    const votes = store.votes.filter((v) => v.episode_id === ep.id);
    const comments = store.comments.filter((c) => c.episode_id === ep.id);

    return {
      id: ep.id,
      story_id: ep.story_id,
      story_title: story?.title ?? "Unknown",
      story_title_zh: story?.title_zh ?? "",
      episode_number: ep.episode_number,
      title: ep.title,
      title_zh: ep.title_zh,
      status: ep.status,
      voting_open: ep.voting_open,
      voting_deadline: computeVotingDeadline(ep),
      published_at: ep.published_at,
      total_votes: votes.length,
      total_comments: comments.length,
      vote_distribution: options.map((opt) => ({
        label: opt.label,
        label_zh: opt.label_zh,
        count: votes.filter((v) => v.option_id === opt.id).length,
      })),
    };
  });

  // --- Generation run stats ---
  const generation_runs = store.generation_runs.map((run) => {
    const story = store.stories.find((s) => s.id === run.story_id);
    const totalDuration = run.steps.reduce((sum, s) => sum + (s.duration_ms ?? 0), 0);
    return {
      id: run.id,
      episode_id: run.episode_id,
      story_title: story?.title ?? "Unknown",
      episode_number: store.episodes.find((e) => e.id === run.episode_id)?.episode_number ?? 0,
      mode: run.mode,
      status: run.status,
      started_at: run.started_at,
      ended_at: run.ended_at,
      total_duration_ms: totalDuration,
      steps: run.steps.map((s) => ({
        step_id: s.step_id,
        label: s.label,
        status: s.status,
        duration_ms: s.duration_ms,
      })),
    };
  });

  // --- Overall summary ---
  const summary = {
    total_stories: store.stories.length,
    total_episodes: store.episodes.length,
    published_episodes: store.episodes.filter((e) => e.status === "published").length,
    draft_episodes: store.episodes.filter((e) => e.status === "draft").length,
    voting_open: store.episodes.filter((e) => e.voting_open).length,
    total_votes: store.votes.length,
    total_comments: store.comments.length,
    moderated_comments: store.comments.filter((c) => c.moderated).length,
    pending_moderation: store.comments.filter((c) => !c.moderated && !c.flagged).length,
    flagged_comments: store.comments.filter((c) => c.flagged).length,
    total_generation_runs: store.generation_runs.length,
    completed_runs: store.generation_runs.filter((r) => r.status === "completed").length,
    failed_runs: store.generation_runs.filter((r) => r.status === "failed").length,
  };

  return NextResponse.json({ summary, stories, episodes, generation_runs });
}
