[!] **前提条件**：此命令仅应在人工测试并提交代码后使用。

**AI 不得执行 git commit** - 只能读取历史（`git log`、`git status`、`git diff`）。

---

## 记录工作进度（简化版 - 只需 2 步）

### 步骤 1: 获取上下文

```bash
python .trellis/scripts/get_context.py
```

### 步骤 2: 一键添加会话

```bash
# 方法 1: 简单参数
python .trellis/scripts/add_session.py \
  --title "会话标题" \
  --commit "hash1,hash2" \
  --summary "完成工作的简要摘要"

# 方法 2: 通过 stdin 传递详细内容
cat << 'EOF' | python .trellis/scripts/add_session.py --title "标题" --commit "hash"
| 功能 | 描述 |
|---------|-------------|
| 新 API | 添加了用户认证端点 |
| 前端 | 更新了登录表单 |

**更新的文件**:
- `packages/api/modules/auth/router.ts`
- `apps/web/modules/auth/components/login-form.tsx`
EOF
```

**自动完成**：
- [OK] 将会话追加到 journal-N.md
- [OK] 自动检测行数，超过 2000 行时创建新文件
- [OK] 更新 index.md（总会话数 +1、最后活跃时间、行数统计、历史记录）

---

## 归档已完成的任务（如有）

如果本次会话完成了某个任务：

```bash
python .trellis/scripts/task.py archive <任务名称>
```

---

## 脚本命令参考

| 命令 | 用途 |
|---------|---------|
| `python get_context.py` | 获取所有上下文信息 |
| `python add_session.py --title "..." --commit "..."` | **一键添加会话（推荐）** |
| `python task.py create "<标题>" [--slug <名称>]` | 创建新任务目录 |
| `python task.py archive <名称>` | 归档已完成的任务 |
| `python task.py list` | 列出活跃任务 |
