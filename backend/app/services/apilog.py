from __future__ import annotations

from sqlalchemy.orm import Session

from ..gnani.client import CallMeta
from ..models import ApiCall


def log_call(db: Session, meta: CallMeta | None) -> None:
    if meta is None:
        return
    db.add(ApiCall(
        provider=meta.provider, model=meta.model, ok=meta.ok, status_code=meta.status_code,
        error_type=meta.error_type, latency_ms=meta.latency_ms, units=meta.units, attempts=meta.attempts,
    ))
    db.commit()
