from occupational_health.services.extraction.mineru import (
    ParsedPage,
    _merge_cross_page_tables,
)
from occupational_health.services.extraction.table_html import (
    parse_html_table,
    rows_to_html,
    rows_to_text,
)
from occupational_health.services.extraction.tables import TableSegment

FIRST = (
    "<table><tr><td>A</td><td>B</td></tr>"
    "<tr><td>1</td><td>2</td></tr></table>"
)
SECOND = (
    "<table><tr><td>A</td><td>B</td></tr>"
    "<tr><td>3</td><td>4</td></tr></table>"
)
OTHER = (
    "<table><tr><td>C</td><td>D</td></tr>"
    "<tr><td>5</td><td>6</td></tr></table>"
)


def _segment(html: str, caption: str | None, table_id: str) -> TableSegment:
    rows = parse_html_table(html)
    header = "| " + " | ".join(cell.text for cell in rows[0]) + " |"
    return TableSegment(
        kind="table",
        text=rows_to_text(caption, rows),
        header=header,
        table_id=table_id,
        section_title=caption,
        total_rows=len(rows),
        html=rows_to_html(rows),
    )


def _pages(first: TableSegment, second: TableSegment, gap: bool = False) -> dict:
    pages = {
        1: ParsedPage("", [first], True),
        2: ParsedPage("", [second], True),
    }
    if gap:
        pages = {1: pages[1], 3: pages[2]}
    return pages


def test_merges_same_header_on_adjacent_pages() -> None:
    pages = _pages(_segment(FIRST, "表1 限值", "t1"), _segment(SECOND, "表1 限值", "t2"))
    _merge_cross_page_tables(pages)
    assert len(pages[1].segments) == 1
    assert pages[2].segments == []
    merged = pages[1].segments[0]
    assert merged.total_rows == 3
    assert merged.end_page == 2
    assert "| 3 | 4 |" in merged.text
    assert merged.table_id == "t1"


def test_keeps_tables_with_different_header_separate() -> None:
    pages = _pages(_segment(FIRST, "表1 限值", "t1"), _segment(OTHER, "表2 限值", "t2"))
    _merge_cross_page_tables(pages)
    assert len(pages[1].segments) == 1
    assert len(pages[2].segments) == 1


def test_does_not_merge_non_adjacent_pages() -> None:
    pages = _pages(
        _segment(FIRST, "表1 限值", "t1"),
        _segment(SECOND, "表1 限值", "t2"),
        gap=True,
    )
    _merge_cross_page_tables(pages)
    assert len(pages[1].segments) == 1
    assert len(pages[3].segments) == 1


def test_does_not_merge_when_page_starts_with_text() -> None:
    pages = _pages(_segment(FIRST, "表1 限值", "t1"), _segment(SECOND, "表1 限值", "t2"))
    pages[2] = ParsedPage(
        "", [TableSegment("text", "正文"), pages[2].segments[0]], True
    )
    _merge_cross_page_tables(pages)
    assert len(pages[2].segments) == 2
