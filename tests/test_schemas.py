"""Tests for config schema validation via Pydantic."""

import pytest
from common import config_path, load_yaml
from pydantic import ValidationError
from schemas import validate_composition_config, validate_video_config


def test_video_generation_config_validates():
    """Full video_generation.yaml should pass schema validation."""
    data = load_yaml(config_path("video_generation.yaml"))
    config = validate_video_config(data)
    assert config.model.name == "hunyuanvideo"
    assert config.quality_assurance.clip_validation.min_fps == 20
    assert config.retry.max_attempts == 3


def test_composition_config_validates():
    """Full composition.yaml should pass schema validation."""
    data = load_yaml(config_path("composition.yaml"))
    config = validate_composition_config(data)
    assert config.episode.target_duration_seconds == 180
    assert config.composition.transitions.between_scenes == "crossfade"


def test_invalid_video_config_raises():
    """Invalid config should raise ValidationError."""
    bad_data = {
        "model": {"name": "test", "provider": "test", "fallback": "test"},
        "episode": {"target_duration_seconds": -1, "scenes_per_episode": "8-12"},
        "generation": {
            "fps": 0,
            "resolution": "720p",
            "clip_duration_seconds": 5,
            "quality": "bad",
        },
        "stitching": {
            "enabled": True,
            "clips_per_scene": "3-5",
            "overlap_frames": 8,
            "continuity_mode": True,
            "style_lock": True,
        },
        "consistency": {
            "character_reference": True,
            "scene_context_window": 3,
            "style_embedding": True,
            "background_lock": True,
            "lighting_lock": True,
            "temporal_coherence": True,
            "cross_episode": {
                "enabled": True,
                "character_sheets": "x",
                "location_sheets": "x",
                "style_guide": "x",
            },
        },
        "output": {"base_dir": "x", "format": "mp4", "naming": "x"},
        "retry": {"max_attempts": 3, "backoff_seconds": 10},
        "quality_assurance": {
            "clip_validation": {
                "min_duration_seconds": 2.5,
                "max_duration_seconds": 7.0,
                "min_resolution": "480p",
                "min_fps": 20,
                "max_black_frame_ratio": 0.15,
                "max_static_frame_ratio": 0.30,
                "min_file_size_kb": 100,
                "content_policy_check": True,
            },
            "consistency_validation": {
                "color_drift_threshold": 0.20,
                "brightness_drift_threshold": 0.15,
                "character_presence_check": True,
                "scene_continuity_check": True,
                "continuity_similarity_min": 0.70,
            },
            "scene_validation": {
                "min_clips_per_scene": 2,
                "target_duration_tolerance": 0.25,
                "all_clips_pass_quality": True,
                "audio_sync_check": True,
            },
            "episode_validation": {
                "min_total_duration_seconds": 150,
                "max_total_duration_seconds": 210,
                "min_scenes": 6,
                "all_scenes_pass_quality": True,
                "cross_scene_consistency": True,
                "content_policy_final": True,
                "audio_present": True,
            },
            "on_failure": {
                "clip": "regenerate",
                "consistency": "regenerate",
                "scene": "block",
                "episode": "block",
                "max_regeneration_attempts": 3,
            },
        },
    }
    with pytest.raises(ValidationError):
        validate_video_config(bad_data)
