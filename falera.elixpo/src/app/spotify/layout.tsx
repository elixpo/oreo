import { pageMetadata } from "@/lib/seo";

export const metadata = pageMetadata({
  title: "Link Spotify to your Falera Badge",
  description: "Enter the code shown by the Spotify app on your Falera Badge and sign in to Spotify, so the badge can show and control what you are playing.",
  path: "/spotify/",
  keywords: ["Falera badge Spotify", "FaleraOS Spotify app"],
});

export default function SpotifyLayout({ children }: { children: React.ReactNode }) {
  return children;
}
