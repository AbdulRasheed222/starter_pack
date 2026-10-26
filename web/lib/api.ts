// Client for the backend. Every call carries Clerk's session token, which the API checks
// against Clerk's keys and the caller's workspace memberships. Shapes mirror workspaces.py
// and notes.py, and the AI module's documents.py, ask.py and usage.py.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export type GetToken = () => Promise<string | null>;

export type Role = "member" | "admin" | "owner";
export const ROLES: Role[] = ["member", "admin", "owner"];

export function atLeast(role: Role, minimum: Role): boolean {
  return ROLES.indexOf(role) >= ROLES.indexOf(minimum);
}

export type WorkspaceSummary = { id: string; name: string; role: Role };
export type WorkspaceDetail = WorkspaceSummary & { created_at: string; members: number };
export type Me = {
  id: string;
  email: string | null;
  workspaces: WorkspaceSummary[];
  max_workspaces: number;
  is_operator: boolean;
};
export type Member = { user_id: string; email: string | null; role: Role; joined_at: string };
export type Invite = {
  id: string;
  email: string;
  role: Role;
  created_at: string;
  expires_at: string;
};
export type CreatedInvite = Invite & { link: string };
export type InvitePreview = {
  workspace_name: string;
  email: string;
  role: Role;
  expired: boolean;
  accepted: boolean;
};
// [module:notes]
export type Note = { id: string; title: string; body: string; created_at: string; updated_at: string };
// [/module:notes]

// [module:ai]
export type DocumentInfo = {
  id: string;
  title: string;
  filename: string;
  kind: string;
  status: "processing" | "ready" | "failed";
  error: string | null;
  pages: number;
  size_bytes: number;
  chunks: number;
  created_at: string;
};
export type UsageDay = { date: string; calls: number; cost_usd: number };
export type Usage = {
  month_start: string;
  spent_usd: number;
  budget_usd: number;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  by_model: Record<string, number>;
  days: UsageDay[];
};

// [/module:ai]
// [module:billing]
export type PlanInfo = {
  key: string;
  available: boolean;
  // [module:ai]
  ai_monthly_budget_usd: number;
  // [/module:ai]
};
export type Billing = {
  enabled: boolean;
  plan: string;
  status: string | null;
  can_manage: boolean;
  plans: PlanInfo[];
};
// [/module:billing]
export type AdminWorkspace = {
  id: string;
  name: string;
  created_at: string;
  members: number;
  // [module:billing]
  plan: string;
  subscription_status: string | null;
  // [/module:billing]
  // [module:ai]
  documents: number;
  spent_usd: number;
  budget_usd: number;
  budget_override_usd: number | null;
  // [/module:ai]
};

// [module:ai]
/** A passage the answer may cite, numbered from 1. */
export type Source = {
  n: number;
  document_id: string;
  title: string;
  page: number | null;
  heading: string | null;
  text: string;
};
export type AnswerPart = { text: string; cites: number[] };
export type AskDone = {
  answer: AnswerPart[];
  grounded: boolean;
  refused: boolean;
  truncated: boolean;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
};
export type Turn = { role: "user" | "assistant"; text: string };
export type AskEvent =
  | { event: "sources"; data: Source[] }
  | { event: "delta"; data: { text: string } }
  | { event: "done"; data: AskDone }
  | { event: "error"; data: { message: string } };

/** Reads a server-sent event stream, calling `onEvent` for each complete event. */
async function readEvents(response: Response, onEvent: (event: AskEvent) => void) {
  const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let name = "";
      let data = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event: ")) name = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (name && data) onEvent({ event: name, data: JSON.parse(data) } as AskEvent);
    }
  }
}

// [/module:ai]

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function errorFrom(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status}).`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
  } catch {
    // keep the generic message
  }
  return new ApiError(response.status, message);
}

async function call(getToken: GetToken, path: string, init: RequestInit = {}): Promise<Response> {
  const token = await getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) throw await errorFrom(response);
  return response;
}

const json = async <T>(response: Promise<Response>): Promise<T> => (await response).json();
const send = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = (getToken: GetToken) => {
  const ws = (id: string) => `/workspaces/${id}`;
  return {
    me: () => json<Me>(call(getToken, "/me")),

    createWorkspace: (name: string) =>
      json<WorkspaceDetail>(call(getToken, "/workspaces", send("POST", { name }))),
    workspace: (id: string) => json<WorkspaceDetail>(call(getToken, ws(id))),
    renameWorkspace: (id: string, name: string) =>
      json<WorkspaceDetail>(call(getToken, ws(id), send("PATCH", { name }))),
    deleteWorkspace: async (id: string) => {
      await call(getToken, ws(id), send("DELETE"));
    },

    members: (id: string) => json<Member[]>(call(getToken, `${ws(id)}/members`)),
    setRole: (id: string, userId: string, role: Role) =>
      json<Member>(call(getToken, `${ws(id)}/members/${userId}`, send("PATCH", { role }))),
    removeMember: async (id: string, userId: string) => {
      await call(getToken, `${ws(id)}/members/${userId}`, send("DELETE"));
    },

    invites: (id: string) => json<Invite[]>(call(getToken, `${ws(id)}/invites`)),
    invite: (id: string, email: string, role: Role) =>
      json<CreatedInvite>(call(getToken, `${ws(id)}/invites`, send("POST", { email, role }))),
    revokeInvite: async (id: string, inviteId: string) => {
      await call(getToken, `${ws(id)}/invites/${inviteId}`, send("DELETE"));
    },
    previewInvite: (token: string) =>
      json<InvitePreview>(call(getToken, "/invites/preview", send("POST", { token }))),
    acceptInvite: (token: string) =>
      json<WorkspaceSummary>(call(getToken, "/invites/accept", send("POST", { token }))),

    adminWorkspaces: () => json<AdminWorkspace[]>(call(getToken, "/admin/workspaces")),
    // [module:notes]

    notes: (id: string) => json<Note[]>(call(getToken, `${ws(id)}/notes`)),
    createNote: (id: string, title: string, body: string) =>
      json<Note>(call(getToken, `${ws(id)}/notes`, send("POST", { title, body }))),
    updateNote: (id: string, noteId: string, patch: Partial<Pick<Note, "title" | "body">>) =>
      json<Note>(call(getToken, `${ws(id)}/notes/${noteId}`, send("PATCH", patch))),
    deleteNote: async (id: string, noteId: string) => {
      await call(getToken, `${ws(id)}/notes/${noteId}`, send("DELETE"));
    },
    // [/module:notes]
    // [module:ai]

    documents: (id: string) => json<DocumentInfo[]>(call(getToken, `${ws(id)}/documents`)),
    uploadDocument: (id: string, file: File) => {
      const form = new FormData();
      form.append("file", file);
      return json<DocumentInfo>(
        call(getToken, `${ws(id)}/documents`, { method: "POST", body: form }),
      );
    },
    deleteDocument: async (id: string, documentId: string) => {
      await call(getToken, `${ws(id)}/documents/${documentId}`, send("DELETE"));
    },
    usage: (id: string) => json<Usage>(call(getToken, `${ws(id)}/usage`)),
    /** Streams an answer. Resolves when the stream ends; errors before it starts throw. */
    ask: async (
      id: string,
      question: string,
      history: Turn[],
      onEvent: (event: AskEvent) => void,
      signal?: AbortSignal,
    ) => {
      const response = await call(getToken, `${ws(id)}/ask`, {
        ...send("POST", { question, history }),
        signal,
      });
      await readEvents(response, onEvent);
    },
    setBudget: (workspaceId: string, budget: number | null) =>
      json<AdminWorkspace>(
        call(
          getToken,
          `/admin/workspaces/${workspaceId}`,
          send("PATCH", { ai_monthly_budget_usd: budget }),
        ),
      ),
    // [/module:ai]
    // [module:billing]

    billing: (id: string) => json<Billing>(call(getToken, `${ws(id)}/billing`)),
    checkout: (id: string, plan: string) =>
      json<{ url: string }>(call(getToken, `${ws(id)}/billing/checkout`, send("POST", { plan }))),
    billingPortal: (id: string) =>
      json<{ url: string }>(call(getToken, `${ws(id)}/billing/portal`, send("POST"))),
    // [/module:billing]
  };
};

export type Api = ReturnType<typeof api>;
