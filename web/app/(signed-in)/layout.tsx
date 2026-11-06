import { arSA, trTR } from "@clerk/localizations";
import { ClerkProvider } from "@clerk/nextjs";

import { currentLocale } from "@/lib/locale";

// Clerk's own screens (sign-in, account menu) follow the chosen language too.
const CLERK_LOCALIZATIONS = { en: undefined, tr: trTR, ar: arSA };

export default async function SignedInLayout({ children }: { children: React.ReactNode }) {
  const locale = await currentLocale();
  return (
    <ClerkProvider
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      afterSignOutUrl="/"
      localization={CLERK_LOCALIZATIONS[locale]}
    >
      {children}
    </ClerkProvider>
  );
}
