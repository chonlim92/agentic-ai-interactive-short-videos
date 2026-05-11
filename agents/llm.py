"""Shared LLM client for all agents.

Supports Anthropic (Claude) and OpenAI backends.
Reads .claude/agents/<name>.agent.md files as system prompts.
Injects project rules from CLAUDE.md and relevant skills.
Learns new skills automatically when agents encounter new task types.
"""

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

# Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
# Licensed under CC BY-NC 4.0. See LICENSE for details.

import os
import sys
import re
from pathlib import Path

import yaml

from common import get_project_root, setup_logging

log = setup_logging("llm")
PROJECT_ROOT = get_project_root()

# Base skill mapping — extended dynamically from skills_registry.yaml
_BASE_AGENT_SKILLS = {
    "writer": ["generate-episode"],
    "director": [],
    "character-designer": [],
    "artist": ["generate-scene-video", "validate-quality"],
    "sound-designer": [],
    "editor": ["compose-episode", "validate-quality"],
    "publisher": ["publish-episode"],
    "community-manager": ["tally-votes"],
}

SKILLS_REGISTRY_PATH = PROJECT_ROOT / "config" / "skills_registry.yaml"
NO_SKILL_MARKER = "\u26a0\ufe0f No matching skill found"


def load_skills_registry() -> dict:
    """Load the dynamic skills registry (learned skills)."""
    if not SKILLS_REGISTRY_PATH.exists():
        return {}
    try:
        with open(SKILLS_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data
    except Exception:
        return {}


def save_skills_registry(registry: dict) -> None:
    """Save the dynamic skills registry."""
    SKILLS_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SKILLS_REGISTRY_PATH, "w", encoding="utf-8") as f:
        yaml.dump(registry, f, default_flow_style=False, allow_unicode=True)


def get_agent_skills(agent_name: str) -> list[str]:
    """Get all skills for an agent (base + learned)."""
    base = list(_BASE_AGENT_SKILLS.get(agent_name, []))
    registry = load_skills_registry()
    learned = registry.get(agent_name, [])
    # Merge without duplicates
    for skill in learned:
        if skill not in base:
            base.append(skill)
    return base


def _detect_language(text: str) -> str:
    """Detect language of text: 'zh' for Chinese, 'en' otherwise."""
    if not text:
        return "en"
    cjk_count = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf')
    total_alpha = sum(1 for ch in text if ch.isalpha())
    if total_alpha == 0:
        return "en"
    return "zh" if cjk_count / total_alpha > 0.3 else "en"


def _get_content_language() -> str:
    """Get the current content language from env or default to 'en'."""
    return os.environ.get("CONTENT_LANGUAGE", "en")


def learn_new_skill(agent_name: str, task_summary: str, output_sample: str) -> str | None:
    """Create a language-specific SKILL.{lang}.md from a successful task.

    Skills are always saved per-language to avoid mixing languages in a single file.
    Returns the skill name if created, None if skipped.
    """
    # Detect language from output sample
    lang = _detect_language(output_sample)

    # Generate a skill name from the task summary (first 50 chars, slugified)
    slug = re.sub(r'[^a-z0-9]+', '-', task_summary[:60].lower()).strip('-')
    if not slug:
        slug = f"{agent_name}-learned"
    skill_name = f"{agent_name}-{slug}"

    skill_dir = PROJECT_ROOT / ".claude" / "skills" / skill_name
    skill_file = skill_dir / f"SKILL.{lang}.md"

    # Don't overwrite existing skills for this language
    if skill_file.exists():
        log.info(f"Skill already exists: {skill_name} ({lang})")
        return skill_name

    # Extract first 2000 chars of output as example format
    output_preview = output_sample[:2000]

    skill_content = f"""# {task_summary}

## Language
- This skill is for **{lang}** content only

## When to Use
- The task matches: "{task_summary}"
- Agent: @{agent_name}
- Content language: {lang}

## Learned From
- Auto-generated from a successful task execution
- Agent produced valid output without a pre-defined skill

## Output Format
The output should be valid YAML matching this structure:

```yaml
{output_preview}
```

## Procedure
1. Follow the instructions in the user prompt
2. Produce output in the YAML format shown above
3. Respond with ONLY valid YAML — no preamble, no markdown fences
4. ALL content must be in **{lang}** — do NOT mix languages
"""

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(skill_content, encoding="utf-8")
    log.info(f"Learned new skill: {skill_name} ({lang}) -> {skill_file}")

    # Register the skill for this agent
    registry = load_skills_registry()
    if agent_name not in registry:
        registry[agent_name] = []
    if skill_name not in registry[agent_name]:
        registry[agent_name].append(skill_name)
    save_skills_registry(registry)

    # Equip the agent.md with the new skill
    _equip_agent_with_skill(agent_name, skill_name)

    return skill_name


def _equip_agent_with_skill(agent_name: str, skill_name: str) -> None:
    """Add a skill reference to the agent's .agent.md frontmatter."""
    agent_path = PROJECT_ROOT / ".claude" / "agents" / f"{agent_name}.agent.md"
    if not agent_path.exists():
        log.warning(f"Cannot equip skill — agent file not found: {agent_path}")
        return

    content = agent_path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        log.warning(f"Agent file has no frontmatter: {agent_path}")
        return

    parts = content.split("---", 2)
    if len(parts) < 3:
        return

    frontmatter_text = parts[1]
    body = parts[2]

    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except Exception:
        log.warning(f"Could not parse frontmatter for {agent_name}")
        return

    # Add or update the skills list
    existing_skills = frontmatter.get("skills", [])
    if not isinstance(existing_skills, list):
        existing_skills = []
    if skill_name not in existing_skills:
        existing_skills.append(skill_name)
        frontmatter["skills"] = existing_skills

        new_frontmatter = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).strip()
        new_content = f"---\n{new_frontmatter}\n---{body}"
        agent_path.write_text(new_content, encoding="utf-8")
        log.info(f"Equipped {agent_name}.agent.md with skill: {skill_name}")


def load_agent_prompt(agent_name: str) -> str:
    """Load a .claude/agents/<name>.agent.md file and return the body (after frontmatter)."""
    agent_path = PROJECT_ROOT / ".claude" / "agents" / f"{agent_name}.agent.md"
    if not agent_path.exists():
        log.warning(f"Agent file not found: {agent_path}")
        return ""
    content = agent_path.read_text(encoding="utf-8")
    # Strip YAML frontmatter (between --- delimiters)
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content


def load_skill(skill_name: str) -> str:
    """Load a skill file, preferring the language-specific version.

    Looks for SKILL.{lang}.md first (based on CONTENT_LANGUAGE env),
    then falls back to SKILL.md for non-learned skills.
    """
    skill_dir = PROJECT_ROOT / ".claude" / "skills" / skill_name
    lang = _get_content_language()

    # Prefer language-specific file
    lang_path = skill_dir / f"SKILL.{lang}.md"
    if lang_path.exists():
        return lang_path.read_text(encoding="utf-8")

    # Fallback to generic SKILL.md (for pre-defined skills)
    generic_path = skill_dir / "SKILL.md"
    if generic_path.exists():
        return generic_path.read_text(encoding="utf-8")

    return ""


def load_project_rules() -> str:
    """Load key project rules from CLAUDE.md relevant to agent execution."""
    claude_path = PROJECT_ROOT / "CLAUDE.md"
    if not claude_path.exists():
        return ""
    content = claude_path.read_text(encoding="utf-8")
    return content


def load_content_policy() -> str:
    """Load content policy from config."""
    policy_path = PROJECT_ROOT / "config" / "content_policy.yaml"
    if not policy_path.exists():
        return ""
    return policy_path.read_text(encoding="utf-8")


def build_system_prompt(agent_name: str) -> str:
    """Build a complete system prompt for an agent, including:
    - The agent's own .agent.md instructions
    - Relevant skills from .claude/skills/
    - Project rules from CLAUDE.md (pipeline, quality, specs)
    - Content policy
    """
    parts = []

    # 1. Agent's own instructions (primary behavior)
    agent_instructions = load_agent_prompt(agent_name)
    if agent_instructions:
        parts.append(f"# Your Role and Instructions\n\n{agent_instructions}")

    # 2. Relevant skills (procedures to follow) — includes learned skills
    skills = get_agent_skills(agent_name)
    if skills:
        skill_texts = []
        for skill_name in skills:
            skill_content = load_skill(skill_name)
            if skill_content:
                skill_texts.append(f"### Skill: {skill_name}\n{skill_content}")
        if skill_texts:
            parts.append(f"# Available Skills (follow these procedures)\n\n" + "\n\n".join(skill_texts))

    # 3. Project rules (pipeline, video specs, quality requirements)
    project_rules = load_project_rules()
    if project_rules:
        parts.append(f"# Project Rules and Specifications\n\n{project_rules}")

    # 4. Content policy
    content_policy = load_content_policy()
    if content_policy:
        parts.append(f"# Content Policy (MUST follow)\n\n```yaml\n{content_policy}\n```")

    return "\n\n---\n\n".join(parts)


def call_llm(system_prompt: str, user_message: str, max_tokens: int = 8000, model_override: str | None = None) -> str:
    """Call the configured LLM provider and return raw text response.

    Uses LLM_PROVIDER env var to select backend (anthropic, openai, or huggingface).
    Uses LLM_MODEL env var for model selection.
    model_override: If provided, overrides both provider and model (format: "provider/model").

    Args:
        system_prompt: System instructions (e.g. agent .md body).
        user_message: The user prompt with context and instructions.
        max_tokens: Max response tokens.
        model_override: Optional "provider/model" string to override env config.

    Returns:
        Raw text response from the LLM.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    model = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")

    # Override from explicit parameter (e.g. from web UI model selection)
    if model_override:
        if "/" in model_override:
            provider, model = model_override.split("/", 1)
        else:
            model = model_override

    log.info(f"Calling {provider}/{model} (max_tokens={max_tokens})")

    if provider == "huggingface":
        return _call_huggingface(system_prompt, user_message, model, max_tokens)
    elif provider == "openai":
        import openai

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            log.error("OPENAI_API_KEY not set. Set it in config/.env.")
            sys.exit(1)
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content.strip()
    else:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            log.error("ANTHROPIC_API_KEY not set. Set it in config/.env.")
            sys.exit(1)
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()


def _call_huggingface(system_prompt: str, user_message: str, model: str, max_tokens: int) -> str:
    """Call HuggingFace Inference API with streaming to show progress."""
    import requests
    import json as _json

    api_token = os.environ.get("HUGGINGFACE_API_TOKEN", "")
    # HuggingFace Router API (OpenAI-compatible endpoint)
    api_url = "https://router.huggingface.co/v1/chat/completions"

    headers = {"Content-Type": "application/json"}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": max_tokens,
        "stream": True,
    }

    # Use session with retry for transient SSL errors
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[502, 503, 504],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    # (connect_timeout, read_timeout) — read_timeout is per-chunk, so no overall limit
    # as long as tokens keep streaming within 120s of each other
    response = session.post(api_url, headers=headers, json=payload, timeout=(30, 120), stream=True)
    if response.status_code != 200:
        error_text = response.text[:500]
        log.error(f"HuggingFace API error ({response.status_code}): {error_text}")
        raise RuntimeError(f"HuggingFace API returned {response.status_code}: {error_text[:200]}")

    # Force UTF-8 decoding (SSE/JSON is always UTF-8; requests may default to ISO-8859-1)
    response.encoding = "utf-8"

    # Determine if we need explicit UTF-8 buffer writes (for non-ASCII content on Windows)
    content_lang = os.environ.get("CONTENT_LANGUAGE", "en")
    use_binary_stdout = content_lang in ("zh", "ja", "ko", "th", "ar", "hi")

    # Stream tokens and print them as they arrive
    collected = []
    token_count = 0
    for raw_line in response.iter_lines():
        # Decode bytes as UTF-8 directly
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line:
            continue
        if not line.startswith("data: "):
            continue
        data_str = line[6:]  # strip "data: " prefix
        if data_str.strip() == "[DONE]":
            break
        try:
            chunk = _json.loads(data_str)
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content", "")
            if content:
                if use_binary_stdout:
                    sys.stdout.buffer.write(content.encode("utf-8"))
                    sys.stdout.buffer.flush()
                else:
                    print(content, end="", flush=True)
                collected.append(content)
                token_count += 1
        except (_json.JSONDecodeError, IndexError, KeyError):
            continue

    # Print newline after streaming completes
    if collected:
        if use_binary_stdout:
            sys.stdout.buffer.write(b"\n")
            sys.stdout.buffer.flush()
        else:
            print()
    log.info(f"Streamed {token_count} chunks, total {len(''.join(collected))} chars")
    return "".join(collected).strip()


def call_agent(agent_name: str, user_message: str, max_tokens: int = 8000, model_override: str | None = None) -> str:
    """Call an LLM using a named agent's full context as the system prompt.

    Includes: agent .agent.md instructions + relevant skills + project rules + content policy.
    If the agent signals 'no matching skill found', learns the new skill automatically.
    Automatically detects content language from user_message for skill loading.

    Args:
        agent_name: Name of the agent (e.g. 'writer', 'director').
        user_message: The task/context to send.
        max_tokens: Max response tokens.
        model_override: Optional "provider/model" to override env config.

    Returns:
        Raw text response.
    """
    # Auto-detect content language from user message (unless already set by caller)
    if not os.environ.get("CONTENT_LANGUAGE"):
        detected_lang = _detect_language(user_message)
        os.environ["CONTENT_LANGUAGE"] = detected_lang
        log.info(f"Auto-detected content language: {detected_lang}")

    system_prompt = build_system_prompt(agent_name)
    if not system_prompt:
        log.error(f"No agent prompt found for '{agent_name}'")
        sys.exit(1)
    log.info(f"Using agent: {agent_name} (with skills + project rules)")
    raw_response = call_llm(system_prompt, user_message, max_tokens, model_override=model_override)

    # Detect "no matching skill" signal and learn
    if NO_SKILL_MARKER in raw_response:
        log.info(f"Agent '{agent_name}' signaled no matching skill — attempting to learn...")
        # Extract a task summary from the first line of user_message
        first_line = user_message.strip().split("\n")[0][:80]
        # Try to parse the output to confirm it's valid before learning
        try:
            parsed = parse_yaml_response(raw_response)
            # Valid output — learn this as a new skill
            import yaml as _yaml
            output_sample = _yaml.dump(parsed, default_flow_style=False, allow_unicode=True)
            skill_name = learn_new_skill(agent_name, first_line, output_sample)
            if skill_name:
                log.info(f"Skill learned: {skill_name}")
        except (ValueError, Exception):
            # Can't parse — still return raw for the caller to handle
            log.warning("Could not learn skill (output not valid YAML)")

    return raw_response


def parse_yaml_response(raw_text: str) -> dict:
    """Parse YAML from LLM response, stripping markdown fences and preamble.

    Returns:
        Parsed dict.

    Raises:
        ValueError: If parsing fails.
    """
    import re
    import yaml

    text = raw_text.strip()

    # If the response contains a ```yaml ... ``` block, extract just that
    fence_match = re.search(r"```(?:yaml|yml)?\s*\n(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    elif text.startswith("```"):
        # Fallback: strip first/last lines if they're fences
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    else:
        # No fences — strip any preamble lines before the first YAML key
        # A YAML key line looks like: word: or word:\n or - item
        lines = text.split("\n")
        start_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            # A valid YAML start: top-level key (word:) or list item (- )
            if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*\s*:', stripped) or stripped.startswith('- '):
                start_idx = i
                break
        if start_idx > 0:
            text = "\n".join(lines[start_idx:])

    # First attempt: parse as-is
    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except yaml.YAMLError:
        pass

    # Second attempt: fix common LLM YAML issues
    text = _repair_yaml(text)
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"LLM output is not a YAML dict, got {type(data).__name__}")
    return data


def call_vlm(
    system_prompt: str,
    user_text: str,
    images: list["Path | str"],
    max_tokens: int = 4000,
    model_override: str | None = None,
) -> str:
    """Call a vision-language model with images + text.

    Uses OpenAI's gpt-4o by default (supports image input).
    Images can be file paths (will be base64-encoded) or data URIs.

    Args:
        system_prompt: System instructions.
        user_text: Text prompt to accompany the images.
        images: List of image file paths or data URIs.
        max_tokens: Max response tokens.
        model_override: Optional "provider/model" override.

    Returns:
        Raw text response from the VLM.
    """
    import base64

    provider = "openai"
    model = "gpt-4o"
    if model_override:
        if "/" in model_override:
            provider, model = model_override.split("/", 1)
        else:
            model = model_override

    log.info(f"Calling VLM {provider}/{model} with {len(images)} images (max_tokens={max_tokens})")

    # Build multimodal content array
    content: list[dict] = []

    # Add images first
    for img in images:
        img_path = Path(img) if not str(img).startswith("data:") else None
        if img_path and img_path.exists():
            ext = img_path.suffix.lower().lstrip(".")
            if ext == "jpg":
                ext = "jpeg"
            b64 = base64.b64encode(img_path.read_bytes()).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/{ext};base64,{b64}", "detail": "low"},
            })
        elif str(img).startswith("data:"):
            content.append({
                "type": "image_url",
                "image_url": {"url": str(img), "detail": "low"},
            })

    # Add text prompt
    content.append({"type": "text", "text": user_text})

    if provider == "openai":
        import openai

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            log.error("OPENAI_API_KEY not set for VLM call.")
            sys.exit(1)
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
        )
        return response.choices[0].message.content.strip()
    else:
        # Fallback: text-only call (non-OpenAI providers may not support images)
        log.warning(f"VLM provider '{provider}' may not support images. Falling back to text-only.")
        return call_llm(system_prompt, user_text, max_tokens, model_override=model_override)


def _repair_yaml(text: str) -> str:
    """Attempt to fix common YAML formatting issues from LLM output."""
    import re

    lines = text.split("\n")
    fixed_lines = []
    for line in lines:
        # Match lines like:  key: value (where value contains unquoted special chars)
        # Only fix value lines (not keys that start list items or nested dicts)
        m = re.match(r'^(\s*(?:-\s+)?[a-zA-Z_][a-zA-Z0-9_]*:\s*)(.+)$', line)
        if m:
            prefix, value = m.group(1), m.group(2)
            # Skip if already quoted, is a number, bool, null, or starts a nested structure
            stripped_val = value.strip()
            if (stripped_val.startswith('"') or stripped_val.startswith("'") or
                stripped_val.startswith('[') or stripped_val.startswith('{') or
                stripped_val in ('true', 'false', 'null', 'yes', 'no', '~', '') or
                re.match(r'^-?\d+(\.\d+)?$', stripped_val) or
                stripped_val.startswith('|') or stripped_val.startswith('>')):
                fixed_lines.append(line)
            else:
                # Quote the value to avoid YAML parsing issues
                escaped = stripped_val.replace('\\', '\\\\').replace('"', '\\"')
                fixed_lines.append(f'{prefix}"{escaped}"')
        else:
            fixed_lines.append(line)
    return "\n".join(fixed_lines)
