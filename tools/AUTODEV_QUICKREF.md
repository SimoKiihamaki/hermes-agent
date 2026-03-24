# AutoDev Integration Quick Reference

## Basic Usage

### Standard Delegation
```python
delegate_task(
    goal="Your task description",
    context="Additional context",
    parent_agent=agent
)
```

### AutoDev Hierarchical Execution
```python
delegate_task(
    goal="Your task description",
    context="Additional context",
    task_type="autodev",  # <-- Add this
    parent_agent=agent
)
```

## When to Use Each Type

| Task Type | Best For | Example |
|-----------|----------|---------|
| `default` (or omit) | Quick fixes, debugging, research, focused tasks | "Fix null pointer in UserService.java:145" |
| `autodev` | Complex features, refactoring, multi-file changes | "Implement REST API for user management" |

## Key Differences

### Default (Standard)
- Single child agent
- Isolated execution
- Fast and focused
- No planning phase
- No review cycle

### AutoDev (Hierarchical)
- Manager→Coder→Reviewer flow
- Task decomposition
- Iterative refinement
- Code review built-in
- Better for complex tasks

## Role Mapping

```
Manager   → plan       (decompose task into subtasks)
Coder     → implement  (execute subtasks, write code)
Reviewer  → review     (validate changes, provide feedback)
```

## Result Format

Both types return JSON with similar structure:

```json
{
  "results": [{
    "status": "completed",
    "summary": "Task summary...",
    "duration_seconds": 10.5
  }],
  "total_duration_seconds": 10.6
}
```

AutoDev adds extra fields:
```json
{
  "results": [{
    ...
    "autodev_mode": true,
    "files_modified": ["file1.py", "file2.py"],
    "iterations": 2,
    "review_iterations": 1
  }],
  "autodev_mode": true
}
```

## Configuration

AutoDev behavior can be configured in the bridge:

```python
from tools.autodev_bridge import AutoDevConfig, HermesAutoDevBridge

config = AutoDevConfig(
    max_iterations=5,           # Review-implement cycles
    num_coders=2,               # Parallel coders
    num_reviewers=1,            # Reviewers
    timeout_seconds=600,        # Timeout
    enable_parallel_coding=True # Parallel execution
)

bridge = HermesAutoDevBridge(parent_agent, config)
```

## Error Handling

If AutoDev components unavailable:
```json
{
  "error": "AutoDev components not available...",
  "duration_seconds": 0.01
}
```

Standard delegation continues to work normally.

## Examples

### Example 1: Quick Bug Fix (use default)
```python
delegate_task(
    goal="Fix authentication timeout issue",
    context="Users getting logged out after 30 seconds",
    parent_agent=agent
)
```

### Example 2: Feature Implementation (use autodev)
```python
delegate_task(
    goal="Implement password reset functionality",
    context="Send email with reset link, expire after 1 hour",
    task_type="autodev",
    parent_agent=agent
)
```

### Example 3: Refactoring (use autodev)
```python
delegate_task(
    goal="Refactor database access layer",
    context="Extract common queries, add connection pooling",
    task_type="autodev",
    parent_agent=agent
)
```

## Debugging

Check if AutoDev available:
```python
from tools.autodev_bridge import AUTODEV_AVAILABLE

if AUTODEV_AVAILABLE:
    print("AutoDev ready for use")
else:
    print("AutoDev not available")
```

## Files

- Integration: `~/Projects/hermes-agent/tools/autodev_bridge.py`
- Handler: `~/Projects/hermes-agent/tools/delegate_tool.py`
- Tests: `~/Projects/hermes-agent/tools/test_autodev_bridge.py`
- Docs: `~/Projects/hermes-agent/tools/AUTODEV_INTEGRATION.md`
- Examples: `~/Projects/hermes-agent/tools/example_autodev_usage.py`
