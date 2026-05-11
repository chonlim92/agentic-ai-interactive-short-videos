// Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
// Licensed under CC BY-NC 4.0. See LICENSE for details.
import Link from "next/link";
import { cookies } from "next/headers";
import { getAllStories, getStoryPosterUrl } from "@/lib/db";
import type { Locale } from "@/lib/i18n";
import { t } from "@/lib/i18n";

export const dynamic = "force-dynamic";

export default async function Home() {
  const locale = (cookies().get("locale")?.value || "en") as Locale;
  const stories = (await getAllStories()).filter((s) => s.status === "active");

  return (
    <main className="min-h-[calc(100vh-4rem)] flex flex-col">
      {/* Hero — compact */}
      <section className="flex flex-col items-center px-6 pt-20 pb-12 text-center relative overflow-hidden">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-gradient-radial from-neon-purple/20 via-transparent to-transparent blur-3xl pointer-events-none" />

        <div className="animate-fade-in-up relative">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-white/10 bg-white/[0.03] text-xs text-white/60 mb-6 backdrop-blur-sm">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            {t(locale, "hero_badge")}
          </div>

          <h1 className="text-4xl md:text-6xl font-black tracking-tight leading-[1.1] mb-4">
            {locale === "zh" ? (
              <>由你塑造的<span className="glow-text">故事</span></>
            ) : (
              <>Stories Shaped <span className="glow-text">By You</span></>
            )}
          </h1>

          <p className="text-base md:text-lg text-white/50 max-w-md mx-auto leading-relaxed">
            {t(locale, "tagline_sub")}
          </p>
        </div>
      </section>

      {/* Stories — primary content */}
      <section className="max-w-5xl mx-auto px-6 pb-16 w-full">
        {stories.length === 0 ? (
          <div className="glass-card p-16 text-center max-w-lg mx-auto">
            <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-gradient-to-br from-neon-purple/10 to-neon-cyan/10 flex items-center justify-center border border-white/5">
              <svg viewBox="0 0 24 24" className="w-10 h-10 text-white/20" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
              </svg>
            </div>
            <p className="text-white/40 text-lg">{t(locale, "stories_empty")}</p>
          </div>
        ) : (
          <div className={`grid gap-6 ${stories.length === 1 ? 'max-w-xl mx-auto' : 'md:grid-cols-2'}`}>
            {stories.map((story, i) => {
              const storyPoster = getStoryPosterUrl(story, "4_3", locale);
              return (
              <Link
                key={story.id}
                href={`/stories/${story.slug}`}
                prefetch={false}
                className="glass-card overflow-hidden hover:border-neon-purple/30 hover:shadow-lg hover:shadow-neon-purple/5 transition-all group block animate-fade-in-up"
                style={{ animationDelay: `${i * 100}ms`, animationFillMode: "both" }}
              >
                {storyPoster && (
                  <div className="aspect-[4/3] w-full overflow-hidden border-b border-white/[0.05] bg-black/30">
                    <img
                      src={storyPoster}
                      alt=""
                      className="w-full h-full object-contain group-hover:scale-105 transition-transform duration-500"
                    />
                  </div>
                )}
                <div className="p-8">
                <div className="flex items-start gap-4 mb-4">
                  <div className="w-12 h-12 shrink-0 rounded-xl bg-gradient-to-br from-neon-purple/20 to-neon-cyan/20 flex items-center justify-center border border-white/10 group-hover:border-neon-purple/30 transition-colors">
                    <svg viewBox="0 0 24 24" className="w-6 h-6 text-neon-purple/80" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                    </svg>
                  </div>
                  <div className="flex-1 min-w-0">
                    <h2 className="text-xl font-bold group-hover:text-neon-purple transition-colors">
                      {locale === "zh" && story.title_zh ? story.title_zh : story.title}
                    </h2>
                    <p className="text-sm text-white/30 mt-0.5">
                      {locale === "zh" ? story.title : story.title_zh}
                    </p>
                  </div>
                  <svg viewBox="0 0 24 24" className="w-5 h-5 text-white/20 group-hover:text-neon-purple/60 group-hover:translate-x-0.5 transition-all shrink-0 mt-1" fill="none" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                  </svg>
                </div>
                <p className="text-sm text-white/50 line-clamp-3 leading-relaxed">
                  {locale === "zh" && story.description_zh ? story.description_zh : story.description}
                </p>
                </div>
              </Link>
              );
            })}
          </div>
        )}
      </section>

      {/* How it works — compact */}
      <section className="max-w-4xl mx-auto px-6 pb-20 w-full">
        <h2 className="text-xl font-bold text-center mb-10 text-white/60">
          {locale === "zh" ? "如何运作" : "How It Works"}
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
          {[
            { step: "01", title: t(locale, "step_watch"), desc: t(locale, "step_watch_desc") },
            { step: "02", title: t(locale, "step_vote"), desc: t(locale, "step_vote_desc") },
            { step: "03", title: t(locale, "step_shape"), desc: t(locale, "step_shape_desc") },
            { step: "04", title: t(locale, "step_repeat"), desc: t(locale, "step_repeat_desc") },
          ].map((item) => (
            <div key={item.step} className="relative">
              <div className="text-3xl font-black text-white/[0.04] mb-1">{item.step}</div>
              <h3 className="text-sm font-semibold mb-0.5">{item.title}</h3>
              <p className="text-xs text-white/40">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
