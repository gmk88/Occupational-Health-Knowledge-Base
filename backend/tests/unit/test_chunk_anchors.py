from occupational_health.services.retrieval.anchors import _match_offsets


def test_exact_anchor_offsets() -> None:
    page = "前文。\n\n苯的 PC-TWA 为 6 mg/m³。\n\n后文。"
    quote = "苯的 PC-TWA 为 6 mg/m³"
    match = _match_offsets(quote, page)
    assert match is not None
    start, end, text, confidence, method = match
    assert page[start:end] == quote
    assert text == quote
    assert confidence == 1.0
    assert method == "exact"


def test_normalized_anchor_offsets() -> None:
    page = "苯的ＰＣ－ＴＷＡ为６mg/m³。"
    quote = "苯的PC-TWA为6mg/m3"
    match = _match_offsets(quote, page)
    assert match is not None
    start, end, text, confidence, method = match
    assert "苯的" in text
    assert confidence == 0.95
    assert method == "normalized_exact"


def test_no_anchor_for_unrelated_text() -> None:
    assert _match_offsets("噪声接触限值", "苯的 PC-TWA 为 6 mg/m³。") is None
