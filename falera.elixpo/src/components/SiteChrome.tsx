"use client";

import { usePathname } from "next/navigation";

/* The pitch deck (/pitch/) is a set of fixed 1920x1080 slides meant to be
 * screenshotted, so the site's header and footer stay off those routes. */
export function isPitchPath(pathname: string | null): boolean {
  return !!pathname && pathname.startsWith("/pitch");
}

export default function SiteChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (isPitchPath(pathname)) return null;
  return <>{children}</>;
}
