"""Request bodies and response serializers."""

from datetime import date

from pydantic import BaseModel, Field

from .graph_models import Chunk, Edge, Job, Node, Source
from .models import Card, Label, Span
from .topics import topic_out


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)


class BlockPatch(BaseModel):
    name: str | None = None
    position: int | None = None
    file_id: int | None = None


class CardIn(BaseModel):
    text: str = Field(min_length=1)
    topic_id: int | None = None
    tag: str = ""
    cite: str = ""
    url: str = ""
    block_id: int | None = None


class CardPatch(BaseModel):
    topic_id: int | None = None
    tag: str | None = None
    cite: str | None = None
    block_id: int | None = None
    position: int | None = None
    clear_block: bool = False


class SpanIn(BaseModel):
    label_id: int
    start_char: int | None = None
    end_char: int | None = None
    start_tok: int | None = None
    end_tok: int | None = None


class SpanPatch(BaseModel):
    accepted: bool | None = None
    label_id: int | None = None


class LabelIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    spans_key: str = "sc"
    color: str = "#6c757d"
    hotkey: str | None = None
    style: str = "custom"


class LabelPatch(BaseModel):
    name: str | None = None
    color: str | None = None
    hotkey: str | None = None
    style: str | None = None


class FetchIn(BaseModel):
    url: str


class PasteSourceIn(BaseModel):
    text: str = Field(min_length=1)
    title: str = ""
    url: str | None = None
    publisher: str = ""
    published: date | None = None
    authors: list[str] = []
    is_html: bool = False


class LocateIn(BaseModel):
    text: str


class CutIn(BaseModel):
    topic_id: int | None = None
    start_char: int
    end_char: int
    tag: str = ""
    cite: str | None = None
    block_id: int | None = None


class ChunkTreeIn(BaseModel):
    strategy: str = "agentic"
    chunks: list[dict]


class EdgeIn(BaseModel):
    src_id: int
    dst_id: int
    relation: str
    src_start: int | None = None
    src_end: int | None = None
    dst_start: int | None = None
    dst_end: int | None = None
    confidence: float = 1.0
    props: dict = {}


# ---------------------------------------------------------------- serializers


def label_out(lbl: Label) -> dict:
    return dict(id=lbl.id, name=lbl.name, spans_key=lbl.spans_key, color=lbl.color, hotkey=lbl.hotkey, style=lbl.style)


def span_out(s: Span) -> dict:
    return dict(
        id=s.id, card_id=s.card_id, label_id=s.label_id, label=s.label.name, spans_key=s.label.spans_key,
        start_tok=s.start_tok, end_tok=s.end_tok, start_char=s.start_char, end_char=s.end_char, text=s.text,
        source=s.source, score=s.score, accepted=s.accepted,
    )


def card_out(c: Card, *, tokens: bool = True, status: str | None = None) -> dict:
    out = dict(
        id=c.id, block_id=c.block_id, position=c.position, tag=c.tag, cite=c.cite, url=c.url, text=c.text,
        spacy_model=c.spacy_model, node_id=c.node_id, source_id=c.source_id, approved=c.approved,
        topic=topic_out(c.topic),
        gh_number=c.gh_number, gh_url=c.gh_url, gh_synced=not c.gh_dirty and c.gh_number is not None,
        created_at=c.created_at, updated_at=c.updated_at,
        spans=[span_out(s) for s in c.spans],
    )
    if tokens:
        out["tokens"] = c.tokens
    if status is not None:
        out["status"] = status
    return out


def source_out(s: Source, *, full_text: bool = True) -> dict:
    out = dict(
        id=s.id, node_id=s.node_id, kind=s.kind, title=s.title, url=s.url, publisher=s.publisher,
        published=s.published, meta=s.meta, created_at=s.created_at, length=len(s.full_text),
        gh_number=s.gh_number, gh_url=s.gh_url, text_path=s.text_path,
    )
    if full_text:
        out["full_text"] = s.full_text
    return out


def chunk_out(c: Chunk) -> dict:
    return dict(
        id=c.id, node_id=c.node_id, source_id=c.source_id, parent_id=c.parent_id, strategy=c.strategy,
        level=c.level, ordinal=c.ordinal, start_char=c.start_char, end_char=c.end_char,
        title=c.title, summary=c.summary, propositions=c.propositions, meta=c.meta,
    )


def node_out(n: Node, **extra) -> dict:
    return dict(id=n.id, kind=n.kind, title=n.title, body=n.body, props=n.props, **extra)


def edge_out(e: Edge) -> dict:
    return dict(
        id=e.id, src_id=e.src_id, dst_id=e.dst_id, relation=e.relation, src_start=e.src_start, src_end=e.src_end,
        dst_start=e.dst_start, dst_end=e.dst_end, confidence=e.confidence, provenance=e.provenance, props=e.props,
    )


def job_out(j: Job) -> dict:
    return dict(id=j.id, kind=j.kind, card_id=j.card_id, source_id=j.source_id, status=j.status,
                error=j.error, created_at=j.created_at, finished_at=j.finished_at)


class RepoIn(BaseModel):
    repo: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
