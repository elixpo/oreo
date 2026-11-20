# FaleraOS sponsor deck

The sponsor pitch deck as plain HTML: one file per slide, each a fixed
1920×1080 page, and a script that renders them to PNGs and a PDF. It is not
part of the website.

```
pitch-deck/
  style.css      shared styles: colours, type, the 1920x1080 canvas, bow bullets, footer, Lumi's corner mark
  slides/        one HTML file per slide; filename order is slide order
  assets/        images the slides use
  render.py      renders slides/*.html to out/NN.png and out/FaleraOS-pitch.pdf
  out/           rendered output (git-ignored)
```

## Install

```bash
python3 -m pip install playwright pillow
python3 -m playwright install chromium-headless-shell
```

`render.py` uses, in order: `$CHROME` if set, Playwright's
`chrome-headless-shell` from its browser cache (`~/.cache/ms-playwright`),
then Playwright's own Chromium (`python3 -m playwright install chromium`).

## Edit a slide

1. Open `slides/NN-name.html` in an editor. Each slide is a complete page:
   a `<style>` block for its own layout, then the slide, with short comments
   marking each part. Shared classes (`.title`, `.lede`, `.p`, `.small`,
   `.card`, `.list`, `.eyebrow`, `.footer`, …) are in `style.css`.
2. Preview it by opening the file in a browser (double-click it). The slide
   is drawn at 1920×1080; zoom the browser out to see all of it.
3. Render it: `python3 render.py --only NN`, then look at `out/NN.png`.

Italic emphasis in a title is `<em>…</em>` (Georgia). A bow-bulleted list is

```html
<ul class="list">
  <li><img class="bow" src="../assets/bow.svg" alt="">First point</li>
</ul>
```

Fonts are system fonts (Arial, Georgia and the system monospace), so slides
open offline and render the same as long as the machine has the same fonts.

## Add, remove or reorder slides

Slides are rendered in filename order, so the two-digit prefix is the
position. To add one, copy a similar slide, give it the right number and
renumber the files after it. To remove or reorder, rename the files so the
numbers run 01, 02, … again.

Each footer has its number written in by hand:

```html
<span class="num">4 / 13</span>
```

After adding, removing or reordering, update the footer (and `<title>`) in
every slide. `render.py` warns about any footer whose `n / N` doesn't match
the file's position and the slide count.

## Render

```bash
python3 render.py                 # every slide to out/01.png … and out/FaleraOS-pitch.pdf
python3 render.py --only 04       # one slide (no PDF)
python3 render.py --scale 2       # 3840x2160 PNGs for a crisper PDF
python3 render.py --out ~/Documents/falera-pitch
```

It prints each file it writes. The PDF has one 16:9 page per slide holding
the PNG's pixels unchanged (lossless).

## Images

All in `assets/`:

| File | What | Used on |
|---|---|---|
| `lumi-badge.webp` | Lumi, the Falera panda, holding a badge | 1, 13 |
| `lumi-mark.webp` | Lumi's small corner mark | 2–12 |
| `bow.svg` | Lumi's bow: bullets, eyebrows, cards | all |
| `board-angle.webp` | Render of the Falera Badge PCB | 3 |
| `pcb_back.jpg` | Photo of the back of the first boards | 4 |
| `oshw_mark.png` | OSHWA certification mark, IN000107 | 4 |
| `photo_portrait.jpg` | FaleraOS on the breadboard badge | 5 |

The photos and the OSHWA mark are copies of the ones in
`falera.elixpo/public/`.

## Where the facts come from

Every number and name on a slide comes from one of these sources. Check the
source before changing a figure, and don't add a figure, supporter or
partner that isn't in one.

1. **Title:** OSHWA certificate IN000107 (README.md).
2. **The problem:** EMAILS_BATCH2.md, the FOSS United "Why it matters" and NIDHI-PRAYAS "Problem" sections.
3. **What Falera is:** README.md; LAUNCH_KIT.md one-line pitch; licences from README.md.
4. **The hardware:** circuit/elixpo/README.md and BOM_COST.md (origin/pcb-bringup), README.md hardware table; ₹4,171.70 is the BOM_COST.md total of the prices paid on 17 Nov 2026.
5. **The software:** README.md (apps, App Store, updates, CLI); apps_market/index.json (10 apps); PR #197 (audio apps, in review).
6. **Built so far:** CHANGELOG.md (v1.4.19, v2.0.0); README.md press section (Adafruit, Espressif USB ID); cli/CHANGELOG.md (1.0.0); BOM_COST.md (orders of 17 Nov 2026); PR #180 (PCB support).
7. **RV565:** elixpo/rv565 README.md and docs/RESULTS_V8.md (badge measurements of 20 Nov 2026; format version 8 = RV565 3.0); README.md press section.
8. **Recognition:** README.md "In the press" and "Recognised upstream"; the fundraiser API (payouts.elixpo.com/f/falera-badge, read 20 Nov 2026: ₹781 from 13 contributors); FUNDRAISER_APPEAL.md (about ₹8,000 spent out of pocket).
9. **Where it goes:** EMAILS_BATCH2.md (FOSS United milestones; NIDHI note's projected ₹3,000 a badge at 100 units); SPONSORS.md (IndiaFOSS 2027, FOSSASIA Summit 2027 as events to approach); README.md (GSoC 2027: Elixpo is applying, not accepted).
10. **The ask:** EMAILS_BATCH2.md, FOSS United budget table (the lines add up to ₹3,00,000).
11. **What sponsors get:** SPONSORS.md "What to send each type" and the "In return" lines of EMAILS_BATCH2.md drafts 1–4. SPONSORS.md defines no tiers, so none are shown.
12. **Team:** README.md "Built by the community" and "Recognition & programs"; EMAILS_BATCH2.md team section. No photos in the repository, so initials are shown.
13. **Contact:** README.md closing line (hello@elixpo.com).
