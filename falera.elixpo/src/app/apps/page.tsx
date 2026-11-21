import Link from "next/link";
import AppCard from "@/components/AppCard";
import { NextStep, PageHeader, Section, SectionHeader } from "@/components/ui";
import { PRELOADED, ALL_APPS, STORE } from "@/data/apps";
import { GITHUB } from "@/lib/links";

const Grid = ({ children }: { children: React.ReactNode }) => (
  <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
);

export default function AppsPage() {
  const more = ALL_APPS.filter((a) => !PRELOADED.find((p) => p.slug === a.slug));
  return (
    <>
      <PageHeader
        eyebrow={`Apps · ${ALL_APPS.length + STORE.length} and counting`}
        title={<>Everything that ships, <em>and everything that streams in.</em></>}
        lede="The preloaded set lands on the badge at flash time. The store pulls fresh apps from GitHub at runtime — no laptop, no recompile, no developer mode toggle."
      >
        <Link href="/docs/apps/" className="btn-primary">Read the app-building docs</Link>
        <a href={`${GITHUB}/tree/main/apps_market`} target="_blank" rel="noreferrer" className="btn-ghost">
          Browse the catalogue on GitHub
        </a>
      </PageHeader>

      <Section id="preloaded">
        <SectionHeader
          eyebrow="Preloaded"
          title={<>Built into <em>FaleraOS 2.0.</em></>}
          lede="Edit any of them locally."
        />
        <Grid>{PRELOADED.map((a) => <AppCard key={a.slug} app={a} />)}</Grid>
      </Section>

      <Section id="more">
        <SectionHeader
          eyebrow="More on the badge"
          title={<>Settings, tools and games, <em>one drawer-tap away.</em></>}
        />
        <Grid>{more.map((a) => <AppCard key={a.slug} app={a} />)}</Grid>
      </Section>

      <Section id="store">
        <SectionHeader
          eyebrow="From the App Store"
          title={<>Install, update or remove, <em>on the badge.</em></>}
          lede={<>These live in <code className="code">apps_market/</code> on the repo; the badge&apos;s App Store installs them.</>}
        />
        <Grid>{STORE.map((a) => <AppCard key={a.slug} app={a} />)}</Grid>
      </Section>

      <NextStep
        title={<>Want one of these <em>on your own badge?</em></>}
        body="Set up a badge in about fifteen minutes with a USB-C cable and a computer."
        href="/get-started/"
        cta="Get started"
      />
    </>
  );
}
