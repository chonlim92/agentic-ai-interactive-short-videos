"use client";

import { useState, useEffect } from "react";

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

export default function AdminEpisodes() {
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  async function loadData() {
    const [epRes, stRes] = await Promise.all([
      fetch("/api/admin/episodes"),
      fetch("/api/admin/stories"),
    ]);
    const epData = await epRes.json();
    const stData = await stRes.json();
    setEpisodes(epData.episodes || []);
    setStories(stData.stories || []);
    setLoading(false);
  }

  useEffect(() => { loadData(); }, []);

  async function toggleVoting(ep: Episode) {
    await fetch(`/api/admin/episodes/${ep.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voting_open: !ep.voting_open }),
    });
    loadData();
  }

  async function updateStatus(ep: Episode, status: string) {
    await fetch(`/api/admin/episodes/${ep.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    loadData();
  }

  async function deleteEpisode(ep: Episode) {
    if (!confirm(`Delete Episode ${ep.episode_number}? This cannot be undone.`)) return;
    await fetch(`/api/admin/episodes/${ep.id}`, { method: "DELETE" });
    loadData();
  }

  const [editingEp, setEditingEp] = useState<Episode | null>(null);
  const [epEditForm, setEpEditForm] = useState({
    title: "",
    title_zh: "",
    admin_prompt: "",
    admin_prompt_weight: "0.75",
  });

  function startEditEpisode(ep: Episode) {
    setEditingEp(ep);
    setEpEditForm({
      title: ep.title,
      title_zh: ep.title_zh || "",
      admin_prompt: ep.admin_prompt || "",
      admin_prompt_weight: String(ep.admin_prompt_weight || 0.75),
    });
  }

  async function handleEditEpisode(e: React.FormEvent) {
    e.preventDefault();
    if (!editingEp) return;
    await fetch(`/api/admin/episodes/${editingEp.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: epEditForm.title,
        title_zh: epEditForm.title_zh,
        admin_prompt: epEditForm.admin_prompt || null,
        admin_prompt_weight: epEditForm.admin_prompt ? parseFloat(epEditForm.admin_prompt_weight) : undefined,
      }),
    });
    setEditingEp(null);
    loadData();
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-neon-purple/30 border-t-neon-purple rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">Episodes</h1>
          <p className="text-sm text-white/40 mt-1">Manage all episodes</p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="btn-primary text-sm py-2.5 px-5"
        >
          + New Episode
        </button>
      </div>

      {showCreate && <CreateForm onCreated={() => { setShowCreate(false); loadData(); }} />}

      {/* Episodes grouped by story */}
      {stories.length === 0 && episodes.length === 0 ? (
        <div className="glass-card p-8 text-center text-white/30">
          No stories or episodes yet. Create a story first, then add episodes.
        </div>
      ) : (
        stories.map((story) => {
          const storyEpisodes = episodes
            .filter((ep) => ep.story_id === story.id)
            .sort((a, b) => a.episode_number - b.episode_number);

          if (storyEpisodes.length === 0) return null;

          return (
            <div key={story.id} className="mb-6">
              <div className="flex items-center gap-3 mb-3">
                <h2 className="text-sm font-semibold text-white/70">
                  {story.title} {story.title_zh ? `(${story.title_zh})` : ""}
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/[0.05] text-white/30 border border-white/[0.06]">
                  {storyEpisodes.length} episode{storyEpisodes.length !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="glass-card overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-white/[0.06]">
                        <th className="text-left p-4 text-xs font-medium text-white/40">#</th>
                        <th className="text-left p-4 text-xs font-medium text-white/40">Title</th>
                        <th className="text-left p-4 text-xs font-medium text-white/40">Status</th>
                        <th className="text-left p-4 text-xs font-medium text-white/40">Voting</th>
                        <th className="text-left p-4 text-xs font-medium text-white/40">Published</th>
                        <th className="text-right p-4 text-xs font-medium text-white/40">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {storyEpisodes.map((ep) => (
                        <tr key={ep.id} className="border-b border-white/[0.03] hover:bg-white/[0.02]">
                          <td className="p-4 font-mono text-white/50">
                            {String(ep.episode_number).padStart(2, "0")}
                          </td>
                          <td className="p-4 font-medium">
                            <a href={`/admin/stories/${story.slug}/episodes/${ep.episode_number}`} className="hover:text-neon-cyan transition-colors">
                              {ep.title}
                            </a>
                          </td>
                          <td className="p-4">
                            <select
                              value={ep.status}
                              onChange={(e) => updateStatus(ep, e.target.value)}
                              className="bg-transparent border border-white/10 rounded-lg px-2 py-1 text-xs text-white/60 focus:outline-none focus:border-neon-purple/40"
                            >
                              <option value="draft" className="bg-[#0a0520]">Draft</option>
                              <option value="published" className="bg-[#0a0520]">Published</option>
                              <option value="archived" className="bg-[#0a0520]">Archived</option>
                            </select>
                          </td>
                          <td className="p-4">
                            <button
                              onClick={() => toggleVoting(ep)}
                              className={`text-xs px-2.5 py-1 rounded-full border font-medium transition-colors ${
                                ep.voting_open
                                  ? "bg-neon-cyan/10 text-neon-cyan border-neon-cyan/20 hover:bg-neon-cyan/20"
                                  : "bg-white/5 text-white/30 border-white/10 hover:text-white/50"
                              }`}
                            >
                              {ep.voting_open ? "Open" : "Closed"}
                            </button>
                          </td>
                          <td className="p-4 text-white/40 text-xs">
                            {new Date(ep.published_at).toLocaleDateString()}
                          </td>
                          <td className="p-4 text-right space-x-3">
                            {!ep.video_url && (
                              <button
                                onClick={() => startEditEpisode(ep)}
                                className="text-xs text-neon-cyan/60 hover:text-neon-cyan transition-colors"
                              >
                                Edit
                              </button>
                            )}
                            <button
                              onClick={() => deleteEpisode(ep)}
                              className="text-xs text-red-400/60 hover:text-red-400 transition-colors"
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          );
        })
      )}

      {/* Uncategorized episodes (no matching story) */}
      {(() => {
        const storyIds = new Set(stories.map((s) => s.id));
        const orphans = episodes.filter((ep) => !storyIds.has(ep.story_id));
        if (orphans.length === 0) return null;
        return (
          <div className="mb-6">
            <h2 className="text-sm font-semibold text-white/40 mb-3">Uncategorized</h2>
            <div className="glass-card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <tbody>
                    {orphans.map((ep) => (
                      <tr key={ep.id} className="border-b border-white/[0.03]">
                        <td className="p-4 font-mono text-white/50">{String(ep.episode_number).padStart(2, "0")}</td>
                        <td className="p-4">{ep.title}</td>
                        <td className="p-4 text-xs text-white/30">{ep.status}</td>
                        <td className="p-4 text-right">
                          <button onClick={() => deleteEpisode(ep)} className="text-xs text-red-400/60 hover:text-red-400">Delete</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Edit episode modal */}
      {editingEp && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <form onSubmit={handleEditEpisode} className="glass-card p-6 w-full max-w-lg space-y-4">
            <h3 className="font-semibold text-white/80">
              Edit Episode {String(editingEp.episode_number).padStart(2, "0")}
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-white/40 block mb-1">Title (EN)</label>
                <input
                  type="text"
                  value={epEditForm.title}
                  onChange={(e) => setEpEditForm({ ...epEditForm, title: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50"
                  required
                />
              </div>
              <div>
                <label className="text-xs text-white/40 block mb-1">Title (中文)</label>
                <input
                  type="text"
                  value={epEditForm.title_zh}
                  onChange={(e) => setEpEditForm({ ...epEditForm, title_zh: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50"
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-white/40 block mb-1">Admin Prompt</label>
              <textarea
                value={epEditForm.admin_prompt}
                onChange={(e) => setEpEditForm({ ...epEditForm, admin_prompt: e.target.value })}
                rows={4}
                className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50 resize-none font-mono"
              />
            </div>
            {epEditForm.admin_prompt && (
              <div className="flex items-center gap-4">
                <label className="text-xs text-white/40">Prompt Weight:</label>
                <input
                  type="range"
                  min="0.5"
                  max="1"
                  step="0.05"
                  value={epEditForm.admin_prompt_weight}
                  onChange={(e) => setEpEditForm({ ...epEditForm, admin_prompt_weight: e.target.value })}
                  className="flex-1 h-1.5 accent-neon-purple"
                />
                <span className="text-sm font-mono text-neon-purple w-12 text-right">
                  {Math.round(parseFloat(epEditForm.admin_prompt_weight) * 100)}%
                </span>
              </div>
            )}
            <div className="flex gap-3 pt-2">
              <button type="submit" className="btn-primary text-sm">Save</button>
              <button type="button" onClick={() => setEditingEp(null)} className="text-sm text-white/40 hover:text-white/60">
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

interface CreateStory {
  id: number;
  title: string;
  title_zh: string;
  slug: string;
}

function CreateForm({ onCreated }: { onCreated: () => void }) {
  const [stories, setStories] = useState<CreateStory[]>([]);
  const [allEpisodes, setAllEpisodes] = useState<{ story_id: number; episode_number: number; video_url: string | null }[]>([]);
  const [form, setForm] = useState({
    story_id: "",
    episode_number: "",
    title: "",
    title_zh: "",
    voting_options: "",
    admin_prompt: "",
    admin_prompt_weight: "0.75",
  });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetch("/api/admin/stories")
      .then((r) => r.json())
      .then((d) => setStories(d.stories || []));
    fetch("/api/admin/episodes")
      .then((r) => r.json())
      .then((d) => setAllEpisodes((d.episodes || []).map((e: { story_id: number; episode_number: number; video_url: string | null }) => ({ story_id: e.story_id, episode_number: e.episode_number, video_url: e.video_url }))));
  }, []);

  // Episode numbers that already have video generated for the selected story
  const generatedNumbers = allEpisodes
    .filter((e) => e.story_id === Number(form.story_id) && e.video_url)
    .map((e) => e.episode_number);
  const epNumTaken = generatedNumbers.includes(parseInt(form.episode_number));

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (epNumTaken) return;
    setSubmitting(true);
    const res = await fetch("/api/admin/episodes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        story_id: form.story_id,
        episode_number: parseInt(form.episode_number),
        title: form.title,
        title_zh: form.title_zh || undefined,
        voting_options: form.voting_options
          ? form.voting_options.split("\n").filter((l) => l.trim())
          : undefined,
        admin_prompt: form.admin_prompt || undefined,
        admin_prompt_weight: form.admin_prompt ? parseFloat(form.admin_prompt_weight) : undefined,
      }),
    });
    setSubmitting(false);
    if (res.ok) onCreated();
  }

  return (
    <form onSubmit={handleCreate} className="glass-card p-6 mb-6 space-y-4">
      <h3 className="text-sm font-semibold text-white/60">Create Episode</h3>

      {/* Story selector */}
      <div>
        <label className="text-xs text-white/40 block mb-1">Story</label>
        <select
          value={form.story_id}
          onChange={(e) => setForm({ ...form, story_id: e.target.value })}
          className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-sm text-white focus:outline-none focus:border-neon-purple/40"
          required
        >
          <option value="" className="bg-[#0a0520]">Select a story...</option>
          {stories.map((s) => (
            <option key={s.id} value={s.id} className="bg-[#0a0520]">
              {s.title} {s.title_zh ? `(${s.title_zh})` : ""}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="text-xs text-white/40 block mb-1">Episode #</label>
          <input
            type="number"
            value={form.episode_number}
            onChange={(e) => setForm({ ...form, episode_number: e.target.value })}
            className={`w-full px-3 py-2 rounded-lg bg-white/[0.03] border text-sm text-white focus:outline-none ${epNumTaken ? 'border-red-500/50 focus:border-red-500/70' : 'border-white/[0.08] focus:border-neon-purple/40'}`}
            required
          />
          {epNumTaken && (
            <p className="text-[10px] text-red-400 mt-1">Episode #{form.episode_number} already has a generated video</p>
          )}
        </div>
        <div>
          <label className="text-xs text-white/40 block mb-1">Title (EN)</label>
          <input
            type="text"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-sm text-white focus:outline-none focus:border-neon-purple/40"
            required
          />
        </div>
        <div>
          <label className="text-xs text-white/40 block mb-1">Title (中文)</label>
          <input
            type="text"
            value={form.title_zh}
            onChange={(e) => setForm({ ...form, title_zh: e.target.value })}
            className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-sm text-white focus:outline-none focus:border-neon-purple/40"
          />
        </div>
      </div>

      <div>
        <label className="text-xs text-white/40 block mb-1">
          Voting Options (one per line, optional)
        </label>
        <textarea
          value={form.voting_options}
          onChange={(e) => setForm({ ...form, voting_options: e.target.value })}
          rows={3}
          placeholder="Option A&#10;Option B&#10;Option C"
          className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-neon-purple/40 resize-none"
        />
      </div>

      {/* Admin prompt section */}
      <div className="border-t border-white/[0.06] pt-4">
        <label className="text-xs text-white/40 block mb-1">
          Admin Story Direction Prompt (optional)
        </label>
        <p className="text-xs text-white/20 mb-2">
          Provide narrative direction for this episode. This overrides audience votes at the specified weight.
        </p>
        <textarea
          value={form.admin_prompt}
          onChange={(e) => setForm({ ...form, admin_prompt: e.target.value })}
          rows={4}
          placeholder="e.g. In this episode, the protagonist should discover the hidden message left by their father..."
          className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-neon-purple/40 resize-none font-mono"
        />
        {form.admin_prompt && (
          <div className="mt-3 flex items-center gap-4">
            <label className="text-xs text-white/40">Prompt Weight:</label>
            <input
              type="range"
              min="0.5"
              max="1"
              step="0.05"
              value={form.admin_prompt_weight}
              onChange={(e) => setForm({ ...form, admin_prompt_weight: e.target.value })}
              className="flex-1 h-1.5 accent-neon-purple"
            />
            <span className="text-sm font-mono text-neon-purple w-12 text-right">
              {Math.round(parseFloat(form.admin_prompt_weight) * 100)}%
            </span>
          </div>
        )}
      </div>

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="btn-primary text-sm py-2.5 px-6 disabled:opacity-50"
        >
          {submitting ? "Creating..." : "Create Episode"}
        </button>
        <button
          type="button"
          onClick={onCreated}
          className="text-sm text-white/40 hover:text-white/60 px-4 py-2.5"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
