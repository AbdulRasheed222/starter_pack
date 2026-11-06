import Link from "next/link";

import { LanguageSwitcher } from "@/components/I18n";
import { translator } from "@/lib/i18n";
import { currentLocale } from "@/lib/locale";

export default async function Landing() {
  const t = translator(await currentLocale());
  const features = [1, 2, 3] as const;
  return (
    <div className="landing">
      <header className="topbar">
        <span className="brand">{t("brand")}</span>
        <nav>
          <LanguageSwitcher />
          <Link href="/sign-in" className="button ghost">
            {t("landing.signIn")}
          </Link>
        </nav>
      </header>
      <main>
        <h1>{t("landing.title")}</h1>
        <p className="lead">{t("landing.subtitle")}</p>
        <Link href="/sign-up" className="button primary">
          {t("landing.getStarted")}
        </Link>
        <ul className="features">
          {features.map((n) => (
            <li key={n}>
              <h2>{t(`landing.f${n}.title`)}</h2>
              <p>{t(`landing.f${n}.text`)}</p>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
