// Cloudflare Pages Function: GET /api/spotify/callback?code=...&state=...
//
// Spotify sends the browser back here. Exchanges the code (with the PKCE
// verifier saved by /login, no client secret), parks the tokens on the PIN's
// record for the badge's next /poll and shows the /spotify page.
// This URL must be listed under Redirect URIs in the Spotify app.

import {
  TOKEN_URL, getRecord, missingConfig, putRecord, redirectUri, toPage, ttlLeft,
} from "../../../relay/spotify.js";

export async function onRequestGet({ request, env }) {
  if (missingConfig(env).length) return toPage(request, { error: "not_configured" });
  const kv = env.SPOTIFY_KV;
  const q = new URL(request.url).searchParams;
  if (q.get("error")) return toPage(request, { error: q.get("error") === "access_denied" ? "denied" : "spotify" });

  const code = q.get("code");
  const state = q.get("state");
  if (!code || !state) return toPage(request, { error: "state" });
  const st = await getRecord(kv, "state:" + state);
  if (!st || !st.pin || !st.v) return toPage(request, { error: "state" });
  await kv.delete("state:" + state);

  let tok;
  try {
    const r = await fetch(TOKEN_URL, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        code,
        redirect_uri: redirectUri(request, env),
        client_id: env.SPOTIFY_CLIENT_ID,
        code_verifier: st.v,
      }),
    });
    tok = await r.json().catch(() => ({}));
    if (!r.ok || !tok.access_token || !tok.refresh_token) return toPage(request, { error: "token" });
  } catch {
    return toPage(request, { error: "token" });
  }

  const key = "pin:" + st.pin;
  const rec = await getRecord(kv, key);
  if (!rec || rec.s !== "pending" || ttlLeft(rec) <= 0) return toPage(request, { error: "pin_expired" });
  await putRecord(
    kv,
    key,
    {
      ...rec,
      s: "authorized",
      tok: {
        access_token: tok.access_token,
        refresh_token: tok.refresh_token,
        expires_in: tok.expires_in || 3600,
        scope: tok.scope || "",
      },
    },
    ttlLeft(rec),
  );
  return toPage(request, { linked: "1" });
}
