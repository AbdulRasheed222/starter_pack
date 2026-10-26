"""Proves that no endpoint leaks one workspace's data to another.

The routes are read from the app itself, so a new endpoint is covered the moment it exists:

1. Every route under /workspaces/{workspace_id} must answer 404 to a signed-in user who is
   not a member, for every method, with real ids from the workspace filled in.
2. A member of workspace B who puts workspace A's row ids into B's URLs must also get a 404.
3. Every other route must be listed in UNSCOPED with a reason, so adding an unscoped endpoint
   is a decision someone has to write down.

When you add a route with a new path parameter, add how to fill it to `ids_for`.
"""

import re

import pytest

from app.api import app
from tests.support import as_user, create_workspace

UNSCOPED = {
    ("GET", "/healthz"): "health check, no data",
    ("GET", "/me"): "only the caller's own memberships",
    ("POST", "/workspaces"): "creates a new workspace owned by the caller",
    ("POST", "/invites/preview"): "needs the secret invite token",
    ("POST", "/invites/accept"): "needs the secret invite token, and the invited email",
}

PARAM = re.compile(r"{(\w+)}")


def routes():
    # Read from the OpenAPI schema: it lists every documented route, including those of
    # included routers, in the shape clients see.
    for path, operations in app.openapi()["paths"].items():
        for method in sorted(operations):
            yield method.upper(), path


SCOPED = [(m, p) for m, p in routes() if "{workspace_id}" in p]


def seed(client, user: str, name: str) -> dict[str, str]:
    """A workspace with one of everything, and the ids to fill its URLs with."""
    workspace_id = create_workspace(client, user, name)
    headers = as_user(user)
    note = client.post(
        f"/workspaces/{workspace_id}/notes", json={"title": f"{name} secret"}, headers=headers
    ).json()
    invite = client.post(
        f"/workspaces/{workspace_id}/invites",
        json={"email": f"guest-{name.lower()}@example.com"},
        headers=headers,
    ).json()
    me = client.get("/me", headers=headers).json()
    return {
        "workspace_id": workspace_id,
        "note_id": note["id"],
        "invite_id": invite["id"],
        "user_id": me["id"],
    }


def ids_for(path: str, ids: dict[str, str]) -> str:
    def fill(match: re.Match) -> str:
        name = match.group(1)
        assert name in ids, f"Teach test_tenant_isolation.py how to fill {{{name}}} in {path}"
        return ids[name]

    return PARAM.sub(fill, path)


@pytest.fixture
def two_workspaces(client):
    return seed(client, "user_alice", "Alpha"), seed(client, "user_bob", "Beta")


def example(schema: dict, components: dict):
    """A small valid value for a JSON schema, so requests get past body validation and reach
    the code that must refuse them."""
    if "$ref" in schema:
        return example(components[schema["$ref"].rsplit("/", 1)[1]], components)
    if "anyOf" in schema:
        return example(schema["anyOf"][0], components)
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object":
        return {
            name: example(prop, components)
            for name, prop in schema.get("properties", {}).items()
            if name in schema.get("required", [])
        }
    if kind == "array":
        return []
    if kind in ("integer", "number"):
        return schema.get("minimum", 1)
    if kind == "boolean":
        return False
    if schema.get("format") == "email":
        return "someone@example.com"
    return "x" * max(schema.get("minLength", 1), 1)


def body_for(method: str, path: str):
    spec = app.openapi()
    content = spec["paths"][path][method.lower()].get("requestBody", {}).get("content", {})
    schema = content.get("application/json", {}).get("schema")
    return example(schema, spec["components"]["schemas"]) if schema else None


def call(client, method: str, template: str, path: str, user: str):
    body = body_for(method, template)
    return client.request(method, path, json=body, headers=as_user(user))


def test_there_are_scoped_routes_to_check():
    # Guards against the checks below passing because they found nothing.
    assert len(SCOPED) >= 10


def test_every_route_is_scoped_or_listed():
    unlisted = [
        f"{m} {p}" for m, p in routes() if "{workspace_id}" not in p and (m, p) not in UNSCOPED
    ]
    assert unlisted == [], (
        "These routes are not under /workspaces/{workspace_id}. Scope them, or add them to "
        f"UNSCOPED with the reason they can't leak data: {unlisted}"
    )


@pytest.mark.parametrize(("method", "path"), SCOPED, ids=[f"{m} {p}" for m, p in SCOPED])
def test_outsiders_get_404(client, two_workspaces, method, path):
    alpha, _ = two_workspaces
    response = call(client, method, path, ids_for(path, alpha), "user_bob")
    assert response.status_code == 404, f"{method} {path} answered {response.status_code}"


@pytest.mark.parametrize(
    ("method", "path"),
    [(m, p) for m, p in SCOPED if len(PARAM.findall(p)) > 1],
    ids=[f"{m} {p}" for m, p in SCOPED if len(PARAM.findall(p)) > 1],
)
def test_other_workspaces_row_ids_get_404(client, two_workspaces, method, path):
    alpha, beta = two_workspaces
    # Bob's own workspace in the URL, Alice's row ids everywhere else.
    mixed = {**alpha, "workspace_id": beta["workspace_id"]}
    response = call(client, method, path, ids_for(path, mixed), "user_bob")
    assert response.status_code == 404, f"{method} {path} answered {response.status_code}"


def test_alphas_data_is_untouched(client, two_workspaces):
    """After every attack above, Alice still has exactly what she had."""
    alpha, _ = two_workspaces
    for method, path in SCOPED:
        call(client, method, path, ids_for(path, alpha), "user_bob")
    headers = as_user("user_alice")
    workspace = client.get(f"/workspaces/{alpha['workspace_id']}", headers=headers).json()
    assert (workspace["name"], workspace["members"]) == ("Alpha", 1)
    notes = client.get(f"/workspaces/{alpha['workspace_id']}/notes", headers=headers).json()
    assert [n["title"] for n in notes] == ["Alpha secret"]
