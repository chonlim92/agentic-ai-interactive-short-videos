"""Tests for config file loading and schema validation."""

from common import config_path, load_yaml


def test_video_generation_config_structure():
    """video_generation.yaml should have all required top-level keys."""
    config = load_yaml(config_path("video_generation.yaml"))
    assert "model" in config
    assert "episode" in config
    assert "generation" in config
    assert "stitching" in config
    assert "consistency" in config
    assert "output" in config
    assert "retry" in config
    assert "quality_assurance" in config


def test_video_generation_model_config():
    """Model config should specify name and provider."""
    config = load_yaml(config_path("video_generation.yaml"))
    assert config["model"]["name"] == "hunyuanvideo"
    assert config["model"]["provider"] == "huggingface"
    assert "fallback" in config["model"]
    assert config["model"]["execution"] in ("cloud", "local")


def test_composition_config_structure():
    """composition.yaml should have required keys."""
    config = load_yaml(config_path("composition.yaml"))
    assert "episode" in config
    assert "composition" in config
    assert "audio" in config
    assert "export" in config
    assert config["episode"]["target_duration_seconds"] == 120


def test_publishing_config_structure():
    """publishing.yaml should have required keys."""
    config = load_yaml(config_path("publishing.yaml"))
    assert "site" in config
    assert "episode_page" in config
    assert "voting" in config
    assert "thumbnails" in config


def test_content_policy_config_structure():
    """content_policy.yaml should have required keys."""
    config = load_yaml(config_path("content_policy.yaml"))
    assert "policy" in config
    assert "prohibited" in config
    assert "allowed" in config
    assert "rating" in config
    assert "checkpoints" in config
    assert "negative_prompts" in config


def test_story_bible_consistency():
    """Story bible should match video generation config values."""
    bible = load_yaml("data/story_bible.yaml")
    video_config = load_yaml(config_path("video_generation.yaml"))
    bible_duration = bible["series"]["episode_duration_seconds"]
    config_duration = video_config["episode"]["target_duration_seconds"]
    assert bible_duration == config_duration
