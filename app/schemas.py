import re
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

from .models import Provider


# ---- auth -------------------------------------------------------------------

class UserRegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(max_length=256)
    phone_number: str | None = Field(default=None, max_length=32)

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Full name is required.")
        return v

    @field_validator("password")
    @classmethod
    def _password_policy(cls, v: str) -> str:
        # Same rule the app shows on the register form.
        ok = (
            len(v) >= 10
            and re.search(r"[A-Z]", v)
            and re.search(r"[a-z]", v)
            and re.search(r"\d", v)
            and re.search(r"[^A-Za-z0-9]", v)
        )
        if not ok:
            raise ValueError(
                "Password must be at least 10 characters and include an uppercase letter, "
                "a lowercase letter, a digit, and a symbol."
            )
        return v


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    phone_number: str | None = None
    full_name: str
    role: str
    is_active: bool
    is_verified: bool


# ---- wallets / conversions ------------------------------------------------------



class WalletOut(BaseModel):
    id: str
    provider: Provider
    balance: float
    currency_code: str


class TopUpRequest(BaseModel):
    provider: Provider
    amount: Decimal = Field(gt=0, le=1_000_000_000, max_digits=14, decimal_places=2)


class ConversionRequest(BaseModel):
    from_provider: Provider
    to_provider: Provider
    amount: Decimal = Field(gt=0, le=1_000_000_000, max_digits=14, decimal_places=2)
    idempotency_key: str = Field(min_length=8, max_length=100)


class TransactionOut(BaseModel):
    id: str
    from_provider: Provider
    to_provider: Provider
    amount_debited: float
    fee_amount: float
    amount_credited: float
    exchange_rate: float
    status: str
