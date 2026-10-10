import os
import sys
import time
import logging
import asyncio
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.session import SessionLocal, engine
from app.models import GradingQueue, GradingQueueStatus
from app.services.grading.pipeline import build_grading_graph

logger = logging.getLogger(__name__)

def claim_and_process_job(worker_id: str = "worker-1", llm_client=None) -> bool:
    """
    Claims 1 pending job from grading_queue using SELECT ... FOR UPDATE SKIP LOCKED
    and runs the LangGraph subjective grading pipeline outside DB transaction.
    """
    db = SessionLocal()
    try:
        query = db.query(GradingQueue).filter(GradingQueue.status == GradingQueueStatus.PENDING)

        if engine.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        elif engine.dialect.name != "sqlite":
            query = query.with_for_update()

        job = query.first()
        if not job:
            return False

        # Claim row
        job.status = GradingQueueStatus.PROCESSING_AI
        job.claimed_by = worker_id
        job.claimed_at = datetime.now(timezone.utc)
        job.attempts += 1
        db.commit()

        answer_id = job.answer_id
    except Exception as e:
        db.rollback()
        logger.error(f"Error claiming job in worker: {e}")
        return False
    finally:
        db.close()

    # Run LangGraph pipeline outside transaction
    try:
        graph = build_grading_graph(llm_client=llm_client)
        initial_state = {
            "answer_id": answer_id,
            "attempts": 1,
            "errors": [],
            "status": "processing"
        }
        graph.invoke(initial_state)
        return True
    except Exception as e:
        logger.error(f"Error processing job {answer_id}: {e}")
        db_err = SessionLocal()
        try:
            err_job = db_err.query(GradingQueue).filter(GradingQueue.answer_id == answer_id).first()
            if err_job:
                if err_job.attempts >= 3:
                    err_job.status = GradingQueueStatus.FAILED
                else:
                    err_job.status = GradingQueueStatus.PENDING
                err_job.updated_at = datetime.now(timezone.utc)
                db_err.commit()
        finally:
            db_err.close()
        return False

def run_worker_loop():
    logger.info("Starting grading background worker loop...")
    while True:
        processed = claim_and_process_job()
        if not processed:
            time.sleep(2)

if __name__ == "__main__":
    run_worker_loop()
