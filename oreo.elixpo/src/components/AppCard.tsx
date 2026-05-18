"use client";

import { motion } from "framer-motion";
import type { AppEntry } from "@/data/apps";

const TINT: Record<AppEntry["tint"], { ring: string; glow: string; text: string }> = {
  primary: { ring: "ring-primary/40", glow: "shadow-[0_0_36px_rgba(255,93,104,0.22)]", text: "text-primary" },
  teal:    { ring: "ring-teal/40",    glow: "shadow-[0_0_36px_rgba(61,220,151,0.20)]", text: "text-teal" },
  gold:    { ring: "ring-gold/40",    glow: "shadow-[0_0_36px_rgba(255,209,102,0.18)]",text: "text-gold" },
  lilac:   { ring: "ring-lilac/40",   glow: "shadow-[0_0_36px_rgba(162,155,254,0.20)]",text: "text-lilac" },
};

export default function AppCard({
  app,
  index = 0,
}: {
  app: AppEntry;
  index?: number;
}) {
  const t = TINT[app.tint] ?? TINT.primary;
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{
        duration: 0.5,
        ease: [0.16, 1, 0.3, 1],
        delay: 0.04 * (index % 6),
      }}
      whileHover={{ y: -4 }}
      className={`card-surface group relative overflow-hidden p-5
                  hover:border-text/30 ${t.glow}`}
    >
      <div className="flex items-start gap-4">
        <div className={`grid h-14 w-14 shrink-0 place-items-center rounded-md
                         bg-card-sub ring-2 ring-inset ${t.ring}
                         font-display text-2xl ${t.text}`}>
          {app.glyph}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <h3 className={`truncate font-display text-lg ${t.text}`}>{app.name}</h3>
            <span className="chip">{app.category}</span>
          </div>
          <p className="mt-1 text-sm leading-relaxed text-text-dim">
            {app.blurb}
          </p>
        </div>
      </div>
      {/* Decorative bottom-line that animates in on hover */}
      <motion.div
        className="absolute inset-x-5 bottom-0 h-px origin-left bg-gradient-to-r
                   from-transparent via-primary to-transparent"
        initial={{ scaleX: 0, opacity: 0 }}
        whileHover={{ scaleX: 1, opacity: 1 }}
        transition={{ duration: 0.35 }}
      />
    </motion.div>
  );
}
