import random

from scythe import nlp, reader


def test_snap_matches_spacy_char_span_expand():
    doc = nlp.get_nlp().make_doc("Nuclear war, per Dr. Robock (2022), would cause “extinction” — soon.  Really!")
    tokens = nlp.tokens_of(doc)
    rng = random.Random(0)
    for _ in range(2000):
        a = rng.randrange(0, len(doc.text))
        b = rng.randrange(a + 1, len(doc.text) + 1)  # empty ranges are rejected by design
        expected = doc.char_span(a, b, alignment_mode="expand")
        got = nlp.snap(tokens, a, b)
        if expected is None or len(expected) == 0:
            assert got is None, (a, b)
        else:
            assert got == (expected.start, expected.end), (a, b, doc.text[a:b])


def test_tokens_rebuild_doc_losslessly():
    text = "Soot  blocks\nsunlight.\n\nAgriculture collapses."
    doc = nlp.get_nlp().make_doc(text)
    assert nlp.doc_from_tokens(nlp.tokens_of(doc)).text == text


def test_sanitize_and_locate_loose_match():
    raw = "Nuclear winter­ would   collapse\nglobal agriculture.\r\n\r\n“No country” spared."
    clean = reader.sanitize_text(raw)
    assert clean == "Nuclear winter would collapse global agriculture.\n\n“No country” spared."
    assert reader.locate(clean, '"No   country" spared') == (clean.index("“"), len(clean) - 1)
    assert reader.locate(clean, "not in here") is None
