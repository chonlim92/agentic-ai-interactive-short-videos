# Episode Generation Pipeline

**Author: Chong Kiat Lim**

The generation pipeline transforms a story concept into a fully produced animated short video through 8 automated stages. Each stage is handled by a specialized AI agent and can be run individually or as a full pipeline.

## Pipeline Overview

```
┌─────────┐   ┌─────────┐   ┌────────────┐   ┌───────────┐
│ 1.Script│──►│2.Scenes │──►│3.Characters│──►│4.Video Gen│
│ (Writer)│   │(Director)   │(Designer)  │   │ (Artist)  │
└─────────┘   └─────────┘   └────────────┘   └───────────┘
                                                    │
┌─────────┐   ┌─────────┐   ┌─────────┐    ┌──────▼──────┐
│8.Publish│◄──│7.Compose│◄──│ 6.Audio │◄───│ 5.Quality  │
│(Publisher)  │ (Editor)│   │ (Sound) │    │   (QA)     │
└─────────┘   └─────────┘   └─────────┘    └────────────┘
```

The admin UI shows real-time progress through all stages:

![Pipeline Progress](images/StorySmithAI_gui_WriterAgent_ScriptStep.jpg)

## Stage 1: Script Generation

**Agent:** @writer | **Model:** Anthropic Claude / OpenAI GPT-4 | **Script:** `agents/generate_episode.py`

The Writer agent generates an episode script based on the story bible, previous episode context, and audience vote results.

**Inputs:**
- `data/stories/{slug}/story_bible.yaml` — world, characters, narrative arc
- `data/stories/{slug}/episodes/{n-1}/engagement.yaml` — previous episode votes and moderated comments
- Admin prompt (optional) — manual story direction override

**Process:**
1. Load story bible and character sheets
2. If episode > 1, load previous episode's vote results and winning option
3. Call LLM (Writer agent persona) with story context + vote results
4. Generate structured script YAML with 6–8 scenes, each containing:
   - Scene description, location, mood, lighting
   - Characters present
   - Dialogue lines with speaker and tone
   - Camera notes
5. Append 2–4 branching vote options for the audience poll

**Output:** `data/stories/{slug}/episodes/{n}/script.yaml`

**Configuration:**
- `VIDEO_LENGTH` env var controls target duration (default 60s, range 30–180s)
- `CONTENT_LANGUAGE` env var sets script language (en/zh)

![Script Generation UI](images/StorySmithAI_gui_WriterAgent_ScriptStep.jpg)

## Stage 2: Scene Breakdown

**Agent:** @director | **Model:** Anthropic Claude / OpenAI GPT-4

The Director agent breaks the script into detailed scene-by-scene shot lists with text-to-video prompts for each clip.

**Inputs:**
- Episode script from Stage 1
- Style guide (`data/stories/{slug}/style_guide.yaml`)
- Character reference sheets

**Process:**
1. Analyze script scenes for visual requirements
2. For each scene, generate 2–5 clip prompts with:
   - Detailed text-to-video prompt (visual description)
   - Negative prompt (what to avoid)
   - Camera angle and movement
   - Character positions and actions
   - Continuity notes (reference to previous clip's last frame)
   - Dialogue/narration text for the clip
3. Ensure visual continuity across clips within a scene

**Output:**
- `scenes_breakdown.yaml` — master scene plan
- `scenes/scene_{n}_clip_{m}_prompt.yaml` — individual clip prompts

![Scene Breakdown UI](images/StorySmithAI_gui_DirectorAgent_ScenesStep.jpg)

## Stage 3: Character Design

**Agent:** @character-designer | **Model:** Anthropic Claude / OpenAI GPT-4 + HuggingFace (image generation)

The Character Designer ensures visual consistency for all characters across clips and episodes.

**Inputs:**
- Character YAML sheets from `data/stories/{slug}/characters/`
- Style guide
- Script character list

**Process:**
1. Review existing character sheets
2. Generate or update character reference images (avatars)
3. Create consistency guidelines for the Artist
4. Define pose/outfit variations needed for each scene

**Output:**
- `characters.yaml` — episode-specific character references
- `characters/avatars/*.png` — character avatar images
- Updated character YAML sheets

![Character Design UI](images/StorySmithAI_gui_CharacterDesignerAgent_CharacterStep.jpg)

## Stage 4: Video Generation

**Agent:** @artist | **Model:** Seedance 2.0 (BytePlus) / CogVideoX / Wan2.1 / AnimateDiff | **Script:** `agents/generate_video.py`

The Artist agent generates video clips from the Director's prompts using AI video generation models.

**Inputs:**
- Scene clip prompt YAMLs from Stage 2
- Character reference images from Stage 3
- Previous clip's last frame (for continuity)

**Process:**
1. For each clip prompt YAML:
   - Build the text-to-video request with prompt, negative prompt, dimensions
   - If continuity mode is enabled, use last frame of previous clip as reference (image-to-video)
   - Submit to the configured video model API
   - For BytePlus/Seedance: POST task → poll until complete → download
   - For HuggingFace: Direct inference API call
2. Save generated clip to `clips/{timestamp}/scene_{n}_clip_{m}.mp4`
3. Run clip-level quality validation on each output

**Supported Models:**

| Model | Provider | API Pattern | Duration | Default |
|-------|----------|-------------|----------|---------|
| **Seedance 2.0** | BytePlus Ark | Task-based (POST + poll) | 5–10s | ✓ |
| CogVideoX-5B | HuggingFace | Inference API | 3–6s | |
| Wan2.1-T2V-14B | HuggingFace | Inference API | 3–6s | |
| HunyuanVideo | HuggingFace | Inference API (fallback) | 3–6s | |
| AnimateDiff-Lightning | HuggingFace | Inference API | 3–6s | |

**Video Specifications:**
- Resolution: 720×1280 (9:16 vertical, TikTok/Reels format)
- FPS: 24
- Quality presets: draft (20 steps), standard (30 steps), high (50 steps)

**Output:** `clips/{timestamp}/scene_*.mp4`

![Video Generation UI](images/StorySmithAI_gui_ArtistAgent_VideoGenStep.jpg)

## Stage 5: Quality Validation

**Agent:** @artist / @showrunner | **Script:** `agents/validate_quality.py`

The Quality gate validates all generated clips against configurable thresholds.

**Clip-Level Checks:**

| Check | Threshold | Description |
|-------|-----------|-------------|
| Duration | 2.5–12.0s | Clip must be within duration range |
| FPS | ≥ 20 | Minimum frame rate |
| Resolution | ≥ 480p | Minimum vertical resolution |
| Black frames | < 15% | Ratio of mostly-black frames |
| Static frames | < 30% | Ratio of frames with no motion |
| File size | ≥ 100 KB | Minimum file size |
| Object consistency | shift < 0.6 | Detects morphing/changing objects |

**Scene Consistency Checks:**

| Check | Threshold | Description |
|-------|-----------|-------------|
| Color drift | < 20% | Histogram change between clips |
| Brightness drift | < 15% | Average brightness change |
| SSIM continuity | ≥ 0.70 | Structural similarity between clip transitions |

**Failure Handling:**
- Clips that fail get flagged with "NEEDS REVIEW" badge
- AI suggestions are generated for how to fix each issue
- Clips can be regenerated with an optional improvement prompt
- Side-by-side comparison of original vs. regenerated clips

![Quality Inspection](images/StorySmithAI_gui_QualityInspectionAgent_QualityStep.jpg)

![AI Suggestions for Failed Clips](images/StorySmithAI_gui_QualityInspectionAgent_with_AIPromptSuggestion.jpg)

![Clip Regeneration Comparison](images/StorySmithAI_gui_QualityInspectionAgent_with_Regeneration.jpg)

## Stage 6: Audio Generation

**Agent:** @sound-designer | **Model:** MusicGen / Bark | **Script:** `agents/generate_audio.py`

The Sound Designer generates background music and optionally narration for each scene.

**Inputs:**
- Script with mood/tone descriptions per scene
- Audio plan YAML (from sound-designer agent)

**Models:**

| Model | Purpose | Provider |
|-------|---------|----------|
| MusicGen (facebook/musicgen-medium) | Background music | HuggingFace Inference API |
| Bark (suno/bark) | Text-to-speech narration | HuggingFace Inference API |

**Modes:**
- **Music only** (default) — generates background music, keeps original clip audio
- **Full audio** — replaces all audio with generated music + narration

**Output:** `audio/{timestamp}/*.wav`

## Stage 7: Episode Composition

**Agent:** @editor | **Script:** `agents/compose_episode.py`

The Editor assembles all clips and audio into the final episode video.

**Inputs:**
- All clips from `clips/{timestamp}/`
- Audio files from `audio/{timestamp}/`
- Composition config (`config/composition.yaml`)

**Process:**
1. Discover and sort clips in natural order (scene_1_clip_1, scene_1_clip_2, etc.)
2. Apply transitions:
   - **Within scenes:** seamless blending (0.2s overlap)
   - **Between scenes:** crossfade (0.8s overlap)
3. Add intro card (5s) and outro card (5s)
4. Mix audio layers (music volume 0.6, SFX 0.8, narration 1.0)
5. Apply watermark ("StorySmith AI · 剧匠AI")
6. Export as H264 MP4, 720p, 24fps, 8Mbps bitrate
7. Generate bilingual subtitles (if Auto Subtitles enabled)

**Composition Options (Admin UI):**
- **Mute Video Audio** — strip original audio from clips
- **No Watermark** — skip logo watermark overlay
- **Auto Subtitles** — transcribe audio and burn bilingual subtitles
- **Skip Opening** — skip title card and AI disclaimer intro

**Output:** `compose/{timestamp}/episode_{n}.mp4`

![Compose Step](images/StorySmithAI_gui_EditorAgent_ComposeStep.jpg)

## Stage 8: Publishing

**Agent:** @publisher | **Script:** `agents/publish_site.py`

The Publisher deploys the finished episode to the website with voting poll and gallery.

**Process:**
1. Copy final video to `final/video/episode_{n}.mp4`
2. Generate EN and ZH versions of the video (different subtitle/audio tracks)
3. Generate 4 poster variants:
   - `poster_horizontal_en.png` — 16:9 English poster
   - `poster_horizontal_zh.png` — 16:9 Chinese poster
   - `poster_vertical_en.png` — 9:16 English poster
   - `poster_vertical_zh.png` — 9:16 Chinese poster
4. Extract gallery screenshots from key frames
5. Generate story-level poster (if first episode)
6. Update `site/data/store.json` with:
   - Episode metadata (title, description, video URLs)
   - Voting poll options (from writer's branching choices)
   - Gallery image URLs
7. Set episode status to "published" with voting open

**Output:**
- `final/video/episode_{n}.mp4` + `episode_{n}_EN.mp4`
- `final/poster/poster_{orientation}_{locale}.png` (4 variants)
- `final/gallery/gallery_*.jpg`
- Updated `site/data/store.json`

![Publish Step](images/StorySmithAI_gui_PublisherAgent_PublishStep.jpg)

## Running the Pipeline

### Via Admin Panel

1. Go to **Admin → Generate**
2. Select **Story** and **Episode**
3. Configure options (LLM model, video model, execution mode, aspect ratio, visual style, audio model)
4. Click **Run Full Pipeline** or run individual steps
5. Monitor progress with live progress bars and time tracking
6. Review outputs at each step — expand to view generated files

### Via CLI

```bash
# Full pipeline
python agents/generate_episode.py --story my-story --episode 1

# Individual steps
python agents/generate_video.py --scene data/stories/my-story/episodes/1/scenes/scene_1_clip_1_prompt.yaml --model seedance2.0
python agents/validate_quality.py --story my-story --episode 1
python agents/generate_audio.py --story my-story --episode 1 --model musicgen
python agents/compose_episode.py --story my-story --episode 1 --transitions crossfade
python agents/publish_site.py --story my-story --episode 1
```

### Via Chat Agents

```
@showrunner generate episode 1 for "the-ancient-without-a-plug"
@artist generate all clips for episode 1
@editor compose episode 1 with crossfade transitions
@publisher deploy episode 1 with voting poll
```
