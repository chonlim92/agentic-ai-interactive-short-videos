"use client";

import { useState, useEffect } from "react";

interface CommentData {
  id: number;
  author: string;
  content: string;
  created_at: string;
}

export function CommentSection({ episodeId }: { episodeId: number }) {
  const [comments, setComments] = useState<CommentData[]>([]);
  const [author, setAuthor] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    fetch(`/api/episodes/${episodeId}/comments`)
      .then((r) => r.json())
      .then((data) => setComments(data.comments || []))
      .catch(() => {});
  }, [episodeId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!author.trim() || !content.trim()) return;

    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      const res = await fetch(`/api/episodes/${episodeId}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ author: author.trim(), content: content.trim() }),
      });

      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Failed to post comment");
      } else {
        setSuccess(true);
        setContent("");
      }
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Comment form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="text-xs text-white/40 block mb-1.5">Name</label>
          <input
            type="text"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            maxLength={50}
            placeholder="Your name"
            className="w-full px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-neon-purple/40 transition-colors"
          />
        </div>
        <div>
          <label className="text-xs text-white/40 block mb-1.5">Comment</label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            maxLength={1000}
            rows={3}
            placeholder="Share your thoughts on this episode..."
            className="w-full px-4 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-sm text-white placeholder:text-white/20 focus:outline-none focus:border-neon-purple/40 transition-colors resize-none"
          />
          <span className="text-xs text-white/20 mt-1 block text-right">
            {content.length}/1000
          </span>
        </div>

        {error && (
          <div className="text-sm text-red-400 bg-red-400/5 border border-red-400/10 rounded-lg px-4 py-2">
            {error}
          </div>
        )}

        {success && (
          <div className="text-sm text-green-400 bg-green-400/5 border border-green-400/10 rounded-lg px-4 py-2">
            Comment submitted! It will appear after moderation.
          </div>
        )}

        <button
          type="submit"
          disabled={!author.trim() || !content.trim() || loading}
          className="btn-primary py-2.5 px-6 text-sm disabled:opacity-30 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
        >
          {loading ? "Posting..." : "Post Comment"}
        </button>
      </form>

      {/* Comments list */}
      {comments.length > 0 && (
        <div className="space-y-4 pt-4 border-t border-white/[0.06]">
          <h4 className="text-sm font-medium text-white/50">
            {comments.length} Comment{comments.length !== 1 ? "s" : ""}
          </h4>
          {comments.map((c) => (
            <div
              key={c.id}
              className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06]"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-white/70">{c.author}</span>
                <span className="text-xs text-white/20">
                  {new Date(c.created_at).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                  })}
                </span>
              </div>
              <p className="text-sm text-white/50 leading-relaxed">{c.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
