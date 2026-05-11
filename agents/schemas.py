"""Configuration schemas for validation.

Uses Pydantic to validate YAML configs at load time, catching
typos, missing fields, and invalid values before they cause runtime errors.
"""

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Video Generation Config Schema
# ---------------------------------------------------------------------------


class ModelConfig(BaseModel):
    name: str
    provider: str
    fallback: str
    execution: str = "cloud"


class EpisodeConfig(BaseModel):
    target_duration_seconds: int = Field(ge=30, le=600)
    scenes_per_episode: str  # "8-12" format


class GenerationConfig(BaseModel):
    fps: int = Field(ge=1, le=60)
    width: int = Field(ge=128, le=3840)
    height: int = Field(ge=128, le=3840)
    aspect_ratio: str = "16:9"
    clip_duration_seconds: int = Field(ge=1, le=30)
    quality: str = Field(pattern=r"^(draft|standard|high)$")
    seed: int | None = None


class StitchingConfig(BaseModel):
    enabled: bool
    clips_per_scene: str  # "3-5" format
    overlap_frames: int = Field(ge=0)
    continuity_mode: bool
    style_lock: bool


class CrossEpisodeConfig(BaseModel):
    enabled: bool
    character_sheets: str
    location_sheets: str
    style_guide: str


class ConsistencyConfig(BaseModel):
    character_reference: bool
    scene_context_window: int = Field(ge=1)
    style_embedding: bool
    background_lock: bool
    lighting_lock: bool
    temporal_coherence: bool
    cross_episode: CrossEpisodeConfig


class OutputConfig(BaseModel):
    base_dir: str
    format: str
    naming: str


class RetryConfig(BaseModel):
    max_attempts: int = Field(ge=1, le=10)
    backoff_seconds: int = Field(ge=1)


class ClipValidationConfig(BaseModel):
    min_duration_seconds: float = Field(ge=0)
    max_duration_seconds: float = Field(ge=1)
    min_resolution: str
    min_fps: int = Field(ge=1)
    max_black_frame_ratio: float = Field(ge=0, le=1)
    max_static_frame_ratio: float = Field(ge=0, le=1)
    min_file_size_kb: int = Field(ge=1)
    content_policy_check: bool


class ConsistencyValidationConfig(BaseModel):
    color_drift_threshold: float = Field(ge=0, le=1)
    brightness_drift_threshold: float = Field(ge=0, le=1)
    character_presence_check: bool
    scene_continuity_check: bool
    continuity_similarity_min: float = Field(ge=0, le=1)


class SceneValidationConfig(BaseModel):
    min_clips_per_scene: int = Field(ge=1)
    target_duration_tolerance: float = Field(ge=0, le=1)
    all_clips_pass_quality: bool
    audio_sync_check: bool


class EpisodeValidationConfig(BaseModel):
    min_total_duration_seconds: int = Field(ge=1)
    max_total_duration_seconds: int = Field(ge=1)
    min_scenes: int = Field(ge=1)
    all_scenes_pass_quality: bool
    cross_scene_consistency: bool
    content_policy_final: bool
    audio_present: bool


class FailureActionConfig(BaseModel):
    clip: str
    consistency: str
    scene: str
    episode: str
    max_regeneration_attempts: int = Field(ge=1, le=10)


class QualityAssuranceConfig(BaseModel):
    clip_validation: ClipValidationConfig
    consistency_validation: ConsistencyValidationConfig
    scene_validation: SceneValidationConfig
    episode_validation: EpisodeValidationConfig
    on_failure: FailureActionConfig


class VideoGenerationFullConfig(BaseModel):
    model: ModelConfig
    episode: EpisodeConfig
    generation: GenerationConfig
    stitching: StitchingConfig
    consistency: ConsistencyConfig
    output: OutputConfig
    retry: RetryConfig
    quality_assurance: QualityAssuranceConfig


# ---------------------------------------------------------------------------
# Composition Config Schema
# ---------------------------------------------------------------------------


class IntroOutroConfig(BaseModel):
    enabled: bool
    duration_seconds: int = Field(ge=0)
    template: str


class TransitionConfig(BaseModel):
    between_clips: str
    between_scenes: str
    clip_transition_seconds: float = Field(ge=0)
    scene_transition_seconds: float = Field(ge=0)


class CompositionBlockConfig(BaseModel):
    intro: IntroOutroConfig
    outro: IntroOutroConfig
    transitions: TransitionConfig


class CompositionEpisodeConfig(BaseModel):
    target_duration_seconds: int = Field(ge=30)
    min_duration_seconds: int = Field(ge=1)
    max_duration_seconds: int = Field(ge=1)


class CompositionFullConfig(BaseModel):
    episode: CompositionEpisodeConfig
    composition: CompositionBlockConfig


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------


def validate_video_config(data: dict) -> VideoGenerationFullConfig:
    """Validate video generation config data against schema."""
    return VideoGenerationFullConfig.model_validate(data)


def validate_composition_config(data: dict) -> CompositionFullConfig:
    """Validate composition config data against schema."""
    return CompositionFullConfig.model_validate(data)
