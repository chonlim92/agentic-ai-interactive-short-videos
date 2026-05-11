"use client";

import { useState, useEffect } from "react";
import { useLocale } from "@/lib/useLocale";
import type { VoteOption } from "@/lib/db";

interface Props {
  episodeId: number;
  options: VoteOption[];
  votingDeadline?: string | null;
}

function useCountdown(deadline: string | null | undefined) {
  const [remaining, setRemaining] = useState<{
    days: number;
    hours: number;
    minutes: number;
    seconds: number;
    expired: boolean;
    total: number;
  } | null>(null);

  useEffect(() => {
    if (!deadline) return;
    function calc() {
      const diff = new Date(deadline!).getTime() - Date.now();
      if (diff <= 0) {
        setRemaining({ days: 0, hours: 0, minutes: 0, seconds: 0, expired: true, total: 0 });
        return;
      }
      const days = Math.floor(diff / 86400000);
      const hours = Math.floor((diff % 86400000) / 3600000);
      const minutes = Math.floor((diff % 3600000) / 60000);
      const seconds = Math.floor((diff % 60000) / 1000);
      setRemaining({ days, hours, minutes, seconds, expired: false, total: diff });
    }
    calc();
    const id = setInterval(calc, 1000);
    return () => clearInterval(id);
  }, [deadline]);

  return remaining;
}

export function VoteForm({ episodeId, options, votingDeadline }: Props) {
  const locale = useLocale();
  const countdown = useCountdown(votingDeadline);
  const [selected, setSelected] = useState<number | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/vote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ episodeId, optionId: selected }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || "Failed to submit vote");
      } else {
        setSubmitted(true);
      }
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (submitted) {
    return (
      <div className="text-center py-8">
        <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-green-500/20 to-green-500/5 border border-green-500/20 flex items-center justify-center mx-auto mb-4">
          <svg viewBox="0 0 24 24" className="w-7 h-7 text-green-400" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
        </div>
        <p className="text-lg font-semibold text-green-400 mb-1">
          {locale === "zh" ? "投票已提交！" : "Vote submitted!"}
        </p>
        <p className="text-sm text-white/30">
          {locale === "zh" ? "投票结束后将公布结果。" : "Results will be revealed after voting closes."}
        </p>
      </div>
    );
  }

  if (countdown?.expired) {
    return (
      <div className="text-center py-8">
        <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-500/20 to-amber-500/5 border border-amber-500/20 flex items-center justify-center mx-auto mb-4">
          <svg viewBox="0 0 24 24" className="w-7 h-7 text-amber-400" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <p className="text-lg font-semibold text-amber-400 mb-1">
          {locale === "zh" ? "投票已截止" : "Voting deadline has passed"}
        </p>
        <p className="text-sm text-white/30">
          {locale === "zh" ? "投票结果将会公布。" : "Results will be announced."}
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {/* Countdown timer */}
      {countdown && !countdown.expired && (
        <div className="flex items-center gap-3 p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] mb-2">
          <svg viewBox="0 0 24 24" className="w-4 h-4 text-neon-cyan shrink-0" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="flex-1">
            <p className="text-xs text-white/40">
              {locale === "zh" ? "投票截止倒计时" : "Vote closes in"}
            </p>
            <div className="flex items-baseline gap-1.5 mt-0.5">
              {countdown.days > 0 && (
                <span className="text-sm font-mono font-bold text-neon-cyan">
                  {countdown.days}<span className="text-[10px] text-white/30 ml-0.5">{locale === "zh" ? "天" : "d"}</span>
                </span>
              )}
              <span className="text-sm font-mono font-bold text-neon-cyan">
                {String(countdown.hours).padStart(2, "0")}<span className="text-[10px] text-white/30 ml-0.5">{locale === "zh" ? "时" : "h"}</span>
              </span>
              <span className="text-sm font-mono font-bold text-neon-cyan">
                {String(countdown.minutes).padStart(2, "0")}<span className="text-[10px] text-white/30 ml-0.5">{locale === "zh" ? "分" : "m"}</span>
              </span>
              <span className="text-sm font-mono font-bold text-neon-cyan">
                {String(countdown.seconds).padStart(2, "0")}<span className="text-[10px] text-white/30 ml-0.5">{locale === "zh" ? "秒" : "s"}</span>
              </span>
            </div>
          </div>
          {votingDeadline && (
            <p className="text-[10px] text-white/20 text-right">
              {new Date(votingDeadline).toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
              {" "}
              {new Date(votingDeadline).toLocaleTimeString(locale === "zh" ? "zh-CN" : "en-US", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </p>
          )}
        </div>
      )}

      {options.map((option) => (
        <label
          key={option.id}
          className={`block p-4 rounded-xl border cursor-pointer transition-all duration-300 ${
            selected === option.id
              ? "border-neon-purple/50 bg-neon-purple/10 shadow-lg shadow-neon-purple/5"
              : "border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12] hover:bg-white/[0.04]"
          }`}
        >
          <input
            type="radio"
            name="vote"
            value={option.id}
            checked={selected === option.id}
            onChange={() => setSelected(option.id)}
            className="sr-only"
          />
          <div className="flex items-center gap-3">
            <div
              className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors ${
                selected === option.id
                  ? "border-neon-purple bg-neon-purple"
                  : "border-white/20"
              }`}
            >
              {selected === option.id && (
                <div className="w-2 h-2 rounded-full bg-white" />
              )}
            </div>
            <div>
              <span className="font-medium text-sm">{locale === "zh" && option.label_zh ? option.label_zh : option.label}</span>
              {(option.description || option.description_zh) && (
                <p className="text-xs text-white/30 mt-0.5">{locale === "zh" && option.description_zh ? option.description_zh : option.description}</p>
              )}
            </div>
          </div>
        </label>
      ))}

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-400 bg-red-400/5 border border-red-400/10 rounded-lg px-4 py-2.5">
          <svg viewBox="0 0 24 24" className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={!selected || loading}
        className="w-full btn-primary py-4 mt-4 disabled:opacity-30 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none"
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-20" />
              <path d="M12 2a10 10 0 019.95 9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
            </svg>
            {locale === "zh" ? "提交中..." : "Submitting..."}
          </span>
        ) : (
          locale === "zh" ? "提交投票" : "Submit Vote"
        )}
      </button>
    </form>
  );
}
