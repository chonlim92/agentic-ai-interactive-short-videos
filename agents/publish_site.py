"""Publish Episode to Website

Deploys a finished episode to the Next.js site with voting poll.
Uses @publisher agent to generate metadata, descriptions, and poll setup.
After publishing, generates story poster, episode poster, and gallery images.

Usage:
    python agents/publish_site.py --episode <number> --story <slug>
    python agents/publish_site.py --episode 1 --story my-story --draft
"""

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

import argparse
import base64
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

from common import (
    config_path,
    episode_dir,
    get_project_root,
    get_story_language,
    load_env,
    load_yaml,
    save_yaml,
    setup_logging,
    story_dir,
)

load_env()
log = setup_logging("publish_site")


def _atomic_write_json(file_path: Path, data: dict) -> None:
    """Write JSON atomically: write to temp file then rename to prevent corruption."""
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=file_path.parent, suffix=".tmp", prefix=file_path.stem
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, file_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_config() -> dict:
    """Load publishing config."""
    return load_yaml(config_path("publishing.yaml"))


def _find_composed_video(ep_dir: Path, episode_number: int, suffix: str = "") -> Path | None:
    """Find the composed video file, checking timestamped run folders in compose/.

    Compose step saves to compose/{timestamp}/episode_{N}{suffix}.mp4.
    This function checks:
    1. compose/{latest_ts}/episode_{N}{suffix}.mp4  (timestamped run folder)
    2. compose/episode_{N}{suffix}.mp4              (legacy flat location)
    3. final/video/episode_{N}{suffix}.mp4           (already published)
    4. final/episode_{N}{suffix}.mp4                 (legacy final)

    Returns the Path if found, or None.
    """
    compose_dir = ep_dir / "compose"
    filename = f"episode_{episode_number}{suffix}.mp4"

    # Check timestamped run folders (sorted descending = latest first)
    if compose_dir.exists():
        run_dirs = sorted(
            [d for d in compose_dir.iterdir() if d.is_dir() and d.name.isdigit() or (len(d.name) == 15 and d.name[:8].isdigit())],
            key=lambda d: d.name,
            reverse=True,
        )
        for rd in run_dirs:
            candidate = rd / filename
            if candidate.exists():
                return candidate

    # Legacy flat compose/ location
    candidate = compose_dir / filename
    if candidate.exists():
        return candidate

    # Already in final/
    candidate = ep_dir / "final" / "video" / filename
    if candidate.exists():
        return candidate
    candidate = ep_dir / "final" / filename
    if candidate.exists():
        return candidate

    return None


def load_publish_spec(episode_number: int, story_slug: str | None = None) -> dict | None:
    """Load episode publish specification."""
    path = episode_dir(episode_number, story_slug) / "publish.yaml"
    try:
        return load_yaml(path)
    except FileNotFoundError:
        return None


def generate_publish_spec_with_llm(episode_number: int, story_slug: str) -> dict:
    """Call publisher agent via LLM to generate publish metadata."""
    from llm import call_agent, parse_yaml_response
    from common import get_project_root, story_dir

    project_root = get_project_root()
    ep_dir = episode_dir(episode_number, story_slug)

    # Use final_summary.yaml as the primary source (reflects actual composed episode)
    final_summary_data = {}
    final_summary_path = ep_dir / "final" / "final_summary.yaml"
    if not final_summary_path.exists():
        final_summary_path = ep_dir / "final_summary.yaml"
    if not final_summary_path.exists():
        final_summary_path = ep_dir / "temp_final_summary.yaml"
    if final_summary_path.exists():
        final_summary_data = load_yaml(str(final_summary_path))

    # Fallback to script only if no summary available
    script_data = {}
    if not final_summary_data:
        script_path = ep_dir / "script.yaml"
        if script_path.exists():
            script_data = load_yaml(str(script_path))

    # Load additional context
    characters_summary = ""
    chars_file = ep_dir / "characters.yaml"
    if chars_file.exists():
        characters_summary = chars_file.read_text(encoding="utf-8")

    # Load store.json for episode context
    import json
    store_path = project_root / "site" / "data" / "store.json"
    episode_context = {}
    if store_path.exists():
        with open(store_path, encoding="utf-8") as f:
            store = json.load(f)
        story = next((s for s in store.get("stories", []) if s.get("slug") == story_slug), None)
        if story:
            episode = next(
                (e for e in store.get("episodes", [])
                 if e.get("story_id") == story["id"] and e.get("episode_number") == episode_number),
                None,
            )
            if episode:
                episode_context = {
                    "story_title": story.get("title", ""),
                    "story_description": story.get("description", ""),
                    "episode_title": episode.get("title", ""),
                }

    # Build the context section based on available data
    if final_summary_data:
        episode_content_section = f"""## Episode Summary (from final composed episode)
```yaml
{yaml.dump(final_summary_data, default_flow_style=False, allow_unicode=True)}
```

NOTE: The voting options MUST be based on this summary (what actually happened in the composed episode),
NOT on any earlier script drafts. The summary reflects only the clips that were selected for the final cut."""
    else:
        episode_content_section = f"""## Episode Script
```yaml
{yaml.dump(script_data, default_flow_style=False, allow_unicode=True)}
```"""

    # Detect story language (cached in story_bible.yaml)
    story_language = get_story_language(story_slug)

    if story_language == "zh":
        bilingual_instruction = (
            "- The story's original language is Chinese (中文). Write primary content in Chinese first, with English translations"
        )
    else:
        bilingual_instruction = (
            "- Include both English and Chinese text for bilingual audience"
        )

    user_message = f"""Generate the publish specification for Episode {episode_number}.

{episode_content_section}

## Story Context
- Story Title: {episode_context.get('story_title', '')}
- Story Description: {episode_context.get('story_description', '')}
- Episode Title: {episode_context.get('episode_title', '')}

## Characters in Episode
```yaml
{characters_summary if characters_summary else "Not available"}
```

## Publishing Requirements (from CLAUDE.md)
- Voting options MUST be based on the final summary above (what actually happened in the video)
- Do NOT use script voting_options — the composed video may differ from the original script
- Voting options should present genuinely different story directions based on where the episode ended
- Comments section MUST have moderation enabled
- NEVER publish content that hasn't passed ethics check
{bilingual_instruction}
- Thumbnail should be eye-catching and represent a key moment

## Publish Spec Format (from publisher.agent.md)
- Must include: title, description, thumbnail prompt, poll with options, scheduling

## Output Requirements
Output ONLY valid YAML. Follow the publish spec format:

publish:
  episode_number: {episode_number}
  title: "<episode title>"
  title_zh: "<chinese title>"
  description: "<2-3 sentence episode description for website - engaging, no spoilers>"
  description_zh: "<chinese description>"
  thumbnail_prompt: "<detailed prompt for generating a thumbnail image - key dramatic moment>"
  tags: ["<tag1>", "<tag2>", ...]
  seo_keywords: ["<keyword1>", "<keyword2>", ...]
  duration_seconds: 180
  poll:
    question: "<what should happen next? - engaging, creates anticipation>"
    question_zh: "<chinese question>"
    options:
      - id: "a"
        label: "<option text from script voting_options>"
        label_zh: "<chinese option>"
        teaser: "<hint at what this leads to - build excitement>"
        teaser_zh: "<chinese hint>"
      - id: "b"
        label: "<option text>"
        label_zh: "<chinese option>"
        teaser: "<hint>"
        teaser_zh: "<chinese hint>"
      - id: "c"
        label: "<option text>"
        label_zh: "<chinese option>"
        teaser: "<hint>"
        teaser_zh: "<chinese hint>"
    deadline_hours: 72
  comments:
    enabled: true
    moderation: "auto"
    max_length: 500
  social_posts:
    twitter: "<tweet text, max 280 chars - hook + call to action>"
    short_teaser: "<15-second teaser script for short-form video>"
"""

    log.info(f"Generating publish spec for Episode {episode_number}...")
    try:
        raw_text = call_agent("publisher", user_message)
        publish_spec = parse_yaml_response(raw_text)
        save_yaml(publish_spec, ep_dir / "publish.yaml")
        log.info("Publish spec generated and saved")
        return publish_spec
    except Exception as e:
        log.error(f"Failed to generate publish spec: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Gallery: Extract frames from composed video
# ---------------------------------------------------------------------------

POSTER_SIZES = {
    "2_3": (800, 1200),
    "7_10": (700, 1000),
    "3_4": (900, 1200),
    "4_3": (1200, 900),
    "9_16": (720, 1280),
    "16_9": (1280, 720),
    "1_1": (1080, 1080),
}

# The 4 poster variants: (orientation, language suffix, aspect)
POSTER_VARIANTS = [
    ("horizontal", "en", 1280, 720),
    ("horizontal", "zh", 1280, 720),
    ("vertical", "en", 720, 1280),
    ("vertical", "zh", 720, 1280),
]


def extract_gallery_frames(video_path: Path, output_dir: Path, count: int = 6, ep_dir: Path | None = None) -> list[Path]:
    """Extract gallery frames from the composed episode.

    Prefers extracting the first frame of each composed clip (for variety).
    Falls back to evenly-spaced frames from the final video if clips aren't found.
    Logo watermark is added AFTER extraction (not before poster reference selection).
    Returns list of saved image paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []

    # Try to find individual clip files to extract first frame of each
    if ep_dir:
        clips_dir = ep_dir / "clips"
        clip_files: list[Path] = []

        # Load edit_plan to know which clips were actually used in compose
        composed_clip_names: set[str] | None = None
        edit_plan_path = ep_dir / "edit_plan.yaml"
        if edit_plan_path.exists():
            try:
                edit_plan = yaml.safe_load(edit_plan_path.read_text(encoding="utf-8"))
                assembly_order = edit_plan.get("edit_plan", {}).get("assembly_order", [])
                if assembly_order:
                    composed_clip_names = set(assembly_order)
                    log.info(f"Edit plan specifies {len(composed_clip_names)} clips for assembly")
            except Exception as e:
                log.warning(f"Could not read edit_plan.yaml: {e}")

        if clips_dir.exists():
            # Find latest run dir in clips/
            run_dirs = sorted(
                [d for d in clips_dir.iterdir() if d.is_dir() and (d.name.isdigit() or (len(d.name) == 15 and d.name[:8].isdigit()))],
                key=lambda d: d.name,
                reverse=True,
            )
            if run_dirs:
                run_dir = run_dirs[0]
                # Find scene clip files (scene_*_clip_*.mp4)
                all_clips = sorted(
                    [f for f in run_dir.glob("scene_*_clip_*.mp4") if f.stat().st_size > 10000],
                    key=lambda f: f.name,
                )
                # Filter to only clips used in compose (edit_plan assembly_order)
                if composed_clip_names:
                    clip_files = [f for f in all_clips if f.name in composed_clip_names]
                    log.info(f"Filtered to {len(clip_files)} clips (from {len(all_clips)} total) matching edit_plan")
                else:
                    clip_files = all_clips

        if clip_files:
            log.info(f"Extracting gallery from {len(clip_files)} individual clips (first frame each)")
            # Select up to `count` clips evenly distributed
            step = max(1, len(clip_files) // count)
            selected_clips = clip_files[::step][:count]
            for i, clip_file in enumerate(selected_clips, 1):
                frame_path = output_dir / f"gallery_{i:02d}.jpg"
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(clip_file),
                    "-frames:v", "1",
                    "-q:v", "2",
                    str(frame_path),
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
                if result.returncode == 0 and frame_path.exists():
                    frames.append(frame_path)
                else:
                    log.warning(f"  Failed to extract frame from {clip_file.name}")
            if frames:
                log.info(f"Extracted {len(frames)} gallery frames from clip first-frames")
                return frames

    # Fallback: extract evenly-spaced frames from final composed video
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video_path)],
            capture_output=True, text=True, timeout=150,
        )
        probe_data = json.loads(probe.stdout)
        duration = float(probe_data["format"]["duration"])
    except Exception as e:
        log.warning(f"Could not probe video duration: {e}")
        duration = 120.0

    # Skip first/last 10% to avoid title card and credits
    start = duration * 0.10
    end = duration * 0.90
    usable = end - start
    interval = usable / (count + 1)

    for i in range(1, count + 1):
        timestamp = start + interval * i
        frame_path = output_dir / f"gallery_{i:02d}.jpg"
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{timestamp:.2f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(frame_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        if result.returncode == 0 and frame_path.exists():
            frames.append(frame_path)
        else:
            log.warning(f"  Failed to extract frame at {timestamp:.1f}s")

    log.info(f"Extracted {len(frames)} gallery frames from video")
    return frames


# ---------------------------------------------------------------------------
# Poster generation via Seedream
# ---------------------------------------------------------------------------


def _create_composite_reference(
    gallery_frame: Path | None,
    character_avatars: list[Path],
    output_path: Path,
) -> Path | None:
    """Create a composite reference image by stitching a gallery frame with character avatars.

    Layout: gallery frame on left (large), character avatars stacked on the right.
    This gives Seedream both style/scene context and character appearance references.
    Returns path to composite image, or the gallery_frame alone if no avatars.
    """
    images_to_combine: list[Path] = []
    if gallery_frame and gallery_frame.exists():
        images_to_combine.append(gallery_frame)
    images_to_combine.extend([a for a in character_avatars if a.exists()])

    if not images_to_combine:
        return None
    if len(images_to_combine) == 1:
        return images_to_combine[0]

    # Use ffmpeg to create a horizontal montage
    output_path.parent.mkdir(parents=True, exist_ok=True)
    n = len(images_to_combine)
    cmd = ["ffmpeg", "-y"]
    for img in images_to_combine:
        cmd.extend(["-i", str(img)])

    # Scale all to 512 height and stack horizontally
    filter_parts = []
    for i in range(n):
        filter_parts.append(f"[{i}:v]scale=-1:512:force_original_aspect_ratio=decrease,pad=ih*3/4:512:(ow-iw)/2:(oh-ih)/2[img{i}]")
    # hstack all
    inputs = "".join(f"[img{i}]" for i in range(n))
    filter_parts.append(f"{inputs}hstack=inputs={n}[out]")
    filter_str = ";".join(filter_parts)

    cmd.extend(["-filter_complex", filter_str, "-map", "[out]", "-q:v", "2", str(output_path)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode == 0 and output_path.exists():
        return output_path
    log.warning(f"Composite reference creation failed: {result.stderr[:200] if result.stderr else ''}")
    # Fallback: just return the gallery frame
    return gallery_frame if gallery_frame and gallery_frame.exists() else None


def _add_logo_watermark(image_path: Path) -> Path:
    """Overlay the horizontal StorySmith AI logo at the bottom-left of an image.

    Modifies the image in-place. The logo is scaled to ~20% of image width,
    fully opaque, with a small margin from the bottom-left corner.
    Returns the same path.
    """
    logo_path = get_project_root() / "site" / "logo" / "storysmithai_logo_horizontal.png"
    if not logo_path.exists():
        log.warning(f"Logo not found: {logo_path}. Skipping watermark.")
        return image_path

    tmp_path = image_path.parent / f"_wm_{image_path.name}"
    # Scale logo to 20% of image width, position at bottom-left with 5% margin
    cmd = [
        "ffmpeg", "-y",
        "-i", str(image_path),
        "-i", str(logo_path),
        "-filter_complex",
        "[1:v]scale=iw*0.20:-1[logo];[0:v][logo]overlay=W*0.03:H-h-H*0.05",
        "-q:v", "2",
        str(tmp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
    if result.returncode == 0 and tmp_path.exists():
        # Replace original with watermarked version
        tmp_path.replace(image_path)
        return image_path
    else:
        log.warning(f"Logo watermark failed for {image_path.name}: {(result.stderr or '')[:150]}")
        if tmp_path.exists():
            tmp_path.unlink()
        return image_path


def _load_titles_from_store(story_slug: str, episode_number: int | None = None) -> dict:
    """Load story and episode titles from store.json (the source of truth for all titles).

    Returns dict with keys: story_title, story_title_zh, episode_title, episode_title_zh.
    """
    result = {
        "story_title": "",
        "story_title_zh": "",
        "episode_title": "",
        "episode_title_zh": "",
    }
    store_path = Path(__file__).resolve().parent.parent / "site" / "data" / "store.json"
    if not store_path.exists():
        return result
    try:
        store_data = json.loads(store_path.read_text(encoding="utf-8"))
        for st in store_data.get("stories", []):
            if st.get("slug") == story_slug:
                result["story_title"] = st.get("title", "")
                result["story_title_zh"] = st.get("title_zh", "")
                if episode_number is not None:
                    for ep in store_data.get("episodes", []):
                        if ep.get("story_id") == st["id"] and ep.get("episode_number") == episode_number:
                            result["episode_title"] = ep.get("title", "")
                            result["episode_title_zh"] = ep.get("title_zh", "")
                            break
                break
    except Exception:
        pass
    return result


def _load_poster_context(ep_dir: Path, story_slug: str) -> dict:
    """Load poster generation context from the final summary and character data.

    Returns dict with keys: narrative_summary, narrative_summary_zh, visual_style,
    title, title_zh, characters (list of {name, name_zh, prompt_keywords}),
    character_avatars (list of Path).
    """
    s_dir = story_dir(story_slug)
    context: dict = {
        "narrative_summary": "",
        "narrative_summary_zh": "",
        "visual_style": "",
        "title": "",
        "title_zh": "",
        "characters": [],
        "character_avatars": [],
    }

    # Load final summary
    final_summary_path = ep_dir / "final" / "final_summary.yaml"
    if final_summary_path.exists():
        try:
            summary = yaml.safe_load(final_summary_path.read_text(encoding="utf-8"))
            primary = summary.get("narrative_summary", "")
            # Resolve bilingual narratives: support both old (EN primary + _zh)
            # and new (story-language primary + _en/_zh) formats
            zh = summary.get("narrative_summary_zh", "")
            en = summary.get("narrative_summary_en", "")
            if zh and not en:
                # Old format: primary is English, _zh has Chinese
                context["narrative_summary"] = primary
                context["narrative_summary_zh"] = zh
            elif en and not zh:
                # New format (zh story): primary is Chinese, _en has English
                context["narrative_summary"] = en
                context["narrative_summary_zh"] = primary
            else:
                # Fallback: use primary as English
                context["narrative_summary"] = primary
                context["narrative_summary_zh"] = zh or ""
            context["visual_style"] = summary.get("visual_style_notes", "")
            context["title"] = summary.get("title", "")
            context["title_zh"] = summary.get("title_zh", summary.get("title_en", ""))
            if not context["title_zh"] and context["title"]:
                context["title_zh"] = context["title"]
            # Get character names from final summary
            for cs in summary.get("character_states", []):
                context["characters"].append({
                    "name": cs.get("name", ""),
                    "name_zh": cs.get("name_zh", cs.get("name_en", "")),
                })
        except Exception as e:
            log.warning(f"Could not load final summary for poster context: {e}")

    # Load character details (prompt_keywords) from episode characters.yaml
    chars_path = ep_dir / "characters.yaml"
    if chars_path.exists():
        try:
            chars_data = yaml.safe_load(chars_path.read_text(encoding="utf-8"))
            for ch in chars_data.get("characters", []):
                ch_name = ch.get("name", "")
                ch_name_lower = ch_name.lower().replace(" ", "_")
                # Match by name or name_en/name_zh (final_summary may use Chinese names)
                for c in context["characters"]:
                    c_name = c.get("name", "")
                    c_name_en = c.get("name_en", c.get("name_zh", ""))
                    if (c_name == ch_name
                            or c_name_en.lower().replace(" ", "_") == ch_name_lower
                            or c_name.lower().replace(" ", "_") == ch_name_lower):
                        c["prompt_keywords"] = ch.get("prompt_keywords", "")
                        # Also store the English name for avatar lookup
                        if not c.get("name_en"):
                            c["name_en"] = ch_name
                        break
        except Exception:
            pass

    # Find character avatar images
    avatars_dir = s_dir / "characters" / "avatars"
    if avatars_dir.exists():
        for c in context["characters"]:
            # Try all known names: name, name_en, name_zh
            name_candidates = set()
            for key in ("name", "name_en", "name_zh"):
                val = c.get(key, "")
                if val:
                    name_candidates.add(val.lower().replace(" ", "_"))
            for name_key in name_candidates:
                found = False
                for ext in (".png", ".jpg", ".jpeg"):
                    avatar_path = avatars_dir / f"{name_key}{ext}"
                    if avatar_path.exists():
                        context["character_avatars"].append(avatar_path)
                        found = True
                        break
                if found:
                    break

    return context


def _generate_poster_seedream(
    prompt: str,
    reference_frame: Path | None,
    output_path: Path,
    width: int,
    height: int,
    negative_prompt: str = "",
) -> Path | None:
    """Generate a poster image using BytePlus Ark Seedream API.

    Uses a reference frame from the video as style guidance.
    After generation, resizes the output to the exact target dimensions
    to guarantee the correct aspect ratio (e.g. 16:9, 9:16).
    """
    import requests as req

    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        log.warning("ARK_API_KEY not set. Cannot generate posters.")
        return None

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # Pass explicit width x height to Seedream for correct aspect ratio.
    # Seedream requires minimum 3,686,400 pixels — scale up if needed, then resize down.
    MIN_PIXELS = 3_686_400
    gen_w, gen_h = width, height
    if gen_w * gen_h < MIN_PIXELS:
        import math
        scale = math.ceil(math.sqrt(MIN_PIXELS / (gen_w * gen_h)) * 10) / 10  # round up to 1 decimal
        gen_w = int(gen_w * scale)
        gen_h = int(gen_h * scale)
        # Ensure even dimensions
        gen_w = gen_w + (gen_w % 2)
        gen_h = gen_h + (gen_h % 2)
    size_param = f"{gen_w}x{gen_h}"

    seed = random.randint(0, 2**31 - 1)
    data: dict = {
        "model": "seedream-4-5-251128",
        "prompt": prompt,
        "size": size_param,
        "width": gen_w,
        "height": gen_h,
        "watermark": False,
        "seed": seed,
    }
    if negative_prompt:
        data["negative_prompt"] = negative_prompt

    # Add reference image if available (for character + style consistency)
    if reference_frame and reference_frame.exists():
        ref_b64 = base64.b64encode(reference_frame.read_bytes()).decode("utf-8")
        data["image"] = f"data:image/jpeg;base64,{ref_b64}"
        data["strength"] = 0.55  # Strong reference — preserve character appearance from avatar sheet

    raw_path = output_path.parent / f"_raw_{output_path.name}"

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = req.post(
                "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations",
                headers=headers, json=data, timeout=1200,
            )
            if resp.status_code != 200:
                log.warning(f"Seedream poster error ({resp.status_code}): {resp.text[:200]}")
                if attempt < max_retries:
                    import time as _time
                    _time.sleep(5 * attempt)
                    continue
                return None

            result = resp.json()
            image_data = None
            for item in result.get("data", []):
                if item.get("b64_json"):
                    image_data = item["b64_json"]
                    break
                elif item.get("url"):
                    img_resp = req.get(item["url"], timeout=600)
                    if img_resp.status_code == 200:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        raw_path.write_bytes(img_resp.content)
                        break

            if image_data:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(base64.b64decode(image_data))
            elif not raw_path.exists():
                log.warning("Seedream returned no image data for poster")
                if attempt < max_retries:
                    import time as _time
                    _time.sleep(5 * attempt)
                    continue
                return None

            # Always resize to exact target dimensions to guarantee aspect ratio
            resized = _resize_poster(raw_path, output_path, width, height)
            if raw_path.exists():
                raw_path.unlink()
            if resized:
                return resized
            # Resize failed — use raw image as-is
            log.warning(f"Poster resize to {width}x{height} failed, using raw image")
            if raw_path.exists():
                raw_path.rename(output_path)
            return output_path if output_path.exists() else None
        except (req.exceptions.SSLError, req.exceptions.ConnectionError) as e:
            log.warning(f"Seedream poster network error (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                import time as _time
                _time.sleep(5 * attempt)
                continue
            return None
        except Exception as e:
            log.warning(f"Seedream poster generation failed: {e}")
            if raw_path.exists():
                raw_path.unlink()
            return None


def _resize_poster(source_path: Path, output_path: Path, width: int, height: int) -> Path | None:
    """Resize a poster image to exact dimensions using ffmpeg.

    Uses padding (letterbox/pillarbox) instead of cropping to avoid
    cutting off AI-generated title text in the poster.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(source_path),
        "-vf", (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
        ),
        "-q:v", "2",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode == 0 and output_path.exists():
        return output_path
    return None


# ---------------------------------------------------------------------------
# Font config persistence in style_guide.yaml
# ---------------------------------------------------------------------------


def _load_poster_font_config(story_slug: str) -> dict:
    """Load poster font configuration from style_guide.yaml.

    Returns dict with keys: font_family, title_font_size, subtitle_font_size,
    title_position, title_color, etc.  Returns empty dict if no config saved yet.
    """
    s_dir = story_dir(story_slug)
    style_path = s_dir / "style_guide.yaml"
    if not style_path.exists():
        return {}
    try:
        sg = yaml.safe_load(style_path.read_text(encoding="utf-8"))
        if isinstance(sg, dict):
            return sg.get("poster_typography", {}) or {}
    except Exception:
        pass
    return {}


def _save_poster_font_config(story_slug: str, font_config: dict) -> None:
    """Save poster font configuration to style_guide.yaml under 'poster_typography'.

    Called after the first episode poster generation to lock in the style
    for all subsequent episodes.
    """
    s_dir = story_dir(story_slug)
    style_path = s_dir / "style_guide.yaml"
    try:
        if style_path.exists():
            sg = yaml.safe_load(style_path.read_text(encoding="utf-8")) or {}
        else:
            sg = {}
        sg["poster_typography"] = font_config
        style_path.write_text(
            yaml.dump(sg, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        log.info(f"Saved poster font config to {style_path}")
    except Exception as e:
        log.warning(f"Failed to save poster font config: {e}")


def _get_poster_font_prompt(story_slug: str) -> str:
    """Build a font/typography instruction string for the Seedream prompt.

    Uses saved config from style_guide.yaml if available (episodes 2+),
    otherwise returns a default set for the first episode (which will be saved).
    """
    config = _load_poster_font_config(story_slug)
    if config:
        parts = []
        if config.get("font_style"):
            parts.append(f"title text in {config['font_style']} font style")
        if config.get("title_position"):
            parts.append(f"title positioned at {config['title_position']} of the poster")
        if config.get("title_color"):
            parts.append(f"title color {config['title_color']}")
        if config.get("subtitle_style"):
            parts.append(f"subtitle in {config['subtitle_style']}")
        parts.append("keep title text fully visible with safe margins from edges")
        return ", ".join(parts)

    # Default for first episode — will be saved after generation
    return (
        "title text in bold cinematic font style, "
        "title positioned at top area of the poster with safe margins, "
        "text fully visible and not cropped, "
        "clean readable title with contrast against background"
    )


def _default_poster_font_config() -> dict:
    """Return the default poster font config to save after first episode."""
    return {
        "font_style": "bold cinematic",
        "title_position": "top area with safe margins",
        "title_color": "white with dark shadow for contrast",
        "subtitle_style": "lighter weight, slightly smaller",
        "title_safe_margin_percent": 10,
        "notes": "Auto-generated during first episode poster creation. "
                 "Edit to customize font appearance for future episodes.",
    }


def generate_story_poster(
    story_slug: str,
    episode_number: int,
    reference_frame: Path | None = None,
) -> dict[str, Path]:
    """Generate 4 story poster variants using Seedream.

    Generates: horizontal_en, horizontal_zh, vertical_en, vertical_zh
    Stored in data/stories/{slug}/poster/
    Uses a "series overview" style — wide establishing shots, logo-like composition.
    Returns dict of {variant_name: path}.
    """
    s_dir = story_dir(story_slug)
    ep_dir = episode_dir(episode_number, story_slug)
    posters_dir = s_dir / "poster"

    # Clean stale story posters before regenerating
    if posters_dir.exists():
        shutil.rmtree(posters_dir)
        log.info(f"Cleaned stale story posters at {posters_dir}")

    posters_dir.mkdir(parents=True, exist_ok=True)

    # Load story metadata
    story_title_en = story_slug.replace("-", " ").title()
    story_title_zh = ""
    style_desc = ""

    # Primary source: store.json (has the actual titles in all languages)
    store_titles = _load_titles_from_store(story_slug, episode_number)
    if store_titles["story_title"]:
        story_title_en = store_titles["story_title"]
    if store_titles["story_title_zh"]:
        story_title_zh = store_titles["story_title_zh"]

    # Try loading style info from story bible (but NOT titles — store.json is authoritative)
    bible_path = s_dir / "story_bible.yaml"
    if bible_path.exists():
        try:
            bible = yaml.safe_load(bible_path.read_text(encoding="utf-8"))
            if isinstance(bible, dict):
                tone = bible.get("tone", {})
                style_desc = tone.get("visual_style", "") or tone.get("mood", "")
        except Exception:
            pass

    # Try loading style guide
    style_path = s_dir / "style_guide.yaml"
    if style_path.exists():
        try:
            sg = yaml.safe_load(style_path.read_text(encoding="utf-8"))
            if isinstance(sg, dict):
                style_desc = (
                    sg.get("animation_style", {}).get("description", "")
                    or sg.get("visual_style", "")
                    or style_desc
                )
        except Exception:
            pass

    # Load poster context from final summary + characters
    poster_ctx = _load_poster_context(ep_dir, story_slug)
    narrative_en = poster_ctx["narrative_summary"]
    narrative_zh = poster_ctx.get("narrative_summary_zh", "")
    char_descriptions = ", ".join(
        c.get("prompt_keywords", c["name"]) for c in poster_ctx["characters"] if c.get("name")
    )

    # Create composite reference: gallery frame + character avatars
    composite_ref = reference_frame
    if poster_ctx["character_avatars"] or reference_frame:
        composite_path = posters_dir / "_composite_ref.jpg"
        composite_ref = _create_composite_reference(
            reference_frame, poster_ctx["character_avatars"], composite_path,
        )

    negative_prompt = (
        "blurry, low quality, watermark, text errors, "
        "photorealistic, live action, ugly, deformed, "
        "text cut off at edges, cropped title, title text touching edges"
    )

    # Load poster font config (from style_guide.yaml if saved, else defaults)
    font_prompt = _get_poster_font_prompt(story_slug)
    font_config_existed = bool(_load_poster_font_config(story_slug))

    generated: dict[str, Path] = {}
    for orientation, lang, w, h in POSTER_VARIANTS:
        title = story_title_zh if lang == "zh" else story_title_en
        narrative = narrative_zh if (lang == "zh" and narrative_zh) else narrative_en
        if not title:
            title = story_title_en  # fallback

        # Orientation-specific composition guidance
        if orientation == "horizontal":
            composition_hints = [
                "wide cinematic landscape composition, 16:9 aspect ratio",
                "panoramic establishing shot of the story world",
                "epic wide-angle scene with characters in environment",
                "widescreen movie poster layout, horizontal framing",
            ]
        else:
            composition_hints = [
                "vertical portrait poster composition, 9:16 aspect ratio",
                "tall dramatic framing with characters prominent",
                "epic vertical composition with sky and ground",
                "portrait-oriented movie poster layout, vertical framing",
            ]

        prompt_parts = [
            f"Animated series key art poster for '{title}'",
        ]
        # Character descriptions FIRST (most important for accuracy)
        if char_descriptions:
            prompt_parts.append(f"MUST feature these exact characters: {char_descriptions}")
        prompt_parts.extend(composition_hints)
        if narrative:
            prompt_parts.append(f"story world: {narrative[:150]}")
        if style_desc:
            prompt_parts.append(style_desc)
        prompt_parts.extend([
            f"title text '{title}' as elegant logo",
            font_prompt,
            "series poster art, atmospheric lighting",
            "high quality illustration, vibrant colors, clean design",
        ])
        prompt = ", ".join(prompt_parts)

        variant_name = f"{orientation}_{lang}"
        poster_path = posters_dir / f"poster_{variant_name}.png"
        log.info(f"Generating story poster {variant_name} ({w}x{h}): '{title}'")

        result = _generate_poster_seedream(
            prompt, composite_ref, poster_path, w, h, negative_prompt,
        )
        if result:
            generated[variant_name] = result
            log.info(f"  Story poster {variant_name}: {result.name}")
        else:
            log.warning(f"  Story poster {variant_name} generation failed")

    log.info(f"Generated {len(generated)}/4 story poster variants")

    # Save default poster font config on first episode (if not already saved)
    if not font_config_existed and generated:
        _save_poster_font_config(story_slug, _default_poster_font_config())

    return generated


def generate_episode_poster(
    episode_number: int,
    story_slug: str,
    reference_frame: Path | None = None,
    episode_title: str | None = None,
) -> dict[str, Path]:
    """Generate 4 episode poster variants using Seedream.

    Generates: horizontal_en, horizontal_zh, vertical_en, vertical_zh
    Stored in episodes/{N}/final/poster/
    Uses a "dramatic scene moment" style — close-up action, emotional character focus.
    Returns dict of {variant_name: path}.
    """
    ep_dir = episode_dir(episode_number, story_slug)
    poster_dir = ep_dir / "final" / "poster"
    poster_dir.mkdir(parents=True, exist_ok=True)

    # Load poster context from final summary + characters
    poster_ctx = _load_poster_context(ep_dir, story_slug)
    narrative_en = poster_ctx["narrative_summary"]
    narrative_zh = poster_ctx.get("narrative_summary_zh", "")
    visual_style = poster_ctx.get("visual_style", "")
    char_descriptions = ", ".join(
        c.get("prompt_keywords", c["name"]) for c in poster_ctx["characters"] if c.get("name")
    )

    # Get episode titles in both languages (store.json is authoritative)
    store_titles = _load_titles_from_store(story_slug, episode_number)
    ep_title_en = store_titles["episode_title"] or episode_title or poster_ctx.get("title", "")
    ep_title_zh = store_titles["episode_title_zh"] or poster_ctx.get("title_zh", "")

    # Fallback: load from script.yaml
    if not ep_title_en or not ep_title_zh:
        script_path = ep_dir / "script.yaml"
        if script_path.exists():
            try:
                script_data = yaml.safe_load(script_path.read_text(encoding="utf-8"))
                ep_title_en = ep_title_en or script_data.get("title", "")
                ep_title_zh = ep_title_zh or script_data.get("title_zh", "")
            except Exception:
                pass
    if not ep_title_en:
        ep_title_en = f"Episode {episode_number}"

    # Get story titles for display on episode poster
    story_title_en = store_titles["story_title"] or story_slug.replace("-", " ").title()
    story_title_zh = store_titles["story_title_zh"] or story_title_en

    # Load style info as fallback
    style_desc = visual_style
    if not style_desc:
        s_dir = story_dir(story_slug)
        style_path = s_dir / "style_guide.yaml"
        if style_path.exists():
            try:
                sg = yaml.safe_load(style_path.read_text(encoding="utf-8"))
                if isinstance(sg, dict):
                    style_desc = (
                        sg.get("animation_style", {}).get("description", "")
                        or sg.get("visual_style", "")
                    )
            except Exception:
                pass

    # Create composite reference: gallery frame + character avatars
    composite_ref = reference_frame
    if poster_ctx["character_avatars"] or reference_frame:
        composite_path = poster_dir / "_composite_ref.jpg"
        composite_ref = _create_composite_reference(
            reference_frame, poster_ctx["character_avatars"], composite_path,
        )

    negative_prompt = (
        "blurry, low quality, watermark, text errors, "
        "photorealistic, live action, ugly, deformed, "
        "text cut off at edges, cropped title, title text touching edges"
    )

    # Load poster font config for consistent typography across episodes
    font_prompt = _get_poster_font_prompt(story_slug)

    generated: dict[str, Path] = {}
    for orientation, lang, w, h in POSTER_VARIANTS:
        title = ep_title_zh if (lang == "zh" and ep_title_zh) else ep_title_en
        story_title = story_title_zh if lang == "zh" else story_title_en
        narrative = narrative_zh if (lang == "zh" and narrative_zh) else narrative_en
        ep_label = f"EP{episode_number}" if lang == "en" else f"第{episode_number}集"

        # Orientation-specific composition guidance
        if orientation == "horizontal":
            composition_hints = [
                "wide cinematic scene composition, 16:9 landscape framing",
                "dramatic widescreen moment with characters in environment",
                "panoramic action scene, horizontal movie poster layout",
            ]
        else:
            composition_hints = [
                "vertical portrait poster composition, 9:16 aspect ratio",
                "dramatic character close-up in key story moment",
                "tall portrait framing, intense emotional expression",
            ]

        prompt_parts = [
            f"Episode poster for '{title}' ({ep_label})",
        ]
        # Character descriptions FIRST (most important for accuracy)
        if char_descriptions:
            prompt_parts.append(f"MUST feature these exact characters: {char_descriptions}")
        prompt_parts.extend([
            f"series title '{story_title}' displayed above episode title",
            *composition_hints,
        ])
        if narrative:
            prompt_parts.append(f"scene: {narrative[:150]}")
        if style_desc:
            prompt_parts.append(style_desc)
        prompt_parts.extend([
            f"story title '{story_title}' at top, episode title '{title}' and '{ep_label}' below it",
            font_prompt,
            "vivid scene illustration, movie poster style, emotional",
            "high quality, dynamic composition",
        ])
        prompt = ", ".join(prompt_parts)

        variant_name = f"{orientation}_{lang}"
        poster_path = poster_dir / f"poster_{variant_name}.png"
        log.info(f"Generating episode poster {variant_name} ({w}x{h}): '{title}' ({ep_label})")

        result = _generate_poster_seedream(
            prompt, composite_ref, poster_path, w, h, negative_prompt,
        )
        if result:
            generated[variant_name] = result
            log.info(f"  Episode poster {variant_name}: {result.name}")
        else:
            log.warning(f"  Episode poster {variant_name} generation failed")

    log.info(f"Generated {len(generated)}/4 episode poster variants")
    return generated


def _prepend_poster_to_video(
    video_path: Path,
    poster_path: Path,
    output_path: Path,
    poster_duration: float = 0.75,
) -> Path | None:
    """Prepend an episode poster as a still image to the beginning of a video.

    The poster is shown for *poster_duration* seconds then the original video
    plays.  A short crossfade smooths the transition.
    Returns the output path on success, or ``None``.
    """
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", str(video_path)],
            capture_output=True, text=True, timeout=150,
        )
        probe_data = json.loads(probe.stdout)
        video_stream = next(s for s in probe_data["streams"] if s["codec_type"] == "video")
        vid_w, vid_h = int(video_stream["width"]), int(video_stream["height"])
        has_audio = any(s["codec_type"] == "audio" for s in probe_data["streams"])
    except Exception as e:
        log.warning(f"Cannot probe video for poster prepend: {e}")
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fade_dur = min(0.3, poster_duration * 0.4)

    # Build filter_complex: poster image → video, then concat with main video
    vf = (
        f"[1:v]scale={vid_w}:{vid_h}:force_original_aspect_ratio=decrease,"
        f"pad={vid_w}:{vid_h}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,fps=24,trim=duration={poster_duration},"
        f"fade=t=out:st={poster_duration - fade_dur}:d={fade_dur}[pv];"
        f"[0:v]fade=t=in:st=0:d={fade_dur}[mv];"
        f"[pv][mv]concat=n=2:v=1:a=0[outv]"
    )

    cmd = ["ffmpeg", "-y", "-i", str(video_path),
           "-loop", "1", "-framerate", "24", "-t", str(poster_duration),
           "-i", str(poster_path)]

    if has_audio:
        vf += (
            f";anullsrc=r=44100:cl=stereo,atrim=0:{poster_duration}[sil];"
            f"[sil][0:a]concat=n=2:v=0:a=1[outa]"
        )
        cmd += ["-filter_complex", vf, "-map", "[outv]", "-map", "[outa]",
                "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-filter_complex", vf, "-map", "[outv]"]

    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", str(output_path)]

    log.info(f"Prepending poster ({poster_duration}s) to video: {video_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode == 0 and output_path.exists():
        log.info(f"  Poster prepended: {output_path.name}")
        return output_path
    else:
        log.warning(f"  Poster prepend failed: {(result.stderr or '')[:300]}")
        return None


# ---------------------------------------------------------------------------
# Full publish asset generation
# ---------------------------------------------------------------------------


def generate_publish_assets(
    episode_number: int,
    story_slug: str,
) -> dict:
    """Generate all publish assets: gallery frames, episode poster, story poster.

    Extracts frames from the pre-subtitle composed video for gallery,
    and uses them as reference for Seedream poster generation.

    Returns dict with paths to generated assets.
    """
    ep_dir = episode_dir(episode_number, story_slug)
    compose_dir = ep_dir / "compose"
    final_dir = ep_dir / "final"

    # Clean stale output directories before regenerating assets
    for sub in ["gallery", "poster", "video"]:
        sub_dir = final_dir / sub
        if sub_dir.exists():
            shutil.rmtree(sub_dir)
            log.info(f"Cleaned stale {sub_dir}")

    final_dir.mkdir(parents=True, exist_ok=True)

    # Find the composed video (checks timestamped run folders first)
    video_path = _find_composed_video(ep_dir, episode_number)
    if not video_path:
        log.warning(f"No composed video found. Skipping asset generation.")
        return {}

    # Copy composed video to final/video/
    import shutil
    video_out_dir = final_dir / "video"
    video_out_dir.mkdir(parents=True, exist_ok=True)
    final_video = video_out_dir / f"episode_{episode_number}.mp4"
    shutil.copy2(video_path, final_video)
    log.info(f"Final video copied to {final_video}")

    # Copy EN version if it exists
    en_video_path = _find_composed_video(ep_dir, episode_number, suffix="_EN")
    if en_video_path:
        final_en_video = video_out_dir / f"episode_{episode_number}_EN.mp4"
        shutil.copy2(en_video_path, final_en_video)
        log.info(f"EN video copied to {final_en_video}")

    assets: dict = {"gallery": [], "episode_posters": {}, "story_posters": {}}

    # 1. Extract gallery frames to final/gallery/ (first frame of each composed clip)
    gallery_dir = final_dir / "gallery"
    gallery_frames = extract_gallery_frames(video_path, gallery_dir, count=6, ep_dir=ep_dir)
    assets["gallery"] = gallery_frames

    # 2. Pick best reference frame for poster generation (middle of video)
    #    NOTE: gallery frames are NOT watermarked yet — clean reference for Seedream
    reference_frame = gallery_frames[len(gallery_frames) // 2] if gallery_frames else None

    # 3. Generate episode poster
    ep_poster = generate_episode_poster(
        episode_number, story_slug,
        reference_frame=reference_frame,
    )
    assets["episode_posters"] = ep_poster

    # 4. Generate story poster (uses this episode's frames as reference)
    # Only generate if no story poster exists yet (first episode) OR always regenerate
    story_posters = generate_story_poster(
        story_slug, episode_number,
        reference_frame=reference_frame,
    )
    assets["story_posters"] = story_posters

    # 5. Add logo watermark to gallery frames and posters (AFTER model generation)
    log.info("Adding logo watermark to gallery frames and posters...")
    for frame in gallery_frames:
        _add_logo_watermark(frame)
    for poster_path in ep_poster.values():
        _add_logo_watermark(poster_path)
    for poster_path in story_posters.values():
        _add_logo_watermark(poster_path)

    # 6. Prepend episode poster to final videos
    #    Chinese video → zh poster, English video → en poster
    #    Pick horizontal or vertical poster based on video aspect ratio
    #    Falls back to other language poster if exact match not found
    poster_dir = final_dir / "poster"
    for vid, lang in [(final_video, "zh")] + ([(final_en_video, "en")] if en_video_path else []):
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", str(vid)],
                capture_output=True, text=True, timeout=150,
            )
            info = json.loads(probe.stdout)
            vs = next(s for s in info["streams"] if s["codec_type"] == "video")
            orientation = "vertical" if int(vs["height"]) > int(vs["width"]) else "horizontal"
        except Exception:
            orientation = "vertical"
        other_lang = "en" if lang == "zh" else "zh"
        poster_file = poster_dir / f"poster_{orientation}_{lang}.png"
        if not poster_file.exists():
            poster_file = poster_dir / f"poster_{orientation}_{other_lang}.png"
            if poster_file.exists():
                log.info(f"  Poster {orientation}_{lang} not found, falling back to {orientation}_{other_lang}")
        if poster_file.exists():
            out = vid.parent / f"{vid.stem}_with_poster{vid.suffix}"
            result = _prepend_poster_to_video(vid, poster_file, out)
            if result:
                # Replace original with poster version
                vid.unlink()
                out.rename(vid)
                log.info(f"  Replaced {vid.name} with poster-prepended version")
        else:
            log.warning(f"  No poster found for prepend ({orientation}_{lang} or {orientation}_{other_lang})")

    # Save asset manifest
    manifest = {
        "episode_number": episode_number,
        "story_slug": story_slug,
        "gallery": [str(f.relative_to(ep_dir)) for f in gallery_frames],
        "episode_posters": {k: str(v.relative_to(ep_dir)) for k, v in ep_poster.items()} if ep_poster else {},
        "story_posters": {k: str(v) for k, v in story_posters.items()},
    }
    save_yaml(manifest, ep_dir / "publish_assets.yaml")
    log.info(f"Publish assets manifest saved: {ep_dir / 'publish_assets.yaml'}")

    return assets


# ---------------------------------------------------------------------------
# VLM-based final summary generation
# ---------------------------------------------------------------------------


def generate_vlm_final_summary(episode_number: int, story_slug: str) -> Path | None:
    """Generate a detailed episode summary using VLM analysis of keyframes + clip metadata.

    Extracts keyframes from the composed video, combines them with clip YAML data,
    and uses a VLM (GPT-4o) to produce a rich narrative summary for continuity
    in the next episode's script generation.
    """
    from llm import call_vlm, parse_yaml_response

    ep_dir = episode_dir(episode_number, story_slug)

    # Find the composed video (checks timestamped run folders first)
    video_path = _find_composed_video(ep_dir, episode_number)
    if not video_path:
        log.warning("No composed video found for VLM summary. Falling back to basic summary.")
        from compose_episode import finalize_summary
        return finalize_summary(ep_dir)

    # Extract keyframes: 1 per ~5s of video for comprehensive understanding
    import tempfile
    keyframes_dir = Path(tempfile.mkdtemp(prefix="vlm_frames_"))

    try:
        # Get video duration
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video_path)],
            capture_output=True, text=True, timeout=150,
        )
        probe_data = json.loads(probe.stdout)
        duration = float(probe_data["format"]["duration"])
    except Exception:
        duration = 120.0

    # Extract frames every ~5s (up to 20 frames for a 2-min video)
    num_frames = min(20, max(8, int(duration / 5)))
    interval = duration / (num_frames + 1)
    frame_paths: list[Path] = []
    for i in range(1, num_frames + 1):
        timestamp = interval * i
        frame_path = keyframes_dir / f"frame_{i:02d}.jpg"
        cmd = [
            "ffmpeg", "-y", "-ss", f"{timestamp:.2f}",
            "-i", str(video_path),
            "-frames:v", "1", "-q:v", "5",
            "-vf", "scale=720:-1",
            str(frame_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=150)
        if result.returncode == 0 and frame_path.exists():
            frame_paths.append(frame_path)

    log.info(f"Extracted {len(frame_paths)} keyframes for VLM analysis")

    # Load clip metadata from temp_final_summary or scenes
    temp_summary_path = ep_dir / "temp_final_summary.yaml"
    clip_context = ""
    if temp_summary_path.exists():
        temp_data = load_yaml(str(temp_summary_path))
        clips_info = temp_data.get("composed_clips", [])
        for clip in clips_info:
            clip_context += f"\n- {clip.get('clip_name', 'unknown')}: {clip.get('prompt', clip.get('action', ''))}"
            if clip.get("dialogue"):
                for d in clip["dialogue"]:
                    if isinstance(d, dict):
                        clip_context += f"\n  [{d.get('character', '?')}]: {d.get('line', '')}"

    # Load script for additional context
    script_path = ep_dir / "script.yaml"
    script_context = ""
    if script_path.exists():
        try:
            script_data = load_yaml(str(script_path))
            script_context = f"Episode Title: {script_data.get('title', '')}\nTitle (ZH): {script_data.get('title_zh', '')}"
        except Exception:
            pass

    # Load character names
    chars_dir = story_dir(story_slug) / "characters"
    character_names = []
    if chars_dir.exists():
        for yml in chars_dir.glob("*.yaml"):
            if yml.name == "README.yaml":
                continue
            try:
                char_data = yaml.safe_load(yml.read_text(encoding="utf-8"))
                if isinstance(char_data, dict):
                    character_names.append(f"{char_data.get('name', '')} ({char_data.get('name_zh', '')})")
            except Exception:
                pass

    # Detect story primary language (cached in story_bible.yaml)
    story_language = get_story_language(story_slug)

    if story_language == "zh":
        language_instruction = (
            "IMPORTANT: This story's original language is Chinese (中文). "
            "Write the PRIMARY narrative_summary in Chinese. "
            "Write narrative_summary_en as the English translation. "
            "All text fields (title, key_events, character_states, ending_state, "
            "visual_style_notes, continuity_notes, unresolved_threads) should be written in Chinese first, "
            "with _en suffixed fields for English translations."
        )
    else:
        language_instruction = (
            "This story's original language is English. "
            "Write the PRIMARY narrative_summary in English. "
            "Write narrative_summary_zh as the Chinese translation."
        )

    # Build VLM prompt
    system_prompt = (
        "You are a story analyst for an animated short video series. "
        "Analyze the provided keyframes and clip metadata to generate a detailed narrative summary. "
        "This summary will be used by the script writer for the NEXT episode to maintain continuity. "
        "Output ONLY valid YAML."
    )

    user_prompt = f"""Analyze these {len(frame_paths)} keyframes from Episode {episode_number} and generate a detailed summary.

{language_instruction}

## Episode Info
{script_context}

## Characters
{chr(10).join(character_names) if character_names else "Not specified"}

## Clip Sequence (what was composed)
{clip_context if clip_context else "Not available"}

## Required Output (YAML format)
Generate a comprehensive episode summary with these fields.
{"Write ALL text fields in Chinese (中文) as the primary language. Add _en suffixed fields for English translations." if story_language == "zh" else "Write ALL text fields in English as the primary language. Add _zh suffixed fields for Chinese translations."}

```yaml
episode_number: {episode_number}
title: "<episode title in {'Chinese' if story_language == 'zh' else 'English'}>"
title_{'en' if story_language == 'zh' else 'zh'}: "<translated title>"

narrative_summary: |
  <2-3 paragraph detailed narrative in {'Chinese' if story_language == 'zh' else 'English'},
   including key plot points, character actions, emotional beats,
   and the state of affairs at the end>

narrative_summary_{'en' if story_language == 'zh' else 'zh'}: |
  <same summary translated to {'English' if story_language == 'zh' else 'Chinese'}>

key_events:
  - "<event 1 in {'Chinese' if story_language == 'zh' else 'English'}>"
  - "<event 2>"
  - "<event 3>"

character_states:
  - name: "<character name in {'Chinese' if story_language == 'zh' else 'English'}>"
    name_{'en' if story_language == 'zh' else 'zh'}: "<translated name>"
    status: "<where they are / what they're doing at episode end>"
    emotional_state: "<how they feel>"
    relationships: "<any relationship changes>"

unresolved_threads:
  - "<plot thread in {'Chinese' if story_language == 'zh' else 'English'}>"

ending_state: |
  <describe the exact visual/narrative state at the end of this episode in {'Chinese' if story_language == 'zh' else 'English'}>

visual_style_notes: |
  <describe the visual style, color palette, and animation approach observed>

continuity_notes: |
  <important details the next episode must maintain for consistency>
```
"""

    try:
        raw_response = call_vlm(system_prompt, user_prompt, frame_paths, max_tokens=4000)
        summary_data = parse_yaml_response(raw_response)
        summary_data["status"] = "final"
        summary_data["episode_number"] = episode_number

        # Save to both locations
        final_path = ep_dir / "final_summary.yaml"
        save_yaml(summary_data, str(final_path))

        final_folder_path = ep_dir / "final" / "final_summary.yaml"
        final_folder_path.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(summary_data, str(final_folder_path))

        log.info(f"VLM-based final summary saved: {final_path}")
        return final_path
    except Exception as e:
        log.warning(f"VLM summary generation failed: {e}. Falling back to basic summary.")
        from compose_episode import finalize_summary
        return finalize_summary(ep_dir)
    finally:
        # Cleanup temp keyframes
        import shutil as _shutil
        try:
            _shutil.rmtree(keyframes_dir, ignore_errors=True)
        except Exception:
            pass


def publish(
    episode_number: int,
    spec: dict,
    config: dict,
    draft: bool = False,
    story_slug: str | None = None,
) -> bool:
    """Publish episode to website.

    Flow:
    1. Update video URLs and status in store.json
    2. Post vote options from publish spec to store.json
    3. Set voting deadline (starts counting from publish time)
    4. Generate publish assets (gallery from clip first-frames, posters)
    """
    mode = "DRAFT" if draft else "LIVE"
    log.info(f"Publishing Episode {episode_number} [{mode}]")

    publish_data = spec.get("publish", spec)
    log.info(f"  Title: {publish_data.get('title', 'Untitled')}")
    log.info(f"  Site: {config['site']['url']}")

    poll = publish_data.get("poll", {})
    if poll:
        log.info(f"  Poll: {poll.get('question', 'No question')}")
        for i, opt in enumerate(poll.get("options", []), 1):
            label = opt if isinstance(opt, str) else opt.get("label", "")
            log.info(f"    {i}. {label}")

    log.info(f"Episode {episode_number} published successfully!")

    # Update store.json: video URLs, status, vote options, voting deadline
    if story_slug:
        store_path = get_project_root() / "site" / "data" / "store.json"
        if store_path.exists():
            try:
                store_data = json.loads(store_path.read_text(encoding="utf-8"))
                story_obj = next((s for s in store_data.get("stories", []) if s.get("slug") == story_slug), None)
                if story_obj:
                    ep_obj = next(
                        (e for e in store_data.get("episodes", [])
                         if e.get("story_id") == story_obj["id"] and e.get("episode_number") == episode_number),
                        None,
                    )
                    if ep_obj:
                        # Video URLs
                        ep_obj["video_url"] = f"/api/assets/{story_slug}/episodes/{episode_number}/final/video/episode_{episode_number}.mp4"
                        ep_dir_check = episode_dir(episode_number, story_slug)
                        en_video = _find_composed_video(ep_dir_check, episode_number, suffix="_EN")
                        if not en_video:
                            en_candidate = ep_dir_check / "final" / "video" / f"episode_{episode_number}_EN.mp4"
                            if en_candidate.exists():
                                en_video = en_candidate
                        if en_video:
                            ep_obj["video_url_en"] = f"/api/assets/{story_slug}/episodes/{episode_number}/final/video/episode_{episode_number}_EN.mp4"
                            log.info(f"  EN video URL set in store.json")

                        # Status
                        if not draft:
                            ep_obj["status"] = "published"
                            log.info(f"  Episode status set to 'published'")

                        # Vote options: write poll options to store.json vote_options array
                        if poll and poll.get("options") and not draft:
                            # Remove any existing vote options for this episode
                            store_data["vote_options"] = [
                                vo for vo in store_data.get("vote_options", [])
                                if vo.get("episode_id") != ep_obj["id"]
                            ]
                            next_id = store_data.get("next_id", {})
                            vote_opt_id = next_id.get("vote_options", 1)
                            for i, opt in enumerate(poll.get("options", [])):
                                if isinstance(opt, str):
                                    label = opt
                                    label_zh = opt
                                    description = None
                                    description_zh = None
                                else:
                                    label = opt.get("label", "")
                                    label_zh = opt.get("label_zh", label)
                                    description = opt.get("teaser") or opt.get("description")
                                    description_zh = opt.get("teaser_zh") or opt.get("description_zh") or description
                                store_data.setdefault("vote_options", []).append({
                                    "id": vote_opt_id,
                                    "episode_id": ep_obj["id"],
                                    "label": label,
                                    "label_zh": label_zh,
                                    "description": description,
                                    "description_zh": description_zh,
                                    "sort_order": i,
                                })
                                vote_opt_id += 1
                            next_id["vote_options"] = vote_opt_id
                            store_data["next_id"] = next_id

                            # Open voting and set deadline (env override)
                            import os
                            env_hours = os.environ.get("VOTE_DEADLINE_HOURS", "")
                            if env_hours:
                                try:
                                    deadline_hours = eval(env_hours)  # supports "365*24"
                                except Exception:
                                    deadline_hours = poll.get("deadline_hours", 72)
                            else:
                                deadline_hours = poll.get("deadline_hours", 72)
                            from datetime import datetime, timedelta, timezone
                            now = datetime.now(timezone.utc)
                            deadline = now + timedelta(hours=int(deadline_hours))
                            ep_obj["voting_open"] = True
                            ep_obj["voting_deadline"] = deadline.isoformat()
                            log.info(f"  Voting opened with {len(poll['options'])} options, deadline in {deadline_hours}h")

                        _atomic_write_json(store_path, store_data)
                        log.info(f"  Store.json updated (video URLs, votes, status)")
            except Exception as e:
                log.warning(f"Failed to update store.json: {e}")

    # Generate publish assets (posters + gallery) after non-draft publish
    if not draft and story_slug:
        log.info("Generating publish assets (posters + gallery)...")
        try:
            assets = generate_publish_assets(episode_number, story_slug)
            if assets.get("gallery"):
                log.info(f"  Gallery: {len(assets['gallery'])} images")
            if assets.get("episode_posters"):
                log.info(f"  Episode posters: {len(assets['episode_posters'])} variants")
            if assets.get("story_posters"):
                log.info(f"  Story posters: {len(assets['story_posters'])} variants")

            # Update store.json with poster and gallery URLs
            store_path = get_project_root() / "site" / "data" / "store.json"
            if store_path.exists():
                try:
                    store_data = json.loads(store_path.read_text(encoding="utf-8"))
                    story_obj = next((s for s in store_data.get("stories", []) if s.get("slug") == story_slug), None)
                    if story_obj:
                        ep_obj = next(
                            (e for e in store_data.get("episodes", [])
                             if e.get("story_id") == story_obj["id"] and e.get("episode_number") == episode_number),
                            None,
                        )
                        if ep_obj:
                            if assets.get("episode_posters"):
                                # Use horizontal_en as the default poster URL
                                default_poster = "poster_horizontal_en.png"
                                if "horizontal_en" in assets["episode_posters"]:
                                    default_poster = assets["episode_posters"]["horizontal_en"].name
                                ep_obj["poster_url"] = f"/api/assets/{story_slug}/episodes/{episode_number}/final/poster/{default_poster}"
                            if assets.get("gallery"):
                                ep_obj["gallery"] = [
                                    f"/api/assets/{story_slug}/episodes/{episode_number}/final/gallery/{p.name}"
                                    for p in assets["gallery"]
                                ]
                            if not story_obj.get("poster_episode_id"):
                                story_obj["poster_episode_id"] = ep_obj["id"]
                            _atomic_write_json(store_path, store_data)
                            log.info(f"  Store.json updated with poster/gallery URLs")
                except Exception as e:
                    log.warning(f"Failed to update store.json with assets: {e}")
        except Exception as e:
            log.warning(f"Asset generation failed (non-blocking): {e}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Publish episode to website")
    parser.add_argument("--episode", type=int, required=True, help="Episode number")
    parser.add_argument("--story", type=str, default=None, help="Story slug")
    parser.add_argument("--draft", action="store_true", help="Publish as draft")
    args = parser.parse_args()

    try:
        config = load_config()
    except FileNotFoundError as e:
        log.error(f"Publishing config not found: {e}")
        sys.exit(1)

    # Step 1: Generate VLM-based final summary FIRST (so publish spec can use it for voting)
    if not args.draft and args.story:
        log.info("Step 1: Generating VLM-based final summary from composed video...")
        generate_vlm_final_summary(args.episode, args.story)

    # Step 2: Generate publish spec (voting options based on VLM summary of actual video)
    spec = load_publish_spec(args.episode, args.story)
    if not spec:
        if args.story:
            spec = generate_publish_spec_with_llm(args.episode, args.story)
        else:
            log.error(f"No publish spec found. Provide --story to auto-generate one.")
            sys.exit(1)

    # Step 3: Publish (video URLs, vote options, deadline, assets)
    publish(args.episode, spec, config, draft=args.draft, story_slug=args.story)


if __name__ == "__main__":
    main()
