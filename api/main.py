"""FastAPI application — Invoice Automation API."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router

app = FastAPI(
    title="Invoice Automation API",
    description="Financial-grade invoice generation from PO + Timesheets + Template.",
    version="1.0.0",
)

# CORS — allow frontend origins
# Set ALLOWED_ORIGINS="*" to allow any origin (for standalone HTML usage)
_origins_env = os.environ.get("ALLOWED_ORIGINS", "")
_origins_list = [o.strip() for o in _origins_env.split(",") if o.strip()]

_allow_all = "*" in _origins_list

if _allow_all:
    ALLOWED_ORIGINS: list[str] = ["*"]
elif _origins_list:
    ALLOWED_ORIGINS = _origins_list
else:
    ALLOWED_ORIGINS = [
        "https://ameerahalameer.github.io",
        "https://invoice-tool.pages.dev",
        "http://localhost:8080",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=not _allow_all,  # credentials not allowed with wildcard
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)

app.include_router(router)


@app.get("/")
async def root():
    return {
        "name": "Invoice Automation API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
