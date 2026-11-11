import { Terminal } from "lucide-react";
import RepoDoc from "@/components/RepoDoc";
import { pageMetadata } from "@/lib/seo";

// Rendered from docs/CLI.md at build time; edit that file, not this page.

export const metadata = pageMetadata({
  title: "oreo CLI: control the badge over USB",
  description: "Install oreo-cli and use the oreo command: the full-screen view, Transfer with the badge's code, files, apps, Wi-Fi, owner profile setup, OreoOS updates, doctor, exit codes and troubleshooting.",
  path: "/docs/cli/",
  keywords: ["oreo CLI", "oreo-cli", "Oreo Badge USB", "OreoOS update", "MicroPython badge CLI", "mpremote"],
  type: "article",
});

export default function CliDocsPage() {
  return (
    <RepoDoc
      file="docs/CLI.md"
      chip="docs · oreo CLI"
      icon={Terminal}
      title="The oreo command-line tool."
      lead="oreo-cli controls the badge from a computer over USB: status, the Transfer app, files, apps, Wi-Fi, your profile, logs, a MicroPython shell and OreoOS updates. It finds the badge by its USB ID, so you never guess a port name."
      quickLinks={[
        { label: "Install", href: "#install" },
        { label: "First run", href: "#first-run" },
        { label: "Full-screen view", href: "#interactive-ui" },
        { label: "Commands", href: "#commands" },
        { label: "Transfer", href: "#oreo-transfer-send-files-to-the-transfer-app" },
        { label: "Profile setup", href: "#oreo-setup-owner-profile" },
        { label: "Wi-Fi", href: "#wi-fi-setup" },
        { label: "Update", href: "#oreo-update-update-oreoos" },
        { label: "Exit status", href: "#exit-status" },
        { label: "Troubleshooting", href: "#troubleshooting" },
      ]}
      related={[
        { href: "/docs/usb/", title: "Connecting the badge", description: "Which USB-C port, port names, Linux permissions, and raw mpremote for advanced use." },
        { href: "/docs/transfer/", title: "The Transfer app", description: "Sending photos, videos and documents with the code the badge shows, and the protocol behind it." },
      ]}
    />
  );
}
