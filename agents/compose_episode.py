"""Compose Episode

Stitches selected scene video clips into a final episode with transitions,
optional audio overlay, random watermark placement, and summary generation.

Usage:
    python agents/compose_episode.py --episode <number> --story <slug>
    python agents/compose_episode.py --episode 1 --story my-story --transitions crossfade
    python agents/compose_episode.py --episode 1 --story my-story --mute-video-audio
    python agents/compose_episode.py --episode 1 --story my-story --list-assets
"""

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from common import (
    config_path,
    episode_dir,
    fetch_story_from_api,
    get_project_root,
    get_story_language,
    load_env,
    load_yaml,
    save_yaml,
    setup_logging,
)

load_env()
log = setup_logging("compose_episode")

PROJECT_ROOT = get_project_root()

# Map HUGGINGFACE_API_TOKEN → HF_TOKEN if not already set
# (HuggingFace libraries expect HF_TOKEN for authenticated access)
if not os.environ.get("HF_TOKEN") and os.environ.get("HUGGINGFACE_API_TOKEN"):
    os.environ["HF_TOKEN"] = os.environ["HUGGINGFACE_API_TOKEN"]


def load_config() -> dict:
    """Load composition config."""
    return load_yaml(config_path("composition.yaml"))


# ---------------------------------------------------------------------------
# Asset discovery
# ---------------------------------------------------------------------------


def _natural_sort_key(p: Path) -> list:
    """Sort filenames naturally: scene_1 < scene_2 < scene_10."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", p.name)]


def discover_clips(ep_dir: Path, clips_run_ts: str | None = None) -> list[Path]:
    """Find all video clips for an episode in the clips/<run_ts>/ directory."""
    clips_dir = ep_dir / "clips"

    if clips_run_ts:
        clips_run_dir = clips_dir / clips_run_ts
    else:
        # Use SELECTED_CLIPS_DIR env or latest
        selected = os.environ.get("SELECTED_CLIPS_DIR")
        if selected:
            clips_run_dir = clips_dir / selected
        elif clips_dir.exists():
            subdirs = sorted([d for d in clips_dir.iterdir() if d.is_dir()], reverse=True)
            clips_run_dir = subdirs[0] if subdirs else clips_dir
        else:
            return []

    if not clips_run_dir.exists():
        return []

    # Find all .mp4 files, excluding .regen files and segment files
    clips = sorted(
        [
            f
            for f in clips_run_dir.glob("scene_*.mp4")
            if ".regen" not in f.name and "_segment" not in f.name
        ],
        key=_natural_sort_key,
    )
    return clips


def discover_audio_files(ep_dir: Path) -> list[Path]:
    """Find all audio files for an episode (audio/<run_ts>/)."""
    audio_dir = ep_dir / "audio"
    if not audio_dir.exists():
        return []

    # Use SELECTED_AUDIO_DIR env or latest
    selected = os.environ.get("SELECTED_AUDIO_DIR")
    if selected:
        audio_run_dir = audio_dir / selected
    else:
        subdirs = sorted([d for d in audio_dir.iterdir() if d.is_dir()], reverse=True)
        if subdirs:
            audio_run_dir = subdirs[0]
        else:
            # No subdirs — check audio_dir itself for files
            audio_run_dir = audio_dir

    if not audio_run_dir.exists():
        return []

    audio_files = sorted(
        list(audio_run_dir.glob("*.wav")) + list(audio_run_dir.glob("*.mp3")),
        key=_natural_sort_key,
    )
    return audio_files


def list_assets(ep_dir: Path) -> dict:
    """List all available clips and audio files for selection.

    Returns a dict with:
      clips: [{name, path, scene, clip, duration_seconds, size_kb, selected}]
      audio: [{name, path, size_kb, selected}]
    """
    clips = discover_clips(ep_dir)
    audio_files = discover_audio_files(ep_dir)

    clip_info = []
    for clip_path in clips:
        info: dict = {
            "name": clip_path.name,
            "path": str(clip_path),
            "size_kb": round(clip_path.stat().st_size / 1024, 1),
            "selected": True,
        }
        # Parse scene/clip numbers from filename
        match = re.match(r"scene_(\d+)_clip_(\d+)", clip_path.stem)
        if match:
            info["scene"] = int(match.group(1))
            info["clip"] = int(match.group(2))

        # Try to get duration via ffprobe
        try:
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "quiet", "-show_entries",
                    "format=duration", "-of", "csv=p=0", str(clip_path),
                ],
                capture_output=True, text=True, timeout=50,
            )
            if probe.returncode == 0 and probe.stdout.strip():
                info["duration_seconds"] = round(float(probe.stdout.strip()), 2)
        except Exception:
            pass

        clip_info.append(info)

    audio_info = []
    for af in audio_files:
        audio_info.append({
            "name": af.name,
            "path": str(af),
            "size_kb": round(af.stat().st_size / 1024, 1),
            "selected": True,
        })

    return {"clips": clip_info, "audio": audio_info}


# ---------------------------------------------------------------------------
# Language Detection
# ---------------------------------------------------------------------------


def _detect_content_language(text: str) -> str:
    """Detect primary language of text. Delegates to common.detect_content_language."""
    from common import detect_content_language
    return detect_content_language(text)


def _detect_story_language(story_slug: str | None) -> str:
    """Detect content language from the story. Delegates to common.get_story_language."""
    if not story_slug:
        return os.environ.get("CONTENT_LANGUAGE", "en")
    return get_story_language(story_slug)


# ---------------------------------------------------------------------------
# Episode Opening Generation
# ---------------------------------------------------------------------------


def _extract_first_frame(clip_path: Path) -> Path | None:
    """Extract the first frame from a video clip as a JPEG image."""
    out_path = clip_path.parent / f"{clip_path.stem}_first_frame.jpg"
    cmd = [
        "ffmpeg", "-y", "-i", str(clip_path),
        "-frames:v", "1", "-q:v", "2",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if result.returncode == 0 and out_path.exists():
        return out_path
    return None


def _generate_opening_ffmpeg(
    first_frame_path: Path,
    story_name: str,
    episode_title: str,
    disclaimer_text: str,
    output_path: Path,
    duration: float = 2.0,
) -> Path | None:
    """Generate opening using ffmpeg text overlay on first frame.

    Displays story name, episode title, AI disclaimer, and "AI生成" label with CJK-compatible fonts.
    Font sizes are dynamically adjusted to fit within the video width.
    Episode title font is one level smaller than the story name.
    "AI生成" label is shown for the full duration (≥2s) to satisfy platform requirements.
    """
    # Get video dimensions from first frame
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(first_frame_path)],
            capture_output=True, text=True, timeout=100,
        )
        probe_data = json.loads(probe.stdout)
        stream = next(s for s in probe_data["streams"] if s["codec_type"] == "video")
        vid_w, vid_h = int(stream["width"]), int(stream["height"])
    except Exception:
        vid_w, vid_h = 720, 1280

    # Find a CJK-compatible font (try common locations)
    font_candidates = [
        "C:/Windows/Fonts/msyh.ttc",          # Microsoft YaHei (Windows)
        "C:/Windows/Fonts/msyhbd.ttc",         # Microsoft YaHei Bold (Windows)
        "C:/Windows/Fonts/simhei.ttf",         # SimHei (Windows)
        "C:/Windows/Fonts/simsun.ttc",         # SimSun (Windows)
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # Linux
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",  # macOS
    ]
    font_path = None
    for fp in font_candidates:
        if Path(fp).exists():
            font_path = fp
            break

    # Escape text for ffmpeg drawtext filter
    def _esc(text: str) -> str:
        return (
            text
            .replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "'\\\\''")
            .replace("%", "%%")
        )

    disc_esc = _esc(disclaimer_text)

    # Dynamic font sizing: estimate character width and scale to fit within 85% of video width
    max_text_width = vid_w * 0.85
    # CJK chars are roughly square; Latin chars ~0.55 width ratio to font size
    def _estimate_text_px_width(text: str, font_size: int) -> float:
        """Estimate pixel width of text at a given font size."""
        cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf'
                        or '\uf900' <= c <= '\ufaff' or '\U00020000' <= c <= '\U0002a6df')
        latin_count = len(text) - cjk_count
        return cjk_count * font_size + latin_count * font_size * 0.55

    def _fit_font_size(text: str, max_size: int, min_size: int = 16) -> int:
        """Find the largest font size that fits text within max_text_width."""
        for size in range(max_size, min_size - 1, -1):
            if _estimate_text_px_width(text, size) <= max_text_width:
                return size
        return min_size

    def _wrap_text(text: str, font_size: int) -> list[str]:
        """Wrap text into multiple lines that each fit within max_text_width."""
        if _estimate_text_px_width(text, font_size) <= max_text_width:
            return [text]
        words = list(text)  # split by character for CJK
        # For Latin text, split by words
        if all(ord(c) < 0x3000 for c in text):
            words = text.split()
            lines = []
            current = ""
            for word in words:
                test = f"{current} {word}".strip() if current else word
                if _estimate_text_px_width(test, font_size) <= max_text_width:
                    current = test
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
            return lines if lines else [text]
        else:
            # CJK: split at roughly half
            mid = len(text) // 2
            # Try to find a good break point near the middle
            return [text[:mid], text[mid:]]

    # Base font sizes relative to video height
    story_max_size = max(int(vid_h * 0.045), 32)
    ep_max_size = max(int(vid_h * 0.035), 24)
    disc_size = max(int(vid_h * 0.022), 14)

    # Fit story name font to width, then episode font is one level smaller
    story_size = _fit_font_size(story_name, story_max_size) if story_name else story_max_size
    # Split story name by colon ("：" or ":") into separate lines first, then wrap each
    if story_name and ("：" in story_name or ":" in story_name):
        colon = "：" if "：" in story_name else ":"
        parts = [p.strip() for p in story_name.split(colon, 1) if p.strip()]
        # Re-fit font size to the longest part
        if parts:
            longest = max(parts, key=len)
            story_size = _fit_font_size(longest, story_max_size)
        story_lines = []
        part_i = 0
        for part in parts:
            if part_i == 0:
                part = f"{part} :"
                part_i += 1
            story_lines.extend(_wrap_text(part, story_size))
    else:
        story_lines = _wrap_text(story_name, story_size) if story_name else []

    # Episode title: fit independently, but cap at story_size - step
    ep_size_cap = max(story_size - 4, ep_max_size - 8, 16)
    ep_size = _fit_font_size(episode_title, min(ep_max_size, ep_size_cap)) if episode_title else ep_max_size
    # Ensure episode font is strictly smaller than story font
    if ep_size >= story_size:
        ep_size = max(story_size - 4, 16)
    ep_lines = _wrap_text(episode_title, ep_size) if episode_title else []

    # Build font parameter (use forward slashes for ffmpeg on Windows)
    if font_path:
        font_path_esc = font_path.replace("\\", "/").replace(":", "\\:")
        font_param = f"fontfile='{font_path_esc}'"
    else:
        font_param = "font='Microsoft YaHei'"

    # "AI Generated" / "AI生成" label size — shown for the full duration at top-left
    ai_label_size = max(int(vid_h * 0.028), 18)
    ai_label_esc = _esc(disclaimer_text)

    # Build filter: darken + vignette + AI label + story name lines + episode title lines + disclaimer
    target_fps = int(os.environ.get("VIDEO_FPS", "24"))
    vf = (
        f"loop=loop={int(duration * target_fps)}:size=1:start=0,"
        f"setpts=PTS-STARTPTS,"
        f"fps={target_fps},"
        # Darken and add cinematic vignette
        f"colorbalance=bs=-0.2:gs=-0.2:rs=-0.15,"
        f"vignette=PI/4,"
        # "AI生成" label — top-left, visible from t=0 for full duration (≥2s platform requirement)
        f"drawtext=text='{ai_label_esc}'"
        f":{font_param}:fontsize={ai_label_size}:fontcolor=white@0.85"
        f":borderw=2:bordercolor=black@0.5"
        f":x={int(vid_w * 0.04)}:y={int(vid_h * 0.03)}"
        f":alpha=1"
    )

    # Story name lines — centered, stacked above vertical center
    story_line_gap = int(vid_h * 0.005)
    total_story_height = len(story_lines) * story_size + max(0, len(story_lines) - 1) * story_line_gap
    story_start_y = vid_h // 2 - int(vid_h * 0.08) - total_story_height
    for i, line in enumerate(story_lines):
        line_esc = _esc(line)
        y_pos = story_start_y + i * (story_size + story_line_gap)
        vf += (
            f",drawtext=text='{line_esc}'"
            f":{font_param}:fontsize={story_size}:fontcolor=white"
            f":borderw=3:bordercolor=black@0.6:shadowx=2:shadowy=2:shadowcolor=black@0.4"
            f":x=(w-text_w)/2:y={y_pos}"
            f":alpha='if(lt(t,0.3),t/0.3,1)'"
        )

    # Episode title lines — each on its own drawtext, stacked below center
    ep_line_gap = int(vid_h * 0.005)
    for i, line in enumerate(ep_lines):
        line_esc = _esc(line)
        y_offset = int(vid_h * 0.02) + i * (ep_size + ep_line_gap)
        vf += (
            f",drawtext=text='{line_esc}'"
            f":{font_param}:fontsize={ep_size}:fontcolor=0xE0D0FF"
            f":borderw=2:bordercolor=black@0.5:shadowx=1:shadowy=1:shadowcolor=black@0.3"
            f":x=(w-text_w)/2:y=(h/2)+{y_offset}"
            f":alpha='if(lt(t,0.5),0,if(lt(t,0.9),(t-0.5)/0.4,1))'"
        )

    # AI disclaimer (bottom)
    vf += (
        f",drawtext=text='{disc_esc}'"
        f":{font_param}:fontsize={disc_size}:fontcolor=white@0.6"
        f":borderw=1:bordercolor=black@0.3"
        f":x=(w-text_w)/2:y=h-text_h-{int(vid_h * 0.06)}"
        f":alpha='if(lt(t,0.8),0,if(lt(t,1.2),(t-0.8)/0.4,1))'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(first_frame_path),
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-color_range", "tv", "-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709",
        "-an",
        str(output_path),
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if result.returncode == 0 and output_path.exists():
        log.info(f"  FFmpeg opening clip saved: {output_path}")
        return output_path
    else:
        stderr_msg = (result.stderr or "")
        log.warning(f"  FFmpeg opening generation failed: {stderr_msg[-500:]}")
        return None


def generate_episode_opening(
    episode_number: int,
    story_slug: str | None,
    first_clip: Path,
    output_dir: Path,
    episode_title: str | None = None,
    content_lang: str | None = None,
    override_story_name: str | None = None,
) -> Path | None:
    """Generate a 2-second episode opening video with story name, episode number, and AI disclaimer.

    Args:
        override_story_name: If set, use this as the story name (e.g. English name for EN version).
    Returns path to the opening clip, or None if generation failed.
    """
    # Detect content language from story background (same logic as generate_episode.py)
    if not content_lang:
        content_lang = _detect_story_language(story_slug)

    # Load story name from API or script.yaml
    story_name = override_story_name or ""
    if not story_name:
        # Try website API first
        story = fetch_story_from_api(story_slug) if story_slug else None
        if story:
            story_name = (
                story.get("title_zh")
                or story.get("title", "")
            ) if content_lang == "zh" else (
                story.get("title")
                or story.get("title_zh", "")
            )

        # Fallback: read from script.yaml (has title / title_zh at root)
        if not story_name and story_slug:
            try:
                from common import episode_dir as _ep_dir
                # Try to find any episode script with the story title
                stories_dir = get_project_root() / "data" / "stories" / story_slug
                # Look for the latest episode script
                ep_dirs = sorted(stories_dir.glob("episodes/*/script.yaml"))
                if ep_dirs:
                    script_data = yaml.safe_load(ep_dirs[-1].read_text(encoding="utf-8"))
                    if script_data:
                        story_name = (
                            script_data.get("title_zh")
                            or script_data.get("title", "")
                        ) if content_lang == "zh" else (
                            script_data.get("title")
                            or script_data.get("title_zh", "")
                        )
            except Exception:
                pass

    # Episode title: just the number
    episode_title = f"第{episode_number}集" if content_lang == "zh" else f"Episode {episode_number}"

    # AI disclaimer
    disclaimer_text = "AI生成" if content_lang == "zh" else "AI Generated"

    log.info(f"Generating episode opening (2s): '{story_name}' | '{episode_title}' | '{disclaimer_text}'")
    first_frame = _extract_first_frame(first_clip)
    if not first_frame:
        log.warning("  Could not extract first frame. Skipping opening.")
        return None

    output_path = output_dir / f"episode_{episode_number}_opening.mp4"

    # Generate opening with ffmpeg text overlay on first frame
    opening = _generate_opening_ffmpeg(
        first_frame, story_name, episode_title, disclaimer_text, output_path,
    )
    first_frame.unlink(missing_ok=True)
    return opening


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


def _has_ffmpeg() -> bool:
    """Check if ffmpeg is available on PATH."""
    return shutil.which("ffmpeg") is not None


def _probe_clip(clip_path: Path) -> dict:
    """Probe a clip for resolution, duration, and audio stream presence."""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", str(clip_path)],
            capture_output=True, text=True, timeout=300,
        )
        data = json.loads(probe.stdout)
        video_stream = next((s for s in data.get("streams", []) if s["codec_type"] == "video"), None)
        audio_stream = next((s for s in data.get("streams", []) if s["codec_type"] == "audio"), None)
        w = int(video_stream["width"]) if video_stream else 0
        h = int(video_stream["height"]) if video_stream else 0
        duration = float(data.get("format", {}).get("duration", 0))
        return {"width": w, "height": h, "has_audio": audio_stream is not None, "duration": duration}
    except Exception:
        return {"width": 0, "height": 0, "has_audio": False, "duration": 0}


def _preprocess_clips(clips: list[Path], mute_video_audio: bool = False) -> tuple[list[Path], list[Path], tuple[int, int], bool]:
    """Prepare clips for concatenation: add silent audio to opening if needed.

    Does NOT resize clips — that happens in the concat filter only if needed.
    Probes all clips and logs their dimensions.
    Returns (clips_to_concat, temp_files_to_cleanup, (min_w, min_h), all_same_dims).
    """
    if not clips:
        return clips, [], (0, 0), True

    # Probe all clips and log dimensions
    probes = [(clip, _probe_clip(clip)) for clip in clips]
    log.info("  Clip dimensions:")
    for clip, info in probes:
        log.info(f"    {clip.name}: {info['width']}x{info['height']}"
                 f" ({info['duration']:.1f}s, audio: {'yes' if info['has_audio'] else 'no'})")

    # Find minimum width and height among scene clips (skip opening)
    scene_dims = [(info["width"], info["height"]) for clip, info in probes
                  if info["width"] > 0 and "_opening" not in clip.name]
    if scene_dims:
        min_w = min(w for w, _ in scene_dims)
        min_h = min(h for _, h in scene_dims)
    else:
        all_dims = [(info["width"], info["height"]) for _, info in probes if info["width"] > 0]
        min_w = min(w for w, _ in all_dims) if all_dims else 720
        min_h = min(h for _, h in all_dims) if all_dims else 1280

    # Ensure even dimensions
    min_w = min_w - (min_w % 2)
    min_h = min_h - (min_h % 2)

    # Check if all clips already have the same dimensions
    all_same_dims = all(
        info["width"] == min_w and info["height"] == min_h
        for _, info in probes if info["width"] > 0
    )
    log.info(f"  Min dimensions: {min_w}x{min_h}, all same: {all_same_dims}")

    processed = []
    temp_files = []

    for clip, info in probes:
        is_opening = "_opening" in clip.name
        needs_audio = not info["has_audio"] and not mute_video_audio and is_opening

        if needs_audio:
            # Only preprocess opening clips that need a silent audio track added
            temp_out = clip.parent / f"_prep_{clip.name}"
            cmd = [
                "ffmpeg", "-y",
                "-i", str(clip),
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest",
                "-movflags", "+faststart",
                str(temp_out),
            ]
            log.info(f"  Adding silent audio to {clip.name}")
            result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
            if result.returncode == 0 and temp_out.exists():
                processed.append(temp_out)
                temp_files.append(temp_out)
            else:
                log.warning(f"  Failed to add audio to {clip.name}: {(result.stderr or '')[:200]}")
                processed.append(clip)
        else:
            processed.append(clip)

    return processed, temp_files, (min_w, min_h), all_same_dims


def _compute_geometry_corrections(clips: list[Path], tmp_dir: Path) -> list[tuple[float, float]]:
    """Compute per-clip scale corrections to fix AI-generated geometry drift.

    AI video generators (e.g. Seedance 2.0) produce each clip with a subtly
    different zoom/framing. This causes objects to appear thinner or wider at
    clip transitions. We detect the geometric transform between consecutive
    bridge frames (last frame of clip[i] ≈ first frame of clip[i+1]) and
    return cumulative (sx, sy) corrections to apply to each clip.

    Returns a list of (sx, sy) per clip. clip[0] is always (1.0, 1.0).
    Subsequent clips have sx > 1.0 if they need to be zoomed in to match.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        log.warning("OpenCV not available — skipping geometry correction")
        return [(1.0, 1.0)] * len(clips)

    corrections = [(1.0, 1.0)]
    cumulative_sx, cumulative_sy = 1.0, 1.0

    for i in range(len(clips) - 1):
        # Extract last frame of clip[i] and first frame of clip[i+1]
        last_f = tmp_dir / f"_geom_last_{i}.png"
        first_f = tmp_dir / f"_geom_first_{i+1}.png"

        try:
            # Last frame: seek near end
            info = _probe_clip(clips[i])
            seek_t = max(0, info.get("duration", 10.0) - 0.1)
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(seek_t), "-i", str(clips[i]),
                 "-frames:v", "1", "-update", "1", str(last_f)],
                capture_output=True, timeout=300,
            )
            # First frame of next clip
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(clips[i + 1]),
                 "-frames:v", "1", "-update", "1", str(first_f)],
                capture_output=True, timeout=300,
            )

            if not last_f.exists() or not first_f.exists():
                corrections.append((cumulative_sx, cumulative_sy))
                continue

            img_last = cv2.imread(str(last_f))
            img_first = cv2.imread(str(first_f))

            if img_last is None or img_first is None:
                corrections.append((cumulative_sx, cumulative_sy))
                continue

            # ORB feature matching + homography
            orb = cv2.ORB_create(5000)
            kp1, des1 = orb.detectAndCompute(img_last, None)
            kp2, des2 = orb.detectAndCompute(img_first, None)

            if des1 is None or des2 is None or len(des1) < 10 or len(des2) < 10:
                corrections.append((cumulative_sx, cumulative_sy))
                continue

            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = sorted(bf.match(des1, des2), key=lambda m: m.distance)[:100]

            if len(matches) < 10:
                corrections.append((cumulative_sx, cumulative_sy))
                continue

            pts1 = np.float32([kp1[m.queryIdx].pt for m in matches])
            pts2 = np.float32([kp2[m.trainIdx].pt for m in matches])

            H, mask = cv2.findHomography(pts2, pts1, cv2.RANSAC, 5.0)
            if H is None or mask.sum() < 8:
                corrections.append((cumulative_sx, cumulative_sy))
                continue

            # Extract scale from homography (maps clip[i+1] -> clip[i] space)
            sx = float(np.sqrt(H[0, 0] ** 2 + H[1, 0] ** 2))
            sy = float(np.sqrt(H[0, 1] ** 2 + H[1, 1] ** 2))

            # Only apply if the correction is reasonable (< 10% per step)
            if abs(sx - 1.0) > 0.10 or abs(sy - 1.0) > 0.10:
                log.warning(f"  Clip {i}->{i+1}: geometry correction too large "
                            f"(sx={sx:.4f}, sy={sy:.4f}), skipping")
                corrections.append((cumulative_sx, cumulative_sy))
                continue

            cumulative_sx *= sx
            cumulative_sy *= sy

            # Cap cumulative correction at ±15%
            cumulative_sx = max(0.85, min(1.15, cumulative_sx))
            cumulative_sy = max(0.85, min(1.15, cumulative_sy))

            log.info(f"  Clip {i}->{i+1}: scale correction sx={sx:.4f}, sy={sy:.4f} "
                     f"(cumulative: {cumulative_sx:.4f}, {cumulative_sy:.4f})")
            corrections.append((cumulative_sx, cumulative_sy))

        except Exception as e:
            log.warning(f"  Clip {i}->{i+1}: geometry detection failed: {e}")
            corrections.append((cumulative_sx, cumulative_sy))
        finally:
            last_f.unlink(missing_ok=True)
            first_f.unlink(missing_ok=True)

    return corrections


def compose_clips(
    clips: list[Path],
    output_path: Path,
    config: dict,
    *,
    mute_video_audio: bool = False,
    audio_files: list[Path] | None = None,
    transition: str | None = None,
    transition_duration: float | None = None,
) -> tuple[Path, tuple[int, int] | None]:
    """Compose selected clips into a single video using ffmpeg.

    Steps:
    1. Probe clips, add silent audio to opening if needed
    2. Concatenate using ffmpeg concat filter (skipping first frame of each
       clip after the first to eliminate duplicate frames at transitions)
    3. Resize final video to min dimensions across all clips
    4. Overlay any external audio files

    Returns (output_path, crop_dims) where crop_dims is the final (w, h).
    """
    if not _has_ffmpeg():
        log.error("ffmpeg not found on PATH. Install ffmpeg first.")
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Step 0: Probe clips and prepare (add silent audio to opening only)
    log.info("Preparing clips for concatenation...")
    processed_clips, temp_files, (min_w, min_h), all_same_dims = _preprocess_clips(clips, mute_video_audio)

    target_fps = int(os.environ.get("VIDEO_FPS", "24"))

    # Step 1: Concatenate clips using the ffmpeg concat filter.
    # For clips after the first, skip the first frame (duplicate of previous clip's last frame).
    concat_output = output_path.parent / "_concat_raw.mp4"
    n = len(processed_clips)

    cmd = ["ffmpeg", "-y"]
    for clip in processed_clips:
        cmd.extend(["-i", str(clip)])

    # Build filter_complex with per-clip processing and crossfade transitions.
    # Crossfade (xfade) masks the subtle proportion shifts between AI-generated clips.
    # Each clip after the first has its first frame trimmed (duplicate of previous clip's last frame).
    xfade_dur = float(os.environ.get("CLIP_CROSSFADE_SECONDS", "0.75"))
    xfade_transition = os.environ.get("CLIP_TRANSITION", "smoothup")
    frame_dur = 1.0 / target_fps

    # Compute per-clip geometry corrections (fixes AI-generated zoom/framing drift)
    log.info("Computing geometry corrections between clips...")
    geom_corrections = _compute_geometry_corrections(processed_clips, output_path.parent)

    filter_lines = []
    # Step A: Pre-process each clip (trim first frame for i>0, geometry correction, normalize format)
    for i in range(n):
        vf_parts = []
        if i > 0:
            vf_parts.append("trim=start_frame=1,setpts=PTS-STARTPTS")
        if not all_same_dims:
            vf_parts.extend([
                f"scale={min_w}:{min_h}:force_original_aspect_ratio=decrease",
                f"pad={min_w}:{min_h}:(ow-iw)/2:(oh-ih)/2",
            ])

        # Apply geometry correction: scale up then crop back to target size
        sx, sy = geom_corrections[i]
        if abs(sx - 1.0) > 0.002 or abs(sy - 1.0) > 0.002:
            # Scale to corrected size (slightly larger), then crop back to target
            corr_w = round(min_w * sx)
            corr_h = round(min_h * sy)
            # Ensure even dimensions
            corr_w = corr_w + (corr_w % 2)
            corr_h = corr_h + (corr_h % 2)
            vf_parts.append(f"scale={corr_w}:{corr_h}")
            vf_parts.append(f"crop={min_w}:{min_h}")

        vf_parts.extend(["format=yuv420p", "setsar=1", f"fps={target_fps}"])
        vf_chain = ",".join(vf_parts)
        filter_lines.append(f"[{i}:v]{vf_chain}[v{i}]")

        if not mute_video_audio:
            if i > 0:
                filter_lines.append(f"[{i}:a]atrim=start={frame_dur:.6f},asetpts=PTS-STARTPTS[a{i}]")
            else:
                filter_lines.append(f"[{i}:a]anull[a{i}]")

    # Step B: Chain xfade between consecutive video streams.
    # xfade needs the offset = duration_of_accumulated_output - xfade_dur.
    # Probe each clip's duration (after trim) to compute offsets.
    clip_durations = []
    for i, clip in enumerate(processed_clips):
        info = _probe_clip(clip)
        dur = info.get("duration", 10.0)
        if i > 0:
            dur -= frame_dur  # trimmed first frame
        clip_durations.append(dur)

    if n == 1:
        # Single clip — no xfade needed
        filter_lines.append("[v0]null[vout]")
        if not mute_video_audio:
            filter_lines.append("[a0]anull[aout]")
    elif xfade_dur <= 0:
        # No crossfade — hard cut via concat filter
        v_inputs = "".join(f"[v{i}]" for i in range(n))
        filter_lines.append(f"{v_inputs}concat=n={n}:v=1:a=0[vout]")
        if not mute_video_audio:
            a_inputs = "".join(f"[a{i}]" for i in range(n))
            filter_lines.append(f"{a_inputs}concat=n={n}:v=0:a=1[aout]")
    else:
        # Chain xfade: v0 xfade v1 -> xf0; xf0 xfade v2 -> xf1; ...
        accumulated_dur = clip_durations[0]
        prev_v = "v0"
        for i in range(1, n):
            offset = max(0, accumulated_dur - xfade_dur)
            out_label = "vout" if i == n - 1 else f"xf{i}"
            filter_lines.append(
                f"[{prev_v}][v{i}]xfade=transition={xfade_transition}:duration={xfade_dur}:offset={offset:.4f}[{out_label}]"
            )
            # After xfade, the accumulated duration grows by clip_dur - xfade_dur
            accumulated_dur = offset + clip_durations[i]
            prev_v = out_label

        # Chain acrossfade for audio
        if not mute_video_audio:
            prev_a = "a0"
            acc_a = clip_durations[0]
            for i in range(1, n):
                out_a = "aout" if i == n - 1 else f"xa{i}"
                filter_lines.append(
                    f"[{prev_a}][a{i}]acrossfade=d={xfade_dur}:c1=tri:c2=tri[{out_a}]"
                )
                acc_a = acc_a - xfade_dur + clip_durations[i]
                prev_a = out_a

    filter_complex = ";".join(filter_lines)
    if mute_video_audio:
        cmd.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-an"])
    else:
        cmd.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"])

    cmd.extend(["-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-color_range", "tv", "-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709"])
    if not mute_video_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "192k"])
    cmd.extend(["-movflags", "+faststart", str(concat_output)])

    log.info(f"Concatenating {n} clips (concat filter, skipping duplicate first frames)...")
    log.info(f"  Output resolution: {min_w}x{min_h}, scale needed: {not all_same_dims}")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)

    if result.returncode != 0:
        log.error(f"ffmpeg concat failed: {(result.stderr or '')[:500]}")
        for f in temp_files:
            f.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg concatenation failed")

    # Step 2: Overlay audio files (if any)
    if audio_files:
        audio_output = output_path.parent / "_with_audio.mp4"
        cmd_audio = ["ffmpeg", "-y", "-i", str(concat_output)]

        for af in audio_files:
            cmd_audio.extend(["-i", str(af)])

        n_audio = len(audio_files)
        if mute_video_audio:
            if n_audio == 1:
                cmd_audio.extend([
                    "-c:v", "copy", "-c:a", "aac",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-shortest", str(audio_output),
                ])
            else:
                filter_parts = [f"[{i + 1}:a]" for i in range(n_audio)]
                filter_complex = "".join(filter_parts) + f"amix=inputs={n_audio}:duration=longest[aout]"
                cmd_audio.extend([
                    "-filter_complex", filter_complex,
                    "-c:v", "copy", "-map", "0:v:0", "-map", "[aout]",
                    "-shortest", str(audio_output),
                ])
        else:
            filter_parts = ["[0:a]"] + [f"[{i + 1}:a]" for i in range(n_audio)]
            filter_complex = "".join(filter_parts) + f"amix=inputs={n_audio + 1}:duration=longest[aout]"
            cmd_audio.extend([
                "-filter_complex", filter_complex,
                "-c:v", "copy", "-map", "0:v:0", "-map", "[aout]",
                "-shortest", str(audio_output),
            ])

        log.info(f"Overlaying {n_audio} audio file(s)...")
        result = subprocess.run(cmd_audio, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            log.warning(f"Audio overlay failed: {result.stderr[:300]}. Using video without overlay.")
            audio_output = concat_output
        else:
            concat_output.unlink(missing_ok=True)
            concat_output = audio_output
    else:
        log.info("No audio overlay files selected.")

    # Step 3: Move to final output path
    if concat_output != output_path:
        shutil.move(str(concat_output), str(output_path))

    # Clean up temp preprocessed files
    for f in temp_files:
        f.unlink(missing_ok=True)

    crop_dims = (min_w, min_h)
    log.info(f"Composed video: {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB) — {min_w}x{min_h}")
    return output_path, crop_dims


# ---------------------------------------------------------------------------
# Watermark
# ---------------------------------------------------------------------------


def add_watermark(
    video_path: Path,
    output_path: Path | None = None,
) -> Path:
    """Add semi-transparent logo watermark that appears randomly for 1-3s.

    The watermark appears at random non-critical positions (avoiding center)
    multiple times throughout the video. Small but recognizable.
    """
    logo_path = PROJECT_ROOT / "site" / "logo" / "storysmithai_logo_horizontal.png"
    if not logo_path.exists():
        log.warning(f"Logo not found: {logo_path}. Skipping watermark.")
        return video_path

    if output_path is None:
        output_path = video_path.parent / f"{video_path.stem}_wm.mp4"

    # Get video duration and dimensions
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", "-show_format", str(video_path),
            ],
            capture_output=True, text=True, timeout=300,
        )
        probe_data = json.loads(probe.stdout)
        duration = float(probe_data["format"]["duration"])
        video_stream = next(s for s in probe_data["streams"] if s["codec_type"] == "video")
        vid_w = int(video_stream["width"])
        vid_h = int(video_stream["height"])
    except Exception as e:
        log.warning(f"Cannot probe video: {e}. Skipping watermark.")
        return video_path

    # Logo sizing: scale to ~15% of video width (visible but not disturbing)
    logo_w = max(int(vid_w * 0.15), 80)
    logo_h = max(int(logo_w * 764 / 1780), 30)  # Maintain aspect ratio

    # Generate random watermark appearances (every 15-25s, lasting 1-3s)
    appearances = []
    t = random.uniform(3, 8)  # First appearance after 3-8s
    while t < duration - 3:
        show_duration = random.uniform(1.0, 3.0)
        # Random position — avoid center (30-70% of frame)
        # Pick from: top-left, top-right, bottom-left, bottom-right quadrants
        quadrant = random.choice(["tl", "tr", "bl", "br"])
        margin = int(vid_w * 0.03)
        if quadrant == "tl":
            x = random.randint(margin, int(vid_w * 0.25))
            y = random.randint(margin, int(vid_h * 0.2))
        elif quadrant == "tr":
            x = random.randint(int(vid_w * 0.65), max(int(vid_w * 0.65) + 1, vid_w - logo_w - margin))
            y = random.randint(margin, int(vid_h * 0.2))
        elif quadrant == "bl":
            x = random.randint(margin, int(vid_w * 0.25))
            y = random.randint(int(vid_h * 0.75), max(int(vid_h * 0.75) + 1, vid_h - logo_h - margin))
        else:  # br
            x = random.randint(int(vid_w * 0.65), max(int(vid_w * 0.65) + 1, vid_w - logo_w - margin))
            y = random.randint(int(vid_h * 0.75), max(int(vid_h * 0.75) + 1, vid_h - logo_h - margin))

        # Clamp to valid range
        x = max(margin, min(x, vid_w - logo_w - margin))
        y = max(margin, min(y, vid_h - logo_h - margin))

        appearances.append({
            "start": round(t, 2),
            "end": round(min(t + show_duration, duration), 2),
            "x": x,
            "y": y,
        })
        t += show_duration + random.uniform(15, 25)

    if not appearances:
        # Very short video — add one appearance
        appearances.append({
            "start": 1.0,
            "end": min(3.0, duration - 0.5),
            "x": int(vid_w * 0.7),
            "y": int(vid_h * 0.05),
        })

    log.info(f"Adding {len(appearances)} watermark appearance(s) to video")
    for i, a in enumerate(appearances):
        log.info(f"  Watermark #{i+1} placed at {a['start']:.1f}s to {a['end']:.1f}s of the video")

    # Build ffmpeg overlay filter with enable expressions
    # For multiple appearances at different positions, chain overlay filters
    filter_parts = []
    prev_label = "0:v"
    for i, a in enumerate(appearances):
        wm_label = f"wm{i}"
        out_label = f"v{i}" if i < len(appearances) - 1 else "vout"
        filter_parts.append(
            f"[1:v]scale={logo_w}:-1,format=rgba,colorchannelmixer=aa=0.4[{wm_label}]"
        )
        enable = f"between(t,{a['start']},{a['end']})"
        filter_parts.append(
            f"[{prev_label}][{wm_label}]overlay={a['x']}:{a['y']}:enable='{enable}'[{out_label}]"
        )
        prev_label = out_label
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(logo_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-color_range", "tv", "-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if result.returncode != 0:
        log.warning(f"Watermark failed: {(result.stderr or '')[:300]}. Using video without watermark.")
        shutil.copy2(str(video_path), str(output_path))
    else:
        log.info(f"Watermark applied: {output_path}")

    return output_path


# ---------------------------------------------------------------------------
# Subtitle generation (auto-transcribe + burn)
# ---------------------------------------------------------------------------


def _fmt_ass_time(seconds: float) -> str:
    """Format seconds to ASS timestamp: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _generate_ass_header(vid_w: int, vid_h: int) -> str:
    """Generate ASS subtitle file header with bilingual styles."""
    font_size_main = max(int(vid_h * 0.035), 16)
    font_size_sub = max(int(vid_h * 0.028), 13)
    outline = max(int(font_size_main * 0.08), 1)
    margin_v = int(vid_h * 0.04)

    return f"""[Script Info]
Title: Episode Subtitles
ScriptType: v4.00+
PlayResX: {vid_w}
PlayResY: {vid_h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,Arial,{font_size_main},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{outline},1,2,20,20,{margin_v},1
Style: Sub,Arial,{font_size_sub},&H0080DDFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{outline},1,2,20,20,{margin_v + font_size_main + 4},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def transcribe_video(video_path: Path) -> list[dict] | None:
    """Transcribe audio from video.

    Order: faster-whisper (local) → openai-whisper (local) → OpenAI Whisper API (cloud).
    Returns list of segments: [{start, end, text}, ...]
    """
    # Try faster-whisper first (local, fast once loaded)
    try:
        from faster_whisper import WhisperModel

        log.info("Transcribing audio with faster-whisper (local)...")
        # Try GPU first, fall back to CPU if CUDA libs not available
        try:
            model = WhisperModel("medium", device="cuda", compute_type="float16")
        except Exception:
            log.info("  CUDA not available, using CPU for transcription...")
            model = WhisperModel("medium", device="cpu", compute_type="int8")
        segments_iter, info = model.transcribe(
            str(video_path),
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
        )
        log.info(f"Detected language: {info.language} ({info.language_probability:.1%})")

        segments = []
        for seg in segments_iter:
            segments.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            })
        log.info(f"Transcribed {len(segments)} segments")
        return segments

    except ImportError:
        log.info("faster-whisper not installed, trying openai-whisper...")
    except Exception as e:
        log.warning(f"faster-whisper failed: {e}. Trying openai-whisper...")

    # Try openai-whisper (local)
    try:
        import whisper as openai_whisper

        log.info("Transcribing audio with openai-whisper (local)...")
        model = openai_whisper.load_model("medium")
        result = model.transcribe(str(video_path), word_timestamps=True)

        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            })
        log.info(f"Transcribed {len(segments)} segments")
        return segments

    except ImportError:
        log.info("openai-whisper not installed, trying OpenAI Whisper API...")
    except Exception as e:
        log.warning(f"openai-whisper failed: {e}. Trying OpenAI Whisper API...")

    # Fallback: OpenAI Whisper API (cloud)
    try:
        import openai

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            log.warning("No OPENAI_API_KEY — cannot use Whisper API. Skipping subtitles.")
            return None

        log.info("Transcribing audio with OpenAI Whisper API...")
        import tempfile
        audio_tmp = Path(tempfile.mktemp(suffix=".wav"))
        extract_cmd = [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_tmp),
        ]
        extract_result = subprocess.run(extract_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        if extract_result.returncode != 0 or not audio_tmp.exists() or audio_tmp.stat().st_size < 1000:
            audio_tmp.unlink(missing_ok=True)
            log.warning("Failed to extract audio from video. No audio track? Skipping subtitles.")
            return None

        client = openai.OpenAI(api_key=api_key)
        try:
            with open(audio_tmp, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
        finally:
            audio_tmp.unlink(missing_ok=True)

        segments = []
        for seg in transcript.segments or []:
            # OpenAI SDK returns Pydantic objects, use attribute access
            segments.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            })
        log.info(f"Transcribed {len(segments)} segments via OpenAI API")
        return segments

    except (ImportError, Exception) as e:
        log.warning(f"All transcription methods failed: {e}. Skipping subtitles.")
        return None


def translate_segments(segments: list[dict], source_lang: str) -> list[dict]:
    """Translate segment texts to English using LLM.

    Returns segments with added 'text_en' field.
    """
    if not segments:
        return segments

    # If source is already English, just copy text
    if source_lang.startswith("en"):
        for seg in segments:
            seg["text_en"] = seg["text"]
        return segments

    try:
        from llm import call_llm

        # Batch all texts for efficient translation
        lines = [seg["text"] for seg in segments]
        numbered = "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines))

        response = call_llm(
            system_prompt=(
                "You are a professional subtitle translator. "
                "Translate each numbered line to natural, concise English. "
                "Keep the same numbering. Output ONLY the numbered translations, "
                "one per line. Do not add explanations."
            ),
            user_message=f"Translate these lines from {source_lang} to English:\n\n{numbered}",
            max_tokens=4000,
        )

        # Parse numbered translations
        translations = {}
        for line in response.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Match "1. translation" or "1: translation"
            m = re.match(r"(\d+)[.\):]\s*(.+)", line)
            if m:
                translations[int(m.group(1))] = m.group(2).strip()

        for i, seg in enumerate(segments):
            seg["text_en"] = translations.get(i + 1, seg["text"])

        log.info(f"Translated {len(translations)} segments to English")

    except Exception as e:
        log.warning(f"Translation failed: {e}. Using original text only.")
        for seg in segments:
            seg["text_en"] = ""

    return segments


def _assign_speakers_from_enhanced_prompts(
    segments: list[dict],
    clips: list[Path],
) -> list[dict]:
    """Assign character names to transcribed segments using enhanced prompt YAMLs.

    Each clip has an associated _enhanced_prompt.yaml that contains dialogue
    with character names. This function maps segments to clips by timestamp
    (using cumulative clip durations), then matches segment text to the clip's
    dialogue lines to assign speakers.

    This is more accurate than script-based matching because enhanced prompts
    reflect what was actually generated per clip, not the whole episode script.

    Returns the segments list with 'speaker' field set where possible.
    """
    if not clips:
        return segments

    # Load enhanced prompts and compute clip time boundaries
    clip_data: list[dict] = []  # [{start, end, dialogues: [(text, char)]}]
    cumulative = 0.0
    for clip_path in clips:
        # Skip opening clips
        if "_opening" in clip_path.name:
            continue

        # Get clip duration
        duration = 0.0
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(clip_path)],
                capture_output=True, text=True, timeout=100,
            )
            probe_data = json.loads(probe.stdout)
            duration = float(probe_data.get("format", {}).get("duration", 0))
        except Exception:
            duration = 5.0  # default estimate

        # Load enhanced prompt YAML
        prompt_path = clip_path.parent / f"{clip_path.stem}_enhanced_prompt.yaml"
        dialogues: list[tuple[str, str]] = []
        if prompt_path.exists():
            try:
                prompt_data = yaml.safe_load(prompt_path.read_text(encoding="utf-8"))
                if prompt_data and isinstance(prompt_data, dict):
                    for d in prompt_data.get("dialogue", []):
                        if isinstance(d, dict):
                            char = d.get("character", "")
                            line = d.get("line", "")
                            if char and line:
                                dialogues.append((line, char))
            except Exception:
                pass

        clip_data.append({
            "start": cumulative,
            "end": cumulative + duration,
            "dialogues": dialogues,
            "clip_name": clip_path.name,
        })
        cumulative += duration

    if not clip_data:
        return segments

    # Get text normalizer for similarity matching
    _normalize = _get_text_normalizer()

    def _text_sim(a: str, b: str) -> float:
        a_n = _normalize(a)
        b_n = _normalize(b)
        if a_n in b_n or b_n in a_n:
            shorter = min(len(a_n), len(b_n))
            longer = max(len(a_n), len(b_n))
            return shorter / longer if longer > 0 else 0
        set_a = set(a_n)
        set_b = set(b_n)
        inter = set_a & set_b
        union = set_a | set_b
        return len(inter) / len(union) if union else 0

    assigned = 0
    for seg in segments:
        if seg.get("speaker"):
            continue  # already assigned
        seg_text = seg.get("text", "")
        if not seg_text:
            continue

        # Find which clip this segment belongs to (by midpoint time)
        seg_mid = (seg.get("start", 0) + seg.get("end", 0)) / 2
        matching_clip = None
        for cd in clip_data:
            if cd["start"] <= seg_mid < cd["end"]:
                matching_clip = cd
                break
        if not matching_clip or not matching_clip["dialogues"]:
            continue

        # Match segment text to clip's dialogue
        best_score = 0.0
        best_char = None
        for d_text, d_char in matching_clip["dialogues"]:
            score = _text_sim(seg_text, d_text)
            if score > best_score:
                best_score = score
                best_char = d_char

        if best_score >= 0.25 and best_char:
            seg["speaker"] = best_char
            assigned += 1

    if assigned > 0:
        log.info(f"  Assigned speakers to {assigned}/{len(segments)} segments from enhanced prompts")

    return segments


def _assign_speakers_from_script(segments: list[dict], story_slug: str | None, episode_number: int | None) -> list[dict]:
    """Assign character names to transcribed segments by matching to script dialogue.

    Uses TEXT SIMILARITY between Whisper transcription and script dialogue lines
    to identify which character is speaking. This is more robust than timing-based
    matching because Whisper timing estimates are accurate but script time_ranges
    are coarse estimates.

    Handles Traditional ↔ Simplified Chinese differences via OpenCC (if available)
    or character-level overlap as fallback.
    """
    if not story_slug or episode_number is None:
        return segments

    try:
        script_path = get_project_root() / "data" / "stories" / story_slug / "episodes" / str(episode_number) / "script.yaml"
        if not script_path.exists():
            return segments
        script_data = yaml.safe_load(script_path.read_text(encoding="utf-8"))
        if not script_data or "scenes" not in script_data:
            return segments

        # Build a flat list of (dialogue_text, character_name) from script
        script_dialogues: list[tuple[str, str]] = []
        for scene in script_data["scenes"]:
            dialogues = scene.get("dialogue", [])
            for d in dialogues:
                char_name = d.get("character", "")
                line = d.get("line", "")
                if char_name and line:
                    script_dialogues.append((line, char_name))

        if not script_dialogues:
            return segments

        # Try to normalize Traditional→Simplified for better matching
        _normalize = _get_text_normalizer()

        def _text_similarity(a: str, b: str) -> float:
            """Character-level Jaccard similarity between two strings."""
            a_norm = _normalize(a)
            b_norm = _normalize(b)
            # Also try substring containment (handles Whisper splitting one line into parts)
            if a_norm in b_norm or b_norm in a_norm:
                shorter = min(len(a_norm), len(b_norm))
                longer = max(len(a_norm), len(b_norm))
                return shorter / longer if longer > 0 else 0
            set_a = set(a_norm)
            set_b = set(b_norm)
            intersection = set_a & set_b
            union = set_a | set_b
            return len(intersection) / len(union) if union else 0

        # Match each segment to the best-matching script dialogue by text similarity
        # Track which script lines have been used to avoid double-assignment
        used_indices: set[int] = set()
        for seg in segments:
            if seg.get("speaker"):
                continue  # already assigned (e.g. from enhanced prompts)
            seg_text = seg.get("text", "")
            if not seg_text:
                continue

            best_score = 0.0
            best_char = None
            best_idx = -1
            for idx, (d_text, d_char) in enumerate(script_dialogues):
                score = _text_similarity(seg_text, d_text)
                if score > best_score:
                    best_score = score
                    best_char = d_char
                    best_idx = idx

            # Require minimum similarity threshold
            if best_score >= 0.3 and best_char:
                seg["speaker"] = best_char
                used_indices.add(best_idx)
                log.debug(f"  Matched '{seg_text[:20]}' → {best_char} (score={best_score:.2f})")

        assigned = sum(1 for s in segments if "speaker" in s)
        log.info(f"  Assigned speakers to {assigned}/{len(segments)} segments from script (text matching)")

    except Exception as e:
        log.warning(f"  Speaker assignment failed: {e}")

    return segments


def _get_text_normalizer():
    """Return a function that normalizes Traditional Chinese to Simplified.
    Falls back to identity function if OpenCC is not available."""
    try:
        import opencc
        converter = opencc.OpenCC("t2s")
        return converter.convert
    except ImportError:
        # Fallback: strip punctuation for better matching
        import re as _re_norm
        _punct = _re_norm.compile(r'[，。！？、；：""''（）…—\s,\.!?\-\s]')
        return lambda text: _punct.sub("", text)


def _parse_time_range(time_str: str) -> float:
    """Parse time string like '0:20' or '1:40' to seconds."""
    parts = time_str.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return 0.0


def generate_subtitles(
    video_path: Path,
    output_path: Path | None = None,
    content_lang: str | None = None,
    story_slug: str | None = None,
    episode_number: int | None = None,
    clips: list[Path] | None = None,
) -> Path | None:
    """Auto-transcribe video and burn bilingual subtitles.

    Steps:
    1. Transcribe audio using whisper (local or API)
    2. Assign speakers from script.yaml (for TTS voice mapping in EN version)
    3. Translate to English if content is non-English
    4. Generate ASS subtitle file (original + English) with speaker names
    5. Burn into video using ffmpeg (speaker names in ASS Name field, not visible)

    Returns path to subtitled video, or None if failed.
    """
    if not _has_ffmpeg():
        log.warning("ffmpeg not found. Cannot burn subtitles.")
        return None

    content_lang = content_lang or os.environ.get("CONTENT_LANGUAGE", "en")

    # Step 1: Transcribe
    segments = transcribe_video(video_path)
    if not segments:
        log.warning("No transcription produced. Skipping subtitles.")
        return None

    # Filter out empty/whitespace-only segments
    segments = [s for s in segments if s["text"].strip()]
    if not segments:
        log.warning("All segments are empty. Skipping subtitles.")
        return None

    # Step 1b: Assign speaker names from enhanced prompts (preferred, per-clip accuracy)
    if clips:
        segments = _assign_speakers_from_enhanced_prompts(segments, clips)

    # Step 1c: Assign remaining speakers from script (fallback for unassigned segments)
    segments = _assign_speakers_from_script(segments, story_slug, episode_number)

    # Step 2: Translate to English if needed
    segments = translate_segments(segments, content_lang)

    # Step 3: Generate ASS file
    # Get video dimensions
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", str(video_path),
            ],
            capture_output=True, text=True, timeout=100,
        )
        probe_data = json.loads(probe.stdout)
        video_stream = next(s for s in probe_data["streams"] if s["codec_type"] == "video")
        vid_w = int(video_stream["width"])
        vid_h = int(video_stream["height"])
    except Exception:
        vid_w, vid_h = 1080, 1920  # Default vertical video

    ass_path = video_path.parent / f"{video_path.stem}.ass"
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(_generate_ass_header(vid_w, vid_h))

        for seg in segments:
            start = _fmt_ass_time(seg["start"])
            end = _fmt_ass_time(seg["end"])
            main_text = seg["text"].replace("\n", "\\N")
            speaker = seg.get("speaker", "")
            # Name field carries speaker identity for TTS voice mapping (not displayed)
            f.write(f"Dialogue: 0,{start},{end},Main,{speaker},0,0,0,,{main_text}\n")

            # Add English translation line if available and different
            text_en = seg.get("text_en", "")
            if text_en and text_en != seg["text"]:
                f.write(f"Dialogue: 0,{start},{end},Sub,{speaker},0,0,0,,{text_en}\n")

    log.info(f"Subtitle file saved: {ass_path} ({len(segments)} segments)")

    # Step 4: Burn subtitles into video
    if output_path is None:
        output_path = video_path.parent / f"{video_path.stem}_sub.mp4"

    # Escape special characters in path for ffmpeg filter
    ass_path_escaped = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"ass='{ass_path_escaped}'",
        "-c:v", "libx264",
        "-color_range", "tv", "-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]

    log.info("Burning subtitles into video...")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if result.returncode != 0:
        log.warning(f"Subtitle burn failed: {(result.stderr or '')[:300]}")
        log.warning("Trying fallback with subtitles filter...")
        # Fallback: try srt-based approach
        srt_path = video_path.parent / f"{video_path.stem}.srt"
        _write_srt(segments, srt_path)
        srt_escaped = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")
        cmd_fallback = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"subtitles='{srt_escaped}'",
            "-c:v", "libx264",
            "-color_range", "tv", "-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
        result = subprocess.run(cmd_fallback, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        if result.returncode != 0:
            log.warning(f"Subtitle burn fallback also failed: {(result.stderr or '')[:300]}")
            return None

    log.info(f"Subtitled video: {output_path}")
    return output_path


def _write_srt(segments: list[dict], srt_path: Path) -> None:
    """Write segments to SRT format (fallback for ASS)."""
    def fmt_srt_time(s: float) -> str:
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = int(s % 60)
        ms = int((s % 1) * 1000)
        return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            f.write(f"{i}\n")
            f.write(f"{fmt_srt_time(seg['start'])} --> {fmt_srt_time(seg['end'])}\n")
            f.write(seg["text"] + "\n")
            text_en = seg.get("text_en", "")
            if text_en and text_en != seg["text"]:
                f.write(text_en + "\n")
            f.write("\n")


# ---------------------------------------------------------------------------
# Global English Version (TTS Dub)
# ---------------------------------------------------------------------------


def _parse_ass_english_segments(ass_path: Path) -> list[dict]:
    """Parse ASS subtitle file and extract English (Sub style) dialogue lines with timing.

    Also captures the Name field (speaker) from ASS for voice assignment.
    """
    segments = []
    with open(ass_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("Dialogue:"):
                continue
            # Format: Dialogue: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
            parts = line.split(",", 9)
            if len(parts) < 10:
                continue
            style = parts[3].strip()
            name = parts[4].strip()
            start_str = parts[1].strip()
            end_str = parts[2].strip()
            text = parts[9].strip().replace("\\N", " ").replace("\\n", " ")
            if not text:
                continue
            segments.append({
                "style": style,
                "name": name,
                "start": _parse_ass_time(start_str),
                "end": _parse_ass_time(end_str),
                "text": text,
            })

    # Prefer Sub (English) lines; fallback to Main if no Sub found
    sub_lines = [s for s in segments if s["style"] == "Sub"]
    if sub_lines:
        return sub_lines
    return [s for s in segments if s["style"] == "Main"]


def _parse_ass_time(time_str: str) -> float:
    """Parse ASS time format (H:MM:SS.cc) to seconds."""
    parts = time_str.split(":")
    if len(parts) == 3:
        h = int(parts[0])
        m = int(parts[1])
        s = float(parts[2])
        return h * 3600 + m * 60 + s
    return 0.0


def _infer_speech_vibe(text: str) -> str:
    """Infer speaking style, pace, and emotion from the dialogue content."""
    text_lower = text.lower()

    # Detect exclamation / urgency
    has_exclamation = "!" in text or "！" in text
    has_question = "?" in text or "？" in text
    is_short = len(text) < 30
    is_long = len(text) > 80

    # Keyword-based emotion detection
    urgency_words = ("run", "hurry", "quick", "watch out", "stop", "help", "danger", "wait", "no!")
    wonder_words = ("what", "how", "where", "who", "why", "incredible", "amazing", "wow", "whoa")
    sad_words = ("sorry", "lost", "miss", "alone", "gone", "dead", "goodbye", "farewell")
    humor_words = ("hah", "funny", "joke", "ridiculous", "seriously", "really?", "oh come on")
    calm_words = ("perhaps", "maybe", "i think", "let me", "consider", "suppose", "well")
    angry_words = ("damn", "stupid", "hate", "enough", "shut up", "fool", "idiot")
    fear_words = ("scared", "afraid", "terrified", "horror", "nightmare", "ghost")

    vibe_parts = []

    if any(w in text_lower for w in urgency_words) or (has_exclamation and is_short):
        vibe_parts.append("Speak FAST and urgently, with rising intensity.")
    elif any(w in text_lower for w in angry_words):
        vibe_parts.append("Speak with controlled anger, firm and sharp.")
    elif any(w in text_lower for w in fear_words):
        vibe_parts.append("Speak with trembling fear, voice slightly shaky.")
    elif any(w in text_lower for w in wonder_words) or has_question:
        vibe_parts.append("Speak with genuine curiosity, voice rising at key words.")
    elif any(w in text_lower for w in sad_words):
        vibe_parts.append("Speak softly and wistfully, with emotional weight.")
    elif any(w in text_lower for w in humor_words):
        vibe_parts.append("Speak with dry wit and a hint of amusement.")
    elif any(w in text_lower for w in calm_words):
        vibe_parts.append("Speak thoughtfully with natural pauses.")
    else:
        vibe_parts.append("Speak naturally with conversational energy.")

    # Pace guidance based on text length
    if is_short and has_exclamation:
        vibe_parts.append("This is a short exclamation — deliver it punchy and quick.")
    elif is_short:
        vibe_parts.append("Keep it brisk, don't drag out short lines.")
    elif is_long:
        vibe_parts.append("Vary your pace — speed up through action, slow down for emphasis.")

    # General speed instruction
    vibe_parts.append(
        "Overall pacing: speak at a lively, natural conversational speed (not slow, not rushed). "
        "Avoid dragging words or adding unnecessary pauses between sentences."
    )

    return " ".join(vibe_parts)


def _generate_tts_segment(text: str, output_path: Path, voice: str = "nova",
                          speaker_name: str = "", gender: str = "") -> bool:
    """Generate TTS audio for a text segment.

    Args:
        voice: For OpenAI — one of: alloy, ash, ballad, coral, echo, fable,
               onyx, nova, sage, shimmer, verse.
               For edge-tts — a full voice name like 'en-US-GuyNeural'.
               If the voice looks like an edge-tts name (contains '-'), it's used directly.
        speaker_name: Character name for expressive instruction context.
        gender: 'male' or 'female' for instruction tuning.

    Tries OpenAI gpt-4o-mini-tts first (most natural), falls back to tts-1-hd,
    then edge-tts.
    Returns True if successful.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Detect if this is an edge-tts voice name (contains dashes like "en-US-GuyNeural")
    is_edge_voice = "-" in voice

    # Try OpenAI TTS
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key and not openai_key.startswith("sk-your_") and not is_edge_voice:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)

            # Build expressive instruction for gpt-4o-mini-tts
            # Infer vibe, pace, and emotion from the actual speech content
            vibe = _infer_speech_vibe(text)
            instruction = (
                "You are a voice actor dubbing an animated short film. "
                "Deliver this line with conviction and personality — NOT like a text-to-speech robot. "
                f"{vibe} "
            )
            if speaker_name:
                instruction += f"You are voicing the character '{speaker_name}'. Stay in character. "
            if gender:
                instruction += f"Use a {gender} voice. "

            # Try gpt-4o-mini-tts first (supports instructions for natural speech)
            try:
                response = client.audio.speech.create(
                    model="gpt-4o-mini-tts",
                    voice=voice,
                    input=text,
                    instructions=instruction,
                    response_format="mp3",
                )
                response.write_to_file(str(output_path))
                log.info(f"  TTS (4o-mini/{voice}): {output_path.name}")
                return True
            except Exception as e:
                # gpt-4o-mini-tts may not be available — fall back to tts-1-hd
                log.debug(f"  gpt-4o-mini-tts failed ({e}), trying tts-1-hd...")
                response = client.audio.speech.create(
                    model="tts-1-hd",
                    voice=voice,
                    input=text,
                    response_format="mp3",
                )
                response.write_to_file(str(output_path))
                log.info(f"  TTS (OpenAI HD/{voice}): {output_path.name}")
                return True

        except Exception as e:
            log.warning(f"  OpenAI TTS failed: {e}. Trying edge-tts fallback...")

    # Fallback / direct edge-tts
    try:
        import asyncio
        import edge_tts
        edge_voice = voice if is_edge_voice else "en-US-JennyMultilingualNeural"

        async def _run_edge_tts():
            comm = edge_tts.Communicate(text, edge_voice, rate="+10%", pitch="+0Hz")
            await comm.save(str(output_path))

        asyncio.run(_run_edge_tts())
        if output_path.exists() and output_path.stat().st_size > 0:
            log.info(f"  TTS (edge/{edge_voice.split('-')[-1]}): {output_path.name}")
            return True
    except Exception as e:
        log.warning(f"  edge-tts fallback also failed: {e}")

    return False


def generate_global_en_version(
    video_path: Path,
    ass_path: Path,
    output_path: Path,
    episode_number: int | None = None,
    story_slug: str | None = None,
    first_clip: Path | None = None,
    has_opening: bool = True,
) -> Path | None:
    """Generate a global English version of the episode with TTS-dubbed audio.

    Steps:
    1. Trim the original opening (first 2s) if present
    2. Parse ASS subtitle file for English text segments + timing
    3. Generate TTS audio for each segment
    4. Extract background audio (non-speech) from original via frequency filtering
    5. Mix background audio + TTS segments (muting original speech)
    6. Optionally prepend an English opening title card

    Args:
        has_opening: If True, trims the first 2s (original opening) before processing.

    Returns path to EN video, or None if failed.
    """
    if not _has_ffmpeg():
        log.warning("ffmpeg not found. Cannot generate EN version.")
        return None

    log.info("Generating global English (EN) version...")

    # Step 0: Trim original opening (first 2s) from the input video
    trimmed_video = video_path
    if has_opening:
        trimmed_video = video_path.parent / f"_en_trimmed_{video_path.name}"
        # Use re-encoding (not -c copy) for frame-accurate trim.
        # With -c copy, -ss jumps to the nearest keyframe which can skip 10+ seconds.
        trim_cmd = [
            "ffmpeg", "-y",
            "-ss", "2.0",
            "-i", str(video_path),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-color_range", "tv", "-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(trimmed_video),
        ]
        log.info("  Trimming original opening (first 2s) from input video (re-encoding for accuracy)...")
        trim_result = subprocess.run(trim_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        if trim_result.returncode != 0 or not trimmed_video.exists():
            log.warning(f"  Trim failed, using original video: {(trim_result.stderr or '')[:300]}")
            trimmed_video = video_path

    # Step 1: Parse English segments from ASS
    # Adjust timings by -2s if we trimmed the opening
    time_offset = 2.0 if has_opening and trimmed_video != video_path else 0.0
    segments = _parse_ass_english_segments(ass_path)
    if not segments:
        log.warning("No English segments found in subtitle file.")
        if trimmed_video != video_path:
            trimmed_video.unlink(missing_ok=True)
        return None

    # Adjust segment timings for trimmed video
    if time_offset > 0:
        adjusted_segments = []
        for seg in segments:
            new_start = seg["start"] - time_offset
            new_end = seg["end"] - time_offset
            if new_end > 0:  # Only keep segments that are after the trim point
                adjusted_segments.append({
                    "text": seg["text"],
                    "start": max(0, new_start),
                    "end": new_end,
                    "name": seg.get("name", ""),
                })
        segments = adjusted_segments

    log.info(f"  Found {len(segments)} English dialogue segments")

    # Step 2: Generate TTS for each segment with multi-voice support
    # Assign voices based on character gender from character YAML files.
    # gpt-4o-mini-tts voices: coral/sage (female), ash/ballad/verse (male)
    # tts-1-hd voices: nova/shimmer (female), onyx/echo (male)
    # edge-tts voices: JennyMultilingualNeural (female), GuyNeural (male)

    # Build speaker->voice mapping based on character gender
    openai_key = os.getenv("OPENAI_API_KEY", "")
    has_openai = bool(openai_key and not openai_key.startswith("sk-your_"))

    # Voices grouped by gender (gpt-4o-mini-tts compatible names)
    openai_female_voices = ["coral", "sage", "nova", "shimmer"]
    openai_male_voices = ["ash", "ballad", "verse", "onyx", "echo"]
    edge_female_voices = ["en-US-JennyMultilingualNeural", "en-US-AriaNeural"]
    edge_male_voices = ["en-US-GuyNeural", "en-US-DavisNeural"]

    # Collect unique speakers from Name field
    speakers = []
    for seg in segments:
        name = seg.get("name", "").strip()
        if name and name not in speakers:
            speakers.append(name)

    # Detect gender and TTS voice for each speaker from character YAML files
    speaker_gender: dict[str, str] = {}
    speaker_voice_from_yaml: dict[str, str] = {}
    speaker_voice_fallback: dict[str, str] = {}
    if story_slug and speakers:
        chars_dir = get_project_root() / "data" / "stories" / story_slug / "characters"
        if chars_dir.exists():
            for char_file in chars_dir.glob("*.yaml"):
                if char_file.name == "README.yaml":
                    continue
                try:
                    char_data = yaml.safe_load(char_file.read_text(encoding="utf-8"))
                    if not char_data:
                        continue
                    # Match by name_zh or name
                    char_name_zh = char_data.get("name_zh", "")
                    char_name_en = char_data.get("name", "")
                    matched_speaker = None
                    for spk in speakers:
                        if spk == char_name_zh or spk == char_name_en:
                            matched_speaker = spk
                            break
                    if not matched_speaker:
                        continue
                    # Read tts_voice directly from character YAML
                    if char_data.get("tts_voice"):
                        speaker_voice_from_yaml[matched_speaker] = char_data["tts_voice"]
                    if char_data.get("tts_voice_fallback"):
                        speaker_voice_fallback[matched_speaker] = char_data["tts_voice_fallback"]
                    # Detect gender from reference_prompt (contains 女性/男性)
                    ref_prompt = char_data.get("reference_prompt", "")
                    if "女性" in ref_prompt or "female" in ref_prompt.lower():
                        speaker_gender[matched_speaker] = "female"
                    elif "男性" in ref_prompt or "male" in ref_prompt.lower():
                        speaker_gender[matched_speaker] = "male"
                except Exception:
                    continue

    log.info(f"  Speaker genders detected: {speaker_gender}")
    log.info(f"  Speaker voices from YAML: {speaker_voice_from_yaml}")

    # Assign voices: prefer tts_voice from character YAML, fall back to gender-based defaults
    speaker_voice_map: dict[str, str] = {}
    female_idx = 0
    male_idx = 0
    for spk in speakers:
        # Use voice from character YAML if available
        if spk in speaker_voice_from_yaml:
            yaml_voice = speaker_voice_from_yaml[spk]
            # If no OpenAI key and the YAML voice is an OpenAI voice, use fallback
            if not has_openai and "-" not in yaml_voice:
                speaker_voice_map[spk] = speaker_voice_fallback.get(
                    spk, edge_female_voices[0] if speaker_gender.get(spk) == "female" else edge_male_voices[0]
                )
            else:
                speaker_voice_map[spk] = yaml_voice
        else:
            # No YAML voice — assign based on gender
            gender = speaker_gender.get(spk, "")
            if gender == "female":
                if has_openai:
                    speaker_voice_map[spk] = openai_female_voices[female_idx % len(openai_female_voices)]
                else:
                    speaker_voice_map[spk] = edge_female_voices[female_idx % len(edge_female_voices)]
                female_idx += 1
            elif gender == "male":
                if has_openai:
                    speaker_voice_map[spk] = openai_male_voices[male_idx % len(openai_male_voices)]
                else:
                    speaker_voice_map[spk] = edge_male_voices[male_idx % len(edge_male_voices)]
                male_idx += 1
            else:
                if (female_idx + male_idx) % 2 == 0:
                    if has_openai:
                        speaker_voice_map[spk] = openai_female_voices[female_idx % len(openai_female_voices)]
                    else:
                        speaker_voice_map[spk] = edge_female_voices[female_idx % len(edge_female_voices)]
                    female_idx += 1
                else:
                    if has_openai:
                        speaker_voice_map[spk] = openai_male_voices[male_idx % len(openai_male_voices)]
                    else:
                        speaker_voice_map[spk] = edge_male_voices[male_idx % len(edge_male_voices)]
                    male_idx += 1

    log.info(f"  Speaker voice map: {speaker_voice_map}")

    # Default voices for unnamed segments (crowd, narration, etc.)
    default_female_voice = openai_female_voices[0] if has_openai else edge_female_voices[0]
    default_male_voice = openai_male_voices[0] if has_openai else edge_male_voices[0]
    import random as _rng

    tts_dir = video_path.parent / "_tts_en"
    tts_dir.mkdir(exist_ok=True)

    # Prepare TTS jobs (segment index, path, text, voice, name, gender)
    tts_jobs = []
    for i, seg in enumerate(segments):
        tts_path = tts_dir / f"seg_{i:03d}.mp3"

        # Pick voice for this segment
        name = seg.get("name", "").strip()
        if name and name in speaker_voice_map:
            voice = speaker_voice_map[name]
            seg_gender = speaker_gender.get(name, "")
        else:
            # No known speaker — detect gender from text content and randomly pick a voice
            seg_text = seg.get("text", "").lower()
            # Heuristic gender detection from speech content
            female_hints = ("lady", "girl", "miss", "ma'am", "madam", "she ", "her ", "mother", "sister", "daughter", "wife", "queen", "princess")
            male_hints = ("sir", "mister", "mr.", "he ", "him ", "man", "boy", "father", "brother", "son", "husband", "king", "old man")
            female_score = sum(1 for h in female_hints if h in seg_text)
            male_score = sum(1 for h in male_hints if h in seg_text)
            if female_score > male_score:
                seg_gender = "female"
            elif male_score > female_score:
                seg_gender = "male"
            else:
                # No hints — random gender
                seg_gender = _rng.choice(["female", "male"])

            if seg_gender == "female":
                voice = _rng.choice(openai_female_voices) if has_openai else _rng.choice(edge_female_voices)
            else:
                voice = _rng.choice(openai_male_voices) if has_openai else _rng.choice(edge_male_voices)
            name = ""

        tts_jobs.append((i, seg, tts_path, voice, name, seg_gender))

    # Generate TTS in parallel (up to 4 concurrent) for speed
    tts_files = []
    max_workers = min(4, len(tts_jobs)) if tts_jobs else 1
    log.info(f"  Generating TTS for {len(tts_jobs)} segments (parallel={max_workers})...")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _tts_worker(job):
        idx, seg, tts_path, voice, name, seg_gender = job
        success = _generate_tts_segment(
            seg["text"], tts_path, voice=voice,
            speaker_name=name, gender=seg_gender,
        )
        return idx, seg, tts_path, success

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_tts_worker, job): job for job in tts_jobs}
        for future in as_completed(futures):
            idx, seg, tts_path, success = future.result()
            if success:
                tts_files.append({"path": tts_path, "start": seg["start"], "end": seg["end"]})
            else:
                log.warning(f"  Skipping segment {idx}: TTS generation failed for: {seg['text'][:50]}")

    # Sort by start time (futures may complete out of order)
    tts_files.sort(key=lambda x: x["start"])

    if not tts_files:
        log.warning("No TTS segments generated. Cannot create EN version.")
        shutil.rmtree(tts_dir, ignore_errors=True)
        if trimmed_video != video_path:
            trimmed_video.unlink(missing_ok=True)
        return None

    log.info(f"  Generated TTS for {len(tts_files)}/{len(segments)} segments ({len(speakers)} named speakers)")

    # Step 3: Get video duration and check for audio stream
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", str(trimmed_video)],
            capture_output=True, text=True, timeout=100,
        )
        probe_data = json.loads(probe.stdout)
        video_duration = float(probe_data.get("format", {}).get("duration", "120"))
        has_audio_stream = any(s.get("codec_type") == "audio" for s in probe_data.get("streams", []))
    except Exception:
        video_duration = 120.0
        has_audio_stream = False

    log.info(f"  Video duration: {video_duration:.1f}s, has audio: {has_audio_stream}")

    # Step 4: Build ffmpeg complex filter
    filter_inputs = ["-i", str(trimmed_video)]
    for tf in tts_files:
        filter_inputs.extend(["-i", str(tf["path"])])

    n_inputs = len(tts_files)
    filter_parts = []

    if has_audio_stream:
        # Mute original audio during speech segments (where TTS will play),
        # keep it at full volume during non-speech (music, SFX, ambient).
        # Build a volume expression that drops to 0 during speech and stays at 1 otherwise.
        # This preserves audio quality between dialogue and completely removes original speech.
        if tts_files:
            # Build enable expression: volume=0 during any speech segment
            # Format: volume=if(between(t,start1,end1)+between(t,start2,end2)+...,0,1)
            # NOTE: No quotes around expression — we pass args as list, not via shell
            between_parts = "+".join(
                f"between(t\\,{tf['start']:.2f}\\,{tf['end']:.2f})" for tf in tts_files
            )
            vol_expr = f"volume=if({between_parts}\\,0\\,1):eval=frame"
            filter_parts.append(f"[0:a]{vol_expr}[bg]")
        else:
            filter_parts.append("[0:a]volume=1.0[bg]")
    else:
        # No audio stream — generate silent background
        log.info("  No audio in source video. Generating silent background.")
        filter_inputs = ["-i", str(trimmed_video), "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={video_duration}"]
        # Re-add TTS inputs after the silent source
        for tf in tts_files:
            filter_inputs.extend(["-i", str(tf["path"])])
        filter_parts.append("[1:a]volume=0.0[bg]")
        # TTS inputs now start at index 2 instead of 1
        n_inputs = len(tts_files)

    # Delay each TTS segment to its start time, boost volume, and pad to video duration
    mix_inputs = ["[bg]"]
    tts_input_offset = 1 if has_audio_stream else 2
    for i, tf in enumerate(tts_files):
        delay_ms = int(tf["start"] * 1000)
        input_idx = i + tts_input_offset
        filter_parts.append(
            f"[{input_idx}:a]adelay={delay_ms}|{delay_ms},volume=3.0,apad=whole_dur={video_duration}[tts{i}]"
        )
        mix_inputs.append(f"[tts{i}]")

    # Mix all together: background + all TTS segments
    # Since background is muted during speech, TTS doesn't compete — use simple amix
    # Use duration=longest so TTS segments near the end aren't cut off mid-sentence
    all_mix = "".join(mix_inputs)
    filter_parts.append(f"{all_mix}amix=inputs={n_inputs + 1}:duration=longest:dropout_transition=2:normalize=0,volume=4.0[aout]")

    filter_complex = ";".join(filter_parts)

    # Output path for the video (may be replaced if we prepend EN opening)
    en_video_no_opening = output_path.parent / f"_en_body_{output_path.name}"

    cmd = [
        "ffmpeg", "-y",
        *filter_inputs,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(en_video_no_opening),
    ]

    log.info("  Mixing TTS audio into video (speech removed, background preserved)...")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)

    # Clean up TTS temp files and trimmed video
    shutil.rmtree(tts_dir, ignore_errors=True)
    if trimmed_video != video_path:
        trimmed_video.unlink(missing_ok=True)

    if result.returncode != 0:
        log.warning(f"  EN version mix failed: {(result.stderr or '')[:500]}")
        en_video_no_opening.unlink(missing_ok=True)
        return None

    if not en_video_no_opening.exists():
        return None

    # Step 5: Generate English opening and prepend
    if episode_number is not None and first_clip is not None:
        # Load English story name from API or script.yaml
        en_story_name = ""
        try:
            story = fetch_story_from_api(story_slug) if story_slug else None
            if story:
                en_story_name = story.get("title") or story.get("title_zh", "")
        except Exception:
            pass
        # Fallback to script.yaml
        if not en_story_name and story_slug:
            try:
                script_path = get_project_root() / "data" / "stories" / story_slug / "episodes" / str(episode_number) / "script.yaml"
                if script_path.exists():
                    script_data = yaml.safe_load(script_path.read_text(encoding="utf-8"))
                    if script_data:
                        en_story_name = script_data.get("title") or script_data.get("title_zh", "")
            except Exception:
                pass

        en_opening = generate_episode_opening(
            episode_number=episode_number,
            story_slug=story_slug,
            first_clip=first_clip,
            output_dir=output_path.parent,
            content_lang="en",
            override_story_name=en_story_name,
        )
        if en_opening and en_opening.exists():
            log.info(f"  EN opening generated: {en_opening.name}")
            # The EN opening has no audio (-an), so add a silent audio track
            # to match the EN body's audio stream for concat compatibility
            en_opening_with_audio = output_path.parent / f"_en_opening_audio_{en_opening.name}"
            add_audio_cmd = [
                "ffmpeg", "-y",
                "-i", str(en_opening),
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                "-movflags", "+faststart",
                str(en_opening_with_audio),
            ]
            add_audio_result = subprocess.run(add_audio_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            if add_audio_result.returncode == 0 and en_opening_with_audio.exists():
                en_opening.unlink(missing_ok=True)
                en_opening = en_opening_with_audio
            else:
                log.warning(f"  Failed to add silent audio to EN opening: {(add_audio_result.stderr or '')[:200]}")

            # Concat EN opening + EN body
            concat_output = output_path.parent / f"_en_concat_{output_path.name}"
            concat_list = output_path.parent / "_en_concat_list.txt"
            concat_list.write_text(
                f"file '{en_opening.resolve()}'\nfile '{en_video_no_opening.resolve()}'\n",
                encoding="utf-8",
            )
            concat_cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                "-movflags", "+faststart",
                str(concat_output),
            ]
            concat_result = subprocess.run(concat_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            concat_list.unlink(missing_ok=True)
            en_opening.unlink(missing_ok=True)

            if concat_result.returncode == 0 and concat_output.exists():
                en_video_no_opening.unlink(missing_ok=True)
                shutil.move(str(concat_output), str(output_path))
                log.info(f"  Global EN version saved (with opening): {output_path}")
                return output_path
            else:
                log.warning(f"  EN concat failed: {(concat_result.stderr or '')[:300]}")
                concat_output.unlink(missing_ok=True)
                # Fall through — use body without opening

    # No opening or opening failed — just rename body
    shutil.move(str(en_video_no_opening), str(output_path))
    log.info(f"  Global EN version saved: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------


def generate_temp_final_summary(
    ep_dir: Path,
    selected_clips: list[Path],
    scenes_run_ts: str | None = None,
) -> Path:
    """Generate a temp_final_summary.yaml from the scene prompts of selected clips.

    This summary captures exactly which clips were composed and their prompts,
    providing context for the next episode's generation.
    """
    scenes_dir = ep_dir / "scenes"

    # Resolve scenes run dir
    if scenes_run_ts:
        scenes_run_dir = scenes_dir / scenes_run_ts
    else:
        selected = os.environ.get("SELECTED_SCENES_DIR")
        if selected:
            scenes_run_dir = scenes_dir / selected
        elif scenes_dir.exists():
            subdirs = sorted([d for d in scenes_dir.iterdir() if d.is_dir()], reverse=True)
            scenes_run_dir = subdirs[0] if subdirs else scenes_dir
        else:
            scenes_run_dir = scenes_dir

    # Collect scene prompts for selected clips
    composed_scenes: list[dict] = []
    seen_scenes: set[int] = set()

    for clip_path in selected_clips:
        clip_name = clip_path.stem  # e.g., scene_1_clip_1
        prompt_file = scenes_run_dir / f"{clip_name}_prompt.yaml"

        clip_entry: dict = {
            "clip_name": clip_name,
            "file": clip_path.name,
        }

        if prompt_file.exists():
            try:
                prompt_data = load_yaml(str(prompt_file))
                clip_entry["prompt"] = prompt_data.get("description") or prompt_data.get("prompt", "")
                clip_entry["dialogue"] = prompt_data.get("dialogue", [])
                clip_entry["action"] = prompt_data.get("action", "")
                clip_entry["environment"] = prompt_data.get("environment", "")
                clip_entry["sound_effects"] = prompt_data.get("sound_effects", [])
            except Exception:
                pass

        # Parse scene number
        match = re.match(r"scene_(\d+)", clip_name)
        if match:
            scene_num = int(match.group(1))
            clip_entry["scene_number"] = scene_num
            seen_scenes.add(scene_num)

        composed_scenes.append(clip_entry)

    # Also load the full scenes_breakdown for scene-level metadata
    scenes_breakdown = {}
    breakdown_file = scenes_run_dir / "scenes_breakdown.yaml"
    if not breakdown_file.exists():
        breakdown_file = ep_dir / "scenes_breakdown.yaml"
    if breakdown_file.exists():
        try:
            scenes_breakdown = load_yaml(str(breakdown_file))
        except Exception:
            pass

    # Build scene-level summaries for the composed scenes only
    scene_summaries = []
    for scene_data in scenes_breakdown.get("scenes", []):
        scene_num = scene_data.get("scene_number")
        if scene_num in seen_scenes:
            scene_summaries.append({
                "scene_number": scene_num,
                "location_ref": scene_data.get("location_ref", ""),
                "mood": scene_data.get("mood", ""),
                "character_refs": scene_data.get("character_refs", []),
                "style": scene_data.get("style", ""),
            })

    summary = {
        "status": "temp",
        "composed_clips": composed_scenes,
        "scene_summaries": scene_summaries,
        "total_clips_composed": len(selected_clips),
        "total_scenes_covered": len(seen_scenes),
        "consistency_notes": scenes_breakdown.get("consistency_notes", ""),
    }

    summary_path = ep_dir / "temp_final_summary.yaml"
    save_yaml(summary, str(summary_path))
    log.info(f"Temp final summary saved: {summary_path}")
    return summary_path


def finalize_summary(ep_dir: Path) -> Path | None:
    """Promote temp_final_summary.yaml to final_summary.yaml after publishing."""
    temp_path = ep_dir / "temp_final_summary.yaml"
    final_path = ep_dir / "final_summary.yaml"

    if not temp_path.exists():
        log.warning("No temp_final_summary.yaml found to finalize.")
        return None

    summary = load_yaml(str(temp_path))
    summary["status"] = "final"
    save_yaml(summary, str(final_path))
    log.info(f"Final summary saved: {final_path}")

    # Also copy summary to final/ folder for publish agent
    final_folder_path = ep_dir / "final" / "final_summary.yaml"
    final_folder_path.parent.mkdir(parents=True, exist_ok=True)
    save_yaml(summary, str(final_folder_path))

    return final_path


# ---------------------------------------------------------------------------
# LLM-based edit plan
# ---------------------------------------------------------------------------


def generate_edit_plan_with_llm(
    episode_number: int, story_slug: str, clips: list[Path]
) -> dict:
    """Call editor agent via LLM to plan the assembly."""
    from llm import call_agent, parse_yaml_response
    from common import story_dir

    ep_dir = episode_dir(episode_number, story_slug)
    script_path = ep_dir / "script.yaml"
    script_data = {}
    if script_path.exists():
        script_data = load_yaml(str(script_path))

    scenes_breakdown = ""
    scenes_file = ep_dir / "scenes_breakdown.yaml"
    if scenes_file.exists():
        scenes_breakdown = scenes_file.read_text(encoding="utf-8")

    audio_plan = ""
    audio_file = ep_dir / "audio_plan.yaml"
    if audio_file.exists():
        audio_plan = audio_file.read_text(encoding="utf-8")

    previous_episodes_context = ""
    if episode_number > 1:
        base = story_dir(story_slug) / "episodes"
        prev_summary = base / str(episode_number - 1) / "final_summary.yaml"
        if prev_summary.exists():
            previous_episodes_context = (
                f"### Previous Episode (Ep {episode_number - 1}) Summary\n"
                f"```yaml\n{prev_summary.read_text(encoding='utf-8')}\n```"
            )
        else:
            prev_script = base / str(episode_number - 1) / "script.yaml"
            if prev_script.exists():
                previous_episodes_context = (
                    f"### Previous Episode (Ep {episode_number - 1}) Script\n"
                    f"```yaml\n{prev_script.read_text(encoding='utf-8')}\n```"
                )

    clip_names = [c.name for c in clips]
    user_message = f"""Plan the post-production assembly for Episode {episode_number}.

## Available Clips ({len(clips)} total)
{yaml.dump(clip_names, default_flow_style=False)}

## Episode Script
```yaml
{yaml.dump(script_data, default_flow_style=False, allow_unicode=True)}
```

## Previous Episode
{previous_episodes_context if previous_episodes_context else "This is the first episode."}

## Scene Breakdown (from @director)
```yaml
{scenes_breakdown if scenes_breakdown else "Not available"}
```

## Audio Plan (from @sound-designer)
```yaml
{audio_plan if audio_plan else "Not available"}
```

## Assembly Specifications
- Target duration: ~2 minutes (120 seconds)
- Transitions: ALL cuts (direct cut, no crossfade or fade effects)

## Output Requirements
Output ONLY valid YAML:

edit_plan:
  total_clips: {len(clips)}
  target_duration_seconds: 120
  assembly_order: [<clip filenames in correct sequence>]
  transitions: cut
  pacing_notes: "<overall pacing>"
"""

    log.info(f"Generating edit plan for Episode {episode_number}...")
    try:
        raw_text = call_agent("editor", user_message)
        edit_plan = parse_yaml_response(raw_text)
        save_yaml(edit_plan, ep_dir / "edit_plan.yaml")
        log.info("Edit plan generated and saved")
        return edit_plan
    except Exception as e:
        log.warning(f"LLM edit plan failed, using default assembly: {e}")
        return {}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Compose episode from scene clips")
    parser.add_argument("--episode", type=int, required=True, help="Episode number")
    parser.add_argument("--story", type=str, default=None, help="Story slug")
    parser.add_argument("--transitions", type=str, default=None, help="Transition style override")
    parser.add_argument("--skip-validation", action="store_true", help="Skip quality validation")
    parser.add_argument(
        "--list-assets", action="store_true",
        help="List available clips and audio files, then exit",
    )
    parser.add_argument(
        "--select-clips", type=str, default=None,
        help="Comma-separated list of clip filenames to include (default: all)",
    )
    parser.add_argument(
        "--select-audio", type=str, default=None,
        help="Comma-separated list of audio filenames to include (default: all)",
    )
    parser.add_argument(
        "--mute-video-audio", action="store_true",
        help="Mute original video audio (strip audio track from clips)",
    )
    parser.add_argument(
        "--no-watermark", action="store_true",
        help="Skip watermark overlay",
    )
    parser.add_argument(
        "--subtitles", action="store_true", default=True,
        help="Auto-generate subtitles from audio (default: enabled)",
    )
    parser.add_argument(
        "--no-subtitles", action="store_true",
        help="Explicitly skip subtitle generation",
    )
    parser.add_argument(
        "--global-en", action="store_true", default=True,
        help="Generate English (global) version with TTS audio (default: enabled)",
    )
    parser.add_argument(
        "--no-global-en", action="store_true",
        help="Skip English global version generation",
    )
    parser.add_argument(
        "--no-opening", action="store_true",
        help="Skip episode opening generation (2s title card)",
    )
    args = parser.parse_args()

    config = load_config()
    if args.transitions:
        config["composition"]["transitions"]["between_scenes"] = args.transitions

    ep_dir = episode_dir(args.episode, args.story)

    # Discover available assets
    all_clips = discover_clips(ep_dir)
    all_audio = discover_audio_files(ep_dir)

    if not all_clips:
        log.error(f"No scene clips found in {ep_dir / 'clips'}")
        log.error("Generate clips first with: python agents/generate_video.py --episode N --story SLUG")
        sys.exit(1)

    # List mode: print assets and exit
    if args.list_assets:
        assets = list_assets(ep_dir)
        print(yaml.dump(assets, default_flow_style=False, allow_unicode=True))
        return

    # Select clips (default: all, sorted in natural scene/clip order)
    if args.select_clips:
        selected_names = set(args.select_clips.split(","))
        selected_clips = [c for c in all_clips if c.name in selected_names]
        if not selected_clips:
            log.error(f"None of the selected clips found: {args.select_clips}")
            sys.exit(1)
    else:
        selected_clips = all_clips

    # Select audio (default: all)
    if args.select_audio is not None:
        if args.select_audio == "":
            selected_audio = []  # Explicitly no audio
        else:
            selected_audio_names = set(args.select_audio.split(","))
            selected_audio = [a for a in all_audio if a.name in selected_audio_names]
    else:
        selected_audio = all_audio  # Default: all

    log.info(f"Composing Episode {args.episode}")
    log.info(f"  Selected clips: {len(selected_clips)}/{len(all_clips)}")
    for c in selected_clips:
        log.info(f"    - {c.name} ({c.stat().st_size / 1024:.0f} KB)")
    log.info(f"  Audio files: {len(selected_audio)}")
    for a in selected_audio:
        log.info(f"    - {a.name} ({a.stat().st_size / 1024:.0f} KB)")
    log.info(f"  Mute video audio: {args.mute_video_audio}")

    # Generate edit plan with editor agent
    try:
        generate_edit_plan_with_llm(args.episode, args.story, selected_clips)
    except Exception as e:
        log.warning(f"Edit plan generation failed (non-blocking): {e}")

    # Compose — use timestamped subfolder like other agents
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_dir = ep_dir / "compose" / ts
    final_dir.mkdir(parents=True, exist_ok=True)
    raw_output = final_dir / f"episode_{args.episode}_raw.mp4"
    final_output = final_dir / f"episode_{args.episode}.mp4"

    # Generate episode opening (2s title card + AI disclaimer)
    if not args.no_opening and selected_clips:
        opening_clip = generate_episode_opening(
            episode_number=args.episode,
            story_slug=args.story,
            first_clip=selected_clips[0],
            output_dir=final_dir,
        )
        if opening_clip:
            selected_clips = [opening_clip] + selected_clips
            log.info(f"  Opening clip prepended: {opening_clip.name}")

    _, crop_dims = compose_clips(
        selected_clips,
        raw_output,
        config,
        mute_video_audio=args.mute_video_audio,
        audio_files=selected_audio if selected_audio else None,
        transition=args.transitions,
    )

    # Add watermark
    if not args.no_watermark:
        wm_result = add_watermark(raw_output, final_output)
        # If watermark succeeded, final_output exists; if it failed, it returned raw_output
        if final_output.exists():
            raw_output.unlink(missing_ok=True)
        else:
            # Watermark failed — just use raw as final
            shutil.move(str(raw_output), str(final_output))
    else:
        shutil.move(str(raw_output), str(final_output))

    # Auto-generate subtitles
    do_subtitles = args.subtitles and not args.no_subtitles
    content_lang = _detect_story_language(args.story)
    ass_path: Path | None = None
    if do_subtitles:
        log.info("Generating auto-subtitles from audio...")
        sub_output = final_output.parent / f"episode_{args.episode}_sub.mp4"
        sub_result = generate_subtitles(final_output, sub_output, content_lang=content_lang,
                                        story_slug=args.story, episode_number=args.episode,
                                        clips=selected_clips)
        if sub_result and sub_result.exists():
            # Replace final with subtitled version
            final_output.unlink(missing_ok=True)
            shutil.move(str(sub_result), str(final_output))
            log.info("Subtitles burned into final episode.")
            # Locate the generated ASS file for global EN
            candidate_ass = final_output.parent / f"{final_output.stem}.ass"
            if not candidate_ass.exists():
                # Try the pre-subtitle video stem
                candidate_ass = final_output.parent / f"episode_{args.episode}.ass"
            if candidate_ass.exists():
                ass_path = candidate_ass
        else:
            log.warning("Subtitle generation failed. Continuing without subtitles.")

    # Generate global English version (TTS dubbed)
    do_global_en = (
        args.global_en
        and not args.no_global_en
        and do_subtitles
        and not content_lang.startswith("en")
    )
    if do_global_en:
        if ass_path and ass_path.exists():
            en_output = final_output.parent / f"episode_{args.episode}_EN.mp4"
            # Pass episode info for EN opening generation
            # Use the first scene clip (not the opening) for the first frame
            first_scene_clip = next((c for c in selected_clips if "_opening" not in c.name), selected_clips[0] if selected_clips else None)
            en_result = generate_global_en_version(
                final_output, ass_path, en_output,
                episode_number=args.episode,
                story_slug=args.story,
                first_clip=first_scene_clip,
                has_opening=not args.no_opening,
            )
            if en_result and en_result.exists():
                # Crop EN video to same content bounds as original if crop was applied
                if crop_dims:
                    crop_w, crop_h = crop_dims
                    en_info = _probe_clip(en_result)
                    if en_info["width"] > crop_w or en_info["height"] > crop_h:
                        log.info(f"Cropping EN video from {en_info['width']}x{en_info['height']} to {crop_w}x{crop_h}")
                        en_cropped = en_result.parent / f"_en_cropped_{en_result.name}"
                        en_crop_cmd = [
                            "ffmpeg", "-y", "-i", str(en_result),
                            "-vf", f"scale={crop_w}:{crop_h}:force_original_aspect_ratio=decrease,pad={crop_w}:{crop_h}:(ow-iw)/2:(oh-ih)/2,crop={crop_w}:{crop_h}",
                            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                            "-color_range", "tv", "-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709",
                            "-c:a", "copy",
                            "-movflags", "+faststart",
                            str(en_cropped),
                        ]
                        en_crop_result = subprocess.run(en_crop_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
                        if en_crop_result.returncode == 0 and en_cropped.exists():
                            en_result.unlink(missing_ok=True)
                            shutil.move(str(en_cropped), str(en_result))
                            log.info(f"  EN video cropped to {crop_w}x{crop_h}")
                        else:
                            log.warning(f"  EN crop failed: {(en_crop_result.stderr or '')[:200]}")
                            en_cropped.unlink(missing_ok=True)
                log.info(f"Global EN version: {en_result} ({en_result.stat().st_size / 1024 / 1024:.1f} MB)")
            else:
                log.warning("Global EN version generation failed.")
        else:
            log.warning("No subtitle file found. Cannot generate global EN version.")

    # Post-assembly validation (informational)
    if not args.skip_validation and final_output.exists():
        from validate_quality import load_qa_config, validate_clip

        qa_config = load_qa_config()
        # Set expected duration: opening + sum of clip durations - crossfade overlaps + tolerance
        # Each crossfade between N clips removes (N-1) * crossfade_dur from total
        opening_dur = 2.0 if not args.no_opening else 0.0
        non_opening_clips = [c for c in selected_clips if "_opening" not in c.name]
        clip_dur_sum = sum(
            _probe_clip(c).get("duration", 5.0)
            for c in non_opening_clips
        )
        n_clips_total = len(non_opening_clips) + (1 if not args.no_opening else 0)
        xfade_dur = float(os.environ.get("CLIP_CROSSFADE_SECONDS", "0.75"))
        xfade_loss = max(0, n_clips_total - 1) * xfade_dur
        expected_dur = opening_dur + clip_dur_sum - xfade_loss
        tolerance = 5.0
        if "clip_validation" not in qa_config:
            qa_config["clip_validation"] = {}
        qa_config["clip_validation"]["max_duration_seconds"] = expected_dur + tolerance
        qa_config["clip_validation"]["min_duration_seconds"] = max(0, expected_dur - tolerance)
        result = validate_clip(final_output, qa_config)
        if not result["passed"]:
            log.warning("Post-assembly validation issues:")
            for issue in result["issues"]:
                log.warning(f"  - {issue}")
        else:
            log.info("Post-assembly validation PASSED")

    # Generate temp final summary from selected clips
    clips_run_ts = None
    if selected_clips:
        clips_run_ts = selected_clips[0].parent.name
    generate_temp_final_summary(ep_dir, selected_clips, scenes_run_ts=clips_run_ts)

    log.info(f"Final episode: {final_output} ({final_output.stat().st_size / 1024 / 1024:.1f} MB)")
    log.info(f"Composition saved to {final_dir}")

    # Clean up intermediate files from compose output dir (opening, raw, temp)
    for cleanup_pat in ["*_opening.mp4", "_prep_*", "_concat_*", "_with_audio.mp4", "_en_body_*", "_en_concat_*", "_en_trimmed_*", "_en_cropped_*", "_en_opening_audio_*"]:
        for f in final_dir.glob(cleanup_pat):
            f.unlink(missing_ok=True)
            log.info(f"  Cleaned up: {f.name}")


if __name__ == "__main__":
    main()
