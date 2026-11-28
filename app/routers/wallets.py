from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Provider, User, Wallet
from ..schemas import TopUpRequest, WalletOut

router = APIRouter(prefix="/wallets", tags=["wallets"])


def wallet_out(w: Wallet) -> WalletOut:
    return WalletOut(id=w.id, provider=Provider(w.provider), balance=float(w.balance), currency_code=w.currency_code)


@router.get("", response_model=list[WalletOut])
def list_wallets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallets = db.scalars(select(Wallet).where(Wallet.user_id == user.id)).all()
    order = {p.value: i for i, p in enumerate(Provider)}
    return [wallet_out(w) for w in sorted(wallets, key=lambda w: order[w.provider])]


@router.post("/top-up", response_model=WalletOut)
def top_up(
    body: TopUpRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.allow_simulated_topup:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Top-ups are disabled on this server.")
    wallet = db.scalar(
        select(Wallet).where(Wallet.user_id == user.id, Wallet.provider == body.provider.value).with_for_update()
    )
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found.")
    wallet.balance = wallet.balance + body.amount
    db.commit()
    return wallet_out(wallet)
