from cryptography.hazmat.primitives.asymmetric import rsa

from tests.support import as_user, token

OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_health_needs_no_sign_in(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_first_request_creates_the_user_with_their_email(client):
    me = client.get("/me", headers=as_user("user_alice")).json()
    assert me["email"] == "alice@example.com"
    assert me["workspaces"] == []
    # The same person on a later request is the same user.
    assert client.get("/me", headers=as_user("user_alice")).json()["id"] == me["id"]


def test_email_is_updated_when_it_changes_in_clerk(client):
    client.get("/me", headers=as_user("user_alice"))
    me = client.get("/me", headers=as_user("user_alice", email="Alice@New.example")).json()
    assert me["email"] == "alice@new.example"


def test_bad_tokens_are_rejected(client):
    cases = {
        "no header": {},
        "not bearer": {"Authorization": "Basic abc"},
        "garbage": {"Authorization": "Bearer not-a-jwt"},
        "wrong key": {"Authorization": f"Bearer {token(key=OTHER_KEY)}"},
        "expired": as_user(exp=1, nbf=0, iat=0),
        "other issuer": as_user(iss="https://evil.example"),
        "other site": as_user(azp="https://evil.example"),
        "unfinished sign-up": as_user(sts="pending"),
    }
    for name, headers in cases.items():
        assert client.get("/me", headers=headers).status_code == 401, name
