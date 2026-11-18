"""MCP server that lets external agents search this knowledge base.

Design notes:
- The server never generates answers. It returns retrieved passages plus
  citations so the caller's own model can answer.
- Auth is pass-through: in HTTP mode the caller's own Bearer key is forwarded to
  the backend, so per-client limits and audit trails stay correct. In stdio mode
  a token is read from ``OH_API_TOKEN``.
- Results are shaped for LLM consumption: bounded text, tables as Markdown.
"""

from __future__ import annotations

import argparse
import os
import re
from typing import Any

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from occupational_health.services.documents.auto_tagging import classify as classify_query
from occupational_health.services.extraction.table_html import TableCell, expand_rows

API_BASE = os.environ.get("OH_API_BASE_URL", "http://127.0.0.1:8000/api/v1")
BRIEF_TEXT_CHARS = 600
FULL_TEXT_CHARS = 3000
MAX_TABLE_ROWS = 40
BRIEF_TABLE_ROWS = 12
BRIEF_TABLE_CONTEXT = 2
TIMEOUT_SECONDS = 30.0

_FULL_DETAIL_MARKERS = (
    "写报告", "写作", "撰写", "起草", "编制", "完整", "全文", "逐条", "全部",
    "所有", "详细", "分析", "对比", "列举", "列出", "摘录", "引用条款",
    "整表", "整张表", "完整表格", "表格内容",
)
_QUERY_TERM_RE = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+(?:[._/-][A-Za-z0-9]+)*")
_QUERY_STOPWORDS = {
    "请问", "请查询", "查询", "检索", "知识库中", "知识库", "职业", "health",
    "的是多少", "是多少", "的是", "相关", "要求", "规定", "多少", "什么",
    "怎么", "如何", "请", "的",
}

INSTRUCTIONS = (
    "职业健康知识库检索工具。检索结果带文档名与页码。"
    "服务端会根据问题自动识别职业病场景，也可显式传 scenario；不传时若识别成功会自动过滤。"
    "detail 默认 auto：快速问答用 brief，写报告/逐条引用/完整表格用 full，也可显式指定。"
    "回答时必须引用来源（文档名 + 页码），职业接触限值、标准编号、单位必须原样引用，"
    "不得改写、换算或推测；检索不到就明确说没有找到，不要凭常识补全。"
)


def _bearer(ctx: Context | None) -> str | None:
    if ctx is not None:
        try:
            request = ctx.request_context.request
        except (AttributeError, ValueError):
            request = None
        if request is not None:
            header = request.headers.get("authorization")
            if header and header.lower().startswith("bearer "):
                return header[7:]
    return os.environ.get("OH_API_TOKEN")


async def _request(
    method: str,
    path: str,
    token: str | None,
    body: dict | None = None,
) -> tuple[Any, dict | None]:
    if not token:
        return None, {
            "error": "unauthorized",
            "message": "缺少 API Key，请在请求头带 Authorization: Bearer <key>",
        }
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(
            base_url=API_BASE, timeout=TIMEOUT_SECONDS
        ) as client:
            response = await client.request(method, path, json=body, headers=headers)
    except httpx.HTTPError as exc:
        return None, {"error": "backend_unavailable", "message": str(exc)}
    try:
        payload = response.json()
    except ValueError:
        return None, {
            "error": "backend_error",
            "status": response.status_code,
            "message": "后端返回了非 JSON 响应",
        }
    if response.status_code >= 400:
        code = "backend_error"
        if response.status_code == 401:
            code = "unauthorized"
        elif response.status_code == 403:
            code = "forbidden"
        elif response.status_code == 429:
            code = "rate_limited"
        return None, {
            "error": code,
            "status": response.status_code,
            "message": payload.get("message") or "请求失败",
        }
    return payload.get("data"), None


def _clip(text: str, limit: int = BRIEF_TEXT_CHARS) -> str:
    clean = (text or "").strip()
    return clean if len(clean) <= limit else f"{clean[:limit]}…（已截断）"


def _resolve_detail(requested: str | None, query: str) -> dict:
    mode = (requested or "auto").strip().lower()
    if mode not in {"auto", "brief", "full"}:
        mode = "auto"
    if mode in {"brief", "full"}:
        return {
            "requested": mode,
            "effective": mode,
            "reason": "explicit",
        }
    normalized = (query or "").casefold()
    if any(marker in normalized for marker in _FULL_DETAIL_MARKERS):
        return {
            "requested": "auto",
            "effective": "full",
            "reason": "query_intent",
        }
    return {
        "requested": "auto",
        "effective": "brief",
        "reason": "default",
    }


def _query_terms(query: str) -> list[str]:
    normalized = (query or "").casefold()
    for stopword in sorted(_QUERY_STOPWORDS, key=len, reverse=True):
        normalized = normalized.replace(stopword, " ")
    terms: list[str] = []
    for match in _QUERY_TERM_RE.findall(normalized):
        term = match.strip()
        if len(term) < 1 or term in _QUERY_STOPWORDS:
            continue
        if term not in terms:
            terms.append(term)
    return terms


def _expand_table(table: dict) -> list[list[str]]:
    rows = [
        [
            TableCell(
                text=str(cell.get("text") or ""),
                rowspan=int(cell.get("rowspan") or 1),
                colspan=int(cell.get("colspan") or 1),
            )
            for cell in row
        ]
        for row in (table.get("rows") or [])
    ]
    return expand_rows(rows)


def _table_lines(
    expanded: list[list[str]],
    row_start: int,
    indices: list[int],
    caption: str | None = None,
    footer: str | None = None,
) -> str:
    lines: list[str] = []
    if caption:
        lines.append(f"表题：{caption}")
    for position, index in enumerate(indices):
        row = expanded[index]
        cells = [
            str(cell).replace("|", "\\|").replace("\n", "<br>")
            for cell in row
        ]
        label = "表头" if index == 0 else str(row_start + index - 1)
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
        if position == 0 and index == 0:
            lines.append("| --- |" + "|".join([" --- "] * len(cells)) + "|")
    if footer:
        lines.append(footer)
    return "\n".join(lines)


def _table_window_markdown(table: dict, query: str) -> tuple[str, dict]:
    expanded = _expand_table(table)
    if not expanded:
        return "", {"matched_rows": [], "displayed_rows": 0}
    row_range = table.get("row_range") or [1, len(expanded)]
    row_start = int(row_range[0] or 1)
    terms = _query_terms(query)
    matched: list[int] = []
    # 短中文词先做整格匹配，避免“苯”误命中“甲苯/二甲苯”。
    for index in range(1, len(expanded)):
        cells = [str(cell).strip().casefold() for cell in expanded[index]]
        if any(
            re.fullmatch(r"[\u4e00-\u9fff]{1,2}", term) and term in cells
            for term in terms
        ):
            matched.append(index)
    if not matched:
        for index in range(1, len(expanded)):
            row_text = " ".join(str(cell) for cell in expanded[index]).casefold()
            if any(term in row_text for term in terms):
                matched.append(index)
    if not matched and len(expanded) > 1:
        matched = [1]
    selected = {0}
    for index in matched:
        start = max(1, index - BRIEF_TABLE_CONTEXT)
        end = min(len(expanded), index + BRIEF_TABLE_CONTEXT + 1)
        selected.update(range(start, end))
    data_indices = sorted(index for index in selected if index > 0)[:BRIEF_TABLE_ROWS]
    indices = [0, *data_indices]
    displayed = len(data_indices)
    omitted = max(0, len(expanded) - 1 - displayed)
    footer = (
        f"（表格共 {len(expanded) - 1} 行数据，已显示命中行窗口 {displayed} 行；"
        f"还有 {omitted} 行未显示，完整表格请调用 get_chunk。）"
    )
    markdown = _table_lines(
        expanded, row_start, indices, table.get("caption"), footer
    )
    return markdown, {
        "matched_rows": [row_start + index - 1 for index in matched],
        "displayed_rows": displayed,
        "row_window": True,
    }


def _table_markdown(table: dict) -> str:
    expanded = _expand_table(table)
    if not expanded:
        return ""
    row_range = table.get("row_range") or [1, len(expanded)]
    row_start = int(row_range[0] or 1)
    indices = list(range(min(MAX_TABLE_ROWS, len(expanded))))
    footer = None
    if len(expanded) > MAX_TABLE_ROWS:
        footer = f"（其余 {len(expanded) - MAX_TABLE_ROWS} 行已省略）"
    return _table_lines(expanded, row_start, indices, table.get("caption"), footer)


def _page_label(item: dict) -> str:
    start = item.get("page_start")
    end = item.get("page_end")
    if end and start and end != start:
        return f"{start}-{end}"
    return str(start or "")


def _allowed_hosts() -> list[str]:
    """Host allow-list for the streamable HTTP transport.

    Cloudflare forwards ``Host: kb.guanmingkun.ltd``; local checks and tests
    use 127.0.0.1/localhost/testserver. ``:*`` entries allow any port.
    """
    raw = os.environ.get(
        "OH_MCP_ALLOWED_HOSTS",
        "kb.guanmingkun.ltd,127.0.0.1,localhost,testserver",
    )
    hosts: list[str] = []
    for item in raw.split(","):
        host = item.strip()
        if not host:
            continue
        hosts.append(host)
        if not host.endswith(":*"):
            hosts.append(f"{host}:*")
    return hosts


def build_server() -> FastMCP:
    mcp = FastMCP(
        "occupational-health-knowledge-base",
        instructions=INSTRUCTIONS,
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=_allowed_hosts(),
        ),
    )

    @mcp.tool()
    async def search_knowledge(
        ctx: Context,
        query: str,
        mode: str = "hybrid",
        top_k: int = 5,
        detail: str = "auto",
        block_types: list[str] | None = None,
        scenario: str | None = None,
        category_ids: list[str] | None = None,
        tag_ids: list[str] | None = None,
        include_replaced: bool = False,
    ) -> dict:
        """检索职业健康知识库，返回原文片段、表格与页码引用。

        Args:
            query: 检索语句，尽量包含物质名、标准号或限值类型。
            mode: hybrid（默认）/ semantic / keyword。
            top_k: 返回条数，1-5。
            detail: auto（默认自动判断）/ brief（简洁）/ full（完整）。
            block_types: 只要正文传 ["text"]，只要表格传 ["table"]。
            scenario: 职业病场景名称或 code，如 "粉尘危害" / "dust"；不传时服务端自动识别。
            category_ids: 场景 ID 过滤，兼容旧参数；服务端也会自动包含通用。
            tag_ids: 标签 ID 过滤。
            include_replaced: 是否包含已替代/废止版本，默认 false。
        """
        filters: dict[str, Any] = {}
        applied_scenario: str | None = None
        scenario_source = "none"
        if block_types:
            filters["block_types"] = block_types

        detail_meta = _resolve_detail(detail, query)
        effective_detail = detail_meta["effective"]

        resolved_ids = list(category_ids or [])
        if resolved_ids:
            scenario_source = "filter"
        inferred_code: str | None = None
        inferred_ids: list[str] = []
        if scenario:
            inferred_code = scenario.strip()
            scenario_source = "explicit"
        elif not resolved_ids:
            guess = classify_query(query, "")
            if (
                guess.get("code")
                and guess["code"] != "general"
                and float(guess.get("confidence") or 0) >= 0.6
            ):
                inferred_code = guess["code"]
                scenario_source = "inferred"

        if inferred_code:
            categories, error = await _request("GET", "/categories", _bearer(ctx))
            if error:
                return error
            needle = inferred_code.casefold()
            matched = [
                item
                for item in categories or []
                if str(item.get("code") or "").casefold() == needle
                or str(item.get("name") or "").casefold() == needle
            ]
            if scenario and not matched:
                return {
                    "error": "unknown_scenario",
                    "message": f"未知场景：{scenario}，请先调用 list_taxonomy 查看场景",
                }
            if matched:
                target_ids = [str(item.get("id")) for item in matched]
                applied_scenario = matched[0].get("name") or inferred_code
                if scenario_source == "inferred":
                    inferred_ids.extend(target_ids)
                else:
                    resolved_ids.extend(target_ids)
        if resolved_ids:
            filters["category_ids"] = list(dict.fromkeys(resolved_ids))
        if inferred_ids:
            filters["scenario_ids"] = list(dict.fromkeys(inferred_ids))
        if tag_ids:
            filters["tag_ids"] = tag_ids
        filters["include_replaced"] = include_replaced
        body = {
            "query": query,
            "mode": mode if mode in {"hybrid", "semantic", "keyword"} else "hybrid",
            "top_k": max(1, min(int(top_k), 5)),
            "filters": filters,
        }
        data, error = await _request("POST", "/search", _bearer(ctx), body)
        if error:
            return error
        results = []
        for item in data.get("items") or []:
            result: dict[str, Any] = {
                "document": item.get("document_name"),
                "document_id": item.get("document_id"),
                "pages": _page_label(item),
                "kind": item.get("kind"),
                "chunk_id": item.get("chunk_id"),
                "matched_chunk_id": item.get("matched_chunk_id"),
                "version_number": item.get("version_number"),
                "lifecycle_status": item.get("lifecycle_status"),
                "document_role": item.get("document_role"),
                "standard_no": item.get("standard_no"),
                "related_documents": item.get("related_documents") or [],
                "amendment_notice": item.get("amendment_notice"),
                "score": round(float((item.get("scores") or {}).get("rrf") or 0), 4),
            }
            table = item.get("table")
            if table:
                if effective_detail == "brief":
                    markdown, preview = _table_window_markdown(table, query)
                    result["table_markdown"] = markdown
                    result["table_preview"] = preview
                else:
                    result["table_markdown"] = _table_markdown(table)
                    result["table_preview"] = {"row_window": False}
                result["row_count"] = table.get("row_count")
                result["column_count"] = table.get("column_count")
                result["row_range"] = table.get("row_range")
            else:
                text_limit = (
                    BRIEF_TEXT_CHARS
                    if effective_detail == "brief"
                    else FULL_TEXT_CHARS
                )
                result["text"] = _clip(item.get("text") or "", text_limit)
            results.append(result)
        return {
            "query": query,
            "mode": data.get("mode"),
            "detail": detail_meta,
            "scenario": applied_scenario,
            "scenario_source": scenario_source,
            "total": data.get("total"),
            "took_ms": data.get("took_ms"),
            "degraded": data.get("degraded"),
            "results": results,
            "citation_rule": "引用时写明文档名与页码；数值与标准号原样照抄。",
        }

    @mcp.tool()
    async def get_chunk(ctx: Context, chunk_id: str) -> dict:
        """按 chunk_id 取回完整片段（用于追问已命中的内容）。"""
        data, error = await _request("GET", f"/chunks/{chunk_id}", _bearer(ctx))
        if error:
            return error
        return {
            "chunk_id": data.get("id"),
            "document_id": data.get("document_id"),
            "document": data.get("document_name"),
            "version_number": data.get("version_number"),
            "lifecycle_status": data.get("lifecycle_status"),
            "standard_no": data.get("standard_no"),
            "pages": _page_label(data),
            "kind": data.get("block_type"),
            "table_header": data.get("table_header"),
            # 表格块的 text 本身就是 Markdown 表格文本，直接返回即可。
            "text": _clip(data.get("text") or "", 4000),
        }

    @mcp.tool()
    async def list_documents(ctx: Context, keyword: str = "") -> dict:
        """列出可检索文档，可按标题关键字过滤。"""
        data, error = await _request("GET", "/documents?page=1&page_size=100", _bearer(ctx))
        if error:
            return error
        needle = (keyword or "").strip().lower()
        items = [
            {
                "document_id": item.get("id"),
                "title": item.get("title"),
                "status": item.get("status"),
                "category": (item.get("category") or {}).get("name"),
                "updated_at": item.get("updated_at"),
            }
            for item in data.get("items") or []
            if not needle or needle in str(item.get("title") or "").lower()
        ]
        return {"total": len(items), "documents": items}

    @mcp.tool()
    async def list_taxonomy(ctx: Context) -> dict:
        """返回职业病场景与标签，便于给检索加上过滤条件。"""
        categories, error = await _request("GET", "/categories", _bearer(ctx))
        if error:
            return error
        tags, error = await _request("GET", "/tags?page=1&page_size=100", _bearer(ctx))
        if error:
            return error
        scenarios = [
            {"id": item.get("id"), "name": item.get("name"), "code": item.get("code")}
            for item in categories or []
        ]
        return {
            "scenarios": scenarios,
            "categories": scenarios,
            "tags": [
                {"id": item.get("id"), "name": item.get("name")}
                for item in (tags.get("items") if isinstance(tags, dict) else []) or []
            ],
        }

    return mcp


mcp = build_server()


class BearerGuard:
    """Reject unauthenticated MCP requests before they reach the transport."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        if not authorization.lower().startswith("bearer "):
            body = (
                b'{"error":"unauthorized","message":"Missing bearer token"}'
            )
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def mcp_app():
    """Build a fresh MCP ASGI app plus the session manager it needs.

    Each FastAPI application gets its own server instance: the streamable HTTP
    session manager can only be started once, and tests create several apps.
    """
    server = build_server()
    application = server.streamable_http_app()
    return BearerGuard(application), server.session_manager


def main() -> None:
    parser = argparse.ArgumentParser(description="Knowledge base MCP server")
    parser.add_argument(
        "--http", action="store_true", help="run standalone streamable HTTP"
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.http:
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
