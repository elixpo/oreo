import { Heart } from "lucide-react";
import ContributeTracks from "@/components/ContributeTracks";
import RepoDoc from "@/components/RepoDoc";

// The guide below is CONTRIBUTING.md, rendered at build time (with its
// Mermaid diagrams drawn as static SVG, src/lib/diagrams.ts); edit that
// file, not this page.

export default function ContributePage() {
  return (
    <RepoDoc
      file="CONTRIBUTING.md"
      chip="made by humans, with humans"
      icon={Heart}
      title={
        <>
          Contribute to Oreo.{" "}
          <span className="bg-gradient-to-r from-primary via-gold to-lilac bg-clip-text text-transparent">
            Bring snacks.
          </span>
        </>
      }
      lead="OreoOS is open: the OS, its apps, the oreo CLI, the hardware and the docs. Most of it is tested on an ordinary computer, so you can start without a badge. Pick one of four paths; each opens its own issue form."
      quickLinks={[
        { label: "How it goes", href: "#how-a-contribution-goes" },
        { label: "Without a badge", href: "#start-without-a-badge" },
        { label: "With a badge", href: "#with-a-badge" },
        { label: "Checks", href: "#checks-before-a-pull-request" },
        { label: "GSoC 2027", href: "#google-summer-of-code-2027" },
      ]}
      bodyTitle="The contributing guide"
      related={[
        { href: "/docs/apps/", title: "Writing OreoOS apps", description: "The app layout, lifecycle, input, drawing and how to check an app." },
        { href: "/hacks/", title: "Badge hacks", description: "Step-by-step recipes, each one a Markdown file you can improve." },
      ]}
    >
      <ContributeTracks />
    </RepoDoc>
  );
}
