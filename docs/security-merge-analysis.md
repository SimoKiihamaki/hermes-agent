# Security Merge Analysis Report
**Date:** 2026-03-24
**Branch Status:** Local (33 commits) vs Upstream (94 commits)

---

## Executive Summary

Three critical security fixes need to be merged from upstream:
1. **SSRF Protection** - Blocks requests to private/internal network addresses
2. **Shell Injection Prevention** - Fixes `~user/$(malicious)` path injection
3. **Workspace Path Restriction** - Prevents `@file:` references from accessing secrets

**Conflict Risk: HIGH** - Local has significant structural changes to `web_tools.py` (page storage system) that will conflict with upstream SSRF integration.

---

## 1. SSRF Protection (Commits: 0791efe2, ad5f973a)

### Files Affected
| File | Change Type | Conflict Risk |
|------|-------------|---------------|
| `tools/url_safety.py` | **NEW FILE** | None |
| `tools/vision_tools.py` | Modified | LOW |
| `tools/web_tools.py` | Modified | **HIGH** |
| `tests/tools/test_url_safety.py` | **NEW FILE** | None |
| `tests/tools/test_vision_tools.py` | Modified | LOW |
| `tests/tools/test_website_policy.py` | Modified | LOW |

### What the Changes Do
- Creates new `tools/url_safety.py` with `is_safe_url()` function that:
  - Resolves hostnames to IP addresses
  - Blocks private IP ranges (RFC 1918)
  - Blocks loopback (127.0.0.0/8), link-local (169.254.0.0/16)
  - **Blocks CGNAT range (100.64.0.0/10)** - NOT covered by Python's `is_private`
  - Blocks known internal hostnames (metadata.google.internal, metadata.goog)
  - **Fails closed** on DNS errors and unexpected exceptions

- `vision_tools.py` changes:
  - Adds SSRF check in `_validate_image_url()`
  - Adds async `_ssrf_redirect_guard()` event hook for httpx client
  - Prevents redirect-based SSRF bypass (302 to internal IP)
  - Adds configurable vision timeout from config.yaml

- `web_tools.py` changes:
  - Imports and uses `is_safe_url()` before each website_policy check
  - Moves SSRF filtering before backend dispatch (covers Parallel, Tavily, Firecrawl)

### Merge Conflicts
- **`tools/web_tools.py` - HIGH RISK**: Local has 2402 lines (page storage system with SQLite/FTS5), upstream is 1727 lines. Completely different structure.
- **Resolution Strategy**: 
  1. Keep local page storage infrastructure
  2. Add `from tools.url_safety import is_safe_url` import
  3. Add SSRF check before each backend call in `web_extract_tool` and `web_crawl_tool`
  4. Copy upstream's `tools/url_safety.py` as-is (new file, no conflict)

---

## 2. Shell Injection Prevention (Commit: 73a88a02)

### Files Affected
| File | Change Type | Conflict Risk |
|------|-------------|---------------|
| `tools/file_operations.py` | Modified | LOW |

### What the Changes Do
Fixes a critical shell injection vulnerability in `ShellFileOperations._expand_path()`:

**Vulnerable code (local):**
```python
expand_result = self._exec(f"echo {path}")
if expand_result.exit_code == 0 and expand_result.stdout.strip():
    return expand_result.stdout.strip()
```

**Fixed code (upstream):**
```python
# Only expand ~username (not the full path) to avoid shell
# injection via path suffixes like "~user/$(malicious)".
expand_result = self._exec(f"echo ~{username}")
if expand_result.exit_code == 0 and expand_result.stdout.strip():
    user_home = expand_result.stdout.strip()
    suffix = path[1 + len(username):]  # e.g. "/rest/of/path"
    return user_home + suffix
```

**Attack vector prevented:** `~user/$(rm -rf /)` or `~user/\`id\`` would execute arbitrary commands.

### Merge Conflicts
- **LOW RISK**: Local line 435 has vulnerable code, upstream changes same location. Clean replacement.

---

## 3. Workspace Path Restriction (Commit: 2d8fad82)

### Files Affected
| File | Change Type | Conflict Risk |
|------|-------------|---------------|
| `agent/context_references.py` | Modified | LOW |
| `tests/test_context_references.py` | Modified | LOW |

### What the Changes Do
Prevents `@file:` and `@folder:` references from accessing sensitive files:

1. **New constants** (added after line 19):
```python
_SENSITIVE_HOME_DIRS = (".ssh", ".aws", ".gnupg", ".kube")
_SENSITIVE_HERMES_DIRS = (Path("skills") / ".hub",)
_SENSITIVE_HOME_FILES = (
    Path(".ssh") / "authorized_keys",
    Path(".ssh") / "id_rsa",
    Path(".ssh") / "id_ed25519",
    Path(".ssh") / "config",
    Path(".bashrc"),
    Path(".zshrc"),
    Path(".profile"),
    Path(".bash_profile"),
    Path(".zprofile"),
    Path(".netrc"),
    Path(".pgpass"),
    Path(".npmrc"),
    Path(".pypirc"),
)
```

2. **Changed default `allowed_root`**: From `None` to `cwd_path` (workspace lockdown)

3. **New function `_ensure_reference_path_allowed()`**: 
   - Blocks exact matches to sensitive files
   - Blocks paths under sensitive directories
   - Raises `ValueError` if path is blocked

4. **Calls added** to `_expand_file_reference()` and `_expand_folder_reference()`

### Merge Conflicts
- **LOW RISK**: Changes are additive (new constants, new function, new function calls). No structural conflicts with local type hints.

---

## Merge Window Recommendations

### Priority Order
1. **P0 - Shell Injection** (file_operations.py) - Critical, trivial merge
2. **P0 - Workspace Path Restriction** (context_references.py) - Critical, easy merge  
3. **P0 - SSRF Protection** (vision_tools.py, url_safety.py) - Critical, easy for vision
4. **P1 - SSRF in web_tools.py** - Complex merge due to structural changes

### Estimated Time
| Task | Time | Complexity |
|------|------|------------|
| Copy `url_safety.py` (new file) | 5 min | Trivial |
| Merge `file_operations.py` | 10 min | Trivial |
| Merge `context_references.py` | 20 min | Easy |
| Merge `vision_tools.py` | 30 min | Easy-Medium |
| Merge `web_tools.py` | 2-3 hours | **Complex** |
| Copy new test files | 15 min | Trivial |
| Merge existing test files | 1 hour | Medium |
| Integration testing | 1-2 hours | Medium |

**Total: 5-7 hours** (within 4-8 hour window)

### Pre-Merge Checklist
- [ ] Fetch upstream: `git fetch origin`
- [ ] Create merge branch: `git checkout -b security-merge`
- [ ] Stage changes in order of complexity (easy first)
- [ ] Run tests after each file merge
- [ ] Focus on `web_tools.py` last with dedicated time block

### New Files to Copy (No Conflicts)
- `tools/url_safety.py` (96 lines)
- `tests/tools/test_url_safety.py` (176 lines)

---

## Test Coverage

Upstream adds 24+ new tests for SSRF protection:
- CGNAT range blocking
- Multicast address blocking
- IPv4-mapped IPv6 handling
- Fail-closed behavior
- Parametrized blocked/allowed IP lists
- Redirect guard validation
