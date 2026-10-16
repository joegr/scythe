def _span(client, card_id, label_id, text, card_text):
    i = card_text.index(text)
    r = client.post(f"/api/cards/{card_id}/spans", json=dict(label_id=label_id, start_char=i, end_char=i + len(text)))
    assert r.status_code == 201, r.text


def test_nested_markdown_and_condensed(client, labels):
    text = "Soot from cities would block sunlight for a decade.\n\nCrops * fail."
    card = client.post("/api/cards", json=dict(text=text, tag="Soot = winter", cite="Robock 22, Rutgers")).json()
    _span(client, card["id"], labels["underline"]["id"], "Soot from cities would block sunlight", text)
    _span(client, card["id"], labels["highlight"]["id"], "block sunlight", text)
    _span(client, card["id"], labels["emphasis"]["id"], "sunlight", text)
    md = client.get(f"/api/cards/{card['id']}.md").text
    assert md.startswith("#### Soot \\= winter\n\n**Robock 22**, Rutgers\n\n")
    assert "<u>Soot from cities would ==block **sunlight**==</u> for a decade." in md
    assert "Crops \\* fail." in md  # card text is escaped
    condensed = client.get(f"/api/cards/{card['id']}.md", params=dict(condensed=True)).text
    assert condensed.rstrip().endswith("<u>Soot from cities would ==block **sunlight**==</u>")
    fm = client.get(f"/api/cards/{card['id']}.md", params=dict(frontmatter=True)).text
    assert fm.startswith(f"---\ncard_id: {card['id']}\n")


def test_urls_are_not_escaped(client):
    card = client.post("/api/cards", json=dict(text="See a_b.", cite="Wiki 02, https://en.wikipedia.org/wiki/Nuclear_winter")).json()
    md = client.get(f"/api/cards/{card['id']}.md").text
    assert "https://en.wikipedia.org/wiki/Nuclear_winter" in md and "See a\\_b." in md
