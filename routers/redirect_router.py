from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from models import QRCode, ScanLog
from services.cache import cache as redirect_cache

router = APIRouter()


def _record_scan(db: Session, token: str, ip: Optional[str]) -> None:
    db.add(ScanLog(qr_token=token, ip_address=ip))
    db.query(QRCode).filter(QRCode.qr_token == token).update(
        {QRCode.scan_count: QRCode.scan_count + 1}
    )
    db.commit()


@router.get("/r/{token}")
def redirect(token: str, request: Request, db: Session = Depends(get_db)):
    """Redirect fallback flow: Cache -> DB -> 404/410 (from slides mermaid diagram)"""
    ip = request.client.host if request.client else None

    # 1. Cache hit — skip DB entirely
    cached_url = redirect_cache.get(token)
    if cached_url:
        _record_scan(db, token, ip)
        return RedirectResponse(url=cached_url, status_code=302)

    # 2. Cache miss — query DB
    qr: Optional[QRCode] = db.query(QRCode).filter(QRCode.qr_token == token).first()

    if qr is None:
        return JSONResponse(status_code=404, content={"detail": "QR code not found"})

    if qr.is_deleted:
        return JSONResponse(status_code=410, content={"detail": "QR code has been deleted"})

    if qr.expires_at and datetime.now(timezone.utc).replace(tzinfo=None) > qr.expires_at:
        return JSONResponse(status_code=410, content={"detail": "QR code has expired"})

    # 3. Warm cache, record scan, redirect
    redirect_cache.set(token, qr.original_url)
    _record_scan(db, token, ip)
    return RedirectResponse(url=qr.original_url, status_code=302)
