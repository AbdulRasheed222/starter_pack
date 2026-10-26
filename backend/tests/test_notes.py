from tests.support import as_user, create_workspace, join


def test_members_share_a_workspaces_notes(client):
    workspace_id = create_workspace(client)
    join(client, workspace_id, "user_bob")
    notes = f"/workspaces/{workspace_id}/notes"

    created = client.post(notes, json={"title": "Plan", "body": "Ship"}, headers=as_user())
    assert created.status_code == 201
    note_id = created.json()["id"]

    as_bob = as_user("user_bob")
    assert [n["title"] for n in client.get(notes, headers=as_bob).json()] == ["Plan"]
    updated = client.patch(f"{notes}/{note_id}", json={"body": "Ship it"}, headers=as_bob).json()
    assert (updated["title"], updated["body"]) == ("Plan", "Ship it")
    assert client.delete(f"{notes}/{note_id}", headers=as_bob).status_code == 204
    assert client.get(f"{notes}/{note_id}", headers=as_bob).status_code == 404


def test_note_input_is_validated(client):
    workspace_id = create_workspace(client)
    notes = f"/workspaces/{workspace_id}/notes"
    assert client.post(notes, json={"title": ""}, headers=as_user()).status_code == 422
    assert client.post(notes, json={"title": "x" * 201}, headers=as_user()).status_code == 422
