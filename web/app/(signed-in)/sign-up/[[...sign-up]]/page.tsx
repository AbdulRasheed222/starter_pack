import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <main className="auth">
      <SignUp fallbackRedirectUrl="/app" />
    </main>
  );
}
