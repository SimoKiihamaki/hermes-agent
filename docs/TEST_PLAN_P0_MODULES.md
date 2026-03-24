# Test Plan for P0 Tools Modules

**Created:** 2024-03-24
**Priority:** P0 - Critical modules requiring test coverage

## Executive Summary

This document outlines a testing strategy for the three P0 priority modules in the `tools/` directory:
- `web_tools.py` (2402 lines) - **NO COVERAGE** ❌
- `tts_tool.py` (846 lines) - **Well-covered** ✅
- `terminal_tool.py` (1362 lines) - **Partially covered** ⚠️

---

## 1. web_tools.py - NO TESTS EXIST (Critical Gap)

### Module Overview
- **Lines:** 2402
- **Purpose:** Web search, extract, crawl with multiple backend providers (Firecrawl, Parallel, Tavily)
- **Features:** SQLite page storage with FTS5, LLM post-processing, website policy checks

### Testable Units (32 functions)

#### A. Page Storage System (HIGH PRIORITY)
These functions have no external dependencies and are ideal for unit testing.

| Function | Purpose | Priority | Complexity |
|----------|---------|----------|------------|
| `_get_db_path()` | Database path resolution | P0 | Low |
| `_hash_url()` | URL hashing | P0 | Low |
| `_init_db()` | Schema initialization, FTS triggers | P0 | Medium |
| `store_page()` | Insert/update page | P0 | Medium |
| `store_pages_from_results()` | Batch storage | P1 | Low |
| `search_pages()` | FTS5 full-text search | P0 | Medium |
| `list_pages()` | Paginated listing | P1 | Low |
| `get_page()` | Retrieve by URL/ID | P1 | Low |
| `delete_page()` | Remove page | P1 | Low |
| `get_storage_stats()` | Database statistics | P2 | Low |

#### B. Page Storage Tools (MEDIUM PRIORITY)
Thin wrappers around storage functions - integration tests.

| Function | Purpose | Priority |
|----------|---------|----------|
| `web_page_search_tool()` | Tool interface for search | P1 |
| `web_page_list_tool()` | Tool interface for list | P1 |
| `web_page_get_tool()` | Tool interface for get | P1 |
| `web_page_delete_tool()` | Tool interface for delete | P2 |
| `web_page_stats_tool()` | Tool interface for stats | P2 |

#### C. Configuration & Backend Selection (HIGH PRIORITY)

| Function | Purpose | Priority | Notes |
|----------|---------|----------|-------|
| `_has_env()` | Environment variable check | P0 | Simple |
| `_load_web_config()` | YAML config loading | P0 | Mock hermes_cli |
| `_get_backend()` | Backend selection logic | P0 | Critical path |

#### D. Backend Clients (MOCK HEAVY)

| Function | Purpose | Priority | Test Strategy |
|----------|---------|----------|---------------|
| `_get_firecrawl_client()` | Firecrawl SDK | P1 | Mock SDK |
| `_get_parallel_client()` | Parallel SDK | P1 | Mock SDK |
| `_get_async_parallel_client()` | Async Parallel | P1 | Mock SDK |
| `_tavily_request()` | Tavily API calls | P1 | Mock requests |

#### E. Search/Extract Normalization (HIGH PRIORITY)

| Function | Purpose | Priority |
|----------|---------|----------|
| `_normalize_tavily_search_results()` | Tavily response format | P0 |
| `_normalize_tavily_documents()` | Tavily document format | P0 |
| `clean_base64_images()` | Remove base64 from text | P0 |

#### F. Main Tools (INTEGRATION TESTS)

| Function | Purpose | Priority |
|----------|---------|----------|
| `web_search_tool()` | Main search tool | P0 |
| `_parallel_search()` | Parallel backend search | P1 |
| `_parallel_extract()` | Parallel async extract | P1 |

#### G. Requirements Checking

| Function | Purpose | Priority |
|----------|---------|----------|
| `check_firecrawl_api_key()` | API key validation | P1 |
| `check_web_api_key()` | Generic API check | P1 |
| `check_auxiliary_model()` | LLM model check | P1 |
| `get_debug_session_info()` | Debug utilities | P2 |

### Recommended Test File: `tests/tools/test_web_tools.py`

```python
"""Tests for tools/web_tools.py — Page storage, search, extract, backend providers.

Coverage priorities:
  P0: Page storage CRUD, FTS5 search, config loading, backend selection
  P1: Tool interfaces, normalization functions, API clients (mocked)
  P2: Stats, debug utilities
"""

# Suggested test classes:

class TestPageStorageDb:
    """Database initialization and connection management."""
    
class TestStorePage:
    """Page storage with upsert logic."""
    
class TestSearchPages:
    """FTS5 full-text search functionality."""
    
class TestHashUrl:
    """URL hashing for quick lookups."""
    
class TestWebConfig:
    """Configuration loading and backend selection."""
    
class TestNormalizeTavily:
    """Tavily response normalization."""
    
class TestCleanBase64Images:
    """Base64 image removal from content."""
    
class TestWebSearchTool:
    """Main search tool with mocked backends."""
```

---

## 2. tts_tool.py - WELL COVERED ✅

### Current Coverage
**Test file:** `tests/tools/test_tts_tool.py` (1296 lines)

### Covered Functions
| Function | Coverage | Test Class |
|----------|----------|------------|
| `_load_tts_config()` | ✅ Complete | `TestLoadTtsConfig` |
| `_get_provider()` | ✅ Complete | `TestGetProvider` |
| `_has_ffmpeg()` | ✅ Complete | `TestHasFfmpeg` |
| `_convert_to_opus()` | ✅ Complete | `TestConvertToOpus` |
| `_strip_markdown_for_tts()` | ✅ Complete | `TestStripMarkdownForTts` |
| `_check_neutts_available()` | ✅ Complete | `TestCheckNeuttsAvailable` |
| `check_tts_requirements()` | ✅ Complete | `TestCheckTtsRequirements` |
| `text_to_speech_tool()` | ✅ Complete | Multiple classes |
| `_generate_elevenlabs()` | ✅ Complete | `TestGenerateElevenlabs` |
| `_generate_openai_tts()` | ✅ Complete | `TestGenerateOpenaiTts` |

### Gaps to Fill
| Function | Status | Priority |
|----------|--------|----------|
| `_generate_edge_tts()` | Not tested | P1 |
| `_generate_neutts()` | Not tested | P1 |
| `stream_tts_to_speaker()` | Not tested | P2 |

### Recommendation
**Status:** Good coverage. Add tests for:
1. `_generate_edge_tts()` async behavior
2. `_generate_neutts()` when neutts available
3. `stream_tts_to_speaker()` audio pipeline

---

## 3. terminal_tool.py - PARTIALLY COVERED ⚠️

### Current Coverage
**Test files:**
- `tests/tools/test_terminal_tool.py` (1183 lines)
- `tests/tools/test_parse_env_var.py` (86 lines)
- `tests/tools/test_terminal_disk_usage.py` (73 lines)
- `tests/tools/test_terminal_tool_requirements.py` (28 lines)

### Covered Functions
| Function | Coverage | Test File |
|----------|----------|-----------|
| `_parse_env_var()` | ✅ Complete | test_parse_env_var.py |
| `_get_env_config()` | ✅ Complete | test_terminal_tool.py |
| `terminal_tool()` | ✅ Complete | test_terminal_tool.py |
| `_check_disk_usage_warning()` | ✅ Complete | test_terminal_disk_usage.py |
| `get_active_environments_info()` | ✅ Complete | test_terminal_disk_usage.py |
| `check_terminal_requirements()` | ✅ Complete | test_terminal_tool_requirements.py |

### Gaps to Fill

| Function | Status | Priority | Notes |
|----------|--------|----------|-------|
| `set_sudo_password_callback()` | Not tested | P2 | Simple setter |
| `set_approval_callback()` | Not tested | P2 | Simple setter |
| `_check_dangerous_command()` | Not tested | P1 | Delegates to approval.py |
| `_check_all_guards()` | Not tested | P1 | Delegates to approval.py |
| `_handle_sudo_failure()` | Not tested | P1 | Gateway context handling |
| `_prompt_for_sudo_password()` | Not tested | P2 | Interactive, hard to test |
| `_transform_sudo_command()` | Not tested | P1 | Sudo password injection |
| `register_task_env_overrides()` | Not tested | P1 | Task config override |
| `clear_task_env_overrides()` | Not tested | P1 | Task config cleanup |
| `_create_environment()` | Partial | P0 | Environment factory |
| `_cleanup_inactive_envs()` | Not tested | P1 | Cleanup logic |
| `_start_cleanup_thread()` | Not tested | P2 | Thread management |
| `_stop_cleanup_thread()` | Not tested | P2 | Thread management |
| `cleanup_all_environments()` | Not tested | P1 | Full cleanup |
| `cleanup_vm()` | Not tested | P1 | Per-task cleanup |
| `_atexit_cleanup()` | Not tested | P2 | Exit handler |

### Recommended Additional Tests

```python
# Add to test_terminal_tool.py or create new files:

class TestSudoHandling:
    """Sudo password and failure handling."""
    
class TestTaskEnvOverrides:
    """Per-task environment configuration overrides."""
    
class TestEnvironmentLifecycle:
    """Environment creation, cleanup, atexit."""
    
class TestCleanupThread:
    """Background cleanup thread management."""
```

---

## Test Implementation Priority

### Phase 1: web_tools.py (Critical - No Tests)
**Estimated effort:** 2-3 days

1. **Day 1:** Page Storage System
   - `test_web_tools_db.py` - Database operations
   - `TestPageStorageDb`, `TestStorePage`, `TestSearchPages`

2. **Day 2:** Configuration & Normalization
   - `test_web_tools_config.py` - Config loading, backend selection
   - `TestWebConfig`, `TestNormalizeTavily`, `TestCleanBase64Images`

3. **Day 3:** Tool Integration Tests
   - `test_web_tools_integration.py` - Main tools with mocked backends
   - `TestWebSearchTool`, `TestWebExtractTool`

### Phase 2: terminal_tool.py Gaps
**Estimated effort:** 1 day

1. **Morning:** Sudo and approval handling
   - `TestSudoHandling`, `TestTransformSudo`

2. **Afternoon:** Environment lifecycle
   - `TestTaskEnvOverrides`, `TestEnvironmentLifecycle`

### Phase 3: tts_tool.py Gaps (Low Priority)
**Estimated effort:** 0.5 days

1. Provider-specific tests for edge_tts and neutts

---

## Testing Patterns & Conventions

Based on existing tests in `tests/tools/`:

### 1. File Structure
```python
"""Tests for tools/{module}.py — Brief description.

Coverage:
  function_name — what is tested
  ...
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import importlib
module = importlib.import_module('tools.module_name')
```

### 2. Fixtures
```python
@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module state before and after each test."""
    # Clear caches, reset globals
    yield
    # Cleanup
```

### 3. Test Class Naming
- `TestFunctionName` for unit tests
- `TestFeatureArea` for related functionality

### 4. Mock External Dependencies
- Mock `hermes_cli.config.load_config` for config tests
- Mock SDK clients (Firecrawl, Parallel, ElevenLabs, etc.)
- Mock file system operations where needed

### 5. JSON Response Testing
```python
result = module.tool_function(...)
assert isinstance(result, str)
parsed = json.loads(result)
assert parsed["success"] is True
```

---

## Files to Create

| File | Priority | Lines Est. |
|------|----------|------------|
| `tests/tools/test_web_tools.py` | P0 | ~800 |
| `tests/tools/test_web_tools_storage.py` | P0 | ~400 |
| Additions to `tests/tools/test_terminal_tool.py` | P1 | ~300 |

---

## Metrics Summary

| Module | Lines | Test Lines | Coverage |
|--------|-------|------------|----------|
| web_tools.py | 2402 | 0 | 0% ❌ |
| tts_tool.py | 846 | 1296 | ~85% ✅ |
| terminal_tool.py | 1362 | 1370 | ~60% ⚠️ |

**Total P0 test debt:** ~1200 lines of tests needed for web_tools.py
