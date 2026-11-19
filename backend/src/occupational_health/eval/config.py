from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(slots=True)
class EvalConfig:
    api_url: str = "http://127.0.0.1:8000/api/v1"
    username: str = "admin"
    password: str = "admin123"
    mode: str = "hybrid"
    top_k: int = 5
    golden_path: Path = Path("eval/golden/ragas_cases.sample.jsonl")
    output_dir: Path = Path("var/eval")

    enable_llm: bool = False
    llm_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    temperature: float = 0.0

    judge_metrics: list[str] = field(
        default_factory=lambda: [
            "context_precision",
            "context_recall",
            "faithfulness",
            "answer_relevancy",
        ]
    )

    @classmethod
    def from_env(cls) -> EvalConfig:
        return cls(
            api_url=_env("OH_EVAL_API_URL", "http://127.0.0.1:8000/api/v1"),
            username=_env("OH_EVAL_USERNAME", "admin"),
            password=_env("OH_EVAL_PASSWORD", "admin123"),
            mode=_env("OH_EVAL_MODE", "hybrid"),
            top_k=_env_int("OH_EVAL_TOP_K", 5),
            golden_path=Path(
                _env("OH_EVAL_GOLDEN", "eval/golden/ragas_cases.sample.jsonl")
            ),
            output_dir=Path(_env("OH_EVAL_OUTPUT_DIR", "var/eval")),
            enable_llm=_env_bool("OH_EVAL_ENABLE_LLM", False),
            llm_url=_env("OH_EVAL_LLM_URL", "https://api.openai.com/v1"),
            llm_api_key=_env("OH_EVAL_LLM_API_KEY", ""),
            llm_model=_env("OH_EVAL_LLM_MODEL", "gpt-4o-mini"),
            embedding_model=_env("OH_EVAL_EMBEDDING_MODEL", "text-embedding-3-small"),
        )

    def safe_dict(self) -> dict:
        return {
            "api_url": self.api_url,
            "mode": self.mode,
            "top_k": self.top_k,
            "golden_path": str(self.golden_path),
            "output_dir": str(self.output_dir),
            "enable_llm": self.enable_llm,
            "llm_url": self.llm_url,
            "llm_model": self.llm_model,
            "embedding_model": self.embedding_model,
            "temperature": self.temperature,
            "judge_metrics": self.judge_metrics,
            "llm_api_key_configured": bool(self.llm_api_key),
        }
