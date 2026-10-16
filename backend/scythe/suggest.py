"""Load the newest trained spancat model and turn its predictions into pending spans."""

import json
from functools import lru_cache
from pathlib import Path

import spacy
from sqlalchemy.orm import Session

from . import nlp
from .config import settings
from .models import Card
from .services import add_span, get_or_create_label


def model_dirs() -> list[Path]:
    if not settings.models_dir.exists():
        return []
    return sorted((p for p in settings.models_dir.iterdir() if p.is_dir()), reverse=True)


def active_model() -> Path | None:
    for d in model_dirs():
        if (d / "model-best" / "meta.json").exists():
            return d
    return None


def model_info(d: Path) -> dict:
    info = {"name": d.name, "path": str(d), "ready": (d / "model-best" / "meta.json").exists()}
    if (d / "scythe.json").exists():
        info.update(json.loads((d / "scythe.json").read_text()))
    if info["ready"]:
        meta = json.loads((d / "model-best" / "meta.json").read_text())
        info["performance"] = meta.get("performance", {})
        info["labels"] = meta.get("labels", {}).get("spancat", [])
    return info


@lru_cache(maxsize=2)
def _load(path: str):
    return spacy.load(path)


def suggest(session: Session, card: Card, threshold: float | None = None) -> int:
    """Replace the card's pending model spans with fresh predictions. Returns the number added."""
    d = active_model()
    if d is None:
        raise LookupError("no trained model; run `make train`")
    pipe = _load(str(d / "model-best"))
    spans_key = pipe.get_pipe("spancat").key
    for s in list(card.spans):
        if s.source == "model" and not s.accepted:
            session.delete(s)
    session.flush()
    session.expire(card, ["spans"])
    doc = pipe(nlp.doc_from_tokens(card.tokens, pipe.vocab))
    group = doc.spans.get(spans_key, [])
    scores = group.attrs.get("scores") if len(group) else None
    added = 0
    for i, sp in enumerate(group):
        score = float(scores[i]) if scores is not None else None
        if threshold is not None and score is not None and score < threshold:
            continue
        label = get_or_create_label(session, sp.label_, spans_key)
        if add_span(session, card, label, start_tok=sp.start, end_tok=sp.end, source="model", score=score,
                    accepted=False):
            added += 1
    return added
