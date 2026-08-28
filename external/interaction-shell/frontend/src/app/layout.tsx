import type { Metadata } from "next";
import "@fontsource-variable/ibm-plex-sans";
import "@fontsource-variable/jetbrains-mono";
import "@radix-ui/themes/styles.css";
import "./globals.css";
import "./collaboration.css";

export const metadata: Metadata = {
  title: "Affordance",
  description: "GUI Agent interaction, live surface, and benchmark Labs",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
