"""Helpers for signing in as test users and setting up workspaces."""

import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

ISSUER = "https://clerk.example.test"
ORIGIN = "http://localhost:3000"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(user: str = "user_alice", key=KEY, email: str | None = "default", **claims) -> str:
    now = int(time.time())
    payload = {"iss": ISSUER, "sub": user, "azp": ORIGIN, "iat": now, "nbf": now, "exp": now + 60}
    if email == "default":
        email = f"{user.removeprefix('user_')}@example.com"
    if email is not None:
        payload["email"] = email
    payload.update(claims)
    return jwt.encode(payload, key, algorithm="RS256")


def as_user(user: str = "user_alice", **kwargs) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(user, **kwargs)}"}


def create_workspace(client: TestClient, user: str = "user_alice", name: str = "Acme") -> str:
    response = client.post("/workspaces", json={"name": name}, headers=as_user(user))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def join(client: TestClient, workspace_id: str, user: str, role: str = "member", by="user_alice"):
    """Invites `user` with `role` and accepts the invite as them."""
    email = f"{user.removeprefix('user_')}@example.com"
    response = client.post(
        f"/workspaces/{workspace_id}/invites",
        json={"email": email, "role": role},
        headers=as_user(by),
    )
    assert response.status_code == 201, response.text
    invite_token = response.json()["link"].rsplit("/", 1)[1]
    response = client.post("/invites/accept", json={"token": invite_token}, headers=as_user(user))
    assert response.status_code == 200, response.text
