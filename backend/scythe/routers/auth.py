"""Sign in with GitHub (GitHub App user authorization) and choose the repo that stores cards."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import auth, jobs
from ..config import settings
from ..db import get_session
from ..github import GitHubError
from ..graph_models import Account
from ..schemas import RepoIn

router = APIRouter(tags=["auth"])

INDEX_TABLES = "files, blocks, cards, spans, nodes, edges, sources, authors, entities, chunks, jobs"


def _state_cookie_kw() -> dict:
    return dict(httponly=True, samesite="lax", secure=settings.api_url.startswith("https://"), path="/api/auth")


class ExchangeIn(BaseModel):
    code: str


@router.get("/auth/config")
def config():
    return dict(
        configured=auth.configured(),
        fake=settings.github_fake,
        install_url=f"https://github.com/apps/{settings.github_app_slug}/installations/new" if settings.github_app_slug else None,
        callback_url=auth.redirect_uri(),
    )


@router.get("/auth/login")
def login(return_to: str, session: Session = Depends(get_session)):
    """Start sign-in. `return_to` is the frontend page to come back to (must be an allowed origin)."""
    if not auth.configured():
        raise HTTPException(503, "GitHub App not configured; set SCYTHE_GITHUB_CLIENT_ID/SECRET, or sign in with a GitHub token")
    target = auth.allowed_return(return_to)
    if settings.github_fake:
        return _finish(session, None, target)
    state = secrets.token_urlsafe(24)
    resp = RedirectResponse(auth.authorize_url(state))
    resp.set_cookie(auth.STATE_COOKIE, f"{state} {target}", max_age=600, **_state_cookie_kw())
    return resp


@router.get("/auth/callback")
def callback(request: Request, code: str = "", state: str = "", session: Session = Depends(get_session)):
    expected, _, target = (request.cookies.get(auth.STATE_COOKIE) or "").partition(" ")
    if not code or not expected or not secrets.compare_digest(expected, state):
        raise HTTPException(400, "invalid OAuth state; start sign-in again")
    return _finish(session, code, auth.allowed_return(target))


def _finish(session: Session, code: str | None, target: str) -> RedirectResponse:
    """Back to the frontend with a one-time code in the fragment (never sent to any server)."""
    account = auth.sign_in(session, code)
    login_code = auth.new_login_code(session, account)
    session.commit()
    resp = RedirectResponse(f"{target}#/auth/{login_code}", status_code=303)
    resp.delete_cookie(auth.STATE_COOKIE, path="/api/auth")
    return resp


@router.post("/auth/exchange")
def exchange(body: ExchangeIn, session: Session = Depends(get_session)):
    """Trade the one-time code for a bearer session token."""
    account = auth.redeem_login_code(session, body.code)
    token = auth.new_session(session, account)
    session.commit()
    return dict(token=token, expires_in=settings.session_days * 86400)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, session: Session = Depends(get_session)):
    auth.end_session(session, auth.bearer(request))
    session.commit()


@router.get("/auth/me")
def me(account: Account = Depends(auth.current_account), session: Session = Depends(get_session)):
    state = auth.app_state(session)
    return dict(
        login=account.login, name=account.name, avatar_url=account.avatar_url, repo=state.repo or None,
        last_sync_at=state.last_sync_at, last_sync_error=state.last_sync_error or None,
    )


@router.get("/github/repos")
def repos(account: Account = Depends(auth.current_account), session: Session = Depends(get_session)):
    """Repositories the GitHub App is installed on and this user can reach."""
    try:
        return [dict(full_name=r["full_name"], private=r.get("private", False), html_url=r.get("html_url"))
                for r in auth.client_for(session, account).repos()]
    except GitHubError as e:
        raise HTTPException(502, str(e)) from e


@router.put("/github/repo")
def choose_repo(body: RepoIn, account: Account = Depends(auth.current_account), session: Session = Depends(get_session)):
    """Point the local index at a repo. Switching repos discards the index and rebuilds it from GitHub."""
    state = auth.app_state(session)
    if state.repo != body.repo:
        session.execute(text(f"TRUNCATE {INDEX_TABLES} RESTART IDENTITY CASCADE"))
        state.repo, state.last_sync_at = body.repo, None
    state.account_id = account.id
    session.commit()
    jobs.enqueue_pull(session)
    return dict(repo=state.repo)


@router.post("/github/sync", status_code=202)
def sync(account: Account = Depends(auth.current_account), session: Session = Depends(get_session)):
    auth.app_state(session).account_id = account.id
    session.commit()
    job = jobs.enqueue_pull(session)
    return dict(queued=job is not None)
