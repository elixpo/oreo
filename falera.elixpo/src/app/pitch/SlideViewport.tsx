"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

/* Shows one 1920x1080 slide. At a 1920x1080 window (the screenshot size)
 * the slide is drawn 1:1 and nothing moves. In a smaller or larger window
 * it is scaled to fit, unless the URL has ?print=1. Arrow keys, Page Up/Down
 * and space step through the deck. */
export default function SlideViewport({
  n,
  total,
  children,
}: {
  n: number;
  total: number;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    const print = new URLSearchParams(window.location.search).get("print") === "1";
    const el = ref.current?.firstElementChild as HTMLElement | null;
    if (!el || print) return;
    const fit = () => {
      const s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
      const x = (window.innerWidth - 1920 * s) / 2;
      const y = (window.innerHeight - 1080 * s) / 2;
      el.style.transform = s === 1 ? "" : `translate(${x}px, ${y}px) scale(${s})`;
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);

  useEffect(() => {
    const go = (to: number) => {
      if (to >= 1 && to <= total) router.push(`/pitch/${to}/${window.location.search}`);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " ") go(n + 1);
      else if (e.key === "ArrowLeft" || e.key === "PageUp") go(n - 1);
      else if (e.key === "Escape") router.push("/pitch/");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [n, total, router]);

  return (
    <div ref={ref} className="pd-viewport">
      {children}
    </div>
  );
}
