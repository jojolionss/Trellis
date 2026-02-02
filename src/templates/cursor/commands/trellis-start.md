# 开始会话

初始化你的 AI 开发会话并开始处理任务。

---

## 操作类型

本文档中的操作分为以下类型：

| 标记 | 含义 | 执行者 |
|--------|---------|----------|
| `[AI]` | 由 AI 执行的 Bash 脚本或文件读取 | 你 (AI) |
| `[USER]` | 由用户执行的斜杠命令 | 用户 |

---

## 初始化

### 步骤 1: 理解 Trellis 工作流 `[AI]`

首先，阅读工作流指南以理解开发流程：

```bash
cat .trellis/workflow.md  # 开发流程、规范和快速入门指南
```

### 步骤 2: 获取当前状态 `[AI]`

```bash
python .trellis/scripts/get_context.py
```

返回内容包括：
- 开发者身份
- Git 状态（分支、未提交的更改）
- 最近的提交
- 活跃的任务
- 日志文件状态

### 步骤 3: 阅读项目规范 `[AI]`

根据即将进行的任务，阅读相应的规范文档：

**前端工作**：
```bash
cat .trellis/spec/frontend/index.md
```

**后端工作**：
```bash
cat .trellis/spec/backend/index.md
```

**跨层功能**：
```bash
cat .trellis/spec/guides/index.md
cat .trellis/spec/guides/cross-layer-thinking-guide.md
```

### 步骤 4: 检查活跃任务 `[AI]`

```bash
python .trellis/scripts/task.py list
```

如果是继续之前的工作，请查看任务文件。

### 步骤 5: 报告就绪状态并询问任务

输出摘要：

```markdown
## 会话已初始化

| 项目 | 状态 |
|------|--------|
| 开发者 | {name} |
| 分支 | {branch} |
| 未提交 | {count} 个文件 |
| 日志 | {file} ({lines}/2000 行) |
| 活跃任务 | {count} |

准备就绪。你想做什么？
```

---

## 处理任务

### 简单任务

1. 根据任务类型阅读相关规范 `[AI]`
2. 直接实现任务 `[AI]`
3. 提醒用户在提交前运行 `/trellis-finish-work` `[USER]`

### 复杂任务（多步骤任务）

#### 步骤 1: 创建任务 `[AI]`

```bash
python .trellis/scripts/task.py create "<标题>" --slug <名称>
```

#### 步骤 2: 实现并验证 `[AI]`

1. 阅读相关规范文档
2. 实现任务
3. 运行 lint 和类型检查

#### 步骤 3: 完成

1. 验证 typecheck 和 lint 通过 `[AI]`
2. 提醒用户测试
3. 提醒用户提交
4. 提醒用户运行 `/trellis-record-session` `[USER]`
5. 归档任务 `[AI]`：
   ```bash
   python .trellis/scripts/task.py archive <任务名称>
   ```

---

## 用户可用命令 `[USER]`

以下斜杠命令供用户使用（非 AI）：

| 命令 | 描述 |
|---------|-------------|
| `/trellis-start` | 开始开发会话（本命令） |
| `/trellis-before-frontend-dev` | 阅读前端规范 |
| `/trellis-before-backend-dev` | 阅读后端规范 |
| `/trellis-check-frontend` | 检查前端代码 |
| `/trellis-check-backend` | 检查后端代码 |
| `/trellis-check-cross-layer` | 跨层验证 |
| `/trellis-finish-work` | 提交前检查清单 |
| `/trellis-record-session` | 记录会话进度 |

---

## AI 执行的脚本 `[AI]`

| 脚本 | 用途 |
|--------|---------|
| `python task.py create "<标题>" [--slug <名称>]` | 创建任务目录 |
| `python task.py list` | 列出活跃任务 |
| `python task.py archive <名称>` | 归档任务 |
| `python get_context.py` | 获取会话上下文 |

---

## 会话结束提醒

**重要**：当任务或会话完成时，提醒用户：

> 在结束本会话前，请运行 `/trellis-record-session` 来记录我们完成的工作。
