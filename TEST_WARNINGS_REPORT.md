# Hermes Agent Test Warnings Analysis & Fix Recommendations

**Analysis Date:** 2026-03-25  
**Total Warnings:** 237 warnings across 6396 tests

## Executive Summary

The test suite has warnings in three main categories:

| Priority | Category | Count | Impact |
|----------|----------|-------|--------|
| 🔴 High | `PytestUnhandledThreadExceptionWarning` | 4 | Unhandled exceptions in background threads |
| 🔴 High | `ResourceWarning` (unclosed resources) | ~200+ | Memory/file descriptor leaks |
| 🟡 Medium | `DeprecationWarning` | 2 | Python 3.14 compatibility issues |
| 🟢 Low | `RuntimeWarning` (unawaited coroutines) | ~20 | Test mock issues |

---

## 1. 🔴 HIGH PRIORITY: PytestUnhandledThreadExceptionWarning

**Count:** 4 warnings  
**Location:** `tests/gateway/test_slack.py` (10 related warnings)  
**Thread:** `_rpc_server_loop` in `tools/code_execution_tool.py`

### Root Cause
The `_rpc_server_loop` thread throws unhandled exceptions when tests terminate before the RPC thread completes.

### Fix Recommendation

**File:** `tools/code_execution_tool.py` (lines 224-300)

```python
# BEFORE (current code):
def _rpc_server_loop(
    server_sock: socket.socket,
    task_id: str,
    tool_call_log: list,
    tool_call_counter: list,
    max_tool_calls: int,
    allowed_tools: frozenset,
) -> None:
    from model_tools import handle_function_call
    conn = None
    try:
        server_sock.settimeout(5)
        conn, _ = server_sock.accept()
        # ...
    except Exception:
        pass  # Swallows exceptions silently

# AFTER (recommended fix):
def _rpc_server_loop(
    server_sock: socket.socket,
    task_id: str,
    tool_call_log: list,
    tool_call_counter: list,
    max_tool_calls: int,
    allowed_tools: frozenset,
    shutdown_event: threading.Event = None,  # NEW: Add shutdown signaling
) -> None:
    from model_tools import handle_function_call
    conn = None
    try:
        server_sock.settimeout(5)
        conn, _ = server_sock.accept()
        # ...
    except socket.timeout:
        logger.debug("RPC server timed out waiting for connection")
    except OSError as e:
        if shutdown_event and shutdown_event.is_set():
            logger.debug("RPC server shutdown requested")
        else:
            logger.warning("RPC server socket error: %s", e)
    except Exception as e:
        logger.exception("Unhandled exception in RPC server loop: %s", e)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
```

**Test Fix:** Add proper cleanup in tests

```python
# In tests/tools/test_code_execution_tool.py
class TestRpcServerLoop:
    def setup_method(self):
        self.shutdown_event = threading.Event()
        
    def teardown_method(self):
        self.shutdown_event.set()  # Signal thread to stop
        # Wait for thread to finish
        time.sleep(0.5)
```

---

## 2. 🔴 HIGH PRIORITY: ResourceWarning - Unclosed Database Connections

**Count:** ~150+ warnings  
**Location:** `hermes_state.py` - `SessionDB` class

### Root Cause
The `SessionDB` class in `hermes_state.py` creates SQLite connections but lacks a `close()` method or context manager protocol. Tests create instances that are garbage collected without closing connections.

### Fix Recommendation

**File:** `hermes_state.py` (add after `__init__` method, around line 130)

```python
# BEFORE (current code):
class SessionDB:
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=10.0,
        )
        # ... schema init ...

# AFTER (recommended fix):
class SessionDB:
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=10.0,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()
        self._closed = False

    def close(self) -> None:
        """Close the database connection. Safe to call multiple times."""
        if self._closed:
            return
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
            self._closed = True

    def __enter__(self) -> "SessionDB":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensure connection is closed."""
        self.close()

    def __del__(self) -> None:
        """Destructor - warn if not properly closed."""
        if not self._closed:
            import warnings
            warnings.warn(
                f"SessionDB for {self.db_path} was not explicitly closed. "
                "Use 'with SessionDB() as db:' or call db.close() explicitly.",
                ResourceWarning,
                stacklevel=2
            )
            self.close()
```

**Test Fix Pattern:**

```python
# In tests, use context manager or explicit close:
def test_something():
    with SessionDB(db_path=test_db_path) as db:
        # ... test code ...
    # Connection automatically closed

# OR

def test_something():
    db = SessionDB(db_path=test_db_path)
    try:
        # ... test code ...
    finally:
        db.close()
```

---

## 3. 🔴 HIGH PRIORITY: ResourceWarning - Unclosed Files in persistent_shell.py

**Count:** 14 warnings  
**Location:** `tools/environments/persistent_shell.py` line 123

### Root Cause
The persistent shell's cleanup method doesn't properly close pipe file handles before setting `_shell_proc = None`.

### Fix Recommendation

**File:** `tools/environments/persistent_shell.py` (lines 110-127)

```python
# BEFORE (current code):
def _cleanup_shell(self):
    if not self._shell_alive:
        return
    try:
        self._shell_proc.stdin.write(b"exit 0\n")
        self._shell_proc.stdin.flush()
    except Exception:
        pass
    try:
        self._shell_proc.terminate()
        self._shell_proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        self._shell_proc.kill()

    self._shell_alive = False
    self._shell_proc = None  # <-- Files not closed!

# AFTER (recommended fix):
def _cleanup_shell(self):
    if not self._shell_alive:
        return
    
    # Close stdin pipe first
    if self._shell_proc and self._shell_proc.stdin:
        try:
            self._shell_proc.stdin.write(b"exit 0\n")
            self._shell_proc.stdin.flush()
        except (OSError, BrokenPipeError):
            pass
        finally:
            try:
                self._shell_proc.stdin.close()
            except Exception:
                pass
    
    # Close stdout/stderr pipes if accessible
    for pipe in (self._shell_proc.stdout, self._shell_proc.stderr):
        if pipe:
            try:
                pipe.close()
            except Exception:
                pass

    # Terminate process
    try:
        self._shell_proc.terminate()
        self._shell_proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        self._shell_proc.kill()
    except Exception:
        pass

    self._shell_alive = False
    self._shell_proc = None
```

---

## 4. 🔴 HIGH PRIORITY: ResourceWarning - Unclosed Files in test_timezone.py

**Count:** 6 warnings  
**Location:** `tests/test_timezone.py` lines 160, 174, 188

### Root Cause
The `_execute_code` method in tests creates subprocess with pipes that aren't fully drained/closed.

### Fix Recommendation

**File:** `tests/test_timezone.py` - Add cleanup helper

```python
class TestCodeExecutionTZ:
    def setup_method(self):
        self._processes_to_cleanup = []
        
    def teardown_method(self):
        for proc in self._processes_to_cleanup:
            try:
                if proc.stdout:
                    proc.stdout.close()
                if proc.stderr:
                    proc.stderr.close()
                if proc.stdin:
                    proc.stdin.close()
                proc.wait(timeout=1)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _execute_code_with_cleanup(self, *args, **kwargs):
        result = self._execute_code(*args, **kwargs)
        # Track any subprocess for cleanup
        # (depends on how _execute_code is implemented)
        return result
```

---

## 5. 🟡 MEDIUM PRIORITY: DeprecationWarning - tar.extract() without filter

**Count:** 1 warning  
**Location:** `tools/tirith_security.py` line 359

### Root Cause
Python 3.14 will require the `filter` argument for `tar.extract()` to prevent path traversal attacks. The code already validates paths manually, but needs to add the filter parameter.

### Fix Recommendation

**File:** `tools/tirith_security.py` (lines 352-360)

```python
# BEFORE (current code):
with tarfile.open(archive_path, "r:gz") as tar:
    for member in tar.getmembers():
        if member.name == "tirith" or member.name.endswith("/tirith"):
            if ".." in member.name:
                continue
            member.name = "tirith"
            tar.extract(member, tmpdir)
            break

# AFTER (recommended fix):
import sys

def _tar_filter(member, path):  # Custom filter function
    """Custom tar extraction filter for tirith binary."""
    # Reject any path with .. components (defense in depth)
    if ".." in member.name:
        return None
    # Only extract the tirith binary
    if member.name == "tirith" or member.name.endswith("/tirith"):
        member.name = "tirith"  # Flatten to just "tirith"
        return member
    return None  # Skip everything else

with tarfile.open(archive_path, "r:gz") as tar:
    for member in tar.getmembers():
        if member.name == "tirith" or member.name.endswith("/tirith"):
            if ".." in member.name:
                continue
            member.name = "tirith"
            # Python 3.12+ supports filter argument
            if sys.version_info >= (3, 12):
                tar.extract(member, tmpdir, filter='data')
            else:
                tar.extract(member, tmpdir)
            break
```

**Alternative (cleaner) approach:**

```python
with tarfile.open(archive_path, "r:gz") as tar:
    # Use tar.extractall with filter for Python 3.12+
    for member in tar.getmembers():
        if member.name == "tirith" or member.name.endswith("/tirith"):
            if ".." in member.name:
                continue
            member.name = "tirith"
            # Python 3.12+ deprecation fix
            try:
                tar.extract(member, tmpdir, filter='data')
            except TypeError:
                # Python < 3.12 doesn't support filter argument
                tar.extract(member, tmpdir)
            break
```

---

## 6. 🟡 MEDIUM PRIORITY: DeprecationWarning - httpx verify parameter

**Count:** 1 warning  
**Location:** `venv/lib/.../httpx/_config.py:51` (transitive dependency)

### Root Cause
The warning originates from httpx library when `verify=<string_path>` is used instead of `verify=ssl.create_default_context()`.

### Fix Recommendation

Search for httpx usage with string paths for SSL verification:

```bash
# Run this to find the source:
grep -rn "verify\s*=\s*['\"].*\.pem" --include="*.py" .
grep -rn "verify\s*=\s*['\"].*\.crt" --include="*.py" .
```

**Example fix pattern:**

```python
# BEFORE (deprecated):
import httpx
client = httpx.Client(verify="/path/to/ca-bundle.pem")

# AFTER (correct):
import ssl
import httpx

ctx = ssl.create_default_context(cafile="/path/to/ca-bundle.pem")
client = httpx.Client(verify=ctx)
```

**Note:** This warning appears to come from a transitive dependency. If direct code isn't found, the fix may need to be in a dependency or configuration file.

---

## 7. 🟢 LOW PRIORITY: RuntimeWarning - Unawaited Coroutines

**Count:** ~20 warnings  
**Location:** Various test files using mocks

### Root Cause
Tests use `AsyncMock` but don't properly await mocked async methods, or mock async methods with sync mocks.

### Fix Recommendation

**File:** `tests/gateway/test_slack.py` (example)

```python
# BEFORE (problematic):
mock_resolve = Mock(return_value="test_user")

# AFTER (correct):
from unittest.mock import AsyncMock

mock_resolve = AsyncMock(return_value="test_user")

# Ensure async methods are properly awaited in tests:
async def test_something():
    user_name = await self._resolve_user_name(user_id)  # Properly awaited
```

**General pattern for async mock fixes:**

```python
# In conftest.py or test file:
from unittest.mock import AsyncMock

# For async methods, use AsyncMock:
some_async_method = AsyncMock(return_value=expected_value)

# Or use autospec:
from unittest.mock import create_autospec

mock_obj = create_autospec(MyAsyncClass, spec_set=True)
```

---

## 8. 🔴 HIGH PRIORITY: ResourceWarning - Unclosed Event Loops & Sockets

**Count:** ~30 warnings  
**Location:** Various async test files

### Root Cause
Async tests create event loops and sockets that aren't properly closed.

### Fix Recommendation

**In `conftest.py`:**

```python
import asyncio
import pytest

@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.new_event_loop()
    yield loop
    # Proper cleanup
    loop.run_until_complete(loop.shutdown_asyncgens())
    loop.run_until_complete(loop.shutdown_default_executor())
    loop.close()

@pytest.fixture
async def async_client():
    """Example async client fixture with proper cleanup."""
    client = await create_client()
    yield client
    await client.aclose()  # Ensure async cleanup
```

---

## Summary: Implementation Priority

### Phase 1 (Immediate - Prevent Resource Leaks)
1. Add `close()`, `__enter__`, `__exit__` to `SessionDB` class
2. Fix pipe closure in `persistent_shell.py` `_cleanup_shell()`
3. Add shutdown signaling to `_rpc_server_loop` thread

### Phase 2 (Before Python 3.14)
4. Add `filter` parameter to `tar.extract()` calls
5. Fix httpx `verify` parameter usage (if found in project code)

### Phase 3 (Test Quality)
6. Update async mocks to use `AsyncMock`
7. Add proper event loop fixtures in `conftest.py`
8. Add subprocess cleanup helpers in test classes

---

## Testing the Fixes

After implementing fixes, verify with:

```bash
# Run with all warnings visible
python -m pytest tests/ -W default -W error::ResourceWarning -W error::DeprecationWarning 2>&1 | head -200

# Run with resource tracking
python -W error::ResourceWarning -m pytest tests/ -q

# Run specific warning categories
python -m pytest tests/ -W error::pytest.PytestUnhandledThreadExceptionWarning
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `hermes_state.py` | Add `close()`, `__enter__`, `__exit__`, `__del__` |
| `tools/environments/persistent_shell.py` | Close pipes in `_cleanup_shell()` |
| `tools/code_execution_tool.py` | Add shutdown signaling to `_rpc_server_loop` |
| `tools/tirith_security.py` | Add `filter='data'` to `tar.extract()` |
| `tests/test_timezone.py` | Add subprocess cleanup |
| `tests/conftest.py` | Add event loop fixture with cleanup |
| `tests/gateway/test_slack.py` | Use `AsyncMock` for async methods |
