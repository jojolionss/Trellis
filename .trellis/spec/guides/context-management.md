# Context Management Guide

> **Purpose**: Strategies for managing LLM context window and long-term memory.

---

## Observation Masking

"Observation Masking" is the technique of hiding verbose tool outputs from the LLM's context window when they aren't strictly necessary.

### When to Mask

- **Large File Reads**: If you only need a specific function, don't read the whole file if possible (or use `grep` first).
- **Long Terminal Output**: Truncate logs or build outputs.
- **Repetitive Status**: Don't repeatedly `ls` the same directory.

### How to Mask (in Trellis)

- Tools often have built-in truncation.
- Agents should summarize findings rather than dumping raw data into the conversation history if not needed for the next step.

## Long-Term Memory Strategy

LLMs have limited context windows. Trellis uses the file system as long-term memory.

### Memory Tiers

1. **Short-Term (Context Window)**:
   - Current conversation.
   - Recently read files.
   
2. **Mid-Term (Task Context)**:
   - `task.json`: Current task status.
   - `journal-*.md`: Work logs and thoughts.
   - `todo.md`: Active todo list.

3. **Long-Term (Repository)**:
   - `.trellis/spec/`: Guidelines and rules (The "Constitution").
   - `src/`: The codebase itself.
   - `docs/`: Documentation.

## Managing Context Overhead

- **Keep it Clean**: Don't pollute the context with failed attempts.
- **Summarize**: When switching agents or phases, summarize the state.
- **Reference by Path**: Instead of pasting file content, reference the file path if the agent can read it.
