"""Tests for episode state tracking and resumability."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))
from episode_state import PIPELINE_STEPS, EpisodeState


@pytest.fixture
def state(tmp_path, monkeypatch):
    """Create an EpisodeState with a temp directory."""
    monkeypatch.setattr("episode_state.episode_dir", lambda n: tmp_path / f"ep{n}")
    return EpisodeState(episode_number=99)


def test_initial_state(state):
    """Fresh state should be not_started with no current step."""
    assert state.status == "not_started"
    assert state.current_step is None


def test_start_step(state):
    """Starting a step updates status and current_step."""
    state.start_step("generate_script")
    assert state.status == "in_progress"
    assert state.current_step == "generate_script"
    assert state.get_step_status("generate_script") == "in_progress"


def test_complete_step(state):
    """Completing a step stores result and advances current_step."""
    state.start_step("collect_votes")
    state.complete_step("collect_votes", result={"winner": "option_a"})
    assert state.get_step_status("collect_votes") == "completed"
    assert state.get_artifact("collect_votes") == {"winner": "option_a"}
    # Should advance to next step
    assert state.current_step == "generate_script"


def test_fail_step(state):
    """Failing a step records error and sets status to failed."""
    state.start_step("generate_script")
    state.fail_step("generate_script", "API error")
    assert state.status == "failed"
    assert state.get_step_status("generate_script") == "failed"


def test_skip_step(state):
    """Skipping a step records reason."""
    state.skip_step("collect_votes", "First episode, no votes")
    assert state.get_step_status("collect_votes") == "skipped"


def test_resume_point(state):
    """Resume point should be first non-completed step."""
    state.skip_step("collect_votes", "no votes")
    state.start_step("generate_script")
    state.complete_step("generate_script")
    assert state.get_resume_point() == "ethics_review"


def test_reset_from(state):
    """Reset from a step should clear it and all subsequent steps."""
    state.skip_step("collect_votes")
    state.start_step("generate_script")
    state.complete_step("generate_script")
    state.start_step("ethics_review")
    state.complete_step("ethics_review")

    state.reset_from("generate_script")
    assert state.get_step_status("generate_script") == "not_started"
    assert state.get_step_status("ethics_review") == "not_started"
    assert state.get_step_status("collect_votes") == "skipped"  # Before reset point


def test_summary(state):
    """Summary should show progress correctly."""
    state.skip_step("collect_votes")
    state.start_step("generate_script")
    state.complete_step("generate_script")
    summary = state.summary()
    assert summary["episode"] == 99
    assert summary["progress"] == f"2/{len(PIPELINE_STEPS)}"
    assert summary["resume_point"] == "ethics_review"


def test_state_persists(tmp_path, monkeypatch):
    """State should survive being reloaded from disk."""
    monkeypatch.setattr("episode_state.episode_dir", lambda n: tmp_path / f"ep{n}")

    state1 = EpisodeState(episode_number=1)
    state1.start_step("collect_votes")
    state1.complete_step("collect_votes", result={"winner": "B"})

    # Reload from disk
    state2 = EpisodeState(episode_number=1)
    assert state2.get_step_status("collect_votes") == "completed"
    assert state2.get_artifact("collect_votes") == {"winner": "B"}


def test_invalid_step_raises(state):
    """Invalid step names should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown step"):
        state.start_step("nonexistent_step")
