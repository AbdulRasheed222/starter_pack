"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useI18n } from "@/components/I18n";
import { useWorkspace } from "@/components/Shell";
import { atLeast } from "@/lib/api";

export default function Settings() {
  const { t } = useI18n();
  const { workspace, me, api, reload } = useWorkspace();
  const router = useRouter();
  const [name, setName] = useState(workspace.name);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isAdmin = atLeast(workspace.role, "admin");

  async function run(action: () => Promise<unknown>, done?: () => void) {
    setError(null);
    setMessage(null);
    try {
      await action();
      done?.();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      <header className="page-head">
        <h1>{t("settings.title")}</h1>
      </header>
      {error && <p className="error">{error}</p>}

      <section className="card">
        <form
          className="row"
          onSubmit={(event) => {
            event.preventDefault();
            run(
              () => api.renameWorkspace(workspace.id, name),
              () => {
                setMessage(t("settings.saved"));
                reload();
              },
            );
          }}
        >
          <label className="grow">
            <span className="label">{t("settings.name")}</span>
            <input
              required
              maxLength={100}
              value={name}
              disabled={!isAdmin}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          {isAdmin && <button className="button primary">{t("common.save")}</button>}
        </form>
        {message && <p className="muted small">{message}</p>}
      </section>

      <section className="card danger-zone">
        <h2>{t("settings.danger")}</h2>
        {workspace.role === "owner" ? (
          <>
            <p className="muted">{t("settings.deleteHelp")}</p>
            <button
              className="button danger"
              onClick={() => {
                const typed = prompt(t("settings.deleteConfirm", { name: workspace.name }));
                if (typed !== workspace.name) return;
                run(
                  () => api.deleteWorkspace(workspace.id),
                  () => router.push("/app"),
                );
              }}
            >
              {t("settings.delete")}
            </button>
          </>
        ) : (
          <button
            className="button danger"
            onClick={() => {
              if (!confirm(t("settings.leaveConfirm"))) return;
              run(
                () => api.removeMember(workspace.id, me.id),
                () => router.push("/app"),
              );
            }}
          >
            {t("settings.leave")}
          </button>
        )}
      </section>
    </>
  );
}
