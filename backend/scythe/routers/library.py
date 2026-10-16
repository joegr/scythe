from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_session
from ..markdown import collection_markdown
from ..models import Block, Card, File
from ..schemas import BlockPatch, NameIn

router = APIRouter(tags=["library"])


def _file_out(session: Session, f: File) -> dict:
    counts = dict(
        session.execute(
            select(Card.block_id, func.count()).where(Card.block_id.in_([b.id for b in f.blocks])).group_by(Card.block_id)
        ).all()
    )
    return dict(
        id=f.id, name=f.name, created_at=f.created_at,
        blocks=[dict(id=b.id, name=b.name, position=b.position, card_count=counts.get(b.id, 0)) for b in f.blocks],
    )


@router.get("/files")
def list_files(session: Session = Depends(get_session)):
    files = session.scalars(select(File).options(selectinload(File.blocks)).order_by(File.name))
    loose = session.scalar(select(func.count()).select_from(Card).where(Card.block_id.is_(None)))
    return dict(files=[_file_out(session, f) for f in files], loose_cards=loose)


@router.post("/files", status_code=201)
def create_file(body: NameIn, session: Session = Depends(get_session)):
    f = File(name=body.name)
    session.add(f)
    session.commit()
    return _file_out(session, f)


@router.patch("/files/{file_id:int}")
def rename_file(file_id: int, body: NameIn, session: Session = Depends(get_session)):
    f = session.get(File, file_id) or _404()
    f.name = body.name
    session.commit()
    return _file_out(session, f)


@router.delete("/files/{file_id:int}", status_code=204)
def delete_file(file_id: int, session: Session = Depends(get_session)):
    session.delete(session.get(File, file_id) or _404())
    session.commit()


@router.post("/files/{file_id:int}/blocks", status_code=201)
def create_block(file_id: int, body: NameIn, session: Session = Depends(get_session)):
    f = session.get(File, file_id) or _404()
    b = Block(file_id=f.id, name=body.name, position=len(f.blocks))
    session.add(b)
    session.commit()
    return dict(id=b.id, file_id=b.file_id, name=b.name, position=b.position, card_count=0)


@router.patch("/blocks/{block_id:int}")
def update_block(block_id: int, body: BlockPatch, session: Session = Depends(get_session)):
    b = session.get(Block, block_id) or _404()
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(b, k, v)
    session.commit()
    return dict(id=b.id, file_id=b.file_id, name=b.name, position=b.position)


@router.delete("/blocks/{block_id:int}", status_code=204)
def delete_block(block_id: int, session: Session = Depends(get_session)):
    session.delete(session.get(Block, block_id) or _404())
    session.commit()


def _cards(session: Session, *where):
    return list(
        session.scalars(select(Card).options(selectinload(Card.spans)).where(*where).order_by(Card.position, Card.id))
    )


@router.get("/files/{file_id:int}.md", response_class=PlainTextResponse)
def file_markdown(file_id: int, condensed: bool = Query(False), session: Session = Depends(get_session)):
    f = session.get(File, file_id) or _404()
    groups = [(b.name, _cards(session, Card.block_id == b.id)) for b in f.blocks]
    return PlainTextResponse(collection_markdown(f.name, groups, condensed), media_type="text/markdown")


@router.get("/blocks/{block_id:int}.md", response_class=PlainTextResponse)
def block_markdown(block_id: int, condensed: bool = Query(False), session: Session = Depends(get_session)):
    b = session.get(Block, block_id) or _404()
    md = collection_markdown(b.name, [(None, _cards(session, Card.block_id == b.id))], condensed)
    return PlainTextResponse(md, media_type="text/markdown")


def _404():
    raise HTTPException(404, "not found")
