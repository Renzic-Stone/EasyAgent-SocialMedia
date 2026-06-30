#!/usr/bin/env python3
"""
opencli-mcp — MCP server for 小红书 (Xiaohongshu / RED).
Zero external dependencies (stdlib only).

双后端（按优先级）：
  1. opencli     (npm @jackwener/opencli + Chrome 扩展)  — 桌面环境首选
  后端仅 opencli，失败时模型用搜索引擎兜底

Usage:
  python /path/to/xiaohongshu_mcp.py
  hermes mcp add xiaohongshu-mcp --command python --args /path/to/xiaohongshu_mcp.py
Class: B — 需登录态（Cookie/浏览器）
"""
import json
import subprocess
import sys

# Windows npm 全局命令需要 .cmd 后缀
OPENCLI_CMD = "opencli.cmd" if sys.platform == "win32" else "opencli"
import re

# ── Platform info ──

SERVER_NAME = "xiaohongshu-mcp"
SERVER_VERSION = "0.1.0"
PLATFORM_DESC = "小红书"
SEARCH_DOMAIN = "xiaohongshu.com"
CLASS = "B"
CLEAN = True

BACKENDS = ["opencli"]

# ── Utility functions ──

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _no_backend_hint() -> str:
    """搜索引擎兜底指引——后端不可用时，告诉模型用搜索引擎替代，禁止自行修复"""
    opencli_ok = _check_opencli()
    if opencli_ok:
        cause = f"{PLATFORM_DESC} 登录 Cookie 已过期或被拦截"
    else:
        cause = f"OpenCLI 连接异常，{PLATFORM_DESC} 无法读取"
    return f"{cause}。\n\n用你自己的搜索工具搜索 site:{SEARCH_DOMAIN} '关键词' 获取内容，\n将结果正常输出给用户，并告知用户该平台登录状态需要更新。\n\n注意：不要尝试自行修复（重试命令、修改参数、换工具等），\n自行修复通常无效且浪费大量时间和上下文资源。\n如果搜索引擎也无法获取有效内容，则跳过此步骤，\n在结尾如实告知用户无法获取该平台的内容。"


def _extract_note_id(url_or_id: str) -> str:
    url_or_id = url_or_id.strip()
    # 已经是纯 ID（十六进制字符串，一般 24 位）
    if re.match(r'^[a-f0-9]{10,32}$', url_or_id, re.I):
        return url_or_id
    # 从 URL 中提取
    # 常见格式：
    #   https://www.xiaohongshu.com/explore/XXXXXXXXXX
    #   https://www.xiaohongshu.com/discovery/item/XXXXXXXXXX
    #   https://xhslink.com/XXX  (短链接)
    for pattern in [
        r'/(?:explore|discovery/item|item|note)/([a-f0-9]{10,32})',
        r'note_id=([a-f0-9]{10,32})',
        r'id=([a-f0-9]{10,32})',
    ]:
        m = re.search(pattern, url_or_id, re.I)
        if m:
            return m.group(1)
    return url_or_id


# ── Data cleaning ──


def _clean_note(raw: dict) -> dict:
    """清洗单条小红书笔记，去除冗余嵌套，只保留关键字段"""
    if not isinstance(raw, dict):
        raw = {}

    # --- ID ---
    note_id = (
        raw.get("id")
        or raw.get("note_id")
        or raw.get("noteId")
        or raw.get("xsec_token_id", "")
    )
    if isinstance(note_id, (int, float)):
        note_id = str(int(note_id))

    # --- Title ---
    title = (
        raw.get("title")
        or raw.get("display_title")
        or raw.get("note_title")
        or ""
    )

    # --- Content (正文, 截断到 1000 字) ---
    content = (
        raw.get("content")
        or raw.get("desc")
        or raw.get("description")
        or raw.get("text")
        or raw.get("desc_text")
        or raw.get("note", {}).get("desc", "")
        or ""
    )
    # 有的 API 把内容埋在更深的嵌套里
    if not content and isinstance(raw.get("note"), dict):
        content = raw["note"].get("desc", "")
    if not content and isinstance(raw.get("data"), dict):
        content = raw["data"].get("desc", "")
    content = str(content)[:1000]

    # --- Author ---
    author_raw = raw.get("author") or raw.get("user") or raw.get("owner") or {}
    if isinstance(author_raw, dict):
        author = (
            author_raw.get("nickname")
            or author_raw.get("name")
            or author_raw.get("nick_name")
            or author_raw.get("nick")
            or author_raw.get("nickName")
            or author_raw.get("user_name")
            or author_raw.get("username")
            or ""
        )
    elif isinstance(author_raw, str):
        author = author_raw
    else:
        author = ""

    # --- Likes ---
    likes = 0
    likes_candidates = [
        raw.get("likes"),
        raw.get("liked_count"),
        raw.get("like_count"),
        raw.get("like_num"),
        raw.get("likedCount"),
        raw.get("likesCount"),
    ]
    # 从 interact_info 中提取
    if isinstance(raw.get("interact_info"), dict):
        likes_candidates.append(raw["interact_info"].get("liked_count"))
        likes_candidates.append(raw["interact_info"].get("likedCount"))
    for v in likes_candidates:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            likes = int(v)
            break

    # --- Collected ---
    collected = 0
    coll_candidates = [
        raw.get("collected"),
        raw.get("collected_count"),
        raw.get("fav_count"),
        raw.get("favorite_count"),
        raw.get("collectedCount"),
        raw.get("favoriteCount"),
        raw.get("favCount"),
    ]
    if isinstance(raw.get("interact_info"), dict):
        coll_candidates.append(raw["interact_info"].get("collected_count"))
        coll_candidates.append(raw["interact_info"].get("collectedCount"))
    for v in coll_candidates:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            collected = int(v)
            break

    # --- Comments count ---
    comments_count = 0
    cc_candidates = [
        raw.get("comments_count"),
        raw.get("comment_count"),
        raw.get("comments_num"),
        raw.get("commentsCount"),
        raw.get("commentCount"),
        raw.get("comments_num"),
    ]
    if isinstance(raw.get("interact_info"), dict):
        cc_candidates.append(raw["interact_info"].get("comment_count"))
        cc_candidates.append(raw["interact_info"].get("commentCount"))
    for v in cc_candidates:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            comments_count = int(v)
            break

    # --- Tags ---
    tags = []
    tags_candidates = [
        raw.get("tags"),
        raw.get("tag_list"),
        raw.get("tagList"),
        raw.get("hashtags"),
    ]
    for tag_list in tags_candidates:
        if isinstance(tag_list, list):
            for t in tag_list:
                if isinstance(t, dict):
                    tag_name = (
                        t.get("name")
                        or t.get("tag_name")
                        or t.get("tag")
                        or t.get("tagName")
                        or t.get("id")
                        or ""
                    )
                    if tag_name:
                        tags.append(str(tag_name))
                elif isinstance(t, str):
                    tags.append(t)
            if tags:
                break
    # 去重
    tags = list(dict.fromkeys(tags))

    # --- Images ---
    images = []
    img_candidates = [
        raw.get("images"),
        raw.get("image_list"),
        raw.get("imageList"),
        raw.get("imgs"),
        raw.get("img_list"),
        raw.get("imgList"),
        raw.get("pictures"),
    ]
    for img_list in img_candidates:
        if isinstance(img_list, list):
            for img in img_list:
                if isinstance(img, dict):
                    url = (
                        img.get("url")
                        or img.get("url_default")
                        or img.get("urlDefault")
                        or img.get("original")
                        or img.get("info_list", [{}])[0].get("url", "")
                        if isinstance(img.get("info_list"), list) and img.get("info_list")
                        else ""
                    )
                    # 有的图片信息在 file 或 image 字段里
                    if not url and isinstance(img.get("file"), dict):
                        url = img["file"].get("url", "")
                    if not url and isinstance(img.get("image"), dict):
                        url = img["image"].get("url", "")
                    if url:
                        images.append(str(url))
                elif isinstance(img, str):
                    images.append(img)
            if images:
                break

    # --- Build cleaned result ---
    result = {
        "id": str(note_id) if note_id else "",
        "title": str(title) if title else "",
        "author": str(author) if author else "",
        "likes": likes,
        "collected": collected,
        "comments_count": comments_count,
    }

    if content:
        result["content"] = str(content)[:1000]

    if tags:
        result["tags"] = tags

    if images:
        result["images"] = images

    # 移除空字段（但不移除 id 和 title，即使在极端情况）
    cleaned = {}
    for k, v in result.items():
        if k in ("id", "title"):
            # 保留 id 和 title，即使空
            cleaned[k] = v
        elif isinstance(v, (list, dict)):
            if v:
                cleaned[k] = v
        elif isinstance(v, (int, float)):
            cleaned[k] = v
        elif v:
            cleaned[k] = v

    return cleaned


def _clean_comment(raw: dict) -> dict:
    """清洗单条评论"""
    if not isinstance(raw, dict):
        raw = {}

    # 评论在不同的 API 下字段名不同
    comment_id = (
        raw.get("id")
        or raw.get("comment_id")
        or raw.get("commentId")
        or raw.get("cid")
        or ""
    )
    user_raw = raw.get("user") or raw.get("author") or raw.get("user_info") or {}
    if isinstance(user_raw, dict):
        user_name = (
            user_raw.get("nickname")
            or user_raw.get("name")
            or user_raw.get("nick_name")
            or user_raw.get("nick")
            or ""
        )
    else:
        user_name = str(user_raw) if user_raw else ""

    content = (
        raw.get("content")
        or raw.get("text")
        or raw.get("comment_content")
        or raw.get("commentContent")
        or raw.get("desc")
        or ""
    )

    likes = 0
    for v in [raw.get("likes"), raw.get("like_count"), raw.get("liked_count"),
              raw.get("likeCount"), raw.get("likedCount")]:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            likes = int(v)
            break

    time_str = raw.get("time") or raw.get("create_time") or raw.get("createTime") or ""

    result = {
        "id": str(comment_id) if comment_id else "",
        "user": str(user_name) if user_name else "",
        "content": str(content)[:500] if content else "",
        "likes": likes,
    }
    if time_str:
        result["time"] = str(time_str)

    # 移除空字段
    return {k: v for k, v in result.items() if v != "" and v != [] and v is not None or k in ("id",)}


# ═══════════════════════════════════════════════════════
# 后端检测
# ═══════════════════════════════════════════════════════

def _check_opencli() -> bool:
    """检测 OpenCLI (npm @jackwener/opencli + Chrome 扩展) 是否可用且已连接"""
    try:
        r = subprocess.run(
            [OPENCLI_CMD, "daemon", "status"],
            capture_output=True, text=True, timeout=10,
        )
        return "connected" in r.stdout.lower()
    except FileNotFoundError:
        return False
    except (subprocess.TimeoutExpired, Exception):
        return False


_CHECK_FUNCS = {
    "opencli": _check_opencli,
}


def _detect_active_backend() -> str | None:
    """按优先级检测，返回第一个可用的后端名称"""
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
    """检测所有后端状态"""
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

    active = _detect_active_backend()

    return {
        "platform": PLATFORM_DESC,
        "backends": statuses,
        "active_backend": active,
        "all_dead": active is None,
    }


# ═══════════════════════════════════════════════════════
# 业务函数 — OpenCLI 后端
# ═══════════════════════════════════════════════════════

def _opencli_search(query: str, count: int = 5) -> list:
    """通过 OpenCLI 搜索小红书笔记"""
    r = subprocess.run(
        [OPENCLI_CMD, "xiaohongshu", "search", query, "-f", "json"],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        raise RuntimeError(f"opencli search 失败: {r.stderr.strip() or 'unknown error'}")
    if not r.stdout.strip():
        return []

    data = json.loads(r.stdout)

    # 标准化为列表
    if isinstance(data, dict):
        # 可能包装在 data/results/items 等字段里
        for wrap_key in ("results", "data", "items", "notes", "list"):
            if isinstance(data.get(wrap_key), list):
                data = data[wrap_key]
                break
        else:
            data = [data]
    elif not isinstance(data, list):
        return []

    cleaned = []
    for item in data:
        if isinstance(item, dict):
            cleaned.append(_clean_note(item))
        if len(cleaned) >= count:
            break
    return cleaned


def _opencli_note(note_id: str) -> dict:
    """通过 OpenCLI 读取笔记详情"""
    r = subprocess.run(
        [OPENCLI_CMD, "xiaohongshu", "note", note_id, "-f", "json"],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        raise RuntimeError(f"opencli note 失败: {r.stderr.strip() or 'unknown error'}")
    if not r.stdout.strip():
        return {"error": "empty response"}

    data = json.loads(r.stdout)
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return {"error": f"unexpected data type: {type(data).__name__}"}

    return _clean_note(data)


def _opencli_comments(note_id: str) -> list:
    """通过 OpenCLI 读取评论"""
    r = subprocess.run(
        [OPENCLI_CMD, "xiaohongshu", "comments", note_id, "-f", "json"],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        raise RuntimeError(f"opencli comments 失败: {r.stderr.strip() or 'unknown error'}")
    if not r.stdout.strip():
        return []

    data = json.loads(r.stdout)

    if isinstance(data, dict):
        # 可能在 comments/data/items 字段里
        for wrap_key in ("comments", "data", "items", "list"):
            if isinstance(data.get(wrap_key), list):
                data = data[wrap_key]
                break
        else:
            data = [data]
    elif not isinstance(data, list):
        return []

    return [_clean_comment(c) for c in data if isinstance(c, dict)]


# ═══════════════════════════════════════════════════════
# MCP Tools 定义
# ═══════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "xiaohongshu_search",
        "description": "搜索小红书笔记",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "count": {
                    "type": "number",
                    "default": 5,
                    "description": "返回数量（默认 5）",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "xiaohongshu_note",
        "description": "获取小红书笔记详情（标题/正文/作者/互动数据）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url_or_id": {
                    "type": "string",
                    "description": "笔记 URL 或笔记 ID",
                },
            },
            "required": ["url_or_id"],
        },
    },
    {
        "name": "xiaohongshu_comments",
        "description": "获取小红书笔记评论",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "笔记 ID",
                },
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "doctor",
        "description": "检查小红书所有后端状态（opencli ）",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]

# ═══════════════════════════════════════════════════════
# MCP 协议事件循环
# ═══════════════════════════════════════════════════════


def handle_call(name: str, args: dict) -> dict:
    """路由 MCP tool 调用"""
    try:
        if name == "doctor":
            result = doctor()
        elif name == "xiaohongshu_search":
            count = args.get("count", 5)
            if not isinstance(count, int) or count < 1:
                count = 5
            if count > 50:
                count = 50
            try:
                result = _opencli_search(args.get("query", ""), count=count)
            except Exception:
                result = {"error": _no_backend_hint()}
        elif name == "xiaohongshu_note":
            url_or_id = args.get("url_or_id", "")
            note_id = _extract_note_id(url_or_id)
            try:
                result = _opencli_note(note_id)
            except Exception:
                result = {"error": _no_backend_hint()}
        elif name == "xiaohongshu_comments":
            note_id = args.get("note_id", "")
            try:
                result = _opencli_comments(note_id)
            except Exception:
                result = {"error": _no_backend_hint()}
        else:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"未知 tool: {name}"}],
            }

        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False, indent=2),
                }
            ],
        }
    except Exception as e:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"处理 {name} 时出错: {str(e)}"}],
        }


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
            pass  # 忽略


if __name__ == "__main__":
    main()
