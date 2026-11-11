import Link from "next/link";
import { ArrowRight, ArrowUpRight } from "lucide-react";
import JsonLd from "@/components/JsonLd";
import Rv565Converter from "@/components/Rv565Converter";
import { SITE_URL, pageMetadata } from "@/lib/seo";

const PATH = "/rv565/convert/";

export const metadata = pageMetadata({
  title: "Video to RGB565, Grayscale and Monochrome Converter for Microcontroller Displays",
  description:
    "Free online converter: turn an MP4 or WebM into an RV565 video or an Arduino clip.h in your display's own pixel format — RGB565 for ST7789 and ILI9341 TFTs, RGB666, RGB444, 4-bit grayscale for SSD1322 OLEDs, or 1-bit for SSD1306 OLEDs and e-paper. Runs in your browser — no upload, no account.",
  path: PATH,
  keywords: [
    "MP4 to RGB565", "video to RGB565 converter", "RGB565 converter", "ESP32 video player",
    "ST7789 video", "Arduino video display", "play video on ESP32", "RV565",
    "TFT_eSPI video", "convert video to C array", "ESP32-S3 SPI display video",
    "SSD1306 video", "OLED animation converter", "video to monochrome bitmap", "ILI9341 video", "RGB666",
  ],
});

const STEPS = [
  ["Convert", "Drop a video here. Pick the frame size, the pixel format your display takes and the frame rate; the page writes an .rv565 file and a clip.h for Arduino."],
  ["Install RV565", "Arduino IDE → Library Manager → search “RV565”, or arduino-cli lib install RV565. ESP-IDF and the Pico SDK are supported too; on a computer, pip install rv565 gives the same tools. The released 1.x library plays version 6 files: tick “Version 6 file” before converting."],
  ["Play", "Open the ESP32S3_Player example, replace clip.h with yours, and upload. Large clips can live in a flash partition instead."],
];

const FAQ = [
  {
    q: "Is my video uploaded anywhere?",
    a: "No. The video is decoded by your browser, converted to your display's pixel format on a canvas and compressed with the browser's built-in zlib. Nothing leaves your device, and there is no account or sign-up.",
  },
  {
    q: "What is the RV565 format?",
    a: "A small video container for microcontrollers whose frames decode straight to the display's native pixels, so the board runs no colour conversion. Version 7 declares one of nine pixel formats (RGB565 in either byte order, RGB444, RGB666, RGB888, 8- and 4-bit grayscale, and 1-bit monochrome in rows or SSD1306-style pages) and a codec (zlib or stored). Frames are keyframes, XOR deltas from the previous frame, or repeats, with a keyframe at least every K frames so seeking stays fast. Version 6, the format the paper arXiv:2610.35935 measured, is the RGB565 + zlib + every-frame-a-keyframe case. Both are specified in the RV565 repository.",
  },
  {
    q: "Which boards and displays work?",
    a: "The released RV565 1.x library plays version 6 files on ESP32-S3 (measured at 24 FPS with zero missed frames), on other ESP32 chips, and experimentally on the Raspberry Pi Pico 2, with ST7789 SPI panels such as 320×240, 240×240 and 135×240 modules; it also works with TFT_eSPI and LovyanGFX. Version 7 adds the formats for ILI9341/ILI9488 18-bit panels, grayscale OLEDs such as the SSD1322, 1-bit OLEDs such as the SSD1306, and e-paper; version 7 files need RV565 2.0 on the board. Until your player is on 2.0, tick “Version 6 file”.",
  },
  {
    q: "What frame size and frame rate should I choose?",
    a: "For a colour TFT on an ESP32-S3, 180×135 at 24 FPS in RGB565 with zlib is the setting measured in the paper: the board scales it to a 320×240 panel and holds 24 FPS without missed frames, and the page predicts missed frames for that setting. Larger frames look sharper but need more memory and time per frame. For an OLED or e-paper panel, choose its native resolution and the matching grayscale or monochrome format; those frames are small, so higher rates are cheap.",
  },
  {
    q: "How long can a clip be?",
    a: "Up to 30 seconds and 200 MB of input per conversion, to keep the browser responsive. For longer clips use the rv565 command-line tool (pip install rv565), which reads the source video with an installed FFmpeg.",
  },
  {
    q: "Can I convert without a browser?",
    a: "Yes. The rv565 package is published on PyPI: pip install rv565, then rv565 encode input.mp4 clip.rv565 --size 180x135 --fps 24, and rv565 c-array clip.rv565 clip.h for Arduino. With pip install \"rv565[pillow]\", Pillow's Image.open reads .rv565 files too.",
  },
];

export default function ConvertPage() {
  return (
    <article>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@graph": [
            {
              "@type": "SoftwareApplication",
              name: "RV565 Video Converter",
              url: `${SITE_URL}${PATH}`,
              applicationCategory: "MultimediaApplication",
              operatingSystem: "Any (web browser)",
              offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
              description:
                "Converts MP4 and WebM video to RV565 video and Arduino C headers in a display's native pixel format (RGB565, RGB666, RGB444, RGB888, grayscale or monochrome) for TFT, OLED and e-paper displays on microcontrollers, entirely in the browser.",
              isAccessibleForFree: true,
              author: { "@type": "Organization", name: "Elixpo", url: "https://elixpo.com" },
              sameAs: ["https://github.com/elixpo/rv565", "https://pypi.org/project/rv565/"],
            },
            {
              "@type": "FAQPage",
              mainEntity: FAQ.map(({ q, a }) => ({
                "@type": "Question",
                name: q,
                acceptedAnswer: { "@type": "Answer", text: a },
              })),
            },
          ],
        }}
      />

      <header className="container-page border-b border-border pb-14 pt-20 sm:pt-28">
        <p className="eyebrow">RV565 · free tool · runs in your browser</p>
        <h1 className="max-w-6xl font-display text-[clamp(2.4rem,5.2vw,5.4rem)] leading-[0.98]">
          Video in your display&apos;s <em>own pixels</em>, ready for your microcontroller.
        </h1>
        <p className="mt-6 max-w-3xl text-[1.05rem] leading-relaxed text-text-dim">
          Turn an MP4 or WebM into an RV565 clip or an Arduino <code className="font-mono">clip.h</code>: RGB565 for
          ST7789 and ILI9341 TFTs, 18-bit RGB666, 4-bit grayscale for SSD1322 OLEDs, 1-bit for SSD1306 OLEDs and
          e-paper, and more. Files use RV565 format version 7, or version 6 for the released RV565 1.x library on
          ESP32-S3, other ESP32 chips and the Raspberry Pi Pico 2. No upload, no account.
        </p>
        <ul className="mt-8 flex flex-wrap gap-3 text-sm">
          <li className="chip">Arduino · Library Manager → RV565</li>
          <li><a href="https://pypi.org/project/rv565/" target="_blank" rel="noreferrer" className="chip hover:text-text">Python · pip install rv565</a></li>
          <li><a href="https://github.com/elixpo/rv565" target="_blank" rel="noreferrer" className="chip hover:text-text">GitHub · elixpo/rv565</a></li>
        </ul>
      </header>

      <section className="container-page border-b border-border py-14">
        <Rv565Converter />
      </section>

      <section className="container-page border-b border-border py-20">
        <p className="eyebrow">From video to screen</p>
        <h2 className="mb-10 max-w-4xl font-display text-[clamp(2rem,3.6vw,3.6rem)] leading-[1]">
          Three steps to video on a microcontroller.
        </h2>
        <ol className="grid gap-4 md:grid-cols-3">
          {STEPS.map(([title, body], i) => (
            <li key={title} className="card-surface flex flex-col p-6">
              <span className="font-mono text-xs text-muted">{String(i + 1).padStart(2, "0")}</span>
              <h3 className="mt-4 font-display text-2xl leading-tight">{title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-muted">{body}</p>
            </li>
          ))}
        </ol>
        <div className="mt-10 flex flex-wrap gap-3">
          <a href="https://github.com/elixpo/rv565" target="_blank" rel="noreferrer" className="btn-primary">
            RV565 library on GitHub <ArrowUpRight className="h-4 w-4" />
          </a>
          <a href="https://pypi.org/project/rv565/" target="_blank" rel="noreferrer" className="btn-ghost">
            pip install rv565 <ArrowUpRight className="h-4 w-4" />
          </a>
          <Link href="/paper/" className="btn-ghost">
            Read the paper <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      <section className="container-page py-20">
        <p className="eyebrow">Questions</p>
        <h2 className="mb-10 font-display text-[clamp(2rem,3.6vw,3.6rem)] leading-[1]">Frequently asked.</h2>
        <div className="divide-y divide-border rounded-[1.4rem] border border-border bg-card">
          {FAQ.map(({ q, a }) => (
            <details key={q} className="group p-6">
              <summary className="cursor-pointer list-none font-semibold marker:hidden">
                {q}
              </summary>
              <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">{a}</p>
            </details>
          ))}
        </div>
      </section>
    </article>
  );
}
