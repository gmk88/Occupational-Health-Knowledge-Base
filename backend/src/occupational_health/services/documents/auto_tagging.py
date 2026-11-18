"""Rule-based classification for occupational-health scenarios.

No LLM is involved. The primary category is the work scenario; document type,
hazard factor and process are stored as tags. Manual non-general categories are
never overwritten.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select

from occupational_health.db.models.content import Chunk
from occupational_health.db.models.documents import Document
from occupational_health.db.models.taxonomy import Category, DocumentTag, Tag
from occupational_health.db.session import SessionLocal
from occupational_health.domain.enums import ChunkRole, DocumentStatus

_LOGGER = logging.getLogger(__name__)

_STANDARD_NO = re.compile(
    r"(?:gbz|gb)\s*/?\s*t?\s*\d+(?:\.\d+)?", re.IGNORECASE
)

_SCENARIO_RULES: dict[str, tuple[str, ...]] = {
    "dust": (
        "粉尘", "尘肺", "矽尘", "煤尘", "石棉尘", "呼吸性粉尘",
        "游离二氧化硅", "砂尘", "水泥尘", "电焊烟尘",
    ),
    "chemical": (
        "苯", "甲苯", "二甲苯", "甲醛", "氨", "硫化氢", "氯气",
        "重金属", "有机溶剂", "化学毒物", "职业中毒", "化学品",
        "镉", "铅", "锰", "汞", "一氧化碳", "酸碱",
    ),
    "physical": (
        "噪声", "高温", "振动", "放射", "电离辐射", "非电离辐射",
        "微波", "紫外", "低温", "异常气压", "热辐射",
    ),
    "health_surveillance": (
        "职业健康监护", "职业健康检查", "上岗前", "在岗期间", "离岗时",
        "体检", "禁忌证", "健康监护档案",
    ),
    "assessment": (
        "检测报告", "评价报告", "检测与评价", "现状评价", "控制效果评价",
        "采样", "现场检测", "职业卫生技术服务", "暴露评估", "检测结果",
        "检测规范", "测定方法",
    ),
    "protection": (
        "个体防护", "防护用品", "呼吸防护", "听力防护", "护目镜",
        "防护服", "应急救援", "事故处置", "中毒事故", "警示标识",
    ),
}

_TYPE_RULES: dict[str, tuple[str, ...]] = {
    "类型:法规标准": (
        "标准", "规范", "规程", "技术要求", "控制规范", "卫生标准", "限值",
    ),
    "类型:检测评价": (
        "检测报告", "评价报告", "检测与评价", "现状评价", "控制效果评价",
        "检测结果", "检测数据", "测定方法",
    ),
    "类型:健康监护": (
        "职业健康监护", "健康监护", "职业健康检查", "上岗前", "在岗期间", "离岗时", "体检",
    ),
    "类型:化学品安全": (
        "sds", "msds", "安全数据表", "安全技术说明书", "化学品安全", "物质安全",
    ),
    "类型:培训材料": ("培训", "课件", "讲义", "宣教", "试题", "考核"),
}

_FACTOR_RULES: dict[str, tuple[str, ...]] = {
    "因素:粉尘": ("粉尘", "尘肺", "矽尘", "煤尘", "石棉尘", "呼吸性粉尘", "游离二氧化硅"),
    "因素:噪声": ("噪声", "听力", "声级"),
    "因素:高温": ("高温", "热辐射", "暑热"),
    "因素:振动": ("振动", "手传振动", "全身振动"),
    "因素:放射": ("放射", "电离辐射", "非电离辐射", "辐射"),
    "因素:化学毒物": ("化学毒物", "有机溶剂", "职业中毒", "苯", "甲醛", "重金属"),
    "因素:生物因素": ("生物因素", "病原微生物", "炭疽", "布鲁氏菌"),
}

_PROCESS_RULES: dict[str, tuple[str, ...]] = {
    "环节:检测": ("检测", "采样", "测定", "监测"),
    "环节:评价": ("评价", "评估"),
    "环节:破碎": ("破碎", "筛分", "粉碎"),
    "环节:装卸": ("装卸", "码头", "堆场", "仓储"),
    "环节:应急处置": ("应急", "救援", "事故处置"),
    "环节:个体防护": ("个体防护", "防护用品", "呼吸防护", "听力防护"),
}

# 标准号本身是强场景信号，避免仅靠标题把常见标准误判为通用。
_STANDARD_SCENARIOS: dict[str, str] = {
    "GBZ 1": "general",
    "GBZ 2.1": "chemical",
    "GB 2.1": "chemical",
    "GBZ 2.2": "physical",
    "GBZ 158": "general",
    "GBZ 188": "health_surveillance",
    "GBZ 194": "chemical",
    "GBZ 197": "assessment",
    "GBZ 196": "assessment",
    "GBZ 223": "chemical",
    "GBZ 225": "general",
    "GBZ 277": "assessment",
    "GBZ 331": "assessment",
    "GBZ 340": "dust",
    "GB 18664": "protection",
    "GB 23466": "protection",
    "GB 2626": "protection",
    "GB 39800": "protection",
    "GB 5083": "general",
    "GB 50187": "general",
    "GB 50073": "general",
    "GB/T 50034": "physical",
    "GB/T 50087": "physical",
    "GB/T 50033": "physical",
    "MT/T 1188": "dust",
    "MT/T 1189": "dust",
    "MT/T 1020": "dust",
    "AQ 1020": "dust",
    "AQ 1051": "protection",
    "WS/T 754": "physical",
    "WS/T 882": "assessment",
    "WS 706": "dust",
}

_TITLE_WEIGHT = 3
_BODY_WEIGHT = 1
_MAX_TEXT_CHARS = 20_000


def _normalize_standard_key(value: str) -> str:
    compact = re.sub(r"[\s/+]", "", value).upper().replace("—", "-").replace("–", "-")
    compact = re.sub(r"^\d+_", "", compact)
    compact = compact.replace("GBZT", "GBZ").replace("GBT", "GB")
    compact = compact.replace("MTT", "MT").replace("WST", "WS")
    compact = re.sub(r"[-_]?(?:19|20)\d{2}.*$", "", compact)
    return compact


def _standard_scenario(text: str) -> str | None:
    # 长号优先，避免 GBZ 188 被 GBZ 1 的前缀误命中。
    candidates = sorted(
        _STANDARD_SCENARIOS.items(),
        key=lambda item: len(_normalize_standard_key(item[0])),
        reverse=True,
    )
    for standard, scenario in candidates:
        if _normalize_standard_key(standard) in text:
            return scenario
    return None


def _scenario_scores(title_l: str, body_l: str) -> dict[str, float]:
    scores: dict[str, float] = {}
    for code, keywords in _SCENARIO_RULES.items():
        score = 0.0
        for keyword in keywords:
            if keyword.lower() in title_l:
                score += _TITLE_WEIGHT
            elif keyword.lower() in body_l:
                score += _BODY_WEIGHT
        if score:
            scores[code] = score
    return scores


def _tag_hits(text_l: str, rules: dict[str, tuple[str, ...]]) -> list[str]:
    return [
        tag
        for tag, keywords in rules.items()
        if any(keyword.lower() in text_l for keyword in keywords)
    ]


def classify(title: str, text: str) -> dict:
    """Return a primary occupational-health scenario and suggested tags."""
    title_l = (title or "").lower()
    body_l = (text or "")[:_MAX_TEXT_CHARS].lower()
    combined = f"{title_l}\n{body_l}"

    scores = _scenario_scores(title_l, body_l)
    standard_scenario = _standard_scenario(_normalize_standard_key(combined))
    if standard_scenario:
        scores[standard_scenario] = scores.get(standard_scenario, 0.0) + 10
    if scores:
        code, best = max(scores.items(), key=lambda item: item[1])
        total = sum(scores.values())
        confidence = round(best / total, 3) if total else 0.0
    else:
        code, best, confidence = "general", 0.0, 0.0

    tags: set[str] = set(_tag_hits(combined, _TYPE_RULES))
    if _STANDARD_NO.search(combined):
        tags.add("类型:法规标准")
    if not tags:
        tags.add("类型:其他资料")
    tags.update(_tag_hits(combined, _FACTOR_RULES))
    tags.update(_tag_hits(combined, _PROCESS_RULES))

    return {
        "code": code,
        "confidence": confidence,
        "score": round(best, 1),
        "tags": sorted(tags),
    }


def _link_tags(db, document: Document, names: list[str]) -> int:
    linked = 0
    for name in names:
        normalized = name.strip().casefold()
        tag = db.scalar(select(Tag).where(Tag.normalized_name == normalized))
        if not tag:
            tag = Tag(name=name.strip(), normalized_name=normalized)
            db.add(tag)
            db.flush()
        exists = db.scalar(
            select(DocumentTag).where(
                DocumentTag.document_id == document.id,
                DocumentTag.tag_id == tag.id,
            )
        )
        if not exists:
            db.add(DocumentTag(document_id=document.id, tag_id=tag.id))
            linked += 1
    return linked


def classify_document(db, document: Document, texts: list[str], settings) -> dict:
    """Apply scenario category and suggested tags; manual category is preserved."""
    if not settings.auto_tagging_enabled:
        return {}

    title = document.title or ""
    body = "\n".join(text for text in texts if text)
    suggestion = classify(title, body)

    current = db.get(Category, document.category_id) if document.category_id else None
    category_updated = False
    if (
        suggestion["code"]
        and (current is None or current.code in {"general", "other"})
        and suggestion["confidence"] >= settings.auto_tagging_min_confidence
    ):
        target = db.scalar(
            select(Category).where(
                Category.code == suggestion["code"], Category.active.is_(True)
            )
        )
        if target and document.category_id != target.id:
            document.category_id = target.id
            category_updated = True

    tags_linked = _link_tags(db, document, suggestion["tags"])
    return {**suggestion, "category_updated": category_updated, "tags_linked": tags_linked}


def apply_auto_classification(
    db, document: Document, texts: list[str], settings
) -> dict:
    """Classify a freshly parsed document and link suggested tags."""
    result = classify_document(db, document, texts, settings)
    if not result:
        return {}
    if result.get("category_updated"):
        _LOGGER.info(
            "auto-classified document %s: scenario:%s",
            document.id,
            result["code"],
        )
    return {
        "category": result["code"],
        "confidence": result["confidence"],
        "category_updated": result["category_updated"],
        "tags_linked": result["tags_linked"],
    }


def backfill_documents(settings) -> dict:
    """Apply scenario classification to already-indexed documents."""
    if not settings.auto_tagging_enabled:
        return {
            "documents": 0,
            "category_updated": 0,
            "tags_linked": 0,
            "skipped": True,
        }

    total = updated = linked = 0
    with SessionLocal() as db:
        documents = list(
            db.scalars(
                select(Document).where(
                    Document.status != DocumentStatus.DELETED,
                    Document.current_version_id.is_not(None),
                )
            )
        )
        for document in documents:
            chunks = list(
                db.scalars(
                    select(Chunk)
                    .where(
                        Chunk.version_id == document.current_version_id,
                        Chunk.index_visible.is_(True),
                        Chunk.chunk_role != ChunkRole.CHILD.value,
                    )
                    .order_by(Chunk.ordinal)
                    .limit(50)
                )
            )
            if not chunks:
                continue
            total += 1
            result = apply_auto_classification(
                db, document, [chunk.raw_text for chunk in chunks], settings
            )
            updated += int(result.get("category_updated", False))
            linked += int(result.get("tags_linked", 0))
        db.commit()
    return {
        "documents": total,
        "category_updated": updated,
        "tags_linked": linked,
    }
