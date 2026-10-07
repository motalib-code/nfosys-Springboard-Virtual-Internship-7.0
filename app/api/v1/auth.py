from typing import Optional
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.core.deps import get_db, get_current_user, oauth2_scheme
from app.schemas.auth import (
    UserRegister, UserLogin, TokenResponse, TokenRefreshRequest,
    UserOut, ExamAccessTokenResponse, ExamStartRequest,
    SessionTokenResponse, HeartbeatResponse
)
from app.services.auth_service import AuthService
from app.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    user_in: UserRegister,
    db: Session = Depends(get_db),
    request: Request = None
):
    # Retrieve bearer token manually if supplied to check optional admin auth for examiner/admin creation
    current_user: Optional[User] = None
    auth_header = request.headers.get("Authorization") if request else None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            current_user = get_current_user(token=token, db=db)
        except Exception:
            current_user = None

    return AuthService.register_user(db, user_in, current_user=current_user)


@router.post("/login", response_model=TokenResponse)
def login(login_in: UserLogin, db: Session = Depends(get_db)):
    return AuthService.authenticate_user(db, login_in)


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(refresh_in: TokenRefreshRequest, db: Session = Depends(get_db)):
    return AuthService.refresh_access_token(db, refresh_in.refresh_token)


# Additional Auth / Exam access routes
exam_auth_router = APIRouter(tags=["Exam Auth"])


@exam_auth_router.post("/exams/{exam_id}/access-token", response_model=ExamAccessTokenResponse)
def get_exam_access_token(
    exam_id: str,
    student_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    token = AuthService.issue_exam_access_token(db, exam_id, current_user, student_id=student_id)
    return {"exam_access_token": token, "token_type": "bearer"}


@exam_auth_router.post("/exams/{exam_id}/start", response_model=SessionTokenResponse)
def start_exam_session(
    exam_id: str,
    start_req: ExamStartRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "unknown")
    return AuthService.start_exam(
        db=db,
        exam_id=exam_id,
        exam_access_token=start_req.exam_access_token,
        current_user=current_user,
        client_ip=client_ip,
        user_agent=user_agent
    )


@exam_auth_router.post("/sessions/{id}/heartbeat", response_model=HeartbeatResponse)
def session_heartbeat(
    id: str,
    request: Request,
    raw_token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "unknown")
    return AuthService.process_heartbeat(
        db=db,
        session_id=id,
        raw_token=raw_token,
        current_user=current_user,
        client_ip=client_ip,
        user_agent=user_agent
    )
