"use client";

// Sign-in page for the badge's Spotify app. The badge shows a 6-character
// code (and a QR code for this page with ?pin=). Submitting goes to the
// Pages Function /api/spotify/login, which sends the browser to Spotify;
// Spotify returns to /api/spotify/callback, which comes back here with
// ?linked=1 or ?error=<reason>. See relay/spotify.js.

import { FormEvent, useEffect, useState } from "react";
import { CheckCircle2, AlertTriangle, Music } from "lucide-react";

const PIN_CHARS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";
const PIN_LEN = 6;

const ERRORS: Record<string, string> = {
  pin: "That code isn't waiting for a sign-in. Check it against the badge; if the badge only just showed it, wait a few seconds and try again. Codes last 10 minutes.",
  pin_expired: "The code expired while you were signing in. Press C on the badge for a new one.",
  denied: "Spotify sign-in was cancelled.",
  state: "The sign-in link was used already or is too old. Start again from the code on the badge.",
  token: "Spotify didn't accept the sign-in. Try again.",
  spotify: "Spotify reported an error. Try again.",
  not_configured: "Spotify sign-in isn't set up on this site yet.",
};

function cleanPin(s: string) {
  let out = "";
  for (const ch of s.toUpperCase()) if (PIN_CHARS.includes(ch)) out += ch;
  return out.slice(0, PIN_LEN);
}

export default function SpotifyLinkPage() {
  const [pin, setPin] = useState("");
  const [linked, setLinked] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    setPin(cleanPin(q.get("pin") || ""));
    setLinked(q.get("linked") === "1");
    const e = q.get("error");
    if (e) setError(ERRORS[e] || ERRORS.spotify);
  }, []);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (pin.length !== PIN_LEN) return;
    window.location.href = "/api/spotify/login?pin=" + encodeURIComponent(pin);
  }

  return (
    <div className="container-page pt-16 pb-28">
      <div className="mx-auto max-w-lg">
        <span className="chip mb-6 inline-flex items-center gap-2">
          <Music className="h-4 w-4" aria-hidden="true" /> Spotify app
        </span>
        <h1 className="font-display text-4xl leading-[1.05] tracking-tight">Link Spotify to your badge</h1>

        {linked ? (
          <div className="card-surface mt-8 flex gap-3 p-6">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
            <p className="text-text-dim">
              Signed in. The badge picks this up by itself, usually within a minute. You can close this page.
            </p>
          </div>
        ) : (
          <>
            <p className="mt-5 text-text-dim">
              Open the Spotify app on your Falera Badge and type the code it shows. You&apos;ll sign in on
              Spotify&apos;s own page; this site never sees your password. Controlling playback needs Spotify Premium.
            </p>
            {error ? (
              <div className="mt-6 flex gap-3 rounded-lg border border-gold/40 bg-gold/10 p-4">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-gold" aria-hidden="true" />
                <p className="text-sm text-text-dim">{error}</p>
              </div>
            ) : null}
            <form onSubmit={submit} className="card-surface mt-8 p-6">
              <label htmlFor="pin" className="text-xs uppercase tracking-widest text-muted">
                Code on the badge
              </label>
              <input
                id="pin"
                value={pin}
                onChange={(e) => setPin(cleanPin(e.target.value))}
                inputMode="text"
                autoComplete="off"
                autoCapitalize="characters"
                spellCheck={false}
                placeholder="ABC234"
                className="mt-2 w-full rounded-md border border-text/10 bg-bg px-4 py-3 font-mono text-2xl tracking-[0.4em] text-text outline-none focus:border-primary"
              />
              <button type="submit" disabled={pin.length !== PIN_LEN} className="btn-primary mt-5 w-full justify-center disabled:opacity-50">
                Continue to Spotify
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
