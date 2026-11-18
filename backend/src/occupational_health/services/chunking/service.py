from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from occupational_health.domain.enums import ChunkMode, ChunkRole
from occupational_health.services.extraction.table_html import expand_rows
from occupational_health.services.extraction.tables import TableSegment, split_table_segments

SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？；.!?;])\s*")
# 段落边界：空行，或 Markdown / 结构化文档的标题行行首。
PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n|^(?=#{1,6}\s)", re.MULTILINE)
TOKEN_RUN = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9]+(?:[._/-][A-Za-z0-9]+)*|[^\s]|\s+")
# 父块最多跨 3 页，避免引用时返回整篇文档的页码范围。
MAX_PARENT_PAGE_SPAN = 3


@dataclass(frozen=True)
class ChunkInput:
    page_number: int
    text: str
    source_type: str
    offset: int = 0


def approximate_token_count(text: str) -> int:
    # CJK characters count as one token each; ASCII words count as one token.
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    ascii_words = len(re.findall(r"[A-Za-z0-9]+(?:[._/-][A-Za-z0-9]+)*", text))
    return cjk + ascii_words


def split_pages(
    pages: list[ChunkInput],
    target: int,
    max_tokens: int,
    overlap: int,
    mode: str | ChunkMode = "sentence",
    table_namespace: str = "",
    page_segments: dict[int, list[TableSegment]] | None = None,
    parent_target: int | None = None,
    parent_max_tokens: int | None = None,
    child_target: int | None = None,
    child_max_tokens: int | None = None,
    child_overlap: int | None = None,
) -> list[dict]:
    """Split page texts into chunks.

    ``structure`` = one paragraph per chunk, ``sentence`` = one sentence per
    chunk; neither uses ``target``/``max_tokens``. Only ``fixed`` packs prose
    into ``target``-sized windows with ``max_tokens`` as a hard ceiling.

    ``overlap`` prepends the tail of the previous prose chunk to the next one
    (token based, may cut mid-sentence). Tables break the overlap chain.

    A table always becomes exactly one chunk. Prose directly in front of it is
    merged into that chunk (``block_type="table"``) so the context stays bound
    to the table, and the merged ``table_html`` is preserved.
    """
    resolved = mode if isinstance(mode, ChunkMode) else ChunkMode(mode)
    if resolved == ChunkMode.PARENT_CHILD:
        return _split_parent_child(
            pages,
            parent_target or target,
            parent_max_tokens or max_tokens,
            child_target or target,
            child_max_tokens or max_tokens,
            child_overlap if child_overlap is not None else overlap,
            table_namespace,
            page_segments,
        )
    splitter = _SPLITTERS[resolved]
    separator = "\n\n" if resolved == ChunkMode.STRUCTURE else ""
    chunks: list[dict] = []
    prose_parts: list[str] = []
    prose_pages: list[int] = []
    ordinal = 0
    previous_body = ""

    def emit(units: list[str], page_numbers: list[int]) -> None:
        nonlocal ordinal, previous_body
        for unit in units:
            if not unit.strip():
                continue
            text = unit
            if overlap > 0 and previous_body:
                prefix = _tail_tokens(previous_body, overlap)
                if prefix:
                    text = f"{prefix}{separator}{unit}"
            chunks.append(_build_chunk(text, page_numbers, ordinal, overlap))
            ordinal += 1
            # 只用未加前缀的正文参与下一次重叠，否则重叠会逐块叠加膨胀。
            previous_body = unit

    def split_units(body: str) -> list[str]:
        units: list[str] = []
        for part in splitter(body, target):
            # 结构/句子模式一块就是一个段落/句子，绝不按 token 数二次切分；
            # 只有固定大小模式才用 max_tokens 兜底硬切。
            if (
                resolved == ChunkMode.FIXED
                and approximate_token_count(part) > max_tokens
            ):
                units.extend(_split_by_fixed(part, max_tokens))
            else:
                units.append(part)
        return [unit for unit in units if unit.strip()]

    def flush_prose() -> None:
        body = "\n\n".join(part for part in prose_parts if part.strip()).strip()
        prose_parts.clear()
        if not body:
            prose_pages.clear()
            return
        page_numbers = prose_pages or [1]
        emit(split_units(body), page_numbers)
        prose_pages.clear()

    last_page: int | None = None
    for page in pages:
        if resolved == ChunkMode.STRUCTURE and last_page is not None and page.page_number != last_page:
            flush_prose()
        last_page = page.page_number
        segments = (page_segments or {}).get(page.page_number)
        if segments is None:
            segments = split_table_segments(
                page.text, page.page_number, table_namespace
            )
        for segment in segments:
            if segment.kind == "formula":
                flush_prose()
                chunks.append(
                    _build_chunk(
                        segment.text,
                        [page.page_number],
                        ordinal,
                        0,
                        block_type="formula",
                    )
                )
                ordinal += 1
                previous_body = ""
                continue
            if segment.kind == "table":
                page_numbers = [page.page_number]
                if segment.end_page and segment.end_page != page.page_number:
                    page_numbers.append(segment.end_page)
                # 只把紧贴表格的那一段并进表格块；更早的正文仍按正常规则切分，
                # 否则整节内容都会被吸进表格块。
                lead = ""
                lead_page = page.page_number
                if prose_parts:
                    body = "\n\n".join(
                        part for part in prose_parts if part.strip()
                    ).strip()
                    units = split_units(body) if body else []
                    if units:
                        lead = units.pop()
                    if units:
                        emit(units, prose_pages or [page.page_number])
                    if lead and prose_pages:
                        lead_page = prose_pages[-1]
                    prose_parts.clear()
                    prose_pages.clear()
                # 表题注常被解析器同时算进表格文本，避免重复拼接。
                if lead and lead in segment.text:
                    lead = ""
                if lead:
                    page_numbers = sorted(set(page_numbers) | {lead_page})
                    text = f"{lead}\n\n{segment.text}"
                else:
                    text = segment.text
                chunks.append(
                    _build_chunk(
                        text,
                        page_numbers,
                        ordinal,
                        0,
                        block_type="table",
                        table_header=segment.header,
                        table_id=segment.table_id,
                        section_title=segment.section_title,
                        html=segment.html,
                    )
                )
                ordinal += 1
                # 表格打断重叠链：表格之后的第一段正文不与表格前的正文重叠。
                previous_body = ""
                continue
            if page.page_number not in prose_pages:
                prose_pages.append(page.page_number)
            prose_parts.append(segment.text)
    flush_prose()
    return chunks


_CJK_RUN = re.compile(r"[\u4e00-\u9fff]")
_WORD_RUN = re.compile(r"[A-Za-z0-9]+(?:[._/-][A-Za-z0-9]+)*")


def _tail_tokens(text: str, count: int) -> str:
    """取文本末尾 ``count`` 个 token，允许在句子中间截断。

    计数口径与 :func:`approximate_token_count` 保持一致：一个汉字或一个
    英文词算一个 token，标点本身不计数但会被一并带出。
    """
    if count <= 0 or not text.strip():
        return ""
    runs = TOKEN_RUN.findall(text)
    taken = 0
    index = len(runs)
    while index > 0 and taken < count:
        index -= 1
        run = runs[index]
        if _CJK_RUN.fullmatch(run) or _WORD_RUN.fullmatch(run):
            taken += 1
    return "".join(runs[index:]).lstrip()


def _split_by_sentences(text: str, target: int) -> list[str]:
    """一句一块；句末标点是唯一边界，不按 token 数聚合。"""
    sentences = [part.strip() for part in SENTENCE_BOUNDARY.split(text) if part.strip()]
    return sentences or [text.strip()]


def _split_by_structure(text: str, target: int) -> list[str]:
    """一段一块；空行或标题行是唯一边界，不按 token 数聚合。"""
    paragraphs = [part.strip() for part in PARAGRAPH_BOUNDARY.split(text) if part.strip()]
    if paragraphs:
        return paragraphs
    # 没有空行/标题时一行一块，不静默变成"按句切分"。
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines or [text.strip()]


def _split_by_fixed(text: str, target: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for run in TOKEN_RUN.findall(text):
        if run.isspace():
            current += run
            continue
        if approximate_token_count(current + run) > target and current.strip():
            parts.append(current.strip())
            current = run
        else:
            current += run
    if current.strip():
        parts.append(current.strip())
    return parts


_SPLITTERS = {
    ChunkMode.STRUCTURE: _split_by_structure,
    ChunkMode.SENTENCE: _split_by_sentences,
    ChunkMode.FIXED: _split_by_fixed,
}


_HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}\s+\S")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def _split_parent_child(
    pages: list[ChunkInput],
    parent_target: int,
    parent_max: int,
    child_target: int,
    child_max: int,
    child_overlap: int,
    table_namespace: str,
    page_segments: dict[int, list[TableSegment]] | None,
) -> list[dict]:
    """Build semantic parents, then small child windows for retrieval."""
    units = split_pages(
        pages,
        parent_target,
        parent_max,
        0,
        mode=ChunkMode.STRUCTURE,
        table_namespace=table_namespace,
        page_segments=page_segments,
    )
    parents: list[dict] = []
    prose: list[dict] = []

    def flush_prose() -> None:
        if not prose:
            return
        text = "\n\n".join(unit["text"] for unit in prose if unit["text"].strip())
        pages_numbers = sorted(
            {number for unit in prose for number in range(unit["page_start"], unit["page_end"] + 1)}
        )
        parents.append(
            _build_chunk(
                text,
                pages_numbers or [1],
                len(parents),
                0,
                chunk_role=ChunkRole.PARENT,
            )
        )
        prose.clear()

    for unit in units:
        if unit.get("block_type") in {"table", "formula"}:
            flush_prose()
            parent = dict(unit)
            parent["ordinal"] = len(parents)
            parent["overlap"] = 0
            parent["chunk_role"] = ChunkRole.PARENT
            parents.append(parent)
            continue
        expanded = (
            _split_by_fixed(unit["text"], parent_max)
            if approximate_token_count(unit["text"]) > parent_max
            else [unit["text"]]
        )
        for part in expanded:
            candidate = dict(unit)
            candidate["text"] = part
            page_span = 1
            if prose:
                starts = [item["page_start"] for item in prose] + [candidate["page_start"]]
                ends = [item["page_end"] for item in prose] + [candidate["page_end"]]
                page_span = max(ends) - min(starts) + 1
            if prose and (
                page_span > MAX_PARENT_PAGE_SPAN
                or approximate_token_count(
                    "\n\n".join(item["text"] for item in [*prose, candidate])
                )
                > parent_target
            ):
                flush_prose()
            prose.append(candidate)
    flush_prose()
    children = build_children_from_parents(
        parents,
        child_target,
        child_max,
        child_overlap,
        ordinal_start=len(parents),
    )
    return [*parents, *children]


def build_children_from_parents(
    parents: list[dict],
    target: int,
    max_tokens: int,
    overlap: int,
    ordinal_start: int | None = None,
) -> list[dict]:
    """Create sentence/row-window children for already edited parent chunks."""
    result: list[dict] = []
    ordinal = (
        max((int(parent.get("ordinal") or 0) for parent in parents), default=-1) + 1
        if ordinal_start is None
        else ordinal_start
    )
    for parent in parents:
        parent_ordinal = int(parent.get("ordinal") or 0)
        if parent.get("block_type") == "table":
            children = _table_children(parent, target, max_tokens)
        elif parent.get("block_type") == "formula":
            children = [
                _build_chunk(
                    parent.get("text") or "",
                    [parent.get("page_start") or 1, parent.get("page_end") or 1],
                    0,
                    0,
                    block_type="formula",
                    section_title=parent.get("section_title"),
                )
            ]
        else:
            children = _prose_children(parent, target, max_tokens, overlap)
        for child_index, child in enumerate(children):
            item = dict(child)
            item["ordinal"] = ordinal
            item["chunk_role"] = ChunkRole.CHILD
            item["parent_ordinal"] = parent_ordinal
            item["child_index"] = child_index
            ordinal += 1
            result.append(item)
    return result


def _context_prefix(parent: dict) -> str:
    first_line = (parent.get("text") or "").splitlines()[0].strip() if parent.get("text") else ""
    if _HEADING_LINE.match(first_line):
        return first_line
    return (parent.get("section_title") or "").strip()


def _prose_children(parent: dict, target: int, max_tokens: int, overlap: int) -> list[dict]:
    text = parent.get("text") or ""
    context = _context_prefix(parent)
    sentences = [part.strip() for part in SENTENCE_BOUNDARY.split(text) if part.strip()]
    if not sentences:
        return []
    units: list[str] = []
    current = ""
    for sentence in sentences:
        if approximate_token_count(sentence) > max_tokens:
            if current:
                units.append(current)
                current = ""
            units.extend(_split_by_fixed(sentence, max_tokens))
            continue
        candidate = f"{current}{sentence}" if current else sentence
        if current and approximate_token_count(candidate) > target:
            units.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        units.append(current)

    children: list[dict] = []
    previous = ""
    for unit in units:
        body = unit
        if context and not body.startswith(context):
            body = f"{context}\n\n{body}"
        if overlap > 0 and previous:
            prefix = _tail_tokens(previous, overlap)
            if prefix:
                body = f"{prefix}\n\n{body}"
        children.append(
            _build_chunk(
                body,
                [parent.get("page_start") or 1, parent.get("page_end") or 1],
                0,
                overlap,
            )
        )
        previous = unit
    return children


def _table_children(parent: dict, target: int, max_tokens: int) -> list[dict]:
    lines = [line.strip() for line in (parent.get("text") or "").splitlines() if line.strip()]
    table_lines = [line for line in lines if line.startswith("|")]
    rows = [
        line for line in table_lines if not _TABLE_SEPARATOR.match(line)
    ]
    if not rows:
        return [
            _build_chunk(
                parent.get("text") or "",
                [parent.get("page_start") or 1, parent.get("page_end") or 1],
                0,
                0,
                block_type="table",
                table_header=parent.get("table_header"),
                table_id=parent.get("table_id"),
                section_title=parent.get("section_title"),
            )
        ]
    header = rows[0]
    data_rows = rows[1:]
    caption = (parent.get("section_title") or "").strip()
    children: list[dict] = []
    current: list[str] = []
    start = 1
    for index, row in enumerate(data_rows, start=1):
        trial = [header, *current, row]
        if current and approximate_token_count("\n".join(trial)) > target:
            children.append(
                _table_child_text(parent, caption, header, current, start, index - 1)
            )
            start = index
            current = [row]
        else:
            current.append(row)
    if current:
        children.append(
            _table_child_text(parent, caption, header, current, start, len(data_rows))
        )
    return children


def _table_child_text(
    parent: dict,
    caption: str,
    header: str,
    rows: list[str],
    row_start: int,
    row_end: int,
) -> dict:
    parts = [caption] if caption else []
    parts.extend([header, "| --- |", *rows])
    return _build_chunk(
        "\n".join(parts),
        [parent.get("page_start") or 1, parent.get("page_end") or 1],
        0,
        0,
        block_type="table",
        table_header=parent.get("table_header") or header,
        table_id=parent.get("table_id"),
        section_title=parent.get("section_title"),
        page_offsets={"row_start": row_start, "row_end": row_end},
    )


def sanitize_text(value: str | None) -> str | None:
    """PostgreSQL text columns reject NUL (0x00) bytes from parsed documents."""
    return value.replace("\x00", "") if value else value


def _build_chunk(
    text: str,
    page_numbers: list[int],
    ordinal: int,
    overlap: int,
    block_type: str = "text",
    table_header: str | None = None,
    table_id: str | None = None,
    section_title: str | None = None,
    html: str | None = None,
    chunk_role: str = ChunkRole.LEAF,
    page_offsets: dict | None = None,
) -> dict:
    # 在生成 hash 之前清洗，保证 token_count / content_hash 与落库文本一致。
    content = sanitize_text(text) or ""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return {
        "ordinal": ordinal,
        "text": content,
        "page_start": min(page_numbers),
        "page_end": max(page_numbers),
        "token_count": approximate_token_count(content),
        "content_hash": digest,
        "overlap": overlap,
        "block_type": block_type,
        "chunk_role": chunk_role,
        "table_header": sanitize_text(table_header),
        "table_id": sanitize_text(table_id),
        "section_title": sanitize_text(section_title),
        "page_offsets": page_offsets or {},
        "table_html": sanitize_text(html),
    }
