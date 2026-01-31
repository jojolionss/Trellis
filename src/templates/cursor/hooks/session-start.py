#!/usr/bin/env python3
"""
Session Start Hook for Cursor - Inject FULL structured context

This hook injects (same as Claude Code version):
1. Current state (git status, current task)
2. Workflow guide (FULL content)
3. Guidelines index (FULL content - frontend/backend/guides)
4. Session instructions (FULL content)
5. Action directive
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def find_trellis_root(start_path: str = None) -> Path | None:
    """Find directory containing .trellis/ from start_path upwards"""
    if start_path is None:
        start_path = os.getcwd()
    
    current = Path(start_path).resolve()
    while current != current.parent:
        if (current / ".trellis").exists():
            return current
        current = current.parent
    return None


def read_file(path: Path, fallback: str = "") -> str:
    """Read file content, return fallback if not found."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return fallback


def run_python_script(script_path: Path, cwd: Path = None) -> str:
    """Run a Python script and return its output."""
    if not script_path.exists():
        return ""
    
    cmd = [sys.executable, str(script_path)]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(cwd) if cwd else None,
        )
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
        return ""


def get_git_status(project_dir: Path) -> str:
    """Get git status information."""
    try:
        # Get current branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
            cwd=str(project_dir)
        )
        branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"
        
        # Get uncommitted file count
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
            cwd=str(project_dir)
        )
        uncommitted = len([l for l in status_result.stdout.strip().split("\n") if l]) if status_result.returncode == 0 else 0
        
        # Get recent commits
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            capture_output=True, text=True, timeout=5,
            cwd=str(project_dir)
        )
        recent_commits = log_result.stdout.strip() if log_result.returncode == 0 else ""
        
        return f"Branch: {branch}\nUncommitted files: {uncommitted}\nRecent commits:\n{recent_commits}"
    except Exception:
        return "Git info unavailable"


def get_current_context(trellis_dir: Path, project_dir: Path) -> str:
    """Get current context - task, git status, etc."""
    context_parts = []
    
    # Try Python script first
    py_script = trellis_dir / "scripts" / "get_context.py"
    if py_script.exists():
        script_output = run_python_script(py_script, cwd=project_dir)
        if script_output:
            return script_output
    
    # Fallback: build context manually
    
    # Developer info
    developer_file = trellis_dir / ".developer"
    if developer_file.exists():
        dev_content = read_file(developer_file)
        for line in dev_content.split("\n"):
            if line.startswith("name="):
                context_parts.append(f"Developer: {line.split('=', 1)[1]}")
                break
    
    # Git status
    context_parts.append(get_git_status(project_dir))
    
    # Current task
    current_task_file = trellis_dir / ".current-task"
    if current_task_file.exists():
        task_path = read_file(current_task_file).strip()
        if task_path:
            context_parts.append(f"\nCurrent Task: {task_path}")
            
            task_json_path = project_dir / task_path / "task.json"
            if task_json_path.exists():
                try:
                    task_data = json.loads(read_file(task_json_path))
                    context_parts.append(f"  Title: {task_data.get('title', 'N/A')}")
                    context_parts.append(f"  Status: {task_data.get('status', 'unknown')}")
                    context_parts.append(f"  Phase: {task_data.get('current_phase', 0)}")
                except json.JSONDecodeError:
                    pass
    else:
        context_parts.append("\nNo active task")
    
    return "\n".join(context_parts)


def main():
    # Parse input from Cursor
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        input_data = {}
    
    # Get workspace root from input
    workspace_roots = input_data.get("workspace_roots", [])
    
    # Find project root
    project_dir = None
    for root in workspace_roots:
        # Handle Cursor's path format (e.g., /E:/Projects/xxx)
        if root.startswith("/") and len(root) > 2 and root[2] == ":":
            root = root[1:].replace("/", "\\")
        
        test_path = Path(root)
        if (test_path / ".trellis").exists():
            project_dir = test_path
            break
    
    if not project_dir:
        project_dir = find_trellis_root()
    
    if not project_dir:
        # No Trellis project found
        output = {
            "additional_context": "[Session Info] No Trellis project found in workspace."
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(0)
    
    trellis_dir = project_dir / ".trellis"
    
    # Build context (inject FULL content like Claude Code version)
    context_parts = []
    
    # 1. Session Header
    context_parts.append("<session-context>")
    context_parts.append("You are starting a new session in a Trellis-managed project.")
    context_parts.append(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    context_parts.append("Read and follow all instructions below carefully.")
    context_parts.append("</session-context>")
    context_parts.append("")
    
    # 2. Current State (FULL)
    context_parts.append("<current-state>")
    context_parts.append(get_current_context(trellis_dir, project_dir))
    context_parts.append("</current-state>")
    context_parts.append("")
    
    # 3. Workflow Guide (FULL content)
    workflow_path = trellis_dir / "workflow.md"
    context_parts.append("<workflow>")
    workflow_content = read_file(workflow_path, "No workflow.md found")
    context_parts.append(workflow_content)
    context_parts.append("</workflow>")
    context_parts.append("")
    
    # 4. Guidelines Index (FULL content)
    context_parts.append("<guidelines>")
    
    context_parts.append("## Frontend")
    frontend_index = read_file(
        trellis_dir / "spec" / "frontend" / "index.md", "Not configured"
    )
    context_parts.append(frontend_index)
    context_parts.append("")
    
    context_parts.append("## Backend")
    backend_index = read_file(
        trellis_dir / "spec" / "backend" / "index.md", "Not configured"
    )
    context_parts.append(backend_index)
    context_parts.append("")
    
    context_parts.append("## Guides")
    guides_index = read_file(
        trellis_dir / "spec" / "guides" / "index.md", "Not configured"
    )
    context_parts.append(guides_index)
    
    context_parts.append("</guidelines>")
    context_parts.append("")
    
    # 5. Session Instructions (FULL content)
    # Try global command first, then project-level
    global_cursor_dir = Path.home() / ".cursor"
    start_md_paths = [
        global_cursor_dir / "commands" / "trellis-start.md",
        project_dir / ".cursor" / "commands" / "trellis-start.md",
    ]
    
    start_content = "Run /trellis-start to begin working."
    for start_md_path in start_md_paths:
        if start_md_path.exists():
            start_content = read_file(start_md_path)
            break
    
    context_parts.append("<instructions>")
    context_parts.append(start_content)
    context_parts.append("</instructions>")
    context_parts.append("")
    
    # 6. Final directive
    context_parts.append("<ready>")
    context_parts.append("Context loaded. Wait for user's first message, then follow <instructions> to handle their request.")
    context_parts.append("</ready>")
    
    # Output in Cursor hook format
    output = {
        "additional_context": "\n".join(context_parts)
    }
    
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
