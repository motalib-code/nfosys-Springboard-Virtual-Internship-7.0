import os
import tempfile
import pytest
from alembic.config import Config
from alembic import command


def test_alembic_migrations():
    # Create temporary database file for migration testing
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db_url = f"sqlite:///{db_path}"
        os.environ["DATABASE_URL"] = db_url

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)

        # Run upgrade head
        command.upgrade(alembic_cfg, "head")

        # Run downgrade -1
        command.downgrade(alembic_cfg, "-1")

        # Re-upgrade head to ensure idempotency
        command.upgrade(alembic_cfg, "head")

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
