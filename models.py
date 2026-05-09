import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text
from sqlalchemy.sql import func
from database import Base


class QRCode(Base):
    __tablename__ = "qr_codes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    qr_token = Column(String(10), unique=True, nullable=False, index=True)
    original_url = Column(Text, nullable=False)
    is_deleted = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=True)
    scan_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    qr_token = Column(String(10), nullable=False, index=True)
    scanned_at = Column(DateTime, server_default=func.now())
    ip_address = Column(String, nullable=True)
