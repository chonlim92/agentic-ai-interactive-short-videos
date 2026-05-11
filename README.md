# StorySmith AI — Agentic AI Interactive Short Videos

**Author: Chong Kiat Lim**

An AI agent team that generates **interactive episodic animated short videos**. Audiences vote on story direction, and a team of **9 specialized AI agents** collaborates to produce each episode — from script to screen.

![Home Page](docs/images/StorySmithAI_gui_frontend_home_page.jpg)

## Concept

**Interactive Story Series** — AI-generated animated shorts with recurring characters and evolving narratives. After each episode, the audience votes on what happens next. Agents handle narrative continuity, video generation, post-production, and publishing automatically.

**Key Features:**
- 9 AI agents collaborating through an 8-stage pipeline
- Multiple video generation models (Seedance 2.0, CogVideoX, Wan2.1, AnimateDiff)
- 4-level automated quality assurance with AI-powered clip regeneration
- Full admin panel with visual pipeline management
- Bilingual support (English / 中文)
- Audience voting and comment moderation
- Content safety enforcement at every stage

## Screenshots

### Public-Facing Website

**Story Page**

![Story Page](docs/images/StorySmithAI_gui_frontend_story_page.jpg)

**Episode Player**

![Episode Page](docs/images/StorySmithAI_gui_frontend_episode_page.jpg)

### Admin Panel

**Dashboard**

![Dashboard](docs/images/StorySmithAI_gui_admin_DashboardPage.jpg)

### Generation Pipeline Stages

**1. Script — Writer Agent**

![Script](docs/images/StorySmithAI_gui_WriterAgent_ScriptStep.jpg)

**2. Scenes — Director Agent**

![Scenes](docs/images/StorySmithAI_gui_DirectorAgent_ScenesStep.jpg)

**3. Characters — Character Designer Agent**

![Characters](docs/images/StorySmithAI_gui_CharacterDesignerAgent_CharacterStep.jpg)

**4. Video Generation — Artist Agent**

![Video Gen](docs/images/StorySmithAI_gui_ArtistAgent_VideoGenStep.jpg)

**5. Quality Inspection — with AI Prompt Suggestions**

![Quality](docs/images/StorySmithAI_gui_QualityInspectionAgent_QualityStep.jpg)

![AI Suggestions](docs/images/StorySmithAI_gui_QualityInspectionAgent_with_AIPromptSuggestion.jpg)

**5b. Quality Inspection — Regeneration Comparison**

![Regeneration](docs/images/StorySmithAI_gui_QualityInspectionAgent_with_Regeneration.jpg)

**6. Compose — Editor Agent**

![Compose](docs/images/StorySmithAI_gui_EditorAgent_ComposeStep.jpg)

**7. Publish — Publisher Agent**

![Publish](docs/images/StorySmithAI_gui_PublisherAgent_PublishStep.jpg)

### Admin Management

**Story Management**

![Stories](docs/images/StorySmithAI_gui_admin_StoryManagementPage.jpg)

**Episode Editor**

![Episode Editor](docs/images/StorySmithAI_gui_admin_EpisodesEditorPage.jpg)

**Comment Moderation**

![Comments](docs/images/StorySmithAI_gui_admin_CommentModerationPage.jpg)

## Architecture

```
├── agents/              # Python automation scripts (7 agents)
├── .claude/agents/      # 9 VS Code Copilot chat agents
├── .claude/skills/      # Reusable agent workflows
├── config/              # YAML configs + environment variables
├── data/stories/        # Per-story data (story-centric structure)
├── mcp/                 # MCP server for episode state
├── site/                # Next.js website (episodes, voting, gallery, admin)
├── docs/                # Documentation
└── tests/               # Test suite
```

The system uses a **two-layer agent architecture**:

- **Chat Agents** (`.claude/agents/`) — Interactive VS Code Copilot personas for planning and creative decisions
- **Python Agents** (`agents/`) — Executable scripts for API calls, video processing, and deployment
- **Admin Web UI** (`site/src/app/admin/`) — Visual interface for the full pipeline

## Agent Team

| Agent | Role | Pipeline Stage | Models Used |
|-------|------|---------------|-------------|
| `@showrunner` | Orchestrator | All stages | — |
| `@writer` | Narrative | 1. Script | Claude / GPT-4 |
| `@director` | Visual Planning | 2. Scenes | Claude / GPT-4 |
| `@character-designer` | Consistency | 3. Characters | Claude / GPT-4 + Image Gen |
| `@artist` | Generation | 4. Video Gen | Seedance 2.0, CogVideoX, Wan2.1 |
| `@sound-designer` | Audio | 6. Audio | MusicGen, Bark TTS |
| `@editor` | Post-Production | 7. Compose | OpenCV, MoviePy |
| `@publisher` | Distribution | 8. Publish | Claude / GPT-4 |
| `@community-manager` | Engagement | Vote tallying | — |

## Episode Pipeline

```mermaid
flowchart TD
    A[🎭 Community Manager\nCollect Votes & Comments] --> B[✍️ Writer\nDraft Script from Votes]
    B --> C[🎬 Showrunner\nEthics Review]
    C --> D[🎥 Director\nScene Breakdown & Prompts]
    D --> E[🎨 Character Designer\nReference Images]
    E --> F[🖌️ Artist\nGenerate Video Clips]
    F --> G{Quality Gate\nClip Validation}
    G -->|Pass| H{Quality Gate\nScene Consistency}
    G -->|Fail x3| D
    H -->|Pass| I[🔊 Sound Designer\nAdd Audio Layers]
    H -->|Fail| F
    I --> J[✂️ Editor\nAssemble Episode]
    J --> K{Quality Gate\nEpisode Validation}
    K -->|Pass| L[🎬 Showrunner\nFinal Review]
    K -->|Fail| J
    L --> M[📢 Publisher\nDeploy to Website]
    M --> N[🎭 Community Manager\nMonitor & Moderate]
    N --> A

    style A fill:#7c3aed,color:#fff
    style B fill:#7c3aed,color:#fff
    style C fill:#ec4899,color:#fff
    style D fill:#06b6d4,color:#fff
    style E fill:#06b6d4,color:#fff
    style F fill:#06b6d4,color:#fff
    style G fill:#f59e0b,color:#000
    style H fill:#f59e0b,color:#000
    style I fill:#7c3aed,color:#fff
    style J fill:#7c3aed,color:#fff
    style K fill:#f59e0b,color:#000
    style L fill:#ec4899,color:#fff
    style M fill:#10b981,color:#fff
    style N fill:#7c3aed,color:#fff
```

### Pipeline Stages Summary

| # | Stage | Agent | What Happens | Output |
|---|-------|-------|-------------|--------|
| 1 | **Script** | @writer | LLM generates episode script from story bible + votes | `script.yaml` |
| 2 | **Scenes** | @director | LLM breaks script into clip-by-clip video prompts | `scenes_breakdown.yaml`, clip prompts |
| 3 | **Characters** | @character-designer | Generate/update character reference sheets and avatars | Character YAMLs, avatar PNGs |
| 4 | **Video Gen** | @artist | AI models generate video clips from prompts | `clips/{timestamp}/scene_*.mp4` |
| 5 | **Quality** | @artist | 4-level validation with AI-powered regeneration | `quality_report.yaml` |
| 6 | **Audio** | @sound-designer | Generate background music and narration | `audio/{timestamp}/*.wav` |
| 7 | **Compose** | @editor | Assemble clips + audio into final episode | `compose/{timestamp}/episode_{n}.mp4` |
| 8 | **Publish** | @publisher | Deploy to website with posters, gallery, and voting poll | `final/`, updated `store.json` |

## Video Generation Models

| Model | Provider | Clip Duration | Default |
|-------|----------|--------------|---------|
| **Seedance 2.0** | BytePlus Ark | 5–10s | ✓ |
| CogVideoX-5B | HuggingFace | 3–6s | |
| Wan2.1-T2V-14B | HuggingFace | 3–6s | |
| HunyuanVideo | HuggingFace | 3–6s | |
| AnimateDiff-Lightning | HuggingFace | 3–6s | |

**Video specs:** 720×1280 (9:16 vertical), 24fps, H264, 8Mbps

## Quality Assurance

4-level automated validation with AI-powered failure recovery:

| Level | Checks | Thresholds |
|-------|--------|------------|
| **Clip** | Duration, FPS, resolution, black/static frames, object consistency | 2.5–12s, ≥20fps, ≥480p, <15% black, <30% static |
| **Consistency** | Color drift, brightness drift, SSIM continuity | <20% color, <15% brightness, ≥0.70 SSIM |
| **Scene** | Clip count, duration tolerance | ≥2 clips, ±25% duration |
| **Episode** | Total duration, scene count, audio, content policy | 150–210s, ≥6 scenes |

Failed clips get AI-generated improvement suggestions and can be regenerated with side-by-side comparison.

## Getting Started

### Prerequisites

- Python 3.11+ with pip
- Node.js 18+ with npm
- API keys: HuggingFace or BytePlus (video), Anthropic or OpenAI (LLM)
- VS Code with GitHub Copilot (optional, for chat agents)

### Installation

```bash
# Clone and install Python deps
git clone https://github.com/your-org/agentic-ai-interactive-short-videos.git
cd agentic-ai-interactive-short-videos
pip install -r requirements.txt

# Configure environment
cp config/.env.example config/.env
# Edit config/.env with your API keys

# Install and start the website
cd site
npm install
npm run dev
```

The site launches at **http://localhost:3000**.

### Usage

#### Via Admin Panel (Recommended)

1. **Login** — Go to `http://localhost:3000/admin`
2. **Create a Story** — Admin → Stories → + New Story
3. **Create an Episode** — Admin → Episodes → + New Episode
4. **Generate** — Admin → Generate → Select story/episode → Run Full Pipeline
5. **View** — Go to homepage → Click your story → Watch the episode

See the [Admin Panel Guide](docs/admin-panel.md) for full details with screenshots.

#### Via CLI

```bash
python agents/generate_episode.py --story my-story --episode 1
python agents/generate_video.py --scene path/to/prompt.yaml --model seedance2.0
python agents/validate_quality.py --story my-story --episode 1
python agents/generate_audio.py --story my-story --episode 1
python agents/compose_episode.py --story my-story --episode 1
python agents/publish_site.py --story my-story --episode 1
python agents/tally_votes.py --episode 1
```

See the [CLI Reference](docs/cli-reference.md) for all arguments and options.

#### Via Chat Agents (VS Code)

```
@showrunner generate episode 2 for "the-ancient-without-a-plug"
@writer draft a script incorporating vote results
@artist generate all scenes using Seedance 2.0
@publisher deploy episode 1 with voting poll
```

See the [Agents Reference](docs/agents-reference.md) for all 9 agents.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Video Generation | HuggingFace Inference API, BytePlus Ark API (Seedance 2.0) |
| Audio Generation | MusicGen (facebook/musicgen-medium), Bark TTS (suno/bark) |
| LLM | Anthropic Claude, OpenAI GPT-4 |
| Website | Next.js 14, React 18, Tailwind CSS, Framer Motion, Recharts |
| Video Processing | OpenCV, MoviePy |
| Audio Processing | Pydub |
| Config | YAML + python-dotenv |
| Validation | Pydantic schemas |
| Testing | Pytest |
| Linting | Ruff |
| Type Checking | Pyright |
| State Management | MCP server |
| Data Store | JSON file (no database) |
| i18n | English + Chinese |

## Documentation

| Document | Description |
|----------|-------------|
| [Getting Started](docs/getting-started.md) | Installation, setup, first episode |
| [Architecture](docs/architecture.md) | System design, data flow, technology stack |
| [Pipeline Guide](docs/pipeline-guide.md) | Detailed 8-stage generation pipeline with models |
| [Admin Panel Guide](docs/admin-panel.md) | Full admin UI documentation with screenshots |
| [Agents Reference](docs/agents-reference.md) | All 9 agents — roles, capabilities, usage |
| [CLI Reference](docs/cli-reference.md) | Command-line usage for all Python scripts |
| [API Reference](docs/api-reference.md) | REST API endpoints |
| [Usage Guides](docs/USAGE_GUIDES.md) | Quick start and workflow guides |
| [Contributing](docs/contributing.md) | Development setup, testing, code style |

## Development

```bash
make install     # Install dependencies
make dev         # Install with dev tools
make check       # Run all checks (lint + format + typecheck + test)
make test        # Run tests only
make clean       # Clean build artifacts
```

## Disclaimer

> **This project is for educational and learning purposes only.**
> It is NOT intended for commercial use, production deployment, or any revenue-generating activity.
> The author provides this software "as is" without warranty of any kind.

## License

This project is licensed under **CC BY-NC 4.0** (Creative Commons Attribution-NonCommercial 4.0 International).

You may share and adapt this work for non-commercial purposes with attribution. See [LICENSE](LICENSE) for full details.
