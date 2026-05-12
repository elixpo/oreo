"""Elixpo Badge — unified colour theme derived from the panda mascot.

Mascot reference palette:
  Dark outline  rgb(38,  38,  48)   — panda shadow / body patches
  White fur     rgb(200, 204, 203)  — panda fur
  Cheek pink    rgb(255,  93, 104)  — blush / accent
  Badge red     rgb(200,  40,  50)  — E-badge on chest

All UI modules import from here. Do NOT define colours anywhere else.

Raw RGB values are also exported (BG_R/G/B etc.) for PIL compositing
calls that can't use api.rgb() directly.
"""

from lix import api

# ── raw component triplets (for PIL / math operations) ────────────────────────

BG_R, BG_G, BG_B           = 14,  12,  20   # near-black warm dark
CARD_R, CARD_G, CARD_B     = 22,  18,  30   # slightly lighter card
PRIMARY_R, PRIMARY_G, PRIMARY_B = 255, 93, 104   # panda cheek pink
TEAL_R, TEAL_G, TEAL_B     = 0,  180, 165   # cool teal (used in splash/accents)
GOLD_R, GOLD_G, GOLD_B     = 255, 200,  60  # badge E gold
FUR_R, FUR_G, FUR_B        = 220, 215, 210  # panda fur near-white (clock/title)
DARK_R, DARK_G, DARK_B     = 38,   38,  48  # panda dark outline
MUTED_R, MUTED_G, MUTED_B  = 120, 100, 130  # warm muted purple

# ── RGB565 colour values ───────────────────────────────────────────────────────

BG           = api.rgb(BG_R,      BG_G,      BG_B)       # page background
CARD         = api.rgb(CARD_R,    CARD_G,    CARD_B)     # card / surface
PRIMARY      = api.rgb(PRIMARY_R, PRIMARY_G, PRIMARY_B)  # pink — main accent
TEAL         = api.rgb(TEAL_R,    TEAL_G,    TEAL_B)     # cool teal
GOLD         = api.rgb(GOLD_R,    GOLD_G,    GOLD_B)     # warm gold
TEXT_BRIGHT  = api.rgb(FUR_R,     FUR_G,     FUR_B)      # bright text (clocks, titles)
TEXT_DIM     = api.rgb(DARK_R,    DARK_G,    DARK_B)     # dark text on light bg
MUTED        = api.rgb(MUTED_R,   MUTED_G,   MUTED_B)    # subdued labels
MUTED2       = api.rgb(70,  58,  80)                     # dimmer variant
STATUS_BG    = api.rgb(10,   8,  16)                     # status bar background
DOCK_BG      = api.rgb(18,  14,  26)                     # dock background
DOCK_SEL     = api.rgb(60,  20,  28)                     # selected dock item fill
SEL_BORDER   = api.rgb(255, 93, 104)                     # selection border (pink)
