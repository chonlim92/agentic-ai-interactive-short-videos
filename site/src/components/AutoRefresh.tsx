"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

/**
 * Polls /api/freshness and triggers a router.refresh() when the episode data
 * has been updated (e.g. after a publish run). Invisible component.
 */
export function AutoRefresh({
  storySlug,
  episodeNumber,
  intervalMs = 10_000,
}: {
  storySlug: string;
  episodeNumber?: number;
  intervalMs?: number;
}) {
  const router = useRouter();
  const lastTs = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const qs = new URLSearchParams({ story: storySlug });
        if (episodeNumber != null) qs.set("episode", String(episodeNumber));
        const res = await fetch(`/api/freshness?${qs}`, { cache: "no-store" });
        if (!res.ok) return;
        const { ts } = await res.json();
        if (lastTs.current === null) {
          // First check — just record the baseline
          lastTs.current = ts;
        } else if (ts > lastTs.current) {
          // Data has changed — refresh the page
          lastTs.current = ts;
          router.refresh();
        }
      } catch {
        // Network error — ignore, retry next interval
      }
    }

    // Initial check
    check();
    const id = setInterval(() => {
      if (!cancelled) check();
    }, intervalMs);

    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [storySlug, episodeNumber, intervalMs, router]);

  return null; // Invisible component
}
