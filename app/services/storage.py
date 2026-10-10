import os
import uuid
from abc import ABC, abstractmethod
from typing import Tuple
from PIL import Image, ImageOps
import io

class StorageBackend(ABC):
    @abstractmethod
    def save_image(self, image_bytes: bytes, filename: str) -> Tuple[str, str]:
        """
        Saves full image and generates thumbnail.
        Returns tuple of (image_url, thumbnail_url).
        """
        pass

class LocalStorageBackend(StorageBackend):
    def __init__(self, base_dir: str = "uploads", base_url: str = "/uploads"):
        self.base_dir = base_dir
        self.base_url = base_url
        os.makedirs(os.path.join(self.base_dir, "images"), exist_ok=True)
        os.makedirs(os.path.join(self.base_dir, "thumbnails"), exist_ok=True)

    def save_image(self, image_bytes: bytes, filename: str) -> Tuple[str, str]:
        # Open image with Pillow, strip EXIF data by creating new clean image
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img)

        # Convert to RGB if palette/RGBA for JPEG/PNG uniformity
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        unique_id = str(uuid.uuid4())
        ext = filename.split(".")[-1].lower() if "." in filename else "jpg"
        if ext not in ["jpg", "jpeg", "png", "webp"]:
            ext = "jpg"

        full_filename = f"{unique_id}.{ext}"
        thumb_filename = f"{unique_id}_thumb.{ext}"

        full_path = os.path.join(self.base_dir, "images", full_filename)
        thumb_path = os.path.join(self.base_dir, "thumbnails", thumb_filename)

        # Save main re-encoded image
        img.save(full_path, quality=90)

        # Create thumbnail (320px max dimension)
        thumb = img.copy()
        thumb.thumbnail((320, 320))
        thumb.save(thumb_path, quality=85)

        image_url = f"{self.base_url}/images/{full_filename}"
        thumbnail_url = f"{self.base_url}/thumbnails/{thumb_filename}"

        return image_url, thumbnail_url

storage_backend = LocalStorageBackend()
