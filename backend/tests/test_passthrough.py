"""The Fly passthrough (server/main.py) against the fake GitHub: commits, and divergence on stale saves."""

import importlib.util
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from scythe.issue_doc import card_file, parse_card_file, source_file
from tests.conftest import REPO

SERVER = Path(__file__).resolve().parents[2] / "server" / "main.py"


@pytest.fixture
def passthrough():
    from scythe.main import app as backend  # serves /fakegh in fake mode

    spec = importlib.util.spec_from_file_location("scythe_server", SERVER)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    server.GITHUB = "http://fake/fakegh"
    server.TRANSPORT = httpx.ASGITransport(app=backend)
    with TestClient(server.app, headers={"Authorization": "Bearer github_pat_fake"}) as c:
        c.server = server
        yield c


def _card(text="Soot from burning cities would block sunlight.", spans=()):
    return {"issue": None, "title": "Soot", "topic": {"slug": "t"}, "file": None, "block": None, "approved": False,
            "cite": "Robock 22", "url": "", "source": None, "links": [], "spans": list(spans), "text": text}


def test_save_then_diverge(passthrough, fake_gh):
    src = passthrough.post(f"/repos/{REPO}/sources", json={"title": "Winter", "content": source_file(
        {"issue": None, "title": "Winter", "url": None, "publisher": "", "published": None, "authors": [], "cite": "", "fetched": None},
        "Soot from burning cities would block sunlight.")}).json()
    assert '"issue": %d' % src["number"] in fake_gh.get_file(REPO, f"sources/{src['number']}.md")

    created = passthrough.post(f"/repos/{REPO}/cards", json={"title": "Soot", "labels": ["scythe:card", "topic:t"], "content": card_file(_card())})
    assert created.status_code == 201, created.text
    n, base = created.json()["number"], created.json()["sha"]
    path = f"cards/{n}.md"
    assert parse_card_file(fake_gh.get_file(REPO, path))["issue"] == n

    current = parse_card_file(fake_gh.get_file(REPO, path))
    mine = {**current, "spans": [{"label": "underline", "key": "sc", "style": "underline", "start_char": 0, "end_char": 4, "src": "manual"}]}
    theirs = {**current, "spans": [{"label": "highlight", "key": "sc", "style": "highlight", "start_char": 10, "end_char": 16, "src": "manual"}]}

    # Someone else saves first, from the same base...
    first = passthrough.put(f"/repos/{REPO}/cards/{n}", json={"content": card_file(theirs), "sha": base, "message": "highlight: burning"})
    assert first.status_code == 200, first.text
    # ...so my save from the old base diverges, and I get their version back.
    second = passthrough.put(f"/repos/{REPO}/cards/{n}", json={"content": card_file(mine), "sha": base, "message": "underline: Soot"})
    assert second.status_code == 409
    body = second.json()
    assert body["diverged"] and body["theirs"]["sha"] == first.json()["sha"]
    assert body["theirs"]["commit"]["message"] == "highlight: burning"
    assert parse_card_file(body["theirs"]["content"])["spans"] == theirs["spans"]

    # Rebasing my change onto theirs fast-forwards.
    rebased = {**theirs, "spans": theirs["spans"] + mine["spans"]}
    ok = passthrough.put(f"/repos/{REPO}/cards/{n}", json={"content": card_file(rebased), "sha": body["theirs"]["sha"], "message": "underline: Soot"})
    assert ok.status_code == 200
    assert [c["message"] for c in fake_gh.commits(REPO, path)] == ["underline: Soot", "highlight: burning", f"card: Soot (#{n})"]


def test_requires_token_and_fetch_issue(passthrough, fake_gh):
    anon = TestClient(passthrough.app)
    assert anon.put(f"/repos/{REPO}/cards/1", json={"content": "x", "sha": "y", "message": "z"}).status_code == 401
    out = passthrough.post(f"/repos/{REPO}/sources", json={"title": "", "url": "https://example.org/a"}).json()
    issue = fake_gh.get_issue(REPO, out["number"])
    assert out["fetching"] and [lb["name"] for lb in issue["labels"]] == ["scythe:fetch"] and "https://example.org/a" in issue["body"]


def test_repo_comes_from_the_path(passthrough):
    body = {"title": "Soot", "labels": ["scythe:card"], "content": card_file(_card())}
    assert passthrough.post("/repos/../cards", json=body).status_code == 404
    passthrough.server.REPOS = {"someone/else"}
    r = passthrough.post(f"/repos/{REPO}/cards", json=body)
    assert r.status_code == 403 and REPO in r.json()["detail"]
    passthrough.server.REPOS = {REPO}
    assert passthrough.post(f"/repos/{REPO}/cards", json=body).status_code == 201


def test_branch_race_on_another_file_is_retried_not_diverged(passthrough, fake_gh):
    """GitHub 409s a contents PUT when main moved under it, even for a different file."""
    inner = passthrough.server.TRANSPORT
    refused = []

    class BranchRace(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if request.method == "PUT" and not refused:
                refused.append(request.url.path)
                return httpx.Response(409, json={"message": "is at abc but expected def"})
            return await inner.handle_async_request(request)

    passthrough.server.TRANSPORT = BranchRace()
    created = passthrough.post(f"/repos/{REPO}/cards", json={"title": "Soot", "labels": ["scythe:card"], "content": card_file(_card())})
    assert created.status_code == 201, created.text
    n, base = created.json()["number"], created.json()["sha"]
    assert refused  # the first commit really was refused once

    refused.clear()
    marked = _card(spans=[{"label": "underline", "key": "sc", "style": "underline", "start_char": 0, "end_char": 4, "src": "manual"}])
    marked["issue"] = n
    saved = passthrough.put(f"/repos/{REPO}/cards/{n}", json={"content": card_file(marked), "sha": base, "message": "underline: Soot"})
    assert saved.status_code == 200, saved.text
    assert refused
