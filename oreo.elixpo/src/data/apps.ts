/* Single source of truth for the app catalogue surfaced on the site.
 * Mirrors the manifest.json files shipped on the badge, but lives
 * here (not auto-generated) so we can curate the order, blurbs, and
 * which apps make the home carousel cut. The badge itself reads its
 * own manifest.json files — this list is purely marketing.
 *
 * The `icon` field is a string ID that AppCard.tsx maps to a
 * lucide-react component — using a string rather than the component
 * directly so this file stays free of React imports and can be
 * consumed by both client and server components without complaint.
 */

export type AppIconId =
  | "Contact" | "Bird"     | "Image"      | "Worm"      | "Compass"
  | "BookOpen"| "Car"      | "Cloud"      | "GitCommit" | "User"
  | "Gamepad2"| "HardDrive"| "Palette"    | "PawPrint"  | "Cpu"
  | "Wifi"    | "Bluetooth"| "RefreshCw"  | "Settings";

export type AppEntry = {
  slug: string;
  name: string;
  blurb: string;
  category: "core" | "game" | "tool" | "store";
  tint:  "primary" | "teal" | "gold" | "lilac";
  icon:  AppIconId;
};

export const PRELOADED: AppEntry[] = [
  { slug: "badge",    name: "Badge",       category: "core", tint: "primary", icon: "Contact",
    blurb: "Conference badge with your name, role, pronouns." },
  { slug: "flappy",   name: "Flappy Oreo", category: "game", tint: "lilac",   icon: "Bird",
    blurb: "Flap the panda. Dodge pipes. High score persists." },
  { slug: "gallery",  name: "Gallery",     category: "core", tint: "gold",    icon: "Image",
    blurb: "Photo viewer with thumbnail carousel. Auto-hiding UI." },
  { slug: "snake",    name: "Snake",       category: "game", tint: "teal",    icon: "Worm",
    blurb: "The original. Eat the dot, don't bite yourself." },
  { slug: "quest",    name: "IR Quest",    category: "game", tint: "primary", icon: "Compass",
    blurb: "IR-beacon scavenger hunt. Find 9 stations, trade tokens." },
  { slug: "reader",   name: "Reader",      category: "tool", tint: "lilac",   icon: "BookOpen",
    blurb: "Markdown + text viewer. AirDrop a .md, read it on the go." },
];

export const ALL_APPS: AppEntry[] = [
  ...PRELOADED,
  { slug: "racer",    name: "Racer",     category: "game", tint: "primary", icon: "Car",
    blurb: "Top-down arcade racer. UP/DOWN steer, A boosts." },
  { slug: "weather",  name: "Weather",   category: "tool", tint: "teal",    icon: "Cloud",
    blurb: "Current conditions + 3-day forecast." },
  { slug: "commits",  name: "Commits",   category: "tool", tint: "gold",    icon: "GitCommit",
    blurb: "Live GitHub commit feed from your followed repos." },
  { slug: "identity", name: "Identity",  category: "core", tint: "lilac",   icon: "User",
    blurb: "Name, handle, contact card — share over IR." },
  { slug: "gamepad",  name: "Gamepad",   category: "tool", tint: "primary", icon: "Gamepad2",
    blurb: "Bluetooth gamepad mode for your laptop." },
  { slug: "storage",  name: "Storage",   category: "tool", tint: "lilac",   icon: "HardDrive",
    blurb: "Flash usage by app + asset bundle." },
  { slug: "wifi",     name: "WiFi",      category: "core", tint: "teal",    icon: "Wifi",
    blurb: "Saved networks, file transfer, ping + speed test." },
  { slug: "bt",       name: "Bluetooth", category: "core", tint: "lilac",   icon: "Bluetooth",
    blurb: "Peer presence (coming soon). Pairing + bonded list." },
  { slug: "updates",  name: "Updates",   category: "core", tint: "gold",    icon: "RefreshCw",
    blurb: "OTA over WiFi. LTS / BETA / OUTDATED states." },
  { slug: "settings", name: "Settings",  category: "core", tint: "primary", icon: "Settings",
    blurb: "Brightness, sleep timer, gestures, theme." },
];

export const STORE: AppEntry[] = [
  { slug: "Colors",   name: "Color Picker", category: "store", tint: "lilac",   icon: "Palette",
    blurb: "HSV picker — UP/DOWN sweeps each channel." },
  { slug: "Oreo Pet", name: "Oreo Pet",     category: "store", tint: "primary", icon: "PawPrint",
    blurb: "Tamagotchi panda. Feed, play, sleep, repeat." },
];
