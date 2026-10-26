"use client";

import { UserButton } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { LanguageSwitcher, useI18n } from "@/components/I18n";
import { useApi, useLoad } from "@/components/hooks";

export default function Workspaces() {
  const { t } = useI18n();
  const api = useApi();
  const router = useRouter();
  const { data: me, error, reload } = useLoad(() => api.me(), [api]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setCreateError(null);
    try {
      const workspace = await api.createWorkspace(name);
      router.push(`/app/${workspace.id}`);
    } catch (e) {
      setCreateError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="landing">
      <header className="topbar">
        <span className="brand">{t("brand")}</span>
        <nav>
          <LanguageSwitcher />
          <UserButton />
        </nav>
      </header>
      <main className="narrow">
        <h1>{t("workspaces.title")}</h1>
        {error && (
          <p className="error">
            {error}{" "}
            <button className="link" onClick={reload}>
              {t("common.retry")}
            </button>
          </p>
        )}
        {!me && !error && <p className="muted">{t("common.loading")}</p>}
        {me && me.workspaces.length === 0 && <p className="muted">{t("workspaces.empty")}</p>}
        {me && me.workspaces.length > 0 && (
          <ul className="list">
            {me.workspaces.map((w) => (
              <li key={w.id}>
                <Link href={`/app/${w.id}`}>{w.name}</Link>
                <span className="badge">{t(`role.${w.role}`)}</span>
              </li>
            ))}
          </ul>
        )}
        {me && (
          <form className="row" onSubmit={create}>
            <input
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("workspaces.namePlaceholder")}
              aria-label={t("workspaces.namePlaceholder")}
            />
            <button className="button primary" disabled={busy}>
              {t("workspaces.create")}
            </button>
          </form>
        )}
        {createError && <p className="error">{createError}</p>}
        {me && <p className="muted small">{t("workspaces.limit", { max: me.max_workspaces })}</p>}
      </main>
    </div>
  );
}
