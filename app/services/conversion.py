from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Provider, Transaction, User, Wallet

CENT = Decimal("0.01")


class ConversionError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Quote:
    rate: Decimal
    gross: Decimal
    fee: Decimal
    credited: Decimal


def quote(settings: Settings, src: Provider, dst: Provider, amount: Decimal) -> Quote:
    """Pure pricing logic: rate, fee and credited amount. Mirrors the app's preview."""
    involves_usd = Provider.USD in (src, dst)
    if not involves_usd:
        rate = Decimal(1)
    elif src is Provider.USD:
        rate = settings.usd_to_sll
    else:
        rate = Decimal(1) / settings.usd_to_sll
    fee_pct = settings.usd_fee if involves_usd else settings.network_fee

    gross = _q(amount * rate)
    fee = _q(gross * fee_pct)
    return Quote(rate=rate, gross=gross, fee=fee, credited=gross - fee)  # credited + fee == gross, always


def _same_request(tx: Transaction, src: Provider, dst: Provider, amount: Decimal) -> bool:
    return tx.from_provider == src.value and tx.to_provider == dst.value and tx.amount_debited == amount


def convert(
    db: Session,
    settings: Settings,
    user: User,
    src: Provider,
    dst: Provider,
    amount: Decimal,
    idempotency_key: str,
) -> Transaction:
    if src is dst:
        raise ConversionError(400, "Choose two different wallets.")

    # Idempotent replay: same key + same request returns the original result;
    # same key + different request is a client bug and must not silently succeed.
    existing = db.scalar(
        select(Transaction).where(Transaction.user_id == user.id, Transaction.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if _same_request(existing, src, dst, amount):
            return existing
        raise ConversionError(409, "Idempotency key was already used for a different request.")

    q = quote(settings, src, dst, amount)
    if q.credited <= 0:
        raise ConversionError(400, "Amount is too small to convert.")

    # Lock both wallets in a fixed order (avoids deadlocks). FOR UPDATE is honoured by
    # PostgreSQL; SQLite serialises writers anyway.
    wallets = {
        w.provider: w
        for w in db.scalars(
            select(Wallet)
            .where(Wallet.user_id == user.id, Wallet.provider.in_([src.value, dst.value]))
            .order_by(Wallet.provider)
            .with_for_update()
        )
    }
    src_wallet, dst_wallet = wallets.get(src.value), wallets.get(dst.value)
    if src_wallet is None or dst_wallet is None:
        raise ConversionError(404, "Wallet not found.")
    if src_wallet.balance < amount:
        raise ConversionError(
            400, f"Insufficient {src.value.replace('_', ' ').title()} balance."
        )

    src_wallet.balance = src_wallet.balance - amount
    dst_wallet.balance = dst_wallet.balance + q.credited
    tx = Transaction(
        user_id=user.id,
        from_provider=src.value,
        to_provider=dst.value,
        amount_debited=amount,
        fee_amount=q.fee,
        amount_credited=q.credited,
        exchange_rate=q.rate.quantize(Decimal("0.00000001")),
        status="COMPLETED",
        idempotency_key=idempotency_key,
    )
    db.add(tx)
    try:
        db.commit()
    except IntegrityError:
        # Two concurrent requests with the same key: the loser returns the winner's row.
        db.rollback()
        existing = db.scalar(
            select(Transaction).where(
                Transaction.user_id == user.id, Transaction.idempotency_key == idempotency_key
            )
        )
        if existing is not None and _same_request(existing, src, dst, amount):
            return existing
        raise ConversionError(409, "Conflicting request, please retry.")
    return tx
