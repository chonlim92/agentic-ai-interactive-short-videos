"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

interface Episode {
  id: number;
  story_id: number;
  episode_number: number;
  title: string;
  title_zh: string;
  status: string;
  video_url: string | null;
  thumbnail_url: string | null;
  voting_open: boolean;
  admin_prompt: string | null;
  admin_prompt_weight: number;
  published_at: string;
}

interface Story {
  id: number;
  title: string;
  title_zh: string;
  slug: string;
}

interface VoteOption {
  id: number;
  label: string;
  label_zh: string;
}

export default function EpisodeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const storySlug = params.slug as string;
  const [episode, setEpisode] = useState<Episode | null>(null);
  const [story, setStory] = useState<Story | null>(null);
  const [voteOptions, setVoteOptions] = useState<VoteOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    title: "",
    title_zh: "",
    admin_prompt: "",
    admin_prompt_weight: "0.75",
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadEpisode();
  }, []);

  async function loadEpisode() {
    const episodeNumber = params.id;
    const [epRes, stRes] = await Promise.all([
      fetch(`/api/admin/stories/${storySlug}/episodes/${episodeNumber}`),
      fetch("/api/admin/stories"),
    ]);
    const epData = await epRes.json();
    const stData = await stRes.json();

    if (epData.episode) {
      setEpisode(epData.episode);
      const stories: Story[] = stData.stories || [];
      const matchedStory = stories.find((s) => s.id === epData.episode.story_id);
      setStory(matchedStory || null);
      setEditForm({
        title: epData.episode.title,
        title_zh: epData.episode.title_zh || "",
        admin_prompt: epData.episode.admin_prompt || "",
        admin_prompt_weight: String(epData.episode.admin_prompt_weight || 0.75),
      });
    }

    if (epData.vote_options) {
      setVoteOptions(epData.vote_options);
    }

    setLoading(false);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!episode) return;
    setSaving(true);
    await fetch(`/api/admin/stories/${storySlug}/episodes/${episode.episode_number}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: editForm.title,
        title_zh: editForm.title_zh,
        admin_prompt: editForm.admin_prompt || null,
        admin_prompt_weight: editForm.admin_prompt
          ? parseFloat(editForm.admin_prompt_weight)
          : undefined,
      }),
    });
    setSaving(false);
    setEditing(false);
    loadEpisode();
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-neon-purple/30 border-t-neon-purple rounded-full animate-spin" />
      </div>
    );
  }

  if (!episode) {
    return (
      <div className="glass-card p-8 text-center text-white/30">
        Episode not found.
      </div>
    );
  }

  const canEdit = !episode.video_url;

  return (
    <div className="max-w-3xl">
      {/* Back button */}
      <button
        onClick={() => router.push("/admin/episodes")}
        className="text-xs text-white/40 hover:text-white/60 mb-6 flex items-center gap-1"
      >
        ← Back to Episodes
      </button>

      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">
            Episode {String(episode.episode_number).padStart(2, "0")}
          </h1>
          {story && (
            <p className="text-sm text-white/40 mt-1">
              {story.title} {story.title_zh ? `(${story.title_zh})` : ""}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          {canEdit && !editing && (
            <button
              onClick={() => setEditing(true)}
              className="text-sm px-4 py-2 rounded-lg border border-neon-cyan/30 text-neon-cyan hover:bg-neon-cyan/10 transition-colors"
            >
              Edit
            </button>
          )}
          <span
            className={`text-xs px-3 py-1.5 rounded-full ${
              episode.status === "published"
                ? "bg-green-500/10 text-green-400 border border-green-500/20"
                : episode.status === "draft"
                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                : "bg-white/5 text-white/30 border border-white/10"
            }`}
          >
            {episode.status}
          </span>
        </div>
      </div>

      {/* Edit form */}
      {editing && canEdit ? (
        <form onSubmit={handleSave} className="glass-card p-6 mb-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-white/40 block mb-1">Title (EN)</label>
              <input
                type="text"
                value={editForm.title}
                onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50"
                required
              />
            </div>
            <div>
              <label className="text-xs text-white/40 block mb-1">Title (中文)</label>
              <input
                type="text"
                value={editForm.title_zh}
                onChange={(e) => setEditForm({ ...editForm, title_zh: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-white/40 block mb-1">Admin Prompt</label>
            <textarea
              value={editForm.admin_prompt}
              onChange={(e) => setEditForm({ ...editForm, admin_prompt: e.target.value })}
              rows={4}
              className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50 resize-none font-mono"
            />
          </div>
          {editForm.admin_prompt && (
            <div className="flex items-center gap-4">
              <label className="text-xs text-white/40">Prompt Weight:</label>
              <input
                type="range"
                min="0.5"
                max="1"
                step="0.05"
                value={editForm.admin_prompt_weight}
                onChange={(e) => setEditForm({ ...editForm, admin_prompt_weight: e.target.value })}
                className="flex-1 h-1.5 accent-neon-purple"
              />
              <span className="text-sm font-mono text-neon-purple w-12 text-right">
                {Math.round(parseFloat(editForm.admin_prompt_weight) * 100)}%
              </span>
            </div>
          )}
          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={saving}
              className="btn-primary text-sm disabled:opacity-40"
            >
              {saving ? "Saving..." : "Save Changes"}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="text-sm text-white/40 hover:text-white/60"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        /* Detail view */
        <div className="space-y-6">
          {/* Title card */}
          <div className="glass-card p-6">
            <div className="grid grid-cols-2 gap-6">
              <div>
                <p className="text-xs text-white/30 mb-1">Title</p>
                <p className="text-white font-medium">{episode.title}</p>
              </div>
              <div>
                <p className="text-xs text-white/30 mb-1">Title (中文)</p>
                <p className="text-white/70">{episode.title_zh || "—"}</p>
              </div>
            </div>
          </div>

          {/* Status & metadata */}
          <div className="glass-card p-6">
            <h3 className="text-xs text-white/30 uppercase tracking-wider mb-4">Metadata</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-xs text-white/30">Status</p>
                <p className="text-white/70">{episode.status}</p>
              </div>
              <div>
                <p className="text-xs text-white/30">Voting</p>
                <p className="text-white/70">{episode.voting_open ? "Open" : "Closed"}</p>
              </div>
              <div>
                <p className="text-xs text-white/30">Created</p>
                <p className="text-white/70">
                  {new Date(episode.published_at).toLocaleDateString()}
                </p>
              </div>
              <div>
                <p className="text-xs text-white/30">Video</p>
                <p className="text-white/70">
                  {episode.video_url ? (
                    <a href={episode.video_url} target="_blank" className="text-neon-cyan hover:underline">
                      View video
                    </a>
                  ) : (
                    <span className="text-white/30">Not generated</span>
                  )}
                </p>
              </div>
            </div>
          </div>

          {/* Admin prompt */}
          {episode.admin_prompt && (
            <div className="glass-card p-6">
              <h3 className="text-xs text-white/30 uppercase tracking-wider mb-3">Admin Prompt</h3>
              <p className="text-sm text-white/60 font-mono whitespace-pre-wrap">
                {episode.admin_prompt}
              </p>
              <p className="text-xs text-white/30 mt-3">
                Weight: {Math.round(episode.admin_prompt_weight * 100)}%
              </p>
            </div>
          )}

          {/* Vote options */}
          {voteOptions.length > 0 && (
            <div className="glass-card p-6">
              <h3 className="text-xs text-white/30 uppercase tracking-wider mb-3">Vote Options</h3>
              <div className="space-y-2">
                {voteOptions.map((opt) => (
                  <div
                    key={opt.id}
                    className="flex items-center gap-3 p-3 rounded-lg bg-white/[0.02] border border-white/[0.05]"
                  >
                    <div className="w-2 h-2 rounded-full bg-neon-purple/50" />
                    <span className="text-sm text-white/70">{opt.label}</span>
                    {opt.label_zh && opt.label_zh !== opt.label && (
                      <span className="text-xs text-white/30">({opt.label_zh})</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
