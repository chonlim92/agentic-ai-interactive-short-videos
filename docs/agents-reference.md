# Agents Reference

**Author: Chong Kiat Lim**

StorySmith AI uses a team of 9 specialized AI agents that collaborate to produce each episode. Agents operate at two layers: interactive chat agents (VS Code Copilot) and executable Python scripts.

## Agent Overview

| Agent | Layer | Role | Pipeline Stage |
|-------|-------|------|---------------|
| @showrunner | Chat | Orchestrator — coordinates pipeline, enforces quality | All stages |
| @writer | Chat + Python | Narrative — scripts, story bible, vote incorporation | Stage 1: Script |
| @director | Chat | Visual planning — scene breakdowns, video prompts | Stage 2: Scenes |
| @character-designer | Chat | Consistency — character reference sheets, avatars | Stage 3: Characters |
| @artist | Chat + Python | Generation — video clips via AI models | Stage 4: Video Gen |
| @sound-designer | Chat + Python | Audio — music, SFX, narration | Stage 6: Audio |
| @editor | Chat + Python | Post-production — assembly, transitions | Stage 7: Compose |
| @publisher | Chat + Python | Distribution — website deploy, posters, polls | Stage 8: Publish |
| @community-manager | Chat + Python | Engagement — votes, comments, teasers | Pre-Stage 1 |

## Chat Agents (VS Code Copilot)

Chat agents are defined in `.claude/agents/*.agent.md`. They are invoked via `@agent-name` in VS Code Copilot Chat.

### @showrunner — Orchestrator

**File:** `.claude/agents/showrunner.agent.md`

The Showrunner oversees the full episode pipeline. It delegates work to specialist agents and enforces quality gates and ethics checks at each stage.

**Responsibilities:**
- Coordinate the 8-stage pipeline
- Perform ethics review on scripts (Stage 3 in the 14-step state machine)
- Confirm all clips/scenes pass quality validation
- Perform final quality + ethics check before publishing
- Block publication if any policy violation is detected
- Trigger the next production cycle

**Usage:**
```
@showrunner generate episode 2 for "the-ancient-without-a-plug"
@showrunner what is the current status of episode 1?
@showrunner run quality validation on all clips
```

### @writer — Narrative

**File:** `.claude/agents/writer.agent.md`

The Writer maintains the story bible and crafts episode scripts that incorporate audience votes.

**Responsibilities:**
- Maintain story bible (`data/stories/{slug}/story_bible.yaml`)
- Draft episode scripts with 6–8 scenes for ~120s episodes
- Incorporate previous episode's vote results and moderated comments
- Create 2–4 branching story options for audience polls
- Reject unethical story directions (content policy checkpoint)

**Writing Rules:**
- Hook within the first 10 seconds
- Incident/event every 20–30 seconds
- Cliffhanger ending
- Show-don't-tell visual storytelling
- Dialogue must be speakable (for narration)

**Python Script:** `agents/generate_episode.py`

**Usage:**
```
@writer draft script for episode 1 incorporating vote results
@writer update the story bible with episode 1 outcomes
```

### @director — Visual Planning

**File:** `.claude/agents/director.agent.md`

The Director translates scripts into detailed visual prompts for video generation.

**Responsibilities:**
- Break scripts into scene shot lists
- Craft text-to-video prompts for each clip
- Define camera angles, composition, and continuity
- Generate dialogue for all clips
- Include negative prompts for prohibited content

**Visual Rules:**
- One scene = one location
- Different camera angles within scenes for variety
- Visual action in every clip (no static talking heads)
- Continuity notes linking to previous clip's last frame

**Usage:**
```
@director break down the script into scenes and clip prompts
@director revise scene 3 prompts for better continuity
```

### @character-designer — Visual Consistency

**File:** `.claude/agents/character-designer.agent.md`

The Character Designer creates and maintains visual consistency for all characters across clips and episodes.

**Responsibilities:**
- Create character reference sheets (YAML + avatar images)
- Maintain visual consistency across clips and episodes
- Provide pose/outfit variations for the Director
- Generate character avatars via image generation models

**Character Sheet Format:**
```yaml
name: "Xiao Xi"
name_en: "Xiao Xi"
name_zh: "小溪"
role: protagonist
age: 28
personality: ["curious", "tech-savvy", "sarcastic"]
appearance: "East Asian, shoulder-length black hair, modern casual"
voice_asset_id: "asset-20260225014954-jbfpf"
avatar_path: "characters/avatars/xiao_xi.png"
```

**Usage:**
```
@character-designer create reference sheets for all characters in episode 1
@character-designer generate avatar for the new character "village elder"
```

### @artist — Video Generation

**File:** `.claude/agents/artist.agent.md`

The Artist generates video clips using AI models and runs clip-level quality validation.

**Responsibilities:**
- Generate video clips via HuggingFace or BytePlus APIs
- Run quality validation on each clip
- Manage multi-clip stitching for scene continuity (last frame → next clip reference)
- Regenerate failed clips (up to 3 attempts per clip)

**Python Script:** `agents/generate_video.py`

**Supported Models:**

| Model | ID | Provider |
|-------|-----|----------|
| Seedance 2.0 | `dreamina-seedance-2-0-260128` | BytePlus Ark |
| CogVideoX-5B | `THUDM/CogVideoX-5b` | HuggingFace |
| Wan2.1-T2V-14B | `Wan-AI/Wan2.1-T2V-14B` | HuggingFace |
| HunyuanVideo | `tencent/HunyuanVideo` | HuggingFace |
| AnimateDiff-Lightning | `ByteDance/AnimateDiff-Lightning` | HuggingFace |

**Usage:**
```
@artist generate all clips for episode 1 using Seedance 2.0
@artist regenerate scene 3 clip 2 with improved prompt
```

### @sound-designer — Audio

**File:** `.claude/agents/sound-designer.agent.md`

The Sound Designer creates audio layers for each episode.

**Responsibilities:**
- Plan audio layers (music, SFX, narration) per scene
- Generate background music via MusicGen
- Generate narration via Bark TTS
- Create audio mixing specifications

**Python Script:** `agents/generate_audio.py`

**Audio Models:**

| Model | HuggingFace ID | Purpose |
|-------|---------------|---------|
| MusicGen Medium | `facebook/musicgen-medium` | Background music |
| Bark | `suno/bark` | Text-to-speech narration |

**Voice Library:** Configured in `config/voice_library.yaml` — 11+ digital voices (primarily Chinese female voices of varying ages and personalities).

**Usage:**
```
@sound-designer generate background music for episode 1
@sound-designer create narration for all scenes
```

### @editor — Post-Production

**File:** `.claude/agents/editor.agent.md`

The Editor assembles clips into the final episode video.

**Responsibilities:**
- Assemble clips into final episode
- Apply transitions (seamless, crossfade, cut, wipe, fade-to-black)
- Run pre-assembly validation
- Synchronize audio with video
- Add watermark, intro/outro cards
- Generate bilingual subtitles

**Python Script:** `agents/compose_episode.py`

**Composition Settings** (from `config/composition.yaml`):
- Target duration: 120s (range 100–140s)
- Intro/outro: 5s each
- Within-scene transitions: seamless (0.2s)
- Between-scene transitions: crossfade (0.8s)
- Export: H264 MP4, 720p, 24fps, 8Mbps

**Usage:**
```
@editor compose episode 1 with crossfade transitions
@editor list available clips and audio for episode 1
```

### @publisher — Distribution

**File:** `.claude/agents/publisher.agent.md`

The Publisher deploys finished episodes to the website.

**Responsibilities:**
- Generate episode metadata (title, description, posters)
- Create 4 poster variants (horizontal/vertical × EN/ZH)
- Extract gallery screenshots
- Deploy to Next.js site
- Set up voting poll with deadline
- Update `site/data/store.json`

**Python Script:** `agents/publish_site.py`

**Publishing Config** (from `config/publishing.yaml`):
- Vote deadline: 72 hours
- Poster: 1280×720 PNG
- Thumbnail source: frame grab at 30% position

**Usage:**
```
@publisher deploy episode 1 with voting poll
@publisher generate thumbnails for episode 1
```

### @community-manager — Engagement

**File:** `.claude/agents/community-manager.agent.md`

The Community Manager handles audience interaction between episodes.

**Responsibilities:**
- Tally audience votes and determine the winning option
- Moderate comments (filter hate speech, spam, prompt injection)
- Summarize audience feedback for the Writer
- Create episode teasers
- Monitor engagement metrics

**Python Script:** `agents/tally_votes.py`

**Comment Moderation Rules** (from `config/content_policy.yaml`):
- Auto-remove: hate speech, threats, spam
- Flag for review: profanity, controversial content
- Pass through: constructive feedback, story suggestions

**Usage:**
```
@community-manager tally votes for episode 1
@community-manager summarize audience feedback
@community-manager close voting for episode 1
```

## Shared Modules

### `agents/common.py` — Utilities

| Function | Purpose |
|----------|---------|
| `get_project_root()` | Absolute path to repo root (CWD-independent) |
| `setup_logging(name)` | Configured logger with timestamps |
| `load_env()` | Load `config/.env` from correct location |
| `load_yaml(path)` / `save_yaml(data, path)` | Safe YAML I/O with error handling |
| `episode_dir(n, story_slug)` | Path to `data/stories/{slug}/episodes/{n}` |
| `story_dir(story_slug)` | Path to `data/stories/{slug}` |
| `config_path(filename)` | Path to `config/{filename}` |
| `load_store()` | Load `site/data/store.json` |
| `get_story_language(story_slug)` | Returns "zh" or "en" |
| `detect_content_language(text)` | Language detection (CJK ratio) |

### `agents/llm.py` — LLM Client

| Function | Purpose |
|----------|---------|
| `call_agent(agent_name, task, context)` | Call LLM with agent.md as system prompt |
| `parse_yaml_response(response)` | Extract YAML from LLM response |
| `learn_new_skill(agent, task, output)` | Auto-generate SKILL.md from a successful task |
| `get_agent_skills(agent_name)` | List base + learned skills |

Supports both **Anthropic Claude** and **OpenAI GPT-4** backends.

### `agents/episode_state.py` — State Machine

Tracks pipeline progress through 14 steps with persistence to `state.yaml`:

| Method | Purpose |
|--------|---------|
| `start_step(step)` | Mark step in-progress |
| `complete_step(step, result)` | Mark step complete with artifacts |
| `fail_step(step, error)` | Mark step failed with error message |
| `summary()` | Brief status summary |

### `agents/schemas.py` — Validation

Pydantic schemas for validating configuration files at load time:
- `VideoGenerationFullConfig` — validates `video_generation.yaml`
- `CompositionConfig` — validates `composition.yaml`
