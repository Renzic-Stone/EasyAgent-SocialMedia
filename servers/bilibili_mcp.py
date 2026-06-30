#!/usr/bin/env python3
"""
bilibili-mcp — MCP server for Bilibili.
Zero external dependencies (stdlib only).

Backends (detected at runtime, first wins):
  1. B站公开 API  (zero-dependency, always available)
  2. OpenCLI      (Chrome extension, subtitles)

Usage:
  chmod +x bilibili_mcp.py
  hermes mcp add bilibili-mcp --command python --args /path/to/bilibili_mcp.py
Class: A — 零配置（无需登录）
"""
import json
import subprocess
import sys

# Windows npm 全局命令需要 .cmd 后缀
OPENCLI_CMD = "opencli.cmd" if sys.platform == "win32" else "opencli"
import urllib.request
from urllib.parse import quote
from pathlib import Path


# ══════════════════════════════════════════════════════
# 元信息
# ══════════════════════════════════════════════════════

SERVER_NAME = "bilibili-mcp"
SERVER_VERSION = "0.1.0"
PLATFORM_DESC = "B站"
SEARCH_DOMAIN = "bilibili.com"
CLASS = "A"
CLEAN = False
BACKENDS = ["api (零依赖)", "opencli"]


BILIBILI_API = "https://api.bilibili.com/x/web-interface"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _bili_api(path: str, params: dict = None) -> dict:
    url = f"{BILIBILI_API}/{path}"
    if params:
        qs = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
        url += f"?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"code": -1, "error": str(e)}


def bilibili_search(query: str, page: int = 1, count: int = 5) -> list:
    """搜索B站视频"""
    data = _bili_api("search/all/v2", {"keyword": query, "page": page})
    if data.get("code") != 0:
        return [{"error": _no_backend_hint()}]
    videos = []
    for section in data.get("data", {}).get("sections", []):
        for item in section.get("items", []):
            if item.get("type") == "video":
                videos.append({
                    "title": item.get("title", ""),
                    "bvid": item.get("bvid", ""),
                    "author": item.get("author", ""),
                    "play": item.get("play", 0),
                    "danmaku": item.get("video_review", 0),
                    "duration": item.get("duration", ""),
                    "pic": item.get("pic", ""),
                })
    return videos[:count]


def bilibili_video(bvid: str) -> dict:
    """获取视频详情（标题、描述、播放数据）"""
    data = _bili_api("view", {"bvid": bvid})
    if data.get("code") != 0:
        return {"error": _no_backend_hint()}
    v = data.get("data", {})
    stat = v.get("stat", {})
    return {
        "title": v.get("title", ""),
        "desc": v.get("desc", "")[:500],
        "author": v.get("owner", {}).get("name", ""),
        "views": stat.get("view", 0),
        "likes": stat.get("like", 0),
        "coins": stat.get("coin", 0),
        "favorites": stat.get("favorite", 0),
        "danmaku": stat.get("danmaku", 0),
        "duration": v.get("duration", 0),
        "pic": v.get("pic", ""),
        "tags": [t.get("tag_name", "") for t in v.get("tags", [])],
    }


def bilibili_hot(count: int = 10) -> list:
    """获取B站热门视频"""
    data = _bili_api("popular")
    if data.get("code") != 0:
        return [{"error": _no_backend_hint()}]
    videos = []
    for v in data.get("data", {}).get("list", []):
        videos.append({
            "title": v.get("title", ""),
            "bvid": v.get("bvid", ""),
            "author": v.get("owner", {}).get("name", ""),
            "views": v.get("stat", {}).get("view", 0),
            "duration": v.get("duration", ""),
        })
    return videos[:count]


def _no_backend_hint() -> str:
    """所有后端不可用时，指引模型用搜索引擎兜底"""
    opencli_ok = _check_opencli()
    if opencli_ok:
        cause = f"{PLATFORM_DESC} 公开 API 暂时不可用，但你已安装 OpenCLI。可以尝试装 Chrome 扩展并登录后使用。"
    else:
        cause = f"{PLATFORM_DESC} 公开 API 暂时不可用（可能被限流或网络异常）"
    return (
        f"{cause}。\n"
        f"\n"
        f"用你自己的搜索工具搜索 site:{SEARCH_DOMAIN} '关键词' 获取内容，\n"
        f"将结果正常输出给用户即可。\n"
        f"\n"
        f"注意：不要尝试自行修复（重试命令、修改参数、换工具等），\n"
        f"自行修复通常无效且浪费大量时间和上下文资源。\n"
        f"如果搜索引擎也无法获取有效内容，则跳过此步骤，\n"
        f"在结尾如实告知用户暂时无法获取该平台的内容。"
    )


def _check_opencli() -> bool:
    """检测 OpenCLI 是否可用且扩展连接"""
    try:
        r = subprocess.run([OPENCLI_CMD, "daemon", "status"],
                         capture_output=True, text=True, timeout=10)
        return "connected" in r.stdout.lower()
    except FileNotFoundError:
        return False
    except Exception:
        return False


def doctor() -> dict:
    """三后端状态检测"""
    backends = {}
    try:
        backends["api (零依赖)"] = _bili_api("popular", {"ps": 1})["code"] == 0
    except Exception:
        backends["api (零依赖)"] = False
    backends["opencli"] = _check_opencli()
    active = None
    for name, ok in backends.items():
        if ok:
            active = name
            break
    return {"backends": backends, "active": active or "none"}


TOOLS = [
    {
        "name": "bilibili_search",
        "description": "搜索B站视频",
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
        "name": "bilibili_video",
        "description": "获取B站视频详情（标题/描述/播放数据）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "bvid": {"type": "string", "description": "视频BV号，如 BV1xx"},
            },
            "required": ["bvid"],
        },
    },
    {
        "name": "bilibili_hot",
        "description": "获取B站热门视频",
        "inputSchema": {
            "type": "object",
            "properties": {
                "count": {"type": "number", "default": 10},
            },
        },
    },
    {
        "name": "doctor",
        "description": "检查所有后端状态",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle_call(name: str, args: dict) -> dict:
    """路由到实际函数"""
    try:
        if name == "bilibili_search":
            result = bilibili_search(args.get("query", ""), count=args.get("count", 5))
        elif name == "bilibili_video":
            result = bilibili_video(args.get("bvid", ""))
        elif name == "bilibili_hot":
            result = bilibili_hot(args.get("count", 10))
        elif name == "doctor":
            result = doctor()
        else:
            return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]}
    except Exception as e:
        return {"isError": True, "content": [{"type": "text", "text": f"Error in {name}: {str(e)}"}]}


def main():
    """MCP stdio 事件循环"""
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
                    "serverInfo": {"name": "bilibili-mcp", "version": "0.1.0"},
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
