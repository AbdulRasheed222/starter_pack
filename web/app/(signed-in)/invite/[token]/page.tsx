import { auth } from "@clerk/nextjs/server";

import AcceptInvite from "@/components/AcceptInvite";

export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  await auth.protect();
  const { token } = await params;
  return <AcceptInvite token={token} />;
}
