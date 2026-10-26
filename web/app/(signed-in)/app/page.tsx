import { auth } from "@clerk/nextjs/server";

import Workspaces from "@/components/Workspaces";

export default async function WorkspacesPage() {
  await auth.protect();
  return <Workspaces />;
}
