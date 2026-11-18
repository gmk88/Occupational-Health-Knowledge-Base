from __future__ import annotations

import re

from occupational_health.services.extraction.tables import (
    is_table_row_line,
    normalize_table_rows,
)

PAGE_NUMBER = re.compile(r"^\s*[-—–]?\s*\d{1,4}\s*[-—–]?\s*$")
FULLWIDTH_MAP = str.maketrans("，。！？；：" "''（）【】", ',.!?;:""()[]')
# 已知 OCR 误识别；只修正确定性的表头错误，不做泛化替换。
OCR_CORRECTIONS = {
    "警 SECEmg/m": "警报值 mg/m³",
    "检测误%F.S.)": "检测误差(%F.S.)",
}

# 只对已从标准原图核对过的缺失字符做定点修复。
# 这些 Unicode 替换符来自 PDF 字体编码缺字，重新解析同一 PDF 不会自行恢复。
OCR_REPLACEMENT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\ufffd\s*——\s*喷头雾化角"), "θ ——喷头雾化角"),
    (re.compile(r"流量偏差\s*%\s*=\s*\ufffd\s*[−-]\s*\ufffd0\s*×\s*100\s*\n\s*\ufffd0"),
     "流量偏差(%) = (M−M₀) × 100 / M₀"),
    (re.compile(r"C\s*=\s*\ufffd\s*[−-]\s*\ufffd0\s*\n\s*\ufffd0\s*×\s*\ufffd\s*×\s*\ufffd"),
     "C = (C−C₀)/(V₀ × D × K)"),
    (re.compile(r"\ufffd\s*=\s*\ufffd2\s*[−-]\s*\ufffd1\s*\n\s*\ufffd0\s*×\s*106"),
     "C = (m₂−m₁) × 10⁶ / V₀"),
    (re.compile(r"□\ufffd\s*=\s*\ufffd2\s*[−-]\s*\ufffd1\s*×\s*100\s*\n\s*\ufffd"),
     "□C = (m₃−m₁) × 100 / m"),
    (re.compile(r"□\ufffd\s*=\s*\ufffd2\s*[−-]\s*\ufffd3\s*×\s*100\s*\n\s*\ufffd"),
     "□C = (m₂−m₃) × 100 / m"),
    (re.compile(r"平均值\ufffd\s*和\s*标准偏差"), r"平均值 $\bar{X}$ 和标准偏差"),
    (re.compile(r"\ufffd\ufffd标准偏差"), r"$\bar{X}$ 标准偏差"),
    (re.compile(r"\ufffd\ufffd\s*=\s*\n\s*1"), r"$\bar{X}$ =\n1"),
    (re.compile(r"\ufffd\ufffd\s*[−-]\s*\ufffd\ufffd"), r"$\bar{X}$ − $\bar{X}$"),
    (re.compile(r"\$X _ \{ \\boldsymbol \{ \\theta \} \} \\bar \{ \}\$\s*本底检测结果"),
     r"$X_0$ 本底检测结果"),
    (re.compile(r"\ufffd——平均值"), r"$\bar{X}$——平均值"),
    (re.compile(r"\ufffd\s*——\s*平均值"), r"$\bar{X}$ ——平均值"),
)



def normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def remove_standalone_page_numbers(lines: list[str]) -> list[str]:
    return [line for line in lines if not PAGE_NUMBER.match(line.strip())]


def remove_repeated_header_footer(lines: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for line in lines:
        # 空行是段落边界，绝不能参与"重复页眉页脚"统计，否则会被整批删掉。
        key = normalize_whitespace(line)
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    repeated = {key for key, value in counts.items() if value >= 3 and len(key) <= 40}
    # 表格行（尤其是跨页重复的表头）不能被当作页眉页脚删掉。
    return [
        line
        for line in lines
        if not line.strip()
        or is_table_row_line(line)
        or normalize_whitespace(line) not in repeated
    ]


_TABLE_HEADER_HINTS = ("序号", "名称", "项目", "指标", "单位", "限值", "标准", "物质", "因素")


def remove_repeated_table_headers(lines: list[str]) -> list[str]:
    """Drop repeated header rows copied into the middle of long tables."""
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = normalize_whitespace(line)
        if (
            is_table_row_line(line)
            and key
            and any(hint in key for hint in _TABLE_HEADER_HINTS)
        ):
            if key in seen:
                continue
            seen.add(key)
        output.append(line)
    return output


def merge_broken_lines(lines: list[str]) -> list[str]:
    merged: list[str] = []
    for line in lines:
        stripped = line.rstrip()
        if merged and merged[-1] and _looks_continuation(stripped):
            merged[-1] = merged[-1] + stripped
        else:
            merged.append(stripped)
    return [line for line in merged if line]


def _looks_continuation(line: str) -> bool:
    if not line:
        return False
    return line[0].islower() or line[0] in "，。；：、）)"


def correct_ocr_text(text: str | None) -> str | None:
    if not text:
        return text
    corrected = text.replace("\x00", "")
    for wrong, correct in OCR_CORRECTIONS.items():
        corrected = corrected.replace(wrong, correct)
    for pattern, replacement in OCR_REPLACEMENT_PATTERNS:
        corrected = pattern.sub(lambda _match, value=replacement: value, corrected)
    return corrected


def clean_text(raw: str) -> tuple[str, int]:
    """Normalise text while keeping paragraph breaks.

    Paragraph boundaries must survive cleaning: ``split_pages`` relies on blank
    lines for the ``structure`` chunk mode. Cleaning per paragraph also prevents
    unrelated blocks from being merged into one long line.
    """
    # PostgreSQL text 列不接受 NUL 字节，解析器输出可能带入，先在源头清掉。
    raw = raw.replace("\x00", "")
    normalized_tables = normalize_table_rows(raw)
    lines = [normalize_whitespace(line) for line in normalized_tables.splitlines()]
    lines = remove_standalone_page_numbers(lines)
    # 页眉页脚需要在全文范围统计，分段后再做会失效。
    lines = remove_repeated_header_footer(lines)
    lines = remove_repeated_table_headers(lines)

    paragraphs: list[list[str]] = [[]]
    for line in lines:
        if line.strip():
            paragraphs[-1].append(line)
        elif paragraphs[-1]:
            paragraphs.append([])

    cleaned = [
        "\n".join(merge_broken_lines(paragraph))
        for paragraph in paragraphs
        if paragraph
    ]
    normalized = "\n\n".join(cleaned).translate(FULLWIDTH_MAP).replace("\x00", "")
    normalized = correct_ocr_text(normalized) or ""
    noise_chars = max(0, len(raw) - len(normalized))
    return normalized, noise_chars
