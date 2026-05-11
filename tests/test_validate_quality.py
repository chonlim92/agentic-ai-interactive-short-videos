"""Tests for agents/validate_quality.py."""

from pathlib import Path

from validate_quality import load_qa_config, validate_clip


def test_load_qa_config():
    """Should load quality assurance config from video_generation.yaml."""
    config = load_qa_config()
    assert "clip_validation" in config
    assert "consistency_validation" in config
    assert "scene_validation" in config
    assert "episode_validation" in config
    assert "on_failure" in config


def test_validate_clip_missing_file():
    """Should fail with clear message for non-existent file."""
    result = validate_clip(Path("/nonexistent/clip.mp4"), load_qa_config())
    assert result["passed"] is False
    assert "does not exist" in result["issues"][0]


def test_validate_clip_too_small(tmp_path):
    """Should fail if file is suspiciously small."""
    small_file = tmp_path / "tiny.mp4"
    small_file.write_bytes(b"\x00" * 50)  # 50 bytes, way under 100KB min
    config = load_qa_config()
    result = validate_clip(small_file, config)
    assert result["passed"] is False
    assert any(
        "too small" in issue.lower() or "File too small" in issue for issue in result["issues"]
    )


def test_qa_config_thresholds():
    """Verify config has sensible threshold values."""
    config = load_qa_config()
    clip = config["clip_validation"]
    assert clip["min_duration_seconds"] > 0
    assert clip["max_duration_seconds"] > clip["min_duration_seconds"]
    assert 0 < clip["max_black_frame_ratio"] < 1
    assert 0 < clip["max_static_frame_ratio"] < 1
    assert clip["min_file_size_kb"] > 0
