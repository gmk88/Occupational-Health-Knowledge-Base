from occupational_health.services.extraction.table_html import (
    TableCell,
    expand_rows,
    header_signature,
    markdown_rows_to_html,
    merge_rows,
    parse_html_table,
    rows_to_html,
    rows_to_markdown,
    rows_to_text,
)

MERGED = (
    "<table>"
    "<tr><td rowspan=2>接触时间</td><td colspan=2>连续波</td></tr>"
    "<tr><td>功率密度</td><td>电场强度</td></tr>"
    "<tr><td>8h</td><td>0.05</td><td>14</td></tr>"
    "</table>"
)


def test_parse_keeps_merged_cells() -> None:
    rows = parse_html_table(MERGED)
    assert len(rows) == 3
    assert rows[0][0] == TableCell("接触时间", 2, 1)
    assert rows[0][1] == TableCell("连续波", 1, 2)


def test_expand_rows_repeats_merged_values() -> None:
    rows = expand_rows(parse_html_table(MERGED))
    assert rows[0] == ["接触时间", "连续波", "连续波"]
    assert rows[1][0] == "接触时间"
    assert rows[2] == ["8h", "0.05", "14"]


def test_rows_to_markdown_is_canonical() -> None:
    markdown = rows_to_markdown(parse_html_table(MERGED))
    assert markdown[0] == "| 接触时间 | 连续波 | 连续波 |"
    assert markdown[2] == "| 8h | 0.05 | 14 |"


def test_rows_to_html_keeps_span_attributes() -> None:
    html = rows_to_html(parse_html_table(MERGED))
    assert 'rowspan="2"' in html
    assert 'colspan="2"' in html
    assert "<table>" in html


def test_rows_to_html_preserves_subrow_breaks() -> None:
    rows = [[TableCell("甲\n乙"), TableCell("1")]]
    html = rows_to_html(rows)
    assert "<td>甲<br>乙</td>" in html
    assert parse_html_table(html)[0][0].text == "甲\n乙"


def test_markdown_rows_to_html_preserves_br_markers() -> None:
    html = markdown_rows_to_html(["| 甲<br>乙 | 1 |"])
    assert "&lt;br&gt;" not in html
    assert "<th>甲<br>乙</th>" in html
    assert parse_html_table(html)[0][0].text == "甲\n乙"


def test_merge_rows_drops_repeated_header() -> None:
    first = parse_html_table(
        "<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>"
    )
    second = parse_html_table(
        "<table><tr><td>A</td><td>B</td></tr><tr><td>3</td><td>4</td></tr></table>"
    )
    merged = merge_rows(first, second)
    assert len(merged) == 3
    assert header_signature(merged) == "A | B"


def test_merge_rows_keeps_header_when_different() -> None:
    first = parse_html_table(
        "<table><tr><td>A</td><td>B</td></tr><tr><td>1</td><td>2</td></tr></table>"
    )
    second = parse_html_table(
        "<table><tr><td>C</td><td>D</td></tr><tr><td>3</td><td>4</td></tr></table>"
    )
    assert len(merge_rows(first, second)) == 4


def test_markdown_rows_to_html_uses_th_for_header() -> None:
    html = markdown_rows_to_html(["| A | B |", "| 1 | 2 |"])
    assert "<th>A</th>" in html
    assert "<td>1</td>" in html


def test_rows_to_text_includes_caption_and_divider() -> None:
    text = rows_to_text("表1 限值", parse_html_table(MERGED))
    assert text.startswith("表1 限值")
    assert "| --- | --- | --- |" in text
