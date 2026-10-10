import os
from abc import ABC, abstractmethod
from typing import Dict, Any

class OcrProvider(ABC):
    @abstractmethod
    def extract_text(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Extracts text from image. Returns dict {"text": str, "avg_confidence": float}.
        """
        pass


class TesseractProvider(OcrProvider):
    def extract_text(self, image_bytes: bytes) -> Dict[str, Any]:
        try:
            import io
            from PIL import Image, ImageEnhance, ImageFilter
            import pytesseract

            img = Image.open(io.BytesIO(image_bytes)).convert('L') # Grayscale
            img = img.filter(ImageFilter.SHARPEN) # Denoise / sharpen

            # Simple thresholding
            threshold = 140
            img = img.point(lambda p: 255 if p > threshold else 0)

            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            texts = []
            confidences = []

            for text, conf in zip(data['text'], data['conf']):
                if text.strip():
                    texts.append(text)
                    try:
                        conf_val = float(conf)
                        if conf_val >= 0:
                            confidences.append(conf_val)
                    except ValueError:
                        pass

            full_text = " ".join(texts)
            avg_conf = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
            return {"text": full_text, "avg_confidence": avg_conf}
        except Exception as e:
            return {"text": "", "avg_confidence": 0.0, "error": str(e)}


class GoogleVisionProvider(OcrProvider):
    def extract_text(self, image_bytes: bytes) -> Dict[str, Any]:
        # Pluggable Google Vision Provider placeholder
        return {"text": "[Google Vision OCR Stub Output]", "avg_confidence": 0.95}


def get_ocr_provider() -> OcrProvider:
    provider_type = os.getenv("OCR_PROVIDER", "tesseract").lower()
    if provider_type == "google_vision":
        return GoogleVisionProvider()
    return TesseractProvider()
