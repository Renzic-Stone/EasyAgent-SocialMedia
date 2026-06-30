#!/usr/bin/env python3
"""
x-mcp — MCP server for X/Twitter.
Multi-backend: twitter-cli > opencli > jina-reader (fallback).

Usage:
  python /path/to/x_mcp.py

Backends (detected at runtime, first wins):
  1. twitter-cli  (pip install twitter-cli, Cookie-based auth)
  2. opencli      (npm install -g @jackwener/opencli)
  3. jina-reader  (zero-dependency HTTP fallback, read-only only)
Class: B — 需登录态（Cookie/浏览器）
"""

import json
import os
import subprocess
import sys

# Windows npm 全局命令需要 .cmd 后缀
OPENCLI_CMD = "opencli.cmd" if sys.platform == "win32" else "opencli"
import urllib.request
from pathlib import Path

SERVER_NAME = "x-mcp"
SERVER_VERSION = "0.1.0"
PLATFORM_DESC = "X/Twitter"
SEARCH_DOMAIN = "twitter.com"
CLASS = "B"
CLEAN = False

BACKENDS = ["twitter-cli", "opencli", "jina-reader"]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

CONFIG_PATH = Path.home() / ".agent-reach" / "config.yaml"


def _no_backend_hint() -> str:
    """搜索引擎兜底指引——后端不可用时，告诉模型用搜索引擎替代，禁止自行修复"""
    opencli_ok = _check_opencli()
    if opencli_ok:
        cause = f"{PLATFORM_DESC} 登录 Cookie 已过期或被拦截"
    else:
        cause = f"OpenCLI 连接异常，{PLATFORM_DESC} 无法读取"
    return f"{cause}。\n\n先用搜索引擎搜索 site:{SEARCH_DOMAIN} '关键词' 获取内容，\n将结果正常输出给用户，并告知用户该平台登录状态需要更新。\n\n注意：不要尝试自行修复（重试命令、修改参数、换工具等），\n自行修复通常无效且浪费大量时间和上下文资源。\n如果搜索引擎也无法获取有效内容，则跳过此步骤，\n在结尾如实告知用户无法获取该平台的内容。"


def _load_config() -> dict:
    """从 YAML 配置文件或环境变量加载 Cookie 配置。"""
    config = {}

    # 方案 A：通过 PyYAML 读取配置文件
    try:
        import yaml
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            twitter_cfg = cfg.get("twitter", {}) or cfg
            if "auth_token" in twitter_cfg:
                config["auth_token"] = str(twitter_cfg["auth_token"])
            if "ct0" in twitter_cfg:
                config["ct0"] = str(twitter_cfg["ct0"])
    except ImportError:
        pass  # yaml 包不存在，回退到环境变量
    except Exception:
        pass

    # 方案 B：环境变量兜底
    if "auth_token" not in config:
        token = os.environ.get("TWITTER_AUTH_TOKEN")
        if token:
            config["auth_token"] = token
    if "ct0" not in config:
        ct0 = os.environ.get("TWITTER_CT0")
        if ct0:
            config["ct0"] = ct0

    return config


def _env_for_twitter_cli() -> dict:
    """构造包含 twitter-cli 认证变量（TWITTER_AUTH_TOKEN, TWITTER_CT0）的 env dict。"""
    cfg = _load_config()
    env = os.environ.copy()
    if "auth_token" in cfg:
        env["TWITTER_AUTH_TOKEN"] = cfg["auth_token"]
    if "ct0" in cfg:
        env["TWITTER_CT0"] = cfg["ct0"]
    return env


def _check_twitter_cli() -> bool:
    """检测 twitter-cli 是否可用"""
    try:
        r = subprocess.run(
            ["twitter", "status"],
            capture_output=True, text=True, timeout=10,
            env=_env_for_twitter_cli(),
        )
        return "ok: true" in r.stdout.lower()
    except FileNotFoundError:
        return False
    except Exception:
        return False


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


def _check_jina_reader() -> bool:
    """检测 Jina Reader 网络连通性"""
    try:
        req = urllib.request.Request(
            "https://r.jina.ai/https://example.com",
            headers={"User-Agent": UA},
            method="HEAD",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


_CHECK_FUNCS = {
    "twitter-cli": _check_twitter_cli,
    "opencli": _check_opencli,
    "jina-reader": _check_jina_reader,
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
    """搜索 X/Twitter 推文。优先 twitter-cli，备选 opencli。Jina Reader 不支持搜索。"""
    active = _detect_active_backend()
    if active is None:
        return {"error": _no_backend_hint()}

    if active == "twitter-cli":
        try:
            r = subprocess.run(
                ["twitter", "search", query, "-n", str(count)],
                capture_output=True, text=True, timeout=10,
                env=_env_for_twitter_cli(),
            )
            if r.returncode != 0:
                return {"error": f"twitter-cli 搜索失败: {r.stderr.strip() or r.stdout.strip()}"}
            return _parse_json_or_raw(r.stdout, "twitter-cli")
        except Exception as e:
            return {"error": f"twitter-cli 搜索异常: {str(e)}"}

    elif active == "opencli":
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

    # Jina Reader 不能搜索
    return {"error": f"当前后端 '{active}' 不支持搜索功能"}


def twitter_tweet(url: str) -> dict:
    """读取单条推文。优先 twitter-cli，兜底 Jina Reader。"""
    active = _detect_active_backend()
    if active is None:
        return {"error": _no_backend_hint()}

    if active == "twitter-cli":
        # 从 URL 提取 tweet ID
        tweet_id = url.strip().rstrip("/").split("/")[-1].split("?")[0]
        try:
            r = subprocess.run(
                ["twitter", "status", tweet_id],
                capture_output=True, text=True, timeout=10,
                env=_env_for_twitter_cli(),
            )
            if r.returncode != 0:
                # twitter-cli 失败 → 降级到 Jina Reader
                return twitter_tweet_jina(url)
            return _parse_json_or_raw(r.stdout, "twitter-cli")
        except Exception:
            # 异常降级
            return twitter_tweet_jina(url)

    # Jina Reader 兜底
    return twitter_tweet_jina(url)


def twitter_tweet_jina(url: str) -> dict:
    """通过 Jina Reader 读取推文（零依赖 HTTP 兜底）"""
    try:
        jina_url = f"https://r.jina.ai/{url}"
        req = urllib.request.Request(jina_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8")
            return {"result": text, "format": "markdown", "source": "jina-reader", "_backend": "jina-reader"}
    except Exception as e:
        return {"error": f"jina-reader 读取失败: {str(e)}"}


def twitter_user(username: str) -> dict:
    """查询用户信息。优先 twitter-cli，备选 opencli。"""
    active = _detect_active_backend()
    if active is None:
        return {"error": _no_backend_hint()}

    if active == "twitter-cli":
        try:
            r = subprocess.run(
                ["twitter", "user", username],
                capture_output=True, text=True, timeout=10,
                env=_env_for_twitter_cli(),
            )
            if r.returncode != 0:
                return {"error": f"twitter-cli 用户查询失败: {r.stderr.strip() or r.stdout.strip()}"}
            return _parse_json_or_raw(r.stdout, "twitter-cli")
        except Exception as e:
            return {"error": f"twitter-cli 用户查询异常: {str(e)}"}

    elif active == "opencli":
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

    return {"error": f"当前后端 '{active}' 不支持用户查询"}


TOOLS = [
    {
        "name": "twitter_search",
        "description": "搜索 X/Twitter 上的推文。优先 twitter-cli，备选 opencli。Jina Reader 不支持搜索。",
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
        "description": "读取单条推文内容。优先 twitter-cli，兜底 Jina Reader（零依赖 HTTP 抓取）。",
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
        "description": "查询 X/Twitter 用户信息。优先 twitter-cli，备选 opencli。",
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
        "description": "检查 X/Twitter 所有后端（twitter-cli / opencli / jina-reader）的可用状态",
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
