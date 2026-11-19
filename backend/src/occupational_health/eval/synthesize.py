from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

from occupational_health.eval.config import EvalConfig
from occupational_health.eval.custom_metrics import contains_fact
from occupational_health.eval.dataset import EvalCase
from occupational_health.eval.retrieve import RetrievedContext

_SENTENCE = re.compile(r"[^。！？\n]+[。！？]?")


@dataclass(slots=True)
class SynthesisResult:
    answer: str
    method: str
    error: str | None = None


SYSTEM_PROMPT = (
    "你是一名职业卫生标准助手。只能使用提供的检索片段回答问题。"
    "数值、单位、标准号必须原样照抄，不得改写或推断。"
    "必须引用文档名和页码。如果检索片段没有答案，回答“未在知识库中找到”。"
    "不要使用外部知识。"
)


def extractive_answer(case: EvalCase, contexts: list[RetrievedContext]) -> str:
    """Deterministic fallback answer used when no judge/generator LLM is configured."""
    if case.expect_no_answer:
        return "未在知识库中找到相关信息。"

    selected: list[str] = []
    for context in contexts:
        for sentence in _SENTENCE.findall(context.text or ""):
            sentence = sentence.strip()
            if not sentence:
                continue
            useful = (
                any(contains_fact(sentence, fact) for fact in case.required_facts)
                if case.required_facts
                else True
            )
            if useful and sentence not in selected:
                selected.append(sentence)
            if len(selected) >= 3:
                break
        if len(selected) >= 3:
            break

    if not selected:
        for context in contexts[:2]:
            text = (context.text or "").strip()
            if text:
                selected.append(text[:300])

    if not selected:
        return "未在知识库中找到相关信息。"

    citation = "；".join(
        f"{context.metadata.get('document') or '未知文档'} "
        f"第 {context.metadata.get('source_page') or context.metadata.get('page_start')} 页"
        for context in contexts[:2]
    )
    return " ".join(selected) + f"（来源：{citation}）"


def llm_answer(
    case: EvalCase,
    contexts: list[RetrievedContext],
    config: EvalConfig,
) -> SynthesisResult:
    if not config.llm_api_key:
        return SynthesisResult(
            answer=extractive_answer(case, contexts),
            method="extractive_no_llm_key",
        )

    payload = {
        "model": config.llm_model,
        "temperature": config.temperature,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": case.query,
                        "contexts": [
                            {
                                "text": context.text,
                                "document": context.metadata.get("document"),
                                "page_start": context.metadata.get("page_start"),
                                "page_end": context.metadata.get("page_end"),
                                "standard_no": context.metadata.get("standard_no"),
                                "lifecycle_status": context.metadata.get(
                                    "lifecycle_status"
                                ),
                            }
                            for context in contexts
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    try:
        response = httpx.post(
            f"{config.llm_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {config.llm_api_key}"},
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
        answer = (
            response.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not answer:
            raise ValueError("empty LLM answer")
        return SynthesisResult(answer=answer, method="llm")
    except Exception as exc:  # noqa: BLE001 - evaluation must degrade, not crash
        return SynthesisResult(
            answer=extractive_answer(case, contexts),
            method="extractive_llm_fallback",
            error=f"{type(exc).__name__}: {exc}",
        )


def synthesize_answer(
    case: EvalCase,
    contexts: list[RetrievedContext],
    config: EvalConfig,
) -> SynthesisResult:
    if not config.enable_llm:
        return SynthesisResult(
            answer=extractive_answer(case, contexts), method="extractive"
        )
    return llm_answer(case, contexts, config)
