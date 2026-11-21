import Link from "next/link";
import type { ReactNode } from "react";

/* The site's shared components. Server components, no client JS.
 *
 *   <Section>        one band of a page: container + vertical rhythm
 *   <SectionHeader>  eyebrow (with Lumi's bow) + title + lede
 *   <PageHeader>     the same, as the page's h1, with room for actions
 *   <Card>           white card, 1px border, no shadow (link or block)
 *   <Stat>           a red number or name with a short label
 *   <Onward>         the one link at the end of a section
 *   <NextStep>       the card at the end of a page that points onward
 *   <Bow>            Lumi's bow, as an eyebrow mark or bullet
 *
 * Classes behind them (container-page, section, eyebrow, card, btn-*)
 * live in globals.css. */

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

const isExternal = (href: string) => /^https?:|^mailto:/.test(href);

/** A link that opens external URLs in a new tab and uses next/link inside. */
export function SmartLink({
  href, className, children, ...rest
}: { href: string; className?: string; children: ReactNode; "aria-label"?: string }) {
  if (isExternal(href)) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className={className} {...rest}>
        {children}
      </a>
    );
  }
  return <Link href={href} className={className} {...rest}>{children}</Link>;
}

/** Lumi's bow (pitch-deck/assets/bow.svg), inline so it costs no request. */
export function Bow({ className = "h-3 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 24" className={cx("shrink-0", className)} aria-hidden="true" focusable="false">
      <path d="M18 12C12 3 3 1 2 7c-1 5-1 10 1 13 3 3 10-1 15-8z" fill="#C93A45" />
      <path d="M22 12c6-9 15-11 16-5 1 5 1 10-1 13-3 3-10-1-15-8z" fill="#C93A45" />
      <rect x="15.5" y="7" width="9" height="10" rx="3.5" fill="#A92F39" />
    </svg>
  );
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cx("eyebrow flex items-center gap-2.5", className)}>
      <Bow />
      <span>{children}</span>
    </p>
  );
}

/** One band of a page. `fill` gives it the light grey-green fill. */
export function Section({
  id, fill = false, tight = false, className, children, label,
}: {
  id?: string;
  fill?: boolean;
  /** Less vertical space, for a strip such as a stat row. */
  tight?: boolean;
  className?: string;
  children: ReactNode;
  /** aria-label, when the section has no visible heading. */
  label?: string;
}) {
  return (
    <section id={id} aria-label={label} className={cx("section", tight && "section-tight", fill && "section-fill", className)}>
      <div className="container-page">{children}</div>
    </section>
  );
}

/** Eyebrow + title + lede. Two columns from lg when `aside` is given. */
export function SectionHeader({
  eyebrow, title, lede, as: Tag = "h2", className, children,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  lede?: ReactNode;
  as?: "h1" | "h2";
  className?: string;
  /** Actions or extra content under the lede. */
  children?: ReactNode;
}) {
  return (
    <header className={cx("max-w-3xl", className)}>
      {eyebrow && <Eyebrow className="mb-5">{eyebrow}</Eyebrow>}
      <Tag className={Tag === "h1" ? "h-display" : "h-title"}>{title}</Tag>
      {lede && <div className="lede mt-5 max-w-prose-site">{lede}</div>}
      {children}
    </header>
  );
}

/** The top of every page: a section holding the h1. */
export function PageHeader({
  eyebrow, title, lede, children, aside, className,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  lede?: ReactNode;
  /** Actions under the lede (buttons, chips). */
  children?: ReactNode;
  /** Optional right column from lg (an image or a status card). */
  aside?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("border-b border-border", className)}>
      <div className="container-page page-top pb-12 sm:pb-16">
        <div className={aside ? "grid items-start gap-10 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-center lg:gap-16" : undefined}>
          <SectionHeader as="h1" eyebrow={eyebrow} title={title} lede={lede}>
            {children && <div className="mt-8 flex flex-wrap items-center gap-3">{children}</div>}
          </SectionHeader>
          {aside}
        </div>
      </div>
    </div>
  );
}

/** White card with a 1px border. With `href` the whole card is a link. */
export function Card({
  href, className, children, fill = false, "aria-label": ariaLabel,
}: {
  href?: string;
  className?: string;
  children: ReactNode;
  fill?: boolean;
  "aria-label"?: string;
}) {
  if (href) {
    return (
      <SmartLink href={href} aria-label={ariaLabel} className={cx("card-link group block min-w-0", className)}>
        {children}
      </SmartLink>
    );
  }
  return <div className={cx(fill ? "card-fill" : "card", className)}>{children}</div>;
}

/** A red value with a short label, as in the deck's number cards. */
export function Stat({
  value, label, href, className,
}: { value: ReactNode; label: ReactNode; href?: string; className?: string }) {
  const body = (
    <>
      <span className="block font-display text-[1.5rem] font-bold leading-none tracking-[-0.03em] text-primary tabular-nums sm:text-[2rem]">
        {value}
      </span>
      <span className="mt-3 block text-sm leading-snug text-text-dim">{label}</span>
    </>
  );
  if (href) {
    return (
      <SmartLink href={href} className={cx("card-link block p-5 sm:p-6", className)}>
        {body}
      </SmartLink>
    );
  }
  return <div className={cx("card p-5 sm:p-6", className)}>{body}</div>;
}

/** A spec or fact: grey mono key, ink value. */
export function Fact({ k, children, className }: { k: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cx("card p-5", className)}>
      <p className="label">{k}</p>
      <p className="mt-2 text-[0.95rem] leading-snug text-text">{children}</p>
    </div>
  );
}

/** The one link at the end of a section. */
export function Onward({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  return (
    <p className={cx("mt-10", className)}>
      <SmartLink href={href} className="link-onward">
        {children} <span aria-hidden="true">→</span>
      </SmartLink>
    </p>
  );
}

/** Bow-bulleted list (the deck's `.list`). */
export function BowList({ items, className }: { items: ReactNode[]; className?: string }) {
  return (
    <ul className={cx("space-y-3", className)}>
      {items.map((item, i) => (
        <li key={i} className="flex gap-3 text-[0.95rem] leading-relaxed text-text-body">
          <Bow className="mt-[0.4rem] h-2.5 w-4" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

/** The end of a page: where to go next. */
export function NextStep({
  eyebrow = "Next", title, body, href, cta,
}: { eyebrow?: string; title: ReactNode; body: ReactNode; href: string; cta: string }) {
  return (
    <Section label="Next step" tight>
      <SmartLink
        href={href}
        className="card-link group flex flex-col gap-6 p-6 sm:p-8 md:flex-row md:items-center md:justify-between"
      >
        <div className="max-w-2xl">
          <p className="eyebrow">{eyebrow}</p>
          <p className="mt-3 font-display text-2xl leading-tight text-text sm:text-[1.75rem]">{title}</p>
          <p className="mt-2 text-text-dim">{body}</p>
        </div>
        <span className="link-onward shrink-0 group-hover:underline">
          {cta} <span aria-hidden="true">→</span>
        </span>
      </SmartLink>
    </Section>
  );
}

export { cx };
