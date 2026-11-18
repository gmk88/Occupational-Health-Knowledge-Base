# 职业健康知识库 MCP 连接说明

本包不包含明文 Token。请先从 `key.txt` 读取一次性密钥，并在本机环境变量中配置：

- Windows PowerShell：`$env:OH_KB_TOKEN = "粘贴 key.txt 内容"`
- Windows 永久设置：`setx OH_KB_TOKEN "粘贴 key.txt 内容"`
- macOS / Linux：`export OH_KB_TOKEN="粘贴 key.txt 内容"`

## 连接信息

- 服务地址：`https://kb.guanmingkun.ltd/mcp/`
- 鉴权方式：`Authorization: Bearer $OH_KB_TOKEN`
- 默认且最多返回 5 条结果
- `search_knowledge` 支持 `scenario`（职业病场景）、`detail=auto|brief|full`
- 场景过滤会自动包含“通用”；服务端也会自动识别场景并用于排序
- `get_chunk` 可获取完整父块或完整表格

## 客户端配置

- WorkBuddy：使用 `mcp.json`，类型为 `streamableHttp`
- Claude Desktop Windows：使用 `claude_desktop_config_windows.json`
- Claude Desktop macOS：使用 `claude_desktop_config_macos.json`
- Claude Code：使用 `claude_code.json`，类型为 `http`

不要把 `key.txt` 或环境变量值转发到群聊。密钥丢失时可联系管理员吊销并重新发放。
