#!/usr/bin/env python3
"""
Initialize developer for Trellis workflow

Usage:
  python init_developer.py <developer-name>

Creates:
  - .trellis/.developer file
  - .trellis/workspace/<name>/ directory
"""

import os
import sys
from datetime import datetime
from pathlib import Path

DIR_WORKFLOW = ".trellis"
DIR_WORKSPACE = "workspace"
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
    """Get existing developer name"""
    dev_file = repo_root / DIR_WORKFLOW / FILE_DEVELOPER
    if dev_file.exists():
        content = dev_file.read_text(encoding="utf-8")
        for line in content.split("\n"):
            if line.startswith("name="):
                return line.split("=", 1)[1].strip()
    return None


def init_developer(name: str, repo_root: Path) -> None:
    """Initialize developer"""
    dev_file = repo_root / DIR_WORKFLOW / FILE_DEVELOPER
    workspace_dir = repo_root / DIR_WORKFLOW / DIR_WORKSPACE / name
    
    # Create .developer file
    dev_content = f"""name={name}
initialized_at={datetime.now().isoformat()}
"""
    dev_file.write_text(dev_content, encoding="utf-8")
    
    # Create workspace directory
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    # Create initial journal file
    journal_file = workspace_dir / "journal-1.md"
    if not journal_file.exists():
        journal_content = f"""# Journal - {name} (Part 1)

> AI development session journal
> Started: {datetime.now().strftime("%Y-%m-%d")}

---

"""
        journal_file.write_text(journal_content, encoding="utf-8")
    
    # Create index.md
    index_file = workspace_dir / "index.md"
    if not index_file.exists():
        index_content = f"""# Workspace Index - {name}

> Journal tracking for AI development sessions.

---

## Current Status

- **Active File**: `journal-1.md`
- **Total Sessions**: 0

---

## Notes

- Sessions are appended to journal files
- New journal file created when current exceeds 2000 lines
"""
        index_file.write_text(index_content, encoding="utf-8")
    
    print(f"Developer initialized: {name}")
    print(f"  .developer file: {dev_file}")
    print(f"  Workspace dir: {workspace_dir}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python init_developer.py <developer-name>")
        print()
        print("Example:")
        print("  python init_developer.py john")
        sys.exit(1)
    
    name = sys.argv[1]
    repo_root = find_repo_root()
    
    # Check if already initialized
    existing = get_developer(repo_root)
    if existing:
        print(f"Developer already initialized: {existing}")
        print()
        print(f"To reinitialize, remove {DIR_WORKFLOW}/{FILE_DEVELOPER} first")
        sys.exit(0)
    
    init_developer(name, repo_root)


if __name__ == "__main__":
    main()
