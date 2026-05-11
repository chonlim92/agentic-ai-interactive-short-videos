import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

/**
 * Lightweight endpoint to check when episode data was last modified.
 * Used by the frontend to auto-refresh when a publish completes.
 *
 * GET /api/freshness?story=<slug>&episode=<number>
 * Returns { ts: <unix_ms> } — the most recent mtime among key files.
 */

export const dynamic = "force-dynamic";

const DATA_ROOT = path.resolve(process.cwd(), "..", "data", "stories");
const STORE_PATH = path.resolve(process.cwd(), "data", "store.json");

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const storySlug = searchParams.get("story");
  const episodeNum = searchParams.get("episode");

  // Collect mtimes from key files that change on publish
  const mtimes: number[] = [];

  // store.json always changes on publish
  if (fs.existsSync(STORE_PATH)) {
    mtimes.push(fs.statSync(STORE_PATH).mtimeMs);
  }

  if (storySlug && episodeNum) {
    const epDir = path.join(DATA_ROOT, storySlug, "episodes", episodeNum, "final");
    // Check video, poster, gallery dirs
    for (const sub of ["video", "poster", "gallery"]) {
      const dir = path.join(epDir, sub);
      if (fs.existsSync(dir)) {
        mtimes.push(fs.statSync(dir).mtimeMs);
        try {
          for (const f of fs.readdirSync(dir)) {
            const fp = path.join(dir, f);
            mtimes.push(fs.statSync(fp).mtimeMs);
          }
        } catch { /* ignore */ }
      }
    }
  } else if (storySlug) {
    // Story-level: check story poster dir
    const posterDir = path.join(DATA_ROOT, storySlug, "poster");
    if (fs.existsSync(posterDir)) {
      mtimes.push(fs.statSync(posterDir).mtimeMs);
    }
  }

  const ts = mtimes.length > 0 ? Math.max(...mtimes) : 0;

  return NextResponse.json(
    { ts: Math.round(ts) },
    { headers: { "Cache-Control": "no-store" } },
  );
}
