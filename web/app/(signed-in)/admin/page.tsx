import { auth } from "@clerk/nextjs/server";

import Admin from "@/components/Admin";

export default async function AdminPage() {
  await auth.protect();
  return <Admin />;
}
