from __future__ import annotations

from occupational_health.services.documents.locating import locate_chunk


def test_exact_chunk_match_returns_source_offsets() -> None:
    page = "第一章 总则\n噪声作业劳动者应当佩戴护耳器并定期体检。\n第二章 附则"
    chunk = "噪声作业劳动者应当佩戴护耳器并定期体检。"

    spans = locate_chunk(page, chunk)

    assert len(spans) == 1
    assert spans[0]["type"] == "chunk"
    assert page[spans[0]["start_offset"] : spans[0]["end_offset"]] == chunk


def test_whitespace_differences_still_locate_chunk() -> None:
    page = "接触限值采用时间加权平均容许浓度（PC-TWA）。\n后文"
    chunk = "接触限值采用 时间加权平均容许浓度（PC-TWA）。"

    spans = locate_chunk(page, chunk)

    assert len(spans) == 1
    assert "时间加权平均容许浓度" in page[
        spans[0]["start_offset"] : spans[0]["end_offset"]
    ]


def test_cross_page_chunk_highlights_only_the_current_page_part() -> None:
    page = "甲页开头\n苯系物接触限值见附表 1 的具体规定。\n甲页结尾"
    chunk = "上一页内容\n苯系物接触限值见附表 1 的具体规定。\n下一页内容"

    spans = locate_chunk(page, chunk)

    assert len(spans) == 1
    highlighted = page[spans[0]["start_offset"] : spans[0]["end_offset"]]
    assert "苯系物接触限值" in highlighted
    assert "甲页开头" not in highlighted
    assert "甲页结尾" not in highlighted


def test_markdown_table_rows_are_matched_without_pipe_differences() -> None:
    page = (
        "表 1 职业接触限值\n"
        "| 物质 | PC-TWA | PC-STEL |\n"
        "| --- | --- | --- |\n"
        "| 苯 | 6 | 10 |\n"
    )
    chunk = "| 物质 | PC-TWA | PC-STEL |\n| 苯 | 6 | 10 |"

    spans = locate_chunk(page, chunk)

    assert spans
    highlighted = page[spans[0]["start_offset"] : spans[0]["end_offset"]]
    assert "物质" in highlighted


def test_unrelated_or_tiny_chunk_returns_no_spans() -> None:
    page = "职业健康监护档案应当长期保存并定期复核。"
    assert locate_chunk(page, "完全不相关的另一份文件内容") == []
    assert locate_chunk(page, "苯") == []
    assert locate_chunk("", "职业健康监护档案应当长期保存") == []


def test_offsets_use_unicode_code_points() -> None:
    page = "😀 职业健康监护档案应当长期保存"
    chunk = "职业健康监护档案应当长期保存"

    spans = locate_chunk(page, chunk)

    assert len(spans) == 1
    assert spans[0]["start_offset"] == 2
    assert page[spans[0]["start_offset"] : spans[0]["end_offset"]] == chunk
