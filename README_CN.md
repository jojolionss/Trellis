<p align="center">
<picture>
<source srcset="assets/trellis.png" media="(prefers-color-scheme: dark)">
<source srcset="assets/trellis.png" media="(prefers-color-scheme: light)">
<img src="assets/trellis.png" alt="Trellis Logo" width="500" style="image-rendering: -webkit-optimize-contrast; image-rendering: crisp-edges;">
</picture>
</p>

<p align="center">
<strong>Claude Code & Cursor 的一站式 AI 开发框架</strong><br/>
<sub>能解决以下问题</sub>
</p>

<p align="center">
<img src="assets/meme_zh.png" alt="AI Coding Meme" width="400" />
</p>

<p align="center">
<a href="https://www.npmjs.com/package/@mindfoldhq/trellis"><img src="https://img.shields.io/npm/v/@mindfoldhq/trellis.svg?style=flat-square&color=blue" alt="npm version" /></a>
<a href="https://github.com/mindfold-ai/Trellis/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-FSL-green.svg?style=flat-square" alt="license" /></a>
<a href="https://github.com/mindfold-ai/Trellis/stargazers"><img src="https://img.shields.io/github/stars/mindfold-ai/Trellis?style=flat-square&color=yellow" alt="stars" /></a>
<a href="https://discord.com/invite/tWcCZ3aRHc"><img src="https://img.shields.io/badge/Discord-Join-7289DA?style=flat-square&logo=discord&logoColor=white" alt="Discord" /></a>
</p>

<p align="center">
<a href="#快速开始">快速开始</a> •
<a href="#为什么要用-trellis">为什么要用 Trellis</a> •
<a href="#使用场景">使用场景</a> •
<a href="#工作原理">工作原理</a> •
<a href="#常见问题">常见问题</a>
</p>

## 为什么要用 Trellis？

| 功能 | 解决什么问题 |
| --- | --- |
| **自动注入** | 规范和工作流自动注入每次对话，写一次，永久生效 |
| **自更新规范库** | 最佳实践存在自更新的 spec 文件中，用得越多，AI 越懂你 |
| **并行会话** | 一个会话窗口可以在后台启动多个会话窗口,每个会话窗口都可以调用多个 Agent 同时工作，运行在各自独立的 worktree |
| **团队共享** | 团队共享规范，团队里有一个高人搞一版本好的规范，拉高全员的ai coding水平 |
| **会话持久化** | 工作记录持久化到仓库，AI 跨会话记住项目上下文, 不用每次再费劲告诉ai你的项目情况是什么 |

## 快速开始

### Claude Code

```bash
# 1. 全局安装
npm install -g @mindfoldhq/trellis@latest

# 2. 在项目目录初始化
trellis init -u your-name --claude

# 3. 启动 Claude Code，开始干活
```

### Cursor

**方式一：终端命令（推荐新用户）**

```bash
# 1. 全局安装
npm install -g @mindfoldhq/trellis@latest

# 2. 在项目目录初始化
trellis init -u your-name --cursor

# 3. 打开 Cursor，使用 /trellis-start 开始干活
```

**方式二：斜杠命令（无需终端）**

如果你已有 Trellis 的全局组件，可以直接在 Cursor 中使用：

```
/trellis-init
```

AI 会自动完成项目级配置：
- 初始化 `.trellis/` 目录结构（workflow/spec/workspace/tasks）
- 创建 `AGENTS.md`
- 创建 `.cursor/hooks.json` 以启用全局 hooks
- 复用已安装的全局组件（agents/commands/hooks/MCP server）

> `your-name` 是你的标识，会创建个人工作区 `.trellis/workspace/your-name/`

<p align="center">
<img src="assets/info.png" alt="Trellis 初始化示例" />
</p>

## use cases

### 教会你的 AI

规范写入文件里，Trellis 会帮你把项目规范,项目信息和工作流的知识自动注入给 AI ,不需要每次都给 AI 解释情况

<p align="center">
<img src="assets/usecase1.png" alt="教 AI - 教一次，永远生效" />
</p>

比如你定义了"组件用 TypeScript Props 接口、PascalCase 命名、函数式写法加 Hooks"，之后 AI 写新代码就会自动照做。

### 并行开发

用 `/trellis:parallel` 可以同时跑多个任务，每个任务在独立的 git worktree 里由调度Agent 自动指挥多个子 agent 完成，干完自己提 PR。

<p align="center">
<img src="assets/usecase2.png" alt="并行开发 - 多个功能同时推进" />
</p>

本地开发时，每个 worker 运行在独立的 worktree（物理隔离的目录），互不阻塞、互不干扰。一个功能完成就可以合并，不用等其他的。

### 自定义工作流

定义自定义的 skill 和 slash command ，为特定任务预加载上下文。

<p align="center">
<img src="assets/usecase3.png" alt="工作流 - 一个命令加载全部上下文" />
</p>

创建类似 `/trellis:before-frontend-dev` 的短命令，一键加载组件规范、检查最近改动、拉取测试模式、查看共享 hooks。

## 工作原理

### 项目结构

**Claude Code 结构：**

```
.trellis/
├── workflow.md              # 工作流指南（启动时自动注入）
├── worktree.yaml            # 多 Agent 配置（用于 /trellis:parallel）
├── spec/                    # 规范库
│   ├── frontend/            #   前端规范
│   ├── backend/             #   后端规范
│   └── guides/              #   决策与分析框架
├── workspace/{name}/        # 个人工作区
├── tasks/                   # 任务管理（进度跟踪等）
└── scripts/                 # 工具脚本

.claude/
├── settings.json            # Hook 配置
├── agents/                  # Agent 定义
│   ├── dispatch.md          #   调度 Agent（纯路由，不读规范）
│   ├── implement.md         #   实现 Agent
│   ├── check.md             #   检查 Agent
│   └── research.md          #   调研 Agent
├── commands/                # 斜杠命令
└── hooks/                   # Hook 脚本
    ├── session-start.py     #   启动时注入上下文
    ├── inject-subagent-context.py  #   给子 Agent 注入规范
    └── ralph-loop.py               #   质量控制循环
```

**Cursor 结构：**

```
.trellis/                    # 项目数据（与 Claude Code 共享）
├── workflow.md              # 工作流指南
├── spec/                    # 规范库
├── workspace/{name}/        # 个人工作区
├── tasks/                   # 任务管理
└── scripts/                 # 工具脚本

.cursor/                     # 项目级配置（仅 hooks.json）
└── hooks.json               # Hook 配置（启用项目钩子）

~/.cursor/                   # 全局配置（所有组件）
├── agents/                  # Agent 定义（全局共享）
│   ├── implement.md         #   实现 Agent
│   ├── check.md             #   检查 Agent
│   ├── debug.md             #   调试 Agent
│   ├── plan.md              #   计划 Agent
│   └── research.md          #   调研 Agent
├── commands/                # 斜杠命令（全局可用，已汉化）
│   ├── trellis-start.md
│   ├── trellis-parallel.md  #   多代理并行开发
│   ├── trellis-finish-work.md
│   └── ...                  #   共 13 个命令
├── hooks/                   # Hook 脚本（全局共享）
│   ├── session-start.py     #   启动时注入上下文
│   └── ralph-loop.py        #   质量控制循环
├── mcp-servers/
│   └── trellis-context/     # MCP 服务器（上下文注入 + 个人版功能）
│       ├── server.py        #   主服务器（含自动安装 mcp）
│       ├── skills_matcher.py #   Skills 触发词匹配器（match_skills 工具调用，默认不自动触发）
│       └── requirements.txt #   Python 依赖列表
└── mcp.json                 # MCP 注册
```

> **设计说明**：Cursor 采用全局安装，因为 agents/commands/hooks 对所有项目相同。
> 项目仅需 `.cursor/hooks.json` 启用钩子，操作时仍作用于当前项目的 `.trellis/` 数据。

### 上下文压缩（Context Compression）

Trellis 通过 JSONL 清单精确控制注入内容：每个任务可以提供 `spec.jsonl` 或各 Agent 的
`implement.jsonl` / `check.jsonl` / `debug.jsonl` / `research.jsonl` / `finish.jsonl`，
只加载当前任务相关的规范与文件，避免把整个仓库塞进上下文。

此外 MCP 提供 `mask_tool_results` 工具对长输出做 Observation Masking（`soft_trim` /
`summary` / `full_compress`），进一步减少 token 消耗。

### 工作流图

<p align="center">
<img src="assets/workflow.png" alt="Trellis 工作流图" />
</p>

## Cursor 适配说明

Trellis 完全支持 Cursor IDE，但由于架构差异，部分实现方式有所不同：

### Claude Code vs Cursor 对照表

| 功能 | Claude Code | Cursor | 说明 |
|------|-------------|--------|------|
| **初始化方式** | `trellis init --claude` | `trellis init --cursor` 或 `/trellis-init` | Cursor 支持斜杠命令一键初始化 |
| **子代理上下文** | `inject-subagent-context.py` | MCP `trellis-context` | Cursor 不支持 PreToolUse 修改子代理输入 |
| **质量控制循环** | `decision: block` | `followup_message` | Cursor 不支持阻止子代理停止 |
| **并行开发** | Git Worktree 物理隔离 | 子代理并行调用（5 模型） | 架构不同，效果等价 |
| **调度代理** | `dispatch.md` 子代理 | 主代理 + 全局 Rules | Cursor 主代理即调度器 |
| **配置位置** | `.claude/` 项目级 | `~/.cursor/` 全局 | agents/commands/hooks 全局安装，避免重复 |
| **项目激活** | 自动（有 .claude/ 即生效） | `.cursor/hooks.json` | 项目级 hooks.json 启用钩子 |
| **Skills 触发** | 手动 @ 引用 | 手动引用 / match_skills | 默认不自动触发（可手动调用 match_skills） |
| **依赖安装** | 手动 pip install | MCP 启动时自动安装 `mcp`（可禁用） | 其他依赖需手动安装 |

### Cursor 特有功能

1. **一键初始化（`/trellis-init`）**
   - 在 Cursor IDE 中输入 `/trellis-init`，AI 自动完成项目级配置
   - 创建 `.trellis/` 目录结构与 `AGENTS.md`
   - 创建 `.cursor/hooks.json`，复用全局 agents/commands/hooks/MCP server
   - 支持 Windows / macOS / Linux 跨平台

2. **完整上下文注入**
   - `session-start.py` 会话启动时注入**完整内容**（workflow.md、spec index、指令）
   - 与原版 Claude Code 行为一致，无需手动调用 `/trellis-start`

3. **MCP 上下文注入**
   - 子代理启动时调用 `trellis-context.get_agent_context()` 获取规范
   - 支持 `implement`、`check`、`debug`、`research`、`plan` 五种代理类型
   - `is_finish=true` 参数支持轻量级 finish 阶段上下文

4. **上下文压缩（Observation Masking）**
   - MCP 工具 `mask_tool_results` 可压缩工具输出，减少上下文占用
   - 支持 `soft_trim` / `summary` / `full_compress` 策略，可指定 head/tail 长度

5. **个人版（SOUL / IDENTITY / Memory）**
   - `SOUL.md` / `IDENTITY.md` 自动创建并注入到 agent context
   - `memory_save` / `memory_search` / `memory_flush` 提供长期记忆
   - 记忆存储在 `~/.trellis/memory/`，跨项目可复用

6. **Ralph Loop（质量控制循环）**
   - 使用 `followup_message` 机制触发主代理重新调度 Check 代理
   - 效果与原版一致：检查不通过则循环，直到全部标记出现

7. **多模型并行代理**
   - Check/Debug/Research 阶段支持 5 个模型同时运行（Opus、Sonnet、GPT-XHigh、GPT-Codex、Gemini-Pro）
   - 发现型任务并行执行，提高效率和覆盖率

8. **斜杠命令格式**
   - Claude Code: `/trellis:start`
   - Cursor: `/trellis-start`
   - 所有命令已汉化

9. **子代理汉化**
   - 所有 Agent 定义（implement、check、debug、research、plan）已翻译为中文
   - 保留 `Please respond in English.` 确保输出质量

### 个人版（Personal Edition）

个人版能力为用户级配置，存放在 `~/.trellis/`，不会进入项目仓库：

- `SOUL.md`：定义核心价值观、决策原则和偏好（MCP 首次启动会自动生成模板）
- `IDENTITY.md`：定义角色/专长画像，会在 `get_agent_context` 时注入
- `memory/`：长期记忆目录（`decisions.jsonl` / `preferences.jsonl` / `patterns.jsonl` + `index.json`）

可用工具：

- `memory_save`：保存重要决策/偏好/模式
- `memory_search`：检索历史记忆
- `memory_flush`：把会话摘要写入长期记忆

### Cursor 快速上手

```bash
# 初始化项目
trellis init -u your-name --cursor

# 或只初始化 Cursor（已有 .trellis/）
trellis init --cursor
```

初始化后使用：

```
/trellis-start          # 开始开发会话
/trellis-finish-work    # 提交前检查
/trellis-record-session # 记录会话进度
```

## 路线图

- [ ] **Skills 触发词系统** — 自动匹配与注入（计划中）
- [x] **一键初始化** — `/trellis-init` 斜杠命令自动安装 ✅
- [x] **多模型并行代理** — Check/Debug/Research 5 模型并行 ✅
- [ ] **更好的代码审查** — 更完善的自动化审查流程
- [ ] **Skill 包** — 预置工作流包，即插即用
- [ ] **更广泛的工具支持** — Cursor、OpenCode、Codex 集成
- [ ] **更强的会话连续性** — 自动保存全会话历史
- [ ] **可视化并行会话** — 实时查看每个 Agent 的进度

## 常见问题

<details>
<summary><strong>为什么用 Trellis 而不是 Skills？</strong></summary>

Skills 是可选的——AI 可能跳过，导致质量不稳定。Trellis 通过 Hook 注入**强制**执行规范：不是"可以用"而是"必须用"。把随机性关进笼子里，质量不会随时间退化。

</details>

<details>
<summary><strong>spec 文件是手写还是让 AI 写？</strong></summary>

大多数时候让 AI 来——你只要说"我们用 Zustand，不用 Redux"，它就会自动创建 spec 文件。但当你有 AI 自己想不到的架构洞察时，就得你来写了。能把团队踩过的坑教给 AI 并且拉高团队开发水平,这就是你不会被 AI 取代的原因。

</details>

<details>
<summary><strong>这和 <code>CLAUDE.md</code> / <code>AGENTS.md</code> / <code>.cursorrules</code> 有什么区别？</strong></summary>

那些是大一统文件——AI 每次都要读全部内容。Trellis 用**分层架构**做上下文压缩：只加载当前任务相关的规范。工程规范应该优雅分层，而不是堆成一坨。

</details>

<details>
<summary><strong>多人协作会冲突吗？</strong></summary>

不会。每人有自己的空间 `.trellis/workspace/{name}/`。

</details>

<details>
<summary><strong>AI 怎么知道之前的对话内容？</strong></summary>

每次结束对话时用 `/trellis:record-session`（Claude Code）或 `/trellis-record-session`（Cursor），AI 会把会话摘要写入 `.trellis/workspace/{name}/journal-N.md`，并在 `index.md` 建立索引。下次 `/trellis:start` 时，AI 会自动读取最近的 journal 和 git 信息，恢复上下文。所以理论上直接扒每天的 journal 文件就能当你的工作日报提交了🤣。

</details>

<details>
<summary><strong>Cursor 和 Claude Code 用的是同一套配置吗？</strong></summary>

`.trellis/` 目录是共享的——包含规范、工作区、任务等。但 AI 工具配置是分开的：
- Claude Code 用 `.claude/`（项目级 agents、hooks、commands）
- Cursor 用 `~/.cursor/`（全局 agents、hooks、commands）+ 项目级 `.cursor/hooks.json`

你可以同时初始化两者：`trellis init -u name --claude --cursor`

Cursor 采用全局安装是因为这些组件对所有项目相同，避免重复。项目只需 `.cursor/hooks.json` 启用钩子即可。

</details>

<details>
<summary><strong>Cursor 的 Ralph Loop 和原版有什么区别？</strong></summary>

功能等价，实现不同：
- **原版**：用 `decision: block` 阻止 Check 代理停止，强制继续检查
- **Cursor**：用 `followup_message` 通知主代理重新调度 Check 代理

最终效果一样：检查不通过就循环，直到所有完成标记出现或达到最大次数（默认 5 次）。

</details>

<details>
<summary><strong>为什么 Cursor 没有 dispatch.md？</strong></summary>

Cursor 的主代理（Agent 模式）本身就是调度器，不需要单独的 dispatch 子代理。调度规则放在项目的 `AGENTS.md` 或全局 Rules 中。这样更简洁，也避免了"子代理调用子代理"的限制问题。

</details>

<details>
<summary><strong><code>/trellis-init</code> 和 <code>trellis init --cursor</code> 有什么区别？</strong></summary>

功能等价，使用场景不同：
- **`trellis init --cursor`**：在终端运行，需要先安装 npm 包
- **`/trellis-init`**：在 Cursor IDE 中输入，AI 自动执行所有步骤

如果你已有其他项目的 Trellis 配置，可以直接用 `/trellis-init`，不需要再装 npm。

</details>

<details>
<summary><strong>Skills 怎么用？</strong></summary>

目前 trellis-context 默认不做自动匹配，但已内置 `match_skills` 工具，
可做关键词/正则/文件模式匹配；也可以继续手动引用 Skill。

Skill 文件可以放在 `~/.cursor/skills/`（用户级）或 `.trellis/skills/`（项目级）。

</details>

<details>
<summary><strong>MCP Server 的依赖是如何安装的？</strong></summary>

`server.py` 会在启动时调用 `_ensure_dependencies()`，默认只尝试安装缺失的 `mcp`
（可通过 `TRELLIS_MCP_NO_AUTO_INSTALL=1` 禁用）。

依赖清单在 `~/.cursor/mcp-servers/trellis-context/requirements.txt`。
如果要使用 `match_skills`（`skills_matcher.py`）的 YAML/regex 能力，
可按需安装 `pyyaml` / `regex`。

</details>

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=mindfold-ai/Trellis&type=Date)](https://star-history.com/#mindfold-ai/Trellis&Date)

## 详细文档

- [完整使用指南](docs/guide-zh.md) — 系统架构、工作流、CLI 命令参考
- [用 K8s 理解 Trellis](docs/use-k8s-to-know-trellis-zh.md) — 如果你熟悉 Kubernetes，这篇文章可以帮你快速理解设计思想

## 社区

- [Discord](https://discord.com/invite/tWcCZ3aRHc) — 加入讨论
- [GitHub Issues](https://github.com/mindfold-ai/Trellis/issues) — 报告 Bug & 提功能建议
- 微信群 — 扫码加入

<p align="center">
<img src="assets/wx_link.jpg" alt="微信群二维码" width="200" />
</p>

<p align="center">
<a href="https://github.com/mindfold-ai/Trellis/blob/main/LICENSE">FSL License</a> •
Made with care by <a href="https://github.com/mindfold-ai">Mindfold</a>
</p>

<p align="center">
<sub>觉得 Trellis 有用？欢迎点个 ⭐</sub>
</p>
