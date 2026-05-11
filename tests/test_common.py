"""Tests for agents/common.py shared utilities."""

import pytest
from common import (
    PROJECT_ROOT,
    config_path,
    episode_dir,
    get_project_root,
    load_yaml,
    save_yaml,
    setup_logging,
)


def test_project_root_exists():
    """PROJECT_ROOT should point to a directory containing AGENTS.md."""
    assert PROJECT_ROOT.exists()
    assert (PROJECT_ROOT / "AGENTS.md").exists()


def test_get_project_root_returns_path():
    assert get_project_root() == PROJECT_ROOT


def test_config_path():
    """config_path should return absolute path under config/."""
    result = config_path("video_generation.yaml")
    assert result.is_absolute()
    assert result.name == "video_generation.yaml"
    assert "config" in str(result)


def test_episode_dir():
    """episode_dir should return data/episodes/<n> path."""
    result = episode_dir(5)
    assert result.name == "5"
    assert "episodes" in str(result)


def test_setup_logging():
    """setup_logging should return a configured logger."""
    logger = setup_logging("test_agent", level="DEBUG")
    assert logger.name == "test_agent"
    assert logger.level == 10  # DEBUG


def test_load_yaml_valid(tmp_path):
    """load_yaml should parse valid YAML files."""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text("key: value\nnested:\n  a: 1\n")
    result = load_yaml(yaml_file)
    assert result == {"key": "value", "nested": {"a": 1}}


def test_load_yaml_missing_file():
    """load_yaml should raise FileNotFoundError for missing files."""
    with pytest.raises(FileNotFoundError):
        load_yaml("/nonexistent/path/file.yaml")


def test_load_yaml_empty_file(tmp_path):
    """load_yaml should return empty dict for empty YAML."""
    yaml_file = tmp_path / "empty.yaml"
    yaml_file.write_text("")
    result = load_yaml(yaml_file)
    assert result == {}


def test_save_yaml(tmp_path):
    """save_yaml should write valid YAML and create directories."""
    output = tmp_path / "sub" / "dir" / "out.yaml"
    data = {"episode": 1, "scenes": [{"number": 1}]}
    result = save_yaml(data, output)
    assert result == output
    assert output.exists()
    # Verify round-trip
    loaded = load_yaml(output)
    assert loaded == data


def test_load_yaml_project_relative():
    """load_yaml with relative path should resolve against PROJECT_ROOT."""
    # This should load the actual story bible
    result = load_yaml("data/story_bible.yaml")
    assert "series" in result
