# Project Guidelines

## Overview

AI agent team for generating interactive episodic animated short videos with audience-driven narrative choices.

## Architecture

```
agents/              → Python agent scripts (video gen, composition, publishing)
.claude/agents/      → Chat agents (.agent.md for VS Code Copilot)
.claude/skills/      → Skills (on-demand workflows for chat agents)
mcp/                 → MCP server implementations
tools/               → CLI tools and standalone scripts
config/              → Environment configs and connection settings
docs/                → Documentation
site/                → Next.js website (episodes, voting, gallery)
data/                → Episode data (story bible, scripts, assets)
```

## Agent Types

| | Python Agents (`agents/`) | Chat Agents (`.claude/agents/`) |
|---|---|---|
| **What** | Executable Python scripts | VS Code Copilot personas |
| **Format** | `.py` files | `.agent.md` (Markdown + YAML frontmatter) |
| **Config** | Matching YAML in `config/` | Self-contained in frontmatter |
| **Run via** | `python agents/<name>.py` | `@agent-name` in Copilot chat |
| **Use case** | Automation, CI, API calls | Interactive planning in editor |

### Python Agents
- `generate_episode.py` — Orchestrates full episode generation
- `generate_video.py` — Calls HuggingFace models for video generation
- `validate_quality.py` — Quality assurance checks at clip, scene, and episode levels
- `compose_episode.py` — Stitches scene clips into final episode
- `publish_site.py` — Deploys episode + poll to Next.js site
- `tally_votes.py` — Collects and summarizes audience votes

### Chat Agents
- `@showrunner` — Orchestrates pipeline, tracks episode state
- `@writer` — Story bible, scripts, vote incorporation
- `@director` — Scene planning, visual prompts, shot composition
- `@character-designer` — Character visual consistency
- `@artist` — Video generation via HuggingFace
- `@sound-designer` — Audio layers (music, SFX, narration)
- `@editor` — Post-production assembly
- `@publisher` — Website deployment and polls
- `@community-manager` — Audience engagement

## Build and Test

```bash
pip install -r requirements.txt        # Install dependencies
cp config/.env.example config/.env     # Configure environment
pytest                                 # Run tests
python agents/generate_episode.py --episode 1  # Generate episode
```

## Conventions

- One agent per file in `agents/`, with a matching config in `config/`
- All HuggingFace/API connections configured via `config/` (never hardcoded)
- Secrets in `.env` files — never committed to version control
- Episode assets organized in `data/episodes/<episode_number>/`
- Character references in `data/characters/`
- Story bible maintained in `data/story_bible.yaml`

## Key Patterns

- **Adding an agent**: Create definition in `agents/` + config in `config/`
- **Adding a skill**: Create `.claude/skills/<name>/SKILL.md`
- **New episode**: Writer script → Director scenes → Artist generation → Quality gates → Editor assembly → Publish
- **Quality assurance**: `validate_quality.py` runs at 4 levels (clip → consistency → scene → episode)
- **Failure recovery**: Regenerate clip (3x) → revise prompt (@director) → simplify scene
- **Composability**: Agents reuse existing tools; prefer composition over duplication
