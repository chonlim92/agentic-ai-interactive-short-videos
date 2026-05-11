"""Shared utilities for all agents.

Provides: project root resolution, config/YAML loading, logging setup.
"""

import logging
import sys
from pathlib import Path

import yaml

# Project root is the parent of the agents/ directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_project_root() -> Path:
    """Return the absolute path to the project root directory."""
    return PROJECT_ROOT


def setup_logging(name: str, level: str = "INFO") -> logging.Logger:
    """Configure and return a logger for an agent.

    Args:
        name: Logger name (typically the agent script name).
        level: Log level (DEBUG, INFO, WARNING, ERROR).
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(
            open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False)
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


def load_env() -> None:
    """Load .env from config directory (CWD-independent)."""
    from dotenv import load_dotenv

    env_path = PROJECT_ROOT / "config" / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
    else:
        logging.getLogger("common").warning(
            f"No .env file found at {env_path}. Using environment variables only."
        )


def load_yaml(path: str | Path) -> dict:
    """Load a YAML file with error handling.

    Args:
        path: Absolute or project-relative path to YAML file.

    Returns:
        Parsed YAML content as dict.

    Raises:
        FileNotFoundError: If file does not exist.
        yaml.YAMLError: If file is not valid YAML.
    """
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved

    if not resolved.exists():
        raise FileNotFoundError(f"YAML file not found: {resolved}")

    with open(resolved, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML dict, got {type(data).__name__}: {resolved}")
    return data


def save_yaml(data: dict, path: str | Path) -> Path:
    """Save data to a YAML file, creating parent directories as needed.

    Args:
        data: Dictionary to serialize.
        path: Absolute or project-relative path.

    Returns:
        The resolved Path where the file was written.
    """
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved

    resolved.parent.mkdir(parents=True, exist_ok=True)
    with open(resolved, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    return resolved


def episode_dir(episode_number: int, story_slug: str | None = None) -> Path:
    """Return the data directory for a given episode number.

    If story_slug is provided, uses new structure: data/stories/<slug>/episodes/<num>
    Otherwise falls back to legacy: data/episodes/<num>
    """
    if story_slug:
        return PROJECT_ROOT / "data" / "stories" / story_slug / "episodes" / str(episode_number)
    return PROJECT_ROOT / "data" / "episodes" / str(episode_number)


def story_dir(story_slug: str) -> Path:
    """Return the data directory for a given story."""
    return PROJECT_ROOT / "data" / "stories" / story_slug


def config_path(filename: str) -> Path:
    """Return the absolute path to a config file."""
    return PROJECT_ROOT / "config" / filename


def fetch_story_from_api(story_slug: str) -> dict | None:
    """Fetch story data from the website API by slug.

    Tries the website API first (resilient to store.json deletion),
    then falls back to reading store.json directly.

    Returns the story dict or None if not found.
    """
    import json
    import os

    api_base = os.environ.get("SITE_API_URL", "http://localhost:3000")

    # Try website API first
    try:
        import urllib.request
        url = f"{api_base}/api/admin/stories/{story_slug}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # GET /api/admin/stories/[id] returns story fields directly
            if data and isinstance(data, dict) and data.get("slug"):
                return data
            # Or it may be nested under a key
            if data and isinstance(data, dict) and "story" in data:
                return data["story"]
    except Exception:
        pass

    # Fallback: read store.json directly
    store_path = PROJECT_ROOT / "site" / "data" / "store.json"
    try:
        if store_path.exists():
            store_data = json.loads(store_path.read_text(encoding="utf-8"))
            for s in store_data.get("stories", []):
                if s.get("slug") == story_slug:
                    return s
    except Exception:
        pass

    return None


def detect_content_language(text: str) -> str:
    """Detect the primary language of text based on character composition.

    Returns 'zh' for Chinese, 'en' for English.
    """
    if not text:
        return "en"
    cjk_count = sum(
        1 for ch in text if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf'
    )
    total_alpha = sum(1 for ch in text if ch.isalpha())
    if total_alpha == 0:
        return "en"
    return "zh" if cjk_count / total_alpha > 0.3 else "en"


def get_story_language(story_slug: str) -> str:
    """Get the story's primary language, caching the result in story_bible.yaml.

    Detection order:
    1. story_bible.yaml ``story_language`` field (cached from a prior call)
    2. Story ``background`` text from the website / store.json
    3. Script content of episode 1
    4. Fallback: ``CONTENT_LANGUAGE`` env var, or ``"en"``

    Once detected, the value is persisted as ``story_language`` in story_bible.yaml
    so that all subsequent pipeline steps use the same language without re-detecting.
    """
    import os
    s_dir = story_dir(story_slug)
    bible_path = s_dir / "story_bible.yaml"

    # 1. Check cached value in story_bible.yaml
    bible = {}
    if bible_path.exists():
        try:
            bible = load_yaml(str(bible_path))
        except Exception:
            bible = {}
    cached = bible.get("story_language")
    if cached and isinstance(cached, str):
        return cached

    # 2. Detect from story background (store.json / API)
    lang = None
    story_data = fetch_story_from_api(story_slug)
    if story_data:
        background = story_data.get("background", "")
        if background:
            lang = detect_content_language(background)

    # 3. Fallback: detect from episode 1 script
    if not lang or lang == "en":
        script_path = s_dir / "episodes" / "1" / "script.yaml"
        if script_path.exists():
            try:
                raw_text = script_path.read_text(encoding="utf-8")
                detected = detect_content_language(raw_text)
                if detected != "en":
                    lang = detected
            except Exception:
                pass

    # 4. Env-var fallback
    if not lang:
        lang = os.environ.get("CONTENT_LANGUAGE", "en")

    # Persist to story_bible.yaml
    bible["story_language"] = lang
    try:
        save_yaml(bible, str(bible_path))
    except Exception:
        pass

    return lang
