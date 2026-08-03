import type { Metadata } from "next";
import { Inter, Geist, Geist_Mono, Manrope } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/shared/providers";
import { cn } from "@/lib/utils";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});

const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" });

const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope" });

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "DashMet — Marketing Dashboard",
  description: "Multi-platform marketing metrics dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn("font-sans", geist.variable, geistMono.variable, manrope.variable)}
    >
      <body className={inter.className}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
