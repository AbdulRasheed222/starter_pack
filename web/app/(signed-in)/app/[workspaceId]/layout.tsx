import { auth } from "@clerk/nextjs/server";

import Shell from "@/components/Shell";

export default async function WorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ workspaceId: string }>;
}) {
  await auth.protect();
  const { workspaceId } = await params;
  return <Shell workspaceId={workspaceId}>{children}</Shell>;
}
