import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { cookies } from "next/headers";
import "./globals.css";
import { LocaleSwitcher } from "@/components/LocaleSwitcher";
import type { Locale } from "@/lib/i18n";
import { t } from "@/lib/i18n";

export const metadata: Metadata = {
  title: "StorySmith AI x 剧匠AI",
  description:
    "AI-generated interactive animated short videos. Vote to shape the story. AI生成的互动动画短片，观众投票塑造故事。",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const cookieStore = cookies();
  const locale = (cookieStore.get("locale")?.value || "en") as Locale;

  return (
    <html lang={locale === "zh" ? "zh-CN" : "en"}>
      <body className="antialiased">
        {/* Navigation */}
        <nav className="fixed top-0 left-0 right-0 z-50 border-b border-white/[0.06] bg-[rgba(5,2,18,0.8)] backdrop-blur-xl">
          <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3 group">
              <Image
                src="/logo-icon.png"
                alt="StorySmith AI"
                width={32}
                height={32}
                className="rounded-lg"
              />
              <span className="font-bold text-lg tracking-tight group-hover:text-white transition-colors">
                {locale === "zh" ? (
                  <span className="text-white">剧匠AI</span>
                ) : (
                  <>
                    <span className="text-white">StorySmith</span>
                    <span className="text-white/50 ml-1">AI</span>
                  </>
                )}
              </span>
            </Link>
            <div className="flex items-center gap-2">
              <LocaleSwitcher currentLocale={locale} />
            </div>
          </div>
        </nav>

        {/* Main content with nav offset */}
        <div className="pt-16">
          {children}
        </div>

        {/* Footer */}
        <footer className="border-t border-white/[0.06] mt-20">
          <div className="max-w-6xl mx-auto px-6 py-10 flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="text-sm text-white/30">
              <span className="font-medium text-white/50">StorySmith AI x 剧匠AI</span>
              <span className="mx-2">·</span>
              {t(locale, "footer_powered")}
            </div>
            <div className="flex items-center gap-6 text-sm text-white/30">
              <Link href="/" className="hover:text-white/60 transition-colors">{t(locale, "nav_stories")}</Link>
              <Link href="/admin" className="hover:text-white/60 transition-colors">{t(locale, "nav_admin")}</Link>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
