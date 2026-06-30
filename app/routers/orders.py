from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_auth
from ..database import get_db

router = APIRouter()


@router.get("/api/orders", response_model=List[schemas.OrderOut])
def list_orders(
    source: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _auth: bool = Depends(require_auth),
):
    query = db.query(models.Order).order_by(models.Order.created_at.desc())
    if source:
        query = query.filter(models.Order.source == source)
    if status:
        query = query.filter(models.Order.status == status)
    return query.all()


@router.patch("/api/orders/{order_id}", response_model=schemas.OrderOut)
def update_order_status(
    order_id: int,
    data: schemas.StatusUpdate,
    db: Session = Depends(get_db),
    _auth: bool = Depends(require_auth),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Замовлення не знайдено")
    order.status = data.status
    db.commit()
    db.refresh(order)
    return order
