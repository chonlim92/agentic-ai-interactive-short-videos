import { getEpisode, getStoryById } from "@/lib/db";
import { notFound, redirect } from "next/navigation";

interface Props {
  params: { id: string };
}

/**
 * Legacy redirect: /episodes/[id] → /stories/[slug]/episodes/[id]
 */
export default async function EpisodeRedirectPage({ params }: Props) {
  const episodeNumber = parseInt(params.id, 10);
  if (isNaN(episodeNumber)) notFound();

  const episode = await getEpisode(episodeNumber);
  if (!episode) notFound();

  const story = await getStoryById(episode.story_id);
  if (!story) notFound();

  redirect(`/stories/${story.slug}/episodes/${episode.episode_number}`);
}
