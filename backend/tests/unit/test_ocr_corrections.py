from occupational_health.services.extraction.cleaning import clean_text, correct_ocr_text
from occupational_health.services.masking.service import mask_text


def test_mask_text_is_disabled() -> None:
    text = "姓名：张三，身份证号110101199001011234，电话13800138000"
    masked, annotations, spans = mask_text(text)
    assert masked == text
    assert annotations == []
    assert spans == []


def test_known_replacement_characters_are_repaired() -> None:
    text = "\ufffd ——喷头雾化角，单位为度（°）。"
    assert correct_ocr_text(text) == "θ ——喷头雾化角，单位为度（°）。"


def test_average_symbol_is_repaired() -> None:
    text = "式中:\n\n\ufffd——平均值；\n\nN——测量数据的个数。"
    corrected = clean_text(text)[0]
    assert "\ufffd" not in corrected
    assert "$\\bar{X}$——平均值" in corrected
