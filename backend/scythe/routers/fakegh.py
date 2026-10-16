"""A GitHub REST emulator over FakeGitHub, mounted at /fakegh when SCYTHE_GITHUB_FAKE=1.

The Pages app talks to GitHub directly; pointing it at this lets the whole browser flow run offline
(and in tests) against the exact endpoints it uses on api.github.com. Not for production.
"""

import re

from fastapi import APIRouter, HTTPException, Request, Response

from ..auth import fake_github
from ..github import GitHubError
from ..issue_doc import parse_meta

router = APIRouter(prefix="/fakegh", tags=["fake-github"])


def _public(issue: dict) -> dict:
    return {k: v for k, v in issue.items() if k not in ("sub_issues", "comment_list")}


def _all(repo: str) -> list[dict]:
    try:
        return fake_github()._repo(repo)["issues"]
    except GitHubError as e:
        raise HTTPException(e.status, "Not Found") from e


@router.get("/user")
def user():
    return fake_github().user()


@router.get("/repos/{owner}/{name}/issues")
def list_issues(owner: str, name: str, labels: str = "", state: str = "open", per_page: int = 30, page: int = 1,
                sort: str = "created", direction: str = "desc"):
    want = {x for x in labels.split(",") if x}
    rows = [i for i in _all(f"{owner}/{name}")
            if want <= {lb["name"] for lb in i["labels"]} and (state == "all" or i["state"] == state)]
    rows.sort(key=lambda i: i["updated_at" if sort == "updated" else "number"], reverse=direction == "desc")
    return [_public(i) for i in rows[(page - 1) * per_page: page * per_page]]


@router.post("/repos/{owner}/{name}/issues", status_code=201)
async def create_issue(owner: str, name: str, request: Request):
    body = await request.json()
    return _public(fake_github().create_issue(f"{owner}/{name}", body["title"], body.get("body", ""), body.get("labels", [])))


@router.get("/repos/{owner}/{name}/issues/{number}")
def get_issue(owner: str, name: str, number: int):
    return _public(fake_github().get_issue(f"{owner}/{name}", number))


@router.patch("/repos/{owner}/{name}/issues/{number}")
async def update_issue(owner: str, name: str, number: int, request: Request):
    return _public(fake_github().update_issue(f"{owner}/{name}", number, **(await request.json())))


@router.get("/repos/{owner}/{name}/issues/{number}/comments")
def comments(owner: str, name: str, number: int):
    return fake_github().list_comments(f"{owner}/{name}", number)


@router.post("/repos/{owner}/{name}/issues/{number}/comments", status_code=201)
async def comment(owner: str, name: str, number: int, request: Request):
    return fake_github().create_comment(f"{owner}/{name}", number, (await request.json())["body"])


@router.get("/repos/{owner}/{name}/issues/{number}/sub_issues")
def sub_issues(owner: str, name: str, number: int):
    parent = fake_github().get_issue(f"{owner}/{name}", number)
    return [_public(i) for i in _all(f"{owner}/{name}") if i["id"] in parent["sub_issues"]]


@router.post("/repos/{owner}/{name}/issues/{number}/sub_issues", status_code=201)
async def add_sub_issue(owner: str, name: str, number: int, request: Request):
    fake_github().add_sub_issue(f"{owner}/{name}", number, (await request.json())["sub_issue_id"])
    return _public(fake_github().get_issue(f"{owner}/{name}", number))


@router.get("/repos/{owner}/{name}/issues/{number}/timeline")
def timeline(owner: str, name: str, number: int):
    """Only what the app reads: cross-references from issues whose links point here."""
    out = []
    for i in _all(f"{owner}/{name}"):
        meta = parse_meta(i["body"]) or {}
        if any(lk.get("to") == number for lk in meta.get("links") or []):
            out.append({"event": "cross-referenced", "source": {"type": "issue", "issue": _public(i)}})
    return out


@router.get("/repos/{owner}/{name}/labels")
def labels(owner: str, name: str):
    names = {lb["name"] for i in _all(f"{owner}/{name}") for lb in i["labels"]}
    names |= set(fake_github()._repo(f"{owner}/{name}")["labels"])
    return [{"name": n, "color": "ededed"} for n in sorted(names)]


@router.get("/search/issues")
def search(q: str, per_page: int = 30):
    """Enough of GitHub's issue search: repo:, label:"…", is:open/closed, and free-text words."""
    repo = re.search(r"repo:(\S+)", q).group(1)
    want_labels = re.findall(r'label:"([^"]+)"|label:(\S+)', q)
    want = {a or b for a, b in want_labels}
    state = "open" if "is:open" in q else "closed" if "is:closed" in q else None
    words = re.sub(r'(repo|label|is):("[^"]*"|\S+)', " ", q).lower().split()
    hits = []
    for i in _all(repo):
        names = {lb["name"] for lb in i["labels"]}
        hay = f"{i['title']} {i['body']}".lower()
        if want <= names and (state is None or i["state"] == state) and all(w.strip('"') in hay for w in words):
            hits.append(_public(i))
    return {"total_count": len(hits), "items": hits[:per_page]}


@router.get("/repos/{owner}/{name}/contents/{path:path}")
def get_contents(owner: str, name: str, path: str, ref: str | None = None):
    import base64

    try:
        content = fake_github().get_file(f"{owner}/{name}", path)
    except GitHubError as e:
        raise HTTPException(e.status, "Not Found") from e
    return {"path": path, "sha": fake_github().blob_sha(content), "encoding": "base64",
            "content": base64.b64encode(content.encode()).decode()}


@router.put("/repos/{owner}/{name}/contents/{path:path}")
async def put_contents(owner: str, name: str, path: str, request: Request):
    import base64

    body = await request.json()
    try:
        out = fake_github().put_file(f"{owner}/{name}", path, base64.b64decode(body["content"]).decode(),
                                     body["message"], body.get("sha"), enforce=True)
    except GitHubError as e:
        raise HTTPException(e.status, str(e)) from e
    return {"content": {"path": path, "sha": out["sha"]}, "commit": {"sha": out["commit"]["sha"], "message": body["message"]}}


@router.delete("/repos/{owner}/{name}/contents/{path:path}")
async def delete_contents(owner: str, name: str, path: str, request: Request):
    body = await request.json()
    fake = fake_github()
    with fake._lock:
        files = fake._repo(f"{owner}/{name}")["files"]
        if path not in files:
            raise HTTPException(404, "Not Found")
        if body.get("sha") != fake.blob_sha(files[path]):
            raise HTTPException(409, f"{path} does not match")
        del files[path]
        fake._save()
    return {"commit": {"message": body.get("message")}}


@router.get("/repos/{owner}/{name}/commits")
def commits(owner: str, name: str, path: str | None = None, per_page: int = 30):
    return [{"sha": c["sha"], "commit": {"message": c["message"], "author": {"name": c["author"], "date": c["date"]}},
             "author": {"login": c["author"]}} for c in fake_github().commits(f"{owner}/{name}", path)[:per_page]]


@router.options("/{path:path}")
def preflight(path: str):
    return Response(status_code=204)
