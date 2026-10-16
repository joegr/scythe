"""End-to-end active-learning loop: label -> train spancat -> suggest -> accept."""

from scythe import suggest, train
from scythe.config import settings

SENTS = [
    "Nuclear winter would collapse global agriculture within two years.",
    "Warming would collapse global agriculture across the tropics.",
    "Soot would collapse global agriculture and starve billions.",
    "Drought would collapse global agriculture in a decade.",
]
PHRASE = "collapse global agriculture"


def test_train_and_suggest(client, labels, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "models_dir", tmp_path)
    for text in SENTS * 3:
        card = client.post("/api/cards", json=dict(text=text)).json()
        i = text.index(PHRASE)
        client.post(f"/api/cards/{card['id']}/spans",
                    json=dict(label_id=labels["underline"]["id"], start_char=i, end_char=i + len(PHRASE)))
    out = train.main(["--max-steps", "60", "--output", str(tmp_path / "run")])
    assert suggest.active_model() == out
    info = client.get("/api/model").json()["active"]
    assert info["status"] == "done" and "underline" in info["labels"]

    target = client.post("/api/cards", json=dict(text="Famine would collapse global agriculture soon.")).json()
    r = client.post(f"/api/cards/{target['id']}/suggest", params=dict(threshold=0.0))
    assert r.status_code == 200, r.text
    pending = [s for s in r.json()["card"]["spans"] if s["source"] == "model"]
    assert pending and all(not s["accepted"] and s["score"] is not None for s in pending)

    client.post(f"/api/cards/{target['id']}/spans/accept-all")
    spans = client.get(f"/api/cards/{target['id']}").json()["spans"]
    assert all(s["accepted"] for s in spans if s["spans_key"] == "sc")
