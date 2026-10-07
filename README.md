# AI-Based Intelligent Examination Platform (Backend - Weeks 1–2)

Production-quality backend for an AI-Based Intelligent Examination Platform featuring automated proctoring schema, dynamic exam paper generation, JWT authentication with role separation, and question bank management.

---

## Tech Stack
- **Python 3.11+ / 3.12**
- **FastAPI** & **Pydantic v2**
- **SQLAlchemy 2.0 ORM** (typed `Mapped[]` style) & **Alembic**
- **PostgreSQL 15** (via docker-compose) / SQLite support
- **python-jose** (JWT) & **passlib[bcrypt]**
- **pytest** & **pytest-cov** (>= 85% coverage)

---

## Architecture & Project Structure
```text
app/
  main.py
  core/        (config.py, security.py, deps.py, exceptions.py)
  db/          (base.py, session.py)
  models/      (enums.py, __init__.py containing User, QuestionBank, Option, Exam, ExamQuestion, ExamSession, Answer, Result, ProctorEvent)
  schemas/     (auth.py, question.py, exam.py, session.py)
  api/v1/      (auth.py, questions.py, exams.py, sessions.py)
  services/    (auth_service.py, question_service.py, exam_service.py, session_service.py, paper_generator.py)
alembic/ , tests/ , docker-compose.yml , requirements.txt , seed.py , README.md
```

---

## Quickstart & Setup Instructions

### 1. Environment & Dependencies
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
pip install -r requirements.txt
```

### 2. Database Migrations & Seeding
Run Alembic migrations to create tables:
```bash
alembic upgrade head
```

Seed initial users (1 admin, 1 examiner, 3 students):
```bash
python3 seed.py
```
Default password for all seeded users: `Password123!`

### 3. Run Application
Start the FastAPI server using uvicorn:
```bash
uvicorn app.main:app --reload
```
Interactive OpenAPI documentation will be available at [http://localhost:8000/docs](http://localhost:8000/docs).

### 4. Running Tests & Coverage
Run the full pytest suite with coverage:
```bash
pytest --cov=app --cov-report=term-missing
```

---

## API Endpoint Reference Table

| Category | Method | Endpoint | Access Level | Description |
|---|---|---|---|---|
| **Auth** | `POST` | `/api/v1/auth/register` | Public / Admin | Register user (student default; admin required for examiner/admin creation) |
| **Auth** | `POST` | `/api/v1/auth/login` | Public | Authenticate user & return JWT tokens |
| **Auth** | `GET` | `/api/v1/auth/me` | Authenticated | Get current authenticated user profile |
| **Auth** | `POST` | `/api/v1/auth/refresh` | Public | Refresh JWT access token |
| **Exam Auth** | `POST` | `/api/v1/exams/{id}/access-token` | Student/Examiner/Admin | Issue exam-specific access token bound to student & exam |
| **Exam Auth** | `POST` | `/api/v1/exams/{id}/start` | Student | Validate exam access token, start session & issue short-lived session token |
| **Exam Auth** | `POST` | `/api/v1/sessions/{id}/heartbeat` | Student | Re-issue fresh session token, rotate JTI, detect IP/User-Agent changes |
| **Questions** | `POST` | `/api/v1/questions` | Examiner / Admin | Create question with type validation (MCQ, multi_select, short/long answer, image_upload) |
| **Questions** | `GET` | `/api/v1/questions` | Examiner / Admin | List/filter questions by subject, difficulty, type, tags |
| **Questions** | `GET` | `/api/v1/questions/{id}` | Examiner / Admin | Get detailed question by ID |
| **Questions** | `PUT` | `/api/v1/questions/{id}` | Examiner (owner) / Admin | Update question |
| **Questions** | `DELETE` | `/api/v1/questions/{id}` | Examiner (owner) / Admin | Soft delete / deactivate question |
| **Exams** | `POST` | `/api/v1/exams` | Examiner / Admin | Create exam configuration with selection rules & proctoring settings |
| **Exams** | `GET` | `/api/v1/exams` | Authenticated | List exams |
| **Exams** | `GET` | `/api/v1/exams/{id}` | Authenticated | Get exam by ID |
| **Exams** | `PUT` | `/api/v1/exams/{id}` | Examiner (owner) / Admin | Update exam configuration |
| **Exams** | `POST` | `/api/v1/exams/{id}/publish` | Examiner (owner) / Admin | Publish exam |
| **Exams** | `DELETE` | `/api/v1/exams/{id}` | Examiner (owner) / Admin | Delete exam |
| **Sessions** | `GET` | `/api/v1/sessions/{id}/paper` | Student / Examiner / Admin | Retrieve deterministic generated paper for active session |
| **Sessions** | `POST` | `/api/v1/sessions/{id}/answers` | Student | Save/update candidate question answer |
| **Sessions** | `POST` | `/api/v1/sessions/{id}/events` | Student | Log proctoring event (tab_switch, gaze_away, etc.) |
| **Sessions** | `POST` | `/api/v1/sessions/{id}/submit` | Student | Submit exam session |

---

## Week 1–2 Requirement Implementation Checklist

- [x] **SQLAlchemy 2.0 ORM & Alembic Migration**: UUID primary keys, FKs with ondelete rules, constraints, check constraints, enums (`app/models/__init__.py`, `alembic/versions/0001_initial.py`).
- [x] **Database Seed Script**: Seeds 1 admin, 1 examiner, and 3 test students (`seed.py`).
- [x] **JWT Auth with Role Separation**: Access & Refresh tokens, claims (`sub`, `role`, `exp`, `jti`, `type`), `require_role` dependency (`app/core/security.py`, `app/core/deps.py`, `app/api/v1/auth.py`).
- [x] **Student Exam Entry & Heartbeat Token Rotation**: Exam access token bound to student + exam, start endpoint session token generation, heartbeat JTI rotation & IP/User-Agent monitoring (`app/services/auth_service.py`, `app/api/v1/auth.py`).
- [x] **Question Bank API & Validation Rules**: MCQ, multi_select, short/long answer, image upload validations, examiner ownership checks (`app/schemas/question.py`, `app/services/question_service.py`, `app/api/v1/questions.py`).
- [x] **Exam Configuration API**: Time window check, duration vs window length validation, bank question availability check (409 conflict), edit-after-start lock (`app/services/exam_service.py`, `app/api/v1/exams.py`).
- [x] **Deterministic Paper Generator Service**: SHA-256 seed (`exam_id + student_id + server_secret`), rule-based question selection & shuffling (`app/services/paper_generator.py`).
- [x] **Pytest Test Suite**: > 85% coverage achieved across question validation, exam config constraints, paper generator determinism, and session token rotation (`tests/`).
