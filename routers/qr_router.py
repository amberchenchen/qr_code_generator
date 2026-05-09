from datetime import datetime, timedelta, timezone

QR_TTL_MINUTES = 3


def _default_expires_at() -> datetime:
    """Return UTC-naive datetime 3 minutes from now."""
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=QR_TTL_MINUTES)

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import QRCode, ScanLog
from schemas import (
    AnalyticsResponse,
    CreateQRRequest,
    QRCodeResponse,
    ScansByDay,
    UpdateQRRequest,
)
from services.cache import cache
from services.qr_image import generate_qr_png
from services.token_generator import generate_token
from services.url_validator import validate_url

router = APIRouter(prefix="/api/qr")

MAX_TOKEN_RETRIES = 5


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _build_response(qr: QRCode, base: str) -> QRCodeResponse:
    return QRCodeResponse(
        token=qr.qr_token,
        short_url=f"{base}/r/{qr.qr_token}",
        qr_code_url=f"{base}/api/qr/{qr.qr_token}/image",
        original_url=qr.original_url,
        created_at=qr.created_at,
        updated_at=qr.updated_at,
        expires_at=qr.expires_at,
        is_deleted=qr.is_deleted,
    )



@router.post("/create", response_model=QRCodeResponse)
def create_qr(body: CreateQRRequest, request: Request, db: Session = Depends(get_db)):
    """
    Create a new QR code.
    Token generation: hash(url + timestamp_ns) → SHA-256 → Base62 [A-Za-z0-9] → 7 chars.
    Collision → retry up to MAX_TOKEN_RETRIES times.
    """
    valid, result = validate_url(body.url)
    if not valid:
        raise HTTPException(status_code=422, detail=result)

    normalized_url = result

    token = None
    for _ in range(MAX_TOKEN_RETRIES):
        candidate = generate_token(normalized_url)
        if not db.query(QRCode).filter(QRCode.qr_token == candidate).first():
            token = candidate
            break

    if token is None:
        raise HTTPException(status_code=500, detail="Failed to generate unique token; try again")

    qr = QRCode(
        qr_token=token,
        original_url=normalized_url,
        expires_at=_default_expires_at(),
    )
    db.add(qr)
    db.commit()
    db.refresh(qr)

    cache.set(token, normalized_url)
    return _build_response(qr, _base_url(request))


@router.get("/{token}", response_model=QRCodeResponse)
def get_qr(token: str, request: Request, db: Session = Depends(get_db)):
    qr: QRCode | None = db.query(QRCode).filter(QRCode.qr_token == token).first()
    if qr is None:
        raise HTTPException(status_code=404, detail="QR code not found")
    return _build_response(qr, _base_url(request))


@router.patch("/{token}", response_model=QRCodeResponse)
def update_qr(token: str, body: UpdateQRRequest, request: Request, db: Session = Depends(get_db)):
    qr: QRCode | None = db.query(QRCode).filter(QRCode.qr_token == token).first()
    if qr is None:
        raise HTTPException(status_code=404, detail="QR code not found")
    if qr.is_deleted:
        raise HTTPException(status_code=410, detail="Cannot update a deleted QR code")

    valid, result = validate_url(body.url)
    if not valid:
        raise HTTPException(status_code=422, detail=result)

    qr.original_url = result
    qr.expires_at = _default_expires_at()
    qr.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(qr)

    cache.delete(token)
    return _build_response(qr, _base_url(request))


@router.delete("/{token}")
def delete_qr(token: str, db: Session = Depends(get_db)):
    """Soft delete: sets is_deleted=True, returns 410 on subsequent redirects."""
    qr: QRCode | None = db.query(QRCode).filter(QRCode.qr_token == token).first()
    if qr is None:
        raise HTTPException(status_code=404, detail="QR code not found")
    if qr.is_deleted:
        raise HTTPException(status_code=410, detail="QR code is already deleted")

    qr.is_deleted = True
    qr.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    cache.delete(token)
    return {"detail": "QR code deleted"}


@router.get("/{token}/image")
def get_qr_image(token: str, request: Request, db: Session = Depends(get_db)):
    """Return the QR code as a PNG image. The QR encodes the short redirect URL."""
    qr: QRCode | None = db.query(QRCode).filter(QRCode.qr_token == token).first()
    if qr is None:
        raise HTTPException(status_code=404, detail="QR code not found")

    short_url = f"{_base_url(request)}/r/{token}"
    png_bytes = generate_qr_png(short_url)
    return Response(content=png_bytes, media_type="image/png")


@router.get("/{token}/analytics", response_model=AnalyticsResponse)
def get_analytics(token: str, db: Session = Depends(get_db)):
    qr: QRCode | None = db.query(QRCode).filter(QRCode.qr_token == token).first()
    if qr is None:
        raise HTTPException(status_code=404, detail="QR code not found")

    rows = (
        db.query(
            func.strftime("%Y-%m-%d", ScanLog.scanned_at).label("date"),
            func.count().label("count"),
        )
        .filter(ScanLog.qr_token == token)
        .group_by("date")
        .order_by("date")
        .all()
    )

    return AnalyticsResponse(
        token=token,
        total_scans=qr.scan_count,
        scans_by_day=[ScansByDay(date=r.date, count=r.count) for r in rows],
    )
