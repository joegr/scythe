"""Knowledge-graph operations: node creation for typed payloads, edge upserts, chunking and traversal."""

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .graph_models import ALL_RELATIONS, SYMMETRIC, Author, Chunk, Edge, Entity, Node, Source
from .models import ENTS_KEY, Card

URL_RE = re.compile(r"https?://[^\s\]\)>,;\"']+")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def new_node(session: Session, kind: str, title: str = "", body: str = "", **props) -> Node:
    node = Node(kind=kind, title=title[:2000], body=body[:10000], props=props)
    session.add(node)
    session.flush()
    return node


def link(
    session: Session,
    src_id: int,
    dst_id: int,
    relation: str,
    *,
    src_range: tuple[int, int] | None = None,
    dst_range: tuple[int, int] | None = None,
    confidence: float = 1.0,
    provenance: str = "manual",
    props: dict | None = None,
) -> Edge | None:
    """Idempotent edge upsert keyed on (src, dst, relation). Symmetric relations are stored src<dst."""
    if relation not in ALL_RELATIONS:
        raise ValueError(f"unknown relation {relation!r}")
    if src_id == dst_id:
        return None
    if relation in SYMMETRIC and src_id > dst_id:
        src_id, dst_id, src_range, dst_range = dst_id, src_id, dst_range, src_range
    values = dict(
        src_id=src_id,
        dst_id=dst_id,
        relation=relation,
        src_start=src_range[0] if src_range else None,
        src_end=src_range[1] if src_range else None,
        dst_start=dst_range[0] if dst_range else None,
        dst_end=dst_range[1] if dst_range else None,
        confidence=confidence,
        provenance=provenance,
        props=props or {},
    )
    update = {k: v for k, v in values.items() if k not in ("src_id", "dst_id", "relation") and v is not None}
    stmt = (
        insert(Edge)
        .values(**values)
        .on_conflict_do_update(constraint="uq_edges_src_dst_rel", set_=update)
        .returning(Edge.id)
    )
    edge_id = session.execute(stmt).scalar_one()
    return session.get(Edge, edge_id)


# ---------------------------------------------------------------- typed nodes


def card_node(session: Session, card: Card) -> Node:
    if card.node_id is None:
        node = new_node(session, "card", card.tag, card.cite, ref_id=card.id)
        card.node_id = node.id
        session.flush()
        return node
    node = session.get(Node, card.node_id)
    node.title, node.body = card.tag[:2000], card.cite[:10000]
    return node


def get_or_create_author(session: Session, name: str) -> Author:
    key = norm(name)
    author = session.scalar(select(Author).where(Author.norm_name == key))
    if author is None:
        node = new_node(session, "author", name.strip())
        author = Author(node_id=node.id, name=name.strip(), norm_name=key)
        session.add(author)
        session.flush()
        node.props = {"ref_id": author.id}
    return author


def get_or_create_entity(session: Session, label: str, name: str, kb_id: str = "") -> Entity:
    key = norm(name)
    entity = session.scalar(select(Entity).where(Entity.label == label, Entity.norm_name == key))
    if entity is None:
        node = new_node(session, "entity", name.strip(), label)
        entity = Entity(node_id=node.id, label=label, name=name.strip(), norm_name=key, kb_id=kb_id)
        session.add(entity)
        session.flush()
        node.props = {"ref_id": entity.id, "label": label}
    return entity


@dataclass
class SourceInfo:
    url: str | None = None
    title: str = ""
    publisher: str = ""
    published: date | None = None
    authors: tuple[str, ...] = ()
    full_text: str = ""
    kind: str = "article"
    cite: str = ""
    key: str = ""  # dedupe key for url-less sources (defaults to the cite)


def upsert_source(session: Session, info: SourceInfo, provenance: str = "ingest") -> Source:
    """Dedupe on URL, else on `key` (or the cite string). Fills empty fields on an existing source."""
    src = None
    key = info.key or info.cite
    if info.url:
        src = session.scalar(select(Source).where(Source.url == info.url))
    elif key:
        src = session.scalar(select(Source).where(Source.meta["key"].astext == key))
    if src is None:
        node = new_node(session, "source", info.title or info.cite or info.url or "Untitled source", info.publisher)
        meta = {k: v for k, v in (("cite", info.cite), ("key", None if info.url else key)) if v}
        src = Source(node_id=node.id, url=info.url or None, meta=meta)
        session.add(src)
        session.flush()
        node.props = {"ref_id": src.id}
    for attr in ("title", "publisher", "published", "full_text", "kind"):
        val = getattr(info, attr)
        if val and not getattr(src, attr):
            setattr(src, attr, val)
    node = session.get(Node, src.node_id)
    node.title = (src.title or info.cite or src.url or node.title)[:2000]
    node.body = src.publisher
    for name in info.authors:
        if name.strip():
            link(session, src.node_id, get_or_create_author(session, name).node_id, "authored_by", provenance=provenance)
    if src.full_text and not src.chunks:
        paragraph_chunks(session, src)
    session.flush()
    return src


# ---------------------------------------------------------------- chunking


def paragraph_chunks(session: Session, source: Source, strategy: str = "paragraph") -> list[Chunk]:
    """Baseline chunker: one level-0 chunk per paragraph. Agentic chunkers replace this via
    `replace_chunks`, which accepts an arbitrary tree."""
    tree = []
    for m in re.finditer(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*", source.full_text):
        if m.group().strip():
            tree.append({"start_char": m.start(), "end_char": m.end()})
    return replace_chunks(session, source, tree, strategy=strategy, provenance="ingest")


def replace_chunks(
    session: Session, source: Source, tree: list[dict], *, strategy: str, provenance: str = "agent"
) -> list[Chunk]:
    """Replace all chunks of `strategy` for a source with a nested tree of
    {start_char, end_char, title?, summary?, propositions?, meta?, children?: [...]}.
    Creates `part_of` edges child->parent (top level -> source) with char anchors into the source."""
    for old in [c for c in source.chunks if c.strategy == strategy]:
        session.delete(session.get(Node, old.node_id))  # cascades to chunk and edges
    session.flush()
    session.expire(source, ["chunks"])
    created: list[Chunk] = []
    n = len(source.full_text)

    def walk(items: list[dict], parent: Chunk | None, level: int) -> None:
        for ordinal, item in enumerate(items):
            start, end = int(item["start_char"]), int(item["end_char"])
            if not (0 <= start < end <= n):
                raise ValueError(f"chunk range {start}:{end} outside source text (len {n})")
            if parent is not None and not (parent.start_char <= start and end <= parent.end_char):
                raise ValueError(f"chunk {start}:{end} not inside parent {parent.start_char}:{parent.end_char}")
            body = source.full_text[start:end]
            node = new_node(session, "chunk", item.get("title", ""), item.get("summary", ""))
            chunk = Chunk(
                node_id=node.id,
                source_id=source.id,
                parent_id=parent.id if parent else None,
                strategy=strategy,
                level=level,
                ordinal=ordinal,
                start_char=start,
                end_char=end,
                text=body,
                title=item.get("title", ""),
                summary=item.get("summary", ""),
                propositions=item.get("propositions", []),
                meta=item.get("meta", {}),
            )
            session.add(chunk)
            session.flush()
            node.props = {"ref_id": chunk.id, "source_id": source.id, "strategy": strategy}
            parent_node = parent.node_id if parent else source.node_id
            link(session, node.id, parent_node, "part_of", dst_range=(start, end), provenance=provenance)
            created.append(chunk)
            walk(item.get("children", []), chunk, level + 1)

    walk(tree, None, 0)
    return created


# ---------------------------------------------------------------- card <-> graph


def attach_card_to_source(session: Session, card: Card, source: Source, provenance: str = "ingest") -> None:
    """Set card.source_id and add `excerpt_of` edges to the source and to every leaf chunk the
    card text overlaps, anchored by where the card text occurs in the source text."""
    card.source_id = source.id
    cnode = card_node(session, card)
    prior = session.scalar(
        select(Edge).where(Edge.src_id == cnode.id, Edge.dst_id == source.node_id, Edge.relation == "excerpt_of")
    )
    if prior is not None and prior.dst_start is not None:
        offset = prior.dst_start  # exact offsets recorded at cut time win over a text search
    else:
        offset = source.full_text.find(card.text) if source.full_text and card.text else -1
    if offset < 0:
        link(session, cnode.id, source.node_id, "excerpt_of", provenance=provenance, confidence=0.5)
        return
    lo, hi = offset, offset + len(card.text)
    link(session, cnode.id, source.node_id, "excerpt_of", src_range=(0, len(card.text)), dst_range=(lo, hi),
         provenance=provenance)
    child_parents = {c.parent_id for c in source.chunks}
    for chunk in source.chunks:
        if chunk.id in child_parents:  # only link leaves; ancestors are reachable via part_of
            continue
        a, b = max(lo, chunk.start_char), min(hi, chunk.end_char)
        if a < b:
            link(session, cnode.id, chunk.node_id, "excerpt_of", src_range=(a - lo, b - lo),
                 dst_range=(a - chunk.start_char, b - chunk.start_char), provenance=provenance)


def source_from_cite(card: Card) -> SourceInfo | None:
    url = card.url or (m.group() if (m := URL_RE.search(card.cite or "")) else "")
    if not url and not card.cite:
        return None
    return SourceInfo(url=url or None, cite=card.cite, title=card.cite[:300] if not url else "")


def link_card_entities(session: Session, card: Card) -> None:
    """Promote NER spans to entity nodes with `mentions` edges anchored at the span."""
    cnode = card_node(session, card)
    for span in card.spans:
        if span.label.spans_key == ENTS_KEY:
            entity = get_or_create_entity(session, span.label.name, span.text)
            link(session, cnode.id, entity.node_id, "mentions", src_range=(span.start_char, span.end_char),
                 provenance="ner")


def index_card(session: Session, card: Card, provenance: str = "ingest") -> None:
    """Ensure a card is fully represented in the graph (node, source, entities)."""
    card_node(session, card)
    session.refresh(card, ["spans"])
    if card.source_id is not None:
        attach_card_to_source(session, card, session.get(Source, card.source_id), provenance)
    elif info := source_from_cite(card):
        attach_card_to_source(session, card, upsert_source(session, info, provenance), provenance)
    link_card_entities(session, card)


# ---------------------------------------------------------------- traversal

NEIGHBORHOOD_SQL = text(
    """
WITH RECURSIVE walk(node_id, depth, path) AS (
    SELECT CAST(:root AS integer), 0, ARRAY[CAST(:root AS integer)]
  UNION ALL
    SELECT CASE WHEN e.src_id = w.node_id THEN e.dst_id ELSE e.src_id END,
           w.depth + 1,
           w.path || CASE WHEN e.src_id = w.node_id THEN e.dst_id ELSE e.src_id END
    FROM walk w
    JOIN edges e ON (
         (:dir IN ('out', 'both') AND e.src_id = w.node_id)
      OR (:dir IN ('in', 'both') AND e.dst_id = w.node_id))
    WHERE w.depth < :depth
      AND (CAST(:relations AS text[]) IS NULL OR e.relation = ANY(CAST(:relations AS text[])))
      AND NOT (CASE WHEN e.src_id = w.node_id THEN e.dst_id ELSE e.src_id END) = ANY(w.path)
)
SELECT node_id, MIN(depth) AS depth FROM walk GROUP BY node_id ORDER BY MIN(depth), node_id LIMIT :limit
"""
)

PATH_SQL = text(
    """
WITH RECURSIVE walk(node_id, path, edge_path) AS (
    SELECT CAST(:a AS integer), ARRAY[CAST(:a AS integer)], ARRAY[]::integer[]
  UNION ALL
    SELECT CASE WHEN e.src_id = w.node_id THEN e.dst_id ELSE e.src_id END,
           w.path || CASE WHEN e.src_id = w.node_id THEN e.dst_id ELSE e.src_id END,
           w.edge_path || e.id
    FROM walk w JOIN edges e ON e.src_id = w.node_id OR e.dst_id = w.node_id
    WHERE cardinality(w.path) <= :max_depth
      AND NOT (CASE WHEN e.src_id = w.node_id THEN e.dst_id ELSE e.src_id END) = ANY(w.path)
      AND NOT CAST(:b AS integer) = ANY(w.path)
)
SELECT path, edge_path FROM walk WHERE node_id = :b ORDER BY cardinality(path) LIMIT 1
"""
)


def neighborhood(
    session: Session, root: int, depth: int = 1, relations: list[str] | None = None,
    direction: str = "both", limit: int = 200,
) -> tuple[list[Node], list[Edge], dict[int, int]]:
    rows = session.execute(
        NEIGHBORHOOD_SQL,
        dict(root=root, depth=depth, relations=relations, dir=direction, limit=limit),
    ).all()
    depths = {r.node_id: r.depth for r in rows}
    ids = list(depths)
    nodes = list(session.scalars(select(Node).where(Node.id.in_(ids))))
    stmt = select(Edge).where(Edge.src_id.in_(ids), Edge.dst_id.in_(ids))
    if relations:
        stmt = stmt.where(Edge.relation.in_(relations))
    edges = list(session.scalars(stmt))
    return nodes, edges, depths


def shortest_path(session: Session, a: int, b: int, max_depth: int = 4) -> tuple[list[int], list[int]] | None:
    row = session.execute(PATH_SQL, dict(a=a, b=b, max_depth=max_depth)).first()
    return (list(row.path), list(row.edge_path)) if row else None
