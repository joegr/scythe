"""Card and span persistence shared by the routers, importers and the suggester."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from . import nlp
from .models import DEFAULT_LABELS, Card, Label, Span

LABEL_PALETTE = ["#198754", "#d63384", "#20c997", "#6610f2", "#dc3545", "#ffc107", "#0dcaf0"]


def seed_labels(session: Session) -> None:
    for spec in DEFAULT_LABELS:
        stmt = insert(Label).values(**spec).on_conflict_do_nothing(index_elements=["name", "spans_key"])
        session.execute(stmt)
    session.commit()


def get_or_create_label(session: Session, name: str, spans_key: str = "sc") -> Label:
    label = session.scalar(select(Label).where(Label.name == name, Label.spans_key == spans_key))
    if label is None:
        count = session.query(Label).count()
        label = Label(
            name=name,
            spans_key=spans_key,
            color=LABEL_PALETTE[count % len(LABEL_PALETTE)],
            style="custom",
        )
        session.add(label)
        session.flush()
    return label


def create_card(
    session: Session,
    text: str,
    *,
    tag: str = "",
    cite: str = "",
    url: str = "",
    block_id: int | None = None,
    source_id: int | None = None,
    topic_id: int | None = None,
    tokens: list[dict] | None = None,
) -> Card:
    """Create a card synchronously with tokenizer-only processing so it can be shown at once.

    NER, graph indexing and summaries run later in a background job (see `jobs.enqueue_card`).
    The tokenizer is the first stage of the full pipeline, so token indices stay valid when the
    job runs the remaining components over `doc_from_tokens(card.tokens)`.
    """
    if tokens is None:
        tokens = nlp.tokens_of(nlp.get_nlp().make_doc(text))
    position = 0
    if block_id is not None:
        position = (
            session.scalar(
                select(Card.position).where(Card.block_id == block_id).order_by(Card.position.desc())
            )
            or 0
        ) + 1
    card = Card(
        text=text,
        tokens=tokens,
        tag=tag,
        cite=cite,
        url=url,
        block_id=block_id,
        source_id=source_id,
        topic_id=topic_id,
        position=position,
        spacy_model=nlp.model_id(),
    )
    session.add(card)
    session.flush()
    return card


def add_span(
    session: Session,
    card: Card,
    label: Label,
    *,
    start_tok: int | None = None,
    end_tok: int | None = None,
    start_char: int | None = None,
    end_char: int | None = None,
    source: str = "manual",
    score: float | None = None,
    accepted: bool = True,
) -> Span | None:
    """Insert (or update) a token-aligned span. Char ranges are expanded to token boundaries."""
    if start_tok is None or end_tok is None:
        if start_char is None or end_char is None:
            raise ValueError("need token or char offsets")
        snapped = nlp.snap(card.tokens, start_char, end_char)
        if snapped is None:
            return None
        start_tok, end_tok = snapped
    if not (0 <= start_tok < end_tok <= len(card.tokens)):
        raise ValueError(f"token range {start_tok}:{end_tok} out of bounds")
    s_char, e_char = nlp.char_bounds(card.tokens, start_tok, end_tok)
    existing = session.scalar(
        select(Span).where(
            Span.card_id == card.id,
            Span.label_id == label.id,
            Span.start_tok == start_tok,
            Span.end_tok == end_tok,
        )
    )
    if existing is not None:
        # A manual or accepted re-label wins over a pending model suggestion.
        if accepted and not existing.accepted:
            existing.accepted, existing.source = True, source
        if score is not None:
            existing.score = score
        return existing
    span = Span(
        card_id=card.id,
        label_id=label.id,
        label=label,
        start_tok=start_tok,
        end_tok=end_tok,
        start_char=s_char,
        end_char=e_char,
        text=card.text[s_char:e_char],
        source=source,
        score=score,
        accepted=accepted,
    )
    session.add(span)
    session.flush()
    return span
