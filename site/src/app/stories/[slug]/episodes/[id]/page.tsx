import { getEpisode, getStory, getVoteOptions, getVoteResults, getEpisodePosterUrl, computeVotingDeadline, getEpisodeNarrative, getEpisodeGalleryUrls, cacheBustAssetUrl, getEpisodePosterUrls } from "@/lib/db";
import { notFound } from "next/navigation";
import { cookies } from "next/headers";
import Link from "next/link";
import { VoteForm } from "@/components/VoteForm";
import { CommentSection } from "@/components/CommentSection";
import { EpisodeVideoPlayer } from "@/components/EpisodeVideoPlayer";
import { GalleryGrid } from "@/components/GalleryGrid";
import { AutoRefresh } from "@/components/AutoRefresh";
import type { Locale } from "@/lib/i18n";

export const dynamic = "force-dynamic";

interface Props {
  params: { slug: string; id: string };
}

export default async function StoryEpisodePage({ params }: Props) {
  const locale = (cookies().get("locale")?.value || "en") as Locale;
  const story = await getStory(params.slug);
  if (!story) notFound();

  const episodeNumber = parseInt(params.id, 10);
  if (isNaN(episodeNumber)) notFound();

  const episode = await getEpisode(episodeNumber, story.id);
  if (!episode) notFound();

  const options = await getVoteOptions(episode.id);
  const results = await getVoteResults(episode.id);
  const totalVotes = results.reduce((sum, r) => sum + r.count, 0);
  const votingDeadline = computeVotingDeadline(episode);

  const posterUrl = getEpisodePosterUrl(story, episodeNumber, locale);
  const videoPosterUrl = getEpisodePosterUrl(story, episodeNumber, locale, "vertical");
  const allPosters = getEpisodePosterUrls(story, episodeNumber, locale);
  const galleryUrls = getEpisodeGalleryUrls(story, episodeNumber);

  const episodeTitle = locale === "zh" && episode.title_zh ? episode.title_zh : episode.title;
  const episodeSubtitle = locale === "zh" ? episode.title : episode.title_zh;
  const narrativeSummary = getEpisodeNarrative(story, episodeNumber, locale);

  return (
    <main className="min-h-[calc(100vh-4rem)] px-6 py-16">
      <AutoRefresh storySlug={params.slug} episodeNumber={episodeNumber} />
      <div className="max-w-7xl mx-auto">
        {/* Back to story */}
        <Link
          href={`/stories/${params.slug}`}
          prefetch={false}
          className="inline-flex items-center gap-1.5 text-xs text-white/30 hover:text-white/50 transition-colors mb-6"
        >
          <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
          {locale === "zh" && story.title_zh ? story.title_zh : story.title}
        </Link>

        {/* Episode header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-xs px-3 py-1 rounded-full bg-neon-purple/10 text-neon-purple border border-neon-purple/20 font-medium">
              {locale === "zh" ? `第 ${episode.episode_number} 集` : `Episode ${episode.episode_number}`}
            </span>
            {episode.published_at && (
              <span className="text-xs text-white/30">
                {new Date(episode.published_at).toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", {
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                })}
              </span>
            )}
          </div>
          <h1 className="text-3xl md:text-4xl font-bold">{episodeTitle}</h1>
          {episodeSubtitle && (
            <p className="text-lg text-white/50 mt-2">{episodeSubtitle}</p>
          )}
          {narrativeSummary && (
            <p className="text-sm text-white/40 mt-3 leading-relaxed">{narrativeSummary}</p>
          )}
        </div>

        {/* Two-column layout: Video left, Voting + Comments right */}
        <div className="flex flex-col lg:flex-row gap-8">
          {/* Left: Video Player */}
          <div className="lg:w-[420px] shrink-0">
            <div className="glass-card overflow-hidden sticky top-24">
              <div className="aspect-[9/16] bg-black/50 relative">
                <EpisodeVideoPlayer
                  videoUrl={episode.video_url ? cacheBustAssetUrl(episode.video_url) : undefined}
                  videoUrlEn={episode.video_url_en ? cacheBustAssetUrl(episode.video_url_en) : undefined}
                  posterUrl={episode.thumbnail_url ? cacheBustAssetUrl(episode.thumbnail_url) : videoPosterUrl || undefined}
                />
              </div>
            </div>
          </div>

          {/* Right: Voting + Comments */}
          <div className="flex-1 min-w-0 space-y-8">
            {/* Voting Section */}
            <section className="glass-card p-8">
              <h2 className="text-xl font-bold mb-6 flex items-center gap-3">
                <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-neon-cyan/20 to-neon-cyan/5 border border-neon-cyan/20 flex items-center justify-center">
                  <svg viewBox="0 0 24 24" className="w-4 h-4 text-neon-cyan" fill="none" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </span>
                {locale === "zh" ? "接下来应该发生什么？" : "What should happen next?"}
              </h2>

              {episode.voting_open ? (
                <VoteForm episodeId={episode.id} options={options} votingDeadline={votingDeadline} />
              ) : options.length > 0 || results.length > 0 ? (
                <div>
                  <p className="text-white/40 mb-6 text-sm">{locale === "zh" ? "投票已结束，以下是结果：" : "Voting has closed. Here are the results:"}</p>
                  <div className="space-y-4">
                    {results.map((r, i) => {
                      const pct = totalVotes > 0 ? Math.round((r.count / totalVotes) * 100) : 0;
                      const isWinner = i === 0 && totalVotes > 0;
                      return (
                        <div key={r.option_id} className="relative">
                          <div className="flex justify-between items-center text-sm mb-2">
                            <span className={`font-medium ${isWinner ? "text-neon-cyan" : "text-white/70"}`}>
                              {locale === "zh" && r.label_zh ? r.label_zh : r.label}
                            </span>
                            <span className="text-white/40 font-mono text-xs">{pct}%</span>
                          </div>
                          <div className="h-2 bg-white/5 rounded-full overflow-hidden border border-white/[0.06]">
                            <div
                              className={`h-full rounded-full transition-all duration-1000 ${
                                isWinner
                                  ? "bg-gradient-to-r from-neon-purple to-neon-cyan"
                                  : "bg-white/10"
                              }`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <p className="text-xs text-white/20 mt-4">
                    {locale === "zh" ? `总投票数：${totalVotes}` : `Total votes: ${totalVotes}`}
                  </p>
                </div>
              ) : (
                <p className="text-white/30 text-sm">{locale === "zh" ? "暂无投票选项" : "No voting options available yet."}</p>
              )}
            </section>

            {/* Comments Section */}
            <section className="glass-card p-8">
              <h2 className="text-xl font-bold mb-6 flex items-center gap-3">
                <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-neon-pink/20 to-neon-pink/5 border border-neon-pink/20 flex items-center justify-center">
                  <svg viewBox="0 0 24 24" className="w-4 h-4 text-neon-pink" fill="none" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
                  </svg>
                </span>
                {locale === "zh" ? "讨论" : "Discussion"}
              </h2>
              <CommentSection episodeId={episode.id} />
            </section>
          </div>
        </div>

        {/* Gallery & Poster */}
        {(allPosters.length > 0 || galleryUrls.length > 0) && (
          <section className="mt-12">
            <h2 className="text-xl font-bold mb-6 flex items-center gap-3">
              <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-neon-purple/20 to-neon-purple/5 border border-neon-purple/20 flex items-center justify-center">
                <svg viewBox="0 0 24 24" className="w-4 h-4 text-neon-purple" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0022.5 18.75V5.25A2.25 2.25 0 0020.25 3H3.75A2.25 2.25 0 001.5 5.25v13.5A2.25 2.25 0 003.75 21z" />
                </svg>
              </span>
              {locale === "zh" ? "图库" : "Gallery"}
            </h2>
            {/* Posters at natural aspect ratio */}
            {allPosters.length > 0 && (
              <div className="flex flex-wrap gap-4 mb-6">
                {allPosters.map((p, i) => (
                  <div key={i} className={`rounded-xl overflow-hidden border border-white/[0.06] bg-black/20 ${p.orientation === "vertical" ? "w-40" : "w-72"}`}>
                    <img src={p.url} alt={`${locale === "zh" ? "海报" : "Poster"} ${i + 1}`} className="w-full h-auto" loading="lazy" />
                  </div>
                ))}
              </div>
            )}
            {/* Gallery screenshots */}
            {galleryUrls.length > 0 && <GalleryGrid urls={galleryUrls} />}
          </section>
        )}
      </div>
    </main>
  );
}
