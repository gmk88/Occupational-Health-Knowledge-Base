from occupational_health.services.masking.rules import apply_spans, detect_spans
from occupational_health.services.masking.service import mask_text


def test_detect_and_mask_id_and_phone_and_name() -> None:
    text = "姓名：张三，身份证号110101199001011234，电话13800138000"
    masked, annotations, _ = mask_text(text)
    assert "张三" not in masked
    assert "110101199001011234" not in masked
    assert "13800138000" not in masked
    assert "[姓名]" in masked and "[身份证号]" in masked and "[联系方式]" in masked
    assert annotations[0]["start_offset"] < annotations[0]["end_offset"]


def test_overlapping_spans_are_deduplicated() -> None:
    text = "姓名：王五 13800138000"
    spans = detect_spans(text)
    positions = [(span.start, span.end) for span in spans]
    for index in range(1, len(positions)):
        assert positions[index][0] >= positions[index - 1][1]


def test_apply_spans_preserves_unmatched_text() -> None:
    text = "苯系物接触限值 PC-TWA"
    assert apply_spans(text, []) == text
