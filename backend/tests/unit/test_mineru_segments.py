from pathlib import Path

from occupational_health.services.extraction.mineru import MineruAdapter


class _Settings:
    mineru_kit_path = Path(".mineru/Scripts/mineru-kit.exe")
    mineru_tier = "basic"
    mineru_model_source = "modelscope"
    mineru_segment_pages = 10
    mineru_segment_cache_enabled = False
    storage_root = Path("var/data")


def _adapter(tmp_path: Path) -> tuple[MineruAdapter, Path]:
    adapter = MineruAdapter(_Settings())
    adapter.available = lambda: True  # type: ignore[method-assign]
    pdf = tmp_path / "dummy.pdf"
    pdf.write_bytes(b"not-a-real-pdf")
    return adapter, pdf


def _fake_segments(calls, count):
    def fake_segment(_path, _namespace, page_range, _heartbeat):
        calls.append(page_range)
        start = page_range[0] if page_range else 1
        end = page_range[1] if page_range else count
        return {
            "extensions": {"mineru": {"parse_mode": "ocr"}},
            "pages": [{"page_idx": n, "blocks": []} for n in range(start - 1, end)],
        }

    return fake_segment


def test_segment_ranges_cover_all_pages(tmp_path: Path) -> None:
    adapter, pdf = _adapter(tmp_path)
    calls: list[tuple[int, int] | None] = []
    adapter._parse_segment = _fake_segments(calls, 23)  # type: ignore[method-assign]
    pages = adapter.parse(pdf, "ns", total_pages=23)
    assert calls == [(1, 10), (11, 20), (21, 23)]
    assert sorted(pages) == list(range(1, 24))


def test_small_document_uses_single_call(tmp_path: Path) -> None:
    adapter, pdf = _adapter(tmp_path)
    calls: list[tuple[int, int] | None] = []
    adapter._parse_segment = _fake_segments(calls, 6)  # type: ignore[method-assign]
    pages = adapter.parse(pdf, "ns", total_pages=6)
    assert calls == [None]
    assert len(pages) == 6


def test_progress_reaches_completion_across_segments(tmp_path: Path) -> None:
    adapter, pdf = _adapter(tmp_path)
    seen: list[float] = []

    def fake_segment(_path, _namespace, page_range, _heartbeat):
        return {"extensions": {}, "pages": [{"page_idx": 0, "blocks": []}]}

    adapter._parse_segment = fake_segment  # type: ignore[method-assign]
    adapter.parse(pdf, "ns", on_heartbeat=seen.append, total_pages=25)
    assert seen[-1] == 1.0
    assert seen == sorted(seen)


def test_cache_disabled_returns_none(tmp_path: Path) -> None:
    adapter, pdf = _adapter(tmp_path)
    assert adapter._cache_file(pdf, (1, 10)) is None
