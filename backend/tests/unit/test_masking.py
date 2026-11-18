from occupational_health.services.masking.rules import apply_spans, detect_spans
from occupational_health.services.masking.service import mask_text


def test_published_text_is_not_masked() -> None:
    text = "姓名：张三，身份证号110101199001011234，电话13800138000"
    masked, annotations, _ = mask_text(text)
    assert masked == text
    assert "张三" in masked
    assert "110101199001011234" in masked
    assert "13800138000" in masked
    assert annotations == []


def test_overlapping_spans_are_deduplicated() -> None:
    text = "姓名：王五 13800138000"
    spans = detect_spans(text)
    positions = [(span.start, span.end) for span in spans]
    for index in range(1, len(positions)):
        assert positions[index][0] >= positions[index - 1][1]


def test_apply_spans_preserves_unmatched_text() -> None:
    text = "苯系物接触限值 PC-TWA"
    assert apply_spans(text, []) == text
