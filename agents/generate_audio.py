"""Generate Audio for Episode Clips

Generates real audio files (background music via MusicGen, narration via Bark TTS)
from the audio plan YAML produced by the sound-designer agent.

Modes:
- MusicGen (default): Generate only background music. Video clips keep their
  Seedance-generated narrative audio. Composition step mixes both channels.
- Bark TTS: Generate both narration AND music. Video clip audio is muted and
  replaced entirely with this step's output.

Usage:
    python agents/generate_audio.py --episode 1 --story my-story
    python agents/generate_audio.py --episode 1 --story my-story --model bark
    python agents/generate_audio.py --episode 1 --story my-story --music-only
"""

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

import argparse
import os
import sys
from pathlib import Path

from common import episode_dir, load_env, load_yaml, save_yaml, setup_logging

load_env()
log = setup_logging("generate_audio")

# Audio model registry
AUDIO_MODEL_REGISTRY = {
    "musicgen": "facebook/musicgen-medium",
    "musicgen-small": "facebook/musicgen-small",
    "musicgen-large": "facebook/musicgen-large",
    "bark": "suno/bark",
}


def resolve_audio_model(model_name: str) -> str:
    """Resolve short name to HuggingFace model ID."""
    if "/" in model_name and model_name.split("/")[0].lower() in ("huggingface", "hf"):
        model_name = "/".join(model_name.split("/")[1:])
    return AUDIO_MODEL_REGISTRY.get(model_name.lower(), model_name)


def generate_music(
    prompt: str,
    duration_seconds: float = 15.0,
    model: str = "facebook/musicgen-medium",
    output_path: Path | None = None,
) -> Path:
    """Generate background music using MusicGen via HuggingFace Inference API.

    Args:
        prompt: Music description (genre, mood, instruments, tempo).
        duration_seconds: Target duration.
        model: HuggingFace model ID.
        output_path: Where to save the WAV/MP3 file.

    Returns:
        Path to the generated audio file.
    """
    import requests

    api_token = os.getenv("HUGGINGFACE_API_TOKEN")
    if not api_token or api_token.startswith("hf_your_"):
        log.warning("No HUGGINGFACE_API_TOKEN. Running in dry-run mode.")
        return _dry_run_audio(output_path, "music")

    log.info(f"Generating music: model={model}, duration={duration_seconds}s")
    log.info(f"  Prompt: {prompt[:100]}...")

    try:
        # MusicGen uses the text-to-audio pipeline via raw Inference API
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        headers = {"Authorization": f"Bearer {api_token}"}
        payload = {"inputs": prompt}

        response = requests.post(api_url, headers=headers, json=payload, timeout=120)

        if response.status_code == 503:
            # Model is loading — retry once after waiting
            log.info("  Model is loading, waiting 30s and retrying...")
            import time

            time.sleep(30)
            response = requests.post(api_url, headers=headers, json=payload, timeout=120)

        if response.status_code != 200:
            raise RuntimeError(
                f"HuggingFace API returned {response.status_code}: {response.text[:200]}"
            )

        if output_path is None:
            output_path = Path("music_output.wav")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_bytes(response.content)
        log.info(f"Music saved: {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")
        return output_path

    except Exception as e:
        log.error(f"Music generation failed: {e}")
        raise


def generate_narration(
    text: str,
    voice_preset: str | None = None,
    model: str = "suno/bark",
    output_path: Path | None = None,
) -> Path:
    """Generate speech narration using Bark TTS via HuggingFace Inference API.

    Args:
        text: The text to speak.
        voice_preset: Optional voice preset for Bark (e.g. "v2/en_speaker_6").
        model: HuggingFace model ID.
        output_path: Where to save the WAV file.

    Returns:
        Path to the generated audio file.
    """
    import requests

    api_token = os.getenv("HUGGINGFACE_API_TOKEN")
    if not api_token or api_token.startswith("hf_your_"):
        log.warning("No HUGGINGFACE_API_TOKEN. Running in dry-run mode.")
        return _dry_run_audio(output_path, "narration")

    log.info(f"Generating narration: model={model}")
    log.info(f"  Text: {text[:80]}...")
    if voice_preset:
        log.info(f"  Voice preset: {voice_preset}")

    try:
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        headers = {"Authorization": f"Bearer {api_token}"}
        payload = {"inputs": text}

        response = requests.post(api_url, headers=headers, json=payload, timeout=120)

        if response.status_code == 503:
            log.info("  Model is loading, waiting 30s and retrying...")
            import time

            time.sleep(30)
            response = requests.post(api_url, headers=headers, json=payload, timeout=120)

        if response.status_code != 200:
            raise RuntimeError(
                f"HuggingFace API returned {response.status_code}: {response.text[:200]}"
            )

        if output_path is None:
            output_path = Path("narration_output.wav")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_bytes(response.content)
        log.info(f"Narration saved: {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")
        return output_path

    except Exception as e:
        log.error(f"Narration generation failed: {e}")
        raise


def _dry_run_audio(output_path: Path | None, kind: str) -> Path:
    """Create a placeholder file for testing without API access."""
    if output_path is None:
        output_path = Path(f"dry_run_{kind}.wav")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"DRY_RUN_PLACEHOLDER_{kind.upper()}")
    log.info(f"Dry-run {kind} output: {output_path}")
    return output_path


def generate_audio_from_plan(
    audio_plan: dict,
    output_dir: Path,
    model: str = "musicgen",
    music_only: bool = True,
) -> dict:
    """Generate real audio files from the LLM-produced audio plan.

    Args:
        audio_plan: The audio plan dict from sound-designer LLM.
        output_dir: Directory to save generated audio files.
        model: Audio model to use (musicgen or bark).
        music_only: If True, generate only background music (default for MusicGen).
                    If False, also generate narration (for Bark TTS mode).

    Returns:
        Manifest dict with paths to all generated audio files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    model_id = resolve_audio_model(model)
    is_bark = "bark" in model.lower()

    plan = audio_plan.get("audio_plan", audio_plan)
    scenes = plan.get("scenes", [])

    manifest = {
        "model": model_id,
        "mode": "full" if is_bark else "music_only",
        "mute_video_audio": is_bark,  # When Bark is used, mute video clip audio in composition
        "tracks": [],
    }

    # Generate background music per scene
    for scene in scenes:
        scene_num = scene.get("scene_number", 0)
        music = scene.get("music", {})
        time_range = scene.get("time_range", "")

        if music:
            # Build music generation prompt from plan details
            music_parts = []
            if music.get("track_description"):
                music_parts.append(music["track_description"])
            if music.get("mood"):
                music_parts.append(f"mood: {music['mood']}")
            if music.get("tempo"):
                music_parts.append(f"tempo: {music['tempo']}")
            if music.get("instruments"):
                music_parts.append(f"instruments: {', '.join(music['instruments'])}")
            if plan.get("music_style"):
                music_parts.append(f"style: {plan['music_style']}")

            music_prompt = ". ".join(music_parts) if music_parts else "ambient background music"

            music_path = output_dir / f"scene_{scene_num}_music.wav"
            try:
                generate_music(
                    prompt=music_prompt,
                    duration_seconds=20.0,  # Scene duration ~15-20s
                    model=model_id if not is_bark else "facebook/musicgen-medium",
                    output_path=music_path,
                )
                manifest["tracks"].append(
                    {
                        "type": "music",
                        "scene": scene_num,
                        "file": music_path.name,
                        "time_range": time_range,
                        "prompt": music_prompt,
                    }
                )
            except Exception as e:
                log.error(f"  Failed to generate music for scene {scene_num}: {e}")

        # Generate ambient sound if specified
        ambient = scene.get("ambient", {})
        if ambient and ambient.get("description"):
            ambient_path = output_dir / f"scene_{scene_num}_ambient.wav"
            try:
                generate_music(
                    prompt=f"ambient sound effects: {ambient['description']}",
                    duration_seconds=20.0,
                    model="facebook/musicgen-medium",
                    output_path=ambient_path,
                )
                manifest["tracks"].append(
                    {
                        "type": "ambient",
                        "scene": scene_num,
                        "file": ambient_path.name,
                        "time_range": time_range,
                    }
                )
            except Exception as e:
                log.error(f"  Failed to generate ambient for scene {scene_num}: {e}")

        # Generate narration (only in Bark TTS mode)
        if not music_only and is_bark:
            narrations = scene.get("narration", [])
            if isinstance(narrations, dict):
                narrations = [narrations]
            for idx, narr in enumerate(narrations):
                text = narr.get("line", "") or narr.get("text", "")
                if not text:
                    continue
                character = narr.get("character", "narrator")
                narr_path = output_dir / f"scene_{scene_num}_narration_{idx + 1}_{character}.wav"
                try:
                    generate_narration(
                        text=text,
                        voice_preset=narr.get("voice_preset"),
                        model=model_id,
                        output_path=narr_path,
                    )
                    manifest["tracks"].append(
                        {
                            "type": "narration",
                            "scene": scene_num,
                            "file": narr_path.name,
                            "character": character,
                            "text": text,
                            "timestamp": narr.get("timestamp", ""),
                        }
                    )
                except Exception as e:
                    log.error(f"  Failed to generate narration for scene {scene_num}: {e}")

    # Generate credits music if present
    credits_music = plan.get("credits_music", {})
    if credits_music and credits_music.get("description"):
        credits_path = output_dir / "credits_music.wav"
        try:
            generate_music(
                prompt=credits_music["description"],
                duration_seconds=credits_music.get("duration_seconds", 10),
                model="facebook/musicgen-medium",
                output_path=credits_path,
            )
            manifest["tracks"].append(
                {
                    "type": "credits",
                    "file": credits_path.name,
                }
            )
        except Exception as e:
            log.error(f"  Failed to generate credits music: {e}")

    # Save manifest
    save_yaml(manifest, output_dir / "audio_manifest.yaml")
    log.info(f"Audio generation complete: {len(manifest['tracks'])} tracks in {output_dir}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate audio for episode")
    parser.add_argument("--episode", type=int, required=True, help="Episode number")
    parser.add_argument("--story", type=str, required=True, help="Story slug")
    parser.add_argument("--model", type=str, default=None, help="Audio model (musicgen, bark)")
    parser.add_argument(
        "--music-only",
        action="store_true",
        default=False,
        help="Generate only background music (default for MusicGen)",
    )
    parser.add_argument(
        "--plan",
        type=str,
        default=None,
        help="Path to audio_plan.yaml (if not provided, uses latest)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (if not provided, creates timestamped subfolder)",
    )
    args = parser.parse_args()

    # Audio model from arg, env override (pipeline), env default, or hardcoded
    model = (
        args.model
        or os.environ.get("AUDIO_MODEL_OVERRIDE")
        or os.environ.get("AUDIO_MODEL")
        or "musicgen"
    )
    # Strip huggingface/ prefix if present from UI
    if model.startswith("huggingface/"):
        model = model[len("huggingface/") :]

    # Determine music-only mode
    is_bark = "bark" in model.lower()
    music_only = args.music_only or (not is_bark)  # MusicGen = music only; Bark = full audio

    log.info(f"Audio generation: model={model}, music_only={music_only}")

    # Find audio plan
    ep_dir = episode_dir(args.episode, args.story)
    if args.plan:
        plan_path = Path(args.plan)
    else:
        # Check for selected audio plan run (set by pipeline from step-runs)
        selected_audio_dir = os.environ.get("SELECTED_AUDIO_DIR")
        if selected_audio_dir:
            plan_path = ep_dir / "audio" / selected_audio_dir / "audio_plan.yaml"
        else:
            # Try root-level audio_plan.yaml first
            plan_path = ep_dir / "audio_plan.yaml"
            if not plan_path.exists():
                # Fallback: find the latest audio plan in audio/ subfolders
                audio_dir = ep_dir / "audio"
                if audio_dir.exists():
                    subdirs = sorted(
                        [
                            d
                            for d in audio_dir.iterdir()
                            if d.is_dir() and (d / "audio_plan.yaml").exists()
                        ],
                        key=lambda d: d.name,
                        reverse=True,
                    )
                    if subdirs:
                        plan_path = subdirs[0] / "audio_plan.yaml"
                        log.info(f"Using latest audio plan from: {subdirs[0].name}")

    if not plan_path.exists():
        log.error(f"Audio plan not found at {plan_path}. Run audio planning step first.")
        sys.exit(1)

    audio_plan = load_yaml(str(plan_path))

    # Output directory: use provided dir or create timestamped subfolder
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = ep_dir / "audio" / ts

    manifest = generate_audio_from_plan(
        audio_plan=audio_plan,
        output_dir=output_dir,
        model=model,
        music_only=music_only,
    )

    # Print summary
    print("--- Audio Generation Complete ---")
    print(f"Model: {resolve_audio_model(model)}")
    print(
        f"Mode: {'music only (video clips keep their narrative audio)' if music_only else 'full audio (video clip audio will be muted)'}"
    )
    print(f"Tracks generated: {len(manifest['tracks'])}")
    print(f"Output: {output_dir}")
    for track in manifest["tracks"]:
        print(f"  [{track['type']}] scene {track.get('scene', '-')}: {track['file']}")

    # Exit with error if no tracks were generated (so GUI shows failure)
    if len(manifest["tracks"]) == 0:
        log.error("No audio tracks were generated. Check API token and model availability.")
        sys.exit(1)


if __name__ == "__main__":
    main()
