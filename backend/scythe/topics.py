"""Debate topics: seed NSDA past resolutions, resolve a card's topic, create custom ones."""

import json
import re
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .graph_models import Topic

SEED = Path(__file__).parent / "data" / "nsda_topics.json"


def seed(session: Session) -> int:
    """Upsert the bundled NSDA topics (idempotent; refreshes wording if the seed file changes)."""
    rows = json.loads(SEED.read_text())
    for r in rows:
        values = dict(slug=r["slug"], event=r["event"], season=r["season"], period=r["period"],
                      resolution=r["resolution"], origin="nsda")
        stmt = insert(Topic).values(**values)
        session.execute(stmt.on_conflict_do_update(
            index_elements=["slug"], set_={k: stmt.excluded[k] for k in ("event", "season", "period", "resolution")}
        ))
    session.commit()
    return len(rows)


def custom_slug(session: Session, resolution: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", resolution.lower()) if w not in {"resolved", "the", "a", "an", "of", "should"}]
    base = "custom"
    for w in words:
        if len(base) + 1 + len(w) > 38:
            break
        base = f"{base}-{w}"
    slug, n = base, 2
    while session.scalar(select(Topic.id).where(Topic.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def create_custom(session: Session, resolution: str, season: str = "", event: str = "custom") -> Topic:
    resolution = resolution.strip()
    if not resolution.lower().startswith("resolved"):
        resolution = f"Resolved: {resolution}"
    topic = Topic(slug=custom_slug(session, resolution), event=event, season=season, resolution=resolution, origin="custom")
    session.add(topic)
    session.flush()
    return topic


def require_topic(session: Session, topic_id: int | None) -> Topic:
    """Every card needs a topic. With no id, fall back to the current topic; with neither, the client
    must prompt the user (HTTP 422 `topic_required`)."""
    from .auth import app_state

    state = app_state(session)
    tid = topic_id if topic_id is not None else state.current_topic_id
    topic = session.get(Topic, tid) if tid is not None else None
    if topic is None:
        raise HTTPException(422, "topic_required")
    state.current_topic_id = topic.id
    return topic


def from_meta(session: Session, slug: str | None, meta: dict | None) -> Topic | None:
    """Resolve a topic from a GitHub label / issue metadata, creating it if this index lacks it."""
    if not slug:
        return None
    topic = session.scalar(select(Topic).where(Topic.slug == slug))
    if topic is None and meta and meta.get("resolution"):
        topic = Topic(slug=slug, event=meta.get("event", "custom"), season=meta.get("season", ""),
                      period=meta.get("period", ""), resolution=meta["resolution"], origin="github")
        session.add(topic)
        session.flush()
    return topic


def topic_out(t: Topic | None) -> dict | None:
    if t is None:
        return None
    return dict(id=t.id, slug=t.slug, event=t.event, season=t.season, period=t.period,
                resolution=t.resolution, origin=t.origin)
