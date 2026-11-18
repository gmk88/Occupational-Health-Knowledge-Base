# 外部接入指南

本系统通过版本化 OpenAPI 接口向外部系统开放。接口文档在线地址为 `http://<host>:8000/api/v1/docs`，规范文件见 `docs/api/openapi.yaml`。

## 鉴权

- 外部系统使用 `Authorization: Bearer <api-key>`。
- 密钥由管理员通过 `oh-api-client --name <name> --scopes documents:read,documents:write,search:read,jobs:read` 创建，仅在创建时展示一次。
- 无效、过期或撤销的密钥返回 `API_KEY_EXPIRED`，不泄露内部细节。

## 统一响应

所有 JSON 响应为 `{code, message, data, request_id}`。错误码表见在线文档。分页参数为 `page`、`page_size`（1–100），排序为白名单字段 `sort`，字段选择为 `fields`。

## 完整流程

1. 上传：`POST /api/v1/documents`（multipart `file`），返回 202 与 `document_id/version_id/job_id`。
2. 轮询：`GET /api/v1/jobs/{jobId}` 直到 `status` 为 `completed`。
3. 检索：`POST /api/v1/search`，`mode` 支持 `semantic/keyword/hybrid`。
4. 读取：`GET /api/v1/documents/{documentId}/pages/{pageNumber}`（默认脱敏视图）。
5. 删除：`DELETE /api/v1/documents/{documentId}`（202）。

## 限制与降级

- 默认 60 请求/分钟、上传 10 次/分钟；超限返回 429 和 `Retry-After`。
- 语义或关键词任一路故障时返回 `degraded=true` 与 `degraded_sources`。
- 普通接入方仅能获得脱敏内容；原文检索 `include_raw` 仅限管理员。
