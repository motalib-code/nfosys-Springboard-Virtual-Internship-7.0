import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings


class StorageBackend(ABC):
    @abstractmethod
    def save_bytes(self, data: bytes, relative_path: str) -> str:
        raise NotImplementedError


class LocalStorageBackend(StorageBackend):
    def __init__(self, root_path: str):
        self.root = Path(root_path)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, data: bytes, relative_path: str) -> str:
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"/{self.root.as_posix()}/{relative_path}"


class StorageService:
    @staticmethod
    def get_backend() -> StorageBackend:
        return LocalStorageBackend(settings.LOCAL_STORAGE_ROOT)

    @staticmethod
    def generate_name(extension: str) -> str:
        return f"{uuid.uuid4().hex}.{extension.lower()}"
