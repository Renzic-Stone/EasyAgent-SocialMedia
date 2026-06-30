# EasyAgent-SocialMedia

**把 AI Agent 的互联网社交平台能力拆成一个个独立的 MCP server，而不是塞进一个大一统框架。**

> `EasyAgent` 是一系列轻量 MCP 工具集的总称。
> `SocialMedia` 是这个系列的第一套：B站、X、小红书、Reddit。

> **如果你想了解项目，请往下看。如果你只想直接获取这个 MCP 服务，请直接对你的 AI Agent 提出要求，而非阅读这份文档。**

---

```
                     数据干净（透传）    需数据清洗（提取/去冗余）
                     ─────────────────   ─────────────────────────
零配置（公开 API）     A-1: B站           A-2: 模板就绪
需登录（Cookie/CLI）   B-1: X, Reddit     B-2: 小红书
```

每个 MCP server 是独立进程，互不影响，按需启动，零 token 注入。

---

## 故事

> 灵感来源于 [Agent-Reach](https://github.com/Panniantong/Agent-Reach)，一个非常优秀的项目——它让你的 AI Agent 能读取 15 个互联网平台，一站式安装、体检、路由。
>
> 但在实际使用中我发现一个问题：**它太重了。**
>
> 框架本身加上所有渠道的检测逻辑、SKILL.md + 6 个 references 每次对话注入 ~30KB token、不需要的平台也占空间、更新依赖上游节奏…… 我只需要其中三个平台（B站、X、小红书），不想为整个框架买单。
>
> 我提出拆成独立的 MCP server——每个平台一个，进程隔离，按需加载。我的 AI 助手（Hermes Agent）负责落地：写代码、搭模板、做规范化。
>
> **结果好得超出预期：**
> - MCP 是独立进程，不占 context，不耗 token
> - 每个 server 自包含，要哪个配哪个
> - 统一 OpenCLI 后端 + 搜索引擎兜底，废弃独立 CLI
> - 一个崩了不影响其他
>
> 用着用着，Reddit 也加进来了。代码慢慢规范化，形成了"四象限分类"的模板体系。
>
> 这就是 EasyAgent-SocialMedia 的由来——**不是另一个框架，而是一组你可以自由搭配的 MCP server，每台只干一件事，但干得漂亮。**

## 架构

```bash
Hermes Agent / Claude Code / Codex / Cursor …
        │
   MCP 网关（进程隔离，按需启动）
        │
   ├── bilibili-mcp   →  [A] 公开API → 自动降级 OpenCLI → 搜索引擎兜底
   ├── x-mcp          →  [B] OpenCLI → [Cookie失效] 搜索引擎兜底
   ├── xiaohongshu-mcp → [B] OpenCLI → [Cookie失效] 搜索引擎兜底
   └── reddit-mcp     →  [B] OpenCLI → [Cookie失效] 搜索引擎兜底
```

每个 MCP server 内部的 backend 检测和降级逻辑自包含，互不依赖。

## 四象限分类

| 象限 | 登录 | 数据清洗 | 示例 |
|------|------|---------|------|
| **A-1** | 无需登录 | 无需清洗（直接透传） | B站（公开 API） |
| **A-2** | 无需登录 | **需要清洗** | 模板就绪（知乎等） |
| **B-1** | **需要登录** | 无需清洗 | X, Reddit |
| **B-2** | **需要登录** | **需要清洗** | 小红书 |

每个 MCP 文件头标注 `CLASS` + `CLEAN`，`doctor()` 输出也包含这两个字段。

## 成品一览

| MCP | 类 | 文件 | 链路 |
|-----|-----|------|------|
| bilibili-mcp | A | `servers/bilibili_mcp.py` | 公开API → 自动降级 OpenCLI → 搜索引擎兜底 |
| x-mcp | B | `servers/x_mcp.py` | OpenCLI → [Cookie失效] 搜索引擎兜底 |
| xiaohongshu-mcp | B-2 | `servers/xiaohongshu_mcp.py` | OpenCLI → [Cookie失效] 搜索引擎兜底 |
| reddit-mcp | B | `servers/reddit_mcp.py` | OpenCLI → [Cookie失效] 搜索引擎兜底 |

每个 MCP server 提供 4-5 个 tool（搜索、详情、评论、状态诊断），均源自同一套模板。

## 一句话启动

下载这个项目后，告诉你的 AI Agent：

> 「帮我配置 EasyAgent-SocialMedia，项目在 [路径]/EasyAgent-SocialMedia。」

Agent 请按以下流程执行：

### Agent 安装流程

```
1. 读取本 README，理解项目结构
2. 询问用户：需要配置哪些平台？（如 B站、X、小红书、Reddit）
3. 根据用户选择的平台，按以下规则操作：
   - [A 类] 零配置，直接注册即可使用
   - [B 类] 先 npm install -g @jackwener/opencli（OpenCLI ），再注册
4. 全部注册完成后，调每个 MCP 的 doctor() 确认状态
5. 告知用户：
   ✅ B站等 A 类平台已就绪
   ⚠️ B 类平台需要用户装 Chrome 扩展 + 登录对应网站
   （提供 Chrome 扩展链接：https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk）
```

> **Agent 要点：** OpenCLI 的安装（`npm install -g @jackwener/opencli`）由你自动执行，不需要用户动手。
> 用户只需要做两件事：装 Chrome 扩展 + 登录网站。等用户说"装好了"时，调 doctor() 确认可用性。

### 注册命令参考

```bash
# Agent 自行执行，不需要用户手动输入
hermes mcp add bilibili-mcp --command python --args {项目路径}/servers/bilibili_mcp.py
hermes mcp add x-mcp --command python --args {项目路径}/servers/x_mcp.py
hermes mcp add xiaohongshu-mcp --command python --args {项目路径}/servers/xiaohongshu_mcp.py
hermes mcp add reddit-mcp --command python --args {项目路径}/servers/reddit_mcp.py
```

### 用户看到的体验

```
你: "帮我配置 EasyAgent-SocialMedia，项目在 ~/EasyAgent-SocialMedia"
Agent: "好的，你需要哪些平台？B站、X、小红书、Reddit？"
你: "B站和 X 吧"
Agent: "B站已就绪。正在安装 OpenCLI... 装好了。
       请装 Chrome 扩展：链接
       然后在 Chrome 里登录 x.com，登录完告诉我。"
你: "装好了"
Agent: 调 doctor() ✅ → "全部配置完成，现在可以用了。"
```

## 模板结构

```
template/mcp_template.py
├── 元信息（SERVER_NAME / CLASS / CLEAN / BACKENDS）
├── [B 系列] 配置管理（Cookie/Token 读取）
├── [象限 2] 数据清洗（_clean_item / _clean_items）
├── 后端检测（_check_* / _CHECK_FUNCS / doctor）
├── 业务函数（按象限选模式）
└── MCP 协议层（通用，不需改）
```

## 附：手动注册参考

以下命令仅供了解 Agent 在背后做了什么。正常使用你不需要手动执行它们——告诉 Agent 一句话，它会代劳。

```bash
# 注册 B站（零配置，直接可用）
hermes mcp add bilibili-mcp --command python --args /path/to/servers/bilibili_mcp.py

# 安装 OpenCLI（解锁 X + 小红书 + Reddit 的登录态）
npm install -g @jackwener/opencli
# 装 Chrome 扩展：https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk

# 注册其他平台
hermes mcp add x-mcp --command python --args /path/to/servers/x_mcp.py
hermes mcp add xiaohongshu-mcp --command python --args /path/to/servers/xiaohongshu_mcp.py
hermes mcp add reddit-mcp --command python --args /path/to/servers/reddit_mcp.py
```

### 扩展流程（从模板创建新 MCP）

1. 复制模板：`cp template/mcp_template.py servers/new_platform_mcp.py`
2. 设置 `CLASS`（A=零配置/B=需登录）、`CLEAN`（True=需清洗）、`BACKENDS`、`SEARCH_DOMAIN`
3. 实现业务函数（参考模板中的 A/B 模式示例）
4. 注册到网关（Agent 会自动执行这一步）

MCP 协议层（TOOLS / handle_call / main）所有平台通用，**复制即用，不需要改**。

## 对比 Agent-Reach

| 维度 | Agent-Reach | EasyAgent-SocialMedia |
|------|------------|------------|
| 架构 | 大一统框架 + 15 渠道 | **独立 MCP server，按需组合** |
| Token 开销 | ~30KB（skill + refs） | **0**（MCP 是独立进程） |
| 进程模型 | 单进程 | **多进程，隔离运行** |
| 依赖 | pip install agent-reach | **零框架依赖，只装底层 CLI** |
| 扩展 | 改项目代码 | **加一个 MCP server 配置** |
| 维护 | 等上游更新 | **各自独立，坏了修哪个** |

## Tools 参考

| Tool | 用途 | 适用 MCP |
|------|------|---------|
| `bilibili_search` / `bilibili_hot` / `bilibili_video` | 搜索 / 热门 / 详情 | bilibili-mcp |
| `twitter_search` / `twitter_tweet` / `twitter_user` | 搜索 / 读推文 / 用户 | x-mcp |
| `xiaohongshu_search` / `xiaohongshu_note` / `xiaohongshu_comments` | 搜索 / 笔记 / 评论 | xiaohongshu-mcp |
| `reddit_hot` / `reddit_search` / `reddit_post` / `reddit_subreddit` | 热门 / 搜索 / 阅读 / 版块 | reddit-mcp |
| `doctor` | 后端状态诊断 | 全部 |

## License

MIT
