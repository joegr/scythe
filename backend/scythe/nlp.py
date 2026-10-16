"""spaCy core: one shared pipeline, token storage, and token-aligned span snapping.

Cards persist the exact tokenization spaCy produced (`words` + trailing whitespace), so a
`Doc` can always be rebuilt losslessly with `doc_from_tokens` regardless of which pipeline
version is loaded later.
"""

from bisect import bisect_left, bisect_right
from functools import lru_cache

import spacy
from spacy.language import Language
from spacy.tokens import Doc
from spacy.vocab import Vocab

from .config import settings


@lru_cache
def get_nlp() -> Language:
    return spacy.load(settings.spacy_model)


def model_id(nlp: Language | None = None) -> str:
    nlp = nlp or get_nlp()
    return f"{nlp.meta['lang']}_{nlp.meta['name']}-{nlp.meta['version']}"


def analyze(text: str) -> Doc:
    """Run the full base pipeline (tokenizer, tagger, parser, NER...)."""
    return get_nlp()(text)


def tokens_of(doc: Doc) -> list[dict]:
    return [{"i": t.i, "idx": t.idx, "text": t.text, "ws": t.whitespace_} for t in doc]


def doc_from_tokens(tokens: list[dict], vocab: Vocab | None = None) -> Doc:
    vocab = vocab or get_nlp().vocab
    return Doc(vocab, words=[t["text"] for t in tokens], spaces=[bool(t["ws"]) for t in tokens])


def snap(tokens: list[dict], start_char: int, end_char: int) -> tuple[int, int] | None:
    """Expand a character range to the tokens it touches.

    Mirrors `doc.char_span(start, end, alignment_mode="expand")`: any token overlapping
    [start_char, end_char) is included. Returns (start_tok, end_tok) with end exclusive, or
    None when the range covers no token (e.g. pure whitespace).
    """
    if not tokens or end_char <= start_char:
        return None
    ends = [t["idx"] + len(t["text"]) for t in tokens]
    starts = [t["idx"] for t in tokens]
    start_tok = bisect_right(ends, start_char)  # first token ending after start_char
    end_tok = bisect_left(starts, end_char)  # tokens starting before end_char
    if start_tok >= end_tok:
        return None
    return start_tok, end_tok


def char_bounds(tokens: list[dict], start_tok: int, end_tok: int) -> tuple[int, int]:
    first, last = tokens[start_tok], tokens[end_tok - 1]
    return first["idx"], last["idx"] + len(last["text"])
