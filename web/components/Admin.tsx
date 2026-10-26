"use client";

import { UserButton } from "@clerk/nextjs";
import Link from "next/link";
import { useMemo, useState } from "react";

import { planName } from "@/components/Billing";
import { LanguageSwitcher, useI18n } from "@/components/I18n";
import { useApi, useFormatDate, useLoad } from "@/components/hooks";
import type { AdminWorkspace } from "@/lib/api";

/** For the people who run the product: every workspace, its plan and AI spending, and a
 *  budget override. The API answers 404 to anyone not in ADMIN_USER_IDS. */
export default function Admin() {
  const { t, locale } = useI18n();
  const api = useApi();
  const { data, error, setData } = useLoad(() => api.adminWorkspaces(), [api]);
  const formatDate = useFormatDate();
  const money = useMemo(
    () => new Intl.NumberFormat(locale, { style: "currency", currency: "USD" }),
    [locale],
  );

  function replace(row: AdminWorkspace) {
    setData((rows) => rows?.map((r) => (r.id === row.id ? row : r)) ?? null);
  }

  return (
    <div className="landing">
      <header className="topbar">
        <Link href="/app" className="brand">
          {t("brand")}
        </Link>
        <nav>
          <LanguageSwitcher />
          <UserButton />
        </nav>
      </header>
      <main>
        <h1>{t("admin.title")}</h1>
        {error && <p className="error">{error}</p>}
        {!data && !error && <p className="muted">{t("common.loading")}</p>}
        {data && (
          <div className="table-wrap">
            <table className="admin">
              <thead>
                <tr>
                  <th>{t("admin.workspace")}</th>
                  <th>{t("admin.plan")}</th>
                  <th>{t("admin.members")}</th>
                  <th>{t("admin.documents")}</th>
                  <th>{t("admin.spent")}</th>
                  <th>{t("admin.budget")}</th>
                </tr>
              </thead>
              <tbody>
                {data.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <strong>{row.name}</strong>
                      <div className="muted small">{formatDate(row.created_at)}</div>
                    </td>
                    <td>
                      {planName(t, row.plan)}
                      {row.subscription_status && (
                        <div className="muted small">{row.subscription_status}</div>
                      )}
                    </td>
                    <td>{row.members}</td>
                    <td>{row.documents}</td>
                    <td>{money.format(row.spent_usd)}</td>
                    <td>
                      <BudgetEditor row={row} onSaved={replace} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}

function BudgetEditor({
  row,
  onSaved,
}: {
  row: AdminWorkspace;
  onSaved: (row: AdminWorkspace) => void;
}) {
  const { t } = useI18n();
  const api = useApi();
  const [value, setValue] = useState(row.budget_override_usd?.toString() ?? "");
  const [problem, setProblem] = useState<string | null>(null);

  async function save(budget: number | null) {
    setProblem(null);
    try {
      const saved = await api.setBudget(row.id, budget);
      setValue(saved.budget_override_usd?.toString() ?? "");
      onSaved(saved);
    } catch (e) {
      setProblem((e as Error).message);
    }
  }

  return (
    <form
      className="row"
      onSubmit={(event) => {
        event.preventDefault();
        save(value.trim() === "" ? null : Number(value));
      }}
    >
      <input
        type="number"
        min={0}
        step="0.01"
        className="narrow-input"
        value={value}
        placeholder={row.budget_usd.toString()}
        aria-label={t("admin.budget")}
        onChange={(e) => setValue(e.target.value)}
      />
      <button className="button">{t("common.save")}</button>
      {row.budget_override_usd !== null && (
        <button type="button" className="link" onClick={() => save(null)}>
          {t("admin.usePlan")}
        </button>
      )}
      {problem && <span className="error small">{problem}</span>}
    </form>
  );
}
