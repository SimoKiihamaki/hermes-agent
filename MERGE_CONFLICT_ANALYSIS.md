# Hermes Agent Upstream Merge Conflict Analysis

**Generated:** 2026-03-24  
**Local:** 32 commits ahead (type hints, linting, AutoDev Phase 6)  
**Upstream:** 94 commits ahead (critical security fixes)  
**Common Ancestor:** `43bca6d107c86efc7e60a4a35ca8a55e1b4b4c1e`

---

## Executive Summary

⚠️ **HIGH RISK MERGE** - 38 files modified in both branches with significant divergence.

### Critical Upstream Security Fixes (Must Preserve)
| Commit | Description | Affected Files |
|--------|-------------|----------------|
| `73a88a02` | Shell injection in `_expand_path` via `~user` path suffix | `tools/file_operations.py` |
| `0791efe2` | SSRF protection in vision_tools and web_tools | `tools/vision_tools.py`, `tools/web_tools.py` |
| `ad5f973a` | Async SSRF redirect guard for httpx | `tools/vision_tools.py` |
| `ed805f57` | MCP-OAuth path traversal fixes | `tools/mcp_oauth.py` |
| `fa6f0695` | ANSI strip from write_file/patch content | `tools/file_tools.py` |

### New Security Files in Upstream (Must Add)
- `tools/url_safety.py` - SSRF protection (blocks private/internal IPs)
- `tools/ansi_strip.py` - ANSI escape sequence removal

---

## 100% Overlap Files (38 files)

### 🔴 CRITICAL CONFLICT RISK (8 files)
Files with both security-critical upstream changes AND significant local modifications:

| File | Upstream Change | Local Change | Risk |
|------|-----------------|--------------|------|
| `tools/web_tools.py` | SSRF protection via `is_safe_url()` | +743 lines (Page Storage System, SQLite FTS5) | **CRITICAL** |
| `tools/terminal_tool.py` | ANSI stripping, import refactoring | Type hints, AutoDev integration | **HIGH** |
| `tools/code_execution_tool.py` | ANSI stripping security fix | Type hints, signature changes | **HIGH** |
| `tools/file_operations.py` | Shell injection fix in `_expand_path` | Type hints, import cleanup | **HIGH** |
| `tools/vision_tools.py` | SSRF redirect guard, timeout config | Minor type fixes | **MEDIUM** |
| `tools/process_registry.py` | Import path changes | Extensive type hints | **MEDIUM** |
| `tools/file_tools.py` | ANSI stripping | Type hints, signature changes | **MEDIUM** |
| `tools/mcp_tool.py` | Security hardening | Type hints, OAuth changes | **MEDIUM** |

### 🟠 MODERATE CONFLICT RISK (12 files)
Files with overlapping changes but likely resolvable:

| File | Conflict Type |
|------|---------------|
| `tools/approval.py` | Minor overlap |
| `tools/browser_tool.py` | Security + local changes |
| `tools/skills_guard.py` | Security behavior change |
| `tools/skills_hub.py` | Feature additions both sides |
| `tools/rl_training_tool.py` | Minor overlap |
| `tools/voice_mode.py` | Minor overlap |
| `gateway/run.py` | Gateway hardening + local |
| `gateway/session.py` | Session management changes |
| `hermes_cli/main.py` | CLI changes both sides |
| `hermes_cli/config.py` | Config additions both sides |
| `cli.py` | CLI changes both sides |
| `run_agent.py` | Entry point changes |

### 🟢 LOWER CONFLICT RISK (18 files)
Files with changes in different sections (likely auto-merge):

```
gateway/platforms/discord.py
gateway/platforms/email.py
gateway/platforms/matrix.py
gateway/platforms/mattermost.py
gateway/platforms/telegram.py
hermes_cli/commands.py
hermes_cli/setup.py
hermes_cli/tools_config.py
model_tools.py
tests/hermes_cli/test_gateway_service.py
tests/tools/test_local_env_blocklist.py
tools/checkpoint_manager.py
tools/delegate_tool.py
tools/fuzzy_match.py
tools/memory_tool.py
tools/patch_parser.py
tools/send_message_tool.py
tools/session_search_tool.py
tools/todo_tool.py
toolsets.py
website/docs/reference/environment-variables.md
```

---

## Detailed Conflict Analysis

### 1. `tools/web_tools.py` - CRITICAL
**Upstream:** Adds SSRF protection at URL processing entry point
```python
# Upstream adds:
from tools.url_safety import is_safe_url
# Filters URLs before dispatch:
if not is_safe_url(url):
    ssrf_blocked.append({...})
```

**Local:** Adds complete Page Storage System (+743 lines)
```python
# Local adds:
import sqlite3
# New tools: web_page_search_tool, web_page_list_tool, etc.
# SQLite FTS5 full-text search
```

**Resolution Strategy:** 
- Merge upstream's SSRF protection into the URL processing section
- Keep local's Page Storage System (adds new functions, doesn't modify existing flow heavily)
- Ensure `is_safe_url()` check is applied before storage operations

### 2. `tools/file_operations.py` - HIGH
**Upstream:** Shell injection fix
```python
# Only expand ~username (not the full path) to avoid shell injection
expand_result = self._exec(f"echo ~{username}")
user_home = expand_result.stdout.strip()
suffix = path[1 + len(username):]  # e.g. "/rest/of/path"
return user_home + suffix
```

**Local:** Type hint cleanup only
```python
# Removed: import json
# Changed: from typing import ..., Tuple -> removed Tuple
```

**Resolution Strategy:**
- Take upstream's security fix as base
- Apply local type hint changes on top

### 3. `tools/terminal_tool.py` - HIGH
**Upstream:** ANSI stripping + import refactoring
```python
from tools.interrupt import is_interrupted, _interrupt_event
from tools.ansi_strip import strip_ansi
output = strip_ansi(output)
```

**Local:** Type hints + AutoDev changes

**Resolution Strategy:**
- Take upstream's security-hardened version
- Apply local type hints on methods
- Verify AutoDev integration still works

---

## New Files from Upstream (Add Without Conflict)

| File | Purpose |
|------|---------|
| `tools/url_safety.py` | SSRF protection - is_safe_url() |
| `tools/ansi_strip.py` | ANSI escape sequence removal |
| `tools/mcp_oauth.py` | OAuth security for MCP |
| `tools/cronjob_tools.py` | Cron-related tools |
| `tools/skill_manager_tool.py` | Skill management |

---

## Local-Only Files (No Conflict)

Files modified only locally (32 commits):
- `tools/hermes_autodev_tool.py` (631 new lines)
- `tools/autodev_bridge.py` (398 new lines)
- `tools/example_autodev_usage.py` (181 new lines)
- `tools/test_autodev_bridge.py` (227 new lines)
- `environments/tool_call_parsers/*.py` (multiple parsers)
- `skills/software-development/autodev/SKILL.md`
- Various test files with type hints

---

## Recommended Merge Strategy

### Phase 1: Preparation
1. Create merge branch from current main
2. Fetch latest upstream: `git fetch origin main`

### Phase 2: Add New Security Files
```bash
git checkout origin/main -- tools/url_safety.py
git checkout origin/main -- tools/ansi_strip.py
git checkout origin/main -- tools/mcp_oauth.py
```

### Phase 3: High-Priority Manual Merges
Handle in order of security criticality:
1. `tools/web_tools.py` - Critical SSRF + local features
2. `tools/file_operations.py` - Shell injection fix
3. `tools/terminal_tool.py` - ANSI stripping
4. `tools/code_execution_tool.py` - ANSI stripping
5. `tools/vision_tools.py` - SSRF redirect guard

### Phase 4: Automated Merge Attempt
```bash
git merge origin/main --no-commit
# Review conflicts, resolve manually
```

### Phase 5: Verification
1. Run test suite: `pytest tests/`
2. Verify security fixes are intact
3. Check type hints with mypy
4. Test AutoDev functionality

---

## Conflict Count Estimate

| Category | Count | Estimated Resolution Time |
|----------|-------|---------------------------|
| Critical (manual merge) | 8 | 2-4 hours |
| Moderate (likely manual) | 12 | 1-2 hours |
| Low (auto-merge) | 18 | 30 min |
| New files (add) | 5+ | 15 min |

**Total Estimated Effort:** 4-8 hours

---

## Security Checklist Post-Merge

- [ ] `is_safe_url()` called in all URL-fetching tools
- [ ] Shell injection fix in `_expand_path` preserved
- [ ] ANSI stripping applied to terminal/code execution output
- [ ] SSRF redirect guard in vision_tools
- [ ] MCP-OAuth path traversal fix preserved
- [ ] All test pass
- [ ] Type checking passes (mypy)
