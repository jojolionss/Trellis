#!/usr/bin/env python3
"""
Add Session to Journal

Usage:
  python add_session.py --title "Title" --commit "hash1,hash2" --summary "Summary"
  echo "content" | python add_session.py --title "Title" --commit "hash"
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# =============================================================================
# Path Constants
# =============================================================================

DIR_WORKFLOW = ".trellis"
DIR_WORKSPACE = "workspace"
FILE_DEVELOPER = ".developer"
FILE_JOURNAL_PREFIX = "journal-"
MAX_LINES = 2000


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


def ensure_developer(repo_root: Path):
    """Ensure developer is initialized"""
    developer = get_developer(repo_root)
    if not developer:
        print("Error: Developer not initialized.", file=sys.stderr)
        print("Run: python .trellis/scripts/init_developer.py <name>", file=sys.stderr)
        sys.exit(1)


def get_dev_dir(repo_root: Path) -> Path:
    """Get developer workspace directory"""
    developer = get_developer(repo_root)
    return repo_root / DIR_WORKFLOW / DIR_WORKSPACE / developer


def get_latest_journal_info(dev_dir: Path) -> tuple[Path | None, int, int]:
    """
    Get latest journal file info.
    Returns: (file_path, number, line_count)
    """
    latest_file = None
    latest_num = -1
    
    for f in dev_dir.glob(f"{FILE_JOURNAL_PREFIX}*.md"):
        if f.is_file():
            match = re.search(rf"{FILE_JOURNAL_PREFIX}(\d+)\.md$", f.name)
            if match:
                num = int(match.group(1))
                if num > latest_num:
                    latest_num = num
                    latest_file = f
    
    if latest_file:
        lines = len(latest_file.read_text(encoding="utf-8").split("\n"))
        return latest_file, latest_num, lines
    
    return None, 0, 0


def get_current_session(index_file: Path) -> int:
    """Get current session number from index.md"""
    if not index_file.exists():
        return 0
    
    content = index_file.read_text(encoding="utf-8")
    for line in content.split("\n"):
        if "Total Sessions" in line:
            match = re.search(r":\s*(\d+)", line)
            if match:
                return int(match.group(1))
    return 0


def count_journal_files(dev_dir: Path, active_num: int) -> str:
    """Generate journal files table"""
    result = []
    active_file = f"{FILE_JOURNAL_PREFIX}{active_num}.md"
    
    journal_files = sorted(
        dev_dir.glob(f"{FILE_JOURNAL_PREFIX}*.md"),
        key=lambda f: int(re.search(r"\d+", f.name).group())
    )
    
    for f in reversed(journal_files):
        if f.is_file():
            filename = f.name
            lines = len(f.read_text(encoding="utf-8").split("\n"))
            status = "Active" if filename == active_file else "Archived"
            result.append(f"| `{filename}` | ~{lines} | {status} |")
    
    return "\n".join(result)


def create_new_journal_file(dev_dir: Path, num: int, developer: str) -> Path:
    """Create new journal file"""
    prev_num = num - 1
    new_file = dev_dir / f"{FILE_JOURNAL_PREFIX}{num}.md"
    today = datetime.now().strftime("%Y-%m-%d")
    
    content = f"""# Journal - {developer} (Part {num})

> Continuation from `{FILE_JOURNAL_PREFIX}{prev_num}.md` (archived at ~{MAX_LINES} lines)
> Started: {today}

---

"""
    
    new_file.write_text(content, encoding="utf-8")
    return new_file


def generate_session_content(
    session_num: int,
    title: str,
    commit: str,
    summary: str,
    extra_content: str
) -> str:
    """Generate session content"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Format commit table
    if commit and commit != "-":
        commit_table = "| Hash | Message |\n|------|---------|"
        for c in commit.split(","):
            c = c.strip()
            commit_table += f"\n| `{c}` | (see git log) |"
    else:
        commit_table = "(No commits - planning session)"
    
    return f"""

## Session {session_num}: {title}

**Date**: {today}
**Task**: {title}

### Summary

{summary}

### Main Changes

{extra_content}

### Git Commits

{commit_table}

### Testing

- [OK] (Add test results)

### Status

[OK] **Completed**

### Next Steps

- None - task complete
"""


def update_index(
    index_file: Path,
    title: str,
    commit: str,
    new_session: int,
    active_file: str,
    dev_dir: Path,
    active_num: int
):
    """Update index.md with new session info"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Format commit for display
    commit_display = "-"
    if commit and commit != "-":
        commit_display = ", ".join(f"`{c.strip()}`" for c in commit.split(","))
    
    files_table = count_journal_files(dev_dir, active_num)
    
    print("Updating index.md for session {}...".format(new_session), file=sys.stderr)
    print("  Title: {}".format(title), file=sys.stderr)
    print("  Commit: {}".format(commit_display), file=sys.stderr)
    print("  Active File: {}".format(active_file), file=sys.stderr)
    print("", file=sys.stderr)
    
    if not index_file.exists():
        print("Error: index.md not found", file=sys.stderr)
        sys.exit(1)
    
    content = index_file.read_text(encoding="utf-8")
    
    if "@@@auto:current-status" not in content:
        print("Error: Markers not found in index.md", file=sys.stderr)
        sys.exit(1)
    
    # Process line by line
    lines = content.split("\n")
    result = []
    in_current_status = False
    in_active_documents = False
    in_session_history = False
    header_written = False
    
    for line in lines:
        if "@@@auto:current-status" in line:
            result.append(line)
            in_current_status = True
            result.append(f"- **Active File**: `{active_file}`")
            result.append(f"- **Total Sessions**: {new_session}")
            result.append(f"- **Last Active**: {today}")
            continue
        
        if "@@@/auto:current-status" in line:
            in_current_status = False
            result.append(line)
            continue
        
        if "@@@auto:active-documents" in line:
            result.append(line)
            in_active_documents = True
            result.append("| File | Lines | Status |")
            result.append("|------|-------|--------|")
            result.append(files_table)
            continue
        
        if "@@@/auto:active-documents" in line:
            in_active_documents = False
            result.append(line)
            continue
        
        if "@@@auto:session-history" in line:
            result.append(line)
            in_session_history = True
            header_written = False
            continue
        
        if "@@@/auto:session-history" in line:
            in_session_history = False
            result.append(line)
            continue
        
        if in_current_status or in_active_documents:
            continue
        
        if in_session_history:
            result.append(line)
            if line.startswith("|---") and not header_written:
                result.append(f"| {new_session} | {today} | {title} | {commit_display} |")
                header_written = True
            continue
        
        result.append(line)
    
    index_file.write_text("\n".join(result), encoding="utf-8")
    print("[OK] Updated index.md successfully!", file=sys.stderr)


def add_session(args):
    """Main function to add session"""
    repo_root = find_repo_root()
    ensure_developer(repo_root)
    
    developer = get_developer(repo_root)
    dev_dir = get_dev_dir(repo_root)
    index_file = dev_dir / "index.md"
    
    title = args.title
    commit = args.commit or "-"
    summary = args.summary or "(Add summary)"
    
    # Read extra content from stdin or file
    extra_content = "(Add details)"
    if args.content_file and Path(args.content_file).exists():
        extra_content = Path(args.content_file).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        extra_content = sys.stdin.read()
    
    # Get current state
    current_file, current_num, current_lines = get_latest_journal_info(dev_dir)
    current_session = get_current_session(index_file)
    new_session = current_session + 1
    
    # Generate session content
    session_content = generate_session_content(
        new_session, title, commit, summary, extra_content
    )
    content_lines = len(session_content.split("\n"))
    
    print("=" * 40, file=sys.stderr)
    print("ADD SESSION", file=sys.stderr)
    print("=" * 40, file=sys.stderr)
    print("", file=sys.stderr)
    print(f"Session: {new_session}", file=sys.stderr)
    print(f"Title: {title}", file=sys.stderr)
    print(f"Commit: {commit}", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"Current journal file: {FILE_JOURNAL_PREFIX}{current_num}.md", file=sys.stderr)
    print(f"Current lines: {current_lines}", file=sys.stderr)
    print(f"New content lines: {content_lines}", file=sys.stderr)
    print(f"Total after append: {current_lines + content_lines}", file=sys.stderr)
    print("", file=sys.stderr)
    
    # Determine target file
    target_file = current_file
    target_num = current_num
    
    if current_lines + content_lines > MAX_LINES:
        target_num = current_num + 1
        print(f"[!] Exceeds {MAX_LINES} lines, creating {FILE_JOURNAL_PREFIX}{target_num}.md", file=sys.stderr)
        target_file = create_new_journal_file(dev_dir, target_num, developer)
        print(f"Created: {target_file}", file=sys.stderr)
    
    # Append session content
    with open(target_file, "a", encoding="utf-8") as f:
        f.write(session_content)
    
    print(f"[OK] Appended session to {target_file.name}", file=sys.stderr)
    print("", file=sys.stderr)
    
    # Update index.md
    active_file = f"{FILE_JOURNAL_PREFIX}{target_num}.md"
    update_index(index_file, title, commit, new_session, active_file, dev_dir, target_num)
    
    print("", file=sys.stderr)
    print("=" * 40, file=sys.stderr)
    print(f"[OK] Session {new_session} added successfully!", file=sys.stderr)
    print("=" * 40, file=sys.stderr)
    print("", file=sys.stderr)
    print("Files updated:", file=sys.stderr)
    print(f"  - {target_file.name}", file=sys.stderr)
    print("  - index.md", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Add a new session to journal file and update index.md"
    )
    parser.add_argument("--title", required=True, help="Session title")
    parser.add_argument("--commit", help="Comma-separated commit hashes")
    parser.add_argument("--summary", help="Brief summary of the session")
    parser.add_argument("--content-file", help="Path to file with detailed content")
    
    args = parser.parse_args()
    add_session(args)


if __name__ == "__main__":
    main()
