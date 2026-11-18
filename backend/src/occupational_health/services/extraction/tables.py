"""Detect tables in extracted text and emit one segment per whole table.

Table content arrives in three shapes: Markdown tables (MinerU, MD files,
DOCX tables converted by the loader), HTML tables (some OCR/layout outputs) and
plain text with wide column separators (PDF text layer). All are canonicalised to
``| a | b |`` rows, then emitted as a single ``table`` segment per table.

Every table gets a ``table_id`` derived from the version namespace, page number,
table sequence and header. Cross-page continuation is merged by the MinerU
adapter; this module only sees one page at a time.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from occupational_health.services.extraction.table_html import markdown_rows_to_html

_MARKDOWN_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_DIVIDER_CELL = re.compile(r"^:?-{2,}:?$")
_HTML_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
_HTML_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_WIDE_SEPARATOR = re.compile(r"\t+|\s{2,}")
_CAPTION = re.compile(
    r"^\s*(?:附表|表|Table|TABLE)\s*[\dA-Za-z一二三四五六七八九十.]+"
    r"[\s:：.、\-—]?.{0,80}$"
)


@dataclass(frozen=True)
class TableSegment:
    kind: str  # "text" | "table" | "formula"
    text: str
    header: str | None = None
    table_id: str | None = None
    section_title: str | None = None
    total_rows: int = 0
    # 原始或重建的表格 HTML（含 rowspan/colspan），供确认页与检索结果还原。
    html: str | None = None
    # 跨页合并后的结束页；单页表为 None。
    end_page: int | None = None


def _strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub("", value)).strip()


def _cells_from_markdown(line: str) -> list[str] | None:
    matched = _MARKDOWN_ROW.match(line)
    if not matched:
        return None
    cells = [cell.strip() for cell in matched.group(1).split("|")]
    return cells if len(cells) >= 2 else None


def _cells_from_html(line: str) -> list[str] | None:
    matched = _HTML_ROW.search(line)
    if not matched:
        return None
    cells = [_strip_tags(cell) for cell in _HTML_CELL.findall(matched.group(1))]
    return cells if len(cells) >= 2 else None


def _cells_from_columns(line: str) -> list[str] | None:
    cells = [cell.strip() for cell in _WIDE_SEPARATOR.split(line.strip())]
    cells = [cell for cell in cells if cell]
    if len(cells) < 2:
        return None
    if any(len(cell) > 60 for cell in cells):
        return None
    return cells


def is_divider(cells: list[str]) -> bool:
    return bool(cells) and all(_DIVIDER_CELL.fullmatch(cell or "") for cell in cells)


def _canonical(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def table_id_for(namespace: str, page_number: int, sequence: int, header: str) -> str:
    key = f"{namespace}:{page_number}:{sequence}:{header}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


_table_id = table_id_for


def normalize_table_rows(text: str) -> str:
    """Rewrite table-ish lines into canonical Markdown rows before cleaning.

    Wide-column lines are only converted when at least two consecutive lines
    look like columns, which avoids turning centred headings into tables.
    """
    lines = text.splitlines()
    candidates: dict[int, list[str]] = {}
    for index, line in enumerate(lines):
        cells = _cells_from_html(line) or _cells_from_markdown(line)
        if cells:
            candidates[index] = cells
            continue
        cells = _cells_from_columns(line)
        if cells:
            candidates[index] = cells

    wide_only = {
        index
        for index in candidates
        if _cells_from_markdown(lines[index]) is None
        and _cells_from_html(lines[index]) is None
    }
    accepted: dict[int, list[str]] = {}
    for index, cells in candidates.items():
        if index in wide_only and (index - 1) not in wide_only and (index + 1) not in wide_only:
            continue
        accepted[index] = cells

    output: list[str] = []
    for index, line in enumerate(lines):
        cells = accepted.get(index)
        output.append(_canonical(cells) if cells else line)
    return "\n".join(output)


def table_text(caption: str | None, rows: list[str]) -> str:
    """题注 + 表头 + 分隔行 + 全部数据行，用于向量化与纯文本兜底。"""
    if not rows:
        return ""
    header_cells = _cells_from_markdown(rows[0]) or []
    divider = "| " + " | ".join(["---"] * max(len(header_cells), 1)) + " |"
    return "\n".join(([caption] if caption else []) + [rows[0], divider, *rows[1:]])


def split_table_segments(
    text: str, page_number: int = 1, namespace: str = ""
) -> list[TableSegment]:
    """Split text into prose segments and one segment per whole table."""
    segments: list[TableSegment] = []
    prose: list[str] = []
    table_block: list[list[str]] = []
    state = {"caption": None, "sequence": 0}

    def flush_prose() -> None:
        if prose:
            # 保留原有换行（含空行段落边界），否则每一行都会被当成独立段落，
            # "按结构切分"会把标题和短行切成大量碎块。
            body = "\n".join(prose).strip()
            if body:
                segments.append(TableSegment("text", body))
            prose.clear()

    def flush_table() -> None:
        if not table_block:
            return
        rows = [_canonical(cells) for cells in table_block if not is_divider(cells)]
        table_block.clear()
        if not rows:
            state["caption"] = None
            return
        header = rows[0]
        state["sequence"] += 1
        table_id = _table_id(namespace, page_number, state["sequence"], header)
        caption = state["caption"]
        segments.append(
            TableSegment(
                kind="table",
                text=table_text(caption, rows),
                header=header,
                table_id=table_id,
                section_title=caption,
                total_rows=len(rows),
                html=markdown_rows_to_html(rows),
            )
        )
        state["caption"] = None

    for line in text.splitlines():
        cells = _cells_from_markdown(line)
        if cells and len(cells) >= 2:
            if not table_block:
                # 表格开始：从紧邻的上一行提取题注，并先输出前面的正文保序。
                state["caption"] = _caption_from(prose)
                flush_prose()
            table_block.append(cells)
            continue
        flush_table()
        prose.append(line)

    flush_table()
    flush_prose()
    return segments


def _caption_from(prose: list[str]) -> str | None:
    for line in reversed(prose):
        candidate = line.strip()
        if not candidate:
            continue
        return candidate if _CAPTION.match(candidate) else None
    return None


def is_table_row_line(line: str) -> bool:
    return _cells_from_markdown(line) is not None
