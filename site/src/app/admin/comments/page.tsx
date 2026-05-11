"use client";

import { useState, useEffect } from "react";

interface Comment {
  id: number;
  episode_id: number;
  author: string;
  content: string;
  moderated: boolean;
  flagged: boolean;
  created_at: string;
}

export default function AdminComments() {
  const [comments, setComments] = useState<Comment[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "pending" | "flagged">("pending");

  async function loadComments() {
    const res = await fetch("/api/admin/comments");
    const data = await res.json();
    setComments(data.comments || []);
    setLoading(false);
  }

  useEffect(() => { loadComments(); }, []);

  async function moderate(id: number, action: "approve" | "flag" | "delete") {
    await fetch("/api/admin/comments", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, action }),
    });
    loadComments();
  }

  const filtered = comments.filter((c) => {
    if (filter === "pending") return !c.moderated && !c.flagged;
    if (filter === "flagged") return c.flagged;
    return true;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-neon-purple/30 border-t-neon-purple rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Comment Moderation</h1>
        <p className="text-sm text-white/40 mt-1">
          Review and moderate audience comments before they appear publicly
        </p>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-6">
        {(["pending", "flagged", "all"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-xs px-4 py-2 rounded-lg border font-medium transition-all ${
              filter === f
                ? "bg-neon-purple/10 text-neon-purple border-neon-purple/30"
                : "bg-white/[0.02] text-white/40 border-white/[0.06] hover:text-white/60"
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
            {f === "pending" && (
              <span className="ml-1.5 text-[10px] bg-white/10 px-1.5 py-0.5 rounded-full">
                {comments.filter((c) => !c.moderated && !c.flagged).length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Comments list */}
      <div className="space-y-3">
        {filtered.length === 0 ? (
          <div className="glass-card p-8 text-center">
            <p className="text-white/30">No comments in this category.</p>
          </div>
        ) : (
          filtered.map((c) => (
            <div key={c.id} className="glass-card p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-sm font-medium text-white/70">{c.author}</span>
                    <span className="text-xs text-white/20">Ep #{c.episode_id}</span>
                    <span className="text-xs text-white/20">
                      {new Date(c.created_at).toLocaleString()}
                    </span>
                    {c.moderated && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-500/10 text-green-400 border border-green-500/20">
                        Approved
                      </span>
                    )}
                    {c.flagged && (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-400/10 text-red-400 border border-red-400/20">
                        Flagged
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-white/50 leading-relaxed">{c.content}</p>
                </div>
                <div className="flex gap-2 shrink-0">
                  {!c.moderated && (
                    <button
                      onClick={() => moderate(c.id, "approve")}
                      className="text-xs px-3 py-1.5 rounded-lg bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-colors"
                    >
                      Approve
                    </button>
                  )}
                  {!c.flagged && (
                    <button
                      onClick={() => moderate(c.id, "flag")}
                      className="text-xs px-3 py-1.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-colors"
                    >
                      Flag
                    </button>
                  )}
                  <button
                    onClick={() => moderate(c.id, "delete")}
                    className="text-xs px-3 py-1.5 rounded-lg bg-red-400/10 text-red-400 border border-red-400/20 hover:bg-red-400/20 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
