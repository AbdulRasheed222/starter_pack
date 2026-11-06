"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useMemo } from "react";

import {
  LOCALES,
  LOCALE_COOKIE,
  LOCALE_NAMES,
  type Locale,
  type Translate,
  translator,
} from "@/lib/i18n";

const I18nContext = createContext<{ locale: Locale; t: Translate } | null>(null);

export function I18nProvider({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  const value = useMemo(() => ({ locale, t: translator(locale) }), [locale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}

/** Saves the choice in a cookie and re-renders the page on the server in that language. */
export function LanguageSwitcher() {
  const { locale, t } = useI18n();
  const router = useRouter();
  return (
    <label className="language">
      <span className="sr-only">{t("language.label")}</span>
      <select
        value={locale}
        onChange={(event) => {
          document.cookie = `${LOCALE_COOKIE}=${event.target.value}; path=/; max-age=31536000; samesite=lax`;
          router.refresh();
        }}
      >
        {LOCALES.map((code) => (
          <option key={code} value={code} lang={code}>
            {LOCALE_NAMES[code]}
          </option>
        ))}
      </select>
    </label>
  );
}
