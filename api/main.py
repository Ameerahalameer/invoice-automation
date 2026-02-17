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
_origins_env = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",") if o.strip()]

if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = [
        "https://invoice-tool.pages.dev",
        "http://localhost:8080",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
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
