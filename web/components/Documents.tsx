"use client";

import { useEffect, useState } from "react";

import { useI18n } from "@/components/I18n";
import { useWorkspace } from "@/components/Shell";
import { useFormatDate, useLoad } from "@/components/hooks";
import { atLeast } from "@/lib/api";

const ACCEPT = ".pdf,.docx,.md,.markdown,.txt";

/** The files the AI answers from. Admins upload and delete; everyone can see the list. */
export default function Documents() {
  const { t } = useI18n();
  const { workspace, api } = useWorkspace();
  const formatDate = useFormatDate();
  const { data, error, reload } = useLoad(() => api.documents(workspace.id), [api, workspace.id]);
  const [uploading, setUploading] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const canManage = atLeast(workspace.role, "admin");
  const processing = data?.some((d) => d.status === "processing") ?? false;

  // Uploads are processed in the background: check back until they are done.
  useEffect(() => {
    if (!processing) return;
    const timer = setInterval(reload, 3000);
    return () => clearInterval(timer);
  }, [processing, reload]);

  async function upload(files: FileList | null) {
    setProblem(null);
    for (const file of Array.from(files ?? [])) {
      setUploading(file.name);
      try {
        await api.uploadDocument(workspace.id, file);
      } catch (e) {
        setProblem(`${file.name}: ${(e as Error).message}`);
      }
    }
    setUploading(null);
    reload();
  }

  async function remove(id: string, title: string) {
    if (!window.confirm(t("documents.deleteConfirm", { title }))) return;
    try {
      await api.deleteDocument(workspace.id, id);
      reload();
    } catch (e) {
      setProblem((e as Error).message);
    }
  }

  return (
    <>
      <header className="page-head">
        <h1>{t("documents.title")}</h1>
        {canManage && (
          <label className="button primary">
            {uploading ? t("documents.uploading", { name: uploading }) : t("documents.upload")}
            <input
              type="file"
              className="sr-only"
              accept={ACCEPT}
              multiple
              disabled={uploading !== null}
              onChange={(e) => {
                upload(e.target.files);
                e.target.value = "";
              }}
            />
          </label>
        )}
      </header>
      <p className="muted">{t("documents.intro")}</p>
      {(error || problem) && <p className="error">{problem ?? error}</p>}
      {data && data.length === 0 && <p className="muted">{t("documents.empty")}</p>}
      {data && data.length > 0 && (
        <ul className="list">
          {data.map((d) => (
            <li key={d.id}>
              <span className="grow">
                <strong>
                  {d.title}{" "}
                  {d.status !== "ready" && (
                    <span className={d.status === "failed" ? "badge danger" : "badge"}>
                      {t(`documents.status.${d.status}`)}
                    </span>
                  )}
                </strong>
                {d.error && <span className="error small">{d.error}</span>}
                <span className="muted small">
                  {t("documents.meta", {
                    file: d.filename,
                    pages: d.pages,
                    passages: d.chunks,
                    date: formatDate(d.created_at),
                  })}
                </span>
              </span>
              {canManage && (
                <button className="link danger" onClick={() => remove(d.id, d.title)}>
                  {t("common.delete")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
