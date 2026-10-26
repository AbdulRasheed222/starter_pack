"use client";

import { UserButton } from "@clerk/nextjs";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext } from "react";

import { LanguageSwitcher, useI18n } from "@/components/I18n";
import { useApi, useLoad } from "@/components/hooks";
import type { Api, Me, WorkspaceDetail } from "@/lib/api";

type WorkspaceContextValue = {
  workspace: WorkspaceDetail;
  me: Me;
  api: Api;
  /** Reloads the workspace and the sidebar after a change, such as a rename. */
  reload: () => void;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside Shell");
  return value;
}

/** The frame of every page inside a workspace: a side menu and the page. */
export default function Shell({
  workspaceId,
  children,
}: {
  workspaceId: string;
  children: React.ReactNode;
}) {
  const { t } = useI18n();
  const api = useApi();
  const router = useRouter();
  const pathname = usePathname();
  const { data, error, reload } = useLoad(
    () => Promise.all([api.workspace(workspaceId), api.me()]),
    [api, workspaceId],
  );

  if (error) {
    return (
      <main className="page">
        <p className="error">{error}</p>
        <Link href="/app" className="button">
          {t("nav.allWorkspaces")}
        </Link>
      </main>
    );
  }
  if (!data) return <main className="page muted">{t("common.loading")}</main>;
  const [workspace, me] = data;

  const base = `/app/${workspace.id}`;
  const links = [
    // [module:ai]
    { href: `${base}/ask`, label: t("nav.ask") },
    { href: `${base}/documents`, label: t("nav.documents") },
    // [/module:ai]
    // [module:notes]
    { href: base, label: t("nav.notes") },
    // [/module:notes]
    { href: `${base}/members`, label: t("nav.members") },
    // [module:ai]
    { href: `${base}/usage`, label: t("nav.usage") },
    // [/module:ai]
    // [module:billing]
    { href: `${base}/billing`, label: t("nav.billing") },
    // [/module:billing]
    { href: `${base}/settings`, label: t("nav.settings") },
  ];

  return (
    <WorkspaceContext.Provider value={{ workspace, me, api, reload }}>
      <div className="shell">
        <aside className="sidebar">
          <span className="brand">{t("brand")}</span>
          <select
            className="switcher"
            aria-label={t("nav.allWorkspaces")}
            value={workspace.id}
            onChange={(event) =>
              router.push(event.target.value ? `/app/${event.target.value}` : "/app")
            }
          >
            {me.workspaces.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
            <option value="">{t("nav.allWorkspaces")}</option>
          </select>
          <nav>
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={pathname === link.href ? "page" : undefined}
              >
                {link.label}
              </Link>
            ))}
          </nav>
          <div className="sidebar-foot">
            <LanguageSwitcher />
            <UserButton />
          </div>
        </aside>
        <main className="page">{children}</main>
      </div>
    </WorkspaceContext.Provider>
  );
}
