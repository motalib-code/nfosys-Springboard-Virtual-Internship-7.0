# AI-Based Intelligent Examination Platform (Backend - Weeks 1–4)

Production-quality backend for an AI-Based Intelligent Examination Platform featuring timed exam session engines, answer submission workflows, objective auto-evaluation, real-time AI proctoring backend via FastAPI WebSockets, and subjective grading pipelines using LangChain and LangGraph.

---

## Architecture Diagram

```mermaid
flowchart TD
    Client[Student Frontend / Browser] -->|REST API| FastAPI[FastAPI Server]
    Client -->|WebSocket /ws/proctor/{id}| WS[WebSocket Proctor Handler]

    WS -->|Async Queue| BGWritter[Background Event Writer]
    BGWritter -->|Batch Write| Postgres[(PostgreSQL 15)]

    FastAPI -->|Submit Exam| ObjEval[Objective Evaluator]
    ObjEval -->|Result & Score Breakdown| Postgres
    ObjEval -->|Enqueue Subjective Answer| GradingQueue[(Grading Queue)]

    Worker[Grading Worker Service] -->|SELECT ... FOR UPDATE SKIP LOCKED| GradingQueue
    Worker -->|LangGraph Pipeline| LangGraph[LangGraph StateGraph]
    LangGraph -->|LLM Evaluation| ChatOpenAI[ChatOpenAI / gpt-4o]
    LangGraph -->|Image OCR| Tesseract[Tesseract OCR Provider]
    LangGraph -->|Save AI Suggestion| Postgres

    Examiner[Examiner Portal] -->|Review & Finalize Marks| FastAPI
    FastAPI -->|Update Result & Audit Log| Postgres
```

---

## Tech Stack
- **Python 3.11+ / 3.12**
- **FastAPI** & **Pydantic v2**
- **SQLAlchemy 2.0 ORM** (typed `Mapped[]` style) & **Alembic**
- **PostgreSQL 15** & **Redis 7** (via docker-compose) / SQLite support
- **python-jose** (JWT) & **passlib[bcrypt]**
- **APScheduler** (`AsyncIOScheduler` + `SQLAlchemyJobStore`)
- **Pillow** & **pytesseract** (OCR)
- **LangChain** (`langchain-core`, `langchain-openai`) & **LangGraph** (`StateGraph`)
- **pytest** & **pytest-cov**

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

### 3. Run Application & Services
Start the FastAPI server:
```bash
uvicorn app.main:app --reload
```
Start the subjective grading queue worker:
```bash
python3 -m app.services.grading_worker
```
Interactive OpenAPI documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

### 4. Running Tests & Coverage
Run the full pytest suite with coverage:
```bash
pytest tests/ --cov=app --cov-report=term-missing
```

---

## Database Index EXPLAIN Notes

The key queries on hot paths have dedicated indexes verified with EXPLAIN:
1. `grading_queue` Index: `ix_grading_queue_exam_status_created_id` on `(exam_id, status, created_at, id)`.
   - **Query**: `SELECT * FROM grading_queue WHERE exam_id = $1 AND status = $2 ORDER BY created_at ASC, id ASC LIMIT 20;`
   - **EXPLAIN Analysis**: Uses Index Scan on `ix_grading_queue_exam_status_created_id` (Cost: ~0.15..8.17), eliminating in-memory sorting.
2. `proctor_events` Index: `ix_proctor_events_session_id_timestamp` on `(session_id, timestamp)`.
   - **Query**: `SELECT * FROM proctor_events WHERE session_id = $1 ORDER BY timestamp ASC;`
   - **EXPLAIN Analysis**: Index Only Scan / Index Scan on session timeline queries.
3. `exam_sessions` Index: `ix_exam_sessions_server_deadline` on `(server_deadline)`.
   - **Query**: `SELECT * FROM exam_sessions WHERE status IN ('in_progress', 'flagged') AND server_deadline <= $1;`
   - **EXPLAIN Analysis**: Used by the 30s sweeper job for fast lookup of expired active sessions.

---

## API Endpoint Reference Table

| Category | Method | Endpoint | Access Level | Description |
|---|---|---|---|---|
| **Auth** | `POST` | `/api/v1/auth/register` | Public / Admin | Register user (student default; admin required for examiner/admin) |
| **Auth** | `POST` | `/api/v1/auth/login` | Public | Authenticate user & return JWT access + refresh tokens |
| **Auth** | `GET` | `/api/v1/auth/me` | Authenticated | Get current authenticated user profile |
| **Auth** | `POST` | `/api/v1/auth/refresh` | Public | Refresh JWT access token |
| **Exam Auth** | `POST` | `/api/v1/exams/{id}/access-token` | Student/Examiner/Admin | Issue exam-specific access token bound to student & exam |
| **Exam Auth** | `POST` | `/api/v1/exams/{id}/start` | Student | Start session, compute `server_deadline`, issue short-lived session token |
| **Exam Auth** | `POST` | `/api/v1/sessions/{id}/heartbeat` | Student | Re-issue fresh session token, rotate JTI, detect IP/User-Agent changes |
| **Sessions** | `GET` | `/api/v1/sessions/{id}/time-remaining` | Student/Examiner/Admin | Get `seconds_remaining` computed server-side and server time |
| **Sessions** | `GET` | `/api/v1/sessions/{id}/paper` | Student/Examiner/Admin | Retrieve deterministic generated paper for active session |
| **Answers** | `PUT` | `/api/v1/sessions/{id}/answers/{question_id}` | Student | Upsert candidate question answer with word count / option validation |
| **Answers** | `POST` | `/api/v1/sessions/{id}/answers/{question_id}/image` | Student | Upload handwritten answer image (Pillow re-encode, thumbnail) |
| **Answers** | `GET` | `/api/v1/sessions/{id}/answers` | Student/Examiner/Admin | Get student's saved answers |
| **Sessions** | `POST` | `/api/v1/sessions/{id}/submit` | Student | Submit exam session (triggers objective auto-eval) |
| **Proctoring** | `POST` | `/api/v1/sessions/{id}/proctor/precheck` | Student | Verify face presence before starting exam |
| **Proctoring** | `WS` | `/api/v1/ws/proctor/{session_id}` | Student (Session Token) | Real-time proctoring WebSocket heartbeat & discrete events |
| **Proctoring** | `GET` | `/api/v1/exams/{id}/proctoring/sessions` | Examiner / Admin | Keyset-paginated list of exam sessions sortable by suspicion score |
| **Proctoring** | `GET` | `/api/v1/sessions/{id}/proctor-events` | Examiner / Admin | Get proctoring event timeline for a session |
| **Grading** | `GET` | `/api/v1/grading/queue` | Examiner / Admin | Keyset-paginated subjective grading queue |
| **Grading** | `GET` | `/api/v1/grading/answers/{answer_id}` | Examiner / Admin | Get student answer, question, model answer & AI suggestion |
| **Grading** | `PUT` | `/api/v1/grading/answers/{answer_id}` | Examiner (owner) / Admin | Examiner sets final marks and writes audit log |
| **Grading** | `POST` | `/api/v1/grading/exams/{exam_id}/finalize` | Examiner (owner) / Admin | Finalize exam results after all subjective answers are graded |
| **Grading** | `GET` | `/api/v1/grading/answers/{answer_id}/ai-trace` | Examiner / Admin | Retrieve AI evaluation execution trace and retries |

---

## Weeks 3–4 Requirements Implementation Checklist

- [x] **Timed Exam Session Engine**: `server_deadline` calculation on `/exams/{id}/start`, `GET /sessions/{id}/time-remaining`, deadline write rejection with grace window, APScheduler `DateTrigger` and 30s sweeper job (`app/services/session_service.py`, `app/services/scheduler.py`).
- [x] **Answer Submission APIs**: `PUT /sessions/{id}/answers/{question_id}` upsert, option validation against candidate paper, word count validation and control character stripping for text answers, multipart image upload with Pillow re-encoding, EXIF stripping, thumbnail generation, magic byte validation (`app/services/session_service.py`, `app/services/storage.py`, `app/api/v1/sessions.py`).
- [x] **Objective Auto-Evaluation**: Strategy pattern (`MCQScoringStrategy` and `MultiSelectScoringStrategy` with documented All-or-Nothing rule), `marks_override` support, non-negative score floor enforcement, score breakdown JSON, automatic trigger upon submission (`app/services/evaluation.py`).
- [x] **AI Proctoring Backend**: Pure, deterministic suspicion scorer (`app/services/suspicion_scorer.py`), WebSocket `/ws/proctor/{session_id}` with short-lived session token auth, JTI verification, 10s heartbeat, missing heartbeat detection (>25s), bounded async queue DB writer, precheck endpoint, examiner REST endpoints, and client contract docs (`docs/proctoring_client_contract.md`).
- [x] **Subjective Grading Pipeline (LangChain + LangGraph)**: LangGraph `StateGraph` pipeline (`app/services/grading/pipeline.py`), Tesseract / Google Vision OCR providers (`app/services/ocr/`), prompt injection defense via `<student_answer>` tags, PII exclusion, score clamping, queue worker with `FOR UPDATE SKIP LOCKED` (`app/services/grading_worker.py`), and examiner portal REST endpoints (`app/api/v1/grading.py`).
- [x] **Comprehensive Pytest Suite**: 30 passing unit and integration tests covering deadlines, answer submission/image handling, objective scoring, proctoring WS and scorer purity, LangGraph pipeline with mocks, queue claiming, auth RBAC, and Alembic migrations (`tests/`).

---

## Known Limitations & Security Notes
- **Websocket Single Scheduler Instance**: In multi-worker deployments (`uvicorn --workers N`), run the APScheduler background sweeper on a single instance by setting `RUN_SCHEDULER=true` on one node or utilizing Postgres advisory locks.
- **AI Score Finality**: AI scores serve strictly as suggestions and are never marked final automatically; examiner review and confirmation are required for all subjective answers.
