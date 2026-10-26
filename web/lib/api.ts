// Client for the backend. Every call carries Clerk's session token, which the API checks
// against Clerk's keys and the caller's workspace memberships. Shapes mirror workspaces.py
// and notes.py.

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
export type Note = { id: string; title: string; body: string; created_at: string; updated_at: string };

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

    notes: (id: string) => json<Note[]>(call(getToken, `${ws(id)}/notes`)),
    createNote: (id: string, title: string, body: string) =>
      json<Note>(call(getToken, `${ws(id)}/notes`, send("POST", { title, body }))),
    updateNote: (id: string, noteId: string, patch: Partial<Pick<Note, "title" | "body">>) =>
      json<Note>(call(getToken, `${ws(id)}/notes/${noteId}`, send("PATCH", patch))),
    deleteNote: async (id: string, noteId: string) => {
      await call(getToken, `${ws(id)}/notes/${noteId}`, send("DELETE"));
    },
  };
};

export type Api = ReturnType<typeof api>;
