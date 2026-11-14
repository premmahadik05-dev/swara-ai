"""Owner-only diagnostics: voice response time by stage, Gnani call health."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth import require_owner
from ..deps import get_db
from ..services import diagnostics as svc

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("/voice", dependencies=[Depends(require_owner)])
def voice(request: Request, hours: int = 168, db: Session = Depends(get_db)):
    """Where the time goes for spoken orders (from the turns this server recorded) and how the Gnani calls are doing. Owner only."""
    return svc.voice_diagnostics(db, request.app.state.settings, request.app.state.gnani.budget.used, hours=min(max(hours, 1), 24 * 30))
