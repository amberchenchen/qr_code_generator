from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from models import QRCode, ScanLog
from services.cache import cache

router = APIRouter()


@router.get("/r/{token}")
def redirect(token: str, request: Request, db: Session = Depends(get_db)):
    """
    302 redirect to the original URL.
    Uses cache first (Redis-style), falls back to DB.
    Returns 410 for deleted/expired links, 404 for unknown tokens.
    Why 302 (not 301): browser must re-check each time so URL updates
    and deletions are reflected immediately — no stale browser cache.
    """
    # Cache hit: still need DB to check deleted/expired state
    cached_url = cache.get(token)

    qr: QRCode | None = db.query(QRCode).filter(QRCode.qr_token == token).first()

    if qr is None:
        return JSONResponse(status_code=404, content={"detail": "QR code not found"})

    if qr.is_deleted:
        cache.delete(token)
        return JSONResponse(status_code=410, content={"detail": "QR code has been deleted"})

    if qr.expires_at and datetime.now(timezone.utc).replace(tzinfo=None) > qr.expires_at:
        cache.delete(token)
        return JSONResponse(status_code=410, content={"detail": "QR code has expired"})

    # Refresh cache and record scan
    cache.set(token, qr.original_url)

    ip = request.client.host if request.client else None
    db.add(ScanLog(qr_token=token, ip_address=ip))
    qr.scan_count += 1
    db.commit()

    return RedirectResponse(url=qr.original_url, status_code=302)
