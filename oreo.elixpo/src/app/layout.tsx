import type { Metadata } from "next";
import "./globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";

export const metadata: Metadata = {
  title: "Oreo — a Python OS for the Elixpo Badge",
  description:
    "Conference badge running OreoOS — Python-native on MicroPython. " +
    "App store, OTA updates, AirDrop-style WiFi transfer, IR quests.",
  metadataBase: new URL("https://oreo.pages.dev"),
  openGraph: {
    title: "Oreo Badge",
    description:
      "A Python OS for a pocket-sized open-hardware conference badge.",
    url: "https://oreo.pages.dev",
    siteName: "Oreo",
    type: "website",
  },
  themeColor: "#0F0C1C",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
