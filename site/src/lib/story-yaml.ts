// Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
// Licensed under CC BY-NC 4.0. See LICENSE for details.
import fs from "fs";
import path from "path";

/**
 * Detect content language based on CJK character ratio.
 * Mirrors agents/common.py detect_content_language().
 */
function detectContentLanguage(text: string): "zh" | "en" {
  if (!text) return "en";
  let cjkCount = 0;
  let totalAlpha = 0;
  for (const ch of text) {
    const code = ch.codePointAt(0)!;
    const isCJK =
      (code >= 0x4e00 && code <= 0x9fff) ||
      (code >= 0x3400 && code <= 0x4dbf);
    if (isCJK) cjkCount++;
    if (/\p{L}/u.test(ch)) totalAlpha++;
  }
  if (totalAlpha === 0) return "en";
  return cjkCount / totalAlpha > 0.3 ? "zh" : "en";
}

/** Escape a YAML string value — wrap in double quotes if it contains special chars. */
function yamlStr(value: string): string {
  if (!value || value === "TBD") return JSON.stringify(value);
  // Multi-line: use YAML block scalar
  if (value.includes("\n")) {
    const indented = value
      .split("\n")
      .map((line) => "  " + line)
      .join("\n");
    return "|\n" + indented;
  }
  // Single line with special chars
  if (/[:#\[\]{}&*!|>'"%@`]/.test(value) || value.trim() !== value) {
    return JSON.stringify(value);
  }
  return value;
}

export interface StoryData {
  title: string;
  title_zh: string;
  slug: string;
  description: string;
  description_zh: string;
  background: string;
}

const DATA_STORIES = path.resolve(process.cwd(), "..", "data", "stories");

/**
 * Populate story_bible.yaml with actual story data.
 * Preserves the template structure but fills in real values.
 */
export function populateStoryBible(data: StoryData): void {
  const storyDir = path.join(DATA_STORIES, data.slug);
  if (!fs.existsSync(storyDir)) return;

  const lang = detectContentLanguage(data.background || data.description);
  const displayTitle = lang === "zh" ? data.title_zh : data.title;
  const displayDesc = lang === "zh" ? data.description_zh : data.description;

  const content = `# Story Bible - Interactive Short Video Series
# This file defines the world, characters, and ongoing narrative state

# Primary language of this story (auto-detected from content)
# Supported: "zh" (Chinese), "en" (English)
story_language: ${JSON.stringify(lang)}

series:
  title: ${yamlStr(displayTitle || data.title)}
  title_en: ${yamlStr(data.title)}
  title_zh: ${yamlStr(data.title_zh || data.title)}
  genre: "TBD"
  style: "animated, stylized"
  episode_duration_seconds: 120
  target_scenes_per_episode: 8
  description: ${yamlStr(displayDesc || data.description)}
  description_en: ${yamlStr(data.description)}
  description_zh: ${yamlStr(data.description_zh || data.description)}

world:
  setting: "TBD"
  time_period: "TBD"
  rules: []
  locations: []

characters: []
  # - name: "Character Name"
  #   role: protagonist
  #   reference: data/characters/character_name.yaml

narrative:
  current_episode: 0
  arc_summary: ${yamlStr(displayDesc || data.description)}
  pending_threads: []
  resolved_threads: []

background: ${yamlStr(data.background)}

tone:
  visual_style: "TBD"
  color_palette: []
  mood: "TBD"
  music_style: "TBD"
`;

  fs.writeFileSync(path.join(storyDir, "story_bible.yaml"), content, "utf-8");
}

/**
 * Populate style_guide.yaml with story-aware defaults.
 * Only writes if the file doesn't exist or still has template content.
 */
export function populateStyleGuide(data: StoryData): void {
  const storyDir = path.join(DATA_STORIES, data.slug);
  if (!fs.existsSync(storyDir)) return;

  const dest = path.join(storyDir, "style_guide.yaml");
  // Only populate if missing — style_guide is typically hand-tuned
  if (fs.existsSync(dest)) {
    const existing = fs.readFileSync(dest, "utf-8");
    // If it's been customized (not template), leave it alone
    if (!existing.includes('type: "stylized animation"')) return;
  }

  const templatePath = path.join(DATA_STORIES, "_template", "style_guide.yaml");
  if (fs.existsSync(templatePath)) {
    fs.copyFileSync(templatePath, dest);
  }
}

/**
 * Ensure story data directory structure and YAML files exist and are populated.
 * Called on both create and update.
 */
export function syncStoryYaml(data: StoryData): void {
  const storyDir = path.join(DATA_STORIES, data.slug);
  try {
    fs.mkdirSync(path.join(storyDir, "characters"), { recursive: true });
    fs.mkdirSync(path.join(storyDir, "locations"), { recursive: true });
    fs.mkdirSync(path.join(storyDir, "episodes"), { recursive: true });
  } catch {
    // Non-fatal
  }
  populateStoryBible(data);
  populateStyleGuide(data);
}
