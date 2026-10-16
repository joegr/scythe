"""spaCy interop (DocBin / Doc JSON / Prodigy JSONL), training and model suggestions."""

import io
import subprocess
import sys
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from .. import jobs, spacy_io, suggest
from ..auth import app_state
from ..config import settings
from ..db import get_session
from ..train import GOLD_SOURCES, spancat_config
from .cards import card_out, load_card

router = APIRouter(tags=["spacy"])


def export_filter(
    card_id: list[int] | None = Query(None),
    file_id: int | None = None,
    block_id: int | None = None,
    label: list[str] | None = Query(None),
    spans_key: list[str] | None = Query(None),
    source: list[str] | None = Query(None),
    accepted_only: bool = True,
    only_labeled: bool = True,
) -> spacy_io.ExportFilter:
    return spacy_io.ExportFilter(card_id, file_id, block_id, label, spans_key, source, accepted_only, only_labeled)


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


@router.get("/spacy/export.spacy")
def export_docbin(f: spacy_io.ExportFilter = Depends(export_filter), session: Session = Depends(get_session)):
    data = spacy_io.export_docbin(session, f)
    return Response(data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="scythe-{_stamp()}.spacy"'})


@router.get("/spacy/export.jsonl")
def export_jsonl(
    format: str = Query("docjson", pattern="^(docjson|prodigy)$"),
    f: spacy_io.ExportFilter = Depends(export_filter),
    session: Session = Depends(get_session),
):
    lines = list(spacy_io.export_docjson(session, f) if format == "docjson" else spacy_io.export_prodigy(session, f))
    return Response("".join(lines), media_type="application/x-ndjson",
                    headers={"Content-Disposition": f'attachment; filename="scythe-{format}-{_stamp()}.jsonl"'})


@router.get("/spacy/training-bundle.zip")
def training_bundle(
    spans_key: str = "sc", dev_ratio: float = Query(0.2, gt=0, lt=1), max_size: int = 12,
    session: Session = Depends(get_session),
):
    """config.cfg + train.spacy + dev.spacy, ready for `python -m spacy train config.cfg
    --paths.train train.spacy --paths.dev dev.spacy`."""
    f = spacy_io.ExportFilter(spans_keys=[spans_key], sources=GOLD_SOURCES)
    train_db, dev_db, n_train, n_dev = spacy_io.split_docbins(session, f, dev_ratio)
    if n_train == 0:
        raise HTTPException(422, "no labeled cards under that spans_key")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("config.cfg", spancat_config(spans_key, max_size).to_str())
        z.writestr("train.spacy", train_db.to_bytes())
        z.writestr("dev.spacy", dev_db.to_bytes())
        z.writestr("README.txt", f"{n_train} train / {n_dev} dev docs, spans_key={spans_key}\n"
                                 "python -m spacy train config.cfg --paths.train train.spacy "
                                 "--paths.dev dev.spacy --output model\n")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="scythe-train-{_stamp()}.zip"'})


@router.post("/spacy/import", status_code=201)
async def import_file(file: UploadFile = File(...), block_id: int | None = None, topic_id: int | None = None,
                      session: Session = Depends(get_session)):
    """Docs keep their own `scythe.topic`; others go under `topic_id` (or the current topic)."""
    data = await file.read()
    default_topic = topic_id if topic_id is not None else app_state(session).current_topic_id
    name = (file.filename or "").lower()
    try:
        if name.endswith(".spacy"):
            result = spacy_io.import_docbin(session, data, block_id, default_topic)
        elif name.endswith((".jsonl", ".json", ".ndjson")):
            result = spacy_io.import_jsonl(session, data, block_id, default_topic)
        else:
            raise HTTPException(422, "expected .spacy or .jsonl")
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(422, f"could not import: {e}") from e
    session.commit()
    for cid in result.card_ids:
        jobs.enqueue_card(session, cid)
    return dict(cards=len(result.card_ids), spans=result.spans, card_ids=result.card_ids)


# ---------------------------------------------------------------- model


_training: subprocess.Popen | None = None


@router.get("/model")
def model_status():
    active = suggest.active_model()
    return dict(
        base_model=settings.spacy_model,
        active=suggest.model_info(active) if active else None,
        runs=[suggest.model_info(d) for d in suggest.model_dirs()[:10]],
        training=_training is not None and _training.poll() is None,
    )


@router.post("/model/train", status_code=202)
def start_training(spans_key: str = "sc", max_steps: int = Query(2000, le=50000)):
    global _training
    if _training is not None and _training.poll() is None:
        raise HTTPException(409, "training already running")
    out = settings.models_dir / _stamp()
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "train.log", "w")  # noqa: SIM115  (owned by the child process)
    _training = subprocess.Popen(
        [sys.executable, "-m", "scythe.train", "--spans-key", spans_key, "--max-steps", str(max_steps),
         "--output", str(out)],
        stdout=log, stderr=subprocess.STDOUT,
    )
    return dict(run=out.name)


@router.get("/model/runs/{name}/log")
def training_log(name: str):
    path = (settings.models_dir / name / "train.log").resolve()
    if settings.models_dir.resolve() not in path.parents or not path.exists():
        raise HTTPException(404, "no log")
    return Response(path.read_text()[-20000:], media_type="text/plain")


@router.post("/cards/{card_id:int}/suggest")
def suggest_spans(card_id: int, threshold: float | None = None, session: Session = Depends(get_session)):
    card = load_card(session, card_id)
    try:
        added = suggest.suggest(session, card, threshold)
    except LookupError as e:
        raise HTTPException(409, str(e)) from e
    session.commit()
    return dict(added=added, card=card_out(load_card(session, card_id), tokens=False))
