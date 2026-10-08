import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Providers from "./providers";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "vietnamese"],
});

export const metadata: Metadata = {
  title: "VCuboidFIT — Demo UI",
  description: "Hệ thống lọc 5% frame hiếm từ dataset nuScenes",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col font-sans bg-[#F7F8FA] text-[#0F172A]">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

