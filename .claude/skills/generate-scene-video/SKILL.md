# Generate Scene Video

## When to Use
- User asks to generate a video clip for a scene
- Artist needs to produce video from a director's prompt
- Pipeline requires scene-level video generation

## Procedure
1. Read the scene prompt file: `data/episodes/<ep_number>/scenes/scene_<n>_prompt.yaml`
2. Verify character references exist in `data/characters/`
3. Run video generation:
   ```bash
   python agents/generate_video.py --scene data/episodes/<ep_number>/scenes/scene_<n>_prompt.yaml
   ```
4. Check output quality (file exists, duration matches spec)
5. Save output to `data/episodes/<ep_number>/scenes/scene_<n>.mp4`

## Parameters
- `--model` — Model to use (cogvideox, wan2, animatediff, svd). Default: cogvideox
- `--quality` — Quality preset (draft, standard, high). Default: standard
- `--seed` — Random seed for reproducibility
