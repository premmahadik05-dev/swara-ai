from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy.orm import Session

from ..deps import get_db
from ..languages import LANGUAGES
from ..models import Customer
from ..auth import require_owner
from ..services import customers as svc
from ..services import export as xp

router = APIRouter(prefix="/api/customers", tags=["customers"])

def _lang(value: str) -> str:
    if value != "" and value not in LANGUAGES:
        raise ValueError("language must be empty or one of: " + ", ".join(LANGUAGES))
    return value


Lang = Annotated[str, AfterValidator(_lang)]  # "" or any key in the language registry
_PHONE = r"^[0-9+()\- ]{0,20}$"


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(default="", pattern=_PHONE)
    language: Lang = ""
    notes: str = Field(default="", max_length=300)


class CustomerPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    phone: Optional[str] = Field(default=None, pattern=_PHONE)
    language: Optional[Lang] = None
    notes: Optional[str] = Field(default=None, max_length=300)
    is_active: Optional[bool] = None


@router.get("")
def list_customers(
    q: str = "", sort: str = "recent", include_synthetic: bool = True, page: int = 1, page_size: int = 20,
    db: Session = Depends(get_db),
):
    return svc.list_customers(db, q=q[:60], sort=sort, include_synthetic=include_synthetic, page=page, page_size=page_size)


@router.get("/export.csv", dependencies=[Depends(require_owner)])
def export_customers(q: str = "", sort: str = "recent", include_synthetic: bool = True, db: Session = Depends(get_db)):
    """Customers as CSV. Owner only: staff can open one customer at a time, but a bulk file of names and phone numbers is the owner's to take.
    Declared before /{customer_id} so the path is never read as an id."""
    body, truncated = svc.export_customers(db, q=q[:60], sort=sort, include_synthetic=include_synthetic)
    return xp.csv_response(body, "customers", truncated)


@router.get("/{customer_id}")
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    out = svc.detail(db, customer_id)
    if out is None:
        raise HTTPException(404, "Customer not found")
    return out


@router.post("", status_code=201, dependencies=[Depends(require_owner)])
def create_customer(body: CustomerIn, db: Session = Depends(get_db)):
    c = Customer(name=body.name.strip(), phone=body.phone.strip(), language=body.language, notes=body.notes.strip(), is_synthetic=False)
    db.add(c)
    db.commit()
    return svc.serialize(c)


@router.patch("/{customer_id}", dependencies=[Depends(require_owner)])
def patch_customer(customer_id: int, body: CustomerPatch, db: Session = Depends(get_db)):
    c = db.get(Customer, customer_id)
    if c is None:
        raise HTTPException(404, "Customer not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    return svc.detail(db, c.id)
