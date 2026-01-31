# Shell Script Conventions

> Standards for shell scripts in the `.trellis/scripts/` directory.

---

## Overview

This project uses Bash shell scripts for workflow automation. All scripts follow consistent patterns for organization, error handling, and output formatting. Scripts are organized into **library files** (sourced by other scripts) and **entry scripts** (executed directly).

---

## Directory Structure

```
.trellis/scripts/
├── common/               # Library files (sourced, not executed)
│   ├── paths.sh          # Path constants and functions
│   ├── developer.sh      # Developer identity management
│   ├── task-queue.sh     # Task queue CRUD
│   ├── task-utils.sh     # Task helper functions
│   ├── phase.sh          # Multi-agent phase tracking
│   ├── registry.sh       # Agent registry management
│   ├── worktree.sh       # Git worktree utilities
│   └── git-context.sh    # Git/session context
├── multi-agent/          # Multi-agent pipeline scripts
│   ├── start.sh
│   ├── status.sh
│   ├── cleanup.sh
│   └── create-pr.sh
├── task.sh               # Main task management CLI
├── get-context.sh        # Session context retrieval
├── init-developer.sh     # Developer initialization
├── get-developer.sh      # Get current developer
└── add-session.sh        # Session recording
```

---

## File Header Format

### Library Files (common/*.sh)

Library files must include a header documenting usage and exports:

```bash
#!/bin/bash
# Short description of what this library provides
#
# Usage: source this file in other scripts
#   source "$(dirname "$0")/common/filename.sh"
#
# Provides:
#   function_name_1      - Brief description
#   function_name_2      - Brief description
#   CONSTANT_NAME        - Brief description (if exported)
```

**Example** (`common/paths.sh`):

```bash
#!/bin/bash
# Common path utilities for Trellis workflow
#
# Usage: source this file in other scripts
#   source "$(dirname "$0")/common/paths.sh"
#
# Provides:
#   get_repo_root          - Get repository root directory
#   get_developer          - Get developer name
#   get_tasks_dir          - Get tasks directory path
#   get_workspace_dir      - Get workspace directory path
```

### Entry Scripts

Entry scripts include usage examples and available commands:

```bash
#!/bin/bash
# Script Name - Brief description
#
# Usage:
#   ./script.sh <command> [options]
#   ./script.sh command1 <arg>       # Description
#   ./script.sh command2 [--flag]    # Description
#
# Commands:
#   command1    - What it does
#   command2    - What it does
```

---

## Dependency Loading

### Pattern: Conditional Source

Libraries ensure their dependencies are loaded before use:

```bash
# Ensure paths.sh is loaded (required dependency)
if ! type get_repo_root &>/dev/null; then
  source "$(dirname "${BASH_SOURCE[0]}")/paths.sh"
fi
```

### Pattern: Script Directory Detection

Always use `BASH_SOURCE[0]` to get the script's directory:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common/paths.sh"
source "$SCRIPT_DIR/common/developer.sh"
```

**Why**: This works correctly regardless of where the script is called from.

---

## Section Separators

Use consistent section separators to organize code:

```bash
# =============================================================================
# Section Name
# =============================================================================

function_in_section() {
  # ...
}

another_function() {
  # ...
}

# =============================================================================
# Next Section
# =============================================================================
```

**Standard sections for entry scripts**:
1. Constants / Configuration
2. Helper Functions
3. Command Implementations (cmd_*)
4. Help / Usage
5. Main Entry (case statement)

---

## Constants

### Naming Convention

| Prefix | Usage | Example |
|--------|-------|---------|
| `DIR_` | Directory names | `DIR_WORKFLOW=".trellis"` |
| `FILE_` | File names | `FILE_DEVELOPER=".developer"` |

### Location

Define all path constants in `common/paths.sh`:

```bash
# Directory names
DIR_WORKFLOW=".trellis"
DIR_WORKSPACE="workspace"
DIR_TASKS="tasks"
DIR_ARCHIVE="archive"
DIR_SPEC="spec"
DIR_SCRIPTS="scripts"

# File names
FILE_DEVELOPER=".developer"
FILE_CURRENT_TASK=".current-task"
FILE_TASK_JSON="task.json"
```

**Why**: Centralizing constants makes renaming directories easy.

---

## Color Definitions

Define colors at the top of entry scripts (after sourcing dependencies):

```bash
# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'  # No Color
```

### Usage

```bash
echo -e "${GREEN}Success message${NC}"
echo -e "${RED}Error message${NC}"
echo -e "${YELLOW}Warning message${NC}"
echo -e "${BLUE}Info/section header${NC}"
echo -e "${CYAN}Highlight/secondary info${NC}"
```

---

## Logging Functions

For scripts that need structured logging, define these functions:

```bash
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
```

### Output Conventions

| Type | Stream | Color | Example |
|------|--------|-------|---------|
| Success | stdout | GREEN | `echo -e "${GREEN}✓ Done${NC}"` |
| Error | stderr | RED | `echo -e "${RED}Error: message${NC}" >&2` |
| Warning | stderr | YELLOW | `echo -e "${YELLOW}Warning: message${NC}" >&2` |
| Info/Header | stdout | BLUE | `echo -e "${BLUE}=== Section ===${NC}"` |
| Progress | stdout | CYAN | `echo -e "${CYAN}Processing...${NC}"` |

---

## Entry Script Structure

Entry scripts follow this standard structure:

```bash
#!/bin/bash
# Script description
#
# Usage:
#   ./script.sh <command> [args]

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common/paths.sh"
source "$SCRIPT_DIR/common/developer.sh"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
# ... more colors
NC='\033[0m'

REPO_ROOT=$(get_repo_root)

# =============================================================================
# Command Implementations
# =============================================================================

cmd_command1() {
  # Implementation
}

cmd_command2() {
  # Implementation
}

# =============================================================================
# Help
# =============================================================================

show_usage() {
  cat << EOF
Script description

Usage:
  $0 command1 <arg>     Description
  $0 command2 [--flag]  Description

Examples:
  $0 command1 value
EOF
}

# =============================================================================
# Main Entry
# =============================================================================

case "${1:-}" in
  command1)
    shift
    cmd_command1 "$@"
    ;;
  command2)
    cmd_command2 "$2"
    ;;
  -h|--help|help)
    show_usage
    ;;
  *)
    show_usage
    exit 1
    ;;
esac
```

---

## Argument Parsing

### Simple Arguments

For commands with positional arguments:

```bash
cmd_example() {
  local arg1="$1"
  local arg2="$2"

  if [[ -z "$arg1" ]]; then
    echo -e "${RED}Error: arg1 is required${NC}" >&2
    exit 1
  fi
}
```

### Options with Flags

For commands with optional flags:

```bash
cmd_create() {
  local title=""
  local priority="P2"
  local slug=""

  # Parse arguments
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --priority|-p)
        priority="$2"
        shift 2
        ;;
      --slug|-s)
        slug="$2"
        shift 2
        ;;
      -*)
        echo -e "${RED}Error: Unknown option $1${NC}" >&2
        exit 1
        ;;
      *)
        if [[ -z "$title" ]]; then
          title="$1"
        fi
        shift
        ;;
    esac
  done

  # Validate required fields
  if [[ -z "$title" ]]; then
    echo -e "${RED}Error: title is required${NC}" >&2
    echo "Usage: $0 create <title> [--priority P0|P1|P2|P3]" >&2
    exit 1
  fi
}
```

---

## Path Handling

### Relative vs Absolute Paths

Support both relative and absolute paths in commands:

```bash
cmd_process() {
  local target_dir="$1"

  # Convert relative to absolute
  if [[ ! "$target_dir" = /* ]]; then
    target_dir="$REPO_ROOT/$target_dir"
  fi

  if [[ ! -d "$target_dir" ]]; then
    echo -e "${RED}Error: Directory not found: $target_dir${NC}" >&2
    exit 1
  fi
}
```

### Path Functions

Use helper functions from `common/paths.sh`:

```bash
# Get repository root (finds nearest .trellis/ directory)
local repo_root=$(get_repo_root)

# Get workflow paths
local tasks_dir=$(get_tasks_dir "$repo_root")
local workspace_dir=$(get_workspace_dir "$repo_root")

# Get current task
local current=$(get_current_task "$repo_root")
```

---

## Error Handling

### Exit on Error

Always use `set -e` at the start of entry scripts:

```bash
#!/bin/bash
set -e  # Exit immediately on error
```

### Error Messages

Always send error messages to stderr:

```bash
# Good: Error to stderr
echo -e "${RED}Error: File not found${NC}" >&2
exit 1

# Bad: Error to stdout
echo -e "${RED}Error: File not found${NC}"
exit 1
```

### Validation Pattern

Validate early and fail fast:

```bash
cmd_archive() {
  local task_name="$1"

  # Validate input
  if [[ -z "$task_name" ]]; then
    echo -e "${RED}Error: Task name is required${NC}" >&2
    echo "Usage: $0 archive <task-name>" >&2
    exit 1
  fi

  # Validate state
  ensure_developer  # Dies if no developer set

  # Validate target exists
  local task_dir=$(find_task_by_name "$task_name")
  if [[ -z "$task_dir" ]]; then
    echo -e "${RED}Error: Task not found: $task_name${NC}" >&2
    exit 1
  fi

  # Now do the actual work...
}
```

---

## Output Return Values

### Pattern: Output Path for Chaining

Commands that create resources should output the path for script chaining:

```bash
cmd_create() {
  # ... creation logic ...

  # Status messages to stderr (for human reading)
  echo -e "${GREEN}Created task: $dir_name${NC}" >&2

  # Return value to stdout (for script chaining)
  echo "$DIR_WORKFLOW/$DIR_TASKS/$dir_name"
}
```

**Usage**:
```bash
# Human sees status messages
# Script captures the path
TASK_DIR=$(./task.sh create "My Task")
```

---

## Function Naming

### Command Functions

Prefix command implementations with `cmd_`:

```bash
cmd_create()      # Handles "create" command
cmd_list()        # Handles "list" command
cmd_archive()     # Handles "archive" command
```

### Helper Functions

Use descriptive names without prefix:

```bash
ensure_developer()         # Validates developer is set
find_task_by_name()        # Searches for task
validate_jsonl()           # Validates JSONL file
```

### Private Functions

Prefix internal helpers with underscore:

```bash
_get_current_task_file()     # Internal helper
_parse_options()             # Internal helper
```

---

## DO / DON'T

### DO

- Include header documentation with `Usage:` and `Provides:`
- Use `set -e` in entry scripts
- Send error messages to stderr
- Use color codes consistently
- Support both relative and absolute paths
- Validate inputs early
- Output machine-readable values to stdout, human messages to stderr
- Use `${BASH_SOURCE[0]}` for script directory detection

### DON'T

- Don't hardcode paths - use constants from `paths.sh`
- Don't assume current directory - always use `$REPO_ROOT`
- Don't send errors to stdout
- Don't forget `shift` when parsing options
- Don't use `$0` for getting script directory (breaks when sourced)
- Don't omit the `NC` (no color) reset after colored output

---

## Common Mistakes

### Mistake 1: Forgetting to shift in option parsing

```bash
# Bad: Infinite loop
while [[ $# -gt 0 ]]; do
  case "$1" in
    --flag)
      flag=true
      # Missing: shift
      ;;
  esac
done

# Good: Always shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --flag)
      flag=true
      shift
      ;;
    --option)
      value="$2"
      shift 2  # Shift both flag and value
      ;;
  esac
done
```

### Mistake 2: Using $0 instead of BASH_SOURCE

```bash
# Bad: Breaks when sourced
SCRIPT_DIR="$(dirname "$0")"

# Good: Works when sourced or executed
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
```

### Mistake 3: Not quoting variables

```bash
# Bad: Breaks with spaces in paths
if [[ -d $target_dir ]]; then

# Good: Always quote
if [[ -d "$target_dir" ]]; then
```

### Mistake 4: Errors to stdout

```bash
# Bad: Error goes to stdout
echo "Error: Something failed"

# Good: Error to stderr
echo "Error: Something failed" >&2
```

---

## Examples

### Complete Library File

```bash
#!/bin/bash
# Developer identity management
#
# Usage: source this file in other scripts
#   source "$(dirname "$0")/common/developer.sh"
#
# Provides:
#   ensure_developer   - Exit if no developer set
#   get_developer_email - Get developer email

# Ensure paths.sh is loaded
if ! type get_repo_root &>/dev/null; then
  source "$(dirname "${BASH_SOURCE[0]}")/paths.sh"
fi

# =============================================================================
# Developer Functions
# =============================================================================

ensure_developer() {
  local repo_root="${1:-$(get_repo_root)}"
  local developer=$(get_developer "$repo_root")

  if [[ -z "$developer" ]]; then
    echo "Error: No developer set. Run init-developer.sh first." >&2
    exit 1
  fi
}

get_developer_email() {
  local repo_root="${1:-$(get_repo_root)}"
  local dev_file="$repo_root/$DIR_WORKFLOW/$FILE_DEVELOPER"

  if [[ -f "$dev_file" ]]; then
    grep "^email=" "$dev_file" 2>/dev/null | cut -d'=' -f2
  fi
}
```

### Complete Entry Script

See `.trellis/scripts/task.sh` for a comprehensive example of an entry script with multiple commands, option parsing, and proper error handling.
