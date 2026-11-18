import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from occupational_health.services.embedding.model import Embedder


def _embedder(preference: str) -> Embedder:
    return Embedder("Qwen/Qwen3-Embedding-0.6B", "master", Path("var/models"), "query", device_preference=preference)


def _fake_torch(monkeypatch: pytest.MonkeyPatch, available: bool) -> None:
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            cuda=SimpleNamespace(
                is_available=lambda: available,
                get_device_name=lambda index: "RTX 3060",
            ),
            version=SimpleNamespace(cuda="12.6"),
            __version__="2.14.1+cu126",
            set_num_threads=lambda count: None,
            backends=SimpleNamespace(cuda=SimpleNamespace(matmul=SimpleNamespace())),
        ),
    )


def test_auto_prefers_cuda_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_torch(monkeypatch, True)
    assert _embedder("auto")._resolve_device() == "cuda"


def test_auto_falls_back_to_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_torch(monkeypatch, False)
    assert _embedder("auto")._resolve_device() == "cpu"


def test_cpu_override_ignores_available_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_torch(monkeypatch, True)
    assert _embedder("cpu")._resolve_device() == "cpu"


def test_forced_cuda_fails_loudly_without_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_torch(monkeypatch, False)
    with pytest.raises(RuntimeError, match="未启用 CUDA"):
        _embedder("cuda")._resolve_device()
