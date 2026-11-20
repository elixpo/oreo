# falera.elixpo

Marketing site, app catalogue, and gated file-transfer launcher for the
**Falera Badge** — `falera.elixpo.com`.

Built with Next.js 14 (App Router, static export) + Tailwind + Framer
Motion. The single source of truth for brand tokens is
[`theme.js`](./theme.js) at the project root; Tailwind re-exports those
tokens as utility classes (`bg-bg`, `text-primary`, etc.).

## Develop

```bash
npm install
npm run dev          # http://localhost:3000
```

## Deploy to Cloudflare Pages

The site is a fully static export — no Workers runtime needed.

```bash
npm run build                                                 # writes ./out
npx wrangler pages deploy out --project-name=falera             # CF push
```

Or connect this folder to a Cloudflare Pages project in the dashboard:

| Setting              | Value                              |
|----------------------|------------------------------------|
| Build command        | `npm install && npm run build`     |
| Output directory     | `out`                              |
| Root directory       | `falera.elixpo`                      |
| Node version         | `20`                               |

## Structure

```
src/
  app/
    layout.tsx        global chrome (Header + Footer)
    page.tsx          home — hero, feature trio, apps showcase
    apps/             preloaded + store catalogue
    badge/            hardware specs
    upload/           gated file-transfer handoff to the badge
    get-started/      flashing + deploy guide
  components/
    Header.tsx        sticky nav + GitHub badge
    Footer.tsx        link columns + brand block
    AppCard.tsx       reusable app tile (Framer-Motion reveal)
    MotionWrap.tsx    shared motion presets
  data/
    apps.ts           preloaded + store catalogue (mirrors manifest.json)
theme.js              brand tokens (colors, radii, motion presets)
tailwind.config.ts    Tailwind config that consumes theme.js
wrangler.toml         Cloudflare Pages deploy config
```

## Brand tokens

The palette + spacing live in [`theme.js`](./theme.js). Any time you
add a new shade or motion preset, add it there first so it shows up in
both Tailwind classes and runtime-imported values automatically.

## /upload

The upload route is *not* itself a transfer endpoint. Browsers block
HTTPS pages from talking to plain-HTTP endpoints on the LAN, and the
badge speaks HTTP only. So `/upload` collects the 6-character code
displayed on the badge screen and hands the user off to
`http://oreo.local/?prefill=<code>` in a new tab — the badge's own
upload page picks up the prefill and continues the gated handshake
from there. End-to-end bytes never leave the local network.

## /spotify (badge sign-in relay)

The badge's Spotify app (`apps_market/spotify`) links to a Spotify account
through this site. `/spotify` is a static page where the owner types the
code the badge shows; four Cloudflare Pages Functions under
`functions/api/spotify/` do the rest (shared code in `relay/spotify.js`):

| Endpoint | Caller | Does |
|---|---|---|
| `POST /api/spotify/session` | badge | new 6-character PIN + a poll secret only the badge sees |
| `GET /api/spotify/login?pin=` | browser | redirects to Spotify (Authorization Code with PKCE) |
| `GET /api/spotify/callback` | Spotify | exchanges the code, parks the tokens under the PIN |
| `POST /api/spotify/poll` | badge | `pending`, then the tokens exactly once, then `expired` |
| `POST /api/spotify/refresh` | badge | forwards a refresh token to Spotify with the client id; stores nothing |

PKCE needs no client secret. `/refresh` exists because
`accounts.spotify.com` chains to a root CA the badge's TLS bundle lacks
(`docs/TLS.md`); it needs only `SPOTIFY_CLIENT_ID`.

Setup (nothing works until both required items exist; the endpoints answer
503 `not_configured` and the badge says so):

1. Create an app at developer.spotify.com/dashboard, tick **Web API**, and
   add the Redirect URI `https://falera.elixpo.com/api/spotify/callback`
   (exactly; also `http://127.0.0.1:8788/api/spotify/callback` for
   `wrangler pages dev`). In development mode Spotify only lets accounts
   listed under the app's **User Management** sign in.
2. Pages project settings: variable `SPOTIFY_CLIENT_ID` = the app's client
   id, and a KV namespace bound as `SPOTIFY_KV` (see `wrangler.toml`).
   `SPOTIFY_REDIRECT_URI` overrides the callback URL if needed.

KV is eventually consistent, so the badge can take up to about a minute to
notice a sign-in. Each link costs about five KV writes.

Tests: `npm run test:spotify`.
