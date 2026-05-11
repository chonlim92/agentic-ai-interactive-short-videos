"use client";

import { useLocale } from "@/lib/useLocale";

interface EpisodeVideoPlayerProps {
  videoUrl?: string | null;
  videoUrlEn?: string | null;
  posterUrl?: string;
}

export function EpisodeVideoPlayer({ videoUrl, videoUrlEn, posterUrl }: EpisodeVideoPlayerProps) {
  const locale = useLocale();

  // Use EN video when locale is EN and an EN version is available
  const effectiveUrl = locale === "en" && videoUrlEn ? videoUrlEn : videoUrl;

  if (!effectiveUrl) {
    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
        <div className="w-20 h-20 rounded-full bg-white/5 border border-white/10 flex items-center justify-center">
          <svg viewBox="0 0 24 24" className="w-8 h-8 text-white/30" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
        </div>
        <p className="text-white/30 text-sm">Video coming soon</p>
      </div>
    );
  }

  return (
    <video
      key={effectiveUrl}
      src={effectiveUrl}
      controls
      className="w-full h-full object-contain"
      poster={posterUrl}
    />
  );
}
