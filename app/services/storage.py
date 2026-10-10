import abc
import os
import uuid
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageBackend(abc.ABC):
    @abc.abstractmethod
    def save_file(self, file_bytes: bytes, filename: str, subfolder: str = "answers") -> str:
        """Saves file bytes and returns accessible path/URL."""
        pass


class LocalStorageBackend(StorageBackend):
    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or settings.UPLOAD_DIR
        os.makedirs(self.base_dir, exist_ok=True)

    def save_file(self, file_bytes: bytes, filename: str, subfolder: str = "answers") -> str:
        folder_path = os.path.join(self.base_dir, subfolder)
        os.makedirs(folder_path, exist_ok=True)

        ext = os.path.splitext(filename)[1] or ".png"
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(folder_path, unique_name)

        with open(file_path, "wb") as f:
            f.write(file_bytes)

        return f"/{settings.UPLOAD_DIR}/{subfolder}/{unique_name}"


def get_storage_backend() -> StorageBackend:
    return LocalStorageBackend()
