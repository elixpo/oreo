import { Newspaper, BadgeCheck, BookOpen } from "lucide-react";
import { Reveal } from "@/components/MotionWrap";
import { COVERAGE, PUBLISHED, UPSTREAM, type PressItem } from "@/data/press";

const GROUPS = [
  { title: "Coverage", Icon: Newspaper, items: COVERAGE },
  { title: "Recognised upstream", Icon: BadgeCheck, items: UPSTREAM },
  { title: "Published", Icon: BookOpen, items: PUBLISHED },
];

function Item({ item }: { item: PressItem }) {
  return (
    <li>
      <a
        href={item.href}
        target="_blank"
        rel="noreferrer"
        className="group block rounded-md px-3 py-2.5 transition-colors hover:bg-bg-raised"
      >
        <span className="flex items-baseline justify-between gap-3">
          <span className="font-medium text-text group-hover:text-primary">{item.who}</span>
          {item.date ? (
            <span className="shrink-0 text-xs tabular-nums text-muted">{item.date}</span>
          ) : null}
        </span>
        <span className="mt-0.5 block text-sm leading-snug text-text-dim">{item.what}</span>
      </a>
    </li>
  );
}

/** "In the press": coverage, upstream recognition and publications, from
 *  src/data/press.ts. `compact` shows the coverage group only. */
export default function PressStrip({ compact = false }: { compact?: boolean }) {
  const groups = compact ? GROUPS.slice(0, 1) : GROUPS;
  return (
    <Reveal>
      <div>
        <h2 className="font-display text-2xl tracking-tight">In the press</h2>
        <p className="mt-2 text-text-dim">
          What others have written about FaleraOS and RV565, and where they've been accepted.
        </p>
        <div className={`mt-6 grid gap-4 ${compact ? "" : "lg:grid-cols-3"}`}>
          {groups.map((g) => (
            <div key={g.title} className="card-surface min-w-0 p-4">
              <p className="flex items-center gap-2 px-3 pb-1 text-xs uppercase tracking-widest text-muted">
                <g.Icon className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                {g.title}
              </p>
              <ul className={compact ? "grid gap-1 sm:grid-cols-2" : "grid gap-1"}>
                {g.items.map((item) => (
                  <Item key={item.href} item={item} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </Reveal>
  );
}
