import os
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.db.base import Base
from app.core.deps import get_db
from app.main import app
from app.models import User, UserRole, QuestionBank, QuestionType, Difficulty, Option, Exam, ExamStatus
from app.core.security import get_password_hash, create_access_token

TEST_SQLALCHEMY_DATABASE_URL = "sqlite:///./test_exam_platform.db"

engine = create_engine(
    TEST_SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def test_admin(db_session):
    admin = User(
        name="Test Admin",
        email="admin_test@example.com",
        password_hash=get_password_hash("password123"),
        role=UserRole.ADMIN,
        is_active=True
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin


@pytest.fixture
def test_examiner(db_session):
    examiner = User(
        name="Test Examiner",
        email="examiner_test@example.com",
        password_hash=get_password_hash("password123"),
        role=UserRole.EXAMINER,
        is_active=True
    )
    db_session.add(examiner)
    db_session.commit()
    db_session.refresh(examiner)
    return examiner


@pytest.fixture
def test_student(db_session):
    student = User(
        name="Test Student 1",
        email="student1_test@example.com",
        password_hash=get_password_hash("password123"),
        role=UserRole.STUDENT,
        is_active=True
    )
    db_session.add(student)
    db_session.commit()
    db_session.refresh(student)
    return student


@pytest.fixture
def test_student_2(db_session):
    student = User(
        name="Test Student 2",
        email="student2_test@example.com",
        password_hash=get_password_hash("password123"),
        role=UserRole.STUDENT,
        is_active=True
    )
    db_session.add(student)
    db_session.commit()
    db_session.refresh(student)
    return student


@pytest.fixture
def admin_headers(test_admin):
    token = create_access_token(test_admin.id, test_admin.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def examiner_headers(test_examiner):
    token = create_access_token(test_examiner.id, test_examiner.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def student_headers(test_student):
    token = create_access_token(test_student.id, test_student.role.value)
    return {"Authorization": f"Bearer {token}"}
