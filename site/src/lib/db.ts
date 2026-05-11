/**
 * StorySmith AI / 剧匠AI — JSON file-based store.
 * Supports multiple stories, each with episodes, voting, comments, and admin prompts.
 */
import fs from "fs";
import path from "path";

const DATA_PATH = path.join(process.cwd(), "data", "store.json");

// --- Store schema ---

interface Store {
  stories: StoryRecord[];
  episodes: EpisodeRecord[];
  vote_options: VoteOptionRecord[];
  votes: VoteRecord[];
  comments: CommentRecord[];
  generation_runs: GenerationRunRecord[];
  step_selections: StepSelectionRecord[];
  skipped_steps: SkippedStepRecord[];
  admin: { password_hash: string };
  next_id: {
    stories: number;
    episodes: number;
    vote_options: number;
    votes: number;
    comments: number;
    generation_runs: number;
  };
}

interface StoryRecord {
  id: number;
  slug: string;
  title: string;
  title_zh: string;
  description: string;
  description_zh: string;
  background: string;
  status: "active" | "completed" | "draft";
  poster_episode_id: number | null;
  selected_poster_en?: string | null;
  selected_poster_zh?: string | null;
  created_at: string;
}

interface EpisodeRecord {
  id: number;
  story_id: number;
  episode_number: number;
  title: string;
  title_zh: string;
  status: string;
  video_url: string | null;
  video_url_en: string | null;
  thumbnail_url: string | null;
  poster_url: string | null;
  gallery: string[];
  voting_open: boolean;
  voting_deadline: string | null;
  admin_prompt: string | null;
  admin_prompt_weight: number;
  published_at: string;
}

interface VoteOptionRecord {
  id: number;
  episode_id: number;
  label: string;
  label_zh: string;
  description: string | null;
  description_zh: string | null;
  sort_order: number;
}

interface VoteRecord {
  id: number;
  episode_id: number;
  option_id: number;
  voter_id: string;
  voted_at: string;
}

interface CommentRecord {
  id: number;
  episode_id: number;
  author: string;
  content: string;
  moderated: boolean;
  flagged: boolean;
  created_at: string;
}

interface GenerationStepRecord {
  step_id: string;
  label: string;
  status: "pending" | "running" | "done" | "failed";
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  output: string;
  exit_code: number | null;
  output_dir: string | null;
  pid?: number | null;
}

interface GenerationRunRecord {
  id: number;
  episode_id: number;
  story_id: number;
  mode: "full" | "single";
  status: "running" | "completed" | "failed";
  steps: GenerationStepRecord[];
  started_at: string;
  ended_at: string | null;
}

interface StepSelectionRecord {
  story_id: number;
  episode_id: number;
  step_id: string;
  run_id: number;
}

interface SkippedStepRecord {
  story_id: number;
  episode_id: number;
  step_id: string;
}

import crypto from "crypto";

// Default admin password from env, fallback to "storysmith"
const DEFAULT_PASSWORD = process.env.ADMIN_DEFAULT_PASSWORD || "storysmith";
const DEFAULT_PASSWORD_HASH = crypto
  .createHash("sha256")
  .update(DEFAULT_PASSWORD)
  .digest("hex");

export function loadStore(): Store {
  const dataDir = path.dirname(DATA_PATH);
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  if (!fs.existsSync(DATA_PATH)) {
    const empty: Store = {
      stories: [],
      episodes: [],
      vote_options: [],
      votes: [],
      comments: [],
      generation_runs: [],
      step_selections: [],
      skipped_steps: [],
      admin: { password_hash: DEFAULT_PASSWORD_HASH },
      next_id: { stories: 1, episodes: 1, vote_options: 1, votes: 1, comments: 1, generation_runs: 1 },
    };
    fs.writeFileSync(DATA_PATH, JSON.stringify(empty, null, 2));
    return empty;
  }
  const store = JSON.parse(fs.readFileSync(DATA_PATH, "utf-8")) as Store;
  // Migration
  if (!store.stories) store.stories = [];
  if (!store.comments) store.comments = [];
  if (!store.generation_runs) store.generation_runs = [];
  if (!store.step_selections) store.step_selections = [];
  if (!store.skipped_steps) store.skipped_steps = [];
  if (!store.admin) store.admin = { password_hash: DEFAULT_PASSWORD_HASH };
  if (!store.next_id.stories) store.next_id.stories = 1;
  if (!store.next_id.comments) store.next_id.comments = 1;
  if (!store.next_id.generation_runs) store.next_id.generation_runs = 1;
  // Migration: ensure episode story_id is always a number
  for (const ep of store.episodes) {
    if (typeof ep.story_id === "string") {
      ep.story_id = Number(ep.story_id);
    }
    // Migration: add poster/gallery fields
    if (!ep.poster_url && ep.poster_url !== null) ep.poster_url = null;
    if (!ep.gallery) ep.gallery = [];
  }
  // Migration: add poster_episode_id to stories
  for (const s of store.stories) {
    if (s.poster_episode_id === undefined) s.poster_episode_id = null;
  }
  // Auto-sync: if .env password changed, update store hash
  if (store.admin.password_hash !== DEFAULT_PASSWORD_HASH) {
    store.admin.password_hash = DEFAULT_PASSWORD_HASH;
    saveStore(store);
  }
  return store;
}

export function saveStore(store: Store): void {
  const dataDir = path.dirname(DATA_PATH);
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  // Atomic write: write to temp file then rename to prevent corruption from concurrent writes
  const tmpPath = DATA_PATH + ".tmp";
  fs.writeFileSync(tmpPath, JSON.stringify(store, null, 2));
  fs.renameSync(tmpPath, DATA_PATH);
}

// --- Story types & queries ---

export interface Story {
  id: number;
  slug: string;
  title: string;
  title_zh: string;
  description: string;
  description_zh: string;
  background: string;
  status: "active" | "completed" | "draft";
  poster_episode_id: number | null;
  selected_poster_en?: string | null;
  selected_poster_zh?: string | null;
  created_at: string;
}

export async function getStories(): Promise<Story[]> {
  const store = loadStore();
  return store.stories
    .filter((s) => s.status !== "draft")
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
}

export async function getAllStories(): Promise<Story[]> {
  const store = loadStore();
  return store.stories.sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
}

export async function getStory(slug: string): Promise<Story | undefined> {
  const store = loadStore();
  return store.stories.find((s) => s.slug === slug);
}

export async function getStoryById(id: number): Promise<Story | undefined> {
  const store = loadStore();
  return store.stories.find((s) => s.id === id);
}

/**
 * Get the poster URL for a story. Uses the poster from the selected episode
 * (poster_episode_id), or falls back to the first episode with a poster.
 */
export function getStoryPosterUrl(story: Story, size: string = "16_9", locale: string = "en"): string | null {
  // Check if admin has selected a specific poster for this language
  const selectedPoster = locale === "zh" ? story.selected_poster_zh : story.selected_poster_en;
  if (selectedPoster) {
    const selectedFile = path.join(storyAssetsDir(story.slug), "poster", selectedPoster);
    if (fs.existsSync(selectedFile)) {
      return cacheBust(selectedFile, `/api/assets/${story.slug}/poster/${selectedPoster}`);
    }
  }

  // New 4-variant poster system: poster/poster_{orientation}_{lang}.png
  // Map legacy size names to orientation
  const orientation = (size === "9_16" || size === "2_3" || size === "7_10" || size === "3_4") ? "vertical" : "horizontal";
  const lang = locale === "zh" ? "zh" : "en";

  const posterDir = path.join(storyAssetsDir(story.slug), "poster");
  if (fs.existsSync(posterDir)) {
    // Try requested variant (orientation + language)
    const variantFile = path.join(posterDir, `poster_${orientation}_${lang}.png`);
    if (fs.existsSync(variantFile)) {
      return cacheBust(variantFile, `/api/assets/${story.slug}/poster/poster_${orientation}_${lang}.png`);
    }
    // Try same orientation, other language
    const otherLang = lang === "en" ? "zh" : "en";
    const fallbackFile = path.join(posterDir, `poster_${orientation}_${otherLang}.png`);
    if (fs.existsSync(fallbackFile)) {
      return cacheBust(fallbackFile, `/api/assets/${story.slug}/poster/poster_${orientation}_${otherLang}.png`);
    }
    // Try any available poster in the directory
    const files = fs.readdirSync(posterDir).filter((f: string) => /^poster_.*\.(png|jpg|jpeg)$/i.test(f));
    if (files.length > 0) {
      const fp = path.join(posterDir, files[0]);
      return cacheBust(fp, `/api/assets/${story.slug}/poster/${files[0]}`);
    }
  }

  // Legacy fallback: posters/ep{N}/ directory
  if (story.poster_episode_id) {
    const store = loadStore();
    const ep = store.episodes.find((e) => e.id === story.poster_episode_id);
    if (ep) {
      const legacyFile = path.join(storyAssetsDir(story.slug), "posters", `ep${ep.episode_number}`, `poster_${size}.jpg`);
      if (fs.existsSync(legacyFile)) {
        return cacheBust(legacyFile, `/api/assets/${story.slug}/posters/ep${ep.episode_number}/poster_${size}.jpg`);
      }
    }
  }

  // Fallback: episode poster (which itself falls back to gallery)
  const store = loadStore();
  const latestEp = store.episodes
    .filter((e) => e.story_id === story.id && e.status === "published")
    .sort((a, b) => b.episode_number - a.episode_number)[0];
  if (latestEp) {
    return getEpisodePosterUrl(story, latestEp.episode_number, locale);
  }
  return null;
}

/**
 * Resolve the on-disk path for story assets.
 */
function storyAssetsDir(slug: string): string {
  return path.resolve(process.cwd(), "..", "data", "stories", slug);
}

/**
 * Append a cache-busting query param.
 * Uses file mtime + a per-process boot stamp so the browser
 * always refetches after a server restart.
 */
const _boot = Date.now();
function cacheBust(filePath: string, url: string): string {
  try {
    const mt = fs.statSync(filePath).mtimeMs;
    return `${url}?v=${Math.round(mt)}-${_boot}`;
  } catch {
    return url;
  }
}

/**
 * Add cache-busting to an /api/assets/... URL by resolving to disk and appending ?v=<mtime>.
 */
export function cacheBustAssetUrl(url: string): string {
  const prefix = "/api/assets/";
  if (!url.startsWith(prefix)) return url;
  const rel = url.slice(prefix.length);
  const filePath = path.resolve(process.cwd(), "..", "data", "stories", rel);
  return cacheBust(filePath, url);
}

/**
 * Get gallery image URLs for an episode (only returns URLs for files that exist on disk).
 */
export function getEpisodeGalleryUrls(story: Story, episodeNumber: number): string[] {
  const galleryDir = path.join(storyAssetsDir(story.slug), "episodes", String(episodeNumber), "final", "gallery");
  if (!fs.existsSync(galleryDir)) return [];
  const files = fs.readdirSync(galleryDir)
    .filter((f) => /\.(jpg|jpeg|png|webp)$/i.test(f))
    .sort();
  return files.map((f) => {
    const filePath = path.join(galleryDir, f);
    return cacheBust(filePath, `/api/assets/${story.slug}/episodes/${episodeNumber}/final/gallery/${f}`);
  });
}

/**
 * Get the episode poster URL. Falls back to first gallery image if no poster file exists.
 */
export function getEpisodePosterUrl(story: Story, episodeNumber: number, locale: string = "en", orientation: "horizontal" | "vertical" = "horizontal"): string | null {
  const posterDir = path.join(storyAssetsDir(story.slug), "episodes", String(episodeNumber), "final", "poster");
  const lang = locale === "zh" ? "zh" : "en";
  const otherOrientation = orientation === "horizontal" ? "vertical" : "horizontal";
  if (fs.existsSync(posterDir)) {
    // Prefer requested orientation in requested language, then other lang, then other orientation
    const preferred = [
      `poster_${orientation}_${lang}.png`,
      `poster_${orientation}_${lang === "en" ? "zh" : "en"}.png`,
      `poster_${otherOrientation}_${lang}.png`,
      `poster_${otherOrientation}_${lang === "en" ? "zh" : "en"}.png`,
      "poster.png",
    ];
    for (const name of preferred) {
      const p = path.join(posterDir, name);
      if (fs.existsSync(p)) {
        return cacheBust(p, `/api/assets/${story.slug}/episodes/${episodeNumber}/final/poster/${name}`);
      }
    }
    // Try any poster file
    const files = fs.readdirSync(posterDir).filter((f: string) => /^poster.*\.(png|jpg|jpeg)$/i.test(f));
    if (files.length > 0) {
      const fp = path.join(posterDir, files[0]);
      return cacheBust(fp, `/api/assets/${story.slug}/episodes/${episodeNumber}/final/poster/${files[0]}`);
    }
  }
  // Fallback: first gallery image
  const gallery = getEpisodeGalleryUrls(story, episodeNumber);
  return gallery.length > 0 ? gallery[0] : null;
}

/**
 * Get ALL episode poster URLs (both orientations in the current locale).
 * Returns { url, orientation } pairs so the UI can render them at natural size.
 */
export function getEpisodePosterUrls(story: Story, episodeNumber: number, locale: string = "en"): { url: string; orientation: "horizontal" | "vertical" }[] {
  const posterDir = path.join(storyAssetsDir(story.slug), "episodes", String(episodeNumber), "final", "poster");
  const lang = locale === "zh" ? "zh" : "en";
  const results: { url: string; orientation: "horizontal" | "vertical" }[] = [];
  if (!fs.existsSync(posterDir)) return results;
  for (const orient of ["horizontal", "vertical"] as const) {
    const name = `poster_${orient}_${lang}.png`;
    const p = path.join(posterDir, name);
    if (fs.existsSync(p)) {
      results.push({ url: cacheBust(p, `/api/assets/${story.slug}/episodes/${episodeNumber}/final/poster/${name}`), orientation: orient });
    } else {
      // Try other language
      const otherLang = lang === "en" ? "zh" : "en";
      const altName = `poster_${orient}_${otherLang}.png`;
      const altP = path.join(posterDir, altName);
      if (fs.existsSync(altP)) {
        results.push({ url: cacheBust(altP, `/api/assets/${story.slug}/episodes/${episodeNumber}/final/poster/${altName}`), orientation: orient });
      }
    }
  }
  return results;
}

/**
 * Read the narrative summary from final_summary.yaml for an episode.
 */
export function getEpisodeNarrative(story: { slug: string }, episodeNumber: number, locale: string): string | null {
  const summaryPath = path.join(storyAssetsDir(story.slug), "episodes", String(episodeNumber), "final_summary.yaml");
  if (!fs.existsSync(summaryPath)) return null;
  try {
    const content = fs.readFileSync(summaryPath, "utf-8");
    // Simple YAML value extraction (avoid adding a yaml dependency)
    const zhMatch = content.match(/^narrative_summary_zh:\s*['"']?([\s\S]*?)(?:\n\S|\n\n)/m);
    const enMatch = content.match(/^narrative_summary:\s*['"']?([\s\S]*?)(?:\n\S|\n\n)/m);
    const zhRaw = zhMatch ? zhMatch[1].replace(/^['"]|['"]$/g, "").trim() : null;
    const enRaw = enMatch ? enMatch[1].replace(/^['"]|['"]$/g, "").trim() : null;
    const raw = locale === "zh" && zhRaw ? zhRaw : enRaw;
    if (!raw) return null;
    // Return first sentence/line as a one-liner
    const firstSentence = raw.split(/[。.!！\n]/).filter(Boolean)[0]?.trim();
    return firstSentence || null;
  } catch {
    return null;
  }
}

export async function createStory(data: {
  title: string;
  title_zh: string;
  slug: string;
  description: string;
  description_zh: string;
  background: string;
}): Promise<number> {
  const store = loadStore();
  const id = store.next_id.stories++;
  store.stories.push({
    id,
    slug: data.slug,
    title: data.title,
    title_zh: data.title_zh,
    description: data.description,
    description_zh: data.description_zh,
    background: data.background,
    status: "active",
    poster_episode_id: null,
    created_at: new Date().toISOString(),
  });
  saveStore(store);
  return id;
}

export async function updateStory(
  id: number,
  data: Partial<Pick<Story, "title" | "title_zh" | "description" | "description_zh" | "background" | "status" | "poster_episode_id" | "selected_poster_en" | "selected_poster_zh">>
): Promise<void> {
  const store = loadStore();
  const story = store.stories.find((s) => s.id === id);
  if (!story) return;
  Object.assign(story, data);
  saveStore(store);
}

// --- Episode types & queries ---

export interface Episode {
  id: number;
  story_id: number;
  episode_number: number;
  title: string;
  title_zh: string;
  status: string;
  video_url: string | null;
  video_url_en: string | null;
  thumbnail_url: string | null;
  poster_url: string | null;
  gallery: string[];
  voting_open: boolean;
  voting_deadline: string | null;
  admin_prompt: string | null;
  admin_prompt_weight: number;
  published_at: string;
}

export async function getEpisodes(storyId?: number): Promise<Episode[]> {
  const store = loadStore();
  return store.episodes
    .filter((e) => e.status === "published" && (storyId == null || e.story_id === storyId))
    .sort((a, b) => b.episode_number - a.episode_number);
}

export async function getEpisodesByStory(storyId: number): Promise<Episode[]> {
  const store = loadStore();
  return store.episodes
    .filter((e) => e.story_id === storyId)
    .sort((a, b) => a.episode_number - b.episode_number);
}

export async function getEpisode(
  episodeNumber: number,
  storyId?: number
): Promise<Episode | undefined> {
  const store = loadStore();
  return store.episodes.find(
    (e) => e.episode_number === episodeNumber && (storyId == null || e.story_id === storyId)
  );
}

export async function getEpisodeById(id: number): Promise<Episode | undefined> {
  const store = loadStore();
  return store.episodes.find((e) => e.id === id);
}

export async function getActiveVotingEpisode(storyId?: number): Promise<Episode | undefined> {
  const store = loadStore();
  return store.episodes
    .filter((e) => e.voting_open && (storyId == null || e.story_id === storyId))
    .sort((a, b) => b.episode_number - a.episode_number)[0];
}

export async function createEpisode(data: {
  story_id: number;
  episode_number: number;
  title: string;
  title_zh?: string;
  video_url?: string;
  video_url_en?: string;
  thumbnail_url?: string;
  voting_options?: { label: string; label_zh?: string }[];
  admin_prompt?: string;
  admin_prompt_weight?: number;
}): Promise<number> {
  const store = loadStore();
  const id = store.next_id.episodes++;

  store.episodes.push({
    id,
    story_id: data.story_id,
    episode_number: data.episode_number,
    title: data.title,
    title_zh: data.title_zh || data.title,
    status: "draft",
    video_url: data.video_url || null,
    video_url_en: data.video_url_en || null,
    thumbnail_url: data.thumbnail_url || null,
    poster_url: null,
    gallery: [],
    voting_open: false,
    voting_deadline: null,
    admin_prompt: data.admin_prompt || null,
    admin_prompt_weight: data.admin_prompt_weight ?? 0.75,
    published_at: new Date().toISOString(),
  });

  if (data.voting_options) {
    data.voting_options.forEach((opt, i) => {
      const optId = store.next_id.vote_options++;
      store.vote_options.push({
        id: optId,
        episode_id: id,
        label: opt.label,
        label_zh: opt.label_zh || opt.label,
        description: null,
        description_zh: null,
        sort_order: i,
      });
    });
  }

  saveStore(store);
  return id;
}

// --- Vote queries ---

export interface VoteOption {
  id: number;
  episode_id: number;
  label: string;
  label_zh: string;
  description: string | null;
  description_zh: string | null;
  sort_order: number;
}

export interface VoteResult {
  option_id: number;
  label: string;
  label_zh: string;
  count: number;
}

export async function getVoteOptions(episodeId: number): Promise<VoteOption[]> {
  const store = loadStore();
  return store.vote_options
    .filter((o) => o.episode_id === episodeId)
    .sort((a, b) => a.sort_order - b.sort_order);
}

export async function getVoteResults(episodeId: number): Promise<VoteResult[]> {
  const store = loadStore();
  const options = store.vote_options
    .filter((o) => o.episode_id === episodeId)
    .sort((a, b) => a.sort_order - b.sort_order);

  return options.map((opt) => ({
    option_id: opt.id,
    label: opt.label,
    label_zh: opt.label_zh,
    count: store.votes.filter((v) => v.option_id === opt.id).length,
  }));
}

export function getVoteDeadlineHours(): number {
  const raw = process.env.VOTE_DEADLINE_HOURS || "72";
  try {
    // Support expressions like "365*24"
    const val = Function(`"use strict"; return (${raw})`)();
    return typeof val === "number" && val > 0 ? val : 72;
  } catch {
    return 72;
  }
}

export function computeVotingDeadline(episode: { published_at: string; voting_deadline: string | null }): string | null {
  if (!episode.published_at) return null;
  // Always recompute from published_at + env hours so changes to VOTE_DEADLINE_HOURS take effect
  const hours = getVoteDeadlineHours();
  const deadline = new Date(new Date(episode.published_at).getTime() + hours * 3600_000);
  return deadline.toISOString();
}

function isVotingExpired(episode: EpisodeRecord): boolean {
  const deadline = computeVotingDeadline(episode);
  if (!deadline) return false;
  return new Date() > new Date(deadline);
}

export async function castVote(
  episodeId: number,
  optionId: number,
  voterId: string
): Promise<{ success: boolean; error?: string }> {
  const store = loadStore();
  const episode = store.episodes.find((e) => e.id === episodeId);
  if (!episode || !episode.voting_open) {
    return { success: false, error: "Voting is closed" };
  }
  // Enforce deadline
  if (isVotingExpired(episode)) {
    episode.voting_open = false;
    saveStore(store);
    return { success: false, error: "Voting deadline has passed" };
  }
  const option = store.vote_options.find(
    (o) => o.id === optionId && o.episode_id === episodeId
  );
  if (!option) return { success: false, error: "Invalid vote option" };

  const existing = store.votes.find(
    (v) => v.episode_id === episodeId && v.voter_id === voterId
  );
  if (existing && process.env.NODE_ENV === "production") {
    return { success: false, error: "Already voted" };
  }

  const id = store.next_id.votes++;
  store.votes.push({ id, episode_id: episodeId, option_id: optionId, voter_id: voterId, voted_at: new Date().toISOString() });
  saveStore(store);
  return { success: true };
}

export async function closeVoting(episodeId: number): Promise<void> {
  const store = loadStore();
  const episode = store.episodes.find((e) => e.id === episodeId);
  if (episode) {
    episode.voting_open = false;
    saveStore(store);
  }
}

// --- Comment queries ---

export interface Comment {
  id: number;
  episode_id: number;
  author: string;
  content: string;
  moderated: boolean;
  flagged: boolean;
  created_at: string;
}

export async function getComments(
  episodeId: number,
  opts?: { includeUnmoderated?: boolean }
): Promise<Comment[]> {
  const store = loadStore();
  return store.comments
    .filter(
      (c) =>
        c.episode_id === episodeId &&
        (opts?.includeUnmoderated || c.moderated) &&
        !c.flagged
    )
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
}

export async function getAllComments(): Promise<Comment[]> {
  const store = loadStore();
  return store.comments.sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
}

export async function addComment(
  episodeId: number,
  author: string,
  content: string
): Promise<{ success: boolean; id?: number; error?: string }> {
  if (!author.trim() || !content.trim()) {
    return { success: false, error: "Author and content are required" };
  }
  if (content.length > 1000) {
    return { success: false, error: "Comment too long (max 1000 chars)" };
  }
  const store = loadStore();
  const episode = store.episodes.find((e) => e.id === episodeId);
  if (!episode) return { success: false, error: "Episode not found" };

  const id = store.next_id.comments++;
  store.comments.push({
    id,
    episode_id: episodeId,
    author: author.trim().substring(0, 50),
    content: content.trim(),
    moderated: false,
    flagged: false,
    created_at: new Date().toISOString(),
  });
  saveStore(store);
  return { success: true, id };
}

export async function moderateComment(
  commentId: number,
  action: "approve" | "flag" | "delete"
): Promise<void> {
  const store = loadStore();
  const idx = store.comments.findIndex((c) => c.id === commentId);
  if (idx === -1) return;
  if (action === "delete") store.comments.splice(idx, 1);
  else if (action === "approve") { store.comments[idx].moderated = true; store.comments[idx].flagged = false; }
  else if (action === "flag") store.comments[idx].flagged = true;
  saveStore(store);
}

export async function getCommentSummaryData(
  episodeId: number
): Promise<{ total: number; moderated: number; flagged: number; comments: Comment[] }> {
  const store = loadStore();
  const all = store.comments.filter((c) => c.episode_id === episodeId);
  return {
    total: all.length,
    moderated: all.filter((c) => c.moderated).length,
    flagged: all.filter((c) => c.flagged).length,
    comments: all.filter((c) => c.moderated && !c.flagged),
  };
}

// --- Admin queries ---

export async function getAllEpisodes(): Promise<Episode[]> {
  const store = loadStore();
  return store.episodes.sort((a, b) => b.episode_number - a.episode_number);
}

export async function updateEpisode(
  id: number,
  data: Partial<Pick<Episode, "title" | "title_zh" | "status" | "video_url" | "video_url_en" | "thumbnail_url" | "voting_open" | "admin_prompt" | "admin_prompt_weight">>
): Promise<void> {
  const store = loadStore();
  const episode = store.episodes.find((e) => e.id === id);
  if (!episode) return;
  Object.assign(episode, data);
  saveStore(store);
}

export async function deleteEpisode(id: number): Promise<void> {
  const store = loadStore();
  store.episodes = store.episodes.filter((e) => e.id !== id);
  store.vote_options = store.vote_options.filter((o) => o.episode_id !== id);
  store.votes = store.votes.filter((v) => v.episode_id !== id);
  store.comments = store.comments.filter((c) => c.episode_id !== id);
  saveStore(store);
}

// --- Auth ---

export async function verifyAdminPassword(password: string): Promise<boolean> {
  const store = loadStore();
  const encoder = new TextEncoder();
  const data = encoder.encode(password);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashHex = Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return hashHex === store.admin.password_hash;
}

export async function changeAdminPassword(newPassword: string): Promise<void> {
  const store = loadStore();
  const encoder = new TextEncoder();
  const data = encoder.encode(newPassword);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  store.admin.password_hash = Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  saveStore(store);
}

// --- Generation Runs ---

export interface GenerationStep {
  step_id: string;
  label: string;
  status: "pending" | "running" | "done" | "failed";
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  output: string;
  exit_code: number | null;
}

export interface GenerationRun {
  id: number;
  episode_id: number;
  story_id: number;
  mode: "full" | "single";
  status: "running" | "completed" | "failed";
  steps: GenerationStep[];
  started_at: string;
  ended_at: string | null;
}

export async function createGenerationRun(data: {
  episode_id: number;
  story_id: number;
  mode: "full" | "single";
  steps: { step_id: string; label: string }[];
}): Promise<number> {
  const store = loadStore();
  const id = store.next_id.generation_runs++;
  store.generation_runs.push({
    id,
    episode_id: data.episode_id,
    story_id: data.story_id,
    mode: data.mode,
    status: "running",
    steps: data.steps.map((s) => ({
      step_id: s.step_id,
      label: s.label,
      status: "pending",
      started_at: null,
      ended_at: null,
      duration_ms: null,
      output: "",
      exit_code: null,
      output_dir: null,
    })),
    started_at: new Date().toISOString(),
    ended_at: null,
  });
  saveStore(store);
  return id;
}

export async function updateGenerationStep(
  runId: number,
  stepId: string,
  update: Partial<GenerationStepRecord>
): Promise<void> {
  const store = loadStore();
  const run = store.generation_runs.find((r) => r.id === runId);
  if (!run) return;
  const step = run.steps.find((s) => s.step_id === stepId);
  if (!step) return;
  Object.assign(step, update);
  saveStore(store);
}

export async function appendGenerationOutput(
  runId: number,
  stepId: string,
  text: string
): Promise<void> {
  const store = loadStore();
  const run = store.generation_runs.find((r) => r.id === runId);
  if (!run) return;
  const step = run.steps.find((s) => s.step_id === stepId);
  if (!step) return;
  step.output += text + "\n";
  saveStore(store);
}

export async function completeGenerationRun(
  runId: number,
  status: "completed" | "failed"
): Promise<void> {
  const store = loadStore();
  const run = store.generation_runs.find((r) => r.id === runId);
  if (!run) return;
  run.status = status;
  run.ended_at = new Date().toISOString();
  saveStore(store);
}

export async function getGenerationRuns(episodeId?: number): Promise<GenerationRun[]> {
  const store = loadStore();
  let runs = store.generation_runs;
  if (episodeId != null) {
    runs = runs.filter((r) => r.episode_id === episodeId);
  }
  return runs.sort((a, b) => b.id - a.id);
}

export async function getGenerationRun(id: number): Promise<GenerationRun | undefined> {
  const store = loadStore();
  return store.generation_runs.find((r) => r.id === id);
}

export async function clearGenerationRuns(episodeId?: number): Promise<void> {
  const store = loadStore();
  if (episodeId != null) {
    store.generation_runs = store.generation_runs.filter((r) => r.episode_id !== episodeId);
    // Also clear step selections for this episode
    store.step_selections = store.step_selections.filter((s) => s.episode_id !== episodeId);
  } else {
    store.generation_runs = [];
    store.step_selections = [];
  }
  // Reset ID counter if no runs remain
  if (store.generation_runs.length === 0) {
    store.next_id.generation_runs = 1;
  }
  saveStore(store);
}

export async function deleteStepFromRun(
  storyId: number,
  episodeId: number,
  stepId: string,
  runId: number
): Promise<void> {
  const store = loadStore();
  const run = store.generation_runs.find(
    (r) => r.id === runId && r.story_id === storyId && r.episode_id === episodeId
  );
  if (!run) return;

  // Remove the step from this run
  run.steps = run.steps.filter((s) => s.step_id !== stepId);

  // If run has no steps left, remove it entirely
  if (run.steps.length === 0) {
    store.generation_runs = store.generation_runs.filter((r) => r.id !== runId);
  }

  // Clear step selection if it pointed to this run
  const selIdx = store.step_selections.findIndex(
    (s) => s.story_id === storyId && s.episode_id === episodeId && s.step_id === stepId && s.run_id === runId
  );
  if (selIdx >= 0) {
    store.step_selections.splice(selIdx, 1);
  }

  // Reset ID counter if no runs remain
  if (store.generation_runs.length === 0) {
    store.next_id.generation_runs = 1;
  }

  saveStore(store);
}

export async function clearStepRuns(
  storyId: number,
  episodeId: number,
  stepId: string
): Promise<void> {
  const store = loadStore();

  // Remove this step from all runs matching story/episode
  for (const run of store.generation_runs) {
    if (run.story_id === storyId && run.episode_id === episodeId) {
      run.steps = run.steps.filter((s) => s.step_id !== stepId);
    }
  }

  // Remove runs that have no steps left
  store.generation_runs = store.generation_runs.filter((r) => r.steps.length > 0);

  // Clear step selection for this step
  store.step_selections = store.step_selections.filter(
    (s) => !(s.story_id === storyId && s.episode_id === episodeId && s.step_id === stepId)
  );

  // Reset ID counter if no runs remain
  if (store.generation_runs.length === 0) {
    store.next_id.generation_runs = 1;
  }

  saveStore(store);
}

export async function skipStep(
  storyId: number,
  episodeId: number,
  stepId: string,
  _stepLabel: string
): Promise<number> {
  const store = loadStore();
  // Store skip in a lightweight array — no generation_run created
  if (!store.skipped_steps) store.skipped_steps = [];
  const already = store.skipped_steps.find(
    (s) => s.story_id === storyId && s.episode_id === episodeId && s.step_id === stepId
  );
  if (!already) {
    store.skipped_steps.push({ story_id: storyId, episode_id: episodeId, step_id: stepId });
  }
  saveStore(store);
  return 0; // No run ID — nothing was created
}

export function unskipStep(
  storyId: number,
  episodeId: number,
  stepId: string
): void {
  const store = loadStore();
  if (!store.skipped_steps) return;
  store.skipped_steps = store.skipped_steps.filter(
    (s) => !(s.story_id === storyId && s.episode_id === episodeId && s.step_id === stepId)
  );
  saveStore(store);
}

export function getSkippedSteps(
  storyId: number,
  episodeId: number
): string[] {
  const store = loadStore();
  if (!store.skipped_steps) return [];
  return store.skipped_steps
    .filter((s) => s.story_id === storyId && s.episode_id === episodeId)
    .map((s) => s.step_id);
}

// --- Step Runs (per story/episode/step) ---

export interface StepRunInfo {
  run_id: number;
  status: "pending" | "running" | "done" | "failed";
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  output: string;
  output_dir: string | null;
  pid: number | null;
  selected: boolean;
}

export async function getStepRuns(
  storyId: number,
  episodeId: number,
  stepId: string
): Promise<StepRunInfo[]> {
  const store = loadStore();
  const selection = store.step_selections.find(
    (s) => s.story_id === storyId && s.episode_id === episodeId && s.step_id === stepId
  );
  const selectedRunId = selection?.run_id ?? null;

  const runs: StepRunInfo[] = [];
  for (const run of store.generation_runs) {
    if (run.story_id !== storyId || run.episode_id !== episodeId) continue;
    const step = run.steps.find((s) => s.step_id === stepId);
    if (!step) continue;
    runs.push({
      run_id: run.id,
      status: step.status,
      started_at: step.started_at,
      ended_at: step.ended_at,
      duration_ms: step.duration_ms,
      output: step.output,
      output_dir: step.output_dir || null,
      pid: step.pid || null,
      selected: run.id === selectedRunId,
    });
  }
  // Sort by run_id descending (newest first)
  runs.sort((a, b) => b.run_id - a.run_id);
  return runs;
}

export async function selectStepRun(
  storyId: number,
  episodeId: number,
  stepId: string,
  runId: number
): Promise<void> {
  const store = loadStore();
  const idx = store.step_selections.findIndex(
    (s) => s.story_id === storyId && s.episode_id === episodeId && s.step_id === stepId
  );
  if (idx >= 0) {
    store.step_selections[idx].run_id = runId;
  } else {
    store.step_selections.push({ story_id: storyId, episode_id: episodeId, step_id: stepId, run_id: runId });
  }
  saveStore(store);
}

export async function getStepSelections(
  storyId: number,
  episodeId: number
): Promise<Record<string, number>> {
  const store = loadStore();
  const result: Record<string, number> = {};
  for (const sel of store.step_selections) {
    if (sel.story_id === storyId && sel.episode_id === episodeId) {
      result[sel.step_id] = sel.run_id;
    }
  }
  return result;
}

export async function hasSuccessfulRun(
  storyId: number,
  episodeId: number,
  stepId: string
): Promise<boolean> {
  const store = loadStore();
  for (const run of store.generation_runs) {
    if (run.story_id !== storyId || run.episode_id !== episodeId) continue;
    const step = run.steps.find((s) => s.step_id === stepId);
    if (step && step.status === "done") return true;
  }
  return false;
}

/**
 * Get the selected run's output_dir and run_id for each step that has a selection.
 * Returns a map of stepId -> { output_dir, run_id }.
 */
export function getSelectedOutputDirs(
  storyId: number,
  episodeId: number
): Record<string, { output_dir: string; run_id: number }> {
  const store = loadStore();
  const result: Record<string, { output_dir: string; run_id: number }> = {};
  for (const sel of store.step_selections) {
    if (sel.story_id !== storyId || sel.episode_id !== episodeId) continue;
    // Find the run and its step to get output_dir
    const run = store.generation_runs.find((r) => r.id === sel.run_id);
    if (!run) continue;
    const step = run.steps.find((s) => s.step_id === sel.step_id);
    if (step?.output_dir) {
      result[sel.step_id] = { output_dir: step.output_dir, run_id: run.id };
    }
  }
  return result;
}
