"use client";

import { useState, type ReactNode } from "react";
import type { Locale } from "@/lib/i18n";

interface Tab {
  id: string;
  label: string;
  badge?: boolean;
  icon: string;
}

interface Props {
  locale: Locale;
  hasActiveVote: boolean;
  episodesContent: ReactNode;
  voteContent: ReactNode;
  galleryContent: ReactNode;
  discussionContent: ReactNode;
}

export function StoryTabs({
  locale,
  hasActiveVote,
  episodesContent,
  voteContent,
  galleryContent,
  discussionContent,
}: Props) {
  const tabs: Tab[] = [
    {
      id: "episodes",
      label: locale === "zh" ? "剧集" : "Episodes",
      icon: "M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z",
    },
    {
      id: "vote",
      label: locale === "zh" ? "投票" : "Vote",
      badge: hasActiveVote,
      icon: "M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
    },
    {
      id: "gallery",
      label: locale === "zh" ? "画廊" : "Gallery",
      icon: "M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0022.5 18.75V5.25A2.25 2.25 0 0020.25 3H3.75A2.25 2.25 0 001.5 5.25v13.5A2.25 2.25 0 003.75 21z",
    },
    {
      id: "discussion",
      label: locale === "zh" ? "讨论" : "Discussion",
      icon: "M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z",
    },
  ];

  const [active, setActive] = useState("episodes");

  const contentMap: Record<string, ReactNode> = {
    episodes: episodesContent,
    vote: voteContent,
    gallery: galleryContent,
    discussion: discussionContent,
  };

  return (
    <div>
      {/* Tab bar */}
      <div className="flex items-center gap-1 border-b border-white/[0.06] mb-8 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActive(tab.id)}
            className={`relative flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap ${
              active === tab.id
                ? "text-white"
                : "text-white/40 hover:text-white/60"
            }`}
          >
            <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round" d={tab.icon} />
            </svg>
            {tab.label}
            {tab.badge && (
              <span className="w-1.5 h-1.5 rounded-full bg-neon-cyan animate-pulse" />
            )}
            {active === tab.id && (
              <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-gradient-to-r from-neon-purple to-neon-cyan" />
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>{contentMap[active]}</div>
    </div>
  );
}
