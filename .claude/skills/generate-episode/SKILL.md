# Generate Episode Script

## When to Use
- User asks to generate a new episode script
- Showrunner triggers episode creation
- Writer needs to produce a full episode script
- The user prompt asks you to "generate", "write", or "create" an episode script

## Output Format
You MUST respond with ONLY valid YAML (no preamble, no explanations, no markdown fences).
The YAML must be a single mapping with these top-level keys:

```yaml
episode: <number>
title: "<episode title>"
title_zh: "<Chinese title>"
duration_seconds: 120
scene_count: <6-8>
scenes:
  - scene_number: 1
    title: "<scene title>"
    time_range: "0:00-0:20"
    duration_seconds: 20
    location: "<setting description>"
    time_of_day: "<Day/Night/Dawn/Dusk>"
    characters_present:
      - "<character name>"
    visual_description: "<what happens visually>"
    dialogue:
      - character: "<name>"
        line: "<what they say>"
        line_zh: "<Chinese translation>"
    mood: "<emotional tone>"
    camera_notes: "<optional camera direction>"
voting_options:
  - label: "<choice A>"
    label_zh: "<Chinese>"
    description: "<what this choice means for the story>"
  - label: "<choice B>"
    label_zh: "<Chinese>"
    description: "<what this choice means>"
visual_style: "<overall visual style>"
color_palette: ["<color1>", "<color2>"]
mood: "<overall episode mood>"
music_style: "<music direction>"
```

## Procedure
1. Read the story bible and style guide provided in the prompt
2. Read previous episode scripts (if provided) to maintain continuity
3. Read vote results (if provided) to incorporate audience choices
4. Generate episode script with 6-8 scenes targeting ~120 seconds total
5. Ensure each scene has enough visual detail for video generation
6. Propose 2-3 voting options for the audience at the end
7. Respond with ONLY the YAML — no other text

## Critical Rules
- Total duration must be approximately 120 seconds
- Each scene should be 15-30 seconds
- Include Chinese translations for titles and dialogue
- The YAML output must parse correctly with no extra text around it
