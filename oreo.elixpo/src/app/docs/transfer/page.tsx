import { Send } from "lucide-react";
import RepoDoc from "@/components/RepoDoc";
import { pageMetadata } from "@/lib/seo";

// Rendered from docs/TRANSFER.md at build time; edit that file, not this page.

export const metadata = pageMetadata({
  title: "Transfer: files from a computer to the badge",
  description: "Send photos, videos and documents to the Oreo Badge over USB with oreo transfer and the six-character code the badge shows; how the code, the safety checks and the line protocol work.",
  path: "/docs/transfer/",
  keywords: ["Oreo Badge Transfer", "oreo transfer send", "USB file transfer MicroPython", "device code pairing"],
  type: "article",
});

export default function TransferDocsPage() {
  return (
    <RepoDoc
      file="docs/TRANSFER.md"
      chip="docs · Transfer"
      icon={Send}
      title="Transfer: files from a computer to the badge."
      lead="Open Transfer on the badge, run oreo send with your files, and type the six-character code only the badge shows. OreoOS keeps running the whole time."
      quickLinks={[
        { label: "Send files", href: "#send-files" },
        { label: "On the badge", href: "#on-the-badge" },
        { label: "Safety", href: "#safety" },
        { label: "The protocol", href: "#the-protocol" },
      ]}
      related={[
        { href: "/docs/cli/", title: "The oreo CLI", description: "Install oreo-cli; every option of oreo transfer and what is converted to what." },
        { href: "/docs/usb/", title: "Connecting the badge", description: "Which USB-C port, port names and permissions." },
      ]}
    />
  );
}
