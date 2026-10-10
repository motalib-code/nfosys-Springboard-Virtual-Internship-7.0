from datetime import datetime, timezone
import logging
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models import ExamSession, SessionStatus, SubmittedReason
from app.services.evaluation import EvaluationService

logger = logging.getLogger(__name__)

scheduler: Optional[AsyncIOScheduler] = None


def init_scheduler() -> AsyncIOScheduler:
    global scheduler
    if scheduler is not None:
        return scheduler

    db_url = settings.get_database_url()
    if db_url.startswith("sqlite"):
        jobstores = {
            'default': MemoryJobStore()
        }
    else:
        jobstores = {
            'default': SQLAlchemyJobStore(url=db_url)
        }

    scheduler = AsyncIOScheduler(jobstores=jobstores, timezone="UTC")
    return scheduler


def auto_submit_session_job(session_id: str, db_session=None) -> None:
    """
    Idempotent job to auto-submit an expired exam session with row lock.
    """
    db = db_session or SessionLocal()
    close_db = db_session is None
    try:
        query = db.query(ExamSession).filter(ExamSession.id == session_id)
        if engine.dialect.name != "sqlite":
            query = query.with_for_update()
        session = query.first()

        if not session:
            logger.warning(f"Auto-submit job: Session {session_id} not found")
            return

        if session.status in [SessionStatus.IN_PROGRESS, SessionStatus.FLAGGED]:
            now = datetime.now(timezone.utc)
            session.status = SessionStatus.AUTO_SUBMITTED
            session.submitted_reason = SubmittedReason.TIME_EXPIRED
            session.submitted_at = now
            db.commit()
            EvaluationService.evaluate_objective(db, session_id)
            logger.info(f"Auto-submitted session {session_id} due to deadline expiration.")
        else:
            logger.info(f"Auto-submit skipped for session {session_id}: status is {session.status.value}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error in auto_submit_session_job for session {session_id}: {e}")
    finally:
        if close_db:
            db.close()


def sweep_expired_sessions(db_session=None) -> None:
    """
    Sweeper job running every 30s to find in-progress sessions past server deadline.
    """
    db = db_session or SessionLocal()
    close_db = db_session is None
    try:
        now = datetime.now(timezone.utc)
        query = db.query(ExamSession).filter(
            ExamSession.status.in_([SessionStatus.IN_PROGRESS, SessionStatus.FLAGGED])
        )
        if engine.dialect.name == "postgresql":
            query = query.filter(ExamSession.server_deadline <= now).with_for_update(skip_locked=True)
        elif engine.dialect.name != "sqlite":
            query = query.filter(ExamSession.server_deadline <= now).with_for_update()

        all_active = query.all()
        expired_sessions = []
        for session in all_active:
            if session.server_deadline:
                deadline = session.server_deadline if session.server_deadline.tzinfo is not None else session.server_deadline.replace(tzinfo=timezone.utc)
                if deadline <= now:
                    expired_sessions.append(session)

        for session in expired_sessions:
            session.status = SessionStatus.AUTO_SUBMITTED
            session.submitted_reason = SubmittedReason.TIME_EXPIRED
            session.submitted_at = now
            logger.info(f"Sweeper auto-submitted expired session {session.id}.")

        if expired_sessions:
            db.commit()
            for s in expired_sessions:
                EvaluationService.evaluate_objective(db, s.id)
    except Exception as e:
        db.rollback()
        logger.error(f"Error in sweep_expired_sessions: {e}")
    finally:
        if close_db:
            db.close()


def schedule_auto_submit_job(session_id: str, deadline: datetime) -> None:
    global scheduler
    if not settings.RUN_SCHEDULER:
        return
    if scheduler is None:
        init_scheduler()

    job_id = f"auto_submit_{session_id}"
    try:
        scheduler.add_job(
            auto_submit_session_job,
            trigger=DateTrigger(run_date=deadline, timezone=timezone.utc),
            args=[session_id],
            id=job_id,
            replace_existing=True
        )
    except Exception as e:
        logger.error(f"Failed to schedule auto-submit job for session {session_id}: {e}")


def start_scheduler() -> None:
    global scheduler
    if not settings.RUN_SCHEDULER:
        logger.info("Scheduler disabled via RUN_SCHEDULER=False")
        return

    if scheduler is None:
        init_scheduler()

    if not scheduler.running:
        scheduler.add_job(
            sweep_expired_sessions,
            trigger=IntervalTrigger(seconds=30, timezone=timezone.utc),
            id="expired_sessions_sweeper",
            replace_existing=True
        )
        scheduler.start()
        logger.info("APScheduler started successfully.")


def shutdown_scheduler() -> None:
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler shutdown.")
