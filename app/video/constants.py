"""Video composition constants."""

# Timeline timing constants (in seconds)
BRAND_INTRO_END = 2.0
HOOK_END = 5.0
INTRO_END = 12.0
OUTRO_BUFFER = 7.0
MIN_BODY_DURATION = 5.0
CTA_MAX_DURATION = 4.0

# Font size adjustments relative to base style.font_size
FONT_SIZE_BRAND_INTRO = 24  # +24 for brand intro
FONT_SIZE_HOOK = 16  # +16 for hook
FONT_SIZE_SUBTITLE = 36  # +36 for subtitles
FONT_SIZE_OUTRO = 20  # +20 for outro

# Stroke width for text
STROKE_WIDTH_DEFAULT = 2
STROKE_WIDTH_SUBTITLE = 4

# Colors
COLOR_WHITE = "#FFFFFF"
COLOR_DARK_BACKGROUND = "#0A0A0A"
COLOR_STROKE = "#000000"

# Text overlay positions (y-axis as percentage of height)
POSITION_CENTER_Y = 0.45
POSITION_CTA_Y = 0.5
POSITION_SUBTITLE_Y = 0.38  # Above center to prevent bottom clipping

# Text margin padding (prevents stroke cutoff - MoviePy issue #2268)
# Increased vertical margin to prevent bottom clipping on multi-line text
SUBTITLE_MARGIN = (20, 60)

# Text width constraints (subtracted from format width)
TEXT_WIDTH_MARGIN = 120
SUBTITLE_WIDTH_MARGIN = 100

# Brand text constants
BRAND_NAME = "NOYAU NEWS"
BRAND_FOLLOW_CTA = "FOLLOW @NOYAUNEWS"

# Combined video timeline constants
COMBINED_BRAND_INTRO_END = 2.0
COMBINED_HOOK_END = 5.0
COMBINED_INTRO_END = 10.0
COMBINED_CTA_DURATION = 5.0

# Story segment timing for combined video
STORY_TRANSITION_DURATION = 2.5  # Duration for "Story one." transition
STORY_HEADLINE_DURATION = 3.0  # Duration for headline overlay

# Combined video font sizes
FONT_SIZE_STORY_NUMBER = 72  # Large number for story indicators (1, 2, 3)
FONT_SIZE_STORY_HEADLINE = 40  # Story headline overlay

# Combined video positions
POSITION_STORY_NUMBER_Y = 0.35
POSITION_STORY_HEADLINE_Y = 0.50
