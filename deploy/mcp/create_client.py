"""给一个外部用户创建独立 MCP 接入方，并生成可直接使用的客户端配置。

用法（在 backend 虚拟环境里执行）：

    .\\.venv\\Scripts\\python.exe ..\\deploy\\mcp\\create_client.py ^
        --name "客户A" --domain kb.guanmingkun.ltd

生成结果在 var/mcp/clients/<name>/：
    key.txt                       一次性密钥（只保存一次）
    claude_desktop_config_windows.json  Claude Desktop Windows（环境变量版）
    claude_desktop_config_macos.json    Claude Desktop macOS（环境变量版）
    claude_code.json                    Claude Code HTTP 配置
    cursor_mcp_config.json              Cursor / Cline 配置
    README.md                           使用说明（不含明文 Token）
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from occupational_health.services.api_clients.service import ApiClientService

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "var" / "mcp" / "clients"


def _base_url(domain: str) -> str:
    value = domain.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return f"{value}/mcp/"


def _slug(name: str, client_id: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z_-]+", "_", name).strip("_")
    return slug or f"client-{client_id[:8]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an MCP client and configs")
    parser.add_argument("--name", required=True, help="对方名称，也作为接入方名称")
    parser.add_argument(
        "--domain",
        default="kb.guanmingkun.ltd",
        help="公网域名或完整 URL（默认 kb.guanmingkun.ltd）",
    )
    parser.add_argument("--limit", type=int, default=60, help="每分钟调用限额")
    args = parser.parse_args()

    client, key = ApiClientService().create_client(
        args.name.strip(),
        ["search:read"],
        rate_limit_per_minute=args.limit,
    )
    url = _base_url(args.domain)
    folder = OUTPUT_ROOT / _slug(args.name, str(client["id"]))
    folder.mkdir(parents=True, exist_ok=True)

    (folder / "key.txt").write_text(key, encoding="ascii")

    template_root = Path(__file__).resolve().parent / "templates"
    outputs = {
        "claude_desktop_config_windows.json": "windows.json",
        "claude_desktop_config_macos.json": "macos.json",
        "claude_code.json": "claude_code.json",
    }
    for output_name, template_name in outputs.items():
        text = (template_root / template_name).read_text(encoding="utf-8")
        text = text.replace("https://kb.guanmingkun.ltd/mcp/", url)
        (folder / output_name).write_text(text, encoding="utf-8")

    cursor_config = {
        "mcpServers": {
            "oh-kb": {
                "url": url,
                "headers": {"Authorization": "Bearer ${OH_KB_TOKEN}"},
            }
        }
    }
    (folder / "cursor_mcp_config.json").write_text(
        json.dumps(cursor_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    readme = (template_root / "README_TEMPLATE.md").read_text(encoding="utf-8")
    (folder / "README.md").write_text(readme, encoding="utf-8")

    print(f"client_id: {client['id']}")
    print(f"rate_limit: {client['rate_limit_per_minute']}/min  scope: search:read")
    print(f"mcp_url: {url}")
    print(f"config_dir: {folder}")
    print("Configs use OH_KB_TOKEN; send key.txt privately and do not paste it into README.")


if __name__ == "__main__":
    main()
