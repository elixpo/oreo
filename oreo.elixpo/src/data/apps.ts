/* Single source of truth for the app catalogue surfaced on the site.
 * Mirrors the manifest.json files shipped on the badge.
 *
 * `pngIcon` is the path under /public; AppCard renders the real PNG
 * from the badge's asset bundle (copied via `cp assets/icons/raw/*
 * → oreo.elixpo/public/icons/`). `icon` is a Lucide string fallback
 * for the rare case the PNG is missing or fails to load.
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
  pngIcon?: string;        // resolved from /public/icons
};

export const PRELOADED: AppEntry[] = [
  { slug: "badge",    name: "Badge",       category: "core", tint: "primary", icon: "Contact",
    pngIcon: "/icons/badge_icon.png",
    blurb: "Conference badge with your name, role, pronouns." },
  { slug: "flappy",   name: "Flappy Oreo", category: "game", tint: "lilac",   icon: "Bird",
    pngIcon: "/icons/flappy_icon.png",
    blurb: "Flap the panda. Dodge pipes. High score persists." },
  { slug: "gallery",  name: "Gallery",     category: "core", tint: "gold",    icon: "Image",
    pngIcon: "/icons/gallery_icon.png",
    blurb: "Photo viewer with thumbnail carousel. Auto-hiding UI." },
  { slug: "snake",    name: "Snake",       category: "game", tint: "teal",    icon: "Worm",
    pngIcon: "/icons/snake_icon.png",
    blurb: "The original. Eat the dot, don't bite yourself." },
  { slug: "quest",    name: "IR Quest",    category: "game", tint: "primary", icon: "Compass",
    pngIcon: "/icons/IR_Quest_icon.png",
    blurb: "IR-beacon scavenger hunt. Find 9 stations, trade tokens." },
  { slug: "reader",   name: "Reader",      category: "tool", tint: "lilac",   icon: "BookOpen",
    pngIcon: "/icons/reader_icon.png",
    blurb: "Markdown + text viewer. AirDrop a .md, read it on the go." },
];

export const ALL_APPS: AppEntry[] = [
  ...PRELOADED,
  { slug: "racer",    name: "Racer",     category: "game", tint: "primary", icon: "Car",
    pngIcon: "/icons/racer_icon.png",
    blurb: "Top-down arcade racer. UP/DOWN steer, A boosts." },
  { slug: "weather",  name: "Weather",   category: "tool", tint: "teal",    icon: "Cloud",
    pngIcon: "/icons/wallpaper_icon.png",
    blurb: "Current conditions + 3-day forecast." },
  { slug: "commits",  name: "Commits",   category: "tool", tint: "gold",    icon: "GitCommit",
    pngIcon: "/icons/commits_icon.png",
    blurb: "Live GitHub commit feed from your followed repos." },
  { slug: "identity", name: "Identity",  category: "core", tint: "lilac",   icon: "User",
    pngIcon: "/icons/identity_icon.png",
    blurb: "Name, handle, contact card — share over IR." },
  { slug: "gamepad",  name: "Gamepad",   category: "tool", tint: "primary", icon: "Gamepad2",
    pngIcon: "/icons/gamepad_icon.png",
    blurb: "Bluetooth gamepad mode for your laptop." },
  { slug: "storage",  name: "Storage",   category: "tool", tint: "lilac",   icon: "HardDrive",
    pngIcon: "/icons/storage_icon.png",
    blurb: "Flash usage by app + asset bundle." },
  { slug: "wifi",     name: "WiFi",      category: "core", tint: "teal",    icon: "Wifi",
    pngIcon: "/icons/wifi_icon.png",
    blurb: "Saved networks, file transfer, ping + speed test." },
  { slug: "bt",       name: "Bluetooth", category: "core", tint: "lilac",   icon: "Bluetooth",
    pngIcon: "/icons/bluetooth_icon.png",
    blurb: "Peer presence (coming soon). Pairing + bonded list." },
  { slug: "updates",  name: "Updates",   category: "core", tint: "gold",    icon: "RefreshCw",
    pngIcon: "/icons/settings_icon.png",
    blurb: "OTA over WiFi. LTS / BETA / OUTDATED states." },
  { slug: "settings", name: "Settings",  category: "core", tint: "primary", icon: "Settings",
    pngIcon: "/icons/settings_icon.png",
    blurb: "Brightness, sleep timer, gestures, theme." },
];

export const STORE: AppEntry[] = [
  { slug: "Colors",   name: "Color Picker", category: "store", tint: "lilac",   icon: "Palette",
    pngIcon: "/icons/color_icon.png",
    blurb: "HSV picker — UP/DOWN sweeps each channel." },
  { slug: "Oreo Pet", name: "Oreo Pet",     category: "store", tint: "primary", icon: "PawPrint",
    pngIcon: "/icons/elixpo_pet_icon.png",
    blurb: "Tamagotchi panda. Feed, play, sleep, repeat." },
];
