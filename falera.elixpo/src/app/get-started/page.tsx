import Link from "next/link";
import { Card, NextStep, PageHeader, Section, SectionHeader } from "@/components/ui";
import { GITHUB } from "@/lib/links";

const STEPS = [
  { n: "01", t: "Flash MicroPython",      b: "Download the ESP32-S3 build, hold the BOOT button, flash via esptool. Two-minute job." },
  { n: "02", t: "Clone the OS",            b: "`git clone https://github.com/elixpo/falera` and copy `.env.example` → `.env` with your WiFi credentials." },
  { n: "03", t: "Deploy",                  b: "`python tools/deploy.py` — pushes everything over USB, skips unchanged files, bumps the version." },
  { n: "04", t: "Install the falera CLI",  b: "Run the installer from the falera CLI docs (it checks the release's SHA-256 and installs with pipx or uv), then `falera` opens the full-screen view. To send photos and documents, open Tools > Transfer on the badge, run `falera send <files>` and type the code the badge shows." },
];

// `code` spans in the step text become <code>.
function withCode(text: string) {
  return text.split(/(`[^`]+`)/).map((part, i) =>
    part.startsWith("`") ? <code key={i} className="code">{part.slice(1, -1)}</code> : part,
  );
}

const MORE = [
  { title: "falera CLI", body: "Install it, then every command: Transfer, Wi-Fi, apps, updates.", href: "/docs/cli/" },
  { title: "Connecting over USB", body: "Which port, permissions, and raw mpremote.", href: "/docs/usb/" },
  { title: "Repo", body: "Source, schematics, CHANGELOG.", href: GITHUB },
];

export default function GetStartedPage() {
  return (
    <>
      <PageHeader
        eyebrow="Get started · ~15 minutes · USB-C + a computer"
        title={<>From box to badge, <em>in four steps.</em></>}
        lede="The deploy script handles version bumps, hash-cache pruning, free-space guards, and secrets generation. You hold the BOOT button, you wait, you tap A."
      />

      <Section id="steps">
        <ol className="grid gap-4">
          {STEPS.map((s) => (
            <li key={s.n} className="card flex flex-col gap-3 p-6 sm:flex-row sm:gap-8 sm:p-8">
              <span className="w-12 shrink-0 font-mono text-xl font-bold text-primary">{s.n}</span>
              <div className="max-w-prose-site">
                <h2 className="h-card">{s.t}</h2>
                <p className="mt-2 leading-relaxed text-text-dim">{withCode(s.b)}</p>
              </div>
            </li>
          ))}
        </ol>
      </Section>

      <Section id="next">
        <SectionHeader eyebrow="Go further" title={<>Guides for <em>after the first boot.</em></>} />
        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {MORE.map((m) => (
            <Card key={m.title} href={m.href} className="p-6">
              <p className="h-card group-hover:text-primary">{m.title}</p>
              <p className="mt-2 text-sm leading-relaxed text-text-dim">{m.body}</p>
            </Card>
          ))}
        </div>

        <Card fill className="mt-10 p-6 sm:p-8">
          <p className="eyebrow">Need help?</p>
          <p className="mt-3 max-w-3xl leading-relaxed text-text-dim">
            Run <code className="code">falera doctor</code> first: it checks the cable, port, permissions and
            firmware and ends with next steps (see{" "}
            <Link href="/docs/cli/#troubleshooting" className="link">troubleshooting</Link>). Still stuck? Open an
            issue with its output and the console log from <code className="code">falera logs --restart</code>.
          </p>
        </Card>
      </Section>

      <NextStep
        title={<>Now write <em>your own app.</em></>}
        body="Apps are plain Python packages: one manifest, one shim and a src/ tree."
        href="/docs/apps/"
        cta="Write an app"
      />
    </>
  );
}
