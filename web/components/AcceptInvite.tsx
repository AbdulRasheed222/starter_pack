"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useI18n } from "@/components/I18n";
import { useApi, useLoad } from "@/components/hooks";
import { ApiError } from "@/lib/api";

export default function AcceptInvite({ token }: { token: string }) {
  const { t } = useI18n();
  const api = useApi();
  const router = useRouter();
  const { data: invite, error } = useLoad(() => api.previewInvite(token), [api, token]);
  const [acceptError, setAcceptError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function accept() {
    setBusy(true);
    setAcceptError(null);
    try {
      const workspace = await api.acceptInvite(token);
      router.push(`/app/${workspace.id}`);
    } catch (e) {
      setAcceptError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      <section className="card narrow">
        <h1>{t("invite.title")}</h1>
        {error && <p className="error">{t("invite.invalid")}</p>}
        {!invite && !error && <p className="muted">{t("common.loading")}</p>}
        {invite && (
          <>
            <p>
              {t("invite.body", {
                workspace: invite.workspace_name,
                role: t(`role.${invite.role}`),
              })}
            </p>
            <p className="muted small">{t("invite.for", { email: invite.email })}</p>
            {invite.expired && <p className="error">{t("invite.expired")}</p>}
            {invite.accepted && <p className="error">{t("invite.used")}</p>}
            {!invite.expired && !invite.accepted && (
              <button className="button primary" disabled={busy} onClick={accept}>
                {t("invite.accept")}
              </button>
            )}
            {acceptError && <p className="error">{acceptError}</p>}
          </>
        )}
      </section>
    </main>
  );
}
