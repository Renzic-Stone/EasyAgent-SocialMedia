#!/usr/bin/env python3
"""
reddit-mcp — MCP server for Reddit.
Single-backend: opencli (EasyAgent 统一登录态).

Usage:
  python /path/to/reddit_mcp.py

Backend:
  opencli  (npm install -g @jackwener/opencli + Chrome extension)
Class: B — 需登录态（Cookie/浏览器）
"""

import json
import subprocess
import sys

# Windows npm 全局命令需要 .cmd 后缀
OPENCLI_CMD = "opencli.cmd" if sys.platform == "win32" else "opencli"
import urllib.request
from urllib.parse import urlencode

SERVER_NAME = "reddit-mcp"
SERVER_VERSION = "0.1.0"
PLATFORM_DESC = "Reddit"
SEARCH_DOMAIN = "reddit.com"
CLASS = "B"
CLEAN = True

BACKENDS = ["opencli"]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


# ───────────────────────── Data Cleaning ─────────────────────────


def _no_backend_hint() -> str:
    """搜索引擎兜底指引——后端不可用时，告诉模型用搜索引擎替代，禁止自行修复"""
    opencli_ok = _check_opencli()
    if opencli_ok:
        cause = f"{PLATFORM_DESC} 登录 Cookie 已过期或被拦截"
    else:
        cause = f"OpenCLI 连接异常，{PLATFORM_DESC} 无法读取"
    return f"{cause}。\n\n先用搜索引擎搜索 site:{SEARCH_DOMAIN} '关键词' 获取内容，\n将结果正常输出给用户，并告知用户该平台登录状态需要更新。\n\n注意：不要尝试自行修复（重试命令、修改参数、换工具等），\n自行修复通常无效且浪费大量时间和上下文资源。\n如果搜索引擎也无法获取有效内容，则跳过此步骤，\n在结尾如实告知用户无法获取该平台的内容。"


def _clean_post(raw: dict) -> dict:
    if not isinstance(raw, dict):
        return {}

    # --- ID ---
    post_id = raw.get("id") or ""
    if isinstance(post_id, (int, float)):
        post_id = str(int(post_id))

    # --- Title ---
    title = raw.get("title") or ""

    # --- Subreddit (去掉 r/ 前缀) ---
    subreddit = raw.get("subreddit_name_prefixed") or raw.get("subreddit") or ""
    if subreddit.startswith("r/"):
        subreddit = subreddit[2:]

    # --- Author (确保 u/ 前缀) ---
    author = raw.get("author") or ""
    if isinstance(author, dict):
        author = author.get("name", "") or author.get("username", "")
    if author and not author.startswith("u/"):
        author = f"u/{author}"

    # --- Score (ups 或 score) ---
    score = 0
    for v in [raw.get("score"), raw.get("ups")]:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            score = int(v)
            break

    # --- Comments count ---
    comments = 0
    for v in [raw.get("num_comments"), raw.get("comments")]:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            comments = int(v)
            break
    # 'comments' might be a list of comment objects, not a count
    if comments == 0 and isinstance(raw.get("comments"), list):
        comments = len(raw["comments"])

    # --- URL ---
    url = raw.get("url") or raw.get("permalink") or ""
    if url and not url.startswith("http"):
        url = f"https://www.reddit.com{url}"

    # --- Selftext (截断到 2000 字) ---
    selftext = raw.get("selftext") or raw.get("body") or ""
    selftext = str(selftext)[:2000]

    # --- Created (时间戳 → 可读格式 "2025-12-01") ---
    created = ""
    ts = raw.get("created_utc") or raw.get("created") or raw.get("timestamp")
    if isinstance(ts, (int, float)) and not isinstance(ts, bool):
        try:
            from datetime import datetime
            created = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        except (OSError, ValueError):
            created = str(ts)

    # --- Preview ---
    preview = (
        raw.get("preview")
        or raw.get("thumbnail")
        or raw.get("preview_image_url")
        or raw.get("url_overridden_by_dest", "")
    )
    # Reddit API 有时把 preview 放在嵌套 dict 里
    if isinstance(preview, dict) and isinstance(preview.get("images"), list):
        for img in preview["images"]:
            if isinstance(img, dict):
                src = img.get("source", {})
                if isinstance(src, dict) and src.get("url"):
                    preview = src["url"]
                    break
                if img.get("url"):
                    preview = img["url"]
                    break

    # 组装结果，跳过空字符串（保留 0 值）
    cleaned = {
        "id": post_id,
        "title": title,
        "subreddit": subreddit,
        "author": author,
        "score": score,
        "comments": comments,
        "url": url,
        "selftext": selftext,
        "created": created,
    }
    if preview:
        cleaned["preview"] = preview

    return cleaned


def _clean_posts(raw_list: list) -> list:
    """批量清洗帖子列表"""
    return [_clean_post(p) for p in raw_list if isinstance(p, dict)]


# ───────────────────────── Backend Detection ─────────────────────────


def _check_opencli() -> bool:
    """检测 OpenCLI 是否可用（daemon 状态为 connected）"""
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


# ───────────────────────── Helpers ─────────────────────────


def _parse_json_or_raw(text: str, backend: str) -> dict:
    """解析 stdout 为 JSON，失败则原样返回"""
    text = text.strip()
    if text and (text[0] in ("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return {"result": text, "format": "text", "_backend": backend}


def _ensure_active() -> tuple[str | None, str | None]:
    """检测活跃后端，返回 (active_backend, error)"""
    active = _detect_active_backend()
    if active is None:
        return None, _no_backend_hint()
    return active, None


# ───────────────────────── Tool Implementations ─────────────────────────


def reddit_hot(subreddit: str = "", limit: int = 10) -> dict:
    """获取 Reddit 热门帖子。可选指定 subreddit。"""
    active, err = _ensure_active()
    if err:
        return {"error": err}

    if active == "opencli":
        try:
            cmd = [OPENCLI_CMD, "reddit", "hot", "--limit", str(limit), "-f", "json"]
            if subreddit:
                cmd = [OPENCLI_CMD, "reddit", "hot", "--limit", str(limit), "-f", "json", subreddit]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                return {"error": f"opencli 热门失败: {r.stderr.strip() or r.stdout.strip()}"}
            result = _parse_json_or_raw(r.stdout, "opencli")
            if isinstance(result, list):
                result = _clean_posts(result)
            elif isinstance(result, dict):
                result = _clean_post(result)
            return result
        except Exception as e:
            return {"error": f"opencli 热门异常: {str(e)}"}

    return {"error": f"当前后端 '{active}' 不支持热门功能"}


def reddit_search(query: str, limit: int = 10) -> dict:
    """搜索 Reddit 帖子。优先 opencli。"""
    active, err = _ensure_active()
    if err:
        return {"error": err}

    if active == "opencli":
        try:
            r = subprocess.run(
                [OPENCLI_CMD, "reddit", "search", query, "--limit", str(limit), "-f", "json"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode != 0:
                return {"error": f"opencli 搜索失败: {r.stderr.strip() or r.stdout.strip()}"}
            result = _parse_json_or_raw(r.stdout, "opencli")
            if isinstance(result, list):
                result = _clean_posts(result)
            elif isinstance(result, dict):
                result = _clean_post(result)
            return result
        except Exception as e:
            return {"error": f"opencli 搜索异常: {str(e)}"}

    return {"error": f"当前后端 '{active}' 不支持搜索功能"}


def reddit_post(url: str) -> dict:
    """读取 Reddit 帖子内容 + 评论。"""
    active, err = _ensure_active()
    if err:
        return {"error": err}

    if active == "opencli":
        try:
            r = subprocess.run(
                [OPENCLI_CMD, "reddit", "read", url, "-f", "json"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode != 0:
                return {"error": f"opencli 读取失败: {r.stderr.strip() or r.stdout.strip()}"}
            result = _parse_json_or_raw(r.stdout, "opencli")
            if isinstance(result, list):
                result = _clean_posts(result)
            elif isinstance(result, dict):
                result = _clean_post(result)
            return result
        except Exception as e:
            return {"error": f"opencli 读取异常: {str(e)}"}

    return {"error": _no_backend_hint()}


def reddit_subreddit(name: str, limit: int = 10) -> dict:
    """浏览指定 subreddit 的帖子。通过 reddit_hot 带 subreddit 参数实现。"""
    return reddit_hot(subreddit=name, limit=limit)


# ───────────────────────── MCP Protocol Definition ─────────────────────────

TOOLS = [
    {
        "name": "reddit_hot",
        "description": "获取 Reddit 热门帖子。可选指定 subreddit（如不传则取全局热门）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subreddit": {"type": "string", "default": "", "description": "Subreddit 名称（可选，不传则取全局热门）"},
                "limit": {"type": "number", "default": 10, "description": "返回帖子数量"},
            },
            "required": [],
        },
    },
    {
        "name": "reddit_search",
        "description": "搜索 Reddit 上的帖子。优先 opencli。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "number", "default": 10, "description": "返回数量"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "reddit_post",
        "description": "读取 Reddit 帖子内容及评论。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "帖子完整 URL，如 https://www.reddit.com/r/subreddit/comments/abc123/...",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "reddit_subreddit",
        "description": "浏览指定 subreddit 的热门帖子。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Subreddit 名称（如 'python'、'programming'）"},
                "limit": {"type": "number", "default": 10, "description": "返回帖子数量"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "doctor",
        "description": "检查 Reddit 后端（opencli）的可用状态",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def handle_call(name: str, args: dict) -> dict:
    """路由 MCP tool 调用到实际处理函数。所有异常被优雅捕获。"""
    try:
        if name == "reddit_hot":
            result = reddit_hot(
                subreddit=args.get("subreddit", ""),
                limit=args.get("limit", 10),
            )
        elif name == "reddit_search":
            result = reddit_search(
                query=args.get("query", ""),
                limit=args.get("limit", 10),
            )
        elif name == "reddit_post":
            result = reddit_post(url=args.get("url", ""))
        elif name == "reddit_subreddit":
            result = reddit_subreddit(
                name=args.get("name", ""),
                limit=args.get("limit", 10),
            )
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
