from __future__ import annotations

from typing import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from .gnani.client import GnaniClient
from .services.catalog import CatalogCache


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_catalog(request: Request) -> CatalogCache:
    return request.app.state.catalog


def get_gnani(request: Request) -> GnaniClient:
    return request.app.state.gnani
