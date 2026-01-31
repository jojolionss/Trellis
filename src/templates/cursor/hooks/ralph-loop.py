#!/usr/bin/env python3
"""
Ralph Loop - SubagentStop Hook for Check Agent Loop Control (Cursor Version)

Based on the Ralph Wiggum technique for autonomous agent loops.
Uses completion markers to control when the check agent can stop.

Key difference from Claude Code version:
- Cursor does NOT support decision:block
- Instead, we use followup_message to trigger main agent to re-dispatch

State file: .trellis/.ralph-state.json
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# =============================================================================
# Configuration
# =============================================================================

MAX_ITERATIONS = 5  # Safety limit to prevent infinite loops
STATE_TIMEOUT_MINUTES = 30  # Reset state if older than this
STATE_FILE = ".trellis/.ralph-state.json"
WORKTREE_YAML = ".trellis/worktree.yaml"
DIR_WORKFLOW = ".trellis"
FILE_CURRENT_TASK = ".current-task"

# Only control loop for check agent
TARGET_AGENT = "check"


def find_trellis_root(start_path: str = None) -> str | None:
    """Find directory containing .trellis/ from start_path upwards"""
    if start_path is None:
        start_path = os.getcwd()
    
    current = Path(start_path).resolve()
    while current != current.parent:
        if (current / DIR_WORKFLOW).exists():
            return str(current)
        current = current.parent
    return None


def get_current_task(root: str) -> str | None:
    """Read current task directory path"""
    current_task_file = os.path.join(root, DIR_WORKFLOW, FILE_CURRENT_TASK)
    if not os.path.exists(current_task_file):
        return None

    try:
        with open(current_task_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else None
    except Exception:
        return None


def get_verify_commands(root: str) -> list[str]:
    """Read verify commands from worktree.yaml."""
    yaml_path = os.path.join(root, WORKTREE_YAML)
    if not os.path.exists(yaml_path):
        return []

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Simple YAML parsing for verify section
        lines = content.split("\n")
        in_verify_section = False
        commands = []

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("verify:"):
                in_verify_section = True
                continue

            if (
                not line.startswith(" ")
                and not line.startswith("\t")
                and stripped.endswith(":")
                and stripped != ""
            ):
                in_verify_section = False
                continue

            if in_verify_section:
                if stripped.startswith("#") or stripped == "":
                    continue
                if stripped.startswith("- "):
                    cmd = stripped[2:].strip()
                    if cmd:
                        commands.append(cmd)

        return commands
    except Exception:
        return []


def run_verify_commands(root: str, commands: list[str]) -> tuple[bool, str]:
    """Run verify commands and return (success, message)."""
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=root,
                capture_output=True,
                timeout=120,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode("utf-8", errors="replace")
                stdout = result.stdout.decode("utf-8", errors="replace")
                error_output = stderr or stdout
                if len(error_output) > 500:
                    error_output = error_output[:500] + "..."
                return False, f"Command failed: {cmd}\n{error_output}"
        except subprocess.TimeoutExpired:
            return False, f"Command timed out: {cmd}"
        except Exception as e:
            return False, f"Command error: {cmd} - {str(e)}"

    return True, "All verify commands passed"


def get_completion_markers(root: str, task_dir: str) -> list[str]:
    """Read check.jsonl and generate completion markers from reasons."""
    check_jsonl_path = os.path.join(root, task_dir, "check.jsonl")
    markers = []

    if not os.path.exists(check_jsonl_path):
        return ["ALL_CHECKS_FINISH"]

    try:
        with open(check_jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    reason = item.get("reason", "")
                    if reason:
                        marker = f"{reason.upper().replace(' ', '_')}_FINISH"
                        if marker not in markers:
                            markers.append(marker)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    if not markers:
        markers = ["ALL_CHECKS_FINISH"]

    return markers


def load_state(root: str) -> dict:
    """Load Ralph Loop state from file"""
    state_path = os.path.join(root, STATE_FILE)
    if not os.path.exists(state_path):
        return {"task": None, "iteration": 0, "started_at": None}

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"task": None, "iteration": 0, "started_at": None}


def save_state(root: str, state: dict) -> None:
    """Save Ralph Loop state to file"""
    state_path = os.path.join(root, STATE_FILE)
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def check_completion(agent_output: str, markers: list[str]) -> tuple[bool, list[str]]:
    """Check if all completion markers are present in agent output."""
    missing = []
    for marker in markers:
        if marker not in agent_output:
            missing.append(marker)

    return len(missing) == 0, missing


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    # Get subagent info
    subagent_type = input_data.get("subagent_type", "")
    summary = input_data.get("summary", "")
    task = input_data.get("task", "")
    loop_count = input_data.get("loop_count", 0)
    
    # Get workspace roots
    workspace_roots = input_data.get("workspace_roots", [])

    # Only control check agent
    if subagent_type != TARGET_AGENT:
        sys.exit(0)

    # Skip for finish phase
    if "[finish]" in task.lower():
        sys.exit(0)

    # Find project root from workspace_roots
    root = None
    for ws_root in workspace_roots:
        # Handle Cursor's path format: /E:/Projects/... -> E:\Projects\...
        if ws_root.startswith("/") and len(ws_root) > 2 and ws_root[2] == ":":
            ws_root = ws_root[1:].replace("/", "\\")
        
        if os.path.exists(os.path.join(ws_root, DIR_WORKFLOW)):
            root = ws_root
            break
    
    if not root:
        root = find_trellis_root()
    
    if not root:
        sys.exit(0)

    # Get current task
    task_dir = get_current_task(root)
    if not task_dir:
        sys.exit(0)

    # Load state
    state = load_state(root)

    # Reset state if task changed or state is too old
    should_reset = False
    if state.get("task") != task_dir:
        should_reset = True
    elif state.get("started_at"):
        try:
            started = datetime.fromisoformat(state["started_at"])
            if (datetime.now() - started).total_seconds() > STATE_TIMEOUT_MINUTES * 60:
                should_reset = True
        except (ValueError, TypeError):
            should_reset = True

    if should_reset:
        state = {
            "task": task_dir,
            "iteration": 0,
            "started_at": datetime.now().isoformat(),
        }

    # Increment iteration
    state["iteration"] = state.get("iteration", 0) + 1
    current_iteration = state["iteration"]

    # Save state
    save_state(root, state)

    # Safety check: max iterations
    if current_iteration >= MAX_ITERATIONS:
        state["iteration"] = 0
        save_state(root, state)
        # Allow completion - don't trigger followup
        sys.exit(0)

    # Check if verify commands are configured
    verify_commands = get_verify_commands(root)

    if verify_commands:
        # Use programmatic verification
        passed, message = run_verify_commands(root, verify_commands)

        if passed:
            state["iteration"] = 0
            save_state(root, state)
            sys.exit(0)  # Allow completion
        else:
            # Verification failed - trigger followup
            output = {
                "followup_message": f"[Ralph Loop {current_iteration}/{MAX_ITERATIONS}] Check verification failed:\n{message}\n\nPlease re-run check agent to fix the issues."
            }
            print(json.dumps(output, ensure_ascii=False))
            sys.exit(0)
    else:
        # No verify commands, use completion markers
        markers = get_completion_markers(root, task_dir)
        all_complete, missing = check_completion(summary, markers)

        if all_complete:
            state["iteration"] = 0
            save_state(root, state)
            sys.exit(0)  # Allow completion
        else:
            # Missing markers - trigger followup
            missing_str = ", ".join(missing)
            output = {
                "followup_message": f"[Ralph Loop {current_iteration}/{MAX_ITERATIONS}] Check agent incomplete. Missing markers: {missing_str}.\n\nIMPORTANT: The check agent must actually run the checks and output completion markers. Please re-dispatch the check agent."
            }
            print(json.dumps(output, ensure_ascii=False))
            sys.exit(0)


if __name__ == "__main__":
    main()
