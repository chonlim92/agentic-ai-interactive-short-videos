# Data Directory Structure
#
# data/
#   stories/
#     _template/          ← Copy this folder to create a new story
#       story_bible.yaml
#       style_guide.yaml
#       characters/
#       locations/
#       episodes/
#     {story-slug}/       ← One folder per story (e.g., "neon-city-2099")
#       story_bible.yaml  ← World, characters, narrative state for this story
#       style_guide.yaml  ← Visual consistency rules for this story
#       characters/       ← Character YAML sheets
#       locations/        ← Location YAML sheets
#       episodes/         ← Generated episode assets (scenes, audio, final video)
#         1/
#           scenes/
#           audio/
#           final/
#         2/
#           ...
#
# When a new story is created via the admin UI, its slug determines the folder name.
# The Python agents read from data/stories/{slug}/ for all story-specific assets.
