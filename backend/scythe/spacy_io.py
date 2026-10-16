"""Lossless conversion between Scythe cards and spaCy data formats.

Supported formats:
- DocBin (`.spacy`): span groups in `doc.spans[key]`, NER in `doc.ents`, card metadata in
  `doc.user_data["scythe"]`. Directly consumable by `spacy train`.
- Doc JSON lines: one `Doc.to_json()` object per line plus a `"scythe"` metadata key.
- Prodigy-style JSONL: {"text", "tokens", "spans", "meta"} with inclusive `token_end`.
"""

import json
import random
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from spacy.tokens import Doc, DocBin
from spacy.tokens import Span as SpacySpan
from spacy.util import filter_spans
from spacy.vocab import Vocab

from . import nlp
from .models import ENTS_KEY, Block, Card, Label, Span
from .services import add_span, create_card, get_or_create_label


@dataclass
class ExportFilter:
    card_ids: list[int] | None = None
    file_id: int | None = None
    block_id: int | None = None
    labels: list[str] | None = None
    spans_keys: list[str] | None = None
    sources: list[str] | None = None
    accepted_only: bool = True
    only_labeled: bool = True  # skip cards with no matching spans


def query_cards(session: Session, f: ExportFilter) -> list[Card]:
    stmt = select(Card).options(selectinload(Card.spans)).order_by(Card.id)
    if f.card_ids:
        stmt = stmt.where(Card.id.in_(f.card_ids))
    if f.block_id is not None:
        stmt = stmt.where(Card.block_id == f.block_id)
    if f.file_id is not None:
        stmt = stmt.join(Block, Card.block_id == Block.id).where(Block.file_id == f.file_id)
    return list(session.scalars(stmt))


def selected_spans(card: Card, f: ExportFilter) -> list[Span]:
    out = []
    for s in card.spans:
        if f.accepted_only and not s.accepted:
            continue
        if f.labels and s.label.name not in f.labels:
            continue
        if f.spans_keys and s.label.spans_key not in f.spans_keys:
            continue
        if f.sources and s.source not in f.sources:
            continue
        out.append(s)
    return out


def card_meta(card: Card) -> dict:
    return {
        "card_id": card.id,
        "tag": card.tag,
        "cite": card.cite,
        "url": card.url,
        "spacy_model": card.spacy_model,
        "topic": card.topic.slug if card.topic else None,
    }


def card_to_doc(card: Card, spans: Iterable[Span], vocab: Vocab | None = None) -> Doc:
    doc = nlp.doc_from_tokens(card.tokens, vocab)
    groups: dict[str, list[SpacySpan]] = {}
    scores: dict[str, list[float | None]] = {}
    ents: list[SpacySpan] = []
    for s in sorted(spans, key=lambda s: (s.start_tok, s.end_tok)):
        sp = SpacySpan(doc, s.start_tok, s.end_tok, label=s.label.name)
        if s.label.spans_key == ENTS_KEY:
            ents.append(sp)
        else:
            groups.setdefault(s.label.spans_key, []).append(sp)
            scores.setdefault(s.label.spans_key, []).append(s.score)
    for key, group in groups.items():
        doc.spans[key] = group
        if any(v is not None for v in scores[key]):
            doc.spans[key].attrs["scores"] = [v if v is not None else 1.0 for v in scores[key]]
    if ents:
        doc.ents = filter_spans(ents)  # doc.ents cannot overlap
    doc.user_data["scythe"] = card_meta(card)
    return doc


def iter_docs(session: Session, f: ExportFilter, vocab: Vocab | None = None) -> Iterator[Doc]:
    for card in query_cards(session, f):
        spans = selected_spans(card, f)
        if f.only_labeled and not spans:
            continue
        yield card_to_doc(card, spans, vocab)


def export_docbin(session: Session, f: ExportFilter) -> bytes:
    db = DocBin(store_user_data=True)
    for doc in iter_docs(session, f):
        db.add(doc)
    return db.to_bytes()


def split_docbins(session: Session, f: ExportFilter, dev_ratio: float = 0.2, seed: int = 0):
    docs = list(iter_docs(session, f))
    random.Random(seed).shuffle(docs)
    n_dev = max(1, round(len(docs) * dev_ratio)) if len(docs) > 1 else 0
    dev, train = docs[:n_dev], docs[n_dev:]
    if not dev:  # a single doc: evaluate on it rather than fail
        dev = train
    return DocBin(store_user_data=True, docs=train), DocBin(store_user_data=True, docs=dev), len(train), len(dev)


def export_docjson(session: Session, f: ExportFilter) -> Iterator[str]:
    for doc in iter_docs(session, f):
        obj = doc.to_json()
        obj["scythe"] = doc.user_data.get("scythe", {})
        yield json.dumps(obj, ensure_ascii=False) + "\n"


def export_prodigy(session: Session, f: ExportFilter) -> Iterator[str]:
    for card in query_cards(session, f):
        spans = selected_spans(card, f)
        if f.only_labeled and not spans:
            continue
        obj = {
            "text": card.text,
            "tokens": [
                {"text": t["text"], "start": t["idx"], "end": t["idx"] + len(t["text"]), "id": t["i"], "ws": bool(t["ws"])}
                for t in card.tokens
            ],
            "spans": [
                {
                    "start": s.start_char,
                    "end": s.end_char,
                    "token_start": s.start_tok,
                    "token_end": s.end_tok - 1,  # Prodigy token_end is inclusive
                    "label": s.label.name,
                    **({"spans_key": s.label.spans_key} if s.label.spans_key != "sc" else {}),
                    **({"score": s.score} if s.score is not None else {}),
                }
                for s in sorted(spans, key=lambda s: s.start_tok)
            ],
            "meta": card_meta(card),
        }
        yield json.dumps(obj, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------- import


@dataclass
class ImportResult:
    card_ids: list[int] = field(default_factory=list)
    spans: int = 0


def _meta_fields(meta: dict) -> dict:
    return {k: str(meta.get(k) or "") for k in ("tag", "cite", "url")}


def _topic_id(session: Session, meta: dict, default_topic_id: int | None) -> int:
    from .graph_models import Topic

    slug = meta.get("topic")
    if slug:
        tid = session.scalar(select(Topic.id).where(Topic.slug == slug))
        if tid:
            return tid
    if default_topic_id is None:
        raise ValueError("topic_required: pass topic_id or include scythe.topic in each doc")
    return default_topic_id


def import_doc(session: Session, doc: Doc, meta: dict | None, block_id: int | None, result: ImportResult,
               default_topic_id: int | None = None) -> Card:
    meta = meta if meta is not None else doc.user_data.get("scythe", {})
    card = create_card(
        session,
        doc.text,
        tokens=nlp.tokens_of(doc),
        block_id=block_id,
        topic_id=_topic_id(session, meta, default_topic_id),
        **_meta_fields(meta),
    )
    for key, group in doc.spans.items():
        scores = group.attrs.get("scores")
        for i, sp in enumerate(group):
            label = get_or_create_label(session, sp.label_, key)
            score = float(scores[i]) if scores is not None and i < len(scores) else None
            if add_span(session, card, label, start_tok=sp.start, end_tok=sp.end, source="import", score=score):
                result.spans += 1
    for ent in doc.ents:
        label = get_or_create_label(session, ent.label_, ENTS_KEY)
        if add_span(session, card, label, start_tok=ent.start, end_tok=ent.end, source="import"):
            result.spans += 1
    result.card_ids.append(card.id)
    return card


def import_docbin(session: Session, data: bytes, block_id: int | None = None,
                  default_topic_id: int | None = None) -> ImportResult:
    result = ImportResult()
    vocab = nlp.get_nlp().vocab
    for doc in DocBin().from_bytes(data).get_docs(vocab):
        import_doc(session, doc, None, block_id, result, default_topic_id)
    return result


def import_jsonl(session: Session, data: bytes, block_id: int | None = None,
                 default_topic_id: int | None = None) -> ImportResult:
    """Accepts both `Doc.to_json()` lines and Prodigy-style lines, detected per line."""
    result = ImportResult()
    vocab = nlp.get_nlp().vocab
    for line in data.decode("utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        is_docjson = "scythe" in obj or "sents" in obj or isinstance(obj.get("spans"), dict)
        if is_docjson:
            meta = obj.pop("scythe", {})
            doc = Doc(vocab).from_json(obj)
            import_doc(session, doc, meta, block_id, result, default_topic_id)
        else:
            _import_prodigy_line(session, obj, block_id, result, default_topic_id)
    return result


def _import_prodigy_line(session: Session, obj: dict, block_id: int | None, result: ImportResult,
                         default_topic_id: int | None = None) -> None:
    text = obj["text"]
    meta = obj.get("meta") or {}
    toks = obj.get("tokens")
    if toks:
        tokens = []
        for i, t in enumerate(toks):
            ws = t.get("ws")
            if ws is None:  # infer from offsets
                nxt = toks[i + 1]["start"] if i + 1 < len(toks) else len(text)
                ws = nxt > t["end"]
            tokens.append({"i": i, "idx": t["start"], "text": t["text"], "ws": " " if ws else ""})
        card = create_card(session, text, tokens=tokens, block_id=block_id,
                           topic_id=_topic_id(session, meta, default_topic_id), **_meta_fields(meta))
    else:
        card = create_card(session, text, block_id=block_id,
                           topic_id=_topic_id(session, meta, default_topic_id), **_meta_fields(meta))
    for s in obj.get("spans") or []:
        label = get_or_create_label(session, s["label"], s.get("spans_key", "sc"))
        if toks and "token_start" in s and "token_end" in s:
            span = add_span(session, card, label, start_tok=s["token_start"], end_tok=s["token_end"] + 1,
                            source="import", score=s.get("score"))
        else:
            span = add_span(session, card, label, start_char=s["start"], end_char=s["end"],
                            source="import", score=s.get("score"))
        if span:
            result.spans += 1
    result.card_ids.append(card.id)


def labels_by_key(session: Session) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for label in session.scalars(select(Label).order_by(Label.id)):
        out.setdefault(label.spans_key, []).append(label.name)
    return out
