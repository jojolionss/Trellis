#!/usr/bin/env python3
"""
Trellis Context MCP Server

Provides context injection for Cursor subagents.
Replaces Claude Code's PreToolUse hook + updatedInput mechanism.

Tools:
- get_agent_context: Get complete context for a specific agent type
- get_current_task: Get current task information
- set_current_task: Set current task path
- update_phase: Update task.json current_phase
- list_tasks: List all tasks
- create_task: Create a new task

Usage in subagent prompt:
"First, call trellis-context MCP's get_agent_context tool with your agent type,
then follow the returned context to complete your task."
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# =============================================================================
# Path Constants
# =============================================================================

DIR_WORKFLOW = ".trellis"
DIR_WORKSPACE = "workspace"
DIR_TASKS = "tasks"
DIR_SPEC = "spec"
FILE_CURRENT_TASK = ".current-task"
FILE_TASK_JSON = "task.json"
FILE_DEVELOPER = ".developer"

# Agent types
AGENT_IMPLEMENT = "implement"
AGENT_CHECK = "check"
AGENT_DEBUG = "debug"
AGENT_RESEARCH = "research"
AGENT_PLAN = "plan"

AGENTS_ALL = (AGENT_IMPLEMENT, AGENT_CHECK, AGENT_DEBUG, AGENT_RESEARCH, AGENT_PLAN)
AGENTS_REQUIRE_TASK = (AGENT_IMPLEMENT, AGENT_CHECK, AGENT_DEBUG)
AGENTS_NO_PHASE_UPDATE = {"debug", "research", "plan"}

# Phase mapping for auto phase update
PHASE_MAPPING = {
    "implement": 1,
    "check": 2,
    "finish": 3,
    "create-pr": 4,
}


# =============================================================================
# Helper Functions (from inject-subagent-context.py)
# =============================================================================

def find_trellis_root(start_path: str = None) -> str | None:
    """Find directory containing .trellis/ from start_path upwards
    
    Search order:
    1. Explicit start_path parameter
    2. TRELLIS_PROJECT_ROOT environment variable
    3. CURSOR_WORKSPACE_ROOT environment variable (Cursor's workspace)
    4. Current working directory (fallback)
    """
    # Priority 1: Explicit parameter
    if start_path:
        path = Path(start_path).resolve()
        if (path / DIR_WORKFLOW).exists():
            return str(path)
    
    # Priority 2: Environment variable (set by hooks or user)
    env_root = os.environ.get("TRELLIS_PROJECT_ROOT")
    if env_root:
        path = Path(env_root).resolve()
        if (path / DIR_WORKFLOW).exists():
            return str(path)
    
    # Priority 3: Cursor workspace (may be set by Cursor)
    cursor_workspace = os.environ.get("CURSOR_WORKSPACE_ROOT")
    if cursor_workspace:
        path = Path(cursor_workspace).resolve()
        if (path / DIR_WORKFLOW).exists():
            return str(path)
    
    # Priority 4: Search upward from CWD
    search_start = start_path or os.getcwd()
    current = Path(search_start).resolve()
    while current != current.parent:
        if (current / DIR_WORKFLOW).exists():
            return str(current)
        current = current.parent
    
    return None


def get_current_task_path(root: str) -> str | None:
    """Read current task directory path from .trellis/.current-task"""
    current_task_file = os.path.join(root, DIR_WORKFLOW, FILE_CURRENT_TASK)
    if not os.path.exists(current_task_file):
        return None
    try:
        with open(current_task_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else None
    except Exception:
        return None


def get_developer_name(root: str) -> str | None:
    """Read developer name from .trellis/.developer"""
    developer_file = os.path.join(root, DIR_WORKFLOW, FILE_DEVELOPER)
    if not os.path.exists(developer_file):
        return None
    try:
        with open(developer_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None


def read_file_content(base_path: str, file_path: str) -> str | None:
    """Read file content, return None if file doesn't exist"""
    full_path = os.path.join(base_path, file_path)
    if os.path.exists(full_path) and os.path.isfile(full_path):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None
    return None


def read_directory_contents(base_path: str, dir_path: str, max_files: int = 20) -> list[tuple[str, str]]:
    """Read all .md files in a directory"""
    full_path = os.path.join(base_path, dir_path)
    if not os.path.exists(full_path) or not os.path.isdir(full_path):
        return []
    
    results = []
    try:
        md_files = sorted([
            f for f in os.listdir(full_path)
            if f.endswith(".md") and os.path.isfile(os.path.join(full_path, f))
        ])
        for filename in md_files[:max_files]:
            file_full_path = os.path.join(full_path, filename)
            relative_path = os.path.join(dir_path, filename)
            try:
                with open(file_full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    results.append((relative_path, content))
            except Exception:
                continue
    except Exception:
        pass
    return results


def read_jsonl_entries(base_path: str, jsonl_path: str) -> list[tuple[str, str]]:
    """Read all file/directory contents referenced in jsonl file"""
    full_path = os.path.join(base_path, jsonl_path)
    if not os.path.exists(full_path):
        return []
    
    results = []
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    file_path = item.get("file") or item.get("path")
                    entry_type = item.get("type", "file")
                    
                    if not file_path:
                        continue
                    
                    if entry_type == "directory":
                        dir_contents = read_directory_contents(base_path, file_path)
                        results.extend(dir_contents)
                    else:
                        content = read_file_content(base_path, file_path)
                        if content:
                            results.append((file_path, content))
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return results


def get_base_agent_context(root: str, task_dir: str, agent_type: str) -> str:
    """Get base context from jsonl files"""
    context_parts = []
    
    agent_jsonl = f"{task_dir}/{agent_type}.jsonl"
    agent_entries = read_jsonl_entries(root, agent_jsonl)
    
    if not agent_entries:
        agent_entries = read_jsonl_entries(root, f"{task_dir}/spec.jsonl")
    
    for file_path, content in agent_entries:
        context_parts.append(f"=== {file_path} ===\n{content}")
    
    return "\n\n".join(context_parts)


def get_implement_context(root: str, task_dir: str) -> str:
    """Complete context for Implement Agent"""
    context_parts = []
    
    base_context = get_base_agent_context(root, task_dir, "implement")
    if base_context:
        context_parts.append(base_context)
    
    prd_content = read_file_content(root, f"{task_dir}/prd.md")
    if prd_content:
        context_parts.append(f"=== {task_dir}/prd.md (Requirements) ===\n{prd_content}")
    
    info_content = read_file_content(root, f"{task_dir}/info.md")
    if info_content:
        context_parts.append(f"=== {task_dir}/info.md (Technical Design) ===\n{info_content}")
    
    return "\n\n".join(context_parts)


def get_check_context(root: str, task_dir: str) -> str:
    """Complete context for Check Agent"""
    context_parts = []
    
    check_entries = read_jsonl_entries(root, f"{task_dir}/check.jsonl")
    
    if check_entries:
        for file_path, content in check_entries:
            context_parts.append(f"=== {file_path} ===\n{content}")
    else:
        # Try Cursor paths first, then fall back to Claude Code paths
        check_files = [
            (".cursor/commands/trellis-finish-work.md", "Finish work checklist"),
            (".cursor/commands/trellis-check-cross-layer.md", "Cross-layer check spec"),
            (".cursor/commands/trellis-check-backend.md", "Backend check spec"),
            (".cursor/commands/trellis-check-frontend.md", "Frontend check spec"),
        ]
        # Fallback to Claude Code paths if Cursor paths not found
        claude_check_files = [
            (".claude/commands/trellis/finish-work.md", "Finish work checklist"),
            (".claude/commands/trellis/check-cross-layer.md", "Cross-layer check spec"),
            (".claude/commands/trellis/check-backend.md", "Backend check spec"),
            (".claude/commands/trellis/check-frontend.md", "Frontend check spec"),
        ]
        # Try Cursor paths first
        found_any = False
        for file_path, description in check_files:
            content = read_file_content(root, file_path)
            if content:
                context_parts.append(f"=== {file_path} ({description}) ===\n{content}")
                found_any = True
        
        # Fall back to Claude Code paths if nothing found
        if not found_any:
            for file_path, description in claude_check_files:
                content = read_file_content(root, file_path)
                if content:
                    context_parts.append(f"=== {file_path} ({description}) ===\n{content}")
        
        spec_entries = read_jsonl_entries(root, f"{task_dir}/spec.jsonl")
        for file_path, content in spec_entries:
            context_parts.append(f"=== {file_path} (Dev spec) ===\n{content}")
    
    prd_content = read_file_content(root, f"{task_dir}/prd.md")
    if prd_content:
        context_parts.append(f"=== {task_dir}/prd.md (Requirements) ===\n{prd_content}")
    
    return "\n\n".join(context_parts)


def get_debug_context(root: str, task_dir: str) -> str:
    """Complete context for Debug Agent"""
    context_parts = []
    
    debug_entries = read_jsonl_entries(root, f"{task_dir}/debug.jsonl")
    
    if debug_entries:
        for file_path, content in debug_entries:
            context_parts.append(f"=== {file_path} ===\n{content}")
    else:
        spec_entries = read_jsonl_entries(root, f"{task_dir}/spec.jsonl")
        for file_path, content in spec_entries:
            context_parts.append(f"=== {file_path} (Dev spec) ===\n{content}")
        
        # Try Cursor paths first, then fall back to Claude Code paths
        check_files = [
            (".cursor/commands/trellis-check-backend.md", "Backend check spec"),
            (".cursor/commands/trellis-check-frontend.md", "Frontend check spec"),
            (".cursor/commands/trellis-check-cross-layer.md", "Cross-layer check spec"),
        ]
        found_any = False
        for file_path, description in check_files:
            content = read_file_content(root, file_path)
            if content:
                context_parts.append(f"=== {file_path} ({description}) ===\n{content}")
                found_any = True
        
        # Fall back to Claude Code paths
        if not found_any:
            claude_check_files = [
                (".claude/commands/trellis/check-backend.md", "Backend check spec"),
                (".claude/commands/trellis/check-frontend.md", "Frontend check spec"),
                (".claude/commands/trellis/check-cross-layer.md", "Cross-layer check spec"),
            ]
            for file_path, description in claude_check_files:
                content = read_file_content(root, file_path)
                if content:
                    context_parts.append(f"=== {file_path} ({description}) ===\n{content}")
    
    codex_output = read_file_content(root, f"{task_dir}/codex-review-output.txt")
    if codex_output:
        context_parts.append(f"=== {task_dir}/codex-review-output.txt (Review Results) ===\n{codex_output}")
    
    return "\n\n".join(context_parts)


def get_finish_context(root: str, task_dir: str) -> str:
    """
    Complete context for Finish phase (final lightweight check before PR)
    
    Read order:
    1. All files in finish.jsonl (if exists)
    2. Fallback to finish-work.md only (lightweight final check)
    3. prd.md (for verifying requirements are met)
    """
    context_parts = []
    
    # 1. Try finish.jsonl first
    finish_entries = read_jsonl_entries(root, f"{task_dir}/finish.jsonl")
    
    if finish_entries:
        for file_path, content in finish_entries:
            context_parts.append(f"=== {file_path} ===\n{content}")
    else:
        # Fallback: only finish-work.md (lightweight)
        # Try Cursor path first
        finish_work_paths = [
            ".cursor/commands/trellis-finish-work.md",
            ".claude/commands/trellis/finish-work.md",
        ]
        for finish_path in finish_work_paths:
            finish_work = read_file_content(root, finish_path)
            if finish_work:
                context_parts.append(f"=== {finish_path} (Finish checklist) ===\n{finish_work}")
                break
    
    # 2. Requirements document (for verifying requirements are met)
    prd_content = read_file_content(root, f"{task_dir}/prd.md")
    if prd_content:
        context_parts.append(f"=== {task_dir}/prd.md (Requirements - verify all met) ===\n{prd_content}")
    
    return "\n\n".join(context_parts)


def get_plan_context(root: str) -> str:
    """Context for Plan Agent"""
    context_parts = []
    
    # Project structure overview
    spec_path = f"{DIR_WORKFLOW}/{DIR_SPEC}"
    project_structure = f"""## Project Structure for Planning

```
{spec_path}/
├── frontend/    # Frontend standards (check before frontend tasks)
├── backend/     # Backend standards (check before backend tasks)
└── guides/      # Cross-layer thinking guides
```

## Planning Guidelines

1. Understand the requirement fully before creating a task
2. Check if similar functionality exists in the codebase
3. Break down complex features into phases
4. Create task with clear title and requirements (prd.md)
"""
    context_parts.append(project_structure)
    
    # Read guides index for planning context
    guides_index = read_file_content(root, f"{DIR_WORKFLOW}/{DIR_SPEC}/guides/index.md")
    if guides_index:
        context_parts.append(f"## Available Guides\n\n{guides_index}")
    
    return "\n\n".join(context_parts)


def get_research_context(root: str, task_dir: str | None) -> str:
    """Context for Research Agent"""
    context_parts = []
    
    spec_path = f"{DIR_WORKFLOW}/{DIR_SPEC}"
    project_structure = f"""## Project Spec Directory Structure

```
{spec_path}/
├── frontend/    # Frontend standards
├── backend/     # Backend standards
└── guides/      # Thinking guides

{DIR_WORKFLOW}/big-question/  # Known issues and pitfalls
```

## Search Tips

- Spec files: `{spec_path}/**/*.md`
- Code search: Use Glob and Grep tools
- External search: Use web search tools"""
    
    context_parts.append(project_structure)
    
    if task_dir:
        research_entries = read_jsonl_entries(root, f"{task_dir}/research.jsonl")
        if research_entries:
            context_parts.append("\n## Additional Search Context\n")
            for file_path, content in research_entries:
                context_parts.append(f"=== {file_path} ===\n{content}")
    
    return "\n\n".join(context_parts)


def build_agent_prompt(agent_type: str, context: str) -> str:
    """Build complete prompt for agent"""
    prompts = {
        AGENT_IMPLEMENT: f"""# Implement Agent Context

You are the Implement Agent. Your context has been loaded.

## Your Context

{context}

---

## Workflow

1. **Understand specs** - Read all dev specs above
2. **Understand requirements** - Read prd.md and info.md
3. **Implement feature** - Follow specs and design
4. **Self-check** - Verify code quality

## Constraints

- Do NOT execute git commit
- Follow all dev specs
- Report modified/created files when done""",

        AGENT_CHECK: f"""# Check Agent Context

You are the Check Agent. Your context has been loaded.

## Your Context

{context}

---

## Workflow

1. **Get changes** - Run `git diff --name-only` and `git diff`
2. **Check against specs** - Verify code follows guidelines
3. **Self-fix** - Fix issues directly, don't just report
4. **Run verification** - Run lint and typecheck

## Constraints

- Fix issues yourself
- Execute complete checklist
- Pay attention to impact analysis""",

        AGENT_DEBUG: f"""# Debug Agent Context

You are the Debug Agent. Your context has been loaded.

## Your Context

{context}

---

## Workflow

1. **Understand issues** - Analyze reported issues
2. **Locate code** - Find positions needing fixes
3. **Fix against specs** - Fix following dev specs
4. **Verify fixes** - Run typecheck

## Constraints

- Do NOT execute git commit
- Run typecheck after each fix
- Report which issues were fixed""",

        AGENT_RESEARCH: f"""# Research Agent Context

You are the Research Agent. Your context has been loaded.

## Your Context

{context}

---

## Workflow

1. **Understand query** - Determine search type and scope
2. **Plan search** - List search steps
3. **Execute search** - Run searches in parallel
4. **Organize results** - Output structured report

## Constraints

- Only describe what exists
- Do not suggest improvements unless asked
- Do not modify any files""",

        AGENT_PLAN: f"""# Plan Agent Context

You are the Plan Agent. Your context has been loaded.

## Your Context

{context}

---

## Workflow

1. **Understand requirement** - Analyze what user wants
2. **Check existing code** - Search for similar functionality
3. **Create task** - Use task.py to create task directory
4. **Write prd.md** - Document requirements clearly
5. **Configure context** - Set up jsonl files for agents

## Constraints

- Do NOT implement code directly
- Create clear, actionable requirements
- Break complex features into phases
- If requirement is unclear, create REJECTED.md and explain""",

        "finish": f"""# Finish Phase Context

This is the FINAL lightweight check before creating PR.

## Your Context

{context}

---

## Workflow

1. **Verify requirements** - Check prd.md requirements are all met
2. **Quick sanity check** - No obvious issues
3. **Ready for PR** - Confirm code is ready for review

## Constraints

- This is a LIGHTWEIGHT check, not full code review
- Focus on requirement completion, not code style
- Output: Ready for PR / Not ready (with reasons)"""
    }
    
    return prompts.get(agent_type, f"# Agent Context\n\n{context}")


# =============================================================================
# MCP Server
# =============================================================================

app = Server("trellis-context")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="get_agent_context",
            description="Get complete context for a specific agent type (implement, check, debug, research, plan). Call this FIRST when starting as a subagent.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_type": {
                        "type": "string",
                        "description": "Agent type: implement, check, debug, research, or plan",
                        "enum": ["implement", "check", "debug", "research", "plan"]
                    },
                    "is_finish": {
                        "type": "boolean",
                        "description": "For check agent only: if true, use lightweight finish context instead of full check context"
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Optional project root path. If not provided, searches upward from cwd."
                    }
                },
                "required": ["agent_type"]
            }
        ),
        Tool(
            name="get_current_task",
            description="Get current task information including task.json content and task directory path",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {
                        "type": "string",
                        "description": "Optional project root path"
                    }
                }
            }
        ),
        Tool(
            name="set_current_task",
            description="Set the current task by writing to .trellis/.current-task",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_path": {
                        "type": "string",
                        "description": "Relative path to task directory (e.g., .trellis/workspace/admin/tasks/01-31-feature)"
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Optional project root path"
                    }
                },
                "required": ["task_path"]
            }
        ),
        Tool(
            name="update_phase",
            description="Update current_phase in task.json",
            inputSchema={
                "type": "object",
                "properties": {
                    "phase": {
                        "type": "integer",
                        "description": "New phase number"
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Optional project root path"
                    }
                },
                "required": ["phase"]
            }
        ),
        Tool(
            name="list_tasks",
            description="List all tasks in the workspace",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {
                        "type": "string",
                        "description": "Optional project root path"
                    }
                }
            }
        ),
        Tool(
            name="create_task",
            description="Create a new task directory with task.json",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Task name/slug"
                    },
                    "title": {
                        "type": "string",
                        "description": "Task title/description"
                    },
                    "dev_type": {
                        "type": "string",
                        "description": "Development type: frontend, backend, or fullstack",
                        "enum": ["frontend", "backend", "fullstack"]
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Optional project root path"
                    }
                },
                "required": ["name", "title"]
            }
        ),
        Tool(
            name="get_workflow",
            description="Get the workflow.md content",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_root": {
                        "type": "string",
                        "description": "Optional project root path"
                    }
                }
            }
        ),
        Tool(
            name="get_spec_index",
            description="Get spec index files (frontend/index.md, backend/index.md, guides/index.md)",
            inputSchema={
                "type": "object",
                "properties": {
                    "spec_type": {
                        "type": "string",
                        "description": "Spec type: frontend, backend, guides, or all",
                        "enum": ["frontend", "backend", "guides", "all"]
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Optional project root path"
                    }
                },
                "required": ["spec_type"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls"""
    
    project_root = arguments.get("project_root") or find_trellis_root()
    
    if not project_root:
        return [TextContent(
            type="text",
            text=f"Error: Could not find .trellis directory.\n\n"
                 f"Searched: CWD={os.getcwd()}\n\n"
                 f"Solutions:\n"
                 f"1. Pass project_root parameter: get_agent_context(agent_type=\"...\", project_root=\"/path/to/project\")\n"
                 f"2. Set env: TRELLIS_PROJECT_ROOT=/path/to/project\n"
                 f"3. Run from a Trellis-initialized project directory"
        )]
    
    if name == "get_agent_context":
        agent_type = arguments.get("agent_type")
        is_finish = arguments.get("is_finish", False)
        
        if agent_type not in AGENTS_ALL:
            return [TextContent(type="text", text=f"Error: Invalid agent_type. Must be one of: {AGENTS_ALL}")]
        
        task_dir = get_current_task_path(project_root)
        
        if agent_type in AGENTS_REQUIRE_TASK and not task_dir:
            return [TextContent(
                type="text",
                text=f"Error: No current task set. Use set_current_task or create_task first.\n\nFor {agent_type} agent, a task must be active."
            )]
        
        if task_dir and not os.path.exists(os.path.join(project_root, task_dir)):
            return [TextContent(type="text", text=f"Error: Task directory not found: {task_dir}")]
        
        # Get context based on agent type
        if agent_type == AGENT_IMPLEMENT:
            context = get_implement_context(project_root, task_dir)
        elif agent_type == AGENT_CHECK:
            # Support finish phase (lightweight check before PR)
            if is_finish:
                context = get_finish_context(project_root, task_dir)
                agent_type = "finish"  # Use finish prompt template
            else:
                context = get_check_context(project_root, task_dir)
        elif agent_type == AGENT_DEBUG:
            context = get_debug_context(project_root, task_dir)
        elif agent_type == AGENT_RESEARCH:
            context = get_research_context(project_root, task_dir)
        elif agent_type == AGENT_PLAN:
            context = get_plan_context(project_root)
        else:
            context = ""
        
        if not context:
            context = "(No specific context files found. Check task directory for *.jsonl files.)"
        
        full_prompt = build_agent_prompt(agent_type, context)
        
        return [TextContent(type="text", text=full_prompt)]
    
    elif name == "get_current_task":
        task_dir = get_current_task_path(project_root)
        if not task_dir:
            return [TextContent(type="text", text="No current task set.")]
        
        task_json_path = os.path.join(project_root, task_dir, FILE_TASK_JSON)
        task_json = {}
        if os.path.exists(task_json_path):
            try:
                with open(task_json_path, "r", encoding="utf-8") as f:
                    task_json = json.load(f)
            except Exception:
                pass
        
        result = {
            "task_dir": task_dir,
            "task_json": task_json,
            "full_path": os.path.join(project_root, task_dir)
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
    
    elif name == "set_current_task":
        task_path = arguments.get("task_path")
        if not task_path:
            return [TextContent(type="text", text="Error: task_path is required")]
        
        current_task_file = os.path.join(project_root, DIR_WORKFLOW, FILE_CURRENT_TASK)
        try:
            with open(current_task_file, "w", encoding="utf-8") as f:
                f.write(task_path)
            return [TextContent(type="text", text=f"Current task set to: {task_path}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error setting current task: {e}")]
    
    elif name == "update_phase":
        phase = arguments.get("phase")
        task_dir = get_current_task_path(project_root)
        
        if not task_dir:
            return [TextContent(type="text", text="Error: No current task set")]
        
        task_json_path = os.path.join(project_root, task_dir, FILE_TASK_JSON)
        if not os.path.exists(task_json_path):
            return [TextContent(type="text", text=f"Error: task.json not found at {task_json_path}")]
        
        try:
            with open(task_json_path, "r", encoding="utf-8") as f:
                task_data = json.load(f)
            
            task_data["current_phase"] = phase
            
            with open(task_json_path, "w", encoding="utf-8") as f:
                json.dump(task_data, f, indent=2, ensure_ascii=False)
            
            return [TextContent(type="text", text=f"Phase updated to: {phase}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error updating phase: {e}")]
    
    elif name == "list_tasks":
        developer = get_developer_name(project_root)
        tasks = []
        
        # Check workspace tasks
        if developer:
            workspace_tasks_dir = os.path.join(project_root, DIR_WORKFLOW, DIR_WORKSPACE, developer, DIR_TASKS)
            if os.path.exists(workspace_tasks_dir):
                for task_name in os.listdir(workspace_tasks_dir):
                    task_path = os.path.join(workspace_tasks_dir, task_name)
                    if os.path.isdir(task_path):
                        task_json_path = os.path.join(task_path, FILE_TASK_JSON)
                        task_info = {"name": task_name, "path": f"{DIR_WORKFLOW}/{DIR_WORKSPACE}/{developer}/{DIR_TASKS}/{task_name}"}
                        if os.path.exists(task_json_path):
                            try:
                                with open(task_json_path, "r", encoding="utf-8") as f:
                                    task_info["task_json"] = json.load(f)
                            except Exception:
                                pass
                        tasks.append(task_info)
        
        # Check root tasks dir
        root_tasks_dir = os.path.join(project_root, DIR_WORKFLOW, DIR_TASKS)
        if os.path.exists(root_tasks_dir):
            for task_name in os.listdir(root_tasks_dir):
                if task_name == "archive":
                    continue
                task_path = os.path.join(root_tasks_dir, task_name)
                if os.path.isdir(task_path):
                    task_json_path = os.path.join(task_path, FILE_TASK_JSON)
                    task_info = {"name": task_name, "path": f"{DIR_WORKFLOW}/{DIR_TASKS}/{task_name}"}
                    if os.path.exists(task_json_path):
                        try:
                            with open(task_json_path, "r", encoding="utf-8") as f:
                                task_info["task_json"] = json.load(f)
                        except Exception:
                            pass
                    tasks.append(task_info)
        
        current_task = get_current_task_path(project_root)
        
        result = {
            "developer": developer,
            "current_task": current_task,
            "tasks": tasks
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
    
    elif name == "create_task":
        task_name = arguments.get("name")
        title = arguments.get("title")
        dev_type = arguments.get("dev_type", "fullstack")
        
        if not task_name or not title:
            return [TextContent(type="text", text="Error: name and title are required")]
        
        developer = get_developer_name(project_root)
        if not developer:
            developer = "default"
        
        # Create task directory
        date_prefix = datetime.now().strftime("%m-%d")
        task_slug = f"{date_prefix}-{task_name}"
        
        task_dir = os.path.join(project_root, DIR_WORKFLOW, DIR_WORKSPACE, developer, DIR_TASKS, task_slug)
        os.makedirs(task_dir, exist_ok=True)
        
        # Create task.json
        task_json = {
            "title": title,
            "status": "active",
            "dev_type": dev_type,
            "current_phase": 0,
            "created_at": datetime.now().isoformat(),
            "next_action": [
                {"phase": 1, "action": "implement"},
                {"phase": 2, "action": "check"},
                {"phase": 3, "action": "finish"},
                {"phase": 4, "action": "create-pr"}
            ]
        }
        
        task_json_path = os.path.join(task_dir, FILE_TASK_JSON)
        with open(task_json_path, "w", encoding="utf-8") as f:
            json.dump(task_json, f, indent=2, ensure_ascii=False)
        
        # Create prd.md template
        prd_path = os.path.join(task_dir, "prd.md")
        with open(prd_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n## Requirements\n\n(Describe your requirements here)\n\n## Acceptance Criteria\n\n- [ ] Criteria 1\n- [ ] Criteria 2\n")
        
        # Set as current task
        relative_task_dir = f"{DIR_WORKFLOW}/{DIR_WORKSPACE}/{developer}/{DIR_TASKS}/{task_slug}"
        current_task_file = os.path.join(project_root, DIR_WORKFLOW, FILE_CURRENT_TASK)
        with open(current_task_file, "w", encoding="utf-8") as f:
            f.write(relative_task_dir)
        
        return [TextContent(type="text", text=f"Task created: {relative_task_dir}\n\nEdit {task_dir}/prd.md to add requirements.")]
    
    elif name == "get_workflow":
        workflow_path = os.path.join(project_root, DIR_WORKFLOW, "workflow.md")
        content = read_file_content(project_root, f"{DIR_WORKFLOW}/workflow.md")
        if content:
            return [TextContent(type="text", text=content)]
        return [TextContent(type="text", text="workflow.md not found")]
    
    elif name == "get_spec_index":
        spec_type = arguments.get("spec_type", "all")
        results = []
        
        spec_types = ["frontend", "backend", "guides"] if spec_type == "all" else [spec_type]
        
        for st in spec_types:
            index_path = f"{DIR_WORKFLOW}/{DIR_SPEC}/{st}/index.md"
            content = read_file_content(project_root, index_path)
            if content:
                results.append(f"=== {index_path} ===\n{content}")
        
        if results:
            return [TextContent(type="text", text="\n\n".join(results))]
        return [TextContent(type="text", text=f"No spec index found for: {spec_type}")]
    
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
