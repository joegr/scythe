"""Knowledge graph: every addressable thing (source, author, card, chunk, entity) is a `Node`;
typed, directed `Edge`s connect them. Typed tables (sources, chunks, ...) hold the payload and
point at their node row, so graph traversal is a single recursive CTE over `edges`.

Relation vocabulary (edge direction reads "src <relation> dst"):

  structural    part_of        chunk -> chunk | chunk -> source   (chunk hierarchy)
                excerpt_of     card -> source | card -> chunk     (card text cut from source text; char anchors)
                derived_from   card -> card                       (recut / re-tag of another card)
  provenance    authored_by    source -> author
                published_in   source -> source                   (article -> journal / outlet)
                cites          source|card|chunk -> source        (bibliographic citation)
                quotes         card|chunk -> card|chunk|source    (verbatim reuse of another text)
  semantic      mentions       card|chunk|source -> entity        (NER / entity linking)
                supports       card|chunk -> card|chunk           (argumentative)
                contradicts    card|chunk -> card|chunk
                answers        card -> card                       (debate response: turns, no-links)
                elaborates     card|chunk -> card|chunk
                same_claim     card|chunk -> card|chunk           (paraphrase / duplicate; symmetric)
                related        any -> any                         (untyped, low-confidence fallback)

Edges carry optional character anchors on both ends (src_start/src_end, dst_start/dst_end)
so "this card's underlined text came from chars 1200-1840 of that source" is queryable.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    LargeBinary,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .models import Base

NODE_KINDS = ("source", "author", "card", "chunk", "entity")
RELATIONS = {
    "structural": ("part_of", "excerpt_of", "derived_from"),
    "provenance": ("authored_by", "published_in", "cites", "quotes"),
    "semantic": ("mentions", "supports", "contradicts", "answers", "elaborates", "same_claim", "related"),
}
ALL_RELATIONS = tuple(r for group in RELATIONS.values() for r in group)
SYMMETRIC = {"same_claim", "related"}
PROVENANCE = ("manual", "ingest", "import", "ner", "model", "agent")
SOURCE_KINDS = ("article", "journal", "book", "report", "website", "study", "transcript", "other")


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    # short searchable text for the node (card tag+cite, chunk summary, author name, ...)
    body: Mapped[str] = mapped_column(Text, default="")
    props: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tsv = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(body, '')), 'B')",
            persisted=True,
        ),
    )

    __table_args__ = (
        CheckConstraint(f"kind IN {NODE_KINDS}", name="ck_nodes_kind"),
        Index("ix_nodes_tsv", "tsv", postgresql_using="gin"),
    )


class Edge(Base):
    __tablename__ = "edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    src_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    dst_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    relation: Mapped[str] = mapped_column(String(30), index=True)
    src_start: Mapped[int | None] = mapped_column(Integer)
    src_end: Mapped[int | None] = mapped_column(Integer)
    dst_start: Mapped[int | None] = mapped_column(Integer)
    dst_end: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    provenance: Mapped[str] = mapped_column(String(10), default="manual")
    props: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    src: Mapped[Node] = relationship(foreign_keys=[src_id])
    dst: Mapped[Node] = relationship(foreign_keys=[dst_id])

    __table_args__ = (
        UniqueConstraint("src_id", "dst_id", "relation", name="uq_edges_src_dst_rel"),
        CheckConstraint(f"relation IN {ALL_RELATIONS}", name="ck_edges_relation"),
        CheckConstraint("src_id <> dst_id", name="ck_edges_no_self_loop"),
    )


class Source(Base):
    """A publication a card can be cut from. `full_text` is the extracted article body."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), unique=True)
    kind: Mapped[str] = mapped_column(String(20), default="article")
    title: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str | None] = mapped_column(Text, unique=True)
    publisher: Mapped[str] = mapped_column(Text, default="")
    published: Mapped[date | None] = mapped_column(Date)
    full_text: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    gh_number: Mapped[int | None] = mapped_column(Integer, unique=True)
    gh_id: Mapped[int | None] = mapped_column(BigInteger)
    gh_url: Mapped[str] = mapped_column(Text, default="", server_default="")
    gh_updated_at: Mapped[str] = mapped_column(String(40), default="", server_default="")
    text_path: Mapped[str] = mapped_column(Text, default="", server_default="")  # repo file holding full_text
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tsv = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(publisher, '')), 'B') || "
            "setweight(to_tsvector('english', coalesce(full_text, '')), 'D')",
            persisted=True,
        ),
    )

    node: Mapped[Node] = relationship()
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", order_by="Chunk.start_char"
    )

    __table_args__ = (Index("ix_sources_tsv", "tsv", postgresql_using="gin"),)


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(Text)
    norm_name: Mapped[str] = mapped_column(Text, unique=True)  # lowercased, whitespace-collapsed
    qualifications: Mapped[str] = mapped_column(Text, default="")

    node: Mapped[Node] = relationship()


class Entity(Base):
    """A named entity (spaCy label + normalized surface form); target of `mentions` edges."""

    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), unique=True)
    label: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(Text)
    norm_name: Mapped[str] = mapped_column(Text)
    kb_id: Mapped[str] = mapped_column(Text, default="")  # spaCy Span.kb_id_ for entity linking

    node: Mapped[Node] = relationship()

    __table_args__ = (UniqueConstraint("label", "norm_name"),)


class Chunk(Base):
    """A contiguous region of a source's full_text, arranged as a tree (parent_id).

    `strategy` records how it was produced ("paragraph" baseline now; "agentic" later), and
    `level` its depth (0 = top-level section). Agentic chunkers can fill `title`, `summary` and
    `propositions` (atomic claims) without schema changes.
    """

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), unique=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), index=True)
    strategy: Mapped[str] = mapped_column(String(30), default="paragraph")
    level: Mapped[int] = mapped_column(Integer, default=0)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    start_char: Mapped[int] = mapped_column(Integer)
    end_char: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    propositions: Mapped[list] = mapped_column(JSONB, default=list)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))

    node: Mapped[Node] = relationship()
    source: Mapped[Source] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_chunks_source_span", "source_id", "start_char", "end_char"),
    )


JOB_STATUSES = ("queued", "running", "done", "failed")


class Job(Base):
    """Background enrichment work (NER, graph indexing, chunking, summaries) for a card or source."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="queued", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Account(Base):
    """A GitHub user who signed in through the GitHub App. Tokens are Fernet-encrypted at rest."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    gh_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    login: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(Text, default="")
    avatar_url: Mapped[str] = mapped_column(Text, default="")
    token_enc: Mapped[bytes] = mapped_column(LargeBinary)
    refresh_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the cookie value
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginCode(Base):
    """One-time code handed to the frontend after OAuth (in the URL fragment), exchanged once for a
    session token via POST so the token itself never appears in a URL. Lives for 60 seconds."""

    __tablename__ = "login_codes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256 of the code
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AppState(Base):
    """Single row: which repo this local index mirrors, and whose token background sync uses."""

    __tablename__ = "app_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    repo: Mapped[str] = mapped_column(String(200), default="")
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[str] = mapped_column(Text, default="")
    syncing: Mapped[bool] = mapped_column(Boolean, default=False)
    # Last topic used to cut a card; pre-selected next time. Null -> the UI prompts for one.
    current_topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"))


TOPIC_EVENTS = ("policy", "ld", "pf", "bq", "custom")


class Topic(Base):
    """A debate resolution every card is filed under. NSDA past topics are seeded from
    `scythe/data/nsda_topics.json`; users can add custom ones. On GitHub: label `topic:<slug>`."""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(44), unique=True)
    event: Mapped[str] = mapped_column(String(10), index=True)
    season: Mapped[str] = mapped_column(String(20), default="")
    period: Mapped[str] = mapped_column(String(60), default="")
    resolution: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(10), default="nsda")  # nsda | custom | github
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint(f"event IN {TOPIC_EVENTS}", name="ck_topics_event"),)
