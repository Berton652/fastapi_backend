from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Provider, Transaction, User
from ..schemas import ConversionRequest, TransactionOut
from ..services.conversion import ConversionError, convert

router = APIRouter(prefix="/conversions", tags=["conversions"])


def tx_out(t: Transaction) -> TransactionOut:
    return TransactionOut(
        id=t.id,
        from_provider=Provider(t.from_provider),
        to_provider=Provider(t.to_provider),
        amount_debited=float(t.amount_debited),
        fee_amount=float(t.fee_amount),
        amount_credited=float(t.amount_credited),
        exchange_rate=float(t.exchange_rate),
        status=t.status,
    )


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_conversion(
    body: ConversionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        tx = convert(db, settings, user, body.from_provider, body.to_provider, body.amount, body.idempotency_key)
    except ConversionError as e:
        raise HTTPException(e.status_code, e.detail)
    return tx_out(tx)


@router.get("", response_model=list[TransactionOut])
def list_conversions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc(), Transaction.id)
        .limit(50)
    ).all()
    return [tx_out(t) for t in rows]
