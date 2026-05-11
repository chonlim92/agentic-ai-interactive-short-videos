import { notFound } from "next/navigation";
import { cookies } from "next/headers";
import Link from "next/link";
import { getStory, getEpisodesByStory, getActiveVotingEpisode, getVoteOptions, getStoryPosterUrl, getEpisodePosterUrl, getEpisodeGalleryUrls, getEpisodeNarrative } from "@/lib/db";
import type { Locale } from "@/lib/i18n";
import { t } from "@/lib/i18n";
import { StoryTabs } from "@/components/StoryTabs";
import { VoteForm } from "@/components/VoteForm";
import { CommentSection } from "@/components/CommentSection";
import { GalleryGrid } from "@/components/GalleryGrid";
import { AutoRefresh } from "@/components/AutoRefresh";

export const dynamic = "force-dynamic";

export default async function StoryPage({ params }: { params: { slug: string } }) {
  const locale = (cookies().get("locale")?.value || "en") as Locale;
  const story = await getStory(params.slug);
  if (!story) notFound();

  const episodes = await getEpisodesByStory(story.id);
  const publishedEpisodes = episodes.filter((e) => e.status === "published");
  const activeVoteEpisode = await getActiveVotingEpisode(story.id);
  const voteOptions = activeVoteEpisode ? await getVoteOptions(activeVoteEpisode.id) : [];

  const title = locale === "zh" && story.title_zh ? story.title_zh : story.title;
  const subtitle = locale === "zh" ? story.title : story.title_zh;
  const description = locale === "zh" && story.description_zh ? story.description_zh : story.description;
  const posterUrl = getStoryPosterUrl(story, "16_9", locale);

  // Gather gallery images per episode
  const episodeGalleries = publishedEpisodes.map((ep) => {
    const poster = getEpisodePosterUrl(story, ep.episode_number, locale);
    const gallery = getEpisodeGalleryUrls(story, ep.episode_number);
    const urls = poster ? [poster, ...gallery] : gallery;
    return {
      episodeNumber: ep.episode_number,
      title: locale === "zh" && ep.title_zh ? ep.title_zh : ep.title,
      urls,
    };
  }).filter((g) => g.urls.length > 0);

  return (
    <main className="min-h-[calc(100vh-4rem)]">
      <AutoRefresh storySlug={params.slug} />
      {/* Story hero */}
      <section className="relative px-6 pt-12 pb-8 overflow-hidden">
        {posterUrl && (
          <div className="absolute inset-0 overflow-hidden">
            <img src={posterUrl} alt="" className="w-full h-full object-cover opacity-20 blur-sm" />
            <div className="absolute inset-0 bg-gradient-to-b from-[#0a0520]/60 via-[#0a0520]/80 to-[#0a0520]" />
          </div>
        )}
        <div className="absolute inset-0 bg-gradient-to-b from-neon-purple/5 to-transparent pointer-events-none" />
        <div className="max-w-4xl mx-auto relative">
          <Link
            href="/"
            prefetch={false}
            className="inline-flex items-center gap-1.5 text-xs text-white/30 hover:text-white/50 transition-colors mb-6"
          >
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
            {locale === "zh" ? "所有故事" : "All Stories"}
          </Link>

          <div className="flex flex-col md:flex-row gap-6 items-start">
            {/* Poster image */}
            {posterUrl && (
              <div className="shrink-0 w-48 md:w-56 aspect-video rounded-xl overflow-hidden border border-white/10 shadow-lg shadow-neon-purple/10 bg-black/30">
                <img src={posterUrl} alt={title} className="w-full h-full object-contain" />
              </div>
            )}

            <div className="flex-1 min-w-0">
              <h1 className="text-3xl md:text-4xl font-black tracking-tight mb-2">
                {title}
              </h1>
              {subtitle && (
                <p className="text-lg text-white/40 mb-4">{subtitle}</p>
              )}
              {description && (
                <p className="text-white/50 max-w-2xl leading-relaxed">{description}</p>
              )}

              {/* Stats bar */}
              <div className="flex items-center gap-6 mt-6 text-sm text-white/30">
                <span className="flex items-center gap-1.5">
                  <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125M3.375 19.5c-.621 0-1.125-.504-1.125-1.125M20.625 4.5H3.375m17.25 0c.621 0 1.125.504 1.125 1.125M20.625 4.5h-7.5c-.621 0-1.125.504-1.125 1.125" />
                  </svg>
                  {publishedEpisodes.length} {locale === "zh" ? "集" : publishedEpisodes.length === 1 ? "Episode" : "Episodes"}
                </span>
                {activeVoteEpisode && (
                  <span className="flex items-center gap-1.5 text-neon-cyan">
                    <span className="w-1.5 h-1.5 rounded-full bg-neon-cyan animate-pulse" />
                    {locale === "zh" ? "投票进行中" : "Voting active"}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Tabbed content */}
      <section className="max-w-4xl mx-auto px-6 pb-16">
        <StoryTabs
          locale={locale}
          hasActiveVote={!!activeVoteEpisode}
          episodesContent={
            publishedEpisodes.length === 0 ? (
              <div className="glass-card p-12 text-center">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-neon-purple/20 to-neon-cyan/10 border border-white/10 flex items-center justify-center mx-auto mb-4">
                  <svg viewBox="0 0 24 24" className="w-7 h-7 text-white/20" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold mb-2 text-white/60">
                  {locale === "zh" ? "暂无剧集" : "No episodes yet"}
                </h3>
                <p className="text-sm text-white/30">
                  {locale === "zh" ? "第一集正在由AI智能体创作中，敬请期待！" : "The first episode is being crafted by our AI agents. Stay tuned!"}
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {publishedEpisodes.map((ep) => {
                  const epPosterUrl = getEpisodePosterUrl(story, ep.episode_number, locale);
                  const epNarrative = getEpisodeNarrative(story, ep.episode_number, locale);
                  return (
                  <Link
                    key={ep.id}
                    href={`/stories/${story.slug}/episodes/${ep.episode_number}`}
                    prefetch={false}
                    className="glass-card p-4 flex items-start gap-4 hover:border-neon-purple/20 transition-all group block"
                  >
                    {/* Episode thumbnail — uncropped poster */}
                    {epPosterUrl ? (
                      <div className="shrink-0 w-28 rounded-lg overflow-hidden border border-white/10 bg-black/30">
                        <img src={epPosterUrl} alt="" className="w-full h-auto object-contain" />
                      </div>
                    ) : (
                      <div className="shrink-0 w-14 h-14 rounded-xl bg-gradient-to-br from-neon-purple/20 to-neon-cyan/10 border border-white/10 flex items-center justify-center">
                        <span className="text-base font-bold text-white/60">{String(ep.episode_number).padStart(2, "0")}</span>
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold group-hover:text-white transition-colors leading-snug">
                        {locale === "zh" && ep.title_zh ? ep.title_zh : ep.title}
                      </h3>
                      {epNarrative && (
                        <p className="text-xs text-white/40 mt-1 line-clamp-2 leading-relaxed">{epNarrative}</p>
                      )}
                      <p className="text-xs text-white/25 mt-1.5">
                        {new Date(ep.published_at).toLocaleDateString(
                          locale === "zh" ? "zh-CN" : "en-US",
                          { year: "numeric", month: "long", day: "numeric" }
                        )}
                      </p>
                    </div>
                    <div className="shrink-0 flex items-center gap-2 pt-1">
                      {ep.voting_open && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/20">
                          {locale === "zh" ? "投票中" : "Voting"}
                        </span>
                      )}
                      <svg viewBox="0 0 24 24" className="w-4 h-4 text-white/20 group-hover:text-neon-purple/60 transition-colors" fill="none" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                      </svg>
                    </div>
                  </Link>
                  );
                })}
              </div>
            )
          }
          voteContent={
            !activeVoteEpisode ? (
              <div className="glass-card p-12 text-center">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-neon-cyan/20 to-neon-cyan/5 border border-neon-cyan/20 flex items-center justify-center mx-auto mb-4">
                  <svg viewBox="0 0 24 24" className="w-7 h-7 text-neon-cyan/30" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold mb-2 text-white/60">
                  {t(locale, "vote_no_active")}
                </h3>
                <p className="text-sm text-white/30">
                  {t(locale, "vote_no_active_sub")}
                </p>
              </div>
            ) : (
              <div className="glass-card p-8">
                <div className="flex items-center gap-2 mb-6">
                  <span className="w-2 h-2 rounded-full bg-neon-cyan animate-pulse" />
                  <span className="text-sm text-neon-cyan">{t(locale, "vote_open_badge")}</span>
                  <span className="text-sm text-white/30 ml-2">
                    — {locale === "zh" && activeVoteEpisode.title_zh ? activeVoteEpisode.title_zh : activeVoteEpisode.title}
                  </span>
                </div>
                <h3 className="text-lg font-semibold mb-5">
                  {t(locale, "vote_question")}
                </h3>
                <VoteForm episodeId={activeVoteEpisode.id} options={voteOptions} />
              </div>
            )
          }
          galleryContent={
            episodeGalleries.length > 0 ? (
              <div className="space-y-8">
                {episodeGalleries.map((g) => (
                  <div key={g.episodeNumber}>
                    <h3 className="text-sm font-semibold text-white/60 mb-3">
                      {locale === "zh" ? `第 ${g.episodeNumber} 集` : `Episode ${g.episodeNumber}`}
                      <span className="text-white/30 font-normal ml-2">— {g.title}</span>
                    </h3>
                    <GalleryGrid urls={g.urls} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="glass-card p-12 text-center">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-neon-pink/20 to-neon-pink/5 border border-neon-pink/20 flex items-center justify-center mx-auto mb-4">
                  <svg viewBox="0 0 24 24" className="w-7 h-7 text-neon-pink/30" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0022.5 18.75V5.25A2.25 2.25 0 0020.25 3H3.75A2.25 2.25 0 001.5 5.25v13.5A2.25 2.25 0 003.75 21z" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold mb-2 text-white/60">
                  {t(locale, "gallery_title")}
                </h3>
                <p className="text-sm text-white/30">
                  {t(locale, "gallery_coming")}
                </p>
              </div>
            )
          }
          discussionContent={
            publishedEpisodes.length > 0 ? (
              <CommentSection episodeId={publishedEpisodes[0].id} />
            ) : (
              <div className="glass-card p-12 text-center">
                <p className="text-sm text-white/30">
                  {locale === "zh" ? "发布第一集后讨论区将开放。" : "Discussion opens after the first episode is published."}
                </p>
              </div>
            )
          }
        />
      </section>
    </main>
  );
}
