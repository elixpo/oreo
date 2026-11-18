"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Reveal, fadeUp, staggerContainer } from "@/components/MotionWrap";
import { Heart, Users, Handshake } from "lucide-react";
import PressStrip from "@/components/PressStrip";

const FUND_URL = "https://payouts.elixpo.com/f/oreo-badge";
// Same-origin Pages Function first (functions/api/supporters.js); the
// payouts API directly as a fallback, which works once it sends CORS.
const SOURCES = ["/api/supporters", "https://payouts.elixpo.com/api/fundraisers/oreo-badge"];

type Money = { amount: number; currency: string };
type Supporter = {
  name: string | null;
  message: string | null;
  amount: number;
  currency: string;
  paid_at: string;
};
type Fund = {
  title?: string;
  goal: Money;
  raised: number;
  contributors: number;
  ended?: boolean;
  supporters: Supporter[];
};

const TEAM = [
  { name: "Ayushman Bhattacharya", role: "Founder, hardware and OreoOS", href: "https://github.com/Circuit-Overtime" },
  { name: "Anwesha Chakraborty", role: "Core maintainer, RV565 co-author", href: "https://github.com/anwe-ch" },
  { name: "Vivek Yadav", role: "Lead co-developer", href: "https://github.com/ez-vivek" },
];
const THANKS = ["Divyanshu Jha", "Karan Ray", "Bhumika Sudarshani"];

// Amounts come in the smallest unit (paise, cents).
function money(amount: number, currency: string) {
  const v = amount / 100;
  if (currency === "USD") return `$${v.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
  return `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function when(s: string) {
  const d = new Date(s.replace(" ", "T") + "Z");
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export default function SupportersPage() {
  const [fund, setFund] = useState<Fund | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (const src of SOURCES) {
        try {
          const r = await fetch(src, { cache: "no-store" });
          if (!r.ok) continue;
          const d = await r.json();
          if (d && d.goal && Array.isArray(d.supporters)) {
            if (!cancelled) setFund(d);
            return;
          }
        } catch {
          // try the next source
        }
      }
      if (!cancelled) setFailed(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const pct = fund ? Math.min(100, Math.round((fund.raised / fund.goal.amount) * 100)) : 0;

  return (
    <div className="relative">
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[560px] overflow-hidden">
        <div className="absolute left-1/3 top-0 h-[420px] w-[420px] rounded-full bg-primary/[0.10] blur-[140px]" />
        <div className="absolute right-1/4 top-32 h-[300px] w-[300px] rounded-full bg-gold/[0.10] blur-[120px]" />
      </div>

      <div className="container-page pt-16 pb-28">
        {/* ── HERO ─────────────────────────────────────────────────── */}
        <motion.div initial="hidden" animate="visible" variants={staggerContainer} className="max-w-3xl">
          <motion.span variants={fadeUp} className="chip mb-6">
            Community · first boards in fabrication
          </motion.span>
          <motion.h1 variants={fadeUp} className="font-display text-4xl leading-[1.05] tracking-tight sm:text-5xl">
            The people building{" "}
            <span className="bg-gradient-to-r from-primary via-gold to-lilac bg-clip-text text-transparent">
              Oreo with us.
            </span>
          </motion.h1>
          <motion.p variants={fadeUp} className="mt-5 max-w-2xl text-text-dim">
            Oreo has no company or investor behind it. The first five boards were paid for out of
            pocket, and the community is funding the rest. Everyone who chips in is thanked here,
            by name.
          </motion.p>
        </motion.div>

        {/* ── PROGRESS ─────────────────────────────────────────────── */}
        <Reveal>
          <div className="mt-12 rounded-lg border border-primary/30 bg-gradient-to-r from-primary/10 via-card to-gold/10 p-6 sm:p-8">
            {fund ? (
              <>
                <div className="flex flex-wrap items-end justify-between gap-4">
                  <div>
                    <p className="text-xs uppercase tracking-widest text-muted">Raised</p>
                    <p className="mt-1 font-display text-4xl tracking-tight tabular-nums">
                      {money(fund.raised, fund.goal.currency)}
                      <span className="text-lg text-text-dim">
                        {" "}of {money(fund.goal.amount, fund.goal.currency)}
                      </span>
                    </p>
                  </div>
                  <p className="flex items-center gap-2 text-text-dim">
                    <Users className="h-4 w-4" aria-hidden="true" />
                    {fund.contributors} {fund.contributors === 1 ? "supporter" : "supporters"}
                  </p>
                </div>
                <div className="mt-5 h-3 overflow-hidden rounded-pill bg-bg/70" role="progressbar"
                     aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
                     aria-label="Fundraiser progress">
                  <div className="h-full rounded-pill bg-gradient-to-r from-primary to-gold"
                       style={{ width: `${Math.max(pct, fund.raised > 0 ? 2 : 0)}%` }} />
                </div>
                <p className="mt-2 text-sm text-text-dim">{pct}% of the goal</p>
              </>
            ) : (
              <p className="text-text-dim">
                {failed
                  ? "The live total couldn't load. It's on the fundraiser page."
                  : "Loading the live total…"}
              </p>
            )}
            <a href={FUND_URL} target="_blank" rel="noreferrer" className="btn-primary mt-6 inline-flex">
              <Heart className="h-4 w-4" aria-hidden="true" /> Fund the badge. Even ₹10 helps
            </a>
          </div>
        </Reveal>

        {/* ── SUPPORTERS ───────────────────────────────────────────── */}
        <Reveal>
          <h2 className="mt-16 font-display text-2xl tracking-tight">Supporters</h2>
        </Reveal>
        {fund && fund.supporters.length > 0 ? (
          <ul className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {fund.supporters.map((s, i) => (
              <motion.li
                key={`${s.paid_at}-${i}`}
                initial={{ opacity: 0, y: 10 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.03 * Math.min(i, 10), duration: 0.45 }}
                className="card-surface flex flex-col gap-2 p-5"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <p className="font-medium text-text">{s.name || "Anonymous"}</p>
                  <p className="text-sm tabular-nums text-primary">{money(s.amount, s.currency)}</p>
                </div>
                {s.message ? <p className="text-sm leading-relaxed text-text-dim">“{s.message}”</p> : null}
                <p className="mt-auto text-xs text-muted">{when(s.paid_at)}</p>
              </motion.li>
            ))}
          </ul>
        ) : (
          <div className="mt-6 card-surface p-6 text-text-dim">
            {fund
              ? "No supporters yet. Be the first, and your name goes here."
              : failed
                ? <>See every supporter on the <a className="text-primary underline-offset-4 hover:underline" href={FUND_URL} target="_blank" rel="noreferrer">fundraiser page</a>.</>
                : "Loading supporters…"}
          </div>
        )}

        {/* ── TEAM ─────────────────────────────────────────────────── */}
        <Reveal>
          <h2 className="mt-16 font-display text-2xl tracking-tight">Built by</h2>
        </Reveal>
        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          {TEAM.map((m) => (
            <a key={m.name} href={m.href} target="_blank" rel="noreferrer"
               className="card-surface p-5 transition-colors hover:border-primary/40">
              <p className="font-medium text-text">{m.name}</p>
              <p className="mt-1 text-sm text-text-dim">{m.role}</p>
            </a>
          ))}
        </div>
        <p className="mt-4 text-sm text-text-dim">
          With thanks to {THANKS.slice(0, -1).join(", ")} and {THANKS[THANKS.length - 1]}, who were
          there from the start.
        </p>

        {/* ── IN THE PRESS ─────────────────────────────────────────── */}
        <div className="mt-16">
          <PressStrip />
        </div>

        {/* ── SPONSORS ─────────────────────────────────────────────── */}
        <Reveal>
          <div className="mt-16 card-surface flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:p-8">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-card-sub text-primary">
              <Handshake className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h2 className="font-display text-xl tracking-tight">Become a founding sponsor</h2>
              <p className="mt-1 text-text-dim">
                Hardware makers, chip companies and developer-tool teams: help us take Oreo from five
                hand-built boards to a factory batch. Write to{" "}
                <span className="select-all font-mono text-text">hello@elixpo.com</span>.
              </p>
            </div>
          </div>
        </Reveal>
      </div>
    </div>
  );
}
