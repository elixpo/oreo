/* The sponsor pitch deck: one fixed 1920x1080 canvas per slide.
 *
 * Every number here comes from a source in the repository or the
 * maintainer's sponsor notes; the comment above each slide names it.
 * Don't add a figure, supporter or partner that isn't in those sources.
 */

import type { CSSProperties, ReactNode } from "react";

const INK = "#142018";
const DIM = "#555C58";
const MUTED = "#5F6962";
const RED = "#C93A45";
const RED_DIM = "#A92F39";
const BORDER = "#D7DBD6";

/* ── Small parts ─────────────────────────────────────────────────────── */

/** Lumi's bow, used as a bullet and a divider. */
export function Bow({ size = 30, color = RED }: { size?: number; color?: string }) {
  return (
    <svg
      className="pd-bow"
      width={size}
      height={Math.round(size * 0.6)}
      viewBox="0 0 40 24"
      aria-hidden="true"
    >
      <path d="M18 12C12 3 3 1 2 7c-1 5-1 10 1 13 3 3 10-1 15-8z" fill={color} />
      <path d="M22 12c6-9 15-11 16-5 1 5 1 10-1 13-3 3-10-1-15-8z" fill={color} />
      <rect x="15.5" y="7" width="9" height="10" rx="3.5" fill={RED_DIM} />
    </svg>
  );
}

function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <div className="pd-eyebrow">
      <Bow size={34} />
      <span>{children}</span>
    </div>
  );
}

function Mark() {
  // eslint-disable-next-line @next/next/no-img-element
  return <img className="pd-mark" src="/pitch/lumi-mark.webp" alt="" />;
}

function Footer({ n, total }: { n: number; total: number }) {
  return (
    <div className="pd-footer">
      <span>
        <b>FaleraOS</b> · Elixpo
      </span>
      <span className="pd-num">
        {n} / {total}
      </span>
      <span>falera.elixpo.com</span>
    </div>
  );
}

function List({ items, style }: { items: ReactNode[]; style?: CSSProperties }) {
  return (
    <ul className="pd-list" style={style}>
      {items.map((it, i) => (
        <li key={i}>
          <Bow size={30} />
          {it}
        </li>
      ))}
    </ul>
  );
}

/** The canvas every slide is drawn on. */
export function SlideCanvas({
  n,
  total,
  mark = true,
  children,
}: {
  n: number;
  total: number;
  mark?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="pd-canvas">
      {mark && <Mark />}
      <div className="pd-body">{children}</div>
      <Footer n={n} total={total} />
    </div>
  );
}

/* ── Slides ──────────────────────────────────────────────────────────── */

type Slide = { title: string; mark?: boolean; body: ReactNode };

/* 1. Title. */
const title: Slide = {
  title: "FaleraOS",
  mark: false,
  body: (
    <>
      <Eyebrow>Sponsor deck · November 2026</Eyebrow>
      <h1
        className="pd-hero"
        style={{
          marginTop: 150,
          fontSize: 200,
          lineHeight: 0.95,
          fontWeight: 600,
          letterSpacing: "-0.05em",
        }}
      >
        Falera<span style={{ color: RED }}>OS</span>
      </h1>
      <p style={{ marginTop: 44, maxWidth: 1060, fontSize: 52, lineHeight: 1.22, letterSpacing: "-0.02em" }}>
        An open conference badge, <em style={{ fontFamily: "Georgia, serif" }}>and</em> the operating
        system that runs it.
      </p>
      <p className="pd-small" style={{ marginTop: 48, fontSize: 28 }}>
        By Elixpo · Certified open source hardware, OSHWA IN000107
      </p>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/pitch/lumi-badge.webp"
        alt="Lumi, the Falera panda, holding a badge"
        style={{ position: "absolute", right: 170, bottom: -100, width: 500 }}
      />
    </>
  ),
};

/* 2. The problem. Sources: EMAILS_BATCH2.md, the FOSS United "Why it
   matters" and NIDHI-PRAYAS "Problem" sections. */
const problem: Slide = {
  title: "The problem",
  body: (
    <>
      <Eyebrow>The problem</Eyebrow>
      <h2 className="pd-title">
        Conference badges are how many developers <em>first touch hardware.</em>
      </h2>
      <div style={{ marginTop: 84, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 56 }}>
        {[
          ["Closed", "Most badges can't be changed or rebuilt by the people who wear them."],
          ["Single-event", "Made for one conference, then put away."],
          ["Imported", "Hardware kits are often imported, expensive and single-purpose."],
        ].map(([h, p]) => (
          <div key={h}>
            <Bow size={40} />
            <div className="pd-h3" style={{ marginTop: 18 }}>{h}</div>
            <p className="pd-p">{p}</p>
          </div>
        ))}
      </div>
      <div className="pd-rule" style={{ marginTop: 80, maxWidth: 1648 }} />
      <p className="pd-lede" style={{ marginTop: 40, maxWidth: 1500 }}>
        Students rarely get a complete device (screen, input, sensors, radio, battery) that they can
        program in a beginner-friendly language and keep using.
      </p>
    </>
  ),
};

/* 3. What Falera is. Sources: README.md, LAUNCH_KIT.md one-line pitch. */
const what: Slide = {
  title: "What Falera is",
  body: (
    <>
      <Eyebrow>What Falera is</Eyebrow>
      <h2 className="pd-title">
        One badge. <em>One open OS.</em>
      </h2>
      <div style={{ marginTop: 72, width: 860 }}>
        <div className="pd-h3">The Falera Badge</div>
        <p className="pd-p">
          An ESP32-S3 badge with a 2.8″ touch screen, eight buttons, IR, a motion sensor, a speaker
          and microSD, on a board anyone can build.
        </p>
        <div className="pd-rule" style={{ margin: "44px 0" }} />
        <div className="pd-h3">FaleraOS</div>
        <p className="pd-p">
          A MicroPython operating system with a home screen, apps, an on-device App Store and
          over-the-air updates.
        </p>
        <p className="pd-small" style={{ marginTop: 56 }}>
          Hardware CERN-OHL-P-2.0 · Software MIT · Art CC-BY-4.0
        </p>
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/pitch/board-angle.webp"
        alt="Render of the Falera Badge PCB"
        style={{ position: "absolute", right: 120, top: 200, width: 720, height: 720, borderRadius: 32, objectFit: "cover" }}
      />
    </>
  ),
};

/* 4. Hardware. Sources: circuit/elixpo/README.md and BOM_COST.md
   (origin/pcb-bringup), README.md hardware table. */
const hardware: Slide = {
  title: "The hardware",
  body: (
    <>
      <Eyebrow>The hardware</Eyebrow>
      <h2 className="pd-title" style={{ maxWidth: 1180 }}>
        A complete device,
        <br />
        <em>₹4,171.70 in parts.</em>
      </h2>
      <div style={{ marginTop: 60, display: "grid", gridTemplateColumns: "600px 540px", columnGap: 36 }}>
        <List
          items={[
            "ESP32-S3: 16 MB flash, 8 MB PSRAM",
            "Wi-Fi and Bluetooth LE 5",
            "2.8″ 320×240 touch screen",
            "Eight buttons",
          ]}
        />
        <List
          items={[
            "IR send and receive, motion sensor",
            "Speaker amp and microSD",
            "LiPo, charged over USB-C",
            "Qwiic and a 4-GPIO header",
          ]}
        />
      </div>
      <div className="pd-card" style={{ marginTop: 56, width: 1120, padding: "30px 40px", display: "flex", alignItems: "center", gap: 40 }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/oshw_mark.png" alt="Certified open source hardware, OSHWA IN000107" style={{ height: 76 }} />
        <p className="pd-small" style={{ fontSize: 24 }}>
          4-layer board, 88 × 133.5 mm. Cost from the prices paid on 17 Nov 2026 for the first five
          boards; customs duty, tools and labour not included.
        </p>
      </div>
      <figure style={{ position: "absolute", right: 136, top: 210, width: 430, margin: 0 }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/pcb_back.jpg"
          alt="Back of the Falera Badge PCB"
          style={{ width: 430, height: 666, display: "block", borderRadius: 20, boxShadow: "0 20px 50px rgba(20,32,24,0.16)" }}
        />
        <figcaption className="pd-small" style={{ marginTop: 14, fontSize: 19 }}>
          The back of the first boards, made before the rename from Oreo.
        </figcaption>
      </figure>
    </>
  ),
};

/* 5. Software. Sources: README.md (apps, App Store, updates, CLI),
   apps_market/index.json (10 apps), PR #197 (audio, in review). */
const software: Slide = {
  title: "The software",
  body: (
    <>
      <Eyebrow>The software</Eyebrow>
      <h2 className="pd-title" style={{ maxWidth: 1000 }}>
        FaleraOS: apps, a store, <em>updates over the air.</em>
      </h2>
      <div style={{ marginTop: 60, width: 1000, display: "grid", gridTemplateColumns: "1fr 1fr", columnGap: 56, rowGap: 44 }}>
        {[
          ["Apps", "Ten built in, from Badge and Commits to Gallery and Reader. Each app is a small Python class."],
          ["App Store", "Ten more install on the badge: games, IR Quest, Weather and Lumi, the panda pet."],
          ["OTA updates", "Checked with SHA-256 and swapped in on the next boot, over verified HTTPS."],
          ["falera CLI", "A computer reaches the badge over USB: files, Wi-Fi, profile, apps, updates."],
        ].map(([h, p]) => (
          <div key={h}>
            <div className="pd-h3" style={{ fontSize: 34 }}>{h}</div>
            <p className="pd-p" style={{ fontSize: 26 }}>{p}</p>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 52, width: 1000, display: "flex", alignItems: "center", gap: 18 }}>
        <Bow size={34} />
        <p style={{ fontSize: 26, lineHeight: 1.4, color: INK }}>
          <b>In review for the PCB:</b> Radio, Podcasts, Music and Jamendo on the speaker.
        </p>
      </div>
      <figure style={{ position: "absolute", right: 136, top: 210, width: 560, margin: 0 }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/photo_portrait.jpg"
          alt="FaleraOS running on the breadboard badge"
          style={{ width: 560, height: 600, objectFit: "cover", borderRadius: 24 }}
        />
        <figcaption className="pd-small" style={{ marginTop: 14, fontSize: 20 }}>
          FaleraOS on the breadboard badge, which runs it today.
        </figcaption>
      </figure>
    </>
  ),
};

/* 6. Built so far. Sources: CHANGELOG.md (v1.4.19, v2.0.0), README.md
   press section (Adafruit, Espressif USB ID), cli/CHANGELOG.md (1.0.0),
   BOM_COST.md (orders of 17 Nov 2026), PR #180 (PCB support). */
const built: Slide = {
  title: "Built so far",
  body: (
    <>
      <Eyebrow>Built so far</Eyebrow>
      <h2 className="pd-title">
        Working software, <em>first boards ordered.</em>
      </h2>
      <div style={{ marginTop: 64, position: "relative", width: 1648 }}>
        {[
          ["16 May 2026", "OS release 1.4.19 on the breadboard badge"],
          ["4 Nov 2026", "Adafruit writes about the OS"],
          ["7 Nov 2026", "FaleraOS 2.0: the App Store and a new shell"],
          ["10 Nov 2026", "Espressif assigns the badge its USB ID, 303a:83ec"],
          ["11 Nov 2026", "falera CLI 1.0: the badge from a computer, over USB"],
          ["17 Nov 2026", "First five PCBs and their parts ordered"],
          ["Now", "PCB drivers and touch screen support in review"],
        ].map(([d, t], i, a) => (
          <div key={d} style={{ display: "grid", gridTemplateColumns: "300px 60px 1fr", alignItems: "center", height: 82 }}>
            <div className="pd-mono" style={{ fontSize: 24, color: i === a.length - 1 ? RED : MUTED, fontWeight: 700, letterSpacing: "0.04em" }}>
              {d}
            </div>
            <div style={{ position: "relative", height: 82, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <div style={{ position: "absolute", top: i === 0 ? 41 : 0, bottom: i === a.length - 1 ? 41 : 0, width: 2, background: BORDER }} />
              <div style={{ position: "relative", width: 18, height: 18, borderRadius: 9, background: i === a.length - 1 ? RED : "#FFFFFF", border: `3px solid ${i === a.length - 1 ? RED : INK}` }} />
            </div>
            <div style={{ fontSize: 31, color: INK, paddingLeft: 16 }}>{t}</div>
          </div>
        ))}
      </div>
    </>
  ),
};

/* 7. RV565. Sources: elixpo/rv565 README.md and docs/RESULTS_V8.md
   (badge measurements of 20 Nov 2026, format version 8 = RV565 3.0),
   falera README.md press section. */
const rv565: Slide = {
  title: "RV565",
  body: (
    <>
      <Eyebrow>Engineering depth</Eyebrow>
      <h2 className="pd-title" style={{ maxWidth: 1560, fontSize: 70 }}>
        RV565: an open video format, <em>born on the badge.</em>
      </h2>
      <div style={{ marginTop: 72, display: "grid", gridTemplateColumns: "780px 1fr", columnGap: 90 }}>
        <div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 24 }}>
            <span style={{ fontSize: 96, fontWeight: 600, letterSpacing: "-0.04em" }}>24 FPS</span>
          </div>
          <p className="pd-p" style={{ marginTop: 4 }}>with zero missed frames on the ESP32-S3.</p>
          <div style={{ marginTop: 44, display: "flex", alignItems: "baseline", gap: 18 }}>
            <span style={{ fontSize: 96, fontWeight: 600, letterSpacing: "-0.04em" }}>31.4</span>
            <span style={{ fontSize: 56, color: MUTED }}>→</span>
            <span style={{ fontSize: 96, fontWeight: 600, letterSpacing: "-0.04em", color: RED }}>6.3 ms</span>
          </div>
          <p className="pd-p" style={{ marginTop: 4 }}>
            Mean frame time of a UI animation on the Falera Badge: whole frames, then RV565 3.0’s
            region deltas.
          </p>
          <p className="pd-small" style={{ marginTop: 40 }}>
            Paper: arXiv 2610.35935 · artifact on Zenodo
          </p>
        </div>
        <div>
          <div className="pd-h3" style={{ fontSize: 30, color: MUTED, fontWeight: 700 }}>Where it ships</div>
          <List
            style={{ marginTop: 28 }}
            items={[
              "Arduino Library Manager",
              "ESP Component Registry",
              "PyPI",
              "Adafruit’s CircuitPython Community Bundle",
              "An example in the Arduino_GFX library",
              <>The Unix <span className="pd-mono">file</span> command recognises it</>,
            ]}
          />
        </div>
      </div>
    </>
  ),
};

/* 8. Recognition. Sources: README.md "In the press" and "Recognised
   upstream"; fundraiser API (payouts.elixpo.com, read 20 Nov 2026);
   FUNDRAISER_APPEAL.md (about ₹8,000 spent out of pocket). */
const recognition: Slide = {
  title: "Recognition",
  body: (
    <>
      <Eyebrow>Recognition so far</Eyebrow>
      <h2 className="pd-title">
        Recognised upstream, <em>covered in the press.</em>
      </h2>
      <div style={{ marginTop: 64, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 32, width: 1648 }}>
        {[
          ["Adafruit blog", "The OS on 4 Nov 2026, RV565 on 10 Nov 2026."],
          ["MA-NO and HardLabs", "Write-ups of the OS and of the open PCB."],
          ["Espressif", "Its own USB ID: 303a:83ec, “Elixpo Falera Badge”."],
          ["OSHWA", "Certified open source hardware, UID IN000107."],
          ["Unix file(1)", "Recognises RV565 videos, upstream since 12 Nov 2026."],
          ["Community fundraiser", "₹781 from 13 contributors so far, toward a first ₹8,000."],
        ].map(([h, p]) => (
          <div key={h} className="pd-card" style={{ padding: "36px 40px", height: 236 }}>
            <Bow size={34} />
            <div className="pd-h3" style={{ marginTop: 16, fontSize: 34 }}>{h}</div>
            <p className="pd-p" style={{ fontSize: 26, marginTop: 10 }}>{p}</p>
          </div>
        ))}
      </div>
      <p className="pd-small" style={{ marginTop: 32, fontSize: 22 }}>
        Fundraiser figures from payouts.elixpo.com/f/falera-badge on 20 Nov 2026. The first boards
        were paid for out of pocket, about ₹8,000.
      </p>
    </>
  ),
};

/* 9. Where it goes. Sources: EMAILS_BATCH2.md (FOSS United milestones,
   NIDHI note's projected cost at 100 units), SPONSORS.md (IndiaFOSS 2027,
   FOSSASIA Summit 2027 as events to approach), README.md (GSoC 2027:
   applying, not accepted). */
const next: Slide = {
  title: "Where it goes",
  body: (
    <>
      <Eyebrow>Where it goes</Eyebrow>
      <h2 className="pd-title">
        From five boards <em>to workshops.</em>
      </h2>
      <div style={{ marginTop: 64, display: "grid", gridTemplateColumns: "1000px 1fr", columnGap: 80 }}>
        <div>
          {[
            ["Month 1", "First PCB badges assembled and running FaleraOS; a build guide published."],
            ["Month 2", "Touch, audio and an app tutorial; 25 badges assembled by a fab house."],
            ["Month 3", "Board revision 2 with fixes from the first batch."],
            ["Month 4", "Two workshops: everyone builds a badge and publishes an app."],
          ].map(([m, t], i) => (
            <div key={m} style={{ display: "grid", gridTemplateColumns: "180px 1fr", alignItems: "baseline", padding: "26px 0", borderTop: i ? `1px solid ${BORDER}` : "none" }}>
              <div className="pd-mono" style={{ fontSize: 24, fontWeight: 700, color: RED, letterSpacing: "0.06em" }}>{m}</div>
              <div style={{ fontSize: 31, lineHeight: 1.35 }}>{t}</div>
            </div>
          ))}
        </div>
        <div style={{ paddingTop: 22 }}>
          <List
            items={[
              <>Events to approach: IndiaFOSS 2027 and FOSSASIA Summit 2027.</>,
              <>About ₹3,000 a badge in parts, projected at 100 units.</>,
              <>Elixpo is <b>applying</b> to be a Google Summer of Code 2027 mentoring organisation.</>,
            ]}
            style={{ fontSize: 28 }}
          />
        </div>
      </div>
    </>
  ),
};

/* 10. The ask. Source: EMAILS_BATCH2.md, FOSS United budget table
   (lines sum to ₹3,00,000). */
const ask: Slide = {
  title: "The ask",
  body: (
    <>
      <Eyebrow>The ask</Eyebrow>
      <h2 className="pd-title">
        <em>₹3,00,000</em> for four months.
      </h2>
      <div style={{ marginTop: 56, width: 1648 }}>
        {[
          ["Maintainer stipends", "2 maintainers × ₹15,000 × 4 months, paid by milestone", "₹1,20,000"],
          ["25 assembled badges", "Factory-assembled, for contributors, testers and workshops", "₹90,000"],
          ["Board revision 2", "Fabrication and assembly of the next prototypes", "₹30,000"],
          ["Test equipment", "Hot-air station, bench supply, logic analyser", "₹25,000"],
          ["Two workshops", "Badge-hacking kits, travel and documentation", "₹35,000"],
        ].map(([h, p, amt]) => (
          <div key={h} style={{ display: "grid", gridTemplateColumns: "520px 1fr 260px", alignItems: "center", height: 104, borderBottom: `1px solid ${BORDER}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
              <Bow size={30} />
              <span style={{ fontSize: 34, fontWeight: 700, letterSpacing: "-0.02em" }}>{h}</span>
            </div>
            <div style={{ fontSize: 27, color: DIM }}>{p}</div>
            <div className="pd-mono" style={{ fontSize: 34, textAlign: "right", fontWeight: 700 }}>{amt}</div>
          </div>
        ))}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 260px", alignItems: "center", height: 110 }}>
          <div style={{ fontSize: 34, fontWeight: 700, paddingLeft: 50 }}>Total</div>
          <div className="pd-mono" style={{ fontSize: 40, textAlign: "right", fontWeight: 700, color: RED }}>₹3,00,000</div>
        </div>
      </div>
    </>
  ),
};

/* 11. What sponsors get. Sources: SPONSORS.md "What to send each type"
   (logo on the silkscreen, README credit, build log, posts) and the
   "In return" lines of EMAILS_BATCH2.md drafts 1-4. SPONSORS.md defines
   no tiers, so none are shown. */
const returns: Slide = {
  title: "What sponsors get",
  body: (
    <>
      <Eyebrow>What sponsors get</Eyebrow>
      <h2 className="pd-title">
        Support in cash <em>or in kind.</em>
      </h2>
      <div style={{ marginTop: 68, display: "grid", gridTemplateColumns: "1000px 1fr", columnGap: 80, width: 1648 }}>
        <div>
          <div className="pd-h3" style={{ fontSize: 30, color: MUTED }}>In return</div>
          <List
            style={{ marginTop: 30 }}
            items={[
              "Your logo on the badge’s silkscreen, for board sponsors",
              "Credit in the repository and on falera.elixpo.com",
              "Credit on workshop materials and event pages",
              "Build logs, videos and posts that tag you",
              "The open KiCad project linked, so others order from you",
            ]}
          />
        </div>
        <div>
          <div className="pd-h3" style={{ fontSize: 30, color: MUTED }}>Ways to give</div>
          <List
            style={{ marginTop: 30 }}
            items={[
              "Funding against the budget",
              "PCB assembly for 10 to 25 badges",
              "Bare boards for revision 2",
              "ESP32-S3 modules for workshop badges",
              "A workshop or a badge at your event",
            ]}
          />
        </div>
      </div>
    </>
  ),
};

/* 12. Team. Sources: README.md "Built by the community" and "Recognition
   & programs"; EMAILS_BATCH2.md team section. No photos in the repo. */
const team: Slide = {
  title: "Team",
  body: (
    <>
      <Eyebrow>The team</Eyebrow>
      <h2 className="pd-title">
        Built in India, <em>in the open.</em>
      </h2>
      <div style={{ marginTop: 72, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 48, width: 1648 }}>
        {[
          ["AB", "Ayushman Bhattacharya", "Founder and lead, Elixpo", "Hardware, FaleraOS and RV565", "github.com/Circuit-Overtime"],
          ["AC", "Anwesha Chakraborty", "Core maintainer, Elixpo", "Co-author of RV565", "github.com/anwe-ch"],
        ].map(([ini, name, role, what, gh]) => (
          <div key={name} className="pd-card" style={{ padding: "44px 48px", display: "flex", gap: 40, alignItems: "center" }}>
            <div style={{ flex: "none", width: 132, height: 132, borderRadius: 66, background: "#FFFFFF", border: `2px solid ${INK}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 44, fontWeight: 700, letterSpacing: "-0.02em" }}>
              {ini}
            </div>
            <div>
              <div style={{ fontSize: 42, fontWeight: 700, letterSpacing: "-0.03em" }}>{name}</div>
              <div style={{ marginTop: 8, fontSize: 28, color: RED, fontWeight: 700 }}>{role}</div>
              <div style={{ marginTop: 8, fontSize: 28, color: DIM }}>{what}</div>
              <div className="pd-mono" style={{ marginTop: 12, fontSize: 21, color: MUTED }}>{gh}</div>
            </div>
          </div>
        ))}
      </div>
      <p className="pd-lede" style={{ marginTop: 64, maxWidth: 1560 }}>
        Elixpo is an open-source community of 45+ contributors. It has taken part in and been
        supported by GSSOC, Hacktoberfest, Pollinations.AI, MS Startup Foundations and OSCI.
      </p>
    </>
  ),
};

/* 13. Contact. Source: README.md closing line (hello@elixpo.com). */
const contact: Slide = {
  title: "Contact",
  mark: false,
  body: (
    <>
      <Eyebrow>Thank you</Eyebrow>
      <h2 className="pd-title" style={{ marginTop: 120, fontSize: 104, maxWidth: 1100 }}>
        Help build the <em>first Falera badges.</em>
      </h2>
      <div style={{ marginTop: 72, fontSize: 56, fontWeight: 600, letterSpacing: "-0.02em", color: RED }}>
        hello@elixpo.com
      </div>
      <div className="pd-mono" style={{ marginTop: 40, fontSize: 27, lineHeight: 1.8, color: DIM }}>
        <div>falera.elixpo.com</div>
        <div>github.com/elixpo/falera</div>
        <div>payouts.elixpo.com/f/falera-badge</div>
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/pitch/lumi-badge.webp"
        alt="Lumi, the Falera panda, holding a badge"
        style={{ position: "absolute", right: 190, bottom: -100, width: 520 }}
      />
    </>
  ),
};

export const SLIDES: Slide[] = [
  title,
  problem,
  what,
  hardware,
  software,
  built,
  rv565,
  recognition,
  next,
  ask,
  returns,
  team,
  contact,
];

export function SlideAt({ n }: { n: number }) {
  const s = SLIDES[n - 1];
  return (
    <SlideCanvas n={n} total={SLIDES.length} mark={s.mark !== false}>
      {s.body}
    </SlideCanvas>
  );
}
