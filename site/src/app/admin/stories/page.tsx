"use client";
import { useState, useEffect } from "react";

interface Story {
  id: string;
  title: string;
  title_zh: string;
  slug: string;
  description: string;
  description_zh: string;
  background: string;
  status: string;
  poster_episode_id: number | null;
  selected_poster_en: string | null;
  selected_poster_zh: string | null;
  created_at: string;
}

export default function AdminStoriesPage() {
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [posterStoryId, setPosterStoryId] = useState<string | null>(null);
  const [storyPosters, setStoryPosters] = useState<Record<string, string>>({});
  const [posterLoading, setPosterLoading] = useState(false);
  const [zoomUrl, setZoomUrl] = useState<string | null>(null);
  const [posterSelections, setPosterSelections] = useState<Record<string, { en: string; zh: string }>>({});
  const [editForm, setEditForm] = useState({
    title: "",
    title_zh: "",
    description: "",
    description_zh: "",
    background: "",
    status: "active",
  });
  const [form, setForm] = useState({
    title: "",
    title_zh: "",
    slug: "",
    description: "",
    description_zh: "",
    background: "",
  });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchStories();
  }, []);

  async function fetchStories() {
    const res = await fetch("/api/admin/stories");
    const data = await res.json();
    setStories(data.stories || []);
    setLoading(false);
  }

  async function loadPosters(storyId: string) {
    if (posterStoryId === storyId) {
      setPosterStoryId(null);
      return;
    }
    setPosterStoryId(storyId);
    setPosterLoading(true);
    try {
      const res = await fetch(`/api/admin/stories/${storyId}/posters`);
      const data = await res.json();
      setStoryPosters(data.story_posters || {});
      // Initialize poster selections from story data
      const story = stories.find((s) => s.id === storyId);
      if (story) {
        setPosterSelections((prev) => ({
          ...prev,
          [storyId]: {
            en: story.selected_poster_en || "",
            zh: story.selected_poster_zh || "",
          },
        }));
      }
    } catch {
      setStoryPosters({});
    }
    setPosterLoading(false);
  }

  async function savePosterSelection(storyId: string, lang: "en" | "zh", filename: string) {
    const key = lang === "en" ? "selected_poster_en" : "selected_poster_zh";
    setPosterSelections((prev) => ({
      ...prev,
      [storyId]: { ...prev[storyId], [lang]: filename },
    }));
    await fetch(`/api/admin/stories/${storyId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [key]: filename || null }),
    });
    fetchStories();
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    await fetch("/api/admin/stories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    setForm({ title: "", title_zh: "", slug: "", description: "", description_zh: "", background: "" });
    setShowForm(false);
    setSubmitting(false);
    fetchStories();
  }

  function startEdit(story: Story) {
    setEditingId(story.id);
    setEditForm({
      title: story.title,
      title_zh: story.title_zh || "",
      description: story.description || "",
      description_zh: story.description_zh || "",
      background: story.background || "",
      status: story.status || "active",
    });
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    await fetch(`/api/admin/stories/${editingId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(editForm),
    });
    setEditingId(null);
    setSubmitting(false);
    fetchStories();
  }

  function autoSlug(title: string) {
    return title
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  }

  return (
    <>
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold">Stories</h1>
          <p className="text-sm text-white/40 mt-1">
            Manage story universes. Each story has its own episodes, characters, and audience.
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="btn-primary text-sm"
        >
          {showForm ? "Cancel" : "+ New Story"}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          className="glass-card p-6 mb-8 space-y-4"
        >
          <h3 className="font-medium text-white/70 mb-3">Create Story Universe</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-white/40 block mb-1">Title (EN)</label>
              <input
                type="text"
                value={form.title}
                onChange={(e) => {
                  setForm({ ...form, title: e.target.value, slug: autoSlug(e.target.value) });
                }}
                className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50"
                required
              />
            </div>
            <div>
              <label className="text-xs text-white/40 block mb-1">Title (中文)</label>
              <input
                type="text"
                value={form.title_zh}
                onChange={(e) => setForm({ ...form, title_zh: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-white/40 block mb-1">Slug</label>
            <input
              type="text"
              value={form.slug}
              onChange={(e) => setForm({ ...form, slug: e.target.value })}
              className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-white/40 block mb-1">Description (EN)</label>
              <textarea
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                rows={2}
                className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50 resize-none"
              />
            </div>
            <div>
              <label className="text-xs text-white/40 block mb-1">Description (中文)</label>
              <textarea
                value={form.description_zh}
                onChange={(e) => setForm({ ...form, description_zh: e.target.value })}
                rows={2}
                className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50 resize-none"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-white/40 block mb-1">
              Story Background &amp; First Episode Prompt
            </label>
            <p className="text-xs text-white/20 mb-2">
              Provide the world-building, themes, tone, and initial narrative direction. This drives the AI agents to create the first episode.
            </p>
            <textarea
              value={form.background}
              onChange={(e) => setForm({ ...form, background: e.target.value })}
              rows={6}
              className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50 resize-none font-mono"
              placeholder="e.g. A cyberpunk city in 2099. Neon-lit streets, AI companions, underground resistance. The protagonist discovers..."
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="btn-primary text-sm disabled:opacity-40"
          >
            {submitting ? "Creating..." : "Create Story"}
          </button>
        </form>
      )}

      {loading ? (
        <div className="text-center text-white/30 py-12">Loading...</div>
      ) : stories.length === 0 ? (
        <div className="glass-card p-12 text-center">
          <p className="text-white/40">No stories yet. Click &quot;+ New Story&quot; to kickoff your first story universe.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {stories.map((story) => (
            <div key={story.id} className="glass-card p-6">
              {editingId === story.id ? (
                <form onSubmit={handleEdit} className="space-y-4">
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
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs text-white/40 block mb-1">Description (EN)</label>
                      <textarea
                        value={editForm.description}
                        onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                        rows={2}
                        className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50 resize-none"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-white/40 block mb-1">Description (中文)</label>
                      <textarea
                        value={editForm.description_zh}
                        onChange={(e) => setEditForm({ ...editForm, description_zh: e.target.value })}
                        rows={2}
                        className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50 resize-none"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-white/40 block mb-1">Background</label>
                    <textarea
                      value={editForm.background}
                      onChange={(e) => setEditForm({ ...editForm, background: e.target.value })}
                      rows={4}
                      className="w-full px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50 resize-none font-mono"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-white/40 block mb-1">Status</label>
                    <select
                      value={editForm.status}
                      onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
                      className="px-3 py-2 rounded-lg bg-white/[0.03] border border-white/[0.08] text-white text-sm focus:outline-none focus:border-neon-purple/50"
                    >
                      <option value="active" className="bg-[#0a0520]">Active</option>
                      <option value="draft" className="bg-[#0a0520]">Draft</option>
                      <option value="completed" className="bg-[#0a0520]">Completed</option>
                    </select>
                  </div>
                  <div className="flex gap-3">
                    <button type="submit" disabled={submitting} className="btn-primary text-sm disabled:opacity-40">
                      {submitting ? "Saving..." : "Save Changes"}
                    </button>
                    <button type="button" onClick={() => setEditingId(null)} className="text-sm text-white/40 hover:text-white/60">
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-semibold text-lg">{story.title}</h3>
                      {story.title_zh && (
                        <p className="text-white/50 text-sm">{story.title_zh}</p>
                      )}
                      <p className="text-xs text-white/30 mt-1">/{story.slug}</p>
                      {story.description && (
                        <p className="text-sm text-white/50 mt-2 max-w-2xl">{story.description}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => startEdit(story)}
                        className="text-xs text-neon-cyan/60 hover:text-neon-cyan transition-colors"
                      >
                        Edit
                      </button>
                      <span className={`text-xs px-2 py-1 rounded-full ${
                        story.status === "active"
                          ? "bg-green-500/10 text-green-400 border border-green-500/20"
                          : "bg-white/5 text-white/30 border border-white/10"
                      }`}>
                        {story.status}
                      </span>
                    </div>
                  </div>
                  {story.background && (
                    <div className="mt-4 p-3 rounded-lg bg-white/[0.02] border border-white/[0.05]">
                      <p className="text-xs text-white/30 mb-1">Background / First Episode Direction:</p>
                      <p className="text-sm text-white/50 font-mono whitespace-pre-wrap">{story.background}</p>
                    </div>
                  )}

                  {/* Story Poster Management */}
                  <div className="mt-4">
                    <button
                      onClick={() => loadPosters(story.id)}
                      className="text-xs text-neon-purple/60 hover:text-neon-purple transition-colors flex items-center gap-1.5"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v13.5A1.5 1.5 0 003.75 21z" />
                      </svg>
                      {posterStoryId === story.id ? "Hide Posters" : "Story Posters"}
                    </button>

                    {posterStoryId === story.id && (
                      <div className="mt-3 p-4 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                        {posterLoading ? (
                          <p className="text-xs text-white/30">Loading posters...</p>
                        ) : Object.keys(storyPosters).length === 0 ? (
                          <p className="text-xs text-white/30">No story posters generated yet. Run the Publish step to generate posters.</p>
                        ) : (
                          <div className="space-y-6">
                            <p className="text-xs text-white/40">
                              Story posters from <code className="text-white/50">data/stories/{story.slug}/poster/</code>
                            </p>
                            {/* Group posters by language */}
                            {(["en", "zh"] as const).map((lang) => {
                              const langLabel = lang === "zh" ? "中文 (Chinese)" : "English";
                              const langPosters = Object.entries(storyPosters).filter(
                                ([variant]) => variant.endsWith(`_${lang}`)
                              );
                              if (langPosters.length === 0) return null;
                              const currentSel = posterSelections[story.id]?.[lang] || "";
                              return (
                                <div key={lang} className="p-3 rounded-lg border border-white/[0.06]">
                                  <p className="text-sm font-medium text-white/70 mb-1">{langLabel}</p>
                                  <p className="text-[10px] text-white/30 mb-3">
                                    {lang === "en" ? "Select poster for English frontend" : "选择中文前端显示的海报"}
                                  </p>
                                  <div className="grid grid-cols-2 gap-4">
                                    {langPosters.map(([variant, url]) => {
                                      const isVertical = variant.startsWith("vertical");
                                      const filename = url.split("/").pop() || "";
                                      const isSelected = currentSel === filename;
                                      return (
                                        <div key={variant} className="text-center">
                                          <div
                                            className={`relative cursor-pointer rounded border-2 transition-all overflow-hidden ${
                                              isSelected
                                                ? "border-neon-purple shadow-lg shadow-neon-purple/20"
                                                : "border-white/10 hover:border-white/20"
                                            }`}
                                            onClick={() => setZoomUrl(url)}
                                          >
                                            <img
                                              src={url}
                                              alt={`Story poster ${variant}`}
                                              className={`w-full object-contain ${
                                                isVertical ? "max-h-80" : "max-h-48"
                                              }`}
                                            />
                                            <div className="absolute top-1 right-1 bg-black/60 rounded px-1.5 py-0.5 text-[9px] text-white/50">
                                              🔍 Click to zoom
                                            </div>
                                          </div>
                                          <div className="flex items-center justify-center gap-2 mt-2">
                                            <label className="flex items-center gap-1.5 cursor-pointer">
                                              <input
                                                type="radio"
                                                name={`poster-${story.id}-${lang}`}
                                                checked={isSelected}
                                                onChange={() => savePosterSelection(story.id, lang, filename)}
                                                className="accent-neon-purple"
                                              />
                                              <span className="text-[10px] text-white/50">
                                                {isVertical ? "Vertical (9:16)" : "Horizontal (16:9)"}
                                              </span>
                                            </label>
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                  {currentSel && (
                                    <button
                                      onClick={() => savePosterSelection(story.id, lang, "")}
                                      className="text-[10px] text-white/30 hover:text-white/50 mt-2"
                                    >
                                      Clear selection (use auto)
                                    </button>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>

    {/* Zoom modal */}
    {zoomUrl && (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
        onClick={() => setZoomUrl(null)}
      >
        <div className="relative max-w-[90vw] max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
          <img
            src={zoomUrl}
            alt="Poster full view"
            className="max-w-full max-h-[90vh] object-contain rounded-lg shadow-2xl"
          />
          <button
            onClick={() => setZoomUrl(null)}
            className="absolute -top-3 -right-3 w-8 h-8 bg-white/10 hover:bg-white/20 rounded-full flex items-center justify-center text-white/80 transition-colors border border-white/20"
          >
            ✕
          </button>
        </div>
      </div>
    )}
    </>
  );
}
