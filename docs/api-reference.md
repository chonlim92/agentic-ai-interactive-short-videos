# Agent API Reference

**Author: Chong Kiat Lim**

## Python Agent Scripts

All agents are run from the project root directory. They use `agents/common.py` for shared functionality.

---

### `generate_episode.py`

Generates an episode script from the story bible and optional vote results.

```bash
python agents/generate_episode.py --episode <number> [--votes <path>]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--episode` | Yes | Episode number to generate |
| `--votes` | No | Path to previous episode's `engagement.yaml` |

**Output**: `data/episodes/<n>/script.yaml`

---

### `generate_video.py`

Generates video clips from scene prompts using HuggingFace models.

```bash
python agents/generate_video.py --scene <path> [--model <name>] [--quality <preset>] [--seed <int>] [--skip-validation]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--scene` | Yes | Path to scene prompt YAML |
| `--model` | No | Model override (cogvideox, wan2, animatediff, svd) |
| `--quality` | No | Quality preset (draft, standard, high) |
| `--seed` | No | Random seed for reproducibility |
| `--skip-validation` | No | Skip post-generation quality check |

**Output**: `data/episodes/<n>/scenes/scene_<n>.mp4`

**Quality gate**: Automatically validates output after generation. Retries up to 3 times on failure.

---

### `validate_quality.py`

Runs quality assurance checks at 4 levels.

```bash
# Per-clip validation
python agents/validate_quality.py --clip <path>

# Scene consistency validation
python agents/validate_quality.py --scene <dir> --scene-number <n>

# Full episode validation
python agents/validate_quality.py --episode <number>

# Save report to file
python agents/validate_quality.py --episode <n> --output <path.yaml>
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--clip` | One of three | Path to single clip file |
| `--scene` + `--scene-number` | One of three | Scenes dir + scene number |
| `--episode` | One of three | Episode number for full validation |
| `--output` | No | Save YAML report to this path |

**Exit code**: `0` = all checks passed, `1` = one or more checks failed

**Quality thresholds** (from `config/video_generation.yaml`):

| Check | Threshold |
|-------|-----------|
| Clip duration | 2.5–7.0 seconds |
| Min FPS | 20 |
| Min resolution | 480p |
| Black frames | < 15% |
| Static frames | < 30% |
| Min file size | 100 KB |
| Continuity SSIM | ≥ 0.70 |
| Color drift | < 20% |
| Brightness drift | < 15% |
| Episode duration | 150–210 seconds |
| Min scenes | 6 |

---

### `compose_episode.py`

Stitches scene clips into a final episode with transitions.

```bash
python agents/compose_episode.py --episode <number> [--transitions <style>] [--skip-validation]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--episode` | Yes | Episode number to compose |
| `--transitions` | No | Transition style (crossfade, cut, wipe, fade_to_black) |
| `--skip-validation` | No | Skip pre-assembly quality checks |

**Input**: `data/episodes/<n>/scenes/scene_*.mp4`
**Output**: `data/episodes/<n>/final/episode_<n>.mp4`

**Quality gate**: Validates all clips before assembly. Blocks if any fail.

---

### `publish_site.py`

Deploys a finished episode to the Next.js website.

```bash
python agents/publish_site.py --episode <number> [--draft]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--episode` | Yes | Episode number to publish |
| `--draft` | No | Publish as draft (not visible to audience) |

**Input**: `data/episodes/<n>/publish.yaml`

---

### `tally_votes.py`

Collects and summarizes audience votes for an episode.

```bash
python agents/tally_votes.py --episode <number> [--format <type>]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `--episode` | Yes | Episode number |
| `--format` | No | Output format: yaml (default), json, summary |

**Output**: `data/episodes/<n>/engagement.yaml`

---

## Shared Module: `agents/common.py`

| Function | Description |
|----------|-------------|
| `get_project_root()` | Returns absolute Path to repo root |
| `setup_logging(name, level="INFO")` | Returns configured logger |
| `load_env()` | Loads `config/.env` (CWD-independent) |
| `load_yaml(path)` | Loads YAML with error handling; supports relative paths |
| `save_yaml(data, path)` | Saves YAML, creates parent dirs |
| `episode_dir(n)` | Returns `data/episodes/<n>` as Path |
| `config_path(filename)` | Returns `config/<filename>` as Path |
