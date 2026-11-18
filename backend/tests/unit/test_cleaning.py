from occupational_health.services.extraction.cleaning import clean_text


def test_clean_text_keeps_paragraph_breaks() -> None:
    raw = "第一段内容。\n续写同一段。\n\n第二段内容。"
    cleaned, _ = clean_text(raw)
    assert "\n\n" in cleaned
    paragraphs = cleaned.split("\n\n")
    assert len(paragraphs) == 2
    assert paragraphs[0].startswith("第一段")
    assert paragraphs[1].startswith("第二段")


def test_clean_text_drops_page_numbers_without_losing_paragraphs() -> None:
    raw = "上一段。\n\n12\n\n下一段。"
    cleaned, _ = clean_text(raw)
    assert "上一段" in cleaned
    assert "下一段" in cleaned
    assert "\n\n" in cleaned
    assert all(line.strip() != "12" for line in cleaned.splitlines())


def test_many_blank_lines_are_not_treated_as_repeated_headers() -> None:
    raw = "第一段。\n\n第二段。\n\n第三段。\n\n第四段。"
    cleaned, _ = clean_text(raw)
    # 空行出现 >= 3 次时曾被当成重复页眉页脚删掉，导致按结构切分失效。
    assert cleaned.count("\n\n") == 3
    assert "第一段" in cleaned and "第四段" in cleaned


def test_clean_text_strips_nul_bytes() -> None:
    raw = "第一段含\x00控制字符。\n\n第二段\x00内容。"
    cleaned, _ = clean_text(raw)
    assert "\x00" not in cleaned
    assert "第一段含控制字符" in cleaned
    assert cleaned.count("\n\n") == 1


def test_clean_text_keeps_table_rows() -> None:
    raw = "| 物质 | 限值 |\n| --- | --- |\n| 苯 | 6 |"
    cleaned, _ = clean_text(raw)
    assert "| 苯 | 6 |" in cleaned
