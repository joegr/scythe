from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import topics
from ..auth import app_state
from ..db import get_session
from ..graph_models import TOPIC_EVENTS, Topic
from ..models import Card

router = APIRouter(tags=["topics"])


class TopicIn(BaseModel):
    resolution: str = Field(min_length=3)
    season: str = ""
    event: str = "custom"


class CurrentIn(BaseModel):
    topic_id: int | None


@router.get("/topics")
def list_topics(
    q: str = "", event: str | None = None, season: str | None = None, limit: int = Query(50, le=600),
    session: Session = Depends(get_session),
):
    """Newest seasons first; custom topics and topics you have cards under float to the top."""
    used = select(Card.topic_id, func.count().label("n")).group_by(Card.topic_id).subquery()
    stmt = select(Topic, func.coalesce(used.c.n, 0)).outerjoin(used, used.c.topic_id == Topic.id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Topic.resolution.ilike(like), Topic.slug.ilike(like), Topic.season.ilike(like)))
    if event:
        stmt = stmt.where(Topic.event == event)
    if season:
        stmt = stmt.where(Topic.season == season)
    stmt = stmt.order_by(func.coalesce(used.c.n, 0).desc(), (Topic.origin == "nsda").asc(), Topic.season.desc(), Topic.id)
    return [{**topics.topic_out(t), "cards": n} for t, n in session.execute(stmt.limit(limit))]


@router.post("/topics", status_code=201)
def create_topic(body: TopicIn, session: Session = Depends(get_session)):
    if body.event not in TOPIC_EVENTS:
        raise HTTPException(422, f"event must be one of {TOPIC_EVENTS}")
    topic = topics.create_custom(session, body.resolution, body.season, body.event)
    session.commit()
    return topics.topic_out(topic)


@router.get("/topics/current")
def current(session: Session = Depends(get_session)):
    state = app_state(session)
    return topics.topic_out(session.get(Topic, state.current_topic_id) if state.current_topic_id else None)


@router.put("/topics/current")
def set_current(body: CurrentIn, session: Session = Depends(get_session)):
    state = app_state(session)
    if body.topic_id is not None and session.get(Topic, body.topic_id) is None:
        raise HTTPException(404, "topic not found")
    state.current_topic_id = body.topic_id
    session.commit()
    return current(session)
