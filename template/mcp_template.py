#!/usr/bin/env python3
"""
MCP Server 模板 — 四象限
=========================

                    数据干净（透传即可）    需数据清洗（提取/去冗余）
                    ─────────────────────   ────────────────────────
零配置（公开 API）    A-1: B站               A-2: 知乎等
需登录（Cookie/CLI）  B-1: X, Reddit         B-2: 小红书

选择依据：
  - 登录？→ 平台是否需要 Cookie / 浏览器登录态 → A/B
  - 清洗？→ 原始 API 返回是否嵌套深、空字段多 → 1/2

添加新平台：复制本文件 → 改元信息 → 删/留对应节 → 实现业务函数
"""

import json
import subprocess
import sys
import urllib.request
from pathlib import Path


# ══════════════════════════════════════════════════════
# 元信息
# ══════════════════════════════════════════════════════

SERVER_NAME = "platform-mcp"       # 唯一标识，如 "zhihu-mcp"
SERVER_VERSION = "0.1.0"
PLATFORM_DESC = "平台中文名"        # 如 "B站"、"X/Twitter"
CLASS = "A"                        # A=零配置  B=需登录
CLEAN = False                      # True=需数据清洗  False=透传

# 后端路由（顺序=优先级，doctor 按序探测）
BACKENDS = ["首选", "备选", "兜底"]

# HTTP 请求头（公开 API / Jina Reader 等用到）
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


# ══════════════════════════════════════════════════════
# Class B 特有：配置管理（A系列可整节删除）
# ══════════════════════════════════════════════════════

# CONFIG_PATH = Path.home() / ".agent-reach" / "config.yaml"
# def _load_config() -> dict:
#     """读取 Cookie/Token，YAML → 环境变量兜底"""
#     ...


# ══════════════════════════════════════════════════════
# Quadrant 2 特有：数据清洗（CLEAN=False 可整节删除）
# ══════════════════════════════════════════════════════

# def _clean_item(raw: dict) -> dict:
#     """从嵌套的原始 API 响应中提取有用字段，丢弃内部ID/空字段/冗余"""
#     return {
#         "id": raw.get("id", ""),
#         "title": raw.get("title", ""),
#         "content": (raw.get("content") or raw.get("desc") or "")[:1000],
#         "author": ...,
#         "likes": ...,
#         # 只保留消费端需要的字段
#     }
#
# def _clean_items(raw_list: list) -> list:
#     """批量清洗"""
#     return [_clean_item(item) for item in raw_list if isinstance(item, dict)]


# ══════════════════════════════════════════════════════
# 后端检测（所有象限通用）
# ══════════════════════════════════════════════════════

def _check_preferred() -> bool:
    """检测首选后端"""
    # A系列: urllib.request / requests 调 API 是否可达
    # B系列: subprocess.run 检测 CLI 是否存在+可用
    raise NotImplementedError


def _check_fallback() -> bool:
    """检测备选后端"""
    raise NotImplementedError


def _check_last_resort() -> bool:
    """检测兜底后端"""
    raise NotImplementedError


_CHECK_FUNCS = {
    "首选": _check_preferred,
    "备选": _check_fallback,
    "兜底": _check_last_resort,
}


def _detect_active_backend() -> str | None:
    """按序探测，返回第一个可用后端名称"""
    for name in BACKENDS:
        fn = _CHECK_FUNCS.get(name)
        if fn is None:
            continue
        try:
            if fn():
                return name
        except Exception:
            continue
    return None


def doctor() -> dict:
    """各后端状态 + 当前活跃后端"""
    statuses = {}
    for name in BACKENDS:
        fn = _CHECK_FUNCS.get(name)
        if fn is None:
            statuses[name] = False
            continue
        try:
            statuses[name] = fn()
        except Exception:
            statuses[name] = False
    return {
        "platform": PLATFORM_DESC,
        "login_required": CLASS == "B",
        "data_cleaned": CLEAN,
        "backends": statuses,
        "active_backend": _detect_active_backend(),
    }


# ══════════════════════════════════════════════════════
# 业务函数 — 按象限选模式
# ══════════════════════════════════════════════════════
#
# A-1（B站型）：直接调 API → 可选 _clean_items
#   def search(query, count=5) -> list:
#       data = _call_api("/search", {"q": query})
#       items = data.get("results", [])[:count]
#       return _clean_items(items) if CLEAN else items
#
# A-2（知乎型）：直接调 API → 必须 _clean_items
# B-1（X/Reddit型）：_detect_active_backend() → 调对应后端 → 可选清洗
# B-2（小红书型）：_detect_active_backend() → 调对应后端 → 必须清洗
#

def example_search(query: str, count: int = 5) -> list | dict:
    """示例搜索函数"""
    raise NotImplementedError


def example_read(item_id: str) -> dict:
    """示例读取函数"""
    raise NotImplementedError


# ══════════════════════════════════════════════════════
# MCP 协议层（全象限通用，不需改动）
# ══════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "doctor",
        "description": f"检查 {PLATFORM_DESC} 所有后端状态",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # ── 添加你的 tool 定义 ──
]


def handle_call(name: str, args: dict) -> dict:
    """路由 MCP 调用到业务函数"""
    try:
        if name == "doctor":
            result = doctor()
        # elif name == "search":
        #     result = example_search(args.get("query",""), args.get("count",5))
        else:
            return {"isError": True, "content": [
                {"type": "text", "text": f"未知 tool: {name}"}
            ]}
        return {"content": [
            {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}
        ]}
    except Exception as e:
        return {"isError": True, "content": [
            {"type": "text", "text": f"执行 {name} 异常：{e}"}
        ]}


def main():
    """MCP stdio JSON-RPC 事件循环"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_id = msg.get("id")
        method = msg.get("method")

        if method == "initialize":
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                },
            }) + "\n")
            sys.stdout.flush()

        elif method == "tools/list":
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": msg_id,
                "result": {"tools": TOOLS},
            }) + "\n")
            sys.stdout.flush()

        elif method == "tools/call":
            params = msg.get("params", {})
            result = handle_call(params.get("name", ""), params.get("arguments", {}))
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": msg_id,
                "result": result,
            }) + "\n")
            sys.stdout.flush()

        elif method == "notifications/initialized":
            pass


if __name__ == "__main__":
    main()
