# Validate Quality

## When to Use
- After generating a video clip (per-clip check)
- After generating all clips for a scene (consistency check)
- Before assembling clips into a final episode (scene-level check)
- Before publishing an episode (episode-level check)
- When @showrunner needs a quality report for decision-making

## Procedure

### Per-Clip Validation (@artist)
```bash
python agents/validate_quality.py --clip data/episodes/<ep_number>/scenes/scene_<n>_clip_<m>.mp4
```
Checks: duration (2.5–7s), fps (≥20), resolution (≥480p), black frames (<15%), static frames (<30%), file size (≥100KB)

### Scene Consistency Validation (@artist)
```bash
python agents/validate_quality.py --scene data/episodes/<ep_number>/scenes/ --scene-number <n>
```
Checks: cross-clip continuity (SSIM ≥0.70), color drift (<20%), brightness drift (<15%), minimum clips per scene

### Episode Validation (@editor / @showrunner)
```bash
python agents/validate_quality.py --episode <ep_number>
```
Checks: total duration (150–210s), minimum scenes (6+), all scenes pass quality, audio present, content policy

### Save Report
```bash
python agents/validate_quality.py --episode <n> --output data/episodes/<n>/quality_report.yaml
```

## Parameters
- `--clip` — Path to a single clip to validate
- `--scene` — Path to scenes directory (used with `--scene-number`)
- `--scene-number` — Scene number to validate
- `--episode` — Episode number for full validation
- `--output` — Save YAML report to file

## Exit Codes
- `0` — All checks passed
- `1` — One or more checks failed (see output for details)

## On Failure
- **Clip**: Regenerate with new seed (up to 3 attempts), then escalate
- **Consistency**: Regenerate the clip causing the break
- **Scene**: Block assembly until all clips pass
- **Episode**: Block publishing until resolved
