from tests.conftest import ARTICLE


def test_cut_is_verbatim_and_anchored(client, source):
    passage = "The resulting “nuclear winter” would collapse global agriculture"
    loc = client.post(f"/api/sources/{source['id']}/locate", json=dict(text='The resulting "nuclear  winter" would collapse global agriculture')).json()
    assert ARTICLE[loc["start_char"]:loc["end_char"]] == passage
    card = client.post(f"/api/sources/{source['id']}/cut", json=dict(**loc, tag="Winter kills crops") | {"text": None}).json()
    assert card["text"] == passage
    assert card["cite"].startswith("Robock 22, Alan Robock, Owen Toon")
    card = client.get(f"/api/cards/{card['id']}").json()
    assert card["status"] == "done"

    node = client.get(f"/api/graph/nodes/{card['node_id']}").json()
    excerpts = {e["other"]["kind"]: e for e in node["outgoing"] if e["relation"] == "excerpt_of"}
    assert excerpts["source"]["dst_start"] == loc["start_char"]
    assert excerpts["chunk"]["dst_start"] == 0  # second paragraph chunk starts at the passage

    hood = client.get(f"/api/graph/nodes/{card['node_id']}/neighborhood", params=dict(depth=2)).json()
    kinds = {n["kind"] for n in hood["nodes"]}
    assert {"card", "source", "author", "chunk"} <= kinds

    author = next(n for n in hood["nodes"] if n["kind"] == "author")
    path = client.get("/api/graph/path", params=dict(a=card["node_id"], b=author["id"])).json()
    assert [e["relation"] for e in path["edges"]] == ["excerpt_of", "authored_by"]


def test_graph_search_and_manual_edges(client, source):
    a = client.post(f"/api/sources/{source['id']}/cut", json=dict(start_char=0, end_char=ARTICLE.index("\n"), tag="Extinction")).json()
    b = client.post("/api/cards", json=dict(text="Nuclear winter is a myth; models overstate soot.", tag="No winter")).json()
    a, b = (client.get(f"/api/cards/{x['id']}").json() for x in (a, b))
    r = client.post("/api/graph/edges", json=dict(src_id=b["node_id"], dst_id=a["node_id"], relation="answers"))
    assert r.status_code == 201
    assert client.post("/api/graph/edges", json=dict(src_id=a["node_id"], dst_id=b["node_id"], relation="nope")).status_code == 422
    hits = client.get("/api/graph/search", params=dict(q="soot")).json()
    assert {"card", "source", "chunk"} <= {h["kind"] for h in hits}
    node = client.get(f"/api/graph/nodes/{a['node_id']}").json()
    assert [e["relation"] for e in node["incoming"]] == ["answers"]
    mentioned = {e["other"]["title"] for e in node["outgoing"] if e["relation"] == "mentions"}
    assert "Rutgers University" in mentioned


def test_agentic_chunk_tree(client, source):
    n = len(ARTICLE)
    split = ARTICLE.index("\n\n")
    tree = [{"start_char": 0, "end_char": n, "title": "Whole", "summary": "s",
             "children": [{"start_char": 0, "end_char": split, "propositions": ["Soot blocks sunlight."]},
                          {"start_char": split + 2, "end_char": n}]}]
    r = client.put(f"/api/sources/{source['id']}/chunks", json=dict(strategy="agentic", chunks=tree))
    assert r.status_code == 200, r.text
    chunks = r.json()
    assert [c["level"] for c in chunks] == [0, 1, 1]
    assert chunks[1]["parent_id"] == chunks[0]["id"]
    bad = [{"start_char": 0, "end_char": 10, "children": [{"start_char": 5, "end_char": 20}]}]
    assert client.put(f"/api/sources/{source['id']}/chunks", json=dict(chunks=bad)).status_code == 422
    paragraph = [c for c in client.get(f"/api/sources/{source['id']}").json()["chunks"] if c["strategy"] == "paragraph"]
    assert len(paragraph) == 2 and paragraph[0]["summary"]  # baseline chunks untouched, summarized


def test_card_and_span_search(client, labels):
    texts = ["Nuclear winter collapses agriculture.", "Climate change causes warming.", "Agriculture adapts to warming."]
    ids = [client.post("/api/cards", json=dict(text=t, tag=t.split()[0])).json()["id"] for t in texts]
    i = texts[2].index("adapts")
    client.post(f"/api/cards/{ids[2]}/spans", json=dict(label_id=labels["highlight"]["id"], start_char=i, end_char=i + 6))
    res = client.get("/api/search", params=dict(q="agriculture")).json()
    assert res["total"] == 2 and {r["card"]["id"] for r in res["results"]} == {ids[0], ids[2]}
    assert "⟦" in res["results"][0]["snippet"]
    res = client.get("/api/search", params=dict(q="agriculture", label="highlight")).json()
    assert [r["card"]["id"] for r in res["results"]] == [ids[2]]
    spans = client.get("/api/search", params=dict(q="adapt", scope="spans")).json()
    assert spans["results"][0]["span"]["text"] == "adapts" and spans["results"][0]["left"].startswith("Agriculture")
