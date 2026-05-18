"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowRight, ShieldCheck, Wifi, RefreshCw, Lock,
} from "lucide-react";
import { Reveal } from "@/components/MotionWrap";

/* The /upload route is the public on-ramp to the badge's local file
 * transfer flow. It does NOT itself transfer bytes — modern browsers
 * block HTTPS → HTTP fetches (mixed content), and the badge speaks
 * HTTP only. So the page collects the 6-character code shown on the
 * badge screen, validates the shape client-side, and hands the user
 * off to http://oreo.local/?prefill=<code> in a new tab. The badge's
 * own upload page picks up the prefill and continues the gated
 * handshake from there.
 *
 * Why have this page at all?
 *   1. Discoverability — a typed URL on the badge is hard to read;
 *      a fancy gradient page with the wordmark feels like a product.
 *   2. Pre-validation — we reject obviously-wrong codes (length,
 *      ambiguous chars) before the user is on the local-only page.
 *   3. Network coaching — we tell the user "be on the same WiFi"
 *      before they encounter the inevitable "can't reach" error.
 */

const CODE_LEN     = 6;
const CODE_CHARSET = /^[A-HJ-NP-Z2-9]+$/i;  // excludes 0/O/1/I/l

export default function UploadPage() {
  const [code, setCode]       = useState("");
  const [error, setError]     = useState<string>("");
  const [phase, setPhase]     = useState<"enter" | "handoff">("enter");
  const inputRef              = useRef<HTMLInputElement>(null);

  // Auto-focus the code input on first render — the user came here
  // to do exactly one thing.
  useEffect(() => { inputRef.current?.focus(); }, []);

  // Normalise as the user types: uppercase + strip non-charset chars.
  function onCodeChange(v: string) {
    const clean = v.toUpperCase().replace(/[^A-HJ-NP-Z2-9]/gi, "");
    setCode(clean.slice(0, CODE_LEN));
    if (error) setError("");
  }

  function handoff() {
    if (code.length !== CODE_LEN) {
      setError(`Code must be ${CODE_LEN} characters.`);
      inputRef.current?.focus();
      return;
    }
    if (!CODE_CHARSET.test(code)) {
      setError("Code uses letters A–Z (minus O/I) and digits 2–9.");
      return;
    }
    setPhase("handoff");
    // Small delay so the success state is visible before the redirect.
    setTimeout(() => {
      const url = `http://oreo.local/?prefill=${encodeURIComponent(code)}`;
      window.open(url, "_blank", "noopener,noreferrer");
    }, 700);
  }

  return (
    <div className="container-page pt-16 pb-28">
      <Reveal>
        <div className="mx-auto max-w-2xl">
          <span className="chip mb-6">
            <Lock className="h-3 w-3" /> peer-to-peer · local network only
          </span>
          <h1 className="font-display text-4xl leading-[1.05] tracking-tight
                         sm:text-5xl">
            Send to your badge.
            <br /><span className="text-primary">No accounts. No cloud.</span>
          </h1>
          <p className="mt-5 max-w-xl text-text-dim">
            Open <span className="text-text">Settings → WiFi → Send files</span> on
            the badge. Enter the 6-character code shown there to start a
            gated, same-network transfer. Files never leave your LAN.
          </p>
        </div>
      </Reveal>

      <div className="mx-auto mt-12 max-w-2xl">
        <AnimatePresence mode="wait">
          {phase === "enter" ? (
            <motion.form
              key="enter"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0  }}
              exit={{    opacity: 0, y:-10 }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              onSubmit={(e) => { e.preventDefault(); handoff(); }}
              className="card-surface p-8 sm:p-10"
            >
              <label className="block text-xs uppercase tracking-widest text-muted">
                Badge code
              </label>

              <div className="mt-3 flex items-center gap-3">
                <input
                  ref={inputRef}
                  value={code}
                  onChange={(e) => onCodeChange(e.target.value)}
                  placeholder="ABCDE2"
                  maxLength={CODE_LEN}
                  spellCheck={false}
                  autoComplete="off"
                  inputMode="text"
                  className="flex-1 rounded-md border border-border bg-bg
                             px-4 py-4 font-mono text-3xl uppercase tracking-[0.45em]
                             text-text outline-none transition-colors
                             placeholder:text-muted-deep
                             focus:border-primary/70"
                />
                <button
                  type="submit"
                  disabled={code.length !== CODE_LEN}
                  className="btn-primary h-14 px-5 disabled:cursor-not-allowed
                             disabled:opacity-50"
                >
                  Open <ArrowRight className="h-4 w-4" />
                </button>
              </div>

              {error ? (
                <motion.p
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y:  0 }}
                  className="mt-3 text-sm text-primary"
                >
                  {error}
                </motion.p>
              ) : (
                <p className="mt-3 text-xs text-muted-deep">
                  Six characters. Skips ambiguous shapes (no 0/O/1/I/L).
                </p>
              )}

              <div className="mt-8 grid gap-3 sm:grid-cols-3">
                <Tile icon={<Wifi className="h-4 w-4" />}        title="Same WiFi"     body="Phone and badge on one network."/>
                <Tile icon={<ShieldCheck className="h-4 w-4" />} title="Tap to allow"  body="Each session waits for badge approval."/>
                <Tile icon={<RefreshCw className="h-4 w-4" />}   title="Auto cleanup"  body="Codes expire in 60 s."/>
              </div>
            </motion.form>
          ) : (
            <motion.div
              key="handoff"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0  }}
              exit={{    opacity: 0, y:-10 }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              className="card-surface flex flex-col items-center gap-4 p-10
                         text-center"
            >
              <div className="grid h-14 w-14 place-items-center rounded-pill
                              bg-primary/15 text-primary">
                <ArrowRight className="h-6 w-6 animate-pulse-soft" />
              </div>
              <h2 className="font-display text-2xl">
                Opening transfer with{" "}
                <span className="text-primary">{code}</span>…
              </h2>
              <p className="max-w-md text-sm text-text-dim">
                A new tab is opening to <code className="text-text">http://oreo.local</code>.
                Make sure your device is on the same WiFi as the badge,
                approve the session on the badge, and pick a file.
              </p>
              <button
                onClick={() => setPhase("enter")}
                className="btn-ghost mt-4"
              >
                Use a different code
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <Reveal delay={0.15}>
          <div className="mt-12 rounded-md border border-border/60 bg-bg-raised/40 p-6
                          text-sm leading-relaxed text-text-dim">
            <p className="text-text">Why two pages?</p>
            <p className="mt-2">
              Browsers block HTTPS pages from talking to plain-HTTP
              endpoints. Cloudflare serves this page over HTTPS; the
              badge speaks HTTP on your LAN. The handoff puts you on
              the badge's own page so the upload itself stays on the
              local network — no cloud, no proxy, no metadata leakage.
            </p>
          </div>
        </Reveal>
      </div>
    </div>
  );
}

function Tile({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="rounded-md border border-border bg-bg-raised/50 p-4">
      <div className="mb-2 text-primary">{icon}</div>
      <p className="text-sm font-semibold text-text">{title}</p>
      <p className="mt-1 text-xs text-text-dim">{body}</p>
    </div>
  );
}
