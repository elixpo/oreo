import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: "Oreo Badge Supporters",
  description: "The people funding the first Oreo badges: live progress of the community fundraiser and every supporter, thanked by name.",
  path: "/supporters/",
  keywords: ["Oreo badge supporters", "fund open hardware", "community-built hardware"],
});

export default function SupportersLayout({ children }: { children: React.ReactNode }) {
  return children;
}
