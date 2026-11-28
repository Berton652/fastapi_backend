from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Provider, RefreshToken, User, Wallet
from ..schemas import RefreshRequest, TokenResponse, UserLoginRequest, UserOut, UserRegisterRequest
from ..security import (
    DUMMY_HASH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        phone_number=u.phone_number,
        full_name=u.full_name,
        role=u.role,
        is_active=u.is_active,
        is_verified=u.is_verified,
    )


def _issue_tokens(db: Session, user_id: str) -> TokenResponse:
    refresh, jti, exp = create_refresh_token(user_id)
    db.add(RefreshToken(jti=jti, user_id=user_id, expires_at=exp))
    db.commit()
    return TokenResponse(access_token=create_access_token(user_id), refresh_token=refresh)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: UserRegisterRequest, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(
        email=email,
        full_name=body.full_name,
        phone_number=body.phone_number,
        password_hash=hash_password(body.password),
    )
    user.wallets = [Wallet(provider=p.value) for p in Provider]
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # lost a race with a concurrent registration
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    return _user_out(user)


@router.post("/login", response_model=TokenResponse)
def login(body: UserLoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not ok or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.", headers={"WWW-Authenticate": "Bearer"}
        )
    return _issue_tokens(db, user.id)


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    invalid = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Invalid refresh token.", headers={"WWW-Authenticate": "Bearer"}
    )
    payload = decode_token(body.refresh_token, "refresh")
    if payload is None:
        raise invalid
    record = db.get(RefreshToken, payload["jti"])
    if record is None or record.user_id != payload["sub"]:
        raise invalid
    if record.revoked:
        # A rotated-out token is being replayed: assume theft and kill every session.
        db.execute(update(RefreshToken).where(RefreshToken.user_id == record.user_id).values(revoked=True))
        db.commit()
        raise invalid
    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise invalid
    record.revoked = True  # rotation: each refresh token works exactly once
    db.commit()
    return _issue_tokens(db, user.id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token, "refresh")
    if payload is not None:
        record = db.get(RefreshToken, payload["jti"])
        if record is not None:
            record.revoked = True
            db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)
