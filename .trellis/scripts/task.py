#!/usr/bin/env python3
"""
Task Management Script for Multi-Agent Pipeline (Python Version)

Usage:
  python task.py create "title" [--slug name]
  python task.py init-context <dir> <dev_type>
  python task.py add-context <dir> <jsonl> <path> [reason]
  python task.py validate <dir>
  python task.py list-context <dir>
  python task.py start <dir>
  python task.py finish
  python task.py list
  python task.py archive <name>
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

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
    """Get developer name from .trellis/.developer"""
    dev_file = repo_root / DIR_WORKFLOW / FILE_DEVELOPER
    if dev_file.exists():
        content = dev_file.read_text(encoding="utf-8")
        for line in content.split("\n"):
            if line.startswith("name="):
                return line.split("=", 1)[1].strip()
    return None


def get_tasks_dir(repo_root: Path) -> Path:
    """Get tasks directory path"""
    return repo_root / DIR_WORKFLOW / DIR_TASKS


def get_current_task(repo_root: Path) -> str | None:
    """Get current task path"""
    current_file = repo_root / DIR_WORKFLOW / FILE_CURRENT_TASK
    if current_file.exists():
        content = current_file.read_text(encoding="utf-8").strip()
        return content if content else None
    return None


def set_current_task(repo_root: Path, task_path: str) -> None:
    """Set current task"""
    current_file = repo_root / DIR_WORKFLOW / FILE_CURRENT_TASK
    current_file.write_text(task_path, encoding="utf-8")


def clear_current_task(repo_root: Path) -> None:
    """Clear current task"""
    current_file = repo_root / DIR_WORKFLOW / FILE_CURRENT_TASK
    if current_file.exists():
        current_file.unlink()


def slugify(text: str) -> str:
    """Convert text to slug"""
    import re
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')


# =============================================================================
# JSONL Default Content
# =============================================================================

def get_implement_jsonl(dev_type: str) -> list[dict]:
    """Get default implement.jsonl content"""
    entries = [
        {"file": f"{DIR_WORKFLOW}/workflow.md", "reason": "Project workflow"},
    ]
    
    if dev_type in ("backend", "fullstack"):
        entries.append({"file": f"{DIR_WORKFLOW}/{DIR_SPEC}/backend/index.md", "reason": "Backend guide"})
    if dev_type in ("frontend", "fullstack"):
        entries.append({"file": f"{DIR_WORKFLOW}/{DIR_SPEC}/frontend/index.md", "reason": "Frontend guide"})
    
    return entries


def get_check_jsonl(dev_type: str) -> list[dict]:
    """Get default check.jsonl content"""
    entries = [
        {"file": ".cursor/commands/trellis-finish-work.md", "reason": "Finish checklist"},
    ]
    
    if dev_type in ("backend", "fullstack"):
        entries.append({"file": ".cursor/commands/trellis-check-backend.md", "reason": "Backend check"})
    if dev_type in ("frontend", "fullstack"):
        entries.append({"file": ".cursor/commands/trellis-check-frontend.md", "reason": "Frontend check"})
    
    return entries


def get_debug_jsonl(dev_type: str) -> list[dict]:
    """Get default debug.jsonl content"""
    entries = []
    
    if dev_type in ("backend", "fullstack"):
        entries.append({"file": ".cursor/commands/trellis-check-backend.md", "reason": "Backend spec"})
    if dev_type in ("frontend", "fullstack"):
        entries.append({"file": ".cursor/commands/trellis-check-frontend.md", "reason": "Frontend spec"})
    
    return entries


# =============================================================================
# Commands
# =============================================================================

def cmd_create(args, repo_root: Path):
    """Create new task"""
    title = args.title
    slug = args.slug or slugify(title)
    
    if not slug:
        print("Error: could not generate slug from title", file=sys.stderr)
        sys.exit(1)
    
    developer = get_developer(repo_root)
    if not developer:
        developer = "default"
    
    tasks_dir = get_tasks_dir(repo_root)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    
    date_prefix = datetime.now().strftime("%m-%d")
    dir_name = f"{date_prefix}-{slug}"
    task_dir = tasks_dir / dir_name
    task_dir.mkdir(exist_ok=True)
    
    task_json = {
        "id": slug,
        "name": slug,
        "title": title,
        "status": "planning",
        "dev_type": None,
        "priority": "P2",
        "creator": developer,
        "assignee": developer,
        "createdAt": datetime.now().strftime("%Y-%m-%d"),
        "current_phase": 0,
        "next_action": [
            {"phase": 1, "action": "implement"},
            {"phase": 2, "action": "check"},
            {"phase": 3, "action": "finish"},
            {"phase": 4, "action": "create-pr"}
        ]
    }
    
    task_json_path = task_dir / FILE_TASK_JSON
    task_json_path.write_text(json.dumps(task_json, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"Created task: {dir_name}", file=sys.stderr)
    print(f"{DIR_WORKFLOW}/{DIR_TASKS}/{dir_name}")


def cmd_init_context(args, repo_root: Path):
    """Initialize context files"""
    target_dir = Path(args.dir)
    if not target_dir.is_absolute():
        target_dir = repo_root / target_dir
    
    dev_type = args.dev_type
    
    if not target_dir.exists():
        print(f"Error: Directory not found: {target_dir}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Initializing context for: {target_dir}")
    print(f"Dev type: {dev_type}")
    
    # implement.jsonl
    implement_file = target_dir / "implement.jsonl"
    entries = get_implement_jsonl(dev_type)
    with open(implement_file, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"  Created implement.jsonl ({len(entries)} entries)")
    
    # check.jsonl
    check_file = target_dir / "check.jsonl"
    entries = get_check_jsonl(dev_type)
    with open(check_file, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"  Created check.jsonl ({len(entries)} entries)")
    
    # debug.jsonl
    debug_file = target_dir / "debug.jsonl"
    entries = get_debug_jsonl(dev_type)
    with open(debug_file, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"  Created debug.jsonl ({len(entries)} entries)")
    
    print("Done!")


def cmd_add_context(args, repo_root: Path):
    """Add entry to jsonl"""
    target_dir = Path(args.dir)
    if not target_dir.is_absolute():
        target_dir = repo_root / target_dir
    
    jsonl_name = args.jsonl
    if not jsonl_name.endswith(".jsonl"):
        jsonl_name += ".jsonl"
    
    path = args.path
    reason = args.reason or "Added manually"
    
    full_path = repo_root / path
    entry_type = "directory" if full_path.is_dir() else "file"
    
    if not full_path.exists():
        print(f"Error: Path not found: {path}", file=sys.stderr)
        sys.exit(1)
    
    jsonl_file = target_dir / jsonl_name
    
    entry = {"file": path, "reason": reason}
    if entry_type == "directory":
        entry["type"] = "directory"
    
    with open(jsonl_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    print(f"Added {entry_type}: {path}")


def cmd_validate(args, repo_root: Path):
    """Validate jsonl files"""
    target_dir = Path(args.dir)
    if not target_dir.is_absolute():
        target_dir = repo_root / target_dir
    
    print(f"Validating: {target_dir}")
    
    total_errors = 0
    for jsonl_name in ["implement.jsonl", "check.jsonl", "debug.jsonl"]:
        jsonl_file = target_dir / jsonl_name
        if not jsonl_file.exists():
            print(f"  {jsonl_name}: not found (skipped)")
            continue
        
        errors = 0
        line_count = 0
        for line_num, line in enumerate(jsonl_file.read_text(encoding="utf-8").split("\n"), 1):
            if not line.strip():
                continue
            line_count += 1
            
            try:
                entry = json.loads(line)
                file_path = entry.get("file") or entry.get("path")
                if not file_path:
                    print(f"  {jsonl_name}:{line_num}: Missing 'file' field")
                    errors += 1
                    continue
                
                full_path = repo_root / file_path
                entry_type = entry.get("type", "file")
                
                if entry_type == "directory":
                    if not full_path.is_dir():
                        print(f"  {jsonl_name}:{line_num}: Directory not found: {file_path}")
                        errors += 1
                else:
                    if not full_path.is_file():
                        print(f"  {jsonl_name}:{line_num}: File not found: {file_path}")
                        errors += 1
            except json.JSONDecodeError:
                print(f"  {jsonl_name}:{line_num}: Invalid JSON")
                errors += 1
        
        if errors == 0:
            print(f"  {jsonl_name}: OK ({line_count} entries)")
        else:
            print(f"  {jsonl_name}: {errors} errors")
        
        total_errors += errors
    
    if total_errors > 0:
        sys.exit(1)


def cmd_list_context(args, repo_root: Path):
    """List jsonl entries"""
    target_dir = Path(args.dir)
    if not target_dir.is_absolute():
        target_dir = repo_root / target_dir
    
    for jsonl_name in ["implement.jsonl", "check.jsonl", "debug.jsonl"]:
        jsonl_file = target_dir / jsonl_name
        if not jsonl_file.exists():
            continue
        
        print(f"\n[{jsonl_name}]")
        for i, line in enumerate(jsonl_file.read_text(encoding="utf-8").split("\n"), 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                file_path = entry.get("file", "?")
                reason = entry.get("reason", "-")
                entry_type = entry.get("type", "file")
                type_marker = "[DIR]" if entry_type == "directory" else ""
                print(f"  {i}. {type_marker} {file_path}")
                print(f"     -> {reason}")
            except json.JSONDecodeError:
                print(f"  {i}. (invalid JSON)")


def cmd_start(args, repo_root: Path):
    """Set current task"""
    task_dir = args.dir
    
    # Convert to relative path
    if os.path.isabs(task_dir):
        task_dir = os.path.relpath(task_dir, repo_root)
    
    full_path = repo_root / task_dir
    if not full_path.exists():
        print(f"Error: Task directory not found: {task_dir}", file=sys.stderr)
        sys.exit(1)
    
    set_current_task(repo_root, task_dir)
    print(f"Current task set to: {task_dir}")


def cmd_finish(args, repo_root: Path):
    """Clear current task"""
    current = get_current_task(repo_root)
    if not current:
        print("No current task set")
        return
    
    clear_current_task(repo_root)
    print(f"Cleared current task (was: {current})")


def cmd_list(args, repo_root: Path):
    """List tasks"""
    tasks_dir = get_tasks_dir(repo_root)
    current_task = get_current_task(repo_root)
    
    print("Active tasks:")
    
    if not tasks_dir.exists():
        print("  (no tasks)")
        return
    
    count = 0
    for d in sorted(tasks_dir.iterdir()):
        if d.is_dir() and d.name != "archive":
            task_json_path = d / FILE_TASK_JSON
            status = "unknown"
            assignee = "-"
            
            if task_json_path.exists():
                try:
                    data = json.loads(task_json_path.read_text(encoding="utf-8"))
                    status = data.get("status", "unknown")
                    assignee = data.get("assignee", "-")
                except:
                    pass
            
            relative_path = f"{DIR_WORKFLOW}/{DIR_TASKS}/{d.name}"
            marker = " <- current" if relative_path == current_task else ""
            print(f"  - {d.name}/ ({status}) @{assignee}{marker}")
            count += 1
    
    if count == 0:
        print("  (no active tasks)")
    
    print(f"\nTotal: {count} task(s)")


def find_task_by_name(task_name: str, tasks_dir: Path) -> Path | None:
    """Find task directory by name or partial name"""
    # First try exact match
    if (tasks_dir / task_name).exists():
        return tasks_dir / task_name
    
    # Try partial match
    for d in tasks_dir.iterdir():
        if d.is_dir() and d.name != "archive":
            if task_name in d.name or d.name.endswith(f"-{task_name}"):
                return d
    
    return None


def cmd_archive(args, repo_root: Path):
    """Archive completed task"""
    task_name = args.name
    tasks_dir = get_tasks_dir(repo_root)
    
    # Find task directory
    task_dir = find_task_by_name(task_name, tasks_dir)
    
    if not task_dir or not task_dir.exists():
        print(f"Error: Task not found: {task_name}", file=sys.stderr)
        print("Active tasks:", file=sys.stderr)
        for d in sorted(tasks_dir.iterdir()):
            if d.is_dir() and d.name != "archive":
                print(f"  - {d.name}/", file=sys.stderr)
        sys.exit(1)
    
    dir_name = task_dir.name
    task_json_path = task_dir / FILE_TASK_JSON
    
    # Update status before archiving
    today = datetime.now().strftime("%Y-%m-%d")
    if task_json_path.exists():
        try:
            data = json.loads(task_json_path.read_text(encoding="utf-8"))
            data["status"] = "completed"
            data["completedAt"] = today
            task_json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except:
            pass
    
    # Clear if current task
    current = get_current_task(repo_root)
    if current and dir_name in current:
        clear_current_task(repo_root)
    
    # Create archive directory
    year_month = datetime.now().strftime("%Y-%m")
    archive_dir = tasks_dir / "archive" / year_month
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    # Move task to archive
    dest = archive_dir / dir_name
    
    # If destination exists, remove it first
    if dest.exists():
        import shutil
        shutil.rmtree(dest)
    
    # Move task directory
    import shutil
    shutil.move(str(task_dir), str(dest))
    
    print(f"Archived: {dir_name} -> archive/{year_month}/", file=sys.stderr)
    print(f"{DIR_WORKFLOW}/{DIR_TASKS}/archive/{year_month}/{dir_name}")


# =============================================================================
# Main
# =============================================================================

def main():
    repo_root = find_repo_root()
    
    parser = argparse.ArgumentParser(description="Task Management for Multi-Agent Pipeline")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # create
    p_create = subparsers.add_parser("create", help="Create new task")
    p_create.add_argument("title", help="Task title")
    p_create.add_argument("--slug", "-s", help="Task slug")
    
    # init-context
    p_init = subparsers.add_parser("init-context", help="Initialize context files")
    p_init.add_argument("dir", help="Task directory")
    p_init.add_argument("dev_type", choices=["backend", "frontend", "fullstack", "test", "docs"])
    
    # add-context
    p_add = subparsers.add_parser("add-context", help="Add entry to jsonl")
    p_add.add_argument("dir", help="Task directory")
    p_add.add_argument("jsonl", help="JSONL file (implement/check/debug)")
    p_add.add_argument("path", help="File or directory path")
    p_add.add_argument("reason", nargs="?", help="Reason for inclusion")
    
    # validate
    p_val = subparsers.add_parser("validate", help="Validate jsonl files")
    p_val.add_argument("dir", help="Task directory")
    
    # list-context
    p_lc = subparsers.add_parser("list-context", help="List jsonl entries")
    p_lc.add_argument("dir", help="Task directory")
    
    # start
    p_start = subparsers.add_parser("start", help="Set current task")
    p_start.add_argument("dir", help="Task directory")
    
    # finish
    subparsers.add_parser("finish", help="Clear current task")
    
    # list
    subparsers.add_parser("list", help="List tasks")
    
    # archive
    p_archive = subparsers.add_parser("archive", help="Archive completed task")
    p_archive.add_argument("name", help="Task name or slug")
    
    args = parser.parse_args()
    
    if args.command == "create":
        cmd_create(args, repo_root)
    elif args.command == "init-context":
        cmd_init_context(args, repo_root)
    elif args.command == "add-context":
        cmd_add_context(args, repo_root)
    elif args.command == "validate":
        cmd_validate(args, repo_root)
    elif args.command == "list-context":
        cmd_list_context(args, repo_root)
    elif args.command == "start":
        cmd_start(args, repo_root)
    elif args.command == "finish":
        cmd_finish(args, repo_root)
    elif args.command == "list":
        cmd_list(args, repo_root)
    elif args.command == "archive":
        cmd_archive(args, repo_root)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
