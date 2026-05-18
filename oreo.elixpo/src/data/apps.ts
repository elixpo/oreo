/* Single source of truth for the app catalogue surfaced on the site.
 * Mirrors the manifest.json files shipped on the badge, but
 * intentionally lives here (not auto-generated) so we can curate the
 * order, the long-form descriptions, and which apps make the home
 * carousel cut. The badge itself reads its own manifest.json files —
 * this list is purely marketing. */

export type AppEntry = {
  slug: string;            // matches apps/<slug>/ on the badge
  name: string;            // display name (manifest.name)
  blurb: string;           // 1-sentence pitch for the marketing card
  category: "core" | "game" | "tool" | "store";
  tint: "primary" | "teal" | "gold" | "lilac";
  glyph: string;           // single-char placeholder until we ship pngs
};

export const PRELOADED: AppEntry[] = [
  { slug: "badge",   name: "Badge",       blurb: "Conference badge with your name, role, pronouns.",           category: "core",  tint: "primary", glyph: "B" },
  { slug: "flappy",  name: "Flappy Oreo", blurb: "Flap the panda. Dodge pipes. High score persists.",          category: "game",  tint: "lilac",   glyph: "F" },
  { slug: "gallery", name: "Gallery",     blurb: "Photo viewer with thumbnail carousel. Auto-hiding UI.",      category: "core",  tint: "gold",    glyph: "G" },
  { slug: "snake",   name: "Snake",       blurb: "The original. Eat the dot, don't bite yourself.",            category: "game",  tint: "teal",    glyph: "S" },
  { slug: "quest",   name: "IR Quest",    blurb: "IR-beacon scavenger hunt. Find 9 stations, trade tokens.",   category: "game",  tint: "primary", glyph: "Q" },
  { slug: "reader",  name: "Reader",      blurb: "Markdown + text viewer. AirDrop a .md, read it on the go.",  category: "tool",  tint: "lilac",   glyph: "R" },
];

export const ALL_APPS: AppEntry[] = [
  ...PRELOADED,
  { slug: "racer",    name: "Racer",         blurb: "Top-down arcade racer. UP/DOWN steer, A boosts.",        category: "game",  tint: "primary", glyph: "R" },
  { slug: "weather",  name: "Weather",       blurb: "Current conditions + 3-day forecast.",                   category: "tool",  tint: "teal",    glyph: "W" },
  { slug: "commits",  name: "Commits",       blurb: "Live GitHub commit feed from your followed repos.",      category: "tool",  tint: "gold",    glyph: "C" },
  { slug: "identity", name: "Identity",      blurb: "Name, handle, contact card — share over IR.",            category: "core",  tint: "lilac",   glyph: "I" },
  { slug: "gamepad",  name: "Gamepad",       blurb: "Bluetooth gamepad mode for your laptop.",                category: "tool",  tint: "primary", glyph: "G" },
  { slug: "storage",  name: "Storage",       blurb: "Flash usage by app + asset bundle.",                     category: "tool",  tint: "muted",   glyph: "D" } as any,
];

export const STORE: AppEntry[] = [
  { slug: "Colors",   name: "Color Picker", blurb: "HSV picker — UP/DOWN sweeps each channel.",              category: "store", tint: "lilac",   glyph: "C" },
  { slug: "Oreo Pet", name: "Oreo Pet",     blurb: "Tamagotchi panda. Feed, play, sleep, repeat.",           category: "store", tint: "primary", glyph: "O" },
];
