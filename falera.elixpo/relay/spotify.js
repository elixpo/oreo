// Shared code for the Spotify sign-in relay (Cloudflare Pages Functions in
// functions/api/spotify/). Lives outside functions/ so it is never a route.
//
// The badge cannot run a browser sign-in, so the relay hands it tokens:
//
//   POST /api/spotify/session   badge  -> { pin, secret, url, expires_in, interval }
//   GET  /api/spotify/login     phone  -> 302 to Spotify (Authorization Code + PKCE)
//   GET  /api/spotify/callback  Spotify-> exchanges the code, parks the tokens
//                                         under the PIN, 302 to /spotify/?linked=1
//   POST /api/spotify/poll      badge  -> { status: pending | authorized | expired }
//   POST /api/spotify/refresh   badge  -> Spotify's token answer (stateless)
//
// PKCE means there is no client secret: the code verifier is made here and
// kept in KV between /login and /callback. /refresh only forwards the badge's
// refresh token with the public client id; it exists because
// accounts.spotify.com's certificate chains to a root CA the badge's TLS
// bundle lacks (api.spotify.com and this site chain to roots it has).
//
// Configuration (Pages project > Settings > Variables and Secrets / Bindings):
//   SPOTIFY_CLIENT_ID     the Spotify app's client id (required)
//   SPOTIFY_KV            a KV namespace binding (required), short-lived
//                         records only: pin:<PIN> and state:<random>
//   SPOTIFY_REDIRECT_URI  optional; defaults to <site origin>/api/spotify/callback
//                         and must be listed in the Spotify app's Redirect URIs.
// Without the required two every endpoint answers 503 / error=not_configured
// (/refresh needs only SPOTIFY_CLIENT_ID).

export const SCOPES = [
  "user-read-playback-state",
  "user-modify-playback-state",
  "user-read-currently-playing",
  "user-library-read",
  "user-read-recently-played",
  "user-top-read",
  "playlist-read-private",
  "playlist-read-collaborative",
].join(" ");

export const PIN_TTL_S = 600; // how long a PIN (and its tokens) live
export const POLL_INTERVAL_S = 3;
export const PIN_LEN = 6;
// 32 symbols without 0/O, 1/I: easy to read off a small screen.
export const PIN_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";

export const AUTHORIZE_URL = "https://accounts.spotify.com/authorize";
export const TOKEN_URL = "https://accounts.spotify.com/api/token";

const NO_STORE = { "cache-control": "no-store" };

export function missingConfig(env) {
  const missing = [];
  if (!env || !env.SPOTIFY_CLIENT_ID) missing.push("SPOTIFY_CLIENT_ID");
  if (!env || !env.SPOTIFY_KV || typeof env.SPOTIFY_KV.get !== "function") missing.push("SPOTIFY_KV");
  return missing;
}

export function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...NO_STORE },
  });
}

export function notConfigured(missing) {
  return json(
    {
      status: "error",
      error: "not_configured",
      missing,
      message: "Spotify relay not configured: set " + missing.join(", "),
    },
    503,
  );
}

export function siteOrigin(request) {
  return new URL(request.url).origin;
}

export function redirectUri(request, env) {
  return (env && env.SPOTIFY_REDIRECT_URI) || siteOrigin(request) + "/api/spotify/callback";
}

// 302 back to the /spotify page with a status for it to show.
export function toPage(request, params) {
  const q = new URLSearchParams(params).toString();
  return new Response(null, {
    status: 302,
    headers: { location: siteOrigin(request) + "/spotify/" + (q ? "?" + q : ""), ...NO_STORE },
  });
}

export function randomPin(len = PIN_LEN) {
  const bytes = crypto.getRandomValues(new Uint8Array(len));
  let pin = "";
  for (const b of bytes) pin += PIN_ALPHABET[b & 31]; // 256 % 32 == 0: uniform
  return pin;
}

export function normalizePin(s) {
  const up = String(s || "").toUpperCase();
  let out = "";
  for (const ch of up) if (PIN_ALPHABET.includes(ch)) out += ch;
  return out.length === PIN_LEN ? out : "";
}

export function b64url(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function randomToken(nBytes = 32) {
  return b64url(crypto.getRandomValues(new Uint8Array(nBytes)));
}

export async function sha256(text) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return b64url(new Uint8Array(d));
}

export function sameString(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function readJson(request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}

export async function getRecord(kv, key) {
  const raw = await kv.get(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function putRecord(kv, key, value, ttlS) {
  // KV refuses expirationTtl under 60 s.
  return kv.put(key, JSON.stringify(value), { expirationTtl: Math.max(60, Math.ceil(ttlS)) });
}

export function ttlLeft(record, now = Date.now()) {
  return PIN_TTL_S - Math.floor((now - (record.t || 0)) / 1000);
}
