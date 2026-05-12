"""Generate Video for a Scene

Calls HuggingFace models to generate video clips from scene prompts.
Supports both Inference API (cloud) and local diffusers pipeline.

Usage:
    python agents/generate_video.py --scene data/episodes/1/scenes/scene_1_prompt.yaml
    python agents/generate_video.py --scene <path> --model hunyuanvideo --quality high
    python agents/generate_video.py --scene <path> --local  # Use local GPU pipeline
"""

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

import argparse
import os
import sys
import time
from pathlib import Path

import yaml
from common import config_path, get_story_language, load_env, load_yaml, setup_logging

load_env()
log = setup_logging("generate_video")

# Model registry: maps short names to HuggingFace model IDs
MODEL_REGISTRY = {
    "hunyuanvideo": "tencent/HunyuanVideo",
    "cogvideox": "THUDM/CogVideoX-5b",
    "wan2.1": "Wan-AI/Wan2.1-T2V-14B",
    "animatediff-lightning": "ByteDance/AnimateDiff-Lightning",
    "seedance2.0": "dreamina-seedance-2-0-260128",
    "text-to-video": "ali-vilab/text-to-video-ms-1.7b",
}

# Models that use BytePlus Ark API instead of HuggingFace
BYTEPLUS_MODELS = {"seedance2.0", "dreamina-seedance-2-0-260128"}

# Quality presets: generation parameters per quality level
QUALITY_PRESETS = {
    "draft": {"num_inference_steps": 20, "guidance_scale": 6.0},
    "standard": {"num_inference_steps": 30, "guidance_scale": 7.5},
    "high": {"num_inference_steps": 50, "guidance_scale": 9.0},
}


def load_scene_prompt(path: str) -> dict:
    """Load scene prompt specification."""
    return load_yaml(path)


def load_config() -> dict:
    """Load video generation config."""
    return load_yaml(config_path("video_generation.yaml"))


def resolve_model_id(model_name: str) -> str:
    """Resolve short model name to full model ID."""
    # Strip provider prefix (e.g. "huggingface/", "byteplus/") if present
    if "/" in model_name and model_name.split("/")[0].lower() in (
        "huggingface",
        "hf",
        "atlascloud",
        "byteplus",
    ):
        model_name = "/".join(model_name.split("/")[1:])
    return MODEL_REGISTRY.get(model_name, model_name)


# Aspect ratio → (width, height) mapping at 720p base
ASPECT_RATIO_MAP = {
    "9:16": (720, 1280),
    "16:9": (1280, 720),
    "1:1": (720, 720),
    "4:3": (960, 720),
    "3:4": (720, 960),
}


def get_video_dimensions() -> tuple[int, int, str]:
    """Get video width, height, and aspect ratio from env override or config."""
    aspect_ratio = os.environ.get("VIDEO_ASPECT_RATIO")
    if not aspect_ratio:
        gen_config = load_config().get("generation", {})
        aspect_ratio = gen_config.get("aspect_ratio", "9:16")
    width, height = ASPECT_RATIO_MAP.get(aspect_ratio, (720, 1280))
    return width, height, aspect_ratio


def generate_video_cloud(
    prompt: dict,
    model: str,
    quality: str,
    seed: int | None = None,
    output_path: Path | None = None,
) -> Path:
    """
    Generate video using HuggingFace Inference API (cloud).
    Supports image-to-video continuity via reference_video field.
    """
    from huggingface_hub import InferenceClient

    api_token = os.getenv("HUGGINGFACE_API_TOKEN")
    if not api_token or api_token.startswith("hf_your_"):
        raise RuntimeError("HUGGINGFACE_API_TOKEN not configured in config/.env")

    model_id = resolve_model_id(model)
    params = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["standard"])

    # Build the text prompt from scene specification
    text_prompt = _build_text_prompt(prompt)
    negative_prompt = prompt.get("negative_prompt", "blurry, low quality, distorted, watermark")

    log.info(f"Calling Inference API: model={model_id}, quality={quality}")
    log.info(f"  Prompt: {text_prompt}")

    client = InferenceClient(token=api_token)

    # Continuity: use last frame image only (NOT full video — that causes the model
    # to waste ~50% of generation reproducing the previous clip)
    reference_image = None
    if prompt.get("reference_video"):
        ref_path = Path(prompt["reference_video"])
        if ref_path.exists():
            reference_image = _get_continuity_reference(
                ref_path
            )  # Last frame(s) for image_to_video

    # Video dimensions from aspect ratio selection
    width, height, aspect_ratio = get_video_dimensions()
    orientation = "vertical" if height > width else ("horizontal" if width > height else "square")
    text_prompt = f"[{width}x{height}, {aspect_ratio} {orientation} video] {text_prompt}"

    # Prefer image_to_video (last frame as starting point) → text_to_video fallback
    if reference_image:
        from PIL import Image

        ref_img = Image.open(reference_image)
        video_bytes = client.image_to_video(
            image=ref_img,
            prompt=text_prompt,
            model=model_id,
            num_inference_steps=params["num_inference_steps"],
            guidance_scale=params["guidance_scale"],
            negative_prompt=negative_prompt,
            seed=seed,
        )
        log.info("  Used image_to_video with last frame for continuation")
    else:
        video_bytes = client.text_to_video(
            prompt=text_prompt,
            model=model_id,
            num_inference_steps=params["num_inference_steps"],
            guidance_scale=params["guidance_scale"],
            negative_prompt=negative_prompt,
            seed=seed,
        )
        log.info("  Used text_to_video (no reference available)")

    # Save output
    if output_path is None:
        output_path = Path("output.mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(video_bytes)

    log.info(f"Video saved: {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")
    return output_path


def generate_video_byteplus(
    prompt: dict,
    model: str,
    quality: str,
    seed: int | None = None,
    output_path: Path | None = None,
) -> Path:
    """
    Generate video using BytePlus Ark API (Seedance 2.0).

    Uses a task-based pattern: POST to create task, then poll for completion.
    Supports reference images/videos for continuity.
    """
    import requests as req

    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        raise RuntimeError("ARK_API_KEY not configured in config/.env")

    model_id = resolve_model_id(model)

    # Signal to _build_text_prompt the reference mode (set by caller via _reference_mode key)
    # Default is "image" since we use last-frame extraction for continuity
    if not prompt.get("_reference_mode"):
        prompt["_reference_mode"] = "image"

    gen_config = load_config().get("generation", {})
    # Prefer duration from the clip prompt YAML, then config, then default 5s
    clip_duration = prompt.get("duration_seconds") or gen_config.get("clip_duration_seconds", 10)

    log.info(
        f"Calling BytePlus Ark API: model={model_id}, quality={quality}, duration={clip_duration}s"
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # Read last-frame reference for continuity
    # Prefer URL (from API's return_last_frame), fall back to local file (base64)
    ref_frame_b64 = None
    ref_frame_url = None
    if prompt.get("_last_frame_url"):
        ref_frame_url = prompt["_last_frame_url"]
    elif prompt.get("reference_video"):
        ref_path = Path(prompt["reference_video"])
        if ref_path.exists() and ref_path.stat().st_size > 100:
            try:
                import base64

                ref_frame_b64 = base64.b64encode(ref_path.read_bytes()).decode("utf-8")
            except Exception as e:
                log.warning(f"  Could not read last-frame reference: {e}")

    # Reference video URL for regeneration (original clip's API URL)
    ref_video_url = prompt.get("_reference_video_url")

    # Build content array with @-tagged references for Seedance
    # Track image and audio indices for @Image1, @Image2, @Audio1, @Audio2 tags
    image_idx = 0
    audio_idx = 0
    image_tag_map: dict[str, str] = {}  # name -> @ImageN tag
    audio_tag_map: dict[str, str] = {}  # name -> @AudioN tag

    content = []

    # Pass character avatar images as reference_image for visual consistency
    avatar_names = []
    for avatar in prompt.get("_character_avatars", []):
        avatar_file = Path(avatar["path"])
        if avatar_file.exists():
            try:
                import base64 as _b64

                avatar_b64 = _b64.b64encode(avatar_file.read_bytes()).decode("utf-8")
                image_idx += 1
                tag = f"@Image{image_idx}"
                image_tag_map[avatar["name"]] = tag
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{avatar_b64}"},
                        "role": "reference_image",
                    }
                )
                avatar_names.append(avatar["name"])
            except Exception as e:
                log.warning(f"  Could not load avatar for {avatar['name']}: {e}")
    if avatar_names:
        log.info(f"  Passing character avatar(s) as reference_image: {', '.join(avatar_names)}")

    # Pass last frame of previous clip as first_frame for continuity
    if ref_frame_url:
        image_idx += 1
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": ref_frame_url},
                "role": "first_frame",
                "_is_last_frame": True,
            }
        )
        log.info(f"  Passing last frame URL as first_frame for seamless continuation")
    elif ref_frame_b64:
        image_idx += 1
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{ref_frame_b64}"},
                "role": "first_frame",
                "_is_last_frame": True,
            }
        )
        log.info(f"  Passing last frame (base64) as first_frame for seamless continuation")

    # Pass original video URL as reference_video for regeneration
    if ref_video_url:
        content.append(
            {
                "type": "video_url",
                "video_url": {"url": ref_video_url},
                "role": "reference_video",
                "_is_reference_video": True,  # Internal marker for retry logic
            }
        )
        log.info(f"  Passing original video as reference_video: {ref_video_url[:80]}...")

    # Pass character voice references as reference_audio (asset-id based)
    voice_refs = prompt.get("_voice_refs", [])
    for vr in voice_refs:
        audio_idx += 1
        tag = f"@Audio{audio_idx}"
        audio_tag_map[vr["name"]] = tag
        content.append(
            {
                "type": "audio_url",
                "audio_url": {
                    "url": vr["url"],  # e.g. "asset://voice_xiao_xi"
                },
                "role": "reference_audio",
            }
        )
    if voice_refs:
        log.info(
            f"  Passing {len(voice_refs)} voice ref(s) as reference_audio: {[vr['name'] for vr in voice_refs]}"
        )

    # Store tag maps in prompt for _build_text_prompt to use
    if image_tag_map:
        prompt["_image_tags"] = image_tag_map
    if audio_tag_map:
        prompt["_audio_tags"] = audio_tag_map

    # Build text prompt AFTER setting up tag maps so it can reference @Image/@Audio
    text_prompt = _build_text_prompt(prompt)
    log.info(f"  Prompt: {text_prompt[:500]}")

    # Insert text as first content item
    content.insert(
        0,
        {
            "type": "text",
            "text": text_prompt,
        },
    )

    # Enable audio generation when voice refs are provided or config says so
    gen_config_audio = gen_config.get("generate_audio", False)
    enable_audio = gen_config_audio or bool(voice_refs)

    data = {
        "model": model_id,
        "content": content,
        "duration": clip_duration,
        "ratio": get_video_dimensions()[2],  # Aspect ratio string e.g. "9:16"
        "generate_audio": enable_audio,
        "return_last_frame": True,
    }

    if enable_audio:
        log.info(
            f"  Audio generation enabled (voice_refs={len(voice_refs)}, config={gen_config_audio})"
        )

    # Submit generation task
    task_url = "https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks"

    # Check for stop signal RIGHT BEFORE the expensive API call (prevents token waste)
    _run_id = os.environ.get("GENERATION_RUN_ID")
    if _run_id:
        _stop_file = Path(".stop") / f"{_run_id}.stop"
        if _stop_file.exists():
            log.info("Stop signal detected before API submission. Aborting to save tokens.")
            _stop_file.unlink(missing_ok=True)
            raise RuntimeError("Generation stopped by user (before submission)")

    # Retry strategy for BytePlus 400 errors:
    # 1. Strip audio_url (asset service may not be activated), keep image references
    # 2. Strip last-frame reference image, keep avatar images only
    # 3. Text-only as last resort

    # Strip internal markers before sending (BytePlus doesn't understand these)
    for item in data["content"]:
        item.pop("_is_last_frame", None)
        item.pop("_is_reference_video", None)

    resp = req.post(task_url, headers=headers, json=data, timeout=60)

    if resp.status_code == 400:
        error_body = resp.text
        log.warning(f"  BytePlus rejected request (400): {error_body[:300]}")

        # Retry 1: Strip audio references, keep image references
        has_audio = any(c.get("type") == "audio_url" for c in data["content"])
        if has_audio:
            log.info("  Retry 1: Stripping audio references, keeping image references...")
            data["content"] = [c for c in data["content"] if c.get("type") != "audio_url"]
            data["generate_audio"] = gen_config_audio
            resp = req.post(task_url, headers=headers, json=data, timeout=60)

        # Retry 2: Strip reference_video, keep images
        if resp.status_code == 400:
            has_video_ref = any(c.get("type") == "video_url" for c in data["content"])
            if has_video_ref:
                error_body = resp.text
                log.warning(f"  BytePlus still rejected (400): {error_body[:300]}")
                log.info("  Retry 2: Stripping reference_video, keeping image references...")
                data["content"] = [c for c in data["content"] if c.get("type") != "video_url"]
                resp = req.post(task_url, headers=headers, json=data, timeout=60)

        # Retry 3: Strip last-frame image, keep only avatar images
        if resp.status_code == 400:
            # Count image references — if more than just avatars, strip the last-frame one
            images = [c for c in data["content"] if c.get("type") == "image_url"]
            if len(images) > len(avatar_names):
                error_body = resp.text
                log.warning(f"  BytePlus still rejected (400): {error_body[:300]}")
                log.info("  Retry 3: Stripping last-frame reference, keeping avatar images only...")
                # Keep only the first N images (avatars) and remove the last-frame one
                kept_images = 0
                new_content = []
                for c in data["content"]:
                    if c.get("type") == "image_url":
                        if kept_images < len(avatar_names):
                            new_content.append(c)
                            kept_images += 1
                        # Skip additional images (last-frame)
                    else:
                        new_content.append(c)
                data["content"] = new_content
                resp = req.post(task_url, headers=headers, json=data, timeout=60)

        # Retry 4: Text-only (no references at all)
        if resp.status_code == 400 and len(data["content"]) > 1:
            error_body = resp.text
            log.warning(f"  BytePlus still rejected (400): {error_body[:300]}")
            log.info("  Retry 4: Text-only (no references)...")
            data["content"] = [c for c in data["content"] if c.get("type") == "text"]
            data["generate_audio"] = gen_config_audio
            resp = req.post(task_url, headers=headers, json=data, timeout=60)

    if resp.status_code != 200:
        error_body = resp.text
        raise RuntimeError(f"BytePlus API error ({resp.status_code}): {error_body[:500]}")

    result = resp.json()

    task_id = result.get("data", {}).get("id") or result.get("id")
    if not task_id:
        raise RuntimeError(f"BytePlus API did not return a task ID: {result}")

    log.info(f"  Task submitted: {task_id}")

    # Poll for completion
    poll_url = (
        f"https://ark.ap-southeast.bytepluses.com/api/v3/contents/generations/tasks/{task_id}"
    )
    max_wait = 300  # 5 minutes max
    elapsed = 0
    poll_interval = 5  # 5s between polls to avoid connection pressure
    max_poll_retries = 3  # Retries per poll attempt for transient errors

    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        # Check for stop signal during polling
        _run_id = os.environ.get("GENERATION_RUN_ID")
        if _run_id:
            _stop_file = Path(".stop") / f"{_run_id}.stop"
            if _stop_file.exists():
                log.info(f"Stop signal detected during polling. Aborting generation.")
                _stop_file.unlink(missing_ok=True)
                raise RuntimeError("Generation stopped by user")

        # Retry logic for transient SSL/connection errors
        poll_result = None
        for retry in range(max_poll_retries):
            try:
                poll_resp = req.get(poll_url, headers=headers, timeout=30)
                poll_resp.raise_for_status()
                poll_result = poll_resp.json()
                break
            except (req.exceptions.SSLError, req.exceptions.ConnectionError) as e:
                if retry < max_poll_retries - 1:
                    wait = (retry + 1) * 2
                    log.warning(
                        f"  Poll retry {retry + 1}/{max_poll_retries} after SSL/connection error, waiting {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"BytePlus poll failed after {max_poll_retries} retries: {e}"
                    ) from e

        if poll_result is None:
            continue

        status = (
            poll_result.get("data", {}).get("status", "") or poll_result.get("status", "")
        ).lower()

        if status in ("completed", "succeeded", "success"):
            # Extract video URL from response
            # BytePlus response can be: {data: {content: {video_url: "..."}}}
            # or flat: {content: {video_url: "..."}} or {data: {outputs: [...]}}
            video_url = None

            # Try nested: data.content.video_url
            video_url = video_url or poll_result.get("data", {}).get("content", {}).get("video_url")
            # Try flat: content.video_url
            video_url = video_url or poll_result.get("content", {}).get("video_url")
            # Try data.video_url
            video_url = video_url or poll_result.get("data", {}).get("video_url")
            # Try data.outputs[0]
            if not video_url:
                outputs = poll_result.get("data", {}).get("outputs", [])
                if outputs:
                    video_url = (
                        outputs[0] if isinstance(outputs[0], str) else outputs[0].get("url", "")
                    )

            if not video_url:
                raise RuntimeError(f"BytePlus returned success but no video output: {poll_result}")

            log.info(f"  Video generated in {elapsed}s, downloading...")

            # Download video
            video_resp = req.get(video_url, timeout=120)
            video_resp.raise_for_status()

            if output_path is None:
                output_path = Path("output.mp4")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(video_resp.content)

            log.info(f"Video saved: {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")

            # Save the BytePlus video URL for use as reference in next clip
            url_file = output_path.parent / f"{output_path.stem}.url"
            url_file.write_text(video_url, encoding="utf-8")

            # Extract and save last_frame_url (from return_last_frame=True)
            last_frame_url = (
                poll_result.get("data", {}).get("content", {}).get("last_frame_url")
                or poll_result.get("content", {}).get("last_frame_url")
                or poll_result.get("data", {}).get("last_frame_url")
            )
            if last_frame_url:
                lf_file = output_path.parent / f"{output_path.stem}_last_frame_url.txt"
                lf_file.write_text(last_frame_url, encoding="utf-8")
                log.info(f"  Last frame URL saved for continuity: {lf_file.name}")

            return output_path
        elif status in ("failed", "error"):
            error_msg = poll_result.get("data", {}).get("error", "Unknown error")
            raise RuntimeError(f"BytePlus generation failed: {error_msg}")
        else:
            if elapsed % 15 == 0:
                log.info(f"  Still processing... ({elapsed}s elapsed, status={status})")

    raise RuntimeError(f"BytePlus generation timed out after {max_wait}s")


def generate_video_local(
    prompt: dict,
    model: str,
    quality: str,
    seed: int | None = None,
    output_path: Path | None = None,
) -> Path:
    """
    Generate video using local diffusers pipeline (requires GPU).

    Args:
        prompt: Scene prompt dict.
        model: Model short name or full HuggingFace model ID.
        quality: Quality preset.
        seed: Random seed.
        output_path: Where to save the output video.

    Returns:
        Path to the generated video file.
    """
    import torch
    from diffusers.utils import export_to_video

    model_id = resolve_model_id(model)
    params = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["standard"])
    text_prompt = _build_text_prompt(prompt)
    negative_prompt = prompt.get("negative_prompt", "blurry, low quality, distorted, watermark")

    log.info(f"Loading local pipeline: {model_id}")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    if device == "cpu":
        log.warning("No CUDA GPU detected. Generation will be very slow.")

    # Video dimensions from aspect ratio selection
    width, height, aspect_ratio = get_video_dimensions()
    gen_config = load_config().get("generation", {})
    fps = gen_config.get("fps", 24)
    # Prefer duration from the clip prompt YAML, then config, then default 5s
    clip_duration = prompt.get("duration_seconds") or gen_config.get("clip_duration_seconds", 5)

    generator = torch.Generator(device=device)
    if seed is not None:
        generator = generator.manual_seed(seed)

    # Include resolution hint in prompt text
    orientation = "vertical" if height > width else ("horizontal" if width > height else "square")
    text_prompt = f"[{width}x{height}, {aspect_ratio} {orientation} video] {text_prompt}"

    # --- AnimateDiff-Lightning special pipeline ---
    is_animatediff = "animatediff-lightning" in model.lower() or "AnimateDiff-Lightning" in model_id

    if is_animatediff:
        from diffusers import AnimateDiffPipeline, EulerDiscreteScheduler, MotionAdapter
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file

        # Select step count based on quality
        step_map = {"draft": 4, "standard": 4, "high": 8}
        step = step_map.get(quality, 4)
        ckpt = f"animatediff_lightning_{step}step_diffusers.safetensors"
        base_model = "emilianJR/epiCRealism"  # Base model for AnimateDiff

        log.info(f"  AnimateDiff-Lightning: steps={step}, base={base_model}")
        adapter = MotionAdapter().to(device, dtype)
        adapter.load_state_dict(load_file(hf_hub_download(model_id, ckpt), device=device))
        pipe = AnimateDiffPipeline.from_pretrained(
            base_model, motion_adapter=adapter, torch_dtype=dtype
        ).to(device)
        pipe.scheduler = EulerDiscreteScheduler.from_config(
            pipe.scheduler.config, timestep_spacing="trailing", beta_schedule="linear"
        )

        log.info(
            f"Generating video locally (AnimateDiff): quality={quality}, seed={seed}, {width}x{height}"
        )
        result = pipe(
            prompt=text_prompt,
            negative_prompt=negative_prompt,
            guidance_scale=1.0,  # AnimateDiff-Lightning uses low guidance
            num_inference_steps=step,
            generator=generator,
            num_frames=fps * clip_duration,
            height=height,
            width=width,
        )
    elif "CogVideoX" in model_id or "cogvideox" in model.lower():
        # --- CogVideoX pipeline (THUDM/CogVideoX-5b) ---
        from diffusers import CogVideoXPipeline

        log.info(f"  CogVideoX local pipeline: {model_id}")
        pipe = CogVideoXPipeline.from_pretrained(model_id, torch_dtype=dtype)
        pipe = pipe.to(device)
        pipe.enable_model_cpu_offload()

        num_frames = min(fps * clip_duration, 49)  # CogVideoX max 49 frames

        log.info(
            f"Generating video locally (CogVideoX): quality={quality}, seed={seed}, {width}x{height}"
        )
        result = pipe(
            prompt=text_prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=params["num_inference_steps"],
            guidance_scale=params["guidance_scale"],
            generator=generator,
            num_frames=num_frames,
            height=height,
            width=width,
        )

    elif "HunyuanVideo" in model_id or "hunyuanvideo" in model.lower():
        # --- HunyuanVideo pipeline (tencent/HunyuanVideo) ---
        from diffusers import HunyuanVideoPipeline

        log.info(f"  HunyuanVideo local pipeline: {model_id}")
        pipe = HunyuanVideoPipeline.from_pretrained(model_id, torch_dtype=dtype)
        pipe = pipe.to(device)
        pipe.enable_model_cpu_offload()

        num_frames = fps * clip_duration

        log.info(
            f"Generating video locally (HunyuanVideo): quality={quality}, seed={seed}, {width}x{height}"
        )
        result = pipe(
            prompt=text_prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=params["num_inference_steps"],
            guidance_scale=params["guidance_scale"],
            generator=generator,
            num_frames=num_frames,
            height=height,
            width=width,
        )

    elif "Wan2.1" in model_id or "wan2.1" in model.lower():
        # --- Wan 2.1 T2V pipeline (Wan-AI/Wan2.1-T2V-14B) ---
        from diffusers import WanPipeline

        log.info(f"  Wan 2.1 local pipeline: {model_id}")
        pipe = WanPipeline.from_pretrained(model_id, torch_dtype=dtype)
        pipe = pipe.to(device)
        pipe.enable_model_cpu_offload()

        num_frames = fps * clip_duration

        log.info(
            f"Generating video locally (Wan 2.1): quality={quality}, seed={seed}, {width}x{height}"
        )
        result = pipe(
            prompt=text_prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=params["num_inference_steps"],
            guidance_scale=params["guidance_scale"],
            generator=generator,
            num_frames=num_frames,
            height=height,
            width=width,
        )

    elif "text-to-video" in model.lower() or "ali-vilab" in model_id.lower():
        # --- ModelScope text-to-video (ali-vilab/text-to-video-ms-1.7b) ---
        from diffusers import TextToVideoSDPipeline

        log.info(f"  TextToVideoSD local pipeline: {model_id}")
        pipe = TextToVideoSDPipeline.from_pretrained(model_id, torch_dtype=dtype)
        pipe = pipe.to(device)
        pipe.enable_model_cpu_offload()

        num_frames = min(fps * clip_duration, 24)  # ModelScope works best with shorter clips

        log.info(
            f"Generating video locally (TextToVideoSD): quality={quality}, seed={seed}, {width}x{height}"
        )
        result = pipe(
            prompt=text_prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=params["num_inference_steps"],
            guidance_scale=params["guidance_scale"],
            generator=generator,
            num_frames=num_frames,
            height=height,
            width=width,
        )

    else:
        # --- Generic diffusers pipeline fallback ---
        from diffusers import DiffusionPipeline

        log.info(f"  Generic diffusers pipeline: {model_id}")
        pipe = DiffusionPipeline.from_pretrained(model_id, torch_dtype=dtype)
        pipe = pipe.to(device)

        # Continuity fallback chain for local gen
        conditioning_frames = None
        if prompt.get("reference_video"):
            ref_path = Path(prompt["reference_video"])
            if ref_path.exists():
                conditioning_frames = _get_continuity_frames_for_local(ref_path, device, torch)

        log.info(f"Generating video locally: quality={quality}, seed={seed}, {width}x{height}")

        pipe_kwargs = {
            "prompt": text_prompt,
            "negative_prompt": negative_prompt,
            "num_inference_steps": params["num_inference_steps"],
            "guidance_scale": params["guidance_scale"],
            "generator": generator,
            "num_frames": fps * clip_duration,
            "height": height,
            "width": width,
        }

        # Pass conditioning frames if the pipeline supports it
        if conditioning_frames is not None:
            pipe_kwargs["conditioning_frames"] = conditioning_frames

        result = pipe(**pipe_kwargs)

    if output_path is None:
        output_path = Path("output.mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_to_video(result.frames[0], str(output_path), fps=fps)

    log.info(f"Video saved: {output_path} ({output_path.stat().st_size / 1024:.1f} KB)")
    return output_path


def _save_enhanced_prompt(prompt: dict, clip_path: Path, suffix: str = "") -> Path | None:
    """Save the enhanced LLM prompt as YAML next to the clip file.

    Args:
        prompt: The enhanced prompt dict.
        clip_path: Path to the clip file (e.g. scene_1_clip_1.mp4).
        suffix: Optional suffix for regen prompts (e.g. '.regen').

    Returns the path to the saved YAML, or None on failure.
    """
    try:
        # Filter out internal/binary fields
        saveable = {
            k: v
            for k, v in prompt.items()
            if not k.startswith("_") and k != "reference_video" and not isinstance(v, bytes)
        }
        yaml_name = f"{clip_path.stem}{suffix}_enhanced_prompt.yaml"
        yaml_path = clip_path.parent / yaml_name
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(saveable, f, default_flow_style=False, allow_unicode=True)
        log.info(f"  Enhanced prompt saved: {yaml_path.name}")
        return yaml_path
    except Exception as e:
        log.warning(f"  Failed to save enhanced prompt: {e}")
        return None


def generate_video(
    prompt: dict,
    model: str,
    quality: str,
    seed: int | None = None,
    output_path: Path | None = None,
    *,
    local: bool = False,
    enhance: bool = True,
) -> Path:
    """
    Generate video -- dispatches to cloud or local backend.

    Falls back to dry-run mode if no API token is configured and not running locally.
    Uses @artist agent to enhance prompts before generation if enhance=True.
    """
    # Enhance prompt with artist agent LLM
    if enhance:
        prompt = enhance_prompt_with_llm(prompt)

    # Save enhanced prompt as YAML next to the output clip
    if output_path:
        _save_enhanced_prompt(prompt, Path(output_path))

    # AnimateDiff-Lightning is local-only (no cloud API endpoint)
    model_id = resolve_model_id(model)
    if "AnimateDiff-Lightning" in model_id or "animatediff-lightning" in model.lower():
        if not local:
            log.info("AnimateDiff-Lightning is local-only, switching to local execution")
        local = True

    # Seedance 2.0 uses BytePlus Ark API
    if model.lower() in BYTEPLUS_MODELS or model_id in BYTEPLUS_MODELS:
        api_key = os.getenv("ARK_API_KEY")
        if not api_key:
            log.warning("No ARK_API_KEY. Running in dry-run mode.")
            return _dry_run(prompt, output_path)
        return generate_video_byteplus(prompt, model, quality, seed, output_path)

    if local:
        return generate_video_local(prompt, model, quality, seed, output_path)

    # Check for API token
    api_token = os.getenv("HUGGINGFACE_API_TOKEN")
    if not api_token or api_token.startswith("hf_your_"):
        log.warning("No HUGGINGFACE_API_TOKEN. Running in dry-run mode.")
        return _dry_run(prompt, output_path)

    return generate_video_cloud(prompt, model, quality, seed, output_path)


def _build_text_prompt(prompt: dict) -> str:
    """Build a structured text prompt with clearly separated sections.

    Sections:
      [Instruction] — How to handle reference image/video continuity
      [Memory]      — Previous clip context (NOT to be regenerated)
      [Content]     — The actual scene to generate (this is the MAIN part)
      [Characters]  — Visual appearance and voice references
      [Location]    — Environment and setting details
      [Rules]       — Quality, style, and physics constraints
    """
    lang = os.environ.get("CONTENT_LANGUAGE", "en")
    sections = []

    # Section names follow story language
    if lang == "zh":
        SEC_INSTRUCTION = "指令"
        SEC_MEMORY = "记忆"
        SEC_CONTENT = "内容"
        SEC_CHARACTERS = "角色"
        SEC_LOCATION = "场景"
        SEC_RULES = "规则"
        SEC_SPEECH = "台词"
    else:
        SEC_INSTRUCTION = "Instruction"
        SEC_MEMORY = "Memory"
        SEC_CONTENT = "Content"
        SEC_CHARACTERS = "Characters"
        SEC_LOCATION = "Location"
        SEC_RULES = "Rules"
        SEC_SPEECH = "Speech"

    # ── [Instruction] ── Reference image instructions
    has_ref = prompt.get("reference_video") and Path(prompt["reference_video"]).exists()
    has_avatars = bool(prompt.get("_character_avatars"))
    instr_parts = []

    # Character avatar reference instruction (with @Image/@Audio tags for Seedance)
    image_tags = prompt.get("_image_tags", {})
    audio_tags = prompt.get("_audio_tags", {})
    if has_avatars:
        avatar_names = [a["name"] for a in prompt["_character_avatars"] if Path(a["path"]).exists()]
        if avatar_names:
            # Build tag-based character references
            tagged_chars = []
            for name in avatar_names:
                parts = []
                if name in image_tags:
                    parts.append(image_tags[name])
                if name in audio_tags:
                    parts.append(audio_tags[name])
                if parts:
                    tagged_chars.append(f"{name}({'/'.join(parts)})")
                else:
                    tagged_chars.append(name)

            if lang == "zh":
                instr_parts.append(
                    f"参考素材中包含角色设定图和语音（{', '.join(tagged_chars)}）。"
                    f"视频中的角色外观（发型、服装、体型、配饰）必须与角色设定图保持一致。"
                )
                if audio_tags:
                    voice_instructions = []
                    for name in avatar_names:
                        if name in audio_tags:
                            voice_instructions.append(f"{name}的语音使用{audio_tags[name]}作为参考")
                    if voice_instructions:
                        instr_parts.append(f"角色语音驱动：{'，'.join(voice_instructions)}。")
            else:
                instr_parts.append(
                    f"Reference assets include character designs and voices ({', '.join(tagged_chars)}). "
                    f"Characters in the video MUST match these designs (hair, clothing, build, accessories)."
                )
                if audio_tags:
                    voice_instructions = []
                    for name in avatar_names:
                        if name in audio_tags:
                            voice_instructions.append(
                                f"{name} speaks matching the voice track from {audio_tags[name]}"
                            )
                    if voice_instructions:
                        instr_parts.append(f"Voice drive: {', '.join(voice_instructions)}.")

    # Continuity last-frame reference instruction
    if has_ref:
        ref_mode = prompt.get("_reference_mode", "video")
        if lang == "zh":
            if ref_mode == "image":
                instr_parts.append(
                    "参考图片中还包含上一个片段的最后一帧。"
                    "第一帧必须严格复制该参考图片的画面：相同的角色位置、姿势、表情、背景、光线、色调。"
                    "从第二帧开始再进行新的动作。不要跳过任何中间状态。"
                )
            else:
                instr_parts.append(
                    "第一帧必须严格复制参考视频的最后一帧：相同的角色位置、姿势、手势、表情、背景、光线、色调。"
                    "角色不能突然改变位置或动作——新动作必须从参考视频的最后状态平滑过渡。"
                    "不要重复参考视频的内容，只生成新内容。"
                )
        else:
            if ref_mode == "image":
                instr_parts.append(
                    "Reference images also include the last frame of the previous clip. "
                    "The FIRST FRAME of this clip must be a near-exact copy of that reference image: "
                    "same character positions, poses, expressions, background, lighting, and color tone. "
                    "New action begins only from the SECOND frame onward. Do NOT skip or jump to a different state."
                )
            else:
                instr_parts.append(
                    "The FIRST FRAME must be a near-exact copy of the last frame of the reference video: "
                    "same character positions, poses, gestures, expressions, background, lighting, and color tone. "
                    "The character must NOT suddenly change position or action — new motion must smoothly continue from the reference video's ending state. "
                    "Do NOT replay any reference content. Generate only NEW continuation."
                )

    if instr_parts:
        sections.append(f"[{SEC_INSTRUCTION}]\n" + "\n".join(instr_parts))

    # ── [Memory] ── Previous clip context (reference only, NOT to be recreated)
    # Only include environment and action — NOT the full description, which would
    # heavily overlap with the current [Content] and waste tokens.
    if has_ref:
        memory_parts = []
        prev_env = prompt.get("_prev_clip_environment", "")
        prev_action = prompt.get("_prev_clip_action", "")
        prev_transition_out = prompt.get("_prev_clip_transition_out", "")
        if prev_env:
            memory_parts.append(prev_env)
        if prev_action:
            memory_parts.append(prev_action)
        if memory_parts:
            if lang == "zh":
                header = "以下仅为上下文记忆，禁止重新生成这些内容，只用于理解当前场景状态"
            else:
                header = "Context memory only — do NOT recreate any of this, it already happened"
            sections.append(f"[{SEC_MEMORY}] ({header})\n" + ". ".join(memory_parts))
        # Exact ending state of previous clip — this is what the first frame MUST match
        if prev_transition_out:
            if lang == "zh":
                sections.append(
                    f"[起始状态] (第一帧必须精确匹配此状态，角色的位置、姿势、手势、表情必须一致)\n{prev_transition_out}"
                )
            else:
                sections.append(
                    f"[Starting State] (First frame MUST exactly match this — character position, pose, gesture, expression)\n{prev_transition_out}"
                )

    # ── [Content] ── The actual scene to generate (MAIN PART)
    content_parts = []

    # When continuing from a previous clip, prepend transition_in to anchor the starting pose
    transition_in = prompt.get("transition_in", "")
    if has_ref and transition_in:
        if lang == "zh":
            content_parts.append(f"开场：{transition_in}。")
        else:
            content_parts.append(f"Opening: {transition_in}.")

    if "description" in prompt:
        content_parts.append(prompt["description"])
    elif "prompt" in prompt:
        content_parts.append(prompt["prompt"])
    elif "subject" in prompt:
        content_parts.append(prompt["subject"])

    if "action" in prompt:
        content_parts.append(prompt["action"])

    if "style" in prompt:
        content_parts.append(f"Style: {prompt['style']}")
    if "camera" in prompt:
        content_parts.append(f"Camera: {prompt['camera']}")
    if "lighting" in prompt:
        content_parts.append(f"Lighting: {prompt['lighting']}")
    if "mood" in prompt:
        content_parts.append(f"Mood: {prompt['mood']}")

    # Include dialogue and narration in the content (these inform the video model
    # about what characters should be doing/saying, and audio generation if enabled)
    # NOTE: dialogue speech text is placed in the dedicated [Speech] section below,
    # but we still note the speaking action context here.
    dialogue = prompt.get("dialogue")
    if dialogue and isinstance(dialogue, list):
        speaking_chars = [
            d.get("character", "") for d in dialogue if isinstance(d, dict) and d.get("line")
        ]
        if speaking_chars:
            if lang == "zh":
                content_parts.append(f"{'、'.join(speaking_chars)}在说话")
            else:
                content_parts.append(f"{', '.join(speaking_chars)} speaking")

    narration = prompt.get("narration")
    if narration and isinstance(narration, str) and narration.strip():
        if lang == "zh":
            content_parts.append("有旁白")
        else:
            content_parts.append("With narration")

    sound_effects = prompt.get("sound_effects")
    if sound_effects and isinstance(sound_effects, list):
        sfx = [s for s in sound_effects if isinstance(s, str) and s.strip()]
        if sfx:
            if lang == "zh":
                content_parts.append("音效: " + ", ".join(sfx))
            else:
                content_parts.append("SFX: " + ", ".join(sfx))

    if content_parts:
        sections.append(f"[{SEC_CONTENT}]\n" + ". ".join(content_parts))

    # ── [Speech] ── Exact spoken dialogue and narration (for audio + subtitles)
    # This section defines the EXACT words to be spoken aloud and shown as subtitles.
    # The model must reproduce these words verbatim — no random/invented words.
    speech_lines = []
    dialogue = prompt.get("dialogue")
    if dialogue and isinstance(dialogue, list):
        for d in dialogue:
            if isinstance(d, dict):
                char_name = d.get("character", "")
                line = d.get("line", "")
                emotion = d.get("emotion", "")
                if line:
                    if char_name and emotion:
                        speech_lines.append(f"{char_name}({emotion}): {line}")
                    elif char_name:
                        speech_lines.append(f"{char_name}: {line}")
                    else:
                        speech_lines.append(line)
    narration = prompt.get("narration")
    if narration and isinstance(narration, str) and narration.strip():
        if lang == "zh":
            speech_lines.append(f"旁白: {narration.strip()}")
        else:
            speech_lines.append(f"Narrator: {narration.strip()}")

    if speech_lines:
        if lang == "zh":
            speech_section = "\n".join(speech_lines)
            speech_section += (
                "\n\n以上是本片段的完整台词。"
                "角色必须清晰地说出以上每一句话，语音必须是有意义的自然语言。"
                "禁止生成含糊不清的咕哝声、随机音节、无意义的声音或乱语。"
                "如果角色在说话，其嘴型动作必须与台词同步。"
            )
        else:
            speech_section = "\n".join(speech_lines)
            speech_section += (
                "\n\nAbove is the EXACT dialogue for this clip. "
                "Characters MUST clearly speak each line above — speech must be intelligible natural language. "
                "Do NOT generate mumbling, random syllables, meaningless sounds, or gibberish. "
                "Character lip movements must sync with the spoken words."
            )
        sections.append(f"[{SEC_SPEECH}]\n{speech_section}")

    # ── [Characters] ── Visual appearance and voice references
    char_parts = []
    if "_visual_refs" in prompt:
        # _visual_refs contains both character and location refs from _inject_character_context
        # Extract only character refs (those starting with [name]: not [Location:])
        refs = prompt["_visual_refs"]
        char_refs = []
        loc_refs = []
        for ref in refs.replace(". Visual refs: ", "").split(" | "):
            ref = ref.strip()
            if ref.startswith("[Location:"):
                loc_refs.append(ref)
            elif ref:
                char_refs.append(ref)
        if char_refs:
            char_parts.extend(char_refs)
        # Store loc_refs for [Location] section
        prompt["_location_refs_extracted"] = loc_refs

    if "_voice_mapping" in prompt:
        if lang == "zh":
            char_parts.append("角色声音: " + ", ".join(prompt["_voice_mapping"]))
        else:
            char_parts.append("Character voices: " + ", ".join(prompt["_voice_mapping"]))

    if char_parts:
        sections.append(f"[{SEC_CHARACTERS}]\n" + "\n".join(char_parts))

    # ── [Location] ── Environment and setting
    loc_parts = []
    if "environment" in prompt:
        loc_parts.append(prompt["environment"])
    loc_refs = prompt.get("_location_refs_extracted", [])
    if loc_refs:
        loc_parts.extend(loc_refs)
    if loc_parts:
        sections.append(f"[{SEC_LOCATION}]\n" + ". ".join(loc_parts))

    # ── [Rules] ── Quality and physics constraints
    # Detect if this clip involves electronic devices
    text_blob = " ".join(
        str(prompt.get(k, ""))
        for k in ("prompt", "description", "subject", "action", "environment")
    )
    device_keywords_zh = (
        "笔记本",
        "电脑",
        "手机",
        "平板",
        "显示器",
        "屏幕",
        "键盘",
        "手提电脑",
        "iPad",
        "显示屏",
    )
    device_keywords_en = (
        "laptop",
        "computer",
        "phone",
        "tablet",
        "monitor",
        "screen",
        "keyboard",
        "ipad",
        "display",
    )
    has_device = any(kw in text_blob for kw in device_keywords_zh) or any(
        kw in text_blob.lower() for kw in device_keywords_en
    )

    # Determine if this clip has dialogue (for audio speech rules)
    has_dialogue = False
    dialogue = prompt.get("dialogue")
    if dialogue and isinstance(dialogue, list):
        has_dialogue = any(isinstance(d, dict) and d.get("line") for d in dialogue)

    if lang == "zh":
        rules = "固定镜头，物理真实，背景人物自然走动。"
        if has_device:
            rules += (
                "笔记本电脑和手机的屏幕内容只能出现在两个位置："
                "1.设备屏幕的正面（面向角色的一面，即键盘上方的屏幕，背对相机）；"
                "2.以青色/蓝绿色半透明高科技全息投影形式悬浮在设备上方空中（颜色=#00CED1青色光芒，高科技线框风格，有微弱光晕）。"
                "全息投影必须悬浮在设备上方20-30厘米的空中，与设备表面之间有明显的空隙，不能贴在设备表面上。"
                "绝对禁止在笔记本电脑的盖子外侧（即朝向相机的那一面）显示任何屏幕内容。"
                "笔记本电脑朝向相机的面只能是盖子的外壳/logo面，绝不能有屏幕画面。"
                "相机始终在角色正面。角色面朝相机，笔记本屏幕背对相机。"
            )
        rules += (
            "视频中出现的所有文字（屏幕上的文字、书本、横幅、广告牌、招牌等）必须是真实有意义的自然语言文字或代码，"
            "禁止出现乱码、无意义的Unicode符号、随机字符或不可读的文字。"
        )
        # Strict physics and anatomy constraints
        rules += (
            "严格遵守真实世界物理规则和人体解剖学："
            "人类只有两只手和两只脚，绝不能出现第三只手、多余的手指或幽灵般的肢体。"
            "物体不能凭空漂浮（除非是全息投影），必须受重力影响。"
            "角色不能在同一个片段内瞬移——所有位置变化必须通过连续的自然运动完成。"
            "身体部位的比例必须始终保持一致，不能突然变大或变小。"
            "物体之间必须有正确的遮挡关系，不能穿透。"
            "头发、衣服、液体必须按照物理规律运动。"
            "物体身份规则：门就是门，窗就是窗，不能混淆。"
            "人只能通过门进出房间，绝不能从窗户进出。"
            "每个物体必须保持其真实身份和功能：椅子用来坐，桌子用来放东西，门用来进出。"
            "角色与物体的交互必须符合现实逻辑，禁止任何荒谬或不可能的动作。"
        )
        # Object identity persistence (anti-morphing)
        rules += (
            "物体身份持久性规则（极其重要）："
            "角色手中持有的物体必须在整个片段中保持同一物体。"
            "手机不能变成硬币，笔记本不能变成书本，杯子不能变成碗。"
            "如果角色开始时手持手机，片段结束时手中仍然是手机——不允许任何物体变形或替换。"
            "所有道具的形状、颜色和大小必须在片段内保持一致。"
            "不允许物体在空中漂浮——除了明确标注的全息投影之外，所有物体必须放在表面上或被角色手持。"
            "桌子上的物品不能悬浮在桌面上方，手中的物品不能脱离手掌漂浮。"
        )
        # Audio speech rules
        if has_dialogue:
            rules += (
                "音频语音规则：角色必须清晰地说出[台词]部分的每一句话，发音必须是清晰的自然语言。"
                "绝对禁止生成含糊不清的哝哝声、随机音节、无意义的声音或乱语。"
                "语音必须听起来自然、有感情、像真人说话一样，不能是机器人式的平板读音。"
                "语调必须符合角色的情绪和场景，有自然的停顿、重音和节奠感。"
            )
        else:
            rules += (
                "此片段无[台词]部分，因此绝对禁止生成任何人物说话的声音。"
                "即使画面中角色看起来在说话、解释或交谈，也不要生成任何语音。"
                "只生成环境音效（风声、脚步声、背景噪音等）。"
                "绝对禁止生成随机音节、无意义的哝哝声或任何听不清的人声。"
            )
        # Subtitle prohibition — subtitles are added in post-production, NOT by the video model
        rules += (
            "绝对禁止在视频画面中生成任何字幕、文字覆盖层或底部文字条。"
            "画面底部必须保持干净，不能有任何叠加的文字。"
            "如果参考图片中有字幕文字，忽略它，不要复制到新视频中。"
        )
    else:
        rules = "Static camera, physically realistic, background people moving naturally. "
        if has_device:
            rules += (
                "Laptop and phone screen content may ONLY appear in two places: "
                "1) on the device screen facing the character (the screen above the keyboard, facing AWAY from camera); "
                "2) as a turquoise/cyan semi-transparent high-tech holographic projection floating IN THE AIR above the device "
                "(color=#00CED1 cyan glow, high-tech wireframe style, with subtle halo). "
                "The projection must hover 20-30cm above the device in mid-air with a visible gap between it and the device surface — it must NOT touch or sit on the device. "
                "The side of the laptop facing the camera is ONLY the outer lid/logo — NEVER show screen content there. "
                "Camera always faces the character from the front. Character faces camera, laptop screen faces away from camera. "
            )
        rules += (
            "ALL text visible in the video (screens, books, banners, signs, advertisements) MUST be real meaningful natural language words or code. "
            "NEVER show gibberish, random unicode symbols, meaningless characters, or unreadable text."
        )
        # Strict physics and anatomy constraints
        rules += (
            "STRICT real-world physics and human anatomy rules: "
            "Humans have exactly TWO hands and TWO feet — NEVER render a third hand, extra fingers, or ghost limbs. "
            "Objects must NOT float in mid-air (except holographic projections) — they must obey gravity. "
            "Characters must NOT teleport within the same clip — all position changes must happen through continuous natural motion. "
            "Body proportions must remain consistent throughout — no sudden size changes. "
            "Objects must have correct occlusion — no clipping or passing through each other. "
            "Hair, clothing, and liquids must move according to physics. "
            "Object identity rules: A door is a door, a window is a window — they must NOT be confused. "
            "People can ONLY enter/exit rooms through DOORS, NEVER through windows. "
            "Every object must keep its real identity and function: chairs are for sitting, tables for placing things, doors for entering/exiting. "
            "Character-object interactions must follow real-world logic — no absurd or impossible actions. "
        )
        # Object identity persistence (anti-morphing)
        rules += (
            "OBJECT IDENTITY PERSISTENCE (CRITICAL): "
            "Any object held by a character MUST remain the SAME object throughout the entire clip. "
            "A phone must NOT transform into a coin. A laptop must NOT become a book. A cup must NOT morph into a bowl. "
            "If a character starts holding a phone, they must STILL be holding a phone at the end — NO object morphing or substitution allowed. "
            "All props must maintain consistent shape, color, and size throughout the clip. "
            "NO objects floating in mid-air — except explicitly marked holographic projections, ALL objects must rest on surfaces or be held by characters. "
            "Items on a table must NOT hover above the table surface. Items in hand must NOT detach and float. "
        )
        # Audio speech rules
        if has_dialogue:
            rules += (
                "Audio speech rules: Characters MUST clearly speak each line from the [Speech] section. "
                "Speech must be intelligible natural language. "
                "Do NOT generate mumbling, random syllables, meaningless sounds, or gibberish. "
                "Voice must sound natural, emotional, and human-like — NOT robotic or flat monotone. "
                "Intonation must match the character's emotion and scene context, with natural pauses, emphasis, and rhythm. "
            )
        else:
            rules += (
                "This clip has NO [Speech] section, therefore ABSOLUTELY NO character speaking voices may be generated. "
                "Even if the visual shows a character appearing to talk, explain, or converse — do NOT generate any speech audio. "
                "Only generate ambient/environment sounds (wind, footsteps, background noise, etc.). "
                "STRICTLY FORBIDDEN: random syllables, meaningless mumbling, or any unclear human voice sounds. "
            )
        # Subtitle prohibition — subtitles are added in post-production, NOT by the video model
        rules += (
            "STRICTLY FORBIDDEN: Do NOT generate any subtitles, text overlays, or bottom text bars in the video. "
            "The bottom of the frame must remain clean with NO overlaid text whatsoever. "
            "If the reference image contains subtitle text, IGNORE it — do NOT copy it into the new video. "
        )
    sections.append(f"[{SEC_RULES}]\n{rules}")

    # Clean up temporary field
    prompt.pop("_location_refs_extracted", None)

    return "\n\n".join(sections) if sections else "A short animated scene"


def enhance_prompt_with_llm(prompt: dict) -> dict:
    """Use the artist agent to enhance a video generation prompt.

    Calls the LLM with the @artist agent instructions to refine
    the prompt for better video generation results. Includes style guide
    and character reference keywords for consistency.
    """
    from common import get_project_root
    from llm import call_agent, parse_yaml_response

    project_root = get_project_root()
    raw_prompt = _build_text_prompt(prompt)

    # Load style guide for context
    style_guide = ""
    style_path = project_root / "data" / "style_guide.yaml"
    if style_path.exists():
        style_guide = style_path.read_text(encoding="utf-8")

    lang = os.environ.get("CONTENT_LANGUAGE", "en")
    target_lang_instruction = "Chinese (中文)" if lang == "zh" else "English"

    user_message = f"""Enhance this video generation prompt for optimal results with HuggingFace/Seedance/CogVideoX/Wan2.1 models.

CRITICAL: The ENTIRE output (prompt, negative_prompt, style, camera, lighting) MUST be in {target_lang_instruction}. ALL fields must use {target_lang_instruction}. Do NOT mix languages.

## Original Prompt (scene fields only)
```yaml
{__import__("yaml").dump({k: v for k, v in prompt.items() if not k.startswith("_") and k != "reference_video"}, default_flow_style=False, allow_unicode=True)}
```

## Text Prompt
{raw_prompt}

## Style Guide
```yaml
{style_guide}
```

## Video Generation Constraints
- Clip duration: {prompt.get("duration_seconds", 10)} seconds — the prompt must describe enough ACTION to fill this duration
- Resolution: 720p minimum, FPS: 24
- The prompt must describe a rich SEQUENCE of actions/events that fill the clip's full duration
- Do NOT describe a static scene — describe MOTION, CHANGE, and PROGRESSION
- Do NOT add instruction-style rules to the prompt (no "must", "never", "always")
{("## Previous Quality Issues (FIX THESE in the enhanced prompt)" + chr(10) + chr(10).join("- " + i for i in prompt["_quality_issues"]) + chr(10)) if prompt.get("_quality_issues") else ""}

## Requirements
- Keep the original intent but add cinematic visual detail and MOTION
- Describe what happens throughout the clip with temporal progression (beginning → middle → end)
- Add specific lighting, color, texture descriptions
- Add micro-actions: character gestures, environmental motion (wind, particles, light changes)
- Include character prompt_keywords if character names are mentioned
- If the prompt mentions a reference_video or _prev_clip_description, preserve the same environment. The FIRST frame of the new clip must visually match the last frame of the previous clip (same positions, poses, background, lighting). Start new action only from the second frame onward
- Whenever a character is actively using a phone, laptop, computer, monitor, or tablet (ONLY when electronic devices are present in the scene): add a TURQUOISE/CYAN (#00CED1) semi-transparent high-tech holographic screen projection floating IN THE AIR above the device (20-30cm gap between projection and device surface, clearly hovering, NOT touching the device). The projection must be spatially anchored above the device the character is using. The screen content must NEVER appear on the outer lid of the laptop (the side facing the camera) or the back of the phone. The laptop facing the camera shows ONLY the outer lid/logo, never a screen. Do NOT add this effect if no electronic device is present in the scene
- ALL text visible in the video (on screens, books, banners, signs, advertisements, scrolls) MUST be real meaningful natural language words or actual code. NEVER generate gibberish, random symbols, meaningless unicode characters, or unreadable squiggles as text. If showing code on a screen, use real programming language syntax
- Make the scene DYNAMIC: characters should be actively doing something, not just standing or sitting still. Emphasize motion, gestures, expressions, and interactions
- BACKGROUND LIFE: If there are crowd scenes, bystanders, or background people, describe them with natural ambient motion (walking, chatting, gesturing, looking around). Never describe background characters as static or frozen
- OBJECT IDENTITY PERSISTENCE: If a character holds an object (phone, cup, tool), that EXACT object must remain the same throughout the clip. NEVER describe an object transforming into a different object. A phone stays a phone, a coin stays a coin
- NO FLOATING OBJECTS: All objects must obey gravity. Items must rest on surfaces or be held by characters. Nothing hovers in mid-air unless it is explicitly a holographic projection
- Keep prompt between 60-150 words — enough to describe temporal progression but concise enough for the model
- If the original prompt contains @ImageN or @AudioN tags (e.g. @Image1, @Audio1), PRESERVE them exactly in the enhanced prompt — these are asset references for the video model
- ALL OUTPUT MUST BE IN {target_lang_instruction} — including negative_prompt
- Output ONLY valid YAML:

prompt: "<enhanced detailed prompt in {target_lang_instruction}>"
negative_prompt: "<comprehensive negative prompt in {target_lang_instruction}>"
style: "<visual style in {target_lang_instruction}>"
camera: "<camera movement in {target_lang_instruction}>"
lighting: "<lighting setup in {target_lang_instruction}>"
duration_seconds: {prompt.get("duration_seconds", 10)}
"""

    try:
        raw_text = call_agent("artist", user_message, max_tokens=2000)
        enhanced = parse_yaml_response(raw_text)
        # Merge enhanced fields back into original prompt
        # ONLY overwrite visual/cinematic fields — preserve audio/narrative fields
        prompt["description"] = enhanced.get("prompt", prompt.get("description", raw_prompt))
        prompt["negative_prompt"] = enhanced.get(
            "negative_prompt", prompt.get("negative_prompt", "")
        )
        if "style" in enhanced:
            prompt["style"] = enhanced["style"]
        if "camera" in enhanced:
            prompt["camera"] = enhanced["camera"]
        if "lighting" in enhanced:
            prompt["lighting"] = enhanced["lighting"]
        # Preserve fields that the artist LLM does not produce:
        # dialogue, narration, sound_effects, transition_in, transition_out, etc.
        # These are already in prompt and should NOT be removed.
        log.info("Prompt enhanced by artist agent")
    except Exception as e:
        log.warning(f"LLM prompt enhancement failed, using original: {e}")

    # Generate missing dialogue: if the prompt describes speaking/explaining but has no dialogue lines,
    # ask the LLM to generate natural dialogue so the video model has actual words to speak.
    _generate_missing_dialogue(prompt)

    return prompt


def _generate_missing_dialogue(prompt: dict) -> None:
    """If prompt describes speaking actions but has no dialogue, generate it via LLM."""
    # Check if dialogue already exists
    dialogue = prompt.get("dialogue")
    if (
        dialogue
        and isinstance(dialogue, list)
        and any(isinstance(d, dict) and d.get("line") for d in dialogue)
    ):
        return  # Dialogue already present

    # Check if the prompt text describes speaking/explaining actions
    text_blob = " ".join(
        str(prompt.get(k, "")) for k in ("prompt", "description", "subject", "action")
    ).lower()

    speaking_keywords_zh = (
        "解释",
        "说",
        "讲",
        "告诉",
        "回答",
        "问",
        "喊",
        "叫",
        "介绍",
        "描述",
        "聊天",
        "交谈",
        "对话",
        "询问",
        "叙述",
        "提醒",
        "劝",
        "安慰",
        "争论",
        "吐槽",
        "感叹",
        "嘀咕",
    )
    speaking_keywords_en = (
        "explain",
        "say",
        "tell",
        "speak",
        "ask",
        "answer",
        "shout",
        "describe",
        "introduce",
        "chat",
        "converse",
        "talk",
        "discuss",
        "narrate",
        "argue",
        "comfort",
        "remind",
        "mutter",
        "exclaim",
    )

    has_speaking_action = any(kw in text_blob for kw in speaking_keywords_zh) or any(
        kw in text_blob for kw in speaking_keywords_en
    )

    if not has_speaking_action:
        return  # No speaking action described — no need for dialogue

    log.info("  Detected speaking action without dialogue — generating via LLM...")

    lang = os.environ.get("CONTENT_LANGUAGE", "en")
    target_lang = "Chinese (中文)" if lang == "zh" else "English"

    # Extract character names from prompt
    characters = []
    if prompt.get("_character_avatars"):
        characters = [a.get("name", "") for a in prompt["_character_avatars"] if a.get("name")]

    try:
        from llm import call_agent, parse_yaml_response

        dialogue_request = f"""Based on this scene description, generate natural dialogue lines for the characters.

Scene description: {text_blob[:500]}
Characters present: {", ".join(characters) if characters else "Unknown"}
Language: {target_lang}
Duration: {prompt.get("duration_seconds", 10)} seconds

Rules:
- Generate 1-3 short dialogue lines that fit naturally into the scene
- Each line should be a complete, meaningful sentence
- Match the tone/emotion of the scene
- Lines should be short enough to say in a few seconds each
- Output MUST be in {target_lang}

Output ONLY valid YAML list:
dialogue:
  - character: "<name>"
    line: "<what they say>"
    emotion: "<emotion>"
"""
        raw = call_agent("artist", dialogue_request, max_tokens=500)
        parsed = parse_yaml_response(raw)
        generated_dialogue = parsed.get("dialogue", [])
        if generated_dialogue and isinstance(generated_dialogue, list):
            # Validate structure
            valid_lines = []
            for d in generated_dialogue:
                if isinstance(d, dict) and d.get("line"):
                    valid_lines.append(
                        {
                            "character": d.get("character", ""),
                            "line": d.get("line", ""),
                            "emotion": d.get("emotion", ""),
                        }
                    )
            if valid_lines:
                prompt["dialogue"] = valid_lines
                log.info(
                    f"  Generated {len(valid_lines)} dialogue line(s): "
                    f"{'; '.join(d['line'][:30] for d in valid_lines)}"
                )
    except Exception as e:
        log.warning(f"  Dialogue generation failed: {e} — clip will have no speech audio")


def _dry_run(prompt: dict, output_path: Path | None) -> Path:
    """Create a placeholder file for testing without API access."""
    if output_path is None:
        output_path = Path("dry_run_output.mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Write a minimal placeholder (not a valid video, but marks the file as generated)
    output_path.write_text("DRY_RUN_PLACEHOLDER")
    log.info(f"Dry-run output: {output_path}")
    return output_path


def extract_first_frame(video_path: Path) -> Path | None:
    """Extract the first frame of a video clip as a reference image."""
    try:
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        out = video_path.parent / f"{video_path.stem}_first_frame.jpg"
        cv2.imwrite(str(out), frame)
        return out
    except (ImportError, Exception) as e:
        log.warning(f"Failed to extract first frame: {e}")
        return None


def extract_last_frame(video_path: Path) -> Path | None:
    """Extract the last frame of a video clip as a reference image."""
    try:
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total - 1))
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        out = video_path.parent / f"{video_path.stem}_last_frame.jpg"
        cv2.imwrite(str(out), frame)
        return out
    except (ImportError, Exception) as e:
        log.warning(f"Failed to extract last frame: {e}")
        return None


def regenerate_clip(
    original_clip: Path,
    improvement_prompt: str | None = None,
    model: str | None = None,
    quality: str | None = None,
    seed: int | None = None,
    local: bool = False,
    story_slug: str | None = None,
) -> Path:
    """Regenerate a single clip with frame preservation.

    Extracts the first frame from the original clip and uses it as the
    starting reference for the new generation. The improvement prompt
    (if provided) is used to guide the regeneration. If no improvement
    prompt is given, the LLM auto-generates one from the original clip's
    scene prompt.

    The regenerated clip is saved with a .regen suffix (e.g. scene_1.regen.mp4)
    so the user can compare before accepting/discarding.

    Returns the path to the regenerated clip.
    """
    if not original_clip.exists():
        raise FileNotFoundError(f"Original clip not found: {original_clip}")

    config = load_config()
    model = model or os.environ.get("VIDEO_MODEL") or config["model"]["name"]
    quality = quality or os.environ.get("VIDEO_QUALITY") or config["generation"]["quality"]

    # Extract first frame as reference
    first_frame = extract_first_frame(original_clip)
    if first_frame:
        log.info(f"Extracted first frame: {first_frame}")
    else:
        log.warning("Could not extract first frame — regeneration will start fresh")

    # Build prompt from original scene prompt or improvement prompt
    clip_name = original_clip.stem  # e.g. scene_1_clip_1
    clips_run_dir = original_clip.parent
    clips_dir = clips_run_dir.parent
    ep_dir = clips_dir.parent
    scenes_dir = ep_dir / "scenes"

    # Find matching scene prompt
    original_prompt = {}
    run_ts = clips_run_dir.name
    scenes_run_dir = scenes_dir / run_ts
    if not scenes_run_dir.exists() and scenes_dir.exists():
        subdirs = sorted([d for d in scenes_dir.iterdir() if d.is_dir()], reverse=True)
        scenes_run_dir = subdirs[0] if subdirs else scenes_dir

    prompt_file = scenes_run_dir / f"{clip_name}_prompt.yaml"
    if prompt_file.exists():
        original_prompt = load_yaml(str(prompt_file))
    else:
        # Try scene-level prompt
        import re as _re

        match = _re.match(r"(scene_\d+)", clip_name)
        if match:
            scene_prompt_file = scenes_run_dir / f"{match.group(1)}_prompt.yaml"
            if scene_prompt_file.exists():
                original_prompt = load_yaml(str(scene_prompt_file))

    # If improvement prompt is provided, use it to override the description
    if improvement_prompt:
        original_prompt["description"] = improvement_prompt
    elif not original_prompt.get("description") and not original_prompt.get("prompt"):
        # Auto-generate improvement prompt via LLM
        log.info("No prompt available — using LLM to generate improvement prompt")
        try:
            from llm import call_agent, parse_yaml_response

            user_msg = f"""Generate a video generation prompt for regenerating this clip: {clip_name}
The clip is part of an animated episode. Create a detailed visual prompt under 100 words.
Output ONLY valid YAML:
prompt: "<detailed visual prompt>"
"""
            raw = call_agent("artist", user_msg, max_tokens=500)
            parsed = parse_yaml_response(raw)
            original_prompt["description"] = parsed.get("prompt", f"Regenerate {clip_name}")
        except Exception as e:
            log.warning(f"LLM prompt generation failed: {e}")
            original_prompt["description"] = f"Regenerate clip {clip_name}"

    # Set first frame as reference for continuity (uses last-frame image approach)
    if first_frame and first_frame.exists():
        original_prompt["reference_video"] = str(first_frame)  # Path to extracted first frame JPEG
        original_prompt["_reference_mode"] = "image"
        log.info(f"  Using first frame as reference_image for continuity")

    # Load the original clip's API URL for passing as reference_video
    url_file = original_clip.parent / f"{original_clip.stem}.url"
    if url_file.exists():
        ref_video_url = url_file.read_text(encoding="utf-8").strip()
        original_prompt["_reference_video_url"] = ref_video_url
        log.info(f"  Passing original video URL as reference_video: {ref_video_url[:80]}...")

    # Run LLM enhancement on the prompt (adds cinematic detail, generates missing dialogue)
    try:
        original_prompt = enhance_prompt_with_llm(original_prompt)
        log.info("  Prompt enhanced by LLM for regeneration")
    except Exception as e:
        log.warning(f"  LLM enhancement failed during regeneration: {e}")

    # Inject character context and animation style
    if story_slug:
        _inject_character_context(original_prompt, story_slug)
    _inject_animation_style(original_prompt)

    # Output to .regen.mp4
    regen_path = original_clip.parent / f"{original_clip.stem}.regen.mp4"

    log.info(f"Regenerating clip: {original_clip.name} → {regen_path.name}")

    # Generate
    retry_config = config.get("retry", {})
    max_attempts = retry_config.get("max_attempts", 3)
    backoff = retry_config.get("backoff_seconds", 10)

    for attempt in range(1, max_attempts + 1):
        try:
            generate_video(original_prompt, model, quality, seed, regen_path, local=local)
            break
        except Exception as e:
            log.error(f"Regeneration failed (attempt {attempt}/{max_attempts}): {e}")
            if attempt < max_attempts:
                log.info(f"Retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                raise RuntimeError(
                    f"All regeneration attempts failed for {original_clip.name}"
                ) from e

    log.info(f"Regenerated clip saved: {regen_path} ({regen_path.stat().st_size / 1024:.1f} KB)")

    # Clean up extracted frame
    if first_frame and first_frame.exists():
        first_frame.unlink(missing_ok=True)

    return regen_path


def _extract_last_segment(video_path: Path) -> Path | None:
    """Extract the last few frames (~0.25s) of a video clip for continuity.

    Kept short to avoid the model wasting generation capacity reproducing
    the previous clip content.
    """
    try:
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 24
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            cap.release()
            return None

        # Extract last ~0.25 seconds (a few frames — enough for visual context)
        frames_to_extract = min(max(fps // 4, 2), total_frames)
        start_frame = total_frames - frames_to_extract

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        frames = []
        for _ in range(frames_to_extract):
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
        cap.release()

        if not frames:
            return None

        # Write the segment as a short video
        segment_path = video_path.parent / f"{video_path.stem}_last_segment.mp4"
        h, w = frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(segment_path), fourcc, fps, (w, h))
        for frame in frames:
            writer.write(frame)
        writer.release()

        log.info(f"  Extracted last {len(frames)} frames ({len(frames) / fps:.1f}s) for continuity")
        return segment_path
    except ImportError:
        log.warning("cv2 not available; cannot extract last segment for continuity")
        return None
    except Exception as e:
        log.warning(f"Failed to extract last segment from {video_path}: {e}")
        return None


def _get_continuity_reference(ref_path: Path) -> Path | None:
    """
    Progressive fallback continuity for cloud (HuggingFace) generation.
    Returns a single image path for image_to_video, or None for text-only fallback.

    Fallback chain:
      1. Multiple last frames composited into a grid (gives model more temporal context)
      2. Single last frame
      3. None (pure text-to-video)
    """
    try:
        import cv2

        cap = cv2.VideoCapture(str(ref_path))
        if not cap.isOpened():
            return None

        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 24
        if total <= 0:
            cap.release()
            return None

        # Level 1: Try extracting last N frames as a horizontal grid image
        # This gives the model temporal context across the last ~1s
        n_frames = min(fps, total, 6)  # Up to 6 frames
        start_frame = max(0, total - n_frames)
        step = max(1, (total - start_frame) // n_frames)
        frames = []
        for i in range(n_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame + i * step)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)

        cap.release()

        if len(frames) > 1:
            # Create a horizontal strip of the last few frames
            import numpy as np

            # Resize frames to a consistent height for the grid
            target_h = 360
            resized = []
            for f in frames:
                h, w = f.shape[:2]
                scale = target_h / h
                resized.append(cv2.resize(f, (int(w * scale), target_h)))
            grid = np.hstack(resized)
            grid_path = ref_path.parent / f"{ref_path.stem}_continuity_grid.png"
            cv2.imwrite(str(grid_path), grid)
            log.info(f"  Continuity: using {len(frames)}-frame grid for context")
            return grid_path

        # Level 2: Single last frame
        if frames:
            frame_path = ref_path.parent / f"{ref_path.stem}_last_frame.png"
            cv2.imwrite(str(frame_path), frames[-1])
            log.info(f"  Continuity: using single last frame")
            return frame_path

        return None
    except ImportError:
        log.warning("  cv2 not available; falling back to text-only generation")
        return None
    except Exception as e:
        log.warning(f"  Continuity reference extraction failed: {e}")
        return None


def _get_continuity_frames_for_local(ref_path: Path, device, torch) -> "torch.Tensor | None":  # noqa: A002, F821
    """
    Progressive fallback continuity for local pipeline generation.
    Returns a tensor of conditioning frames, or None for text-only.

    Fallback chain:
      1. Full last 1s as video segment → all frames as conditioning_frames tensor
      2. Multiple last frames (reduced set)
      3. Single last frame repeated
      4. None (text-only)
    """
    try:
        import cv2

        # Level 1: Extract last 1s segment frames
        segment_path = _extract_last_segment(ref_path)
        if segment_path and segment_path.exists():
            cap = cv2.VideoCapture(str(segment_path))
            frames = []
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frames.append(frame)
            cap.release()
            if frames:
                conditioning_frames = [
                    torch.from_numpy(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float()
                    / 255.0
                    for f in frames
                ]
                conditioning_frames = torch.stack(conditioning_frames).to(device)
                log.info(f"  Continuity (local): using {len(frames)}-frame segment (1s)")
                return conditioning_frames

        # Level 2: Extract a few last frames directly from original video
        cap = cv2.VideoCapture(str(ref_path))
        if not cap.isOpened():
            return None
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            cap.release()
            return None

        n_frames = min(4, total)
        start = total - n_frames
        frames = []
        for i in range(n_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, start + i)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
        cap.release()

        if frames:
            conditioning_frames = [
                torch.from_numpy(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float()
                / 255.0
                for f in frames
            ]
            conditioning_frames = torch.stack(conditioning_frames).to(device)
            log.info(f"  Continuity (local): using {len(frames)} last frames")
            return conditioning_frames

        return None
    except ImportError:
        log.warning("  cv2 not available; falling back to text-only local generation")
        return None
    except Exception as e:
        log.warning(f"  Local continuity frame extraction failed: {e}")
        return None


# Cache for loaded character/location data per story
_character_cache: dict[str, list[dict]] = {}
_location_cache: dict[str, list[dict]] = {}


def _load_story_characters(story_slug: str) -> list[dict]:
    """Load all character YAML files for a story."""
    if story_slug in _character_cache:
        return _character_cache[story_slug]
    from common import get_project_root

    chars_dir = get_project_root() / "data" / "stories" / story_slug / "characters"
    characters = []
    if chars_dir.exists():
        import yaml as _yaml

        for f in chars_dir.glob("*.yaml"):
            if f.name == "README.yaml":
                continue
            try:
                data = _yaml.safe_load(f.read_text(encoding="utf-8"))
                if data and isinstance(data, dict):
                    characters.append(data)
            except Exception:
                pass
    _character_cache[story_slug] = characters
    return characters


def _load_story_locations(story_slug: str) -> list[dict]:
    """Load all location YAML files for a story."""
    if story_slug in _location_cache:
        return _location_cache[story_slug]
    from common import get_project_root

    locs_dir = get_project_root() / "data" / "stories" / story_slug / "locations"
    locations = []
    if locs_dir.exists():
        import yaml as _yaml

        for f in locs_dir.glob("*.yaml"):
            if f.name == "README.yaml":
                continue
            try:
                data = _yaml.safe_load(f.read_text(encoding="utf-8"))
                if data and isinstance(data, dict):
                    locations.append(data)
            except Exception:
                pass
    _location_cache[story_slug] = locations
    return locations


def _inject_character_context(prompt: dict, story_slug: str | None) -> None:
    """Inject character visual descriptions, voice references, and location details into prompt."""
    if not story_slug:
        return

    characters = _load_story_characters(story_slug)
    locations = _load_story_locations(story_slug)

    # Find characters mentioned in the prompt text
    text = prompt.get("description", "") or prompt.get("prompt", "") or prompt.get("subject", "")
    matched_parts = []
    voice_refs = []  # Collect voice URLs for Seedance reference_audio

    def _name_in_text(entry: dict, text: str) -> str | None:
        """Check if any name variant (name, name_zh) appears in text. Returns the matched name."""
        for key in ("name", "name_zh"):
            n = entry.get(key, "")
            if n and n in text:
                return n
        return None

    for char in characters:
        matched_name = _name_in_text(char, text)
        if not matched_name:
            continue
        name = char.get("name", "") or char.get("name_zh", "")
        # Build comprehensive character description
        parts = []
        if char.get("prompt_keywords"):
            parts.append(char["prompt_keywords"])
        # Add appearance details
        appearance = char.get("appearance", {})
        if appearance:
            app_items = []
            if appearance.get("hair"):
                app_items.append(f"hair: {appearance['hair']}")
            if appearance.get("eyes"):
                app_items.append(f"eyes: {appearance['eyes']}")
            if appearance.get("build"):
                app_items.append(appearance["build"])
            if appearance.get("distinguishing_features"):
                app_items.extend(appearance["distinguishing_features"])
            if app_items:
                parts.append(", ".join(app_items))
        # Add clothing
        clothing = char.get("clothing", {})
        if clothing and clothing.get("default_outfit"):
            parts.append(clothing["default_outfit"])
        # Add personality visual cues
        if char.get("personality_visual_cues"):
            parts.append(char["personality_visual_cues"])

        if parts:
            matched_parts.append(f"[{name}]: {'; '.join(parts)}")

        # Collect voice reference for Seedance audio generation
        # Priority: voice_asset_id (from digital character library) > voice_url
        voice_asset_id = char.get("voice_asset_id")
        voice_url = char.get("voice_url")
        if voice_asset_id:
            voice_refs.append({"name": name, "url": f"asset://{voice_asset_id}"})
            matched_parts.append(f"[Voice: {name}]: digital character asset")
        elif voice_url:
            voice_refs.append({"name": name, "url": voice_url})
            matched_parts.append(f"[Voice: {name}]: reference_audio provided")

    # Find locations mentioned in the prompt text
    for loc in locations:
        loc_name = _name_in_text(loc, text)
        if not loc_name:
            continue
        loc_parts = []
        if loc.get("prompt_keywords"):
            loc_parts.append(loc["prompt_keywords"])
        if loc.get("description"):
            loc_parts.append(loc["description"])
        if loc.get("visual_features"):
            loc_parts.append(
                ", ".join(loc["visual_features"])
                if isinstance(loc["visual_features"], list)
                else loc["visual_features"]
            )
        if loc_parts:
            matched_parts.append(f"[Location: {loc_name}]: {'; '.join(loc_parts)}")

    # Also check location_ref field from scene breakdown
    location_ref = prompt.get("location_ref", "") or prompt.get("environment", "")
    if location_ref:
        for loc in locations:
            loc_name = _name_in_text(loc, location_ref)
            if not loc_name:
                continue
            if any(loc_name in p for p in matched_parts):
                continue
            loc_parts = []
            if loc.get("prompt_keywords"):
                loc_parts.append(loc["prompt_keywords"])
            if loc.get("description"):
                loc_parts.append(loc["description"])
            if loc_parts:
                matched_parts.append(f"[Location: {loc_name}]: {'; '.join(loc_parts)}")

    if matched_parts:
        context_info = ". Visual refs: " + " | ".join(matched_parts)
        # Store in a separate field so it survives LLM prompt enhancement
        prompt["_visual_refs"] = context_info
        log.info(f"  Injected character/location context: {len(matched_parts)} refs")

    # Collect character avatar image paths (full-body reference PNGs)
    avatar_paths = []
    from common import get_project_root

    avatars_dir = get_project_root() / "data" / "stories" / story_slug / "characters" / "avatars"
    for char in characters:
        matched_name = _name_in_text(char, text)
        if not matched_name:
            continue
        name = char.get("name", "") or char.get("name_zh", "")
        # Look up avatar by slug field, then compute pinyin slug
        slug = char.get("slug", "")
        if not slug:
            import re as _re

            slug_try = name.lower().replace(" ", "_")
            if slug_try.isascii() and _re.match(r"^[a-z0-9_]+$", slug_try):
                slug = slug_try
            else:
                try:
                    from pypinyin import Style, pinyin

                    py = pinyin(name, style=Style.NORMAL)
                    slug = "_".join(s[0] for s in py if s[0])
                    slug = _re.sub(r"[^a-z0-9_]", "", slug.lower())
                except ImportError:
                    import hashlib as _hl

                    slug = f"char_{_hl.md5(name.encode('utf-8')).hexdigest()[:8]}"
        avatar_file = avatars_dir / f"{slug}.png"
        if avatar_file.exists():
            avatar_paths.append({"name": name, "path": str(avatar_file)})
    if avatar_paths:
        prompt["_character_avatars"] = avatar_paths
        log.info(f"  Injected {len(avatar_paths)} character avatar images")

    # Store voice references for Seedance reference_audio
    if voice_refs:
        prompt["_voice_refs"] = voice_refs
        # Also store voice-character mapping for text prompt injection
        voice_mapping = [
            f"{vr['name']}的声音=asset://{vr['url'].replace('asset://', '')}" for vr in voice_refs
        ]
        prompt["_voice_mapping"] = voice_mapping
        log.info(f"  Injected {len(voice_refs)} character voice refs for audio generation")


def _inject_animation_style(prompt: dict) -> None:
    """Inject visual style into prompt based on VIDEO_STYLE env var (language-aware)."""
    lang = os.environ.get("CONTENT_LANGUAGE", "en")
    style_key = os.environ.get("VIDEO_STYLE", "chinese-cartoon")

    # Style presets: (en_keywords, zh_keywords, en_prefix, zh_prefix, negative_additions)
    STYLE_PRESETS = {
        "chinese-cartoon": {
            "en_keywords": "Chinese animation, cartoon style, 2D animation, smooth animation, vibrant colors, guofeng",
            "zh_keywords": "国风动画, 卡通风格, 2D动画, 流畅动画, 鲜艳色彩",
            "en_prefix": "Chinese cartoon animation style. ",
            "zh_prefix": "国风动画卡通风格。",
            "negative": "photorealistic, live action, real person, photograph",
            "negative_zh": "真人实拍, 写实照片, 真实人物, 摄影风格",
        },
        "anime": {
            "en_keywords": "anime style, Japanese animation, cel shading, detailed eyes, dynamic poses, vibrant",
            "zh_keywords": "日本动漫风格, 赛璐璐上色, 精致眼睛, 动态姿态",
            "en_prefix": "Japanese anime style. ",
            "zh_prefix": "日本动漫风格。",
            "negative": "photorealistic, live action, real person, photograph, western cartoon",
            "negative_zh": "真人实拍, 写实照片, 真实人物, 摄影风格, 西方卡通",
        },
        "pixar-3d": {
            "en_keywords": "3D animated, Pixar style, CGI, smooth rendering, subsurface scattering, cinematic lighting",
            "zh_keywords": "3D动画, 皮克斯风格, CGI渲染, 电影级光照",
            "en_prefix": "Pixar-style 3D animation. ",
            "zh_prefix": "皮克斯风格3D动画。",
            "negative": "2D, flat, hand-drawn, photorealistic, live action",
            "negative_zh": "2D平面, 手绘, 写实照片, 真人实拍",
        },
        "watercolor": {
            "en_keywords": "watercolor illustration, soft edges, paint bleeding, pastel palette, artistic, hand-painted",
            "zh_keywords": "水彩插画风格, 柔和边缘, 颜料晕染, 柔和色调",
            "en_prefix": "Watercolor illustration style. ",
            "zh_prefix": "水彩插画风格。",
            "negative": "photorealistic, sharp edges, 3D render, digital art",
            "negative_zh": "写实照片, 锐利边缘, 3D渲染, 数字艺术",
        },
        "comic-book": {
            "en_keywords": "comic book style, bold outlines, halftone dots, dramatic shading, graphic novel, pop art colors",
            "zh_keywords": "漫画风格, 粗线条, 网点效果, 戏剧性阴影",
            "en_prefix": "Comic book graphic novel style. ",
            "zh_prefix": "漫画图像小说风格。",
            "negative": "photorealistic, soft edges, 3D render, anime",
            "negative_zh": "写实照片, 柔和边缘, 3D渲染, 日式动漫",
        },
        "stop-motion": {
            "en_keywords": "stop motion animation, claymation, tactile textures, handcrafted, miniature sets, visible imperfections",
            "zh_keywords": "定格动画, 黏土动画, 手工质感, 微缩场景",
            "en_prefix": "Stop motion claymation style. ",
            "zh_prefix": "定格黏土动画风格。",
            "negative": "smooth, digital, photorealistic, 2D flat",
            "negative_zh": "光滑数字效果, 写实照片, 2D平面",
        },
        "pixel-art": {
            "en_keywords": "pixel art, retro game, 16-bit, limited palette, blocky, nostalgic, sprite animation",
            "zh_keywords": "像素艺术, 复古游戏, 16位风格, 有限色板",
            "en_prefix": "Pixel art retro game style. ",
            "zh_prefix": "像素艺术复古游戏风格。",
            "negative": "photorealistic, smooth, high resolution, 3D render",
            "negative_zh": "写实照片, 光滑效果, 高分辨率写实, 3D渲染",
        },
        "ink-wash": {
            "en_keywords": "Chinese ink wash painting, sumi-e, monochrome, brush strokes, traditional, minimalist, flowing ink",
            "zh_keywords": "水墨画风格, 写意, 黑白灰, 毛笔笔触, 传统中国画",
            "en_prefix": "Chinese ink wash painting style. ",
            "zh_prefix": "中国水墨画风格。",
            "negative": "colorful, photorealistic, 3D render, cartoon, bright colors",
            "negative_zh": "彩色写实, 3D渲染, 卡通风格, 鲜艳色彩",
        },
        "flat-vector": {
            "en_keywords": "flat vector design, motion graphics, geometric shapes, clean lines, bold colors, minimal detail",
            "zh_keywords": "扁平矢量设计, 运动图形, 几何图形, 简洁线条",
            "en_prefix": "Flat vector motion graphics style. ",
            "zh_prefix": "扁平矢量运动图形风格。",
            "negative": "photorealistic, textured, 3D, hand-drawn, detailed",
            "negative_zh": "写实照片, 纹理细节, 3D立体, 手绘, 过度细节",
        },
        "realistic-cgi": {
            "en_keywords": "realistic CGI, photorealistic rendering, ray tracing, cinematic, high detail, volumetric lighting",
            "zh_keywords": "写实CGI, 光线追踪, 电影级, 高细节, 体积光",
            "en_prefix": "Realistic CGI cinematic style. ",
            "zh_prefix": "写实CGI电影风格。",
            "negative": "cartoon, anime, flat, hand-drawn, low poly",
            "negative_zh": "卡通风格, 动漫风格, 平面设计, 手绘, 低多边形",
        },
    }

    preset = STYLE_PRESETS.get(style_key, STYLE_PRESETS["chinese-cartoon"])

    if lang == "zh":
        style_keywords = preset["zh_keywords"]
        style_prefix = preset["zh_prefix"]
    else:
        style_keywords = preset["en_keywords"]
        style_prefix = preset["en_prefix"]

    if "style" in prompt:
        prompt["style"] = f"{prompt['style']}, {style_keywords}"
    else:
        prompt["style"] = style_keywords

    # Prepend style to the main prompt/description
    for key in ("prompt", "description", "subject"):
        if key in prompt:
            prompt[key] = f"{style_prefix}{prompt[key]}"
            break

    # Add style-specific negative prompt (language-matched)
    neg = prompt.get("negative_prompt", "")
    if lang == "zh":
        anti = preset.get("negative_zh", preset["negative"])
    else:
        anti = preset["negative"]
    if anti.split(",")[0].strip().lower() not in neg.lower():
        prompt["negative_prompt"] = f"{neg}, {anti}" if neg else anti

    # Add concise negative prompts — keep short to avoid confusing the model
    if lang == "zh":
        quality_neg = "物体位移, 物体变形, 手机变硬币, 物体漂浮, 悬浮物体, 过度变焦, 空间逻辑错误, 屏幕显示在笔记本背盖上, 屏幕显示在手机背面, 显示器在设备背面, 从背后拍摄角色, 乱码文字, 无意义符号, 随机字符"
    else:
        quality_neg = "object morphing, object switching, phone turning into coin, floating objects, hovering objects, objects shifting position, excessive zoom, spatial logic error, screen on laptop lid backside, screen on back of phone, monitor on back of device, filming character from behind, gibberish text, random symbols, meaningless unicode, unreadable characters"

    current_neg = prompt.get("negative_prompt", "")
    if "floating" not in current_neg and "悬浮" not in current_neg:
        prompt["negative_prompt"] = f"{current_neg}, {quality_neg}" if current_neg else quality_neg


def _validate_and_regen(
    output_path: Path,
    prompt: dict,
    model: str,
    quality: str,
    seed: int | None,
    local: bool,
    scene_prompt_path: Path | None = None,
    story_slug: str | None = None,
) -> None:
    """Run quality validation and regenerate if failed.

    On failure, reloads the ORIGINAL scene YAML prompt and re-runs full LLM
    enhancement (not the already-enhanced prompt). Passes the original video's
    first frame as reference so the regenerated clip maintains visual continuity.

    Args:
        scene_prompt_path: Path to the original scene prompt YAML for this clip.
            Used to reload a clean prompt for re-enhancement on each regen attempt.
    """
    from validate_quality import load_qa_config, validate_clip

    qa_config = load_qa_config()
    result = validate_clip(output_path, qa_config)
    if result["passed"]:
        log.info("  Quality check PASSED")
        return

    log.warning("  Quality check FAILED:")
    for issue in result["issues"]:
        log.warning(f"    - {issue}")

    # Load the original clip's API URL for passing as reference_video
    url_file = output_path.parent / f"{output_path.stem}.url"
    ref_video_url = None
    if url_file.exists():
        ref_video_url = url_file.read_text(encoding="utf-8").strip()
        log.info(f"  Loaded original clip API URL for reference_video: {ref_video_url[:80]}...")

    # Extract first frame from the failed clip as fallback reference
    first_frame = extract_first_frame(output_path) if output_path.exists() else None

    regen_max = qa_config.get("on_failure", {}).get("max_regeneration_attempts", 3)
    for regen in range(1, regen_max + 1):
        log.info(f"  Regenerating (attempt {regen}/{regen_max})...")

        # Reload the ORIGINAL scene YAML so we re-enhance from scratch each time
        if scene_prompt_path and scene_prompt_path.exists():
            regen_prompt = load_scene_prompt(str(scene_prompt_path))
            log.info(f"  Reloaded original scene prompt: {scene_prompt_path.name}")
        else:
            # Fallback: use existing prompt dict (already enhanced — not ideal)
            regen_prompt = dict(prompt)
            log.warning("  No scene prompt YAML found — reusing current prompt")

        # Attach original video URL as reference_video (preferred)
        if ref_video_url:
            regen_prompt["_reference_video_url"] = ref_video_url
            log.info(f"  Passing original video URL as reference_video for regeneration")

        # Also attach first frame as reference_image fallback
        if first_frame and first_frame.exists():
            regen_prompt["reference_video"] = str(first_frame)
            regen_prompt["_reference_mode"] = "image"

        # Carry over character context and animation style
        if story_slug:
            _inject_character_context(regen_prompt, story_slug)
        _inject_animation_style(regen_prompt)

        # Add quality failure context so LLM enhancement can address specific issues
        regen_prompt["_quality_issues"] = result["issues"]

        try:
            # enhance=True (default) will re-run enhance_prompt_with_llm inside generate_video
            generate_video(regen_prompt, model, quality, seed, output_path, local=local)
        except Exception as e:
            log.error(f"  Regeneration failed: {e}")
            continue
        result = validate_clip(output_path, qa_config)
        if result["passed"]:
            log.info(f"  Quality check PASSED on regeneration attempt {regen}")
            # Clean up frame
            if first_frame and first_frame.exists():
                first_frame.unlink(missing_ok=True)
            return
    log.error("  Max regeneration attempts reached. Flagging for manual review.")
    if first_frame and first_frame.exists():
        first_frame.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Generate scene video")
    parser.add_argument("--scene", type=str, default=None, help="Path to scene prompt YAML")
    parser.add_argument(
        "--episode", type=int, default=None, help="Episode number (generates all scenes)"
    )
    parser.add_argument("--story", type=str, default=None, help="Story slug")
    parser.add_argument("--model", type=str, default=None, help="Model override")
    parser.add_argument("--quality", type=str, default=None, help="Quality preset")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument(
        "--local", action="store_true", help="Use local GPU pipeline instead of API"
    )
    parser.add_argument("--skip-validation", action="store_true", help="Skip quality validation")
    parser.add_argument(
        "--regenerate-clip",
        type=str,
        default=None,
        help="Path to clip to regenerate (preserving first/last frames)",
    )
    parser.add_argument(
        "--improvement-prompt",
        type=str,
        default=None,
        help="Improvement prompt for clip regeneration",
    )
    args = parser.parse_args()

    # Also check VIDEO_EXEC_LOCAL env var (set by admin UI)
    if os.environ.get("VIDEO_EXEC_LOCAL") == "1":
        args.local = True

    # Handle clip regeneration mode
    if args.regenerate_clip:
        clip_path = Path(args.regenerate_clip)
        if not clip_path.exists():
            log.error(f"Clip not found: {clip_path}")
            sys.exit(1)
        try:
            regen_path = regenerate_clip(
                original_clip=clip_path,
                improvement_prompt=args.improvement_prompt,
                model=args.model,
                quality=args.quality,
                seed=args.seed,
                local=args.local,
                story_slug=args.story,
            )
            log.info(f"Regenerated clip: {regen_path}")
            print(f"Regenerated clip saved: {regen_path}")
        except Exception as e:
            log.error(f"Clip regeneration failed: {e}")
            sys.exit(1)
        return

    if not args.scene and not args.episode:
        parser.error("Either --scene, --episode, or --regenerate-clip is required")

    # Set CONTENT_LANGUAGE from story if available (so LLM skill loading uses correct language)
    if args.story and not os.environ.get("CONTENT_LANGUAGE"):
        lang = get_story_language(args.story)
        os.environ["CONTENT_LANGUAGE"] = lang
        if lang != "en":
            log.info(f"Content language set to: {lang}")

    # If --episode is given, find all scene prompts and process them
    if args.episode and not args.scene:
        from common import episode_dir

        ep_dir = episode_dir(args.episode, args.story)
        scenes_dir = ep_dir / "scenes"

        # Use selected scenes run dir from env (passed by admin UI)
        selected_scenes_run = os.environ.get("SELECTED_SCENES_DIR")
        if selected_scenes_run:
            run_dir = scenes_dir / selected_scenes_run
            if run_dir.exists():
                log.info(f"Using selected scenes run: {selected_scenes_run}")
                scenes_dir = run_dir
            else:
                log.warning(f"Selected scenes run dir not found: {run_dir}, falling back to latest")
                selected_scenes_run = None

        # If no env override, use the latest timestamped subfolder
        if not selected_scenes_run and scenes_dir.exists():
            subdirs = sorted([d for d in scenes_dir.iterdir() if d.is_dir()], reverse=True)
            if subdirs:
                scenes_dir = subdirs[0]
                log.info(f"Using latest scenes run: {scenes_dir.name}")

        if not scenes_dir.exists():
            log.info(f"No scenes directory at {scenes_dir}, creating placeholder")
            scenes_dir.mkdir(parents=True, exist_ok=True)
            log.info("Video generation complete (no scene prompts found yet)")
            return
        import re

        def _natural_sort_key(p: Path) -> list:
            """Sort filenames naturally: scene_1 < scene_2 < scene_10."""
            return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", p.name)]

        prompts = sorted(scenes_dir.glob("*_prompt.yaml"), key=_natural_sort_key)
        if not prompts:
            log.info(f"No scene prompts found in {scenes_dir}")
            log.info("Video generation complete (no scene prompts found yet)")
            return

        # Determine output dir for clips
        clips_dir = ep_dir / "clips"
        clips_run_dir = clips_dir / scenes_dir.name
        clips_run_dir.mkdir(parents=True, exist_ok=True)

        config = load_config()
        model = args.model or os.environ.get("VIDEO_MODEL") or config["model"]["name"]
        quality = args.quality or os.environ.get("VIDEO_QUALITY") or config["generation"]["quality"]
        seed = args.seed or config["generation"].get("seed")
        retry_config = config.get("retry", {})
        max_attempts = retry_config.get("max_attempts", 3)
        backoff = retry_config.get("backoff_seconds", 10)

        # Cost protection: limit retries for expensive cloud models
        resolved = resolve_model_id(model)
        is_expensive_model = resolved in BYTEPLUS_MODELS or "seedance" in model.lower()
        if is_expensive_model:
            max_attempts = min(max_attempts, 1)  # Never auto-retry expensive models
            log.info(
                f"Cost protection: max_attempts capped to {max_attempts} for expensive model {resolved}"
            )

        log.info(
            f"Generating {len(prompts)} clips (model={resolve_model_id(model)}, quality={quality})"
        )
        log.info(f"Clips output: {clips_run_dir}")

        prev_clip_path: Path | None = None
        prev_clip_description: str | None = None  # Carry forward for environment anchoring
        prev_clip_environment: str | None = None  # Carry location/setting for continuity
        prev_clip_action: str | None = None  # Carry last action/posture for continuity
        prev_clip_transition_out: str | None = (
            None  # Exact ending state for next clip's first frame
        )
        generated_count = 0

        # Stop file: checked between each clip to allow graceful termination
        run_id = os.environ.get("GENERATION_RUN_ID")
        stop_file = Path(".stop") / f"{run_id}.stop" if run_id else None

        # Write PID file so the stop route can always find and kill this process
        pid_file = None
        if run_id:
            pid_dir = Path(".stop")
            pid_dir.mkdir(parents=True, exist_ok=True)
            pid_file = pid_dir / f"{run_id}.pid"
            pid_file.write_text(str(os.getpid()), encoding="utf-8")
            log.info(f"  PID file written: {pid_file} (pid={os.getpid()})")

        def _check_stop() -> None:
            """Raise SystemExit if stop signal detected. Call before expensive operations."""
            if stop_file and stop_file.exists():
                log.info(f"Stop signal detected ({stop_file}). Halting video generation.")
                stop_file.unlink(missing_ok=True)
                if pid_file:
                    pid_file.unlink(missing_ok=True)
                sys.exit(1)

        for prompt_path in prompts:
            # Check for stop signal before each clip generation
            _check_stop()

            prompt_data = load_scene_prompt(str(prompt_path))
            output_name = prompt_path.stem.replace("_prompt", "") + ".mp4"
            output_path = clips_run_dir / output_name

            # Cost protection: skip if clip already exists with reasonable file size
            min_clip_size = config.get("cost_protection", {}).get("min_clip_size_bytes", 50_000)
            if output_path.exists() and output_path.stat().st_size >= min_clip_size:
                log.info(
                    f"[{generated_count + 1}/{len(prompts)}] Skipping {output_name} — already exists ({output_path.stat().st_size / 1024:.0f} KB)"
                )
                prev_clip_path = output_path
                prev_clip_description = (
                    prompt_data.get("description")
                    or prompt_data.get("prompt")
                    or prompt_data.get("subject", "")
                )
                prev_clip_environment = prompt_data.get("environment", "")
                prev_clip_action = prompt_data.get("action", "")
                prev_clip_transition_out = prompt_data.get("transition_out", "")
                generated_count += 1
                continue

            # Cost protection: lock file to prevent concurrent generation of the same clip
            lock_file = output_path.parent / f"{output_path.stem}.lock"
            if lock_file.exists():
                lock_age = time.time() - lock_file.stat().st_mtime
                if lock_age < 600:  # Lock valid for 10 minutes
                    log.warning(
                        f"[{generated_count + 1}/{len(prompts)}] Skipping {output_name} — generation in progress (lock age: {lock_age:.0f}s)"
                    )
                    continue
                else:
                    log.warning(f"  Stale lock file ({lock_age:.0f}s old), removing and proceeding")
                    lock_file.unlink(missing_ok=True)
            try:
                lock_file.write_text(str(os.getpid()), encoding="utf-8")
            except OSError:
                pass

            # Inject continuity: use API-provided last_frame_url, fall back to cv2 extraction
            if prev_clip_path and prev_clip_path.exists() and prev_clip_path.stat().st_size > 1000:
                # Prefer API-provided last frame URL (exact pixel match, no re-encoding)
                lf_url_file = prev_clip_path.parent / f"{prev_clip_path.stem}_last_frame_url.txt"
                if lf_url_file.exists():
                    lf_url = lf_url_file.read_text(encoding="utf-8").strip()
                    if lf_url:
                        prompt_data["_last_frame_url"] = lf_url
                        prompt_data["_reference_mode"] = "image"
                        log.info(
                            f"  Continuity: using API last_frame_url from {prev_clip_path.name}"
                        )
                else:
                    # Fallback: extract last frame locally with cv2
                    last_frame = extract_last_frame(prev_clip_path)
                    if last_frame and last_frame.exists():
                        prompt_data["reference_video"] = str(last_frame)
                        prompt_data["_reference_mode"] = "image"
                        log.info(
                            f"  Continuity: last frame extracted from {prev_clip_path.name} -> {last_frame.name}"
                        )
                    else:
                        log.warning(
                            f"  Continuity: failed to extract last frame from {prev_clip_path.name}"
                        )
                if prev_clip_description:
                    prompt_data["_prev_clip_description"] = prev_clip_description
                if prev_clip_environment:
                    prompt_data["_prev_clip_environment"] = prev_clip_environment
                if prev_clip_action:
                    prompt_data["_prev_clip_action"] = prev_clip_action
                if prev_clip_transition_out:
                    prompt_data["_prev_clip_transition_out"] = prev_clip_transition_out
                log.info(
                    f"  Continuity: referencing previous clip {prev_clip_path.name} ({prev_clip_path.stat().st_size / 1024:.0f} KB)"
                )
            elif prev_clip_path:
                log.warning(f"  Continuity skipped: {prev_clip_path.name} missing or too small")

            # Inject character visual context and animated style into the prompt
            _inject_character_context(prompt_data, args.story)
            _inject_animation_style(prompt_data)

            log.info(f"[{generated_count + 1}/{len(prompts)}] Generating: {output_name}")

            success = False
            for attempt in range(1, max_attempts + 1):
                _check_stop()  # Check before each attempt (especially important for retries)
                try:
                    generate_video(prompt_data, model, quality, seed, output_path, local=args.local)
                    success = True
                    break
                except Exception as e:
                    log.error(f"  Generation failed (attempt {attempt}/{max_attempts}): {e}")
                    if attempt < max_attempts:
                        log.info(f"  Retrying in {backoff}s...")
                        time.sleep(backoff)

            if not success:
                log.error(f"  All attempts failed for {output_name}. Stopping.")
                lock_file.unlink(missing_ok=True)
                sys.exit(1)

            # Quality validation (skip auto-regen for expensive models — flag for manual review)
            if not args.skip_validation and output_path.exists():
                if is_expensive_model:
                    from validate_quality import load_qa_config, validate_clip

                    qa_config = load_qa_config()
                    qa_result = validate_clip(output_path, qa_config)
                    if qa_result["passed"]:
                        log.info("  Quality check PASSED")
                    else:
                        log.warning(
                            "  Quality check FAILED (skipping auto-regen for expensive model):"
                        )
                        for issue in qa_result["issues"]:
                            log.warning(f"    - {issue}")
                        log.warning(
                            "  Flagged for manual review — re-run generate_clips step to retry."
                        )
                else:
                    _validate_and_regen(
                        output_path,
                        prompt_data,
                        model,
                        quality,
                        seed,
                        args.local,
                        scene_prompt_path=prompt_path,
                        story_slug=args.story,
                    )

            lock_file.unlink(missing_ok=True)

            prev_clip_path = output_path
            prev_clip_description = (
                prompt_data.get("description")
                or prompt_data.get("prompt")
                or prompt_data.get("subject", "")
            )
            prev_clip_environment = prompt_data.get("environment", "")
            prev_clip_action = prompt_data.get("action", "")
            prev_clip_transition_out = prompt_data.get("transition_out", "")
            generated_count += 1

        log.info(f"Video generation complete: {generated_count}/{len(prompts)} clips generated")
        log.info(f"Clips saved to {clips_run_dir}")

        # Clean up PID file on successful completion
        if pid_file:
            pid_file.unlink(missing_ok=True)
        return

    # Single scene mode (--scene <path>)
    config = load_config()
    prompt = load_scene_prompt(args.scene)

    model = args.model or os.environ.get("VIDEO_MODEL") or config["model"]["name"]
    quality = args.quality or os.environ.get("VIDEO_QUALITY") or config["generation"]["quality"]
    seed = args.seed or config["generation"].get("seed")

    # Determine output path: put videos in a separate 'clips' folder
    scene_path = Path(args.scene)
    output_name = scene_path.stem.replace("_prompt", "") + ".mp4"
    # Output to clips/<run_ts>/ next to scenes/<run_ts>/
    clips_dir = scene_path.parent.parent.parent / "clips"
    # Use same run timestamp as the scenes source
    clips_run_dir = clips_dir / scene_path.parent.name
    clips_run_dir.mkdir(parents=True, exist_ok=True)
    output_path = clips_run_dir / output_name

    # Inject character visual context and animated style
    _inject_character_context(prompt, args.story)
    _inject_animation_style(prompt)

    log.info(f"Generating clip: {output_name}")

    # Generate
    retry_config = config.get("retry", {})
    max_attempts = retry_config.get("max_attempts", 3)
    backoff = retry_config.get("backoff_seconds", 10)

    for attempt in range(1, max_attempts + 1):
        try:
            generate_video(prompt, model, quality, seed, output_path, local=args.local)
            break
        except Exception as e:
            log.error(f"Generation failed (attempt {attempt}/{max_attempts}): {e}")
            if attempt < max_attempts:
                log.info(f"Retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                log.error("All generation attempts failed.")
                sys.exit(1)

    log.info(f"Video saved to {output_path}")

    # Quality validation gate
    if not args.skip_validation and output_path.exists():
        from validate_quality import load_qa_config, validate_clip

        qa_config = load_qa_config()
        result = validate_clip(output_path, qa_config)
        if result["passed"]:
            log.info("Quality check PASSED")
        else:
            log.warning("Quality check FAILED:")
            for issue in result["issues"]:
                log.warning(f"  - {issue}")

            # Attempt regeneration
            regen_max = qa_config.get("on_failure", {}).get("max_regeneration_attempts", 3)
            for regen in range(1, regen_max + 1):
                log.info(f"Regenerating (attempt {regen}/{regen_max})...")
                try:
                    generate_video(prompt, model, quality, seed, output_path, local=args.local)
                except Exception as e:
                    log.error(f"Regeneration failed: {e}")
                    continue
                result = validate_clip(output_path, qa_config)
                if result["passed"]:
                    log.info(f"Quality check PASSED on regeneration attempt {regen}")
                    break
            else:
                log.error("Max regeneration attempts reached. Flagging for manual review.")
                sys.exit(1)


if __name__ == "__main__":
    main()
