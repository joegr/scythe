"""GitHub REST access for the card store, with a drop-in fake for tests and offline development.

Only the endpoints Scythe needs: the signed-in user, repos the GitHub App is installed on,
issues (create / update / list), labels, sub-issues and repository files.
"""

import base64
import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import httpx

API = "https://api.github.com"


class GitHubError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"GitHub {status}: {message}")
        self.status = status


class GitHub(Protocol):
    def user(self) -> dict: ...
    def repos(self) -> list[dict]: ...
    def create_issue(self, repo: str, title: str, body: str, labels: list[str]) -> dict: ...
    def update_issue(self, repo: str, number: int, **fields) -> dict: ...
    def get_issue(self, repo: str, number: int) -> dict: ...
    def list_issues(self, repo: str, label: str, since: str | None = None) -> Iterator[dict]: ...
    def ensure_label(self, repo: str, name: str, color: str, description: str = "") -> None: ...
    def add_sub_issue(self, repo: str, parent: int, child_id: int) -> None: ...
    def put_file(self, repo: str, path: str, content: str, message: str) -> dict: ...
    def get_file(self, repo: str, path: str) -> str: ...


class RestGitHub:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self.http = client or httpx.Client(base_url=API, timeout=20)
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _req(self, method: str, url: str, **kw) -> httpx.Response:
        r = self.http.request(method, url, headers=self.headers, **kw)
        if r.status_code >= 400:
            try:
                msg = r.json().get("message", r.text)
            except ValueError:
                msg = r.text
            raise GitHubError(r.status_code, msg)
        return r

    def _pages(self, url: str, params: dict, key: str | None = None) -> Iterator[dict]:
        params = {**params, "per_page": 100}
        while url:
            r = self._req("GET", url, params=params)
            data = r.json()
            yield from (data[key] if key else data)
            url = r.links.get("next", {}).get("url")
            params = {}

    def user(self) -> dict:
        return self._req("GET", "/user").json()

    def repos(self) -> list[dict]:
        out = []
        for inst in self._pages("/user/installations", {}, "installations"):
            out.extend(self._pages(f"/user/installations/{inst['id']}/repositories", {}, "repositories"))
        return out

    def create_issue(self, repo: str, title: str, body: str, labels: list[str]) -> dict:
        return self._req("POST", f"/repos/{repo}/issues", json=dict(title=title, body=body, labels=labels)).json()

    def update_issue(self, repo: str, number: int, **fields) -> dict:
        return self._req("PATCH", f"/repos/{repo}/issues/{number}", json=fields).json()

    def get_issue(self, repo: str, number: int) -> dict:
        return self._req("GET", f"/repos/{repo}/issues/{number}").json()

    def list_issues(self, repo: str, label: str, since: str | None = None) -> Iterator[dict]:
        params = {"labels": label, "state": "all", "sort": "created", "direction": "asc"}
        if since:
            params["since"] = since
        for issue in self._pages(f"/repos/{repo}/issues", params):
            if "pull_request" not in issue:
                yield issue

    def ensure_label(self, repo: str, name: str, color: str, description: str = "") -> None:
        try:
            self._req("POST", f"/repos/{repo}/labels", json=dict(name=name, color=color, description=description))
        except GitHubError as e:
            if e.status != 422:  # already exists
                raise

    def add_sub_issue(self, repo: str, parent: int, child_id: int) -> None:
        try:
            self._req("POST", f"/repos/{repo}/issues/{parent}/sub_issues", json=dict(sub_issue_id=child_id))
        except GitHubError as e:
            if e.status != 422:  # already a sub-issue
                raise

    def put_file(self, repo: str, path: str, content: str, message: str) -> dict:
        sha = None
        try:
            sha = self._req("GET", f"/repos/{repo}/contents/{path}").json()["sha"]
        except GitHubError as e:
            if e.status != 404:
                raise
        payload = dict(message=message, content=base64.b64encode(content.encode()).decode())
        if sha:
            payload["sha"] = sha
        return self._req("PUT", f"/repos/{repo}/contents/{path}", json=payload).json()["content"]

    def get_file(self, repo: str, path: str) -> str:
        data = self._req("GET", f"/repos/{repo}/contents/{path}").json()
        return base64.b64decode(data["content"]).decode()


class FakeGitHub:
    """In-process stand-in for GitHub with the same surface. Persists to JSON when given a path,
    so the dev server keeps its "issues" across reloads."""

    _lock = threading.Lock()

    def __init__(self, path: Path | None = None, login: str = "scythe-dev", repos: tuple[str, ...] = ("scythe-dev/cards",)):
        self.path = path
        self.login = login
        self.state = {"repos": {r: {"issues": [], "labels": {}, "files": {}, "next": 1} for r in repos}}
        if path and path.exists():
            self.state = json.loads(path.read_text())
            for r in repos:
                self.state["repos"].setdefault(r, {"issues": [], "labels": {}, "files": {}, "next": 1})

    def _save(self):
        if self.path:
            self.path.write_text(json.dumps(self.state))

    def _repo(self, repo: str) -> dict:
        if repo not in self.state["repos"]:
            raise GitHubError(404, "Not Found")
        return self.state["repos"][repo]

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def _issue(self, repo: str, number: int) -> dict:
        for i in self._repo(repo)["issues"]:
            if i["number"] == number:
                return i
        raise GitHubError(404, "Not Found")

    def user(self) -> dict:
        return {"id": 1, "login": self.login, "name": "Scythe Dev", "avatar_url": ""}

    def repos(self) -> list[dict]:
        return [{"full_name": r, "private": True, "html_url": f"https://github.com/{r}"} for r in self.state["repos"]]

    def create_issue(self, repo: str, title: str, body: str, labels: list[str]) -> dict:
        with self._lock:
            r = self._repo(repo)
            n = r["next"]
            r["next"] += 1
            issue = dict(
                id=100000 + n, number=n, node_id=f"I_{n}", title=title, body=body, state="open",
                labels=[{"name": x} for x in labels], updated_at=self._now(), sub_issues=[], comments=0,
                comment_list=[], user={"login": self.login}, html_url=f"https://github.com/{repo}/issues/{n}",
            )
            r["issues"].append(issue)
            self._save()
            return dict(issue)

    def update_issue(self, repo: str, number: int, **fields) -> dict:
        with self._lock:
            issue = self._issue(repo, number)
            for k, v in fields.items():
                issue[k] = [{"name": x} for x in v] if k == "labels" else v
            issue["updated_at"] = self._now()
            self._save()
            return dict(issue)

    def get_issue(self, repo: str, number: int) -> dict:
        return dict(self._issue(repo, number))

    def list_issues(self, repo: str, label: str, since: str | None = None) -> Iterator[dict]:
        cutoff = datetime.fromisoformat(since.replace("Z", "+00:00")) if since else None
        for i in list(self._repo(repo)["issues"]):
            updated = datetime.fromisoformat(i["updated_at"].replace("Z", "+00:00"))
            if any(lb["name"] == label for lb in i["labels"]) and (cutoff is None or updated >= cutoff):
                yield dict(i)

    def create_comment(self, repo: str, number: int, body: str) -> dict:
        with self._lock:
            issue = self._issue(repo, number)
            comment = {"id": len(issue["comment_list"]) + 1, "body": body}
            issue["comment_list"].append(comment)
            issue["comments"] = len(issue["comment_list"])
            self._save()
            return comment

    def list_comments(self, repo: str, number: int) -> list[dict]:
        return list(self._issue(repo, number)["comment_list"])

    def ensure_label(self, repo: str, name: str, color: str, description: str = "") -> None:
        with self._lock:
            self._repo(repo)["labels"].setdefault(name, {"color": color, "description": description})
            self._save()

    def add_sub_issue(self, repo: str, parent: int, child_id: int) -> None:
        with self._lock:
            subs = self._issue(repo, parent)["sub_issues"]
            if child_id not in subs:
                subs.append(child_id)
            self._save()

    @staticmethod
    def blob_sha(content: str) -> str:
        import hashlib

        raw = content.encode()
        return hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest()

    def put_file(self, repo: str, path: str, content: str, message: str, sha: str | None = None,
                 enforce: bool = False) -> dict:
        """Contents API semantics when `enforce`: updating needs the current blob sha (else 409/422)."""
        with self._lock:
            r = self._repo(repo)
            current = r["files"].get(path)
            if enforce and current is not None:
                if sha is None:
                    raise GitHubError(422, 'Invalid request. "sha" wasn\'t supplied.')
                if sha != self.blob_sha(current):
                    raise GitHubError(409, f"{path} does not match {sha}")
            r["files"][path] = content
            commit = {"sha": self.blob_sha(f"{path}{message}{self._now()}"), "path": path, "message": message,
                      "author": self.login, "date": self._now()}
            r.setdefault("commits", []).append(commit)
            self._save()
        return {"path": path, "sha": self.blob_sha(content), "html_url": f"https://github.com/{repo}/blob/main/{path}",
                "commit": commit}

    def commits(self, repo: str, path: str | None = None) -> list[dict]:
        rows = [c for c in self._repo(repo).get("commits", []) if path is None or c["path"] == path]
        return list(reversed(rows))

    def get_file(self, repo: str, path: str) -> str:
        try:
            return self._repo(repo)["files"][path]
        except KeyError:
            raise GitHubError(404, "Not Found") from None
