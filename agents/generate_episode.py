"""Generate Episode Script

Orchestrates full episode generation by calling LLM with agent instructions
from .claude/agents/*.agent.md as system prompts.

Usage:
    python agents/generate_episode.py --episode <number> --story <slug>
    python agents/generate_episode.py --episode 2 --story my-story --votes data/episodes/1/engagement.yaml
    python agents/generate_episode.py --episode 1 --story my-story --stage script
"""

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for non-ASCII output (Chinese, etc.)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stderr.reconfigure(encoding='utf-8')

import yaml

from common import (
    detect_content_language,
    episode_dir,
    get_project_root,
    get_story_language,
    load_env,
    load_yaml,
    save_yaml,
    setup_logging,
    story_dir,
)
from episode_state import EpisodeState
from llm import call_agent, parse_yaml_response

load_env()
log = setup_logging("generate_episode")

PROJECT_ROOT = get_project_root()


def _char_slug(char: dict) -> str:
    """Generate an ASCII-safe filename slug from a character dict.

    Uses name (lowercase, spaces to underscores) if ASCII-safe,
    otherwise converts to pinyin for Chinese characters.
    """
    name = char.get("name", "") or char.get("name_zh", "") or "unknown"
    # Try ASCII-safe slug from name
    slug = name.lower().replace(" ", "_")
    if slug.isascii() and re.match(r'^[a-z0-9_]+$', slug):
        return slug
    # Non-ASCII name — convert to pinyin
    try:
        from pypinyin import pinyin, Style
        py = pinyin(name, style=Style.NORMAL)
        slug = "_".join(s[0] for s in py if s[0])
        slug = re.sub(r'[^a-z0-9_]', '', slug.lower())
        if slug:
            return slug
    except ImportError:
        pass
    # Fallback: hash-based
    h = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return f"char_{h}"


def _is_seedance_model() -> bool:
    """Check if the configured video model is Seedance (BytePlus)."""
    try:
        cfg = load_yaml(str(PROJECT_ROOT / "config" / "video_generation.yaml"))
        model_name = cfg.get("model", {}).get("name", "")
        return model_name.lower().startswith("seedance")
    except Exception:
        return False


def _clip_duration_specs() -> dict:
    """Return clip duration specifications based on the video model and VIDEO_LENGTH.

    VIDEO_LENGTH env var controls episode duration (default 60s).
    Seedance 2.0 supports up to 10-second clips natively.
    Other models are limited to 3-6 seconds.
    """
    total_seconds = int(os.environ.get("VIDEO_LENGTH", "60"))
    total_seconds = max(30, min(180, total_seconds))  # clamp 30s-180s

    if _is_seedance_model():
        clip_default = 10
        clips_per_scene = 2
        scene_duration = clip_default * clips_per_scene  # 20s
        scenes = max(2, round(total_seconds / scene_duration))
        total_clips = scenes * clips_per_scene
        return {
            "clip_range": "8-10",
            "clip_default": clip_default,
            "scene_range": str(scene_duration),
            "clips_per_scene": str(clips_per_scene),
            "scenes_per_episode": str(scenes),
            "total_clips": str(total_clips),
            "max_total_seconds": total_seconds,
        }
    clip_default = 5
    clips_per_scene = 3
    scene_duration = clip_default * clips_per_scene  # 15s
    scenes = max(2, round(total_seconds / scene_duration))
    total_clips = scenes * clips_per_scene
    return {
        "clip_range": "3-6",
        "clip_default": clip_default,
        "scene_range": str(scene_duration),
        "clips_per_scene": str(clips_per_scene),
        "scenes_per_episode": str(scenes),
        "total_clips": str(total_clips),
        "max_total_seconds": total_seconds,
    }


def load_store() -> dict:
    """Load store.json from site/data/."""
    store_path = PROJECT_ROOT / "site" / "data" / "store.json"
    with open(store_path, encoding="utf-8") as f:
        return json.load(f)


def load_story_bible(story_slug: str | None = None) -> dict:
    """Load the story bible from the story directory."""
    if story_slug:
        return load_yaml(str(story_dir(story_slug) / "story_bible.yaml"))
    return load_yaml("data/story_bible.yaml")


def load_vote_results(path: str) -> dict | None:
    """Load vote results from previous episode."""
    try:
        return load_yaml(path)
    except FileNotFoundError:
        log.info(f"No vote results at {path}, starting fresh.")
        return None


def load_previous_episode_engagement(episode_number: int) -> str:
    """Load vote results and moderated comments from the previous episode via API.

    Fetches data from the website API so the script writer can consider
    audience feedback when generating the next episode.

    Returns formatted text for LLM consumption, or empty string if unavailable.
    """
    prev_ep = episode_number - 1
    if prev_ep < 1:
        return ""

    import urllib.request
    api_base = os.environ.get("SITE_API_URL", "http://localhost:3000")
    parts = []

    # Fetch vote results
    try:
        url = f"{api_base}/api/episodes/{prev_ep}/results"
        req_obj = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req_obj, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("total_votes", 0) > 0:
                results_text = []
                for r in data.get("results", []):
                    results_text.append(f"  - {r['label']}: {r['votes']} votes ({r['percentage']}%)")
                winner = data.get("winner", "N/A")
                parts.append(
                    f"### Episode {prev_ep} Vote Results (total: {data['total_votes']})\n"
                    f"Winner: {winner}\n" + "\n".join(results_text)
                )
    except Exception as e:
        log.debug(f"Could not fetch vote results for episode {prev_ep}: {e}")

    # Fetch moderated comments
    try:
        url = f"{api_base}/api/episodes/{prev_ep}/comments/summary"
        req_obj = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req_obj, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            comments = data.get("moderated_comments", [])
            if comments:
                comment_lines = []
                for c in comments[:20]:  # Limit to 20 comments
                    comment_lines.append(f"  - {c.get('author', 'Anon')}: {c.get('content', '')}")
                parts.append(
                    f"### Episode {prev_ep} Audience Comments ({len(comments)} moderated)\n"
                    + "\n".join(comment_lines)
                )
    except Exception as e:
        log.debug(f"Could not fetch comments for episode {prev_ep}: {e}")

    return "\n\n".join(parts) if parts else ""


def get_episode_context(story_slug: str, episode_number: int) -> dict:
    """Get episode context from store.json (admin_prompt, title, etc)."""
    store = load_store()
    story = next((s for s in store.get("stories", []) if s.get("slug") == story_slug), None)
    if not story:
        return {}
    episode = next(
        (e for e in store.get("episodes", [])
         if e.get("story_id") == story["id"] and e.get("episode_number") == episode_number),
        None,
    )
    if not episode:
        return {}
    return {
        "title": episode.get("title", ""),
        "title_zh": episode.get("title_zh", ""),
        "admin_prompt": episode.get("admin_prompt", ""),
        "admin_prompt_weight": episode.get("admin_prompt_weight", 0.8),
        "story_title": story.get("title", ""),
        "story_description": story.get("description", ""),
        "story_background": story.get("background", ""),
    }


def load_style_guide(story_slug: str) -> str:
    """Load style guide YAML as string."""
    path = story_dir(story_slug) / "style_guide.yaml"
    if path.exists():
        return path.read_text(encoding="utf-8")
    # Fallback to project-level
    fallback = PROJECT_ROOT / "data" / "style_guide.yaml"
    if fallback.exists():
        return fallback.read_text(encoding="utf-8")
    return ""


def load_voice_library() -> tuple[str, set[str]]:
    """Load voice library YAML and return (formatted_text, valid_asset_ids)."""
    path = PROJECT_ROOT / "config" / "voice_library.yaml"
    if not path.exists():
        return "", set()
    data = load_yaml(str(path))
    voices = data.get("voices", [])
    valid_ids = {v["asset_id"] for v in voices if v.get("asset_id")}
    # Format for LLM consumption
    lines = []
    for v in voices:
        lines.append(
            f"- asset_id: \"{v['asset_id']}\"  # {v.get('name', '')} | "
            f"{v.get('gender', '')} | {v.get('age_range', '')} | "
            f"{v.get('language', '')} | {v.get('description', '')}"
        )
    return "\n".join(lines), valid_ids


def get_language_instruction(story_slug: str) -> str:
    """Get a language instruction based on the story's primary language.

    All episodes of the same story should output in the same language.
    Uses the unified get_story_language() from common.py which caches
    the result in story_bible.yaml.
    """
    lang = get_story_language(story_slug)
    if lang == "zh":
        return (
            "## LANGUAGE REQUIREMENT (CRITICAL)\n"
            "The story background is written in Chinese. You MUST output ALL content values "
            "(titles, descriptions, dialogue, visual descriptions, scene titles, mood, "
            "camera notes, voting options, narration, prompts, negative_prompt, subject, "
            "environment, action, transition_in, transition_out, consistency_notes, etc.) in Chinese (中文). "
            "Only keep YAML keys and field names in English. "
            "ALL human-readable string values MUST be in Chinese — no mixing with English."
        )
    return ""


def get_negative_prompt_instruction(story_slug: str) -> str:
    """Return the negative_prompt instruction with prohibited content from content_policy.yaml.

    If the story is not in English, instructs the LLM to translate to the story language.
    """
    # Load prohibited items from content_policy.yaml
    policy_path = Path(__file__).parent.parent / "config" / "content_policy.yaml"
    prohibited_items = []
    if policy_path.exists():
        policy = load_yaml(str(policy_path))
        prohibited_items = policy.get("prohibited", [])
    if not prohibited_items:
        prohibited_items = ["sexual_content", "graphic_violence", "discrimination", "nudity", "weapons"]

    # Format items as human-readable (replace underscores with spaces)
    items_str = ", ".join(item.replace("_", " ") for item in prohibited_items)
    items_str += ", blurry, low quality"

    # Check language
    lang = get_story_language(story_slug)
    if lang != "en" and lang:
        return (
            f"The following items MUST be included in every clip's negative_prompt, "
            f"translated to the story's language: {items_str}"
        )
    return f"Every clip MUST include negative_prompt: \"{items_str}\""


def load_existing_characters(story_slug: str) -> str:
    """Load all existing character YAML files as context."""
    chars_dir = story_dir(story_slug) / "characters"
    if not chars_dir.exists():
        return "No existing characters defined."
    parts = []
    for f in sorted(chars_dir.glob("*.yaml")):
        if f.name == "README.yaml":
            continue
        parts.append(f"### {f.stem}\n```yaml\n{f.read_text(encoding='utf-8')}\n```")
    return "\n\n".join(parts) if parts else "No existing characters defined."


def load_existing_locations(story_slug: str) -> str:
    """Load all existing location YAML files as context."""
    locs_dir = story_dir(story_slug) / "locations"
    if not locs_dir.exists():
        return "No existing locations defined."
    parts = []
    for f in sorted(locs_dir.glob("*.yaml")):
        if f.name == "README.yaml":
            continue
        parts.append(f"### {f.stem}\n```yaml\n{f.read_text(encoding='utf-8')}\n```")
    return "\n\n".join(parts) if parts else "No existing locations defined."


def load_previous_episodes(story_slug: str, current_episode: int) -> str:
    """Load summaries (preferred) or scripts from all previous episodes for continuity.

    Checks multiple locations for final_summary.yaml:
    1. ep_dir/final/final_summary.yaml (published output folder)
    2. ep_dir/final_summary.yaml (promoted from temp)
    3. ep_dir/temp_final_summary.yaml (composed but not yet published)
    4. ep_dir/script.yaml (fallback to original script)
    """
    if current_episode <= 1:
        return "This is the first episode. No previous episodes exist."

    parts = []
    base = story_dir(story_slug) / "episodes"
    for ep_num in range(1, current_episode):
        ep_path = base / str(ep_num)
        # Prefer final/final_summary > final_summary > temp_final_summary > script
        final_folder_summary = ep_path / "final" / "final_summary.yaml"
        summary_path = ep_path / "final_summary.yaml"
        temp_summary_path = ep_path / "temp_final_summary.yaml"
        script_path = ep_path / "script.yaml"
        if final_folder_summary.exists():
            content = final_folder_summary.read_text(encoding="utf-8")
            parts.append(f"### Episode {ep_num} Summary (Published — from final folder)\n```yaml\n{content}\n```")
        elif summary_path.exists():
            content = summary_path.read_text(encoding="utf-8")
            parts.append(f"### Episode {ep_num} Summary (Published)\n```yaml\n{content}\n```")
        elif temp_summary_path.exists():
            content = temp_summary_path.read_text(encoding="utf-8")
            parts.append(f"### Episode {ep_num} Summary (Draft)\n```yaml\n{content}\n```")
        elif script_path.exists():
            content = script_path.read_text(encoding="utf-8")
            parts.append(f"### Episode {ep_num} Script\n```yaml\n{content}\n```")
        else:
            parts.append(f"### Episode {ep_num}\n(No data available)")

    if not parts:
        return "No previous episode data found."

    return "\n\n".join(parts)


def generate_script_with_llm(
    episode_number: int,
    story_slug: str,
    story_bible: dict,
    votes: dict | None,
    model_override: str | None = None,
) -> dict:
    """Call writer agent via LLM to generate an episode script."""
    episode_context = get_episode_context(story_slug, episode_number)

    if not episode_context.get("admin_prompt"):
        log.error("No admin_prompt found for this episode in store.json")
        sys.exit(1)

    specs = _clip_duration_specs()
    style_guide = load_style_guide(story_slug)
    characters = load_existing_characters(story_slug)
    previous_episodes = load_previous_episodes(story_slug, episode_number)
    language_instruction = get_language_instruction(story_slug)

    # Auto-load audience engagement (votes + comments) from previous episode
    engagement = load_previous_episode_engagement(episode_number)

    user_message = f"""Generate a full episode script for Episode {episode_number}.

## Story Info
- Title: {episode_context.get('story_title', '')}
- Description: {episode_context.get('story_description', '')}

## Story Background
{episode_context.get('story_background', '')}

## Story Bible
```yaml
{yaml.dump(story_bible, default_flow_style=False, allow_unicode=True)}
```

## Style Guide
```yaml
{style_guide}
```

## Existing Characters
{characters}

## Previous Episodes (continue the storyline from where the last episode ended)
{previous_episodes}

## Episode Direction (Admin Prompt, weight={episode_context.get('admin_prompt_weight', 0.8)})
{episode_context.get('admin_prompt', '')}

## Previous Vote Results
{yaml.dump(votes, default_flow_style=False, allow_unicode=True) if votes else "No CLI vote file provided."}

## Audience Engagement from Previous Episode (votes + comments auto-loaded from website)
{engagement if engagement else "No previous engagement data available (first episode or site unreachable)."}

## IMPORTANT: Consider the audience vote winner and comments when shaping this episode's story direction.
## The winning vote option should strongly influence the plot. Audience comments reveal what they liked,
## disliked, and hope for — weave those sentiments into the story naturally.

{language_instruction}

## Narrative Structure (MANDATORY — this is what makes or breaks engagement)

### Story Density
- Every scene MUST advance the plot. Zero filler. Zero "establishing mood" scenes with no action.
- Each scene introduces at least ONE of: new information, a conflict, a reversal, a choice, or a consequence.
- Characters must WANT something in every scene — and something must BLOCK them.
- Show, don't tell. Replace exposition with action, discovery, or confrontation.
- Compress time aggressively: skip mundane transitions, cut straight to the moment things change.

### Emotional Hooks (apply at least 3 per episode)
- **Mystery gap**: Reveal PART of a secret early — make the audience desperate to know the rest.
- **Ticking clock**: Introduce urgency — a deadline, a countdown, a "before it's too late" pressure.
- **Betrayal/twist**: Someone or something is not what it appears. Plant the seed early, reveal late.
- **Impossible dilemma**: Force the protagonist into a choice where BOTH options have painful consequences.
- **Dramatic irony**: Let the audience know something the character doesn't — creates unbearable tension.
- **Emotional whiplash**: A moment of hope immediately followed by disaster (or vice versa).

### Escalation Pattern (scene by scene)
1. **Opening hook** (Scene 1): Start IN THE MIDDLE of action or conflict. Never start calm. The first 5 seconds must grab attention.
2. **Deepening** (Scenes 2-3): Raise stakes. What seemed simple becomes complicated. New obstacles appear.
3. **Midpoint twist** (Scene 4): A revelation that CHANGES everything. The audience must rethink what they assumed.
4. **Acceleration** (Scenes 5-6): Events spiral. Multiple threads converge. Tension becomes almost unbearable.
5. **Cliffhanger peak** (Final scene): End at MAXIMUM tension. The worst possible moment to stop watching.

### Cliffhanger Requirements (Final Scene)
- The episode MUST end at the PEAK of a crisis — NOT after resolution, NOT during a lull.
- Use one of these proven patterns:
  - A character discovers something shocking (but we don't see their reaction)
  - A threat arrives at the worst possible moment
  - A choice is forced and the character reaches for their decision — cut to black
  - A trusted ally does something inexplicable
  - The protagonist's plan succeeds... but reveals a WORSE problem
- The final visual frame should be emotionally charged: a face in shock, a hand reaching, a shadow appearing.
- The audience should feel PHYSICALLY uncomfortable that it ended there.

### Voting Options
- The voting_options MUST present genuinely different story directions that the audience would be excited to debate.
- Each option should feel like it could lead to a COMPLETELY different next episode.
- At least one option should be the "risky/unexpected" choice that tempts the audience.
- Options should NOT be obvious "good vs bad" — all options must have interesting consequences.

## Physical Realism (MANDATORY)

## Content Richness (MANDATORY — THIS IS CRITICAL)
- The visual_description for EACH scene MUST be a rich, detailed, beat-by-beat description.
- MINIMUM 3-5 sentences per scene. For longer scenes (15s+), write 5-8 sentences.
- Describe SPECIFIC actions: "Xiaoxi reaches for the glowing crystal, her fingers trembling as blue light
  pulses from within. The crystal suddenly cracks, sending a shockwave that ripples through the water around
  her feet. She stumbles backward, catching herself on the ancient stone pillar as dust cascades from the
  ceiling above."
- BAD example (too thin): "Xiaoxi finds a crystal in the cave." ← NEVER do this.
- GOOD example (content-rich): "Xiaoxi crouches beside a jagged rock formation deep in the cave, her
  lantern casting long shadows across the dripping walls. She notices a faint blue glow pulsing from a crack
  in the stone — a crystal embedded in the rock face. She carefully chips away the surrounding stone with
  her knife, each strike echoing through the cavern. As the crystal loosens, the blue light intensifies
  dramatically, illuminating her wide-eyed expression. She pulls it free, and the entire cave trembles —
  stalactites sway overhead, and a low rumble builds from deep underground."
- The total story content MUST fill the full {specs['max_total_seconds']}s episode duration. Every second
  must have meaningful visual action described. Thin descriptions create boring, empty video clips.
- Each clip (3-6s) will be generated from the visual_description — if the description is too thin,
  the AI video model has nothing to work with and produces static, lifeless output.
- Dialogue lines should feel natural and advance the plot — no filler lines, no exposition dumps.
- All actions, movements, and events MUST obey real-world physics: gravity, inertia, momentum, weight, balance.
- Objects fall at realistic speeds, liquids flow naturally, hair/cloth moves with wind/motion realistically.
- Characters cannot teleport, float without reason, or defy physics unless explicitly supernatural in the story.
- Lighting must be consistent with the time of day and light sources described.
- Scale and proportions must remain consistent within and across scenes.

## Scene Transitions (MANDATORY)
- When location changes between scenes, the script MUST include a motivated transition:
  - A character must SAY or DO something that bridges the two locations (dialogue intent, physical movement, or a time cue).
  - Example: if Scene 1 is indoors and Scene 2 is outdoors, Scene 1 should end with the character deciding to leave, or Scene 2 should start with the character arriving.
- Characters CANNOT teleport — the audience must understand HOW and WHY they moved.
- When time jumps occur (day→night), include a visual or dialogue cue in the scene description.

## Video Specifications (STRICTLY ENFORCE)
- Episode TOTAL duration: EXACTLY {specs['max_total_seconds']} seconds ({specs['max_total_seconds'] // 60}m{specs['max_total_seconds'] % 60:02d}s). The last scene's time_range MUST end at or before {specs['max_total_seconds'] // 60}:{specs['max_total_seconds'] % 60:02d}.
- Clip duration range: {specs['clip_range']}s. Default: {specs['clip_default']}s. You MAY vary per clip.
- BUDGET MATH (you MUST follow this):
  - Total budget: {specs['max_total_seconds']}s
  - Clip duration: {specs['clip_range']}s each (default {specs['clip_default']}s)
  - Target: {specs['scenes_per_episode']} scenes × {specs['clips_per_scene']} clips = ~{specs['total_clips']} clips
  - Each scene gets {specs['clips_per_scene']} clips ({specs['scene_range']}s per scene)
- HARD RULE: the SUM of all clip duration_seconds MUST NOT exceed {specs['max_total_seconds']}s. If it does, REDUCE clip count or shorten clips.
- Prefer FEWER clips per scene to minimize visual inconsistency between clips.
- The sum of all scene duration_seconds MUST equal exactly {specs['max_total_seconds']}.
- All time_range values MUST fit within 0:00 to {specs['max_total_seconds'] // 60}:{specs['max_total_seconds'] % 60:02d}. Do NOT exceed {specs['max_total_seconds'] // 60}:{specs['max_total_seconds'] % 60:02d}.

## Output Requirements
Output ONLY valid YAML (no markdown fences, no explanation) in this exact structure:

episode: {episode_number}
title: "<english title>"
title_zh: "<chinese title>"
duration_seconds: {specs['max_total_seconds']}
scene_count: <{specs['scenes_per_episode']}>
scenes:
  - scene_number: 1
    title: "<scene title>"
    time_range: "0:00-0:15"
    duration_seconds: 15
    location: "<location description>"
    time_of_day: "<day/night/dawn/etc>"
    characters_present:
      - "<character name>"
    visual_description: "<RICH beat-by-beat description of what happens visually. Describe each action, character expression, environmental change, and key object interaction in detail. MINIMUM 3-5 sentences. Must be specific enough for AI video generation — every second of the scene must have visual content described. Thin/vague descriptions are REJECTED.>"
    dialogue:
      - character: "<name>"
        line: "<what they say>"
        tone: "<delivery style>"
    camera_notes: "<camera angles, movements, transitions>"
    mood: "<emotional tone>"
    music_notes: "<music/sfx direction>"
  # ... more scenes (last scene's time_range MUST end at or before {specs['max_total_seconds'] // 60}:{specs['max_total_seconds'] % 60:02d})
voting_options:
  - id: "a"
    label: "<option text>"
    description: "<what this choice leads to>"
  - id: "b"
    label: "<option text>"
    description: "<what this choice leads to>"
  - id: "c"
    label: "<option text>"
    description: "<what this choice leads to>"
tone:
  visual_style: "<style description>"
  color_palette: ["<color1>", "<color2>", ...]
  mood: "<overall mood>"
  music_style: "<music direction>"
"""

    log.info(f"Episode context: {episode_context.get('title', 'untitled')}")
    raw_text = call_agent("writer", user_message, model_override=model_override)

    try:
        script = parse_yaml_response(raw_text)
    except (ValueError, Exception) as e:
        log.error(f"Failed to parse LLM output as YAML: {e}")
        log.error(f"Raw output (first 500 chars): {raw_text[:500]}")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_dir = episode_dir(episode_number, story_slug) / "script" / ts
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / "raw_output.txt"
        debug_path.write_text(raw_text, encoding="utf-8")
        log.error(f"Raw LLM output saved to {debug_path}")
        sys.exit(1)

    log.info(f"Script generated: {script.get('title', 'untitled')} with {len(script.get('scenes', []))} scenes")

    # Post-generation validation: enforce target duration
    _enforce_script_duration(script, target=specs['max_total_seconds'])

    return script


def _enforce_script_duration(script: dict, target: int = 120) -> None:
    """Fix scene time_ranges and durations to fit within the target duration.

    If the LLM generated scenes that exceed the target, proportionally scale
    all scene durations down to fit exactly within the target.
    """
    scenes = script.get("scenes", [])
    if not scenes:
        return

    total_duration = sum(s.get("duration_seconds", 0) for s in scenes)
    if total_duration <= 0:
        return

    if total_duration <= target * 1.1:  # Within 10% tolerance
        # Just fix time_ranges to be consistent with duration_seconds
        elapsed = 0
        for scene in scenes:
            dur = scene.get("duration_seconds", 15)
            start_min, start_sec = divmod(int(elapsed), 60)
            end_min, end_sec = divmod(int(elapsed + dur), 60)
            scene["time_range"] = f"{start_min}:{start_sec:02d}-{end_min}:{end_sec:02d}"
            elapsed += dur
        return

    # Scale durations proportionally to fit within target
    log.warning(f"Script total duration {total_duration}s exceeds target {target}s. Scaling down.")
    scale = target / total_duration
    elapsed = 0
    for scene in scenes:
        dur = max(10, int(scene.get("duration_seconds", 15) * scale))
        scene["duration_seconds"] = dur
        start_min, start_sec = divmod(int(elapsed), 60)
        end_min, end_sec = divmod(int(elapsed + dur), 60)
        scene["time_range"] = f"{start_min}:{start_sec:02d}-{end_min}:{end_sec:02d}"
        elapsed += dur

    script["duration_seconds"] = int(elapsed)
    log.info(f"Adjusted script: {len(scenes)} scenes, total {int(elapsed)}s")


def generate_scenes_with_llm(episode_number: int, story_slug: str, model_override: str | None = None) -> dict:
    """Call director agent via LLM to plan scenes with visual prompts."""
    ep_dir = episode_dir(episode_number, story_slug)
    script_path = ep_dir / "script.yaml"
    if not script_path.exists():
        log.error(f"Script not found at {script_path}. Run 'script' stage first.")
        sys.exit(1)

    script = load_yaml(str(script_path))
    episode_context = get_episode_context(story_slug, episode_number)
    specs = _clip_duration_specs()
    style_guide = load_style_guide(story_slug)
    characters = load_existing_characters(story_slug)
    locations = load_existing_locations(story_slug)
    previous_episodes = load_previous_episodes(story_slug, episode_number)
    language_instruction = get_language_instruction(story_slug)
    negative_prompt_instruction = get_negative_prompt_instruction(story_slug)

    # Load audience engagement from previous episode for reference
    engagement = load_previous_episode_engagement(episode_number)

    # Extract expected values from script for validation (needed in prompt)
    expected_scene_count = script.get("scene_count", len(script.get("scenes", [])))
    expected_total_duration = script.get("duration_seconds", 120)
    script_scene_durations = {s.get("scene_number", i + 1): s.get("duration_seconds", 0) for i, s in enumerate(script.get("scenes", []))}

    user_message = f"""Break down this episode script into detailed scene-by-scene video generation prompts.

## Episode Script
```yaml
{yaml.dump(script, default_flow_style=False, allow_unicode=True)}
```

## Previous Episodes (for visual continuity reference)
{previous_episodes}

## Story Context
- Title: {episode_context.get('story_title', '')}
- Description: {episode_context.get('story_description', '')}
- Background: {episode_context.get('story_background', '')}

## Episode Direction (Admin Prompt — the user's creative vision for this episode)
{episode_context.get('admin_prompt', 'No episode direction provided.')}

## Audience Engagement from Previous Episode (votes + comments — for reference, script already incorporates these)
{engagement if engagement else 'No previous engagement data available.'}

## Style Guide
```yaml
{style_guide}
```

## Character References (include prompt_keywords in every clip featuring them)
{characters}

## Location References
{locations}

## Video Specifications (STRICTLY ENFORCE — violations will be rejected)
- Episode total: {specs['max_total_seconds']}s. Default clip duration: {specs['clip_default']}s.
- Clip duration range: {specs['clip_range']}s. You MAY vary clip durations within this range to fit the budget.
- Target: {specs['clips_per_scene']} clips per scene ({specs['scene_range']}s per scene). Prefer FEWER clips to minimize visual inconsistency.
- HARD RULE: the SUM of all clip duration_seconds MUST NOT exceed {specs['max_total_seconds']}s. Count carefully. If over budget, reduce clip count or shorten individual clips.
- Each clip MUST have `duration_seconds` set to a value within {specs['clip_range']}s
- Clip N+1 MUST reference last frame of clip N for continuity
- Resolution: 720p, FPS: 24, Aspect ratio: 9:16 (vertical)
- {negative_prompt_instruction}
- Use `duration_seconds` as the field name for clip duration (NOT `duration`)
- CRITICAL: The `prompt` field MUST describe a rich SEQUENCE of actions that fill the clip's full duration_seconds. A static description is INVALID.
- Each clip MUST include `dialogue` (character lines spoken during the clip) and/or `narration` (voiceover text). Silent clips are only acceptable for purely atmospheric moments.
- `dialogue` entries must specify WHO says WHAT and their emotional tone. These will be used for voice generation.
- `narration` is for narrator voiceover — use it to fill gaps where no character speaks, or to provide internal monologue.
- `sound_effects` should list key ambient and action sounds that make the scene feel alive.
- Each clip prompt should include:
  1. Opening state (what we see at the start of the clip)
  2. Main action sequence (describe as many progressive actions as needed to fill the duration — more actions for longer clips)
  3. Character micro-expressions and gestures (eyebrow raise, hand gesture, head turn, etc.)
  4. Environmental motion (wind, light changes, background activity, particles)
  5. Ending state (where the clip leaves off for the next clip to continue from)
- Think of each clip as a MINI-SCENE with a beginning, middle, and end — NOT a photograph.
- IMPORTANT: each scene's total clip durations MUST NOT exceed its target_duration. For example, if target_duration is 20s, do NOT create 4 clips of 10s (=40s). Instead use 2 clips of 10s, or 3 clips of 8s, etc.
- BAD example (too static): "小溪坐在桌前打字，灯光昏暗"
- GOOD example (action-filled): "小溪快速敲击键盘，代码在屏幕上飞速滚动，她的手指突然停住——屏幕闪烁后弹出错误提示。她皱眉用手推了一下眼镜，深吸一口气，然后抬头看向窗外，窗帘被夜风轻轻吹动。台灯在桌面投下暖黄色光圈，咖啡杯里的热气缓缓升腾。"

## Clip Timeline (MANDATORY for every clip)
- Every clip MUST include a `timeline` array that breaks down the clip into 2-3 second segments.
- Each segment specifies: time range, detailed action, characters visible, location details, dialogue (with mood/speed/expression), and camera angle.
- The timeline is the PRIMARY source of truth for what happens in the clip. The `prompt`, `action`, and `subject` fields should be summaries of the timeline.
- Example for a 10-second clip:
  ```yaml
  timeline:
    - time: "[00:00 to 00:03]"
      detail: "小溪快速敲击键盘，代码在屏幕上滚动，手指突然停住"
      characters: "小溪: 黑色齐肩短发，戴眼镜，穿白色T恤，坐在办公椅上，身体前倾"
      location: "深夜卧室书桌前，台灯发出暖黄光，背景有书架和窗户"
      dialogue: "小溪(专注，语速快，皱眉): '再跑一次单元测试...'"
      camera: "中景，略俯，从右侧拍摄"
    - time: "[00:03 to 00:06]"
      detail: "屏幕闪烁弹出错误提示，小溪推了一下眼镜叹气"
      characters: "小溪: 表情从专注变为沮丧，用右手推眼镜，左手离开键盘"
      location: "同一书桌，屏幕发出红色光芒反射在脸上"
      dialogue: "小溪(沮丧，语速慢，闭眼叹气): '又出bug了...'"
      camera: "特写脸部，缓慢推进"
    - time: "[00:06 to 00:10]"
      detail: "小溪转头看向窗外，窗帘被风轻吹，月光洒入"
      characters: "小溪: 侧脸朝窗户方向，眼神中有一丝好奇"
      location: "窗户方向，窗帘飘动，窗外可见月亮和远处屋顶"
      dialogue: "(沉默，只有风声)"
      camera: "跟随视线从小溪侧脸摇到窗户"
  ```

## Action and Dialogue Density (CRITICAL — clips with thin content will be REJECTED)
- The `prompt` field MUST be at LEAST 3 sentences long (more is better). Each sentence should describe a distinct action, reaction, or environmental change.
- Characters MUST speak or think aloud. Main characters should have inner monologue (self-talk, muttering, exclamations) woven into the action. Example: 小溪盯着屏幕喃喃自语："这个bug到底藏在哪里..." 她揉了揉太阳穴，突然眼睛一亮："等等，是不是这里的引用出了问题？"
- Supporting characters should react verbally too: gasps, questions, exclamations.
- The `action` field must list at LEAST 3 distinct sequential actions separated by commas or periods.
- BAD action (too thin): "小溪看向窗外"
- GOOD action (rich): "小溪转头看向窗外，眼神中闪过一丝惊讶。她放下手中的咖啡杯，站起身走向窗边，用手掀开窗帘一角。窗外的蓝白光越来越亮，她不自觉地后退一步，回头看了一眼笔记本电脑的屏幕"
- Every clip should make the audience feel they are watching a real moment with sounds, speech, and physical detail — NOT reading a script summary.

## Scene Transitions (MANDATORY — no teleportation between scenes)
- When the LOCATION changes between scenes, the transition MUST be motivated:
  - A character says they need to go somewhere, or decides to leave
  - Show the character physically moving: opening a door, walking out, getting into a vehicle
  - Use a transitional clip at the END of the previous scene or START of the next scene showing the journey
- When the TIME changes between scenes (day→night, morning→afternoon), show visual cues:
  - A time-lapse of sky changing, clock hands moving, sun/moon position shifting
  - Or a dialogue/narration line indicating time has passed ("三小时后..." / "Later that evening...")
- Characters cannot appear in a new location without the audience seeing HOW they got there.
- The LAST clip of scene N and the FIRST clip of scene N+1 must share a logical connection:
  - Same character in both, or a visual/audio bridge (e.g., sound carries over, camera follows movement)
  - The transition_out of scene N's final clip must set up the transition_in of scene N+1's first clip
- Examples of GOOD transitions:
  - Scene 1 ends: character grabs coat and walks toward door → Scene 2 starts: character steps outside into street
  - Scene 1 ends: character says "我们去找他" → Scene 2 starts: characters arriving at destination
  - Scene 1 ends: character falls asleep at desk → Scene 2 starts: morning light wakes character
- Examples of BAD transitions (FORBIDDEN):
  - Scene 1: character in bedroom → Scene 2: character suddenly in forest (no explanation)
  - Scene 1: daytime conversation → Scene 2: nighttime different location (no time bridge)

## Physical Realism (MANDATORY for all clip prompts)
- Every clip MUST depict physically plausible motion: gravity pulls objects down, thrown items follow arcs, hair/cloth reacts to wind/movement.
- Characters must show weight and balance — feet planted on ground, bodies leaning into turns, realistic reaction times.
- Lighting direction and shadows MUST be consistent with the described light sources (sun position, lamps, etc.).
- Object scale must remain constant — a character cannot be taller than a building in one clip and shorter in the next.
- Include physics cues in each clip prompt: describe HOW things move, not just WHAT moves (e.g., "hair flows backward from the wind" not just "windy").
- Negative prompts MUST include: "defying gravity, floating without reason, inconsistent shadows, objects passing through each other, unnatural body proportions"

## Narrative Tension (for final scene)
- The LAST scene's final clip MUST end at the peak of tension — mid-action, mid-revelation, or at a moment of maximum suspense.
- Do NOT resolve the conflict in the final clip. Leave the audience desperate to know what happens next.

## Quality Criteria (include per scene)
- required_elements: what MUST be visible
- forbidden_elements: what must NOT appear
- motion_expectation: static/subtle/moderate/dynamic
- lighting_consistency: anchor for cross-clip checks
- camera_continuity: how camera relates to previous clip

{language_instruction}

## Output Requirements
- Generate EXACTLY {expected_scene_count} scenes (matching the script). Do NOT add extra scenes beyond the script.
- BUDGET CHECK: sum of ALL clip duration_seconds must be ≤ {specs['max_total_seconds']}s. Each clip: {specs['clip_range']}s. If over budget, reduce clip count or shorten clips.
- Output ONLY valid YAML (no markdown fences, no explanation). Follow the scene_prompt format from your instructions.

scenes:
  - scene_number: 1
    total_clips: <{specs['clips_per_scene']}>
    target_duration: <{specs['scene_range']}>
    style: "<from style guide>"
    character_refs: ["<character names in scene>"]
    location_ref: "<location>"
    clips:
      - clip_number: 1
        duration_seconds: <{specs['clip_range']}s — choose based on action needed>
        timeline:
          - time: "[00:00 to 00:02]"
            detail: "<What happens in this time range — character actions, facial expressions, gestures>"
            characters: "<Who is visible, what they look like, posture and orientation>"
            location: "<Where — specific area of the set, background elements visible>"
            dialogue: "<Exact line spoken, with (mood, speed, expression) annotation, e.g. 小溪(惊讶，语速快，瞪大眼): '这是什么地方？!'>"
            camera: "<Camera angle and movement, e.g. medium close-up, slowly dolly in>"
          - time: "[00:02 to 00:05]"
            detail: "<Next beat of action>"
            characters: "<Updated character state>"
            location: "<Any location change or new elements revealed>"
            dialogue: "<Next line or (silence) if no speech>"
            camera: "<Camera change or continuation>"
          - time: "[00:05 to 00:08]"
            detail: "<Clip conclusion — setup for next clip>"
            characters: "<Final character positions>"
            location: "<Final visible environment>"
            dialogue: "<Final line or reaction>"
            camera: "<Final camera position>"
        subject: "<detailed character and action description — summary of timeline>"
        environment: "<setting, time of day, atmosphere, environmental motion>"
        camera: "<primary angle and movement for the full clip>"
        action: "<sequential actions filling the clip duration — summary>"
        prompt: "<Rich description of a SEQUENCE of actions that fills the clip's duration_seconds. More actions for longer clips. Example: 年轻女性快速敲击键盘，代码在全息投影上飞速滚动。突然屏幕闪烁弹出红色错误提示，她的手指停在半空中。她皱眉推了一下黑框眼镜，深吸一口气向后靠在椅背上。桌上咖啡杯里的热气缓缓升腾，台灯投下暖黄色光圈。她缓缓转头看向窗外，窗帘被夜风轻轻吹动，月光洒在地板上。>"
        dialogue:
          - character: "<who speaks>"
            line: "<what they say>"
            emotion: "<calm/angry/surprised/thoughtful/excited/etc.>"
            speed: "<slow/normal/fast>"
            expression: "<facial expression: smile/frown/wide-eyed/etc.>"
          - character: "<who speaks>"
            line: "<response>"
            emotion: "<emotion>"
            speed: "<speed>"
            expression: "<expression>"
        narration: "<narrator voiceover text for this clip, if any — use for internal monologue, scene-setting, or time transitions>"
        sound_effects:
          - "<key sound: e.g. keyboard typing, wind blowing, door creaking>"
          - "<ambient: e.g. cricket chirping, city hum, rain pattering>"
        negative_prompt: "<prohibited content in story language>"
        transition_in: "<opening state - what we see at frame 1>"
        transition_out: "<ending state - what the last frame shows, for next clip to continue>"
      - clip_number: 2
        subject: "<continuation - starts exactly where clip 1 ended>"
        ...
    mood: "<color palette, lighting mood>"
    quality_criteria:
      required_elements: ["<what must be visible>"]
      forbidden_elements: ["<what must not appear>"]
      motion_expectation: "<static/subtle/moderate/dynamic>"
      lighting_consistency: "<lighting anchor>"
  # ... more scenes
consistency_notes: "<key visual anchors across all scenes>"
"""

    log.info(f"Generating scene breakdowns for Episode {episode_number}...")

    # HuggingFace caps at 8192 max_tokens. Use continuation calls if output is incomplete.
    MAX_TOKENS = 8192
    max_continuations = 3

    def is_scene_complete(scene: dict) -> bool:
        """Check if a scene has all required fields and at least one complete clip."""
        clips = scene.get("clips", [])
        if not clips:
            return False
        # Check last clip has required fields (subject + duration in either key name)
        last_clip = clips[-1]
        has_duration = last_clip.get("duration_seconds") or last_clip.get("duration")
        return bool(last_clip.get("subject") and has_duration)

    def normalize_scenes(scenes: list) -> list:
        """Normalize scene/clip data to use consistent field names and enforce budget.
        Respects per-clip duration from scene YAML; clamps to model min/max.
        Enforces per-scene target_duration AND total episode budget."""
        specs = _clip_duration_specs()
        clip_default = specs["clip_default"]
        max_total = specs["max_total_seconds"]
        # Parse clip_range for min/max (e.g. "8-10" → 8, 10)
        clip_range = specs["clip_range"]
        if "-" in str(clip_range):
            clip_min, clip_max = [int(x) for x in str(clip_range).split("-")]
        else:
            clip_min = clip_max = int(clip_range)

        for scene in scenes:
            for clip in scene.get("clips", []):
                # Normalize 'duration' → 'duration_seconds'
                if "duration" in clip and "duration_seconds" not in clip:
                    clip["duration_seconds"] = clip.pop("duration")
                # If no duration set, use default
                if not clip.get("duration_seconds"):
                    clip["duration_seconds"] = clip_default
                # Clamp to model capability range
                clip["duration_seconds"] = max(clip_min, min(clip_max, clip["duration_seconds"]))

        # --- Per-scene enforcement: trim clips that exceed scene target_duration ---
        for scene in scenes:
            target = scene.get("target_duration")
            if not target:
                continue
            clips = scene.get("clips", [])
            scene_dur = sum(c.get("duration_seconds", clip_default) for c in clips)
            while scene_dur > target and len(clips) > 1:
                removed = clips.pop()
                scene_dur -= removed.get("duration_seconds", clip_default)
                log.info(f"  Per-scene trim: removed clip {removed.get('clip_number', '?')} from scene {scene.get('scene_number', '?')} "
                         f"({removed.get('duration_seconds', clip_default)}s) — scene was {scene_dur + removed.get('duration_seconds', clip_default)}s vs target {target}s")
            scene["total_clips"] = len(clips)
            scene["target_duration"] = sum(c.get("duration_seconds", clip_default) for c in clips)

        # --- Episode-level enforcement: trim if total exceeds budget ---
        total_duration = sum(
            clip.get("duration_seconds", clip_default)
            for scene in scenes
            for clip in scene.get("clips", [])
        )

        if total_duration > max_total:
            log.warning(f"Scene plan total {total_duration}s exceeds {max_total}s budget. Trimming clips.")
            while True:
                current_total = sum(
                    clip.get("duration_seconds", clip_default)
                    for scene in scenes
                    for clip in scene.get("clips", [])
                )
                if current_total <= max_total:
                    break
                # Find scene with most clips and remove its last clip
                scenes_by_clips = sorted(scenes, key=lambda s: len(s.get("clips", [])), reverse=True)
                trimmed = False
                for s in scenes_by_clips:
                    if len(s.get("clips", [])) > 1:
                        removed = s["clips"].pop()
                        log.info(f"  Trimmed clip {removed.get('clip_number', '?')} from scene {s.get('scene_number', '?')} ({removed.get('duration_seconds', clip_default)}s)")
                        trimmed = True
                        break
                if not trimmed:
                    break

            # Update total_clips and target_duration fields
            for s in scenes:
                s["total_clips"] = len(s.get("clips", []))
                s["target_duration"] = sum(c.get("duration_seconds", clip_default) for c in s.get("clips", []))

        return scenes

    def extract_complete_scenes(parsed: dict) -> list:
        """Return only fully-complete scenes, discarding any truncated last scene."""
        scenes = parsed.get("scenes", [])
        if not scenes:
            return []
        # All scenes except possibly the last are complete (they were followed by another scene)
        complete = scenes[:-1] if len(scenes) > 1 else []
        # Check if the last scene is complete
        if scenes and is_scene_complete(scenes[-1]):
            complete.append(scenes[-1])
        return complete

    def _salvage_partial_yaml(text: str) -> dict | None:
        """Try to extract complete scenes from truncated YAML by trimming from the end."""
        import re as _re
        _text = text.strip()
        # Remove markdown fences if present
        _fence = _re.search(r"```(?:yaml|yml)?\s*\n(.*)", _text, _re.DOTALL)
        if _fence:
            _text = _fence.group(1).strip()
        # Remove trailing ``` if present
        if _text.endswith("```"):
            _text = _text[:-3].strip()
        # Find all "- scene_number:" positions to know where each scene starts
        scene_starts = [m.start() for m in _re.finditer(r"^\s{2,4}- scene_number:", _text, _re.MULTILINE)]
        if not scene_starts:
            return None
        # For single scene: try trimming incomplete clip entries from the end
        if len(scene_starts) == 1:
            # Find all clip_number markers within the scene
            clip_starts = [m.start() for m in _re.finditer(r"^\s{6,8}- clip_number:", _text, _re.MULTILINE)]
            if len(clip_starts) >= 2:
                # Try progressively removing the last clip(s)
                for i in range(len(clip_starts) - 1, 0, -1):
                    truncated = _text[:clip_starts[i]].rstrip()
                    try:
                        data = yaml.safe_load(truncated)
                        if isinstance(data, dict) and "scenes" in data and data["scenes"]:
                            return data
                    except Exception:
                        continue
            return None
        # Multi-scene: try parsing with progressively fewer scenes (drop the last N)
        for i in range(len(scene_starts) - 1, 0, -1):
            truncated = _text[:scene_starts[i]].rstrip()
            try:
                data = yaml.safe_load(truncated)
                if isinstance(data, dict) and "scenes" in data and data["scenes"]:
                    return data
            except Exception:
                continue
        return None

    # First call
    raw_text = call_agent("director", user_message, max_tokens=MAX_TOKENS, model_override=model_override)

    # Collect all complete scenes across calls
    all_complete_scenes: list = []
    consistency_notes = ""

    for attempt in range(max_continuations + 1):
        # Try to parse — handle both dict with scenes: key AND bare list of scenes
        parsed = None
        try:
            parsed = parse_yaml_response(raw_text)
        except (ValueError, Exception) as e:
            # parse_yaml_response fails if result is a list (bare scene list from LLM)
            # Try parsing as bare YAML list and wrap it
            try:
                import re as _re
                _text = raw_text.strip()
                # Strip markdown fences (greedy — take everything after opening fence)
                _fence = _re.search(r"```(?:yaml|yml)?\s*\n(.*)", _text, _re.DOTALL)
                if _fence:
                    _text = _fence.group(1).strip()
                # Remove trailing ``` if present
                if _text.endswith("```"):
                    _text = _text[:-3].strip()
                bare_data = yaml.safe_load(_text)
                if isinstance(bare_data, list) and bare_data and isinstance(bare_data[0], dict) and "scene_number" in bare_data[0]:
                    parsed = {"scenes": bare_data}
                    log.info(f"Parsed continuation as bare scene list ({len(bare_data)} scenes)")
                elif isinstance(bare_data, dict) and "scenes" in bare_data:
                    parsed = bare_data
                    log.info(f"Parsed continuation after fence stripping ({len(bare_data.get('scenes', []))} scenes)")
            except Exception:
                pass

            if parsed is None:
                # Try to salvage complete scenes from truncated YAML
                salvaged = _salvage_partial_yaml(raw_text)
                if salvaged:
                    parsed = salvaged
                    log.info(f"Salvaged {len(salvaged.get('scenes', []))} scenes from truncated YAML")
                else:
                    log.warning(f"YAML parse failed on attempt {attempt}: {e}")
                    break

        # Extract complete scenes from this response
        new_complete = extract_complete_scenes(parsed)
        normalize_scenes(new_complete)
        consistency_notes = parsed.get("consistency_notes", consistency_notes)

        # Determine which scenes are actually NEW (not already collected)
        existing_numbers = {s.get("scene_number") for s in all_complete_scenes}
        new_scenes = [s for s in new_complete if s.get("scene_number") not in existing_numbers]

        if new_scenes:
            all_complete_scenes.extend(new_scenes)
            log.info(f"Got {len(new_scenes)} new complete scenes (total: {len(all_complete_scenes)}/{expected_scene_count})")
        else:
            log.warning(f"Continuation {attempt} produced no new complete scenes. Stopping.")
            break

        # Check if we have all scenes
        if len(all_complete_scenes) >= expected_scene_count:
            log.info(f"All {expected_scene_count} scenes collected.")
            break

        # Need more — request continuation for missing scenes
        if attempt < max_continuations:
            missing_start = max(s.get("scene_number", 0) for s in all_complete_scenes) + 1

            # Build memory summary of already-generated scenes
            scene_summaries = []
            for scene in all_complete_scenes:
                sn = scene.get("scene_number", "?")
                clip_count = len(scene.get("clips", []))
                scene_dur = sum(c.get("duration_seconds", 0) for c in scene.get("clips", []))
                location = scene.get("location_ref", "")
                style = scene.get("style", "")
                scene_summaries.append(f"  Scene {sn}: {clip_count} clips, {scene_dur}s, location='{location}', style='{style}'")

            missing_scenes_info = []
            for sn in range(missing_start, expected_scene_count + 1):
                s_info = script_scene_durations.get(sn)
                if s_info:
                    missing_scenes_info.append(f"  Scene {sn}: {s_info}s")

            last_scene_yaml = yaml.dump(all_complete_scenes[-1], default_flow_style=False, allow_unicode=True)[:800]

            continuation_prompt = f"""Generate scenes {missing_start} through {expected_scene_count} for this episode.

## Memory: Already Generated Scenes (DO NOT repeat these)
{chr(10).join(scene_summaries)}

## Still Needed
Scenes {missing_start} through {expected_scene_count}.

Expected durations from script:
{chr(10).join(missing_scenes_info)}

## Last Completed Scene (for continuity reference)
```
{last_scene_yaml}
```

Output a complete YAML document with a `scenes:` key containing ONLY scenes {missing_start}-{expected_scene_count}.
Use `duration_seconds` (not `duration`) for clip durations.
Include `consistency_notes` at the end. No markdown fences, no explanation.

{language_instruction}"""
            raw_text = call_agent("director", continuation_prompt, max_tokens=MAX_TOKENS, model_override=model_override)
        else:
            break

    # Final result
    if not all_complete_scenes:
        log.error("Failed to generate any complete scenes")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_dir = ep_dir / "scenes" / ts
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / "raw_output.txt"
        debug_path.write_text(raw_text, encoding="utf-8")
        log.error(f"Raw output saved to {debug_path}")
        sys.exit(1)

    # Sort scenes by scene_number and trim to expected count
    all_complete_scenes.sort(key=lambda s: s.get("scene_number", 0))
    if len(all_complete_scenes) > expected_scene_count:
        log.warning(f"LLM generated {len(all_complete_scenes)} scenes but script has {expected_scene_count}. Trimming extras.")
        all_complete_scenes = all_complete_scenes[:expected_scene_count]
    total_clip_duration = sum(
        sum(c.get("duration_seconds", 0) for c in scene.get("clips", []))
        for scene in all_complete_scenes
    )
    log.info(f"Final: {len(all_complete_scenes)}/{expected_scene_count} scenes, "
             f"total clip duration: {total_clip_duration}s (target: {expected_total_duration}s)")

    if len(all_complete_scenes) < expected_scene_count:
        log.warning(f"Proceeding with {len(all_complete_scenes)} scenes (missing {expected_scene_count - len(all_complete_scenes)})")

    scenes_data = {"scenes": all_complete_scenes}
    if consistency_notes:
        scenes_data["consistency_notes"] = consistency_notes

    # Save scenes_breakdown.yaml at root level as active output
    save_yaml(scenes_data, ep_dir / "scenes_breakdown.yaml")

    scene_count = len(scenes_data.get("scenes", []))
    log.info(f"Scene breakdown complete: {scene_count} scenes generated")
    return scenes_data


def _show_referenced_characters(script: dict, story_slug: str) -> None:
    """Display existing character files that are referenced in the episode script."""
    # Collect all character names from script scenes
    referenced_names = set()
    for scene in script.get("scenes", []):
        for name in scene.get("characters_present", []):
            referenced_names.add(name)
        for dlg in scene.get("dialogue", []):
            if dlg.get("character"):
                referenced_names.add(dlg["character"])

    if not referenced_names:
        return

    # Load existing character files
    chars_dir = story_dir(story_slug) / "characters"
    if not chars_dir.exists():
        return

    char_files = {f.stem: f for f in chars_dir.glob("*.yaml") if f.name != "README.yaml"}
    if not char_files:
        return

    # Match referenced names to existing files (by stem or name/name_zh fields)
    matched = {}
    for f_stem, f_path in char_files.items():
        content = load_yaml(str(f_path))
        names_in_file = {f_stem, content.get("name", ""), content.get("name_zh", "")}
        names_in_file.discard("")
        if referenced_names & names_in_file:
            matched[f_stem] = f_path

    if not matched:
        log.info(f"No existing character files match episode characters: {referenced_names}")
        return

    log.info(f"=== Referenced Characters ({len(matched)}/{len(referenced_names)} found on disk) ===")
    for stem, fpath in sorted(matched.items()):
        print(f"\n--- {stem} ({fpath.name}) ---")
        print(fpath.read_text(encoding="utf-8"))
    print("=" * 60)
    # Check which referenced names have no file
    matched_names = set()
    for f_stem, f_path in matched.items():
        content = load_yaml(str(f_path))
        matched_names.update({f_stem, content.get("name", ""), content.get("name_zh", "")})
    matched_names.discard("")
    unmatched = referenced_names - matched_names
    if unmatched:
        log.info(f"Characters without existing files (will be newly designed): {unmatched}")


def generate_characters_with_llm(episode_number: int, story_slug: str, model_override: str | None = None) -> dict:
    """Call character-designer agent via LLM to produce character consistency sheets."""
    ep_dir = episode_dir(episode_number, story_slug)
    script_path = ep_dir / "script.yaml"
    if not script_path.exists():
        log.error(f"Script not found at {script_path}. Run 'script' stage first.")
        sys.exit(1)

    script = load_yaml(str(script_path))

    # Show existing characters referenced in this episode's script
    _show_referenced_characters(script, story_slug)

    episode_context = get_episode_context(story_slug, episode_number)
    style_guide = load_style_guide(story_slug)
    existing_chars = load_existing_characters(story_slug)
    previous_episodes = load_previous_episodes(story_slug, episode_number)
    language_instruction = get_language_instruction(story_slug)
    voice_library_text, valid_voice_ids = load_voice_library()

    user_message = f"""Design character consistency sheets for all characters in this episode.

## Episode Script
```yaml
{yaml.dump(script, default_flow_style=False, allow_unicode=True)}
```

## Previous Episodes (maintain character consistency across episodes)
{previous_episodes}

## Story Context
- Title: {episode_context.get('story_title', '')}
- Description: {episode_context.get('story_description', '')}
- Background: {episode_context.get('story_background', '')}

## Style Guide
```yaml
{style_guide}
```

## Existing Character Data (update/extend these, maintain consistency)
{existing_chars}

## Cross-Episode Consistency Requirements (from CLAUDE.md)
- Every character needs fixed "visual anchor" keywords for consistent AI generation
- Include prompt_keywords field that @director and @artist always include in video prompts
- Track deliberate appearance changes in change_log
- Characters should represent diverse backgrounds respectfully
- NEVER design characters promoting stereotypes or discrimination

## Voice Library (MUST pick voice_asset_id from this list)
Pick the best matching voice for each character based on:
1. gender and age_range (must match the character)
2. language (must match the story language)
3. personality, mood, and tags (match the character's temperament — e.g. a wise elder → calm/authoritative voice, a cheerful girl → bright/energetic voice, a mysterious figure → deep/enigmatic voice)
Read each voice's description and tags carefully to find the best personality fit.
Use ONLY the exact asset_id values listed below. Do NOT invent IDs.
{voice_library_text}

{language_instruction}

## Output Requirements
Output ONLY valid YAML (no markdown fences). Follow the character sheet format:

characters:
  - name: "<character name>"
    name_zh: "<chinese name>"
    role: "<protagonist/supporting/background>"
    appearance:
      age: "<apparent age>"
      build: "<body type>"
      hair: "<hair color, style, length>"
      eyes: "<eye color, shape>"
      skin: "<skin tone>"
      distinguishing_features: ["<feature1>", "<feature2>"]
    clothing:
      default_outfit: "<detailed outfit description for AI generation>"
      accessories: ["<item1>", "<item2>"]
      variants: []
    color_palette: ["#hex1", "#hex2", "#hex3"]
    animation_style: "<art style notes matching style guide>"
    prompt_keywords: "<keywords that consistently reproduce this character in AI video>"
    personality_visual_cues: "<how personality shows in body language/expression>"
    reference_prompt: "<a single detailed prompt that could generate a reference image>"
    voice_asset_id: "<exact asset_id from the Voice Library above, e.g. asset-20260225014946-gdm92>"
  # ... more characters
"""

    log.info(f"Generating character sheets for Episode {episode_number}...")
    raw_text = call_agent("character-designer", user_message, model_override=model_override)

    try:
        chars_data = parse_yaml_response(raw_text)
    except (ValueError, Exception) as e:
        log.error(f"Failed to parse character-designer output: {e}")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_dir = ep_dir / "characters" / ts
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / "raw_output.txt"
        debug_path.write_text(raw_text, encoding="utf-8")
        log.error(f"Raw output saved to {debug_path}")
        sys.exit(1)

    # Validate and fix voice_asset_id values
    if valid_voice_ids:
        for char in chars_data.get("characters", []):
            vid = char.get("voice_asset_id", "")
            # Strip accidental asset:// prefix if LLM added it
            if vid.startswith("asset://"):
                vid = vid[len("asset://"):]
                char["voice_asset_id"] = vid
            if vid not in valid_voice_ids:
                char_name = char.get("name", "unknown")
                log.warning(f"Character '{char_name}' has invalid voice_asset_id '{vid}', clearing it.")
                char.pop("voice_asset_id", None)

    # Save character sheets
    chars_dir = story_dir(story_slug) / "characters"
    avatars_dir = chars_dir / "avatars"
    chars_dir.mkdir(parents=True, exist_ok=True)
    avatars_dir.mkdir(parents=True, exist_ok=True)
    save_yaml(chars_data, ep_dir / "characters.yaml")

    for char in chars_data.get("characters", []):
        slug = _char_slug(char)
        # Store slug in the character data for cross-referencing
        char["slug"] = slug
        char_yaml_path = chars_dir / f"{slug}.yaml"
        avatar_path = avatars_dir / f"{slug}.png"

        # For ep2+, skip characters that already have both YAML and avatar
        if episode_number > 1 and char_yaml_path.exists() and avatar_path.exists():
            log.info(f"Character '{char.get('name', slug)}' already exists with avatar, skipping.")
            # Still update the YAML (may have new change_log entries)
            save_yaml(char, char_yaml_path)
            char["avatar_image"] = str(avatar_path)
            continue

        save_yaml(char, char_yaml_path)

        # Generate full-body avatar image
        avatar = generate_character_avatar(char, story_slug)
        if avatar:
            char["avatar_image"] = str(avatar)
            log.info(f"Avatar saved: {avatar}")
        else:
            log.warning(f"Failed to generate avatar for '{char.get('name', slug)}'")

    log.info(f"Character sheets complete: {len(chars_data.get('characters', []))} characters")
    return chars_data


def edit_character_yaml_with_llm(char: dict, edit_prompt: str, story_slug: str, model_override: str | None = None) -> dict:
    """Use LLM to edit a character YAML based on a user's natural language instruction.

    Returns the updated character dict.
    """
    language_instruction = get_language_instruction(story_slug)
    char_yaml_str = yaml.dump(char, default_flow_style=False, allow_unicode=True)

    user_message = f"""Edit the following character YAML according to the user's instruction.
Return the COMPLETE updated character YAML — do not omit any fields.
Only modify fields relevant to the instruction; keep everything else unchanged.

## User Instruction
{edit_prompt}

## Current Character YAML
```yaml
{char_yaml_str}
```

{language_instruction}

## Output Requirements
Output ONLY valid YAML (no markdown fences, no extra text). Return the full character object.
"""

    log.info(f"Editing character '{char.get('name', 'unknown')}' with LLM: {edit_prompt}")
    raw_text = call_agent("character-designer", user_message, model_override=model_override)

    try:
        updated = parse_yaml_response(raw_text)
    except (ValueError, Exception) as e:
        log.error(f"Failed to parse LLM edit output: {e}")
        log.error(f"Raw: {raw_text[:500]}")
        return char

    # If LLM wrapped in a list or "characters" key, unwrap
    if isinstance(updated, dict) and "characters" in updated:
        chars_list = updated["characters"]
        if isinstance(chars_list, list) and len(chars_list) > 0:
            updated = chars_list[0]
    if isinstance(updated, list) and len(updated) > 0:
        updated = updated[0]

    # Preserve slug
    if char.get("slug"):
        updated["slug"] = char["slug"]

    log.info(f"Character YAML edited successfully.")
    return updated


def generate_locations_with_llm(episode_number: int, story_slug: str, model_override: str | None = None) -> dict:
    """Call director agent via LLM to design locations, then generate reference images."""
    ep_dir = episode_dir(episode_number, story_slug)
    scenes_path = ep_dir / "scenes_breakdown.yaml"
    if not scenes_path.exists():
        log.error(f"Scenes breakdown not found at {scenes_path}. Run 'scenes' stage first.")
        sys.exit(1)

    scenes = load_yaml(str(scenes_path))
    script_path = ep_dir / "script.yaml"
    script = load_yaml(str(script_path)) if script_path.exists() else {}

    episode_context = get_episode_context(story_slug, episode_number)
    style_guide = load_style_guide(story_slug)
    existing_locs = load_existing_locations(story_slug)
    language_instruction = get_language_instruction(story_slug)

    user_message = f"""Design detailed location sheets for all locations appearing in this episode's scenes.
Each location needs enough visual detail that an AI image generator can produce a consistent reference image.

## Episode Scenes
```yaml
{yaml.dump(scenes, default_flow_style=False, allow_unicode=True)}
```

## Episode Script
```yaml
{yaml.dump(script, default_flow_style=False, allow_unicode=True)}
```

## Story Context
- Title: {episode_context.get('story_title', '')}
- Description: {episode_context.get('story_description', '')}
- Background: {episode_context.get('story_background', '')}

## Style Guide
```yaml
{style_guide}
```

## Existing Location Data (update/extend these, maintain consistency)
{existing_locs}

{language_instruction}

## Output Requirements
Output ONLY valid YAML (no markdown fences). Follow this format:

locations:
  - name: "<location name>"
    name_zh: "<中文名>"
    slug: "<kebab-case-slug>"
    description: "<detailed description of the location>"
    time_variants:
      day: "<daytime appearance description>"
      night: "<nighttime appearance description>"
      dawn: "<dawn/dusk appearance if relevant>"
    key_features:
      - "<distinctive visual element 1>"
      - "<distinctive visual element 2>"
      - "<distinctive visual element 3>"
    color_palette: ["#hex1", "#hex2", "#hex3", "#hex4"]
    prompt_keywords: "<keywords for consistent AI generation of this location>"
    negative_keywords: "<what should NOT appear in this location>"
    reference_prompt: "<a single detailed prompt that could generate a reference image of this location — include architecture style, materials, lighting, atmosphere, specific objects>"
    used_in_scenes: [1, 2]  # scene numbers where this location appears
  # ... more locations
"""

    log.info(f"Generating location sheets for Episode {episode_number}...")
    raw_text = call_agent("director", user_message, model_override=model_override)

    try:
        locs_data = parse_yaml_response(raw_text)
    except (ValueError, Exception) as e:
        log.error(f"Failed to parse director location output: {e}")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_path = ep_dir / f"locations_raw_{ts}.txt"
        debug_path.write_text(raw_text, encoding="utf-8")
        log.error(f"Raw output saved to {debug_path}")
        sys.exit(1)

    # Save location sheets
    locs_dir = story_dir(story_slug) / "locations"
    images_dir = locs_dir / "images"
    locs_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    save_yaml(locs_data, ep_dir / "locations.yaml")

    for loc in locs_data.get("locations", []):
        slug = loc.get("slug", loc.get("name", "unknown").lower().replace(" ", "-"))
        loc["slug"] = slug
        loc_yaml_path = locs_dir / f"{slug}.yaml"
        image_path = images_dir / f"{slug}.png"

        # Skip locations that already have both YAML and image
        if loc_yaml_path.exists() and image_path.exists():
            log.info(f"Location '{loc.get('name', slug)}' already exists with image, skipping image gen.")
            save_yaml(loc, loc_yaml_path)
            loc["reference_image"] = str(image_path)
            continue

        save_yaml(loc, loc_yaml_path)

        # Generate location reference image
        img = generate_location_image(loc, story_slug)
        if img:
            loc["reference_image"] = str(img)
            log.info(f"Location image saved: {img}")
        else:
            log.warning(f"Failed to generate image for location '{loc.get('name', slug)}'")

    log.info(f"Location sheets complete: {len(locs_data.get('locations', []))} locations")
    return locs_data


def generate_location_image(loc: dict, story_slug: str) -> Path | None:
    """Generate a reference image for a location using Seedream or HuggingFace SD.

    Returns the path to the saved PNG, or None on failure.
    """
    locs_dir = story_dir(story_slug) / "locations"
    images_dir = locs_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    slug = loc.get("slug", "unknown")
    image_path = images_dir / f"{slug}.png"

    # Build prompt
    style_guide = load_style_guide(story_slug)
    style_desc = ""
    if isinstance(style_guide, dict):
        style_desc = style_guide.get("animation_style", "") or style_guide.get("visual_style", "")
        if isinstance(style_desc, dict):
            style_desc = style_desc.get("description", "")

    ref_prompt = loc.get("reference_prompt", "")
    if not ref_prompt:
        parts = [loc.get("description", "")]
        for feature in loc.get("key_features", []):
            parts.append(feature)
        ref_prompt = ", ".join(parts)

    prompt = (
        f"Detailed environment concept art, wide establishing shot, "
        f"no characters, no people, no text, "
        f"{style_desc}. "
        f"{ref_prompt}"
    )
    negative_prompt = loc.get("negative_keywords", "")
    if negative_prompt and isinstance(negative_prompt, list):
        negative_prompt = ", ".join(negative_prompt)
    negative_prompt = f"people, characters, humans, text, watermark, {negative_prompt}"

    log.info(f"Generating location image for '{loc.get('name', slug)}'...")

    # Try Seedream first
    ark_api_key = os.environ.get("ARK_API_KEY")
    if ark_api_key:
        result = _generate_location_image_seedream(prompt, image_path, ark_api_key, negative_prompt)
        if result:
            return result
        log.warning("Seedream location image failed, trying HuggingFace fallback...")

    # Fallback: HuggingFace SD
    hf_token = os.environ.get("HUGGINGFACE_API_TOKEN")
    if hf_token:
        result = _generate_avatar_huggingface(prompt, image_path, hf_token, negative_prompt)
        if result:
            return result
        log.warning("HuggingFace location image also failed.")

    log.error("No image generation API available for location images.")
    return None


def _generate_location_image_seedream(prompt: str, output_path: Path, api_key: str, negative_prompt: str = "") -> Path | None:
    """Generate location image using BytePlus Ark Seedream API (landscape format)."""
    import requests as req
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = req.Session()
    retries = Retry(total=3, backoff_factor=2, status_forcelist=[502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    seed = random.randint(0, 2**31 - 1)
    data = {
        "model": "seedream-4-5-251128",
        "prompt": prompt,
        "size": "2K",
        "aspect_ratio": "16:9",
        "watermark": False,
        "seed": seed,
    }
    if negative_prompt:
        data["negative_prompt"] = negative_prompt
    log.info(f"  Seedream location seed: {seed}")

    try:
        resp = session.post(
            "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations",
            headers=headers, json=data, timeout=120,
        )
        if resp.status_code != 200:
            log.warning(f"Seedream API error ({resp.status_code}): {resp.text[:300]}")
            return None

        result = resp.json()
        image_data = None
        for item in result.get("data", []):
            if item.get("b64_json"):
                image_data = item["b64_json"]
                break
            elif item.get("url"):
                img_resp = req.get(item["url"], timeout=60)
                if img_resp.status_code == 200:
                    output_path.write_bytes(img_resp.content)
                    log.info(f"  Seedream location image saved: {output_path}")
                    return output_path

        if image_data:
            import base64
            output_path.write_bytes(base64.b64decode(image_data))
            log.info(f"  Seedream location image saved: {output_path}")
            return output_path

        log.warning(f"Seedream returned no image data: {result}")
        return None
    except Exception as e:
        log.warning(f"Seedream location image generation failed: {e}")
        return None


def generate_keyframes(episode_number: int, story_slug: str) -> dict:
    """Generate start, middle, and end keyframe images for each clip in each scene.

    Within a scene, end of clip N is reused as start of clip N+1 for continuity.
    Returns dict with keyframe metadata and paths.
    """
    ep_dir = episode_dir(episode_number, story_slug)
    scenes_path = ep_dir / "scenes_breakdown.yaml"
    if not scenes_path.exists():
        log.error(f"Scenes breakdown not found at {scenes_path}. Run 'scenes' stage first.")
        sys.exit(1)

    scenes_data = load_yaml(str(scenes_path))
    style_guide = load_style_guide(story_slug)
    style_desc = ""
    if isinstance(style_guide, dict):
        style_desc = style_guide.get("animation_style", "") or style_guide.get("visual_style", "")
        if isinstance(style_desc, dict):
            style_desc = style_desc.get("description", "")

    # Load characters and locations for prompt enrichment
    chars_path = ep_dir / "characters.yaml"
    chars_data = load_yaml(str(chars_path)) if chars_path.exists() else {}
    locs_path = ep_dir / "locations.yaml"
    locs_data = load_yaml(str(locs_path)) if locs_path.exists() else {}

    # Build character/location lookup
    char_lookup = {}
    for c in chars_data.get("characters", []):
        char_lookup[c.get("name", "")] = c.get("prompt_keywords", c.get("reference_prompt", ""))
    loc_lookup = {}
    for loc in locs_data.get("locations", []):
        loc_lookup[loc.get("name", "")] = loc.get("prompt_keywords", loc.get("reference_prompt", ""))

    keyframes_dir = ep_dir / "keyframes"
    keyframes_dir.mkdir(parents=True, exist_ok=True)

    keyframe_results = {"scenes": []}

    for scene in scenes_data.get("scenes", []):
        scene_num = scene.get("scene_number", 0)
        scene_style = scene.get("style", style_desc)
        scene_mood = scene.get("mood", "")
        scene_loc = scene.get("location_ref", "")
        loc_keywords = loc_lookup.get(scene_loc, "")
        char_refs = scene.get("character_refs", [])
        char_keywords = ", ".join(char_lookup.get(c, c) for c in char_refs if c)

        clips = scene.get("clips", [])
        scene_keyframes = {"scene_number": scene_num, "clips": []}
        prev_end_path = None  # For continuity: end of clip N = start of clip N+1

        for clip in clips:
            clip_num = clip.get("clip_number", 0)
            clip_dir = keyframes_dir / f"scene_{scene_num}" / f"clip_{clip_num}"
            clip_dir.mkdir(parents=True, exist_ok=True)

            subject = clip.get("subject", "")
            environment = clip.get("environment", "")
            camera = clip.get("camera", "")
            transition_in = clip.get("transition_in", "")
            transition_out = clip.get("transition_out", "")
            action = clip.get("action", "")
            negative_prompt = clip.get("negative_prompt", "")

            # Build prompts for start/middle/end
            base_context = f"{scene_style}, {scene_mood}, {char_keywords}, {loc_keywords}"

            start_prompt = (
                f"{base_context}. "
                f"Opening frame: {transition_in}. "
                f"{subject}, {environment}, camera: {camera}. "
                f"Film still, single frame, high quality"
            )
            middle_prompt = (
                f"{base_context}. "
                f"Mid-action: {action}. "
                f"{subject}, {environment}, camera: {camera}. "
                f"Film still, single frame, high quality"
            )
            end_prompt = (
                f"{base_context}. "
                f"Ending frame: {transition_out}. "
                f"{subject}, {environment}, camera: {camera}. "
                f"Film still, single frame, high quality"
            )

            clip_keyframe_info = {
                "scene_number": scene_num,
                "clip_number": clip_num,
                "keyframes": {},
            }

            # Start frame: reuse previous clip's end if available (within same scene)
            start_path = clip_dir / "start.png"
            if prev_end_path and prev_end_path.exists():
                # Copy previous clip's end frame as this clip's start
                import shutil
                shutil.copy2(prev_end_path, start_path)
                log.info(f"  Scene {scene_num} Clip {clip_num}: start = previous clip end (copied)")
                clip_keyframe_info["keyframes"]["start"] = str(start_path)
            else:
                if not start_path.exists():
                    img = _generate_keyframe_image(start_prompt, start_path, negative_prompt)
                    if img:
                        clip_keyframe_info["keyframes"]["start"] = str(img)
                    else:
                        log.warning(f"  Failed to generate start keyframe for scene {scene_num} clip {clip_num}")
                else:
                    log.info(f"  Scene {scene_num} Clip {clip_num}: start already exists, skipping")
                    clip_keyframe_info["keyframes"]["start"] = str(start_path)

            # Middle frame
            middle_path = clip_dir / "middle.png"
            if not middle_path.exists():
                img = _generate_keyframe_image(middle_prompt, middle_path, negative_prompt)
                if img:
                    clip_keyframe_info["keyframes"]["middle"] = str(img)
                else:
                    log.warning(f"  Failed to generate middle keyframe for scene {scene_num} clip {clip_num}")
            else:
                log.info(f"  Scene {scene_num} Clip {clip_num}: middle already exists, skipping")
                clip_keyframe_info["keyframes"]["middle"] = str(middle_path)

            # End frame
            end_path = clip_dir / "end.png"
            if not end_path.exists():
                img = _generate_keyframe_image(end_prompt, end_path, negative_prompt)
                if img:
                    clip_keyframe_info["keyframes"]["end"] = str(img)
                else:
                    log.warning(f"  Failed to generate end keyframe for scene {scene_num} clip {clip_num}")
            else:
                log.info(f"  Scene {scene_num} Clip {clip_num}: end already exists, skipping")
                clip_keyframe_info["keyframes"]["end"] = str(end_path)

            prev_end_path = end_path
            scene_keyframes["clips"].append(clip_keyframe_info)

        keyframe_results["scenes"].append(scene_keyframes)

    # Save keyframe manifest
    save_yaml(keyframe_results, ep_dir / "keyframes.yaml")
    log.info(f"Keyframe generation complete for Episode {episode_number}")
    return keyframe_results


def _generate_keyframe_image(prompt: str, output_path: Path, negative_prompt: str = "") -> Path | None:
    """Generate a single keyframe image using Seedream or HuggingFace SD."""
    ark_api_key = os.environ.get("ARK_API_KEY")
    if ark_api_key:
        result = _generate_keyframe_seedream(prompt, output_path, ark_api_key, negative_prompt)
        if result:
            return result

    hf_token = os.environ.get("HUGGINGFACE_API_TOKEN")
    if hf_token:
        result = _generate_avatar_huggingface(prompt, output_path, hf_token, negative_prompt)
        if result:
            return result

    log.error("No image generation API available for keyframe generation.")
    return None


def _generate_keyframe_seedream(prompt: str, output_path: Path, api_key: str, negative_prompt: str = "") -> Path | None:
    """Generate keyframe image using BytePlus Ark Seedream API (16:9 landscape)."""
    import requests as req
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = req.Session()
    retries = Retry(total=3, backoff_factor=2, status_forcelist=[502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    seed = random.randint(0, 2**31 - 1)
    data = {
        "model": "seedream-4-5-251128",
        "prompt": prompt,
        "size": "1080p",
        "aspect_ratio": "16:9",
        "watermark": False,
        "seed": seed,
    }
    if negative_prompt:
        data["negative_prompt"] = negative_prompt

    try:
        resp = session.post(
            "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations",
            headers=headers, json=data, timeout=120,
        )
        if resp.status_code != 200:
            log.warning(f"Seedream keyframe API error ({resp.status_code}): {resp.text[:300]}")
            return None

        result = resp.json()
        image_data = None
        for item in result.get("data", []):
            if item.get("b64_json"):
                image_data = item["b64_json"]
                break
            elif item.get("url"):
                img_resp = req.get(item["url"], timeout=60)
                if img_resp.status_code == 200:
                    output_path.write_bytes(img_resp.content)
                    log.info(f"  Keyframe saved: {output_path}")
                    return output_path

        if image_data:
            import base64
            output_path.write_bytes(base64.b64decode(image_data))
            log.info(f"  Keyframe saved: {output_path}")
            return output_path

        log.warning(f"Seedream returned no image data for keyframe")
        return None
    except Exception as e:
        log.warning(f"Seedream keyframe generation failed: {e}")
        return None


def generate_character_avatar(char: dict, story_slug: str) -> Path | None:
    """Generate a full-body character avatar PNG using Seedream (BytePlus) or HuggingFace SD.

    Returns the path to the saved PNG, or None on failure.
    """
    chars_dir = story_dir(story_slug) / "characters"
    avatars_dir = chars_dir / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    slug = char.get("slug") or _char_slug(char)
    avatar_path = avatars_dir / f"{slug}.png"

    # Build a detailed prompt from the character sheet
    style_guide = load_style_guide(story_slug)
    style_desc = ""
    if isinstance(style_guide, dict):
        style_desc = style_guide.get("animation_style", "") or style_guide.get("visual_style", "")
        if isinstance(style_desc, dict):
            style_desc = style_desc.get("description", "")
    char_style = char.get("animation_style", "")

    # Use reference_prompt if available, otherwise build from appearance
    base_prompt = char.get("reference_prompt", "")
    if not base_prompt:
        parts = []
        appearance = char.get("appearance", {})
        if appearance.get("age"):
            parts.append(str(appearance["age"]))
        if appearance.get("build"):
            parts.append(appearance["build"])
        if appearance.get("hair"):
            parts.append(f"hair: {appearance['hair']}")
        if appearance.get("eyes"):
            parts.append(f"eyes: {appearance['eyes']}")
        if appearance.get("skin"):
            parts.append(f"skin tone: {appearance['skin']}")
        if appearance.get("distinguishing_features"):
            parts.extend(appearance["distinguishing_features"])
        clothing = char.get("clothing", {})
        if clothing.get("default_outfit"):
            parts.append(clothing["default_outfit"])
        if clothing.get("accessories"):
            parts.append("accessories: " + ", ".join(clothing["accessories"]))
        base_prompt = ", ".join(parts)

    prompt = (
        f"Character design reference sheet, three-view orthographic drawing (三视图), "
        f"front view | side view | back view, "
        f"full body standing pose, evenly spaced on a single image, "
        f"solid pure white background (#FFFFFF), no background elements, "
        f"no scenery, no shadow on ground, no gradient, "
        f"clean isolated character sheet on flat white, "
        f"professional animation character turnaround sheet, "
        f"{char_style or style_desc}. "
        f"{base_prompt}"
    )
    negative_prompt = (
        "background, scenery, landscape, room, interior, floor, shadow, "
        "gradient, pattern, texture, wall, sky, ground, furniture, "
        "single view only, one angle only, portrait, headshot"
    )

    log.info(f"Generating avatar for '{char.get('name', slug)}'...")

    # Try Seedream (BytePlus Ark) first
    ark_api_key = os.environ.get("ARK_API_KEY")
    if ark_api_key:
        result = _generate_avatar_seedream(prompt, avatar_path, ark_api_key, negative_prompt)
        if result:
            _remove_white_background(result)
            return result
        log.warning("Seedream avatar generation failed, trying HuggingFace fallback...")

    # Fallback: HuggingFace Stable Diffusion
    hf_token = os.environ.get("HUGGINGFACE_API_TOKEN")
    if hf_token:
        result = _generate_avatar_huggingface(prompt, avatar_path, hf_token, negative_prompt)
        if result:
            _remove_white_background(result)
            return result
        log.warning("HuggingFace avatar generation also failed.")

    log.error(f"No image generation API available. Set ARK_API_KEY or HUGGINGFACE_API_TOKEN.")
    return None


def _remove_white_background(image_path: Path, threshold: int = 240) -> None:
    """Convert near-white background pixels to transparent in a PNG image."""
    try:
        from PIL import Image
        img = Image.open(image_path).convert("RGBA")
        pixels = img.load()
        w, h = img.size
        for y in range(h):
            for x in range(w):
                r, g, b, a = pixels[x, y]
                if r >= threshold and g >= threshold and b >= threshold:
                    pixels[x, y] = (r, g, b, 0)
        img.save(image_path, "PNG")
        log.info(f"  Removed white background: {image_path.name}")
    except ImportError:
        log.warning("Pillow not installed — skipping background removal")
    except Exception as e:
        log.warning(f"Background removal failed: {e}")


def _generate_avatar_seedream(prompt: str, output_path: Path, api_key: str, negative_prompt: str = "") -> Path | None:
    """Generate avatar using BytePlus Ark Seedream API."""
    import time
    import requests as req
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = req.Session()
    retries = Retry(total=3, backoff_factor=2, status_forcelist=[502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    seed = random.randint(0, 2**31 - 1)
    data = {
        "model": "seedream-4-5-251128",
        "prompt": prompt,
        "size": "2K",
        "aspect_ratio": "16:9",  # Landscape for three-view character sheet
        "watermark": False,
        "seed": seed,
    }
    if negative_prompt:
        data["negative_prompt"] = negative_prompt
    log.info(f"  Seedream seed: {seed}")

    try:
        resp = session.post(
            "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations",
            headers=headers, json=data, timeout=120,
        )
        if resp.status_code != 200:
            log.warning(f"Seedream API error ({resp.status_code}): {resp.text[:300]}")
            return None

        result = resp.json()
        # Extract image data from response
        image_data = None
        for item in result.get("data", []):
            if item.get("b64_json"):
                image_data = item["b64_json"]
                break
            elif item.get("url"):
                # Download from URL
                img_resp = req.get(item["url"], timeout=60)
                if img_resp.status_code == 200:
                    output_path.write_bytes(img_resp.content)
                    log.info(f"  Seedream avatar saved: {output_path}")
                    return output_path

        if image_data:
            import base64
            output_path.write_bytes(base64.b64decode(image_data))
            log.info(f"  Seedream avatar saved: {output_path}")
            return output_path

        log.warning(f"Seedream returned no image data: {result}")
        return None
    except Exception as e:
        log.warning(f"Seedream avatar generation failed: {e}")
        return None


def _generate_avatar_huggingface(prompt: str, output_path: Path, hf_token: str, negative_prompt: str = "") -> Path | None:
    """Generate avatar using HuggingFace Stable Diffusion Inference API."""
    import requests as req

    # Use Stable Diffusion via HuggingFace Inference API (Router endpoint)
    api_url = "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-xl-base-1.0"

    headers = {
        "Authorization": f"Bearer {hf_token}",
    }
    seed = random.randint(0, 2**31 - 1)
    payload: dict = {
        "inputs": prompt,
        "parameters": {"seed": seed},
    }
    if negative_prompt:
        payload["parameters"]["negative_prompt"] = negative_prompt
    log.info(f"  HuggingFace seed: {seed}")

    try:
        resp = req.post(api_url, headers=headers, json=payload, timeout=120)
        if resp.status_code != 200:
            log.warning(f"HuggingFace SD API error ({resp.status_code}): {resp.text[:300]}")
            return None

        # Response is raw image bytes
        if resp.headers.get("content-type", "").startswith("image/"):
            output_path.write_bytes(resp.content)
            log.info(f"  HuggingFace avatar saved: {output_path}")
            return output_path

        log.warning(f"HuggingFace returned unexpected content-type: {resp.headers.get('content-type')}")
        return None
    except Exception as e:
        log.warning(f"HuggingFace avatar generation failed: {e}")
        return None
    """Call sound-designer agent via LLM to plan audio layers."""
    ep_dir = episode_dir(episode_number, story_slug)
    script_path = ep_dir / "script.yaml"
    if not script_path.exists():
        log.error(f"Script not found at {script_path}. Run 'script' stage first.")
        sys.exit(1)

    script = load_yaml(str(script_path))
    episode_context = get_episode_context(story_slug, episode_number)
    style_guide = load_style_guide(story_slug)
    previous_episodes = load_previous_episodes(story_slug, episode_number)
    language_instruction = get_language_instruction(story_slug)

    # Load scene breakdown if available (from director step)
    scenes_breakdown = ""
    scenes_file = ep_dir / "scenes_breakdown.yaml"
    if scenes_file.exists():
        scenes_breakdown = scenes_file.read_text(encoding="utf-8")

    user_message = f"""Design the complete audio plan for this episode.

## Episode Script
```yaml
{yaml.dump(script, default_flow_style=False, allow_unicode=True)}
```

## Previous Episodes (maintain audio themes and motifs continuity)
{previous_episodes}

## Scene Breakdown (from @director)
```yaml
{scenes_breakdown if scenes_breakdown else "Not yet available - use script scenes for timing"}
```

## Story Context
- Title: {episode_context.get('story_title', '')}
- Description: {episode_context.get('story_description', '')}
- Background: {episode_context.get('story_background', '')}

## Style Guide
```yaml
{style_guide}
```

## Audio Requirements (from CLAUDE.md)
- Episode duration: ~2 minutes (120 seconds)
- Audio must match scene mood defined by @director
- Use only royalty-free or AI-generated audio
- Store audio assets in episode audio/ directory
- Music should have smooth transitions between scenes

{language_instruction}

## Output Requirements
Output ONLY valid YAML (no markdown fences). Follow the audio spec format:

audio_plan:
  overall_mood: "<mood>"
  music_style: "<genre/style>"
  scenes:
    - scene_number: 1
      time_range: "<start-end>"
      music:
        track_description: "<what music plays - specific enough for AI generation>"
        mood: "<epic, calm, tense, etc.>"
        tempo: "<slow/medium/fast>"
        volume: <0.0-1.0>
        instruments: ["<instrument1>", "<instrument2>"]
        transition: "<how music changes from previous scene>"
      sound_effects:
        - trigger: "<what triggers this SFX>"
          effect: "<description of SFX>"
          timestamp: "<MM:SS>"
          intensity: "<low/medium/high>"
      ambient:
        description: "<background ambience - specific for generation>"
      narration:
        - character: "<who speaks>"
          line: "<what they say>"
          voice: "<voice description>"
          style: "<whispered/normal/dramatic>"
          timestamp: "<MM:SS>"
    # ... more scenes
  credits_music:
    description: "<end credits music>"
    duration_seconds: 10
"""

    log.info(f"Generating audio plan for Episode {episode_number}...")
    raw_text = call_agent("sound-designer", user_message, model_override=model_override)

    try:
        audio_data = parse_yaml_response(raw_text)
    except (ValueError, Exception) as e:
        log.error(f"Failed to parse sound-designer output: {e}")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_dir = ep_dir / "audio" / ts
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_path = debug_dir / "raw_output.txt"
        debug_path.write_text(raw_text, encoding="utf-8")
        log.error(f"Raw output saved to {debug_path}")
        sys.exit(1)

    # Save audio plan
    audio_dir = ep_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    save_yaml(audio_data, ep_dir / "audio_plan.yaml")

    log.info(f"Audio plan complete: {len(audio_data.get('audio_plan', {}).get('scenes', []))} scene audio specs")
    return audio_data


def run_pipeline(episode_number: int, votes_path: str | None = None, resume: bool = False, story_slug: str | None = None) -> None:
    """Run the episode generation pipeline with state tracking."""
    state = EpisodeState(episode_number)

    # If resuming, find where to pick up
    if resume:
        resume_point = state.get_resume_point()
        if resume_point is None:
            log.info("Pipeline already completed. Nothing to resume.")
            return
        log.info(f"Resuming from step: {resume_point}")
    else:
        # Fresh start -- reset if previously run
        if state.status in ("completed", "failed"):
            log.info("Resetting pipeline for fresh run")
            state.reset_from("collect_votes")

    # Step 1: Collect votes
    if state.get_step_status("collect_votes") not in ("completed", "skipped"):
        if votes_path:
            state.start_step("collect_votes")
            votes = load_vote_results(votes_path)
            if votes:
                result = {"path": votes_path, "winner": votes.get("winner")}
                state.complete_step("collect_votes", result=result)
            else:
                state.skip_step("collect_votes", "No vote data found")
        else:
            state.skip_step("collect_votes", "No votes path provided (first episode?)")

    # Step 2: Generate script via LLM
    if state.get_step_status("generate_script") not in ("completed", "skipped"):
        state.start_step("generate_script")
        try:
            story_bible = load_story_bible(story_slug)
            votes = None
            vote_artifact = state.get_artifact("collect_votes")
            if vote_artifact and vote_artifact.get("path"):
                votes = load_vote_results(vote_artifact["path"])

            if not story_slug:
                log.error("--story is required for LLM script generation")
                sys.exit(1)

            script = generate_script_with_llm(episode_number, story_slug, story_bible, votes)
            output_path = episode_dir(episode_number, story_slug) / "script.yaml"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            save_yaml(script, output_path)
            state.complete_step("generate_script", result={"path": str(output_path)})
            log.info(f"Script saved to {output_path}")
        except SystemExit:
            raise
        except Exception as e:
            state.fail_step("generate_script", str(e))
            log.error(f"Script generation failed: {e}")
            sys.exit(1)

    log.info(f"Episode {episode_number} pipeline status: {state.summary()}")


def run_stage(episode_number: int, stage: str, story_slug: str | None = None, model_override: str | None = None) -> None:
    """Run a specific stage of the pipeline.

    Stages:
        script - Generate episode script (@writer agent)
        scenes - Plan scenes and visual breakdowns (@director agent)
        characters - Design character consistency sheets (@character-designer agent)
        audio - Generate audio layers (@sound-designer agent)

    Each run saves output to a timestamped subfolder:
        {ep_dir}/{stage}/{timestamp}/output.yaml
    And copies to root level as the active output for downstream stages.
    """
    if not story_slug:
        log.error("--story is required for all stages")
        sys.exit(1)

    # model_override can also come from env (set by web API)
    if not model_override:
        model_override = os.environ.get("LLM_MODEL_OVERRIDE") or None

    # Set CONTENT_LANGUAGE env var for skill loading (language-specific skills)
    lang_instruction = get_language_instruction(story_slug)
    story_lang = get_story_language(story_slug)
    os.environ["CONTENT_LANGUAGE"] = story_lang

    log.info(f"Running stage '{stage}' for Episode {episode_number}" + (f" (model: {model_override})" if model_override else ""))
    ep_dir = episode_dir(episode_number, story_slug)

    # Log selected run dirs from env (passed by admin UI)
    selected_dirs = {k: v for k, v in os.environ.items() if k.startswith("SELECTED_") and k.endswith("_DIR")}
    if selected_dirs:
        log.info("Using selected run dirs from previous steps:")
        for k, v in sorted(selected_dirs.items()):
            log.info(f"  {k}={v}")

    # Resolve script path: use selected run dir if available, else root level
    selected_script_dir = os.environ.get("SELECTED_SCRIPT_DIR")
    if selected_script_dir:
        candidate = ep_dir / "script" / selected_script_dir / "script.yaml"
        if candidate.exists():
            # Copy selected script to root level so downstream reads it
            shutil.copy2(candidate, ep_dir / "script.yaml")
            log.info(f"Using script from selected run: {selected_script_dir}")
        else:
            log.warning(f"Selected script run dir not found: {candidate}, falling back to root")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = ep_dir / stage / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    if stage == "script":
        story_bible = load_story_bible(story_slug)
        votes = None
        script = generate_script_with_llm(episode_number, story_slug, story_bible, votes, model_override=model_override)
        # Save to run subfolder
        save_yaml(script, run_dir / "script.yaml")
        # Copy to root level as active output
        save_yaml(script, ep_dir / "script.yaml")
        log.info(f"Script saved to {run_dir / 'script.yaml'}")
        print("--- Generated Script ---")
        print(yaml.dump(script, default_flow_style=False, allow_unicode=True))
    elif stage == "scenes":
        result = generate_scenes_with_llm(episode_number, story_slug, model_override=model_override)
        # Save to run subfolder
        save_yaml(result, run_dir / "scenes_breakdown.yaml")
        # Copy individual clip prompts to run subfolder
        for scene in result.get("scenes", []):
            scene_num = scene.get("scene_number", 0)
            for clip in scene.get("clips", []):
                clip_num = clip.get("clip_number", 0)
                save_yaml(clip, run_dir / f"scene_{scene_num}_clip_{clip_num}_prompt.yaml")
        # Root level is already saved by generate_scenes_with_llm
        log.info(f"Scenes saved to {run_dir / 'scenes_breakdown.yaml'}")
        print("--- Scene Breakdown ---")
        print(yaml.dump(result, default_flow_style=False, allow_unicode=True))
    elif stage == "characters":
        result = generate_characters_with_llm(episode_number, story_slug, model_override=model_override)
        # Save to run subfolder
        save_yaml(result, run_dir / "characters.yaml")
        # Root level is already saved by generate_characters_with_llm
        log.info(f"Characters saved to {run_dir / 'characters.yaml'}")
        print("--- Character Sheets ---")
        print(yaml.dump(result, default_flow_style=False, allow_unicode=True))
    elif stage == "locations":
        result = generate_locations_with_llm(episode_number, story_slug, model_override=model_override)
        # Save to run subfolder
        save_yaml(result, run_dir / "locations.yaml")
        log.info(f"Locations saved to {run_dir / 'locations.yaml'}")
        print("--- Location Sheets ---")
        print(yaml.dump(result, default_flow_style=False, allow_unicode=True))
    elif stage == "keyframes":
        result = generate_keyframes(episode_number, story_slug)
        # Save to run subfolder
        save_yaml(result, run_dir / "keyframes.yaml")
        log.info(f"Keyframes saved to {run_dir / 'keyframes.yaml'}")
        print("--- Keyframes ---")
        print(yaml.dump(result, default_flow_style=False, allow_unicode=True))
    elif stage == "audio":
        result = generate_audio_with_llm(episode_number, story_slug, model_override=model_override)
        # Save to run subfolder
        save_yaml(result, run_dir / "audio_plan.yaml")
        # Root level is already saved by generate_audio_with_llm
        log.info(f"Audio plan saved to {run_dir / 'audio_plan.yaml'}")
        print("--- Audio Plan ---")
        print(yaml.dump(result, default_flow_style=False, allow_unicode=True))

        # Also run audio generation (MusicGen/Bark) in the same step
        log.info("Running audio generation from plan...")
        import subprocess
        gen_audio_script = Path(__file__).parent / "generate_audio.py"
        gen_cmd = [
            sys.executable, str(gen_audio_script),
            "--episode", str(episode_number),
            "--story", story_slug,
            "--plan", str(run_dir / "audio_plan.yaml"),
            "--output-dir", str(run_dir),
        ]
        # Pass through audio model override if set
        audio_model = os.environ.get("AUDIO_MODEL_OVERRIDE") or os.environ.get("AUDIO_MODEL")
        if audio_model:
            gen_cmd.extend(["--model", audio_model])
        gen_result = subprocess.run(gen_cmd, cwd=str(Path(__file__).parent.parent), env=os.environ)
        if gen_result.returncode != 0:
            log.error(f"Audio generation failed with exit code {gen_result.returncode}")
            sys.exit(gen_result.returncode)
    else:
        log.error(f"Unknown stage: {stage}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Generate episode script")
    parser.add_argument("--episode", type=int, required=True, help="Episode number")
    parser.add_argument("--story", type=str, default=None, help="Story slug (e.g. the-ancient-without-a-plug)")
    parser.add_argument("--votes", type=str, default=None, help="Path to vote results YAML")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--status", action="store_true", help="Show pipeline status")
    parser.add_argument("--stage", type=str, default=None,
                        choices=["script", "scenes", "characters", "locations", "keyframes", "audio"],
                        help="Run a specific pipeline stage")
    parser.add_argument("--model", type=str, default=None,
                        help="LLM model override (format: provider/model, e.g. huggingface/Qwen/Qwen2.5-72B-Instruct)")
    parser.add_argument("--regenerate-avatar", type=str, default=None, metavar="SLUG",
                        help="Regenerate avatar for a single character by slug")
    parser.add_argument("--avatar-prompt", type=str, default=None,
                        help="Optional edit instruction for character YAML before regenerating avatar")
    args = parser.parse_args()

    if args.status:
        state = EpisodeState(args.episode)
        summary = state.summary()
        log.info(f"Episode {args.episode}: {summary['status']} ({summary['progress']})")
        log.info(f"  Current step: {summary['current_step']}")
        log.info(f"  Resume point: {summary['resume_point']}")
        return

    if args.regenerate_avatar:
        if not args.story:
            log.error("--story is required for --regenerate-avatar")
            sys.exit(1)
        slug = args.regenerate_avatar
        char_yaml = story_dir(args.story) / "characters" / f"{slug}.yaml"
        if not char_yaml.exists():
            log.error(f"Character YAML not found: {char_yaml}")
            sys.exit(1)
        char = load_yaml(str(char_yaml))
        # If user provided an edit prompt, use LLM to modify the character YAML first
        if args.avatar_prompt:
            char = edit_character_yaml_with_llm(char, args.avatar_prompt, args.story, model_override=args.model)
            save_yaml(char, char_yaml)
            log.info(f"Character YAML updated via LLM: {char_yaml}")
        avatar = generate_character_avatar(char, args.story)
        if avatar:
            log.info(f"Avatar regenerated: {avatar}")
        else:
            log.error("Avatar regeneration failed")
            sys.exit(1)
        return

    if args.stage:
        run_stage(args.episode, args.stage, args.story, model_override=args.model)
    else:
        run_pipeline(args.episode, args.votes, args.resume, story_slug=args.story)


if __name__ == "__main__":
    main()
