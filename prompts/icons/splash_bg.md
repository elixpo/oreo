# Boot splash background — `splash_bg`

**Size:** 320×240 (full-screen, landscape)
**Optimiser bucket:** `splash_bg`

## Visual brief

A rich, festive scene that the OS dims to ~25% brightness and uses as the
boot splash backdrop behind the white-on-dark mascot + title.

Think: panda-themed conference-confetti vibe — sparse balloons, soft pink
clouds, gold confetti dots, a glow gradient. Dense enough to look cared-for
but with mid-tones simple enough to survive heavy dimming (anything too
detailed turns into mud once dimmed).

Avoid hard pure-white highlights (they'll still read after dim and clash
with the title text). Avoid putting any subject inside the centre 160×100
rectangle — that's where the mascot + "OREO OS" + tagline sit.

## Style

- Flat colour blocks with light pixel-art shading; no photoreal gradients.
- Reuse the theme palette in [THEME.md](THEME.md):
  pink #FF5D68, gold #FFBE1E, teal #00B4A5, cream #FFF8EB.
- Confetti / balloon clusters in the upper-left and lower-right corners
  so the centre stays clear for the logo stack.

## Negative prompts

- No text, no letters, no numbers.
- No human faces, no badge mockups, no UI chrome.
- No pure white shapes larger than ~10 px.
