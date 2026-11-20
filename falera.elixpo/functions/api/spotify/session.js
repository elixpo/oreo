// Cloudflare Pages Function: POST /api/spotify/session
//
// The badge asks for a PIN to show. The answer also carries a poll secret
// that only the badge sees; /poll hands the tokens over only with it. The
// record lives in KV as pin:<PIN> for PIN_TTL_S. See relay/spotify.js.

import {
  PIN_TTL_S, POLL_INTERVAL_S, json, missingConfig, notConfigured, putRecord,
  randomPin, randomToken, sha256, siteOrigin,
} from "../../../relay/spotify.js";

export async function onRequestPost({ request, env }) {
  const missing = missingConfig(env);
  if (missing.length) return notConfigured(missing);
  const kv = env.SPOTIFY_KV;

  let pin = "";
  for (let i = 0; i < 5 && !pin; i++) {
    const p = randomPin();
    if (!(await kv.get("pin:" + p))) pin = p;
  }
  if (!pin) return json({ status: "error", error: "busy", message: "Try again" }, 503);

  const secret = randomToken(24);
  await putRecord(kv, "pin:" + pin, { s: "pending", h: await sha256(secret), t: Date.now() }, PIN_TTL_S);
  return json({
    status: "ok",
    pin,
    secret,
    url: siteOrigin(request) + "/spotify/?pin=" + pin,
    expires_in: PIN_TTL_S,
    interval: POLL_INTERVAL_S,
  });
}
