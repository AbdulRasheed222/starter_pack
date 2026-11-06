"use client";

import { useState } from "react";

import { useI18n } from "@/components/I18n";
import { useWorkspace } from "@/components/Shell";
import { useFormatDate, useLoad } from "@/components/hooks";
import type { Note } from "@/lib/api";

/** The example feature: replace it with your product. */
export default function Notes() {
  const { t } = useI18n();
  const { workspace, api } = useWorkspace();
  const formatDate = useFormatDate();
  const { data: notes, error, reload } = useLoad(() => api.notes(workspace.id), [api, workspace.id]);
  const [editing, setEditing] = useState<Note | "new" | null>(null);

  return (
    <>
      <header className="page-head">
        <h1>{t("notes.title")}</h1>
        <button className="button primary" onClick={() => setEditing("new")}>
          {t("notes.new")}
        </button>
      </header>
      <p className="muted">{t("notes.intro")}</p>
      {error && <p className="error">{error}</p>}
      {editing && (
        <NoteEditor
          note={editing === "new" ? null : editing}
          onDone={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
      {notes && notes.length === 0 && !editing && <p className="muted">{t("notes.empty")}</p>}
      <ul className="cards">
        {notes?.map((note) => (
          <li key={note.id} className="card">
            <h2>{note.title}</h2>
            {note.body && <p className="body">{note.body}</p>}
            <footer>
              <span className="muted small">
                {t("notes.updated", { date: formatDate(note.updated_at) })}
              </span>
              <button className="link" onClick={() => setEditing(note)}>
                {t("common.edit")}
              </button>
            </footer>
          </li>
        ))}
      </ul>
    </>
  );
}

function NoteEditor({ note, onDone }: { note: Note | null; onDone: () => void }) {
  const { t } = useI18n();
  const { workspace, api } = useWorkspace();
  const [title, setTitle] = useState(note?.title ?? "");
  const [body, setBody] = useState(note?.body ?? "");
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <form
      className="card editor"
      onSubmit={(event) => {
        event.preventDefault();
        run(() =>
          note
            ? api.updateNote(workspace.id, note.id, { title, body })
            : api.createNote(workspace.id, title, body),
        );
      }}
    >
      <input
        required
        maxLength={200}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder={t("notes.titlePlaceholder")}
        aria-label={t("notes.titlePlaceholder")}
      />
      <textarea
        rows={4}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder={t("notes.bodyPlaceholder")}
        aria-label={t("notes.bodyPlaceholder")}
      />
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button className="button primary">{t("common.save")}</button>
        <button type="button" className="button" onClick={onDone}>
          {t("common.cancel")}
        </button>
        {note && (
          <button
            type="button"
            className="button danger push"
            onClick={() => run(() => api.deleteNote(workspace.id, note.id))}
          >
            {t("common.delete")}
          </button>
        )}
      </div>
    </form>
  );
}
