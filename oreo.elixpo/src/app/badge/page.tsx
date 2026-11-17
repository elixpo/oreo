"use client";

import { motion } from "framer-motion";
import { Reveal, fadeUp, staggerContainer } from "@/components/MotionWrap";
import {
  Cpu, MemoryStick, Battery, Radio, Usb, Layers,
  Layout, Ruler, Github,
} from "lucide-react";

const SPECS = [
  { Icon: Cpu,          k: "MCU",      v: "ESP32-S3-WROOM-1 · dual core @ 240 MHz" },
  { Icon: MemoryStick,  k: "Memory",   v: "16 MB flash · 8 MB PSRAM · microSD" },
  { Icon: Radio,        k: "Radio",    v: "Wi-Fi 2.4 GHz · Bluetooth LE 5 · IR transmit and receive" },
  { Icon: Layout,       k: "Display",  v: "2.8″ ILI9341 320×240 · resistive touch · landscape" },
  { Icon: Battery,      k: "Power",    v: "LiPo · USB-C charging (BQ24074) · 3.3 V buck-boost" },
  { Icon: Usb,          k: "I/O",      v: "8 buttons · MPU-6050 · speaker · Qwiic · 4-GPIO header" },
  { Icon: Ruler,        k: "Dimensions", v: "88 × 133.5 mm portrait PCB" },
  { Icon: Layers,       k: "Layers",   v: "4-layer FR-4 · 1.6 mm · black mask" },
];

const STACK = [
  { lvl: "apps/",        body: "Userland — manifest.json + main.py per app.",
    tint: "from-primary/30 to-primary/5" },
  { lvl: "oreoOS/",      body: "The OS: launcher, store, OTA, notifications, file transfer.",
    tint: "from-lilac/30 to-lilac/5" },
  { lvl: "oreoWare/",    body: "HAL / Board Support: drivers for screen, buttons, IMU, BLE, WiFi, IR, battery.",
    tint: "from-teal/30 to-teal/5" },
  { lvl: "MicroPython",  body: "Runtime — we credit it loudly; we did not write it.",
    tint: "from-gold/30 to-gold/5" },
];

export default function BadgePage() {
  return (
    <div className="relative">
      {/* Soft brand glows */}
      <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[640px] overflow-hidden">
        <div className="absolute left-1/3 top-0  h-[440px] w-[440px] rounded-full bg-primary/[0.10] blur-[140px]" />
        <div className="absolute right-1/4 top-32 h-[300px] w-[300px] rounded-full bg-lilac/[0.10]  blur-[120px]" />
        <div className="absolute left-1/4 top-64  h-[260px] w-[260px] rounded-full bg-teal/[0.08]   blur-[120px]" />
      </div>

      <div className="container-page pt-16 pb-28">
        {/* ── HERO ────────────────────────────────────────────────────── */}
        <div className="max-w-3xl">
          <motion.div initial="hidden" animate="visible" variants={staggerContainer}>
            <motion.span variants={fadeUp} className="chip mb-6">
              PCB v1 · first boards ordered
            </motion.span>
            <motion.h1
              variants={fadeUp}
              className="font-display text-4xl leading-[1.05] tracking-tight sm:text-5xl"
            >
              The hardware,{" "}
              <span className="bg-gradient-to-r from-primary via-gold to-lilac
                               bg-clip-text text-transparent">
                all open.
              </span>
            </motion.h1>
            <motion.p variants={fadeUp} className="mt-5 max-w-2xl text-text-dim">
              A 2.8″ touch screen, eight buttons, IR for line-of-sight quests,
              an MPU-6050 for shake and tilt, a speaker, and LEDs around the
              frame. The KiCad design, the bill of materials and the build
              notes live in the repo, so you can fork them and make your own.
            </motion.p>
            <motion.div variants={fadeUp} className="mt-8 flex flex-wrap gap-3">
              <a
                href="https://github.com/elixpo/oreo/blob/main/circuit/elixpo/README.md"
                target="_blank" rel="noreferrer"
                className="btn-primary"
              >
                <Github className="h-4 w-4" /> Board design notes
              </a>
              <a
                href="https://github.com/elixpo/oreo/blob/main/circuit/elixpo/BOM_COST.md"
                target="_blank" rel="noreferrer"
                className="btn-ghost"
              >
                Bill of materials
              </a>
              <a
                href="https://github.com/elixpo/oreo/tree/main/circuit/elixpo"
                target="_blank" rel="noreferrer"
                className="btn-ghost"
              >
                KiCad files
              </a>
              <a
                href="https://github.com/elixpo/oreo"
                target="_blank" rel="noreferrer"
                className="btn-ghost"
              >
                Repo
              </a>
            </motion.div>
            <motion.a
              variants={fadeUp}
              href="https://certification.oshwa.org/in000107.html"
              target="_blank" rel="noreferrer"
              className="mt-8 inline-flex items-center gap-4"
              aria-label="Certified open source hardware, OSHWA UID IN000107"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/oshw_mark.png"
                alt="OSHW IN000107"
                className="h-12 w-auto"
                width={4000} height={1122}
                decoding="async"
              />
              <span className="text-sm text-text-dim">
                Certified open source hardware by OSHWA
              </span>
            </motion.a>
          </motion.div>

        </div>

        {/* ── THE BOARD ───────────────────────────────────────────────── */}
        <Reveal>
          <div className="mt-16 grid gap-4 sm:grid-cols-2">
            {[
              { src: "/pcb_front.jpg", alt: "Front of the Oreo badge PCB", label: "Front" },
              { src: "/pcb_back.jpg",  alt: "Back of the Oreo badge PCB",  label: "Back" },
            ].map((img) => (
              <figure
                key={img.src}
                className="overflow-hidden rounded-lg border border-border bg-bg-raised/40"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={img.src}
                  alt={img.alt}
                  className="h-auto w-full object-contain"
                  width={700} height={1064}
                  loading="lazy"
                  decoding="async"
                />
                <figcaption className="px-4 py-3 text-xs uppercase tracking-widest text-muted">
                  {img.label}
                </figcaption>
              </figure>
            ))}
          </div>
        </Reveal>

        {/* ── SPEC GRID ────────────────────────────────────────────── */}
        <div className="mt-14 grid gap-3 sm:grid-cols-2">
          {SPECS.map((s, i) => (
            <motion.div
              key={s.k}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.04 * i, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              className="card-surface flex items-start gap-3 p-5"
            >
              <div className="grid h-9 w-9 place-items-center rounded-md
                              bg-card-sub text-primary">
                <s.Icon className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-widest text-muted">{s.k}</p>
                <p className="mt-1 text-text">{s.v}</p>
              </div>
            </motion.div>
          ))}
        </div>

        {/* ── LAYERED ARCHITECTURE ────────────────────────────────── */}
        <Reveal>
          <div className="mt-16">
            <h2 className="font-display text-2xl tracking-tight">
              Layered architecture
            </h2>
            <p className="mt-2 text-text-dim">
              Four layers, each can be rewritten without the others noticing.
            </p>
          </div>
        </Reveal>

        <div className="mt-8 grid gap-3">
          {STACK.map((row, i) => (
            <motion.div
              key={row.lvl}
              initial={{ opacity: 0, x: -16 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.06 * i, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
              className={`relative overflow-hidden rounded-lg border border-border
                          bg-gradient-to-r ${row.tint} p-5`}
            >
              <div className="flex items-center justify-between gap-4">
                <code className="font-mono text-lg text-text">{row.lvl}</code>
                <span className="text-xs uppercase tracking-widest text-muted">
                  L{STACK.length - i}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-text-dim">{row.body}</p>
            </motion.div>
          ))}
        </div>

        {/* ── CREDITS ───────────────────────────────────────────────── */}
        <Reveal>
          <div className="mt-16 card-surface p-6">
            <h2 className="font-display text-2xl tracking-tight">Made by</h2>
            <p className="mt-3 max-w-2xl text-text-dim">
              Designed by{" "}
              <a href="https://github.com/Circuit-Overtime" target="_blank" rel="noreferrer"
                 className="text-text underline-offset-4 hover:underline">
                Ayushman Bhattacharya (@Circuit-Overtime)
              </a>{" "}
              with{" "}
              <a href="https://github.com/anwe-ch" target="_blank" rel="noreferrer"
                 className="text-text underline-offset-4 hover:underline">
                Anwesha Chakraborty (@anwe-ch)
              </a>
              , Elixpo core maintainer and co-author of the RV565 video format the
              badge plays.
            </p>
          </div>
        </Reveal>
      </div>
    </div>
  );
}
