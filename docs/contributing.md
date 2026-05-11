# Contributing

**Author: Chong Kiat Lim**

## Development Setup

```bash
# Clone the repo
git clone <repo-url>
cd agentic-ai-interactive-short-videos

# Create and activate virtual environment (manual — no auto-activation)
python -m venv .video_venv
# Windows:
.\.video_venv\Scripts\activate
# Linux/Mac:
source .video_venv/bin/activate

# Install all dependencies
pip install -r requirements.txt
pip install -e ".[dev]"

# Set up environment
cp config/.env.example config/.env
# Edit config/.env with your HuggingFace API token
```

## Development Workflow

### Running Tests
```bash
pytest                       # Run all tests
pytest tests/test_common.py  # Run specific test file
pytest -k "test_load_yaml"  # Run tests matching pattern
pytest --cov=agents          # With coverage
```

### Linting & Formatting
```bash
ruff check agents/ tests/    # Lint
ruff check --fix agents/     # Auto-fix lint issues
ruff format agents/ tests/   # Format code
```

### Type Checking
```bash
pyright agents/ tests/
```

### Running Agents
```bash
# Always run from the project root
python agents/generate_episode.py --episode 1
python agents/generate_video.py --scene data/episodes/1/scenes/scene_1_prompt.yaml
python agents/validate_quality.py --episode 1
python agents/compose_episode.py --episode 1
python agents/publish_site.py --episode 1
python agents/tally_votes.py --episode 1 --format summary
```

## Project Structure Conventions

### Adding a Python Agent
1. Create `agents/<name>.py`
2. Import from `agents/common.py` for logging, config loading, paths
3. Add matching config in `config/<name>.yaml` if needed
4. Add tests in `tests/test_<name>.py`

### Adding a Chat Agent
1. Create `.claude/agents/<name>.agent.md` with YAML frontmatter
2. Define: description, tools, responsibilities, constraints, approach
3. Add skills check pattern: "ALWAYS check available skills first"

### Adding a Skill
1. Create `.claude/skills/<name>/SKILL.md`
2. Document: when to use, step-by-step procedure, parameters

### Adding Config
1. Place in `config/<name>.yaml`
2. Add a Pydantic schema in `agents/schemas.py` (if applicable)
3. Add test coverage in `tests/test_config.py`

## Code Style

- **Python 3.11+** features allowed (union types `X | Y`, match statements)
- **Ruff** for linting and formatting (config in `pyproject.toml`)
- **100-char** line length
- **Double quotes** for strings
- Import order: stdlib → third-party → local (enforced by ruff `I` rule)

## Git Conventions

- Branches: `feature/<name>`, `fix/<name>`, `docs/<name>`
- Commits: concise, imperative mood ("Add quality validation", not "Added...")
- Never commit: `.env` files, generated videos, `__pycache__/`

## Quality Gates

All PRs must pass:
1. `ruff check` — no lint errors
2. `ruff format --check` — code is formatted
3. `pyright` — no type errors
4. `pytest` — all tests pass
