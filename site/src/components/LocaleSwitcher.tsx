"use client";
import { useRouter } from "next/navigation";
import type { Locale } from "@/lib/i18n";

export function LocaleSwitcher({ currentLocale }: { currentLocale: Locale }) {
  const router = useRouter();

  async function switchLocale(locale: Locale) {
    document.cookie = `locale=${locale};path=/;max-age=${60 * 60 * 24 * 365}`;
    router.refresh();
  }

  return (
    <div className="flex items-center gap-1 text-xs">
      <button
        onClick={() => switchLocale("en")}
        className={`px-2 py-1 rounded transition-colors ${
          currentLocale === "en"
            ? "text-white bg-white/10"
            : "text-white/40 hover:text-white/60"
        }`}
      >
        EN
      </button>
      <button
        onClick={() => switchLocale("zh")}
        className={`px-2 py-1 rounded transition-colors ${
          currentLocale === "zh"
            ? "text-white bg-white/10"
            : "text-white/40 hover:text-white/60"
        }`}
      >
        中文
      </button>
    </div>
  );
}
