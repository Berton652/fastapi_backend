from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Always 401 (never 403) so the app's refresh-on-401 logic triggers reliably.
    if creds is None:
        raise unauthorized
    payload = decode_token(creds.credentials, "access")
    if payload is None:
        raise unauthorized
    user = db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise unauthorized
    return user
