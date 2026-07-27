from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import logging
import os

from app.core.config import settings
from app.api.v1 import router as api_router

logger = logging.getLogger(__name__)

app = FastAPI(title="Expandimo Automation", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": str(exc)})

# Serve uploaded files (CVs etc)
os.makedirs(settings.STORAGE_PATH, exist_ok=True)
app.mount("/storage", StaticFiles(directory=settings.STORAGE_PATH), name="storage")

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
