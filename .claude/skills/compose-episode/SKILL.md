# Compose Episode

## When to Use
- User asks to assemble scene clips into a final episode
- Editor needs to stitch scenes together
- All scene videos are generated and ready

## Procedure
1. Verify all scene clips exist in `data/episodes/<ep_number>/scenes/`
2. Read audio mix spec from `data/episodes/<ep_number>/audio/mix.yaml`
3. Run episode composition:
   ```bash
   python agents/compose_episode.py --episode <ep_number>
   ```
4. Verify final output at `data/episodes/<ep_number>/final/episode_<n>.mp4`
5. Check duration, resolution, and audio sync

## Parameters
- `--episode` — Episode number to compose
- `--transitions` — Transition style (crossfade, cut, wipe). Default: crossfade
- `--intro` — Include intro sequence (true/false). Default: true
- `--outro` — Include outro sequence (true/false). Default: true
