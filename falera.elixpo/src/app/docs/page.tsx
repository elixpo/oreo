import { Card, NextStep, PageHeader, Section, SectionHeader } from "@/components/ui";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: "FaleraOS Documentation",
  description: "Developer guides and engineering deep dives for FaleraOS and the Falera Badge.",
  path: "/docs/",
  keywords: ["FaleraOS documentation", "ESP32-S3 development", "MicroPython documentation"],
});

const docs = [
  {
    href: "/docs/cli/",
    title: "The falera CLI",
    description: "Install falera-cli, then control the badge over USB: the full-screen view, Transfer, files, apps, Wi-Fi, profile setup, updates and troubleshooting.",
  },
  {
    href: "/docs/usb/",
    title: "Connecting the badge",
    description: "Which USB-C port, port names, Linux permissions, the CLI first, and raw mpremote for advanced use.",
  },
  {
    href: "/docs/transfer/",
    title: "The Transfer app",
    description: "Send photos, videos and documents with the code the badge shows; the safety checks and the protocol.",
  },
  {
    href: "/docs/apps/",
    title: "Writing FaleraOS apps",
    description: "App structure, lifecycle hooks, manifests, graphics, controls, and deployment.",
  },
  {
    href: "/docs/video-architecture/",
    title: "RV565 video architecture",
    description: "Independent RGB565 frames, firmware inflation, SPI2 GDMA stripes, and the measured path from 0.5 to 24 FPS.",
  },
  {
    href: "/paper/",
    title: "RV565 research paper",
    description: "Preview the forthcoming paper, authors, measured results, and scope of the cross-layer video architecture.",
  },
];

const guides = docs.filter((d) => !d.href.includes("video") && d.href !== "/paper/");
const deep = docs.filter((d) => d.href.includes("video") || d.href === "/paper/");

function DocCard({ doc, n }: { doc: (typeof docs)[number]; n: number }) {
  return (
    <Card href={doc.href} className="flex h-full flex-col p-6 sm:p-7">
      <span className="font-mono text-sm font-bold text-primary">{String(n).padStart(2, "0")}</span>
      <h3 className="h-card mt-4 group-hover:text-primary">{doc.title}</h3>
      <p className="mt-2 flex-1 text-sm leading-relaxed text-text-dim">{doc.description}</p>
      <span className="link-onward mt-6">Read <span aria-hidden="true">→</span></span>
    </Card>
  );
}

export default function DocsPage() {
  return (
    <>
      <PageHeader
        eyebrow="FaleraOS docs"
        title={<>Build on the badge. <em>Understand the system.</em></>}
        lede="Practical developer references and detailed accounts of the engineering decisions behind FaleraOS."
      />

      <Section id="guides">
        <SectionHeader eyebrow="Developer guides" title={<>Use the badge <em>from your computer.</em></>} />
        <div className="mt-10 grid gap-4 md:grid-cols-2">
          {guides.map((doc, i) => <DocCard key={doc.href} doc={doc} n={i + 1} />)}
        </div>
      </Section>

      <Section id="deep-dives">
        <SectionHeader eyebrow="Engineering deep dives" title={<>How the video <em>path works.</em></>} />
        <div className="mt-10 grid gap-4 md:grid-cols-2">
          {deep.map((doc, i) => <DocCard key={doc.href} doc={doc} n={guides.length + i + 1} />)}
        </div>
      </Section>

      <NextStep
        title={<>Recipes, <em>step by step.</em></>}
        body="Put your name, photos and colours on the badge, read its sensors, and ship your own updates."
        href="/hacks/"
        cta="Browse the hacks"
      />
    </>
  );
}
