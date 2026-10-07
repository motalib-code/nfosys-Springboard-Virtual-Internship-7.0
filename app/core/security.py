import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_token(
    claims: Dict[str, Any],
    expires_delta: timedelta,
    token_type: str = "access"
) -> str:
    to_encode = claims.copy()
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    jti = str(uuid.uuid4())
    to_encode.update({
        "exp": expire,
        "iat": now,
        "type": token_type,
        "jti": jti,
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_access_token(user_id: str, role: str) -> str:
    return create_token(
        claims={"sub": user_id, "role": role},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access"
    )


def create_refresh_token(user_id: str, role: str) -> str:
    return create_token(
        claims={"sub": user_id, "role": role},
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh"
    )


def create_exam_access_token(student_id: str, exam_id: str) -> str:
    return create_token(
        claims={"sub": student_id, "student_id": student_id, "exam_id": exam_id},
        expires_delta=timedelta(minutes=settings.EXAM_ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="exam_access"
    )


def create_session_token(session_id: str, student_id: str, exam_id: str) -> str:
    return create_token(
        claims={"sub": student_id, "session_id": session_id, "student_id": student_id, "exam_id": exam_id},
        expires_delta=timedelta(minutes=settings.SESSION_TOKEN_EXPIRE_MINUTES),
        token_type="session"
    )


def decode_jwt_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return {}
