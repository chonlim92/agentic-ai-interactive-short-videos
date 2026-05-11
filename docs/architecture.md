# Architecture

**Author: Chong Kiat Lim**

## System Overview

StorySmith AI uses a **two-layer agent architecture** — interactive chat agents plan and orchestrate creative work, while Python automation agents execute the actual video generation, processing, and deployment. A full-featured admin web UI ties everything together.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         EPISODE PIPELINE                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────┐    ┌────────┐    ┌──────────┐    ┌────────┐              │
│  │ Audience │───►│ Writer │───►│ Director │───►│ Artist │              │
│  │  Votes   │    │(script)│    │ (scenes) │    │(video) │              │
│  └──────────┘    └────────┘    └──────────┘    └────────┘              │
│       ▲                              │               │                   │
│       │                     ┌────────▼────────┐     │                   │
│       │                     │ Character       │     │                   │
│       │                     │ Designer        │     │                   │
│       │                     └─────────────────┘     ▼                   │
│  ┌──────────┐    ┌──────────┐    ┌────────┐    ┌───────────┐          │
│  │Community │◄───│Publisher │◄───│ Editor │◄───│Sound      │          │
│  │ Manager  │    │ (deploy) │    │(assemble)   │Designer   │          │
│  └──────────┘    └──────────┘    └────────┘    └───────────┘          │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                        QUALITY GATES                                     │
├─────────────────────────────────────────────────────────────────────────┤
│  Gate 1: Per-clip (Artist)     → duration, fps, black/static frames     │
│  Gate 2: Consistency (Artist)  → color/brightness drift, SSIM           │
│  Gate 3: Pre-assembly (Editor) → all clips pass, scene completeness     │
│  Gate 4: Episode (Showrunner)  → total duration, audio, content policy  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Two-Layer Agent Architecture

### Layer 1: Chat Agents (`.claude/agents/`)

Interactive VS Code Copilot personas that plan and orchestrate work. They reason about creative decisions, delegate to Python agents for execution, and communicate with each other via the showrunner.

| Agent | File | Responsibility |
|-------|------|----------------|
| @showrunner | `showrunner.agent.md` | Pipeline orchestration, quality authority |
| @writer | `writer.agent.md` | Story bible, scripts, vote incorporation |
| @director | `director.agent.md` | Scene breakdowns, visual prompts |
| @character-designer | `character-designer.agent.md` | Visual consistency, reference sheets |
| @artist | `artist.agent.md` | Video generation via HuggingFace |
| @sound-designer | `sound-designer.agent.md` | Music, SFX, narration |
| @editor | `editor.agent.md` | Post-production assembly |
| @publisher | `publisher.agent.md` | Website deployment, polls |
| @community-manager | `community-manager.agent.md` | Audience engagement |

### Layer 2: Python Agents (`agents/`)

Executable scripts that perform actual work: calling APIs, processing video, composing episodes, deploying to web.

| Script | Purpose | Config |
|--------|---------|--------|
| `generate_episode.py` | Generate episode script from story bible + votes | — |
| `generate_video.py` | Call HuggingFace/BytePlus for clip generation | `video_generation.yaml` |
| `generate_audio.py` | Generate music and narration | `voice_library.yaml` |
| `validate_quality.py` | 4-level quality assurance checks | `video_generation.yaml` |
| `compose_episode.py` | Stitch clips into final episode | `composition.yaml` |
| `publish_site.py` | Deploy to Next.js site | `publishing.yaml` |
| `tally_votes.py` | Collect and summarize audience votes | — |

### Layer 3: Admin Web UI (`site/src/app/admin/`)

A full-featured admin panel built with Next.js that provides a visual interface for the entire pipeline — from story creation to episode generation, quality review, and publishing. See the [Admin Panel Guide](admin-panel.md) for full details.

### Shared Modules

| Module | Purpose |
|--------|---------|
| `agents/common.py` | Path helpers, YAML I/O, logging, env loading, language detection |
| `agents/llm.py` | LLM client (Anthropic Claude / OpenAI), dynamic skill learning |
| `agents/episode_state.py` | Pipeline state tracking (14 steps, resumable) |
| `agents/schemas.py` | Pydantic validation schemas for configs |

## Data Architecture

### Story-Centric Structure

All data is organized per story, with episodes nested inside:

```
data/stories/
├── _template/                   # Copied when creating a new story
│   ├── story_bible.yaml
│   ├── style_guide.yaml
│   ├── characters/
│   └── locations/
└── {story-slug}/                # One folder per story
    ├── story_bible.yaml         # World, characters, narrative arc
    ├── style_guide.yaml         # Visual consistency rules
    ├── characters/
    │   ├── {character}.yaml     # Design sheet per character
    │   └── avatars/             # Character avatar images
    ├── locations/
    │   └── {location}.yaml      # Location reference sheets
    ├── poster/                  # Story-level posters
    └── episodes/
        └── {n}/                 # One folder per episode
            ├── script.yaml              # Writer output
            ├── scenes_breakdown.yaml    # Director output
            ├── characters.yaml          # Character refs for this episode
            ├── scenes/                  # Clip prompt YAMLs
            ├── clips/{timestamp}/       # Generated video clips
            ├── audio/{timestamp}/       # Generated audio files
            ├── compose/{timestamp}/     # Composed episode video
            ├── final/                   # Published assets
            │   ├── video/               # Final episode MP4s
            │   ├── poster/              # Episode posters (4 variants)
            │   └── gallery/             # Gallery screenshots
            ├── state.yaml               # Pipeline state (resumable)
            ├── quality_report.yaml      # QA results
            └── engagement.yaml          # Votes + comments
```

### Website Data Store

The Next.js site uses a JSON file store at `site/data/store.json` — no external database required:

```json
{
  "stories": [...],
  "episodes": [...],
  "votes": [...],
  "comments": [...],
  "generation_runs": [...],
  "step_runs": [...]
}
```

## Video Generation Models

| Model | Provider | API | Clip Duration | Best For |
|-------|----------|-----|--------------|----------|
| **Seedance 2.0** | BytePlus Ark | Task-based (POST + poll) | 5–10s | High-quality animation, default model |
| CogVideoX-5B | HuggingFace | Inference API | 3–6s | General purpose |
| Wan2.1-T2V-14B | HuggingFace | Inference API | 3–6s | High fidelity |
| HunyuanVideo | HuggingFace | Inference API | 3–6s | Fallback model |
| AnimateDiff-Lightning | HuggingFace | Inference API | 3–6s | Fast generation |
| text-to-video-ms-1.7b | HuggingFace | Inference API | 3–6s | Lightweight |

### Audio Models

| Model | Provider | Purpose |
|-------|----------|---------|
| MusicGen (facebook/musicgen-medium) | HuggingFace | Background music generation |
| Bark (suno/bark) | HuggingFace | Text-to-speech narration |

### LLM Backends

| Provider | Used For |
|----------|----------|
| Anthropic Claude | Script writing, scene planning, character design, publishing metadata |
| OpenAI GPT-4 | Alternative LLM backend (same functions) |

## Quality Assurance

Validation runs at four levels via `python agents/validate_quality.py`:

| Level | Agent | When | Checks |
|-------|-------|------|--------|
| **Clip** | @artist | After each clip | Duration (2.5–12s), FPS (≥20), resolution (≥480p), black frames (<15%), static frames (<30%), file size (≥100KB), object consistency |
| **Consistency** | @artist | After all clips in scene | Color drift (<20%), brightness drift (<15%), SSIM continuity (≥0.70) |
| **Scene** | @editor | Before assembly | Min 2 clips, duration tolerance (25%), all clips passing |
| **Episode** | @showrunner | Before publish | Total duration (150–210s), min 6 scenes, audio present, content policy |

### Failure Recovery

1. Clip fails → @artist regenerates (up to 3 attempts)
2. Consistency fails → @artist regenerates the offending clip
3. Persistent failure → @showrunner escalates to @director for prompt revision
4. Episode fails → @editor diagnoses; publishing is **blocked**

## Content Safety

All content passes through ethics checkpoints defined in `config/content_policy.yaml`:

1. **Script writing** — @writer rejects unethical story directions
2. **Scene prompts** — @director includes negative prompts for prohibited content
3. **Video generation** — @artist reviews output before saving
4. **Comment moderation** — @community-manager filters all audience input
5. **Final review** — @showrunner blocks publication if policy is violated

Audience comments are **never** passed raw to other agents — they are always moderated and summarized first to prevent prompt injection.

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Video Generation | HuggingFace Inference API, BytePlus Ark API (Seedance 2.0) |
| Audio Generation | MusicGen, Bark TTS |
| LLM | Anthropic Claude, OpenAI GPT-4 |
| Website | Next.js 14 (React 18), Tailwind CSS, Framer Motion, Recharts |
| Video Processing | OpenCV, MoviePy |
| Audio Processing | Pydub |
| Config | YAML + python-dotenv |
| Validation | Pydantic schemas |
| Testing | Pytest |
| Linting | Ruff (100-char lines, double quotes) |
| Type Checking | Pyright (basic mode) |
| State Management | MCP server (`mcp/episode_state_server.py`) |
| Data Store | JSON file (`site/data/store.json`) |
| i18n | English + Chinese (locale cookie) |

## MCP Server

The Model Context Protocol server (`mcp/episode_state_server.py`) exposes episode pipeline state to chat agents:

| Tool | Purpose |
|------|---------|
| `get_episode_status` | Full pipeline state for an episode |
| `get_episode_summary` | Brief status summary |
| `start_step` | Mark a pipeline step as started |
| `complete_step` | Mark a step as completed with artifacts |
| `fail_step` | Mark a step as failed with error |
| `list_pipeline_steps` | List all 14 pipeline steps |

The 14 pipeline steps tracked by the state machine:

`collect_votes` → `generate_script` → `ethics_review` → `scene_breakdown` → `character_references` → `generate_clips` → `quality_gate_clips` → `quality_gate_consistency` → `add_audio` → `pre_assembly_validation` → `compose_episode` → `post_assembly_validation` → `final_review` → `publish`
