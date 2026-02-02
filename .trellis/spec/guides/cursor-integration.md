# Cursor Integration Guide

> **Purpose**: How to effectively use Trellis within the Cursor IDE environment.

---

## Cursor vs Claude Code

Trellis is designed to work across different agentic environments.

| Feature | Cursor | Claude Code |
|---------|--------|-------------|
| **Interface** | IDE (VS Code fork) | CLI |
| **Context** | File context, terminal, diffs | Terminal output, read files |
| **Tools** | MCP (Model Context Protocol) | Built-in tools |
| **Best For** | Coding, debugging, complex edits | Quick tasks, scripting, orchestration |

## MCP Usage in Cursor

Cursor uses MCP (Model Context Protocol) to connect LLMs with local tools.

### Common Tools

- **`read_file`**: Read file contents.
- **`write_file`**: Create or overwrite files.
- **`str_replace`**: targeted edits (preferred over full rewrites).
- **`grep` / `glob`**: Search codebase.
- **`run_terminal_cmd`**: Execute shell commands.

### Best Practices

1. **Use `str_replace`**: Avoid rewriting large files to minimize context usage and risk of hallucinations.
2. **Check Context**: Use `get_agent_context` to load Trellis-specific instructions.
3. **Terminal**: Use terminal for git operations, running tests, etc.

## Cross-Platform Scripts

Trellis scripts in `.trellis/scripts/` are designed to be cross-platform.

- **Windows**: Use Git Bash or WSL to run `.sh` scripts.
- **Linux/Mac**: Native support.
- **Python**: Used for complex logic (e.g., `task.py`) to ensure cross-platform compatibility.

---

## Workflow Integration

1. **Start**: Use `.cursor/commands/trellis-start.md` (or just ask "start task").
2. **Dev**: Follow the loop (Plan -> Implement -> Check).
3. **Finish**: Use `.cursor/commands/trellis-finish-work.md`.
