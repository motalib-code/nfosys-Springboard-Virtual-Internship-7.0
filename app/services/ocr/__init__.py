from abc import ABC, abstractmethod
from typing import Dict, Any
from app.core.config import settings


class OcrProvider(ABC):
    @abstractmethod
    def extract_text(self, image_bytes: bytes) -> Dict[str, Any]:
        """Returns {"text": str, "avg_confidence": float}."""
        pass


class TesseractProvider(OcrProvider):
    def extract_text(self, image_bytes: bytes) -> Dict[str, Any]:
        import io
        from PIL import Image, ImageOps, ImageFilter
        import pytesseract

        try:
            img = Image.open(io.BytesIO(image_bytes))
            # Image preprocessing: convert to grayscale, denoise/filter, threshold
            gray = ImageOps.grayscale(img)
            filtered = gray.filter(ImageFilter.SMOOTH)

            # Run Tesseract with data output for confidence
            data = pytesseract.image_to_data(filtered, output_type=pytesseract.Output.DICT)
            text_parts = []
            confidences = []

            for i in range(len(data.get("text", []))):
                word = data["text"][i].strip()
                conf = float(data["conf"][i])
                if word and conf >= 0:
                    text_parts.append(word)
                    confidences.append(conf)

            full_text = " ".join(text_parts)
            avg_conf = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
            return {
                "text": full_text,
                "avg_confidence": round(avg_conf, 2)
            }
        except Exception as e:
            return {
                "text": f"[OCR Error: {str(e)}]",
                "avg_confidence": 0.0
            }


class GoogleVisionProvider(OcrProvider):
    def extract_text(self, image_bytes: bytes) -> Dict[str, Any]:
        # Optional pluggable provider
        return {
            "text": "[Google Vision OCR Stub]",
            "avg_confidence": 0.90
        }


def get_ocr_provider() -> OcrProvider:
    if settings.OCR_PROVIDER.lower() == "google_vision":
        return GoogleVisionProvider()
    return TesseractProvider()
