from app.config import get_settings
from tests.support import as_user, create_workspace, join


def test_creator_becomes_owner(client):
    workspace_id = create_workspace(client, name="  Acme  ")
    detail = client.get(f"/workspaces/{workspace_id}", headers=as_user()).json()
    assert detail["name"] == "Acme"
    assert detail["role"] == "owner"
    assert detail["members"] == 1
    me = client.get("/me", headers=as_user()).json()
    assert me["workspaces"] == [{"id": workspace_id, "name": "Acme", "role": "owner"}]


def test_owned_workspaces_are_limited(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_workspaces_per_user", 2)
    create_workspace(client, name="One")
    create_workspace(client, name="Two")
    response = client.post("/workspaces", json={"name": "Three"}, headers=as_user())
    assert response.status_code == 409


def test_roles_decide_who_can_rename_and_delete(client):
    workspace_id = create_workspace(client)
    join(client, workspace_id, "user_bob", "member")
    join(client, workspace_id, "user_carol", "admin")
    path = f"/workspaces/{workspace_id}"

    assert client.patch(path, json={"name": "X"}, headers=as_user("user_bob")).status_code == 403
    assert client.patch(path, json={"name": "Y"}, headers=as_user("user_carol")).status_code == 200
    assert client.delete(path, headers=as_user("user_carol")).status_code == 403
    assert client.delete(path, headers=as_user("user_alice")).status_code == 204
    assert client.get(path, headers=as_user("user_alice")).status_code == 404


def test_member_management_rules(client):
    workspace_id = create_workspace(client)
    join(client, workspace_id, "user_bob", "member")
    join(client, workspace_id, "user_carol", "admin")
    ids = {
        u: client.get("/me", headers=as_user(u)).json()["id"] for u in ("user_alice", "user_bob")
    }
    members = f"/workspaces/{workspace_id}/members"

    def set_role(target: str, role: str, by: str) -> int:
        path = f"{members}/{ids[target]}"
        return client.patch(path, json={"role": role}, headers=as_user(by)).status_code

    def remove(target: str, by: str) -> int:
        return client.delete(f"{members}/{ids[target]}", headers=as_user(by)).status_code

    listed = client.get(members, headers=as_user("user_bob")).json()
    assert [(m["email"], m["role"]) for m in listed] == [
        ("alice@example.com", "owner"),
        ("bob@example.com", "member"),
        ("carol@example.com", "admin"),
    ]
    # Members can't change roles; admins can, but not to or from owner.
    assert set_role("user_bob", "admin", by="user_bob") == 403
    assert set_role("user_bob", "admin", by="user_carol") == 200
    assert set_role("user_bob", "owner", by="user_carol") == 403
    assert set_role("user_alice", "member", by="user_carol") == 403
    # The last owner can't step down, leave or be removed.
    assert set_role("user_alice", "admin", by="user_alice") == 409
    assert remove("user_alice", by="user_alice") == 409
    # With a second owner, they can.
    assert set_role("user_bob", "owner", by="user_alice") == 200
    assert remove("user_alice", by="user_alice") == 204
    assert client.get(f"/workspaces/{workspace_id}", headers=as_user()).status_code == 404


def test_members_can_leave_but_not_remove_others(client):
    workspace_id = create_workspace(client)
    join(client, workspace_id, "user_bob")
    join(client, workspace_id, "user_dave")
    dave_id = client.get("/me", headers=as_user("user_dave")).json()["id"]
    bob_id = client.get("/me", headers=as_user("user_bob")).json()["id"]
    members = f"/workspaces/{workspace_id}/members"

    assert client.delete(f"{members}/{dave_id}", headers=as_user("user_bob")).status_code == 403
    assert client.delete(f"{members}/{bob_id}", headers=as_user("user_bob")).status_code == 204
    assert client.get("/me", headers=as_user("user_bob")).json()["workspaces"] == []


def test_deleting_a_workspace_deletes_its_data(client, session):
    from sqlalchemy import func, select

    from app.models import Membership, Note

    workspace_id = create_workspace(client)
    join(client, workspace_id, "user_bob")
    client.post(f"/workspaces/{workspace_id}/notes", json={"title": "Hi"}, headers=as_user())
    client.delete(f"/workspaces/{workspace_id}", headers=as_user())
    assert session.scalar(select(func.count()).select_from(Note)) == 0
    assert session.scalar(select(func.count()).select_from(Membership)) == 0
