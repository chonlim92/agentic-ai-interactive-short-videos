import { NextRequest, NextResponse } from "next/server";
import { loadStore } from "@/lib/db";
import fs from "fs";
import path from "path";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");

/**
 * GET /api/admin/artifacts?story_id=1&episode=1[&step=generate_script&run_ts=20260507_004604]
 * Returns the list of generated artifacts for each pipeline step.
 * If step + run_ts are provided, returns only that step's artifacts from the run-specific subfolder.
 */
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const storyId = searchParams.get("story_id");
  const episodeNum = searchParams.get("episode");
  const stepParam = searchParams.get("step");
  const runTs = searchParams.get("run_ts");

  if (!storyId || !episodeNum) {
    return NextResponse.json({ error: "story_id and episode are required" }, { status: 400 });
  }

  // Validate run_ts format
  if (runTs && (runTs.includes("..") || runTs.includes("/"))) {
    return NextResponse.json({ error: "Invalid run_ts" }, { status: 400 });
  }

  const store = loadStore();
  const story = store.stories.find((s: { id: number }) => s.id === parseInt(storyId, 10));
  if (!story) {
    return NextResponse.json({ error: "Story not found" }, { status: 404 });
  }

  const epDir = path.join(PROJECT_ROOT, "data", "stories", story.slug, "episodes", episodeNum);
  const storyDir = path.join(PROJECT_ROOT, "data", "stories", story.slug);

  // Map step IDs to their output subfolder names
  const stepFolders: Record<string, string> = {
    generate_script: "script",
    plan_scenes: "scenes",
    design_characters: "characters",
    generate_clips: "clips",
    add_audio: "audio",
    compose_episode: "compose",
    publish: "publish",
  };

  // If step + run_ts provided, return only that step's run-specific artifacts
  if (stepParam && runTs && stepFolders[stepParam]) {
    const files: { name: string; size: number; type: string }[] = [];

    if (stepParam === "design_characters") {
      // Characters are story-level, not episode-level — always read from storyDir/characters
      const charsDir = path.join(storyDir, "characters");
      if (fs.existsSync(charsDir)) {
        for (const f of fs.readdirSync(charsDir)) {
          const fp = path.join(charsDir, f);
          if (fs.statSync(fp).isFile() && f !== "README.yaml") {
            files.push({ name: f, size: fs.statSync(fp).size, type: path.extname(f).slice(1) || "file" });
          }
        }
        const avatarsDir = path.join(charsDir, "avatars");
        if (fs.existsSync(avatarsDir)) {
          for (const f of fs.readdirSync(avatarsDir)) {
            const fp = path.join(avatarsDir, f);
            if (fs.statSync(fp).isFile() && f.endsWith(".png")) {
              files.push({ name: `avatars/${f}`, size: fs.statSync(fp).size, type: "png" });
            }
          }
        }
      }
    } else if (stepParam === "publish") {
      // Publish assets live in final/gallery, final/poster, and story-level posters
      const publishFile2 = path.join(epDir, "publish.yaml");
      if (fs.existsSync(publishFile2)) {
        files.push({ name: "publish.yaml", size: fs.statSync(publishFile2).size, type: "yaml" });
      }
      const galleryDir2 = path.join(epDir, "final", "gallery");
      if (fs.existsSync(galleryDir2)) {
        for (const f of fs.readdirSync(galleryDir2)) {
          const fp = path.join(galleryDir2, f);
          if (fs.statSync(fp).isFile() && /\.(jpg|jpeg|png|webp)$/i.test(f)) {
            files.push({ name: `gallery/${f}`, size: fs.statSync(fp).size, type: path.extname(f).slice(1) });
          }
        }
      }
      const posterDir2 = path.join(epDir, "final", "poster");
      if (fs.existsSync(posterDir2)) {
        for (const f of fs.readdirSync(posterDir2)) {
          const fp = path.join(posterDir2, f);
          if (fs.statSync(fp).isFile() && /\.(jpg|jpeg|png|webp)$/i.test(f) && !f.startsWith("_")) {
            files.push({ name: `poster/${f}`, size: fs.statSync(fp).size, type: path.extname(f).slice(1) });
          }
        }
      }
      // Story posters (new: poster/, legacy: posters/)
      for (const posterDirName of ["poster", "posters"]) {
        const storyPostersDir2 = path.join(storyDir, posterDirName);
        if (fs.existsSync(storyPostersDir2)) {
          const walkPosters2 = (dir: string) => {
            for (const f of fs.readdirSync(dir)) {
              const fp = path.join(dir, f);
              if (fs.statSync(fp).isDirectory()) walkPosters2(fp);
              else if (/\.(jpg|jpeg|png|webp)$/i.test(f) && !f.startsWith("_") && !f.includes("base")) {
                files.push({ name: `story_posters/${path.relative(storyPostersDir2, fp).replace(/\\/g, "/")}`, size: fs.statSync(fp).size, type: path.extname(f).slice(1) });
              }
            }
          };
          walkPosters2(storyPostersDir2);
        }
      }
    } else {
      const runDir = path.join(epDir, stepFolders[stepParam], runTs);
      if (fs.existsSync(runDir)) {
        for (const f of fs.readdirSync(runDir)) {
          const fp = path.join(runDir, f);
          if (fs.statSync(fp).isFile()) {
            files.push({ name: f, size: fs.statSync(fp).size, type: path.extname(f).slice(1) || "file" });
          }
        }
      }
    }

    return NextResponse.json({
      artifacts: { [stepParam]: { available: files.length > 0, files } },
      state: null,
    });
  }

  // Define what artifacts each step produces
  const artifacts: Record<string, { files: { name: string; path: string; size: number; type: string }[]; available: boolean }> = {};

  // Step 1: generate_script -> script.yaml
  const scriptFile = path.join(epDir, "script.yaml");
  artifacts.generate_script = {
    available: fs.existsSync(scriptFile),
    files: fs.existsSync(scriptFile) ? [{ name: "script.yaml", path: scriptFile, size: fs.statSync(scriptFile).size, type: "yaml" }] : [],
  };

  // Step 2: plan_scenes -> scenes/ directory
  const scenesDir = path.join(epDir, "scenes");
  const sceneFiles: { name: string; path: string; size: number; type: string }[] = [];
  if (fs.existsSync(scenesDir)) {
    for (const f of fs.readdirSync(scenesDir)) {
      const fp = path.join(scenesDir, f);
      if (fs.statSync(fp).isFile()) {
        const ext = path.extname(f).slice(1);
        sceneFiles.push({ name: f, path: fp, size: fs.statSync(fp).size, type: ext });
      }
    }
  }
  artifacts.plan_scenes = { available: fs.existsSync(scenesDir) && sceneFiles.length > 0, files: sceneFiles };

  // Step 3: design_characters -> characters/ in story dir (including avatars/ subfolder)
  const charsDir = path.join(storyDir, "characters");
  const charFiles: { name: string; path: string; size: number; type: string }[] = [];
  if (fs.existsSync(charsDir)) {
    for (const f of fs.readdirSync(charsDir)) {
      const fp = path.join(charsDir, f);
      if (fs.statSync(fp).isFile() && f !== "README.yaml") {
        const ext = path.extname(f).slice(1);
        charFiles.push({ name: f, path: fp, size: fs.statSync(fp).size, type: ext });
      }
    }
    // Include avatar images from avatars/ subfolder
    const avatarsDir = path.join(charsDir, "avatars");
    if (fs.existsSync(avatarsDir)) {
      for (const f of fs.readdirSync(avatarsDir)) {
        const fp = path.join(avatarsDir, f);
        if (fs.statSync(fp).isFile() && f.endsWith(".png")) {
          charFiles.push({ name: `avatars/${f}`, path: fp, size: fs.statSync(fp).size, type: "png" });
        }
      }
    }
  }
  artifacts.design_characters = { available: charFiles.length > 0, files: charFiles };

  // Step 4: generate_clips -> clips/ directory
  const clipsDir = path.join(epDir, "clips");
  const clipFiles: { name: string; path: string; size: number; type: string }[] = [];
  if (fs.existsSync(clipsDir)) {
    const walkClips = (dir: string) => {
      for (const f of fs.readdirSync(dir)) {
        const fp = path.join(dir, f);
        if (fs.statSync(fp).isDirectory()) walkClips(fp);
        else if (f.endsWith(".mp4") || f.endsWith(".webm")) {
          clipFiles.push({ name: path.relative(clipsDir, fp).replace(/\\/g, "/"), path: fp, size: fs.statSync(fp).size, type: path.extname(f).slice(1) });
        }
      }
    };
    walkClips(clipsDir);
  }
  artifacts.generate_clips = { available: clipFiles.length > 0, files: clipFiles };

  // Step 5: validate_quality -> quality_report.yaml
  const qualityFile = path.join(epDir, "quality_report.yaml");
  artifacts.validate_quality = {
    available: fs.existsSync(qualityFile),
    files: fs.existsSync(qualityFile) ? [{ name: "quality_report.yaml", path: qualityFile, size: fs.statSync(qualityFile).size, type: "yaml" }] : [],
  };

  // Step 6: add_audio -> audio/ directory
  const audioDir = path.join(epDir, "audio");
  const audioFiles: { name: string; path: string; size: number; type: string }[] = [];
  if (fs.existsSync(audioDir)) {
    for (const f of fs.readdirSync(audioDir)) {
      const fp = path.join(audioDir, f);
      if (fs.statSync(fp).isFile()) {
        audioFiles.push({ name: f, path: fp, size: fs.statSync(fp).size, type: path.extname(f).slice(1) });
      }
    }
  }
  artifacts.add_audio = { available: audioFiles.length > 0, files: audioFiles };

  // Step 7: compose_episode -> compose/ directory (with timestamped subfolders)
  const finalDir = path.join(epDir, "compose");
  const finalFiles: { name: string; path: string; size: number; type: string }[] = [];
  if (fs.existsSync(finalDir)) {
    const walkCompose = (dir: string) => {
      for (const f of fs.readdirSync(dir)) {
        const fp = path.join(dir, f);
        if (fs.statSync(fp).isDirectory()) walkCompose(fp);
        else if (/\.(mp4|webm|ass|srt|mkv)$/i.test(f)) {
          finalFiles.push({ name: path.relative(finalDir, fp).replace(/\\/g, "/"), path: fp, size: fs.statSync(fp).size, type: path.extname(f).slice(1) });
        }
      }
    };
    walkCompose(finalDir);
  }
  artifacts.compose_episode = { available: finalFiles.length > 0, files: finalFiles };

  // Step 8: publish -> publish.yaml + final/gallery/ + final/poster/ + story posters
  const publishFile = path.join(epDir, "publish.yaml");
  const publishFiles: { name: string; path: string; size: number; type: string }[] = [];
  if (fs.existsSync(publishFile)) {
    publishFiles.push({ name: "publish.yaml", path: publishFile, size: fs.statSync(publishFile).size, type: "yaml" });
  }
  // Gallery images
  const galleryDir = path.join(epDir, "final", "gallery");
  if (fs.existsSync(galleryDir)) {
    for (const f of fs.readdirSync(galleryDir)) {
      const fp = path.join(galleryDir, f);
      if (fs.statSync(fp).isFile() && /\.(jpg|jpeg|png|webp)$/i.test(f)) {
        publishFiles.push({ name: `gallery/${f}`, path: fp, size: fs.statSync(fp).size, type: path.extname(f).slice(1) });
      }
    }
  }
  // Episode poster
  const posterDir = path.join(epDir, "final", "poster");
  if (fs.existsSync(posterDir)) {
    for (const f of fs.readdirSync(posterDir)) {
      const fp = path.join(posterDir, f);
      if (fs.statSync(fp).isFile() && /\.(jpg|jpeg|png|webp)$/i.test(f) && !f.startsWith("_")) {
        publishFiles.push({ name: `poster/${f}`, path: fp, size: fs.statSync(fp).size, type: path.extname(f).slice(1) });
      }
    }
  }
  // Story posters (new: poster/, legacy: posters/)
  for (const posterDirName of ["poster", "posters"]) {
    const storyPostersDir = path.join(storyDir, posterDirName);
    if (fs.existsSync(storyPostersDir)) {
      const walkPosters = (dir: string) => {
        for (const f of fs.readdirSync(dir)) {
          const fp = path.join(dir, f);
          if (fs.statSync(fp).isDirectory()) walkPosters(fp);
          else if (/\.(jpg|jpeg|png|webp)$/i.test(f) && !f.startsWith("_") && !f.includes("base")) {
            publishFiles.push({ name: `story_posters/${path.relative(storyPostersDir, fp).replace(/\\/g, "/")}`, path: fp, size: fs.statSync(fp).size, type: path.extname(f).slice(1) });
          }
        }
      };
      walkPosters(storyPostersDir);
    }
  }
  artifacts.publish = {
    available: publishFiles.length > 0,
    files: publishFiles,
  };

  // Also check state.yaml for step completion status
  const stateFile = path.join(epDir, "state.yaml");
  let stepCompletionState: string | null = null;
  if (fs.existsSync(stateFile)) {
    stepCompletionState = fs.readFileSync(stateFile, "utf-8");
  }

  // Strip full paths from response (only expose name, size, type)
  const safeArtifacts: Record<string, { available: boolean; files: { name: string; size: number; type: string }[] }> = {};
  for (const [k, v] of Object.entries(artifacts)) {
    safeArtifacts[k] = { available: v.available, files: v.files.map((f) => ({ name: f.name, size: f.size, type: f.type })) };
  }

  return NextResponse.json({ artifacts: safeArtifacts, state: stepCompletionState });
}
