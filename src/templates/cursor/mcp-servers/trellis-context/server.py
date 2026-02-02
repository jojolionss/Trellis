#!/usr/bin/env python3
"""
Trellis Context MCP Server

Provides context injection for Cursor subagents.
Replaces Claude Code's PreToolUse hook + updatedInput mechanism.

Tools:
- get_agent_context: Get complete context for a specific agent type
- mask_tool_results: Compress/trim large tool results to save context tokens
- memory_save: Save important information to long-term memory (Personal Edition)
- memory_search: Search long-term memory (Personal Edition)
- memory_flush: Flush a session summary into long-term memory (Personal Edition)
- get_current_task: Get current task information
- set_current_task: Set current task path
- update_phase: Update task.json current_phase
- list_tasks: List all tasks
- create_task: Create a new task
- match_skills: Find skills that match a prompt and file context

Usage in subagent prompt:
"First, call trellis-context MCP's get_agent_context tool with your agent type,
then follow the returned context to complete your task."
"""

import json
import math
import os
import re
import uuid
import sys
import subprocess
import importlib.util
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# =============================================================================
# Auto-install Dependencies (runs once at startup)
# =============================================================================

def _ensure_dependencies() -> None:
    """
    Ensure required runtime deps are installed.

    This is a convenience for Cursor Personal Edition so users can run the MCP
    server without manual `pip install`. Set `TRELLIS_MCP_NO_AUTO_INSTALL=1` to
    disable auto-install.
    """
    disable = os.environ.get("TRELLIS_MCP_NO_AUTO_INSTALL", "").strip().lower()
    if disable in {"1", "true", "yes"}:
        return

    # Keep this list in sync with requirements.txt for this MCP server template.
    required = {
        "mcp": "mcp",
        # Skill matching uses YAML frontmatter.
        "yaml": "pyyaml",
        # Regex triggers use the third-party `regex` module for timeout support.
        "regex": "regex",
    }

    missing: list[str] = []
    for module, package in required.items():
        if importlib.util.find_spec(module) is None:
            missing.append(package)

    if not missing:
        return

    print(f"Installing missing dependencies: {', '.join(missing)}...", file=sys.stderr)

    # Best-effort install: global -> user-site.
    commands = [
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *missing],
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--user", *missing],
    ]
    for cmd in commands:
        try:
            subprocess.check_call(cmd)
            return
        except subprocess.CalledProcessError:
            continue

    print(f"Warning: Failed to install dependencies: {missing}", file=sys.stderr)

_ensure_dependencies()

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ModuleNotFoundError as e:
    raise ModuleNotFoundError(
        "Missing dependency 'mcp'. Install it with `pip install mcp` (or set up your environment so this MCP server can auto-install it)."
    ) from e

# Import skills matcher (local module; depends on pyyaml/regex per requirements.txt)
try:
    import skills_matcher
    SKILLS_MATCHER = skills_matcher.SkillsMatcher()
except ImportError:
    skills_matcher = None  # type: ignore
    SKILLS_MATCHER = None

# =============================================================================
# Observation Masking (Context Compression)
# =============================================================================

DEFAULT_MASK_CONFIG = {
    "keep_recent_turns": 5,  # Reserved for future use (Cursor/IDE integration)
    "head_chars": 500,
    "tail_chars": 500,
    "enabled_tools": ["Read", "Grep", "Shell", "Glob"],
}


def soft_trim(text: str, head_chars: int = 500, tail_chars: int = 500) -> str:
    """Trim text while preserving head and tail."""
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, indent=2)

    # Don't trim if under threshold (keep some buffer so small logs remain intact)
    if len(text) <= (head_chars + tail_chars + 100):
        return text

    head = text[:head_chars]
    tail = text[-tail_chars:] if tail_chars > 0 else ""
    truncated = len(text) - len(head) - len(tail)

    return f"{head}\n...[{truncated} chars truncated]...\n{tail}"


def mask_tool_result(tool_name: str, result: Any, strategy: str = "soft_trim", *, head_chars: int | None = None, tail_chars: int | None = None) -> str:
    """Mask a tool result according to strategy."""
    tool_name = tool_name or "Unknown"
    strategy = (strategy or "soft_trim").strip()

    hc = int(head_chars) if head_chars is not None else int(DEFAULT_MASK_CONFIG["head_chars"])
    tc = int(tail_chars) if tail_chars is not None else int(DEFAULT_MASK_CONFIG["tail_chars"])

    # Normalize to string
    if isinstance(result, str):
        text = result
    else:
        try:
            text = json.dumps(result, ensure_ascii=False, indent=2)
        except Exception:
            text = str(result)

    if strategy == "soft_trim":
        return soft_trim(text, head_chars=hc, tail_chars=tc)

    # "summary" and "full_compress" are heuristic (no LLM in server).
    if strategy == "summary":
        # Smaller trims + basic stats
        lines = text.count("\n") + 1 if text else 0
        summary_head = soft_trim(text, head_chars=min(200, hc), tail_chars=min(200, tc))
        return f"[summary:{tool_name}] {len(text)} chars, {lines} lines\n\n{summary_head}"

    if strategy == "full_compress":
        # Aggressive: keep only head and a short tail
        return soft_trim(text, head_chars=min(300, hc), tail_chars=min(120, tc))

    # Unknown strategy: return as-is
    return text


# =============================================================================
# Long-term Memory (Personal Edition)
# =============================================================================

MEMORY_CATEGORY_TO_FILE = {
    "decision": "decisions.jsonl",
    "preference": "preferences.jsonl",
    "pattern": "patterns.jsonl",
}

MEMORY_INDEX_FILE = "index.json"


def _trellis_user_dir() -> Path:
    """User-level Trellis directory (~/.trellis)."""
    return Path.home() / ".trellis"


def _memory_dir() -> Path:
    return _trellis_user_dir() / "memory"


def _default_memory_index() -> dict[str, Any]:
    return {
        "last_updated": None,
        "counts": {"decisions": 0, "preferences": 0, "patterns": 0},
        "keywords": {},
    }


def _ensure_memory_store() -> Path:
    mem_dir = _memory_dir()
    mem_dir.mkdir(parents=True, exist_ok=True)

    # Ensure category files exist (append-only JSONL)
    for filename in MEMORY_CATEGORY_TO_FILE.values():
        path = mem_dir / filename
        if not path.exists():
            path.write_text("", encoding="utf-8")

    # Ensure index exists
    index_path = mem_dir / MEMORY_INDEX_FILE
    if not index_path.exists():
        index_path.write_text(json.dumps(_default_memory_index(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return mem_dir


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in re.findall(r"[a-zA-Z0-9_]+", text)]


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        # Accept "Z" suffix by converting to "+00:00"
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _load_memory_index(mem_dir: Path) -> dict[str, Any]:
    index_path = mem_dir / MEMORY_INDEX_FILE
    try:
        data = json.loads(index_path.read_text(encoding="utf-8") or "{}")
        if not isinstance(data, dict):
            return _default_memory_index()
        # Fill missing keys
        base = _default_memory_index()
        base.update(data)
        if not isinstance(base.get("counts"), dict):
            base["counts"] = _default_memory_index()["counts"]
        if not isinstance(base.get("keywords"), dict):
            base["keywords"] = {}
        return base
    except Exception:
        return _default_memory_index()


def _save_memory_index(mem_dir: Path, index: dict[str, Any]) -> None:
    index_path = mem_dir / MEMORY_INDEX_FILE
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, item: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _memory_plural_key(category: str) -> str:
    return {
        "decision": "decisions",
        "preference": "preferences",
        "pattern": "patterns",
    }.get(category, "patterns")


def _update_index_for_entry(index: dict[str, Any], entry: dict[str, Any], category: str) -> dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    index["last_updated"] = now_iso

    plural = _memory_plural_key(category)
    counts = index.setdefault("counts", {})
    counts[plural] = int(counts.get(plural, 0)) + 1

    keywords = index.setdefault("keywords", {})
    entry_id = entry.get("id")
    # Index tags as keywords (cheap + predictable).
    for tag in entry.get("tags") or []:
        if not isinstance(tag, str) or not tag.strip():
            continue
        key = tag.strip().lower()
        ids = keywords.setdefault(key, [])
        if isinstance(ids, list) and entry_id and entry_id not in ids:
            ids.append(entry_id)

    return index


def memory_save_entry(category: str, content: str, tags: list[str] | None = None, importance: int | None = None) -> dict[str, Any]:
    mem_dir = _ensure_memory_store()

    if category not in MEMORY_CATEGORY_TO_FILE:
        raise ValueError(f"Invalid category: {category}")

    if not isinstance(content, str) or not content.strip():
        raise ValueError("content is required")

    tags = tags or []
    if not isinstance(tags, list):
        tags = []
    tags = [t for t in tags if isinstance(t, str) and t.strip()]

    imp = int(importance) if importance is not None else 3
    imp = max(1, min(5, imp))

    entry = {
        "id": uuid.uuid4().hex,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "content": content.strip(),
        "tags": tags,
        "importance": imp,
    }

    jsonl_path = mem_dir / MEMORY_CATEGORY_TO_FILE[category]
    _append_jsonl(jsonl_path, entry)

    index = _load_memory_index(mem_dir)
    index = _update_index_for_entry(index, entry, category)
    _save_memory_index(mem_dir, index)

    return entry


def _load_memories(mem_dir: Path, category: str | None = None) -> list[dict[str, Any]]:
    files: list[Path] = []
    if category:
        filename = MEMORY_CATEGORY_TO_FILE.get(category)
        if not filename:
            return []
        files = [mem_dir / filename]
    else:
        files = [mem_dir / f for f in MEMORY_CATEGORY_TO_FILE.values()]

    memories: list[dict[str, Any]] = []
    for path in files:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    memories.append(item)
            except Exception:
                continue
    return memories


def memory_search_entries(query: str, category: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    if not isinstance(query, str) or not query.strip():
        return []

    mem_dir = _ensure_memory_store()
    memories = _load_memories(mem_dir, category=category)
    if not memories:
        return []

    keywords = _tokenize(query)
    if not keywords:
        return []

    # Build document frequencies for query keywords
    df: dict[str, int] = {kw: 0 for kw in set(keywords)}
    per_doc_tokens: list[set[str]] = []

    for m in memories:
        combined = f"{m.get('content', '')}\n{' '.join(m.get('tags') or [])}"
        toks = set(_tokenize(combined))
        per_doc_tokens.append(toks)
        for kw in df:
            if kw in toks:
                df[kw] += 1

    n_docs = len(memories)
    idf: dict[str, float] = {kw: (math.log((n_docs + 1) / (df[kw] + 1)) + 1.0) for kw in df}

    now = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []

    for m, toks in zip(memories, per_doc_tokens, strict=False):
        combined = f"{m.get('content', '')}\n{' '.join(m.get('tags') or [])}"
        token_list = _tokenize(combined)
        counts = Counter(token_list)

        base = 0.0
        for kw in df:
            tf = float(counts.get(kw, 0))
            if tf > 0:
                base += tf * idf[kw]

        if base <= 0:
            continue

        # Time decay: older memories rank lower (min 0.5x)
        ts = _parse_ts(m.get("ts"))
        age_days = (now - ts).days if ts else 9999
        time_factor = max(0.5, 1.0 - (age_days / 60.0))

        # Importance bonus
        imp = m.get("importance", 3)
        try:
            imp_val = max(1, min(5, int(imp)))
        except Exception:
            imp_val = 3
        importance_factor = imp_val / 5.0

        score = base * time_factor * importance_factor
        if score <= 0:
            continue

        item = dict(m)
        item["score"] = round(score, 6)
        results.append(item)

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results[: max(1, int(limit or 10))]


# =============================================================================
# Soul System (Personalization)
# =============================================================================

SOUL_FILENAME = "SOUL.md"
IDENTITY_FILENAME = "IDENTITY.md"

SOUL_TEMPLATE = """# AI Soul Configuration

## Core Values

Define what matters most in your development work:

- Code Quality: {high/medium} - How much to prioritize clean code over speed
- Innovation: {high/medium/low} - Willingness to suggest new approaches
- Safety: {high/medium} - Caution level for destructive operations

## Decision Principles

When to ask vs proceed:

- Ambiguous requirements: {ask/clarify/assume}
- Multiple valid approaches: {ask/choose best/suggest options}
- Destructive operations: {always ask/warn and proceed/just do it}

## Expertise Focus

Areas where deeper knowledge should be applied:

- Languages: TypeScript, Python, Go
- Frameworks: React, FastAPI, Node.js
- Domains: Web development, DevOps, Data processing

## Anti-Patterns to Avoid

Things that should never happen:

- Never commit secrets to git
- Never run destructive operations without confirmation
- Never delete user data without an explicit request
"""

IDENTITY_TEMPLATE = """# AI Identity

## Communication Style

- Language: English (use Chinese for Chinese input)
- Tone: Professional but friendly
- Verbosity: Concise (expand only when asked)

## Response Preferences

- Code blocks: Prefer fenced code blocks
- Explanations: Before code, not after
- Examples: Provide when introducing new concepts

## Formatting

- Use markdown headers for structure
- Use bullet points for lists
- Use tables for comparisons
- Use code fences for all code
"""


def _ensure_soul_identity_templates() -> tuple[Path, Path]:
    base = _trellis_user_dir()
    base.mkdir(parents=True, exist_ok=True)

    soul_path = base / SOUL_FILENAME
    identity_path = base / IDENTITY_FILENAME

    if not soul_path.exists():
        soul_path.write_text(SOUL_TEMPLATE.strip() + "\n", encoding="utf-8")
    if not identity_path.exists():
        identity_path.write_text(IDENTITY_TEMPLATE.strip() + "\n", encoding="utf-8")

    return soul_path, identity_path


def _load_soul_identity_context() -> str | None:
    soul_path, identity_path = _ensure_soul_identity_templates()
    parts: list[str] = []

    try:
        if soul_path.exists():
            soul_text = soul_path.read_text(encoding="utf-8")
            parts.append(
                f"=== {soul_path} (Soul Configuration) ===\n"
                f"{soft_trim(soul_text, head_chars=800, tail_chars=400)}"
            )
    except Exception:
        pass

    try:
        if identity_path.exists():
            identity_text = identity_path.read_text(encoding="utf-8")
            parts.append(
                f"=== {identity_path} (Identity Configuration) ===\n"
                f"{soft_trim(identity_text, head_chars=800, tail_chars=400)}"
            )
    except Exception:
        pass

    return "\n\n".join(parts) if parts else None

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


def get_developer_name(root: str) -> str:
    """
    Personal Edition: single-user mode.

    Always use the default workspace (`.trellis/workspace/default/`).
    This intentionally ignores `.trellis/.developer` while keeping existing
    task paths (from `.trellis/.current-task`) working for backward compatibility.
    """
    return "default"


def _safe_resolve_under_base(base_path: str, rel_path: str) -> Path | None:
    """
    Resolve a relative path under base_path, preventing path traversal.

    Returns None if rel_path escapes base_path (or is invalid).
    """
    if not isinstance(rel_path, str) or not rel_path.strip():
        return None

    base = Path(base_path).resolve()
    try:
        candidate = (base / rel_path).resolve()
    except Exception:
        return None

    try:
        candidate.relative_to(base)
    except Exception:
        return None

    return candidate


def read_file_content(base_path: str, file_path: str) -> str | None:
    """Read file content, return None if file doesn't exist"""
    full_path = _safe_resolve_under_base(base_path, file_path)
    if full_path is None or not full_path.exists() or not full_path.is_file():
        return None

    try:
        content = full_path.read_text(encoding="utf-8")
        # Automatically trim very large injected context to save tokens.
        if "Read" in DEFAULT_MASK_CONFIG.get("enabled_tools", []):
            return soft_trim(
                content,
                head_chars=int(DEFAULT_MASK_CONFIG["head_chars"]),
                tail_chars=int(DEFAULT_MASK_CONFIG["tail_chars"]),
            )
        return content
    except Exception:
        return None


def read_directory_contents(base_path: str, dir_path: str, max_files: int = 20) -> list[tuple[str, str]]:
    """Read all .md files in a directory"""
    full_dir = _safe_resolve_under_base(base_path, dir_path)
    if full_dir is None or not full_dir.exists() or not full_dir.is_dir():
        return []

    results: list[tuple[str, str]] = []
    try:
        md_files = sorted([p for p in full_dir.iterdir() if p.is_file() and p.name.endswith(".md")], key=lambda p: p.name)
        for p in md_files[:max_files]:
            relative_path = (Path(dir_path) / p.name).as_posix()
            try:
                content = p.read_text(encoding="utf-8")
                if "Read" in DEFAULT_MASK_CONFIG.get("enabled_tools", []):
                    content = soft_trim(
                        content,
                        head_chars=int(DEFAULT_MASK_CONFIG["head_chars"]),
                        tail_chars=int(DEFAULT_MASK_CONFIG["tail_chars"]),
                    )
                results.append((relative_path, content))
            except Exception:
                continue
    except Exception:
        pass
    return results


def read_jsonl_entries(base_path: str, jsonl_path: str) -> list[tuple[str, str]]:
    """Read all file/directory contents referenced in jsonl file"""
    full_path = _safe_resolve_under_base(base_path, jsonl_path)
    if full_path is None or not full_path.exists() or not full_path.is_file():
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
            name="mask_tool_results",
            description="Compress/trim large tool results to save context tokens (Observation Masking).",
            inputSchema={
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "description": "Name of the tool whose result to mask"},
                    "result": {"description": "Original tool result (string or JSON-serializable)"},
                    "strategy": {
                        "type": "string",
                        "description": "Masking strategy",
                        "enum": ["soft_trim", "full_compress", "summary"],
                        "default": "soft_trim",
                    },
                    "head_chars": {"type": "integer", "description": "Override head chars (optional)"},
                    "tail_chars": {"type": "integer", "description": "Override tail chars (optional)"},
                },
                "required": ["tool_name", "result"],
            },
        ),
        Tool(
            name="memory_save",
            description="Save important information to long-term memory (Personal Edition).",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["decision", "preference", "pattern"],
                        "description": "Memory category",
                    },
                    "content": {"type": "string", "description": "Memory content"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for search (optional)"},
                    "importance": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Importance 1-5 (optional)"},
                },
                "required": ["category", "content"],
            },
        ),
        Tool(
            name="memory_search",
            description="Search long-term memory with keyword matching and time decay (Personal Edition).",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "category": {"type": "string", "enum": ["decision", "preference", "pattern"], "description": "Optional category filter"},
                    "limit": {"type": "integer", "default": 10, "description": "Max results"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="memory_flush",
            description="Manually flush a session summary into long-term memory (Personal Edition).",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["decision", "preference", "pattern"],
                        "default": "pattern",
                        "description": "Which memory category to store the flush under",
                    },
                    "content": {"type": "string", "description": "Summary / content to save"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags (optional)"},
                    "importance": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Importance 1-5 (optional)"},
                },
                "required": ["content"],
            },
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
        ),
        Tool(
            name="match_skills",
            description="Find skills that match a prompt and optional file context. Skills are defined in SKILL.md files with triggers (keywords, patterns, files). Returns matched skills sorted by relevance score.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "User prompt to match against skill triggers (keywords, regex patterns)"
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional file paths for context-based matching (glob patterns in skill triggers)"
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 5,
                        "description": "Maximum number of matching skills to return (1-50)"
                    },
                    "project_root": {
                        "type": "string",
                        "description": "Optional project root for project-level skills (.trellis/skills/)"
                    }
                },
                "required": ["prompt"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls"""
    
    project_root = arguments.get("project_root") or find_trellis_root()
    
    # match_skills can run without a Trellis project (uses global skills dirs)
    if not project_root and name != "match_skills":
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

        # Soul / Identity injection (Personal Edition)
        soul_ctx = _load_soul_identity_context()
        if soul_ctx:
            context = f"{soul_ctx}\n\n{context}"
        
        full_prompt = build_agent_prompt(agent_type, context)
        
        return [TextContent(type="text", text=full_prompt)]

    elif name == "mask_tool_results":
        tool_name = arguments.get("tool_name") or "Unknown"
        result = arguments.get("result")
        strategy = arguments.get("strategy", "soft_trim")
        head_chars = arguments.get("head_chars")
        tail_chars = arguments.get("tail_chars")

        masked = mask_tool_result(tool_name, result, strategy=strategy, head_chars=head_chars, tail_chars=tail_chars)
        return [TextContent(type="text", text=masked)]

    elif name == "memory_save":
        try:
            category = arguments.get("category")
            content = arguments.get("content")
            tags = arguments.get("tags")
            importance = arguments.get("importance")

            entry = memory_save_entry(category, content, tags=tags, importance=importance)
            return [TextContent(type="text", text=json.dumps(entry, indent=2, ensure_ascii=False))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error saving memory: {e}")]

    elif name == "memory_search":
        try:
            query = arguments.get("query", "")
            category = arguments.get("category")
            limit = arguments.get("limit", 10)
            results = memory_search_entries(query, category=category, limit=limit)
            return [TextContent(type="text", text=json.dumps(results, indent=2, ensure_ascii=False))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error searching memory: {e}")]

    elif name == "memory_flush":
        try:
            category = arguments.get("category", "pattern")
            content = arguments.get("content") or arguments.get("summary") or ""
            tags = arguments.get("tags") or []
            importance = arguments.get("importance")

            if not isinstance(tags, list):
                tags = []
            tags = [t for t in tags if isinstance(t, str) and t.strip()]
            if "session-summary" not in [t.lower() for t in tags]:
                tags.append("session-summary")

            entry = memory_save_entry(category, content, tags=tags, importance=importance)
            return [TextContent(type="text", text=json.dumps(entry, indent=2, ensure_ascii=False))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error flushing memory: {e}")]
    
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

    elif name == "match_skills":
        # Check if skills_matcher is available
        if SKILLS_MATCHER is None:
            return [TextContent(
                type="text",
                text="Error: Skills matching is not available. skills_matcher.py may be missing.\n"
                     "Please ensure the trellis-context server includes skills_matcher.py and restart Cursor."
            )]

        prompt = arguments.get("prompt")
        if prompt is None:
            return [TextContent(type="text", text="Error: prompt is required")]

        files = arguments.get("files", [])
        max_results = arguments.get("max_results", 5)

        # Validate files parameter
        if not isinstance(files, list):
            files = []
        files = [str(f) for f in files if f is not None]

        # Validate max_results
        try:
            max_results = int(max_results)
        except (TypeError, ValueError):
            max_results = 5
        max_results = max(1, min(50, max_results))

        # Perform matching
        matches = SKILLS_MATCHER.match(str(prompt), files, project_root)

        # Format results
        results: list[dict[str, Any]] = []
        for m in matches[:max_results]:
            results.append({
                "name": m.skill.name,
                "description": m.skill.description,
                "score": m.score,
                "matched_by": m.matched_by,
                "path": m.skill.path,
            })

        return [TextContent(type="text", text=json.dumps(results, indent=2, ensure_ascii=False))]
    
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
