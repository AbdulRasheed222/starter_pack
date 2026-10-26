"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { useI18n } from "@/components/I18n";
import { useWorkspace } from "@/components/Shell";
import type { AskDone, Source, Turn } from "@/lib/api";

type Exchange = {
  question: string;
  sources: Source[];
  /** Text as it streams in; replaced by `done.answer` when the answer is complete. */
  draft: string;
  done: AskDone | null;
  error: string | null;
};

/** Plain text of an answer, sent back as history so follow-up questions make sense. */
function answerText(exchange: Exchange): string {
  return exchange.done?.answer.map((part) => part.text).join("") ?? "";
}

export default function Ask() {
  const { t } = useI18n();
  const { workspace, api } = useWorkspace();
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);

  function update(index: number, change: (exchange: Exchange) => Exchange) {
    setExchanges((all) => all.map((e, i) => (i === index ? change(e) : e)));
  }

  async function submit() {
    const text = question.trim();
    if (!text || busy) return;
    const history: Turn[] = exchanges
      .filter((e) => e.done && !e.done.refused)
      .slice(-4)
      .flatMap((e) => [
        { role: "user" as const, text: e.question },
        { role: "assistant" as const, text: answerText(e) || "-" },
      ]);
    const index = exchanges.length;
    setExchanges((all) => [
      ...all,
      { question: text, sources: [], draft: "", done: null, error: null },
    ]);
    setQuestion("");
    setBusy(true);
    abort.current = new AbortController();
    try {
      await api.ask(
        workspace.id,
        text,
        history,
        (event) => {
          if (event.event === "sources") update(index, (e) => ({ ...e, sources: event.data }));
          if (event.event === "delta")
            update(index, (e) => ({ ...e, draft: e.draft + event.data.text }));
          if (event.event === "done") update(index, (e) => ({ ...e, done: event.data }));
          if (event.event === "error")
            update(index, (e) => ({ ...e, error: event.data.message }));
        },
        abort.current.signal,
      );
    } catch (error) {
      if ((error as Error).name !== "AbortError")
        update(index, (e) => ({ ...e, error: (error as Error).message }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="page-head">
        <h1>{t("ask.title")}</h1>
      </header>
      <p className="muted">
        {t("ask.intro")}{" "}
        <Link href={`/app/${workspace.id}/documents`}>{t("nav.documents")}</Link>
      </p>
      <ol className="thread">
        {exchanges.map((exchange, index) => (
          <li key={index}>
            <p className="question" dir="auto">{exchange.question}</p>
            <Answer exchange={exchange} />
          </li>
        ))}
      </ol>
      <form
        className="ask-form"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <textarea
          rows={2}
          dir="auto"
          maxLength={2000}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={t("ask.placeholder")}
          aria-label={t("ask.placeholder")}
        />
        <div className="row">
          {busy ? (
            <button type="button" className="button" onClick={() => abort.current?.abort()}>
              {t("ask.stop")}
            </button>
          ) : (
            <button className="button primary" disabled={!question.trim()}>
              {t("ask.send")}
            </button>
          )}
          {exchanges.length > 0 && !busy && (
            <button type="button" className="button ghost" onClick={() => setExchanges([])}>
              {t("ask.clear")}
            </button>
          )}
        </div>
      </form>
    </>
  );
}

function Answer({ exchange }: { exchange: Exchange }) {
  const { t } = useI18n();
  const { done, error, draft, sources } = exchange;
  const [open, setOpen] = useState<number | null>(null);

  if (error) return <p className="error">{error}</p>;
  if (!done) return <p className="answer streaming" dir="auto">{draft || t("ask.thinking")}</p>;
  if (done.refused) return <p className="notice">{t("ask.refused")}</p>;

  const cited = sources.filter((s) => done.answer.some((part) => part.cites.includes(s.n)));
  const shown = cited.find((s) => s.n === open);
  return (
    <div>
      <p className="answer" dir="auto">
        {done.answer.map((part, i) => (
          <span key={i}>
            {part.text}
            {part.cites.map((n) => (
              <button
                key={n}
                className="cite"
                aria-label={t("ask.source", { n })}
                aria-expanded={open === n}
                onClick={() => setOpen(open === n ? null : n)}
              >
                {n}
              </button>
            ))}
          </span>
        ))}
      </p>
      {!done.grounded && <p className="badge">{t("ask.notGrounded")}</p>}
      {done.truncated && <p className="badge">{t("ask.truncated")}</p>}
      {shown && (
        <blockquote className="source">
          <strong>
            {shown.n}. {shown.title}
            {shown.page ? ` · ${t("ask.page", { page: shown.page })}` : ""}
          </strong>
          <p dir="auto">{shown.text}</p>
        </blockquote>
      )}
      {cited.length > 0 && (
        <p className="muted small">
          {t("ask.sources")}{" "}
          {cited.map((s) => `${s.n}. ${s.title}${s.page ? ` (${s.page})` : ""}`).join(" · ")}
        </p>
      )}
    </div>
  );
}
