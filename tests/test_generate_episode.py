"""Tests for agents/generate_episode.py."""

from generate_episode import generate_script, load_story_bible


def test_load_story_bible():
    """Should load the actual story bible from data/."""
    bible = load_story_bible()
    assert "series" in bible
    assert bible["series"]["episode_duration_seconds"] == 180


def test_generate_script_no_votes():
    """Should generate a valid script structure without vote data."""
    bible = {"series": {"title": "Test"}}
    script = generate_script(1, bible, None)
    assert script["episode"] == 1
    assert script["based_on_vote"] is None
    assert len(script["voting_options"]) == 3


def test_generate_script_with_votes():
    """Should incorporate vote winner into script."""
    bible = {"series": {"title": "Test"}}
    votes = {"winner": "Option B", "total_votes": 100}
    script = generate_script(2, bible, votes)
    assert script["episode"] == 2
    assert script["based_on_vote"] == "Option B"
