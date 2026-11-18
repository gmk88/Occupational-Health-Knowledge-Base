from occupational_health.services.chunking.service import ChunkInput, split_pages
from occupational_health.services.extraction.cleaning import (
    clean_text,
    remove_repeated_table_headers,
)
from occupational_health.services.extraction.table_html import (
    TableCell,
    expand_rows,
    parse_html_table,
    rows_to_markdown,
)
from occupational_health.services.masking.rules import detect_spans


def test_table_cell_preserves_subrows() -> None:
    rows = parse_html_table("<table><tr><td>甲<br>乙</td><td>1</td></tr></table>")
    assert rows[0][0].text == "甲\n乙"
    assert rows_to_markdown(rows) == ["| 甲<br>乙 | 1 |"]


def test_repeated_table_header_is_removed() -> None:
    header = "| 序号 | 名称 | 限值 |"
    lines = [header, "| 1 | 苯 | 6 |", header, "| 2 | 甲苯 | 50 |"]
    assert remove_repeated_table_headers(lines) == [
        header,
        "| 1 | 苯 | 6 |",
        "| 2 | 甲苯 | 50 |",
    ]


def test_known_ocr_header_is_corrected() -> None:
    cleaned, _ = clean_text("表 A.1\n警 SECEmg/m")
    assert "警报值 mg/m³" in cleaned
    assert "警 SECEmg/m" not in cleaned


def test_generic_conclusion_is_not_masked() -> None:
    assert detect_spans("结论：应当定期检测。") == []
    assert detect_spans("体检结论：合格") != []


def test_parent_chunk_page_span_is_bounded() -> None:
    pages = [ChunkInput(index, f"第{index}页内容。", "text_layer") for index in range(1, 8)]
    chunks = split_pages(
        pages,
        target=500,
        max_tokens=800,
        overlap=0,
        mode="parent_child",
        parent_target=500,
        parent_max_tokens=800,
        child_target=80,
        child_max_tokens=120,
        child_overlap=0,
    )
    parents = [chunk for chunk in chunks if chunk["chunk_role"] == "parent"]
    assert len(parents) >= 3
    assert all(chunk["page_end"] - chunk["page_start"] + 1 <= 3 for chunk in parents)


def test_known_merged_subrows_are_repaired() -> None:
    rows = [[TableCell("224"), TableCell("铅及其无机化合物铅尘铅烟"), TableCell("0.050.03")]]
    expanded = expand_rows(rows)
    assert len(expanded) == 2
    assert expanded[0][1] == "铅尘"
    assert expanded[0][2] == "0.05"
    assert expanded[1][1] == "铅烟"
    assert expanded[1][2] == "0.03"