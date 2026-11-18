from occupational_health.mcp.server import (
    _resolve_detail,
    _table_window_markdown,
    _query_terms,
)


def test_detail_auto_uses_brief_for_lookup() -> None:
    detail = _resolve_detail("auto", "苯的 PC-TWA 是多少？")
    assert detail["effective"] == "brief"
    assert detail["reason"] == "default"


def test_detail_auto_uses_full_for_writing() -> None:
    detail = _resolve_detail("auto", "请根据表格写一份完整的分析报告")
    assert detail["effective"] == "full"
    assert detail["reason"] == "query_intent"


def test_detail_explicit_wins() -> None:
    detail = _resolve_detail("brief", "完整列出全部条款")
    assert detail["effective"] == "brief"
    assert detail["reason"] == "explicit"


def test_query_terms_skip_generic_words() -> None:
    terms = _query_terms("请查询知识库中苯的 PC-TWA 是多少")
    assert "苯" in terms
    assert "pc-twa" in terms
    assert "查询" not in terms


def test_table_window_shows_header_and_matched_rows() -> None:
    headers = [
        {"text": name, "rowspan": 1, "colspan": 1}
        for name in ("物质", "PC-TWA", "PC-STEL")
    ]
    rows = [headers]
    for name, twa, stel in (
        ("苯", "6", "10"),
        ("甲苯", "50", "100"),
        ("二甲苯", "50", "100"),
        ("乙苯", "100", "150"),
        ("苯乙烯", "50", "100"),
    ):
        rows.append(
            [
                {"text": name, "rowspan": 1, "colspan": 1},
                {"text": twa, "rowspan": 1, "colspan": 1},
                {"text": stel, "rowspan": 1, "colspan": 1},
            ]
        )
    table = {
        "caption": "工作场所有害因素职业接触限值",
        "rows": rows,
        "row_range": [1, 5],
        "row_count": 6,
        "column_count": 3,
    }
    markdown, preview = _table_window_markdown(table, "苯")
    assert "| 表头 | 物质 | PC-TWA | PC-STEL |" in markdown
    assert "| 1 | 苯 | 6 | 10 |" in markdown
    assert "完整表格请调用 get_chunk" in markdown
    assert preview["row_window"] is True
    assert 1 in preview["matched_rows"]
