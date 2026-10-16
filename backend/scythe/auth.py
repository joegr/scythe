"""GitHub App user-to-server OAuth: code exchange, token refresh, cookie sessions."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .crypto import decrypt, encrypt
from .db import get_session
from .github import FakeGitHub, GitHub, RestGitHub
from .graph_models import Account, AppState, AuthSession, LoginCode

STATE_COOKIE = "scythe_oauth_state"  # lives on the API origin only, for the OAuth round trip
TOKEN_URL = "https://github.com/login/oauth/access_token"
AUTHORIZE_URL = "https://github.com/login/oauth/authorize"

_fake: FakeGitHub | None = None


def fake_github() -> FakeGitHub:
    global _fake
    if _fake is None:
        _fake = FakeGitHub(settings.github_fake_path)
    return _fake


def configured() -> bool:
    return settings.github_fake or bool(settings.github_client_id and settings.github_client_secret)


def redirect_uri() -> str:
    return f"{settings.api_url.rstrip('/')}/api/auth/callback"


def allowed_return(url: str) -> str:
    """Only send sign-in codes back to a configured frontend origin."""
    parsed = httpx.URL(url)
    origin = f"{parsed.scheme}://{parsed.host}" + (f":{parsed.port}" if parsed.port else "")
    if parsed.scheme not in ("http", "https") or origin not in settings.frontend_origins:
        raise HTTPException(400, f"return_to origin {origin} is not in SCYTHE_FRONTEND_ORIGINS")
    return str(parsed.copy_with(fragment=None))


def authorize_url(state: str) -> str:
    q = httpx.QueryParams(client_id=settings.github_client_id, redirect_uri=redirect_uri(), state=state)
    return f"{AUTHORIZE_URL}?{q}"


def _token_request(data: dict) -> dict:
    r = httpx.post(TOKEN_URL, data={"client_id": settings.github_client_id,
                                     "client_secret": settings.github_client_secret, **data},
                   headers={"Accept": "application/json"}, timeout=20)
    payload = r.json()
    if r.status_code >= 400 or "error" in payload:
        raise HTTPException(401, payload.get("error_description") or payload.get("error") or "token exchange failed")
    return payload


def _store_tokens(account: Account, payload: dict) -> None:
    now = datetime.now(UTC)
    account.token_enc = encrypt(payload["access_token"])
    if payload.get("refresh_token"):
        account.refresh_enc = encrypt(payload["refresh_token"])
    account.expires_at = now + timedelta(seconds=int(payload["expires_in"])) if payload.get("expires_in") else None
    if payload.get("refresh_token_expires_in"):
        account.refresh_expires_at = now + timedelta(seconds=int(payload["refresh_token_expires_in"]))


def sign_in(session: Session, code: str | None) -> Account:
    """Exchange an OAuth code (or, in fake mode, nothing) for an account row with fresh tokens."""
    if settings.github_fake:
        payload, user = {"access_token": "fake"}, fake_github().user()
    else:
        payload = _token_request({"code": code, "redirect_uri": redirect_uri()})
        user = RestGitHub(payload["access_token"]).user()
    account = session.scalar(select(Account).where(Account.gh_user_id == user["id"]))
    if account is None:
        account = Account(gh_user_id=user["id"], login=user["login"], token_enc=b"")
        session.add(account)
    account.login, account.name, account.avatar_url = user["login"], user.get("name") or "", user.get("avatar_url") or ""
    _store_tokens(account, payload)
    session.flush()
    return account


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_login_code(session: Session, account: Account) -> str:
    raw = secrets.token_urlsafe(24)
    session.add(LoginCode(id=_hash(raw), account_id=account.id, expires_at=datetime.now(UTC) + timedelta(seconds=60)))
    return raw


def redeem_login_code(session: Session, raw: str) -> Account:
    code = session.get(LoginCode, _hash(raw))
    if code is None or code.expires_at < datetime.now(UTC):
        raise HTTPException(401, "sign-in code expired; sign in again")
    account = session.get(Account, code.account_id)
    session.delete(code)
    return account


def new_session(session: Session, account: Account) -> str:
    raw = secrets.token_urlsafe(32)
    session.add(AuthSession(id=hashlib.sha256(raw.encode()).hexdigest(), account_id=account.id,
                            expires_at=datetime.now(UTC) + timedelta(days=settings.session_days)))
    state = app_state(session)
    if state.account_id is None:
        state.account_id = account.id
    return raw


def app_state(session: Session) -> AppState:
    state = session.get(AppState, 1)
    if state is None:
        state = AppState(id=1)
        session.add(state)
        session.flush()
    return state


def access_token(session: Session, account: Account) -> str:
    """The account's token, refreshed first if it expires within five minutes."""
    if settings.github_fake:
        return "fake"
    if account.expires_at and account.expires_at - timedelta(minutes=5) < datetime.now(UTC):
        if not account.refresh_enc:
            raise HTTPException(401, "GitHub session expired; sign in again")
        _store_tokens(account, _token_request({"grant_type": "refresh_token",
                                               "refresh_token": decrypt(account.refresh_enc)}))
        session.commit()
    return decrypt(account.token_enc)


def client_for(session: Session, account: Account) -> GitHub:
    if settings.github_fake:
        return fake_github()
    return RestGitHub(access_token(session, account))


def bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else None


GITHUB_TOKEN_PREFIXES = ("github_pat_", "ghp_", "gho_", "ghu_")
_verified: dict[str, tuple[int, datetime]] = {}  # token hash -> (account id, checked at)


def account_for_github_token(session: Session, token: str) -> Account:
    """The Pages app signs in with a fine-grained token; verify it against GitHub (cached for five
    minutes) and keep it, encrypted, as that account's token for index pulls."""
    key = _hash(token)
    hit = _verified.get(key)
    if hit and datetime.now(UTC) - hit[1] < timedelta(minutes=5):
        account = session.get(Account, hit[0])
        if account is not None:
            return account
    gh = fake_github() if settings.github_fake else RestGitHub(token)
    try:
        user = gh.user()
    except Exception as e:
        raise HTTPException(401, "GitHub rejected this token") from e
    account = session.scalar(select(Account).where(Account.gh_user_id == user["id"]))
    if account is None:
        account = Account(gh_user_id=user["id"], login=user["login"], token_enc=b"")
        session.add(account)
    account.login, account.name, account.avatar_url = user["login"], user.get("name") or "", user.get("avatar_url") or ""
    account.token_enc, account.refresh_enc, account.expires_at = encrypt(token), None, None
    state = app_state(session)
    if state.account_id is None:
        state.account_id = account.id
    session.commit()
    _verified[key] = (account.id, datetime.now(UTC))
    return account


def current_account(request: Request, session: Session = Depends(get_session)) -> Account:
    raw = bearer(request)
    if raw and raw.startswith(GITHUB_TOKEN_PREFIXES):
        return account_for_github_token(session, raw)
    if raw:
        auth = session.get(AuthSession, _hash(raw))
        if auth is not None and auth.expires_at > datetime.now(UTC):
            account = session.get(Account, auth.account_id)
            if account is not None:
                return account
    raise HTTPException(401, "sign in with GitHub")


def end_session(session: Session, raw: str | None) -> None:
    if raw:
        auth = session.get(AuthSession, hashlib.sha256(raw.encode()).hexdigest())
        if auth is not None:
            session.delete(auth)
