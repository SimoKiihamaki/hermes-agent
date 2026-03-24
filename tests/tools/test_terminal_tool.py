"""Tests for tools/terminal_tool.py — Terminal execution, background processes, PTY mode, timeout handling.

Coverage:
  terminal_tool — command execution, foreground/background, timeout, workdir
  _get_env_config — environment variable parsing, defaults
  _parse_env_var — validation and error handling
  _check_disk_usage_warning — disk space checks
  _transform_sudo_command — sudo password injection
  _handle_sudo_failure — messaging context sudo hints
  _create_environment — environment factory for all backends
  cleanup_vm / cleanup_all_environments — environment lifecycle
  get_active_environments_info — introspection
  register_task_env_overrides / clear_task_env_overrides — per-task config
"""

import json
import os
import sys
import time
import pytest
import subprocess
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

# Ensure parent directory is on path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the terminal_tool module using importlib to get module, not function
import importlib
tt = importlib.import_module('tools.terminal_tool')


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_terminal_state():
    """Reset module state before and after each test."""
    # Clear active environments
    tt._active_environments.clear()
    tt._last_activity.clear()
    tt._creation_locks.clear()
    tt._task_env_overrides.clear()
    # Reset cached sudo password
    tt._cached_sudo_password = ""
    # Stop cleanup thread if running
    tt._stop_cleanup_thread()
    
    yield
    
    # Cleanup after test
    tt._active_environments.clear()
    tt._last_activity.clear()
    tt._creation_locks.clear()
    tt._task_env_overrides.clear()
    tt._stop_cleanup_thread()


@pytest.fixture
def mock_env_local(monkeypatch):
    """Configure terminal for local execution."""
    monkeypatch.setenv("TERMINAL_ENV", "local")
    monkeypatch.delenv("TERMINAL_DOCKER_IMAGE", raising=False)
    monkeypatch.delenv("TERMINAL_MODAL_IMAGE", raising=False)
    monkeypatch.delenv("TERMINAL_TIMEOUT", raising=False)
    monkeypatch.delenv("TERMINAL_CWD", raising=False)


@pytest.fixture
def mock_env_docker(monkeypatch):
    """Configure terminal for Docker execution."""
    monkeypatch.setenv("TERMINAL_ENV", "docker")
    monkeypatch.setenv("TERMINAL_DOCKER_IMAGE", "test/image:latest")


@pytest.fixture
def mock_local_env_instance():
    """Create a mock LocalEnvironment instance."""
    mock_env = MagicMock()
    mock_env.execute.return_value = {"output": "test output", "returncode": 0}
    mock_env.env = os.environ.copy()
    return mock_env


# =============================================================================
# _parse_env_var Tests
# =============================================================================

class TestParseEnvVar:
    """Test suite for _parse_env_var helper."""

    def test_default_value(self, monkeypatch):
        """Returns default when env var not set."""
        monkeypatch.delenv("TEST_VAR", raising=False)
        result = tt._parse_env_var("TEST_VAR", "42", int, "integer")
        assert result == 42

    def test_custom_value(self, monkeypatch):
        """Parses custom value correctly."""
        monkeypatch.setenv("TEST_VAR", "100")
        result = tt._parse_env_var("TEST_VAR", "42", int, "integer")
        assert result == 100

    def test_invalid_int_raises(self, monkeypatch):
        """Raises ValueError for invalid integer."""
        monkeypatch.setenv("TEST_VAR", "not_a_number")
        with pytest.raises(ValueError) as exc_info:
            tt._parse_env_var("TEST_VAR", "42", int, "integer")
        assert "expected integer" in str(exc_info.value).lower()

    def test_json_parsing(self, monkeypatch):
        """Parses JSON arrays correctly."""
        monkeypatch.setenv("TEST_JSON", '["a", "b"]')
        result = tt._parse_env_var("TEST_JSON", "[]", json.loads, "valid JSON")
        assert result == ["a", "b"]

    def test_invalid_json_raises(self, monkeypatch):
        """Raises ValueError for invalid JSON."""
        monkeypatch.setenv("TEST_JSON", "not json")
        with pytest.raises(ValueError) as exc_info:
            tt._parse_env_var("TEST_JSON", "[]", json.loads, "valid JSON")
        assert "expected valid json" in str(exc_info.value).lower()


# =============================================================================
# _get_env_config Tests
# =============================================================================

class TestGetEnvConfig:
    """Test suite for _get_env_config."""

    def test_default_env_type(self, monkeypatch):
        """Defaults to 'local' environment."""
        monkeypatch.delenv("TERMINAL_ENV", raising=False)
        config = tt._get_env_config()
        assert config["env_type"] == "local"

    def test_custom_env_type(self, monkeypatch):
        """Respects TERMINAL_ENV setting."""
        monkeypatch.setenv("TERMINAL_ENV", "docker")
        config = tt._get_env_config()
        assert config["env_type"] == "docker"

    def test_default_timeout(self, monkeypatch):
        """Default timeout is 180 seconds."""
        monkeypatch.delenv("TERMINAL_TIMEOUT", raising=False)
        config = tt._get_env_config()
        assert config["timeout"] == 180

    def test_custom_timeout(self, monkeypatch):
        """Custom timeout is parsed correctly."""
        monkeypatch.setenv("TERMINAL_TIMEOUT", "300")
        config = tt._get_env_config()
        assert config["timeout"] == 300

    def test_default_lifetime(self, monkeypatch):
        """Default lifetime is 300 seconds."""
        monkeypatch.delenv("TERMINAL_LIFETIME_SECONDS", raising=False)
        config = tt._get_env_config()
        assert config["lifetime_seconds"] == 300

    def test_local_cwd_uses_getcwd(self, monkeypatch):
        """Local environment uses os.getcwd() as cwd."""
        monkeypatch.setenv("TERMINAL_ENV", "local")
        monkeypatch.delenv("TERMINAL_CWD", raising=False)
        config = tt._get_env_config()
        assert config["cwd"] == os.getcwd()

    def test_docker_default_cwd(self, monkeypatch):
        """Docker environment defaults to /root."""
        monkeypatch.setenv("TERMINAL_ENV", "docker")
        monkeypatch.delenv("TERMINAL_CWD", raising=False)
        config = tt._get_env_config()
        assert config["cwd"] == "/root"

    def test_ssh_default_cwd(self, monkeypatch):
        """SSH environment defaults to ~."""
        monkeypatch.setenv("TERMINAL_ENV", "ssh")
        monkeypatch.delenv("TERMINAL_CWD", raising=False)
        config = tt._get_env_config()
        assert config["cwd"] == "~"

    def test_ssh_config(self, monkeypatch):
        """SSH config is parsed correctly."""
        monkeypatch.setenv("TERMINAL_ENV", "ssh")
        monkeypatch.setenv("TERMINAL_SSH_HOST", "example.com")
        monkeypatch.setenv("TERMINAL_SSH_USER", "testuser")
        monkeypatch.setenv("TERMINAL_SSH_PORT", "2222")
        config = tt._get_env_config()
        assert config["ssh_host"] == "example.com"
        assert config["ssh_user"] == "testuser"
        assert config["ssh_port"] == 2222

    def test_container_config_defaults(self, monkeypatch):
        """Container resource defaults are sensible."""
        monkeypatch.setenv("TERMINAL_ENV", "docker")
        config = tt._get_env_config()
        assert config["container_cpu"] == 1
        assert config["container_memory"] == 5120  # 5GB
        assert config["container_disk"] == 51200   # 50GB
        assert config["container_persistent"] is True


# =============================================================================
# terminal_tool - Foreground Execution Tests
# =============================================================================

class TestTerminalToolForeground:
    """Test suite for foreground terminal execution."""

    def test_returns_json_string(self, mock_env_local, mock_local_env_instance):
        """Result is always a JSON string."""
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
                "container_cpu": 1,
                "container_memory": 5120,
                "container_disk": 51200,
                "container_persistent": True,
                "docker_volumes": [],
                "docker_mount_cwd_to_workspace": False,
                "docker_forward_env": [],
            }
            result = tt.terminal_tool(command="echo hello")
            assert isinstance(result, str)
            parsed = json.loads(result)
            assert isinstance(parsed, dict)

    def test_successful_command_structure(self, mock_env_local, mock_local_env_instance):
        """Successful command returns proper structure."""
        mock_local_env_instance.execute.return_value = {
            "output": "hello world",
            "returncode": 0
        }
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            result_json = tt.terminal_tool(command="echo 'hello world'")
            result = json.loads(result_json)
            
            assert result["output"] == "hello world"
            assert result["exit_code"] == 0
            assert result["error"] is None

    def test_command_with_nonzero_exit(self, mock_env_local, mock_local_env_instance):
        """Non-zero exit code is captured correctly."""
        mock_local_env_instance.execute.return_value = {
            "output": "error: file not found",
            "returncode": 1
        }
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            result = json.loads(tt.terminal_tool(command="ls /nonexistent"))
            
            assert result["exit_code"] == 1
            assert "error: file not found" in result["output"]

    def test_custom_timeout_parameter(self, mock_env_local, mock_local_env_instance):
        """Custom timeout is passed to environment."""
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            tt.terminal_tool(command="sleep 1", timeout=300)
            
            # Check that timeout was passed to execute
            call_kwargs = mock_local_env_instance.execute.call_args[1]
            assert call_kwargs["timeout"] == 300

    def test_workdir_parameter(self, mock_env_local, mock_local_env_instance):
        """Working directory is passed to environment."""
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            tt.terminal_tool(command="ls", workdir="/home/user")
            
            call_kwargs = mock_local_env_instance.execute.call_args[1]
            assert call_kwargs["cwd"] == "/home/user"

    def test_environment_reuse(self, mock_env_local, mock_local_env_instance):
        """Environment is reused for same task_id."""
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance) as mock_create, \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            
            # First call creates environment
            tt.terminal_tool(command="echo one", task_id="task_123")
            assert mock_create.call_count == 1
            
            # Second call reuses environment
            tt.terminal_tool(command="echo two", task_id="task_123")
            assert mock_create.call_count == 1  # Not called again

    def test_different_task_ids_create_different_envs(self, mock_env_local, mock_local_env_instance):
        """Different task_ids get different environments."""
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance) as mock_create, \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            
            tt.terminal_tool(command="echo one", task_id="task_a")
            tt.terminal_tool(command="echo two", task_id="task_b")
            
            assert mock_create.call_count == 2


# =============================================================================
# terminal_tool - Timeout Handling Tests
# =============================================================================

class TestTerminalToolTimeout:
    """Test suite for timeout handling."""

    def test_timeout_returns_124_exit_code(self, mock_env_local, mock_local_env_instance):
        """Timeout returns exit code 124 (like timeout command)."""
        mock_local_env_instance.execute.side_effect = Exception("timeout exceeded")
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 5,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            result = json.loads(tt.terminal_tool(command="sleep 100", timeout=5))
            
            assert result["exit_code"] == 124
            assert "timed out" in result["error"].lower()

    def test_timeout_error_message_includes_seconds(self, mock_env_local, mock_local_env_instance):
        """Timeout error message includes the timeout value."""
        mock_local_env_instance.execute.side_effect = Exception("Command timeout after 10s")
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 10,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            result = json.loads(tt.terminal_tool(command="slow_cmd", timeout=10))
            
            assert "10" in result["error"]


# =============================================================================
# terminal_tool - Background Process Tests
# =============================================================================

class TestTerminalToolBackground:
    """Test suite for background process execution."""

    def test_background_returns_session_id(self, mock_env_local, mock_local_env_instance):
        """Background execution returns a session_id."""
        mock_session = MagicMock()
        mock_session.id = "proc_test123"
        mock_session.pid = 12345
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}), \
             patch('tools.process_registry.process_registry') as mock_registry:
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            mock_registry.spawn_local.return_value = mock_session
            
            result = json.loads(tt.terminal_tool(
                command="python server.py",
                background=True
            ))
            
            assert "session_id" in result
            assert result["session_id"] == "proc_test123"
            assert result["exit_code"] == 0

    def test_background_includes_pid(self, mock_env_local, mock_local_env_instance):
        """Background execution includes PID."""
        mock_session = MagicMock()
        mock_session.id = "proc_abc"
        mock_session.pid = 54321
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}), \
             patch('tools.process_registry.process_registry') as mock_registry:
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            mock_registry.spawn_local.return_value = mock_session
            
            result = json.loads(tt.terminal_tool(
                command="long_process",
                background=True
            ))
            
            assert result["pid"] == 54321

    def test_background_uses_spawn_local_for_local_env(self, mock_env_local, mock_local_env_instance):
        """Local environment uses spawn_local."""
        mock_session = MagicMock()
        mock_session.id = "proc_local"
        mock_session.pid = 111
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}), \
             patch('tools.process_registry.process_registry') as mock_registry:
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            mock_registry.spawn_local.return_value = mock_session
            
            tt.terminal_tool(command="test", background=True)
            
            mock_registry.spawn_local.assert_called_once()
            mock_registry.spawn_via_env.assert_not_called()

    def test_background_uses_spawn_via_env_for_docker(self, mock_env_docker, mock_local_env_instance):
        """Docker environment uses spawn_via_env."""
        mock_session = MagicMock()
        mock_session.id = "proc_docker"
        mock_session.pid = None  # Remote has no local PID
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}), \
             patch('tools.process_registry.process_registry') as mock_registry:
            mock_config.return_value = {
                "env_type": "docker",
                "cwd": "/root",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "test/image",
            }
            mock_registry.spawn_via_env.return_value = mock_session
            
            tt.terminal_tool(command="test", background=True, task_id="docker_task")
            
            mock_registry.spawn_via_env.assert_called_once()
            mock_registry.spawn_local.assert_not_called()

    def test_background_check_interval_minimum(self, mock_env_local, mock_local_env_instance):
        """Check interval has minimum of 30 seconds."""
        mock_session = MagicMock()
        mock_session.id = "proc_interval"
        mock_session.pid = 222
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}), \
             patch('tools.process_registry.process_registry') as mock_registry:
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            mock_registry.spawn_local.return_value = mock_session
            mock_registry.pending_watchers = []
            
            result = json.loads(tt.terminal_tool(
                command="server",
                background=True,
                check_interval=10  # Below minimum
            ))
            
            assert "check_interval_note" in result
            assert "30" in result["check_interval_note"]

    def test_background_failure_returns_error(self, mock_env_local, mock_local_env_instance):
        """Background spawn failure returns error JSON."""
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}), \
             patch('tools.process_registry.process_registry') as mock_registry:
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            mock_registry.spawn_local.side_effect = RuntimeError("Failed to spawn")
            
            result = json.loads(tt.terminal_tool(
                command="fail",
                background=True
            ))
            
            assert result["exit_code"] == -1
            assert "Failed to start background process" in result["error"]


# =============================================================================
# terminal_tool - PTY Mode Tests
# =============================================================================

class TestTerminalToolPtyMode:
    """Test suite for PTY mode execution."""

    def test_pty_passed_to_spawn_local(self, mock_env_local, mock_local_env_instance):
        """PTY flag is passed to spawn_local."""
        mock_session = MagicMock()
        mock_session.id = "proc_pty"
        mock_session.pid = 333
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}), \
             patch('tools.process_registry.process_registry') as mock_registry:
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            mock_registry.spawn_local.return_value = mock_session
            
            tt.terminal_tool(command="python", background=True, pty=True)
            
            call_kwargs = mock_registry.spawn_local.call_args[1]
            assert call_kwargs["use_pty"] is True

    def test_pty_false_by_default(self, mock_env_local, mock_local_env_instance):
        """PTY is False by default."""
        mock_session = MagicMock()
        mock_session.id = "proc_nopty"
        mock_session.pid = 444
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}), \
             patch('tools.process_registry.process_registry') as mock_registry:
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            mock_registry.spawn_local.return_value = mock_session
            
            tt.terminal_tool(command="test", background=True)
            
            call_kwargs = mock_registry.spawn_local.call_args[1]
            assert call_kwargs["use_pty"] is False


# =============================================================================
# terminal_tool - Security/Guard Tests
# =============================================================================

class TestTerminalToolSecurity:
    """Test suite for security checks and guards."""

    def test_blocked_command_returns_error(self, mock_env_local, mock_local_env_instance):
        """Blocked command returns proper error JSON."""
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={
                 "approved": False,
                 "message": "Command blocked: dangerous pattern detected",
                 "description": "rm -rf detected"
             }):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            result = json.loads(tt.terminal_tool(command="rm -rf /"))
            
            assert result["exit_code"] == -1
            assert result["status"] == "blocked"
            assert "blocked" in result["error"].lower()

    def test_force_bypasses_guards(self, mock_env_local, mock_local_env_instance):
        """force=True bypasses security guards."""
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards') as mock_guards:
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            mock_local_env_instance.execute.return_value = {"output": "done", "returncode": 0}
            
            tt.terminal_tool(command="dangerous_cmd", force=True)
            
            mock_guards.assert_not_called()

    def test_approval_required_status(self, mock_env_local, mock_local_env_instance):
        """Approval required returns proper status."""
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={
                 "approved": False,
                 "status": "approval_required",
                 "message": "Waiting for user approval",
                 "command": "reboot",
                 "description": "system restart",
                 "pattern_key": "reboot_cmd"
             }):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            result = json.loads(tt.terminal_tool(command="reboot"))
            
            assert result["status"] == "approval_required"
            assert result["command"] == "reboot"


# =============================================================================
# _transform_sudo_command Tests
# =============================================================================

class TestTransformSudoCommand:
    """Test suite for sudo command transformation."""

    def test_no_sudo_returns_unchanged(self, monkeypatch):
        """Commands without sudo are returned unchanged."""
        monkeypatch.delenv("SUDO_PASSWORD", raising=False)
        tt._cached_sudo_password = ""
        
        cmd, stdin = tt._transform_sudo_command("ls -la")
        assert cmd == "ls -la"
        assert stdin is None

    def test_sudo_with_env_password(self, monkeypatch):
        """Sudo command uses password from env var."""
        monkeypatch.setenv("SUDO_PASSWORD", "testpass")
        tt._cached_sudo_password = ""
        
        cmd, stdin = tt._transform_sudo_command("sudo ls")
        
        assert "sudo -S -p ''" in cmd
        assert stdin == "testpass\n"

    def test_sudo_with_cached_password(self, monkeypatch):
        """Sudo command uses cached password."""
        monkeypatch.delenv("SUDO_PASSWORD", raising=False)
        tt._cached_sudo_password = "cachedpass"
        
        cmd, stdin = tt._transform_sudo_command("sudo whoami")
        
        assert "sudo -S -p ''" in cmd
        assert stdin == "cachedpass\n"

    def test_no_password_returns_none_stdin(self, monkeypatch):
        """Without password, stdin is None."""
        monkeypatch.delenv("SUDO_PASSWORD", raising=False)
        tt._cached_sudo_password = ""
        
        cmd, stdin = tt._transform_sudo_command("sudo ls")
        
        # Command unchanged when no password
        assert cmd == "sudo ls"
        assert stdin is None

    def test_multiple_sudos_transformed(self, monkeypatch):
        """Multiple sudo occurrences are all transformed."""
        monkeypatch.setenv("SUDO_PASSWORD", "pass")
        tt._cached_sudo_password = ""
        
        cmd, stdin = tt._transform_sudo_command("sudo ls && sudo cat file")
        
        assert cmd.count("sudo -S -p ''") == 2

    def test_does_not_match_sudoers_or_visudo(self, monkeypatch):
        """Doesn't transform 'sudoers' or 'visudo'."""
        monkeypatch.setenv("SUDO_PASSWORD", "pass")
        
        cmd, stdin = tt._transform_sudo_command("cat /etc/sudoers")
        assert "sudo -S -p ''" not in cmd
        
        cmd, stdin = tt._transform_sudo_command("visudo")
        assert "sudo -S -p ''" not in cmd


# =============================================================================
# _handle_sudo_failure Tests
# =============================================================================

class TestHandleSudoFailure:
    """Test suite for sudo failure handling."""

    def test_no_tip_in_non_gateway(self, monkeypatch):
        """No tip added in non-gateway context."""
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        
        output = "sudo: a password is required"
        result = tt._handle_sudo_failure(output, "local")
        
        assert result == output  # Unchanged

    def test_tip_added_in_gateway_context(self, monkeypatch):
        """Tip added for sudo failure in gateway context."""
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "session_123")
        
        output = "sudo: a password is required"
        result = tt._handle_sudo_failure(output, "local")
        
        assert "Tip:" in result
        assert "SUDO_PASSWORD" in result

    def test_handles_various_sudo_errors(self, monkeypatch):
        """Handles various sudo error messages."""
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "session_123")
        
        for error in [
            "sudo: a password is required",
            "sudo: no tty present",
            "sudo: a terminal is required",
        ]:
            result = tt._handle_sudo_failure(error, "local")
            assert "Tip:" in result


# =============================================================================
# Output Truncation Tests
# =============================================================================

class TestOutputTruncation:
    """Test suite for output truncation."""

    def test_long_output_truncated(self, mock_env_local, mock_local_env_instance):
        """Very long output is truncated."""
        # Create output longer than MAX_OUTPUT_CHARS (50000)
        long_output = "x" * 60000
        mock_local_env_instance.execute.return_value = {
            "output": long_output,
            "returncode": 0
        }
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}), \
             patch('agent.redact.redact_sensitive_text', side_effect=lambda x: x):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            result = json.loads(tt.terminal_tool(command="cat bigfile"))
            
            assert "TRUNCATED" in result["output"]
            assert len(result["output"]) < 60000


# =============================================================================
# Environment Cleanup Tests
# =============================================================================

class TestEnvironmentCleanup:
    """Test suite for environment cleanup functions."""

    def test_cleanup_vm_removes_from_active(self, mock_env_local):
        """cleanup_vm removes environment from tracking."""
        mock_env = MagicMock()
        
        tt._active_environments["task_123"] = mock_env
        tt._last_activity["task_123"] = time.time()
        
        tt.cleanup_vm("task_123")
        
        assert "task_123" not in tt._active_environments
        assert "task_123" not in tt._last_activity

    def test_cleanup_vm_calls_cleanup_method(self, mock_env_local):
        """cleanup_vm calls env.cleanup() if available."""
        mock_env = MagicMock()
        mock_env.cleanup = MagicMock()
        
        tt._active_environments["task_456"] = mock_env
        tt._last_activity["task_456"] = time.time()
        
        tt.cleanup_vm("task_456")
        
        mock_env.cleanup.assert_called_once()

    def test_cleanup_vm_handles_stop_method(self, mock_env_local):
        """cleanup_vm calls env.stop() if cleanup not available."""
        mock_env = MagicMock(spec=['stop'])  # Only has stop, not cleanup
        mock_env.stop = MagicMock()
        
        tt._active_environments["task_789"] = mock_env
        tt._last_activity["task_789"] = time.time()
        
        tt.cleanup_vm("task_789")
        
        mock_env.stop.assert_called_once()

    def test_cleanup_all_environments(self, mock_env_local):
        """cleanup_all_environments removes all environments."""
        for i in range(3):
            mock_env = MagicMock()
            mock_env.cleanup = MagicMock()
            tt._active_environments[f"task_{i}"] = mock_env
            tt._last_activity[f"task_{i}"] = time.time()
        
        count = tt.cleanup_all_environments()
        
        assert count == 3
        assert len(tt._active_environments) == 0

    def test_cleanup_nonexistent_task_is_safe(self, mock_env_local):
        """Cleaning up non-existent task is safe."""
        # Should not raise
        tt.cleanup_vm("nonexistent_task")
        assert True


# =============================================================================
# get_active_environments_info Tests
# =============================================================================

class TestGetActiveEnvironmentsInfo:
    """Test suite for environment introspection."""

    def test_empty_environments(self, mock_env_local):
        """Empty environments returns zero count."""
        info = tt.get_active_environments_info()
        
        assert info["count"] == 0
        assert info["task_ids"] == []

    def test_counts_active_environments(self, mock_env_local):
        """Correctly counts active environments."""
        tt._active_environments["task_1"] = MagicMock()
        tt._active_environments["task_2"] = MagicMock()
        tt._last_activity["task_1"] = time.time()
        tt._last_activity["task_2"] = time.time()
        
        info = tt.get_active_environments_info()
        
        assert info["count"] == 2
        assert "task_1" in info["task_ids"]
        assert "task_2" in info["task_ids"]


# =============================================================================
# Task Environment Overrides Tests
# =============================================================================

class TestTaskEnvOverrides:
    """Test suite for per-task environment overrides."""

    def test_register_and_clear_overrides(self):
        """Overrides can be registered and cleared."""
        tt.register_task_env_overrides("task_xyz", {
            "modal_image": "custom/image:latest",
            "cwd": "/custom/dir"
        })
        
        assert "task_xyz" in tt._task_env_overrides
        assert tt._task_env_overrides["task_xyz"]["modal_image"] == "custom/image:latest"
        
        tt.clear_task_env_overrides("task_xyz")
        
        assert "task_xyz" not in tt._task_env_overrides

    def test_overrides_applied_to_terminal_tool(self, mock_env_local, mock_local_env_instance):
        """Task overrides are applied during terminal execution."""
        tt.register_task_env_overrides("override_task", {
            "cwd": "/override/dir"
        })
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance) as mock_create, \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}):
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/default/dir",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            mock_local_env_instance.execute.return_value = {"output": "ok", "returncode": 0}
            
            tt.terminal_tool(command="pwd", task_id="override_task")
            
            # Check that cwd override was used
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["cwd"] == "/override/dir"
        
        tt.clear_task_env_overrides("override_task")


# =============================================================================
# Retry Logic Tests
# =============================================================================

class TestTerminalToolRetry:
    """Test suite for retry logic on transient errors."""

    def test_retries_on_transient_error(self, mock_env_local, mock_local_env_instance):
        """Retries on transient errors."""
        # First call fails, second succeeds
        mock_local_env_instance.execute.side_effect = [
            Exception("Connection reset"),
            {"output": "success", "returncode": 0}
        ]
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}), \
             patch('time.sleep'):  # Speed up test
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            result = json.loads(tt.terminal_tool(command="flaky_cmd"))
            
            assert result["exit_code"] == 0
            assert mock_local_env_instance.execute.call_count == 2

    def test_fails_after_max_retries(self, mock_env_local, mock_local_env_instance):
        """Fails after max retries exhausted."""
        mock_local_env_instance.execute.side_effect = Exception("Persistent error")
        
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', return_value=mock_local_env_instance), \
             patch.object(tt, '_check_all_guards', return_value={"approved": True}), \
             patch('time.sleep'):  # Speed up test
            mock_config.return_value = {
                "env_type": "local",
                "cwd": "/tmp",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "",
            }
            result = json.loads(tt.terminal_tool(command="always_fails"))
            
            assert result["exit_code"] == -1
            assert "failed" in result["error"].lower()


# =============================================================================
# Callback Registration Tests
# =============================================================================

class TestCallbackRegistration:
    """Test suite for callback registration functions."""

    def test_set_sudo_password_callback(self):
        """sudo password callback can be set."""
        def test_callback():
            return "test_pass"
        
        tt.set_sudo_password_callback(test_callback)
        
        assert tt._sudo_password_callback is test_callback

    def test_set_approval_callback(self):
        """approval callback can be set."""
        def test_approval(cmd, desc):
            return "once"
        
        tt.set_approval_callback(test_approval)
        
        assert tt._approval_callback is test_approval


# =============================================================================
# Disk Usage Warning Tests
# =============================================================================

class TestDiskUsageWarning:
    """Test suite for disk usage warning."""

    def test_returns_false_on_error(self, monkeypatch):
        """Returns False when check fails."""
        with patch.object(tt, '_get_scratch_dir', side_effect=Exception("No scratch dir")):
            result = tt._check_disk_usage_warning()
            assert result is False

    def test_returns_false_under_threshold(self, monkeypatch, tmp_path):
        """Returns False when under threshold."""
        monkeypatch.setenv("TERMINAL_DISK_WARNING_GB", "500")
        
        # Create small directory
        hermes_dir = tmp_path / "hermes-test123"
        hermes_dir.mkdir()
        (hermes_dir / "small.txt").write_text("x" * 100)
        
        with patch.object(tt, '_get_scratch_dir', return_value=tmp_path):
            result = tt._check_disk_usage_warning()
            assert result is False


# =============================================================================
# Exception Handling Tests
# =============================================================================

class TestExceptionHandling:
    """Test suite for exception handling."""

    def test_general_exception_returns_error_json(self, mock_env_local):
        """General exceptions return proper error JSON."""
        with patch.object(tt, '_get_env_config', side_effect=RuntimeError("Unexpected error")):
            result = json.loads(tt.terminal_tool(command="test"))
            
            assert result["exit_code"] == -1
            assert result["status"] == "error"
            assert "Failed to execute command" in result["error"]

    def test_import_error_returns_disabled_status(self, mock_env_local, mock_local_env_instance):
        """ImportError returns disabled status."""
        with patch.object(tt, '_get_env_config') as mock_config, \
             patch.object(tt, '_create_environment', side_effect=ImportError("minisweagent not found")):
            mock_config.return_value = {
                "env_type": "docker",
                "cwd": "/root",
                "timeout": 60,
                "lifetime_seconds": 300,
                "docker_image": "test/image",
            }
            
            result = json.loads(tt.terminal_tool(command="test", task_id="import_test"))
            
            assert result["exit_code"] == -1
            assert result["status"] == "disabled"
            assert "mini-swe-agent not available" in result["error"]


# =============================================================================
# check_terminal_requirements Tests
# =============================================================================

class TestCheckTerminalRequirements:
    """Test suite for check_terminal_requirements."""

    def test_local_backend_always_passes(self, monkeypatch):
        """Local backend always passes requirements check."""
        monkeypatch.setenv("TERMINAL_ENV", "local")
        
        assert tt.check_terminal_requirements() is True

    def test_docker_requires_docker_available(self, monkeypatch):
        """Docker backend requires Docker to be available."""
        monkeypatch.setenv("TERMINAL_ENV", "docker")
        
        with patch('tools.terminal_tool.importlib.util.find_spec', return_value=MagicMock()), \
             patch('tools.environments.docker.find_docker', return_value=None):
            assert tt.check_terminal_requirements() is False

    def test_ssh_requires_host_and_user(self, monkeypatch):
        """SSH backend requires host and user config."""
        monkeypatch.setenv("TERMINAL_ENV", "ssh")
        monkeypatch.delenv("TERMINAL_SSH_HOST", raising=False)
        monkeypatch.delenv("TERMINAL_SSH_USER", raising=False)
        
        assert tt.check_terminal_requirements() is False

    def test_unknown_env_type_fails(self, monkeypatch):
        """Unknown environment type fails requirements."""
        monkeypatch.setenv("TERMINAL_ENV", "unknown_backend")
        
        assert tt.check_terminal_requirements() is False


# =============================================================================
# Integration Tests (using actual local execution)
# =============================================================================

class TestTerminalToolIntegration:
    """Integration tests using actual local execution."""

    @pytest.mark.integration
    def test_simple_echo_command(self, mock_env_local):
        """Simple echo command works."""
        result = json.loads(tt.terminal_tool(command="echo 'hello world'"))
        
        assert result["exit_code"] == 0
        assert "hello world" in result["output"]

    @pytest.mark.integration
    def test_command_with_pipe(self, mock_env_local):
        """Piped commands work."""
        result = json.loads(tt.terminal_tool(command="echo 'test' | wc -c"))
        
        assert result["exit_code"] == 0
        # 'test\n' = 5 characters
        assert "5" in result["output"]

    @pytest.mark.integration
    def test_command_exit_code_propagates(self, mock_env_local):
        """Non-zero exit code propagates."""
        result = json.loads(tt.terminal_tool(command="ls /nonexistent_directory_12345"))
        
        assert result["exit_code"] != 0

    @pytest.mark.integration
    def test_workdir_changes_directory(self, mock_env_local, tmp_path):
        """Working directory is changed correctly."""
        result = json.loads(tt.terminal_tool(command="pwd", workdir=str(tmp_path)))
        
        assert result["exit_code"] == 0
        assert str(tmp_path) in result["output"]
