# AI-Based Intelligent Examination Platform (Weeks 1–4 Backend)

Production-quality backend for an AI-Based Intelligent Examination Platform featuring automated AI proctoring schema, dynamic exam paper generation, timed exam session engine with APScheduler auto-submission, objective auto-evaluation, LangChain/LangGraph subjective AI grading pipeline, and examiner grading portal.

---

## Architecture Diagram

```mermaid
graph TD
    Client[Web Frontend / Mobile] -->|HTTP / REST| API[FastAPI Gateway / Routers]
    Client -->|WebSocket| WS[FastAPI WebSocket /ws/proctor/{id}]

    API --> AuthService[Auth & Token Service]
    API --> ExamService[Exam & Session Service]
    API --> AnswerService[Answer Submission & Storage]
    API --> EvaluatorService[Objective Evaluator Engine]

    WS --> ProctorEngine[Proctoring Signal Handler]
    ProctorEngine --> SuspicionScorer[Pure Suspicion Scorer]
    ProctorEngine --> EventQueue[Bounded Async Event Queue]
    EventQueue --> EventWriter[Background Event Writer Worker]

    ExamService --> APScheduler[AsyncIO APScheduler / Sweeper]
    AnswerService --> Storage[StorageBackend - Local/S3]

    EvaluatorService --> Strategy[Pluggable Scoring Strategies]
    EvaluatorService --> GradingQueueDB[(Grading Queue Table)]

    GradingQueueDB --> Worker[Background Grading Worker]
    Worker --> LangGraph[LangGraph StateGraph Pipeline]

    LangGraph --> OCR[OCR Provider - Tesseract / Vision]
    LangGraph --> LLM[LangChain ChatOpenAI - Structured Output]
    LangGraph --> Guardrails[Score Guardrails & Guard Prompt]

    Worker --> AIEvaluationDB[(AI Evaluations Table)]

    EventWriter --> Postgres[(PostgreSQL Database)]
    APScheduler --> Postgres
    LangGraph --> Postgres
```

---

## Tech Stack
- **Python 3.11+ / 3.12**
- **FastAPI** & **Pydantic v2**
- **SQLAlchemy 2.0 ORM** & **Alembic**
- **PostgreSQL 15** & **Redis 7** (via docker-compose)
- **APScheduler** (`AsyncIOScheduler` + `SQLAlchemyJobStore`)
- **LangChain** (`langchain-core`, `langchain-openai`) & **LangGraph**
- **Pillow** & **pytesseract** (OCR)
- **pytest** & **pytest-cov** (>= 85% coverage)

---

## Quickstart & Setup Instructions

### 1. Environment & Dependencies
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
pip install -r requirements.txt
```

### 2. Database Migrations & Seeding
Run Alembic migrations to create/update tables:
```bash
alembic upgrade head
```

Seed initial users (1 admin, 1 examiner, 3 students):
```bash
python3 seed.py
```
Default password for all seeded users: `Password123!`

### 3. Run Application & Worker
Start the FastAPI server:
```bash
uvicorn app.main:app --reload
```

Start the background subjective grading worker:
```bash
python3 -m app.workers.grading_worker
```
Interactive OpenAPI documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

### 4. Running Tests & Coverage
Run full test suite:
```bash
python3 -m pytest --cov=app --cov-report=term-missing
```

---

## Key Query EXPLAIN Notes (Performance Analysis)

1. **Queue Claiming Query**:
   `EXPLAIN SELECT * FROM grading_queue WHERE status = 'pending' FOR UPDATE SKIP LOCKED;`
   *Notes*: Uses `ix_grading_queue_status` index to lock available pending items without row contention across multiple concurrent workers.

2. **Proctoring Timeline & Keysated Session Queries**:
   `EXPLAIN SELECT * FROM exam_sessions WHERE exam_id = '...' ORDER BY suspicion_score DESC;`
   *Notes*: Efficient sort on index for examiner proctoring dashboard monitoring.

---

## API Endpoint Reference Table

| Category | Method | Endpoint | Access Level | Description |
|---|---|---|---|---|
| **Auth** | `POST` | `/api/v1/auth/register` | Public / Admin | Register user |
| **Auth** | `POST` | `/api/v1/auth/login` | Public | Authenticate user & return JWT tokens |
| **Timed Engine** | `GET` | `/api/v1/sessions/{id}/time-remaining` | Student | Server-computed remaining seconds & server_time |
| **Answers** | `PUT` | `/api/v1/sessions/{id}/answers/{q_id}` | Student | Upsert answer (MCQ single/multi-select, text limits) |
| **Answers** | `POST` | `/api/v1/sessions/{id}/answers/{q_id}/image` | Student | Upload image answer (magic bytes MIME check, EXIF strip, thumbnail) |
| **Answers** | `GET` | `/api/v1/sessions/{id}/answers` | Student | Restore saved student answers |
| **Proctoring** | `WS` | `/api/v1/ws/proctor/{session_id}` | Student | Real-time WebSocket signal pipeline & heartbeat monitor |
| **Proctoring** | `POST` | `/api/v1/sessions/{id}/proctor/precheck` | Student | Verify face detection before starting exam |
| **Proctoring** | `GET` | `/api/v1/exams/{id}/proctoring/sessions` | Examiner/Admin | List session suspicion scores & flags |
| **Grading** | `GET` | `/api/v1/grading/queue` | Examiner/Admin | Keyset-paginated queue of subjective answers |
| **Grading** | `GET` | `/api/v1/grading/answers/{answer_id}` | Examiner/Admin | Inspect student answer, model answer, & AI score suggestion |
| **Grading** | `PUT` | `/api/v1/grading/answers/{answer_id}` | Examiner/Admin | Examiner finalizes manual grade and writes audit log |
| **Grading** | `POST` | `/api/v1/grading/exams/{exam_id}/finalize` | Examiner/Admin | Aggregate scores and mark exam result as FINAL |

---

## Requirement Implementation Checklist (Weeks 3–4)

- [x] **Timed Exam Session Engine & APScheduler**: Server deadline calculation, server_time synchronization, 3s grace window enforcement, DateTrigger + 30s sweeper auto-submission (`app/services/session_service.py`, `app/services/scheduler.py`).
- [x] **Answer Submission APIs & StorageBackend**: Upsert answers, MCQ/multi-select option validation, word count bounds, MIME magic bytes check, Pillow EXIF strip & 320px thumbnail generation (`app/services/storage.py`, `app/services/session_service.py`).
- [x] **Objective Auto-Evaluation Engine**: MCQ/multi-select scoring, pluggable strategy classes (`AllOrNothingStrategy`, `PartialCreditStrategy`), negative marking, marks override, score breakdown JSONB (`app/services/evaluator.py`, `app/services/scoring_strategies.py`).
- [x] **AI Proctoring Engine & Suspicion Scorer**: WebSocket signal handler, 10s heartbeat monitor, silence detection (>25s), pure deterministic SuspicionScorer with time-decay/caps, async queue persistence (`app/services/suspicion_scorer.py`, `app/api/v1/proctoring.py`).
- [x] **Subjective Grading Pipeline (LangChain + LangGraph)**: LangGraph StateGraph, OCR provider abstraction, key points extraction, structured LLM grading, prompt injection guardrails with `<student_answer>` tags, FOR UPDATE SKIP LOCKED worker (`app/services/grading/pipeline.py`, `app/workers/grading_worker.py`).
- [x] **Examiner Grading Portal API**: Keyset paginated queue, answer detail inspection, manual grade override with audit log, exam result finalization (`app/api/v1/grading.py`).
