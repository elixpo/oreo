"use client";

import { motion } from "framer-motion";
import { Reveal, staggerContainer, fadeUp } from "@/components/MotionWrap";
import AppCard from "@/components/AppCard";
import { PRELOADED, ALL_APPS, STORE } from "@/data/apps";

export default function AppsPage() {
  return (
    <div className="container-page pt-16 pb-28">
      <motion.div
        initial="hidden"
        animate="visible"
        variants={staggerContainer}
      >
        <motion.span variants={fadeUp} className="chip mb-6">
          {ALL_APPS.length + STORE.length} apps and counting
        </motion.span>
        <motion.h1
          variants={fadeUp}
          className="font-display text-4xl leading-[1.05] tracking-tight sm:text-5xl"
        >
          Everything that ships,
          <br /><span className="text-primary">and everything that streams in.</span>
        </motion.h1>
        <motion.p
          variants={fadeUp}
          className="mt-5 max-w-2xl text-text-dim"
        >
          The preloaded set lands on the badge at flash time. The store
          pulls fresh apps from GitHub at runtime — no laptop, no
          recompile, no developer mode toggle.
        </motion.p>
      </motion.div>

      {/* Preloaded */}
      <Reveal>
        <div className="mt-16">
          <h2 className="font-display text-2xl tracking-tight">Preloaded</h2>
          <p className="mt-1 text-sm text-muted">
            Shipped with v1. Edit or remove any of them locally.
          </p>
        </div>
      </Reveal>
      <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {PRELOADED.map((a, i) => <AppCard key={a.slug} app={a} index={i} />)}
      </div>

      {/* Full catalogue */}
      <Reveal>
        <div className="mt-20">
          <h2 className="font-display text-2xl tracking-tight">More on the badge</h2>
          <p className="mt-1 text-sm text-muted">
            Settings, tools, and games sit one drawer-tap away.
          </p>
        </div>
      </Reveal>
      <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {ALL_APPS.filter(a => !PRELOADED.find(p => p.slug === a.slug)).map((a, i) =>
          <AppCard key={a.slug} app={a} index={i} />)}
      </div>

      {/* Store */}
      <Reveal>
        <div className="mt-20 flex items-end justify-between gap-4">
          <div>
            <h2 className="font-display text-2xl tracking-tight">From the store</h2>
            <p className="mt-1 text-sm text-muted">
              Community apps installable at runtime from{" "}
              <code className="text-text-dim">apps_market/</code> on the repo.
            </p>
          </div>
          <a
            href="https://github.com/elixpo/oreo/tree/main/apps_market"
            target="_blank" rel="noreferrer"
            className="text-sm text-muted transition-colors hover:text-text"
          >
            Browse on GitHub →
          </a>
        </div>
      </Reveal>
      <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {STORE.map((a, i) => <AppCard key={a.slug} app={a} index={i} />)}
      </div>
    </div>
  );
}
