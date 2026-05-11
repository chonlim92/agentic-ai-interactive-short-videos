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


def test_generate_script_with_votes():
    """Should incorporate vote winner into script."""
    bible = {"series": {"title": "Test"}}
    votes = {"winner": "Option B", "total_votes": 100}
    script = generate_script(2, bible, votes)
    assert script["episode"] == 2
    assert script["based_on_vote"] == "Option B"
