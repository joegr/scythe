"""Background enrichment run after a card/source is shown: NER, graph indexing, chunk summaries.

Summaries are an extractive baseline (spaCy sentence + noun-chunk salience) so agentic chunking
has `title`, `summary` and `propositions` to start from and can overwrite them later.
"""

from collections import Counter

from sqlalchemy.orm import Session

from . import graph, nlp
from .graph_models import Chunk, Node, Source
from .models import ENTS_KEY, Card
from .services import add_span, get_or_create_label

SUMMARIZER = "extractive-v1"


def enrich_card(session: Session, card: Card) -> None:
    """Run the full pipeline over the stored tokens, persist NER spans, index into the graph."""
    pipe = nlp.get_nlp()
    doc = pipe(nlp.doc_from_tokens(card.tokens, pipe.vocab))
    for ent in doc.ents:
        label = get_or_create_label(session, ent.label_, ENTS_KEY)
        add_span(session, card, label, start_tok=ent.start, end_tok=ent.end, source="ner")
    session.flush()
    graph.index_card(session, card)


def summarize(text: str) -> tuple[str, str, list[str]]:
    """Return (title, summary, propositions) for a chunk of text."""
    doc = nlp.get_nlp()(text)
    sents = [s.text.strip() for s in doc.sents if s.text.strip()]
    phrases = Counter(
        " ".join(t.text for t in nc if not (t.is_stop or t.is_punct)).lower()
        for nc in doc.noun_chunks
        if nc.root.pos_ in ("NOUN", "PROPN") and not nc.root.is_stop
    )
    phrases.pop("", None)
    weights = Counter(t.lemma_.lower() for t in doc if t.pos_ in ("NOUN", "PROPN", "VERB", "ADJ") and not t.is_stop)
    title = phrases.most_common(1)[0][0] if phrases else (sents[0][:80] if sents else "")
    best = max(
        doc.sents,
        key=lambda s: sum(weights[t.lemma_.lower()] for t in s) / (len(s) ** 0.5 or 1),
        default=None,
    )
    return title, best.text.strip() if best is not None else "", sents


def enrich_source(session: Session, source: Source) -> None:
    if source.full_text and not source.chunks:
        graph.paragraph_chunks(session, source)
        session.refresh(source, ["chunks"])
    pipe = nlp.get_nlp()
    for chunk in source.chunks:
        if chunk.meta.get("summarizer") or chunk.strategy != "paragraph":
            continue  # never overwrite agentic output
        title, summary, props = summarize(chunk.text)
        chunk.title, chunk.summary, chunk.propositions = title, summary, props
        chunk.meta = {**chunk.meta, "summarizer": SUMMARIZER}
        node = session.get(Node, chunk.node_id)
        node.title, node.body = title, summary
        _link_chunk_entities(session, chunk, pipe(chunk.text))
    session.flush()


def _link_chunk_entities(session: Session, chunk: Chunk, doc) -> None:
    for ent in doc.ents:
        entity = graph.get_or_create_entity(session, ent.label_, ent.text)
        graph.link(session, chunk.node_id, entity.node_id, "mentions",
                   src_range=(ent.start_char, ent.end_char), provenance="ner")
