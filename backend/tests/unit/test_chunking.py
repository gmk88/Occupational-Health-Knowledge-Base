from occupational_health.services.chunking.service import (
    ChunkInput,
    approximate_token_count,
    split_pages,
)
from occupational_health.services.extraction.tables import TableSegment


def test_token_count_counts_cjk_and_ascii() -> None:
    assert approximate_token_count("苯") == 1
    assert approximate_token_count("PC-TWA") == 1
    assert approximate_token_count("苯系物 PC-TWA") == 4


def test_fixed_respects_max_tokens() -> None:
    pages = [ChunkInput(1, "长文本。" * 300, "text_layer")]
    chunks = split_pages(pages, target=100, max_tokens=200, overlap=20, mode="fixed")
    assert len(chunks) > 1
    assert all(chunk["token_count"] <= 200 for chunk in chunks)


def test_chunk_records_page_range() -> None:
    pages = [
        ChunkInput(1, "第一页内容。", "text_layer"),
        ChunkInput(2, "第二页内容。", "ocr"),
    ]
    chunks = split_pages(pages, target=50, max_tokens=200, overlap=0)
    assert chunks[0]["page_start"] == 1
    assert chunks[-1]["page_end"] == 2


def test_sentence_mode_is_one_sentence_per_chunk() -> None:
    pages = [ChunkInput(1, "第一句。第二句。第三句。", "text_layer")]
    chunks = split_pages(pages, target=10, max_tokens=20, overlap=0, mode="sentence")
    assert [chunk["text"] for chunk in chunks] == ["第一句。", "第二句。", "第三句。"]


def test_structure_mode_is_one_paragraph_per_chunk() -> None:
    text = "第一段内容较长。\n\n第二段内容。"
    pages = [ChunkInput(1, text, "text_layer")]
    chunks = split_pages(pages, target=100, max_tokens=200, overlap=0, mode="structure")
    assert [chunk["text"] for chunk in chunks] == ["第一段内容较长。", "第二段内容。"]


def test_fixed_mode_respects_target() -> None:
    pages = [ChunkInput(1, "固定大小切分测试文本" * 40, "text_layer")]
    chunks = split_pages(pages, target=20, max_tokens=40, overlap=0, mode="fixed")
    assert len(chunks) > 1
    assert all(chunk["token_count"] <= 40 for chunk in chunks)


def test_structure_keeps_long_paragraph_whole() -> None:
    # 一段一块：超长段落不再被硬切成定长窗口。
    long_text = "职业卫生技术服务机构应当依法独立开展活动。" * 80
    pages = [ChunkInput(1, long_text, "text_layer")]
    chunks = split_pages(pages, target=100, max_tokens=200, overlap=20, mode="structure")
    assert len(chunks) == 1
    assert chunks[0]["token_count"] > 200


def test_table_becomes_single_chunk() -> None:
    from occupational_health.services.extraction.cleaning import clean_text

    raw = (
        "接触限值说明\n\n"
        "| 物质 | PC-TWA | PC-STEL |\n"
        "| --- | --- | --- |\n"
        "| 苯 | 6 | 10 |\n"
        "| 甲苯 | 50 | 100 |\n\n"
        "以上为常用限值。"
    )
    cleaned, _ = clean_text(raw)
    chunks = split_pages(
        [ChunkInput(1, cleaned, "text_layer")],
        target=512,
        max_tokens=768,
        overlap=64,
        mode="fixed",
    )
    tables = [chunk for chunk in chunks if chunk["block_type"] == "table"]
    assert len(tables) == 1
    table = tables[0]
    assert "| 物质 |" in table["text"]
    assert "| 苯 | 6 | 10 |" in table["text"]
    assert table["table_header"] == "| 物质 | PC-TWA | PC-STEL |"
    assert table["table_html"] and "<table>" in table["table_html"]
    # 表格前的短正文并入表格块，表格后正文单独成块。
    assert chunks[0]["block_type"] == "table"
    assert chunks[-1]["block_type"] == "text"


def test_table_chunk_carries_identity_and_caption() -> None:
    from occupational_health.services.extraction.cleaning import clean_text

    raw = (
        "表 1 化学因素限值\n\n"
        "| 物质 | PC-TWA |\n"
        "| --- | --- |\n"
        "| 苯 | 6 |\n"
        "| 甲苯 | 50 |"
    )
    cleaned, _ = clean_text(raw)
    chunks = split_pages(
        [ChunkInput(1, cleaned, "text_layer")],
        target=512,
        max_tokens=768,
        overlap=0,
        mode="fixed",
        table_namespace="version-1",
    )
    tables = [chunk for chunk in chunks if chunk["block_type"] == "table"]
    assert len(tables) == 1
    table = tables[0]
    assert table["table_id"]
    assert table["section_title"] == "表 1 化学因素限值"
    assert table["page_start"] == 1 and table["page_end"] == 1
    assert "| 苯 | 6 |" in table["text"]


def test_fixed_respects_target_not_max_tokens() -> None:
    # 之前会把约 target 的块继续累加到 max_tokens，看起来像"上限大小切分"。
    text = "固定切分内容" * 100
    chunks = split_pages(
        [ChunkInput(1, text, "text_layer")],
        target=100,
        max_tokens=600,
        overlap=0,
        mode="fixed",
    )
    assert len(chunks) >= 5
    assert all(chunk["token_count"] <= 120 for chunk in chunks)


def test_structure_is_one_paragraph_per_chunk_regardless_of_target() -> None:
    paragraphs = ["段落甲内容" * 20, "段落乙内容" * 20, "段落丙内容" * 20]
    text = "\n\n".join(paragraphs)
    chunks = split_pages(
        [ChunkInput(1, text, "text_layer")],
        target=100,
        max_tokens=768,
        overlap=0,
        mode="structure",
    )
    assert [chunk["text"] for chunk in chunks] == paragraphs


def test_structure_and_sentence_ignore_target_and_max() -> None:
    long_text = "很长的段落内容" * 100
    pages = [ChunkInput(1, long_text, "text_layer")]
    structure = split_pages(pages, target=64, max_tokens=128, overlap=0, mode="structure")
    sentence = split_pages(pages, target=64, max_tokens=128, overlap=0, mode="sentence")
    fixed = split_pages(pages, target=64, max_tokens=128, overlap=0, mode="fixed")
    assert len(structure) == 1 and structure[0]["token_count"] > 128
    assert len(sentence) == 1 and sentence[0]["token_count"] > 128
    assert len(fixed) > 1 and all(c["token_count"] <= 128 for c in fixed)


def test_table_is_boundary_and_still_one_chunk() -> None:
    from occupational_health.services.extraction.cleaning import clean_text

    raw = "\n\n".join(
        [
            "前言说明工作场所化学有害因素的分类与适用范围。",
            "| 物质 | PC-TWA |\n| --- | --- |\n| 苯 | 6 |",
            "结论说明用人单位应当定期开展检测并保存记录。",
        ]
    )
    cleaned, _ = clean_text(raw)
    chunks = split_pages(
        [ChunkInput(1, cleaned, "text_layer")],
        target=100,
        max_tokens=768,
        overlap=0,
        mode="structure",
    )
    tables = [chunk for chunk in chunks if chunk["block_type"] == "table"]
    assert len(tables) == 1
    # 前置正文并入表格块，表格后的正文仍是独立正文块。
    assert chunks[0]["block_type"] == "table"
    assert "前言说明" in chunks[0]["text"]
    assert chunks[-1]["block_type"] == "text"


def test_chunks_strip_nul_and_hash_matches_cleaned_text() -> None:
    import hashlib

    text = "含\x00控制字符的正文内容。"
    chunks = split_pages(
        [ChunkInput(1, text, "text_layer")],
        target=100,
        max_tokens=200,
        overlap=0,
        mode="fixed",
    )
    assert len(chunks) == 1
    content = chunks[0]["text"]
    assert "\x00" not in content
    assert chunks[0]["content_hash"] == hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert chunks[0]["token_count"] == approximate_token_count(content)


def test_structure_overlap_repeats_previous_tail() -> None:
    text = "第一段内容。\n\n第二段内容。"
    chunks = split_pages(
        [ChunkInput(1, text, "text_layer")],
        target=100,
        max_tokens=200,
        overlap=2,
        mode="structure",
    )
    assert chunks[0]["text"] == "第一段内容。"
    assert chunks[1]["text"] == "内容。\n\n第二段内容。"
    assert chunks[1]["token_count"] == approximate_token_count(chunks[1]["text"])


def test_overlap_does_not_accumulate() -> None:
    text = "\n\n".join(["甲" * 5, "乙" * 5, "丙" * 5])
    chunks = split_pages(
        [ChunkInput(1, text, "text_layer")],
        target=100,
        max_tokens=200,
        overlap=3,
        mode="structure",
    )
    # 第三块只重复第二块尾部，不会把第一块的内容叠加进来。
    assert chunks[2]["text"] == "乙乙乙\n\n丙丙丙丙丙"


def test_overlap_resets_after_table() -> None:
    from occupational_health.services.extraction.cleaning import clean_text

    raw = "\n\n".join(
        [
            "前文内容说明。",
            "| 物质 | 限值 |\n| --- | --- |\n| 苯 | 6 |",
            "后文内容说明。",
        ]
    )
    cleaned, _ = clean_text(raw)
    chunks = split_pages(
        [ChunkInput(1, cleaned, "text_layer")],
        target=100,
        max_tokens=200,
        overlap=4,
        mode="structure",
    )
    table_index = next(
        index for index, chunk in enumerate(chunks) if chunk["block_type"] == "table"
    )
    after = chunks[table_index + 1]
    assert after["block_type"] == "text"
    # 清洗会把全角句号转成半角，这里只比较正文是否被重叠前缀污染。
    assert after["text"].startswith("后文内容说明")
    assert "前文内容说明" not in after["text"]


def test_prose_before_table_merges_into_table_chunk() -> None:
    from occupational_health.services.extraction.cleaning import clean_text

    raw = "\n\n".join(
        [
            "本表给出工作场所化学有害因素的职业接触限值。",
            "| 物质 | PC-TWA |\n| --- | --- |\n| 苯 | 6 |",
        ]
    )
    cleaned, _ = clean_text(raw)
    chunks = split_pages(
        [ChunkInput(1, cleaned, "text_layer")],
        target=100,
        max_tokens=200,
        overlap=0,
        mode="structure",
    )
    assert len(chunks) == 1
    table = chunks[0]
    assert table["block_type"] == "table"
    assert table["text"].startswith("本表给出")
    assert "| 苯 | 6 |" in table["text"]
    assert table["table_html"]
    assert table["table_header"] == "| 物质 | PC-TWA |"


def test_table_caption_is_not_duplicated_when_merged() -> None:
    from occupational_health.services.extraction.cleaning import clean_text

    raw = "表 1 化学因素限值\n\n| 物质 | PC-TWA |\n| --- | --- |\n| 苯 | 6 |"
    cleaned, _ = clean_text(raw)
    chunks = split_pages(
        [ChunkInput(1, cleaned, "text_layer")],
        target=100,
        max_tokens=200,
        overlap=0,
        mode="structure",
    )
    assert len(chunks) == 1
    assert chunks[0]["block_type"] == "table"
    assert chunks[0]["text"].count("表 1 化学因素限值") == 1


def test_invalid_mode_raises() -> None:
    import pytest

    from occupational_health.domain.enums import ChunkMode

    with pytest.raises(ValueError):
        split_pages([], target=10, max_tokens=20, overlap=0, mode="bogus")
    assert ChunkMode.STRUCTURE.value == "structure"


def test_parent_child_builds_semantic_parents_and_retrieval_children() -> None:
    text = "\n\n".join(
        [
            "苯的职业接触限值适用于工作场所空气检测。",
            "检测结果的判定应结合采样时间与接触限值。",
            "用人单位应定期开展职业病危害因素检测。",
        ]
    )
    chunks = split_pages(
        [ChunkInput(1, text, "text_layer")],
        target=80,
        max_tokens=120,
        overlap=0,
        mode="parent_child",
        parent_target=80,
        parent_max_tokens=120,
        child_target=30,
        child_max_tokens=40,
        child_overlap=4,
    )
    parents = [chunk for chunk in chunks if chunk["chunk_role"] == "parent"]
    children = [chunk for chunk in chunks if chunk["chunk_role"] == "child"]
    assert parents and children
    assert all(chunk["parent_ordinal"] == parents[0]["ordinal"] for chunk in children)
    assert all(chunk["token_count"] <= 40 for chunk in children)
    assert "苯" in "".join(chunk["text"] for chunk in children)


def test_parent_child_table_children_repeat_header_and_row_window() -> None:
    from occupational_health.services.extraction.cleaning import clean_text

    rows = "\n".join(
        [f"| 物质{i} | {i} | {i + 1} |" for i in range(1, 9)]
    )
    raw = "表 1 接触限值\n\n| 物质 | PC-TWA | PC-STEL |\n| --- | --- | --- |\n" + rows
    cleaned, _ = clean_text(raw)
    chunks = split_pages(
        [ChunkInput(1, cleaned, "text_layer")],
        target=120,
        max_tokens=200,
        overlap=0,
        mode="parent_child",
        parent_target=120,
        parent_max_tokens=200,
        child_target=28,
        child_max_tokens=40,
        child_overlap=0,
    )
    parents = [chunk for chunk in chunks if chunk["block_type"] == "table" and chunk["chunk_role"] == "parent"]
    children = [chunk for chunk in chunks if chunk["block_type"] == "table" and chunk["chunk_role"] == "child"]
    assert len(parents) == 1
    assert len(children) >= 2
    assert all("| 物质 | PC-TWA | PC-STEL |" in chunk["text"] for chunk in children)
    assert all(chunk["page_offsets"].get("row_end", 0) >= 1 for chunk in children)

def test_formula_segment_is_atomic_in_parent_child_mode() -> None:
    formula = r"$$L_{\mathrm{P}}=L_{\mathrm{w}}+10 \cdot \lg \left(\frac{Q}{4 \pi r^{2}}\right)\tag{5.2.2-1}$$"
    segments = {1: [TableSegment("formula", formula)]}
    chunks = split_pages(
        [ChunkInput(1, "", "text_layer")],
        target=80,
        max_tokens=120,
        overlap=0,
        mode="parent_child",
        page_segments=segments,
        parent_target=80,
        parent_max_tokens=120,
        child_target=40,
        child_max_tokens=60,
        child_overlap=0,
    )
    parents = [chunk for chunk in chunks if chunk["chunk_role"] == "parent"]
    children = [chunk for chunk in chunks if chunk["chunk_role"] == "child"]
    assert len(parents) == 1
    assert len(children) == 1
    assert parents[0]["block_type"] == "formula"
    assert children[0]["block_type"] == "formula"
    assert parents[0]["text"] == formula
    assert children[0]["text"] == formula