"""GitHub Issues as the card store: push format, approval, links, archive, and full rebuild from issues."""

from sqlalchemy import text

from scythe.issues import parse_meta
from tests.conftest import ARTICLE, REPO


def _issue(fake_gh, number):
    return fake_gh.get_issue(REPO, number)


def _label(client, labels, card, name, phrase):
    i = card["text"].index(phrase)
    r = client.post(f"/api/cards/{card['id']}/spans",
                    json=dict(label_id=labels[name]["id"], start_char=i, end_char=i + len(phrase)))
    assert r.status_code == 201, r.text


def test_api_requires_sign_in():
    from fastapi.testclient import TestClient

    from scythe.main import app

    with TestClient(app) as anon:
        assert anon.get("/api/cards").status_code == 401
        assert anon.get("/api/auth/config").json()["fake"] is True


def test_topic_is_required_and_remembered(client):
    client.put("/api/topics/current", json={"topic_id": None})
    r = client.post("/api/cards", json=dict(text="Soot blocks sunlight."))
    assert r.status_code == 422 and r.json()["detail"] == "topic_required"
    ld = client.get("/api/topics", params=dict(q="wealth tax", event="ld")).json()[0]
    assert ld["resolution"] == "Resolved: The United States ought to adopt a wealth tax."
    card = client.post("/api/cards", json=dict(text="Soot blocks sunlight.", topic_id=ld["id"])).json()
    assert card["topic"]["slug"] == ld["slug"]
    assert client.get("/api/topics/current").json()["id"] == ld["id"]  # last used becomes the default
    custom = client.post("/api/topics", json=dict(resolution="Nuclear winter is real", season="2026-27")).json()
    assert custom["slug"].startswith("custom-") and custom["resolution"].startswith("Resolved: ")


def test_cut_card_becomes_sub_issue_with_metadata(client, source, labels, fake_gh):
    card = client.post(f"/api/sources/{source['id']}/cut",
                       json=dict(start_char=0, end_char=ARTICLE.index("\n"), tag="Nuclear war causes extinction")).json()
    _label(client, labels, card, "underline", "soot from burning cities would block sunlight")
    _label(client, labels, card, "highlight", "block sunlight")
    card = client.get(f"/api/cards/{card['id']}").json()
    assert card["gh_number"] and card["gh_synced"]

    issue = _issue(fake_gh, card["gh_number"])
    assert issue["title"] == "Nuclear war causes extinction"
    names = {lb["name"] for lb in issue["labels"]}
    assert {"scythe:card", f"topic:{card['topic']['slug']}"} <= names
    assert "<ins>soot from burning cities would <mark>block sunlight</mark></ins>" in issue["body"]
    meta = parse_meta(issue["body"])
    assert meta["text"] == card["text"]
    assert {(s["label"], s["start_char"], s["end_char"]) for s in meta["spans"]} == {
        (s["label"], s["start_char"], s["end_char"]) for s in card["spans"] if s["spans_key"] == "sc"}
    assert not any(s["key"] == "ents" for s in meta["spans"])  # NER is derived, not stored

    src_issue = _issue(fake_gh, client.get(f"/api/sources/{source['id']}").json()["gh_number"])
    assert card["gh_number"] + 100000 in src_issue["sub_issues"]  # fake ids are 100000 + number
    text_path = parse_meta(src_issue["body"])["text_path"]
    assert ARTICLE in fake_gh.get_file(REPO, text_path)


def test_approve_link_archive(client, fake_gh):
    a = client.post("/api/cards", json=dict(text="Warming causes extinction.", tag="Warming bad")).json()
    b = client.post("/api/cards", json=dict(text="Warming is slow and adaptable.", tag="Warming slow")).json()
    client.post(f"/api/cards/{a['id']}/approve")
    a, b = (client.get(f"/api/cards/{x['id']}").json() for x in (a, b))
    assert "approved" in {lb["name"] for lb in _issue(fake_gh, a["gh_number"])["labels"]}

    client.post("/api/graph/edges", json=dict(src_id=b["node_id"], dst_id=a["node_id"], relation="answers"))
    body = _issue(fake_gh, b["gh_number"])["body"]
    assert f"Answers #{a['gh_number']}" in body
    assert parse_meta(body)["links"] == [{"rel": "answers", "to": a["gh_number"]}]

    assert client.delete(f"/api/cards/{b['id']}").status_code == 204
    closed = _issue(fake_gh, b["gh_number"])
    assert closed["state"] == "closed" and closed["state_reason"] == "not_planned"


def test_index_rebuilds_from_github(client, source, labels, session, fake_gh):
    """Wipe Postgres, pull from issues, and get the same cards, spans, topics, blocks and links back."""
    f = client.post("/api/files", json=dict(name="Nuke Aff")).json()
    block = client.post(f"/api/files/{f['id']}/blocks", json=dict(name="Advantage 1")).json()
    cut = client.post(f"/api/sources/{source['id']}/cut", json=dict(
        start_char=0, end_char=ARTICLE.index("\n"), tag="Extinction", block_id=block["id"])).json()
    _label(client, labels, cut, "underline", "soot from burning cities")
    _label(client, labels, cut, "emphasis", "soot")
    other = client.post("/api/cards", json=dict(text="Models overstate soot.", tag="No winter")).json()
    client.post(f"/api/cards/{cut['id']}/approve")
    before = {c["tag"]: c for c in (client.get(f"/api/cards/{x['id']}").json() for x in (cut, other))}
    client.post("/api/graph/edges", json=dict(src_id=before["No winter"]["node_id"],
                                              dst_id=before["Extinction"]["node_id"], relation="contradicts"))

    session.execute(text("TRUNCATE files, blocks, cards, spans, nodes, edges, sources, authors, entities, chunks, jobs "
                         "RESTART IDENTITY CASCADE"))
    session.execute(text("UPDATE app_state SET last_sync_at = NULL"))
    session.commit()
    assert client.get("/api/cards").json() == []

    assert client.post("/api/github/sync").status_code == 202
    after = {c["tag"]: client.get(f"/api/cards/{c['id']}").json() for c in client.get("/api/cards").json()}
    assert set(after) == {"Extinction", "No winter"}
    ext = after["Extinction"]
    assert ext["approved"] and ext["text"] == before["Extinction"]["text"]
    assert ext["topic"]["slug"] == before["Extinction"]["topic"]["slug"]
    assert ext["block_id"] is not None and ext["source_id"] is not None
    gold = lambda c: sorted((s["label"], s["start_tok"], s["end_tok"]) for s in c["spans"] if s["spans_key"] == "sc")  # noqa: E731
    assert gold(ext) == gold(before["Extinction"])
    files = client.get("/api/files").json()["files"]
    assert [(x["name"], [b["name"] for b in x["blocks"]]) for x in files] == [("Nuke Aff", ["Advantage 1"])]
    node = client.get(f"/api/graph/nodes/{after['No winter']['node_id']}").json()
    assert [(e["relation"], e["other"]["title"]) for e in node["outgoing"] if e["relation"] == "contradicts"] == [
        ("contradicts", "Extinction")]
    assert any(e["kind"] == "card.enrich" for e in client.get("/api/jobs", params=dict(card_id=ext["id"])).json())


def test_sign_in_code_is_single_use_and_origin_checked(client):
    from tests.conftest import sign_in

    code = sign_in(client)
    assert client.post("/api/auth/exchange", json={"code": code}).status_code == 401
    r = client.get("/api/auth/login", params={"return_to": "https://evil.example/"}, follow_redirects=False)
    assert r.status_code == 400
    assert client.get("/api/auth/me").json()["login"] == "scythe-dev"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_pages_origin_preflight(client):
    r = client.options("/api/cards", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
        "Access-Control-Request-Private-Network": "true",
    })
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert r.headers["access-control-allow-private-network"] == "true"
    blocked = client.options("/api/cards", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in blocked.headers


def test_github_token_bearer_and_fake_rest_emulator():
    """The Pages flow: a GitHub token works on the local API, and /fakegh speaks GitHub REST."""
    from fastapi.testclient import TestClient

    from scythe.issue_doc import card_body
    from scythe.main import app

    with TestClient(app) as c:
        h = {"Authorization": "Bearer github_pat_fake"}
        assert c.get("/api/auth/me", headers=h).json()["login"] == "scythe-dev"
        meta = {"kind": "card", "text": "Soot blocks sunlight.", "cite": "", "spans": [], "links": [{"rel": "answers", "to": 1}]}
        a = c.post(f"/fakegh/repos/{REPO}/issues", json={"title": "First", "body": "x", "labels": ["scythe:card"]}).json()
        b = c.post(f"/fakegh/repos/{REPO}/issues",
                   json={"title": "Second", "body": card_body(meta), "labels": ["scythe:card", "topic:t"]}).json()
        assert [i["number"] for i in c.get(f"/fakegh/repos/{REPO}/issues", params={"labels": "scythe:card,topic:t"}).json()] == [b["number"]]
        found = c.get("/fakegh/search/issues", params={"q": f'repo:{REPO} is:issue label:"scythe:card" soot'}).json()
        assert [i["number"] for i in found["items"]] == [b["number"]]
        tl = c.get(f"/fakegh/repos/{REPO}/issues/{a['number']}/timeline").json()
        assert tl[0]["source"]["issue"]["number"] == b["number"]
        c.patch(f"/fakegh/repos/{REPO}/issues/{b['number']}", json={"state": "closed"})
        assert c.get(f"/fakegh/repos/{REPO}/issues/{b['number']}").json()["state"] == "closed"
