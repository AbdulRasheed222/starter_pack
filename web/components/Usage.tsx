"use client";

import { useMemo } from "react";

import { useI18n } from "@/components/I18n";
import { useWorkspace } from "@/components/Shell";
import { useLoad } from "@/components/hooks";

/** AI spending this month against the workspace's cap, and calls per day. */
export default function Usage() {
  const { t, locale } = useI18n();
  const { workspace, api } = useWorkspace();
  const { data, error } = useLoad(() => api.usage(workspace.id), [api, workspace.id]);
  const money = useMemo(
    () =>
      new Intl.NumberFormat(locale, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 2,
      }),
    [locale],
  );
  const number = useMemo(() => new Intl.NumberFormat(locale), [locale]);
  const day = useMemo(
    () => new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" }),
    [locale],
  );

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">{t("common.loading")}</p>;

  const share = data.budget_usd > 0 ? Math.min(data.spent_usd / data.budget_usd, 1) : 1;
  const most = Math.max(1, ...data.days.map((d) => d.calls));
  const width = 600;
  const height = 120;
  const slot = width / data.days.length;

  return (
    <>
      <header className="page-head">
        <h1>{t("usage.title")}</h1>
      </header>
      <p className="muted">{t("usage.intro")}</p>

      <div className="stats">
        <div className="stat">
          <span className="label">{t("usage.spent")}</span>
          <strong>{money.format(data.spent_usd)}</strong>
          <span className="muted small">
            {t("usage.ofBudget", { budget: money.format(data.budget_usd) })}
          </span>
          <div
            className="meter"
            role="meter"
            aria-label={t("usage.spent")}
            aria-valuemin={0}
            aria-valuemax={data.budget_usd}
            aria-valuenow={data.spent_usd}
          >
            <span style={{ inlineSize: `${share * 100}%` }} data-full={share >= 1} />
          </div>
        </div>
        <div className="stat">
          <span className="label">{t("usage.calls")}</span>
          <strong>{number.format(data.calls)}</strong>
        </div>
        <div className="stat">
          <span className="label">{t("usage.tokens")}</span>
          <strong>{number.format(data.input_tokens + data.output_tokens)}</strong>
          <span className="muted small">
            {t("usage.tokensSplit", {
              input: number.format(data.input_tokens),
              output: number.format(data.output_tokens),
            })}
          </span>
        </div>
      </div>
      {share >= 1 && <p className="notice">{t("usage.capped")}</p>}

      <section className="card">
        <h2>{t("usage.perDay")}</h2>
        <svg
          className="bars"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={t("usage.perDay")}
        >
          <line x1={0} x2={width} y1={height - 0.5} y2={height - 0.5} className="axis" />
          {data.days.map((d, i) => {
            const h = (d.calls / most) * (height - 8);
            return (
              <g key={d.date}>
                <rect x={i * slot} y={0} width={slot} height={height} className="hit">
                  <title>
                    {`${day.format(new Date(d.date))}: ${t("usage.callsCount", {
                      count: d.calls,
                    })}, ${money.format(d.cost_usd)}`}
                  </title>
                </rect>
                {d.calls > 0 && (
                  <rect x={i * slot + 2} y={height - h} width={slot - 4} height={h} rx={2} />
                )}
              </g>
            );
          })}
        </svg>
        <div className="row muted small">
          <span>{day.format(new Date(data.days[0].date))}</span>
          <span className="push">{day.format(new Date(data.days[data.days.length - 1].date))}</span>
        </div>
        <details>
          <summary className="small">{t("usage.table")}</summary>
          <table className="small">
            <tbody>
              {data.days
                .filter((d) => d.calls > 0)
                .map((d) => (
                  <tr key={d.date}>
                    <td>{day.format(new Date(d.date))}</td>
                    <td>{t("usage.callsCount", { count: d.calls })}</td>
                    <td>{money.format(d.cost_usd)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </details>
      </section>

      {Object.keys(data.by_model).length > 0 && (
        <section className="card">
          <h2>{t("usage.byModel")}</h2>
          <ul className="plain">
            {Object.entries(data.by_model).map(([model, cost]) => (
              <li key={model} className="row">
                <code>{model}</code>
                <span className="push">{money.format(cost)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
