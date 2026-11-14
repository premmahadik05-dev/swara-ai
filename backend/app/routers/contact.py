"""Contact form on the landing page. Messages are stored for the shop owner; e-mail forwarding only if SMTP is set up."""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import auth as A
from ..deps import get_db
from ..models import ContactMessage, utcnow
from ..security import auth_rate_limit
from ..services import mailer

log = logging.getLogger("swara.contact")
router = APIRouter(prefix="/api/contact", tags=["contact"])


class ContactIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(max_length=254)
    topic: Literal["general", "demo", "support", "partnership"] = "general"
    message: str = Field(min_length=10, max_length=2000)
    website: str = Field(default="", max_length=200)  # honeypot: people never see or fill this field


def _forward(settings, row: ContactMessage) -> None:
    try:
        mailer.send(settings, settings.contact_to, f"SWARA AI contact: {row.topic}",
                    f"From: {row.name} <{row.email}>\nTopic: {row.topic}\n\n{row.message}\n")
        log.info("contact message %s forwarded by e-mail", row.id)
    except mailer.MailError as exc:
        log.warning("contact message %s not forwarded: %s", row.id, exc)


@router.post("", status_code=201, dependencies=[Depends(auth_rate_limit)])
def send(body: ContactIn, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    s = request.app.state.settings
    email = A.normalise_email(body.email)
    if not A.valid_email(email):
        raise A.err(422, "BAD_EMAIL", "Enter a valid e-mail address so we can reply.")
    if body.website:  # a bot filled the hidden field: pretend it worked, store nothing
        return {"ok": True, "forwarded": False, "message": "Thanks. Your message was received."}
    name = " ".join(body.name.split())
    row = ContactMessage(name=name, email=email, topic=body.topic, message=body.message.strip())
    db.add(row)
    db.commit()
    forwarded = bool(s.contact_to and s.smtp_configured)
    if forwarded:
        tasks.add_task(_forward, s, row)
    return {
        "ok": True, "forwarded": forwarded,
        "message": ("Thanks. Your message was sent to the SWARA AI team." if forwarded else
                    "Thanks. Your message was saved on this server for the shop owner to read."),
    }


@router.get("/messages")
def messages(limit: int = 50, _: A.Principal = Depends(A.require_owner), db: Session = Depends(get_db)):
    rows = db.scalars(select(ContactMessage).order_by(ContactMessage.created_at.desc()).limit(max(1, min(limit, 200))))
    return [{"id": r.id, "name": r.name, "email": r.email, "topic": r.topic, "message": r.message, "created_at": A.iso(r.created_at),
             "handled": r.handled_at is not None} for r in rows]


@router.post("/messages/{message_id}/handled")
def mark_handled(message_id: int, _: A.Principal = Depends(A.require_owner), db: Session = Depends(get_db)):
    row = db.get(ContactMessage, message_id)
    if row is None:
        raise A.err(404, "NOT_FOUND", "No such message.")
    row.handled_at = row.handled_at or utcnow()
    db.commit()
    return {"ok": True}
