# Personal Edition Guide

> **Purpose**: Customizing Trellis for your personal identity and coding style.

---

## Core Concepts

Trellis Personal Edition allows you to imbue the agent with a specific "Soul" or identity.

### Files

- **`SOUL.md`**: Defines the core personality, values, and high-level directives of the agent.
- **`IDENTITY.md`**: Defines the specific persona (e.g., "Senior Backend Engineer", "Security Specialist").

## Memory System

The Personal Edition enhances the standard memory system with user-specific preferences.

### User Preferences

- **Coding Style**: Preferred patterns (e.g., functional vs OOP).
- **Communication**: Concise vs verbose, formal vs casual.
- **Tools**: Preferred libraries or frameworks.

### Implementation

These preferences are typically loaded into the agent's system prompt or context at the start of a session.

## Customizing Your Agent

1. **Define `SOUL.md`**: What drives this agent? (e.g., "Rigorous correctness", "Creative exploration").
2. **Set `IDENTITY.md`**: Who is this agent?
3. **Tune Skills**: Add custom skills in `.cursor/skills/` that reflect your personal workflows.
