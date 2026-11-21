import Link from "next/link";
import { Card, NextStep, PageHeader, Section, SectionHeader, Stat } from "@/components/ui";
import { pageMetadata } from "@/lib/seo";

/* /rv565/ — the overview of RV565, linking the converter, the paper and the
 * architecture notes. Every fact here is from those pages and from
 * src/data/press.ts. */

export const metadata = pageMetadata({
  title: "RV565: frame-independent video for microcontroller displays",
  description:
    "RV565 is Elixpo's frame-independent video format and library for SPI displays on ESP32-S3, other ESP32 chips and (experimentally) the Raspberry Pi Pico 2: frames decode straight to the panel's native pixels. 24 FPS with zero missed deadlines on ESP32-S3; paper on arXiv; Arduino, ESP-IDF and PyPI packages.",
  path: "/rv565/",
  keywords: ["RV565", "RGB565 video", "ESP32-S3 video", "microcontroller video format", "SPI display video", "Arduino video"],
});

const PARTS = [
  { n: "01", title: "Video converter", body: "Turn an MP4 or WebM into an RV565 clip or an Arduino clip.h in your display's own pixel format. Runs in your browser: no upload, no account.", href: "/rv565/convert/" },
  { n: "02", title: "Research paper", body: "Cross-layer co-design for frame-independent video on ESP32-S3: the dual-core pipeline, the decode-cost model and the measurements. arXiv 2610.35935.", href: "/paper/" },
  { n: "03", title: "Video architecture", body: "Independent RGB565 frames, firmware inflation, SPI2 GDMA stripes, and the measured path from 0.5 to 24 FPS inside FaleraOS.", href: "/docs/video-architecture/" },
];

const SHIPS: [string, string, string][] = [
  ["Arduino", "RV565 in the Library Manager", "https://www.arduinolibraries.info/libraries/rv565"],
  ["Espressif", "RV565 in the component registry", "https://components.espressif.com/components/elixpo/rv565"],
  ["PyPI", "The rv565 encoder and tools", "https://pypi.org/project/rv565/"],
  ["Adafruit", "RV565 ships in the CircuitPython Community Bundle", "https://github.com/adafruit/CircuitPython_Community_Bundle/pull/292"],
  ["Arduino_GFX", "Includes an RV565 video example", "https://github.com/moononournation/Arduino_GFX/pull/823"],
  ["The file command", "Recognises RV565 videos", "https://bugs.astron.com/view.php?id=822"],
];

export default function Rv565Page() {
  return (
    <>
      <PageHeader
        eyebrow="RV565 · video for microcontrollers"
        title={<>Video in your display&apos;s <em>own pixels.</em></>}
        lede="RV565 is a small video container for microcontrollers whose frames decode straight to the display's native pixels, so the board runs no colour conversion. It plays FaleraOS's Gallery videos, and runs on ESP32-S3 and other ESP32 chips, and experimentally on the Raspberry Pi Pico 2."
      >
        <Link href="/rv565/convert/" className="btn-primary">Convert a video</Link>
        <a href="https://github.com/elixpo/rv565" target="_blank" rel="noreferrer" className="btn-ghost">RV565 on GitHub ↗</a>
        <a href="https://pypi.org/project/rv565/" target="_blank" rel="noreferrer" className="btn-ghost">pip install rv565 ↗</a>
      </PageHeader>

      <Section label="Measured on ESP32-S3" tight>
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
          <Stat value="24 FPS" label="on both workloads, zero deadline misses (dual-core)" />
          <Stat value="10.3 ms" label="worst-frame slack, against a 41.7 ms period" />
          <Stat value="98.1%" label="of the 40 MHz SPI wire-time bound" />
          <Stat value="9" label="pixel formats in format version 7, RGB565 to 1-bit" />
        </div>
      </Section>

      <Section id="parts">
        <SectionHeader
          eyebrow="Tools and research"
          title={<>Convert, read, <em>and see how it works.</em></>}
        />
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {PARTS.map((p) => (
            <Card key={p.href} href={p.href} className="flex h-full flex-col p-6 sm:p-7">
              <span className="font-mono text-sm font-bold text-primary">{p.n}</span>
              <h3 className="h-card mt-4 group-hover:text-primary">{p.title}</h3>
              <p className="mt-2 flex-1 text-sm leading-relaxed text-text-dim">{p.body}</p>
              <span className="link-onward mt-6">Open <span aria-hidden="true">→</span></span>
            </Card>
          ))}
        </div>
      </Section>

      <Section id="formats">
        <div className="grid gap-12 lg:grid-cols-2 lg:gap-16">
          <SectionHeader
            eyebrow="The format"
            title={<>Three versions, <em>one container.</em></>}
            lede="Version 6, the format the paper measured, is RGB565 with zlib and every frame a keyframe. Version 7 (RV565 2.0) declares one of nine pixel formats and adds delta, repeat and partial-delta frames. Version 8 (RV565 3.0) adds region deltas, so a player decodes and sends only the rectangle that changed."
          />
          <div className="grid content-start gap-4">
            <Card className="p-6">
              <p className="label">Version 6 · RV565 1.x</p>
              <p className="mt-2 text-sm leading-relaxed text-text-dim">RGB565 + zlib, every frame a keyframe. Measured at 24 FPS with zero missed frames on ESP32-S3.</p>
            </Card>
            <Card className="p-6">
              <p className="label">Version 7 · RV565 2.0</p>
              <p className="mt-2 text-sm leading-relaxed text-text-dim">Nine pixel formats for TFT, OLED and e-paper panels; stored or zlib frames; XOR deltas, repeats and partial deltas.</p>
            </Card>
            <Card className="p-6">
              <p className="label">Version 8 · RV565 3.0</p>
              <p className="mt-2 text-sm leading-relaxed text-text-dim">Region deltas: each changed band also carries the columns that changed.</p>
            </Card>
          </div>
        </div>
      </Section>

      <Section id="ships">
        <SectionHeader eyebrow="Where it ships" title={<>Packaged, <em>and recognised upstream.</em></>} />
        <ul className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SHIPS.map(([who, what, href]) => (
            <li key={href}>
              <Card href={href} className="h-full p-6">
                <p className="h-card group-hover:text-primary">{who} <span aria-hidden="true" className="text-muted">↗</span></p>
                <p className="mt-1 text-sm leading-relaxed text-text-dim">{what}</p>
              </Card>
            </li>
          ))}
        </ul>
      </Section>

      <NextStep
        title={<>Try it on <em>your own clip.</em></>}
        body="Pick the frame size, the pixel format your display takes and the frame rate."
        href="/rv565/convert/"
        cta="Open the converter"
      />
    </>
  );
}
