"""Git files -> issues: the spaCy worker reads cards/ and sources/ and rewrites their issues."""

import json

import spacy

from scythe import action
from scythe.github import FakeGitHub
from scythe.issue_doc import card_file, meta_block, parse_meta, source_file

REPO = "scythe-dev/cards"
TEXT = "Alan Robock of Rutgers found that soot from burning cities would block sunlight."
NLP = spacy.load("en_core_web_sm")


def _write(root, path, content):
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(content)


def _card(n, spans, source=None, title="Soot blocks sunlight", **kw):
    return {"issue": n, "title": title, "topic": {"slug": "cx-2025-26-exploration-development-arctic"}, "file": kw.get("file"),
            "block": kw.get("block"), "approved": kw.get("approved", False), "cite": "Robock 22, Rutgers", "url": "",
            "source": source, "links": kw.get("links", []), "spans": spans, "text": TEXT}


def test_card_file_becomes_processed_issue(tmp_path):
    gh = FakeGitHub(None, repos=(REPO,))
    src = gh.create_issue(REPO, "placeholder", "", ["scythe:source"])
    card = gh.create_issue(REPO, "placeholder", "", ["scythe:card", "keep-me"])
    _write(tmp_path, f"sources/{src['number']}.md", source_file(
        {"issue": src["number"], "title": "Nuclear winter", "url": "https://x.org", "publisher": "Nature Food",
         "published": "2022-08-15", "authors": ["Alan Robock"], "cite": "", "fetched": None}, "Intro.\n\n" + TEXT))
    i = TEXT.index("soot")
    _write(tmp_path, f"cards/{card['number']}.md", card_file(_card(card["number"], [
        {"label": "underline", "key": "sc", "style": "underline", "start_char": i + 1, "end_char": i + 13, "src": "manual"}],
        source=src["number"], file="Aff", block="Adv 1", approved=True, links=[{"rel": "answers", "to": 99}])))

    done = action.run(gh, REPO, [("A", f"cards/{card['number']}.md"), ("A", f"sources/{src['number']}.md")], tmp_path, lambda: NLP)
    assert done[0].endswith(f"sources/{src['number']}.md")  # sources first

    issue = gh.get_issue(REPO, card["number"])
    meta = parse_meta(issue["body"])
    under = [s for s in meta["spans"] if s["key"] == "sc"][0]
    assert TEXT[under["start_char"]:under["end_char"]] == "soot from burning" and under["start"] < under["end"]
    assert any(s["key"] == "ents" and s["label"] == "PERSON" for s in meta["spans"])
    assert meta["processed"]["model"].startswith("en_core_web_sm") and meta["path"] == f"cards/{card['number']}.md"
    assert issue["title"] == "Soot blocks sunlight" and "<ins>soot from burning</ins>" in issue["body"] and "Answers #99" in issue["body"]
    assert {lb["name"] for lb in issue["labels"]} == {"scythe:card", "topic:cx-2025-26-exploration-development-arctic",
                                                       "file:Aff", "block:Adv 1", "approved", "keep-me"}
    assert card["id"] in gh.get_issue(REPO, src["number"])["sub_issues"]
    src_meta = parse_meta(gh.get_issue(REPO, src["number"])["body"])
    assert src_meta["text_path"] == f"sources/{src['number']}.md" and src_meta["authors"] == ["Alan Robock"]

    action.run(gh, REPO, [("D", f"cards/{card['number']}.md")], tmp_path, lambda: NLP)
    assert gh.get_issue(REPO, card["number"])["state"] == "closed"


def test_meta_block_cannot_close_comment():
    block = meta_block({"text": "a --> b <!-- c"})
    assert block.count("-->") == 1 and json.loads(block.split("\n")[1])["text"] == "a --> b <!-- c"
