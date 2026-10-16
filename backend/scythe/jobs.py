"""In-process background job runner backed by the `jobs` table.

Requests commit their data, then `enqueue_*` records a Job row and submits it to a small thread
pool, so the UI renders the card immediately and polls `/api/jobs?card_id=` for progress.
Unfinished jobs are re-submitted at startup.

Kinds:
  card.enrich    NER spans, graph indexing (source anchors, entities)
  source.enrich  baseline chunking + extractive summaries
  gh.push_card   write the card to its GitHub issue (coalesced: one pending push per card)
  gh.pull        refresh the index from GitHub issues
"""

import logging
import threading
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from sqlalchemy import select

from .db import SessionLocal
from .graph_models import Job, Source
from .models import Card

log = logging.getLogger("scythe.jobs")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="scythe-job")
_card_locks: defaultdict[int, threading.Lock] = defaultdict(threading.Lock)


def _run(job_id: int) -> None:
    from . import enrich, gh_sync  # local imports keep spaCy off the API import path

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if job is None or job.status == "done":
            return
        job.status = "running"
        session.commit()
        follow_up: list[tuple[str, dict]] = []
        try:
            if job.kind == "card.enrich":
                enrich.enrich_card(session, session.get(Card, job.card_id))
            elif job.kind == "source.enrich":
                enrich.enrich_source(session, session.get(Source, job.source_id))
            elif job.kind == "gh.push_card":
                with _card_locks[job.card_id]:
                    card = session.get(Card, job.card_id)
                    if card is not None and (card.gh_dirty or card.gh_number is None):
                        gh, repo = gh_sync.connection(session)
                        gh_sync.push_card(session, gh, repo, card)
            elif job.kind == "gh.pull":
                stats = gh_sync.pull(session)
                follow_up = [("card.enrich", {"card_id": cid}) for cid in stats["changed_card_ids"]]
                # Cards edited while disconnected (or whose push failed) go up after the pull.
                dirty = session.scalars(select(Card.id).where(Card.gh_dirty.is_(True))).all()
                follow_up += [("gh.push_card", {"card_id": cid}) for cid in dirty]
                job.error = str({k: v for k, v in stats.items() if k != "changed_card_ids"})
            else:
                raise ValueError(f"unknown job kind {job.kind}")
            job.status = "done"
        except Exception as exc:
            session.rollback()
            job = session.get(Job, job_id)
            job.status, job.error = "failed", traceback.format_exc()[-4000:]
            log.exception("job %s failed", job_id)
            if job.kind == "gh.pull":
                from .auth import app_state

                app_state(session).last_sync_error = str(exc)
        job.finished_at = datetime.now(UTC)
        session.commit()
        if job.kind == "card.enrich" and job.status == "done":
            card = session.get(Card, job.card_id)
            if card is not None and card.source_id:
                _enqueue(session, "source.enrich", source_id=card.source_id, once=True)
        for kind, ids in follow_up:
            _enqueue(session, kind, pending_only=kind == "gh.push_card", **ids)


def _enqueue(session, kind: str, *, card_id: int | None = None, source_id: int | None = None,
             once: bool = False, pending_only: bool = False) -> Job | None:
    """`once`: skip if any non-failed job of this kind exists for the target.
    `pending_only`: skip if one is still queued (it will pick up the latest state when it runs)."""
    if once or pending_only:
        stmt = select(Job.id).where(Job.kind == kind, Job.source_id == source_id, Job.card_id == card_id)
        stmt = stmt.where(Job.status == "queued") if pending_only else stmt.where(Job.status != "failed")
        if session.scalar(stmt.limit(1)):
            return None
    job = Job(kind=kind, card_id=card_id, source_id=source_id)
    session.add(job)
    session.commit()
    _pool.submit(_run, job.id)
    return job


def enqueue_card(session, card_id: int) -> Job:
    """New or re-imported card: index it locally and make sure it exists on GitHub."""
    push_card(session, card_id)
    return _enqueue(session, "card.enrich", card_id=card_id)


def push_card(session, card_id: int) -> Job | None:
    """Mark a card changed and schedule a (coalesced) push to its GitHub issue."""
    card = session.get(Card, card_id)
    if card is not None and not card.gh_dirty:
        card.gh_dirty = True
        session.commit()
    return _enqueue(session, "gh.push_card", card_id=card_id, pending_only=True)


def enqueue_source(session, source_id: int) -> Job | None:
    return _enqueue(session, "source.enrich", source_id=source_id, once=True)


def enqueue_pull(session) -> Job | None:
    return _enqueue(session, "gh.pull", pending_only=True)


def resume_pending() -> None:
    with SessionLocal() as session:
        for job in session.scalars(select(Job).where(Job.status.in_(("queued", "running")))):
            job.status = "queued"
            session.commit()
            _pool.submit(_run, job.id)
