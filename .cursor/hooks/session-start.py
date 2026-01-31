#!/usr/bin/env python3
"""
Session Start Hook for Cursor - Inject structured context

This hook injects:
1. Current state (git status, current task)
2. Workflow guide
3. Guidelines index (frontend/backend/guides)
4. Session instructions
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


def run_python_script(script_path: Path, args: list = None) -> str:
    """Run a Python script and return its output."""
    if not script_path.exists():
        return "Script not found"
    
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=script_path.parent.parent.parent,  # repo root
        )
        return result.stdout if result.returncode == 0 else "No context available"
    except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
        return "No context available"


def get_current_context(trellis_dir: Path) -> str:
    """Get current context using Python script or fallback to manual."""
    # Try Python script first
    py_script = trellis_dir / "scripts" / "get_context.py"
    if py_script.exists():
        return run_python_script(py_script)
    
    # Fallback: build context manually
    context_parts = []
    
    # Current task
    current_task_file = trellis_dir / ".current-task"
    if current_task_file.exists():
        task_path = read_file(current_task_file).strip()
        context_parts.append(f"Current Task: {task_path}")
        
        task_json = trellis_dir.parent / task_path / "task.json"
        if task_json.exists():
            try:
                task_data = json.loads(read_file(task_json))
                context_parts.append(f"  Status: {task_data.get('status', 'unknown')}")
                context_parts.append(f"  Phase: {task_data.get('current_phase', 0)}")
            except json.JSONDecodeError:
                pass
    else:
        context_parts.append("No active task")
    
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
        # Handle Cursor's path format
        if root.startswith("/") and len(root) > 2 and root[2] == ":":
            root = root[1:].replace("/", "\\")
        
        test_path = Path(root)
        if (test_path / ".trellis").exists():
            project_dir = test_path
            break
    
    if not project_dir:
        project_dir = find_trellis_root()
    
    if not project_dir:
        # No Trellis project found, output minimal context
        output = {
            "additional_context": "[Session Info] No Trellis project found in workspace."
        }
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(0)
    
    trellis_dir = project_dir / ".trellis"
    cursor_dir = project_dir / ".cursor"
    
    # Build context
    context_parts = []
    
    # 1. Header
    context_parts.append(f"[Session Info] Mode: agent, Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    context_parts.append("")
    context_parts.append("[Project Context - Auto Injected]")
    context_parts.append("")
    
    # 2. Current State
    context_parts.append("## Current State")
    context_parts.append(get_current_context(trellis_dir))
    context_parts.append("")
    
    # 3. Workflow (brief)
    workflow_path = trellis_dir / "workflow.md"
    if workflow_path.exists():
        context_parts.append("## Workflow")
        context_parts.append("See .trellis/workflow.md for full workflow guide.")
        context_parts.append("")
    
    # 4. Guidelines Index (brief)
    spec_dir = trellis_dir / "spec"
    if spec_dir.exists():
        context_parts.append("## Available Specs")
        for subdir in ["frontend", "backend", "guides"]:
            index_file = spec_dir / subdir / "index.md"
            if index_file.exists():
                context_parts.append(f"- .trellis/spec/{subdir}/index.md")
        context_parts.append("")
    
    # 5. Session Instructions
    start_md = cursor_dir / "commands" / "trellis-start.md"
    if start_md.exists():
        context_parts.append("## Quick Start")
        context_parts.append("Run /trellis-start to begin working.")
        context_parts.append("")
    
    # Output in Cursor hook format
    output = {
        "additional_context": "\n".join(context_parts)
    }
    
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
