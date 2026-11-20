// Tests for the Spotify sign-in relay (functions/api/spotify/*, relay/spotify.js)
// with a fake KV namespace and a fake Spotify token endpoint.
//
//   node --test scripts/spotify-relay.test.mjs      (npm run test:spotify)

import test from "node:test";
import assert from "node:assert/strict";

import { onRequestPost as session } from "../functions/api/spotify/session.js";
import { onRequestGet as login } from "../functions/api/spotify/login.js";
import { onRequestGet as callback } from "../functions/api/spotify/callback.js";
import { onRequestPost as poll } from "../functions/api/spotify/poll.js";
import { onRequestPost as refresh } from "../functions/api/spotify/refresh.js";
import { normalizePin, randomPin, sha256, PIN_ALPHABET } from "../relay/spotify.js";

const SITE = "https://falera.example";

class FakeKV {
  constructor() {
    this.m = new Map();
    this.ttl = new Map();
  }
  async get(k) {
    return this.m.has(k) ? this.m.get(k) : null;
  }
  async put(k, v, opts = {}) {
    if (opts.expirationTtl !== undefined && opts.expirationTtl < 60) throw new Error("ttl < 60");
    this.m.set(k, v);
    this.ttl.set(k, opts.expirationTtl);
  }
  async delete(k) {
    this.m.delete(k);
  }
}

function envWith(kv = new FakeKV()) {
  return { SPOTIFY_CLIENT_ID: "client123", SPOTIFY_KV: kv };
}

const post = (path, body) =>
  new Request(SITE + path, { method: "POST", body: JSON.stringify(body), headers: { "content-type": "application/json" } });
const get = (path) => new Request(SITE + path);

async function newSession(env) {
  const r = await session({ request: post("/api/spotify/session", {}), env });
  assert.equal(r.status, 200);
  return r.json();
}

function withFetch(fake, fn) {
  const orig = globalThis.fetch;
  globalThis.fetch = fake;
  return fn().finally(() => {
    globalThis.fetch = orig;
  });
}

test("pins use the unambiguous alphabet and normalise", () => {
  for (let i = 0; i < 50; i++) {
    const p = randomPin();
    assert.equal(p.length, 6);
    for (const ch of p) assert.ok(PIN_ALPHABET.includes(ch));
  }
  assert.equal(normalizePin(" abc-234 "), "ABC234");
  assert.equal(normalizePin("ABC23"), "");
  assert.equal(normalizePin("ABC2340"), "ABC234"); // 0 is not in the alphabet
});

test("every endpoint fails clearly without configuration", async () => {
  for (const env of [{}, { SPOTIFY_CLIENT_ID: "x" }, { SPOTIFY_KV: new FakeKV() }]) {
    const r = await session({ request: post("/api/spotify/session", {}), env });
    assert.equal(r.status, 503);
    const d = await r.json();
    assert.equal(d.error, "not_configured");
    assert.ok(d.missing.length >= 1);
    const p = await poll({ request: post("/api/spotify/poll", { pin: "ABC234", secret: "s" }), env });
    assert.equal(p.status, 503);
    const l = await login({ request: get("/api/spotify/login?pin=ABC234"), env });
    assert.equal(l.status, 302);
    assert.match(l.headers.get("location"), /\/spotify\/\?error=not_configured$/);
    const c = await callback({ request: get("/api/spotify/callback?code=a&state=b"), env });
    assert.match(c.headers.get("location"), /error=not_configured/);
  }
});

test("session stores only a hash of the poll secret", async () => {
  const kv = new FakeKV();
  const env = envWith(kv);
  const s = await newSession(env);
  assert.equal(s.status, "ok");
  assert.equal(s.url, `${SITE}/spotify/?pin=${s.pin}`);
  assert.equal(s.expires_in, 600);
  const rec = JSON.parse(kv.m.get("pin:" + s.pin));
  assert.equal(rec.s, "pending");
  assert.equal(rec.h, await sha256(s.secret));
  assert.ok(!kv.m.get("pin:" + s.pin).includes(s.secret));
  assert.equal(kv.ttl.get("pin:" + s.pin), 600);
});

test("full link: session, login (PKCE), callback, poll once", async () => {
  const kv = new FakeKV();
  const env = envWith(kv);
  const s = await newSession(env);

  // Pending until signed in.
  let r = await poll({ request: post("/api/spotify/poll", { pin: s.pin, secret: s.secret }), env });
  assert.deepEqual(await r.json(), { status: "pending" });

  // Login redirects to Spotify with an S256 challenge and no secret.
  r = await login({ request: get("/api/spotify/login?pin=" + s.pin.toLowerCase()), env });
  assert.equal(r.status, 302);
  const auth = new URL(r.headers.get("location"));
  assert.equal(auth.origin + auth.pathname, "https://accounts.spotify.com/authorize");
  assert.equal(auth.searchParams.get("client_id"), "client123");
  assert.equal(auth.searchParams.get("code_challenge_method"), "S256");
  assert.equal(auth.searchParams.get("redirect_uri"), `${SITE}/api/spotify/callback`);
  assert.match(auth.searchParams.get("scope"), /user-modify-playback-state/);
  const state = auth.searchParams.get("state");
  const saved = JSON.parse(kv.m.get("state:" + state));
  assert.equal(saved.pin, s.pin);
  assert.equal(auth.searchParams.get("code_challenge"), await sha256(saved.v));

  // Callback exchanges the code with the verifier.
  let sent;
  await withFetch(
    async (url, init) => {
      sent = { url, body: new URLSearchParams(init.body.toString()) };
      return new Response(JSON.stringify({ access_token: "AT", refresh_token: "RT", expires_in: 3600, scope: "x" }), {
        status: 200,
      });
    },
    async () => {
      r = await callback({ request: get(`/api/spotify/callback?code=CODE&state=${state}`), env });
    },
  );
  assert.equal(r.headers.get("location"), `${SITE}/spotify/?linked=1`);
  assert.equal(sent.url, "https://accounts.spotify.com/api/token");
  assert.equal(sent.body.get("grant_type"), "authorization_code");
  assert.equal(sent.body.get("code_verifier"), saved.v);
  assert.equal(sent.body.get("client_id"), "client123");
  assert.equal(sent.body.get("client_secret"), null);
  assert.equal(kv.m.has("state:" + state), false, "state is single-use");

  // A wrong secret gets nothing.
  r = await poll({ request: post("/api/spotify/poll", { pin: s.pin, secret: "nope" }), env });
  assert.equal(r.status, 403);

  // The badge gets the tokens once.
  r = await poll({ request: post("/api/spotify/poll", { pin: s.pin, secret: s.secret }), env });
  const d = await r.json();
  assert.equal(d.status, "authorized");
  assert.equal(d.access_token, "AT");
  assert.equal(d.refresh_token, "RT");
  assert.equal(d.client_id, "client123");
  r = await poll({ request: post("/api/spotify/poll", { pin: s.pin, secret: s.secret }), env });
  assert.deepEqual(await r.json(), { status: "expired" });
});

test("login refuses unknown pins; callback refuses unknown state and Spotify errors", async () => {
  const env = envWith();
  let r = await login({ request: get("/api/spotify/login?pin=ZZZZZZ"), env });
  assert.match(r.headers.get("location"), /error=pin/);
  r = await login({ request: get("/api/spotify/login?pin=12"), env });
  assert.match(r.headers.get("location"), /error=pin$/);
  r = await callback({ request: get("/api/spotify/callback?code=a&state=missing"), env });
  assert.match(r.headers.get("location"), /error=state/);
  r = await callback({ request: get("/api/spotify/callback?error=access_denied&state=x"), env });
  assert.match(r.headers.get("location"), /error=denied/);
});

test("a failed token exchange leaves the pin pending", async () => {
  const kv = new FakeKV();
  const env = envWith(kv);
  const s = await newSession(env);
  const r1 = await login({ request: get("/api/spotify/login?pin=" + s.pin), env });
  const state = new URL(r1.headers.get("location")).searchParams.get("state");
  let r;
  await withFetch(
    async () => new Response(JSON.stringify({ error: "invalid_grant" }), { status: 400 }),
    async () => {
      r = await callback({ request: get(`/api/spotify/callback?code=bad&state=${state}`), env });
    },
  );
  assert.match(r.headers.get("location"), /error=token/);
  r = await poll({ request: post("/api/spotify/poll", { pin: s.pin, secret: s.secret }), env });
  assert.deepEqual(await r.json(), { status: "pending" });
});

test("refresh forwards with the client id only and passes errors through", async () => {
  const env = { SPOTIFY_CLIENT_ID: "client123" }; // no KV needed
  let sent;
  let r;
  await withFetch(
    async (url, init) => {
      sent = { url, body: new URLSearchParams(init.body.toString()) };
      return new Response(JSON.stringify({ access_token: "AT2", expires_in: 3600, scope: "s" }), { status: 200 });
    },
    async () => {
      r = await refresh({ request: post("/api/spotify/refresh", { refresh_token: "RT" }), env });
    },
  );
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { access_token: "AT2", expires_in: 3600, scope: "s" });
  assert.equal(sent.url, "https://accounts.spotify.com/api/token");
  assert.equal(sent.body.get("grant_type"), "refresh_token");
  assert.equal(sent.body.get("refresh_token"), "RT");
  assert.equal(sent.body.get("client_id"), "client123");
  assert.equal(sent.body.get("client_secret"), null);

  await withFetch(
    async () => new Response(JSON.stringify({ error: "invalid_grant", error_description: "revoked" }), { status: 400 }),
    async () => {
      r = await refresh({ request: post("/api/spotify/refresh", { refresh_token: "RT" }), env });
    },
  );
  assert.equal(r.status, 400);
  assert.equal((await r.json()).error, "invalid_grant");

  r = await refresh({ request: post("/api/spotify/refresh", {}), env });
  assert.equal(r.status, 400);
  r = await refresh({ request: post("/api/spotify/refresh", { refresh_token: "RT" }), env: {} });
  assert.equal(r.status, 503);
  assert.equal((await r.json()).error, "not_configured");
});
