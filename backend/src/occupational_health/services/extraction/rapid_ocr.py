"""Lightweight ONNX OCR fallback for pages without a text layer.

MinerU 4.x handles PDF structure (including tables); this adapter only
produces plain text when MinerU is unavailable or the file is not a PDF.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from occupational_health.core.errors import ApiError

_LOGGER = logging.getLogger(__name__)


class RapidOcrAdapter:
    def __init__(self, render_dpi: int = 200) -> None:
        self.render_dpi = render_dpi
        self._engine: Any | None = None

    def recognize(self, path: Path, page_number: int) -> dict:
        """Recognise a single page; ``page_number`` is honoured."""
        return self.recognize_batch(path, [page_number]).get(
            page_number,
            {"text": "", "confidence": None, "blocks": [], "failed": True},
        )

    def recognize_batch(self, path: Path, page_numbers: list[int]) -> dict[int, dict]:
        """Recognise multiple pages, mapping results back to page numbers.

        A failed page yields ``failed=True`` with empty text so one bad page does
        not abort the whole batch.
        """
        if not page_numbers:
            return {}
        images = [self._render_page(path, number) for number in page_numbers]
        try:
            parsed = self._predict(images)
        except Exception as exc:
            _LOGGER.exception("RapidOCR failed: %s", exc)
            parsed = [None] * len(images)
        finally:
            for image in images:
                image.unlink(missing_ok=True)

        output: dict[int, dict] = {}
        for page_number, item in zip(page_numbers, parsed, strict=True):
            success = bool(item and item.get("text"))
            output[page_number] = {
                **(item or {"text": "", "confidence": None, "blocks": []}),
                "failed": not success,
            }
        return output

    def _predict(self, images: list[Path]) -> list[dict | None]:
        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as exc:
                raise ApiError(
                    503,
                    "MODEL_UNAVAILABLE",
                    "OCR 引擎不可用，请安装 rapidocr_onnxruntime",
                ) from exc
            self._engine = RapidOCR()

        output: list[dict | None] = []
        for image in images:
            try:
                result, _ = self._engine(str(image))
                if not result:
                    output.append(None)
                    continue
                texts = [
                    str(item[1]) for item in result if len(item) > 1 and item[1]
                ]
                scores = [
                    float(item[2])
                    for item in result
                    if len(item) > 2 and item[2] is not None
                ]
                output.append(
                    {
                        "text": "\n".join(texts),
                        "confidence": (
                            round(sum(scores) / len(scores), 3) if scores else None
                        ),
                        "blocks": [
                            {"label": "text", "content": text} for text in texts
                        ],
                    }
                )
            except Exception as exc:
                _LOGGER.warning("RapidOCR failed on %s: %s", image.name, exc)
                output.append(None)
        return output

    def _render_page(self, path: Path, page_number: int) -> Path:
        try:
            document = fitz.open(path)
        except Exception as exc:
            raise ApiError(400, "PDF_INVALID", "文档无法打开，可能已损坏") from exc
        try:
            if page_number < 1 or page_number > document.page_count:
                raise ApiError(400, "PDF_INVALID", f"页码 {page_number} 超出范围")
            pixmap = document[page_number - 1].get_pixmap(dpi=self.render_dpi)
            handle, tmp = tempfile.mkstemp(suffix=".png")
            os.close(handle)
            pixmap.save(tmp)
            return Path(tmp)
        finally:
            document.close()
