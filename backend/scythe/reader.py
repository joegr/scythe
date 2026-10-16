"""Reader mode: fetch a page and reduce it to sanitized plain text with paragraph breaks.

The sanitized text becomes `Source.full_text` and is the single string cards are cut from, so
every card is a verbatim substring of it (no rewriting) and keeps exact char anchors.
"""

import re
import unicodedata
from datetime import date

import trafilatura

from .graph import SourceInfo

_INVISIBLE = dict.fromkeys(map(ord, "­​‌‍⁠﻿"), None)
_SPACES = re.compile(r"[ \t  -   　]+")


def sanitize_text(text: str) -> str:
    """Normalize to NFC, drop invisible characters, collapse intra-line whitespace, and keep
    paragraphs separated by exactly one blank line. Quotes/dashes are preserved verbatim."""
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paras = []
    for block in re.split(r"\n\s*\n", text):
        lines = [_SPACES.sub(" ", ln).strip() for ln in block.split("\n")]
        para = " ".join(ln for ln in lines if ln)
        if para:
            paras.append(para)
    return "\n\n".join(paras)


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


def _authors(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(a.strip() for a in re.split(r";|\band\b|\|", value) if a.strip())


def extract(html: str, url: str | None = None) -> SourceInfo:
    doc = trafilatura.bare_extraction(
        html,
        url=url,
        with_metadata=True,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
        as_dict=True,
    )
    if not doc or not doc.get("text"):
        raise ValueError("no readable article text found")
    # trafilatura separates paragraphs with single newlines; make them blank-line separated.
    body = sanitize_text(doc["text"].replace("\n", "\n\n"))
    return SourceInfo(
        url=url or doc.get("url") or None,
        title=(doc.get("title") or "").strip(),
        publisher=(doc.get("sitename") or doc.get("hostname") or "").strip(),
        published=_date(doc.get("date")),
        authors=_authors(doc.get("author")),
        full_text=body,
        kind="article",
    )


def fetch(url: str) -> SourceInfo:
    html = trafilatura.fetch_url(url)
    if not html:
        raise ValueError(f"could not fetch {url}")
    return extract(html, url)


def locate(full_text: str, passage: str) -> tuple[int, int] | None:
    """Find a pasted passage inside source text: exact match first, then whitespace- and
    quote-insensitive match. Returns char offsets into `full_text`."""
    passage = passage.strip()
    if not passage:
        return None
    i = full_text.find(passage)
    if i >= 0:
        return i, i + len(passage)
    words = sanitize_text(passage).split()
    if not words:
        return None
    pattern = r"\s+".join(_loose(w) for w in words)
    m = re.search(pattern, full_text)
    return (m.start(), m.end()) if m else None


_QUOTES = {"'": "['‘’]", '"': "[\"“”]", "‘": "['‘’]", "’": "['‘’]",
           "“": "[\"“”]", "”": "[\"“”]", "-": "[-‐-―]",
           "–": "[-‐-―]", "—": "[-‐-―]"}


def _loose(word: str) -> str:
    return "".join(_QUOTES.get(ch, re.escape(ch)) for ch in word)


def default_cite(info_title: str, authors: list[str], publisher: str, published: date | None, url: str | None) -> str:
    """Debate-style cite: `Lastname YY, Full Name, "Title," Publisher, M-D-YYYY, URL`."""
    head = ""
    if authors:
        last = authors[0].split()[-1]
        head = f"{last} {published.strftime('%y')}" if published else last
    elif published:
        head = f"{(publisher or 'Unknown').split(',')[0].strip()} {published.strftime('%y')}"
    parts = [p for p in (
        head,
        ", ".join(authors) if authors else "",
        f'"{info_title}"' if info_title else "",
        publisher,
        f"{published.month}-{published.day}-{published.year}" if published else "",
        url or "",
    ) if p]
    return ", ".join(parts)
