"""MinerU 4.x document parsing adapter.

Runs the ``mineru-kit`` CLI from an isolated virtual environment and converts
its ``middle_json`` output into ``TableSegment`` objects. Table blocks become a
single segment per table (no row splitting); tables continued on the next page
are merged when their header or caption matches.

The adapter never imports MinerU into the main process: MinerU 4.x pulls in
pydantic>=2.12, gradio, onnxruntime(-directml) and its own torch stack, which
conflicts with the OCR/embedding dependencies already installed here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from occupational_health.services.extraction.cleaning import correct_ocr_text
from occupational_health.services.extraction.table_html import (
    merge_rows,
    parse_html_table,
    rows_to_html,
    rows_to_text,
)
from occupational_health.services.extraction.tables import TableSegment, table_id_for

_LOGGER = logging.getLogger(__name__)

_IGNORED_BLOCKS = {"header", "footer", "page_number", "aside_text"}
# MinerU 4.x: 独立公式为 equation/interline_equation，行内公式为 equation_inline。
_FORMULA_BLOCK_TYPES = {
    "equation",
    "interline_equation",
    "equation_inline",
    "inline_equation",
}
_FORMULA_SPAN_TYPES = _FORMULA_BLOCK_TYPES | {"formula"}
# tqdm 进度行，例如：MFR Predict: 98%|████ | 224/229 [03:08<00:32, 6.40s/it]
_TQDM = re.compile(r"(\d{1,3})%\s*\|[^|]*\|\s*(\d+)\s*/\s*(\d+)")


def _estimate_progress(text: str) -> float:
    """Estimate whole-document parse progress from MinerU's per-model tqdm bars.

    MinerU writes one JSON for the entire document only when every model stage
    finishes, so there is no real page counter yet. Each model (OCR-det, OCR-rec,
    Layout, MFR, Table-*) emits a full 0..100% bar; counting finished stages plus
    the current stage ratio gives a monotonically useful approximation.
    """
    stages: dict[str, float] = {}
    order: list[str] = []
    for line in text.splitlines():
        matched = _TQDM.search(line)
        if not matched:
            continue
        done, total = int(matched.group(2)), int(matched.group(3))
        if total <= 0:
            continue
        head = line.split(":", 1)[0].strip()
        name = head.split()[0] if head else "model"
        ratio = min(done / total, 1.0)
        if name not in stages:
            order.append(name)
        stages[name] = max(stages[name] if name in stages else 0.0, ratio)
    if not order:
        return 0.0
    finished = sum(1 for name in order if stages[name] >= 0.999)
    current = next((stages[name] for name in order if stages[name] < 0.999), 0.0)
    estimated_total = max(6, len(order) + 1, finished + 2)
    return min((finished + current) / estimated_total, 0.9)


def _pdf_page_count(file_path: Path) -> int:
    try:
        import fitz

        with fitz.open(file_path) as document:
            return document.page_count
    except Exception:
        return 0


@dataclass(frozen=True)
class ParsedPage:
    """One page of MinerU output."""

    text: str
    segments: list[TableSegment]
    used_ocr: bool


class MineruAdapter:
    """Parse a PDF with MinerU and return page text plus structured segments."""

    def __init__(self, settings) -> None:
        self.settings = settings
        self.kit = Path(settings.mineru_kit_path)
        if not self.kit.is_absolute():
            self.kit = (Path.cwd() / self.kit).resolve()
        # .mineru/Scripts/mineru-kit.exe -> backend/
        self.working_dir = self.kit.parents[2]

    def available(self) -> bool:
        return self.kit.is_file()

    def parse(
        self,
        file_path: Path,
        namespace: str,
        on_heartbeat: Callable[[float], None] | None = None,
        total_pages: int = 0,
    ) -> dict[int, ParsedPage]:
        if not self.available():
            raise FileNotFoundError(f"mineru-kit not found: {self.kit}")
        if not file_path.is_file():
            raise FileNotFoundError(f"document not found: {file_path}")

        page_count = total_pages or _pdf_page_count(file_path)
        segment_size = int(self.settings.mineru_segment_pages or 0)
        if segment_size <= 0 or page_count <= segment_size:
            segments: list[tuple[int, int] | None] = [None]
        else:
            segments = [
                (start, min(start + segment_size - 1, page_count))
                for start in range(1, page_count + 1, segment_size)
            ]

        all_pages: list[dict] = []
        extensions: dict = {}
        completed = 0
        for page_range in segments:

            def report(local_progress: float, done=completed) -> None:
                if on_heartbeat:
                    on_heartbeat((done + local_progress) / len(segments))

            data = self._parse_segment(file_path, namespace, page_range, report)
            if not extensions:
                extensions = data.get("extensions") or {}
            all_pages.extend(data.get("pages") or [])
            completed += 1
            if on_heartbeat:
                on_heartbeat(completed / len(segments))
        if on_heartbeat:
            on_heartbeat(1.0)

        merged = {"pages": all_pages, "extensions": extensions}
        pages = self._convert(merged, namespace)
        _merge_cross_page_tables(pages)
        return pages

    def _parse_segment(
        self,
        file_path: Path,
        namespace: str,
        page_range: tuple[int, int] | None,
        on_heartbeat: Callable[[float], None],
    ) -> dict:
        cache_file = self._cache_file(file_path, page_range)
        if cache_file is not None and cache_file.is_file():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                if cached.get("pages"):
                    _LOGGER.info(
                        "mineru cache hit %s pages %s",
                        file_path.name,
                        page_range or "all",
                    )
                    on_heartbeat(1.0)
                    return cached
            except (OSError, ValueError):
                pass

        with tempfile.TemporaryDirectory(prefix="oh-mineru-") as tmp:
            output = Path(tmp) / "output"
            output.mkdir(parents=True, exist_ok=True)
            log_path = Path(tmp) / "mineru.log"
            command = [
                str(self.kit),
                "parse",
                str(file_path),
                "-o",
                str(output),
                "--format",
                "middle_json",
                "--tier",
                self.settings.mineru_tier,
            ]
            if page_range:
                command.extend(["--pages", f"{page_range[0]}-{page_range[1]}"])
            env = os.environ.copy()
            env["MINERU_MODEL_SOURCE"] = self.settings.mineru_model_source
            env["MINERU_TELEMETRY_DISABLED"] = "1"
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    command,
                    cwd=str(self.working_dir),
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                best_progress = 0.0
                while process.poll() is None:
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            progress = _estimate_progress(_tail(log_path, 131_072))
                        except OSError:
                            progress = 0.0
                        best_progress = max(best_progress, progress)
                        on_heartbeat(best_progress)
            if process.returncode != 0:
                tail = _tail(log_path)
                raise RuntimeError(f"mineru-kit exited {process.returncode}: {tail}")

            documents = sorted(output.glob("*.json"))
            if not documents:
                raise RuntimeError(f"mineru produced no middle_json: {_tail(log_path)}")
            data = json.loads(documents[0].read_text(encoding="utf-8"))

        if cache_file is not None and data.get("pages"):
            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache_file.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8"
                )
                os.replace(temporary, cache_file)
            except OSError as exc:
                _LOGGER.warning("failed to cache mineru segment: %s", exc)
        return data

    def _cache_file(
        self, file_path: Path, page_range: tuple[int, int] | None
    ) -> Path | None:
        if not self.settings.mineru_segment_cache_enabled:
            return None
        # 对象存储的文件名本身就是内容 sha256；否则退回 size+mtime。
        # 绝不能把路径拼进 key：worker 用相对路径、外部调用用绝对路径会各缓存一份。
        stem = file_path.stem
        if re.fullmatch(r"[0-9a-fA-F]{64}", stem):
            digest = stem[:24]
        else:
            stat = file_path.stat()
            digest = hashlib.sha256(
                f"{stat.st_size}:{stat.st_mtime_ns}".encode()
            ).hexdigest()[:24]
        label = "all" if page_range is None else f"{page_range[0]}-{page_range[1]}"
        return (
            Path(self.settings.storage_root)
            / "cache"
            / "mineru"
            / digest
            / f"{self.settings.mineru_tier}-{label}.json"
        )


    def _convert(self, data: dict, namespace: str) -> dict[int, ParsedPage]:
        mode = (data.get("extensions") or {}).get("mineru", {}).get("parse_mode")
        used_ocr = mode == "ocr"
        result: dict[int, ParsedPage] = {}
        for page in data.get("pages") or []:
            page_number = int(page.get("page_idx", 0)) + 1
            prose: list[str] = []
            segments: list[TableSegment] = []
            sequence = 0

            def flush_prose() -> None:
                # 空行保留段落边界，否则「按结构切分」会退化为按句切分。
                body = "\n\n".join(part for part in prose if part.strip()).strip()
                prose.clear()
                if body:
                    segments.append(TableSegment("text", body))

            for block in page.get("blocks") or []:
                kind = block.get("type")
                if kind in _IGNORED_BLOCKS:
                    continue
                if kind == "table":
                    flush_prose()
                    sequence += 1
                    segment = _table_segment(block, page_number, sequence, namespace)
                    if segment is not None:
                        segment = replace(
                            segment,
                            text=correct_ocr_text(segment.text),
                            header=correct_ocr_text(segment.header),
                            html=correct_ocr_text(segment.html),
                        )
                        segments.append(segment)
                    continue
                if kind in _FORMULA_BLOCK_TYPES:
                    flush_prose()
                    formula = correct_ocr_text(_block_text(block))
                    if formula:
                        segments.append(TableSegment("formula", formula))
                    continue
                text = correct_ocr_text(_block_text(block))
                if text:
                    prose.append(text)
            flush_prose()

            result[page_number] = ParsedPage(
                text="\n\n".join(
                    segment.text for segment in segments if segment.text.strip()
                ),
                segments=segments,
                used_ocr=used_ocr,
            )
        return result


def _formula_text(value: object) -> str:
    """Extract a LaTeX formula from any MinerU content shape."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("latex", "content", "text"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, (list, dict)):
                nested = _formula_text(item)
                if nested:
                    return nested
        return ""
    if isinstance(value, list):
        parts = [_formula_text(item) for item in value]
        return "".join(part for part in parts if part)
    return ""


def _wrap_formula(latex: str, *, block: bool = False) -> str:
    normalized = re.sub(r"\s+", " ", latex.strip()).strip()
    normalized = normalized.strip("$").strip()
    if not normalized:
        return ""
    return f"$${normalized}$$" if block else f"${normalized}$"


def _block_text(block: dict) -> str:
    kind = str(block.get("type") or "")
    content = block.get("content")

    # MinerU 4.x sometimes stores a formula block as one raw LaTeX string.
    # Iterating that string would emit one character per line.
    if kind in _FORMULA_BLOCK_TYPES:
        return _wrap_formula(_formula_text(content), block=True)

    parts: list[str] = []
    has_inline_formula = False
    for item in content if isinstance(content, list) else [content]:
        if isinstance(item, dict):
            item_kind = str(item.get("type") or "")
            value = item.get("content")
            if isinstance(value, (list, dict)):
                value = _block_text({"type": item_kind, "content": value})
            if not isinstance(value, str) or not value.strip():
                continue
            if item_kind in _FORMULA_SPAN_TYPES:
                wrapped = _wrap_formula(_formula_text(value), block=False)
                if wrapped:
                    parts.append(wrapped)
                    has_inline_formula = True
            else:
                parts.append(value)
        elif isinstance(item, str) and item.strip():
            parts.append(item)

    if has_inline_formula:
        # Inline formulas must stay in the same sentence as surrounding text.
        return "".join(parts).strip()
    return "\n".join(part.strip() for part in parts if part.strip())


def _table_segment(
    block: dict, page_number: int, sequence: int, namespace: str
) -> TableSegment | None:
    caption = ""
    html = ""
    for item in block.get("content") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "table_caption":
            caption = _block_text(item)
        elif item.get("type") == "table_body" and isinstance(item.get("content"), str):
            html = item["content"]
    if not html:
        return None

    rows = parse_html_table(html)
    if not rows:
        return None
    title = caption or None
    header = "| " + " | ".join(cell.text for cell in rows[0]) + " |"
    return TableSegment(
        kind="table",
        text=rows_to_text(title, rows),
        header=header,
        table_id=table_id_for(namespace, page_number, sequence, header),
        section_title=title,
        total_rows=len(rows),
        html=rows_to_html(rows),
    )


def _normalise_header(segment: TableSegment) -> str:
    return " ".join((segment.header or "").split())


def _same_table(first: TableSegment, second: TableSegment) -> bool:
    left = _normalise_header(first)
    right = _normalise_header(second)
    if left and right and left == right:
        return True
    first_caption = (first.section_title or "").strip()
    second_caption = (second.section_title or "").strip()
    if first_caption and second_caption:
        if first_caption == second_caption:
            return True
        if "续" in second_caption or second_caption.startswith(first_caption):
            return True
    return False


def _merge_cross_page_tables(pages: dict[int, ParsedPage]) -> None:
    """Merge a table continued right at the top of the next page.

    Only adjacent pages are considered, and only when the previous page ends with
    a table and the next page starts with one whose header/caption matches.
    """
    previous: int | None = None
    for page_number in sorted(pages):
        if previous is None or page_number != previous + 1:
            previous = page_number
            continue
        prev_segments = pages[previous].segments
        current_segments = pages[page_number].segments
        if not prev_segments or not current_segments:
            previous = page_number
            continue
        last = prev_segments[-1]
        first = current_segments[0]
        if last.kind != "table" or first.kind != "table" or not _same_table(last, first):
            previous = page_number
            continue

        merged = merge_rows(
            parse_html_table(last.html or ""), parse_html_table(first.html or "")
        )
        if not merged:
            previous = page_number
            continue
        prev_segments[-1] = replace(
            last,
            text=rows_to_text(last.section_title, merged),
            total_rows=len(merged),
            html=rows_to_html(merged),
            end_page=page_number,
        )
        current_segments.pop(0)
        _LOGGER.info(
            "merged cross-page table %s: page %s + %s",
            last.table_id,
            previous,
            page_number,
        )
        previous = page_number


def _tail(path: Path, limit: int = 800) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return ""
