"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useI18n } from "@/components/I18n";
import { useWorkspace } from "@/components/Shell";
import { useFormatDate, useLoad } from "@/components/hooks";
import { type CreatedInvite, ROLES, type Role, atLeast } from "@/lib/api";

export default function Members() {
  const { t } = useI18n();
  const { workspace, me, api, reload: reloadWorkspace } = useWorkspace();
  const router = useRouter();
  const formatDate = useFormatDate();
  const isAdmin = atLeast(workspace.role, "admin");
  const isOwner = workspace.role === "owner";

  const members = useLoad(() => api.members(workspace.id), [api, workspace.id]);
  const invites = useLoad(
    () => (isAdmin ? api.invites(workspace.id) : Promise.resolve([])),
    [api, workspace.id, isAdmin],
  );
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      members.reload();
      invites.reload();
      reloadWorkspace();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  // Owners can grant any role; admins can't make or unmake owners.
  const assignable = (current: Role): Role[] =>
    isOwner ? ROLES : current === "owner" ? [] : ROLES.filter((r) => r !== "owner");

  return (
    <>
      <header className="page-head">
        <h1>{t("members.title")}</h1>
        <span className="muted">{t("members.count", { count: workspace.members })}</span>
      </header>
      {(error || members.error) && <p className="error">{error ?? members.error}</p>}
      <ul className="list">
        {members.data?.map((m) => {
          const self = m.user_id === me.id;
          const options = assignable(m.role);
          return (
            <li key={m.user_id}>
              <span>
                {m.email ?? m.user_id}
                {self && <span className="muted"> ({t("members.you")})</span>}
              </span>
              <span className="row push">
                {isAdmin && options.length > 0 ? (
                  <select
                    value={m.role}
                    aria-label={m.email ?? m.user_id}
                    onChange={(e) =>
                      run(() => api.setRole(workspace.id, m.user_id, e.target.value as Role))
                    }
                  >
                    {options.map((r) => (
                      <option key={r} value={r}>
                        {t(`role.${r}`)}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span className="badge">{t(`role.${m.role}`)}</span>
                )}
                {self ? (
                  <button
                    className="link danger"
                    onClick={() => {
                      if (!confirm(t("settings.leaveConfirm"))) return;
                      run(async () => {
                        await api.removeMember(workspace.id, m.user_id);
                        router.push("/app");
                      });
                    }}
                  >
                    {t("members.leave")}
                  </button>
                ) : (
                  isAdmin &&
                  options.length > 0 && (
                    <button
                      className="link danger"
                      onClick={() => {
                        if (!confirm(t("members.removeConfirm", { email: m.email ?? "" }))) return;
                        run(() => api.removeMember(workspace.id, m.user_id));
                      }}
                    >
                      {t("members.remove")}
                    </button>
                  )
                )}
              </span>
            </li>
          );
        })}
      </ul>

      {isAdmin && (
        <>
          <InviteForm canInviteOwner={isOwner} onCreated={invites.reload} />
          <h2>{t("invites.pending")}</h2>
          {invites.data?.length === 0 && <p className="muted">{t("invites.none")}</p>}
          <ul className="list">
            {invites.data?.map((invite) => (
              <li key={invite.id}>
                <span>
                  {invite.email} <span className="badge">{t(`role.${invite.role}`)}</span>
                </span>
                <span className="row push">
                  <span className="muted small">
                    {t("invites.expires", { date: formatDate(invite.expires_at) })}
                  </span>
                  <button
                    className="link danger"
                    onClick={() => run(() => api.revokeInvite(workspace.id, invite.id))}
                  >
                    {t("invites.revoke")}
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

function InviteForm({
  canInviteOwner,
  onCreated,
}: {
  canInviteOwner: boolean;
  onCreated: () => void;
}) {
  const { t } = useI18n();
  const { workspace, api } = useWorkspace();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [created, setCreated] = useState<CreatedInvite | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setCopied(false);
    try {
      setCreated(await api.invite(workspace.id, email, role));
      setEmail("");
      onCreated();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="card">
      <h2>{t("invites.title")}</h2>
      <form className="row" onSubmit={submit}>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t("invites.email")}
          aria-label={t("invites.email")}
        />
        <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {ROLES.filter((r) => canInviteOwner || r !== "owner").map((r) => (
            <option key={r} value={r}>
              {t(`role.${r}`)}
            </option>
          ))}
        </select>
        <button className="button primary">{t("invites.send")}</button>
      </form>
      {error && <p className="error">{error}</p>}
      {created && (
        <div className="notice">
          <p>{t("invites.created", { email: created.email })}</p>
          <div className="row">
            {/* Links stay left to right inside right-to-left pages. */}
            <code dir="ltr">{created.link}</code>
            <button
              className="button"
              onClick={async () => {
                await navigator.clipboard.writeText(created.link);
                setCopied(true);
              }}
            >
              {copied ? t("invites.copied") : t("invites.copy")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
