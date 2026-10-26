import { clerkMiddleware } from "@clerk/nextjs/server";

// Clerk runs on the signed-in pages only; the landing page never loads it. Each page checks
// sign-in itself (auth.protect), as Clerk recommends over path matching here.
export default clerkMiddleware({ signInUrl: "/sign-in", signUpUrl: "/sign-up" });

export const config = {
  matcher: ["/app/:path*", "/invite/:path*", "/sign-in/:path*", "/sign-up/:path*"],
};
