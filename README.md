# 职业健康知识库

一个面向职业病防治与职业卫生管理的本地知识库系统。系统把 PDF、Word、Markdown 等资料解析为可检索的知识块，通过 FastAPI 与 MCP 对外提供检索服务，并为外部 Agent 返回文档名、页码、标准号、版本状态和关联文件。

## 功能

- PDF / Word / Markdown / 文本上传与异步解析
- MinerU 4.x 结构化解析，OCR 回退
- 语义父子块：子块命中、父块返回
- 表格、公式、页码、脱敏处理
- 职业病场景分类：通用、粉尘危害、化学毒物、物理因素、职业健康监护、检测评价、防护与应急
- 文档生命周期状态：现行、已替代、废止、被取代、待确认
- 修改单、补充卷、勘误、替代版本关系
- 混合检索：语义 + 关键词 + RRF 融合
- Web 检索、切分确认、标签浏览、文档管理
- MCP Streamable HTTP 服务，支持 Claude、WorkBuddy、Cursor、Claude Code
- 首页一键导出文档清单 CSV
- Cloudflare Tunnel 公网暴露，仅开放 `/mcp`

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+、FastAPI、Pydantic、SQLAlchemy、Alembic |
| 数据与队列 | PostgreSQL、Redis、Celery |
| 检索 | Qdrant、RRF、父子块召回 |
| 解析 | MinerU 4.x、RapidOCR、PyMuPDF |
| Embedding | Qwen3-Embedding-0.6B，本地 8001 服务 |
| 前端 | React 19、TypeScript、Vite、TanStack Query |
| 外部接入 | FastMCP、Streamable HTTP、Bearer API Key |
| 部署 | Windows 脚本、PowerShell 看门狗、Cloudflare Tunnel |

## 仓库边界

本仓库只包含源码、配置模板、脚本、测试和文档。

**不会包含：**

- 标准 PDF 原文
- 真实数据库
- Qdrant 数据
- 本地模型权重
- API Key / Bearer Token
- cookies、会话文件
- Cloudflare 真实隧道 UUID 与凭证路径

相关目录和文件已由 `.gitignore` 排除。请不要手动把这些内容加入 Git。

## 快速开始

### 1. 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
copy .env.example .env
```

按 `.env` 中的说明配置：

```text
OH_DATABASE_URL
OH_REDIS_URL
OH_QDRANT_URL
OH_QDRANT_API_KEY
OH_SESSION_SECRET
OH_MODEL_ROOT
```

执行迁移并启动：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn occupational_health.api.main:app --host 127.0.0.1 --port 8000
```

### 2. 前端

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

### 3. Worker 与向量服务

项目提供 Windows 脚本：

```text
启动项目.bat
启动公网访问.bat
停止项目.bat
```

也可以单独启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn occupational_health.services.embedding.server:app --host 127.0.0.1 --port 8001
.\.venv\Scripts\python.exe -m celery -A occupational_health.workers.celery_app worker --pool=solo --concurrency=1
.\.venv\Scripts\python.exe -m celery -A occupational_health.workers.celery_app worker --pool=solo --concurrency=1 -Q embedding
```

## MCP 接入

MCP 端点：

```text
https://<your-domain>/mcp/
```

支持工具：

```text
search_knowledge
get_chunk
list_documents
list_taxonomy
```

检索参数：

```text
query        查询内容
top_k        返回条数，默认且最多 5
scenario     职业病场景，可选
detail       auto | brief | full
block_types  text | table
```

示例：

```json
{
  "query": "苯的 PC-TWA 是多少",
  "scenario": "化学毒物",
  "detail": "brief",
  "top_k": 5
}
```

生成个人接入配置：

```powershell
.\.venv\Scripts\python.exe ..\deploy\mcp\create_client.py --name "客户A" --domain your-domain.com
```

配置文件使用 `OH_KB_TOKEN` 环境变量，不在 README 或 JSON 中写明文 Token。

## 目录结构

```text
backend/     FastAPI 后端、模型、服务、迁移与测试
frontend/    React 管理前端
deploy/      MCP 工具、Cloudflare Tunnel、PowerShell 脚本
docs/api/    OpenAPI 文档
```

## 测试

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

```powershell
cd frontend
npm test
npm run build
```

## 许可

MIT License。详见 `LICENSE`。
