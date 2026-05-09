from contextlib import asynccontextmanager

from fastapi import FastAPI

import models
from database import engine
from routers import qr_router, redirect_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup
    models.Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="QR Code Generator",
    description="Dynamic QR code system — create, redirect, update, delete",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(qr_router.router)
app.include_router(redirect_router.router)


@app.get("/")
def root():
    return {"message": "QR Code Generator API", "docs": "/docs"}
