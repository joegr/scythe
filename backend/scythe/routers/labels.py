from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import LABEL_STYLES, Label
from ..schemas import LabelIn, LabelPatch, label_out

router = APIRouter(tags=["labels"])


@router.get("/labels")
def list_labels(session: Session = Depends(get_session)):
    return [label_out(lbl) for lbl in session.scalars(select(Label).order_by(Label.spans_key, Label.id))]


@router.post("/labels", status_code=201)
def create_label(body: LabelIn, session: Session = Depends(get_session)):
    if body.style not in LABEL_STYLES:
        raise HTTPException(422, f"style must be one of {LABEL_STYLES}")
    label = Label(**body.model_dump())
    session.add(label)
    try:
        session.commit()
    except IntegrityError as e:
        raise HTTPException(409, "label already exists for that spans_key") from e
    return label_out(label)


@router.patch("/labels/{label_id:int}")
def update_label(label_id: int, body: LabelPatch, session: Session = Depends(get_session)):
    label = session.get(Label, label_id) or _404()
    if body.style is not None and body.style not in LABEL_STYLES:
        raise HTTPException(422, f"style must be one of {LABEL_STYLES}")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(label, k, v)
    session.commit()
    return label_out(label)


@router.delete("/labels/{label_id:int}", status_code=204)
def delete_label(label_id: int, session: Session = Depends(get_session)):
    session.delete(session.get(Label, label_id) or _404())
    session.commit()


def _404():
    raise HTTPException(404, "label not found")
