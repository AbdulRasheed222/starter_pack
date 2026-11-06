import "server-only";

import { cookies, headers } from "next/headers";

import { type Locale, LOCALE_COOKIE, fromAcceptLanguage, isLocale } from "@/lib/i18n";

/** The visitor's language: their choice in the switcher, else their browser's, else English. */
export async function currentLocale(): Promise<Locale> {
  const chosen = (await cookies()).get(LOCALE_COOKIE)?.value;
  if (isLocale(chosen)) return chosen;
  return fromAcceptLanguage((await headers()).get("accept-language"));
}
