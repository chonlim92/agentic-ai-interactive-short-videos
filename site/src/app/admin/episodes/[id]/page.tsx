"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

/**
 * Legacy redirect: /admin/episodes/[id] → /admin/stories/[slug]/episodes/[episodeNumber]
 */
export default function EpisodeDetailRedirect() {
  const params = useParams();
  const router = useRouter();

  useEffect(() => {
    const id = params.id;
    // Fetch episode and stories to resolve the slug, then redirect
    Promise.all([
      fetch(`/api/admin/episodes/${id}`).then((r) => r.json()),
      fetch("/api/admin/stories").then((r) => r.json()),
    ])
      .then(([epData, stData]) => {
        if (epData.episode) {
          const stories = stData.stories || [];
          const story = stories.find((s: { id: number }) => s.id === epData.episode.story_id);
          const slug = story?.slug || String(epData.episode.story_id);
          router.replace(`/admin/stories/${slug}/episodes/${epData.episode.episode_number}`);
        } else {
          router.replace("/admin/episodes");
        }
      })
      .catch(() => router.replace("/admin/episodes"));
  }, [params.id, router]);

  return (
    <div className="flex items-center justify-center h-64">
      <div className="w-8 h-8 border-2 border-neon-purple/30 border-t-neon-purple rounded-full animate-spin" />
    </div>
  );
}
