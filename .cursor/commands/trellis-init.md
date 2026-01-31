# Trellis 项目初始化

初始化当前项目为 Trellis 工作流项目。

## 参数

- `$DEVELOPER_NAME` - 开发者名字（用于 workspace 目录）

## 执行步骤

### 1. 创建目录结构

```
.trellis/
├── workflow.md          # 工作流指南
├── .developer           # 开发者信息
├── .current-task        # 当前任务（空）
├── spec/
│   ├── frontend/
│   │   └── index.md
│   ├── backend/
│   │   └── index.md
│   └── guides/
│       └── index.md
├── workspace/
│   └── $DEVELOPER_NAME/
│       └── tasks/
└── tasks/
    └── archive/
```

### 2. 创建 workflow.md

```markdown
# Project Workflow

## Development Flow

1. **Plan** - Use plan agent to create task with requirements
2. **Implement** - Use implement agent to write code
3. **Check** - Use check agent to verify quality
4. **Debug** - Use debug agent to fix issues (if any)
5. **Finish** - Create PR and archive task

## Task Management

- Current task: `.trellis/.current-task`
- Task directory: `.trellis/tasks/` or `.trellis/workspace/<dev>/tasks/`

## Agents

Call agents via Task tool:
- `implement` - Code implementation
- `check` - Quality verification
- `debug` - Issue fixing
- `research` - Code search
- `plan` - Task planning

Each agent should call `trellis-context.get_agent_context` first.
```

### 3. 创建 .developer 文件

```
name=$DEVELOPER_NAME
initialized_at=<current ISO timestamp>
```

### 4. 创建 spec index 文件

**frontend/index.md:**
```markdown
# Frontend Development Guide

## Structure
- Components in `src/components/`
- Pages in `src/pages/` or `src/app/`
- Hooks in `src/hooks/`

## Conventions
- Use TypeScript
- Follow existing patterns
- Keep components small and focused
```

**backend/index.md:**
```markdown
# Backend Development Guide

## Structure
- API routes in `src/api/` or `src/routes/`
- Services in `src/services/`
- Models in `src/models/`

## Conventions
- Use TypeScript
- Handle errors properly
- Add input validation
```

**guides/index.md:**
```markdown
# Development Guides

## Thinking Process
1. Understand requirements fully
2. Plan before coding
3. Verify after implementing

## Quality Standards
- No lint errors
- No type errors
- Follow existing patterns
```

### 5. 复制 Cursor 命令

从模板复制以下命令到 `.cursor/commands/`:
- trellis-start.md
- trellis-finish-work.md
- trellis-check-backend.md
- trellis-check-frontend.md
- trellis-check-cross-layer.md
- 等其他 trellis-*.md 命令

如果命令已存在于全局 `~/.cursor/commands/`，直接复制过来。

### 6. 创建 AGENTS.md

在项目根目录创建 `AGENTS.md`，包含调度规则：

```markdown
# Multi-Agent Dispatch Rules

## Agent Selection

| Task Type | Agent | When to Use |
|-----------|-------|-------------|
| Implementation | implement | Writing new code, adding features |
| Quality Check | check | Verifying code quality, running tests |
| Bug Fixing | debug | Fixing errors, debugging issues |
| Research | research | Finding code, understanding patterns |
| Planning | plan | Creating new tasks, breaking down requirements |

## Workflow

1. For new features: plan → implement → check
2. For bugs: debug → check
3. For research: research only

## Agent Invocation

Use Task tool with appropriate subagent_type.
Each agent will call MCP `trellis-context.get_agent_context` for context.
```

### 7. 输出完成信息

```
✅ Trellis 项目初始化完成！

开发者: $DEVELOPER_NAME
目录结构: .trellis/

下一步:
1. 运行 /trellis-start 开始工作
2. 或直接描述你的任务，我会调度合适的代理
```

---

## 注意事项

- 如果 `.trellis/` 已存在，询问是否覆盖
- 全局组件（agents, hooks, MCP）已安装在 `~/.cursor/`，无需再安装
- 只创建项目级配置
