"""Tests for agents/generate_episode.py."""

import pytest
from generate_episode import load_story_bible


def test_load_story_bible():
    """Should load the actual story bible from data/."""
    bible = load_story_bible("the-ancient-without-a-plug")
    assert "series" in bible


def test_load_story_bible_missing():
    """Should raise for nonexistent story."""
    with pytest.raises(SystemExit):
        load_story_bible("nonexistent-story")
