# Security Merge Checklist
**Upstream Security Fixes → Local Branch**
**Estimated Time:** 6-8 hours | **Date:** 2026-03-24
**🔴 UPDATED:** 2026-03-24 18:45 - 20 new upstream commits analyzed

---

## Overview

Merging **6 security-related fixes** from upstream (20 new commits total):
1. **🔴 SUPPLY CHAIN FIX** - Remove litellm/typer/platformdirs (credential stealer in litellm 1.82.7/1.82.8) - `18cbd18f`
2. **🔴 SUPPLY CHAIN HARDENING** - Pin all dependency version ranges - `c9b76057`
3. **🔴 SUPPLY CHAIN CI** - Add PR scanning for supply chain attack patterns - `ac5b8a47`
4. **SSRF Protection** - Blocks private/internal network requests
5. **Shell Injection Prevention** - Fixes `~user/$(malicious)` injection
6. **Workspace Path Restriction** - Prevents `@file:` access to secrets

**Priority:** 🔴 **CRITICAL** - Merge within 24-48 hours (supply chain compromise active)

**Critical Conflict:** `web_tools.py` (local: 2402 lines with page storage vs upstream: 1727 lines with SSRF)

---

## 20 New Upstream Commits (2026-03-24)

| # | Commit | Date | Category | Description | Impact |
|---|--------|------|----------|-------------|--------|
| 1 | `48191558` | 2026-03-24 | fix | Update context pressure warnings/token estimates | Low |
| 2 | `0b993c1e` | 2026-03-24 | docs | Quote pip install extras (zsh fix) | Low |
| 3 | `97183349` | 2026-03-24 | docs | Fix api-server response storage docs | Low |
| 4 | `ebcb81b6` | 2026-03-24 | docs | Document 9 undocumented features | Low |
| 5 | `ac5b8a47` | 2026-03-24 | **🔴 CI/SEC** | **Add supply chain audit workflow for PR scanning** | **HIGH** |
| 6 | `624e4a8e` | 2026-03-24 | chore | Regenerate uv.lock with hashes | Medium |
| 7 | `177e4325` | 2026-03-24 | refactor | Update mini_swe_runner for built-in backends | Low |
| 8 | `c9b76057` | 2026-03-24 | **🔴 SEC** | **Pin all dependency version ranges** | **HIGH** |
| 9 | `745859ba` | 2026-03-24 | feat | Env var passthrough for skills/user config | Medium |
| 10 | `ad1bf16f` | 2026-03-24 | chore | Remove remaining mini-swe-agent references | Low |
| 11 | `e2c81c6e` | 2026-03-24 | docs | Add missing skills/CLI/messaging docs | Low |
| 12 | `677b11d8` | 2026-03-24 | **fix/sec** | Reject relative cwd paths for containers | Medium |
| 13 | `ee3f3e75` | 2026-03-24 | docs | Fix stale/incorrect docs (18 files) | Low |
| 14 | `02b38b93` | 2026-03-24 | refactor | Remove mini-swe-agent dependency | Low |
| 15 | `2233f764` | 2026-03-24 | fix | Handle 402 insufficient credits error | Low |
| 16 | `98b55709` | 2026-03-24 | fix | Make browser command timeout configurable | Low |
| 17 | `773d3bb4` | 2026-03-24 | docs | Update docs for /model command overhaul | Low |
| 18 | `a312ee7b` | 2026-03-24 | fix | Ensure first delta fired during reasoning | Low |
| 19 | `2e524272` | 2026-03-24 | refactor | Extract shared switch_model() | Low |
| 20 | `ce39f9cc` | 2026-03-24 | fix | Detect virtualenv path dynamically | Low |

**Plus earlier security commit:** `18cbd18f` - Remove compromised litellm/typer/platformdirs deps

---

## Security Commits - Detailed Breakdown

### 🔴 1. `18cbd18f` - Remove Compromised Dependencies (CRITICAL)

**Date:** 2026-03-24 07:03 | **Author:** Teknium

**Summary:** Removes litellm, typer, platformdirs from hermes-agent deps due to supply chain compromise.

**Threat Details:**
- litellm 1.82.7/1.82.8 contained credential stealer via `.pth` auto-exec payload
- PyPI quarantined entire package, blocking fresh hermes-agent installs
- Reference: https://github.com/BerriAI/litellm/issues/24512

**Files Changed:**
| File | Changes |
|------|---------|
| `pyproject.toml` | -4 lines (removed deps) |
| `scripts/install.sh` | +5/-2 lines (fixed failure messages) |
| `setup-hermes.sh` | +1/-1 lines (warning update) |

**Action Required:** `git checkout origin/main -- pyproject.toml`

---

### 🔴 2. `c9b76057` - Pin All Dependency Versions (HIGH)

**Date:** 2026-03-24 08:25 | **Author:** Teknium

**Summary:** Adds upper-bound version pins (`<next_major`) to all dependencies in pyproject.toml.

**Why Critical:**
- Previously most deps were unpinned or had only floor bounds
- Fresh installs would pull latest PyPI version (supply chain risk)
- Limits blast radius from attacks like litellm credential stealer
- Floors set to current known-good installed versions

**Files Changed:**
| File | Changes |
|------|---------|
| `pyproject.toml` | +39/-39 lines (version pins) |

**Example Change:**
```toml
# Before: requests>=2.28.0
# After:  requests>=2.28.0,<3.0.0
```

**Action Required:** Already included in pyproject.toml checkout from #1

---

### 🔴 3. `ac5b8a47` - Add Supply Chain Audit Workflow (HIGH)

**Date:** 2026-03-24 08:56 | **Author:** Teknium

**Summary:** Adds GitHub Actions workflow for PR scanning to detect supply chain attack patterns.

**Detection Rules:**

| Severity | Pattern | Action |
|----------|---------|--------|
| 🔴 CRITICAL | `.pth` files | **Blocks merge** |
| 🔴 CRITICAL | base64 decode + exec/eval combo | **Blocks merge** |
| 🔴 CRITICAL | subprocess with encoded commands | **Blocks merge** |
| ⚠️ WARNING | base64 encode/decode alone | Comment only |
| ⚠️ WARNING | exec/eval alone | Comment only |
| ⚠️ WARNING | Outbound POST/PUT requests | Comment only |
| ⚠️ WARNING | setup.py/sitecustomize.py changes | Comment only |
| ⚠️ WARNING | marshal.loads/pickle.loads/compile() | Comment only |

**Files Changed:**
| File | Changes |
|------|---------|
| `.github/workflows/supply-chain-audit.yml` | +192 lines (NEW) |

**Action Required:** `git checkout origin/main -- .github/workflows/supply-chain-audit.yml`

---

## Additional Security-Related Commit

### `677b11d8` - Reject Relative CWD Paths (Medium)

**Summary:** Rejects relative cwd paths for container terminal backends to prevent path traversal.

**Action Required:** Low priority - review if using container backends

---

## 1. Pre-Merge Backup

```bash
# Navigate to project
cd ~/Projects/hermes-agent

# Verify clean working directory
git status

# If uncommitted changes exist, stash them
git stash push -m "Pre-security-merge stash"

# Create backup branch from current state
git branch backup-pre-security-merge

# Create working merge branch
git checkout -b security-merge

# Fetch latest upstream
git fetch origin

# Verify upstream branches
git branch -r | grep origin
```

---

## 2. Merge Order (Easy → Complex)

### 🔴 Phase 0: Supply Chain Fix (CRITICAL - DO FIRST) ~15 min

```bash
# Check if we're using affected versions
grep -E "litellm|typer|platformdirs" requirements.txt pyproject.toml setup.py 2>/dev/null

# Checkout the dependency fix from upstream
git checkout origin/main -- pyproject.toml
git checkout origin/main -- requirements.txt  # if exists

# If requirements.txt is local-only, manually remove:
# - litellm>=1.82.0 → REMOVE (credential stealer in 1.82.7/1.82.8)
# - typer → REMOVE
# - platformdirs → REMOVE

# Verify removal
grep -E "litellm|typer|platformdirs" pyproject.toml requirements.txt 2>/dev/null
# Should return nothing

# Reinstall clean dependencies
pip install -e . --force-reinstall
```

**Why this is critical:**
- litellm 1.82.7/1.82.8 contained `.pth` auto-exec credential stealer
- Commits: `18cbd18f` removes compromised dependencies
- If you've run pip install recently, check ~/.bash_history for suspicious activity

---

### Phase 1: New Files (No Conflicts) ~5 min

```bash
# Copy new SSRF protection module
git checkout origin/main -- tools/url_safety.py

# Copy new SSRF tests
git checkout origin/main -- tests/tools/test_url_safety.py

# Verify files exist
ls -la tools/url_safety.py tests/tools/test_url_safety.py
```

---

### Phase 2: Shell Injection Fix (file_operations.py) ~10 min

```bash
# Merge file_operations.py
git checkout origin/main -- tools/file_operations.py

# The fix is in _expand_path() around line 435
# Verify the change:
grep -A5 "echo ~" tools/file_operations.py
```

**What changed:**
- Old: `echo {path}` (vulnerable to `~user/$(cmd)`)
- New: `echo ~{username}` then concatenate suffix (safe)

---

### Phase 3: Workspace Path Restriction (context_references.py) ~20 min

```bash
# Attempt merge
git merge origin/main --no-commit -- tools/agent/context_references.py

# If conflicts, resolve manually:
# - Keep local type hints
# - Add upstream's _SENSITIVE_* constants after line 19
# - Add upstream's _ensure_reference_path_allowed() function
# - Add function calls in _expand_file_reference() and _expand_folder_reference()
```

**Key additions to preserve:**
```python
_SENSITIVE_HOME_DIRS = (".ssh", ".aws", ".gnupg", ".kube")
_SENSITIVE_HOMES_FILES = (Path(".ssh") / "authorized_keys", ...)
```

---

### Phase 4: Vision Tools SSRF (vision_tools.py) ~30 min

```bash
# Merge vision_tools.py
git merge origin/main --no-commit -- tools/vision_tools.py

# Key changes to verify:
# 1. Import: from tools.url_safety import is_safe_url
# 2. _validate_image_url() calls is_safe_url()
# 3. _ssrf_redirect_guard() async hook exists
# 4. Configurable vision timeout
```

---

### Phase 5: Web Tools SSRF (CRITICAL CONFLICT) ~2-3 hours

```bash
# DO NOT blindly checkout - will lose page storage system!
# Instead, manually merge:

# Open both versions for comparison
git show origin/main:tools/web_tools.py > /tmp/upstream_web_tools.py
git show HEAD:tools/web_tools.py > /tmp/local_web_tools.py

# Use diff tool
diff -u /tmp/upstream_web_tools.py /tmp/local_web_tools.py
# Or use: code --diff /tmp/upstream_web_tools.py /tmp/local_web_tools.py
```

#### Conflict Resolution Strategy for web_tools.py

**KEEP (Local):**
- All page storage infrastructure (SQLite, FTS5)
- `PageStorage` class
- `stored_pages` dictionary
- Page retrieval functions

**ADD (Upstream):**
```python
# Add import at top
from tools.url_safety import is_safe_url
```

**ADD SSRF check in web_extract_tool() before backend dispatch:**
```python
# Before calling Parallel, Tavily, or Firecrawl backends
if not is_safe_url(url):
    return f"Error: Access to internal/private URLs is blocked for security"
```

**ADD SSRF check in web_crawl_tool() similarly**

**Manual merge steps:**
1. Keep entire local file as base
2. Add `from tools.url_safety import is_safe_url` import
3. Find where `website_policy.check()` is called
4. Add `is_safe_url(url)` check BEFORE policy check
5. Return error message if SSRF check fails

---

### Phase 6: Test File Merges ~1 hour

```bash
# Merge test files (lower conflict risk)
git merge origin/main --no-commit -- tests/tools/test_vision_tools.py
git merge origin/main --no-commit -- tests/tools/test_website_policy.py
git merge origin/main --no-commit -- tests/test_context_references.py

# Resolve any conflicts, preferring upstream test logic
```

---

## 3. Post-Merge Verification

```bash
# Stage all changes
git add -A

# Run linting
ruff check tools/ tests/

# Run type checking (if configured)
mypy tools/

# Run SSRF-specific tests
pytest tests/tools/test_url_safety.py -v

# Run vision tests
pytest tests/tools/test_vision_tools.py -v

# Run context reference tests  
pytest tests/test_context_references.py -v

# Run full test suite
pytest tests/ -v --tb=short

# Manual verification - SSRF should block:
python -c "from tools.url_safety import is_safe_url; print(is_safe_url('http://127.0.0.1/admin'))"
# Expected: False

python -c "from tools.url_safety import is_safe_url; print(is_safe_url('http://metadata.google.internal'))"
# Expected: False
```

---

## 4. Commit & Push

```bash
# Review staged changes
git diff --cached --stat

# Commit
git commit -m "Merge upstream security fixes: SSRF, shell injection, path restriction"

# Push to remote (review first)
git push origin security-merge

# After review/approval, merge to main:
git checkout main
git merge security-merge
git push origin main
```

---

## 5. Rollback Procedure

### If merge goes wrong before commit:

```bash
# Abort merge
git merge --abort

# Or reset to last commit
git reset --hard HEAD
```

### If committed but need to undo:

```bash
# Undo last commit, keep changes staged
git reset --soft HEAD~1

# Undo last commit, discard changes
git reset --hard HEAD~1
```

### Complete rollback to backup:

```bash
# Return to main
git checkout main

# Delete failed merge branch
git branch -D security-merge

# Restore from backup
git checkout backup-pre-security-merge
git checkout -b security-merge-retry

# Or hard reset main to backup
git checkout main
git reset --hard backup-pre-security-merge
```

### Recover stashed changes:

```bash
# List stashes
git stash list

# Apply stash
git stash pop
```

---

## Quick Reference: File Status

| File | Action | Risk |
|------|--------|------|
| `tools/url_safety.py` | Copy from upstream | ✅ None |
| `tests/tools/test_url_safety.py` | Copy from upstream | ✅ None |
| `tools/file_operations.py` | Replace from upstream | ✅ Low |
| `tools/agent/context_references.py` | Merge | ⚠️ Low |
| `tools/vision_tools.py` | Merge | ⚠️ Medium |
| `tools/web_tools.py` | **Manual merge** | 🔴 **HIGH** |
| Test files | Merge | ⚠️ Medium |

---

## Time Estimates (Updated for 20 New Commits)

| Phase | Time | Status | Notes |
|-------|------|--------|-------|
| Backup & Setup | 10 min | ⬜ | |
| 🔴 **Phase 0: Supply Chain Fixes** | **20 min** | ⬜ | NEW: pyproject.toml + audit workflow |
| Phase 1: New Files | 5 min | ⬜ | |
| Phase 2: file_operations.py | 10 min | ⬜ | |
| Phase 3: context_references.py | 20 min | ⬜ | |
| Phase 4: vision_tools.py | 30 min | ⬜ | |
| Phase 5: web_tools.py | 2-3 hrs | ⬜ | Critical conflict |
| Phase 6: Test files | 1 hr | ⬜ | |
| Phase 7: Review other 20 commits | **30 min** | ⬜ | NEW: docs/refactors/chore |
| Verification | 1-2 hrs | ⬜ | |
| **TOTAL** | **6-8 hrs** | | |

**Time Increase:** +1-2 hours due to:
- Additional supply chain audit workflow to merge
- Review of 20 new commits for compatibility
- Extra verification of dependency version pins

---

## Pre-Flight Checks

- [ ] Working directory is clean (`git status`)
- [ ] Backup branch created (`backup-pre-security-merge`)
- [ ] On merge branch (`security-merge`)
- [ ] Upstream fetched (`git fetch origin`)
- [ ] Blocked 5-7 hours of uninterrupted time
- [ ] IDE/editor ready for manual web_tools.py merge
