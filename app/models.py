import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Provider(str, enum.Enum):
    """Wire values match the Android client's @SerialName values exactly."""

    QMONEY = "QMONEY"
    ORANGE_MONEY = "ORANGE_MONEY"
    AFRIMONEY = "AFRIMONEY"
    USD = "USD"

    @property
    def currency_code(self) -> str:
        return "USD" if self is Provider.USD else "SLL"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    wallets: Mapped[list["Wallet"]] = relationship(back_populates="user")


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_wallet_user_provider"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))

    user: Mapped[User] = relationship(back_populates="wallets")

    @property
    def currency_code(self) -> str:
        return Provider(self.provider).currency_code


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_tx_user_idem"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    from_provider: Mapped[str] = mapped_column(String(20))
    to_provider: Mapped[str] = mapped_column(String(20))
    amount_debited: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    amount_credited: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    idempotency_key: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class RefreshToken(Base):
    """Server-side record of issued refresh tokens, so they can be rotated and revoked."""

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
