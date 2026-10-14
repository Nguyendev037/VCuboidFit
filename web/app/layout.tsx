import { Suspense } from "react";
import type { Metadata } from "next";
import { Be_Vietnam_Pro, Inter, JetBrains_Mono, Newsreader, Space_Grotesk } from "next/font/google";
import "./globals.css";
import Providers from "./providers";
import PresentationMode from "@/components/PresentationMode";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "vietnamese"],
});

const spaceGrotesk = Space_Grotesk({ variable: "--font-space-grotesk", subsets: ["latin", "vietnamese"] });
const jetbrainsMono = JetBrains_Mono({ variable: "--font-jetbrains-mono", subsets: ["latin", "vietnamese"] });
const landingSans = Be_Vietnam_Pro({ variable: "--font-landing-sans", subsets: ["latin", "vietnamese"], weight: ["400", "500", "600"] });
const landingSerif = Newsreader({ variable: "--font-landing-serif", subsets: ["latin", "vietnamese"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "VCuboidFIT — Demo UI",
  description: "Hệ thống lọc 5% frame hiếm từ dataset nuScenes",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={`${inter.variable} ${spaceGrotesk.variable} ${jetbrainsMono.variable} ${landingSans.variable} ${landingSerif.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col font-sans bg-[#F7F8FA] text-[#0F172A]">
        <Providers><Suspense><PresentationMode /></Suspense>{children}</Providers>
      </body>
    </html>
  );
}

