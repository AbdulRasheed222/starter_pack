import type { Metadata } from "next";

import { I18nProvider } from "@/components/I18n";
import { direction, translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = translator(await currentLocale());
  return { title: t("brand"), description: t("landing.subtitle") };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await currentLocale();
  return (
    <html lang={locale} dir={direction(locale)}>
      <body>
        <I18nProvider locale={locale}>{children}</I18nProvider>
      </body>
    </html>
  );
}
