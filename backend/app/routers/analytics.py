from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import get_db
from ..services import analytics as svc

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/overview")
def overview(days: int = 30, include_synthetic: bool = True, db: Session = Depends(get_db)):
    return svc.overview(db, days=min(max(days, 1), 90), include_synthetic=include_synthetic)


@router.get("/sales")
def sales(grain: str = "day", periods: int = 30, include_synthetic: bool = True, db: Session = Depends(get_db)):
    return svc.sales_series(db, grain=grain, periods=periods, include_synthetic=include_synthetic)


@router.get("/inventory")
def inventory(db: Session = Depends(get_db)):
    return svc.inventory_summary(db)


@router.get("/demand")
def demand(days: int = 30, include_synthetic: bool = True, db: Session = Depends(get_db)):
    return svc.demand_insights(db, days=days, include_synthetic=include_synthetic)


@router.get("/latency")
def latency(hours: int = 168, db: Session = Depends(get_db)):
    return svc.latency(db, hours=min(max(hours, 1), 24 * 30))


@router.get("/stock-movement")
def stock_movement(days: int = 30, db: Session = Depends(get_db)):
    return svc.stock_movement(db, days=min(max(days, 1), 365))
