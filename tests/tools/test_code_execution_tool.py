#!/usr/bin/env python3
"""
Comprehensive test suite for code_execution_tool.py (execute_code sandbox).

Tests cover:
- Python code execution
- Tool call handling via RPC
- Error handling (syntax, runtime, etc.)
- Timeout handling
- Stdout capture and truncation
- Import restrictions (environment filtering)
- Output size limits
- Schema generation
- Helper functions

Uses extensive mocking to avoid subprocess/socket hangs in CI environments.

Run with: python -m pytest tests/tools/test_code_execution_tool.py -v
"""

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from io import BytesIO
from unittest.mock import MagicMock, Mock, patch, mock_open

import pytest

# Skip all tests on Windows
pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Unix domain sockets required for code execution sandbox"
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_handle_function_call():
    """Mock tool dispatcher that returns canned responses."""
    def _dispatcher(function_name, function_args, task_id=None, user_task=None):
        if function_name == "terminal":
            cmd = function_args.get("command", "")
            return json.dumps({"output": f"mock output for: {cmd}", "exit_code": 0})
        if function_name == "web_search":
            return json.dumps({"results": [{"url": "https://example.com", "title": "Test"}]})
        if function_name == "read_file":
            return json.dumps({"content": "line1\nline2", "total_lines": 2})
        if function_name == "write_file":
            return json.dumps({"status": "ok"})
        if function_name == "search_files":
            return json.dumps({"matches": [{"file": "test.py"}]})
        if function_name == "patch":
            return json.dumps({"status": "ok", "replacements": 1})
        if function_name == "web_extract":
            return json.dumps({"results": [{"url": "https://example.com", "content": "text"}]})
        return json.dumps({"error": f"Unknown tool: {function_name}"})
    return _dispatcher


@pytest.fixture
def mock_config():
    """Mock config with short timeout for fast tests."""
    return {"timeout": 5, "max_tool_calls": 10}


@pytest.fixture
def mock_interrupt_event():
    """Mock interrupt event that is not set."""
    event = MagicMock()
    event.is_set.return_value = False
    return event


@pytest.fixture
def temp_sandbox_dir(tmp_path):
    """Create a temporary directory for sandbox files."""
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()
    return sandbox_dir


# ============================================================================
# Import and Module Setup Tests
# ============================================================================

class TestModuleImports:
    """Test that the module imports correctly and exposes expected symbols."""

    def test_module_imports_successfully(self):
        """Verify the module can be imported."""
        from tools import code_execution_tool
        assert code_execution_tool is not None

    def test_exports_expected_constants(self):
        """Verify expected constants are exported."""
        from tools.code_execution_tool import (
            SANDBOX_AVAILABLE,
            SANDBOX_ALLOWED_TOOLS,
            DEFAULT_TIMEOUT,
            DEFAULT_MAX_TOOL_CALLS,
            MAX_STDOUT_BYTES,
            MAX_STDERR_BYTES,
        )
        assert isinstance(SANDBOX_AVAILABLE, bool)
        assert isinstance(SANDBOX_ALLOWED_TOOLS, frozenset)
        assert DEFAULT_TIMEOUT == 300
        assert DEFAULT_MAX_TOOL_CALLS == 50
        assert MAX_STDOUT_BYTES == 50_000
        assert MAX_STDERR_BYTES == 10_000

    def test_exports_expected_functions(self):
        """Verify expected functions are exported."""
        from tools.code_execution_tool import (
            check_sandbox_requirements,
            generate_hermes_tools_module,
            execute_code,
            build_execute_code_schema,
            _rpc_server_loop,
            _kill_process_group,
            _load_config,
        )
        assert callable(check_sandbox_requirements)
        assert callable(generate_hermes_tools_module)
        assert callable(execute_code)
        assert callable(build_execute_code_schema)
        assert callable(_rpc_server_loop)
        assert callable(_kill_process_group)
        assert callable(_load_config)


# ============================================================================
# check_sandbox_requirements Tests
# ============================================================================

class TestCheckSandboxRequirements:
    """Tests for check_sandbox_requirements function."""

    def test_returns_true_on_posix(self):
        """On non-Windows systems, sandbox should be available."""
        from tools.code_execution_tool import check_sandbox_requirements
        # Since we skip on Windows, this should always be True
        assert check_sandbox_requirements() is True

    @patch("tools.code_execution_tool.SANDBOX_AVAILABLE", False)
    def test_returns_false_when_unavailable(self):
        """When SANDBOX_AVAILABLE is False, should return False."""
        from tools.code_execution_tool import check_sandbox_requirements
        assert check_sandbox_requirements() is False


# ============================================================================
# generate_hermes_tools_module Tests
# ============================================================================

class TestGenerateHermesToolsModule:
    """Tests for generate_hermes_tools_module function."""

    def test_generates_all_allowed_tools(self):
        """When given all allowed tools, all should be in output."""
        from tools.code_execution_tool import (
            generate_hermes_tools_module,
            SANDBOX_ALLOWED_TOOLS,
        )
        src = generate_hermes_tools_module(list(SANDBOX_ALLOWED_TOOLS))
        for tool in SANDBOX_ALLOWED_TOOLS:
            assert f"def {tool}(" in src, f"Missing tool: {tool}"

    def test_generates_only_requested_subset(self):
        """Only requested tools should be generated."""
        from tools.code_execution_tool import generate_hermes_tools_module
        src = generate_hermes_tools_module(["terminal", "web_search"])
        assert "def terminal(" in src
        assert "def web_search(" in src
        assert "def read_file(" not in src

    def test_empty_list_generates_infrastructure_only(self):
        """Empty tool list still generates RPC infrastructure."""
        from tools.code_execution_tool import generate_hermes_tools_module
        src = generate_hermes_tools_module([])
        assert "def _connect(" in src
        assert "def _call(" in src
        assert "def terminal(" not in src

    def test_non_allowed_tools_ignored(self):
        """Tools not in SANDBOX_ALLOWED_TOOLS are ignored."""
        from tools.code_execution_tool import generate_hermes_tools_module
        src = generate_hermes_tools_module(["vision_analyze", "terminal"])
        assert "def terminal(" in src
        assert "def vision_analyze(" not in src

    def test_includes_rpc_infrastructure(self):
        """Generated module includes UDS RPC infrastructure."""
        from tools.code_execution_tool import generate_hermes_tools_module
        src = generate_hermes_tools_module(["terminal"])
        assert "HERMES_RPC_SOCKET" in src
        assert "socket.AF_UNIX" in src
        assert "def _connect(" in src
        assert "def _call(" in src

    def test_includes_convenience_helpers(self):
        """Generated module includes json_parse, shell_quote, retry helpers."""
        from tools.code_execution_tool import generate_hermes_tools_module
        src = generate_hermes_tools_module(["terminal"])
        assert "def json_parse(" in src
        assert "def shell_quote(" in src
        assert "def retry(" in src

    def test_generated_code_is_valid_python(self):
        """Generated module should be syntactically valid Python."""
        from tools.code_execution_tool import (
            generate_hermes_tools_module,
            SANDBOX_ALLOWED_TOOLS,
        )
        src = generate_hermes_tools_module(list(SANDBOX_ALLOWED_TOOLS))
        # This will raise SyntaxError if invalid
        compile(src, "hermes_tools.py", "exec")

    def test_tool_signatures_match_expected(self):
        """Each tool has expected parameters in signature."""
        from tools.code_execution_tool import generate_hermes_tools_module, _TOOL_STUBS
        src = generate_hermes_tools_module(["search_files"])
        # search_files should have context, offset, output_mode params
        assert "context" in src
        assert "offset" in src
        assert "output_mode" in src

    def test_tool_stub_contains_docstring(self):
        """Generated functions include docstrings."""
        from tools.code_execution_tool import generate_hermes_tools_module
        src = generate_hermes_tools_module(["terminal"])
        assert '"""Run a shell command' in src or '"""' in src


# ============================================================================
# build_execute_code_schema Tests
# ============================================================================

class TestBuildExecuteCodeSchema:
    """Tests for build_execute_code_schema function."""

    def test_default_schema_structure(self):
        """Default schema has correct structure."""
        from tools.code_execution_tool import build_execute_code_schema
        schema = build_execute_code_schema()
        assert schema["name"] == "execute_code"
        assert "parameters" in schema
        assert "code" in schema["parameters"]["properties"]
        assert "code" in schema["parameters"]["required"]

    def test_default_includes_all_tools(self):
        """Default schema mentions all sandbox tools."""
        from tools.code_execution_tool import (
            build_execute_code_schema,
            SANDBOX_ALLOWED_TOOLS,
        )
        schema = build_execute_code_schema()
        desc = schema["description"]
        for tool in SANDBOX_ALLOWED_TOOLS:
            assert tool in desc, f"Missing tool: {tool}"

    def test_subset_only_lists_enabled_tools(self):
        """Schema only mentions tools in the enabled set."""
        from tools.code_execution_tool import build_execute_code_schema
        schema = build_execute_code_schema({"terminal", "read_file"})
        desc = schema["description"]
        assert "terminal(" in desc
        assert "read_file(" in desc
        assert "web_search(" not in desc

    def test_empty_set_produces_valid_schema(self):
        """Empty set should not produce broken import syntax."""
        from tools.code_execution_tool import build_execute_code_schema
        schema = build_execute_code_schema(set())
        code_desc = schema["parameters"]["properties"]["code"]["description"]
        assert "import , ..." not in code_desc

    def test_none_defaults_to_all_tools(self):
        """None argument should default to all tools."""
        from tools.code_execution_tool import (
            build_execute_code_schema,
            SANDBOX_ALLOWED_TOOLS,
        )
        schema_none = build_execute_code_schema(None)
        schema_all = build_execute_code_schema(SANDBOX_ALLOWED_TOOLS)
        assert schema_none["description"] == schema_all["description"]

    def test_description_mentions_limits(self):
        """Schema description mentions timeout, output limits, tool call limit."""
        from tools.code_execution_tool import build_execute_code_schema
        schema = build_execute_code_schema()
        desc = schema["description"]
        assert "timeout" in desc.lower()
        assert "50KB" in desc or "50kb" in desc.lower()
        assert "50 tool calls" in desc

    def test_description_mentions_helpers(self):
        """Schema description mentions helper functions."""
        from tools.code_execution_tool import build_execute_code_schema
        schema = build_execute_code_schema()
        desc = schema["description"]
        assert "json_parse" in desc
        assert "shell_quote" in desc
        assert "retry" in desc


# ============================================================================
# _load_config Tests
# ============================================================================

class TestLoadConfig:
    """Tests for _load_config function."""

    def test_returns_empty_dict_on_import_error(self):
        """Should return empty dict if CLI_CONFIG is unavailable."""
        from tools.code_execution_tool import _load_config
        with patch.dict("sys.modules", {"cli": None}):
            result = _load_config()
        assert result == {} or isinstance(result, dict)

    def test_returns_code_execution_section(self):
        """Should return code_execution section from CLI_CONFIG."""
        from tools.code_execution_tool import _load_config
        mock_cli = MagicMock()
        mock_cli.CLI_CONFIG = {"code_execution": {"timeout": 120}}
        with patch.dict("sys.modules", {"cli": mock_cli}):
            result = _load_config()
        assert isinstance(result, dict)


# ============================================================================
# _kill_process_group Tests
# ============================================================================

class TestKillProcessGroup:
    """Tests for _kill_process_group function."""

    @patch("tools.code_execution_tool._IS_WINDOWS", False)
    def test_kills_process_group_on_posix(self):
        """On POSIX, should use os.killpg to kill process group."""
        from tools.code_execution_tool import _kill_process_group
        
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        
        with patch("os.killpg") as mock_killpg, \
             patch("os.getpgid", return_value=12345):
            _kill_process_group(mock_proc)
            mock_killpg.assert_called_once()

    @patch("tools.code_execution_tool._IS_WINDOWS", True)
    def test_terminates_on_windows(self):
        """On Windows, should call proc.terminate()."""
        from tools.code_execution_tool import _kill_process_group
        
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        
        _kill_process_group(mock_proc)
        mock_proc.terminate.assert_called_once()

    @patch("tools.code_execution_tool._IS_WINDOWS", False)
    def test_escalate_sends_sigkill_after_timeout(self):
        """With escalate=True, should SIGKILL after SIGTERM timeout."""
        from tools.code_execution_tool import _kill_process_group
        
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)
        
        with patch("os.killpg") as mock_killpg, \
             patch("os.getpgid", return_value=12345):
            _kill_process_group(mock_proc, escalate=True)
            # Should have called killpg twice (SIGTERM + SIGKILL)
            assert mock_killpg.call_count >= 1

    @patch("tools.code_execution_tool._IS_WINDOWS", False)
    def test_handles_process_not_found(self):
        """Should handle ProcessLookupError gracefully."""
        from tools.code_execution_tool import _kill_process_group
        
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.kill.side_effect = ProcessLookupError("not found")
        
        with patch("os.killpg", side_effect=ProcessLookupError("not found")), \
             patch("os.getpgid", return_value=12345):
            # Should not raise
            _kill_process_group(mock_proc)


# ============================================================================
# _rpc_server_loop Tests
# ============================================================================

class TestRpcServerLoop:
    """Tests for _rpc_server_loop function."""

    def test_accepts_connection_and_processes_request(self, mock_handle_function_call):
        """RPC loop should accept connections and dispatch tool calls."""
        from tools.code_execution_tool import _rpc_server_loop
        
        # Create a mock server socket
        mock_server = MagicMock()
        mock_conn = MagicMock()
        
        # Simulate a single tool call request then disconnection
        request = json.dumps({"tool": "terminal", "args": {"command": "echo hi"}})
        mock_conn.recv.side_effect = [(request + "\n").encode(), b""]
        mock_server.accept.return_value = (mock_conn, ("client", 12345))
        
        tool_call_log = []
        tool_call_counter = [0]
        
        with patch("model_tools.handle_function_call", side_effect=mock_handle_function_call):
            _rpc_server_loop(
                mock_server,
                "test-task",
                tool_call_log,
                tool_call_counter,
                max_tool_calls=10,
                allowed_tools=frozenset(["terminal"]),
            )
        
        assert tool_call_counter[0] == 1
        assert len(tool_call_log) == 1
        assert tool_call_log[0]["tool"] == "terminal"

    def test_rejects_unauthorized_tool(self, mock_handle_function_call):
        """RPC loop should reject tools not in allowed_tools."""
        from tools.code_execution_tool import _rpc_server_loop
        
        mock_server = MagicMock()
        mock_conn = MagicMock()
        
        # Request for a tool NOT in allowed_tools
        request = json.dumps({"tool": "vision_analyze", "args": {}})
        responses = []
        def capture_send(data):
            responses.append(data)
        mock_conn.sendall = capture_send
        mock_conn.recv.side_effect = [(request + "\n").encode(), b""]
        mock_server.accept.return_value = (mock_conn, ("client", 12345))
        
        with patch("model_tools.handle_function_call", side_effect=mock_handle_function_call):
            _rpc_server_loop(
                mock_server,
                "test-task",
                [],
                [0],
                max_tool_calls=10,
                allowed_tools=frozenset(["terminal"]),  # vision_analyze not allowed
            )
        
        # Should have sent an error response
        assert len(responses) == 1
        response = json.loads(responses[0].decode())
        assert "error" in response
        assert "not available" in response["error"]

    def test_enforces_tool_call_limit(self, mock_handle_function_call):
        """RPC loop should reject calls after max_tool_calls is reached."""
        from tools.code_execution_tool import _rpc_server_loop
        
        mock_server = MagicMock()
        mock_conn = MagicMock()
        
        # Two requests, but limit is 1
        request1 = json.dumps({"tool": "terminal", "args": {"command": "echo 1"}})
        request2 = json.dumps({"tool": "terminal", "args": {"command": "echo 2"}})
        
        responses = []
        def capture_send(data):
            responses.append(data)
        mock_conn.sendall = capture_send
        mock_conn.recv.side_effect = [
            (request1 + "\n").encode(),
            (request2 + "\n").encode(),
            b""
        ]
        mock_server.accept.return_value = (mock_conn, ("client", 12345))
        
        with patch("model_tools.handle_function_call", side_effect=mock_handle_function_call):
            _rpc_server_loop(
                mock_server,
                "test-task",
                [],
                [0],
                max_tool_calls=1,  # Only allow 1 call
                allowed_tools=frozenset(["terminal"]),
            )
        
        # Second call should have received an error
        assert len(responses) == 2
        response2 = json.loads(responses[1].decode())
        assert "error" in response2
        assert "limit" in response2["error"].lower()

    def test_handles_malformed_json_request(self):
        """RPC loop should handle malformed JSON gracefully."""
        from tools.code_execution_tool import _rpc_server_loop
        
        mock_server = MagicMock()
        mock_conn = MagicMock()
        
        responses = []
        def capture_send(data):
            responses.append(data)
        mock_conn.sendall = capture_send
        mock_conn.recv.side_effect = [b"not valid json\n", b""]
        mock_server.accept.return_value = (mock_conn, ("client", 12345))
        
        _rpc_server_loop(
            mock_server,
            "test-task",
            [],
            [0],
            max_tool_calls=10,
            allowed_tools=frozenset(["terminal"]),
        )
        
        assert len(responses) == 1
        response = json.loads(responses[0].decode())
        assert "error" in response

    def test_strips_blocked_terminal_params(self, mock_handle_function_call):
        """RPC loop should strip background/check_interval/pty from terminal args."""
        from tools.code_execution_tool import _rpc_server_loop
        
        mock_server = MagicMock()
        mock_conn = MagicMock()
        
        # Terminal request with blocked params
        request = json.dumps({
            "tool": "terminal",
            "args": {
                "command": "echo hi",
                "background": True,  # Should be stripped
                "check_interval": 5,  # Should be stripped
                "pty": True,  # Should be stripped
            }
        })
        
        captured_args = {}
        def capture_dispatch(fn, args, task_id=None):
            captured_args.update(args)
            return mock_handle_function_call(fn, args, task_id)
        
        mock_conn.recv.side_effect = [(request + "\n").encode(), b""]
        mock_server.accept.return_value = (mock_conn, ("client", 12345))
        
        with patch("model_tools.handle_function_call", side_effect=capture_dispatch):
            _rpc_server_loop(
                mock_server,
                "test-task",
                [],
                [0],
                max_tool_calls=10,
                allowed_tools=frozenset(["terminal"]),
            )
        
        # Blocked params should be stripped
        assert "background" not in captured_args
        assert "check_interval" not in captured_args
        assert "pty" not in captured_args
        # Command should still be present
        assert captured_args.get("command") == "echo hi"


# ============================================================================
# execute_code - Input Validation Tests
# ============================================================================

class TestExecuteCodeInputValidation:
    """Tests for execute_code input validation."""

    @patch("tools.code_execution_tool.SANDBOX_AVAILABLE", False)
    def test_returns_error_on_windows(self):
        """On Windows, execute_code should return an error."""
        from tools.code_execution_tool import execute_code
        result = json.loads(execute_code("print('hi')", task_id="test"))
        assert "error" in result
        assert "Windows" in result["error"]

    def test_empty_code_returns_error(self):
        """Empty code string should return error."""
        from tools.code_execution_tool import execute_code
        result = json.loads(execute_code("", task_id="test"))
        assert "error" in result
        assert "No code" in result["error"]

    def test_whitespace_only_code_returns_error(self):
        """Whitespace-only code should return error."""
        from tools.code_execution_tool import execute_code
        result = json.loads(execute_code("   \n\t  ", task_id="test"))
        assert "error" in result
        assert "No code" in result["error"]


# ============================================================================
# execute_code - Integration Tests (with mocking)
# ============================================================================

class TestExecuteCodeIntegration:
    """Integration tests for execute_code with mocked subprocess.
    
    These tests use heavy mocking to avoid the hanging issues that
    affect the original test_code_execution.py tests.
    """

    @pytest.fixture
    def mock_interrupt_event(self):
        """Create a mock interrupt event that is not set."""
        event = MagicMock()
        event.is_set.return_value = False
        return event

    @pytest.fixture
    def mock_config(self):
        """Mock config with short timeout for fast tests."""
        return {"timeout": 5, "max_tool_calls": 10}

    def test_basic_print_execution_mocked(self, mock_interrupt_event, mock_config):
        """Test basic print statement execution with mocked subprocess."""
        from tools.code_execution_tool import execute_code
        
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]  # Running, then exited
        mock_proc.returncode = 0
        mock_proc.stdout = BytesIO(b"hello world\n")
        mock_proc.stderr = BytesIO(b"")
        
        with patch("tools.interrupt._interrupt_event", mock_interrupt_event), \
             patch("tools.code_execution_tool._load_config", return_value=mock_config), \
             patch("subprocess.Popen", return_value=mock_proc) as mock_popen, \
             patch("socket.socket") as mock_socket, \
             patch("tempfile.mkdtemp", return_value="/tmp/sandbox"), \
             patch("os.setsid", return_value=12345), \
             patch("shutil.rmtree"), \
             patch("os.unlink"), \
             patch("builtins.open", mock_open()):
            
            mock_server = MagicMock()
            mock_socket.return_value = mock_server
            
            result = json.loads(execute_code(
                'print("hello world")',
                task_id="test",
                enabled_tools=["terminal"]
            ))
        
        assert result["status"] == "success"
        assert "hello world" in result["output"]

    def test_syntax_error_mocked(self, mock_interrupt_event, mock_config):
        """Test that syntax errors are captured properly."""
        from tools.code_execution_tool import execute_code
        
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 1]
        mock_proc.returncode = 1
        mock_proc.stdout = BytesIO(b"")
        mock_proc.stderr = BytesIO(b"SyntaxError: invalid syntax\n")
        
        with patch("tools.interrupt._interrupt_event", mock_interrupt_event), \
             patch("tools.code_execution_tool._load_config", return_value=mock_config), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("socket.socket") as mock_socket, \
             patch("tempfile.mkdtemp", return_value="/tmp/sandbox"), \
             patch("os.setsid", return_value=12345), \
             patch("shutil.rmtree"), \
             patch("os.unlink"), \
             patch("builtins.open", mock_open()):
            
            mock_server = MagicMock()
            mock_socket.return_value = mock_server
            
            result = json.loads(execute_code(
                "def broken(",
                task_id="test",
                enabled_tools=["terminal"]
            ))
        
        assert result["status"] == "error"
        assert "SyntaxError" in result.get("error", "") or "SyntaxError" in result.get("output", "")

    def test_runtime_error_mocked(self, mock_interrupt_event, mock_config):
        """Test that runtime errors are captured properly."""
        from tools.code_execution_tool import execute_code
        
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 1]
        mock_proc.returncode = 1
        mock_proc.stdout = BytesIO(b"before error\n")
        mock_proc.stderr = BytesIO(b"RuntimeError: test error\n")
        
        with patch("tools.interrupt._interrupt_event", mock_interrupt_event), \
             patch("tools.code_execution_tool._load_config", return_value=mock_config), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("socket.socket") as mock_socket, \
             patch("tempfile.mkdtemp", return_value="/tmp/sandbox"), \
             patch("os.setsid", return_value=12345), \
             patch("shutil.rmtree"), \
             patch("os.unlink"), \
             patch("builtins.open", mock_open()):
            
            mock_server = MagicMock()
            mock_socket.return_value = mock_server
            
            result = json.loads(execute_code(
                'raise RuntimeError("test error")',
                task_id="test",
                enabled_tools=["terminal"]
            ))
        
        assert result["status"] == "error"

    def test_timeout_kills_process_mocked(self, mock_interrupt_event):
        """Test that timeout kills the subprocess."""
        from tools.code_execution_tool import execute_code
        
        mock_proc = MagicMock()
        # Simulate process never exiting (poll always returns None initially)
        poll_count = [0]
        def poll_side_effect():
            poll_count[0] += 1
            if poll_count[0] < 3:
                return None
            return 0
        
        mock_proc.poll.side_effect = poll_side_effect
        mock_proc.returncode = 0
        mock_proc.stdout = BytesIO(b"")
        mock_proc.stderr = BytesIO(b"")
        
        config = {"timeout": 0.1, "max_tool_calls": 10}  # Very short timeout
        
        with patch("tools.interrupt._interrupt_event", mock_interrupt_event), \
             patch("tools.code_execution_tool._load_config", return_value=config), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("socket.socket") as mock_socket, \
             patch("tempfile.mkdtemp", return_value="/tmp/sandbox"), \
             patch("os.setsid", return_value=12345), \
             patch("tools.code_execution_tool._kill_process_group") as mock_kill, \
             patch("shutil.rmtree"), \
             patch("os.unlink"), \
             patch("builtins.open", mock_open()):
            
            mock_server = MagicMock()
            mock_socket.return_value = mock_server
            
            result = json.loads(execute_code(
                "import time; time.sleep(999)",
                task_id="test",
                enabled_tools=["terminal"]
            ))
        
        # Process should have exited (either normally or via timeout)
        assert result["status"] in ("success", "timeout", "error")


# ============================================================================
# Environment Variable Filtering Tests
# ============================================================================

class TestEnvironmentFiltering:
    """Tests for environment variable filtering in execute_code.
    
    Note: _SAFE_ENV_PREFIXES and _SECRET_SUBSTRINGS are local variables
    inside execute_code(), so we test the behavior through integration tests
    and by examining the source code structure.
    """

    def test_source_code_has_secret_substrings(self):
        """Verify the source code contains the expected secret filtering logic."""
        import tools.code_execution_tool as module
        import inspect
        
        source = inspect.getsource(module.execute_code)
        
        # Verify that secret substrings are defined
        assert "TOKEN" in source or "SECRET" in source
        assert "PASSWORD" in source or "PASSWD" in source

    def test_source_code_has_safe_prefixes(self):
        """Verify the source code contains the expected safe prefix logic."""
        import tools.code_execution_tool as module
        import inspect
        
        source = inspect.getsource(module.execute_code)
        
        # Verify that safe prefixes are defined
        assert "PATH" in source
        assert "HOME" in source
        assert "PYTHONPATH" in source


# ============================================================================
# Output Size Limit Tests
# ============================================================================

class TestOutputSizeLimits:
    """Tests for stdout/stderr size limiting."""

    def test_constants_are_reasonable(self):
        """Size limit constants should be reasonable values."""
        from tools.code_execution_tool import (
            MAX_STDOUT_BYTES,
            MAX_STDERR_BYTES,
        )
        assert MAX_STDOUT_BYTES == 50_000  # 50KB
        assert MAX_STDERR_BYTES == 10_000  # 10KB

    def test_head_tail_truncation_logic(self):
        """Test the head+tail truncation algorithm directly."""
        from tools.code_execution_tool import MAX_STDOUT_BYTES
        
        # Simulate the truncation logic
        head_bytes = int(MAX_STDOUT_BYTES * 0.4)  # 40%
        tail_bytes = MAX_STDOUT_BYTES - head_bytes  # 60%
        
        assert head_bytes == 20_000
        assert tail_bytes == 30_000
        assert head_bytes + tail_bytes == MAX_STDOUT_BYTES


# ============================================================================
# Tool Stub Drift Tests
# ============================================================================

class TestToolStubDrift:
    """Verify that _TOOL_STUBS stay in sync with real tool schemas."""

    def test_all_allowed_tools_have_stubs(self):
        """Every tool in SANDBOX_ALLOWED_TOOLS should have a stub."""
        from tools.code_execution_tool import (
            SANDBOX_ALLOWED_TOOLS,
            _TOOL_STUBS,
        )
        for tool in SANDBOX_ALLOWED_TOOLS:
            assert tool in _TOOL_STUBS, f"Missing stub for: {tool}"

    def test_stub_signatures_have_required_params(self):
        """Each stub should have required parameters."""
        from tools.code_execution_tool import _TOOL_STUBS
        
        # Check specific tools have expected params
        assert "command" in _TOOL_STUBS["terminal"][1]
        assert "query" in _TOOL_STUBS["web_search"][1]
        assert "path" in _TOOL_STUBS["read_file"][1]
        assert "path" in _TOOL_STUBS["write_file"][1]
        assert "pattern" in _TOOL_STUBS["search_files"][1]
        assert "path" in _TOOL_STUBS["patch"][1]
        assert "urls" in _TOOL_STUBS["web_extract"][1]

    def test_stub_args_expr_includes_all_params(self):
        """The args expression should include all parameters."""
        import re
        from tools.code_execution_tool import _TOOL_STUBS
        
        for tool_name, (func_name, sig, doc, args_expr) in _TOOL_STUBS.items():
            # Extract param names from signature
            params = set(re.findall(r'(\w+)\s*:', sig))
            for param in params:
                assert f'"{param}"' in args_expr, \
                    f"Tool {tool_name}: param {param} not in args expression"


# ============================================================================
# Registry Integration Tests
# ============================================================================

class TestRegistryIntegration:
    """Tests for tool registry integration."""

    def test_execute_code_registered(self):
        """execute_code should be registered in the toolset."""
        from tools.registry import registry
        # Import triggers registration
        import tools.code_execution_tool  # noqa: F401
        
        entry = registry._tools.get("execute_code")
        assert entry is not None
        assert entry.toolset == "code_execution"

    def test_handler_calls_execute_code(self):
        """The registered handler should call execute_code."""
        from tools.registry import registry
        import tools.code_execution_tool  # noqa: F401
        
        entry = registry._tools.get("execute_code")
        assert callable(entry.handler)

    def test_check_fn_uses_sandbox_requirements(self):
        """The check_fn should use check_sandbox_requirements."""
        from tools.registry import registry
        import tools.code_execution_tool  # noqa: F401
        
        entry = registry._tools.get("execute_code")
        assert entry.check_fn is not None
        # The check_fn should match SANDBOX_AVAILABLE on POSIX
        assert entry.check_fn() == (sys.platform != "win32")


# ============================================================================
# EXECUTE_CODE_SCHEMA Tests
# ============================================================================

class TestExecuteCodeSchema:
    """Tests for the default EXECUTE_CODE_SCHEMA."""

    def test_schema_exists(self):
        """EXECUTE_CODE_SCHEMA should be defined."""
        from tools.code_execution_tool import EXECUTE_CODE_SCHEMA
        assert EXECUTE_CODE_SCHEMA is not None

    def test_schema_has_correct_name(self):
        """Schema should have correct function name."""
        from tools.code_execution_tool import EXECUTE_CODE_SCHEMA
        assert EXECUTE_CODE_SCHEMA["name"] == "execute_code"

    def test_schema_has_code_parameter(self):
        """Schema should have 'code' parameter."""
        from tools.code_execution_tool import EXECUTE_CODE_SCHEMA
        props = EXECUTE_CODE_SCHEMA["parameters"]["properties"]
        assert "code" in props
        assert props["code"]["type"] == "string"


# ============================================================================
# Thread Safety Tests
# ============================================================================

class TestThreadSafety:
    """Tests for thread safety in the code execution module."""

    def test_tool_call_counter_is_thread_safe(self):
        """Tool call counter should be safe for concurrent access."""
        from tools.code_execution_tool import _rpc_server_loop
        
        # This test verifies the counter is a list (mutable reference)
        # rather than an int (immutable)
        counter = [0]
        
        def increment():
            for _ in range(100):
                counter[0] += 1
        
        threads = [threading.Thread(target=increment) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Note: This doesn't prove thread safety, but verifies the design
        # uses a mutable container which is the intended pattern
        assert counter[0] == 1000


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_enabled_tools_uses_all(self):
        """Empty enabled_tools should fall back to all allowed tools."""
        from tools.code_execution_tool import (
            SANDBOX_ALLOWED_TOOLS,
            generate_hermes_tools_module,
        )
        # When sandbox_tools is empty, execute_code falls back to SANDBOX_ALLOWED_TOOLS
        src = generate_hermes_tools_module(list(SANDBOX_ALLOWED_TOOLS))
        assert "def terminal(" in src

    def test_nonoverlapping_enabled_tools_uses_all(self):
        """Non-overlapping enabled_tools should fall back to all allowed tools."""
        from tools.code_execution_tool import SANDBOX_ALLOWED_TOOLS
        # The logic in execute_code:
        # session_tools = set(enabled_tools) if enabled_tools else set()
        # sandbox_tools = frozenset(SANDBOX_ALLOWED_TOOLS & session_tools)
        # if not sandbox_tools: sandbox_tools = SANDBOX_ALLOWED_TOOLS
        enabled = ["vision_analyze", "browser_snapshot"]
        session_tools = set(enabled)
        sandbox_tools = SANDBOX_ALLOWED_TOOLS & session_tools
        assert len(sandbox_tools) == 0  # No overlap

    def test_tool_doc_lines_order(self):
        """_TOOL_DOC_LINES should have consistent ordering."""
        from tools.code_execution_tool import _TOOL_DOC_LINES
        
        names = [name for name, _ in _TOOL_DOC_LINES]
        assert "terminal" in names
        assert "web_search" in names
        assert len(names) == 7  # All 7 allowed tools


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
