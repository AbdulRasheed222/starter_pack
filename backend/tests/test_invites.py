from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.models import Invite
from tests.support import as_user, create_workspace, join


def invite(client, workspace_id, email="bob@example.com", role="member", by="user_alice"):
    return client.post(
        f"/workspaces/{workspace_id}/invites",
        json={"email": email, "role": role},
        headers=as_user(by),
    )


def token_of(response) -> str:
    return response.json()["link"].rsplit("/", 1)[1]


def accept(client, invite_token, user="user_bob", **kwargs):
    return client.post(
        "/invites/accept", json={"token": invite_token}, headers=as_user(user, **kwargs)
    )


def test_invite_link_adds_the_member_with_the_invited_role(client, session):
    workspace_id = create_workspace(client)
    response = invite(client, workspace_id, email="Bob@Example.com", role="admin")
    assert response.status_code == 201
    created = response.json()
    assert created["email"] == "bob@example.com"
    assert created["link"].startswith("http://localhost:3000/invite/")

    # Only a hash of the token is stored.
    stored = session.scalar(select(Invite))
    assert token_of(response) not in stored.token_hash

    preview = client.post(
        "/invites/preview", json={"token": token_of(response)}, headers=as_user("user_bob")
    ).json()
    assert preview == {
        "workspace_name": "Acme",
        "email": "bob@example.com",
        "role": "admin",
        "expired": False,
        "accepted": False,
    }
    joined = accept(client, token_of(response)).json()
    assert joined == {"id": workspace_id, "name": "Acme", "role": "admin"}
    # It works once.
    assert accept(client, token_of(response)).status_code == 410
    assert client.get(f"/workspaces/{workspace_id}/invites", headers=as_user()).json() == []


def test_invite_needs_the_invited_email(client, monkeypatch):
    workspace_id = create_workspace(client)
    invite_token = token_of(invite(client, workspace_id))
    assert accept(client, invite_token, user="user_mallory").status_code == 403
    assert accept(client, invite_token, user="user_bob", email=None).status_code == 400
    # Turning the check off makes the link alone enough.
    monkeypatch.setattr(get_settings(), "invite_requires_email_match", False)
    assert accept(client, invite_token, user="user_mallory").status_code == 200


def test_expired_and_unknown_invites_fail(client, session):
    workspace_id = create_workspace(client)
    invite_token = token_of(invite(client, workspace_id))
    stored = session.scalar(select(Invite))
    stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()
    assert accept(client, invite_token).status_code == 410
    assert accept(client, "x" * 43).status_code == 404


def test_only_admins_invite_and_only_owners_invite_owners(client):
    workspace_id = create_workspace(client)
    join(client, workspace_id, "user_bob", "member")
    join(client, workspace_id, "user_carol", "admin")
    assert invite(client, workspace_id, "d@example.com", by="user_bob").status_code == 403
    assert invite(client, workspace_id, "d@example.com", by="user_carol").status_code == 201
    assert (
        invite(client, workspace_id, "e@example.com", "owner", by="user_carol").status_code == 403
    )
    assert invite(client, workspace_id, "e@example.com", "owner").status_code == 201


def test_reinviting_replaces_the_old_link_and_members_cannot_be_reinvited(client):
    workspace_id = create_workspace(client)
    first = token_of(invite(client, workspace_id))
    second = token_of(invite(client, workspace_id))
    assert accept(client, first).status_code == 404
    assert accept(client, second).status_code == 200
    assert invite(client, workspace_id).status_code == 409


def test_revoked_invites_stop_working(client):
    workspace_id = create_workspace(client)
    response = invite(client, workspace_id)
    path = f"/workspaces/{workspace_id}/invites/{response.json()['id']}"
    assert client.delete(path, headers=as_user()).status_code == 204
    assert accept(client, token_of(response)).status_code == 404
