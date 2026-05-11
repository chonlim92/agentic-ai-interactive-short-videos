# Getting Started

**Author: Chong Kiat Lim**

This guide walks you through setting up StorySmith AI from scratch — installing dependencies, configuring API keys, starting the website, and generating your first episode.

## Prerequisites

| Requirement | Minimum Version | Purpose |
|-------------|----------------|---------|
| Python | 3.11+ | Agent scripts, video processing |
| Node.js | 18+ | Next.js website |
| npm | 9+ | Package management |
| VS Code | Latest | Chat agents via GitHub Copilot |
| GitHub Copilot | Active subscription | Interactive agent personas |

### API Keys (at least one required for video generation)

| Provider | Key | Used For |
|----------|-----|----------|
| HuggingFace | `HUGGINGFACE_API_TOKEN` | Video generation (CogVideoX, Wan2.1, AnimateDiff), audio (MusicGen, Bark) |
| BytePlus | `ARK_API_KEY` | Seedance 2.0 video generation |
| Anthropic | `ANTHROPIC_API_KEY` | LLM calls (script writing, scene planning) |
| OpenAI | `OPENAI_API_KEY` | Alternative LLM backend |

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/agentic-ai-interactive-short-videos.git
cd agentic-ai-interactive-short-videos
```

### 2. Python Environment

```bash
# Create a virtual environment (recommended)
python -m venv .venv

# Activate it
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Windows cmd:
.venv\Scripts\activate.bat
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp config/.env.example config/.env
```

Edit `config/.env` and add your API keys:

```dotenv
# Required: at least one video generation API
HUGGINGFACE_API_TOKEN=hf_your_token_here
ARK_API_KEY=your_byteplus_ark_key_here

# Required: at least one LLM for script/scene generation
ANTHROPIC_API_KEY=sk-ant-your_key_here
# or
OPENAI_API_KEY=sk-your_key_here

# Site configuration
SITE_URL=http://localhost:3000
SITE_API_URL=http://localhost:3000
ADMIN_PASSWORD=your_admin_password

# Video settings
VIDEO_LENGTH=60
VIDEO_ASPECT_RATIO=9:16
CONTENT_LANGUAGE=zh
```

### 4. Install the Next.js Website

```bash
cd site
npm install
cd ..
```

### 5. Initialize the Database

```bash
cd site
node scripts/init-db.js
cd ..
```

This creates `site/data/store.json` with the default schema.

## Starting the Application

### Development Mode (Recommended)

**Option A: PowerShell script (Windows)**

```powershell
.\start-site.ps1
```

This script safely adds Node.js to your PATH without overwriting your Python virtual environment.

**Option B: Manual start**

```bash
cd site
npm run dev
```

The site launches at **http://localhost:3000**.

### Production Mode

```bash
cd site
npm run build
npm start
```

| | Development | Production |
|---|---|---|
| **Command** | `npm run dev` | `npm run build && npm start` |
| **Hot reload** | Yes | No |
| **Performance** | Slower (on-demand compilation) | Optimized |
| **Error detail** | Full stack traces | Minimal |

## Your First Episode

### Via the Admin Panel (Recommended)

1. Open **http://localhost:3000/admin** and log in with your admin password
2. Go to **Stories → + New Story** and create a story with title, slug, and description
3. Go to **Episodes → + New Episode**, select your story, set the episode number and title
4. Go to **Generate**, select your story and episode
5. Click **Run Full Pipeline** — the system runs all 8 stages automatically:
   - Script → Scenes → Characters → Video Gen → Quality → Audio → Compose → Publish
6. Visit the homepage to see your published episode

### Via CLI

```bash
# Generate script
python agents/generate_episode.py --story my-story --episode 1

# Generate video clips
python agents/generate_video.py --scene data/stories/my-story/episodes/1/scenes/scene_1_clip_1_prompt.yaml

# Validate quality
python agents/validate_quality.py --story my-story --episode 1

# Compose final video
python agents/compose_episode.py --story my-story --episode 1

# Publish to website
python agents/publish_site.py --story my-story --episode 1
```

### Via Chat Agents (VS Code)

Open VS Code with GitHub Copilot and use the agent personas:

```
@showrunner generate episode 1 for "my-story"
@writer draft a script for episode 1
@artist generate all clips for episode 1
```

## Project Structure

```
agentic-ai-interactive-short-videos/
├── agents/              # Python agent scripts
├── .claude/agents/      # 9 VS Code Copilot chat agents
├── .claude/skills/      # Reusable agent workflows
├── config/              # YAML configs + .env
├── data/stories/        # Story data (per-story folders)
├── docs/                # Documentation
├── mcp/                 # MCP server for episode state
├── site/                # Next.js website
├── tests/               # Pytest test suite
└── tools/               # Utility scripts
```

## Next Steps

- [Architecture Overview](architecture.md) — System design and data flow
- [Pipeline Guide](pipeline-guide.md) — Detailed 8-stage generation pipeline
- [Admin Panel Guide](admin-panel.md) — Full admin GUI documentation
- [Agents Reference](agents-reference.md) — All 9 agents in detail
- [CLI Reference](cli-reference.md) — Command-line usage for all scripts
- [API Reference](api-reference.md) — REST API endpoints
