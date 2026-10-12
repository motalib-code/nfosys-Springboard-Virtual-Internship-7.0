import os
import uuid
import io
from abc import ABC, abstractmethod
from PIL import Image
from fastapi import HTTPException, status
from app.core.config import settings


class StorageBackend(ABC):
    @abstractmethod
    def save_image_and_thumbnail(self, file_bytes: bytes, extension: str) -> tuple[str, str]:
        """Saves image and generates thumbnail, returning (image_url, thumbnail_url)."""
        pass


class LocalStorageBackend(StorageBackend):
    def __init__(self, upload_dir: str = settings.UPLOAD_DIR):
        self.upload_dir = upload_dir
        os.makedirs(self.upload_dir, exist_ok=True)

    def save_image_and_thumbnail(self, file_bytes: bytes, extension: str) -> tuple[str, str]:
        # Validate magic bytes
        image_format = self._validate_and_get_format(file_bytes)

        try:
            image = Image.open(io.BytesIO(file_bytes))
            # Strip EXIF / metadata by converting / copying raw pixels
            data = list(image.getdata())
            clean_image = Image.new(image.mode, image.size)
            clean_image.putdata(data)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"success": False, "error": "Invalid image file format", "details": None}
            )

        filename = f"{uuid.uuid4()}"
        ext = extension.lower()
        if not ext.startswith("."):
            ext = f".{ext}"

        image_filename = f"{filename}{ext}"
        thumb_filename = f"{filename}_thumb{ext}"

        image_path = os.path.join(self.upload_dir, image_filename)
        thumb_path = os.path.join(self.upload_dir, thumb_filename)

        # Save clean re-encoded image
        clean_image.save(image_path, format=image_format)

        # Generate thumbnail (e.g. max 320px)
        thumb_image = clean_image.copy()
        thumb_image.thumbnail((320, 320))
        thumb_image.save(thumb_path, format=image_format)

        image_url = f"/static/uploads/{image_filename}"
        thumbnail_url = f"/static/uploads/{thumb_filename}"
        return image_url, thumbnail_url

    def _validate_and_get_format(self, file_bytes: bytes) -> str:
        if file_bytes.startswith(b"\xff\xd8\xff"):
            return "JPEG"
        elif file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "PNG"
        elif len(file_bytes) > 12 and file_bytes.startswith(b"RIFF") and file_bytes[8:12] == b"WEBP":
            return "WEBP"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"success": False, "error": "Invalid image magic bytes. Allowed formats: JPEG, PNG, WEBP.", "details": None}
            )


storage_backend: StorageBackend = LocalStorageBackend()
