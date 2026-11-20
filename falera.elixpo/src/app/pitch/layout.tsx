import type { Metadata } from "next";
import "./pitch.css";

// A private sales deck: kept out of search (noindex here, an
// X-Robots-Tag in public/_headers) and out of sitemap.ts.
export const metadata: Metadata = {
  title: "Sponsor deck",
  robots: {
    index: false,
    follow: false,
    nocache: true,
    googleBot: { index: false, follow: false, noimageindex: true },
  },
  alternates: { canonical: null },
};

export default function PitchLayout({ children }: { children: React.ReactNode }) {
  return children;
}
