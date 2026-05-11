"use client";
// Copyright (c) 2026 Chong Kiat Lim. All rights reserved.
// Licensed under CC BY-NC 4.0. See LICENSE for details.

import { useState, useEffect } from "react";
import type { Locale } from "./i18n";

export function useLocale(): Locale {
  const [locale, setLocale] = useState<Locale>("en");

  useEffect(() => {
    const match = document.cookie.match(/(?:^|; )locale=([^;]*)/);
    setLocale((match?.[1] as Locale) || "en");
  }, []);

  // Listen for cookie changes (when LocaleSwitcher triggers router.refresh)
  useEffect(() => {
    const observer = new MutationObserver(() => {
      const match = document.cookie.match(/(?:^|; )locale=([^;]*)/);
      const newLocale = (match?.[1] as Locale) || "en";
      setLocale(newLocale);
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
    return () => observer.disconnect();
  }, []);

  return locale;
}
