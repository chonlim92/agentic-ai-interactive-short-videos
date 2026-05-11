import { NextRequest, NextResponse } from "next/server";
import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import { isAdminAuthenticated } from "@/lib/auth";
import { stopActiveProcess } from "../route";
import { loadStore, updateGenerationStep, completeGenerationRun } from "@/lib/db";

const IS_WINDOWS = process.platform === "win32";
const PROJECT_ROOT = path.resolve(process.cwd(), "..");

/**
 * Create a stop file that the Python agent checks between iterations.
 * This ensures the process stops even if taskkill fails or the process
 * is in a sleep/poll state that makes it hard to kill immediately.
 */
function createStopFile(runId: number): void {
  const stopDir = path.join(PROJECT_ROOT, ".stop");
  if (!fs.existsSync(stopDir)) {
    fs.mkdirSync(stopDir, { recursive: true });
  }
  fs.writeFileSync(path.join(stopDir, `${runId}.stop`), new Date().toISOString());
}

/**
 * Read the PID file written by the Python agent on startup.
 * This is the most reliable way to find the actual process to kill,
 * regardless of Next.js hot-reload state or DB stale data.
 */
function readPidFile(runId: number): number | null {
  try {
    const pidPath = path.join(PROJECT_ROOT, ".stop", `${runId}.pid`);
    if (fs.existsSync(pidPath)) {
      const pid = parseInt(fs.readFileSync(pidPath, "utf-8").trim(), 10);
      return isNaN(pid) ? null : pid;
    }
  } catch {}
  return null;
}

/**
 * Kill a process by PID using platform-appropriate method.
 */
function killByPid(pid: number): boolean {
  try {
    if (IS_WINDOWS) {
      execSync(`taskkill /pid ${pid} /T /F`, { stdio: "ignore" });
    } else {
      process.kill(-pid, "SIGKILL");
    }
    return true;
  } catch {
    return false;
  }
}

export async function POST(req: NextRequest) {
  if (!isAdminAuthenticated()) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json();
  const runId: number = body.run_id;

  if (!runId) {
    return NextResponse.json({ error: "run_id required" }, { status: 400 });
  }

  // Always create a stop file so the Python process detects it between clips
  createStopFile(runId);

  // Try in-memory stop first (preferred — handles stream cleanup too)
  const stopped = stopActiveProcess(runId);
  if (stopped) {
    return NextResponse.json({ success: true, message: "Process stop signal sent" });
  }

  // Read PID file written by the Python agent (most reliable after hot-reload)
  const pidFromFile = readPidFile(runId);
  let killed = false;
  if (pidFromFile) {
    killed = killByPid(pidFromFile);
    if (killed) {
      // Clean up PID file
      try { fs.unlinkSync(path.join(PROJECT_ROOT, ".stop", `${runId}.pid`)); } catch {}
    }
  }

  // Fallback: kill by PID from database (handles cases where PID file doesn't exist)
  if (!killed) {
    const store = loadStore();
    const run = store.generation_runs.find((r: { id: number }) => r.id === runId);
    if (!run) {
      return NextResponse.json({ error: "Run not found" }, { status: 404 });
    }

    const runningStep = run.steps.find((s: { status: string }) => s.status === "running");
    const pid = runningStep?.pid;

    if (pid) {
      killed = killByPid(pid);
    }

    // Update DB to mark as failed regardless of whether kill succeeded
    if (runningStep) {
      updateGenerationStep(runId, runningStep.step_id, {
        status: "failed",
        ended_at: new Date().toISOString(),
      });
    }
    completeGenerationRun(runId, "failed");

    return NextResponse.json({ success: true, message: pid ? `Killed process ${pid}` : "Run marked as failed (no PID found)" });
  }

  // PID file kill succeeded — update DB
  const store = loadStore();
  const run = store.generation_runs.find((r: { id: number }) => r.id === runId);
  if (run) {
    const runningStep = run.steps.find((s: { status: string }) => s.status === "running");
    if (runningStep) {
      updateGenerationStep(runId, runningStep.step_id, {
        status: "failed",
        ended_at: new Date().toISOString(),
      });
    }
    completeGenerationRun(runId, "failed");
  }

  return NextResponse.json({ success: true, message: `Killed process ${pidFromFile} (from PID file)` });
}
