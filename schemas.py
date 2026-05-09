from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CreateQRRequest(BaseModel):
    url: str


class UpdateQRRequest(BaseModel):
    url: str


class QRCodeResponse(BaseModel):
    token: str
    short_url: str
    qr_code_url: str
    original_url: str
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    is_deleted: bool

    model_config = {"from_attributes": True}


class ScansByDay(BaseModel):
    date: str
    count: int


class AnalyticsResponse(BaseModel):
    token: str
    total_scans: int
    scans_by_day: list[ScansByDay]
