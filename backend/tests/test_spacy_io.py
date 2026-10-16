import io
import json
import zipfile

from spacy.tokens import DocBin

from scythe import nlp

TEXT = "Alan Robock of Rutgers found that nuclear winter would collapse global agriculture."


def _card_with_spans(client, labels):
    card = client.post("/api/cards", json=dict(text=TEXT, tag="Winter", cite="Robock 22")).json()
    custom = client.post("/api/labels", json=dict(name="CLAIM", spans_key="arg")).json()
    for label_id, phrase in [
        (labels["underline"]["id"], "nuclear winter would collapse global agriculture"),
        (labels["highlight"]["id"], "collapse global agriculture"),
        (custom["id"], "nuclear winter would collapse"),
    ]:
        i = TEXT.index(phrase)
        client.post(f"/api/cards/{card['id']}/spans", json=dict(label_id=label_id, start_char=i, end_char=i + len(phrase)))
    return client.get(f"/api/cards/{card['id']}").json()


def _signature(doc):
    return (
        doc.text,
        {k: sorted((s.start, s.end, s.label_) for s in g) for k, g in doc.spans.items()},
        sorted((e.start, e.end, e.label_) for e in doc.ents),
    )


def test_docbin_roundtrip(client, labels):
    card = _card_with_spans(client, labels)
    assert any(s["spans_key"] == "ents" for s in card["spans"]), "background NER should have run"
    data = client.get("/api/spacy/export.spacy").content
    docs = list(DocBin().from_bytes(data).get_docs(nlp.get_nlp().vocab))
    assert len(docs) == 1
    original = docs[0]
    assert original.user_data["scythe"]["card_id"] == card["id"]
    assert set(original.spans) == {"sc", "arg"}
    assert original.ents

    r = client.post("/api/spacy/import", files={"file": ("x.spacy", data)})
    assert r.status_code == 201, r.text
    new_id = r.json()["card_ids"][0]
    again = client.get("/api/spacy/export.spacy", params=dict(card_id=new_id)).content
    reimported = next(DocBin().from_bytes(again).get_docs(nlp.get_nlp().vocab))
    assert _signature(reimported) == _signature(original)
    assert reimported.user_data["scythe"]["tag"] == "Winter"


def test_docjson_and_prodigy_roundtrip(client, labels):
    card = _card_with_spans(client, labels)
    ref = next(DocBin().from_bytes(client.get("/api/spacy/export.spacy").content).get_docs(nlp.get_nlp().vocab))
    for fmt in ("docjson", "prodigy"):
        body = client.get("/api/spacy/export.jsonl", params=dict(format=fmt, card_id=card["id"])).content
        line = json.loads(body.splitlines()[0])
        if fmt == "prodigy":
            assert {"text", "tokens", "spans", "meta"} <= set(line)
        r = client.post("/api/spacy/import", files={"file": (f"x.{fmt}.jsonl", body)})
        assert r.status_code == 201, r.text
        new_id = r.json()["card_ids"][0]
        out = client.get("/api/spacy/export.spacy", params=dict(card_id=new_id)).content
        doc = next(DocBin().from_bytes(out).get_docs(nlp.get_nlp().vocab))
        assert _signature(doc) == _signature(ref), fmt


def test_doc_json_endpoint_and_training_bundle(client, labels):
    card = _card_with_spans(client, labels)
    dj = client.get(f"/api/cards/{card['id']}/doc.json").json()
    assert dj["text"] == TEXT and "sc" in dj["spans"] and dj["scythe"]["card_id"] == card["id"]
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/spacy/training-bundle.zip").content))
    assert {"config.cfg", "train.spacy", "dev.spacy", "README.txt"} <= set(z.namelist())
    assert "spacy.ngram_range_suggester.v1" in z.read("config.cfg").decode()
