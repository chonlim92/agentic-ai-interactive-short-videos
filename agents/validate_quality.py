"""Validate Video Quality

Runs quality assurance checks on generated clips, scenes, and episodes.
Called by @artist after generation, @editor before assembly, and @showrunner before publish.

Usage:
    python agents/validate_quality.py --clip data/episodes/1/scenes/scene_1_clip_1.mp4
    python agents/validate_quality.py --scene data/episodes/1/scenes/ --scene-number 1
    python agents/validate_quality.py --episode 1
    python agents/validate_quality.py --episode 1 --story my-story --review
"""

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

import argparse
import os
import re
import sys
from pathlib import Path

from common import config_path, episode_dir, load_env, load_yaml, save_yaml, setup_logging

load_env()
log = setup_logging("validate_quality")


def load_qa_config() -> dict:
    """Load quality assurance config."""
    config = load_yaml(config_path("video_generation.yaml"))
    return config.get("quality_assurance", {})


# ---------------------------------------------------------------------------
# Clip-level validation (@artist runs after each clip generation)
# ---------------------------------------------------------------------------


def validate_clip(clip_path: Path, qa_config: dict) -> dict:
    """
    Validate a single generated clip against quality criteria.

    Returns:
        dict with keys: passed (bool), issues (list[str]), metrics (dict)
    """
    clip_config = qa_config.get("clip_validation", {})
    issues = []
    metrics = {}

    if not clip_path.exists():
        return {"passed": False, "issues": ["File does not exist"], "metrics": {}}

    # File size check
    file_size_kb = clip_path.stat().st_size / 1024
    metrics["file_size_kb"] = round(file_size_kb, 1)
    min_size = clip_config.get("min_file_size_kb", 100)
    if file_size_kb < min_size:
        issues.append(f"File too small: {file_size_kb:.1f}KB < {min_size}KB minimum")

    # Duration, resolution, fps checks (require opencv)
    try:
        import cv2

        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            issues.append("Cannot open video file")
            return {"passed": False, "issues": issues, "metrics": metrics}

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = frame_count / fps if fps > 0 else 0

        metrics["duration_seconds"] = round(duration, 2)
        metrics["fps"] = round(fps, 1)
        metrics["resolution"] = f"{width}x{height}"
        metrics["frame_count"] = frame_count

        # Duration check
        min_dur = clip_config.get("min_duration_seconds", 2.5)
        max_dur = clip_config.get("max_duration_seconds", 7.0)
        if duration < min_dur:
            issues.append(f"Duration too short: {duration:.2f}s < {min_dur}s")
        if duration > max_dur:
            issues.append(f"Duration too long: {duration:.2f}s > {max_dur}s")

        # FPS check
        min_fps = clip_config.get("min_fps", 20)
        if fps < min_fps:
            issues.append(f"FPS too low: {fps:.1f} < {min_fps}")

        # Resolution check
        min_res_map = {"480p": 480, "720p": 720, "1080p": 1080}
        min_res_str = clip_config.get("min_resolution", "480p")
        min_height = min_res_map.get(min_res_str, 480)
        if height < min_height:
            issues.append(f"Resolution too low: {height}p < {min_res_str}")

        # Black frame / static frame analysis
        black_frames = 0
        static_frames = 0
        prev_frame = None
        sample_interval = max(1, frame_count // 30)  # Sample up to 30 frames

        for i in range(0, frame_count, sample_interval):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret:
                break

            # Black frame detection
            if frame.mean() < 5:
                black_frames += 1

            # Static frame detection
            if prev_frame is not None:
                diff = cv2.absdiff(frame, prev_frame).mean()
                if diff < 1.0:
                    static_frames += 1

            prev_frame = frame

        samples = max(1, frame_count // sample_interval)
        black_ratio = black_frames / samples
        static_ratio = static_frames / max(1, samples - 1)

        metrics["black_frame_ratio"] = round(black_ratio, 3)
        metrics["static_frame_ratio"] = round(static_ratio, 3)

        max_black = clip_config.get("max_black_frame_ratio", 0.15)
        max_static = clip_config.get("max_static_frame_ratio", 0.30)
        if black_ratio > max_black:
            issues.append(f"Too many black frames: {black_ratio:.1%} > {max_black:.0%}")
        if static_ratio > max_static:
            issues.append(f"Too many static frames: {static_ratio:.1%} > {max_static:.0%}")

        cap.release()

    except ImportError:
        issues.append("opencv-python not installed -- skipping video analysis")

    # Object consistency check: detect sudden object identity changes within the clip
    # (e.g., phone transforms into coin, or laptop becomes a book mid-clip)
    try:
        _check_object_consistency(clip_path, issues, metrics)
    except Exception as e:
        log.warning(f"Object consistency check failed: {e}")

    # Floating object detection: find objects that defy gravity
    try:
        _check_floating_objects(clip_path, issues, metrics)
    except Exception as e:
        log.warning(f"Floating object check failed: {e}")

    # Audio naturalness check: verify speech audio is intelligible (not gibberish)
    try:
        _check_audio_naturalness(clip_path, clip_config, issues, metrics)
    except Exception as e:
        log.warning(f"Audio naturalness check failed: {e}")

    passed = len(issues) == 0
    return {"passed": passed, "issues": issues, "metrics": metrics}


def _check_object_consistency(clip_path: Path, issues: list, metrics: dict) -> None:
    """Detect sudden object identity changes within a clip.

    Samples frames across the clip and compares local regions for dramatic
    content shifts that suggest an object morphed into a different object
    (e.g., phone→coin, laptop→book). Uses histogram comparison on central
    regions where held objects typically appear.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return

    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        return

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if frame_count < 10:
        cap.release()
        return

    # Sample 8 evenly-spaced frames
    sample_count = 8
    indices = [int(i * (frame_count - 1) / (sample_count - 1)) for i in range(sample_count)]

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    cap.release()

    if len(frames) < 4:
        return

    # Compare center-bottom region (where hands/held objects typically are)
    h, w = frames[0].shape[:2]
    # Focus on lower-center area: 40-80% height, 25-75% width
    y1, y2 = int(h * 0.4), int(h * 0.8)
    x1, x2 = int(w * 0.25), int(w * 0.75)

    prev_hist = None
    max_shift = 0.0
    shift_count = 0

    for frame in frames:
        region = frame[y1:y2, x1:x2]
        hist = cv2.calcHist([region], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        hist = cv2.normalize(hist, hist).flatten()

        if prev_hist is not None:
            correlation = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
            shift = 1.0 - correlation
            if shift > max_shift:
                max_shift = shift
            # A shift > 0.6 between adjacent samples suggests object identity change
            if shift > 0.6:
                shift_count += 1

        prev_hist = hist

    metrics["object_consistency_max_shift"] = round(max_shift, 3)
    metrics["object_consistency_violations"] = shift_count

    if shift_count >= 2:
        issues.append(
            f"Object identity change detected: {shift_count} dramatic content shifts "
            f"in held-object region (max shift: {max_shift:.3f}). "
            f"Possible object morphing (e.g., phone→coin, laptop→book)"
        )


def _check_floating_objects(clip_path: Path, issues: list, metrics: dict) -> None:
    """Detect objects that appear to float/defy gravity.

    Uses edge detection and connected component analysis on sampled frames.
    Looks for isolated bright/distinct blobs in the upper portion of the frame
    that are disconnected from any surface or character — suggesting floating objects.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return

    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        return

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if frame_count < 6:
        cap.release()
        return

    # Sample 6 frames
    sample_count = 6
    indices = [int(i * (frame_count - 1) / (sample_count - 1)) for i in range(sample_count)]

    floating_frames = 0
    total_checked = 0

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue

        total_checked += 1
        h, w = frame.shape[:2]

        # Focus on upper half (floating objects defy gravity — they're above surfaces)
        upper = frame[0:int(h * 0.5), :]

        # Edge detection to find distinct object boundaries
        gray = cv2.cvtColor(upper, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

        # Find contours (potential floating objects)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Look for small-to-medium isolated blobs (not the background or main character)
        min_area = (h * w) * 0.002  # Min 0.2% of frame
        max_area = (h * w) * 0.08   # Max 8% of frame
        suspicious_blobs = 0

        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area < area < max_area:
                # Check if the blob is isolated (not touching frame edges)
                x, y, bw, bh = cv2.boundingRect(contour)
                if x > 5 and y > 5 and (x + bw) < (w - 5) and (y + bh) < (int(h * 0.5) - 5):
                    # Check aspect ratio — floating objects tend to be compact
                    aspect = max(bw, bh) / max(min(bw, bh), 1)
                    if aspect < 4:  # Not a line/edge
                        suspicious_blobs += 1

        if suspicious_blobs >= 3:
            floating_frames += 1

    cap.release()

    floating_ratio = floating_frames / max(total_checked, 1)
    metrics["floating_object_ratio"] = round(floating_ratio, 3)

    if floating_ratio > 0.5:
        issues.append(
            f"Possible floating objects detected in {floating_frames}/{total_checked} "
            f"sampled frames. Objects appear suspended without support in the upper frame."
        )


def _check_audio_naturalness(
    clip_path: Path, clip_config: dict, issues: list, metrics: dict
) -> None:
    """Check if audio contains natural speech vs gibberish/random noise.

    Analyzes the audio track for:
    1. Presence of audio at all
    2. Speech-like patterns (energy in speech frequency bands)
    3. Repetitive noise patterns that suggest gibberish
    """
    try:
        import subprocess
        import json as _json
    except ImportError:
        return

    # Use ffprobe to check audio stream existence and properties
    try:
        probe_cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-select_streams", "a",
            str(clip_path),
        ]
        probe_result = subprocess.run(
            probe_cmd, capture_output=True, text=True, timeout=10
        )
        if probe_result.returncode != 0:
            metrics["has_audio"] = False
            return

        probe_data = _json.loads(probe_result.stdout)
        audio_streams = probe_data.get("streams", [])
        metrics["has_audio"] = len(audio_streams) > 0

        if not audio_streams:
            return

    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        # ffprobe not available — skip audio checks
        return

    # Extract audio to raw PCM and analyze frequency patterns
    try:
        import numpy as np

        # Extract audio as raw PCM via ffmpeg
        extract_cmd = [
            "ffmpeg", "-v", "quiet", "-i", str(clip_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            "-f", "s16le", "pipe:1",
        ]
        extract_result = subprocess.run(
            extract_cmd, capture_output=True, timeout=15
        )
        if extract_result.returncode != 0 or len(extract_result.stdout) < 100:
            return

        audio_data = np.frombuffer(extract_result.stdout, dtype=np.int16).astype(np.float32)
        audio_data = audio_data / 32768.0  # Normalize to [-1, 1]

        if len(audio_data) < 1600:  # Less than 0.1s at 16kHz
            return

        # Check for speech-like energy distribution
        # Speech typically has energy concentrated in 300-3400 Hz band
        sample_rate = 16000
        n_fft = min(2048, len(audio_data))
        spectrum = np.abs(np.fft.rfft(audio_data[:n_fft]))
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)

        # Speech band (300-3400 Hz) vs total energy
        speech_mask = (freqs >= 300) & (freqs <= 3400)
        total_energy = np.sum(spectrum**2) + 1e-10
        speech_energy = np.sum(spectrum[speech_mask]**2)
        speech_ratio = speech_energy / total_energy

        metrics["audio_speech_energy_ratio"] = round(float(speech_ratio), 3)

        # Check for repetitive patterns (gibberish tends to have very regular repetition)
        # Split audio into small windows and check auto-correlation
        window_size = 1600  # 100ms windows
        windows = [audio_data[i:i + window_size]
                    for i in range(0, len(audio_data) - window_size, window_size)]

        if len(windows) >= 4:
            # Compare consecutive windows — natural speech varies, gibberish repeats
            similarities = []
            for i in range(len(windows) - 1):
                if len(windows[i]) == len(windows[i + 1]):
                    # Skip windows with zero variance (constant signal) to avoid
                    # numpy RuntimeWarning from corrcoef dividing by zero stddev
                    if np.std(windows[i]) < 1e-10 or np.std(windows[i + 1]) < 1e-10:
                        continue
                    corr = np.corrcoef(windows[i], windows[i + 1])[0, 1]
                    if not np.isnan(corr):
                        similarities.append(abs(corr))

            if similarities:
                avg_similarity = float(np.mean(similarities))
                metrics["audio_window_repetition"] = round(avg_similarity, 3)

                # Very high repetition (>0.85) suggests robotic/gibberish audio
                if avg_similarity > 0.85 and speech_ratio > 0.3:
                    issues.append(
                        f"Audio may contain unnatural/gibberish speech: "
                        f"high repetition pattern ({avg_similarity:.3f}), "
                        f"speech energy ratio {speech_ratio:.3f}. "
                        f"Speech sounds robotic or contains repeated syllables."
                    )

    except (ImportError, Exception) as e:
        log.debug(f"Audio analysis skipped: {e}")


# ---------------------------------------------------------------------------
# Consistency validation (@artist runs across clips within a scene)
# ---------------------------------------------------------------------------


def validate_clip_consistency(clip_paths: list[Path], qa_config: dict) -> dict:
    """
    Validate consistency between adjacent clips in a scene.

    Returns:
        dict with keys: passed (bool), issues (list[str]), metrics (dict)
    """
    consistency_config = qa_config.get("consistency_validation", {})
    issues = []
    metrics: dict[str, int | float] = {"clip_pairs_checked": 0}

    if len(clip_paths) < 2:
        return {"passed": True, "issues": [], "metrics": metrics}

    try:
        import cv2
    except ImportError:
        return {
            "passed": True,
            "issues": ["opencv/numpy not installed -- skipping consistency checks"],
            "metrics": metrics,
        }

    min_similarity = consistency_config.get("continuity_similarity_min", 0.70)
    brightness_threshold = consistency_config.get("brightness_drift_threshold", 0.15)
    color_threshold = consistency_config.get("color_drift_threshold", 0.20)

    for i in range(len(clip_paths) - 1):
        clip_a = clip_paths[i]
        clip_b = clip_paths[i + 1]

        # Get last frame of clip A
        cap_a = cv2.VideoCapture(str(clip_a))
        frame_count_a = int(cap_a.get(cv2.CAP_PROP_FRAME_COUNT))
        cap_a.set(cv2.CAP_PROP_POS_FRAMES, frame_count_a - 1)
        ret_a, last_frame_a = cap_a.read()
        cap_a.release()

        # Get first frame of clip B
        cap_b = cv2.VideoCapture(str(clip_b))
        ret_b, first_frame_b = cap_b.read()
        cap_b.release()

        if not ret_a or not ret_b:
            issues.append(f"Cannot read frames for clips {i + 1} -> {i + 2}")
            continue

        metrics["clip_pairs_checked"] = i + 1

        # Resize to same dimensions for comparison
        h = min(last_frame_a.shape[0], first_frame_b.shape[0])
        w = min(last_frame_a.shape[1], first_frame_b.shape[1])
        frame_a = cv2.resize(last_frame_a, (w, h))
        frame_b = cv2.resize(first_frame_b, (w, h))

        # SSIM-like structural similarity (simplified)
        gray_a = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY).astype(float)
        gray_b = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY).astype(float)
        numerator = 2 * gray_a.mean() * gray_b.mean() + 1e-5
        denominator = gray_a.mean() ** 2 + gray_b.mean() ** 2 + 1e-5
        similarity = numerator / denominator
        metrics[f"pair_{i + 1}_{i + 2}_similarity"] = round(similarity, 3)

        if similarity < min_similarity:
            issues.append(
                f"Clip {i + 1} -> {i + 2} continuity break: "
                f"similarity {similarity:.3f} < {min_similarity}"
            )

        # Brightness drift
        brightness_a = gray_a.mean() / 255.0
        brightness_b = gray_b.mean() / 255.0
        brightness_diff = abs(brightness_a - brightness_b)
        if brightness_diff > brightness_threshold:
            issues.append(
                f"Clip {i + 1} -> {i + 2} brightness drift: "
                f"{brightness_diff:.3f} > {brightness_threshold}"
            )

        # Color histogram drift
        hist_a = cv2.calcHist([frame_a], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        hist_b = cv2.calcHist([frame_b], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        hist_a = cv2.normalize(hist_a, hist_a).flatten()
        hist_b = cv2.normalize(hist_b, hist_b).flatten()
        color_diff = 1.0 - cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL)
        metrics[f"pair_{i + 1}_{i + 2}_color_drift"] = round(color_diff, 3)

        if color_diff > color_threshold:
            issues.append(
                f"Clip {i + 1} -> {i + 2} color drift: {color_diff:.3f} > {color_threshold}"
            )

    passed = len(issues) == 0
    return {"passed": passed, "issues": issues, "metrics": metrics}


# ---------------------------------------------------------------------------
# Scene-level validation (@editor runs before assembly)
# ---------------------------------------------------------------------------


def validate_scene(scene_dir: Path, scene_number: int, qa_config: dict) -> dict:
    """
    Validate all clips for a scene are present and pass quality.

    Returns:
        dict with keys: passed (bool), issues (list[str]), clip_results (list)
    """
    scene_config = qa_config.get("scene_validation", {})
    issues = []
    clip_results = []

    # Find clips for this scene
    pattern = f"scene_{scene_number}_clip_*.mp4"
    clips = sorted(scene_dir.glob(pattern))

    if not clips:
        # Also try alternate naming
        pattern_alt = f"scene_{scene_number}.mp4"
        clips = sorted(scene_dir.glob(pattern_alt))

    min_clips = scene_config.get("min_clips_per_scene", 2)
    if len(clips) < min_clips:
        issues.append(f"Scene {scene_number}: only {len(clips)} clips (need {min_clips}+)")

    # Validate each clip individually
    all_clips_must_pass = scene_config.get("all_clips_pass_quality", True)
    for clip_path in clips:
        result = validate_clip(clip_path, qa_config)
        clip_results.append({"file": clip_path.name, **result})
        if not result["passed"] and all_clips_must_pass:
            issues.append(f"Scene {scene_number}/{clip_path.name} failed: {result['issues']}")

    # Consistency across clips
    if len(clips) >= 2:
        consistency = validate_clip_consistency(clips, qa_config)
        if not consistency["passed"]:
            issues.extend(consistency["issues"])

    passed = len(issues) == 0
    return {"passed": passed, "issues": issues, "clip_results": clip_results}


# ---------------------------------------------------------------------------
# Episode-level validation (@showrunner runs before publishing)
# ---------------------------------------------------------------------------


def validate_episode(episode_number: int, qa_config: dict, story_slug: str | None = None) -> dict:
    """
    Validate the full episode is ready for publishing.

    Returns:
        dict with keys: passed (bool), issues (list[str]), scene_results (list)
    """
    episode_config = qa_config.get("episode_validation", {})
    issues = []
    scene_results = []

    ep_dir = episode_dir(episode_number, story_slug)
    scenes_dir = ep_dir / "scenes"
    final_dir = ep_dir / "final"
    final_video = final_dir / f"episode_{episode_number}.mp4"

    # Check final video exists
    if not final_video.exists():
        issues.append(f"Final video not found: {final_video}")
        return {"passed": False, "issues": issues, "scene_results": []}

    # Validate final video duration
    try:
        import cv2

        cap = cv2.VideoCapture(str(final_video))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        cap.release()

        min_dur = episode_config.get("min_total_duration_seconds", 150)
        max_dur = episode_config.get("max_total_duration_seconds", 210)
        if duration < min_dur:
            issues.append(f"Episode too short: {duration:.1f}s < {min_dur}s")
        if duration > max_dur:
            issues.append(f"Episode too long: {duration:.1f}s > {max_dur}s")
    except ImportError:
        issues.append("opencv-python not installed -- cannot validate duration")

    # Check audio track exists
    if episode_config.get("audio_present", True):
        audio_dir = ep_dir / "audio"
        if audio_dir.exists():
            audio_files = list(audio_dir.glob("*.wav")) + list(audio_dir.glob("*.mp3"))
        else:
            audio_files = []
        if not audio_files:
            issues.append("No audio files found for episode")

    # Validate individual scenes
    if scenes_dir.exists():
        scene_prompts = sorted(scenes_dir.glob("scene_*_prompt.yaml"))
        scene_numbers = set()
        for p in scene_prompts:
            try:
                num = int(p.stem.split("_")[1])
                scene_numbers.add(num)
            except (IndexError, ValueError):
                pass

        min_scenes = episode_config.get("min_scenes", 6)
        if len(scene_numbers) < min_scenes:
            issues.append(f"Only {len(scene_numbers)} scenes (need {min_scenes}+)")

        # Validate each scene
        if episode_config.get("all_scenes_pass_quality", True):
            for scene_num in sorted(scene_numbers):
                result = validate_scene(scenes_dir, scene_num, qa_config)
                scene_results.append({"scene": scene_num, **result})
                if not result["passed"]:
                    issues.append(f"Scene {scene_num} failed quality check")

    passed = len(issues) == 0
    return {"passed": passed, "issues": issues, "scene_results": scene_results}


# ---------------------------------------------------------------------------
# Per-clip review with LLM suggestions
# ---------------------------------------------------------------------------


def _get_clip_thumbnail_base64(clip_path: Path, frame_index: int = 0) -> str | None:
    """Extract a frame from a clip and return as base64 JPEG (for LLM context)."""
    try:
        import cv2
        import base64

        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            return None
        if frame_index < 0:
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_index = max(0, total - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return base64.b64encode(buf.tobytes()).decode("ascii")
    except (ImportError, Exception):
        return None


def _get_frame_hash(clip_path: Path, frame_index: int) -> str | None:
    """Get a perceptual hash of a frame for comparison."""
    try:
        import cv2
        import hashlib

        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            return None
        if frame_index < 0:
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_index = max(0, total - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        small = cv2.resize(frame, (64, 64))
        return hashlib.md5(small.tobytes()).hexdigest()
    except (ImportError, Exception):
        return None


def _load_clip_prompt(clip_path: Path) -> dict | None:
    """Try to load the scene prompt YAML that corresponds to a clip."""
    # Clip name like scene_1_clip_1.mp4 → scene_1_clip_1_prompt.yaml
    # Or scene_1.mp4 → scene_1_prompt.yaml
    name = clip_path.stem  # e.g. scene_1_clip_1
    # Look for prompt in the scenes dir (sibling or parent)
    clips_run_dir = clip_path.parent  # clips/<run_ts>/
    clips_dir = clips_run_dir.parent  # clips/
    ep_dir = clips_dir.parent  # episodes/<num>/
    scenes_dir = ep_dir / "scenes"

    # Try to match scene prompt by run_ts or latest
    run_ts = clips_run_dir.name
    scenes_run_dir = scenes_dir / run_ts
    if not scenes_run_dir.exists():
        # Try latest scenes dir
        if scenes_dir.exists():
            subdirs = sorted([d for d in scenes_dir.iterdir() if d.is_dir()], reverse=True)
            scenes_run_dir = subdirs[0] if subdirs else scenes_dir

    prompt_file = scenes_run_dir / f"{name}_prompt.yaml"
    if prompt_file.exists():
        try:
            return load_yaml(str(prompt_file))
        except Exception:
            pass

    # Try just the scene name (scene_1_prompt.yaml for scene_1_clip_1)
    match = re.match(r"(scene_\d+)", name)
    if match:
        scene_prompt = scenes_run_dir / f"{match.group(1)}_prompt.yaml"
        if scene_prompt.exists():
            try:
                return load_yaml(str(scene_prompt))
            except Exception:
                pass
    return None


def generate_clip_review(
    episode_number: int,
    story_slug: str | None,
    clips_run_ts: str | None = None,
    qa_config: dict | None = None,
) -> dict:
    """Generate a per-clip review report with quality checks and LLM suggestions.

    Returns a review report dict with per-clip entries including:
    - quality metrics and pass/fail
    - LLM-generated improvement suggestions
    - suggested improvement prompts for regeneration
    """
    if qa_config is None:
        qa_config = load_qa_config()

    ep_dir = episode_dir(episode_number, story_slug)
    clips_dir = ep_dir / "clips"

    # Find the clips run directory
    if clips_run_ts:
        clips_run_dir = clips_dir / clips_run_ts
    else:
        # Use SELECTED_CLIPS_DIR from env, or latest
        selected = os.environ.get("SELECTED_CLIPS_DIR")
        if selected:
            clips_run_dir = clips_dir / selected
        elif clips_dir.exists():
            subdirs = sorted([d for d in clips_dir.iterdir() if d.is_dir()], reverse=True)
            clips_run_dir = subdirs[0] if subdirs else clips_dir
        else:
            return {
                "passed": False,
                "issues": ["No clips directory found"],
                "clips": [],
                "run_ts": None,
            }

    if not clips_run_dir.exists():
        return {
            "passed": False,
            "issues": [f"Clips run directory not found: {clips_run_dir}"],
            "clips": [],
            "run_ts": clips_run_ts,
        }

    # Find all clip files (exclude segment files and regen files)
    clip_files = sorted([
        f for f in clips_run_dir.glob("*.mp4")
        if "_segment" not in f.name and ".regen" not in f.name
    ])

    if not clip_files:
        return {
            "passed": False,
            "issues": ["No clip files found"],
            "clips": [],
            "run_ts": clips_run_dir.name,
        }

    log.info(f"Reviewing {len(clip_files)} clips in {clips_run_dir}")

    # Run quality checks on each clip
    clip_reviews: list[dict] = []
    all_passed = True

    for clip_path in clip_files:
        log.info(f"  Evaluating: {clip_path.name}")
        result = validate_clip(clip_path, qa_config)
        clip_prompt = _load_clip_prompt(clip_path)

        review_entry: dict = {
            "name": clip_path.name,
            "passed": result["passed"],
            "issues": result["issues"],
            "metrics": result["metrics"],
            "prompt": clip_prompt.get("description") or clip_prompt.get("prompt", "") if clip_prompt else "",
            "suggestion": None,
            "improvement_prompt": None,
            "first_frame_hash": _get_frame_hash(clip_path, 0),
            "last_frame_hash": _get_frame_hash(clip_path, -1),
        }

        if not result["passed"]:
            all_passed = False

        clip_reviews.append(review_entry)

    # Run consistency checks between adjacent clips
    if len(clip_files) >= 2:
        consistency = validate_clip_consistency(clip_files, qa_config)
        if not consistency["passed"]:
            all_passed = False
            # Attach consistency issues to the relevant clips
            for issue in consistency["issues"]:
                match = re.search(r"Clip (\d+) -> (\d+)", issue)
                if match:
                    idx = int(match.group(2)) - 1  # Second clip in the pair
                    if 0 <= idx < len(clip_reviews):
                        clip_reviews[idx]["issues"].append(issue)
                        clip_reviews[idx]["passed"] = False

    # Use LLM to generate improvement suggestions for failed clips
    _generate_llm_suggestions(clip_reviews, qa_config)

    report = {
        "passed": all_passed,
        "issues": [] if all_passed else ["Some clips need attention"],
        "clips": clip_reviews,
        "run_ts": clips_run_dir.name,
        "total_clips": len(clip_files),
        "failed_clips": sum(1 for c in clip_reviews if not c["passed"]),
    }

    # Save the review report in quality/<run_ts>/ (separate from clips)
    quality_dir = ep_dir / "quality" / clips_run_dir.name
    quality_dir.mkdir(parents=True, exist_ok=True)

    report_path = quality_dir / "clip_review.yaml"
    save_yaml(report, str(report_path))
    
    import json
    json_report_path = quality_dir / "clip_review.json"
    with open(json_report_path, "w", encoding="utf-8") as jf:
        json.dump(report, jf, indent=2, ensure_ascii=False)
    
    log.info(f"Review report saved to {quality_dir}")

    return report


def _generate_llm_suggestions(clip_reviews: list[dict], qa_config: dict) -> None:
    """Use LLM to generate improvement suggestions for clips with issues."""
    try:
        from llm import call_agent, parse_yaml_response
    except ImportError:
        log.warning("LLM module not available, skipping suggestions")
        return

    clips_needing_review = [c for c in clip_reviews if not c["passed"]]
    if not clips_needing_review:
        log.info("All clips passed — no LLM suggestions needed")
        return

    log.info(f"Generating LLM suggestions for {len(clips_needing_review)} clips...")

    # Build a batch request for all failing clips
    clip_summaries = []
    for c in clips_needing_review:
        clip_summaries.append(
            f"- {c['name']}: issues={c['issues']}, metrics={c['metrics']}, "
            f"original_prompt=\"{c.get('prompt', 'N/A')}\""
        )

    user_message = f"""Review these video clips that failed quality checks. For each clip, provide:
1. A brief suggestion explaining what needs improvement
2. An improved prompt that could fix the issues when regenerating

IMPORTANT CONSTRAINTS:
- The first and last frames of each clip MUST remain the same after regeneration (they connect to neighboring clips)
- Keep improved prompts under 100 words
- Focus on fixing the specific issues identified
- Preserve the original scene intent and characters

## Clips needing review:
{chr(10).join(clip_summaries)}

Output ONLY valid YAML as a list:
```yaml
clips:
  - name: "<clip_name>"
    suggestion: "<brief explanation of what to improve>"
    improvement_prompt: "<improved prompt for regeneration>"
```
"""

    try:
        raw = call_agent("artist", user_message, max_tokens=4000)
        suggestions = parse_yaml_response(raw)

        suggestions_list = suggestions.get("clips", [])
        if not isinstance(suggestions_list, list):
            suggestions_list = []

        # Match suggestions back to clip reviews
        for suggestion in suggestions_list:
            name = suggestion.get("name", "")
            for review in clip_reviews:
                if review["name"] == name:
                    review["suggestion"] = suggestion.get("suggestion")
                    review["improvement_prompt"] = suggestion.get("improvement_prompt")
                    break

        log.info(f"LLM suggestions generated for {len(suggestions_list)} clips")
    except Exception as e:
        log.warning(f"LLM suggestion generation failed: {e}")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def print_report(result: dict, level: str):
    """Print a human-readable quality report."""
    # For clip review reports, show REVIEW instead of FAIL
    if result.get("clips") is not None:
        status = "PASS" if result["passed"] else "NEEDS REVIEW"
    else:
        status = "PASS" if result["passed"] else "FAIL"
    print(f"\n{'=' * 60}")
    print(f"  Quality Check [{level}]: {status}")
    print(f"{'=' * 60}")

    if result.get("metrics"):
        print("\n  Metrics:")
        for k, v in result["metrics"].items():
            print(f"    {k}: {v}")

    if result.get("issues"):
        print(f"\n  Issues ({len(result['issues'])}):")
        for issue in result["issues"]:
            print(f"    - {issue}")
    else:
        print("\n  No issues found.")

    print()


def main():
    parser = argparse.ArgumentParser(description="Validate video quality")
    parser.add_argument("--clip", type=str, help="Path to a single clip to validate")
    parser.add_argument("--scene", type=str, help="Path to scenes directory")
    parser.add_argument("--scene-number", type=int, help="Scene number to validate")
    parser.add_argument("--episode", type=int, help="Episode number to validate")
    parser.add_argument("--story", type=str, default=None, help="Story slug")
    parser.add_argument("--output", type=str, help="Save report to YAML file")
    parser.add_argument(
        "--review",
        action="store_true",
        help="Generate per-clip review report with LLM suggestions",
    )
    parser.add_argument(
        "--clips-run-ts",
        type=str,
        default=None,
        help="Specific clips run timestamp to review",
    )
    args = parser.parse_args()

    qa_config = load_qa_config()

    # Track whether this is a review mode (always exits 0 — informational only)
    is_review_mode = False

    if args.review and args.episode:
        is_review_mode = True
        # Per-clip review mode with LLM suggestions
        result = generate_clip_review(
            args.episode,
            args.story,
            clips_run_ts=args.clips_run_ts,
            qa_config=qa_config,
        )
        print_report(result, f"CLIP REVIEW: Episode {args.episode}")
        # Also print per-clip details
        for clip in result.get("clips", []):
            status = "PASS" if clip["passed"] else "REVIEW"
            print(f"  [{status}] {clip['name']}")
            if clip.get("issues"):
                for issue in clip["issues"]:
                    print(f"        Issue: {issue}")
            if clip.get("suggestion"):
                print(f"        Suggestion: {clip['suggestion']}")
            if clip.get("improvement_prompt"):
                print(f"        Improved prompt: {clip['improvement_prompt'][:100]}...")
    elif args.clip:
        result = validate_clip(Path(args.clip), qa_config)
        print_report(result, f"CLIP: {args.clip}")
    elif args.scene and args.scene_number:
        result = validate_scene(Path(args.scene), args.scene_number, qa_config)
        print_report(result, f"SCENE {args.scene_number}")
    elif args.episode:
        is_review_mode = True
        # When run as a pipeline step, validate clips (not final episode)
        result = generate_clip_review(
            args.episode,
            args.story,
            clips_run_ts=args.clips_run_ts,
            qa_config=qa_config,
        )
        print_report(result, f"EPISODE {args.episode} CLIPS")
    else:
        parser.print_help()
        sys.exit(1)

    # Save report if requested
    if args.output:
        save_yaml(result, args.output)
        log.info(f"Report saved to {args.output}")

    # Review mode always exits 0 — it's informational, not a gate.
    # The user reviews suggestions in the UI and decides what to regenerate.
    if is_review_mode:
        sys.exit(0)
    else:
        sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
