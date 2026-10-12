import time
import os
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.session import SessionLocal, engine
from app.models import GradingQueue, GradingQueueStatus
from app.services.grading.pipeline import grading_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("grading_worker")


def process_queue_batch(worker_id: str = "worker-1", limit: int = 10, db_session: Session = None) -> int:
    """
    Claims pending queue items using SELECT ... FOR UPDATE SKIP LOCKED,
    runs the LangGraph pipeline OUTSIDE the open transaction, and updates status.
    """
    close_db = False
    if db_session:
        db = db_session
    else:
        db = SessionLocal()
        close_db = True

    claimed_items = []
    try:
        query = db.query(GradingQueue).filter(GradingQueue.status == GradingQueueStatus.PENDING)
        if engine.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        elif engine.dialect.name != "sqlite":
            query = query.with_for_update()

        items = query.order_by(GradingQueue.priority.desc(), GradingQueue.created_at.asc()).limit(limit).all()

        now = datetime.now(timezone.utc)
        for item in items:
            item.status = GradingQueueStatus.PROCESSING_AI
            item.claimed_by = worker_id
            item.claimed_at = now
            item.attempts += 1
            claimed_items.append((item.id, item.answer_id, item.attempts))

        if close_db:
            db.commit()
        else:
            db.flush()
    except Exception as e:
        if close_db:
            db.rollback()
        logger.error(f"Failed to claim queue items: {e}")
        return 0
    finally:
        if close_db:
            db.close()

    # Process items outside DB transaction
    processed_count = 0
    for q_id, ans_id, attempts in claimed_items:
        try:
            initial_state = {
                "answer_id": ans_id,
                "attempts": attempts,
                "db_session": db,
                "errors": []
            }
            res = grading_graph.invoke(initial_state)
            processed_count += 1
            logger.info(f"Worker {worker_id} successfully processed answer {ans_id}")
        except Exception as e:
            logger.error(f"Worker {worker_id} error processing answer {ans_id}: {e}")
            # Mark failed or dead-letter
            db_err: Session = SessionLocal()
            try:
                q_item = db_err.query(GradingQueue).filter(GradingQueue.id == q_id).first()
                if q_item:
                    q_item.status = GradingQueueStatus.FAILED if q_item.attempts >= 3 else GradingQueueStatus.PENDING
                db_err.commit()
            finally:
                db_err.close()

    return processed_count


def run_worker_loop():
    worker_id = f"worker-{os.getpid()}"
    logger.info(f"Starting grading worker {worker_id}...")
    while True:
        processed = process_queue_batch(worker_id=worker_id)
        if processed == 0:
            time.sleep(2)


if __name__ == "__main__":
    run_worker_loop()
