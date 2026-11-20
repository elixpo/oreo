import Link from "next/link";
import { SLIDES, SlideAt } from "./deck";

export default function PitchIndex() {
  return (
    <div className="pd-index">
      <div style={{ maxWidth: 1560, margin: "0 auto" }}>
        <div className="pd-eyebrow" style={{ fontSize: 13 }}>Private · not indexed</div>
        <h1 style={{ marginTop: 12, fontSize: 40, fontWeight: 600, letterSpacing: "-0.04em" }}>
          FaleraOS sponsor deck
        </h1>
        <p style={{ marginTop: 8, fontSize: 17, color: "#555C58", maxWidth: 820, lineHeight: 1.5 }}>
          {SLIDES.length} slides, each a fixed 1920×1080 page for screenshots. Open one, then use the
          arrow keys. Add <code>?print=1</code> to turn off fit-to-window scaling;{" "}
          <code>scripts/pitch-pdf.py</code> renders them all into a PDF.
        </p>
      </div>
      <div className="pd-index-grid">
        {SLIDES.map((s, i) => (
          <Link key={i} href={`/pitch/${i + 1}/`} className="pd-thumb">
            <div className="pd-thumb-frame">
              <SlideAt n={i + 1} />
            </div>
            <div className="pd-thumb-label">
              {i + 1}. {s.title}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
