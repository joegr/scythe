"""Scythe passthrough: cards and spans in, git commits out. Stateless; deployed on Fly.

Every call names the repo in its path and carries the user's GitHub token (Authorization: Bearer ...),
which is passed straight through to GitHub as that user: commits and issues are authored by them, and
GitHub decides which repos they can write. SCYTHE_REPOS, if set, limits which repos this server serves.
Saves are commits pinned to the file version the editor started from; if someone else committed first, GitHub refuses (like a
non-fast-forward push) and this returns 409 with their version: a divergence.

    POST /repos/{owner}/{repo}/cards      {title, labels, content}  -> issue #n + commit cards/n.md
    PUT  /repos/{owner}/{repo}/cards/{n}  {content, sha, message}   -> commit, or 409 {theirs}
    POST /repos/{owner}/{repo}/sources    {title, content? | url}   -> issue #n + commit sources/n.md,
                                                                  or a scythe:fetch issue for the
                                                                  article fetcher Action
"""

import base64
import json
import os
import re

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

REPOS = {r.strip().lower() for r in os.environ.get("SCYTHE_REPOS", "").split(",") if r.strip()}  # empty: any repo
GITHUB = os.environ.get("GITHUB_API", "https://api.github.com").rstrip("/")
TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests route GitHub calls in-process
ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

app = FastAPI(title="scythe-passthrough", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST", "PUT"],
                   allow_headers=["Authorization", "Content-Type"], max_age=600)


class NewCard(BaseModel):
    title: str
    labels: list[str]
    content: str  # cards/<n>.md with "issue": null; the number is filled in here


class Save(BaseModel):
    content: str
    sha: str  # the version this edit started from
    message: str


class NewSource(BaseModel):
    title: str
    content: str | None = None  # sources/<n>.md, "issue": null
    url: str | None = None      # without content: ask the fetcher Action to read the article


class Diverged(Exception):
    def __init__(self, repo: str = "", path: str = ""):
        self.repo, self.path = repo, path


NAME = re.compile(r"^(?!\.\.?$)[A-Za-z0-9_.-]{1,100}$")


def repo_of(owner: str, repo: str) -> str:
    if not (NAME.match(owner) and NAME.match(repo)):
        raise HTTPException(404, "no such repo")
    full = f"{owner}/{repo}"
    if REPOS and full.lower() not in REPOS:
        raise HTTPException(403, f"this server doesn't serve {full}")
    return full


async def gh(request: Request, method: str, path: str, body: dict | None = None) -> dict:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "sign in with GitHub")
    async with httpx.AsyncClient(timeout=20, transport=TRANSPORT) as client:
        r = await client.request(method, f"{GITHUB}{path}", json=body, headers={
            "Authorization": auth, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    if r.status_code == 409 or (r.status_code == 422 and "sha" in r.text):
        raise Diverged()
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.json().get("message", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text)
    return r.json() if r.content else {}


def with_issue(content: str, n: int) -> str:
    """Set "issue": n in the JSON front matter without reformatting anything else."""
    head, sep, rest = content.partition("\n---\n")
    if not head.startswith("---\n") or not sep or '"issue": null' not in head:
        raise HTTPException(422, 'content must start with JSON front matter containing "issue": null')
    return head.replace('"issue": null', f'"issue": {n}', 1) + sep + rest


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


async def commit(request: Request, repo: str, path: str, content: str, message: str, sha: str | None = None) -> dict:
    body = {"message": message, "content": b64(content), **({"sha": sha} if sha else {})}
    try:
        out = await gh(request, "PUT", f"/repos/{repo}/contents/{path}", body)
    except Diverged:
        raise Diverged(repo, path) from None
    return {"sha": out["content"]["sha"], "commit": out["commit"]["sha"]}


@app.exception_handler(Diverged)
async def diverged(request: Request, exc: Diverged):
    """Their version: file content, blob sha, and the commit that made it."""
    cur = await gh(request, "GET", f"/repos/{exc.repo}/contents/{exc.path}")
    last = await gh(request, "GET", f"/repos/{exc.repo}/commits?path={exc.path}&per_page=1")
    c = last[0] if last else {}
    return JSONResponse(status_code=409, content={
        "diverged": True,
        "theirs": {"content": base64.b64decode(cur["content"]).decode(), "sha": cur["sha"],
                   "commit": {"sha": c.get("sha"), "message": (c.get("commit") or {}).get("message"),
                              "author": (c.get("author") or {}).get("login") or ((c.get("commit") or {}).get("author") or {}).get("name"),
                              "date": ((c.get("commit") or {}).get("author") or {}).get("date")}},
    })


@app.get("/healthz")
def healthz():
    return {"ok": True, "repos": sorted(REPOS) or "any"}


@app.post("/repos/{owner}/{repo}/cards", status_code=201)
async def create_card(owner: str, repo: str, body: NewCard, request: Request):
    repo = repo_of(owner, repo)
    issue = await gh(request, "POST", f"/repos/{repo}/issues", {
        "title": body.title, "labels": body.labels,
        "body": "This card lives in git; the Scythe Action fills in this issue from the file."})
    n = issue["number"]
    saved = await commit(request, repo, f"cards/{n}.md", with_issue(body.content, n), f"card: {body.title} (#{n})")
    return {"number": n, "url": issue["html_url"], **saved}


@app.put("/repos/{owner}/{repo}/cards/{n}")
async def save_card(owner: str, repo: str, n: int, body: Save, request: Request):
    return await commit(request, repo_of(owner, repo), f"cards/{n}.md", body.content, body.message, body.sha)


@app.post("/repos/{owner}/{repo}/sources", status_code=201)
async def create_source(owner: str, repo: str, body: NewSource, request: Request):
    repo = repo_of(owner, repo)
    if body.content is None and not body.url:
        raise HTTPException(422, "send the text, or a url to fetch")
    fetch = body.content is None
    meta = json.dumps({"kind": "fetch", "url": body.url}) if fetch else None
    issue = await gh(request, "POST", f"/repos/{repo}/issues", {
        "title": body.title or body.url or "Untitled source",
        "labels": ["scythe:fetch" if fetch else "scythe:source"],
        "body": f"Fetching {body.url}\n\n<!-- scythe:v1\n{meta}\n-->\n" if fetch else "The text lives in git."})
    n = issue["number"]
    out = {"number": n, "url": issue["html_url"], "fetching": fetch}
    if not fetch:
        out |= await commit(request, repo, f"sources/{n}.md", with_issue(body.content, n), f"source: {body.title} (#{n})")
    return out
