from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.core.config import settings
from app.api.v1.auth import router as auth_router, exam_auth_router
from app.api.v1.questions import router as questions_router
from app.api.v1.exams import router as exams_router
from app.api.v1.sessions import router as sessions_router
from app.api.v1.proctoring import router as proctoring_router, event_writer_worker
from app.api.v1.grading import router as grading_router
from app.services.scheduler import start_scheduler, shutdown_scheduler
import asyncio


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    bg_task = asyncio.create_task(event_writer_worker())
    yield
    bg_task.cancel()
    shutdown_scheduler()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Include routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(exam_auth_router, prefix=settings.API_V1_STR)
app.include_router(questions_router, prefix=settings.API_V1_STR)
app.include_router(exams_router, prefix=settings.API_V1_STR)
app.include_router(sessions_router, prefix=settings.API_V1_STR)
app.include_router(proctoring_router, prefix=settings.API_V1_STR)
app.include_router(grading_router, prefix=settings.API_V1_STR)


@app.get("/")
def root():
    return {"message": "AI-Based Intelligent Examination Platform API is running"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    formatted_errors = []
    for err in exc.errors():
        err_copy = dict(err)
        if "ctx" in err_copy and "error" in err_copy["ctx"]:
            err_copy["ctx"] = {k: str(v) for k, v in err_copy["ctx"].items()}
        formatted_errors.append(err_copy)
    return JSONResponse(
        status_code=422,
        content={"detail": formatted_errors}
    )
