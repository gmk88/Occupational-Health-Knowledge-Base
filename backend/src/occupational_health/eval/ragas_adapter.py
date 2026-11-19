from __future__ import annotations

from typing import Any

from occupational_health.eval.config import EvalConfig

_METRIC_ALIASES = {
    "context_precision": "context_precision",
    "context_recall": "context_recall",
    "faithfulness": "faithfulness",
    "answer_relevancy": "answer_relevancy",
    "answer_correctness": "answer_correctness",
}


def ragas_available() -> bool:
    try:
        import ragas  # noqa: F401
        from datasets import Dataset  # noqa: F401
    except ImportError:
        return False
    return True


def _metric_objects(names: list[str]) -> list[Any]:
    from ragas import metrics as ragas_metrics

    selected: list[Any] = []
    for name in names:
        canonical = _METRIC_ALIASES.get(name)
        if not canonical:
            continue
        metric = getattr(ragas_metrics, canonical, None)
        if metric is not None:
            selected.append(metric)
    return selected


def run_ragas(rows: list[dict[str, Any]], config: EvalConfig) -> dict[str, Any]:
    """Run RAGAS when an LLM judge is configured.

    The function degrades gracefully: missing dependencies, missing API keys,
    or provider errors are reported instead of aborting the evaluation run.
    """
    if not config.enable_llm:
        return {"status": "disabled", "reason": "llm judge disabled"}
    if not config.llm_api_key:
        return {"status": "error", "error": "OH_EVAL_LLM_API_KEY is not configured"}
    if not ragas_available():
        return {
            "status": "error",
            "error": "ragas/datasets not installed; pip install -e '.[eval]'",
        }

    try:
        from datasets import Dataset
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from ragas import evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
    except ImportError as exc:
        return {"status": "error", "error": f"missing optional dependency: {exc}"}

    metric_objects = _metric_objects(config.judge_metrics)
    if not metric_objects:
        return {"status": "error", "error": "no supported RAGAS metrics selected"}

    dataset = Dataset.from_dict(
        {
            "question": [row["question"] for row in rows],
            "contexts": [row["contexts"] for row in rows],
            "answer": [row["answer"] for row in rows],
            "ground_truth": [row["ground_truth"] for row in rows],
        }
    )

    try:
        chat = ChatOpenAI(
            base_url=config.llm_url,
            api_key=config.llm_api_key,
            model=config.llm_model,
            temperature=config.temperature,
        )
        embeddings = OpenAIEmbeddings(
            base_url=config.llm_url,
            api_key=config.llm_api_key,
            model=config.embedding_model,
        )
        result = evaluate(
            dataset,
            metrics=metric_objects,
            llm=LangchainLLMWrapper(chat),
            embeddings=LangchainEmbeddingsWrapper(embeddings),
        )
        scores: dict[str, float] = {}
        for key, value in dict(result).items():
            if isinstance(value, (int, float)):
                scores[str(key)] = round(float(value), 4)
        return {
            "status": "ok",
            "scores": scores,
            "model": config.llm_model,
            "embedding_model": config.embedding_model,
        }
    except Exception as exc:  # noqa: BLE001 - report provider/runtime failures
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
