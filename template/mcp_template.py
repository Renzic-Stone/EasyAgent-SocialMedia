#!/usr/bin/env python3
"""
EasyAgent MCP Server 模板
=========================

后端架构（EasyAgent v2）：
  Class A (零配置):  公开API → OpenCLI
  Class B (需登录):  OpenCLI → Jina Reader

原则：不维护平台独立 CLI（twitter-cli / rdt-cli / xhs-cli 等）。
      OpenCLI 统一接管所有登录态平台的读写。
      搜索失败时由错误消息指引模型用搜索引擎兜底。

添加新平台：复制本文件 → 改元信息 → 实现业务函数 → 填检测函数
"""

import json
import subprocess
import sys
import urllib.request
from pathlib import Path


# ══════════════════════════════════════════════════════
# 元信息
# ══════════════════════════════════════════════════════

SERVER_NAME = "platform-mcp"
SERVER_VERSION = "0.1.0"
PLATFORM_DESC = "平台中文名"
CLASS = "B"        # A=零配置  B=需登录
CLEAN = False      # True=需数据清洗

BACKENDS = ["opencli"] if CLASS == "B" else ["公开API", "opencli"]

# ── Windows 兼容 ──
OPENCLI_CMD = "opencli.cmd" if sys.platform == "win32" else "opencli"

# ── 搜索引擎兜底域名（B 类必填，A 类不需要）──
SEARCH_DOMAIN = "example.com"

# ── HTTP 请求头 ──
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


# ══════════════════════════════════════════════════════
# 后端检测
# ══════════════════════════════════════════════════════

def _check_opencli() -> bool:
    """检测 OpenCLI daemon + 扩展是否连接"""
    try:
        r = subprocess.run(
            [OPENCLI_CMD, "daemon", "status"],
            capture_output=True, text=True, timeout=10,
        )
        return "connected" in r.stdout.lower()
    except:
        return False




def _detect_active_backend() -> str | None:
    """按序探测，返回第一个可用的后端"""
    for name in BACKENDS:
        fn = _CHECK_FUNCS.get(name)
        if fn is None:
            continue
        try:
            if fn():
                return name
        except:
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
        except:
            statuses[name] = False
    return {
        "platform": PLATFORM_DESC,
        "class": CLASS,
        "backends": statuses,
        "active_backend": _detect_active_backend(),
    }


# ══════════════════════════════════════════════════════
# 搜索引擎兜底指引（B 类必加，A 类可删）
# ══════════════════════════════════════════════════════

def _no_backend_hint() -> str:
    """所有后端不可用时，指引模型用搜索引擎兜底（原则⑤⑥）"""
    opencli_ok = _check_opencli()
    if opencli_ok:
        cause = f"{PLATFORM_DESC} 登录 Cookie 已过期或被拦截"
    else:
        cause = f"OpenCLI 连接异常，{PLATFORM_DESC} 无法读取"
    return (
        f"{cause}。\n"
        f"\n"
        f"用你自己的搜索工具搜索 site:{SEARCH_DOMAIN} '关键词' 获取内容，\n"
        f"将结果正常输出给用户，并告知用户该平台登录状态需要更新。\n"
        f"\n"
        f"注意：不要尝试自行修复（重试命令、修改参数、换工具等），\n"
        f"自行修复通常无效且浪费大量时间和上下文资源。\n"
        f"如果搜索引擎也无法获取有效内容，则跳过此步骤，\n"
        f"在结尾如实告知用户无法获取该平台的内容。"
    )


# ══════════════════════════════════════════════════════
# 业务函数
# ══════════════════════════════════════════════════════
#
# Class A 模式：直接调公开 API
#   def search(query, count=5) -> list:
#       ...
#
# Class B 模式：调 OpenCLI → 失败返回 _no_backend_hint()
#   def search(query, count=5) -> dict:
#       active = _detect_active_backend()
#       if active == "opencli":
#           try: ...
#           except: ...
#       return {"error": _no_backend_hint()}
#


def example_search(query: str, count: int = 5) -> list | dict:
    raise NotImplementedError


# ══════════════════════════════════════════════════════
# MCP 协议层（通用，不需改动）
# ══════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "doctor",
        "description": f"检查 {PLATFORM_DESC} 所有后端状态",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle_call(name: str, args: dict) -> dict:
    try:
        if name == "doctor":
            result = doctor()
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
