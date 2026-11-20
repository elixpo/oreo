// Cloudflare Pages Function: GET /api/spotify/login?pin=XXXXXX
//
// The /spotify page sends the browser here with the PIN from the badge.
// Starts Spotify's Authorization Code flow with PKCE: the code verifier is
// kept in KV under a random state value until /callback. See relay/spotify.js.

import {
  AUTHORIZE_URL, PIN_TTL_S, SCOPES, getRecord, missingConfig, normalizePin,
  putRecord, randomToken, redirectUri, sha256, toPage, ttlLeft,
} from "../../../relay/spotify.js";

export async function onRequestGet({ request, env }) {
  if (missingConfig(env).length) return toPage(request, { error: "not_configured" });
  const kv = env.SPOTIFY_KV;
  const pin = normalizePin(new URL(request.url).searchParams.get("pin"));
  if (!pin) return toPage(request, { error: "pin" });

  const rec = await getRecord(kv, "pin:" + pin);
  if (!rec || rec.s !== "pending" || ttlLeft(rec) <= 0) return toPage(request, { error: "pin", pin });

  const verifier = randomToken(48); // 64 characters, within PKCE's 43..128
  const state = randomToken(24);
  await putRecord(kv, "state:" + state, { pin, v: verifier }, Math.min(PIN_TTL_S, ttlLeft(rec)));

  const q = new URLSearchParams({
    response_type: "code",
    client_id: env.SPOTIFY_CLIENT_ID,
    scope: SCOPES,
    redirect_uri: redirectUri(request, env),
    state,
    code_challenge_method: "S256",
    code_challenge: await sha256(verifier),
  });
  return new Response(null, {
    status: 302,
    headers: { location: AUTHORIZE_URL + "?" + q.toString(), "cache-control": "no-store" },
  });
}
