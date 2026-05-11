"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale } from "@/lib/useLocale";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";

// -- Types --
interface LogEntry { timestamp: string; type: "info" | "success" | "error" | "warning" | "step"; message: string; stepId?: string; }
type StepStatus = "pending" | "running" | "done" | "failed" | "locked";
interface StepState { id: string; label: string; status: StepStatus; started_at: string | null; ended_at: string | null; duration_ms: number | null; output: string; }
interface Story { id: number; title: string; title_zh: string; slug: string; }
interface EpisodeOption { id: number; episode_number: number; title: string; title_zh?: string; story_id: number; }
interface ArtifactFile { name: string; size: number; type: string; }
interface StepArtifacts { available: boolean; files: ArtifactFile[]; }
interface GenerationRun { id: number; episode_id: number; story_id: number; mode: "full" | "single"; status: "running" | "completed" | "failed"; steps: { step_id: string; label: string; status: string; started_at: string | null; ended_at: string | null; duration_ms: number | null; output: string }[]; started_at: string; ended_at: string | null; }
interface StepRunInfo { run_id: number; status: "pending" | "running" | "done" | "failed"; started_at: string | null; ended_at: string | null; duration_ms: number | null; output: string; output_dir: string | null; selected: boolean; }
interface ModelInfo { id: string; label: string; provider: string; free: boolean; available: boolean; }

// -- Pipeline definition --
const PIPELINE_STEPS = [
  { id: "generate_script", labelKey: "admin_gen_step_script" as TranslationKey, descKey: "admin_gen_step_script_desc" as TranslationKey },
  { id: "plan_scenes", labelKey: "admin_gen_step_scenes" as TranslationKey, descKey: "admin_gen_step_scenes_desc" as TranslationKey },
  { id: "design_characters", labelKey: "admin_gen_step_characters" as TranslationKey, descKey: "admin_gen_step_characters_desc" as TranslationKey },
  { id: "design_locations", labelKey: "admin_gen_step_locations" as TranslationKey, descKey: "admin_gen_step_locations_desc" as TranslationKey },
  { id: "generate_keyframes", labelKey: "admin_gen_step_keyframes" as TranslationKey, descKey: "admin_gen_step_keyframes_desc" as TranslationKey },
  { id: "generate_clips", labelKey: "admin_gen_step_clips" as TranslationKey, descKey: "admin_gen_step_clips_desc" as TranslationKey },
  { id: "validate_quality", labelKey: "admin_gen_step_quality" as TranslationKey, descKey: "admin_gen_step_quality_desc" as TranslationKey },
  { id: "add_audio", labelKey: "admin_gen_step_audio" as TranslationKey, descKey: "admin_gen_step_audio_desc" as TranslationKey },
  { id: "compose_episode", labelKey: "admin_gen_step_compose" as TranslationKey, descKey: "admin_gen_step_compose_desc" as TranslationKey },
  { id: "publish", labelKey: "admin_gen_step_publish" as TranslationKey, descKey: "admin_gen_step_publish_desc" as TranslationKey },
];

/** Get translated step label */
function stepLabel(locale: Locale, stepId: string): string {
  const step = PIPELINE_STEPS.find((s) => s.id === stepId);
  return step ? t(locale, step.labelKey) : stepId;
}
/** Get translated step description */
function stepDesc(locale: Locale, stepId: string): string {
  const step = PIPELINE_STEPS.find((s) => s.id === stepId);
  return step ? t(locale, step.descKey) : "";
}

// -- SVG Icons --
function StepIcon({ stepId, className }: { stepId: string; className?: string }) {
  const cls = className || "w-10 h-10";
  switch (stepId) {
    case "generate_script": return (<svg className={cls} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="10" y="6" width="28" height="36" rx="3" /><line x1="16" y1="14" x2="32" y2="14" /><line x1="16" y1="20" x2="32" y2="20" /><line x1="16" y1="26" x2="28" y2="26" /><line x1="16" y1="32" x2="24" y2="32" /></svg>);
    case "plan_scenes": return (<svg className={cls} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="10" width="40" height="28" rx="3" /><polygon points="20,18 20,34 34,26" /><line x1="4" y1="38" x2="44" y2="38" /></svg>);
    case "design_characters": return (<svg className={cls} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="24" cy="16" r="8" /><path d="M10 42c0-8 6-14 14-14s14 6 14 14" /><circle cx="36" cy="12" r="5" strokeDasharray="3 2" /><path d="M30 38c0-5 3-9 6-9" strokeDasharray="3 2" /></svg>);
    case "design_locations": return (<svg className={cls} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M24 4C16 4 10 10 10 18c0 10 14 26 14 26s14-16 14-26c0-8-6-14-14-14z" /><circle cx="24" cy="18" r="6" /><line x1="4" y1="42" x2="44" y2="42" /></svg>);
    case "generate_keyframes": return (<svg className={cls} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="8" width="12" height="12" rx="2" /><rect x="18" y="8" width="12" height="12" rx="2" /><rect x="32" y="8" width="12" height="12" rx="2" /><path d="M10 28v12" /><path d="M24 28v12" /><path d="M38 28v12" /><circle cx="10" cy="34" r="3" /><circle cx="24" cy="34" r="3" /><circle cx="38" cy="34" r="3" /><line x1="13" y1="34" x2="21" y2="34" /><line x1="27" y1="34" x2="35" y2="34" /></svg>);
    case "generate_clips": return (<svg className={cls} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="6" y="12" width="36" height="24" rx="3" /><circle cx="14" cy="12" r="3" /><circle cx="34" cy="12" r="3" /><circle cx="14" cy="36" r="3" /><circle cx="34" cy="36" r="3" /><polygon points="20,20 20,32 32,26" /></svg>);
    case "validate_quality": return (<svg className={cls} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M24 4L6 12v12c0 10 8 16 18 20 10-4 18-10 18-20V12L24 4z" /><polyline points="16,24 22,30 32,18" /></svg>);
    case "add_audio": return (<svg className={cls} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 18v12" /><path d="M18 14v20" /><path d="M24 10v28" /><path d="M30 14v20" /><path d="M36 18v12" /><path d="M6 22v4" /><path d="M42 22v4" /></svg>);
    case "compose_episode": return (<svg className={cls} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="8" width="16" height="12" rx="2" /><rect x="28" y="8" width="16" height="12" rx="2" /><rect x="4" y="28" width="16" height="12" rx="2" /><rect x="28" y="28" width="16" height="12" rx="2" /><path d="M20 14h8" /><path d="M20 34h8" /><path d="M24 20v8" /></svg>);
    case "publish": return (<svg className={cls} viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M24 38V14" /><polyline points="16,22 24,14 32,22" /><path d="M8 38h32" /><circle cx="24" cy="8" r="3" /></svg>);
    default: return null;
  }
}

// -- Helpers --
function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
function fmtDur(ms: number | null | undefined) {
  if (!ms) return "";
  if (ms < 1000) return `${ms}ms`;
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}
function fmtTime(ms: number) { const s = Math.floor(ms / 1000); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }

// -- Main Component --
export default function AdminGenerate() {
  const locale = useLocale();
  const [stories, setStories] = useState<Story[]>([]);
  const [episodes, setEpisodes] = useState<EpisodeOption[]>([]);
  const [selectedStory, setSelectedStory] = useState("");
  const [selectedEpisode, setSelectedEpisode] = useState("");
  const [running, setRunning] = useState(false);
  const [runningStepId, setRunningStepId] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [stepStates, setStepStates] = useState<StepState[]>(PIPELINE_STEPS.map((s) => ({ id: s.id, label: s.id, status: "locked", started_at: null, ended_at: null, duration_ms: null, output: "" })));
  const [pipelineResult, setPipelineResult] = useState<"idle" | "success" | "failed">("idle");
  const [, setRunId] = useState<number | null>(null);
  const activeRunIdRef = useRef<number | null>(null);
  const [artifacts, setArtifacts] = useState<Record<string, StepArtifacts>>({});
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [showConsole, setShowConsole] = useState(false);
  const [previousRuns, setPreviousRuns] = useState<GenerationRun[]>([]);
  const [stepRuns, setStepRuns] = useState<Record<string, StepRunInfo[]>>({});
  const [stepSelections, setStepSelections] = useState<Record<string, number>>({});
  const [skippedSteps, setSkippedSteps] = useState<string[]>([]);
  const [llmModels, setLlmModels] = useState<ModelInfo[]>([]);
  const [videoModels, setVideoModels] = useState<ModelInfo[]>([]);
  const [audioModels, setAudioModels] = useState<ModelInfo[]>([]);
  const [selectedLlmModel, setSelectedLlmModel] = useState("");
  const [selectedVideoModel, setSelectedVideoModel] = useState("");
  const [videoExecLocal, setVideoExecLocal] = useState(false);
  const [videoAspectRatio, setVideoAspectRatio] = useState("9:16");
  const [videoStyle, setVideoStyle] = useState("chinese-cartoon");
  const [videoLength, setVideoLength] = useState("60");
  const [videoQuality, setVideoQuality] = useState("high");
  const [selectedAudioModel, setSelectedAudioModel] = useState("");
  const logEndRef = useRef<HTMLDivElement>(null);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const userScrolledUp = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);
  // Live clips streamed during generation
  const [liveClips, setLiveClips] = useState<{ name: string; runTs: string }[]>([]);
  const liveClipsRunTsRef = useRef<string | null>(null);
  // Avatar regeneration state: slug -> "loading" | "done" | "error"
  const [regenAvatarState, setRegenAvatarState] = useState<Record<string, string>>({});
  // Avatar edit prompt per slug
  const [avatarEditPrompt, setAvatarEditPrompt] = useState<Record<string, string>>({});

  // Compose options state
  const [composeSelectedClips, setComposeSelectedClips] = useState<Record<string, boolean>>({});
  const [composeSelectedAudio, setComposeSelectedAudio] = useState<Record<string, boolean>>({});
  const [composeMuteVideoAudio, setComposeMuteVideoAudio] = useState(false);
  const [composeNoWatermark, setComposeNoWatermark] = useState(false);
  const [composeSubtitles, setComposeSubtitles] = useState(true);
  const [composeGlobalEn, setComposeGlobalEn] = useState(true);
  const [composeNoOpening, setComposeNoOpening] = useState(false);

  // Clip review state
  interface ClipReview {
    name: string;
    passed: boolean;
    issues: string[];
    metrics: Record<string, number | string>;
    prompt: string;
    suggestion: string | null;
    improvement_prompt: string | null;
    first_frame_hash: string | null;
    last_frame_hash: string | null;
  }
  const [clipReview, setClipReview] = useState<{ available: boolean; clips: ClipReview[]; run_ts: string | null; passed: boolean; total_clips: number; failed_clips: number } | null>(null);
  const [clipReviewLoading, setClipReviewLoading] = useState(false);
  const [regenLoadingClip, setRegenLoadingClip] = useState<string | null>(null);
  const [regenPrompts, setRegenPrompts] = useState<Record<string, string>>({});
  const [regenResults, setRegenResults] = useState<Record<string, { regen_clip: string | null }>>({});

  useEffect(() => {
    fetch("/api/admin/stories").then((r) => r.json()).then((d) => setStories(d.stories || []));
    fetch("/api/admin/episodes").then((r) => r.json()).then((d) => setEpisodes(d.episodes || []));
    fetch("/api/admin/models").then((r) => r.json()).then((d) => {
      setLlmModels(d.llm || []);
      setVideoModels(d.video || []);
      setAudioModels(d.audio || []);
    });
  }, []);

  const filteredEpisodes = selectedStory ? episodes.filter((ep) => ep.story_id === parseInt(selectedStory)) : [];

  // Load step selections when story/episode change
  const loadStepSelections = useCallback(() => {
    if (!selectedStory || !selectedEpisode) { setStepSelections({}); setSkippedSteps([]); return; }
    fetch(`/api/admin/step-runs?story_id=${selectedStory}&episode_id=${selectedEpisode}`)
      .then((r) => r.json())
      .then((d) => { setStepSelections(d.selections || {}); setSkippedSteps(d.skipped || []); })
      .catch(() => {});
  }, [selectedStory, selectedEpisode]);

  // Load runs for a specific step
  const loadStepRuns = useCallback((stepId: string) => {
    if (!selectedStory || !selectedEpisode) return;
    fetch(`/api/admin/step-runs?story_id=${selectedStory}&episode_id=${selectedEpisode}&step=${stepId}`)
      .then((r) => r.json())
      .then((d) => setStepRuns((prev) => ({ ...prev, [stepId]: d.runs || [] })))
      .catch(() => {});
  }, [selectedStory, selectedEpisode]);

  // Load all step runs for all steps
  const loadAllStepRuns = useCallback(() => {
    if (!selectedStory || !selectedEpisode) return;
    for (const step of PIPELINE_STEPS) {
      loadStepRuns(step.id);
    }
  }, [selectedStory, selectedEpisode, loadStepRuns]);

  // Load artifacts when episode is selected
  const loadArtifacts = useCallback((stepId?: string, outputDir?: string) => {
    if (!selectedStory || !selectedEpisode) return;
    const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
    if (!epObj) return;
    // If stepId + outputDir given, load run-specific artifacts for that step
    if (stepId && outputDir) {
      fetch(`/api/admin/artifacts?story_id=${selectedStory}&episode=${epObj.episode_number}&step=${stepId}&run_ts=${outputDir}`)
        .then((r) => r.json())
        .then((d) => {
          if (d.artifacts?.[stepId]) {
            setArtifacts((prev) => ({ ...prev, [stepId]: d.artifacts[stepId] }));
          }
        })
        .catch(() => {});
    } else {
      fetch(`/api/admin/artifacts?story_id=${selectedStory}&episode=${epObj.episode_number}`)
        .then((r) => r.json())
        .then((d) => {
          if (d.artifacts) setArtifacts(d.artifacts);
        })
        .catch(() => {});
    }
  }, [selectedStory, selectedEpisode, episodes]);

  useEffect(() => { loadArtifacts(); loadStepSelections(); loadAllStepRuns(); }, [loadArtifacts, loadStepSelections, loadAllStepRuns]);

  // Load run-specific artifacts when a step is viewed and has a selected run
  useEffect(() => {
    if (!selectedStep || !selectedStory || !selectedEpisode) return;
    const selectedRunId = stepSelections[selectedStep];
    if (selectedRunId) {
      const runs = stepRuns[selectedStep] || [];
      const run = runs.find((r) => r.run_id === selectedRunId);
      if (run?.output_dir) loadArtifacts(selectedStep, run.output_dir);
      else loadArtifacts(selectedStep);  // Fallback: load from global path when output_dir is null
    }

    // When viewing compose_episode, also load clips and audio artifacts for the picker
    if (selectedStep === "compose_episode") {
      const clipsRunId = stepSelections["generate_clips"];
      if (clipsRunId) {
        const clipsRun = (stepRuns["generate_clips"] || []).find((r) => r.run_id === clipsRunId);
        if (clipsRun?.output_dir) loadArtifacts("generate_clips", clipsRun.output_dir);
      } else {
        // No selected clips run — try loading from the first successful run
        const clipsRuns = stepRuns["generate_clips"] || [];
        const firstSuccess = clipsRuns.find((r) => r.status === "done");
        if (firstSuccess?.output_dir) loadArtifacts("generate_clips", firstSuccess.output_dir);
      }
      const audioRunId = stepSelections["add_audio"];
      if (audioRunId) {
        const audioRun = (stepRuns["add_audio"] || []).find((r) => r.run_id === audioRunId);
        if (audioRun?.output_dir) loadArtifacts("add_audio", audioRun.output_dir);
      } else {
        // No selected audio run — try loading from the first successful run
        const audioRuns = stepRuns["add_audio"] || [];
        const firstSuccess = audioRuns.find((r) => r.status === "done");
        if (firstSuccess?.output_dir) loadArtifacts("add_audio", firstSuccess.output_dir);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStep, stepSelections, stepRuns, selectedStory, selectedEpisode]);

  useEffect(() => {
    if (selectedEpisode) fetch(`/api/admin/generation-runs?episode_id=${selectedEpisode}`).then((r) => r.json()).then((d) => setPreviousRuns(d.runs || []));
    else setPreviousRuns([]);
  }, [selectedEpisode]);

  function addLog(type: LogEntry["type"], message: string, stepId?: string) {
    setLogs((prev) => [...prev, { timestamp: new Date().toISOString(), type, message, stepId }]);
    if (!userScrolledUp.current) {
      setTimeout(() => { const el = logContainerRef.current; if (el) el.scrollTop = el.scrollHeight; }, 50);
    }
  }
  function startTimer() { startTimeRef.current = Date.now(); setElapsedMs(0); timerRef.current = setInterval(() => setElapsedMs(Date.now() - startTimeRef.current), 100); }
  function stopTimer() { if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; } }

  // Skip a step (mark as done without running)
  async function handleSkipStep(stepId: string) {
    if (!selectedStory || !selectedEpisode) return;
    const stepDef = PIPELINE_STEPS.find((s) => s.id === stepId);
    const isCurrentlySkipped = stepIsSkipped(stepId);
    const res = await fetch("/api/admin/step-runs", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        story_id: parseInt(selectedStory),
        episode_id: parseInt(selectedEpisode),
        step_id: stepId,
        action: isCurrentlySkipped ? "unskip" : "skip",
        label: stepLabel(locale, stepId),
      }),
    });
    if (res.ok) {
      addLog("info", isCurrentlySkipped ? `${t(locale, "admin_gen_unskip")}: ${stepLabel(locale, stepId)}` : `${t(locale, "admin_gen_skip")}: ${stepLabel(locale, stepId)}`);
      loadStepSelections();
    }
  }

  // Run pipeline (full or single step)
  async function runStep(stepId?: string) {
    if (!selectedEpisode) { addLog("error", "Select a story and episode first"); return; }
    const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
    const episodeNum = epObj ? String(epObj.episode_number) : selectedEpisode;
    const effectiveMode = stepId ? "single" : "full";

    setRunning(true); setLogs([]); setPipelineResult("idle"); setShowConsole(true);
    setRunningStepId(stepId || null);
    if (stepId) {
      setStepStates((prev) => prev.map((s) => s.id === stepId ? { ...s, status: "running", output: "" } : s));
    } else {
      // Full pipeline: mark first pending as running
      setStepStates((prev) => {
        const firstPending = prev.findIndex((s) => s.status !== "done");
        return prev.map((s, i) => i === firstPending ? { ...s, status: "running", output: "" } : { ...s, output: "" });
      });
    }
    startTimer();
    const controller = new AbortController(); abortRef.current = controller;
    addLog("info", `Starting ${effectiveMode === "full" ? t(locale, "admin_gen_full_pipeline") : stepLabel(locale, stepId || "")}...`);

    try {
      const res = await fetch("/api/generate", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ episode: episodeNum, mode: effectiveMode, step: stepId, episode_id: parseInt(selectedEpisode), story_id: parseInt(selectedStory), ...(selectedLlmModel ? { llm_model: selectedLlmModel } : {}), ...(selectedVideoModel ? { video_model: selectedVideoModel } : {}), ...(selectedAudioModel ? { audio_model: selectedAudioModel } : {}), video_local: videoExecLocal, video_aspect_ratio: videoAspectRatio, video_style: videoStyle, video_length: videoLength, video_quality: videoQuality, ...(stepId === "compose_episode" ? (() => {
          const allClipFiles = (artifacts["generate_clips"]?.files || []).filter((f: ArtifactFile) => f.type === "mp4" && /^scene_\d+_clip_\d+/.test(f.name) && !f.name.includes("_segment") && !f.name.includes(".regen"));
          const selectedClipFiles = allClipFiles.filter((f: ArtifactFile) => composeSelectedClips[f.name] !== false);
          const allAudioFiles = (artifacts["add_audio"]?.files || []).filter((f: ArtifactFile) => (f.type === "mp3" || f.type === "wav") && !f.name.includes("_segment"));
          const selectedAudioFiles = allAudioFiles.filter((f: ArtifactFile) => composeSelectedAudio[f.name] !== false);
          return {
            compose_mute_video_audio: composeMuteVideoAudio, compose_no_watermark: composeNoWatermark, compose_subtitles: composeSubtitles, compose_global_en: composeGlobalEn, compose_no_opening: composeNoOpening,
            compose_select_clips: selectedClipFiles.length < allClipFiles.length ? selectedClipFiles.map((f: ArtifactFile) => f.name).join(",") : undefined,
            compose_select_audio: selectedAudioFiles.length < allAudioFiles.length ? selectedAudioFiles.map((f: ArtifactFile) => f.name).join(",") : undefined,
          };
        })() : {}) }),
        signal: controller.signal,
      });
      if (!res.ok) { const err = await res.json().catch(() => ({ error: "Unknown" })); addLog("error", `API: ${err.error || res.statusText}`); setPipelineResult("failed"); setRunning(false); stopTimer(); return; }
      const reader = res.body?.getReader();
      if (!reader) { addLog("error", "No stream"); setRunning(false); stopTimer(); return; }
      const decoder = new TextDecoder(); let buffer = "";
      while (true) {
        const { done, value } = await reader.read(); if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n"); buffer = lines.pop() || "";
        let et = "", ed = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) et = line.slice(7);
          else if (line.startsWith("data: ")) { ed = line.slice(6); if (et && ed) { try { handleSSE(et, JSON.parse(ed)); } catch {} et = ""; ed = ""; } }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") addLog("warning", "Cancelled");
      else addLog("error", `Error: ${err instanceof Error ? err.message : "Unknown"}`);
      setPipelineResult("failed");
    }
    setRunning(false); setRunningStepId(null); stopTimer();
    // Reload artifacts after run
    loadArtifacts();
    // Refresh step runs and selections
    loadAllStepRuns();
    loadStepSelections();
    // Refresh run history
    if (selectedEpisode) fetch(`/api/admin/generation-runs?episode_id=${selectedEpisode}`).then((r) => r.json()).then((d) => setPreviousRuns(d.runs || []));
  }

  function handleSSE(event: string, data: Record<string, unknown>) {
    switch (event) {
      case "pipeline_start": if (data.run_id) { setRunId(data.run_id as number); activeRunIdRef.current = data.run_id as number; } break;
      case "step_skipped":
        setStepStates((p) => p.map((s) => s.id === data.step ? { ...s, status: "done" as StepStatus, output: (data.reason as string) || "Skipped" } : s));
        addLog("warning", `${stepLabel(locale, data.step as string)}: ${data.reason || "Skipped"}`, data.step as string); break;
      case "step_start":
        setStepStates((p) => p.map((s) => s.id === data.step ? { ...s, status: "running", started_at: data.started_at as string } : s));
        // Reset live clips when generate_clips starts
        if (data.step === "generate_clips") { setLiveClips([]); liveClipsRunTsRef.current = null; }
        addLog("step", `${data.label}`, data.step as string); break;
      case "log": {
        const logText = data.text as string;
        addLog((data.level as LogEntry["type"]) || "info", logText, data.step as string);
        setStepStates((p) => p.map((s) => s.id === data.step ? { ...s, output: s.output + logText + "\n" } : s));
        // Detect clip output directory and individual clip completions
        if (data.step === "generate_clips" && logText) {
          // "Clips output: <path>" — extract run timestamp
          const outputMatch = logText.match(/Clips output:\s+(.+)/i);
          if (outputMatch) {
            const parts = outputMatch[1].trim().replace(/\\/g, "/").split("/");
            const clipsIdx = parts.findIndex((p: string) => p === "clips");
            if (clipsIdx >= 0 && clipsIdx + 1 < parts.length) {
              const ts = parts[clipsIdx + 1];
              if (/^\d{8}_\d{6}$/.test(ts)) liveClipsRunTsRef.current = ts;
            }
          }
          // "Video saved: <path> (size)" — a new clip is ready
          const savedMatch = logText.match(/Video saved:\s+(.+?)\s*\(/i);
          if (savedMatch && liveClipsRunTsRef.current) {
            const filePath = savedMatch[1].trim().replace(/\\/g, "/");
            const fileName = filePath.split("/").pop() || "";
            // Skip segment files
            if (fileName && !fileName.includes("_segment")) {
              setLiveClips((prev) => {
                if (prev.some((c) => c.name === fileName)) return prev;
                return [...prev, { name: fileName, runTs: liveClipsRunTsRef.current! }];
              });
            }
          }
        }
        break;
      }
      case "step_end":
        setStepStates((p) => p.map((s) => s.id === data.step ? { ...s, status: (data.success ? "done" : "failed") as StepStatus, ended_at: new Date().toISOString(), duration_ms: (data.duration_ms as number) || null } : s));
        // Clear live clips when step ends (artifacts will load normally)
        if (data.step === "generate_clips") { setLiveClips([]); liveClipsRunTsRef.current = null; }
        addLog(data.success ? "success" : "error", `${stepLabel(locale, data.step as string)} ${data.success ? "done" : "failed"}`, data.step as string); break;
      case "pipeline_end":
        if (data.success) { addLog("success", t(locale, "admin_gen_complete")); setPipelineResult("success"); }
        else { addLog("error", `${t(locale, "admin_gen_failed")}: ${data.failed_step}`); setPipelineResult("failed"); }
        break;
    }
  }

  async function cancelGeneration() {
    // Kill server-side process — await to ensure DB is updated before refreshing
    if (activeRunIdRef.current) {
      try {
        await fetch("/api/generate/stop", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ run_id: activeRunIdRef.current }),
        });
      } catch {}
    }
    abortRef.current?.abort();
    setRunning(false);
    setRunningStepId(null);
    stopTimer();
    addLog("warning", "Stopped by user");
    // Mark any running step as failed in both stepStates and stepRuns
    setStepStates((prev) => prev.map((s) => s.status === "running" ? { ...s, status: "failed" } : s));
    setStepRuns((prev) => {
      const updated = { ...prev };
      for (const key of Object.keys(updated)) {
        updated[key] = updated[key].map((r) => r.status === "running" ? { ...r, status: "failed" } : r);
      }
      return updated;
    });
    activeRunIdRef.current = null;
    // Refresh all data from DB now that stop has completed
    loadAllStepRuns();
    loadStepSelections();
    if (selectedEpisode) fetch(`/api/admin/generation-runs?episode_id=${selectedEpisode}`).then((r) => r.json()).then((d) => setPreviousRuns(d.runs || []));
  }

  // Preview file content
  function getSelectedRunOutputDir(stepId: string): string | null {
    const selectedRunId = stepSelections[stepId];
    if (!selectedRunId) return null;
    const runs = stepRuns[stepId] || [];
    const run = runs.find((r) => r.run_id === selectedRunId);
    return run?.output_dir || null;
  }

  async function previewFile(stepId: string, fileName: string) {
    if (!selectedStory || !selectedEpisode) return;
    const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
    if (!epObj) return;
    setPreviewLoading(true);
    setPreviewContent(null);
    const outputDir = getSelectedRunOutputDir(stepId);
    const runTsParam = outputDir ? `&run_ts=${outputDir}` : "";
    try {
      const res = await fetch(`/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epObj.episode_number}&step=${stepId}&file=${encodeURIComponent(fileName)}${runTsParam}`);
      if (!res.ok) { setPreviewContent("Error loading file"); return; }
      const ct = res.headers.get("Content-Type") || "";
      if (ct.startsWith("text/") || ct.includes("yaml") || ct.includes("json")) {
        setPreviewContent(await res.text());
      } else {
        setPreviewContent(`[Binary file: ${fileName} (${ct})]`);
      }
    } catch {
      setPreviewContent("Error loading file");
    } finally {
      setPreviewLoading(false);
    }
  }

  function downloadFile(stepId: string, fileName: string) {
    if (!selectedStory || !selectedEpisode) return;
    const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
    if (!epObj) return;
    const outputDir = getSelectedRunOutputDir(stepId);
    const runTsParam = outputDir ? `&run_ts=${outputDir}` : "";
    const url = `/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epObj.episode_number}&step=${stepId}&file=${encodeURIComponent(fileName)}${runTsParam}`;
    const a = document.createElement("a"); a.href = url; a.download = fileName; a.click();
  }

  // --- Clip Review Functions ---
  async function loadClipReview() {
    if (!selectedStory || !selectedEpisode) return;
    const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
    if (!epObj) return;
    const outputDir = getSelectedRunOutputDir("generate_clips");
    setClipReviewLoading(true);
    try {
      const params = new URLSearchParams({ story_id: selectedStory, episode: String(epObj.episode_number) });
      if (outputDir) params.set("run_ts", outputDir);
      const res = await fetch(`/api/admin/clip-review?${params}`);
      const data = await res.json();
      setClipReview(data);
    } catch {
      setClipReview(null);
    } finally {
      setClipReviewLoading(false);
    }
  }

  async function runClipReview() {
    if (!selectedStory || !selectedEpisode) return;
    const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
    if (!epObj) return;
    const outputDir = getSelectedRunOutputDir("generate_clips");
    setClipReviewLoading(true);
    setClipReview(null);
    try {
      const res = await fetch("/api/admin/clip-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "run_review",
          story_id: parseInt(selectedStory),
          episode: epObj.episode_number,
          run_ts: outputDir,
        }),
      });
      const data = await res.json();
      setClipReview(data);
    } catch {
      addLog("error", "Failed to run clip review");
    } finally {
      setClipReviewLoading(false);
    }
  }

  async function regenerateClip(clipName: string) {
    if (!selectedStory || !selectedEpisode) return;
    const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
    if (!epObj) return;
    const outputDir = getSelectedRunOutputDir("generate_clips");
    const prompt = regenPrompts[clipName] || undefined;
    setRegenLoadingClip(clipName);
    try {
      const res = await fetch("/api/admin/clip-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "regenerate",
          story_id: parseInt(selectedStory),
          episode: epObj.episode_number,
          run_ts: outputDir,
          clip_name: clipName,
          improvement_prompt: prompt,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setRegenResults((prev) => ({ ...prev, [clipName]: { regen_clip: data.regen_clip } }));
        addLog("success", `Regenerated: ${clipName}`);
      } else {
        addLog("error", `Regeneration failed: ${data.stderr?.slice(0, 200) || "Unknown error"}`);
      }
    } catch {
      addLog("error", `Failed to regenerate ${clipName}`);
    } finally {
      setRegenLoadingClip(null);
    }
  }

  async function acceptRegen(clipName: string) {
    if (!selectedStory || !selectedEpisode) return;
    const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
    if (!epObj) return;
    const outputDir = getSelectedRunOutputDir("generate_clips");
    try {
      await fetch("/api/admin/clip-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "accept_regen",
          story_id: parseInt(selectedStory),
          episode: epObj.episode_number,
          run_ts: outputDir,
          clip_name: clipName,
        }),
      });
      setRegenResults((prev) => { const next = { ...prev }; delete next[clipName]; return next; });
      addLog("success", `Accepted regenerated clip: ${clipName}`);
      // Refresh artifacts to show the updated clip
      loadArtifacts("generate_clips", outputDir || undefined);
    } catch {
      addLog("error", `Failed to accept regenerated clip: ${clipName}`);
    }
  }

  async function discardRegen(clipName: string) {
    if (!selectedStory || !selectedEpisode) return;
    const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
    if (!epObj) return;
    const outputDir = getSelectedRunOutputDir("generate_clips");
    try {
      await fetch("/api/admin/clip-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "discard_regen",
          story_id: parseInt(selectedStory),
          episode: epObj.episode_number,
          run_ts: outputDir,
          clip_name: clipName,
        }),
      });
      setRegenResults((prev) => { const next = { ...prev }; delete next[clipName]; return next; });
      addLog("info", `Discarded regenerated clip: ${clipName}`);
    } catch {
      addLog("error", `Failed to discard regenerated clip: ${clipName}`);
    }
  }

  // Load clip review when quality step is selected and clips run is available
  useEffect(() => {
    if (selectedStep === "validate_quality" && selectedStory && selectedEpisode) {
      loadClipReview();
    } else {
      setClipReview(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStep, selectedStory, selectedEpisode, stepSelections]);

  // Steps that can be skipped
  const SKIPPABLE_STEPS = ["validate_quality", "add_audio"];

  // Is a step runnable?
  function canRunStep(stepId: string): boolean {
    if (running) return false;
    const idx = PIPELINE_STEPS.findIndex((s) => s.id === stepId);
    // First step is always runnable
    if (idx === 0) return true;
    // Previous step must have a successful run or be skipped
    const prevId = PIPELINE_STEPS[idx - 1]?.id;
    const prevRuns = stepRuns[prevId] || [];
    const prevHasSuccess = prevRuns.some((r) => r.status === "done");
    return prevHasSuccess || stepIsSkipped(prevId);
  }

  // Does a step have at least one successful run?
  function stepHasSuccess(stepId: string): boolean {
    const runs = stepRuns[stepId] || [];
    return runs.some((r) => r.status === "done");
  }

  // Is the step marked as skipped?
  function stepIsSkipped(stepId: string): boolean {
    return skippedSteps.includes(stepId);
  }

  function getEffectiveStatus(stepId: string): StepStatus {
    const state = stepStates.find((s) => s.id === stepId);
    if (state?.status === "running") return "running";
    // Check if any run succeeded for this step
    if (stepHasSuccess(stepId)) return "done";
    // Skipped counts as done for pipeline flow
    if (stepIsSkipped(stepId)) return "done";
    // Check if any run failed (but none succeeded)
    const runs = stepRuns[stepId] || [];
    if (runs.some((r) => r.status === "failed") && !stepHasSuccess(stepId)) return "failed";
    const idx = PIPELINE_STEPS.findIndex((s) => s.id === stepId);
    if (idx === 0) return "pending";
    // Previous step must have a successful run or be skipped
    const prevId = PIPELINE_STEPS[idx - 1]?.id;
    if (stepHasSuccess(prevId) || stepIsSkipped(prevId)) return "pending";
    return "locked";
  }

  // Select a run for a step
  async function selectRun(stepId: string, runId: number) {
    if (!selectedStory || !selectedEpisode) return;
    await fetch("/api/admin/step-runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ story_id: parseInt(selectedStory), episode_id: parseInt(selectedEpisode), step_id: stepId, run_id: runId }),
    });
    setStepSelections((prev) => ({ ...prev, [stepId]: runId }));
    setStepRuns((prev) => ({
      ...prev,
      [stepId]: (prev[stepId] || []).map((r) => ({ ...r, selected: r.run_id === runId })),
    }));
    // Immediately load artifacts for this run
    const runs = stepRuns[stepId] || [];
    const run = runs.find((r) => r.run_id === runId);
    if (run?.output_dir) {
      loadArtifacts(stepId, run.output_dir);
    }
    // Clear preview since it may be stale
    setPreviewContent(null);
  }

  const totalSteps = PIPELINE_STEPS.length;
  const completedSteps = PIPELINE_STEPS.filter((s) => getEffectiveStatus(s.id) === "done").length;



  return (
    <div className="max-w-7xl mx-auto px-4">
      {/* Header */}
      <div className="text-center mb-10 pt-6">
        <h1 className="text-4xl font-black tracking-tight">
          <span className="glow-text">{t(locale, "admin_gen_title")}</span>
        </h1>
        <p className="text-white/30 text-sm mt-2">{t(locale, "admin_gen_subtitle")}</p>
        {running && (
          <div className="mt-4 inline-flex items-center gap-3 px-5 py-2.5 rounded-full bg-violet-500/[0.06] border border-violet-500/20">
            <span className="relative flex h-2.5 w-2.5"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-60" /><span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-violet-400" /></span>
            <span className="text-sm font-mono text-violet-300/80 tabular-nums">{fmtTime(elapsedMs)}</span>
            <span className="text-xs text-white/30">{completedSteps}/{totalSteps}</span>
            <button onClick={cancelGeneration} className="ml-2 px-3 py-1 text-xs border border-rose-500/30 text-rose-400 rounded-lg hover:bg-rose-500/10">{t(locale, "admin_gen_cancel")}</button>
          </div>
        )}
      </div>

      {/* Config */}
      <div className="glass-card rounded-2xl p-6 mb-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-white/30 font-bold block mb-2">{t(locale, "admin_gen_story")}</span>
            <select value={selectedStory} onChange={(e) => { setSelectedStory(e.target.value); setSelectedEpisode(""); setArtifacts({}); setSelectedStep(null); setStepRuns({}); setStepSelections({}); }}
              className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.07] text-sm text-white/90 focus:outline-none focus:ring-2 focus:ring-violet-500/30">
              <option value="" className="bg-[#0c0820]">{t(locale, "admin_gen_select_story")}</option>
              {stories.map((s) => <option key={s.id} value={String(s.id)} className="bg-[#0c0820]">{s.title_zh ? `${s.title_zh} (${s.title})` : s.title}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-white/30 font-bold block mb-2">{t(locale, "admin_gen_episode")}</span>
            <select value={selectedEpisode} onChange={(e) => { setSelectedEpisode(e.target.value); setSelectedStep(null); setPreviewContent(null); }} disabled={!selectedStory}
              className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.07] text-sm text-white/90 focus:outline-none focus:ring-2 focus:ring-violet-500/30 disabled:opacity-20">
              <option value="" className="bg-[#0c0820]">{selectedStory ? t(locale, "admin_gen_select_episode") : t(locale, "admin_gen_select_story_first")}</option>
              {filteredEpisodes.map((ep) => <option key={ep.id} value={String(ep.id)} className="bg-[#0c0820]">{t(locale, "admin_gen_ep_prefix")} {ep.episode_number} - {ep.title_zh ? `${ep.title_zh} (${ep.title})` : ep.title}</option>)}
            </select>
          </label>
          <div className="flex items-end">
            <button onClick={() => runStep()} disabled={!selectedEpisode || running}
              className="btn-primary w-full text-sm disabled:opacity-15 disabled:cursor-not-allowed">
              {t(locale, "admin_gen_run_full")}
            </button>
          </div>
        </div>

        {/* Model Selection */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4 pt-4 border-t border-white/[0.05]">
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-white/30 font-bold block mb-2">{t(locale, "admin_gen_llm_model")}</span>
            <select value={selectedLlmModel} onChange={(e) => setSelectedLlmModel(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.07] text-sm text-white/90 focus:outline-none focus:ring-2 focus:ring-violet-500/30">
              <option value="" className="bg-[#0c0820]">{t(locale, "admin_gen_default_config")}</option>
              {llmModels.map((m) => <option key={m.id} value={m.id} disabled={!m.available} className="bg-[#0c0820]">{m.label}{!m.available ? (m.provider === "huggingface" ? " (no HF token)" : " (no API key)") : ""}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-white/30 font-bold block mb-2">{t(locale, "admin_gen_video_model")}</span>
            <select value={selectedVideoModel} onChange={(e) => setSelectedVideoModel(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.07] text-sm text-white/90 focus:outline-none focus:ring-2 focus:ring-violet-500/30">
              <option value="" className="bg-[#0c0820]">{t(locale, "admin_gen_default_config")}</option>
              {videoModels.map((m) => <option key={m.id} value={m.id} disabled={!m.available} className="bg-[#0c0820]">{m.label}{!m.available ? (m.provider === "huggingface" ? " (no HF token)" : " (no API key)") : ""}</option>)}
            </select>
          </label>
          <div className="block">
            <span className="text-xs uppercase tracking-wider text-white/30 font-bold block mb-2">{t(locale, "admin_gen_video_exec")}</span>
            <div className="flex gap-3 mt-1">
              <label className={`flex-1 flex items-center gap-2 px-4 py-3 rounded-xl border cursor-pointer transition-all ${!videoExecLocal ? 'bg-violet-500/10 border-violet-500/40 text-violet-300' : 'bg-white/[0.04] border-white/[0.07] text-white/60 hover:border-white/20'}`}>
                <input type="radio" name="videoExec" checked={!videoExecLocal} onChange={() => setVideoExecLocal(false)} className="accent-violet-500" />
                <div>
                  <div className="text-sm font-medium">{t(locale, "admin_gen_exec_cloud")}</div>
                  <div className="text-[10px] opacity-60">{t(locale, "admin_gen_exec_cloud_desc")}</div>
                </div>
              </label>
              <label className={`flex-1 flex items-center gap-2 px-4 py-3 rounded-xl border cursor-pointer transition-all ${videoExecLocal ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300' : 'bg-white/[0.04] border-white/[0.07] text-white/60 hover:border-white/20'}`}>
                <input type="radio" name="videoExec" checked={videoExecLocal} onChange={() => setVideoExecLocal(true)} className="accent-emerald-500" />
                <div>
                  <div className="text-sm font-medium">{t(locale, "admin_gen_exec_local")}</div>
                  <div className="text-[10px] opacity-60">{t(locale, "admin_gen_exec_local_desc")}</div>
                </div>
              </label>
            </div>
          </div>
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-white/30 font-bold block mb-2">{t(locale, "admin_gen_aspect_ratio")}</span>
            <select value={videoAspectRatio} onChange={(e) => setVideoAspectRatio(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.07] text-sm text-white/90 focus:outline-none focus:ring-2 focus:ring-violet-500/30">
              <option value="9:16" className="bg-[#0c0820]">{t(locale, "admin_gen_ratio_vertical")}</option>
              <option value="16:9" className="bg-[#0c0820]">{t(locale, "admin_gen_ratio_horizontal")}</option>
              <option value="1:1" className="bg-[#0c0820]">{t(locale, "admin_gen_ratio_square")}</option>
              <option value="4:3" className="bg-[#0c0820]">{t(locale, "admin_gen_ratio_classic")}</option>
              <option value="3:4" className="bg-[#0c0820]">{t(locale, "admin_gen_ratio_portrait")}</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-white/30 font-bold block mb-2">{t(locale, "admin_gen_visual_style")}</span>
            <select value={videoStyle} onChange={(e) => setVideoStyle(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.07] text-sm text-white/90 focus:outline-none focus:ring-2 focus:ring-violet-500/30">
              <option value="chinese-cartoon" className="bg-[#0c0820]">{t(locale, "admin_gen_style_chinese_cartoon")}</option>
              <option value="anime" className="bg-[#0c0820]">{t(locale, "admin_gen_style_anime")}</option>
              <option value="pixar-3d" className="bg-[#0c0820]">{t(locale, "admin_gen_style_pixar")}</option>
              <option value="watercolor" className="bg-[#0c0820]">{t(locale, "admin_gen_style_watercolor")}</option>
              <option value="comic-book" className="bg-[#0c0820]">{t(locale, "admin_gen_style_comic")}</option>
              <option value="stop-motion" className="bg-[#0c0820]">{t(locale, "admin_gen_style_stop_motion")}</option>
              <option value="pixel-art" className="bg-[#0c0820]">{t(locale, "admin_gen_style_pixel")}</option>
              <option value="ink-wash" className="bg-[#0c0820]">{t(locale, "admin_gen_style_ink_wash")}</option>
              <option value="flat-vector" className="bg-[#0c0820]">{t(locale, "admin_gen_style_flat_vector")}</option>
              <option value="realistic-cgi" className="bg-[#0c0820]">{t(locale, "admin_gen_style_realistic")}</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-white/30 font-bold block mb-2">Episode Length</span>
            <select value={videoLength} onChange={(e) => setVideoLength(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.07] text-sm text-white/90 focus:outline-none focus:ring-2 focus:ring-violet-500/30">
              <option value="30" className="bg-[#0c0820]">30 seconds</option>
              <option value="60" className="bg-[#0c0820]">60 seconds (default)</option>
              <option value="90" className="bg-[#0c0820]">90 seconds</option>
              <option value="120" className="bg-[#0c0820]">120 seconds</option>
              <option value="150" className="bg-[#0c0820]">150 seconds</option>
              <option value="180" className="bg-[#0c0820]">180 seconds</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-white/30 font-bold block mb-2">Video Quality</span>
            <select value={videoQuality} onChange={(e) => setVideoQuality(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.07] text-sm text-white/90 focus:outline-none focus:ring-2 focus:ring-violet-500/30">
              <option value="low" className="bg-[#0c0820]">Low (fast)</option>
              <option value="medium" className="bg-[#0c0820]">Medium</option>
              <option value="high" className="bg-[#0c0820]">High (default)</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-white/30 font-bold block mb-2">{t(locale, "admin_gen_audio_model")}</span>
            <select value={selectedAudioModel} onChange={(e) => setSelectedAudioModel(e.target.value)}
              className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-white/[0.07] text-sm text-white/90 focus:outline-none focus:ring-2 focus:ring-violet-500/30">
              <option value="" className="bg-[#0c0820]">{t(locale, "admin_gen_default_config")}</option>
              {audioModels.map((m) => <option key={m.id} value={m.id} disabled={!m.available} className="bg-[#0c0820]">{m.label}{!m.available ? (m.provider === "huggingface" ? " (no HF token)" : " (no API key)") : ""}</option>)}
            </select>
          </label>
        </div>
      </div>

      {/* Pipeline Steps - Always visible */}
      {selectedEpisode && (
        <div className="mb-8">
          {/* Horizontal step strip */}
          <div className="flex items-stretch gap-0 overflow-x-auto pt-4 pl-3 pb-2">
            {PIPELINE_STEPS.map((step, idx) => {
              const status = getEffectiveStatus(step.id);
              const isSelected = selectedStep === step.id;
              const isRunning = runningStepId === step.id || stepStates.find((s) => s.id === step.id)?.status === "running";
              const locked = status === "locked";
              const skipped = stepIsSkipped(step.id);

              return (
                <div key={step.id} className="flex items-stretch">
                  {/* Step card */}
                  <button
                    onClick={() => !locked && setSelectedStep(isSelected ? null : step.id)}
                    disabled={locked}
                    className={`relative flex flex-col items-center justify-center px-5 py-4 rounded-xl border transition-all duration-300 min-w-[110px] ${
                      locked ? "opacity-30 cursor-not-allowed border-white/[0.03] bg-transparent" :
                      isSelected ? "border-violet-500/40 bg-violet-500/[0.06] scale-105 shadow-lg shadow-violet-500/10" :
                      skipped ? "border-amber-500/30 bg-amber-500/[0.03] hover:bg-amber-500/[0.06] cursor-pointer" :
                      status === "done" ? "border-emerald-500/30 bg-emerald-500/[0.03] hover:bg-emerald-500/[0.06] cursor-pointer" :
                      status === "failed" ? "border-rose-500/30 bg-rose-500/[0.03] hover:bg-rose-500/[0.06] cursor-pointer" :
                      isRunning ? "border-violet-500/40 bg-violet-500/[0.05]" :
                      "border-white/[0.06] bg-white/[0.01] hover:bg-white/[0.03] cursor-pointer"
                    }`}
                  >
                    {/* Step number */}
                    <div className={`absolute -top-2 -left-1 w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-black ${
                      skipped ? "bg-amber-500/20 text-amber-400" :
                      status === "done" ? "bg-emerald-500/20 text-emerald-400" :
                      status === "failed" ? "bg-rose-500/20 text-rose-400" :
                      isRunning ? "bg-violet-500/20 text-violet-400" :
                      "bg-white/[0.05] text-white/20"
                    }`}>{idx + 1}</div>

                    {/* Icon */}
                    <div className={`mb-2 ${
                      skipped ? "text-amber-400" :
                      status === "done" ? "text-emerald-400" :
                      status === "failed" ? "text-rose-400" :
                      isRunning ? "text-violet-400 animate-pulse" :
                      locked ? "text-white/10" : "text-white/25"
                    }`}>
                      {skipped ? (
                        <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3 8l4 4-4 4m7-8l4 4-4 4m7-8l4 4-4 4" /></svg>
                      ) : status === "done" ? (
                        <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
                      ) : status === "failed" ? (
                        <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                      ) : isRunning ? (
                        <svg className="w-8 h-8 animate-spin" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" strokeDasharray="28 62" strokeLinecap="round" /></svg>
                      ) : (
                        <StepIcon stepId={step.id} className="w-8 h-8" />
                      )}
                    </div>

                    {/* Label */}
                    <span className={`text-[11px] font-bold text-center leading-tight ${
                      skipped ? "text-amber-300/80" :
                      status === "done" ? "text-emerald-300/80" :
                      status === "failed" ? "text-rose-300/80" :
                      isRunning ? "text-violet-300" :
                      locked ? "text-white/15" : "text-white/40"
                    }`}>{stepLabel(locale, step.id)}</span>

                    {/* Stop button for running step */}
                    {isRunning && (
                      <button
                        onClick={(e) => { e.stopPropagation(); cancelGeneration(); }}
                        className="mt-2 px-2 py-0.5 text-[9px] font-bold border border-rose-500/40 text-rose-400 rounded hover:bg-rose-500/20 transition-all z-10"
                      >
                        {t(locale, "admin_gen_stop")}
                      </button>
                    )}

                    {/* Running ring */}
                    {isRunning && <div className="absolute inset-0 rounded-xl border border-violet-500/30 animate-ping opacity-20 pointer-events-none" />}
                  </button>

                  {/* Arrow between steps */}
                  {idx < PIPELINE_STEPS.length - 1 && (
                    <div className="flex items-center px-1">
                      <svg width="20" height="12" viewBox="0 0 20 12" className={skipped ? "text-amber-400/30" : status === "done" ? "text-emerald-400/30" : "text-white/8"}>
                        <path d="M2 6h14m0 0l-3-3m3 3l-3 3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Progress bar */}
          <div className="mt-4 h-1 bg-white/[0.03] rounded-full overflow-hidden">
            <div className="h-full rounded-full transition-[width] duration-700 ease-out bg-gradient-to-r from-violet-500 to-emerald-500"
              style={{ width: `${Math.round((completedSteps / totalSteps) * 100)}%` }} />
          </div>
        </div>
      )}

      {/* Selected Step Detail Panel */}
      {selectedStep && selectedEpisode && (
        <div className="glass-card rounded-2xl overflow-hidden mb-8 animate-fade-in-up">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.05]">
            <div className="flex items-center gap-3">
              <StepIcon stepId={selectedStep} className="w-6 h-6 text-white/30" />
              <span className="text-base font-bold text-white/70">{stepLabel(locale, selectedStep)}</span>
              <span className="text-xs text-white/20">{stepDesc(locale, selectedStep)}</span>
            </div>
            <div className="flex items-center gap-2">
              {canRunStep(selectedStep) && !running && (
                <button onClick={() => runStep(selectedStep)} disabled={running}
                  className="px-4 py-2 text-xs font-bold rounded-lg bg-violet-500/20 text-violet-300 border border-violet-500/30 hover:bg-violet-500/30 disabled:opacity-30 transition-all">
                  {stepHasSuccess(selectedStep) ? t(locale, "admin_gen_rerun") : t(locale, "admin_gen_run_step")}
                </button>
              )}
              {canRunStep(selectedStep) && !running && SKIPPABLE_STEPS.includes(selectedStep) && (
                <button onClick={() => handleSkipStep(selectedStep)} disabled={running}
                  className={`px-4 py-2 text-xs font-bold rounded-lg border disabled:opacity-30 transition-all ${
                    stepIsSkipped(selectedStep)
                      ? "bg-amber-500/20 text-amber-300 border-amber-500/30 hover:bg-amber-500/30"
                      : "bg-zinc-500/20 text-zinc-300 border-zinc-500/30 hover:bg-zinc-500/30"
                  }`}>
                  {stepIsSkipped(selectedStep) ? t(locale, "admin_gen_unskip") : t(locale, "admin_gen_skip")}
                </button>
              )}
              {running && runningStepId === selectedStep && (
                <button onClick={cancelGeneration}
                  className="px-4 py-2 text-xs font-bold rounded-lg bg-rose-500/20 text-rose-300 border border-rose-500/30 hover:bg-rose-500/30 transition-all">
                  {t(locale, "admin_gen_stop")}
                </button>
              )}
              {!canRunStep(selectedStep) && !running && (
                <span className="text-[10px] text-amber-400/60 px-3 py-1 border border-amber-500/20 rounded-lg bg-amber-500/[0.04]">
                  {t(locale, "admin_gen_prev_step_required")}
                </span>
              )}
              <button onClick={() => { setSelectedStep(null); setPreviewContent(null); }} className="text-white/20 hover:text-white/50 p-2 rounded-lg hover:bg-white/[0.05]">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
          </div>

          {/* Content area */}
          <div className="p-6">
            {/* Step Runs list */}
            {(stepRuns[selectedStep] && stepRuns[selectedStep].length > 0) ? (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold">{t(locale, "admin_gen_step_runs")}</h3>
                  <button
                    onClick={async () => {
                      if (!window.confirm(t(locale, "admin_gen_confirm_clear_step"))) return;
                      await fetch(`/api/admin/step-runs?story_id=${selectedStory}&episode_id=${selectedEpisode}&step_id=${selectedStep}`, { method: "DELETE" });
                      setStepRuns((prev) => ({ ...prev, [selectedStep]: [] }));
                      setStepSelections((prev) => { const next = { ...prev }; delete next[selectedStep]; return next; });
                      loadAllStepRuns();
                      // Refresh history list
                      if (selectedEpisode) fetch(`/api/admin/generation-runs?episode_id=${selectedEpisode}`).then((r) => r.json()).then((d) => setPreviousRuns(d.runs || []));
                    }}
                    className="text-[10px] text-white/20 hover:text-rose-400 border border-white/[0.06] hover:border-rose-500/30 px-2 py-0.5 rounded transition-colors"
                  >
                    {t(locale, "admin_gen_clear_all")}
                  </button>
                </div>
                <div className="space-y-2 mb-6">
                  {stepRuns[selectedStep].map((run, idx) => {
                    const isSelected = stepSelections[selectedStep] === run.run_id;
                    // Treat stale "running" status as failed when pipeline isn't active
                    const effectiveRunStatus = (run.status === "running" && !running) ? "failed" : run.status;
                    const isSuccess = effectiveRunStatus === "done";
                    const isFailed = effectiveRunStatus === "failed";
                    const isRunning = effectiveRunStatus === "running";
                    return (
                      <div key={run.run_id}
                        className={`flex flex-wrap items-center gap-2 sm:gap-3 px-4 py-3 rounded-xl border transition-all ${
                          isSelected ? "border-violet-500/40 bg-violet-500/[0.06]" :
                          isSuccess ? "border-emerald-500/20 bg-emerald-500/[0.02]" :
                          isFailed ? "border-rose-500/20 bg-rose-500/[0.02]" :
                          "border-white/[0.06] bg-white/[0.01]"
                        }`}
                      >
                        {/* Radio selection - only for successful runs */}
                        <button
                          onClick={() => isSuccess && selectRun(selectedStep, run.run_id)}
                          disabled={!isSuccess}
                          className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 transition-all ${
                            isSelected ? "border-violet-400 bg-violet-500/30" :
                            isSuccess ? "border-emerald-500/40 hover:border-violet-400 cursor-pointer" :
                            "border-white/10 cursor-not-allowed"
                          }`}
                        >
                          {isSelected && <div className="w-2.5 h-2.5 rounded-full bg-violet-400" />}
                        </button>

                        {/* Status badge */}
                        <div className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          isSuccess ? "bg-emerald-500/15 text-emerald-400" :
                          isFailed ? "bg-rose-500/15 text-rose-400" :
                          isRunning ? "bg-violet-500/15 text-violet-400" :
                          "bg-white/5 text-white/30"
                        }`}>
                          {isSuccess ? t(locale, "admin_gen_run_success") :
                           isFailed ? t(locale, "admin_gen_run_failed") :
                           isRunning ? t(locale, "admin_gen_run_running") : run.status}
                        </div>

                        {/* Run info */}
                        <div className="flex-1 min-w-0">
                          <span className="text-sm text-white/50 font-mono">
                            {t(locale, "admin_gen_run_label")} #{stepRuns[selectedStep].length - idx} - {stepLabel(locale, selectedStep)}
                          </span>
                          {run.started_at && (
                            <span className="text-[10px] text-white/20 ml-3">
                              {new Date(run.started_at).toLocaleString()}
                            </span>
                          )}
                        </div>

                        {/* Duration */}
                        {run.duration_ms && (
                          <span className="text-[10px] text-white/20 font-mono shrink-0">{fmtDur(run.duration_ms)}</span>
                        )}

                        {/* Selected badge */}
                        {isSelected && (
                          <span className="text-[9px] font-bold text-violet-400 bg-violet-500/15 px-2 py-0.5 rounded shrink-0 ml-auto">
                            {t(locale, "admin_gen_selected")}
                          </span>
                        )}

                        {/* Select button for non-selected successful runs */}
                        {isSuccess && !isSelected && (
                          <button
                            onClick={() => selectRun(selectedStep, run.run_id)}
                            className="text-[10px] font-bold text-white/30 hover:text-violet-300 px-2 py-1 rounded border border-white/[0.06] hover:border-violet-500/30 transition-all shrink-0 ml-auto"
                          >
                            {t(locale, "admin_gen_select")}
                          </button>
                        )}

                        {/* Delete button */}
                        {!(isRunning && running) && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              if (!window.confirm(t(locale, "admin_gen_confirm_delete_run"))) return;
                              fetch(`/api/admin/step-runs?story_id=${selectedStory}&episode_id=${selectedEpisode}&step_id=${selectedStep}&run_id=${run.run_id}`, { method: "DELETE" }).then(() => {
                                loadStepRuns(selectedStep);
                                loadStepSelections();
                                // Refresh history list
                                if (selectedEpisode) fetch(`/api/admin/generation-runs?episode_id=${selectedEpisode}`).then((r) => r.json()).then((d) => setPreviousRuns(d.runs || []));
                              });
                            }}
                            className="text-white/30 hover:text-rose-400 p-1.5 rounded hover:bg-rose-500/10 transition-all shrink-0 border border-transparent hover:border-rose-500/30"
                            title="Delete this run"
                          >
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" /></svg>
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Artifacts for selected run */}
                {artifacts[selectedStep]?.available && (
                  <div>
                    {/* Character avatar gallery for design_characters step */}
                    {selectedStep === "design_characters" && (() => {
                      const avatarFiles = artifacts[selectedStep].files.filter((f) =>
                        f.name.startsWith("avatars/") && f.type === "png"
                      );
                      if (avatarFiles.length === 0) return null;
                      const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
                      const epNum = epObj?.episode_number;
                      const avatarOutputDir = getSelectedRunOutputDir(selectedStep);
                      const avatarRunTsParam = avatarOutputDir ? `&run_ts=${avatarOutputDir}` : "";

                      // Determine which slugs are from previous episodes (check characters.yaml in run output)
                      // For simplicity: all avatars in current run are regenerable
                      const cacheBuster = (slug: string) => regenAvatarState[slug] === "done" ? `&_t=${Date.now()}` : "";

                      async function handleRegenAvatar(slug: string) {
                        if (!epNum || !selectedStory) return;
                        setRegenAvatarState((prev) => ({ ...prev, [slug]: "loading" }));
                        try {
                          const payload: Record<string, unknown> = { story_id: selectedStory, episode: epNum, slug };
                          const editPrompt = avatarEditPrompt[slug]?.trim();
                          if (editPrompt) payload.prompt = editPrompt;
                          const res = await fetch("/api/admin/regenerate-avatar", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify(payload),
                          });
                          if (res.ok) {
                            setRegenAvatarState((prev) => ({ ...prev, [slug]: "done" }));
                            if (editPrompt) setAvatarEditPrompt((prev) => ({ ...prev, [slug]: "" }));
                            // Refresh artifacts to update file sizes
                            loadArtifacts();
                          } else {
                            setRegenAvatarState((prev) => ({ ...prev, [slug]: "error" }));
                          }
                        } catch {
                          setRegenAvatarState((prev) => ({ ...prev, [slug]: "error" }));
                        }
                      }

                      return (
                        <div className="mb-6">
                          <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold mb-3">{t(locale, "admin_gen_character_avatars")}</h3>
                          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                            {avatarFiles.map((file) => {
                              const slug = file.name.replace("avatars/", "").replace(".png", "");
                              const url = `/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epNum}&step=${selectedStep}&file=${encodeURIComponent(file.name)}${avatarRunTsParam}${cacheBuster(slug)}`;
                              const charName = slug.replace(/^char_[a-z0-9]*_[a-f0-9]+$/, slug);
                              const regenState = regenAvatarState[slug];
                              const isLoading = regenState === "loading";
                              return (
                                <div key={file.name} className="rounded-xl border border-white/[0.06] bg-black/30 overflow-hidden">
                                  <div className="aspect-[3/4] bg-white/[0.02] flex items-center justify-center p-2 relative">
                                    {/* eslint-disable-next-line @next/next/no-img-element */}
                                    <img src={url} alt={charName} className={`max-w-full max-h-full object-contain rounded ${isLoading ? "opacity-30 animate-pulse" : ""}`} />
                                    {isLoading && (
                                      <div className="absolute inset-0 flex items-center justify-center">
                                        <svg className="w-8 h-8 text-violet-400 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                                      </div>
                                    )}
                                  </div>
                                  <div className="px-3 py-2 border-t border-white/[0.04] flex flex-col gap-1">
                                    <div className="flex items-center gap-2">
                                      <span className="text-[11px] text-white/50 font-mono truncate flex-1">{file.name.replace("avatars/", "")}</span>
                                      <span className="text-[10px] text-white/20 shrink-0">{fmtSize(file.size)}</span>
                                      <button
                                        onClick={() => handleRegenAvatar(slug)}
                                        disabled={isLoading}
                                        className={`shrink-0 p-1 rounded transition-all border border-transparent ${
                                          regenState === "error"
                                            ? "text-rose-400 hover:bg-rose-500/10 hover:border-rose-500/30"
                                            : regenState === "done"
                                              ? "text-emerald-400 hover:bg-emerald-500/10 hover:border-emerald-500/30"
                                              : "text-white/30 hover:text-amber-300 hover:bg-amber-500/10 hover:border-amber-500/30"
                                        }`}
                                        title={t(locale, "admin_gen_regenerate_avatar")}
                                      >
                                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" /></svg>
                                      </button>
                                    </div>
                                    <input
                                      type="text"
                                      placeholder="Edit prompt (optional)"
                                      value={avatarEditPrompt[slug] || ""}
                                      onChange={(e) => setAvatarEditPrompt((prev) => ({ ...prev, [slug]: e.target.value }))}
                                      onKeyDown={(e) => { if (e.key === "Enter" && !isLoading) handleRegenAvatar(slug); }}
                                      disabled={isLoading}
                                      className="w-full text-[11px] bg-white/[0.04] border border-white/[0.08] rounded px-2 py-1 text-white/70 placeholder:text-white/20 focus:outline-none focus:border-violet-500/40 disabled:opacity-40"
                                    />
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })()}

                    {/* Gallery and poster images for publish step */}
                    {selectedStep === "publish" && (() => {
                      const galleryFiles = artifacts[selectedStep].files.filter((f) =>
                        f.name.startsWith("gallery/") && ["jpg", "jpeg", "png", "webp"].includes(f.type)
                      );
                      const posterFiles = artifacts[selectedStep].files.filter((f) =>
                        f.name.startsWith("poster/") && ["jpg", "jpeg", "png", "webp"].includes(f.type)
                      );
                      const storyPosterFiles = artifacts[selectedStep].files.filter((f) =>
                        f.name.startsWith("story_posters/") && ["jpg", "jpeg", "png", "webp"].includes(f.type)
                      );
                      if (galleryFiles.length === 0 && posterFiles.length === 0 && storyPosterFiles.length === 0) return null;
                      const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
                      const epNum = epObj?.episode_number;
                      const publishOutputDir = getSelectedRunOutputDir(selectedStep);
                      const publishRunTsParam = publishOutputDir ? `&run_ts=${publishOutputDir}` : "";
                      return (
                        <div className="mb-6 space-y-6">
                          {/* Episode Poster */}
                          {posterFiles.length > 0 && (
                            <div>
                              <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold mb-3">Episode Poster ({posterFiles.length} variants)</h3>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                {posterFiles.map((file) => {
                                  const url = `/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epNum}&step=publish&file=${encodeURIComponent(file.name)}${publishRunTsParam}`;
                                  const isVertical = file.name.includes("vertical");
                                  return (
                                    <div key={file.name} className="rounded-xl border border-white/[0.06] bg-black/30 overflow-hidden">
                                      <div className={`${isVertical ? "aspect-[9/16]" : "aspect-video"} bg-white/[0.02] flex items-center justify-center p-2`}>
                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                        <img src={url} alt={file.name} className="max-w-full max-h-full object-contain rounded" />
                                      </div>
                                      <div className="px-3 py-2 border-t border-white/[0.04] flex items-center justify-between">
                                        <span className="text-[11px] text-white/40 font-mono truncate">{file.name.replace("poster/", "")}</span>
                                        <span className="text-[10px] text-white/20">{fmtSize(file.size)}</span>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                          {/* Gallery */}
                          {galleryFiles.length > 0 && (
                            <div>
                              <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold mb-3">Gallery ({galleryFiles.length} frames)</h3>
                              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                                {galleryFiles.map((file) => {
                                  const url = `/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epNum}&step=publish&file=${encodeURIComponent(file.name)}${publishRunTsParam}`;
                                  return (
                                    <div key={file.name} className="rounded-xl border border-white/[0.06] bg-black/30 overflow-hidden">
                                      <div className="aspect-video bg-white/[0.02] flex items-center justify-center p-1">
                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                        <img src={url} alt={file.name} className="max-w-full max-h-full object-contain rounded" />
                                      </div>
                                      <div className="px-2 py-1 border-t border-white/[0.04] flex items-center justify-between">
                                        <span className="text-[10px] text-white/40 font-mono truncate">{file.name.replace("gallery/", "")}</span>
                                        <span className="text-[9px] text-white/20">{fmtSize(file.size)}</span>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                          {/* Story Posters */}
                          {storyPosterFiles.length > 0 && (
                            <div>
                              <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold mb-3">Story Posters ({storyPosterFiles.length} variants)</h3>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                                {storyPosterFiles.map((file) => {
                                  const url = `/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epNum}&step=publish&file=${encodeURIComponent(file.name)}${publishRunTsParam}`;
                                  const isVertical = file.name.includes("vertical");
                                  return (
                                    <div key={file.name} className="rounded-xl border border-white/[0.06] bg-black/30 overflow-hidden">
                                      <div className={`${isVertical ? "aspect-[9/16]" : "aspect-video"} bg-white/[0.02] flex items-center justify-center p-1`}>
                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                        <img src={url} alt={file.name} className="max-w-full max-h-full object-contain rounded" />
                                      </div>
                                      <div className="px-2 py-1 border-t border-white/[0.04] flex items-center justify-between">
                                        <span className="text-[10px] text-white/40 font-mono truncate">{file.name.replace("story_posters/", "")}</span>
                                        <span className="text-[9px] text-white/20">{fmtSize(file.size)}</span>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })()}

                    {/* Inline media players for video/audio files */}
                    {(() => {
                      const mediaFiles = artifacts[selectedStep].files.filter((f) =>
                        ["mp4", "webm", "mp3", "wav"].includes(f.type) && !f.name.includes("_segment")
                      );
                      if (mediaFiles.length === 0) return null;
                      const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
                      const epNum = epObj?.episode_number;
                      const mediaOutputDir = getSelectedRunOutputDir(selectedStep);
                      const mediaRunTsParam = mediaOutputDir ? `&run_ts=${mediaOutputDir}` : "";
                      return (
                        <div className="mb-6">
                          <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold mb-3">{t(locale, "admin_gen_media_preview")}</h3>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {mediaFiles.map((file) => {
                              const url = `/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epNum}&step=${selectedStep}&file=${encodeURIComponent(file.name)}${mediaRunTsParam}`;
                              const isVideo = file.type === "mp4" || file.type === "webm";
                              return (
                                <div key={file.name} className="rounded-xl border border-white/[0.06] bg-black/30 overflow-hidden">
                                  {isVideo ? (
                                    <video controls className="w-full max-h-64 bg-black" preload="metadata">
                                      <source src={url} type={file.type === "mp4" ? "video/mp4" : "video/webm"} />
                                    </video>
                                  ) : (
                                    <div className="p-4">
                                      <audio controls className="w-full" preload="metadata">
                                        <source src={url} type={file.type === "mp3" ? "audio/mpeg" : "audio/wav"} />
                                      </audio>
                                    </div>
                                  )}
                                  <div className="px-3 py-2 border-t border-white/[0.04] flex items-center justify-between">
                                    <span className="text-[11px] text-white/40 font-mono truncate">{file.name}</span>
                                    <span className="text-[10px] text-white/20">{fmtSize(file.size)}</span>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })()}

                    {/* File list (excluding _segment files) */}
                    <div className="mb-4">
                      <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold mb-3">{t(locale, "admin_gen_files")}</h3>
                      <div className="space-y-1.5">
                        {artifacts[selectedStep].files.filter((f) => !f.name.includes("_segment") && f.type !== "url").map((file) => (
                          <div key={file.name} className="flex items-center gap-3 px-4 py-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04] hover:border-white/[0.08] transition-colors group">
                            <div className="text-white/20">
                              {(file.type === "yaml" || file.type === "yml" || file.type === "json") ? (
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>
                              ) : (file.type === "mp4" || file.type === "webm") ? (
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M15.91 11.672a.375.375 0 010 .656l-5.603 3.113a.375.375 0 01-.557-.328V8.887c0-.286.307-.466.557-.327l5.603 3.112z" /></svg>
                              ) : (file.type === "mp3" || file.type === "wav") ? (
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z" /></svg>
                              ) : (
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>
                              )}
                            </div>
                            <span className="flex-1 text-sm text-white/60 font-mono truncate">{file.name}</span>
                            <span className="text-xs text-white/20">{fmtSize(file.size)}</span>
                            <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              {(file.type === "yaml" || file.type === "yml" || file.type === "json" || file.type === "txt") && (
                                <button onClick={() => previewFile(selectedStep, file.name)} className="px-2 py-1 text-[10px] font-bold rounded bg-white/[0.05] text-white/40 hover:text-white/70 border border-white/[0.06] hover:border-white/[0.12]">
                                  {t(locale, "admin_gen_view")}
                                </button>
                              )}
                              <button onClick={() => downloadFile(selectedStep, file.name)} className="px-2 py-1 text-[10px] font-bold rounded bg-white/[0.05] text-white/40 hover:text-white/70 border border-white/[0.06] hover:border-white/[0.12]">
                                {t(locale, "admin_gen_download")}
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Preview area */}
                    {previewLoading && <div className="text-center py-8 text-white/20 text-sm">{t(locale, "admin_gen_loading")}</div>}
                    {previewContent && (
                      <div className="mt-4">
                        <div className="flex items-center justify-between mb-2">
                          <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold">{t(locale, "admin_gen_preview")}</h3>
                          <button onClick={() => setPreviewContent(null)} className="text-xs text-white/20 hover:text-white/40">{t(locale, "admin_gen_close")}</button>
                        </div>
                        <pre className="bg-black/40 border border-white/[0.04] rounded-lg p-4 text-xs text-white/50 font-mono leading-relaxed max-h-96 overflow-auto whitespace-pre-wrap">{previewContent}</pre>
                      </div>
                    )}
                  </div>
                )}

                {/* Clip Review Panel — shown for validate_quality step (independent of artifacts) */}
                {selectedStep === "validate_quality" && (
                  <div className="mt-6">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold">{t(locale, "admin_gen_clip_review")}</h3>
                      <button
                        onClick={runClipReview}
                        disabled={clipReviewLoading || running || !stepHasSuccess("generate_clips")}
                        className="px-4 py-2 text-xs font-bold rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/30 hover:bg-amber-500/30 disabled:opacity-30 transition-all"
                      >
                        {clipReviewLoading ? t(locale, "admin_gen_analyzing") : clipReview?.available ? t(locale, "admin_gen_rerun_review") : t(locale, "admin_gen_run_quality_review")}
                      </button>
                    </div>

                    {clipReviewLoading && (
                      <div className="text-center py-12">
                        <svg className="w-8 h-8 animate-spin text-amber-400/40 mx-auto mb-3" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" strokeDasharray="28 62" strokeLinecap="round" /></svg>
                        <p className="text-sm text-white/25">{t(locale, "admin_gen_analyzing_clips")}</p>
                      </div>
                    )}

                    {!clipReviewLoading && clipReview?.available && (
                      <div>
                        {/* Summary */}
                        <div className={`flex items-center gap-3 mb-4 px-4 py-3 rounded-xl border ${clipReview.passed ? "border-emerald-500/30 bg-emerald-500/[0.04]" : "border-amber-500/30 bg-amber-500/[0.04]"}`}>
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center ${clipReview.passed ? "bg-emerald-500/20" : "bg-amber-500/20"}`}>
                            {clipReview.passed ? (
                              <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
                            ) : (
                              <svg className="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" /></svg>
                            )}
                          </div>
                          <div>
                            <span className={`text-sm font-bold ${clipReview.passed ? "text-emerald-300" : "text-amber-300"}`}>
                              {clipReview.passed ? t(locale, "admin_gen_all_passed") : `${clipReview.failed_clips} / ${clipReview.total_clips} ${t(locale, "admin_gen_clips_need_attention")}`}
                            </span>
                            {clipReview.run_ts && (
                              <span className="text-[10px] text-white/20 ml-3">{t(locale, "admin_gen_run_ts")}: {clipReview.run_ts}</span>
                            )}
                          </div>
                        </div>

                        {/* Per-clip cards */}
                        <div className="space-y-4">
                          {clipReview.clips.map((clip) => {
                            const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
                            const epNum = epObj?.episode_number;
                            const clipsOutputDir = getSelectedRunOutputDir("generate_clips");
                            const clipsRunTsParam = clipsOutputDir ? `&run_ts=${clipsOutputDir}` : "";
                            const videoUrl = `/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epNum}&step=generate_clips&file=${encodeURIComponent(clip.name)}${clipsRunTsParam}`;
                            const hasRegen = !!regenResults[clip.name];
                            const regenName = clip.name.replace(/\.mp4$/, ".regen.mp4");
                            const regenUrl = hasRegen ? `/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epNum}&step=generate_clips&file=${encodeURIComponent(regenName)}${clipsRunTsParam}&_t=${Date.now()}` : "";
                            const isRegenLoading = regenLoadingClip === clip.name;

                            return (
                              <div key={clip.name} className={`rounded-xl border overflow-hidden ${clip.passed ? "border-emerald-500/20 bg-emerald-500/[0.02]" : "border-amber-500/20 bg-amber-500/[0.02]"}`}>
                                {/* Clip header */}
                                <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.04]">
                                  <div className="flex items-center gap-2">
                                    <span className={`w-2 h-2 rounded-full ${clip.passed ? "bg-emerald-400" : "bg-amber-400"}`} />
                                    <span className="text-sm font-mono text-white/60">{clip.name}</span>
                                    {clip.metrics.duration_seconds && (
                                      <span className="text-[10px] text-white/20">{clip.metrics.duration_seconds}s</span>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-2">
                                    {clip.passed && !hasRegen && (
                                      <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/15 px-2 py-0.5 rounded">{t(locale, "admin_gen_clip_pass")}</span>
                                    )}
                                    {!clip.passed && (
                                      <span className="text-[10px] font-bold text-amber-400 bg-amber-500/15 px-2 py-0.5 rounded">{t(locale, "admin_gen_clip_needs_review")}</span>
                                    )}
                                  </div>
                                </div>

                                <div className="p-4">
                                  {/* Video preview side by side for regen comparison */}
                                  <div className={`grid gap-4 mb-4 ${hasRegen ? "grid-cols-2" : "grid-cols-1"}`}>
                                    <div>
                                      <div className="text-[10px] text-white/20 mb-1 font-bold uppercase">
                                        {hasRegen ? t(locale, "admin_gen_clip_original") : t(locale, "admin_gen_clip_preview")}
                                      </div>
                                      <video controls className="w-full max-h-48 rounded-lg bg-black" preload="metadata">
                                        <source src={videoUrl} type="video/mp4" />
                                      </video>
                                    </div>
                                    {hasRegen && (
                                      <div>
                                        <div className="text-[10px] text-violet-400/60 mb-1 font-bold uppercase">{t(locale, "admin_gen_clip_regenerated")}</div>
                                        <video controls className="w-full max-h-48 rounded-lg bg-black border border-violet-500/20" preload="metadata">
                                          <source src={regenUrl} type="video/mp4" />
                                        </video>
                                      </div>
                                    )}
                                  </div>

                                  {/* Issues */}
                                  {clip.issues.length > 0 && (
                                    <div className="mb-3">
                                      <div className="text-[10px] text-white/20 font-bold uppercase mb-1">{t(locale, "admin_gen_clip_issues")}</div>
                                      {clip.issues.map((issue, i) => (
                                        <div key={i} className="text-xs text-amber-400/70 flex gap-1.5 mb-0.5">
                                          <span className="shrink-0">•</span>
                                          <span>{issue}</span>
                                        </div>
                                      ))}
                                    </div>
                                  )}

                                  {/* LLM suggestion */}
                                  {clip.suggestion && (
                                    <div className="mb-3 px-3 py-2 rounded-lg bg-violet-500/[0.05] border border-violet-500/15">
                                      <div className="text-[10px] text-violet-400/60 font-bold uppercase mb-1">{t(locale, "admin_gen_clip_ai_suggestion")}</div>
                                      <p className="text-xs text-white/50">{clip.suggestion}</p>
                                    </div>
                                  )}

                                  {/* Accept/Decline suggestion or Regenerate */}
                                  {hasRegen ? (
                                    <div className="flex gap-2">
                                      <button
                                        onClick={() => acceptRegen(clip.name)}
                                        className="flex-1 px-3 py-2 text-xs font-bold rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/30 transition-all"
                                      >
                                        {t(locale, "admin_gen_clip_accept_regen")}
                                      </button>
                                      <button
                                        onClick={() => discardRegen(clip.name)}
                                        className="flex-1 px-3 py-2 text-xs font-bold rounded-lg bg-rose-500/20 text-rose-300 border border-rose-500/30 hover:bg-rose-500/30 transition-all"
                                      >
                                        {t(locale, "admin_gen_clip_discard")}
                                      </button>
                                    </div>
                                  ) : (
                                    <div>
                                      {/* Improvement prompt input */}
                                      <div className="flex gap-2 mb-2">
                                        <input
                                          type="text"
                                          placeholder={clip.improvement_prompt || "Optional improvement prompt (leave empty for auto)"}
                                          value={regenPrompts[clip.name] || ""}
                                          onChange={(e) => setRegenPrompts((prev) => ({ ...prev, [clip.name]: e.target.value }))}
                                          className="flex-1 px-3 py-2 text-xs rounded-lg bg-white/[0.04] border border-white/[0.07] text-white/70 placeholder-white/20 focus:outline-none focus:ring-1 focus:ring-violet-500/30"
                                        />
                                      </div>

                                      {/* Action buttons */}
                                      <div className="flex gap-2">
                                        {clip.improvement_prompt && !regenPrompts[clip.name] && (
                                          <button
                                            onClick={() => {
                                              setRegenPrompts((prev) => ({ ...prev, [clip.name]: clip.improvement_prompt || "" }));
                                              regenerateClip(clip.name);
                                            }}
                                            disabled={isRegenLoading || running}
                                            className="flex-1 px-3 py-2 text-xs font-bold rounded-lg bg-violet-500/20 text-violet-300 border border-violet-500/30 hover:bg-violet-500/30 disabled:opacity-30 transition-all"
                                          >
                                            {isRegenLoading ? t(locale, "admin_gen_clip_regenerating") : t(locale, "admin_gen_clip_accept_and_regen")}
                                          </button>
                                        )}
                                        <button
                                          onClick={() => regenerateClip(clip.name)}
                                          disabled={isRegenLoading || running}
                                          className="flex-1 px-3 py-2 text-xs font-bold rounded-lg bg-white/[0.05] text-white/50 border border-white/[0.08] hover:bg-white/[0.08] hover:text-white/70 disabled:opacity-30 transition-all"
                                        >
                                          {isRegenLoading ? (
                                            <span className="flex items-center justify-center gap-2">
                                              <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" strokeDasharray="28 62" strokeLinecap="round" /></svg>
                                              {t(locale, "admin_gen_clip_regenerating")}
                                            </span>
                                          ) : t(locale, "admin_gen_clip_regenerate")}
                                        </button>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {!clipReviewLoading && !clipReview?.available && !stepHasSuccess("generate_clips") && (
                      <div className="text-center py-8">
                        <p className="text-sm text-white/20">{t(locale, "admin_gen_clip_generate_first")}</p>
                      </div>
                    )}

                    {!clipReviewLoading && !clipReview?.available && stepHasSuccess("generate_clips") && (
                      <div className="text-center py-8">
                        <p className="text-sm text-white/20">{t(locale, "admin_gen_clip_click_review")}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Live clips — shown progressively during generate_clips */}
                {selectedStep === "generate_clips" && liveClips.length > 0 && running && runningStepId === "generate_clips" && (
                  <div className="mt-6">
                    <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold mb-3 flex items-center gap-2">
                      <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                      {t(locale, "admin_gen_clips_generating")} ({liveClips.length})
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {liveClips.map((clip) => {
                        const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
                        const epNum = epObj?.episode_number;
                        const url = `/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epNum}&step=generate_clips&file=${encodeURIComponent(clip.name)}&run_ts=${clip.runTs}&_t=${Date.now()}`;
                        return (
                          <div key={clip.name} className="rounded-xl border border-emerald-500/20 bg-black/30 overflow-hidden animate-fadeIn">
                            <video controls className="w-full max-h-64 bg-black" preload="auto" autoPlay muted>
                              <source src={url} type="video/mp4" />
                            </video>
                            <div className="px-3 py-2 border-t border-white/[0.04] flex items-center justify-between">
                              <span className="text-[11px] text-emerald-300/60 font-mono truncate">{clip.name}</span>
                              <span className="text-[10px] text-emerald-400/40">{t(locale, "admin_gen_clip_new")}</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12">
                <StepIcon stepId={selectedStep} className="w-16 h-16 text-white/10 mx-auto mb-4" />
                <p className="text-sm text-white/25 mb-4">{t(locale, "admin_gen_no_runs")}</p>
                {canRunStep(selectedStep) && (
                  <div className="flex items-center justify-center gap-3">
                    <button onClick={() => runStep(selectedStep)} disabled={running}
                      className="btn-primary text-sm disabled:opacity-30">
                      {t(locale, "admin_gen_run_step")} {stepLabel(locale, selectedStep)}
                    </button>
                    {SKIPPABLE_STEPS.includes(selectedStep) && (
                      <button onClick={() => handleSkipStep(selectedStep)} disabled={running}
                        className={`px-4 py-2 text-sm font-bold rounded-lg border disabled:opacity-30 transition-all ${
                          stepIsSkipped(selectedStep)
                            ? "bg-amber-500/20 text-amber-300 border-amber-500/30 hover:bg-amber-500/30"
                            : "bg-zinc-500/20 text-zinc-300 border-zinc-500/30 hover:bg-zinc-500/30"
                        }`}>
                        {stepIsSkipped(selectedStep) ? t(locale, "admin_gen_unskip") : t(locale, "admin_gen_skip")}
                      </button>
                    )}
                  </div>
                )}
                {!canRunStep(selectedStep) && (
                  <p className="text-xs text-white/15 mt-2">{t(locale, "admin_gen_prev_step_required")}</p>
                )}
                {/* Live clips in the no-runs fallback */}
                {selectedStep === "generate_clips" && liveClips.length > 0 && running && runningStepId === "generate_clips" && (
                  <div className="mt-8 text-left">
                    <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold mb-3 flex items-center gap-2">
                      <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                      {t(locale, "admin_gen_clips_generating")} ({liveClips.length})
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {liveClips.map((clip) => {
                        const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
                        const epNum = epObj?.episode_number;
                        const url = `/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epNum}&step=generate_clips&file=${encodeURIComponent(clip.name)}&run_ts=${clip.runTs}&_t=${Date.now()}`;
                        return (
                          <div key={clip.name} className="rounded-xl border border-emerald-500/20 bg-black/30 overflow-hidden animate-fadeIn">
                            <video controls className="w-full max-h-64 bg-black" preload="auto" autoPlay muted>
                              <source src={url} type="video/mp4" />
                            </video>
                            <div className="px-3 py-2 border-t border-white/[0.04] flex items-center justify-between">
                              <span className="text-[11px] text-emerald-300/60 font-mono truncate">{clip.name}</span>
                              <span className="text-[10px] text-emerald-400/40">{t(locale, "admin_gen_clip_new")}</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Compose Options Panel — shown for compose_episode step (outside ternary so it always renders) */}
            {selectedStep === "compose_episode" && canRunStep("compose_episode") && (() => {
              const hasClips = stepHasSuccess("generate_clips") || stepIsSkipped("generate_clips");
              const clipsArtifacts = hasClips ? (artifacts["generate_clips"]?.files?.filter((f: ArtifactFile) => f.type === "mp4" && /^scene_\d+_clip_\d+/.test(f.name) && !f.name.includes("_segment") && !f.name.includes(".regen")) || []) : [];
              const audioArtifacts = hasClips ? (artifacts["add_audio"]?.files?.filter((f: ArtifactFile) => (f.type === "mp3" || f.type === "wav") && !f.name.includes("_segment")) || []) : [];
              const epObj = episodes.find((e) => String(e.id) === selectedEpisode);
              const epNum = epObj?.episode_number;
              const clipsOutputDir = getSelectedRunOutputDir("generate_clips");
              const clipsRunTsParam = clipsOutputDir ? `&run_ts=${clipsOutputDir}` : "";
              const audioOutputDir = getSelectedRunOutputDir("add_audio");
              const audioRunTsParam = audioOutputDir ? `&run_ts=${audioOutputDir}` : "";
              const allClipsSelected = clipsArtifacts.length > 0 && clipsArtifacts.every((f: ArtifactFile) => composeSelectedClips[f.name] !== false);
              const someClipsSelected = clipsArtifacts.some((f: ArtifactFile) => composeSelectedClips[f.name] !== false);
              const allAudioSelected = audioArtifacts.length > 0 && audioArtifacts.every((f: ArtifactFile) => composeSelectedAudio[f.name] !== false);
              const someAudioSelected = audioArtifacts.some((f: ArtifactFile) => composeSelectedAudio[f.name] !== false);

              return (
                <div className="mt-6 space-y-6">
                  {/* Compose Controls */}
                  <div className="flex flex-wrap gap-4">
                    {/* Mute Video Audio Toggle */}
                    <label title="Strip all audio from the composed video. Useful for adding custom audio later." className={`flex items-center gap-4 px-6 py-4 rounded-xl border cursor-pointer transition-all ${composeMuteVideoAudio ? "bg-amber-500/10 border-amber-500/40" : "bg-white/[0.02] border-white/[0.07] hover:border-white/[0.15]"}`}>
                      <input type="checkbox" checked={composeMuteVideoAudio} onChange={(e) => setComposeMuteVideoAudio(e.target.checked)} className="accent-amber-500 w-6 h-6" />
                      <span className={`text-lg font-medium whitespace-nowrap ${composeMuteVideoAudio ? "text-amber-300" : "text-white/50"}`}>
                        <svg className="w-6 h-6 inline-block mr-1.5 -mt-0.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M17.25 9.75L19.5 12m0 0l2.25 2.25M19.5 12l2.25-2.25M19.5 12l-2.25 2.25m-10.5-6l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z" /></svg>
                        Mute Audio
                      </span>
                    </label>
                    {/* No Watermark Toggle */}
                    <label title="Remove the logo watermark overlay from the final video." className={`flex items-center gap-4 px-6 py-4 rounded-xl border cursor-pointer transition-all ${composeNoWatermark ? "bg-amber-500/10 border-amber-500/40" : "bg-white/[0.02] border-white/[0.07] hover:border-white/[0.15]"}`}>
                      <input type="checkbox" checked={composeNoWatermark} onChange={(e) => setComposeNoWatermark(e.target.checked)} className="accent-amber-500 w-6 h-6" />
                      <span className={`text-lg font-medium whitespace-nowrap ${composeNoWatermark ? "text-amber-300" : "text-white/50"}`}>
                        <svg className="w-6 h-6 inline-block mr-1.5 -mt-0.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" /></svg>
                        No Watermark
                      </span>
                    </label>
                    {/* Auto Subtitles Toggle */}
                    <label title="Auto-transcribe speech and burn bilingual subtitles (ASS format) into the video." className={`flex items-center gap-4 px-6 py-4 rounded-xl border cursor-pointer transition-all ${composeSubtitles ? "bg-emerald-500/10 border-emerald-500/40" : "bg-white/[0.02] border-white/[0.07] hover:border-white/[0.15]"}`}>
                      <input type="checkbox" checked={composeSubtitles} onChange={(e) => setComposeSubtitles(e.target.checked)} className="accent-emerald-500 w-6 h-6" />
                      <span className={`text-lg font-medium whitespace-nowrap ${composeSubtitles ? "text-emerald-300" : "text-white/50"}`}>
                        <svg className="w-6 h-6 inline-block mr-1.5 -mt-0.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.076-4.076a1.526 1.526 0 011.037-.443 48.282 48.282 0 005.68-.494c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" /></svg>
                        Subtitles
                      </span>
                    </label>
                    {/* Global EN Version Toggle */}
                    <label title="Generate an English-dubbed version with TTS narration. Requires subtitles to be enabled." className={`flex items-center gap-4 px-6 py-4 rounded-xl border cursor-pointer transition-all ${composeGlobalEn && composeSubtitles ? "bg-blue-500/10 border-blue-500/40" : "bg-white/[0.02] border-white/[0.07]"} ${!composeSubtitles ? "opacity-40 pointer-events-none" : "hover:border-white/[0.15]"}`}>
                      <input type="checkbox" checked={composeGlobalEn && composeSubtitles} onChange={(e) => setComposeGlobalEn(e.target.checked)} disabled={!composeSubtitles} className="accent-blue-500 w-6 h-6" />
                      <span className={`text-lg font-medium whitespace-nowrap ${composeGlobalEn && composeSubtitles ? "text-blue-300" : "text-white/50"}`}>
                        <svg className="w-6 h-6 inline-block mr-1.5 -mt-0.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M10.5 21l5.25-11.25L21 21m-9-3h7.5M3 5.621a48.474 48.474 0 016-.371m0 0c1.12 0 2.233.038 3.334.114M9 5.25V3m3.334 2.364C11.176 10.658 7.69 15.08 3 17.502m9.334-12.138c.896.061 1.785.147 2.666.257m-4.589 8.495a18.023 18.023 0 01-3.827-5.802" /></svg>
                        Global EN
                      </span>
                    </label>
                    {/* No Opening Toggle */}
                    <label title="Skip the 2-second title card opening at the beginning of the episode." className={`flex items-center gap-4 px-6 py-4 rounded-xl border cursor-pointer transition-all ${composeNoOpening ? "bg-amber-500/10 border-amber-500/40" : "bg-white/[0.02] border-white/[0.07] hover:border-white/[0.15]"}`}>
                      <input type="checkbox" checked={composeNoOpening} onChange={(e) => setComposeNoOpening(e.target.checked)} className="accent-amber-500 w-6 h-6" />
                      <span className={`text-lg font-medium whitespace-nowrap ${composeNoOpening ? "text-amber-300" : "text-white/50"}`}>
                        <svg className="w-6 h-6 inline-block mr-1.5 -mt-0.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3 8.689c0-.864.933-1.405 1.683-.977l7.108 4.061a1.125 1.125 0 010 1.954l-7.108 4.061A1.125 1.125 0 013 16.811V8.69zM12.75 8.689c0-.864.933-1.405 1.683-.977l7.108 4.061a1.125 1.125 0 010 1.954l-7.108 4.061a1.125 1.125 0 01-1.683-.977V8.69z" /></svg>
                        Skip Opening
                      </span>
                    </label>
                  </div>

                  {/* Clip Selection */}
                  {clipsArtifacts.length > 0 && (
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-8.625 0V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125M3.375 4.5c-.621 0-1.125.504-1.125 1.125M20.625 4.5H3.375m17.25 0c.621 0 1.125.504 1.125 1.125m0 0v12.75c0 .621-.504 1.125-1.125 1.125m1.125-13.875c0-.621-.504-1.125-1.125-1.125" /></svg>
                          Video Clips ({clipsArtifacts.length})
                        </h3>
                        <button
                          onClick={() => {
                            const newState: Record<string, boolean> = {};
                            clipsArtifacts.forEach((f: ArtifactFile) => { newState[f.name] = !allClipsSelected; });
                            setComposeSelectedClips(newState);
                          }}
                          className="text-[10px] font-bold text-white/30 hover:text-violet-300 px-2 py-1 rounded border border-white/[0.06] hover:border-violet-500/30 transition-all"
                        >
                          {allClipsSelected ? "Deselect All" : "Select All"}
                        </button>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                        {clipsArtifacts.map((file: ArtifactFile) => {
                          const isSelected = composeSelectedClips[file.name] !== false;
                          const videoUrl = `/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epNum}&step=generate_clips&file=${encodeURIComponent(file.name)}${clipsRunTsParam}`;
                          return (
                            <div key={file.name}
                              onClick={() => setComposeSelectedClips((prev) => ({ ...prev, [file.name]: !isSelected }))}
                              className={`rounded-xl border overflow-hidden cursor-pointer transition-all ${isSelected ? "border-violet-500/40 bg-violet-500/[0.04] ring-1 ring-violet-500/20" : "border-white/[0.06] bg-white/[0.01] opacity-50"}`}
                            >
                              <div className="relative">
                                <video className="w-full h-28 object-cover bg-black" preload="metadata" muted>
                                  <source src={videoUrl} type="video/mp4" />
                                </video>
                                <div className={`absolute top-2 left-2 w-5 h-5 rounded border-2 flex items-center justify-center transition-all ${isSelected ? "bg-violet-500 border-violet-400" : "bg-black/50 border-white/30"}`}>
                                  {isSelected && <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={3} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>}
                                </div>
                              </div>
                              <div className="px-3 py-2 flex items-center justify-between">
                                <span className="text-[11px] font-mono text-white/50 truncate">{file.name}</span>
                                <span className="text-[10px] text-white/20">{fmtSize(file.size)}</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      {!allClipsSelected && someClipsSelected && (
                        <div className="mt-2 text-[10px] text-violet-300/60">
                          {clipsArtifacts.filter((f: ArtifactFile) => composeSelectedClips[f.name] !== false).length} of {clipsArtifacts.length} clips selected
                        </div>
                      )}
                    </div>
                  )}

                  {/* Audio Selection */}
                  <div>
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-xs uppercase tracking-wider text-white/25 font-bold flex items-center gap-2">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z" /></svg>
                          Audio Files ({audioArtifacts.length})
                        </h3>
                        <button
                          onClick={() => {
                            const newState: Record<string, boolean> = {};
                            audioArtifacts.forEach((f: ArtifactFile) => { newState[f.name] = !allAudioSelected; });
                            setComposeSelectedAudio(newState);
                          }}
                          className="text-[10px] font-bold text-white/30 hover:text-violet-300 px-2 py-1 rounded border border-white/[0.06] hover:border-violet-500/30 transition-all"
                        >
                          {allAudioSelected ? "Deselect All" : "Select All"}
                        </button>
                      </div>
                      <div className="space-y-2">
                        {audioArtifacts.map((file: ArtifactFile) => {
                          const isSelected = composeSelectedAudio[file.name] !== false;
                          const audioUrl = `/api/admin/artifacts/download?story_id=${selectedStory}&episode=${epNum}&step=add_audio&file=${encodeURIComponent(file.name)}${audioRunTsParam}`;
                          return (
                            <div key={file.name}
                              className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition-all ${isSelected ? "border-violet-500/30 bg-violet-500/[0.04]" : "border-white/[0.06] bg-white/[0.01] opacity-50"}`}
                            >
                              <button
                                onClick={() => setComposeSelectedAudio((prev) => ({ ...prev, [file.name]: !isSelected }))}
                                className={`w-5 h-5 rounded border-2 flex items-center justify-center shrink-0 transition-all ${isSelected ? "bg-violet-500 border-violet-400" : "bg-transparent border-white/30 hover:border-violet-400"}`}
                              >
                                {isSelected && <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={3} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>}
                              </button>
                              <div className="flex-1 min-w-0">
                                <audio controls className="w-full h-8" preload="metadata" style={{ filter: isSelected ? "none" : "grayscale(1) opacity(0.5)" }}>
                                  <source src={audioUrl} type={file.type === "mp3" ? "audio/mpeg" : "audio/wav"} />
                                </audio>
                              </div>
                              <span className="text-[11px] font-mono text-white/40 truncate shrink-0 max-w-[150px]">{file.name}</span>
                              <span className="text-[10px] text-white/20 shrink-0">{fmtSize(file.size)}</span>
                            </div>
                          );
                        })}
                      </div>
                      {!allAudioSelected && someAudioSelected && (
                        <div className="mt-2 text-[10px] text-violet-300/60">
                          {audioArtifacts.filter((f: ArtifactFile) => composeSelectedAudio[f.name] !== false).length} of {audioArtifacts.length} audio files selected
                        </div>
                      )}
                      {audioArtifacts.length === 0 && (
                        <div className="flex items-center gap-3 px-4 py-6 rounded-xl border border-white/[0.06] bg-white/[0.01]">
                          <svg className="w-5 h-5 text-white/15" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z" /></svg>
                          <span className="text-sm text-white/20">No audio files available. Run the audio step to add background music or narration.</span>
                        </div>
                      )}
                    </div>

                  {clipsArtifacts.length === 0 && !hasClips && (
                    <div className="text-center py-8">
                      <p className="text-sm text-white/20">No clips available. Generate clips first and select a run.</p>
                    </div>
                  )}
                </div>
              );
            })()}

          </div>
        </div>
      )}

      {/* Result banner */}
      {pipelineResult !== "idle" && !running && (
        <div className={`mb-8 rounded-2xl p-6 border text-center ${pipelineResult === "success" ? "border-emerald-500/20 bg-emerald-500/[0.03]" : "border-rose-500/20 bg-rose-500/[0.03]"}`}>
          <div className={`inline-flex items-center justify-center w-12 h-12 rounded-full mb-3 ${pipelineResult === "success" ? "bg-emerald-500/15" : "bg-rose-500/15"}`}>
            {pipelineResult === "success" ? (
              <svg className="w-7 h-7 text-emerald-400" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
            ) : (
              <svg className="w-7 h-7 text-rose-400" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" /></svg>
            )}
          </div>
          <p className={`text-lg font-bold ${pipelineResult === "success" ? "text-emerald-300" : "text-rose-300"}`}>
            {pipelineResult === "success" ? t(locale, "admin_gen_complete") : t(locale, "admin_gen_failed")}
          </p>
          <p className="text-xs text-white/30 mt-1">
            {pipelineResult === "success" ? `${completedSteps} ${t(locale, "admin_gen_steps_completed")}` : t(locale, "admin_gen_check_failed")}
          </p>
        </div>
      )}

      {/* Console (collapsible) */}
      {(showConsole || logs.length > 0) && (
        <div className="glass-card rounded-2xl overflow-hidden mb-8">
          <button onClick={() => setShowConsole(!showConsole)}
            className="w-full flex items-center justify-between px-5 py-3 hover:bg-white/[0.01] transition-colors">
            <span className="text-xs uppercase tracking-wider text-white/20 font-bold">{t(locale, "admin_gen_console")}</span>
            <div className="flex items-center gap-2">
              {logs.length > 0 && <span className="text-[10px] text-white/15 font-mono">{logs.length} {t(locale, "admin_gen_lines")}</span>}
              <svg className={`w-3.5 h-3.5 text-white/15 transition-transform ${showConsole ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" /></svg>
            </div>
          </button>
          {showConsole && (
            <div className="border-t border-white/[0.04]">
              <div ref={logContainerRef} onScroll={() => { const el = logContainerRef.current; if (el) { userScrolledUp.current = el.scrollTop + el.clientHeight < el.scrollHeight - 32; } }} className="bg-black/30 p-4 max-h-56 overflow-auto font-mono text-xs leading-relaxed space-y-0.5">
                {logs.length === 0 ? <span className="text-white/10">{t(locale, "admin_gen_waiting")}</span> : logs.map((log, i) => (
                  <div key={i} className="flex gap-3 py-0.5 hover:bg-white/[0.01] rounded px-2 -mx-2">
                    <span className="text-white/10 shrink-0 select-none tabular-nums text-[10px] pt-0.5">{new Date(log.timestamp).toLocaleTimeString()}</span>
                    <span className={log.type === "error" ? "text-rose-400/70" : log.type === "success" ? "text-emerald-400/70" : log.type === "warning" ? "text-amber-400/70" : log.type === "step" ? "text-violet-400 font-bold" : "text-white/30"}>{log.message}</span>
                  </div>
                ))}
                {running && <div className="flex items-center gap-2 pt-1"><span className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" /><span className="text-[10px] text-violet-400/40">{t(locale, "admin_gen_streaming")}</span></div>}
                <div ref={logEndRef} />
              </div>
              {logs.length > 0 && (
                <div className="flex justify-end px-4 py-2 border-t border-white/[0.03]">
                  <button onClick={() => { setLogs([]); setShowConsole(false); }} className="text-[10px] text-white/20 hover:text-white/50">{t(locale, "admin_gen_clear")}</button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Previous Runs */}
      {previousRuns.length > 0 && (
        <div className="mb-10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs uppercase tracking-wider text-white/20 font-bold">{t(locale, "admin_gen_history")}</h2>
            <button
              onClick={async () => {
                if (!window.confirm(t(locale, "admin_gen_confirm_clear_history"))) return;
                await fetch(`/api/admin/generation-runs?episode_id=${selectedEpisode}`, { method: "DELETE" });
                setPreviousRuns([]);
                setStepRuns({});
                setStepSelections({});
                loadAllStepRuns();
              }}
              className="text-[10px] text-white/20 hover:text-rose-400 border border-white/[0.06] hover:border-rose-500/30 px-3 py-1 rounded-lg transition-colors"
            >
              {t(locale, "admin_gen_clear_all")}
            </button>
          </div>
          <div className="space-y-2">
            {previousRuns.slice(0, 5).map((run) => {
              // Compute per-step local count: how many runs with the same step(s) exist up to this one (by id, ascending)
              const stepKey = run.mode === "full" ? "__full__" : run.steps.map((s) => s.step_id).join(",");
              const sameStepRuns = previousRuns.filter((r) => {
                const k = r.mode === "full" ? "__full__" : r.steps.map((s) => s.step_id).join(",");
                return k === stepKey;
              }).sort((a, b) => a.id - b.id);
              const localNum = sameStepRuns.findIndex((r) => r.id === run.id) + 1;
              const runStepLabel = run.mode === "full" ? t(locale, "admin_gen_full_pipeline") : run.steps.map((s) => stepLabel(locale, s.step_id)).join(", ");
              return (
              <div key={run.id}
                className="glass-card-hover rounded-xl px-5 py-3 flex items-center gap-4">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${run.status === "completed" ? "bg-emerald-500/10" : run.status === "failed" ? "bg-rose-500/10" : "bg-violet-500/10"}`}>
                  {run.status === "completed" ? <svg className="w-4 h-4 text-emerald-400" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg>
                  : run.status === "failed" ? <svg className="w-4 h-4 text-rose-400" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                  : <div className="w-3 h-3 border-2 border-violet-400/30 border-t-violet-400 rounded-full animate-spin" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white/50 font-medium truncate">{t(locale, "admin_gen_run_label")} #{localNum} - {runStepLabel}</p>
                  <p className="text-[10px] text-white/20">{new Date(run.started_at).toLocaleString()}{run.ended_at && ` - ${fmtDur(new Date(run.ended_at).getTime() - new Date(run.started_at).getTime())}`}</p>
                </div>
                <div className="flex gap-1 shrink-0">
                  {run.steps.map((s, i) => <div key={i} className={`w-2 h-2 rounded-full ${s.status === "done" ? "bg-emerald-400" : s.status === "failed" ? "bg-rose-400" : s.status === "running" ? "bg-violet-400" : "bg-white/10"}`} />)}
                </div>
              </div>
              );
            })}
          </div>
        </div>
      )}

    </div>
  );
}
