from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import gh_sync, graph, jobs, spacy_io, topics
from ..github import GitHubError
from ..db import get_session
from ..graph_models import Job, Node
from ..markdown import card_markdown
from ..models import Card, Label, Span
from ..schemas import CardIn, CardPatch, SpanIn, SpanPatch, card_out, job_out, span_out
from ..services import add_span, create_card

router = APIRouter(tags=["cards"])


def card_status(session: Session, card_id: int) -> str:
    status = session.scalar(select(Job.status).where(Job.card_id == card_id).order_by(Job.id.desc()).limit(1))
    return status or "done"


def load_card(session: Session, card_id: int) -> Card:
    card = session.scalar(select(Card).options(selectinload(Card.spans)).where(Card.id == card_id))
    if card is None:
        raise HTTPException(404, "card not found")
    return card


@router.get("/cards")
def list_cards(
    block_id: int | None = None,
    loose: bool = False,
    source_id: int | None = None,
    topic_id: int | None = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    session: Session = Depends(get_session),
):
    stmt = select(Card).options(selectinload(Card.spans))
    if block_id is not None:
        stmt = stmt.where(Card.block_id == block_id).order_by(Card.position, Card.id)
    else:
        if loose:
            stmt = stmt.where(Card.block_id.is_(None))
        stmt = stmt.order_by(Card.updated_at.desc())
    if source_id is not None:
        stmt = stmt.where(Card.source_id == source_id)
    if topic_id is not None:
        stmt = stmt.where(Card.topic_id == topic_id)
    return [card_out(c, tokens=False) for c in session.scalars(stmt.limit(limit).offset(offset))]


@router.post("/cards", status_code=201)
def create(body: CardIn, session: Session = Depends(get_session)):
    topic = topics.require_topic(session, body.topic_id)
    card = create_card(session, body.text, tag=body.tag, cite=body.cite, url=body.url, block_id=body.block_id,
                       topic_id=topic.id)
    session.commit()
    jobs.enqueue_card(session, card.id)
    return card_out(load_card(session, card.id), status="queued")


@router.get("/cards/{card_id:int}")
def get_card(card_id: int, session: Session = Depends(get_session)):
    return card_out(load_card(session, card_id), status=card_status(session, card_id))


@router.patch("/cards/{card_id:int}")
def update_card(card_id: int, body: CardPatch, session: Session = Depends(get_session)):
    card = load_card(session, card_id)
    if body.topic_id is not None:
        topics.require_topic(session, body.topic_id)
    for k, v in body.model_dump(exclude_none=True, exclude={"clear_block"}).items():
        setattr(card, k, v)
    if body.clear_block:
        card.block_id = None
    if card.node_id:
        graph.card_node(session, card)
    session.commit()
    jobs.push_card(session, card_id)
    return card_out(load_card(session, card_id), status=card_status(session, card_id))


@router.post("/cards/{card_id:int}/approve")
def approve(card_id: int, approved: bool = True, session: Session = Depends(get_session)):
    """Approval is the `approved` label on the card's issue."""
    card = load_card(session, card_id)
    card.approved = approved
    session.commit()
    jobs.push_card(session, card_id)
    return card_out(load_card(session, card_id), status=card_status(session, card_id))


@router.delete("/cards/{card_id:int}", status_code=204)
def delete_card(card_id: int, session: Session = Depends(get_session)):
    card = load_card(session, card_id)
    if card.gh_number is not None:
        try:
            gh, repo = gh_sync.connection(session)
            gh_sync.archive_card(gh, repo, card.gh_number)
        except (gh_sync.NotConnected, GitHubError) as e:
            raise HTTPException(502, f"could not close the GitHub issue: {e}") from e
    if card.node_id:
        session.delete(session.get(Node, card.node_id))
    session.delete(card)
    session.commit()


@router.get("/cards/{card_id:int}.md", response_class=PlainTextResponse)
def markdown(card_id: int, condensed: bool = False, frontmatter: bool = False, session: Session = Depends(get_session)):
    md = card_markdown(load_card(session, card_id), condensed=condensed, frontmatter=frontmatter)
    return PlainTextResponse(md, media_type="text/markdown")


@router.get("/cards/{card_id:int}/doc.json")
def doc_json(card_id: int, session: Session = Depends(get_session)):
    """The card as `spacy.tokens.Doc.to_json()` (all accepted span groups and ents)."""
    card = load_card(session, card_id)
    f = spacy_io.ExportFilter(only_labeled=False)
    doc = spacy_io.card_to_doc(card, spacy_io.selected_spans(card, f))
    return {**doc.to_json(), "scythe": doc.user_data["scythe"]}


@router.get("/jobs")
def list_jobs(card_id: int | None = None, source_id: int | None = None, session: Session = Depends(get_session)):
    stmt = select(Job).order_by(Job.id.desc()).limit(50)
    if card_id is not None:
        stmt = stmt.where(Job.card_id == card_id)
    if source_id is not None:
        stmt = stmt.where(Job.source_id == source_id)
    return [job_out(j) for j in session.scalars(stmt)]


# ---------------------------------------------------------------- spans


@router.post("/cards/{card_id:int}/spans", status_code=201)
def create_span(card_id: int, body: SpanIn, session: Session = Depends(get_session)):
    card = load_card(session, card_id)
    label = session.get(Label, body.label_id) or _404("label")
    try:
        span = add_span(session, card, label, start_tok=body.start_tok, end_tok=body.end_tok,
                        start_char=body.start_char, end_char=body.end_char)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if span is None:
        raise HTTPException(422, "selection covers no tokens")
    session.commit()
    out = span_out(span)
    jobs.push_card(session, card_id)
    return out


@router.patch("/spans/{span_id:int}")
def update_span(span_id: int, body: SpanPatch, session: Session = Depends(get_session)):
    span = session.get(Span, span_id) or _404("span")
    if body.label_id is not None:
        span.label = session.get(Label, body.label_id) or _404("label")
    if body.accepted is not None:
        span.accepted = body.accepted
        if body.accepted and span.source == "model":
            span.source = "manual"  # accepted suggestions count as gold
    session.commit()
    out = span_out(span)
    jobs.push_card(session, span.card_id)
    return out


@router.delete("/spans/{span_id:int}", status_code=204)
def delete_span(span_id: int, session: Session = Depends(get_session)):
    span = session.get(Span, span_id) or _404("span")
    card_id = span.card_id
    session.delete(span)
    session.commit()
    jobs.push_card(session, card_id)


@router.post("/cards/{card_id:int}/spans/accept-all")
def accept_all(card_id: int, session: Session = Depends(get_session)):
    card = load_card(session, card_id)
    for s in card.spans:
        if s.source == "model" and not s.accepted:
            s.accepted, s.source = True, "manual"
    session.commit()
    jobs.push_card(session, card_id)
    return card_out(load_card(session, card_id), tokens=False)


def _404(what: str):
    raise HTTPException(404, f"{what} not found")
