"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X, Github, Tag, User, Contact, Bird, Image as ImageIcon,
  Worm, Compass, BookOpen, Car, Cloud, GitCommit, Gamepad2,
  HardDrive, Palette, PawPrint, Cpu, Wifi, Bluetooth,
  RefreshCw, Settings, type LucideIcon,
} from "lucide-react";
import type { AppEntry, AppIconId } from "@/data/apps";

const ICONS: Record<AppIconId, LucideIcon> = {
  Contact, Bird, Image: ImageIcon, Worm, Compass, BookOpen, Car, Cloud,
  GitCommit, User, Gamepad2, HardDrive, Palette, PawPrint, Cpu, Wifi,
  Bluetooth, RefreshCw, Settings,
};

type Tint = { ring: string; glow: string; text: string };

const TINT: Record<AppEntry["tint"], Tint> = {
  primary: { ring: "ring-primary/40", glow: "shadow-[0_0_36px_rgba(255,93,104,0.22)]", text: "text-primary" },
  teal:    { ring: "ring-teal/40",    glow: "shadow-[0_0_36px_rgba(61,220,151,0.20)]", text: "text-teal" },
  gold:    { ring: "ring-gold/40",    glow: "shadow-[0_0_36px_rgba(255,209,102,0.18)]",text: "text-gold" },
  lilac:   { ring: "ring-lilac/40",   glow: "shadow-[0_0_36px_rgba(162,155,254,0.20)]",text: "text-lilac" },
};

/* The icon tile is its own component so the grid card and the
 * detail modal share the "real PNG with Lucide fallback" logic.
 * `image-rendering: pixelated` keeps the chunky badge pixel art
 * crisp at every zoom level. */
function IconTile({
  app, tint, Icon, size = "md",
}: {
  app: AppEntry;
  tint: Tint;
  Icon: LucideIcon;
  size?: "md" | "lg";
}) {
  const [pngOk, setPngOk] = useState(true);
  const dim    = size === "lg" ? "h-20 w-20" : "h-14 w-14";
  const iconSz = size === "lg" ? "h-10 w-10" : "h-6 w-6";
  const pad    = size === "lg" ? "p-3"       : "p-2";
  return (
    <div className={`grid ${dim} shrink-0 place-items-center rounded-md
                     overflow-hidden bg-card-sub ring-2 ring-inset
                     ${tint.ring} ${tint.text} ${pad}`}>
      {app.pngIcon && pngOk ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={app.pngIcon}
          alt=""
          aria-hidden="true"
          onError={() => setPngOk(false)}
          className="h-full w-full object-contain"
          style={{ imageRendering: "pixelated" }}
          loading="lazy"
          decoding="async"
        />
      ) : (
        <Icon className={iconSz} />
      )}
    </div>
  );
}

export default function AppCard({
  app,
  index = 0,
}: {
  app: AppEntry;
  index?: number;
}) {
  const [open, setOpen] = useState(false);
  const tint = TINT[app.tint] ?? TINT.primary;
  const Icon = ICONS[app.icon] ?? Cpu;

  return (
    <>
      <motion.button
        type="button"
        onClick={() => setOpen(true)}
        initial={{ opacity: 0, y: 14 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{
          duration: 0.5,
          ease: [0.16, 1, 0.3, 1],
          delay: 0.04 * (index % 6),
        }}
        whileHover={{ y: -4 }}
        className={`card-surface group relative w-full overflow-hidden p-5
                    text-left hover:border-text/30 ${tint.glow}`}
      >
        <div className="flex items-start gap-4">
          <IconTile app={app} tint={tint} Icon={Icon} size="md" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <h3 className={`truncate font-display text-lg ${tint.text}`}>
                {app.name}
              </h3>
              <span className="chip">{app.category}</span>
            </div>
            <p className="mt-1 text-sm leading-relaxed text-text-dim">
              {app.blurb}
            </p>
          </div>
        </div>
        <motion.div
          className="absolute inset-x-5 bottom-0 h-px origin-left bg-gradient-to-r
                     from-transparent via-primary to-transparent"
          initial={{ scaleX: 0, opacity: 0 }}
          whileHover={{ scaleX: 1, opacity: 1 }}
          transition={{ duration: 0.35 }}
        />
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{    opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-50 grid place-items-center
                       bg-bg/80 px-4 backdrop-blur"
          >
            <motion.div
              initial={{ scale: 0.96, opacity: 0, y: 8 }}
              animate={{ scale: 1,    opacity: 1, y: 0 }}
              exit={{    scale: 0.96, opacity: 0, y: 8 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              onClick={(e) => e.stopPropagation()}
              className="card-surface ring-glow relative w-full max-w-lg
                         overflow-hidden p-8"
            >
              <button
                onClick={() => setOpen(false)}
                className="absolute right-4 top-4 grid h-9 w-9 place-items-center
                           rounded-md text-muted hover:bg-card-sub hover:text-text"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>

              <div className="flex items-center gap-5">
                <IconTile app={app} tint={tint} Icon={Icon} size="lg" />
                <div>
                  <h2 className={`font-display text-3xl ${tint.text}`}>
                    {app.name}
                  </h2>
                  <p className="mt-1 text-sm text-muted">apps/{app.slug}/</p>
                </div>
              </div>

              <p className="mt-6 leading-relaxed text-text-dim">{app.blurb}</p>

              <div className="mt-6 grid grid-cols-2 gap-3 text-sm">
                <Meta k={<Tag className="h-3.5 w-3.5" />}  v={app.category}      label="Category" />
                <Meta k={<User className="h-3.5 w-3.5" />} v="@Circuit-Overtime" label="Author" />
              </div>

              <div className="mt-7 flex flex-wrap gap-3">
                <a
                  href={`https://github.com/elixpo/oreo/tree/main/apps/${encodeURIComponent(app.slug)}`}
                  target="_blank" rel="noreferrer"
                  className="btn-primary"
                >
                  <Github className="h-4 w-4" /> View source
                </a>
                <a
                  href={`https://github.com/elixpo/oreo/blob/main/apps/${encodeURIComponent(app.slug)}/manifest.json`}
                  target="_blank" rel="noreferrer"
                  className="btn-ghost"
                >
                  manifest.json
                </a>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function Meta({ k, v, label }: { k: React.ReactNode; v: string; label: string }) {
  return (
    <div className="rounded-md border border-border/60 bg-bg-raised/50 px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-xs uppercase tracking-widest text-muted">
        {k} {label}
      </p>
      <p className="mt-1 truncate text-text">{v}</p>
    </div>
  );
}
