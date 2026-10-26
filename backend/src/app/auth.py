"""Who is calling: a user signed in with Clerk.

The web app sends Clerk's short-lived session token as a bearer token. We check its signature
against Clerk's published keys, then the expiry, issuer and the origin that asked for it
(`azp`). The Clerk user id becomes a User row on first use. Clerk only says who someone is;
which workspaces they belong to lives in our database (see tenancy.py).
"""

from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models import User


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def signing_key(settings: Settings, token: str):
    """The public key Clerk signed this token with. Replaced in tests."""
    url = settings.clerk_issuer.rstrip("/") + "/.well-known/jwks.json"
    return _jwks_client(url).get_signing_key_from_jwt(token).key


def verify_clerk_token(settings: Settings, token: str) -> dict:
    """The claims of a valid session token, or a 401."""
    if not settings.clerk_issuer:
        raise HTTPException(status_code=503, detail="CLERK_ISSUER is not configured.")
    try:
        claims = jwt.decode(
            token,
            signing_key(settings, token),
            algorithms=["RS256"],
            issuer=settings.clerk_issuer.rstrip("/"),
            options={"require": ["exp", "nbf", "iss", "sub"]},
            leeway=5,
        )
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Please sign in again.") from exc
    # Without this check, a token minted for another site on the same Clerk instance would work.
    azp = claims.get("azp")
    if azp is not None and azp not in settings.cors_origin_list:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    # Pending sessions have not finished signing up.
    if claims.get("sts") == "pending":
        raise HTTPException(status_code=401, detail="Please finish signing up.")
    return claims


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip() or None
    return None


def current_user(
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    token = _bearer(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Please sign in.")
    claims = verify_clerk_token(get_settings(), token)
    clerk_id = str(claims["sub"])
    email = claims.get("email")
    email = email.strip().lower() if isinstance(email, str) and email.strip() else None

    user = session.scalar(select(User).where(User.clerk_user_id == clerk_id))
    if user is None:
        user = User(clerk_user_id=clerk_id, email=email)
        session.add(user)
        try:
            session.commit()
        except IntegrityError:  # two first requests at once
            session.rollback()
            user = session.scalar(select(User).where(User.clerk_user_id == clerk_id))
            assert user is not None
    elif email and user.email != email:
        user.email = email
        session.commit()
    return user


CurrentUser = Annotated[User, Depends(current_user)]
