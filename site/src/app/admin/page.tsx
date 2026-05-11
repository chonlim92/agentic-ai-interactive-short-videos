"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  AreaChart, Area,
} from "recharts";
import { useLocale } from "@/lib/useLocale";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";

// Dashboard-specific bilingual labels
const DL = {
  en: {
    dashboard: "Dashboard",
    dashboard_sub: "Overview of stories, episodes & generation pipeline",
    stories: "Stories",
    episodes_total: "episodes total",
    total_votes: "Total Votes",
    across_episodes: "across {n} episodes",
    comments: "Comments",
    pending: "pending",
    gen_runs: "Gen Runs",
    completed_failed: "{c} completed, {f} failed",
    episode_status: "Episode Status",
    published: "Published",
    draft: "Draft",
    voting_open: "Voting Open",
    comment_moderation: "Comment Moderation",
    approved: "Approved",
    pending_label: "Pending",
    flagged: "Flagged",
    no_episodes: "No episodes yet",
    no_comments: "No comments yet",
    story_details: "Story Details",
    episodes: "Episodes",
    published_drafts: "{p} published, {d} drafts",
    votes: "Votes",
    polls_open: "{n} polls open",
    need_review: "need review",
    episode_engagement: "Episode Engagement",
    no_episodes_story: "No episodes for this story",
    vote_distribution: "Vote Distribution",
    no_vote_data: "No vote data available",
    cumulative_engagement: "Cumulative Engagement",
    need_2_episodes: "Need 2+ episodes for trend",
    voting_deadlines: "Voting Deadlines",
    no_active_deadlines: "No active voting deadlines",
    expired: "Expired",
    pipeline_durations: "Pipeline Step Durations",
    no_gen_runs: "No generation runs yet",
    story_comparison: "Story Comparison",
    no_story_data: "No story data available",
    all_episodes: "All Episodes",
    story_col: "Story",
    episode_col: "Episode",
    title_col: "Title",
    status_col: "Status",
    votes_col: "Votes",
    comments_col: "Comments",
    vote_deadline_col: "Vote Deadline",
    voting: "Voting",
    total_votes_legend: "Total Votes",
    total_comments_legend: "Total Comments",
    duration_s: "Duration (s)",
  },
  zh: {
    dashboard: "仪表盘",
    dashboard_sub: "故事、剧集和生成流水线概览",
    stories: "故事",
    episodes_total: "集（总计）",
    total_votes: "总投票数",
    across_episodes: "覆盖 {n} 集",
    comments: "评论",
    pending: "待审核",
    gen_runs: "生成运行",
    completed_failed: "{c} 已完成，{f} 失败",
    episode_status: "剧集状态",
    published: "已发布",
    draft: "草稿",
    voting_open: "投票中",
    comment_moderation: "评论审核",
    approved: "已通过",
    pending_label: "待审",
    flagged: "已标记",
    no_episodes: "暂无剧集",
    no_comments: "暂无评论",
    story_details: "故事详情",
    episodes: "剧集",
    published_drafts: "{p} 已发布，{d} 草稿",
    votes: "投票",
    polls_open: "{n} 个投票进行中",
    need_review: "需审核",
    episode_engagement: "剧集参与度",
    no_episodes_story: "该故事暂无剧集",
    vote_distribution: "投票分布",
    no_vote_data: "暂无投票数据",
    cumulative_engagement: "累计参与度",
    need_2_episodes: "需要2集以上才能显示趋势",
    voting_deadlines: "投票截止时间",
    no_active_deadlines: "暂无进行中的投票",
    expired: "已过期",
    pipeline_durations: "流水线步骤耗时",
    no_gen_runs: "暂无生成运行",
    story_comparison: "故事对比",
    no_story_data: "暂无故事数据",
    all_episodes: "所有剧集",
    story_col: "故事",
    episode_col: "集数",
    title_col: "标题",
    status_col: "状态",
    votes_col: "投票",
    comments_col: "评论",
    vote_deadline_col: "投票截止",
    voting: "投票中",
    total_votes_legend: "总投票数",
    total_comments_legend: "总评论数",
    duration_s: "耗时（秒）",
  },
} as const;

type DLKey = keyof typeof DL.en;

// --- Types ---

interface DashboardSummary {
  total_stories: number;
  total_episodes: number;
  published_episodes: number;
  draft_episodes: number;
  voting_open: number;
  total_votes: number;
  total_comments: number;
  moderated_comments: number;
  pending_moderation: number;
  flagged_comments: number;
  total_generation_runs: number;
  completed_runs: number;
  failed_runs: number;
}

interface StoryStats {
  id: number;
  slug: string;
  title: string;
  title_zh: string;
  total_episodes: number;
  published: number;
  drafts: number;
  voting_open: number;
  total_votes: number;
  total_comments: number;
  moderated_comments: number;
  flagged_comments: number;
}

interface EpisodeStats {
  id: number;
  story_id: number;
  story_title: string;
  story_title_zh: string;
  episode_number: number;
  title: string;
  title_zh: string;
  status: string;
  voting_open: boolean;
  voting_deadline: string | null;
  published_at: string;
  total_votes: number;
  total_comments: number;
  vote_distribution: { label: string; label_zh: string; count: number }[];
}

interface GenerationRunStats {
  id: number;
  episode_id: number;
  story_title: string;
  episode_number: number;
  mode: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  total_duration_ms: number;
  steps: { step_id: string; label: string; status: string; duration_ms: number | null }[];
}

interface DashboardData {
  summary: DashboardSummary;
  stories: StoryStats[];
  episodes: EpisodeStats[];
  generation_runs: GenerationRunStats[];
}

// --- Theme colors ---
const COLORS = {
  purple: "#a855f7",
  cyan: "#22d3ee",
  pink: "#ec4899",
  amber: "#f59e0b",
  green: "#22c55e",
  red: "#ef4444",
  blue: "#3b82f6",
};
const PIE_COLORS = [COLORS.purple, COLORS.cyan, COLORS.pink, COLORS.amber, COLORS.green, COLORS.blue];

const tooltipStyle = {
  contentStyle: {
    background: "rgba(15, 10, 30, 0.95)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: "12px",
    color: "#fff",
    fontSize: "13px",
  },
  itemStyle: { color: "#fff" },
  labelStyle: { color: "rgba(255,255,255,0.6)" },
};

// Locale-aware text helpers
function lz(locale: string, en: string, zh?: string): string {
  return locale === "zh" && zh ? zh : en;
}

const STEP_LABEL_KEYS: Record<string, TranslationKey> = {
  generate_script: "admin_gen_step_script",
  plan_scenes: "admin_gen_step_scenes",
  design_characters: "admin_gen_step_characters",
  design_locations: "admin_gen_step_locations",
  generate_keyframes: "admin_gen_step_keyframes",
  generate_clips: "admin_gen_step_clips",
  validate_quality: "admin_gen_step_quality",
  add_audio: "admin_gen_step_audio",
  compose_episode: "admin_gen_step_compose",
  publish: "admin_gen_step_publish",
};

function localizedStepLabel(locale: Locale, stepId: string, fallback: string): string {
  const key = STEP_LABEL_KEYS[stepId];
  return key ? t(locale, key) : fallback;
}

export default function AdminDashboard() {
  const locale = useLocale();
  const dl = DL[locale];
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedStory, setSelectedStory] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/admin/dashboard")
      .then((r) => r.json())
      .then((d: DashboardData) => {
        setData(d);
        if (d.stories.length > 0) setSelectedStory(d.stories[0].id);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-2 border-neon-purple/30 border-t-neon-purple rounded-full animate-spin" />
      </div>
    );
  }

  if (!data) {
    return <p className="text-white/40 text-center py-12">Failed to load dashboard data.</p>;
  }

  const { summary, stories, episodes, generation_runs } = data;
  const storyEpisodes = episodes.filter((e) => e.story_id === selectedStory);
  const storyRuns = generation_runs.filter((r) =>
    storyEpisodes.some((e) => e.id === r.episode_id)
  );

  // --- Derived chart data ---
  const episodeStatusData = [
    { name: dl.published, value: summary.published_episodes, color: COLORS.green },
    { name: dl.draft, value: summary.draft_episodes, color: COLORS.amber },
    { name: dl.voting_open, value: summary.voting_open, color: COLORS.cyan },
  ].filter((d) => d.value > 0);

  const commentBreakdown = [
    { name: dl.approved, value: summary.moderated_comments, color: COLORS.green },
    { name: dl.pending_label, value: summary.pending_moderation, color: COLORS.amber },
    { name: dl.flagged, value: summary.flagged_comments, color: COLORS.red },
  ].filter((d) => d.value > 0);

  const epLabel = (n: number) => locale === "zh" ? `第${n}集` : `Ep ${n}`;
  const episodeEngagement = storyEpisodes.map((ep) => ({
    name: epLabel(ep.episode_number),
    votes: ep.total_votes,
    comments: ep.total_comments,
  }));

  // Vote distribution for the selected story's episodes
  const voteCharts = storyEpisodes.filter((ep) => ep.vote_distribution.length > 0);

  // Step duration data from generation runs
  const latestRun = storyRuns[0];
  const stepDurations = latestRun
    ? latestRun.steps
        .filter((s) => s.duration_ms != null && s.duration_ms > 0)
        .map((s) => {
          const lbl = localizedStepLabel(locale as Locale, s.step_id, s.label);
          return {
            step: lbl.length > 18 ? lbl.substring(0, 16) + "…" : lbl,
            fullLabel: lbl,
            duration: Math.round((s.duration_ms ?? 0) / 1000),
            status: s.status,
          };
        })
    : [];

  // Story radar (multi-story comparison)
  const storyRadar = stories.map((s) => {
    const name = lz(locale, s.title, s.title_zh);
    return {
      story: name.length > 20 ? name.substring(0, 18) + "…" : name,
      episodes: s.total_episodes,
      votes: s.total_votes,
      comments: s.total_comments,
    };
  });

  // Episode timeline (cumulative votes over episodes)
  const episodeTimeline = storyEpisodes
    .sort((a, b) => a.episode_number - b.episode_number)
    .reduce<{ name: string; votes: number; comments: number; cumVotes: number; cumComments: number }[]>((acc, ep) => {
      const prev = acc[acc.length - 1];
      acc.push({
        name: epLabel(ep.episode_number),
        votes: ep.total_votes,
        comments: ep.total_comments,
        cumVotes: (prev?.cumVotes ?? 0) + ep.total_votes,
        cumComments: (prev?.cumComments ?? 0) + ep.total_comments,
      });
      return acc;
    }, []);

  // Active voting deadlines
  const activeDeadlines = storyEpisodes
    .filter((ep) => ep.voting_open && ep.voting_deadline)
    .map((ep) => ({
      episode_number: ep.episode_number,
      title: lz(locale, ep.title, ep.title_zh),
      deadline: ep.voting_deadline!,
      remaining: new Date(ep.voting_deadline!).getTime() - Date.now(),
    }))
    .sort((a, b) => a.remaining - b.remaining);

  return (
    <div className="max-w-6xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">{dl.dashboard}</h1>
        <p className="text-sm text-white/40 mt-1">
          {dl.dashboard_sub}
        </p>
      </div>

      {/* Summary stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          { label: dl.stories, value: summary.total_stories, sublabel: `${summary.total_episodes} ${dl.episodes_total}`, color: "purple" as const },
          { label: dl.total_votes, value: summary.total_votes, sublabel: dl.across_episodes.replace("{n}", String(summary.total_episodes)), color: "cyan" as const },
          { label: dl.comments, value: summary.total_comments, sublabel: `${summary.pending_moderation} ${dl.pending}`, color: "pink" as const },
          { label: dl.gen_runs, value: summary.total_generation_runs, sublabel: dl.completed_failed.replace("{c}", String(summary.completed_runs)).replace("{f}", String(summary.failed_runs)), color: "amber" as const },
        ].map((card, i) => (
          <motion.div
            key={card.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08, duration: 0.4, ease: "easeOut" }}
          >
            <StatCard {...card} />
          </motion.div>
        ))}
      </div>

      {/* Overview charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Episode status pie */}
        <ChartCard title={dl.episode_status} icon="pie">
          {episodeStatusData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={episodeStatusData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={4}
                  dataKey="value"
                  stroke="none"
                >
                  {episodeStatusData.map((d, i) => (
                    <Cell key={i} fill={d.color} />
                  ))}
                </Pie>
                <Tooltip {...tooltipStyle} />
                <Legend
                  formatter={(value) => <span className="text-white/60 text-xs">{value}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart message={dl.no_episodes} />
          )}
        </ChartCard>

        {/* Comment breakdown pie */}
        <ChartCard title={dl.comment_moderation} icon="chat">
          {commentBreakdown.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={commentBreakdown}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={85}
                  paddingAngle={4}
                  dataKey="value"
                  stroke="none"
                >
                  {commentBreakdown.map((d, i) => (
                    <Cell key={i} fill={d.color} />
                  ))}
                </Pie>
                <Tooltip {...tooltipStyle} />
                <Legend
                  formatter={(value) => <span className="text-white/60 text-xs">{value}</span>}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart message={dl.no_comments} />
          )}
        </ChartCard>
      </div>

      {/* Story selector + per-story section */}
      {stories.length > 0 && (
        <>
          <div className="flex items-center gap-3 mb-6">
            <h2 className="text-lg font-semibold">{dl.story_details}</h2>
            {stories.length > 1 && (
              <select
                value={selectedStory ?? ""}
                onChange={(e) => setSelectedStory(Number(e.target.value))}
                className="bg-white/[0.05] border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white/80 focus:outline-none focus:border-neon-purple/40"
              >
                {stories.map((s) => (
                  <option key={s.id} value={s.id} className="bg-[#0f0a1e]">
                    {lz(locale, s.title, s.title_zh)}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Story stat cards */}
          {(() => {
            const s = stories.find((st) => st.id === selectedStory);
            if (!s) return null;
            return (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                <StatCard label={dl.episodes} value={s.total_episodes} sublabel={dl.published_drafts.replace("{p}", String(s.published)).replace("{d}", String(s.drafts))} color="purple" />
                <StatCard label={dl.votes} value={s.total_votes} sublabel={dl.polls_open.replace("{n}", String(s.voting_open))} color="cyan" />
                <StatCard label={dl.comments} value={s.total_comments} sublabel={`${s.moderated_comments} ${dl.approved.toLowerCase()}`} color="pink" />
                <StatCard label={dl.flagged} value={s.flagged_comments} sublabel={dl.need_review} color="amber" />
              </div>
            );
          })()}

          {/* Engagement bar chart */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            <ChartCard title={dl.episode_engagement} icon="bar">
              {episodeEngagement.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={episodeEngagement} barGap={4}>
                    <XAxis dataKey="name" tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                    <Tooltip {...tooltipStyle} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                    <Bar dataKey="votes" fill={COLORS.cyan} radius={[6, 6, 0, 0]} name={dl.votes} />
                    <Bar dataKey="comments" fill={COLORS.pink} radius={[6, 6, 0, 0]} name={dl.comments} />
                    <Legend formatter={(value) => <span className="text-white/60 text-xs">{value}</span>} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart message={dl.no_episodes_story} />
              )}
            </ChartCard>

            {/* Vote distribution for latest episode with votes */}
            <ChartCard title={dl.vote_distribution} icon="vote">
              {voteCharts.length > 0 ? (
                <div className="space-y-4">
                  {voteCharts.slice(0, 3).map((ep) => (
                    <div key={ep.id}>
                      <p className="text-xs text-white/40 mb-2">{epLabel(ep.episode_number)}: {lz(locale, ep.title, ep.title_zh)}</p>
                      <ResponsiveContainer width="100%" height={voteCharts.length === 1 ? 200 : 100}>
                        <BarChart data={ep.vote_distribution.map((v) => ({ ...v, displayLabel: lz(locale, v.label, v.label_zh) }))} layout="vertical" barSize={16}>
                          <XAxis type="number" tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                          <YAxis type="category" dataKey="displayLabel" tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 11 }} axisLine={false} tickLine={false} width={100} />
                          <Tooltip {...tooltipStyle} />
                          <Bar dataKey="count" radius={[0, 6, 6, 0]} name={dl.votes}>
                            {ep.vote_distribution.map((_, i) => (
                              <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyChart message={dl.no_vote_data} />
              )}
            </ChartCard>
          </div>

          {/* Generation pipeline chart */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {/* Cumulative engagement area chart */}
            <ChartCard title={dl.cumulative_engagement} icon="bar">
              {episodeTimeline.length > 1 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={episodeTimeline}>
                    <defs>
                      <linearGradient id="gradVotes" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.cyan} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={COLORS.cyan} stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="gradComments" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={COLORS.pink} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={COLORS.pink} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="name" tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                    <Tooltip {...tooltipStyle} cursor={{ stroke: "rgba(255,255,255,0.08)" }} />
                    <Area type="monotone" dataKey="cumVotes" stroke={COLORS.cyan} fill="url(#gradVotes)" strokeWidth={2} name={dl.total_votes_legend} />
                    <Area type="monotone" dataKey="cumComments" stroke={COLORS.pink} fill="url(#gradComments)" strokeWidth={2} name={dl.total_comments_legend} />
                    <Legend formatter={(value) => <span className="text-white/60 text-xs">{value}</span>} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart message={dl.need_2_episodes} />
              )}
            </ChartCard>

            {/* Active voting deadlines */}
            <ChartCard title={dl.voting_deadlines} icon="vote">
              {activeDeadlines.length > 0 ? (
                <div className="space-y-3">
                  {activeDeadlines.map((d) => {
                    const days = Math.floor(d.remaining / 86400000);
                    const hours = Math.floor((d.remaining % 86400000) / 3600000);
                    const expired = d.remaining <= 0;
                    const urgent = d.remaining > 0 && d.remaining < 86400000;
                    return (
                      <motion.div
                        key={d.episode_number}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        className={`p-4 rounded-xl border ${
                          expired
                            ? "bg-red-500/5 border-red-500/20"
                            : urgent
                            ? "bg-amber-500/5 border-amber-500/20"
                            : "bg-white/[0.02] border-white/[0.06]"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-sm font-medium">{epLabel(d.episode_number)}: {d.title}</p>
                            <p className="text-xs text-white/30 mt-0.5">
                              {new Date(d.deadline).toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric", year: "numeric" })}
                              {" "}
                              {new Date(d.deadline).toLocaleTimeString(locale === "zh" ? "zh-CN" : "en-US", { hour: "2-digit", minute: "2-digit" })}
                            </p>
                          </div>
                          <div className="text-right">
                            {expired ? (
                              <span className="text-xs px-2 py-1 rounded-full bg-red-500/10 text-red-400 border border-red-500/20">{dl.expired}</span>
                            ) : (
                              <span className={`text-sm font-mono font-bold ${urgent ? "text-amber-400" : "text-neon-cyan"}`}>
                                {days > 0 ? `${days}d ` : ""}{hours}h
                              </span>
                            )}
                          </div>
                        </div>
                        {!expired && (
                          <div className="mt-2 h-1.5 bg-white/5 rounded-full overflow-hidden">
                            <motion.div
                              className={`h-full rounded-full ${urgent ? "bg-amber-400" : "bg-neon-cyan"}`}
                              initial={{ width: 0 }}
                              animate={{ width: `${Math.max(5, Math.min(100, (d.remaining / (365 * 24 * 3600000)) * 100))}%` }}
                              transition={{ duration: 1, ease: "easeOut" }}
                            />
                          </div>
                        )}
                      </motion.div>
                    );
                  })}
                </div>
              ) : (
                <EmptyChart message={dl.no_active_deadlines} />
              )}
            </ChartCard>
          </div>

          {/* Pipeline + radar row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            <ChartCard title={dl.pipeline_durations} icon="pipeline" subtitle={latestRun ? `Run #${latestRun.id} — ${epLabel(latestRun.episode_number)}` : undefined}>
              {stepDurations.length > 0 ? (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={stepDurations} layout="vertical" barSize={14}>
                    <XAxis type="number" tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }} axisLine={false} tickLine={false} unit="s" />
                    <YAxis type="category" dataKey="step" tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 10 }} axisLine={false} tickLine={false} width={130} />
                    <Tooltip
                      {...tooltipStyle}
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      formatter={(value: any, _name: any, props: any) => [
                        `${value}s`,
                        props?.payload?.fullLabel ?? _name,
                      ]}
                    />
                    <Bar dataKey="duration" radius={[0, 6, 6, 0]} name={dl.duration_s}>
                      {stepDurations.map((s, i) => (
                        <Cell
                          key={i}
                          fill={s.status === "done" ? COLORS.green : s.status === "failed" ? COLORS.red : COLORS.amber}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart message={dl.no_gen_runs} />
              )}
            </ChartCard>

            {/* Multi-story radar (useful when > 1 story) */}
            <ChartCard title={dl.story_comparison} icon="radar">
              {storyRadar.length > 0 ? (
                <ResponsiveContainer width="100%" height={280}>
                  <RadarChart data={storyRadar}>
                    <PolarGrid stroke="rgba(255,255,255,0.08)" />
                    <PolarAngleAxis dataKey="story" tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 11 }} />
                    <PolarRadiusAxis tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 10 }} axisLine={false} />
                    <Radar name={dl.episodes} dataKey="episodes" stroke={COLORS.purple} fill={COLORS.purple} fillOpacity={0.25} />
                    <Radar name={dl.votes} dataKey="votes" stroke={COLORS.cyan} fill={COLORS.cyan} fillOpacity={0.2} />
                    <Radar name={dl.comments} dataKey="comments" stroke={COLORS.pink} fill={COLORS.pink} fillOpacity={0.15} />
                    <Legend formatter={(value) => <span className="text-white/60 text-xs">{value}</span>} />
                    <Tooltip {...tooltipStyle} />
                  </RadarChart>
                </ResponsiveContainer>
              ) : (
                <EmptyChart message={dl.no_story_data} />
              )}
            </ChartCard>
          </div>
        </>
      )}

      {/* Episodes table */}
      <ChartCard title={dl.all_episodes} icon="list" className="mb-8">
        {episodes.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  <th className="text-left py-3 px-2 text-white/40 font-medium text-xs">{dl.story_col}</th>
                  <th className="text-left py-3 px-2 text-white/40 font-medium text-xs">{dl.episode_col}</th>
                  <th className="text-left py-3 px-2 text-white/40 font-medium text-xs">{dl.title_col}</th>
                  <th className="text-center py-3 px-2 text-white/40 font-medium text-xs">{dl.status_col}</th>
                  <th className="text-center py-3 px-2 text-white/40 font-medium text-xs">{dl.votes_col}</th>
                  <th className="text-center py-3 px-2 text-white/40 font-medium text-xs">{dl.comments_col}</th>
                  <th className="text-center py-3 px-2 text-white/40 font-medium text-xs">{dl.vote_deadline_col}</th>
                </tr>
              </thead>
              <tbody>
                {episodes.map((ep) => (
                  <tr key={ep.id} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                    <td className="py-2.5 px-2 text-white/50 text-xs">{lz(locale, ep.story_title, ep.story_title_zh)}</td>
                    <td className="py-2.5 px-2 text-white/70 font-mono">#{ep.episode_number}</td>
                    <td className="py-2.5 px-2 text-white/80">{lz(locale, ep.title, ep.title_zh)}</td>
                    <td className="py-2.5 px-2 text-center">
                      <StatusBadge status={ep.status} votingOpen={ep.voting_open} locale={locale} />
                    </td>
                    <td className="py-2.5 px-2 text-center text-white/60">{ep.total_votes}</td>
                    <td className="py-2.5 px-2 text-center text-white/60">{ep.total_comments}</td>
                    <td className="py-2.5 px-2 text-center text-xs">
                      {ep.voting_deadline ? (
                        <span className={
                          new Date(ep.voting_deadline).getTime() < Date.now()
                            ? "text-white/30"
                            : new Date(ep.voting_deadline).getTime() - Date.now() < 86400000
                            ? "text-amber-400"
                            : "text-neon-cyan"
                        }>
                          {new Date(ep.voting_deadline).toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric" })}
                        </span>
                      ) : (
                        <span className="text-white/15">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyChart message={dl.no_episodes} />
        )}
      </ChartCard>
    </div>
  );
}

// --- Subcomponents ---

function StatCard({
  label,
  value,
  sublabel,
  color,
}: {
  label: string;
  value: number;
  sublabel: string;
  color: "purple" | "cyan" | "pink" | "amber";
}) {
  const colors = {
    purple: "from-neon-purple/20 to-neon-purple/5 border-neon-purple/20",
    cyan: "from-neon-cyan/20 to-neon-cyan/5 border-neon-cyan/20",
    pink: "from-neon-pink/20 to-neon-pink/5 border-neon-pink/20",
    amber: "from-accent/20 to-accent/5 border-accent/20",
  };

  return (
    <div className={`rounded-2xl p-5 bg-gradient-to-br border ${colors[color]}`}>
      <p className="text-xs text-white/40 mb-1">{label}</p>
      <p className="text-3xl font-bold">{value}</p>
      <p className="text-xs text-white/30 mt-1">{sublabel}</p>
    </div>
  );
}

function ChartCard({
  title,
  icon,
  subtitle,
  className,
  children,
}: {
  title: string;
  icon: string;
  subtitle?: string;
  className?: string;
  children: React.ReactNode;
}) {
  const icons: Record<string, React.ReactNode> = {
    pie: (
      <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6a7.5 7.5 0 107.5 7.5h-7.5V6z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 10.5H21A7.5 7.5 0 0013.5 3v7.5z" />
      </svg>
    ),
    bar: (
      <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
      </svg>
    ),
    chat: (
      <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
      </svg>
    ),
    vote: (
      <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.633 10.5c.806 0 1.533-.446 2.031-1.08a9.041 9.041 0 012.861-2.4c.723-.384 1.35-.956 1.653-1.715a4.498 4.498 0 00.322-1.672V3a.75.75 0 01.75-.75A2.25 2.25 0 0116.5 4.5c0 1.152-.26 2.243-.723 3.218-.266.558.107 1.282.725 1.282h3.126c1.026 0 1.945.694 2.054 1.715.045.422.068.85.068 1.285a11.95 11.95 0 01-2.649 7.521c-.388.482-.987.729-1.605.729H13.48c-.483 0-.964-.078-1.423-.23l-3.114-1.04a4.501 4.501 0 00-1.423-.23H5.904M14.25 9h2.25M5.904 18.75c.083.205.173.405.27.602.197.4-.078.898-.523.898h-.908c-.889 0-1.713-.518-1.972-1.368a12 12 0 01-.521-3.507c0-1.553.295-3.036.831-4.398C3.387 10.203 4.167 9.75 5 9.75h1.053c.472 0 .745.556.5.96a8.958 8.958 0 00-1.302 4.665c0 1.194.232 2.333.654 3.375z" />
      </svg>
    ),
    pipeline: (
      <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
      </svg>
    ),
    radar: (
      <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 006 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0118 16.5h-2.25m-7.5 0h7.5m-7.5 0l-1 3m8.5-3l1 3m0 0l.5 1.5m-.5-1.5h-9.5m0 0l-.5 1.5m.75-9l3-3 2.148 2.148A12.061 12.061 0 0116.5 7.605" />
      </svg>
    ),
    list: (
      <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 6.75h12M8.25 12h12m-12 5.25h12M3.75 6.75h.007v.008H3.75V6.75zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zM3.75 12h.007v.008H3.75V12zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm-.375 5.25h.007v.008H3.75v-.008zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
      </svg>
    ),
  };

  return (
    <motion.div
      className={`glass-card p-6 ${className ?? ""}`}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold flex items-center gap-2 text-white/70">
          <span className="text-neon-purple">{icons[icon]}</span>
          {title}
        </h3>
        {subtitle && <span className="text-xs text-white/30">{subtitle}</span>}
      </div>
      {children}
    </motion.div>
  );
}

function StatusBadge({ status, votingOpen, locale }: { status: string; votingOpen: boolean; locale: string }) {
  const statusLabels: Record<string, Record<string, string>> = {
    en: { voting: "Voting", published: "published", draft: "draft" },
    zh: { voting: "投票中", published: "已发布", draft: "草稿" },
  };
  const labels = statusLabels[locale] ?? statusLabels.en;
  if (votingOpen) {
    return <span className="text-xs px-2 py-0.5 rounded-full bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/20">{labels.voting}</span>;
  }
  const styles: Record<string, string> = {
    published: "bg-green-500/10 text-green-400 border-green-500/20",
    draft: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${styles[status] ?? "bg-white/5 text-white/40 border-white/10"}`}>
      {labels[status] ?? status}
    </span>
  );
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center h-48">
      <p className="text-white/20 text-sm">{message}</p>
    </div>
  );
}
