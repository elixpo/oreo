// Cloudflare Pages Function: POST /api/spotify/poll  {"pin": ..., "secret": ...}
//
// The badge asks whether its PIN has been signed in. With the right secret
// it gets the tokens exactly once; the record is then deleted.
// See relay/spotify.js.

import {
  getRecord, json, missingConfig, normalizePin, notConfigured, readJson, sameString, sha256,
} from "../../../relay/spotify.js";

export async function onRequestPost({ request, env }) {
  const missing = missingConfig(env);
  if (missing.length) return notConfigured(missing);
  const kv = env.SPOTIFY_KV;
  const body = await readJson(request);
  const pin = normalizePin(body.pin);
  const secret = typeof body.secret === "string" ? body.secret : "";
  if (!pin || !secret) return json({ status: "error", error: "bad_request" }, 400);

  const key = "pin:" + pin;
  const rec = await getRecord(kv, key);
  if (!rec) return json({ status: "expired" });
  if (!sameString(await sha256(secret), rec.h)) return json({ status: "error", error: "forbidden" }, 403);
  if (rec.s !== "authorized" || !rec.tok) return json({ status: "pending" });

  await kv.delete(key);
  return json({ status: "authorized", client_id: env.SPOTIFY_CLIENT_ID, ...rec.tok });
}
