"use client";

import { motion } from "framer-motion";
import { Reveal, fadeUp, staggerContainer } from "@/components/MotionWrap";
import { Cpu, MemoryStick, Battery, Radio, Usb, Layers } from "lucide-react";

const SPECS = [
  { icon: <Cpu className="h-4 w-4" />,         k: "MCU",      v: "ESP32-S3 dual core @ 240 MHz" },
  { icon: <MemoryStick className="h-4 w-4" />, k: "Memory",   v: "16 MB flash · 8 MB PSRAM" },
  { icon: <Radio className="h-4 w-4" />,       k: "Radio",    v: "WiFi 2.4 GHz · BLE 5 · IR transceiver" },
  { icon: <Layers className="h-4 w-4" />,      k: "Display",  v: "ST7789 240×320 IPS · portrait" },
  { icon: <Battery className="h-4 w-4" />,     k: "Power",    v: "USB-C + LiPo deep-sleep · ~5 µA standby" },
  { icon: <Usb className="h-4 w-4" />,         k: "I/O",      v: "8-button matrix · IMU · 1-wire IR · I²C bus" },
];

export default function BadgePage() {
  return (
    <div className="container-page pt-16 pb-28">
      <motion.div initial="hidden" animate="visible" variants={staggerContainer}>
        <motion.span variants={fadeUp} className="chip mb-6">
          ESP32-S3-DevKitC · breadboard phase
        </motion.span>
        <motion.h1
          variants={fadeUp}
          className="font-display text-4xl leading-[1.05] tracking-tight sm:text-5xl"
        >
          The hardware,
          <br /><span className="text-primary">all open.</span>
        </motion.h1>
        <motion.p variants={fadeUp} className="mt-5 max-w-2xl text-text-dim">
          Tufty-classic portrait layout. Eight buttons, IR for line-of-sight
          quests, an MPU6050 for shake and tilt, four LEDs around the frame.
          Schematics and BOM live on the repo — fork them and roll your own.
        </motion.p>
      </motion.div>

      <Reveal>
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
                {s.icon}
              </div>
              <div>
                <p className="text-xs uppercase tracking-widest text-muted">{s.k}</p>
                <p className="mt-1 text-text">{s.v}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </Reveal>

      <Reveal delay={0.1}>
        <div className="mt-16 rounded-lg border border-border bg-bg-raised/40 p-8">
          <h2 className="font-display text-2xl">Layered architecture</h2>
          <p className="mt-2 text-text-dim">
            Four layers, each can be rewritten without the others noticing.
          </p>
          <ul className="mt-6 grid gap-2 text-sm text-text-dim">
            <li><span className="text-text">apps/</span> — userland; manifest.json + main.py per app.</li>
            <li><span className="text-text">oreoOS/</span> — the OS: launcher, store, OTA, notifications, file transfer.</li>
            <li><span className="text-text">oreoWare/</span> — HAL / Board Support Package: drivers for the screen, buttons, IMU, BLE, WiFi, IR, battery.</li>
            <li><span className="text-text">MicroPython</span> — runtime (we credit it loudly; we did not write it).</li>
          </ul>
        </div>
      </Reveal>
    </div>
  );
}
