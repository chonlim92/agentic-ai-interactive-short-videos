# CLI Reference

**Author: Chong Kiat Lim**

Complete command-line reference for all Python agent scripts. All commands should be run from the project root directory.

## Quick Reference

```bash
# Full episode pipeline
python agents/generate_episode.py --story <slug> --episode <n>

# Individual steps
python agents/generate_video.py --scene <path> [--model <name>]
python agents/generate_audio.py --story <slug> --episode <n>
python agents/validate_quality.py --story <slug> --episode <n>
python agents/compose_episode.py --story <slug> --episode <n>
python agents/publish_site.py --story <slug> --episode <n>
python agents/tally_votes.py --episode <n>
```

## Makefile Shortcuts

```bash
make help                  # Show all available commands
make install               # pip install -r requirements.txt
make dev                   # Install all deps + dev tools
make lint                  # Run Ruff linter
make format                # Run Ruff formatter
make typecheck             # Run Pyright type checker
make test                  # Run pytest
make test-cov              # Run pytest with coverage report
make check                 # All checks: lint + format + typecheck + test
make clean                 # Remove __pycache__, .pytest_cache, etc.

# Agent shortcuts
make generate-episode EP=1              # Generate episode 1 script
make generate-video SCENE=path/to.yaml  # Generate video for a scene
make validate EP=1                      # Validate episode 1
make compose EP=1                       # Compose episode 1
make publish EP=1                       # Publish episode 1
make tally EP=1                         # Tally votes for episode 1
```

---

## generate_episode.py

Orchestrates full episode script generation. Calls the Writer agent via LLM to produce a structured script YAML.

### Usage

```bash
python agents/generate_episode.py --episode <number> [options]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--episode <n>` | Yes | — | Episode number to generate |
| `--story <slug>` | No | auto-detect | Story slug (folder name in `data/stories/`) |
| `--votes <path>` | No | — | Path to previous episode's `engagement.yaml` for vote incorporation |
| `--stage <stage>` | No | — | Run a specific pipeline stage only |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VIDEO_LENGTH` | 60 | Target episode duration in seconds (clamped 30–180) |
| `CONTENT_LANGUAGE` | en | Script language (`en` or `zh`) |
| `ANTHROPIC_API_KEY` | — | Anthropic Claude API key (required for LLM calls) |
| `OPENAI_API_KEY` | — | Alternative: OpenAI API key |

### Examples

```bash
# Generate first episode
python agents/generate_episode.py --story the-ancient-without-a-plug --episode 1

# Generate episode 2 using episode 1's votes
python agents/generate_episode.py --story the-ancient-without-a-plug --episode 2 \
  --votes data/stories/the-ancient-without-a-plug/episodes/1/engagement.yaml

# Generate a 2-minute episode
VIDEO_LENGTH=120 python agents/generate_episode.py --story my-story --episode 1
```

### Output

```
data/stories/{slug}/episodes/{n}/script.yaml
```

---

## generate_video.py

Generates video clips using AI models (HuggingFace Inference API or BytePlus Ark API).

### Usage

```bash
python agents/generate_video.py --scene <path> [options]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--scene <path>` | Yes | — | Path to scene prompt YAML |
| `--model <name>` | No | from config | Model name (see table below) |
| `--quality <preset>` | No | from config | Quality preset: `draft`, `standard`, `high` |
| `--seed <int>` | No | random | Random seed for reproducibility |
| `--local` | No | false | Use local diffusers pipeline instead of cloud API |
| `--skip-validation` | No | false | Skip post-generation quality check |

### Supported Models

| Name | HuggingFace / API ID | Provider |
|------|---------------------|----------|
| `seedance2.0` | `dreamina-seedance-2-0-260128` | BytePlus Ark (requires `ARK_API_KEY`) |
| `hunyuanvideo` | `tencent/HunyuanVideo` | HuggingFace |
| `cogvideox` | `THUDM/CogVideoX-5b` | HuggingFace |
| `wan2.1` | `Wan-AI/Wan2.1-T2V-14B` | HuggingFace |
| `animatediff-lightning` | `ByteDance/AnimateDiff-Lightning` | HuggingFace |
| `text-to-video` | `ali-vilab/text-to-video-ms-1.7b` | HuggingFace |

### Quality Presets

| Preset | Inference Steps | Guidance Scale |
|--------|----------------|----------------|
| `draft` | 20 | 6.0 |
| `standard` | 30 | 7.5 |
| `high` | 50 | 9.0 |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HUGGINGFACE_API_TOKEN` | — | HuggingFace API token |
| `ARK_API_KEY` | — | BytePlus Ark API key (for Seedance 2.0) |
| `VIDEO_ASPECT_RATIO` | 9:16 | Video aspect ratio (`9:16`, `16:9`, `1:1`, `4:3`, `3:4`) |

### Examples

```bash
# Generate with default model (Seedance 2.0)
python agents/generate_video.py \
  --scene data/stories/my-story/episodes/1/scenes/scene_1_clip_1_prompt.yaml

# Generate with specific model and quality
python agents/generate_video.py \
  --scene data/stories/my-story/episodes/1/scenes/scene_2_clip_1_prompt.yaml \
  --model cogvideox --quality high --seed 42

# Local generation (requires GPU)
python agents/generate_video.py \
  --scene data/stories/my-story/episodes/1/scenes/scene_1_clip_1_prompt.yaml \
  --local
```

### Output

```
data/stories/{slug}/episodes/{n}/clips/{timestamp}/scene_{n}_clip_{m}.mp4
```

---

## generate_audio.py

Generates background music and narration for an episode.

### Usage

```bash
python agents/generate_audio.py --episode <number> [options]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--episode <n>` | Yes | — | Episode number |
| `--story <slug>` | No | auto-detect | Story slug |
| `--model <name>` | No | musicgen | Audio model: `musicgen`, `musicgen-small`, `musicgen-large`, `bark` |
| `--music-only` | No | true | Generate background music only (default mode) |

### Models

| Name | HuggingFace ID | Purpose |
|------|---------------|---------|
| `musicgen` | `facebook/musicgen-medium` | Background music (default) |
| `musicgen-small` | `facebook/musicgen-small` | Lighter music generation |
| `musicgen-large` | `facebook/musicgen-large` | Higher quality music |
| `bark` | `suno/bark` | Text-to-speech narration |

### Examples

```bash
# Generate background music
python agents/generate_audio.py --story my-story --episode 1

# Generate with Bark narration
python agents/generate_audio.py --story my-story --episode 1 --model bark
```

### Output

```
data/stories/{slug}/episodes/{n}/audio/{timestamp}/*.wav
```

---

## validate_quality.py

Multi-level quality validation for clips, scenes, and episodes.

### Usage

```bash
python agents/validate_quality.py [options]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--clip <path>` | No | — | Validate a single clip file |
| `--scene <dir>` | No | — | Validate scene consistency (requires `--scene-number`) |
| `--scene-number <n>` | No | — | Scene number (with `--scene`) |
| `--episode <n>` | No | — | Full episode validation |
| `--story <slug>` | No | auto-detect | Story slug |
| `--output <path>` | No | — | Save YAML report to path |
| `--review` | No | false | Interactive review mode |

### Validation Thresholds

#### Clip-Level

| Check | Threshold | Description |
|-------|-----------|-------------|
| Duration | 2.5–12.0s | Acceptable clip length range |
| FPS | ≥ 20 | Minimum frame rate |
| Resolution | ≥ 480p | Minimum vertical resolution |
| Black frames | < 15% | Maximum ratio of mostly-black frames |
| Static frames | < 30% | Maximum ratio of frames with no motion |
| File size | ≥ 100 KB | Minimum file size |
| Object consistency | shift < 0.6 | Maximum histogram shift (object morphing detection) |
| Floating objects | < 50% frames | Detects physics-defying artifacts |
| Audio naturalness | repetition < 0.85 | Detects gibberish audio |

#### Scene Consistency

| Check | Threshold | Description |
|-------|-----------|-------------|
| Color drift | < 20% | Maximum histogram change between clips |
| Brightness drift | < 15% | Maximum average brightness change |
| SSIM continuity | ≥ 0.70 | Minimum structural similarity at clip boundaries |

#### Episode-Level

| Check | Threshold | Description |
|-------|-----------|-------------|
| Total duration | 150–210s | Target episode length range |
| Min scenes | 6 | Minimum scene count |
| Audio present | Required | Audio track must exist |
| Content policy | Clean | No prohibited content |

### Examples

```bash
# Validate a single clip
python agents/validate_quality.py --clip data/stories/my-story/episodes/1/clips/run1/scene_1_clip_1.mp4

# Validate full episode
python agents/validate_quality.py --story my-story --episode 1

# Interactive review mode
python agents/validate_quality.py --story my-story --episode 1 --review

# Save report
python agents/validate_quality.py --story my-story --episode 1 --output report.yaml
```

### Output

```
data/stories/{slug}/episodes/{n}/quality_report.yaml
```

---

## compose_episode.py

Assembles video clips and audio into the final episode.

### Usage

```bash
python agents/compose_episode.py --episode <number> [options]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--episode <n>` | Yes | — | Episode number |
| `--story <slug>` | No | auto-detect | Story slug |
| `--transitions <style>` | No | from config | Transition style: `seamless`, `crossfade`, `cut`, `wipe`, `fade_to_black` |
| `--mute-video-audio` | No | false | Replace video audio with audio layer only |
| `--skip-validation` | No | false | Skip pre-assembly validation checks |
| `--list-assets` | No | false | List available clips and audio files (no assembly) |

### Composition Config (`config/composition.yaml`)

| Setting | Default | Description |
|---------|---------|-------------|
| Target duration | 120s | Episode target length |
| Duration range | 100–140s | Acceptable range |
| Intro duration | 5s | Title card length |
| Outro duration | 5s | Credits length |
| Clip transitions | seamless (0.2s) | Within-scene transition |
| Scene transitions | crossfade (0.8s) | Between-scene transition |
| Music volume | 0.6 | Background music level |
| SFX volume | 0.8 | Sound effects level |
| Narration volume | 1.0 | Voice narration level |
| Export codec | H264 | Video codec |
| Export resolution | 720p | Output resolution |
| Export FPS | 24 | Output frame rate |
| Export bitrate | 8M | Output bitrate |

### Examples

```bash
# Compose with default settings
python agents/compose_episode.py --story my-story --episode 1

# Compose with crossfade and muted video audio
python agents/compose_episode.py --story my-story --episode 1 \
  --transitions crossfade --mute-video-audio

# List available assets
python agents/compose_episode.py --story my-story --episode 1 --list-assets
```

### Output

```
data/stories/{slug}/episodes/{n}/compose/{timestamp}/episode_{n}.mp4
```

---

## publish_site.py

Deploys the finished episode to the Next.js website.

### Usage

```bash
python agents/publish_site.py --episode <number> [options]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--episode <n>` | Yes | — | Episode number |
| `--story <slug>` | No | auto-detect | Story slug |
| `--draft` | No | false | Publish as draft (hidden from audience) |

### Process

1. Find the composed video in `compose/{timestamp}/episode_{n}.mp4`
2. Generate EN and ZH video variants
3. Generate 4 poster variants (horizontal/vertical × EN/ZH)
4. Extract gallery screenshots
5. Generate story poster (if first episode)
6. Update `site/data/store.json` with episode data, video URLs, and poll options
7. Set episode status to "published" with voting open

### Examples

```bash
# Publish episode
python agents/publish_site.py --story my-story --episode 1

# Publish as draft (not visible to audience)
python agents/publish_site.py --story my-story --episode 1 --draft
```

### Output

```
data/stories/{slug}/episodes/{n}/final/
├── video/episode_{n}.mp4
├── video/episode_{n}_EN.mp4
├── poster/poster_horizontal_en.png
├── poster/poster_horizontal_zh.png
├── poster/poster_vertical_en.png
├── poster/poster_vertical_zh.png
└── gallery/gallery_*.jpg

site/data/store.json  (updated)
```

---

## tally_votes.py

Collects audience votes and comments for an episode.

### Usage

```bash
python agents/tally_votes.py --episode <number> [options]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--episode <n>` | Yes | — | Episode number |
| `--format <type>` | No | yaml | Output format: `yaml`, `json`, `summary` |
| `--close` | No | false | Close voting for the episode |

### Examples

```bash
# Get vote results
python agents/tally_votes.py --episode 1

# Get summary format
python agents/tally_votes.py --episode 1 --format summary

# Close voting
python agents/tally_votes.py --episode 1 --close
```

### Output

```
data/stories/{slug}/episodes/{n}/engagement.yaml
```

The engagement file contains:
```yaml
votes:
  total: 42
  options:
    - text: "Ask the villagers for help"
      votes: 18
      percentage: 42.9
    - text: "Explore the village on her own"
      votes: 15
      percentage: 35.7
    - text: "Try to use her smartphone"
      votes: 9
      percentage: 21.4
  winner: "Ask the villagers for help"
comments:
  total: 5
  moderated: [...]
```

---

## Environment Reference

All environment variables are configured in `config/.env`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `HUGGINGFACE_API_TOKEN` | For HF models | — | HuggingFace API token |
| `ARK_API_KEY` | For Seedance | — | BytePlus Ark API key |
| `ANTHROPIC_API_KEY` | For LLM | — | Anthropic Claude API key |
| `OPENAI_API_KEY` | Alt LLM | — | OpenAI API key |
| `SITE_URL` | No | `http://localhost:3000` | Website URL |
| `SITE_API_URL` | No | `http://localhost:3000` | API URL |
| `ADMIN_PASSWORD` | No | — | Admin panel password |
| `VIDEO_LENGTH` | No | `60` | Target video duration (seconds) |
| `VIDEO_ASPECT_RATIO` | No | `9:16` | Video aspect ratio |
| `CONTENT_LANGUAGE` | No | `en` | Content language (`en`/`zh`) |
