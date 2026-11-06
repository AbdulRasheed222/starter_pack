// Languages. Each one is a JSON file in messages/ with the same keys as en.json, which
// `npm run check:messages` enforces. To add one, copy en.json, translate it and list it here.

import ar from "@/messages/ar.json";
import en from "@/messages/en.json";
import tr from "@/messages/tr.json";

export const LOCALES = ["en", "tr", "ar"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE = "locale";

/** Written right to left. The layout uses logical CSS properties, so it mirrors by itself. */
const RTL: ReadonlySet<Locale> = new Set(["ar"]);

/** Each language's name in that language, for the switcher. */
export const LOCALE_NAMES: Record<Locale, string> = { en: "English", tr: "Türkçe", ar: "العربية" };

export type Messages = typeof en;
export type MessageKey = keyof Messages;

const MESSAGES: Record<Locale, Messages> = { en, tr, ar };

export function isLocale(value: string | undefined | null): value is Locale {
  return LOCALES.includes(value as Locale);
}

export function direction(locale: Locale): "ltr" | "rtl" {
  return RTL.has(locale) ? "rtl" : "ltr";
}

export function messages(locale: Locale): Messages {
  return MESSAGES[locale];
}

/** The first supported language in an Accept-Language header, e.g. "tr-TR,tr;q=0.9,en;q=0.8". */
export function fromAcceptLanguage(header: string | null): Locale {
  for (const part of (header ?? "").split(",")) {
    const code = part.split(";")[0].trim().slice(0, 2).toLowerCase();
    if (isLocale(code)) return code;
  }
  return DEFAULT_LOCALE;
}

/** A translator: t("members.count", { count: 3 }) fills {count} in the message. */
export function translator(locale: Locale) {
  const table = MESSAGES[locale];
  return (key: MessageKey, values?: Record<string, string | number>): string => {
    let text: string = table[key] ?? en[key] ?? key;
    for (const [name, value] of Object.entries(values ?? {})) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
    return text;
  };
}

export type Translate = ReturnType<typeof translator>;
