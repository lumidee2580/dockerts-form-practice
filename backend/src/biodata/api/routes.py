"""API routes mounted under ``/api/v1``."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from biodata import service
from biodata.db import get_session
from biodata.pdf import render_records
from biodata.schemas import BioRecordCreate, BioRecordPage, BioRecordRead

router = APIRouter(tags=["bio-records"])

SessionDep = Annotated[Session, Depends(get_session)]
IdempotencyKeyDep = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        description="Client generated key making this write replay-safe.",
    ),
]


@router.post(
    "/bio-records",
    response_model=BioRecordRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {"description": "Replay of an identical earlier request."},
        status.HTTP_409_CONFLICT: {"description": "Idempotency key reused with a different body."},
    },
)
def create_bio_record(
    payload: BioRecordCreate,
    idempotency_key: IdempotencyKeyDep,
    session: SessionDep,
    response: Response,
) -> BioRecordRead:
    """Create a biodata record, idempotently on ``Idempotency-Key``."""
    try:
        record, created = service.create_record(session, payload, idempotency_key)
    except service.IdempotencyKeyReuseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return BioRecordRead.model_validate(record)


@router.get("/bio-records", response_model=BioRecordPage)
def list_bio_records(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BioRecordPage:
    """Return a page of records ordered by ``created_at`` descending."""
    items, total = service.list_records(session, limit=limit, offset=offset)
    return BioRecordPage(
        items=[BioRecordRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/bio-records/export.pdf", response_class=Response)
def export_bio_records(session: SessionDep) -> Response:
    """Download every stored biodata record as a PDF."""
    records: list[BioRecordRead] = []
    offset = 0
    while True:
        items, _ = service.list_records(session, limit=100, offset=offset)
        records.extend(BioRecordRead.model_validate(item) for item in items)
        if len(items) < 100:
            break
        offset += len(items)

    return Response(
        content=render_records(records),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="biodata-records.pdf"'},
    )


@router.get("/bio-records/{record_id}", response_model=BioRecordRead)
def get_bio_record(record_id: uuid.UUID, session: SessionDep) -> BioRecordRead:
    """Return a single record by id."""
    try:
        record = service.get_record(session, record_id)
    except service.RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return BioRecordRead.model_validate(record)
