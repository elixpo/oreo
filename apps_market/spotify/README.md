# Spotify

A remote for Spotify Connect: the badge shows what your Spotify account
is playing on a phone, computer or speaker, and controls it. The badge
itself plays no audio. Originally written by sea-deep (#47).

## Use

The first time, the app shows a QR code and a 6-character code. Scan it,
or open falera.elixpo.com/spotify and type the code, then sign in to
Spotify. The badge notices within a minute and switches to the player.

| Screen | Buttons |
|---|---|
| Player | A play/pause, LEFT/RIGHT previous/next, UP/DOWN volume, B library, C unlink (asks first) |
| Library | UP/DOWN move, A open or play, RIGHT on a playlist plays all of it, B or LEFT back |
| Link | C new code |

C is the app's own key (`CAPTURES_C`); double-tap C for the notification
panel. Play, pause, skip and volume need Spotify Premium (Spotify's rule
for its playback API); without it the player still shows what is playing.

## How it works

- `src/app.py` is the UI. Every request runs on one background worker
  (`oreoOS.cache.Refresh`), one at a time; `update()` only starts jobs and
  collects results. Playback is polled every 4 s while playing, 12 s
  otherwise, and only while Wi-Fi is up.
- `src/net.py` sends GET/PUT/POST over the OS's verified TLS
  (`oreoOS._http.tls_wrap`) with a deadline, and returns the status code.
- `src/client.py` calls the Spotify Web API and keeps only what the screen
  shows from each response.
- `src/auth.py` holds the saved tokens, refresh timing and the pairing
  state machine. `src/qr.py` draws the sign-in QR code.

Linking goes through the relay on the Falera website
(`falera.elixpo/functions/api/spotify/`, described in
`falera.elixpo/README.md`): the badge gets a PIN, the owner signs in with
Spotify's Authorization Code flow with PKCE (no client secret anywhere),
and the badge collects its tokens once with a secret only it knows. The
badge then refreshes its access token through the relay's stateless
`/api/spotify/refresh`: accounts.spotify.com uses a root CA that the
badge's TLS bundle does not carry (docs/TLS.md), while api.spotify.com and
falera.elixpo.com use roots it does.

If the relay has no Spotify client id or storage configured, the app says
"Sign-in relay not set up".

## Settings and storage

Everything lives in `/state/spotify.json` (`oreoOS.state`): the access and
refresh tokens, the client id and the token expiry. Unlinking (C, then A)
deletes the tokens. To use another relay (your own deployment of the
site), add `"relay": "https://your.site"` to that file; the default is
`https://falera.elixpo.com`.

## Not ported from #47

- Album art. Spotify serves covers as JPEG and the badge has no JPEG
  decoder, so the player draws a placeholder. A relay endpoint that turns
  the 64x64 cover into RGB565 would bring it back.
- The client-secret relay and the in-memory session store (replaced by
  PKCE and KV); the simulator, `badge_data/` and config changes.
- Needs FaleraOS with `oreoOS.state` and verified TLS; on an older OS the
  app asks for an update.
