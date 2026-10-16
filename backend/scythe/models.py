"""Postgres schema. Spans are stored token-aligned (spaCy Span semantics: end_tok exclusive)."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SPAN_SOURCES = ("manual", "ner", "model", "import")
LABEL_STYLES = ("underline", "highlight", "emphasis", "tag", "cite", "custom")
ENTS_KEY = "ents"  # pseudo spans_key: spans under it round-trip through doc.ents


class Base(DeclarativeBase):
    pass


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    blocks: Mapped[list["Block"]] = relationship(
        back_populates="file", cascade="all, delete-orphan", order_by="Block.position"
    )


class Block(Base):
    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    position: Mapped[int] = mapped_column(Integer, default=0)

    file: Mapped[File] = relationship(back_populates="blocks")
    cards: Mapped[list["Card"]] = relationship(back_populates="block", order_by="Card.position")


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    block_id: Mapped[int | None] = mapped_column(
        ForeignKey("blocks.id", ondelete="SET NULL"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    tag: Mapped[str] = mapped_column(Text, default="")
    cite: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text)
    # [{"i", "idx", "text", "ws"}] exactly as spaCy tokenized it, so Doc(words, spaces) rebuilds `text`.
    tokens: Mapped[list[dict]] = mapped_column(JSONB)
    spacy_model: Mapped[str] = mapped_column(String(200), default="")
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"), unique=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"), index=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="RESTRICT"), index=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # GitHub issue backing this card (the source of truth); null until the first push lands.
    gh_number: Mapped[int | None] = mapped_column(Integer, unique=True)
    gh_id: Mapped[int | None] = mapped_column(BigInteger)
    gh_url: Mapped[str] = mapped_column(Text, default="", server_default="")
    gh_updated_at: Mapped[str] = mapped_column(String(40), default="", server_default="")
    gh_dirty: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    tsv = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(tag, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(cite, '')), 'B') || "
            "setweight(to_tsvector('english', coalesce(text, '')), 'C')",
            persisted=True,
        ),
    )

    block: Mapped[Block | None] = relationship(back_populates="cards")
    source: Mapped["Source | None"] = relationship()  # noqa: F821
    topic: Mapped["Topic | None"] = relationship(lazy="joined")  # noqa: F821
    spans: Mapped[list["Span"]] = relationship(
        back_populates="card", cascade="all, delete-orphan", order_by="Span.start_tok"
    )

    __table_args__ = (Index("ix_cards_tsv", "tsv", postgresql_using="gin"),)


class Label(Base):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    spans_key: Mapped[str] = mapped_column(String(100), default="sc")
    color: Mapped[str] = mapped_column(String(20), default="#6c757d")
    hotkey: Mapped[str | None] = mapped_column(String(5))
    style: Mapped[str] = mapped_column(String(20), default="custom")

    __table_args__ = (UniqueConstraint("name", "spans_key"),)


class Span(Base):
    __tablename__ = "spans"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id", ondelete="CASCADE"), index=True)
    label_id: Mapped[int] = mapped_column(ForeignKey("labels.id", ondelete="CASCADE"), index=True)
    start_tok: Mapped[int] = mapped_column(Integer)
    end_tok: Mapped[int] = mapped_column(Integer)
    start_char: Mapped[int] = mapped_column(Integer)
    end_char: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), default="manual", index=True)
    score: Mapped[float | None] = mapped_column(Float)
    accepted: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tsv = mapped_column(TSVECTOR, Computed("to_tsvector('english', text)", persisted=True))

    card: Mapped[Card] = relationship(back_populates="spans")
    label: Mapped[Label] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("card_id", "label_id", "start_tok", "end_tok"),
        Index("ix_spans_tsv", "tsv", postgresql_using="gin"),
    )


DEFAULT_LABELS = [
    dict(name="underline", spans_key="sc", color="#212529", hotkey="1", style="underline"),
    dict(name="highlight", spans_key="sc", color="#5ce1e6", hotkey="2", style="highlight"),
    dict(name="emphasis", spans_key="sc", color="#0d6efd", hotkey="3", style="emphasis"),
    dict(name="tag", spans_key="sc", color="#6f42c1", hotkey="4", style="tag"),
    dict(name="cite", spans_key="sc", color="#fd7e14", hotkey="5", style="cite"),
]


from . import graph_models  # noqa: E402,F401  (registers graph tables on Base.metadata)
