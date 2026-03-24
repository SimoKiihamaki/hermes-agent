"""Shared fixtures for the hermes-agent test suite."""

import asyncio
import os
import signal
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def _isolate_hermes_home(tmp_path, monkeypatch):
    """Redirect HERMES_HOME to a temp dir so tests never write to ~/.hermes/."""
    fake_home = tmp_path / "hermes_test"
    fake_home.mkdir()
    (fake_home / "sessions").mkdir()
    (fake_home / "cron").mkdir()
    (fake_home / "memories").mkdir()
    (fake_home / "skills").mkdir()
    monkeypatch.setenv("HERMES_HOME", str(fake_home))
    # Reset plugin singleton so tests don't leak plugins from ~/.hermes/plugins/
    try:
        import hermes_cli.plugins as _plugins_mod
        monkeypatch.setattr(_plugins_mod, "_plugin_manager", None)
    except Exception:
        pass
    # Tests should not inherit the agent's current gateway/messaging surface.
    # Individual tests that need gateway behavior set these explicitly.
    monkeypatch.delenv("HERMES_SESSION_PLATFORM", raising=False)
    monkeypatch.delenv("HERMES_SESSION_CHAT_ID", raising=False)
    monkeypatch.delenv("HERMES_SESSION_CHAT_NAME", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)


# Provider-related environment variables that must be isolated between tests
# to prevent pollution when running with pytest-xdist
PROVIDER_ENV_VARS = (
    "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "GLM_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY",
    "KIMI_API_KEY", "KIMI_BASE_URL", "MINIMAX_API_KEY", "MINIMAX_CN_API_KEY",
    "AI_GATEWAY_API_KEY", "AI_GATEWAY_BASE_URL",
    "KILOCODE_API_KEY", "KILOCODE_BASE_URL",
    "DASHSCOPE_API_KEY", "OPENCODE_ZEN_API_KEY", "OPENCODE_GO_API_KEY",
    "NOUS_API_KEY", "GITHUB_TOKEN", "GH_TOKEN", "COPILOT_GITHUB_TOKEN",
    "OPENAI_BASE_URL", "HERMES_COPILOT_ACP_COMMAND", "COPILOT_CLI_PATH",
    "HERMES_COPILOT_ACP_ARGS", "COPILOT_ACP_BASE_URL",
)


@pytest.fixture(autouse=True)
def _isolate_provider_env(monkeypatch, request):
    """Clear all provider-related environment variables before each test.

    This fixture runs automatically for all tests to prevent environment
    variable pollution between parallel test workers (pytest-xdist).
    """
    for key in PROVIDER_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    # Skip auth store mock for tests that need real auth store access
    # These tests set up their own auth fixtures and need _load_auth_store to work
    needs_real_auth_patterns = (
        "test_auth_",
        "/test_auth_",
        "test_auxiliary_client",  # Codex token reading tests
        "test_vision_tools",      # Vision requirements checks
        "test_tools_config",      # Toolset availability checks
        "test_setup_model_provider",  # Setup auth state checks
    )
    nodeid = request.node.nodeid
    needs_real_auth = any(pattern in nodeid for pattern in needs_real_auth_patterns)
    
    if not needs_real_auth:
        # Mock auth store to prevent file-based state leakage
        monkeypatch.setattr("hermes_cli.auth._load_auth_store", lambda: {})


@pytest.fixture()
def tmp_dir(tmp_path):
    """Provide a temporary directory that is cleaned up automatically."""
    return tmp_path


@pytest.fixture()
def mock_config():
    """Return a minimal hermes config dict suitable for unit tests."""
    return {
        "model": "test/mock-model",
        "toolsets": ["terminal", "file"],
        "max_turns": 10,
        "terminal": {
            "backend": "local",
            "cwd": "/tmp",
            "timeout": 30,
        },
        "compression": {"enabled": False},
        "memory": {"memory_enabled": False, "user_profile_enabled": False},
        "command_allowlist": [],
    }


# ── Global test timeout ─────────────────────────────────────────────────────
# Kill any individual test that takes longer than 30 seconds.
# Prevents hanging tests (subprocess spawns, blocking I/O) from stalling the
# entire test suite.

def _timeout_handler(signum, frame):
    raise TimeoutError("Test exceeded 30 second timeout")

@pytest.fixture(autouse=True)
def _ensure_current_event_loop(request):
    """Provide a default event loop for sync tests that call get_event_loop().

    Python 3.11+ no longer guarantees a current loop for plain synchronous tests.
    A number of gateway tests still use asyncio.get_event_loop().run_until_complete(...).
    Ensure they always have a usable loop without interfering with pytest-asyncio's
    own loop management for @pytest.mark.asyncio tests.
    """
    if request.node.get_closest_marker("asyncio") is not None:
        yield
        return

    # Python 3.12+ deprecates get_event_loop() when no loop is running.
    # Check for running loop first, then fall back to creating a new one.
    try:
        loop = asyncio.get_running_loop()
        created = False
    except RuntimeError:
        # No running loop - create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        created = True

    try:
        yield
    finally:
        if created and loop is not None:
            try:
                loop.close()
            finally:
                asyncio.set_event_loop(None)


@pytest.fixture(autouse=True)
def _enforce_test_timeout():
    """Kill any individual test that takes longer than 30 seconds.
    SIGALRM is Unix-only; skip on Windows."""
    if sys.platform == "win32":
        yield
        return
    old = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(30)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)
