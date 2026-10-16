"""Database search over cards and spans (Postgres full-text search)."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..models import Block, Card, Label, Span
from ..schemas import card_out, span_out

router = APIRouter(tags=["search"])

# Sentinel highlight markers (split client-side) instead of HTML, so snippets are never rendered as markup.
HL_OPEN, HL_CLOSE = "⟦", "⟧"
HEADLINE_OPTS = f"StartSel={HL_OPEN}, StopSel={HL_CLOSE}, MaxFragments=2, MinWords=8, MaxWords=30, FragmentDelimiter= … "
CONTEXT_TOKENS = 12


@router.get("/search")
def search(
    q: str = "",
    scope: str = Query("cards", pattern="^(cards|spans)$"),
    label: list[str] | None = Query(None),
    source: list[str] | None = Query(None),
    file_id: int | None = None,
    block_id: int | None = None,
    source_id: int | None = None,
    topic_id: int | None = None,
    accepted: bool | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int = Query(25, le=200),
    offset: int = 0,
    session: Session = Depends(get_session),
):
    tsq = func.websearch_to_tsquery("english", q) if q.strip() else None
    if scope == "spans":
        return _search_spans(session, tsq, label, source, file_id, block_id, source_id, topic_id, accepted, since, until, limit, offset)

    stmt = select(Card).options(selectinload(Card.spans))
    if tsq is not None:
        rank = func.ts_rank(Card.tsv, tsq)
        snippet = func.ts_headline("english", Card.text, tsq, HEADLINE_OPTS)
        stmt = stmt.add_columns(rank, snippet).where(Card.tsv.op("@@")(tsq)).order_by(rank.desc())
    else:
        stmt = stmt.order_by(Card.updated_at.desc())
    if label or source or accepted is not None:
        span_q = select(Span.id).join(Label).where(Span.card_id == Card.id)
        if label:
            span_q = span_q.where(Label.name.in_(label))
        if source:
            span_q = span_q.where(Span.source.in_(source))
        if accepted is not None:
            span_q = span_q.where(Span.accepted.is_(accepted))
        stmt = stmt.where(exists(span_q))
    stmt = _card_filters(stmt, file_id, block_id, source_id, topic_id, since, until)
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = session.execute(stmt.limit(limit).offset(offset)).unique().all()
    results = []
    for row in rows:
        card = row[0]
        results.append({
            "card": card_out(card, tokens=False),
            "rank": float(row[1]) if tsq is not None else None,
            "snippet": row[2] if tsq is not None else None,
        })
    return dict(scope="cards", total=total, results=results, hl=[HL_OPEN, HL_CLOSE])


def _card_filters(stmt, file_id, block_id, source_id, topic_id, since, until):
    if block_id is not None:
        stmt = stmt.where(Card.block_id == block_id)
    if file_id is not None:
        stmt = stmt.where(Card.block_id.in_(select(Block.id).where(Block.file_id == file_id)))
    if source_id is not None:
        stmt = stmt.where(Card.source_id == source_id)
    if topic_id is not None:
        stmt = stmt.where(Card.topic_id == topic_id)
    if since is not None:
        stmt = stmt.where(Card.created_at >= since)
    if until is not None:
        stmt = stmt.where(func.date(Card.created_at) <= until)
    return stmt


def _search_spans(session, tsq, label, source, file_id, block_id, source_id, topic_id, accepted, since, until, limit, offset):
    stmt = select(Span, Card).join(Card, Span.card_id == Card.id).join(Label, Span.label_id == Label.id)
    if tsq is not None:
        rank = func.ts_rank(Span.tsv, tsq)
        stmt = stmt.add_columns(rank).where(Span.tsv.op("@@")(tsq)).order_by(rank.desc())
    else:
        stmt = stmt.order_by(Span.created_at.desc())
    if label:
        stmt = stmt.where(Label.name.in_(label))
    if source:
        stmt = stmt.where(Span.source.in_(source))
    if accepted is not None:
        stmt = stmt.where(Span.accepted.is_(accepted))
    stmt = _card_filters(stmt, file_id, block_id, source_id, topic_id, since, until)
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    results = []
    for row in session.execute(stmt.limit(limit).offset(offset)).all():
        span, card = row[0], row[1]
        toks = card.tokens
        lo, hi = max(0, span.start_tok - CONTEXT_TOKENS), min(len(toks), span.end_tok + CONTEXT_TOKENS)
        left = card.text[toks[lo]["idx"]:span.start_char] if lo < span.start_tok else ""
        right_end = toks[hi - 1]["idx"] + len(toks[hi - 1]["text"]) if hi > span.end_tok else span.end_char
        results.append({
            "span": span_out(span),
            "card": dict(id=card.id, tag=card.tag, cite=card.cite, block_id=card.block_id),
            "left": ("… " if lo > 0 else "") + left,
            "right": card.text[span.end_char:right_end] + (" …" if hi < len(toks) else ""),
            "rank": float(row[2]) if tsq is not None else None,
        })
    return dict(scope="spans", total=total, results=results)
