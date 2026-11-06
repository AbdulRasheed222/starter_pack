import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <main className="auth">
      <SignIn fallbackRedirectUrl="/app" />
    </main>
  );
}
