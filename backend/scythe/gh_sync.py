"""Two-way sync between GitHub issues (truth) and the local Postgres index.

push_*: write a card/source to its issue (creating it, labels and the source sub-issue link).
pull:   rebuild/refresh index rows from issues, re-tokenizing verbatim text with spaCy.
"""

import logging
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import graph, nlp, topics
from .auth import app_state, client_for
from .github import GitHub, GitHubError
from .graph_models import Account, Source
from .issues import (
    APPROVED_LABEL, CARD_LABEL, LABEL_COLORS, SOURCE_LABEL, card_issue, label_names, parse_meta, prefixed,
    sha, source_issue, source_text_path,
)
from .models import Block, Card, File
from .services import add_span, create_card, get_or_create_label

log = logging.getLogger("scythe.github")
_labels_seen: set[tuple[str, str]] = set()


class NotConnected(Exception):
    pass


def connection(session: Session) -> tuple[GitHub, str]:
    state = app_state(session)
    if not state.repo or state.account_id is None:
        raise NotConnected("no repository selected")
    return client_for(session, session.get(Account, state.account_id)), state.repo


def _ensure_labels(gh: GitHub, repo: str, labels: list[str]) -> None:
    for name in labels:
        if (repo, name) in _labels_seen:
            continue
        prefix = name.split(":", 1)[0]
        gh.ensure_label(repo, name, LABEL_COLORS.get(name, LABEL_COLORS.get(prefix, "ededed")))
        _labels_seen.add((repo, name))


# ---------------------------------------------------------------- push


def push_source(session: Session, gh: GitHub, repo: str, source: Source) -> Source:
    text_url = ""
    if source.full_text and not source.text_path:
        source.text_path = source_text_path(source)
        body = f"# {source.title or source.url or 'Source'}\n\n{source.url or ''}\n\n---\n\n{source.full_text}\n"
        text_url = gh.put_file(repo, source.text_path, body, f"scythe: add source text {source.text_path}").get("html_url", "")
    title, body, labels = source_issue(session, source, text_url)
    _ensure_labels(gh, repo, labels)
    if source.gh_number is None:
        issue = gh.create_issue(repo, title, body, labels)
        source.gh_number, source.gh_id, source.gh_url = issue["number"], issue["id"], issue["html_url"]
    else:
        issue = gh.update_issue(repo, source.gh_number, title=title, body=body, labels=labels)
    source.gh_updated_at = issue["updated_at"]
    session.flush()
    return source


def push_card(session: Session, gh: GitHub, repo: str, card: Card) -> Card:
    session.refresh(card, ["spans"])
    source = session.get(Source, card.source_id) if card.source_id else None
    if source is not None and source.gh_number is None:
        push_source(session, gh, repo, source)
    title, body, labels = card_issue(session, card)
    _ensure_labels(gh, repo, labels)
    if card.gh_number is None:
        issue = gh.create_issue(repo, title, body, labels)
        card.gh_number, card.gh_id, card.gh_url = issue["number"], issue["id"], issue["html_url"]
        if source is not None:
            gh.add_sub_issue(repo, source.gh_number, card.gh_id)
    else:
        issue = gh.update_issue(repo, card.gh_number, title=title, body=body, labels=labels)
    card.gh_updated_at = issue["updated_at"]
    card.gh_dirty = False
    session.flush()
    return card


def archive_card(gh: GitHub, repo: str, number: int) -> None:
    """GitHub issues can't be deleted over REST; closing as not-planned archives the card."""
    gh.update_issue(repo, number, state="closed", state_reason="not_planned")


# ---------------------------------------------------------------- pull


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _block_for(session: Session, labels: set[str]) -> Block | None:
    file_name, block_name = prefixed(labels, "file"), prefixed(labels, "block")
    if not file_name or not block_name:
        return None
    f = session.scalar(select(File).where(File.name == file_name))
    if f is None:
        f = File(name=file_name)
        session.add(f)
        session.flush()
    b = session.scalar(select(Block).where(Block.file_id == f.id, Block.name == block_name))
    if b is None:
        b = Block(file_id=f.id, name=block_name, position=len(f.blocks))
        session.add(b)
        session.flush()
    return b


def pull_source(session: Session, gh: GitHub, repo: str, issue: dict) -> Source | None:
    meta = parse_meta(issue.get("body"))
    if not meta or meta.get("kind") != "source":
        return None
    source = session.scalar(select(Source).where(Source.gh_number == issue["number"]))
    if source is not None and source.gh_updated_at == issue["updated_at"]:
        return source
    text = source.full_text if source is not None else ""
    if meta.get("text_path") and (source is None or sha(source.full_text) != meta.get("text_sha")):
        try:
            raw = gh.get_file(repo, meta["text_path"])
            text = raw.split("\n---\n\n", 1)[1].rstrip("\n") if "\n---\n\n" in raw else raw
        except GitHubError as e:
            log.warning("source #%s text unavailable: %s", issue["number"], e)
    if source is None:
        info = graph.SourceInfo(
            url=meta.get("url"), title=meta.get("title", ""), publisher=meta.get("publisher", ""),
            published=_date(meta.get("published")), authors=tuple(meta.get("authors", [])), full_text=text,
            kind=meta.get("source_kind", "article"), cite=meta.get("cite", ""), key=meta.get("key") or f"gh:{issue['number']}",
        )
        source = graph.upsert_source(session, info, provenance="import")
    else:
        source.title, source.publisher = meta.get("title", ""), meta.get("publisher", "")
        source.published = _date(meta.get("published"))
        if text and text != source.full_text:
            source.full_text = text
    source.gh_number, source.gh_id, source.gh_url = issue["number"], issue["id"], issue["html_url"]
    source.gh_updated_at, source.text_path = issue["updated_at"], meta.get("text_path", "")
    session.flush()
    return source


def pull_card(session: Session, issue: dict) -> tuple[Card | None, bool]:
    """Upsert one card from its issue. Returns (card, changed). Closed issues leave the index."""
    meta = parse_meta(issue.get("body"))
    if not meta or meta.get("kind") != "card":
        return None, False
    card = session.scalar(select(Card).where(Card.gh_number == issue["number"]))
    if issue.get("state") == "closed":
        if card is not None:
            session.delete(card)
        return None, card is not None
    if card is not None and card.gh_updated_at == issue["updated_at"]:
        return card, False
    if card is not None and card.gh_dirty:
        log.warning("card #%s changed on GitHub and locally; GitHub wins", issue["number"])
    labels = label_names(issue)
    block = _block_for(session, labels)
    topic = topics.from_meta(session, prefixed(labels, "topic") or (meta.get("topic") or {}).get("slug"), meta.get("topic"))
    source_id = None
    if meta.get("source"):
        source_id = session.scalar(select(Source.id).where(Source.gh_number == meta["source"]))
    text = meta["text"]
    if card is None or card.text != text:
        if card is not None:
            session.delete(card)
            session.flush()
        card = create_card(session, text, tag=issue["title"], cite=meta.get("cite", ""), url=meta.get("url", ""),
                           block_id=block.id if block else None, source_id=source_id,
                           topic_id=topic.id if topic else None)
    else:
        card.tag, card.cite, card.url = issue["title"], meta.get("cite", ""), meta.get("url", "")
        card.block_id, card.source_id = (block.id if block else None), source_id
        card.topic_id = topic.id if topic else None
        for s in list(card.spans):
            if s.label.spans_key != "ents" and not (s.source == "model" and not s.accepted):
                session.delete(s)
        session.flush()
    processed_model = (meta.get("processed") or {}).get("model") or meta.get("spacy_model")
    same_tokens = processed_model == card.spacy_model
    for sp in meta.get("spans", []):
        if sp.get("key") == "ents":
            continue  # the index derives entities itself
        label = get_or_create_label(session, sp["label"], sp.get("key", "sc"))
        try:
            if same_tokens and "start" in sp:
                add_span(session, card, label, start_tok=sp["start"], end_tok=sp["end"], source=sp.get("src", "manual"),
                         score=sp.get("score"))
            else:  # different tokenizer version: re-snap by characters
                add_span(session, card, label, start_char=sp["start_char"], end_char=sp["end_char"],
                         source=sp.get("src", "manual"), score=sp.get("score"))
        except ValueError as e:
            log.warning("card #%s: dropped span %s: %s", issue["number"], sp, e)
    card.approved = APPROVED_LABEL in labels
    card.gh_number, card.gh_id, card.gh_url = issue["number"], issue["id"], issue["html_url"]
    card.gh_updated_at, card.gh_dirty = issue["updated_at"], False
    graph.card_node(session, card)
    session.flush()
    return card, True


def pull_links(session: Session, card: Card, meta: dict) -> None:
    cnode = graph.card_node(session, card)
    for link in meta.get("links", []):
        target = session.scalar(select(Card).where(Card.gh_number == link["to"]))
        node_id = graph.card_node(session, target).id if target is not None else session.scalar(
            select(Source.node_id).where(Source.gh_number == link["to"]))
        if node_id:
            graph.link(session, cnode.id, node_id, link["rel"], provenance="import")


def pull(session: Session, full: bool = False) -> dict:
    """Refresh the index from GitHub. Incremental (issues updated since the last sync) unless `full`."""
    gh, repo = connection(session)
    state = app_state(session)
    since = None if full or state.last_sync_at is None else state.last_sync_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    started = datetime.now(UTC)
    stats = {"sources": 0, "cards": 0, "removed": 0}
    for issue in gh.list_issues(repo, SOURCE_LABEL, since):
        if pull_source(session, gh, repo, issue):
            stats["sources"] += 1
    changed: list[tuple[Card, dict]] = []
    for issue in gh.list_issues(repo, CARD_LABEL, since):
        card, did_change = pull_card(session, issue)
        if card is None and did_change:
            stats["removed"] += 1
        elif card is not None and did_change:
            changed.append((card, parse_meta(issue["body"])))
    for card, meta in changed:  # second pass: link targets now exist
        pull_links(session, card, meta)
    stats["cards"] = len(changed)
    state.last_sync_at, state.last_sync_error = started, ""
    session.flush()
    stats["changed_card_ids"] = [c.id for c, _ in changed]
    return stats
