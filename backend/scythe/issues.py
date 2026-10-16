"""How cards and sources are written into GitHub issues, and read back.

A card issue looks like:

    title:  <tag>
    body:   **Head 24**, rest of cite
            <card text, formatting as <ins>/<mark>/**>      (rendered for people on GitHub)
            Answers #7                                      (typed links -> GitHub backlinks)
            <!-- scythe:v1 {...} -->                        (machine truth: verbatim text, spans, links)
    labels: scythe:card, file:<name>, block:<name>, approved

The hidden JSON block is authoritative; the visible Markdown is regenerated from it on every push,
so hand edits to the visible part on GitHub are overwritten (edit the card in Scythe instead).
"""

import hashlib
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .graph_models import Author, Edge, Node, Source
from .markdown import body_markdown, cite_markdown, escape
from .models import ENTS_KEY, Card

CARD_LABEL, SOURCE_LABEL, APPROVED_LABEL = "scythe:card", "scythe:source", "approved"
LABEL_COLORS = {CARD_LABEL: "1c1d1f", SOURCE_LABEL: "6b6f76", APPROVED_LABEL: "2f5d62", "file": "e6e3dc",
                "block": "f7f6f2", "topic": "c9d6d8"}
# Relations shown as typed links between issues (structural/derived ones live in the index only).
LINK_RELATIONS = {"derived_from", "cites", "quotes", "supports", "contradicts", "answers", "elaborates", "same_claim", "related"}
META_RE = re.compile(r"<!-- scythe:v1\n(.*?)\n-->", re.S)
MAX_LABEL = 50


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _meta_block(meta: dict) -> str:
    # "<" and ">" only occur inside JSON strings, where \\u003c / \\u003e are equivalent; this keeps
    # the payload from ever closing the HTML comment.
    payload = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
    return "<!-- scythe:v1\n" + payload.replace("<", "\\u003c").replace(">", "\\u003e") + "\n-->"


def parse_meta(body: str | None) -> dict | None:
    m = META_RE.search(body or "")
    return json.loads(m.group(1)) if m else None


def label_names(issue: dict) -> set[str]:
    return {lb["name"] if isinstance(lb, dict) else lb for lb in issue.get("labels", [])}


def prefixed(labels: set[str], prefix: str) -> str | None:
    for name in labels:
        if name.startswith(prefix + ":"):
            return name[len(prefix) + 1:]
    return None


def _clip(label: str) -> str:
    return label[:MAX_LABEL]


def card_labels(card: Card) -> list[str]:
    labels = [CARD_LABEL]
    if card.topic is not None:
        labels.append(f"topic:{card.topic.slug}")
    if card.block is not None:
        labels += [_clip(f"file:{card.block.file.name}"), _clip(f"block:{card.block.name}")]
    if card.approved:
        labels.append(APPROVED_LABEL)
    return labels


def card_links(session: Session, card: Card) -> list[dict]:
    """Outgoing typed edges from this card to other issue-backed nodes."""
    if card.node_id is None:
        return []
    rows = session.execute(
        select(Edge, Node).join(Node, Node.id == Edge.dst_id)
        .where(Edge.src_id == card.node_id, Edge.relation.in_(LINK_RELATIONS)).order_by(Edge.id)
    ).all()
    out = []
    for edge, node in rows:
        number = _issue_number(session, node)
        if number:
            out.append({"rel": edge.relation, "to": number})
    return out


def _issue_number(session: Session, node: Node) -> int | None:
    if node.kind == "card":
        return session.scalar(select(Card.gh_number).where(Card.node_id == node.id))
    if node.kind == "source":
        return session.scalar(select(Source.gh_number).where(Source.node_id == node.id))
    return None


def card_issue(session: Session, card: Card) -> tuple[str, str, list[str]]:
    spans = [s for s in card.spans if s.accepted and s.label.spans_key != ENTS_KEY]
    source = session.get(Source, card.source_id) if card.source_id else None
    links = card_links(session, card)
    meta = {
        "kind": "card",
        "text": card.text,
        "cite": card.cite,
        "url": card.url,
        "source": source.gh_number if source else None,
        "spacy_model": card.spacy_model,
        "topic": {k: getattr(card.topic, k) for k in ("slug", "event", "season", "period", "resolution")}
        if card.topic else None,
        "spans": [
            {"label": s.label.name, "key": s.label.spans_key, "start": s.start_tok, "end": s.end_tok,
             "start_char": s.start_char, "end_char": s.end_char, "src": s.source,
             **({"score": s.score} if s.score is not None else {})}
            for s in sorted(spans, key=lambda s: (s.start_tok, s.end_tok, s.label.name))
        ],
        "links": links,
    }
    parts = []
    if card.cite:
        parts.append(cite_markdown(card.cite))
    parts.append(body_markdown(card, flavor="github"))
    if links:
        parts.append("\n".join(f"{link['rel'].replace('_', ' ').capitalize()} #{link['to']}" for link in links))
    parts.append(_meta_block(meta))
    return (card.tag or card.text[:80]).strip(), "\n\n".join(p for p in parts if p) + "\n", card_labels(card)


def source_authors(session: Session, source: Source) -> list[str]:
    return list(session.scalars(
        select(Author.name).join(Edge, Edge.dst_id == Author.node_id)
        .where(Edge.src_id == source.node_id, Edge.relation == "authored_by").order_by(Edge.id)
    ))


def source_issue(session: Session, source: Source, text_url: str = "") -> tuple[str, str, list[str]]:
    authors = source_authors(session, source)
    meta = {
        "kind": "source",
        "url": source.url,
        "title": source.title,
        "publisher": source.publisher,
        "published": source.published.isoformat() if source.published else None,
        "authors": authors,
        "source_kind": source.kind,
        "text_path": source.text_path,
        "text_sha": sha(source.full_text),
        "cite": source.meta.get("cite", ""),
        "key": source.meta.get("key", ""),
    }
    line = ", ".join(escape(x) for x in [", ".join(authors), source.publisher,
                                         source.published.isoformat() if source.published else ""] if x)
    parts = [line] if line else []
    if source.url:
        parts.append(source.url)
    if source.text_path:
        link = f"[{source.text_path}]({text_url})" if text_url else f"`{source.text_path}`"
        parts.append(f"Full text: {link} · {len(source.full_text):,} characters")
    parts.append(_meta_block(meta))
    title = source.title or source.meta.get("cite") or source.url or "Untitled source"
    return title.strip()[:256], "\n\n".join(parts) + "\n", [SOURCE_LABEL]


def source_text_path(source: Source) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (source.title or source.url or "source").lower()).strip("-")[:60] or "source"
    return f"sources/{slug}-{sha(source.url or source.full_text)[:8]}.md"
