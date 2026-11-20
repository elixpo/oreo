// Cloudflare Pages Function: POST /api/spotify/refresh  {"refresh_token": ...}
//
// The badge refreshes its access token here instead of at
// accounts.spotify.com, whose certificate chains to a root CA the badge's
// TLS bundle does not include. Forwards the refresh token with the public
// client id (PKCE refresh: no client secret) and passes Spotify's answer
// back, errors included (400 invalid_grant tells the badge to link again).
// Stores nothing. Needs SPOTIFY_CLIENT_ID only. See relay/spotify.js.

import { TOKEN_URL, json, notConfigured, readJson } from "../../../relay/spotify.js";

export async function onRequestPost({ request, env }) {
  if (!env || !env.SPOTIFY_CLIENT_ID) return notConfigured(["SPOTIFY_CLIENT_ID"]);
  const body = await readJson(request);
  const rt = typeof body.refresh_token === "string" ? body.refresh_token : "";
  if (!rt || rt.length > 2048) return json({ error: "invalid_request" }, 400);

  let r;
  try {
    r = await fetch(TOKEN_URL, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ grant_type: "refresh_token", refresh_token: rt, client_id: env.SPOTIFY_CLIENT_ID }),
    });
  } catch {
    return json({ error: "upstream_unreachable" }, 502);
  }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) return json({ error: d.error || "refresh_failed", error_description: d.error_description || "" }, r.status === 400 ? 400 : 502);
  const out = { access_token: d.access_token, expires_in: d.expires_in || 3600, scope: d.scope || "" };
  if (d.refresh_token) out.refresh_token = d.refresh_token;
  return json(out);
}
