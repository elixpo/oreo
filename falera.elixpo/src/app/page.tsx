import Link from "next/link";
import AppCard from "@/components/AppCard";
import { FUND_URL } from "@/lib/links";
import { Card, Eyebrow, Fact, Onward, Section, SectionHeader, Stat } from "@/components/ui";
import { PRELOADED, STORE } from "@/data/apps";

/* The home page tells one story, top to bottom: what Falera is, the proof,
 * the badge, the apps, building for it, RV565, and supporting it. Every
 * section ends with one link onward to the page that goes deeper. */

const PROOF = [
  { value: "57", label: "FaleraOS releases since May 2026", href: "https://github.com/elixpo/falera/tags" },
  { value: "20", label: "apps: 10 built in, 10 in the App Store", href: "/apps/" },
  { value: <span className="font-mono text-[0.85em]">IN000107</span>, label: "OSHWA-certified open source hardware", href: "https://certification.oshwa.org/in000107.html" },
  { value: <span className="font-mono text-[0.85em]">303a:83ec</span>, label: "its own USB ID, assigned by Espressif", href: "https://github.com/espressif/usb-pids/pull/425" },
  { value: "Adafruit", label: "covered FaleraOS and RV565 on its blog", href: "https://blog.adafruit.com/2026/11/04/oreoos-a-micropython-based-operating-system/" },
];

const SPECS: [string, string][] = [
  ["MCU", "ESP32-S3, dual core at 240 MHz, 8 MB PSRAM"],
  ["Display", "2.8″ 320×240 touch screen, eight buttons"],
  ["Radio", "Wi-Fi, Bluetooth LE 5, IR send and receive"],
  ["Power", "LiPo with USB-C charging"],
];

const SHOWCASE = [
  ...PRELOADED.filter((a) => ["store", "gallery", "reader"].includes(a.slug)),
  ...STORE.filter((a) => ["Lumi", "snake", "quest"].includes(a.slug)),
];

const BUILD = [
  { n: "01", title: "Set up the badge", body: "Flash MicroPython, deploy FaleraOS and install the falera CLI. About fifteen minutes with a USB-C cable.", href: "/get-started/" },
  { n: "02", title: "Drive it from your computer", body: "The falera CLI sends files to the Transfer app, sets up Wi-Fi and your profile, installs apps and updates FaleraOS.", href: "/docs/cli/" },
  { n: "03", title: "Write an app", body: "Subclass oreoOS.App, draw on a 320×240 screen, react to eight buttons. Start from falera new.", href: "/docs/apps/" },
];

export default function Home() {
  return (
    <>
      {/* 1 · What Falera is */}
      <div className="border-b border-border">
        <div className="container-page grid items-center gap-12 py-14 sm:py-20 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] lg:gap-16 lg:py-24">
          <div>
            <Eyebrow className="mb-6">FaleraOS by Elixpo · open hardware</Eyebrow>
            <h1 className="h-display max-w-[17ch]">
              <span className="sr-only">FaleraOS: </span>
              A Python operating system, <em>in a pocket-sized badge.</em>
            </h1>
            <p className="lede mt-6 max-w-prose-site">
              FaleraOS runs 20 apps on the ESP32-S3 Falera Badge: a launcher, an on-device App Store,
              OTA updates over Wi-Fi, file transfer over USB, IR-quest peer pairing, and a Tamagotchi
              panda that judges you for skipping meals.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/get-started/" className="btn-primary">Get started</Link>
              <a href={FUND_URL} target="_blank" rel="noreferrer" className="btn-accent">Fund the badge</a>
              <a href="https://github.com/elixpo/falera" target="_blank" rel="noreferrer" className="btn-ghost">
                Source on GitHub
              </a>
            </div>
          </div>
          <figure className="card-fill overflow-hidden">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/badge-angle.webp"
              alt="The Falera Badge PCB: black solder mask, white silkscreen with Lumi the panda, eight buttons along the bottom"
              width={900}
              height={750}
              fetchPriority="high"
              decoding="async"
              className="aspect-[6/5] h-auto w-full object-cover"
            />
          </figure>
        </div>
      </div>

      {/* 2 · Proof */}
      <Section label="Proof" tight>
        <ul className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-5 [&>li:first-child]:col-span-2 lg:[&>li:first-child]:col-span-1">
          {PROOF.map((p) => (
            <li key={p.label} className="min-w-0">
              <Stat value={p.value} label={p.label} href={p.href} className="h-full" />
            </li>
          ))}
        </ul>
      </Section>

      {/* 3 · The badge */}
      <Section id="badge">
        <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.8fr)] lg:gap-16">
          <div>
            <SectionHeader
              eyebrow="The badge"
              title={<>The hardware, <em>all open.</em></>}
              lede="A 2.8″ touch screen, eight buttons, IR for line-of-sight quests, a motion sensor for shake and tilt, and a speaker, on a 4-layer board. The KiCad design, the bill of materials and the build notes are in the repo, so you can fork them and make your own."
            />
            <div className="mt-10 grid gap-3 sm:grid-cols-2 sm:gap-4">
              {SPECS.map(([k, v]) => <Fact key={k} k={k}>{v}</Fact>)}
            </div>
            <Onward href="/badge/">See the board in 3D</Onward>
          </div>
          <figure className="card-fill mx-auto w-full max-w-sm p-6 sm:p-8 lg:max-w-none">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/pcb_back_card.webp"
              alt="Back of the Falera Badge PCB, a KiCad render: the ESP32-S3 module, the OSHW mark, the microSD slot and USB-C"
              width={808}
              height={1218}
              loading="lazy"
              decoding="async"
              className="mx-auto h-auto max-h-[22rem] w-auto sm:max-h-[34rem]"
            />
          </figure>
        </div>
      </Section>

      {/* 4 · Apps and the App Store */}
      <Section id="apps">
        <SectionHeader
          eyebrow="Apps and the App Store"
          title={<>Everything that ships, <em>and everything that streams in.</em></>}
          lede="Ten apps come on every badge. The on-device App Store installs ten more from GitHub at runtime: no laptop, no recompile."
        />
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SHOWCASE.map((app) => <AppCard key={app.slug} app={app} />)}
        </div>
        <Onward href="/apps/">See all 20 apps</Onward>
      </Section>

      {/* 5 · Build for it */}
      <Section id="build" fill>
        <SectionHeader
          eyebrow="Build for it"
          title={<>Build your own apps. <em>It&apos;s a manifest and a main.py.</em></>}
          lede={<>Apps are plain Python packages that FaleraOS loads at runtime. Fork the repo, drop your app in <code className="code">apps_market/</code> and open a pull request: the next person to refresh the store will see it.</>}
        />
        <ol className="mt-10 grid gap-4 md:grid-cols-3">
          {BUILD.map((b) => (
            <li key={b.n}>
              <Card href={b.href} className="flex h-full flex-col p-6">
                <span className="font-mono text-sm font-bold text-primary">{b.n}</span>
                <span className="h-card mt-4 block group-hover:text-primary">{b.title}</span>
                <span className="mt-2 block text-sm leading-relaxed text-text-dim">{b.body}</span>
              </Card>
            </li>
          ))}
        </ol>
        <Onward href="/docs/">Read the docs</Onward>
      </Section>

      {/* 6 · RV565 */}
      <Section id="rv565">
        <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-16">
          <div>
            <SectionHeader
              eyebrow="RV565 video"
              title={<>Video, <em>built for the hardware.</em></>}
              lede="RV565 is Elixpo's frame-independent video format for microcontroller displays: frames decode straight to the panel's own pixels. It plays the Gallery's videos on the badge, and ships for Arduino, ESP-IDF and Python."
            />
            <Onward href="/rv565/">Explore RV565</Onward>
          </div>
          <div className="grid grid-cols-2 content-start gap-3 sm:gap-4">
            <Stat value="24 FPS" label="on ESP32-S3 with zero missed deadlines, dual-core" />
            <Stat value="98.1%" label="of the 40 MHz SPI wire-time bound" />
            <Stat value="arXiv" label="the paper, 2610.35935 (cs.AR)" href="/paper/" />
            <Stat value="In-browser" label="converter: MP4 to RV565 or clip.h, no upload" href="/rv565/convert/" />
          </div>
        </div>
      </Section>

      {/* 7 · Support */}
      <Section id="support" fill>
        <div className="grid items-start gap-12 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)] lg:gap-16">
          <div>
            <SectionHeader
              eyebrow="Support"
              title={<>The first Falera PCBs <em>are being made now.</em></>}
              lede="Falera has no company or investor behind it. The first five boards were paid for out of pocket, and the community is funding the rest. Even $1 or ₹100 helps build them, and everyone who chips in is thanked by name."
            >
              <div className="mt-8 flex flex-wrap gap-3">
                <a href={FUND_URL} target="_blank" rel="noreferrer" className="btn-accent">Fund the badge</a>
              </div>
            </SectionHeader>
            <Onward href="/supporters/">Meet our supporters</Onward>
          </div>
          <Card className="p-6 sm:p-8">
            <p className="eyebrow">Sponsors</p>
            <p className="h-card mt-3">Become a founding sponsor</p>
            <p className="mt-2 text-sm leading-relaxed text-text-dim">
              Hardware makers, chip companies and developer-tool teams: help take Falera from five
              hand-built boards to a factory batch. Write to{" "}
              <span className="select-all font-mono text-text">hello@elixpo.com</span>.
            </p>
          </Card>
        </div>
      </Section>
    </>
  );
}
