"""Knowledge-graph browsing and search."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, literal, select, union_all
from sqlalchemy.orm import Session

from .. import graph, jobs
from ..db import get_session
from ..graph_models import RELATIONS, SYMMETRIC, Chunk, Edge, Node, Source
from ..models import Card
from ..schemas import EdgeIn, edge_out, node_out

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/relations")
def relations():
    return dict(groups=RELATIONS, symmetric=sorted(SYMMETRIC))


@router.get("/search")
def search_nodes(
    q: str,
    kinds: list[str] | None = Query(None),
    limit: int = Query(30, le=200),
    session: Session = Depends(get_session),
):
    """Full-text search over the whole graph: node titles/bodies plus the full text of cards,
    sources and chunks, mapped back onto their nodes, ranked, with degree for context."""
    tsq = func.websearch_to_tsquery("english", q)
    hits = union_all(
        select(Node.id.label("node_id"), func.ts_rank(Node.tsv, tsq).label("rank")).where(Node.tsv.op("@@")(tsq)),
        select(Card.node_id, func.ts_rank(Card.tsv, tsq)).where(Card.node_id.is_not(None), Card.tsv.op("@@")(tsq)),
        select(Source.node_id, func.ts_rank(Source.tsv, tsq) * literal(0.8)).where(Source.tsv.op("@@")(tsq)),
        select(Chunk.node_id, func.ts_rank(Chunk.tsv, tsq) * literal(0.6)).where(Chunk.tsv.op("@@")(tsq)),
    ).subquery()
    ranked = (
        select(hits.c.node_id, func.max(hits.c.rank).label("rank"))
        .group_by(hits.c.node_id).order_by(func.max(hits.c.rank).desc()).limit(limit)
    ).subquery()
    stmt = select(Node, ranked.c.rank).join(ranked, ranked.c.node_id == Node.id).order_by(ranked.c.rank.desc())
    if kinds:
        stmt = stmt.where(Node.kind.in_(kinds))
    rows = session.execute(stmt).all()
    degree = _degrees(session, [n.id for n, _ in rows])
    return [node_out(n, rank=float(r), degree=degree.get(n.id, 0)) for n, r in rows]


def _degrees(session: Session, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    ends = union_all(
        select(Edge.src_id.label("n")).where(Edge.src_id.in_(ids)),
        select(Edge.dst_id.label("n")).where(Edge.dst_id.in_(ids)),
    ).subquery()
    return dict(session.execute(select(ends.c.n, func.count()).group_by(ends.c.n)).all())


@router.get("/nodes/{node_id:int}")
def get_node(node_id: int, session: Session = Depends(get_session)):
    node = session.get(Node, node_id) or _404()
    out_edges = session.execute(
        select(Edge, Node).join(Node, Node.id == Edge.dst_id).where(Edge.src_id == node_id).order_by(Edge.relation)
    ).all()
    in_edges = session.execute(
        select(Edge, Node).join(Node, Node.id == Edge.src_id).where(Edge.dst_id == node_id).order_by(Edge.relation)
    ).all()
    return node_out(
        node,
        outgoing=[{**edge_out(e), "other": node_out(n)} for e, n in out_edges],
        incoming=[{**edge_out(e), "other": node_out(n)} for e, n in in_edges],
    )


@router.get("/nodes/{node_id:int}/neighborhood")
def get_neighborhood(
    node_id: int,
    depth: int = Query(1, ge=1, le=4),
    relations: list[str] | None = Query(None),
    direction: str = Query("both", pattern="^(in|out|both)$"),
    limit: int = Query(200, le=1000),
    session: Session = Depends(get_session),
):
    session.get(Node, node_id) or _404()
    nodes, edges, depths = graph.neighborhood(session, node_id, depth, relations, direction, limit)
    return dict(
        root=node_id,
        nodes=[node_out(n, depth=depths[n.id]) for n in nodes],
        edges=[edge_out(e) for e in edges],
    )


@router.get("/path")
def path(a: int, b: int, max_depth: int = Query(4, le=6), session: Session = Depends(get_session)):
    found = graph.shortest_path(session, a, b, max_depth)
    if found is None:
        raise HTTPException(404, "no path within max_depth")
    node_ids, edge_ids = found
    nodes = {n.id: n for n in session.scalars(select(Node).where(Node.id.in_(node_ids)))}
    edges = {e.id: e for e in session.scalars(select(Edge).where(Edge.id.in_(edge_ids)))}
    return dict(nodes=[node_out(nodes[i]) for i in node_ids], edges=[edge_out(edges[i]) for i in edge_ids])


@router.post("/edges", status_code=201)
def create_edge(body: EdgeIn, session: Session = Depends(get_session)):
    for nid in (body.src_id, body.dst_id):
        session.get(Node, nid) or _404()
    try:
        edge = graph.link(
            session, body.src_id, body.dst_id, body.relation,
            src_range=(body.src_start, body.src_end) if body.src_start is not None else None,
            dst_range=(body.dst_start, body.dst_end) if body.dst_start is not None else None,
            confidence=body.confidence, provenance="manual", props=body.props,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if edge is None:
        raise HTTPException(422, "self-loops are not allowed")
    session.commit()
    _push_if_card(session, edge.src_id)
    return edge_out(edge)


@router.delete("/edges/{edge_id:int}", status_code=204)
def delete_edge(edge_id: int, session: Session = Depends(get_session)):
    edge = session.get(Edge, edge_id) or _404()
    src_id = edge.src_id
    session.delete(edge)
    session.commit()
    _push_if_card(session, src_id)


def _push_if_card(session: Session, node_id: int) -> None:
    """Typed links are written into the card's issue body, so re-push the source card."""
    card_id = session.scalar(select(Card.id).where(Card.node_id == node_id))
    if card_id is not None:
        jobs.push_card(session, card_id)


def _404():
    raise HTTPException(404, "not found")
