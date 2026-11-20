import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SLIDES, SlideAt } from "../deck";
import SlideViewport from "../SlideViewport";

export const dynamicParams = false;

export function generateStaticParams() {
  return SLIDES.map((_, i) => ({ n: String(i + 1) }));
}

type Props = { params: Promise<{ n: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const n = Number((await params).n);
  const s = SLIDES[n - 1];
  return { title: s ? `${n} / ${SLIDES.length}: ${s.title} · Sponsor deck` : "Sponsor deck" };
}

export default async function SlidePage({ params }: Props) {
  const n = Number((await params).n);
  if (!Number.isInteger(n) || n < 1 || n > SLIDES.length) notFound();
  return (
    <SlideViewport n={n} total={SLIDES.length}>
      <SlideAt n={n} />
    </SlideViewport>
  );
}
