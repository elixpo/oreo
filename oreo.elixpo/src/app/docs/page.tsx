import Link from "next/link";
import { ArrowRight, BookOpen, Boxes, Code2, FileText, Send, Terminal, Usb } from "lucide-react";
import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: "Technical Documentation",
  description: "Developer guides and engineering deep dives for OreoOS and the Oreo Badge.",
  path: "/docs/",
  keywords: ["OreoOS documentation", "ESP32-S3 development", "MicroPython documentation"],
});

const docs = [
  {
    href: "/docs/cli/",
    title: "The oreo CLI",
    description: "Install oreo-cli, then control the badge over USB: the full-screen view, Transfer, files, apps, Wi-Fi, profile setup, updates and troubleshooting.",
    icon: Terminal,
    accent: "text-primary",
  },
  {
    href: "/docs/usb/",
    title: "Connecting the badge",
    description: "Which USB-C port, port names, Linux permissions, the CLI first, and raw mpremote for advanced use.",
    icon: Usb,
    accent: "text-gold",
  },
  {
    href: "/docs/transfer/",
    title: "The Transfer app",
    description: "Send photos, videos and documents with the code the badge shows; the safety checks and the protocol.",
    icon: Send,
    accent: "text-teal",
  },
  {
    href: "/docs/apps/",
    title: "Writing OreoOS apps",
    description: "App structure, lifecycle hooks, manifests, graphics, controls, and deployment.",
    icon: Code2,
    accent: "text-teal",
  },
  {
    href: "/docs/video-architecture/",
    title: "RV565 video architecture",
    description: "Independent RGB565 frames, firmware inflation, SPI2 GDMA stripes, and the measured path from 0.5 to 24 FPS.",
    icon: Boxes,
    accent: "text-primary",
  },
  {
    href: "/paper/",
    title: "RV565 research paper",
    description: "Preview the forthcoming paper, authors, measured results, and scope of the cross-layer video architecture.",
    icon: FileText,
    accent: "text-lilac",
  },
];

export default function DocsPage() {
  return (
    <div className="container-page py-16 pb-28">
      <span className="chip mb-6"><BookOpen className="h-3.5 w-3.5" /> OreoOS docs</span>
      <h1 className="max-w-3xl font-display text-4xl tracking-tight sm:text-5xl">
        Build on the badge. Understand the system.
      </h1>
      <p className="mt-5 max-w-2xl text-text-dim">
        Practical developer references and detailed accounts of the engineering decisions behind OreoOS.
      </p>

      <div className="mt-12 grid gap-5 md:grid-cols-2">
        {docs.map((doc) => (
          <Link key={doc.href} href={doc.href} className="card-surface group p-7 hover:border-primary/50">
            <doc.icon className={`h-6 w-6 ${doc.accent}`} />
            <h2 className="mt-5 font-display text-2xl">{doc.title}</h2>
            <p className="mt-3 leading-relaxed text-text-dim">{doc.description}</p>
            <span className="mt-6 inline-flex items-center gap-2 text-sm text-primary">
              Read documentation
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
