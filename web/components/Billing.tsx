"use client";

import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { useI18n } from "@/components/I18n";
import { useWorkspace } from "@/components/Shell";
import { useLoad } from "@/components/hooks";
import type { Translate } from "@/lib/i18n";

const PLAN_NAMES = { free: "billing.plan.free", pro: "billing.plan.pro" } as const;

/** A plan's display name. Add a message key here when you add a plan in billing.py. */
export function planName(t: Translate, key: string): string {
  return key in PLAN_NAMES ? t(PLAN_NAMES[key as keyof typeof PLAN_NAMES]) : key;
}

/** The workspace's plan. Owners upgrade through Stripe Checkout and manage it in Stripe's
 *  customer portal; the plan here changes when Stripe's webhook reports it. */
export default function Billing() {
  const { t, locale } = useI18n();
  const { workspace, api } = useWorkspace();
  const params = useSearchParams();
  const { data, error } = useLoad(() => api.billing(workspace.id), [api, workspace.id]);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const money = useMemo(
    () => new Intl.NumberFormat(locale, { style: "currency", currency: "USD" }),
    [locale],
  );

  async function go(load: () => Promise<{ url: string }>) {
    setBusy(true);
    setProblem(null);
    try {
      window.location.assign((await load()).url);
    } catch (e) {
      setProblem((e as Error).message);
      setBusy(false);
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">{t("common.loading")}</p>;

  const subscribed = data.status !== null && data.status !== "canceled";
  return (
    <>
      <header className="page-head">
        <h1>{t("billing.title")}</h1>
      </header>
      {params.get("checkout") === "success" && (
        <p className="notice">{t("billing.thanks")}</p>
      )}
      {!data.enabled && <p className="notice">{t("billing.off")}</p>}
      {data.status === "past_due" && <p className="notice">{t("billing.pastDue")}</p>}
      {(problem || null) && <p className="error">{problem}</p>}

      <ul className="cards">
        {data.plans.map((plan) => {
          const current = plan.key === data.plan;
          return (
            <li key={plan.key} className="card">
              <h2>
                {planName(t, plan.key)}{" "}
                {current && <span className="badge">{t("billing.current")}</span>}
              </h2>
              <p className="muted">
                {t("billing.budget", { budget: money.format(plan.ai_monthly_budget_usd) })}
              </p>
              {data.can_manage && !current && plan.key !== "free" && !subscribed && (
                <button
                  className="button primary"
                  disabled={busy || !plan.available}
                  onClick={() => go(() => api.checkout(workspace.id, plan.key))}
                >
                  {t("billing.upgrade")}
                </button>
              )}
            </li>
          );
        })}
      </ul>

      {data.can_manage && subscribed && (
        <button
          className="button"
          disabled={busy}
          onClick={() => go(() => api.billingPortal(workspace.id))}
        >
          {t("billing.manage")}
        </button>
      )}
      {!data.can_manage && <p className="muted">{t("billing.ownersOnly")}</p>}
    </>
  );
}
