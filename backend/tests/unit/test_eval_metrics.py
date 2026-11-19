from occupational_health.eval.custom_metrics import contains_fact, evaluate_custom
from occupational_health.eval.dataset import EvalCase, GoldDocument
from occupational_health.eval.retrieve import RetrievedContext


def test_contains_fact_normalizes_units() -> None:
    assert contains_fact("苯 PC-TWA 6 mg/m3", "6 mg/m³")
    assert not contains_fact("苯 PC-TWA 6 mg/m3", "10 mg/m³")


def test_custom_metrics_for_exact_limit() -> None:
    case = EvalCase(
        id="limit",
        query="苯的 PC-TWA 是多少？",
        query_type="exact_limit",
        required_facts=["苯", "PC-TWA", "6 mg/m³"],
        gold_documents=[
            GoldDocument(
                title="GBZ2.1规范.pdf", standard_no="GBZ 2.1-2019", page=22
            )
        ],
        expected_lifecycle=["current"],
    )
    contexts = [
        RetrievedContext(
            text="苯 PC-TWA 6 mg/m³",
            metadata={
                "standard_no": "GBZ 2.1-2019",
                "page_start": 21,
                "page_end": 22,
                "lifecycle_status": "current",
                "document_role": "main",
            },
        )
    ]
    metrics = evaluate_custom(case, contexts, "苯的 PC-TWA 为 6 mg/m³。")
    assert metrics["required_fact_coverage"] == 1.0
    assert metrics["numeric_exact_match"] == 1.0
    assert metrics["standard_no_match"] == 1.0
    assert metrics["citation_page_accuracy"] == 1.0
    assert metrics["lifecycle_valid"] == 1.0


def test_lifecycle_metric_rejects_replaced_document() -> None:
    case = EvalCase(id="old", query="旧标准？")
    contexts = [
        RetrievedContext(
            text="旧内容",
            metadata={
                "lifecycle_status": "replaced",
                "page_start": 1,
                "page_end": 1,
            },
        )
    ]
    metrics = evaluate_custom(case, contexts, "答案")
    assert metrics["lifecycle_valid"] == 0.0


def test_abstention_metric() -> None:
    case = EvalCase(id="none", query="火星限值？", expect_no_answer=True)
    metrics = evaluate_custom(case, [], "未在知识库中找到相关信息。")
    assert metrics["abstention_accuracy"] == 1.0
