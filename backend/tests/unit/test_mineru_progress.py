from occupational_health.services.extraction.mineru import (
    _block_text,
    _estimate_progress,
)


def test_empty_log_has_no_progress() -> None:
    assert _estimate_progress("") == 0.0
    assert _estimate_progress("loading models...\nno tqdm here") == 0.0


def test_progress_advances_with_model_stages() -> None:
    first = "\r".join(
        [
            "OCR-det: 100%|██████████| 28/28 [00:00<00:00, 50.37it/s]",
            "OCR-rec Predict:  50%|████      | 20/40 [00:01<00:01, 12.00it/s]",
        ]
    )
    second = first + "\r" + (
        "OCR-rec Predict: 100%|██████████| 40/40 [00:02<00:00, 12.00it/s]\r"
        "MFR Predict:  25%|██        | 57/229 [00:04<00:12, 15.00it/s]"
    )
    first_ratio = _estimate_progress(first)
    second_ratio = _estimate_progress(second)
    assert 0.0 < first_ratio < 0.9
    assert second_ratio > first_ratio
    assert second_ratio <= 0.9


def test_progress_is_capped_below_completion() -> None:
    log = "\r".join(
        f"Stage{i} Predict: 100%|██████████| 10/10 [00:00<00:00, 10.00it/s]"
        for i in range(12)
    )
    assert _estimate_progress(log) <= 0.9


def test_equation_block_keeps_latex_on_one_line() -> None:
    block = {
        "type": "equation",
        "content": r"L_{\mathrm{P}}=L_{\mathrm{w}}+10 \cdot \lg \left(\frac{Q}{4 \pi r^{2}}\right)\tag{5.2.2-1}",
    }
    result = _block_text(block)
    assert "\n" not in result
    assert result.startswith("$$")
    assert result.endswith("$$")
    assert r"\frac{Q}{4 \pi r^{2}}" in result


def test_inline_equation_stays_inside_sentence() -> None:
    block = {
        "type": "text",
        "content": [
            {"type": "text", "content": "式中的 "},
            {"type": "equation_inline", "content": r"S_{\mathrm{G}i}"},
            {"type": "text", "content": " 为某一车间的面积。"},
        ],
    }
    result = _block_text(block)
    assert "\n" not in result
    assert result == r"式中的 $S_{\mathrm{G}i}$ 为某一车间的面积。"