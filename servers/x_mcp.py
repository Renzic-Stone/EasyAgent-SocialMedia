#!/usr/bin/env python3
"""
x-mcp — MCP server for X/Twitter.

Usage:
  python /path/to/x_mcp.py

Backend:
  opencli  (npm install -g @jackwener/opencli)
Class: B — 需登录态（Cookie/浏览器）
"""

import json
import subprocess
import sys

# Windows npm 全局命令需要 .cmd 后缀
OPENCLI_CMD = "opencli.cmd" if sys.platform == "win32" else "opencli"
import urllib.request


SERVER_NAME = "x-mcp"
SERVER_VERSION = "0.1.0"
PLATFORM_DESC = "X/Twitter"
SEARCH_DOMAIN = "twitter.com"
CLASS = "B"
CLEAN = False

BACKENDS = ["opencli"]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _no_backend_hint() -> str:
    """搜索引擎兜底指引——后端不可用时，告诉模型用搜索引擎替代，禁止自行修复"""
    opencli_ok = _check_opencli()
    if opencli_ok:
        cause = f"{PLATFORM_DESC} 登录 Cookie 已过期或被拦截"
    else:
        cause = f"OpenCLI 连接异常，{PLATFORM_DESC} 无法读取"
    return f"{cause}。\n\n先用搜索引擎搜索 site:{SEARCH_DOMAIN} '关键词' 获取内容，\n将结果正常输出给用户，并告知用户该平台登录状态需要更新。\n\n注意：不要尝试自行修复（重试命令、修改参数、换工具等），\n自行修复通常无效且浪费大量时间和上下文资源。\n如果搜索引擎也无法获取有效内容，则跳过此步骤，\n在结尾如实告知用户无法获取该平台的内容。"



def _check_opencli() -> bool:
    """检测 OpenCLI 是否可用"""
    try:
        r = subprocess.run(
            [OPENCLI_CMD, "daemon", "status"],
            capture_output=True, text=True, timeout=10,
        )
        return "connected" in r.stdout.lower()
    except FileNotFoundError:
        return False
    except Exception:
        return False


_CHECK_FUNCS = {
    "opencli": _check_opencli,
}


def _detect_active_backend() -> str | None:
    """按优先级检测并返回第一个可用后端名称"""
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
    """返回各后端状态 + 当前活跃后端。"""
    active = _detect_active_backend()
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
        "backends": statuses,
        "active_backend": active,
        "all_dead": active is None,
    }


def _parse_json_or_raw(text: str, backend: str) -> dict:
    """解析 stdout 为 JSON，失败则原样返回"""
    text = text.strip()
    if text and (text[0] in ("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return {"result": text, "format": "text", "_backend": backend}


def twitter_search(query: str, count: int = 5) -> dict:
    """搜索 X/Twitter 推文。"""
    active = _detect_active_backend()
    if active is None:
        return {"error": _no_backend_hint()}

    if active == "opencli":
        try:
            r = subprocess.run(
                [OPENCLI_CMD, "twitter", "search", query, "-f", "yaml", "-n", str(count)],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode != 0:
                return {"error": f"opencli 搜索失败: {r.stderr.strip() or r.stdout.strip()}"}
            return {"result": r.stdout.strip(), "format": "yaml", "_backend": "opencli"}
        except Exception as e:
            return {"error": f"opencli 搜索异常: {str(e)}"}

    return {"error": f"当前后端不支持搜索功能"}


def twitter_tweet(url: str) -> dict:
    """读取单条推文。"""
    active = _detect_active_backend()
    if active is None:
        return {"error": _no_backend_hint()}

    if active == "opencli":
        tweet_id = url.strip().rstrip("/").split("/")[-1].split("?")[0]
        try:
            r = subprocess.run(
                [OPENCLI_CMD, "twitter", "status", tweet_id, "-f", "yaml"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode != 0:
                return {"error": f"opencli 读取推文失败: {r.stderr.strip() or r.stdout.strip()}"}
            return {"result": r.stdout.strip(), "format": "yaml", "_backend": "opencli"}
        except Exception as e:
            return {"error": f"opencli 读取推文异常: {str(e)}"}

    return {"error": _no_backend_hint()}


def twitter_user(username: str) -> dict:
    """查询用户信息。"""
    active = _detect_active_backend()
    if active is None:
        return {"error": _no_backend_hint()}

    if active == "opencli":
        try:
            r = subprocess.run(
                [OPENCLI_CMD, "twitter", "user", username, "-f", "yaml"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode != 0:
                return {"error": f"opencli 用户查询失败: {r.stderr.strip() or r.stdout.strip()}"}
            return {"result": r.stdout.strip(), "format": "yaml", "_backend": "opencli"}
        except Exception as e:
            return {"error": f"opencli 用户查询异常: {str(e)}"}

    return {"error": f"当前后端不支持用户查询"}



TOOLS = [
    {
        "name": "twitter_search",
        "description": "搜索 X/Twitter 上的推文。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "count": {"type": "number", "default": 5, "description": "返回数量"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "twitter_tweet",
        "description": "读取单条推文内容。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "推文完整 URL，如 https://x.com/user/status/1234567890",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "twitter_user",
        "description": "查询 X/Twitter 用户信息。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {"type": "string", "description": "用户名（不含 @ 前缀）"},
            },
            "required": ["username"],
        },
    },
    {
        "name": "doctor",
        "description": "检查 X/Twitter 所有后端（opencli）的可用状态",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle_call(name: str, args: dict) -> dict:
    """路由 MCP tool 调用到实际处理函数。所有异常被优雅捕获。"""
    try:
        if name == "twitter_search":
            result = twitter_search(
                args.get("query", ""),
                count=args.get("count", 5),
            )
        elif name == "twitter_tweet":
            result = twitter_tweet(args.get("url", ""))
        elif name == "twitter_user":
            result = twitter_user(args.get("username", ""))
        elif name == "doctor":
            result = doctor()
        else:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"未知 tool: {name}"}],
            }
        return {
            "content": [
                {"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}
            ],
        }
    except Exception as e:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"处理 {name} 时出错: {str(e)}"}],
        }


def main():
    """MCP stdio 事件循环：从 stdin 读取 JSON-RPC 请求并响应。"""
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
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {
                                "name": SERVER_NAME,
                                "version": SERVER_VERSION,
                            },
                        },
                    }
                )
                + "\n"
            )
            sys.stdout.flush()

        elif method == "tools/list":
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {"tools": TOOLS},
                    }
                )
                + "\n"
            )
            sys.stdout.flush()

        elif method == "tools/call":
            params = msg.get("params", {})
            result = handle_call(
                params.get("name", ""), params.get("arguments", {})
            )
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": result,
                    }
                )
                + "\n"
            )
            sys.stdout.flush()

        elif method == "notifications/initialized":
            pass


if __name__ == "__main__":
    main()
