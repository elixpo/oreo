"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Github, Cpu, Wifi, Bluetooth } from "lucide-react";
import { Reveal, fadeUp, staggerContainer } from "@/components/MotionWrap";
import AppCard from "@/components/AppCard";
import { PRELOADED } from "@/data/apps";

export default function Home() {
  return (
    <>
      {/* ── HERO ─────────────────────────────────────────────────────── */}
      <section className="container-page pt-20 pb-28">
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="max-w-3xl"
        >
          <motion.span
            variants={fadeUp}
            className="chip mb-6 bg-card-sub/70"
          >
            <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-primary" />
            v1.4 · MicroPython · open source
          </motion.span>

          <motion.h1
            variants={fadeUp}
            className="font-display text-5xl leading-[1.05] tracking-tight
                       sm:text-7xl"
          >
            A python operating system,
            <br />
            <span className="text-primary">in a pocket-sized badge.</span>
          </motion.h1>

          <motion.p
            variants={fadeUp}
            className="mt-6 max-w-2xl text-lg leading-relaxed text-text-dim"
          >
            OreoOS runs 20+ apps on a breadboard ESP32-S3 — a launcher,
            an on-device app store, OTA updates over WiFi, AirDrop-style
            file transfer, IR-quest peer-pairing, and a Tamagotchi panda
            that judges you for skipping meals.
          </motion.p>

          <motion.div
            variants={fadeUp}
            className="mt-10 flex flex-wrap items-center gap-3"
          >
            <Link href="/get-started/" className="btn-primary">
              Get started <ArrowRight className="h-4 w-4" />
            </Link>
            <Link href="/upload/" className="btn-ghost">
              Try file transfer
            </Link>
            <a
              href="https://github.com/elixpo/oreo"
              target="_blank" rel="noreferrer"
              className="btn-ghost"
            >
              <Github className="h-4 w-4" /> Source
            </a>
          </motion.div>
        </motion.div>

        {/* Floating tile preview – decorative; the real "screenshot"
            will land once we have a clean screen capture. */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
          className="pointer-events-none absolute right-8 top-32 hidden lg:block"
        >
          <div className="relative h-72 w-44 animate-float-y rounded-[28px]
                          border-[10px] border-bg-raised bg-bg
                          shadow-[0_40px_80px_-20px_rgba(255,93,104,0.28)]">
            <div className="absolute inset-0 grid grid-cols-3 grid-rows-4 gap-2 p-3">
              {[..."BGFSQRWI"].map((g, i) => (
                <div
                  key={i}
                  className="grid place-items-center rounded-md bg-card-sub
                             font-display text-primary"
                >
                  {g}
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </section>

      {/* ── FEATURE TRIO ─────────────────────────────────────────────── */}
      <section className="container-page py-20">
        <Reveal>
          <h2 className="font-display text-3xl tracking-tight">
            Three things make the badge feel alive
          </h2>
        </Reveal>
        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {[
            {
              icon: <Cpu className="h-5 w-5" />,
              title: "Python all the way down",
              body:
                "MicroPython on ESP32-S3. Apps are a manifest.json + main.py — write one in ~30 lines and it shows up in the drawer.",
            },
            {
              icon: <Wifi className="h-5 w-5" />,
              title: "AirDrop, the open-hardware way",
              body:
                "WiFi-based file transfer with on-badge approval. 6-digit code, beacon handshake, RGB565 conversion in the browser.",
            },
            {
              icon: <Bluetooth className="h-5 w-5" />,
              title: "Peer presence (soon)",
              body:
                "BT will return for proximity-based features — IR-quest assists, sync gestures, badge-to-badge nudges.",
            },
          ].map((f, i) => (
            <Reveal key={f.title} delay={0.05 * i}>
              <div className="card-surface p-6">
                <div className="mb-4 inline-flex h-9 w-9 items-center justify-center
                                rounded-md bg-card-sub text-primary">
                  {f.icon}
                </div>
                <h3 className="font-display text-xl">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-text-dim">
                  {f.body}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── APPS CAROUSEL ────────────────────────────────────────────── */}
      <section className="container-page py-20">
        <Reveal>
          <div className="flex items-end justify-between gap-4">
            <div>
              <h2 className="font-display text-3xl tracking-tight">
                Preloaded apps
              </h2>
              <p className="mt-2 text-text-dim">
                Ship with the badge. Customise or replace any of them.
              </p>
            </div>
            <Link
              href="/apps/"
              className="text-sm text-muted transition-colors hover:text-text"
            >
              All apps →
            </Link>
          </div>
        </Reveal>

        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {PRELOADED.map((app, i) => (
            <AppCard key={app.slug} app={app} index={i} />
          ))}
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────────────────────── */}
      <section className="container-page py-20">
        <Reveal>
          <div className="overflow-hidden rounded-lg border border-primary/30
                          bg-gradient-to-r from-primary/15 via-card to-lilac/10
                          p-10 sm:p-14">
            <h2 className="font-display text-3xl leading-tight tracking-tight
                           sm:text-4xl">
              Build your own apps.<br />
              <span className="text-primary">It's a manifest and a main.py.</span>
            </h2>
            <p className="mt-4 max-w-2xl text-text-dim">
              The badge ships with 20 first-party apps and an on-device store
              that pulls from GitHub at runtime. Fork the repo, drop your app
              in <code className="rounded bg-bg-raised px-1.5 py-0.5 text-sm">apps_market/</code>
              {" "}and submit a PR — the next person to refresh the store will see it.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <a
                href="https://github.com/elixpo/oreo/blob/main/CONTRIBUTING.md"
                target="_blank" rel="noreferrer"
                className="btn-primary"
              >
                Read the contributing guide
              </a>
              <Link href="/get-started/" className="btn-ghost">
                Setup the hardware
              </Link>
            </div>
          </div>
        </Reveal>
      </section>
    </>
  );
}
