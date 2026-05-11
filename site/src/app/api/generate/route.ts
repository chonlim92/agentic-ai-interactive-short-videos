import { NextRequest } from "next/server";
import { spawn, execSync, ChildProcess } from "child_process";
import { StringDecoder } from "string_decoder";
import path from "path";
import { isAdminAuthenticated } from "@/lib/auth";
import {
  createGenerationRun,
  updateGenerationStep,
  appendGenerationOutput,
  completeGenerationRun,
  loadStore,
  saveStore,
  selectStepRun,
  getSelectedOutputDirs,
} from "@/lib/db";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");
const IS_WINDOWS = process.platform === "win32";

// Track active processes by run ID so they can be stopped
const activeProcesses = new Map<number, { proc: ChildProcess; stepId: string; aborted: boolean }>();

export function getActiveProcess(runId: number) {
  return activeProcesses.get(runId);
}

/**
 * Kill a process and its entire child tree.
 * On Windows, uses `taskkill /T /F` which terminates the whole tree.
 * On POSIX, kills the process group via negative PID.
 */
function killProcessTree(proc: ChildProcess): void {
  const pid = proc.pid;
  if (!pid) {
    try { proc.kill("SIGKILL"); } catch {}
    return;
  }

  try {
    if (IS_WINDOWS) {
      // /T = kill child processes, /F = force
      execSync(`taskkill /pid ${pid} /T /F`, { stdio: "ignore" });
    } else {
      // Kill the process group (negative PID)
      process.kill(-pid, "SIGKILL");
    }
  } catch {
    // Process may have already exited
    try { proc.kill("SIGKILL"); } catch {}
  }
}

export function stopActiveProcess(runId: number): boolean {
  const entry = activeProcesses.get(runId);
  if (!entry) return false;
  entry.aborted = true;
  // Update DB immediately so the status shows as failed even if close handler fails
  updateGenerationStep(runId, entry.stepId, {
    status: "failed",
    ended_at: new Date().toISOString(),
  });
  completeGenerationRun(runId, "failed");
  // Kill entire process tree (not just the parent process)
  killProcessTree(entry.proc);
  return true;
}

// Check if a process with the given PID is still running
function isProcessAlive(pid: number): boolean {
  try {
    if (IS_WINDOWS) {
      const out = execSync(`tasklist /FI "PID eq ${pid}" /NH`, { encoding: "utf-8", stdio: ["pipe", "pipe", "ignore"] });
      return out.includes(String(pid));
    } else {
      process.kill(pid, 0); // signal 0 = just check if process exists
      return true;
    }
  } catch {
    return false;
  }
}

// On module load, clean up any stale "running" runs from a previous server session.
// If the server restarted (e.g. hot-reload), those processes are gone but DB still says "running".
// But if the process PID is still alive, keep the run as "running".
try {
  const store = loadStore();
  let cleaned = 0;
  for (const run of store.generation_runs || []) {
    if (run.status === "running") {
      // Check if any running step still has a live process
      const runningStep = (run.steps || []).find((s: { status: string }) => s.status === "running");
      const pid = runningStep?.pid;
      if (pid && isProcessAlive(pid)) {
        console.log(`[generate] Run ${run.id} step PID ${pid} is still alive — keeping as running`);
        continue;
      }
      run.status = "failed";
      run.ended_at = new Date().toISOString();
      for (const step of run.steps || []) {
        if (step.status === "running") {
          step.status = "failed";
          step.ended_at = new Date().toISOString();
        }
      }
      cleaned++;
    }
  }
  if (cleaned > 0) {
    saveStore(store);
    console.log(`[generate] Cleaned up ${cleaned} stale 'running' generation run(s) from previous session`);
  }
} catch (e) {
  console.warn("[generate] Failed to clean up stale runs on startup:", e);
}

const AGENTS_DIR = path.join(PROJECT_ROOT, "agents");

type AgentStep = {
  id: string;
  label: string;
  command: string;
  args: (episode: string, storySlug: string) => string[];
};

const PIPELINE_STEPS: AgentStep[] = [
  {
    id: "generate_script",
    label: "Generate Script",
    command: "python",
    args: (ep, story) => [path.join(AGENTS_DIR, "generate_episode.py"), "--episode", ep, "--story", story, "--stage", "script"],
  },
  {
    id: "plan_scenes",
    label: "Plan Scenes & Scenarios",
    command: "python",
    args: (ep, story) => [path.join(AGENTS_DIR, "generate_episode.py"), "--episode", ep, "--story", story, "--stage", "scenes"],
  },
  {
    id: "design_characters",
    label: "Design Characters",
    command: "python",
    args: (ep, story) => [path.join(AGENTS_DIR, "generate_episode.py"), "--episode", ep, "--story", story, "--stage", "characters"],
  },
  {
    id: "design_locations",
    label: "Design Locations",
    command: "python",
    args: (ep, story) => [path.join(AGENTS_DIR, "generate_episode.py"), "--episode", ep, "--story", story, "--stage", "locations"],
  },
  {
    id: "generate_keyframes",
    label: "Generate Keyframes",
    command: "python",
    args: (ep, story) => [path.join(AGENTS_DIR, "generate_episode.py"), "--episode", ep, "--story", story, "--stage", "keyframes"],
  },
  {
    id: "generate_clips",
    label: "Generate Video Clips",
    command: "python",
    args: (ep, story) => [path.join(AGENTS_DIR, "generate_video.py"), "--episode", ep, "--story", story],
  },
  {
    id: "validate_quality",
    label: "Validate Quality",
    command: "python",
    args: (ep, story) => [path.join(AGENTS_DIR, "validate_quality.py"), "--episode", ep, "--story", story],
  },
  {
    id: "add_audio",
    label: "Audio (Plan + Generate)",
    command: "python",
    args: (ep, story) => [path.join(AGENTS_DIR, "generate_episode.py"), "--episode", ep, "--story", story, "--stage", "audio"],
  },
  {
    id: "compose_episode",
    label: "Compose & Edit Episode",
    command: "python",
    args: (ep, story) => [path.join(AGENTS_DIR, "compose_episode.py"), "--episode", ep, "--story", story],
  },
  {
    id: "publish",
    label: "Publish to Site",
    command: "python",
    args: (ep, story) => [path.join(AGENTS_DIR, "publish_site.py"), "--episode", ep, "--story", story],
  },
];

const STEP_MAP: Record<string, AgentStep> = Object.fromEntries(
  PIPELINE_STEPS.map((s) => [s.id, s])
);

function sseMessage(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

// Map step IDs to their output subfolder names (for output_dir extraction)
const STEP_TO_FOLDER: Record<string, string> = {
  generate_script: "script",
  plan_scenes: "scenes",
  design_characters: "characters",
  design_locations: "locations",
  generate_keyframes: "keyframes",
  generate_clips: "clips",
  add_audio: "audio",
  compose_episode: "compose",
  publish: "publish",
};

// Extract timestamp folder from "saved to <path>" log lines
const SAVED_TO_REGEX = /saved to\s+(.+?)(?:[\r\n]|$)/i;

function extractOutputDirFromLog(text: string, stepId: string): string | null {
  const stepFolder = STEP_TO_FOLDER[stepId];
  if (!stepFolder) return null;
  const match = text.match(SAVED_TO_REGEX);
  if (!match) return null;
  const savedPath = match[1].trim().replace(/\\/g, "/");
  const parts = savedPath.split("/");
  const folderIdx = parts.findIndex((p) => p === stepFolder);
  if (folderIdx >= 0 && folderIdx + 1 < parts.length) {
    const tsFolder = parts[folderIdx + 1];
    if (/^\d{8}_\d{6}$/.test(tsFolder)) return tsFolder;
  }
  return null;
}

function runAgent(
  step: AgentStep,
  episode: string,
  storySlug: string,
  controller: ReadableStreamDefaultController,
  env: NodeJS.ProcessEnv,
  runId: number,
  storyId: number,
  episodeId: number
): Promise<{ success: boolean; code: number | null }> {
  return new Promise((resolve) => {
    const args = step.args(episode, storySlug);
    const startTime = Date.now();
    const proc = spawn(step.command, args, {
      cwd: PROJECT_ROOT,
      env,
      // detached on POSIX creates a process group we can kill together
      detached: !IS_WINDOWS,
    });

    // Register process for stop capability
    activeProcesses.set(runId, { proc, stepId: step.id, aborted: false });

    // Track output_dir extracted from stdout
    let detectedOutputDir: string | null = null;

    controller.enqueue(
      sseMessage("step_start", { step: step.id, label: step.label, run_id: runId, started_at: new Date().toISOString() })
    );

    updateGenerationStep(runId, step.id, {
      status: "running",
      started_at: new Date().toISOString(),
      pid: proc.pid || null,
    });

    // Use StringDecoder to handle multi-byte UTF-8 characters split across chunks
    const stdoutDecoder = new StringDecoder("utf8");
    const stderrDecoder = new StringDecoder("utf8");
    let stdoutBuffer = "";

    proc.stdout.on("data", (chunk: Buffer) => {
      const text = stdoutDecoder.write(chunk);
      stdoutBuffer += text;
      // Only emit complete lines (ending with \n); keep partial line in buffer
      const parts = stdoutBuffer.split("\n");
      stdoutBuffer = parts.pop() || ""; // last part is incomplete (no trailing \n)
      for (const line of parts) {
        if (!line) continue;
        try { controller.enqueue(sseMessage("log", { step: step.id, text: line })); } catch {}
      }
      // Try to extract output_dir from this chunk
      if (!detectedOutputDir) {
        const dir = extractOutputDirFromLog(text, step.id);
        if (dir) {
          detectedOutputDir = dir;
          // Persist output_dir immediately so it survives HMR/server restarts
          updateGenerationStep(runId, step.id, { output_dir: dir });
        }
      }
      appendGenerationOutput(runId, step.id, text);
    });

    proc.stderr.on("data", (chunk: Buffer) => {
      const text = stderrDecoder.write(chunk);
      const lines = text.split("\n").filter(Boolean);
      for (const line of lines) {
        try {
          controller.enqueue(
            sseMessage("log", { step: step.id, text: line, level: "error" })
          );
        } catch {}
      }
      // Also try to extract output_dir from stderr (Python logging may go to stderr)
      if (!detectedOutputDir) {
        const dir = extractOutputDirFromLog(text, step.id);
        if (dir) {
          detectedOutputDir = dir;
          updateGenerationStep(runId, step.id, { output_dir: dir });
        }
      }
      appendGenerationOutput(runId, step.id, text);
    });

    proc.on("close", (code) => {
      // Flush any remaining buffered stdout
      if (stdoutBuffer) {
        try { controller.enqueue(sseMessage("log", { step: step.id, text: stdoutBuffer })); } catch {}
        // Check for output_dir in the remaining buffer
        if (!detectedOutputDir) {
          const dir = extractOutputDirFromLog(stdoutBuffer + "\n", step.id);
          if (dir) detectedOutputDir = dir;
        }
        stdoutBuffer = "";
      }

      const entry = activeProcesses.get(runId);
      const wasAborted = entry?.aborted || false;
      activeProcesses.delete(runId);

      const success = code === 0 && !wasAborted;
      const duration_ms = Date.now() - startTime;
      try {
        controller.enqueue(
          sseMessage("step_end", { step: step.id, success, code, duration_ms, stopped: wasAborted })
        );
      } catch {
        // Stream already closed (client disconnected/aborted)
      }
      updateGenerationStep(runId, step.id, {
        status: wasAborted ? "failed" : (success ? "done" : "failed"),
        ended_at: new Date().toISOString(),
        duration_ms,
        exit_code: code,
        output_dir: detectedOutputDir,
      });
      // Auto-select this run if step succeeded
      if (success) {
        selectStepRun(storyId, episodeId, step.id, runId);
      }
      resolve({ success, code });
    });

    proc.on("error", (err) => {
      activeProcesses.delete(runId);
      try {
        controller.enqueue(
          sseMessage("log", {
            step: step.id,
            text: `Process error: ${err.message}`,
            level: "error",
          })
        );
        controller.enqueue(
          sseMessage("step_end", { step: step.id, success: false, code: -1, duration_ms: Date.now() - startTime })
        );
      } catch {
        // Stream already closed
      }
      updateGenerationStep(runId, step.id, {
        status: "failed",
        ended_at: new Date().toISOString(),
        duration_ms: Date.now() - startTime,
        exit_code: -1,
      });
      resolve({ success: false, code: -1 });
    });
  });
}

export async function POST(req: NextRequest) {
  if (!isAdminAuthenticated()) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), {
      status: 401,
    });
  }

  const body = await req.json();
  const episode: string = String(body.episode || "1");
  const mode: string = body.mode || "full"; // full | single
  const stepId: string | undefined = body.step; // for single-step mode
  const episodeId: number = body.episode_id || 0;
  const storyId: number = body.story_id || 0;
  const llmModel: string | undefined = body.llm_model;
  const videoModel: string | undefined = body.video_model;
  const videoLocal: boolean = body.video_local === true;
  const videoAspectRatio: string = body.video_aspect_ratio || "9:16";
  const videoStyle: string = body.video_style || "chinese-cartoon";
  const videoLength: string = body.video_length || "60";
  const videoQuality: string = body.video_quality || "high";
  const audioModel: string | undefined = body.audio_model;
  // Compose-specific options
  const composeMuteVideoAudio: boolean = body.compose_mute_video_audio === true;
  const composeNoWatermark: boolean = body.compose_no_watermark === true;
  const composeSubtitles: boolean = body.compose_subtitles === true;
  const composeGlobalEn: boolean = body.compose_global_en === true;
  const composeNoOpening: boolean = body.compose_no_opening === true;
  const composeSelectClips: string | undefined = body.compose_select_clips;
  const composeSelectAudio: string | undefined = body.compose_select_audio;

  // Resolve story slug from story_id
  const store = loadStore();
  const story = store.stories.find((s: { id: number }) => s.id === storyId);
  const storySlug: string = story?.slug || "unknown";

  // Determine which steps to run
  let stepsToRun: AgentStep[];
  if (mode === "single" && stepId && STEP_MAP[stepId]) {
    stepsToRun = [STEP_MAP[stepId]];
  } else {
    stepsToRun = [...PIPELINE_STEPS];
  }

  // Override compose_episode args with request-scoped options
  stepsToRun = stepsToRun.map((s) => {
    if (s.id !== "compose_episode") return s;
    return {
      ...s,
      args: (ep: string, st: string) => {
        const a = [path.join(AGENTS_DIR, "compose_episode.py"), "--episode", ep, "--story", st];
        if (composeMuteVideoAudio) a.push("--mute-video-audio");
        if (composeNoWatermark) a.push("--no-watermark");
        if (!composeSubtitles) a.push("--no-subtitles");
        if (!composeGlobalEn) a.push("--no-global-en");
        if (composeNoOpening) a.push("--no-opening");
        if (composeSelectClips) { a.push("--select-clips", composeSelectClips); }
        if (composeSelectAudio !== undefined) { a.push("--select-audio", composeSelectAudio); }
        return a;
      },
    };
  });

  // Skip add_audio step in full pipeline when using Seedance (it generates its own audio)
  const effectiveVideoModel = videoModel || process.env.VIDEO_MODEL || "";
  const skippedSteps: string[] = [];
  if (mode === "full" && effectiveVideoModel.toLowerCase().includes("seedance")) {
    skippedSteps.push("add_audio");
    stepsToRun = stepsToRun.filter((s) => s.id !== "add_audio");
  }

  // Create persistent run record
  const runId = await createGenerationRun({
    episode_id: episodeId,
    story_id: storyId,
    mode: mode as "full" | "single",
    steps: stepsToRun.map((s) => ({ step_id: s.id, label: s.label })),
  });

  const stream = new ReadableStream({
    async start(controller) {
      controller.enqueue(
        sseMessage("pipeline_start", {
          episode,
          mode,
          run_id: runId,
          steps: stepsToRun.map((s) => ({ id: s.id, label: s.label })),
          skipped_steps: skippedSteps,
        })
      );

      // Notify frontend about skipped steps
      for (const skipped of skippedSteps) {
        const skippedDef = PIPELINE_STEPS.find((s) => s.id === skipped);
        controller.enqueue(
          sseMessage("step_skipped", {
            step: skipped,
            label: skippedDef?.label || skipped,
            reason: `Skipped: ${effectiveVideoModel} generates its own audio`,
          })
        );
      }

      const env = {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8",
        GENERATION_RUN_ID: String(runId),
        ...(llmModel ? { LLM_MODEL_OVERRIDE: llmModel } : {}),
        ...(videoModel ? { VIDEO_MODEL: videoModel } : {}),
        ...(audioModel ? { AUDIO_MODEL_OVERRIDE: audioModel } : {}),
        ...(videoLocal ? { VIDEO_EXEC_LOCAL: "1" } : {}),
        // Map HUGGINGFACE_API_TOKEN to HF_TOKEN for HuggingFace libraries
        ...(process.env.HUGGINGFACE_API_TOKEN && !process.env.HF_TOKEN
          ? { HF_TOKEN: process.env.HUGGINGFACE_API_TOKEN }
          : {}),
        VIDEO_ASPECT_RATIO: videoAspectRatio,
        VIDEO_STYLE: videoStyle,
        VIDEO_LENGTH: videoLength,
        VIDEO_QUALITY: videoQuality,
      } as NodeJS.ProcessEnv;

      for (const step of stepsToRun) {
        // Check if this run was already aborted (e.g. user pressed Stop)
        const abortEntry = activeProcesses.get(runId);
        if (abortEntry?.aborted) {
          break;
        }

        // Log previous steps' selected output paths
        const selectedDirs = getSelectedOutputDirs(storyId, episodeId);
        const stepIdx = PIPELINE_STEPS.findIndex((s) => s.id === step.id);
        const prevSteps = PIPELINE_STEPS.slice(0, stepIdx);
        const inputPaths: string[] = [];
        // Build env vars for selected output dirs
        const selectedEnv: Record<string, string> = {};
        for (const prev of prevSteps) {
          const sel = selectedDirs[prev.id];
          if (sel) {
            const folder = STEP_TO_FOLDER[prev.id] || prev.id;
            const fullPath = `data/stories/${storySlug}/episodes/${episode}/${folder}/${sel.output_dir}`;
            // Compute step-relative run number (count runs for this step, find position)
            const store = loadStore();
            const stepRuns = store.generation_runs
              .filter((r: { story_id: number; episode_id: number; steps: { step_id: string }[] }) =>
                r.story_id === storyId && r.episode_id === episodeId &&
                r.steps.some((s: { step_id: string }) => s.step_id === prev.id))
              .sort((a: { id: number }, b: { id: number }) => a.id - b.id);
            const relativeIdx = stepRuns.findIndex((r: { id: number }) => r.id === sel.run_id) + 1;
            inputPaths.push(`  ${prev.label} (run #${relativeIdx || sel.run_id}): ${fullPath}`);
            // Pass selected run dirs as env vars (e.g. SELECTED_SCENES_DIR, SELECTED_SCRIPT_DIR)
            const envKey = `SELECTED_${folder.toUpperCase()}_DIR`;
            selectedEnv[envKey] = sel.output_dir;
          }
        }
        if (inputPaths.length > 0) {
          const inputLog = `[inputs] Using outputs from previous steps:\n${inputPaths.join("\n")}`;
          controller.enqueue(sseMessage("log", { step: step.id, text: inputLog }));
          appendGenerationOutput(runId, step.id, inputLog + "\n");
        }

        const result = await runAgent(step, episode, storySlug, controller, { ...env, ...selectedEnv }, runId, storyId, episodeId);
        if (!result.success) {
          await completeGenerationRun(runId, "failed");
          controller.enqueue(
            sseMessage("pipeline_end", {
              success: false,
              failed_step: step.id,
              run_id: runId,
            })
          );
          controller.close();
          return;
        }
      }

      await completeGenerationRun(runId, "completed");
      controller.enqueue(sseMessage("pipeline_end", { success: true, run_id: runId }));
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
