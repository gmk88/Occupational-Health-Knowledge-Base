from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class Embedder:
    def __init__(
        self,
        model_id: str,
        revision: str,
        model_root: Path,
        query_instruction: str,
        batch_size: int = 32,
        device_preference: str = "auto",
        fp16: bool = True,
    ) -> None:
        self.model_id = model_id
        self.revision = revision
        self.model_root = model_root
        self.query_instruction = query_instruction
        self.batch_size = batch_size
        self.device_preference = device_preference
        self.fp16 = fp16
        self._model: Any | None = None
        self.device = "cpu"
        self.fp16_enabled = False

    def load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("sentence-transformers is not installed") from exc

        self.device = self._resolve_device()
        if self.device == "cuda":
            import torch

            torch.backends.cuda.matmul.allow_tf32 = True
        local = self.model_root / self.model_id.split("/")[-1]
        self._model = SentenceTransformer(
            str(local) if local.is_dir() else self.model_id,
            revision=None if local.is_dir() else self.revision,
            local_files_only=True,
            device=self.device,
        )
        self.fp16_enabled = False
        if self.device == "cuda" and self.fp16:
            # Half precision roughly halves GPU memory and speeds inference.
            try:
                self._model = self._model.half()
                self.fp16_enabled = True
            except Exception:
                pass

    def encode(self, texts: list[str], query: bool = False) -> list[list[float]]:
        self.load()
        prompt = self.query_instruction if query else None
        batch_size = self.batch_size
        while True:
            try:
                vectors = self._model.encode(
                    texts,
                    batch_size=batch_size,
                    normalize_embeddings=True,
                    prompt=prompt,
                )
                return [vector.tolist() for vector in vectors]
            except RuntimeError as exc:
                # 6GB 显卡上显存不足可能表现为 OOM，也可能是 CUDA 缓存分配器
                # 的内部断言；两种都清缓存并减半批次，直到批次为 1 仍失败。
                message = str(exc).lower()
                memory_failure = (
                    "out of memory" in message
                    or "cudacachingallocator" in message
                    or "internal assert failed" in message
                )
                if self.device != "cuda" or not memory_failure or batch_size <= 1:
                    raise
                import torch

                torch.cuda.empty_cache()
                batch_size = max(1, batch_size // 2)

    @property
    def dimensions(self) -> int:
        return 1024

    @property
    def device_info(self) -> dict:
        info: dict[str, Any] = {
            "device": self.device,
            "fp16": self.fp16_enabled,
            "torch": None,
            "cuda_available": False,
            "cuda_version": None,
            "gpu": None,
        }
        try:
            import torch
        except Exception:
            return info
        info["torch"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        info["cuda_version"] = torch.version.cuda
        if info["cuda_available"]:
            info["gpu"] = torch.cuda.get_device_name(0)
        return info

    def _resolve_device(self) -> str:
        """Pick the inference device; ``cuda`` mode fails loudly when unavailable."""
        try:
            import torch
        except Exception as exc:
            if self.device_preference == "cuda":
                raise RuntimeError("未安装 torch，无法使用 GPU 向量化") from exc
            return "cpu"
        available = torch.cuda.is_available()
        if self.device_preference == "cuda":
            if not available:
                raise RuntimeError(
                    "OH_EMBEDDING_DEVICE=cuda 但当前 torch 未启用 CUDA，"
                    "请安装 CUDA 版 torch 或改用 OH_EMBEDDING_DEVICE=cpu"
                )
            return "cuda"
        if self.device_preference == "cpu" or not available:
            self._pin_cpu_threads(torch)
            return "cpu"
        return "cuda"

    @staticmethod
    def _pin_cpu_threads(torch_module: Any) -> None:
        threads = os.environ.get("EMBEDDING_CPU_THREADS", "4")
        torch_module.set_num_threads(int(threads))
        os.environ.setdefault("OMP_NUM_THREADS", threads)
        os.environ.setdefault("MKL_NUM_THREADS", threads)
