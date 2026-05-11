"""Episode State Tracking

Manages pipeline state for each episode, enabling resumability.
State is persisted to data/episodes/<n>/state.yaml.

Usage:
    from episode_state import EpisodeState

    state = EpisodeState(episode_number=1)
    state.start_step("generate_script")
    # ... do work ...
    state.complete_step("generate_script", result={"path": "script.yaml"})
"""

from datetime import UTC, datetime

from common import episode_dir, load_yaml, save_yaml, setup_logging

log = setup_logging("episode_state")

# Pipeline steps in execution order
PIPELINE_STEPS = [
    "collect_votes",
    "generate_script",
    "ethics_review",
    "scene_breakdown",
    "character_references",
    "generate_clips",
    "quality_gate_clips",
    "quality_gate_consistency",
    "add_audio",
    "pre_assembly_validation",
    "compose_episode",
    "post_assembly_validation",
    "final_review",
    "publish",
]

# Valid state transitions
STEP_STATUSES = ["not_started", "in_progress", "completed", "failed", "skipped"]


class EpisodeState:
    """Manages the pipeline state for a single episode."""

    def __init__(self, episode_number: int):
        self.episode_number = episode_number
        self.state_path = episode_dir(episode_number) / "state.yaml"
        self._state = self._load_or_create()

    def _load_or_create(self) -> dict:
        """Load existing state or create a fresh one."""
        if self.state_path.exists():
            state = load_yaml(self.state_path)
            if state:
                log.info(f"Loaded existing state for Episode {self.episode_number}")
                return state

        # Initialize fresh state
        state = {
            "episode": self.episode_number,
            "status": "not_started",
            "created_at": _now(),
            "updated_at": _now(),
            "current_step": None,
            "steps": {step: {"status": "not_started"} for step in PIPELINE_STEPS},
            "artifacts": {},
            "errors": [],
        }
        self._save(state)
        log.info(f"Created new state for Episode {self.episode_number}")
        return state

    def _save(self, state: dict | None = None) -> None:
        """Persist state to disk."""
        if state is None:
            state = self._state
        state["updated_at"] = _now()
        save_yaml(state, self.state_path)

    @property
    def status(self) -> str:
        """Overall episode status."""
        return self._state["status"]

    @property
    def current_step(self) -> str | None:
        """Currently active pipeline step."""
        return self._state["current_step"]

    def start_step(self, step: str) -> None:
        """Mark a pipeline step as in-progress."""
        if step not in PIPELINE_STEPS:
            raise ValueError(f"Unknown step: {step}. Valid: {PIPELINE_STEPS}")

        self._state["steps"][step] = {
            "status": "in_progress",
            "started_at": _now(),
        }
        self._state["current_step"] = step
        self._state["status"] = "in_progress"
        self._save()
        log.info(f"Step started: {step}")

    def complete_step(self, step: str, result: dict | None = None) -> None:
        """Mark a pipeline step as completed."""
        if step not in PIPELINE_STEPS:
            raise ValueError(f"Unknown step: {step}")

        self._state["steps"][step]["status"] = "completed"
        self._state["steps"][step]["completed_at"] = _now()
        if result:
            self._state["steps"][step]["result"] = result
            # Also store in artifacts for easy lookup
            self._state["artifacts"][step] = result

        # Advance current_step to next incomplete step
        self._state["current_step"] = self._next_incomplete_step()

        # Check if all steps are done
        if self._all_done():
            self._state["status"] = "completed"
            self._state["completed_at"] = _now()

        self._save()
        log.info(f"Step completed: {step}")

    def fail_step(self, step: str, error: str) -> None:
        """Mark a step as failed with error details."""
        if step not in PIPELINE_STEPS:
            raise ValueError(f"Unknown step: {step}")

        self._state["steps"][step]["status"] = "failed"
        self._state["steps"][step]["failed_at"] = _now()
        self._state["steps"][step]["error"] = error
        self._state["status"] = "failed"
        self._state["errors"].append({"step": step, "error": error, "at": _now()})
        self._save()
        log.error(f"Step failed: {step} -- {error}")

    def skip_step(self, step: str, reason: str = "") -> None:
        """Mark a step as skipped."""
        if step not in PIPELINE_STEPS:
            raise ValueError(f"Unknown step: {step}")

        self._state["steps"][step] = {"status": "skipped", "reason": reason}
        self._save()
        log.info(f"Step skipped: {step} ({reason})")

    def get_step_status(self, step: str) -> str:
        """Get the status of a specific step."""
        return self._state["steps"].get(step, {}).get("status", "unknown")

    def get_resume_point(self) -> str | None:
        """
        Find the step to resume from.
        Returns the first step that is not completed/skipped.
        """
        for step in PIPELINE_STEPS:
            status = self.get_step_status(step)
            if status in ("not_started", "in_progress", "failed"):
                return step
        return None

    def get_artifact(self, step: str) -> dict | None:
        """Get the artifact/result from a completed step."""
        return self._state.get("artifacts", {}).get(step)

    def reset_step(self, step: str) -> None:
        """Reset a step back to not_started (for retries)."""
        if step not in PIPELINE_STEPS:
            raise ValueError(f"Unknown step: {step}")
        self._state["steps"][step] = {"status": "not_started"}
        self._save()
        log.info(f"Step reset: {step}")

    def reset_from(self, step: str) -> None:
        """Reset this step and all subsequent steps (for partial re-runs)."""
        found = False
        for s in PIPELINE_STEPS:
            if s == step:
                found = True
            if found:
                self._state["steps"][s] = {"status": "not_started"}
        self._state["status"] = "in_progress"
        self._state["current_step"] = step
        self._save()
        log.info(f"Reset pipeline from step: {step}")

    def summary(self) -> dict:
        """Get a summary of the episode state."""
        completed = sum(
            1
            for s in PIPELINE_STEPS
            if self._state["steps"][s]["status"] in ("completed", "skipped")
        )
        return {
            "episode": self.episode_number,
            "status": self._state["status"],
            "progress": f"{completed}/{len(PIPELINE_STEPS)}",
            "current_step": self._state["current_step"],
            "resume_point": self.get_resume_point(),
        }

    def _next_incomplete_step(self) -> str | None:
        """Find the next step that isn't completed or skipped."""
        for step in PIPELINE_STEPS:
            status = self._state["steps"][step]["status"]
            if status not in ("completed", "skipped"):
                return step
        return None

    def _all_done(self) -> bool:
        """Check if all pipeline steps are completed or skipped."""
        return all(
            self._state["steps"][s]["status"] in ("completed", "skipped") for s in PIPELINE_STEPS
        )


def _now() -> str:
    """Current UTC timestamp as ISO string."""
    return datetime.now(UTC).isoformat()
