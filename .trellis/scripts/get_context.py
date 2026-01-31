#!/usr/bin/env python3
"""
Get Session Context for AI Agent

Usage:
  python get_context.py           # Text output
  python get_context.py --json    # JSON output
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DIR_WORKFLOW = ".trellis"
DIR_WORKSPACE = "workspace"
DIR_TASKS = "tasks"
DIR_SPEC = "spec"
FILE_DEVELOPER = ".developer"
FILE_CURRENT_TASK = ".current-task"
FILE_TASK_JSON = "task.json"


def find_repo_root(start_path: str = None) -> Path:
    """Find directory containing .trellis/"""
    if start_path is None:
        start_path = os.getcwd()
    
    current = Path(start_path).resolve()
    while current != current.parent:
        if (current / DIR_WORKFLOW).exists():
            return current
        current = current.parent
    return Path(start_path)


def get_developer(repo_root: Path) -> str | None:
    """Get developer name"""
    dev_file = repo_root / DIR_WORKFLOW / FILE_DEVELOPER
    if dev_file.exists():
        content = dev_file.read_text(encoding="utf-8")
        for line in content.split("\n"):
            if line.startswith("name="):
                return line.split("=", 1)[1].strip()
    return None


def get_current_task(repo_root: Path) -> str | None:
    """Get current task path"""
    current_file = repo_root / DIR_WORKFLOW / FILE_CURRENT_TASK
    if current_file.exists():
        content = current_file.read_text(encoding="utf-8").strip()
        return content if content else None
    return None


def get_git_info(repo_root: Path) -> dict:
    """Get git status info"""
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=repo_root
        ).stdout.strip() or "unknown"
        
        status_output = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=repo_root
        ).stdout
        uncommitted = len([l for l in status_output.split("\n") if l.strip()])
        
        log_output = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            capture_output=True, text=True, cwd=repo_root
        ).stdout
        commits = [l.strip() for l in log_output.split("\n") if l.strip()][:5]
        
        return {
            "branch": branch,
            "uncommitted_changes": uncommitted,
            "is_clean": uncommitted == 0,
            "recent_commits": commits
        }
    except:
        return {
            "branch": "unknown",
            "uncommitted_changes": 0,
            "is_clean": True,
            "recent_commits": []
        }


def get_tasks(repo_root: Path) -> list[dict]:
    """Get list of active tasks"""
    tasks = []
    tasks_dir = repo_root / DIR_WORKFLOW / DIR_TASKS
    
    if not tasks_dir.exists():
        return tasks
    
    for d in sorted(tasks_dir.iterdir()):
        if d.is_dir() and d.name != "archive":
            task_json_path = d / FILE_TASK_JSON
            task_info = {"dir": d.name, "name": d.name, "status": "unknown"}
            
            if task_json_path.exists():
                try:
                    data = json.loads(task_json_path.read_text(encoding="utf-8"))
                    task_info["name"] = data.get("name", d.name)
                    task_info["status"] = data.get("status", "unknown")
                    task_info["assignee"] = data.get("assignee", "-")
                except:
                    pass
            
            tasks.append(task_info)
    
    return tasks


def output_json(repo_root: Path):
    """Output context as JSON"""
    developer = get_developer(repo_root)
    git_info = get_git_info(repo_root)
    tasks = get_tasks(repo_root)
    current_task = get_current_task(repo_root)
    
    result = {
        "developer": developer,
        "git": git_info,
        "tasks": {
            "current": current_task,
            "active": tasks,
            "directory": f"{DIR_WORKFLOW}/{DIR_TASKS}"
        }
    }
    
    print(json.dumps(result, indent=2, ensure_ascii=False))


def output_text(repo_root: Path):
    """Output context as text"""
    developer = get_developer(repo_root)
    git_info = get_git_info(repo_root)
    tasks = get_tasks(repo_root)
    current_task = get_current_task(repo_root)
    
    print("=" * 40)
    print("SESSION CONTEXT")
    print("=" * 40)
    print()
    
    print("## DEVELOPER")
    if developer:
        print(f"Name: {developer}")
    else:
        print("ERROR: Not initialized. Run: python init_developer.py <name>")
    print()
    
    print("## GIT STATUS")
    print(f"Branch: {git_info['branch']}")
    if git_info['is_clean']:
        print("Working directory: Clean")
    else:
        print(f"Working directory: {git_info['uncommitted_changes']} uncommitted change(s)")
    print()
    
    print("## RECENT COMMITS")
    for commit in git_info['recent_commits']:
        print(f"  {commit}")
    if not git_info['recent_commits']:
        print("  (no commits)")
    print()
    
    print("## CURRENT TASK")
    if current_task:
        print(f"Path: {current_task}")
        task_dir = repo_root / current_task
        task_json_path = task_dir / FILE_TASK_JSON
        if task_json_path.exists():
            try:
                data = json.loads(task_json_path.read_text(encoding="utf-8"))
                print(f"Name: {data.get('name', 'unknown')}")
                print(f"Status: {data.get('status', 'unknown')}")
            except:
                pass
    else:
        print("(none)")
    print()
    
    print("## ACTIVE TASKS")
    for task in tasks:
        marker = " <- current" if f"{DIR_WORKFLOW}/{DIR_TASKS}/{task['dir']}" == current_task else ""
        print(f"  - {task['dir']}/ ({task['status']}){marker}")
    if not tasks:
        print("  (no active tasks)")
    print(f"\nTotal: {len(tasks)} task(s)")
    print()
    
    print("## PATHS")
    if developer:
        print(f"Workspace: {DIR_WORKFLOW}/{DIR_WORKSPACE}/{developer}/")
    print(f"Tasks: {DIR_WORKFLOW}/{DIR_TASKS}/")
    print(f"Spec: {DIR_WORKFLOW}/{DIR_SPEC}/")
    print()
    print("=" * 40)


def main():
    parser = argparse.ArgumentParser(description="Get Session Context")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    repo_root = find_repo_root()
    
    if args.json:
        output_json(repo_root)
    else:
        output_text(repo_root)


if __name__ == "__main__":
    main()
