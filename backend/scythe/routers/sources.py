"""Reader-mode sources and verbatim card cutting."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import graph, jobs, reader, topics
from ..db import get_session
from ..graph_models import Author, Edge, Source
from ..schemas import ChunkTreeIn, CutIn, FetchIn, LocateIn, PasteSourceIn, chunk_out, source_out
from ..services import create_card
from .cards import card_out, load_card

router = APIRouter(tags=["sources"])


def _authors(session: Session, source: Source) -> list[str]:
    return list(
        session.scalars(
            select(Author.name).join(Edge, Edge.dst_id == Author.node_id)
            .where(Edge.src_id == source.node_id, Edge.relation == "authored_by").order_by(Edge.id)
        )
    )


def _reader_out(session: Session, source: Source) -> dict:
    authors = _authors(session, source)
    return {
        **source_out(source),
        "authors": authors,
        "default_cite": source.meta.get("cite")
        or reader.default_cite(source.title, authors, source.publisher, source.published, source.url),
    }


@router.post("/reader/extract")
def extract(body: FetchIn):
    """Stateless reader for the Pages app: fetch a URL and return sanitized text + metadata. The
    browser saves it as a source issue; nothing is stored here."""
    try:
        info = reader.fetch(body.url)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return dict(url=info.url, title=info.title, publisher=info.publisher,
                published=info.published.isoformat() if info.published else None, authors=list(info.authors),
                text=info.full_text,
                default_cite=reader.default_cite(info.title, list(info.authors), info.publisher, info.published, info.url))


@router.post("/sources/fetch", status_code=201)
def fetch_source(body: FetchIn, session: Session = Depends(get_session)):
    existing = session.scalar(select(Source).where(Source.url == body.url))
    if existing is not None and existing.full_text:
        return _reader_out(session, existing)
    try:
        info = reader.fetch(body.url)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    source = graph.upsert_source(session, info)
    session.commit()
    jobs.enqueue_source(session, source.id)
    return _reader_out(session, source)


@router.post("/sources/paste", status_code=201)
def paste_source(body: PasteSourceIn, session: Session = Depends(get_session)):
    if body.is_html:
        try:
            info = reader.extract(body.text, body.url)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
    else:
        info = graph.SourceInfo(full_text=reader.sanitize_text(body.text))
    info.url = body.url or info.url
    info.title = body.title or info.title
    info.publisher = body.publisher or info.publisher
    info.published = body.published or info.published
    info.authors = tuple(body.authors) or info.authors
    if not info.url and not info.title:
        info.title = info.full_text[:80]
    if not info.url:
        info.key = f"pasted:{info.title}"
    source = graph.upsert_source(session, info)
    session.commit()
    jobs.enqueue_source(session, source.id)
    return _reader_out(session, source)


@router.get("/sources")
def list_sources(q: str | None = None, limit: int = Query(50, le=200), session: Session = Depends(get_session)):
    stmt = select(Source).order_by(Source.created_at.desc())
    if q:
        tsq = func.websearch_to_tsquery("english", q)
        stmt = select(Source).where(Source.tsv.op("@@")(tsq)).order_by(func.ts_rank(Source.tsv, tsq).desc())
    return [source_out(s, full_text=False) for s in session.scalars(stmt.limit(limit))]


@router.get("/sources/{source_id:int}")
def get_source(source_id: int, session: Session = Depends(get_session)):
    source = session.get(Source, source_id) or _404()
    out = _reader_out(session, source)
    out["chunks"] = [chunk_out(c) for c in source.chunks]
    return out


@router.post("/sources/{source_id:int}/locate")
def locate(source_id: int, body: LocateIn, session: Session = Depends(get_session)):
    """Anchor a copy-pasted passage to exact offsets in the source's reader text."""
    source = session.get(Source, source_id) or _404()
    found = reader.locate(source.full_text, body.text)
    if found is None:
        raise HTTPException(404, "passage not found in source text")
    start, end = found
    return dict(start_char=start, end_char=end, text=source.full_text[start:end])


@router.post("/sources/{source_id:int}/cut", status_code=201)
def cut(source_id: int, body: CutIn, session: Session = Depends(get_session)):
    """Create a card whose text is exactly source.full_text[start:end] (trimmed of outer whitespace)."""
    source = session.get(Source, source_id) or _404()
    topic = topics.require_topic(session, body.topic_id)
    start, end = body.start_char, body.end_char
    if not (0 <= start < end <= len(source.full_text)):
        raise HTTPException(422, "range outside source text")
    raw = source.full_text[start:end]
    start += len(raw) - len(raw.lstrip())
    end -= len(raw) - len(raw.rstrip())
    if start >= end:
        raise HTTPException(422, "empty selection")
    cite = body.cite if body.cite is not None else _reader_out(session, source)["default_cite"]
    card = create_card(session, source.full_text[start:end], tag=body.tag, cite=cite, url=source.url or "",
                       block_id=body.block_id, source_id=source.id, topic_id=topic.id)
    graph.link(session, graph.card_node(session, card).id, source.node_id, "excerpt_of",
               src_range=(0, end - start), dst_range=(start, end), provenance="manual")
    session.commit()
    jobs.enqueue_card(session, card.id)  # anchors excerpt_of edges, NER, entities
    return card_out(load_card(session, card.id), status="queued")


@router.put("/sources/{source_id:int}/chunks")
def put_chunks(source_id: int, body: ChunkTreeIn, session: Session = Depends(get_session)):
    """Replace chunks of one strategy with a nested tree. This is the write path for agentic chunkers:
    [{start_char, end_char, title?, summary?, propositions?, meta?, children?: [...]}]."""
    source = session.get(Source, source_id) or _404()
    try:
        chunks = graph.replace_chunks(session, source, body.chunks, strategy=body.strategy)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, str(e)) from e
    session.commit()
    return [chunk_out(c) for c in chunks]


def _404():
    raise HTTPException(404, "source not found")
