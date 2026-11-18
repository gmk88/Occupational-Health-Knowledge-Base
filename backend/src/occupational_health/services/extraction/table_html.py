"""Shared helpers for structured tables (HTML -> cells -> Markdown/HTML).

Used by both the MinerU adapter (which receives real HTML with rowspan/colspan)
and the regular-expression fallback (which only has Markdown rows). Keeping the
conversion in one place means the review page and the search API can rely on a
single canonical representation.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from html.parser import HTMLParser

_INLINE_WHITESPACE = re.compile(r"[ \t]+")
_NEWLINE_RUN = re.compile(r"\n+")


@dataclass(frozen=True)
class TableCell:
    text: str
    rowspan: int = 1
    colspan: int = 1


def _positive_int(value: str | None) -> int:
    try:
        parsed = int(value or "1")
    except ValueError:
        return 1
    return max(1, min(parsed, 20))


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[TableCell]] = []
        self._row: list[TableCell] | None = None
        self._cell: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
            return
        if tag in ("td", "th") and self._row is not None:
            values = dict(attrs)
            self._cell = {
                "parts": [],
                "rowspan": _positive_int(values.get("rowspan")),
                "colspan": _positive_int(values.get("colspan")),
            }
            return
        if tag == "br" and self._cell is not None:
            self._cell["parts"].append("\n")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            raw = "".join(self._cell["parts"])
            raw = "\n".join(_INLINE_WHITESPACE.sub(" ", part).strip() for part in raw.split("\n"))
            text = _NEWLINE_RUN.sub("\n", raw).strip()
            self._row.append(
                TableCell(text, self._cell["rowspan"], self._cell["colspan"])
            )
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None


def parse_html_table(source: str) -> list[list[TableCell]]:
    """Parse a ``<table>`` fragment, keeping rowspan/colspan information."""
    parser = _TableParser()
    parser.feed(source)
    parser.close()
    return parser.rows


def _known_subrow_repair(row: list[str]) -> list[list[str]] | None:
    text = " ".join(cell for cell in row if cell)
    rules = (
        (
            ("铅及其无机化合物", "铅尘铅烟", "0.050.03"),
            (("铅尘", "0.05"), ("铅烟", "0.03")),
        ),
        (
            ("镍及其无机化合物", "金属镍与难溶性镍化合物", "10.5"),
            (("金属镍与难溶性镍化合物", "1"), ("可溶性镍化合物", "0.5")),
        ),
        (
            ("钼及其化合物", "不溶性化合物", "64"),
            (("钼，不溶性化合物", "6"), ("钼，可溶性化合物", "4")),
        ),
    )
    for needles, replacements in rules:
        if not all(needle in text for needle in needles):
            continue
        merged_value = needles[-1]
        repaired: list[list[str]] = []
        for name, value in replacements:
            cells = list(row)
            for index, cell in enumerate(cells):
                if needles[0] in cell:
                    cells[index] = name
                elif cell == merged_value:
                    cells[index] = value
            repaired.append(cells)
        return repaired
    return None


def expand_rows(rows: list[list[TableCell]]) -> list[list[str]]:
    """Flatten merged cells into a rectangular grid of repeated values."""
    grid: dict[tuple[int, int], str] = {}
    max_column = 0
    for row_index, row in enumerate(rows):
        column = 0
        for cell in row:
            while (row_index, column) in grid:
                column += 1
            for dr in range(cell.rowspan):
                for dc in range(cell.colspan):
                    grid[(row_index + dr, column + dc)] = cell.text
            column += cell.colspan
            max_column = max(max_column, column)
    if not grid:
        return []
    max_row = max(row for row, _ in grid) + 1
    expanded = [
        [grid.get((row, column), "") for column in range(max_column)]
        for row in range(max_row)
    ]
    repaired: list[list[str]] = []
    for row in expanded:
        fixed = _known_subrow_repair(row)
        repaired.extend(fixed if fixed else [row])
    return repaired


def rows_to_markdown(rows: list[list[TableCell]]) -> list[str]:
    lines: list[str] = []
    for cells in expand_rows(rows):
        normalized = [cell.replace("\n", "<br>") for cell in cells]
        lines.append("| " + " | ".join(normalized) + " |")
    return lines


def rows_to_html(rows: list[list[TableCell]]) -> str:
    """Serialise cells back to a normalised, escaped HTML table."""
    parts = ["<table>"]
    for row in rows:
        parts.append("<tr>")
        for cell in row:
            attrs = ""
            if cell.rowspan > 1:
                attrs += f' rowspan="{cell.rowspan}"'
            if cell.colspan > 1:
                attrs += f' colspan="{cell.colspan}"'
            parts.append(f"<td{attrs}>{html_lib.escape(cell.text)}</td>")
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


def markdown_rows_to_html(rows: list[str]) -> str:
    """Build a displayable HTML table from canonical Markdown rows."""
    parts = ["<table>"]
    for index, row in enumerate(rows):
        cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
        parts.append("<tr>")
        for cell in cells:
            tag = "th" if index == 0 else "td"
            parts.append(f"<{tag}>{html_lib.escape(cell)}</{tag}>")
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)


def header_signature(rows: list[list[TableCell]]) -> str:
    if not rows:
        return ""
    return " | ".join(cell.text for cell in rows[0])


def merge_rows(
    first: list[list[TableCell]],
    second: list[list[TableCell]],
    drop_header: bool = True,
) -> list[list[TableCell]]:
    """Append a continuation table, dropping its repeated header row."""
    if not first:
        return list(second)
    if not second:
        return list(first)
    if drop_header and header_signature(first) == header_signature(second):
        return [*first, *second[1:]]
    return [*first, *second]


def rows_to_text(caption: str | None, rows: list[list[TableCell]]) -> str:
    """Canonical text used for embedding and plain-text fallbacks."""
    markdown = rows_to_markdown(rows)
    if not markdown:
        return ""
    header = markdown[0]
    column_count = max(len([cell for cell in header.split("|") if cell.strip()]), 1)
    divider = "| " + " | ".join(["---"] * column_count) + " |"
    return "\n".join(([caption] if caption else []) + [header, divider, *markdown[1:]])
