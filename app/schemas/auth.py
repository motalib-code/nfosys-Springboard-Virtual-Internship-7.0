from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional
from datetime import datetime
from app.models.enums import UserRole


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    name: str
    role: Optional[UserRole] = UserRole.STUDENT


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExamAccessTokenResponse(BaseModel):
    exam_access_token: str
    token_type: str = "bearer"


class ExamStartRequest(BaseModel):
    exam_access_token: str


class SessionTokenResponse(BaseModel):
    session_id: str
    session_token: str
    token_type: str = "bearer"


class HeartbeatResponse(BaseModel):
    session_token: str
    is_flagged: bool
    status: str
