from typing import Generator, List, Callable, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.core.security import decode_jwt_token
from app.core.exceptions import CredentialsException, PermissionDeniedException
from app.models import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    payload = decode_jwt_token(token)
    if not payload:
        raise CredentialsException(detail="Could not validate credentials or token expired")

    token_type = payload.get("type")
    if token_type not in ["access", "session"]:
        raise CredentialsException(detail="Invalid token type for request")

    user_id: str = payload.get("sub")
    if user_id is None:
        raise CredentialsException(detail="Token payload invalid")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise CredentialsException(detail="User not found or inactive")

    return user


def require_role(*roles: Any) -> Callable:
    allowed_roles = []
    for r in roles:
        if isinstance(r, (list, tuple, set)):
            allowed_roles.extend(r)
        else:
            allowed_roles.append(r)

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            role_names = [r.value if hasattr(r, "value") else str(r) for r in allowed_roles]
            raise PermissionDeniedException(
                detail=f"Operation not permitted. Required role: {role_names}"
            )
        return current_user
    return role_checker
